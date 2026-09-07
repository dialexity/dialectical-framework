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
    steps = [e for e in events if not e.final]

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
