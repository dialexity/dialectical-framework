"""`explore` is one action to a person, and it published between zero and four streams.

WHAT WAS WRONG
==============
`explore` — both doors, the Advisor's tool and `ExplorationPipeline` itself — opened no
progress scope at all. `report_progress` is a deliberate no-op with no scope installed,
so everything the wheel-building phase could have said was dropped, while the two skills
underneath it (`ExploreTransformations`, `GenerateSynthesis`) DID open scopes of their
own, because each is also reachable directly. Run under `explore` that produced
`2 x deepened wheels` closing events for one call — the same defect `deepen` had, where a
host clears its indicator on `final` and so cleared it halfway through the work — and
nothing whatsoever in front of them, across the phase
`tests/e2e/probe_build_wheels_progress.py` measured as 110.9s of a 163.2s k=4 wall.

So three claims, and they need three different kinds of test:

1. **Each door installs one stream**, keyed, named `exploration`, closing once. Stubs at
   the door (`TestOneExploreIsOneProgressStream`, `TestTheExplorerDoorOwnsItsStream`),
   because what is being pinned is the composition, not the reasoning.
2. **A nested scope folds in rather than opening a second stream.** Pinned at both doors,
   with the stubs opening scopes exactly where the real skills open theirs.
3. **The build phase actually speaks, and speaks IN TIME.** That one cannot be stubbed:
   it runs against a real graph (`TestBuildWheelsSpeaksBeforeItGoesQuiet`) and asserts on
   event TIMESTAMPS, because the phase it announces is synchronous all the way down —
   the announcement is published as a task, and without `flush_progress` that task
   cannot run until the phase it describes has already finished.

WHAT THIS DOES NOT PROVE
========================
Same limit as `test_advisor_deepen.py::TestOneDeepenIsOneProgressStream`, and for the
same reason: where a stub opens the nested scope, it is the STUB'S scope that defers. If
`ExploreTransformations` dropped its own `progress_scope` tomorrow these would stay
green. Driving the real skills needs a committed Wheel with transitions and a full
transformation run; what is worth catching cheaply is the door's install plus the seam's
deferral.

Run: poetry run pytest tests/test_explore_progress_scope.py
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.progress import (expect_progress,
                                                  flush_progress,
                                                  progress_hash_key,
                                                  progress_scope,
                                                  report_progress)

pytestmark = pytest.mark.llm

#: Same contract as `test_tool_progress_scopes.py`: a host may render `stage` and
#: `detail` verbatim, so neither may name the machinery.
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


@pytest.fixture
async def bus():
    """Subscribe-able bus for one run, wired into the progress seam."""
    b = GraphEventBus()
    await b.connect()
    # RESTORE, never clear: the module-level bus is wired once by the session-scoped
    # `di_container` fixture, so `None` here would mute progress for every later test.
    previous = progress_module._event_bus
    progress_module.set_event_bus(b)
    try:
        yield b
    finally:
        progress_module.set_event_bus(previous)
        await b.disconnect()


async def _drain(received: list, *, timeout: float = 5.0) -> None:
    """Wait until `received` stops growing, rather than sleeping a fixed interval."""
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


async def _collect(bus, sid: str, run) -> list:
    """Run `run()` under `sid` while draining that sid's progress channel.

    The `scope` is entered around the AWAIT, not around building the coroutine:
    `_publish` drops every event when no sid is in scope, so a factory that left the
    `with` before anything ran would report "the person saw silence" about the harness
    rather than about the code under test.
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
            await run()
        await _drain(received)
    finally:
        listener.cancel()
    return received


def _assert_one_stream(events: list, *, stage: str, key: str) -> list[str]:
    """Everything true of any stream on this channel. Returns the step labels."""
    assert events, "not one progress event — the person saw silence"

    finals = [e for e in events if e.final]
    notes = [e for e in events if e.note and not e.final]
    steps = [e for e in events if not e.final and not e.note]

    assert len(finals) == 1, (
        f"expected exactly one closing event, got {len(finals)} — a host clears its"
        f" indicator on `final`, so two means it cleared mid-run"
    )
    final = finals[0]
    assert final.done == final.total, (
        f"closed at {final.done}/{final.total} — a shortfall means work was declared"
        f" for a branch that never ran: a bar that cannot fill"
    )
    for i, event in enumerate(steps):
        assert event.done == i, (
            f"step {i} published done={event.done} — counters are snapshotted at"
            f" publish time so gathered events do not all carry the same number"
        )
    for note in notes:
        assert note.done <= note.total

    assert {e.stage for e in events} == {stage}, (
        f"more than one stage on this channel: {sorted({e.stage for e in events})} —"
        f" an inner stage name here means a nested scope installed instead of"
        f" deferring"
    )
    assert {e.key for e in events} == {key}, (
        f"stream keyed {sorted({e.key for e in events})}, expected {key!r}"
    )

    for term in BANNED:
        assert term not in stage.lower(), f"stage {stage!r} names the machinery"
    for event in events:
        lowered = event.detail.lower()
        for term in BANNED:
            assert term not in lowered, (
                f"label {event.detail!r} names the machinery ({term!r})"
            )
        assert len(event.detail) < 200
        if event.final:
            assert event.detail == "", (
                f"the closing event labelled itself {event.detail!r}; the label beside"
                f" a host's spinner is the host's to write"
            )

    return [e.detail for e in steps]


# ---------------------------------------------------------------------------
# 1. The Advisor's door
# ---------------------------------------------------------------------------


@pytest.fixture
def stubs_below_the_door(monkeypatch):
    """Stub the pipeline and the synthesis, opening scopes where the real ones do.

    The stubs' stage names and keys differ from the door's ON PURPOSE: an inner name
    reaching the channel is the visible symptom of a scope that installed instead of
    deferring.
    """
    from dialectical_framework.agents.explorer import explorer as exp_mod
    from dialectical_framework.agents.explorer.explorer import ExplorationResult
    from dialectical_framework.agents.explorer.skills import \
        generate_synthesis as gs_mod
    from dialectical_framework.concerns import create_nexus as cn_mod
    from dialectical_framework.concerns import expand_nexus as en_mod

    # The nexus phase is stubbed and reports NOTHING, which is deliberate on both
    # counts: real hashes would mean a real graph for a phase this file is not about,
    # and the phase is graph work whose every node and edge is already announced as an
    # effect on the `sid` channel. A step here would report the one phase that needs
    # no reporting — so its absence from these streams is the assertion, not an
    # omission.
    class _FakeNexus:
        short_hash = "nnnnnnn"

    class _CreateResult:
        nexus = _FakeNexus()

    async def stub_expand(self, nexus_hash, perspective_hashes):
        return None

    async def stub_create(self, intent, perspective_hashes, preset=None, title=None):
        return _CreateResult()

    monkeypatch.setattr(en_mod.ExpandNexus, "resolve", stub_expand)
    monkeypatch.setattr(cn_mod.CreateNexus, "resolve", stub_create)

    async def stub_pipeline(self):
        # `expect_progress` growth rather than `total=`, because that is how the real
        # pipeline's transformation phase sizes itself: it opens at 0 and grows as each
        # edge pair discovers what it owes.
        with progress_scope("transformation", key="inner-key"):
            expect_progress(2)
            report_progress("Working out what good looks like here")
            report_progress("Looking for concrete moves to take")
        return ExplorationResult(
            nexus_hash=self.nexus_hash,
            wheel_hashes=["top4444"],
            deepened_wheel_hashes=["top4444"],
        )

    async def stub_synthesis(self):
        with progress_scope("synthesis", key="inner-key", total=1):
            report_progress("Drawing out what emerges from the whole picture")
        return None

    monkeypatch.setattr(exp_mod.ExplorationPipeline, "resolve", stub_pipeline)
    monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)


class TestOneExploreIsOneProgressStream:
    """Asserted through `run_exploration_detailed`, which is where the scope lives.

    Not through the `@llm.tool`: that wrapper is one of three doors into this body —
    the nexus-scoped advisor variant and the Advisor's closing seam call it directly —
    and a stream that exists for one caller in three is worse than none, because the
    two silent paths look identical to a finished one.
    """

    async def test_one_closing_event_and_the_inner_steps_fold_in(
        self, bus, stubs_below_the_door
    ):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration_detailed

        case = Case()
        case.commit()

        events = await _collect(
            bus,
            case.sid,
            lambda: run_exploration_detailed(
                perspective_hashes=["aaaaaaa1", "bbbbbbb2"],
                intent="figure out the work relationship",
                nexus_hash="ccccccc3",
            ),
        )
        labels = _assert_one_stream(
            events, stage="exploration", key="ccccccc:aaaaaaa,bbbbbbb"
        )

        assert len(labels) == 3, (
            f"the transformation and synthesis steps did not both fold into the"
            f" door's stream: {labels}"
        )
        assert "Drawing out what emerges from the whole picture" in labels, (
            "the last phase of the call was dropped rather than deferred — a stream"
            " that closes before the work does is the defect this replaces"
        )

    async def test_the_key_names_the_tensions_and_survives_a_bracket_echo(
        self, bus, stubs_below_the_door
    ):
        """The key is built from RAW model output, above any attempt to resolve it.

        This framework renders hashes into prompts as `[[abc1234]]`, and a model
        echoing the brackets back is the most common malformed-hash shape here. Two
        spellings of one call keying two streams is the single thing a key prevents.
        Sorted, so the same SET of tensions keys the same stream however they were
        named.
        """
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration_detailed

        case = Case()
        case.commit()

        events = await _collect(
            bus,
            case.sid,
            lambda: run_exploration_detailed(
                perspective_hashes=[" [[bbbbbbb2]] ", "[[aaaaaaa1]]"],
                intent="",
                nexus_hash=None,
            ),
        )

        assert {e.key for e in events} == {"aaaaaaa,bbbbbbb"}, (
            f"key is {sorted({e.key for e in events})} — either prompt-template"
            f" punctuation reached a host-rendered surface, or the order the model"
            f" happened to name the tensions in changed the stream"
        )

    async def test_the_deferred_tensions_are_not_in_the_key(
        self, bus, stubs_below_the_door, di_container
    ):
        """The key describes the work DONE, not the work asked for.

        The perspective cap weaves the first N and reports the rest for a follow-up
        call — which is a different action and a different stream. A key covering the
        deferred ones would make this call's bar claim work it never started, the same
        mistake as counting them in the denominator.
        """
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration_detailed

        current = di_container.settings()
        di_container.settings.override(
            current.model_copy(update={
                "advisor_max_perspectives_per_exploration": 1
            })
        )
        try:
            case = Case()
            case.commit()
            events = await _collect(
                bus,
                case.sid,
                lambda: run_exploration_detailed(
                    perspective_hashes=["aaaaaaa1", "bbbbbbb2"],
                    intent="",
                    nexus_hash=None,
                ),
            )
        finally:
            di_container.settings.reset_override()
            di_container.settings.override(current)

        assert {e.key for e in events} == {"aaaaaaa"}, (
            f"key is {sorted({e.key for e in events})} — it names a tension this call"
            f" deferred rather than wove"
        )


# ---------------------------------------------------------------------------
# 2. The Explorer's door
# ---------------------------------------------------------------------------


class TestTheExplorerDoorOwnsItsStream:
    """`ExplorationPipeline` is called directly by the Explorer agent and by probes.

    Its key is the nexus rather than a digest, because there IS one node the person
    named to get here — `progress_hash_key`'s dividing line.
    """

    @pytest.fixture
    def stubbed_wheels(self, monkeypatch):
        from dialectical_framework.agents.explorer.skills import \
            build_wheels as bw_mod
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        class _Report:
            def __init__(self) -> None:
                self.ok = True
                self.summary = "built"
                self.artifacts: dict = {}

            def merge(self, other):
                return self

        class _Struct:
            def __init__(self, hash_: str) -> None:
                self.hash = hash_
                self.short_hash = hash_[:7]

        class _Result:
            new_cycles = [_Struct("cyc11111")]
            new_wheels = [_Struct("whl11111")]

        async def stub_build(self):
            # The real skill reports from inside `resolve`; a step from here proves the
            # scope is installed ABOVE the build phase and not merely around the
            # per-wheel fan-out that follows it.
            expect_progress(1)
            report_progress("Working out how these could cause one another")
            return _Result()

        monkeypatch.setattr(bw_mod.BuildWheels, "resolve", stub_build)
        monkeypatch.setattr(
            bw_mod.BuildWheels, "report", property(lambda self: _Report()),
            raising=False,
        )

        async def stub_transformations(self):
            with progress_scope("transformation", key="inner-key"):
                expect_progress(1)
                report_progress("Looking for concrete moves to take")
            return et_mod.ExploreTransformationsResult()

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", stub_transformations
        )

    async def test_the_build_phase_and_the_fan_out_share_one_stream(
        self, bus, stubbed_wheels
    ):
        from dialectical_framework.agents.explorer.explorer import \
            ExplorationPipeline

        case = Case()
        case.commit()

        events = await _collect(
            bus,
            case.sid,
            lambda: ExplorationPipeline(nexus_hash="nnnnnnn7").resolve(),
        )
        labels = _assert_one_stream(events, stage="exploration", key="nnnnnnn")

        assert len(labels) == 2, (
            f"expected the build step and the fan-out step in one stream: {labels}"
        )

    async def test_it_defers_when_a_caller_already_owns_a_stream(
        self, bus, stubbed_wheels
    ):
        """This is what makes the Advisor's door safe.

        Both doors name the same stage, which would be a collision if the inner one
        installed. It does not: `stage` and `key` are discarded and the declarations
        fold into the caller's denominator.
        """
        from dialectical_framework.agents.explorer.explorer import \
            ExplorationPipeline

        case = Case()
        case.commit()

        async def _under_an_outer_scope() -> None:
            with progress_scope("outer-owner", key="owner-key"):
                await ExplorationPipeline(nexus_hash="nnnnnnn7").resolve()

        events = await _collect(bus, case.sid, _under_an_outer_scope)

        assert {e.stage for e in events} == {"outer-owner"}, (
            f"stages seen: {sorted({e.stage for e in events})} — the pipeline"
            f" installed its own scope instead of deferring"
        )
        assert {e.key for e in events} == {"owner-key"}
        finals = [e for e in events if e.final]
        assert len(finals) == 1
        steps = [e for e in events if not e.final and not e.note]
        assert steps, "the pipeline's steps were dropped rather than folded in"
        assert finals[0].total == len(steps), (
            f"declarations did not reach the outer denominator:"
            f" {finals[0].done}/{finals[0].total} against {len(steps)} steps"
        )


# ---------------------------------------------------------------------------
# 3. The phase that had to be timed, not merely counted
# ---------------------------------------------------------------------------


def _nexus_over_two_tensions() -> Nexus:
    """A real Nexus with two complete Perspectives connected to it.

    Helpers imported from the sibling module rather than copied: they build a
    Perspective with its Polarity and all four aspect positions, which is what
    `PerspectiveCombination` needs to build anything at all.
    """
    from test_perspectives_batched_lookup import _perspective, _statement

    pp1 = _perspective(_statement("Hire fast"), _statement("Hire slowly"), "fast")
    pp2 = _perspective(_statement("Ship early"), _statement("Ship polished"), "ship")

    nexus = Nexus(intent="how to grow the team", preset="preset:balanced")
    nexus.commit()
    for pp in (pp1, pp2):
        pp.nexus.connect(nexus)
    return nexus


class TestBuildWheelsSpeaksBeforeItGoesQuiet:
    """The widest silence measured anywhere in this tree, and why a label is not enough.

    `PerspectiveCombination` is synchronous all the way down — at k=4 it built 24
    cycles and 96 wheels without a single await, 110.9s of a 163.2s wall with no event
    on either channel. A publish is a fire-and-forget task, so announcing that phase
    the ordinary way would deliver the label only once the phase had ENDED, and a host
    would show it for the instant before the next step replaced it. `flush_progress`
    is what buys the loop the turn it needs.

    Which makes the load-bearing assertion a TIMESTAMP, not a label: the count and the
    wording would be identical on the broken path.
    """

    async def test_the_combination_label_is_published_before_the_phase_returns(
        self, bus, monkeypatch
    ):
        from dialectical_framework.agents.explorer.skills.build_wheels import \
            BuildWheels
        from dialectical_framework.concerns import perspective_combination as pc_mod

        returned_at: list[float] = []
        real_resolve = pc_mod.PerspectiveCombination.resolve

        def timed_resolve(self, *args, **kwargs):
            result = real_resolve(self, *args, **kwargs)
            returned_at.append(time.time())
            return result

        monkeypatch.setattr(pc_mod.PerspectiveCombination, "resolve", timed_resolve)

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = _nexus_over_two_tensions()

        events = await _collect(
            bus,
            case.sid,
            lambda: BuildWheels(nexus_hash=nexus.hash).resolve(),
        )
        labels = [e.detail for e in events if not e.final and not e.note]

        assert returned_at, "the combination phase never ran — the fixture is broken"
        assert "Working out how these could cause one another" in labels, (
            f"the build phase is still silent: {labels}"
        )
        announced = next(
            e for e in events
            if e.detail == "Working out how these could cause one another"
        )
        assert announced.timestamp < returned_at[0], (
            f"the label was published {announced.timestamp - returned_at[0]:.3f}s"
            f" AFTER the phase it announces had finished — that is the 0.0s flash,"
            f" worse than silence, because it names the wait as over while the person"
            f" is still in it. `flush_progress` is what prevents it."
        )

    async def test_both_estimation_passes_announce_themselves(self, bus):
        """The two labels are what a person waits through: 112 provider calls at k=4.

        One step per pass and not one per structure — the calls are gathered per
        type+size group, so per-structure steps would all carry one timestamp.
        """
        from dialectical_framework.agents.explorer.skills.build_wheels import \
            BuildWheels

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = _nexus_over_two_tensions()

        events = await _collect(
            bus,
            case.sid,
            lambda: BuildWheels(nexus_hash=nexus.hash).resolve(),
        )
        labels = _assert_one_stream(
            events, stage="exploration", key=nexus.short_hash
        )

        assert "Weighing which order of events is most likely" in labels, (
            f"the cycle estimation pass never announced itself: {labels}"
        )
        assert "Weighing how well each arrangement holds up" in labels, (
            f"the wheel estimation pass never announced itself: {labels}"
        )

    async def test_an_empty_pass_declares_no_step(self, bus):
        """A single tension has nothing to order, and a phantom step cannot be filled.

        Layer-1 structures are excluded from estimation entirely, so with one
        perspective the two estimation steps must not be declared — a declared step
        that never reports is a denominator a bar can never reach.
        """
        from dialectical_framework.agents.explorer.skills.build_wheels import \
            BuildWheels
        from test_perspectives_batched_lookup import _perspective, _statement

        case = Case()
        case.commit()
        with scope(case.sid):
            pp = _perspective(_statement("Only one"), _statement("Its opposite"), "one")
            nexus = Nexus(intent="a single tension", preset="preset:balanced")
            nexus.commit()
            pp.nexus.connect(nexus)

        events = await _collect(
            bus,
            case.sid,
            lambda: BuildWheels(nexus_hash=nexus.hash).resolve(),
        )
        labels = [e.detail for e in events if not e.final and not e.note]

        assert labels == ["Working out how these could cause one another"], (
            f"expected the build label alone on the single-tension path: {labels}"
        )


# ---------------------------------------------------------------------------
# 4. The seam primitive the above depends on
# ---------------------------------------------------------------------------


class TestFlushProgressDelivers:
    """`flush_progress` is a fixed number of loop turns. This is what fixes the number.

    `_FLUSH_TURNS` counts the hops the in-memory bus needs — the `_send` task, the
    broadcaster's backend listener, the subscriber's own queue — and a wrong count is
    invisible everywhere else: the event still arrives, just later, which on the path
    this exists for means after the synchronous phase it was meant to precede.
    """

    async def _stream(self, bus, sid: str):
        received: list = []
        ready = asyncio.Event()

        async def _listen() -> None:
            async with bus.subscribe_progress(sid) as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        listener = asyncio.create_task(_listen())
        await ready.wait()
        return received, listener

    async def test_an_announced_step_has_arrived_when_the_flush_returns(self, bus):
        case = Case()
        case.commit()
        received, listener = await self._stream(bus, case.sid)
        try:
            with scope(case.sid), progress_scope("exploration", key="k"):
                expect_progress(1)
                report_progress("Working out how these could cause one another")
                # The control, and the whole reason this function exists: a publish is
                # `loop.create_task`, so with no yield the send has not even STARTED.
                assert received == [], (
                    "an event arrived without the loop being given a turn — if this"
                    " ever holds, `_publish` no longer defers and `flush_progress`"
                    " has nothing to do"
                )
                await flush_progress()
                assert len(received) == 1, (
                    f"after the flush the subscriber holds {len(received)} events —"
                    f" `_FLUSH_TURNS` is too low for the bus's fan-out, so every"
                    f" label in front of a synchronous phase still arrives late"
                )
                assert received[0].detail == (
                    "Working out how these could cause one another"
                )
        finally:
            listener.cancel()

    async def test_it_is_harmless_with_no_scope_installed(self, bus):
        """Callers should not have to ask whether anything is listening."""
        await flush_progress()
