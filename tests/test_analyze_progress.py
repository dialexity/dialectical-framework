"""`analyze` must speak while it works, using instrumentation that already existed.

WHY THIS TEST EXISTS
====================
The progress seam only fires when some caller installed a scope, and for a long
time exactly five tools did. `analyze` was not one of them — so the richest
instrumentation in the tree was a no-op on the path a model reaches most directly.
`analyze` runs the SAME `AnalysisPipeline` as `ingest` and `anchor`, so the entire
silence was one missing `with`: 31 `expect_progress`/`report_progress`/
`note_progress` calls across six modules, every one of them already written,
already tested through the other two tools, and mute here. (Seven when this was
written — `AnalysisPipeline` owned a pair of its own, which has since moved down into
`FindPolarities.resolve()`; see the flash note on the first test below.)

That is the shape of defect this file exists to catch, and it is a nasty one
because **nothing about it looks wrong at either end**. Every call site is correct.
Every unit test on those sites passes. The tool returns the right answer. The only
observable is that a person sat through minutes of nothing, which no assertion
about a scope OBJECT can see — the object is never created.

WHAT IS PINNED, AND WHY BEHAVIOURALLY
=====================================
The load-bearing assertion is that a label published DEEP under the pipeline
arrives on the bus: `"Looking for what genuinely pushes back"` comes from
`FindPolarities.resolve()`, which the pipeline awaits directly, and the tetrad step
comes from inside a `gather` that `resolve` creates. Together they pin both halves of
the ordering requirement in
`utils/progress.py` — that a scope is installed at all, and that it is installed
before the tasks are created. A scope placed one level too low (inside a skill)
leaves the other level silent, and a scope placed after the gather leaves
everything silent while still publishing a tidy `final`.

The leak checks matter more here than on most paths: `analyze`'s `text` parameter
is documented as "the user's situation, dilemma, or content", so it is the person's
own words by definition, and both the labels and the stream KEY are things a host
may render verbatim.

Mock brain throughout: this is about the accounting, not the reasoning.

Run: poetry run pytest tests/test_analyze_progress.py
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.analyst.analyst import _progress_key, analyze
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module

#: Distinctive enough that any substring of it appearing in a label is a leak and
#: not a coincidence of ordinary English.
SITUATION = (
    "Quarterly hiring at Brightmoor Logistics doubled the delivery team, and the "
    "same quarter produced the three worst dispatch failures in the company's "
    "history. Nobody can say whether the failures came from the new hires or from "
    "the supervisors who no longer had time to check anything."
)

INTENT = "Find the structural trade-off this situation keeps returning to"

#: Terms a host may not render to a person under the silent Advisor. Kept in step
#: with `tests/test_ingest_progress.py` — the same contract, a different entry
#: point, and the whole point of the seam is that the machinery stays hidden.
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

#: Any run of the person's own text this long inside a label is a leak.
_LEAK_RUN = 40


@pytest.fixture
def two_theses(monkeypatch):
    """Force extraction to succeed so the run reaches `AnalysisPipeline`'s steps.

    Same reason as `tests/test_ingest_progress.py`'s copy: mock brain returns the
    SAME DTO on every call, so real extraction yields nothing that survives its own
    dedup and the pipeline stops at "No theses extracted" — the one branch that
    never reaches the gathered work, which is precisely the work this file is about.
    """
    from dialectical_framework.concerns.thesis_extraction import ThesisExtraction
    from dialectical_framework.graph.nodes.statement import Statement

    branch = "dx://taxonomy/System(General.v1)/Viability/Integrity"

    async def fake_resolve(
        self, text="", count=3, focus="", domain_hint="", not_like_these=None
    ):
        out = []
        for name in ("Hire fast to meet demand", "Hire slowly to keep oversight"):
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
    # session-scoped `di_container` fixture, so `None` here would silently disable
    # progress for every test that ran afterwards.
    previous = progress_module._event_bus
    progress_module.set_event_bus(bus)
    try:
        yield bus
    finally:
        progress_module.set_event_bus(previous)
        await bus.disconnect()


async def _drain(received: list, *, timeout: float = 5.0) -> None:
    """Wait until `received` stops growing.

    Not a fixed sleep: publishes are fire-and-forget `create_task`s, and a fixed
    interval passes on an idle machine while dropping the closing event under load
    — which reads as a missing `final` rather than as flake.
    """
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


async def _run_analyze_collecting(bus, sid: str, **kwargs) -> list:
    """Run `analyze` under `sid` while draining its progress channel.

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
            await analyze.fn(**kwargs)
        await _drain(received)
    finally:
        listener.cancel()
    return received


def _assert_accounting_closes(events: list) -> None:
    """One stream, one close, and a denominator the steps actually add up to."""
    assert events, "not one progress event — the person saw silence"

    finals = [e for e in events if e.final]
    # Notes are not steps and must be excluded from every count below; that is the
    # whole reason `ProgressEvent.note` exists rather than completions riding on
    # `report_progress`. A note reaching `steps` would make `done` overshoot.
    notes = [e for e in events if e.note and not e.final]
    steps = [e for e in events if not e.final and not e.note]

    assert len(finals) == 1, (
        f"expected exactly one closing event, got {len(finals)} — a host clears"
        f" its indicator on `final`, so two means it cleared mid-run"
    )
    final = finals[0]
    assert steps, (
        "a `final` arrived with no steps before it: the scope is installed but"
        " nothing under it reported, which is the mis-placed-scope signature"
    )
    assert final.done == final.total, (
        f"closed at {final.done}/{final.total} — every declared step on this path"
        f" is reported at its own site, so a shortfall means work was declared"
        f" for a branch that never ran (a phantom step: a bar that cannot fill)"
    )
    for i, event in enumerate(steps):
        assert event.done == i, (
            f"step {i} published done={event.done} — the counters are snapshotted"
            f" at publish time precisely so gathered events do not all carry the"
            f" same number"
        )
    for note in notes:
        assert note.done <= note.total, (
            "a note moved the counters past the denominator, which is the one"
            " thing `note=True` is supposed to make impossible"
        )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_analyze_lights_up_the_instrumentation_that_was_already_there(
    collected_progress, two_theses
):
    """The whole point: no new reporting site, and the person stops sitting in silence.

    Every asserted label is published by code this test does not touch and that was
    working before this scope existed — one from a skill `AnalysisPipeline.resolve`
    awaits directly, one from inside a `gather` that `resolve` creates. That pairing is
    deliberate: it is what distinguishes "a scope exists" from "the scope is in the
    right place".

    The extraction label being published ONCE is the flash regression, and it is only
    visible from out here. It used to be declared by `AnalysisPipeline` itself,
    immediately before `find.resolve()`, where it landed in the same instant as Phase
    0's own step and lived 0.0s; it now publishes inside `FindPolarities.resolve()`,
    below that phase. A unit test on the skill cannot see a caller's event, so
    re-declaring it up there would leave
    `test_ingest_progress.py::TestTheExtractionLabelWaitsForConsolidation` green and
    show up here as the same label twice.

    What this does NOT pin is the ORDER of the two labels on the assembled stream: mock
    brain's dedup collapses this fixture's two theses into one, so Phase 0 returns
    before its own guard and never speaks on this path. The ordering is pinned at the
    skill instead, where the hash count can be arranged.
    """
    case = Case()
    case.commit()

    events = await _run_analyze_collecting(
        collected_progress, case.sid, text=SITUATION, intent=INTENT
    )
    _assert_accounting_closes(events)

    details = [e.detail for e in events if not e.final]
    assert "Looking for what genuinely pushes back" in details, (
        "the pipeline never spoke — this is the pre-existing instrumentation the"
        " tool-level scope exists to light up, and it is the assertion that fails"
        " if someone removes the `with`"
    )
    assert details.count("Looking for what genuinely pushes back") == 1, (
        "the extraction label was published twice — one `FindPolarities.resolve()` ran,"
        " so a second copy means it was re-declared at the caller, which is the 0.0s"
        f" flash this label was moved to stop. Got: {details}"
    )
    assert any("overreaches" in d for d in details), (
        "the tetrad-generation step never announced itself — it runs inside a"
        " `gather` created by `AnalysisPipeline.resolve`, so this is what a scope"
        " installed too late (after the tasks) breaks while still closing tidily"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_one_analyze_is_one_keyed_stream(collected_progress, two_theses):
    """Every event carries the same stage and key, and the key is the tool's own.

    Two `analyze` calls can be in flight in one round, and without a key their
    counts interleave into a single nonsensical bar. Asserting the key EQUALS
    `_progress_key(...)` rather than merely being non-empty is what catches a
    future edit that keys the stream off something cheaper to hand (the intent, a
    node hash) and re-opens the leak the next test closes.
    """
    case = Case()
    case.commit()

    events = await _run_analyze_collecting(
        collected_progress, case.sid, text=SITUATION, intent=INTENT
    )
    assert events

    expected = _progress_key(SITUATION, None, None)
    assert {e.stage for e in events} == {"analysis"}, (
        f"more than one stage on this channel: {sorted({e.stage for e in events})}"
        f" — an inner stage name appearing here means a nested scope installed"
        f" instead of deferring"
    )
    assert {e.key for e in events} == {expected}, (
        "the stream is not keyed by the tool's own content-derived id"
    )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_nothing_a_host_renders_carries_the_persons_words_or_the_machinery(
    collected_progress, two_theses
):
    """Labels AND the key are host-rendered surfaces, so both are checked.

    The key is checked here and not only in the test above because it is derived
    FROM the person's text: a future edit that passed the text through instead of
    hashing it would still be "keyed", still be stable, still be unique, and would
    put the person's situation into whatever a host shows next to its spinner.
    """
    case = Case()
    case.commit()

    events = await _run_analyze_collecting(
        collected_progress, case.sid, text=SITUATION, intent=INTENT
    )
    assert events

    # No exemption for `final`. It used to be exempt "by convention", because the
    # seam built its detail as `f"{stage} finished"` — and that convention hid a real
    # leak: `synthesis` is BANNED, and `GenerateSynthesis` opens its own scope under
    # the Advisor's `explore`, which installs none, so `"synthesis finished"` went out
    # to a host past three tests written to catch exactly that. The seam now closes
    # with an empty detail, which passes the ban trivially and honestly.
    for event in events:
        lowered = event.detail.lower()
        for term in BANNED:
            assert term not in lowered, (
                f"label {event.detail!r} names the machinery ({term!r}) — the"
                f" silent Advisor's contract is that a host may render these"
                f" verbatim"
            )
        assert len(event.detail) < 200, (
            f"label is {len(event.detail)} chars: too long to be a label and"
            f" long enough to be carrying content"
        )
        if event.final:
            assert event.detail == "", (
                f"the closing event labelled itself {event.detail!r}; the label"
                f" beside a host's spinner is the host's to write, from `stage`,"
                f" `key`, `done` and `total`"
            )

        for start in range(0, len(SITUATION) - _LEAK_RUN):
            run = SITUATION[start : start + _LEAK_RUN]
            assert run not in event.detail, f"source text leaked into {event.detail!r}"
            assert run not in (event.key or ""), "source text leaked into the key"


@pytest.mark.llm
@pytest.mark.asyncio
async def test_a_run_that_extracts_nothing_still_closes_its_stream(collected_progress):
    """The early-return branch, deliberately WITHOUT the `two_theses` fixture.

    Mock brain's identical DTOs collapse in extraction's own dedup, so this run
    returns "no theses" before reaching any gathered work. It is the phantom-step
    trap in its natural habitat: a step declared above that guard would be reported
    on the path above and never here, and the only visible symptom is a `final`
    that closes short. `record_decision`'s in-band refusals set the precedent that
    closing at 0/0 is legitimate, so the assertion is on the arithmetic closing,
    not on there being steps.
    """
    case = Case()
    case.commit()

    events = await _run_analyze_collecting(
        collected_progress, case.sid, text=SITUATION, intent=INTENT
    )

    finals = [e for e in events if e.final]
    assert len(finals) == 1, (
        f"expected exactly one closing event on the early-return branch, got"
        f" {len(finals)} — a tool that returns early must still close its stream"
    )
    assert finals[0].done == finals[0].total, (
        f"closed at {finals[0].done}/{finals[0].total} on a branch that returned"
        f" early: a step was declared above a guard it does not reach"
    )
