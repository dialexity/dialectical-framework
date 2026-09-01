"""`anchor` must speak while it works, and its arithmetic must close.

WHY THIS TEST EXISTS
====================
`anchor` was measured at ~40s of near-total silence: `call_census` puts it at
parallelism ~1.15 over ~9 dependency stages, so there is no fan-out left to
compress it into, and nothing writes a graph node until a perspective commits.
Progress reporting is therefore not a nicety here — it is the only thing standing
between the person and an unbroken pause.

WHY IT IS A BEHAVIOURAL TEST AND NOT A SOURCE GREP
==================================================
The counting is spread across five call sites in four modules (`anchor`,
`AnchorTheses`, `IntroducePolarity`, `AnalysisPipeline`, `ExpandPolarity`), and
each declares its own slice of the denominator via `expect_progress` at the point
where the work becomes knowable. A grep can check one site against one constant;
only running the tool can check that the SUM of what was expected equals the sum
of what was reported. Both halves of that failure are silent and both look fine in
the code:

* expecting more than you report → the bar sticks below 100% forever;
* reporting more than you expected → `done` overshoots `total`, and a host doing
  `done / total` renders 140%.

The specific trap this pins is the one `utils/progress.py` documents: a task
created BEFORE the scope is installed captures a context copy without it and
reports NOTHING. `AnalysisPipeline` gathers its expansions, so if the scope were
opened inside a skill instead of at the tool, the thesis-only branch would go
silent for its single most expensive stage while every unit test on the scope
object still passed.

Mock brain throughout — this is about the accounting, not the reasoning.

Run: poetry run pytest tests/test_anchor_progress.py
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.advisor.tools.anchor import anchor
from dialectical_framework.concerns.antithesis_extraction import (
    AntithesisExtraction, AntithesisProcessed)
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module

BRANCH = "dx://taxonomy/System(General.v1)/Viability/Integrity"
A_MEANING = f"{BRANCH}/Separation"

THESIS = "Buy out the cofounder now"
ANTITHESIS = "Keep him and reset the terms"
CONTEXT = (
    "Cofounder holds 45% equity. Two anchor accounts are 60% of revenue and "
    "both CEOs call him, not me."
)

#: Terms a host may not render to a person under the silent Advisor. The detail
#: strings are the one part of this seam that is written FOR a human, and
#: `utils/progress.py` warns they may be shown verbatim.
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
)


@pytest.fixture
async def collected_progress():
    """Subscribe to `sid:progress` and hand back (sid, events) for one run."""
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


async def _run_anchor_collecting(bus, sid: str, **kwargs) -> list:
    """Run `anchor` under `sid` while draining its progress channel.

    The `scope` is entered around the AWAIT, not around building the coroutine.
    A factory returning `anchor.fn(...)` from inside a `with scope(...)` block
    leaves the scope before anything runs, and `_publish` silently drops every
    event when no sid is in scope — which is precisely how the first version of
    this test reported "the person saw silence" about its own harness.
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
            await anchor.fn(**kwargs)
        # Publishes are fire-and-forget `create_task`s, so wait until the list
        # STOPS GROWING rather than for a fixed interval — a fixed sleep is a
        # timing assumption that passes on an idle machine and drops the closing
        # event under load, which reads as a missing `final` rather than as flake.
        await _drain(received)
    finally:
        listener.cancel()
    return received


async def _drain(received: list, *, timeout: float = 3.0) -> None:
    """Wait until `received` stops growing (mirrors `test_progress.py`)."""
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


@pytest.fixture
def five_antitheses(monkeypatch):
    """The thesis-only branch needs a real fan-out; mock brain returns one DTO."""

    async def fake_extract(self, thesis, text="", not_like_these=None, count=5):
        out = []
        for name in ("Reset the terms", "Sell instead", "Let it run"):
            stmt = Statement(text=name, meaning=A_MEANING)
            stmt.commit()
            out.append(
                AntithesisProcessed(
                    component=stmt,
                    mode_value=0.8,
                    arousal_value=0.6,
                    heuristic_similarity=0.85,
                )
            )
        return out

    monkeypatch.setattr(AntithesisExtraction, "resolve", fake_extract)


def _assert_accounting_closes(events: list, *, branch: str) -> None:
    assert events, f"{branch}: not one progress event — the person saw silence"

    finals = [e for e in events if e.final]
    steps = [e for e in events if not e.final]

    assert len(finals) == 1, (
        f"{branch}: expected exactly one closing event, got {len(finals)} —"
        " a host clears its indicator on `final`"
    )
    final = finals[0]
    assert final.stage == "anchor"

    # One non-None key, shared by every event of this run. `execute_tools()` runs a
    # tool round concurrently, so two `anchor` calls in one round publish two
    # interleaved streams under the same sid and stage; the key is the only thing
    # that lets a host tell them apart and not clear its indicator on the first
    # `final` while the second is still working.
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

    # Monotonic, and never ahead of the denominator mid-run.
    for i, event in enumerate(steps):
        assert event.done == i, f"{branch}: step {i} reported done={event.done}"
        assert event.done <= event.total, (
            f"{branch}: {event.done}/{event.total} mid-run — `done` overtook"
            " `total`, which reads as more than everything"
        )


@pytest.mark.llm
@pytest.mark.asyncio
async def test_the_both_poles_branch_reports_and_the_total_closes(collected_progress):
    case = Case()
    case.commit()

    events = await _run_anchor_collecting(
        collected_progress,
        case.sid,
        thesis=THESIS,
        antithesis=ANTITHESIS,
        context=CONTEXT,
    )
    _assert_accounting_closes(events, branch="both-poles")


@pytest.mark.llm
@pytest.mark.asyncio
async def test_the_thesis_only_branch_reports_from_inside_the_gather(
    collected_progress, five_antitheses
):
    """The branch that would go silent if the scope moved down into a skill.

    `AnalysisPipeline` gathers one `ExpandPolarity` per tension, and those tasks
    are created inside the tool. Their reports are the majority of this branch's
    steps, so a scope installed anywhere below `anchor` would leave the expensive
    stage unannounced while the cheap ones above it still spoke.
    """
    case = Case()
    case.commit()

    events = await _run_anchor_collecting(
        collected_progress, case.sid, thesis=THESIS, antithesis=None, context=CONTEXT
    )
    _assert_accounting_closes(events, branch="thesis-only")

    details = [e.detail for e in events if not e.final]
    assert any("overreaches" in d for d in details), (
        "the tetrad-generation step never announced itself — it runs inside"
        " `AnalysisPipeline`'s gather, so this is what a mis-placed scope breaks"
    )


class TestTheProgressKeySeparatesConcurrentAnchors:
    """The key's job, tested on the key rather than by racing two anchors.

    Two concurrent `anchor` calls is the situation the key exists for, but driving
    it here would also drive two concurrent graph write sequences through
    GQLAlchemy, which is not concurrency-safe (CLAUDE.md) — the test would be
    exercising a hazard the framework does not claim to support, and any flake it
    produced would be attributed to progress. So the two properties the
    demultiplexing rests on are asserted directly, and the single-run tests above
    assert the key actually reaches the events.
    """

    def test_different_tensions_get_different_keys(self):
        from dialectical_framework.agents.advisor.tools.anchor import \
            _progress_key

        assert _progress_key(THESIS, ANTITHESIS) != _progress_key(THESIS, None)
        assert _progress_key(THESIS, ANTITHESIS) != _progress_key(
            "Something else", ANTITHESIS
        )

    def test_the_same_tension_gets_a_stable_key(self):
        """Stable across a retry of the same call, so a host does not see the work
        restart under a new id."""
        from dialectical_framework.agents.advisor.tools.anchor import \
            _progress_key

        assert _progress_key(THESIS, ANTITHESIS) == _progress_key(THESIS, ANTITHESIS)

    def test_the_key_does_not_carry_the_persons_words(self):
        """A host may render the key; it must not turn into a label quoting them."""
        from dialectical_framework.agents.advisor.tools.anchor import \
            _progress_key

        key = _progress_key(THESIS, ANTITHESIS)
        assert THESIS.lower() not in key.lower()
        assert "cofounder" not in key.lower()


@pytest.mark.llm
@pytest.mark.asyncio
@pytest.mark.parametrize("with_antithesis", [True, False], ids=["both-poles", "thesis-only"])
async def test_no_detail_string_names_the_machinery(
    collected_progress, five_antitheses, with_antithesis
):
    """A host may render `detail` verbatim, including under the silent Advisor.

    The framework's own vocabulary is exactly what that contract forbids, and a
    detail string is the one place it is easy to leak without any prompt review
    noticing — nothing else in the tree renders these words to a person.

    BOTH branches, because they do not share a single string: `AnchorTheses` and
    `AnalysisPipeline` speak only on the thesis-only leg, and running one branch
    left two of the seven details unchecked.
    """
    case = Case()
    case.commit()

    events = await _run_anchor_collecting(
        collected_progress,
        case.sid,
        thesis=THESIS,
        antithesis=ANTITHESIS if with_antithesis else None,
        context=CONTEXT,
    )

    steps = [e for e in events if not e.final]
    # Without this the loop below iterates nothing and the test cannot fail —
    # which is exactly what it did while the harness was dropping every event.
    assert steps, "no step events to inspect; this test would pass vacuously"

    for event in events:
        if event.final:
            # The closing event's detail is "<stage> finished", i.e. the stage
            # name — a host's own label, not prose written for the person.
            continue
        lowered = event.detail.lower()
        leaked = [term for term in BANNED if term in lowered]
        assert not leaked, f"progress detail leaked {leaked}: {event.detail!r}"
