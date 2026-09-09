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
                                                  note_progress,
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

    @pytest.mark.asyncio
    async def test_the_closing_event_carries_no_label_of_its_own(self, bus):
        """The stage name is not prose, and "done" is a claim `done` cannot back.

        This closed with `f"{stage} finished"` for a long time, and it was wrong three
        ways at once. It repeated `stage`, which the event already carries in its own
        field. It put an internal name in front of a person: the vocabulary tests on
        `ingest`, `anchor` and `analyze` all had to exempt `final` to stay green, and
        that exemption hid a live leak — `synthesis` is a banned word, and
        `GenerateSynthesis` opens its own scope under the Advisor's `explore`, which
        installs none, so `"synthesis finished"` went out on the silent path. And every
        cheerful replacement ("Done", "Finished") asserts success, which `done` cannot
        support: it counts steps ANNOUNCED, so a run whose last step raised still
        closes full.

        So the closing event says only what it knows — `final=True` and the counters —
        and the label belongs to the host. Pinned here at the seam rather than only in
        the three vocabulary tests, because those would each go green again if this
        regressed to a word they happen not to ban.
        """
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-empty") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-empty"), progress_scope("synthesis", total=1):
            report_progress("Drawing out what emerges from the whole picture")

        got = await _drain_list(received)
        listener.cancel()

        final = [e for e in got if e.final]
        assert len(final) == 1
        assert final[0].detail == "", (
            f"the closing event labelled itself {final[0].detail!r}; a host writes"
            f" that line from `stage`, `key`, `done` and `total`"
        )
        assert final[0].stage == "synthesis", (
            "the stage must still be on the event — dropping the detail moves the"
            " label to the host, it does not withhold what the host needs"
        )

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


class TestANoteSaysSomethingWithoutClaimingAStep:
    """The third kind of event, and the counters must not notice it.

    `note_progress` exists for N gathered single calls — all starting at one
    instant, each unsubdividable, returning at different times. The only thing that
    makes it safe is that it touches nothing: if a note ever incremented `done`,
    every one of them would be a step nobody expected, `done` would overshoot
    `total`, and a host would render past 100% on the one path where the person is
    watching hardest (`SourceDigest`'s parts, seconds after they paste a document).
    """

    @pytest.mark.asyncio
    async def test_a_note_moves_the_label_and_leaves_the_bar_alone(self, bus):
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-note") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-note"), progress_scope("s", total=2) as prog:
            report_progress("reading part 1 of 2")
            report_progress("reading part 2 of 2")
            note_progress("1 of 2 parts read")
            note_progress("2 of 2 parts read")
            assert prog.done == 2, "a note was counted as a step"
            assert prog.total == 2, "a note grew the denominator"

        got = await _drain_list(received)
        listener.cancel()

        notes = [e for e in got if e.note]
        assert [e.detail for e in notes] == ["1 of 2 parts read", "2 of 2 parts read"]
        # Both notes carry the counters the last STEP left behind — same numbers,
        # twice, which is exactly the signal "still working, nothing new completed
        # in the accounting sense".
        assert all((e.done, e.total) == (2, 2) for e in notes)
        assert all(not e.note for e in got if e.final), (
            "the closing event was flagged a note — a host clears on `final`"
        )
        steps = [e for e in got if not e.final and not e.note]
        assert len(steps) == 2 and all(e.note is False for e in steps)

    @pytest.mark.asyncio
    async def test_notes_do_not_disturb_the_closing_accounting(self, bus):
        """`final.done == final.total` is the invariant every progress test rests on."""
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-note2") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-note2"), progress_scope("s") as prog:
            expect_progress(3)
            for i in range(3):
                report_progress(f"step {i}")
                note_progress(f"{i + 1} of 3 done")
            assert prog.done == 3 and prog.total == 3

        got = await _drain_list(received)
        listener.cancel()

        final = next(e for e in got if e.final)
        assert (final.done, final.total) == (3, 3)

    def test_a_note_without_a_scope_is_a_noop(self):
        assert current_progress_scope() is None
        note_progress("nobody is listening")

    @pytest.mark.asyncio
    async def test_a_note_arriving_after_final_is_dropped(self, bus):
        """Same straggler guard as `report_progress`, for the same reason.

        A gathered part that outlives its scope still holds a context copy pointing
        at it. A note published after the `final` event would tell a host that had
        already cleared its indicator that something is still landing — and unlike a
        late step this one moves no counter, so nothing else in the accounting would
        reveal it. The channel is the only witness, so assert on the channel.
        """
        received = []

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-note3") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        ready = asyncio.Event()
        listener = asyncio.create_task(_listen())
        await ready.wait()

        release = asyncio.Event()
        late_detail = "a part came back after everything closed"

        async def _straggler() -> None:
            await release.wait()
            note_progress(late_detail)

        with scope("sid-note3"):
            with progress_scope("s", total=1) as prog:
                late = asyncio.create_task(_straggler())
                report_progress("on time")
            release.set()
            await late

        got = await _drain_list(received)
        listener.cancel()

        assert prog._closed, "the scope should have closed before the straggler ran"
        assert late_detail not in [e.detail for e in got], (
            "a note published after the `final` event reached the channel"
        )
        assert got[-1].final, "the closing event was no longer last"


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


class TestNestingDefersToTheInstalledScope:
    """A nested scope installs nothing: the outermost owns the stream.

    Deliberately unlike `call_census`/`retry_accounting`, which are stacks — and
    deliberately unlike the rule that used to be here (innermost wins, outer resumes
    on exit), which never described a real nesting in this tree. The only real one is
    `deepen`, whose two skills each open a scope: under the old rule the tool
    published TWO `final` events for one action and a host cleared its indicator
    halfway through.
    """

    def test_a_nested_scope_hands_back_the_outer_one(self):
        with progress_scope("outer", total=1) as outer:
            with progress_scope("inner", total=1) as inner:
                assert inner is outer, (
                    "the nested scope installed its own — a host would see two"
                    " denominators, and two `final` events, for one action"
                )
                report_progress("belongs to the one stream")
            report_progress("outer again")
            assert outer.done == 2
            assert outer.total == 2, (
                "the nested scope's declared step was lost — a deferring skill still"
                " does its work, so its total belongs to the outer denominator"
            )

    @pytest.mark.asyncio
    async def test_only_the_outermost_publishes_a_final(self, bus):
        """THE claim `deepen` needed. A host clears its indicator on `final`."""
        received = []
        ready = asyncio.Event()

        async def _listen() -> None:
            async with bus.subscribe_progress("sid-nest") as subscriber:
                ready.set()
                async for event in subscriber:
                    received.append(event.message)

        listener = asyncio.create_task(_listen())
        await ready.wait()

        with scope("sid-nest"), progress_scope("tool", key="k1"):
            with progress_scope("skill-a", key="a", total=1):
                report_progress("first skill")
            with progress_scope("skill-b", key="b", total=1):
                report_progress("second skill")

        got = await _drain_list(received)
        listener.cancel()

        finals = [e for e in got if e.final]
        assert len(finals) == 1, (
            f"{len(finals)} closing events for one tool call — the sequential-sibling"
            " case, which is what `deepen` actually does"
        )
        assert finals[0].stage == "tool" and finals[0].done == 2
        assert {e.stage for e in got} == {"tool"}, (
            "an inner stage name reached the channel: one call is one stream, and a"
            f" host keying on (stage, key) would treat these as three. Got: {got}"
        )
        assert {e.key for e in got} == {"k1"}

    def test_a_closed_outer_scope_swallows_the_stragglers(self):
        """The alternative would be a fresh stream, `final` and all, after the tool
        returned — the same straggler `report_progress` already refuses."""
        with progress_scope("outer") as outer:
            pass
        assert outer._closed

        # The context copy a straggling task holds still points at the closed scope.
        token = progress_module._current.set(outer)
        try:
            with progress_scope("late", total=3) as late:
                assert late is outer
                report_progress("nobody should hear this")
            assert outer.done == 0
        finally:
            progress_module._current.reset(token)


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


class TestOneKeyConstructionForEveryStream:
    """`progress_key` is a hoist, so the pin is that it changed no digest.

    Four tools had hand-written copies of the same sha256 one-liner before this
    existed, each keyed on its own arguments, and `add_input` would have been the
    fifth. Delegating them is only safe if the bytes are identical — a rekey is
    invisible everywhere else in this suite, because every assertion about a key
    elsewhere compares it to what the same function just returned. So these assert
    against LITERAL digests of the documented material, computed here rather than
    by calling the thing under test.
    """

    def _digest(self, material: str) -> str:
        import hashlib

        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]

    def test_parts_join_with_newlines_and_lists_with_commas(self):
        from dialectical_framework.utils.progress import progress_key

        assert progress_key("a", ["b", "c"]) == self._digest("a\nb,c")
        assert progress_key("only") == self._digest("only")

    def test_a_missing_part_is_an_empty_string_not_the_word_none(self):
        """`None` must contribute nothing, and a tuple counts as a list.

        The tools pass `Optional[str]` and `Optional[list[str]]` straight through,
        so `str(None)` leaking into the material would make an omitted argument
        indistinguishable from one whose text is literally "None".
        """
        from dialectical_framework.utils.progress import progress_key

        assert progress_key(None, None) == self._digest("\n")
        assert progress_key("a", None) == self._digest("a\n")
        assert progress_key("a", ("b", "c")) == progress_key("a", ["b", "c"])

    def test_the_four_delegates_still_produce_their_original_digests(self):
        """The hoist's whole risk, asserted one tool at a time."""
        from dialectical_framework.agents.advisor.tools.anchor import \
            _progress_key as anchor_key
        from dialectical_framework.agents.advisor.tools.ingest import \
            _progress_key as ingest_key
        from dialectical_framework.agents.advisor.tools.record_decision import \
            _progress_key as decision_key
        from dialectical_framework.agents.analyst.analyst import \
            _progress_key as analyze_key

        assert ingest_key("some text", ["h1", "h2"]) == self._digest(
            "some text\nh1,h2"
        )
        assert ingest_key(None, None) == self._digest("\n")
        assert anchor_key("Stay put", "Move on") == self._digest("Stay put\nMove on")
        assert anchor_key("Stay put", None) == self._digest("Stay put\n")
        assert decision_key("Leave?", "Yes") == self._digest("Leave?\nYes")
        assert analyze_key("situation", ["t1"], ["i1"]) == self._digest(
            "situation\nt1\ni1"
        )
        assert analyze_key(None, None, None) == self._digest("\n\n")

    def test_the_same_call_keys_the_same_stream_twice(self):
        """Content-derived is the point: a retry must not open a second bar."""
        from dialectical_framework.utils.progress import progress_key

        assert progress_key("x", ["y"]) == progress_key("x", ["y"])
        assert progress_key("x", ["y"]) != progress_key("x", ["z"])

    def test_the_key_carries_none_of_the_words_it_was_built_from(self):
        """A key is a host-rendered surface; most of these parts are the person's
        own text, and one of them is whole pasted documents."""
        from dialectical_framework.utils.progress import progress_key

        key = progress_key("Should I leave Ravensbourne?", ["abc1234"])
        assert "Ravensbourne" not in key
        assert "abc1234" not in key
        assert len(key) == 10


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
