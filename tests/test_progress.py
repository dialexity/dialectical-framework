"""Tests for the `sid:progress` channel and the scope that feeds it.

The load-bearing claims, in order of what would hurt most if they broke:

1. **An existing graph-event subscriber sees nothing new.** This is the entire
   reason the separate channel was chosen over widening `GraphEvent`, so it is
   asserted directly rather than inferred from the channel name.
2. **A gathered child's reports reach the parent's scope.** ContextVar copies make
   this the failure mode that would silently produce an empty progress stream while
   every unit test on the scope object still passed.
3. **A task created before the scope is installed reports nothing.** The ordering
   trap, asserted so the requirement is executable rather than a comment.
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.execution_report import (Effect,
                                                          ExecutionReport,
                                                          NodeRef)
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.events.progress_event import (
    PROGRESS_CHANNEL_SUFFIX, ProgressEvent, progress_channel)
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.progress import (current_progress_scope,
                                                  expect_progress,
                                                  progress_scope,
                                                  report_progress)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override — this test module doesn't need the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override — this test module doesn't need the DB."""
    yield


@pytest.fixture
async def bus():
    b = GraphEventBus()
    await b.connect()
    # RESTORE rather than clear on teardown: the module-level bus is wired once by
    # the session-scoped `di_container` fixture, so setting it to None here would
    # silently disable progress for every test that ran afterwards — including the
    # e2e probe, whose whole point is to see these events.
    previous = progress_module._event_bus
    progress_module.set_event_bus(b)
    yield b
    progress_module.set_event_bus(previous)
    await b.disconnect()


class TestTheGraphChannelIsUntouched:
    """The promise that makes this change safe to ship to existing hosts."""

    @pytest.mark.asyncio
    async def test_progress_never_appears_on_the_graph_channel(self, bus):
        """A host subscribed the old way must not receive a single new message.

        This is THE contract. If it fails, hosts doing `event.message.effect`
        break on upgrade, which is precisely what the separate channel was chosen
        to avoid.
        """
        received = []

        async def _listen() -> None:
            async with bus.subscribe("sid-a") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-a"), progress_scope("transformation") as prog:
            prog.expect(3)
            report_progress("step one")
            report_progress("step two")

        await asyncio.sleep(0.2)
        listener.cancel()

        assert received == [], (
            "a progress signal reached the graph mutation channel — every existing"
            f" subscriber would now be handed {received!r}, whose `.effect` is absent"
        )

    @pytest.mark.asyncio
    async def test_graph_effects_never_appear_on_the_progress_channel(self, bus):
        """And the reverse, so a host can render progress without type-checking."""
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-b") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        await bus.publish(
            "sid-b",
            Effect(seq=0, effect_type="node_created", node=NodeRef(label="Statement")),
        )
        await asyncio.sleep(0.2)
        listener.cancel()

        assert received == []

    def test_the_progress_channel_is_never_the_sid(self):
        """A suffix collision would fan progress straight into the graph stream."""
        assert progress_channel("abc") != "abc"
        assert progress_channel("abc").startswith("abc")
        assert PROGRESS_CHANNEL_SUFFIX


class TestConcurrentReportersShareOneScope:
    """The ContextVar-copy failure mode, which unit tests on the object cannot see."""

    @pytest.mark.asyncio
    async def test_gathered_children_report_into_the_parents_scope(self, bus):
        """Six concurrent workers, one denominator, every step counted.

        A `ContextVar.set()` inside a child is invisible to the parent — so the
        scope has to be a mutable object shared by reference. If it ever becomes
        immutable (or gets re-`set` per child), this is the test that catches it:
        the events would carry `total=0` and a fraction of the steps.
        """
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-c") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        async def _worker(n: int) -> None:
            expect_progress(2)
            report_progress(f"worker {n} first")
            await asyncio.sleep(0)
            report_progress(f"worker {n} second")

        with scope("sid-c"), progress_scope("transformation", key="wheel7") as prog:
            await asyncio.gather(*[_worker(n) for n in range(6)])
            assert prog.total == 12, "children's `expect` did not reach the parent"
            assert prog.done == 12, "children's `report_progress` did not reach it"

        await asyncio.sleep(0.2)
        listener.cancel()

        steps = [e for e in received if not e.final]
        assert len(steps) == 12
        assert all(isinstance(e, ProgressEvent) for e in received)
        assert all(e.stage == "transformation" for e in received)
        assert all(e.key == "wheel7" for e in received)
        # Every step index is claimed exactly once — no two children published the
        # same `done`, which is what a per-child counter would have produced.
        assert sorted(e.done for e in steps) == list(range(12))

    @pytest.mark.asyncio
    async def test_a_task_created_before_the_scope_reports_nothing(self, bus):
        """The ordering trap, made executable.

        `asyncio.ensure_future` captures the context at creation, so work started
        before the scope exists cannot see it. This is asserted because the fix for
        it (create tasks INSIDE the scope) is invisible in a diff and the symptom is
        a silent empty stream.
        """
        started = asyncio.Event()
        release = asyncio.Event()

        async def _early() -> None:
            started.set()
            await release.wait()
            report_progress("from a task that predates the scope")

        with scope("sid-d"):
            early = asyncio.create_task(_early())
            await started.wait()

            with progress_scope("transformation") as prog:
                release.set()
                await early
                assert prog.done == 0, (
                    "a task created before the scope reported into it — the"
                    " ContextVar is being read at publish time from the wrong place"
                )


class TestTheCountersTellTheTruth:

    @pytest.mark.asyncio
    async def test_detail_describes_the_step_that_just_started(self, bus):
        """`done` is finished-count, `detail` is in-flight — so they disagree by one.

        Documented and asserted because the alternative reading ("done includes the
        step named in detail") makes a host show work as complete while it runs.
        """
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-e") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-e"), progress_scope("s", total=2):
            report_progress("first")
            report_progress("second")

        got = await _drain_list(received)
        listener.cancel()

        first = next(e for e in got if e.detail == "first")
        second = next(e for e in got if e.detail == "second")
        assert first.done == 0 and first.total == 2
        assert second.done == 1 and second.total == 2

    @pytest.mark.asyncio
    async def test_the_final_event_reports_what_completed_not_what_was_promised(
        self, bus
    ):
        """A partial build says so. Rounding `done` up to `total` would hide it."""
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-f") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-f"), progress_scope("s", total=5):
            report_progress("only one of five ran")

        got = await _drain_list(received)
        listener.cancel()

        final = [e for e in got if e.final]
        assert len(final) == 1, "exactly one closing event, so a host can clear once"
        assert final[0].done == 1
        assert final[0].total == 5

    @pytest.mark.asyncio
    async def test_the_final_event_fires_even_when_the_work_raises(self, bus):
        """Otherwise a crash leaves every host spinning forever."""
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-g") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with pytest.raises(RuntimeError):
            with scope("sid-g"), progress_scope("s", total=2):
                report_progress("about to blow up")
                raise RuntimeError("boom")

        got = await _drain_list(received)
        listener.cancel()

        assert any(e.final for e in got)

    def test_expect_is_additive_because_work_is_discovered_lazily(self):
        with progress_scope("s") as prog:
            assert prog.total == 0
            prog.expect(4)
            prog.expect(6)
            assert prog.total == 10, (
                "assignment rather than addition — the second discoverer would"
                " erase the first one's work"
            )

    def test_a_negative_or_zero_expectation_is_ignored(self):
        with progress_scope("s", total=3) as prog:
            prog.expect(0)
            prog.expect(-5)
            assert prog.total == 3


class TestNoScopeCostsNothing:
    """`report_progress` sits on a hot path and must be free when unused."""

    def test_reporting_without_a_scope_is_a_noop(self):
        assert current_progress_scope() is None
        report_progress("nobody is listening")
        expect_progress(10)

    @pytest.mark.asyncio
    async def test_reporting_without_a_bus_is_a_noop(self):
        previous = progress_module._event_bus
        progress_module.set_event_bus(None)
        try:
            with scope("sid-h"), progress_scope("s", total=1) as prog:
                report_progress("no bus wired")
            assert prog.done == 1, "counting must not depend on a bus being present"
        finally:
            progress_module.set_event_bus(previous)

    @pytest.mark.asyncio
    async def test_reporting_outside_a_sid_scope_is_a_noop(self, bus):
        """No sid means no channel to publish on. Must not raise."""
        with progress_scope("s", total=1):
            report_progress("no sid in context")
        await asyncio.sleep(0.1)

    def test_reporting_outside_an_event_loop_is_a_noop(self):
        """Sync callers exist; a missing loop is not their problem."""
        with progress_scope("s", total=1):
            report_progress("no running loop")


class TestNestingKeepsOnlyTheInnermost:
    """Deliberately unlike `call_census`/`retry_accounting`, which are stacks."""

    def test_the_inner_scope_shadows_and_the_outer_resumes(self):
        with progress_scope("outer", total=1) as outer:
            with progress_scope("inner", total=1) as inner:
                report_progress("belongs to inner only")
                assert inner.done == 1
                assert outer.done == 0, (
                    "both scopes counted one step — a host would see two"
                    " denominators for one instant"
                )
            report_progress("outer again")
            assert outer.done == 1


class TestProgressStepsMatchesTheCalls:
    """`PROGRESS_STEPS` is a denominator; drift makes every bar wrong, silently."""

    def _assert_matches(self, cls) -> None:
        import inspect

        # The WHOLE class, not `resolve` alone: a step moved into a helper (as
        # `ExpandPolarity` already does) would otherwise leave the constant wrong
        # while this test stayed green — the same reasoning as the anchor-headline
        # tripwire in `test_prompt_review_regressions.py`.
        source = inspect.getsource(cls)
        calls = source.count("report_progress(")
        assert calls == cls.PROGRESS_STEPS, (
            f"{cls.__name__}.resolve() reports {calls} step(s) but PROGRESS_STEPS"
            f" says {cls.PROGRESS_STEPS} — callers size their denominator from the"
            " constant, so every progress fraction is now wrong"
        )

    def test_the_declared_step_count_equals_the_reporting_calls(self):
        from dialectical_framework.concerns.transformation_generation import \
            TransformationGeneration

        self._assert_matches(TransformationGeneration)

    def test_the_anchor_skills_declare_what_they_report(self):
        """The two `anchor` legs, whose constants are their OWN denominator.

        Unlike `TransformationGeneration`, these two call `expect_progress` with
        their own `PROGRESS_STEPS`, so drift here does not merely mis-size a
        caller's bar — it makes the skill lie about itself, and the fraction it
        publishes can never reach its own total.
        """
        from dialectical_framework.agents.analyst.skills.anchor_theses import \
            AnchorTheses
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity

        self._assert_matches(IntroducePolarity)
        self._assert_matches(AnchorTheses)


async def _drain_list(received: list, *, timeout: float = 1.0) -> list:
    """Wait until `received` stops growing. Publishes are fire-and-forget."""
    previous = -1
    deadline = 0.0
    while previous != len(received) and deadline < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        deadline += 0.05
    return list(received)


class TestAStragglerCannotReopenAClosedScope:

    @pytest.mark.asyncio
    async def test_a_step_arriving_after_final_is_dropped(self):
        """A task outliving its scope still holds a context copy pointing at it.

        Without the `_closed` guard its late step would publish after the `final`
        event, telling a host that had already cleared its indicator to start over.
        """
        release = asyncio.Event()
        scope_seen: list = []

        async def _straggler() -> None:
            await release.wait()
            report_progress("late")
            scope_seen.append(current_progress_scope())

        with scope("sid-i"):
            with progress_scope("s", total=2) as prog:
                late = asyncio.create_task(_straggler())
                report_progress("on time")
            release.set()
            await late

        assert prog.done == 1, "a late step was counted after the scope closed"
