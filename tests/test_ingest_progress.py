"""`ingest` must speak while it works, and the sweep must show a real denominator.

WHY THIS TEST EXISTS
====================
`ingest` was the longest silence left in the tree. `probe_ingest_cost.py` measured
a 120 KB source at 85-98s with only 1.3-3.9s spent outside a provider call — so
the wait is real work the whole way through, there is no idle to remove, and the
only thing left to do about it is say what is happening. A 1.2 MB source is 33
extraction windows against that document's 4, at a sweep cap of 3, i.e. minutes.

Everything under the tool was ALREADY instrumented and still silent:
`AnalysisPipeline.resolve` has called `expect_progress`/`report_progress` since
`anchor`, and on this path both were no-ops purely because no scope was installed
above them. That is the trap `utils/progress.py` documents, and it is why the
scope belongs at the tool: **both fan-outs here are gathers** — the digest's parts
and the extraction sweep's windows — and a scope opened inside either skill leaves
the other one mute.

WHAT IS PINNED, AND WHY BEHAVIOURALLY
=====================================
The counting is spread over three modules (`ingest`, `SourceDigest`,
`SurfaceTheses`) plus the pipeline's pre-existing pair. A grep checks one site
against one constant; only running the tool checks that the SUM of what was
expected equals the sum of what was reported. Both halves of that failure look
fine in the source and are invisible at runtime:

* expecting more than you report → the bar sticks below 100% forever;
* reporting more than you expected → `done` overshoots and a host renders 140%.

The sweep gets its own test because it is the one place in ingestion where the
framework knows the denominator in advance — every window WILL be read, coverage
being the guarantee — so it is the one place a host can show "7 of 33" instead of
an indeterminate wait. And because its detail strings are built from the window
list, they are the likeliest place for the person's own document to end up in a
label a host renders verbatim.

Mock brain throughout: this is about the accounting, not the reasoning.

Run: poetry run pytest tests/test_ingest_progress.py
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.advisor.tools.ingest import (_progress_key,
                                                               ingest)
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.chunking import chunk_text

SHORT_SOURCE = (
    "The team ships fast because nobody waits for review, and the same absence "
    "of review is why the last three outages took a day to explain. Speed is "
    "bought with the ability to say why anything happened."
)

INTENT = "Find the structural trade-offs this material keeps returning to"

#: Terms a host may not render to a person under the silent Advisor. Detail
#: strings are the one part of this seam written FOR a human, and
#: `utils/progress.py` warns a host may show them verbatim.
BANNED = (
    "thesis",
    "antithesis",
    "polarity",
    "tetrad",
    "perspective",
    "nexus",
    "wheel",
    "dialectical",
    "framework",
    "synthesis",
    "digest",
)


def _long_source(kilobytes: int) -> str:
    """A source big enough to force BOTH fan-outs: digest parts and sweep windows.

    Built from one repeated paragraph on purpose. The content does not matter —
    mock brain returns the same DTO whatever it is read — and what does matter is
    that `chunk_text` sees more than `CHUNK_SIZE` characters, so `SourceDigest`
    takes its map/reduce branch and `SurfaceTheses` takes `_extraction_sweep`
    instead of `_extraction_loop`.
    """
    paragraph = (
        "Every control that makes the system trustworthy also makes it slower to "
        "change, and every shortcut that makes it fast to change removes a way of "
        "knowing whether it still works. "
    )
    return (paragraph * ((kilobytes * 1024) // len(paragraph) + 1))[: kilobytes * 1024]


@pytest.fixture
def two_theses(monkeypatch):
    """Force extraction to succeed so the run reaches `AnalysisPipeline`.

    Mock brain returns the SAME DTO every call, so real extraction yields nothing
    that survives its own dedup and every branch here stops at "No theses
    extracted" — which is exactly the branch that never reaches the gathered work.
    The pipeline's steps are the ones that were already instrumented and already
    silent, so a test that cannot reach them cannot show that installing the scope
    at the tool is what lights them up.
    """
    from dialectical_framework.concerns.thesis_extraction import ThesisExtraction
    from dialectical_framework.graph.nodes.statement import Statement

    branch = "dx://taxonomy/System(General.v1)/Viability/Integrity"

    async def fake_resolve(
        self, text="", count=3, focus="", domain_hint="", not_like_these=None
    ):
        out = []
        for name in ("Ship without review", "Review before shipping"):
            stmt = Statement(text=name, meaning=f"{branch}/Separation")
            stmt.commit()
            out.append(stmt)
        return out

    monkeypatch.setattr(ThesisExtraction, "resolve", fake_resolve)


@pytest.fixture
async def collected_progress():
    """Subscribe to `sid:progress` and hand back the bus for one run."""
    bus = GraphEventBus()
    await bus.connect()
    # RESTORE, never clear: the module-level bus is wired once by the
    # session-scoped `di_container` fixture, so `None` here would silently
    # disable progress for every test that ran afterwards.
    previous = progress_module._event_bus
    progress_module.set_event_bus(bus)
    try:
        yield bus
    finally:
        progress_module.set_event_bus(previous)
        await bus.disconnect()


async def _run_ingest_collecting(bus, sid: str, **kwargs) -> list:
    """Run `ingest` under `sid` while draining its progress channel.

    The `scope` is entered around the AWAIT, not around building the coroutine:
    `_publish` drops every event when no sid is in scope, so a factory that left
    the `with` block before anything ran would report "the person saw silence"
    about the harness rather than about the tool.
    """
    received: list = []
    ready = asyncio.Event()

    async def _listen() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            ready.set()
            async for event in subscriber:
                received.append(event.message)

    listener = asyncio.create_task(_listen())
    await ready.wait()
    try:
        with scope(sid):
            await ingest.fn(**kwargs)
        await _drain(received)
    finally:
        listener.cancel()
    return received


async def _drain(received: list, *, timeout: float = 5.0) -> None:
    """Wait until `received` stops growing (mirrors `test_anchor_progress.py`).

    Not a fixed sleep: publishes are fire-and-forget `create_task`s, and a fixed
    interval passes on an idle machine while dropping the closing event under
    load — which reads as a missing `final` rather than as flake.
    """
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


def _assert_accounting_closes(events: list, *, branch: str) -> None:
    assert events, f"{branch}: not one progress event — the person saw silence"

    finals = [e for e in events if e.final]
    # Notes are not steps and must be excluded from every count below — that is the
    # whole reason `ProgressEvent.note` exists rather than the digest's completions
    # riding on `report_progress`. If a note ever reached `steps`, `done` would
    # overshoot `total` and both assertions at the end of this helper would fire.
    notes = [e for e in events if e.note and not e.final]
    steps = [e for e in events if not e.final and not e.note]

    assert len(finals) == 1, (
        f"{branch}: expected exactly one closing event, got {len(finals)} —"
        " a host clears its indicator on `final`"
    )
    final = finals[0]
    assert final.stage == "ingest"

    # One non-None key, shared by every event of this run. `execute_tools()` runs a
    # tool round concurrently, so two `ingest` calls in one round publish two
    # interleaved streams under the same sid and stage; the key is the only thing
    # that lets a host tell them apart instead of clearing its indicator on the
    # first `final` while the second is still reading.
    keys = {e.key for e in events}
    assert keys != {None}, f"{branch}: progress published with no key"
    assert len(keys) == 1, f"{branch}: one run published several keys: {keys}"

    assert steps, f"{branch}: only the closing event fired; no stage announced itself"

    # THE claim: everything expected was reported, and nothing extra was.
    assert final.done == final.total, (
        f"{branch}: closed at {final.done}/{final.total} — some site called"
        " `expect_progress` for work no site reports, so the bar can never fill"
    )
    assert len(steps) == final.total, (
        f"{branch}: {len(steps)} step(s) reported against a declared total of"
        f" {final.total} — a site reports work it never expected, so `done`"
        " overshoots and a host renders past 100%"
    )

    for i, event in enumerate(steps):
        assert event.done == i, f"{branch}: step {i} reported done={event.done}"
        assert event.done <= event.total, (
            f"{branch}: {event.done}/{event.total} mid-run — `done` overtook"
            " `total`, which reads as more than everything"
        )

    # A note must be free: it says something happened and moves no counter. The
    # ordering claim above is what breaks if one ever does, but it breaks with a
    # confusing message, so check the property directly where it is stated.
    for event in notes:
        assert event.done <= event.total, (
            f"{branch}: a note reported {event.done}/{event.total} — notes are"
            " supposed to carry the counters untouched"
        )
        assert event.stage == "ingest" and event.key is not None


@pytest.mark.llm
@pytest.mark.asyncio
async def test_a_source_that_fits_one_prompt_reports_and_the_total_closes(
    collected_progress, two_theses
):
    """The cheap branch: no digest fan-out, no sweep, one extraction pass.

    Runs all the way into `AnalysisPipeline`, which is the point: its steps were
    instrumented for `anchor` and were no-ops here purely because no scope was
    installed above them, and the expansions run inside a `gather` created by the
    tool. A scope opened lower down would leave them silent while the cheap
    capture steps above still spoke.
    """
    case = Case()
    case.commit()

    events = await _run_ingest_collecting(
        collected_progress, case.sid, text=SHORT_SOURCE, intent=INTENT
    )
    _assert_accounting_closes(events, branch="single-window")

    details = [e.detail for e in events if not e.final]
    assert "Taking in the material" in details, (
        "the capture step never announced itself — it is the first thing that"
        " happens and the person's own paste is what it acknowledges"
    )
    assert "Looking for what genuinely pushes back" in details, (
        "the pipeline never spoke — this is the pre-existing instrumentation that"
        " the tool-level scope exists to light up"
    )
    assert any("overreaches" in d for d in details), (
        "the tetrad-generation step never announced itself — it runs inside"
        " `AnalysisPipeline`'s gather, so this is what a mis-placed scope breaks"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_a_source_too_big_for_one_prompt_reports_both_fan_outs(
    collected_progress,
):
    """The branch the scope placement exists for.

    Both fan-outs here are `gather`s created inside the tool: `SourceDigest`'s
    parts and `SurfaceTheses`' windows. A scope opened inside either skill would
    leave the other silent, and this is the only test that would catch it —
    everything asserting on the scope OBJECT still passes when the scope is in the
    wrong place.
    """
    source = _long_source(120)
    parts = len(chunk_text(source))
    assert parts > 1, "the harness must actually force the multi-part branch"

    case = Case()
    case.commit()

    events = await _run_ingest_collecting(
        collected_progress, case.sid, text=source, intent=INTENT
    )
    _assert_accounting_closes(events, branch="swept")

    details = [e.detail for e in events if not e.final]
    assert f"Reading part 1 of {parts}" in details, (
        "no part reading announced itself — `SourceDigest` fans out inside a"
        " gather, so this is what a mis-placed scope breaks first"
    )
    assert f"Combining {parts} readings into one understanding" in details
    assert any(d.startswith("Reading section 1 of ") for d in details), (
        "the extraction sweep never announced a window — it is the longest"
        " single phase on this path"
    )
    # The notes reach the bus too, and only an end-to-end run shows it: the scope
    # they publish under is installed at the TOOL, and `note_progress` reads the
    # same ContextVar with the same "a task created before the scope sees nothing"
    # trap. Their own accounting is checked at the concern
    # (`TestTheDigestSaysWhenAPartComesBack`); what is asserted here is that they
    # arrive at all, on the channel, alongside the steps.
    assert f"{parts} of {parts} parts read" in [e.detail for e in events if e.note], (
        "no part completion reached the progress channel — the digest's gathered"
        " parts are the widest hole on this path and the notes are the only thing"
        " that speaks during them"
    )


@pytest.mark.llm
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kilobytes", [None, 120], ids=["single-window", "swept"]
)
async def test_no_detail_string_names_the_machinery(collected_progress, kilobytes):
    """A host may render `detail` verbatim, including under the silent Advisor.

    BOTH branches, because they share almost no strings: the digest's map/reduce
    pair and the sweep's per-window line only exist on the long one, and running
    the short source alone left them unchecked.
    """
    case = Case()
    case.commit()

    events = await _run_ingest_collecting(
        collected_progress,
        case.sid,
        text=SHORT_SOURCE if kilobytes is None else _long_source(kilobytes),
        intent=INTENT,
    )

    steps = [e for e in events if not e.final]
    # Without this the loop below iterates nothing and the test cannot fail.
    assert steps, "no step events to inspect; this test would pass vacuously"

    for event in steps:
        lowered = event.detail.lower()
        leaked = [term for term in BANNED if term in lowered]
        assert not leaked, f"progress detail leaked {leaked}: {event.detail!r}"


@pytest.mark.llm
@pytest.mark.asyncio
async def test_no_detail_string_carries_the_persons_document(collected_progress):
    """Indices, never content.

    On every other progress path the "unit of work" is something the framework
    made up. Here it is a window of the person's own file, and the natural way to
    write a useful label — naming what is being read — would paste 40,000
    characters of it into an event a host may render.
    """
    source = _long_source(120)
    case = Case()
    case.commit()

    events = await _run_ingest_collecting(
        collected_progress, case.sid, text=source, intent=INTENT
    )

    # A distinctive phrase from the source, long enough that an accidental match
    # would have to be an actual leak.
    fingerprint = "removes a way of knowing"
    assert fingerprint in source
    for event in events:
        assert fingerprint not in event.detail, (
            f"a progress detail quoted the source: {event.detail[:120]!r}"
        )
        # Nothing here should be long enough to hold a window either way.
        assert len(event.detail) < 200, f"suspiciously long detail: {len(event.detail)}"


class TestTheSweepsDenominatorIsTheWindowCount:
    """The sweep's counter, tested on the sweep rather than through the tool.

    Through `ingest` the denominator is a sum over five sites and the window count
    is one addend, so an off-by-one here would still close. Driving `_sweep_windows`
    directly is the only way to assert the number a host would render as "7 of 33"
    is the number of windows.

    DB-free: `extract_candidates` is replaced, and nothing else in this method
    touches the graph.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    @pytest.mark.asyncio
    async def test_every_window_is_declared_and_reported(self, monkeypatch):
        from dialectical_framework.agents.analyst.skills import surface_theses
        from dialectical_framework.concerns.thesis_extraction import \
            ThesisExtraction
        from dialectical_framework.utils.progress import progress_scope

        async def fake_extract(self, *, text, count, focus, not_like_these):
            return ["Speed against explainability"]

        monkeypatch.setattr(ThesisExtraction, "extract_candidates", fake_extract)

        skill = surface_theses.SurfaceTheses(intent=INTENT)
        windows = [f"window {i}" for i in range(7)]

        # Captured rather than read off the bus: this test is about the strings and
        # the denominator, and a bus would add a drain and a sid to a case that
        # needs neither. Note `scope.done` therefore stays 0 here — the second test
        # is the one that checks the counter moves.
        reported: list[str] = []
        monkeypatch.setattr(
            surface_theses, "report_progress", lambda detail: reported.append(detail)
        )

        with progress_scope("ingest") as progress:
            await skill._sweep_windows(
                windows=windows,
                focus="",
                target_count=3,
                not_like_these=[],
                reports=[],
            )
            assert progress.total == len(windows), (
                f"declared {progress.total} for {len(windows)} windows — the one"
                " denominator on this path that is known in advance"
            )

        assert reported == [
            f"Reading section {i} of {len(windows)} for tensions"
            for i in range(1, len(windows) + 1)
        ], (
            "windows must report in document order with a 1-based index: `gather`"
            f" preserves argument order, so a host can trust it. Got: {reported}"
        )

    @pytest.mark.asyncio
    async def test_a_second_sweep_adds_to_the_denominator(self, monkeypatch):
        """The zero-candidate retry re-reads every window, which is more work.

        `expect_progress` is additive on purpose (`utils/progress.py`), and this is
        the site where that choice is visible: assignment would make the retry
        look like the first sweep starting over, and the person would watch a bar
        that had reached the end go back to the beginning.
        """
        from dialectical_framework.concerns.thesis_extraction import \
            ThesisExtraction
        from dialectical_framework.utils.progress import progress_scope

        async def fake_extract(self, *, text, count, focus, not_like_these):
            return []

        monkeypatch.setattr(ThesisExtraction, "extract_candidates", fake_extract)

        from dialectical_framework.agents.analyst.skills.surface_theses import \
            SurfaceTheses

        skill = SurfaceTheses(intent=INTENT)
        windows = [f"window {i}" for i in range(4)]

        with progress_scope("ingest") as progress:
            for _ in range(2):
                await skill._sweep_windows(
                    windows=windows,
                    focus="",
                    target_count=3,
                    not_like_these=[],
                    reports=[],
                )
            assert progress.total == 2 * len(windows)
            assert progress.done == 2 * len(windows)

    @pytest.mark.asyncio
    async def test_the_broader_retry_says_so(self, monkeypatch):
        """Same window, second reading — the label has to say which pass it is.

        The retry re-reads every window, so with one shared string a person sees
        "section 1 of 4" twice and reads it as the work having looped rather than
        widened. This is the only place in ingestion where the same unit of work is
        legitimately announced twice.
        """
        from dialectical_framework.agents.analyst.skills import surface_theses
        from dialectical_framework.concerns.thesis_extraction import \
            ThesisExtraction
        from dialectical_framework.utils.progress import progress_scope

        async def fake_extract(self, *, text, count, focus, not_like_these):
            return []

        monkeypatch.setattr(ThesisExtraction, "extract_candidates", fake_extract)

        reported: list[str] = []
        monkeypatch.setattr(
            surface_theses, "report_progress", lambda detail: reported.append(detail)
        )

        skill = surface_theses.SurfaceTheses(intent=INTENT)
        with progress_scope("ingest"):
            await skill._sweep_windows(
                windows=["a", "b"],
                focus="",
                target_count=3,
                not_like_these=[],
                reports=[],
                broader=True,
            )

        assert reported == [
            "Reading section 1 of 2 again, more broadly",
            "Reading section 2 of 2 again, more broadly",
        ], reported


class TestTheProgressKeySeparatesConcurrentIngests:
    """The key's two properties, asserted on the key.

    Racing two real `ingest` calls would also race two graph write sequences
    through GQLAlchemy, which is not concurrency-safe (CLAUDE.md) — any flake that
    produced would be blamed on progress. The single-run tests above already
    assert the key reaches the events.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def test_different_material_gets_different_keys(self):
        assert _progress_key(SHORT_SOURCE, None) != _progress_key("Other text", None)
        assert _progress_key(None, ["abc123"]) != _progress_key(None, ["def456"])
        assert _progress_key(SHORT_SOURCE, None) != _progress_key(
            SHORT_SOURCE, ["abc123"]
        )

    def test_the_same_material_gets_a_stable_key(self):
        """Stable across a retry of the same call, so a host does not see the work
        restart under a new id."""
        assert _progress_key(SHORT_SOURCE, ["abc"]) == _progress_key(
            SHORT_SOURCE, ["abc"]
        )

    def test_the_key_does_not_carry_the_persons_document(self):
        """A host may render the key. On this path the material is a whole file."""
        key = _progress_key(SHORT_SOURCE, None)
        assert "review" not in key.lower()
        assert len(key) == 10, "a rendered key should stay short as well as opaque"


class TestOneLabelNeverCoversAGatheredFanOut:
    """The two holes the LIVE run found, pinned at the sites that closed them.

    `tests/e2e/probe_ingest_progress.py` measured both against a real provider,
    and they are the same defect at two scales: a phase announces itself ONCE
    and then runs a gather, so the label stays on screen for the whole fan-out.
    A mock brain cannot show that — every call returns instantly, so the hole
    has no duration — which is why the numbers below come from the probe and the
    assertions here are about WHERE the steps are declared.

    Both are checked on the concern rather than through `ingest`, for the reason
    `TestTheSweepsDenominatorIsTheWindowCount` gives: through the tool these are
    two addends in a sum over seven sites, and a step lost here would still
    close. It also matters that the `two_theses` fixture PATCHES
    `ThesisExtraction.resolve`, so no test that runs the whole tool reaches the
    first of these two sites at all.

    DB-free where it can be: the second class needs real `Statement`s, so it
    keeps the graph fixtures.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    @pytest.mark.asyncio
    async def test_the_single_window_path_announces_its_classify_phase(
        self, monkeypatch
    ):
        """The common chat case, and it was the widest progress gap of the 1 KB run.

        `_extraction_loop` says "Reading the material for tensions" once and then
        runs extraction, the step-2 gate AND classification under it — 12.2s of a
        45.5s wall. `_extraction_sweep` has always split the last one out, so the
        person who pasted a paragraph was told less than the person who uploaded a
        file. Asserting the COUNT in the label matters as much as the label: it is
        what makes the step a report of this run rather than a fixed string.
        """
        from dialectical_framework.concerns import thesis_extraction
        from dialectical_framework.concerns.thesis_extraction import ThesisExtraction
        from dialectical_framework.utils.progress import progress_scope

        async def fake_extract(self, *, text, count, focus, not_like_these):
            self._text = text
            self._count = count
            return ["Speed against explainability", "Review against throughput"]

        classified: list[list[tuple[str, str]]] = []

        async def fake_classify(self, pairs, *, domain_hint=""):
            classified.append(list(pairs))
            return []

        monkeypatch.setattr(ThesisExtraction, "extract_candidates", fake_extract)
        monkeypatch.setattr(ThesisExtraction, "classify_candidates", fake_classify)

        reported: list[str] = []
        monkeypatch.setattr(
            thesis_extraction, "report_progress", lambda detail: reported.append(detail)
        )

        with progress_scope("ingest") as progress:
            await ThesisExtraction().resolve(text=SHORT_SOURCE, count=2)
            assert progress.total == 1, (
                "exactly one step for the classify phase — extraction is the"
                " caller's step and the step-2 gate stays inside it"
            )

        assert reported == ["Placing 2 candidate tension(s)"], (
            "the label must match the sweep's wording verbatim, so the person"
            " cannot tell how large their source was from the vocabulary, and it"
            f" must carry the real candidate count. Got: {reported}"
        )
        assert classified, "the step must be declared BEFORE the work, not after"

    @pytest.mark.asyncio
    async def test_the_opposition_chain_subdivides_inside_the_gather(
        self, monkeypatch
    ):
        """`find_polarities` gathers ten of these chains; per-thesis links stagger.

        This is the 14.4s hole — the widest that survived the 120 KB run — and it
        is the case where reporting at the gather CANNOT help: all ten tasks start
        at the same instant, so ten events would land on the same timestamp and
        the silence would be unchanged. Links 2 and 3 fire only when link 1 of
        that thesis has returned, which is what spreads them out.
        """
        from dialectical_framework.concerns import antithesis_extraction
        from dialectical_framework.concerns.antithesis_extraction import \
            AntithesisExtraction
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.utils.progress import progress_scope

        order: list[str] = []

        async def fake_taxonomy(self, thesis):
            order.append("link1")
            return None

        async def fake_candidates(self, thesis, taxonomy):
            order.append("link2")
            return []

        async def fake_persist(self, thesis, selected):
            order.append("link3")
            return []

        monkeypatch.setattr(
            AntithesisExtraction, "_contextualize_taxonomy", fake_taxonomy
        )
        monkeypatch.setattr(AntithesisExtraction, "_extract_candidates", fake_candidates)
        monkeypatch.setattr(AntithesisExtraction, "_persist_candidates", fake_persist)
        monkeypatch.setattr(
            AntithesisExtraction, "_truncate_candidates", lambda self, c: c
        )

        reported: list[str] = []
        monkeypatch.setattr(
            antithesis_extraction,
            "report_progress",
            lambda detail: reported.append(detail),
        )

        thesis = Statement(
            text="Ship without review",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
        )
        thesis.commit()

        with progress_scope("ingest") as progress:
            await AntithesisExtraction().resolve(thesis=thesis, text=SHORT_SOURCE)
            assert progress.total == 2, (
                "two steps, not three: link 1 runs immediately after the caller's"
                " own announcement, so a step there would restate it once per thesis"
            )

        assert reported == [
            "Weighing what could stand against this",
            "Judging how strongly each opposition holds",
        ], reported
        assert order == ["link1", "link2", "link3"], (
            "the chain must stay sequential — it is what makes these steps"
            f" stagger instead of arriving together. Got: {order}"
        )

    @pytest.mark.asyncio
    async def test_a_mechanical_opposition_declares_nothing(self, monkeypatch):
        """The counter-case, and the rule it protects.

        A SIMPLE thesis is ONE call producing a mechanical negation, under a phase
        the caller already announced. `record_decision` makes the same judgement
        about its own graph writes: a step is worth declaring only where the
        alternative is silence. Without this test the natural "be consistent"
        edit is to declare steps on both branches, and the person would then be
        told twice about work that already finished.
        """
        from dialectical_framework.concerns.antithesis_extraction import \
            AntithesisExtraction
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.utils.progress import progress_scope

        async def fake_simple(self, thesis):
            return []

        monkeypatch.setattr(
            AntithesisExtraction, "_process_simple_thesis", fake_simple
        )

        thesis = Statement(
            text="Ship without review", meaning="dx://taxonomy/Simple/Negation"
        )
        thesis.commit()
        assert thesis.is_simple, "fixture must take the SIMPLE branch to mean anything"

        with progress_scope("ingest") as progress:
            await AntithesisExtraction().resolve(thesis=thesis)
            assert progress.total == 0

    @pytest.mark.asyncio
    async def test_the_new_labels_name_no_machinery(self):
        """The same ban the tool-level test applies, on strings it cannot reach.

        `two_theses` patches `ThesisExtraction.resolve`, so
        `test_no_detail_string_names_the_machinery` never sees the classify label.
        """
        labels = (
            "Placing 2 candidate tension(s)",
            "Weighing what could stand against this",
            "Judging how strongly each opposition holds",
        )
        for label in labels:
            for term in BANNED:
                assert term not in label.lower(), f"{label!r} names {term!r}"


class TestTheDigestSaysWhenAPartComesBack:
    """The third hole, and the only one a note can fill.

    `SourceDigest` reads a big source in gathered parts. Below
    `MAX_CONCURRENT_PART_READINGS` nothing queues, so every part announces itself in
    the same instant and then the channel goes quiet until the reduce — measured at
    **25.4s on a 120 KB source**, the widest hole of that run and the first thing a
    person meets after pasting a document. Two other facts make it the one site that
    earns a note: a part reading writes NO graph node, so the `sid` channel has
    nothing to say either, and the parts return at different times (11.2s, 12.6s,
    13.0s), so completions trickle where starts did not.

    Asserted at the concern, not through `ingest`: the tool's stream is a sum over
    seven sites, and these events deliberately do not enter that sum at all.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    async def _digest_parts(self, monkeypatch, parts: int) -> tuple[list, object]:
        """Run the part fan-out under a scope, returning (events, scope).

        `note_progress` and `report_progress` are captured at the module level so the
        two kinds stay distinguishable without a bus — what matters here is which
        function each site calls, and the bus plumbing is `test_progress.py`'s job.
        """
        from dialectical_framework.concerns import source_digest as digest_module
        from dialectical_framework.concerns.source_digest import SourceDigest
        from dialectical_framework.utils.progress import progress_scope

        events: list = []
        monkeypatch.setattr(
            digest_module,
            "report_progress",
            lambda detail: events.append(("step", detail)),
        )
        monkeypatch.setattr(
            digest_module,
            "note_progress",
            lambda detail: events.append(("note", detail)),
        )

        with progress_scope("ingest") as progress:
            await SourceDigest()._generate_digest_from_parts(
                [f"part {i} text" for i in range(1, parts + 1)],
                None,
                "context",
            )
        return events, progress

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_every_part_reports_a_completion(self, monkeypatch):
        events, _ = await self._digest_parts(monkeypatch, parts=4)

        notes = [detail for kind, detail in events if kind == "note"]
        assert notes == [
            "1 of 4 parts read",
            "2 of 4 parts read",
            "3 of 4 parts read",
            "4 of 4 parts read",
        ], (
            "the parts announced themselves and then said nothing about coming"
            f" back — this is the 25.4s hole. Got: {events}"
        )

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_count_is_completions_and_not_the_part_index(self, monkeypatch):
        """Why it counts rather than names.

        `gather` preserves argument order in its RESULT, not in completion order, so
        the parts finish in whatever order the provider returns them. Counting says
        something true either way; "part 2 read" out of order invites the question of
        where parts 1 and 3 went. It is also the line that stays honest during a
        retry: it sticks at "3 of 4", which is exactly what is happening.
        """
        events, _ = await self._digest_parts(monkeypatch, parts=3)

        notes = [detail for kind, detail in events if kind == "note"]
        # A count reaches its own total exactly once, whatever order parts land in.
        assert notes[-1] == "3 of 3 parts read"
        assert len({n for n in notes}) == 3, f"a completion repeated itself: {notes}"

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_completions_are_not_steps(self, monkeypatch):
        """The invariant that makes this safe, at the site rather than in the seam.

        Parts plus the reduce is what `expect_progress` declared, and a note is not
        an addend. Counting these as steps would report 9 for a 4-part source
        against a declared 5 and render a host past 100%.
        """
        events, progress = await self._digest_parts(monkeypatch, parts=4)

        steps = [detail for kind, detail in events if kind == "step"]
        assert len(steps) == 5, f"parts + reduce is 5 steps, got {steps}"
        assert progress.total == 5, (
            "the denominator counted completions — `expect_progress(total + 1)` is"
            " parts plus the reduce, and notes must not be in it"
        )

    def test_a_completion_names_no_machinery_and_no_content(self):
        """Same two bans as every other label on this path.

        The unit of work here is a slice of the person's own file, and "digest" is
        itself a banned word — so the honest wording has to describe the READING
        without naming either.
        """
        label = "3 of 4 parts read"
        for term in BANNED:
            assert term not in label.lower(), f"{label!r} names {term!r}"
        assert len(label) < 200


class TestTheConsolidationPhaseSaysItIsRunning:
    """The fourth hole, and the only one where the label on screen was WRONG.

    `FindPolarities` runs a Phase 0 before extraction: `AntitheticalThesisDetection`
    compares the surfaced tensions pairwise, and every pair it merges is written as
    an opposition directly and taken OUT of the extraction that follows. On the
    120 KB run that phase took **12.4s and removed 8 of the 10 surfaced tensions**,
    and the only line on screen for those twelve seconds was the caller's "Looking
    for what genuinely pushes back" — a label about extraction, over a phase that
    was busy cancelling most of it (`tests/e2e/probe_ingest_progress.py`).

    So this is not the fan-out defect the class above pins. Nothing here is gathered
    and nothing is silent: the channel had an event, it just described different
    work than the work being done. The fix is one step at Phase 0's own site.

    Asserted on the skill rather than through `ingest`, for the reason
    `TestOneLabelNeverCoversAGatheredFanOut` gives — and additionally because the
    `two_theses` fixture patches `ThesisExtraction.resolve`, which is upstream of
    this phase but says nothing about how many hashes reach it.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    async def _consolidate(
        self, monkeypatch, hashes: list[str]
    ) -> tuple[list[str], object, list[list[str]]]:
        """Run Phase 0 under a scope with detection stubbed to merge nothing.

        Merging nothing is the conservative case for this test: the step is declared
        before the detector is called, so a fixture that merged pairs would exercise
        the graph writes without changing anything about the accounting, while
        needing real `Statement`s to do it.
        """
        from types import SimpleNamespace

        from dialectical_framework.agents.analyst.skills import find_polarities
        from dialectical_framework.agents.analyst.skills.find_polarities import \
            FindPolarities
        from dialectical_framework.concerns.antithetical_thesis_detection import \
            AntitheticalThesisDetection
        from dialectical_framework.utils.progress import progress_scope

        called: list[list[str]] = []

        async def fake_detect(self, *, thesis_hashes, text):
            called.append(list(thesis_hashes))
            return SimpleNamespace(merge_pairs=[], suggest_pairs=[])

        monkeypatch.setattr(AntitheticalThesisDetection, "resolve", fake_detect)

        reported: list[str] = []
        monkeypatch.setattr(
            find_polarities, "report_progress", lambda detail: reported.append(detail)
        )

        with progress_scope("ingest") as progress:
            await FindPolarities(thesis_hashes=hashes)._consolidate_antithetical(
                hashes, "irrelevant under a stubbed detector"
            )

        return reported, progress, called

    @pytest.mark.asyncio
    async def test_the_phase_declares_one_step_before_it_runs(self, monkeypatch):
        """One step, carrying this run's count, published before the detector call."""
        reported, progress, called = await self._consolidate(
            monkeypatch, ["h1", "h2", "h3"]
        )

        assert reported == [
            "Checking whether any of the 3 tension(s) already oppose each other"
        ], (
            "the label must name the pairwise check and carry the real count, so a"
            f" person can tell this phase from the extraction after it. Got: {reported}"
        )
        assert progress.total == 1, (
            "exactly one step: the merges after the detector call write graph nodes,"
            " which the `sid` channel already carries"
        )
        assert called, "the step must be declared BEFORE the work, not after"

    @pytest.mark.asyncio
    async def test_below_two_tensions_it_declares_nothing(self, monkeypatch):
        """The phantom-step guard, and the reason the step is not at the caller.

        With one hash there is no pair to compare, so Phase 0 returns before the
        detector. A step declared at `AnalysisPipeline` — where the count is not yet
        known — would be expected on every single-thesis `anchor` run and reported on
        none of them, leaving the denominator one short forever and a bar that never
        fills.
        """
        reported, progress, called = await self._consolidate(monkeypatch, ["h1"])

        assert reported == [], f"a phase that did not run announced itself: {reported}"
        assert progress.total == 0, (
            "the denominator grew for work no site will report — this is exactly the"
            " half of the accounting failure that looks fine in the source"
        )
        assert not called, "detection ran on a single hash"

    def test_the_label_names_no_machinery(self):
        """`consolidate`, `antithetical` and `heuristic similarity` are all out.

        The honest wording has to describe a pairwise comparison without naming the
        concern that performs it or the score it thresholds on.
        """
        label = "Checking whether any of the 3 tension(s) already oppose each other"
        for term in BANNED:
            assert term not in label.lower(), f"{label!r} names {term!r}"
        assert "consolidat" not in label.lower()
        assert "heuristic" not in label.lower()
        assert len(label) < 200


class TestTheOppositionAnglesSayWhenTheyComeBack:
    """The fifth hole, and the second site — with the digest — to earn a note.

    `AntithesisExtraction._extract_candidates` is link 2 of the opposition chain, and
    the step above it ("Weighing what could stand against this") announces a
    `gather` over one `ModePointResultDto` call per mode point — up to 11 of them.
    On the 120 KB run those calls were the **largest provider-time block of the whole
    ingest: 22 calls, 94.2s, mean 4.3s**, under that one label, and the method writes
    NO graph node by its own docstring — so the `sid` channel had nothing to say in
    that window either (`tests/e2e/probe_ingest_progress.py`).

    Five earlier runs did not promote it because at two theses the silence is only
    ~5s per wave. At ten it is up to 110 gathered calls under one label.

    What is asserted here is that both gather branches note their completions, that
    each note is published as its own call returns rather than after the gather, and
    that the notes are NOT steps.

    **The note deliberately carries NO count, and that is asserted too.** It first read
    "N of M angles considered", which was true per chain and false to the eye:
    `find_polarities` gathers one chain PER thesis and each counted only its own calls,
    so a person watching ten theses read "5 of 11" and then "1 of 11". A fraction in
    front of a person is a promise about the whole, so it may not be scoped to a
    fan-out the person cannot see. `test_a_returning_angle_promises_no_total` is what
    keeps a future reader from "improving" the wording back.
    """

    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    async def _weigh_angles(
        self, monkeypatch, *, count: int, angles: int = 3
    ) -> tuple[list, object]:
        """Run link 2 with a stubbed conversation, returning (events, scope).

        `count` picks the branch: at or below `angles` the per-point call returns one
        candidate, above it the batch call returns several. Both are gathers of single
        provider calls, so both owe notes — and the batch branch is the one a reader
        is most likely to forget, since its wrapper looks different.

        The calls return in STAGGERED order on purpose: it is the only fact a note
        publishes, so a fixture where they all returned together would pass while
        saying nothing.

        The stub logs its OWN returns into the same list as the notes, which is what
        lets a test tell "noted as each call came back" from "noted once the gather
        finished" — with the count gone from the wording, that interleaving is the
        whole content of the note.
        """
        from types import SimpleNamespace

        from dialectical_framework.concerns import antithesis_extraction
        from dialectical_framework.concerns.antithesis_extraction import (
            AntithesisExtraction, ModePointBatchResultDto, ModePointResultDto)
        from dialectical_framework.concerns.antithesis_classification import \
            ContextualizedTaxonomyDto
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.utils.progress import progress_scope

        fields = list(ContextualizedTaxonomyDto.MODE_FIELDS)[:angles]
        taxonomy = SimpleNamespace(
            apex="Shipping nothing at all",
            **{name: f"context for {name}" for name in fields},
        )

        delays = iter([0.03, 0.01, 0.02] * angles)
        events: list[tuple[str, str]] = []

        class _Isolated:
            async def submit(self, *, response_model, user_content):
                await asyncio.sleep(next(delays))
                one = ModePointResultDto(
                    statement="Review before shipping",
                    heuristic_similarity=0.6,
                    arousal_label="moderate",
                    explanation="stub",
                )
                events.append(("returned", ""))
                if response_model is ModePointBatchResultDto:
                    return ModePointBatchResultDto(candidates=[one])
                return one

        class _Conversation:
            def isolate(self):
                return _Isolated()

        monkeypatch.setattr(
            antithesis_extraction,
            "note_progress",
            lambda detail: events.append(("note", detail)),
        )
        monkeypatch.setattr(
            antithesis_extraction,
            "report_progress",
            lambda detail: events.append(("step", detail)),
        )

        service = AntithesisExtraction()
        service._conversation = _Conversation()
        service._text = SHORT_SOURCE
        service._not_like_these = []
        service._count = count

        thesis = Statement(text="Ship without review")

        with progress_scope("ingest") as progress:
            candidates = await service._extract_candidates(thesis, taxonomy)

        assert candidates, "the fixture must produce candidates to mean anything"
        return events, progress

    @pytest.mark.asyncio
    async def test_every_angle_reports_when_it_returns(self, monkeypatch):
        """One note per gathered call on the single-candidate branch."""
        events, _ = await self._weigh_angles(monkeypatch, count=3)

        notes = [detail for kind, detail in events if kind == "note"]
        assert notes == ["Another angle weighed"] * 3, (
            f"three gathered calls owe three notes. Got: {notes}"
        )

    @pytest.mark.asyncio
    async def test_the_batch_branch_notes_too(self, monkeypatch):
        """Asking for several candidates per point must not lose the notes.

        `_candidates_per_branch` switches to `ModePointBatchResultDto` whenever the
        requested count exceeds the number of mode points, which on a narrow taxonomy
        is the ORDINARY case rather than an exotic one. It is a separate `gather`
        expression, so it is a separate place to forget the wrapper.
        """
        events, _ = await self._weigh_angles(monkeypatch, count=9)

        notes = [detail for kind, detail in events if kind == "note"]
        assert notes == ["Another angle weighed"] * 3, (
            f"the batch branch dropped its notes. Got: {notes}"
        )

    @pytest.mark.asyncio
    async def test_each_note_lands_as_its_own_call_comes_back(self, monkeypatch):
        """A note per RETURN, not a burst of notes after the gather.

        This is the whole content of an uncounted note: it says "something just
        finished", so it is worth nothing unless it is published at the moment the
        thing finished. Wrapping the gather instead of each call — the natural
        simplification once the counter is gone — would emit all three notes at the
        end, when the label above them is already changing anyway.

        The stub staggers its returns (0.03/0.01/0.02s), so a per-call note has to
        interleave strictly: return, note, return, note, return, note.
        """
        events, _ = await self._weigh_angles(monkeypatch, count=3)

        streamed = [kind for kind, _ in events if kind in ("returned", "note")]
        assert streamed == ["returned", "note"] * 3, (
            "the notes did not follow their own calls back — they were published"
            f" around the gather rather than inside it: {streamed}"
        )

    @pytest.mark.asyncio
    async def test_the_angles_are_not_steps(self, monkeypatch):
        """The invariant that makes this safe: link 2's step count is unchanged.

        The step for link 2 is declared by `resolve`, one for the whole fan-out.
        Counting completions as steps here would report up to 11 against a declared 2
        and render a host past 100% — and it would do it once per thesis.
        """
        events, progress = await self._weigh_angles(monkeypatch, count=3)

        steps = [detail for kind, detail in events if kind == "step"]
        assert steps == [], f"link 2's fan-out declared a step of its own: {steps}"
        assert progress.total == 0, (
            "the denominator grew inside the fan-out — `resolve` already declared"
            " this phase, and a note is not an addend"
        )
        assert progress.done == 0

    @pytest.mark.asyncio
    async def test_a_returning_angle_promises_no_total(self, monkeypatch):
        """No fraction in the wording, and this is a UX rule rather than a style one.

        `find_polarities` gathers one of these chains per thesis and each chain can
        only count its own calls, so a numerator here is scoped to a fan-out the
        person cannot see: ten theses in flight made the line read "5 of 11" and then
        "1 of 11". Each was true of its own tension; together they were a bar falling
        backwards. A fraction shown to a person is a promise about the whole, so this
        window — which does not know the whole — may not make one.

        Asserted against the LIVE note rather than a literal, so that restoring a
        count at the site fails here even if this docstring is never read.
        """
        events, _ = await self._weigh_angles(monkeypatch, count=3)

        for _, label in [e for e in events if e[0] == "note"]:
            assert " of " not in label, (
                f"{label!r} counts against a total this window does not know"
            )
            assert not any(ch.isdigit() for ch in label), (
                f"{label!r} carries a number; see this test's docstring"
            )
            for term in BANNED:
                assert term not in label.lower(), f"{label!r} names {term!r}"
            for term in ("mode point", "taxonomy", "branch", "apex", "arousal"):
                assert term not in label.lower(), f"{label!r} names {term!r}"
            assert len(label) < 200
