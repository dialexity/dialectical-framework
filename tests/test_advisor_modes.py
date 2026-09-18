"""
`Advisor(mode=...)` — the three surfaces, and what holds them together.

    FULL        builds, records.            the Advisor as shipped
    CONSULTANT  records, never builds.      a graph that already exists, consulted
    VIEW        reads, nothing else.        a seat that is not the one doing the work

The contract is enforced in two places and nowhere else: the TOOLSET (what the
head is never handed it cannot reach) and the closing seam — which DECLINES on
VIEW (`_repair_unrecorded_decision` returns before the classifier is asked) and
on CONSULTANT records the decision, grounds it on what exists, and WITHHOLDS the
weave (`_schedule_pathway_construction` returns `NOT_BUILDING` before touching
the queue). The prompt is told which surface it is on so the head does not spend
turns reaching for what it does not have — but the prompt is not what stops it,
which is the same division of labour as the nexus pin.

Three things in here are worth knowing before editing them.

`_BUILD_TOOL_NAMES` / `_WRITE_TOOL_NAMES` (the prompt's two sets) and the three
toolset factories are lists that must agree, and nothing but
`TestTheListsAreOne` holds them together: a tool added to one and not the other
gives a head that holds a build tool while being told it has none, or a full
Advisor whose own prompt renders as a consultant's.

The seam tests assert what was CONCLUDED, not merely what was written — a repair
that ran and then failed to write looks identical from the outside, and it is not
the same fact.

And `_settle_deferred_work` / `_refresh_context` deliberately still run on every
surface: settling honours one-writer-per-sid (a reading head on a half-woven
graph is worse than one on a shallow graph) and the refresh is a read.
`TestTheGateHasThreeSites` is what keeps a well-meaning "not building means do
nothing" edit from taking them.
"""

from __future__ import annotations

import inspect

import pytest

from dialectical_framework.agents.advisor.advisor import (
    Advisor, _build_consultant_tools, _build_tools, _build_view_tools)
from dialectical_framework.agents.advisor.mode import AdvisorMode
from dialectical_framework.agents.advisor.system_prompts import (
    DEFAULT_TOOL_NAMES, _BUILD_TOOL_NAMES, _WRITE_TOOL_NAMES, system_prompt)
from dialectical_framework.agents.advisor.tools.scoped import \
    build_scoped_tools
from dialectical_framework.agents.turn_timing import (ClosingOutcome,
                                                      DeferralOutcome)
from dialectical_framework.concerns.decision_confirmation_check import (
    ConfirmationVerdictDto, DecisionConfirmationCheck)
from dialectical_framework.concerns.record_decision import RecordDecision
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.scope_context import scope

# The DB-free repair stub, imported rather than re-declared: it binds the REAL
# seam methods, and a second copy would drift from the one every other seam test
# drives (`tests/` is on sys.path — see CLAUDE.md, Testing).
from test_decision_confirmation_repair import _StubAdvisor

READING = {"sync", "inspect_node", "read_digest"}
DECIDING = {"record_decision", "discard", "audit_feasibility"}
BUILDING = {"ingest", "anchor", "explore", "deepen"}

MANDATE = "## What Is Not Available Here"


def _names(tools: list) -> set[str]:
    return {t.__name__ for t in tools}


def _tool_by_name(tools: list, name: str):
    return next(t for t in tools if t.__name__ == name)


def _new_nexus() -> Nexus:
    """A committed nexus in a fresh scope, for the pinned factory."""
    nexus = Nexus(intent="advisor modes test")
    nexus.save()
    nexus.commit()
    return nexus


class TestTheToolsetsAreTheSurfaces:
    """What the head is handed, which is the whole enforcement."""

    async def test_view_holds_the_three_reading_tools(self):
        assert _names(Advisor(mode=AdvisorMode.VIEW)._tools) == READING

    async def test_consultant_holds_reading_plus_deciding_and_no_build_tool(self):
        names = _names(Advisor(mode=AdvisorMode.CONSULTANT)._tools)
        assert names == READING | DECIDING
        assert not names & BUILDING

    async def test_full_holds_everything(self):
        assert _names(Advisor()._tools) == READING | DECIDING | BUILDING

    async def test_the_mode_accepts_its_string_value(self):
        """A host reading the mode from config passes a string; the constructor
        normalises it, so `mode="consultant"` is the same surface."""
        assert _names(Advisor(mode="consultant")._tools) == READING | DECIDING
        assert Advisor(mode="view")._mode is AdvisorMode.VIEW

    async def test_the_factories_alone_say_the_same(self):
        """Called directly, so a future `__init__` branch cannot be the only
        thing keeping a surface narrow."""
        assert _names(_build_view_tools()) == READING
        assert _names(_build_consultant_tools()) == READING | DECIDING
        assert _names(_build_tools()) == READING | DECIDING | BUILDING

    @pytest.mark.parametrize(
        "mode, expected",
        [
            (AdvisorMode.VIEW, READING),
            (AdvisorMode.CONSULTANT, READING | DECIDING),
            (AdvisorMode.FULL, READING | DECIDING | (BUILDING - {"ingest"})),
        ],
    )
    async def test_the_scoped_head_keeps_the_pin_on_every_surface(
        self, mode, expected
    ):
        """The pinned `sync`, not the unscoped one, on all three.

        The discriminator is the SIGNATURE, not the name: both are called
        `sync`, and only the unscoped one exposes `nexus_hash` for the model to
        redirect. Asserting on the name would pass with the pin gone. (`ingest`
        is never wired when pinned — bulk extraction belongs to the unscoped
        flow.)
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            tools = build_scoped_tools(_new_nexus().hash[:7], mode=mode)

        assert _names(tools) == expected
        sync = _tool_by_name(tools, "sync")
        assert list(inspect.signature(sync).parameters) == [], (
            "the scoped head got the UNSCOPED sync — it can be pointed at any "
            "exploration in the case"
        )

    async def test_app_tools_are_still_merged_on_the_narrow_surfaces(self):
        """Deliberate, and documented at the parameter: the framework cannot
        tell a host's chart lookup from a host's write, so the mode governs the
        framework's own surface and the host owns its own."""
        from mirascope import llm

        @llm.tool
        async def lookup_natal_chart(person: str) -> str:
            """Look up the natal chart for a person."""
            return f"chart for {person}"

        view = Advisor(mode=AdvisorMode.VIEW, app_tools=[lookup_natal_chart])
        assert _names(view._tools) == READING | {"lookup_natal_chart"}
        consultant = Advisor(
            mode=AdvisorMode.CONSULTANT, app_tools=[lookup_natal_chart]
        )
        assert _names(consultant._tools) == (
            READING | DECIDING | {"lookup_natal_chart"}
        )


class TestTheListsAreOne:
    """The toolset factories and the prompt's two name sets are halves of one list.

    `system_prompt` derives the render from `_BUILD_TOOL_NAMES` and
    `_WRITE_TOOL_NAMES` while the factories decide what is actually handed over,
    and nothing else compares them. Drift in either direction is silent and bad
    in a different way: a build tool missing from the set gives a head holding
    it and a prompt saying it has none; a read tool wrongly in a set makes the
    full Advisor's own prompt render as a narrower surface's.
    """

    def test_the_default_toolset_splits_exactly_into_reads_and_writes(self):
        assert set(DEFAULT_TOOL_NAMES) == READING | _WRITE_TOOL_NAMES

    def test_build_is_a_strict_subset_of_write(self):
        assert _BUILD_TOOL_NAMES < _WRITE_TOOL_NAMES
        assert _BUILD_TOOL_NAMES == BUILDING

    def test_the_view_gets_exactly_what_is_not_a_write(self):
        assert set(DEFAULT_TOOL_NAMES) - _names(_build_view_tools()) == (
            _WRITE_TOOL_NAMES
        )

    def test_the_consultant_gets_exactly_what_is_not_a_build(self):
        assert set(DEFAULT_TOOL_NAMES) - _names(_build_consultant_tools()) == (
            _BUILD_TOOL_NAMES
        )

    def test_audit_feasibility_is_a_write_and_not_a_build(self):
        """It reads like a read and is not: a FeasibilityEstimation plus a
        critique Rationale, two provider calls per pathway. But it adds no
        structure, so the consultant keeps it. Pinned by name because it is the
        one member a reader would move."""
        assert "audit_feasibility" in _WRITE_TOOL_NAMES
        assert "audit_feasibility" not in _BUILD_TOOL_NAMES
        assert "audit_feasibility" not in _names(_build_view_tools())
        assert "audit_feasibility" in _names(_build_consultant_tools())

    def test_discard_is_a_write_and_not_a_build(self):
        """A write with the softest possible name — a soft-marked node is out of
        every active query afterwards — and the consultant's way of honouring a
        rejection."""
        assert "discard" in _WRITE_TOOL_NAMES
        assert "discard" not in _BUILD_TOOL_NAMES
        assert "discard" not in _names(_build_view_tools())
        assert "discard" in _names(_build_consultant_tools())


class TestThePromptFollowsTheToolset:
    """Rendered from the tool NAMES, so the prompt cannot disagree with the
    tools the head holds — there is no second parameter to get out of step."""

    def _view(self, scoped: bool = False) -> str:
        return system_prompt(
            tool_names=sorted(READING),
            scoped_nexus_hash="abc1234" if scoped else None,
        )

    def _consultant(self, scoped: bool = False) -> str:
        return system_prompt(
            tool_names=sorted(READING | DECIDING),
            scoped_nexus_hash="abc1234" if scoped else None,
        )

    def test_each_narrow_surface_renders_its_own_mandate(self):
        view, consultant = self._view(), self._consultant()
        assert MANDATE in view and "This surface reads." in view
        assert MANDATE in consultant
        assert "This surface consults; it does not build." in consultant
        assert "This surface consults" not in view
        assert "This surface reads." not in consultant

    def test_the_full_render_has_no_mandate(self):
        assert MANDATE not in system_prompt()

    def test_one_build_name_turns_the_consultant_render_off(self):
        """Derived from the names rather than passed as a flag: a scoped session
        wiring a single build tool is a building surface."""
        render = system_prompt(tool_names=sorted(READING | DECIDING | {"anchor"}))
        assert MANDATE not in render

    def test_one_write_name_turns_the_view_render_into_the_consultant_one(self):
        render = system_prompt(tool_names=sorted(READING | {"discard"}))
        assert "This surface consults" in render
        assert "This surface reads." not in render

    def test_an_unknown_app_tool_name_does_not_widen_either_surface(self):
        """App tools are never in either set — a host's own lookup must not
        turn the framework's narrow render off."""
        assert "This surface reads." in system_prompt(
            tool_names=sorted(READING | {"lookup_natal_chart"})
        )
        assert "This surface consults" in system_prompt(
            tool_names=sorted(READING | DECIDING | {"lookup_natal_chart"})
        )

    def test_the_building_arc_is_dropped_on_both(self):
        """Same reason it is dropped when scoped: the arc IS the building
        sequence, and there is nothing here to build with."""
        assert "## Default Arc" not in self._view()
        assert "## Default Arc" not in self._consultant()
        assert "## Default Arc" in system_prompt()

    def test_the_convergence_engine_renders_where_decisions_are_wired(self):
        assert "Decision Readiness" not in self._view()
        assert "Decision Readiness" in self._consultant()
        assert "Decision Readiness" in system_prompt()

    @pytest.mark.parametrize("scoped", [False, True])
    def test_no_narrow_render_instructs_an_absent_build_tool(self, scoped):
        """The gap this feature is really about: gating the toolset does NOT
        gate the prompt. Each phrase names a build tool the head does not have,
        in a section that renders regardless of the toolset."""
        for render in (self._view(scoped), self._consultant(scoped)):
            assert "After explore" not in render
            assert "anchor or ingest" not in render
            assert "announce additions and removals" not in render
            assert "`anchor` plants it" not in render
            assert "offer to `anchor`" not in render

    def test_the_consultant_may_still_discard_and_the_view_may_not(self):
        assert "silently `discard`" in self._consultant()
        assert "`discard`" not in self._view()
        assert "You cannot retract it" in self._view()

    def test_the_scoped_consultant_keeps_the_consent_rule(self):
        """Retractions are consented inside an exploration whichever surface
        is pinned to it — the consultant variant keeps the confirm-then-discard
        shape and drops only the `anchor` offer."""
        render = self._consultant(scoped=True)
        assert "retractions are consented, not silent" in render
        assert "`anchor`" not in render

    @pytest.mark.parametrize("scoped", [False, True])
    def test_the_cache_seam_survives(self, scoped):
        """One breakpoint sentinel and the context slot LAST — the invariant
        `split_system_for_cache` rests on, asserted here because a new section
        appended after `_CONTEXT_SLOT` would break caching silently."""
        for render in (self._view(scoped), self._consultant(scoped)):
            assert render.count("\n\n## Current Understanding\n\n") == 1
            assert render.rstrip().endswith("{dialectical_context}")


class TestTheClosingSeamOnEachSurface:
    """The framework's own initiative, which is the half no toolset can gate.

    `_repair_unrecorded_decision` writes a Decision the model never recorded and
    schedules the weave that builds perspectives, cycles and wheels off the turn.
    On VIEW it does not run at all. On CONSULTANT it records, grounds on what
    exists, and does not weave.
    """

    def _confirming_classifier(self, monkeypatch, calls: list) -> None:
        async def fake_check(self, *, user_message, assistant_message):
            calls.append(user_message)
            return ConfirmationVerdictDto(
                confirmed=True,
                question="Buy out the cofounder or restructure?",
                stance="Buy him out",
                rationale="He is checked out.",
            )

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)

    def _recording(self, monkeypatch) -> dict:
        recorded: dict = {}

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "abc1234deadbeef"

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)
        return recorded

    async def test_view_never_asks_the_classifier(self, monkeypatch):
        """Not "nothing was written" — nothing was CONCLUDED. A seam that ran
        and then failed to write looks the same from outside and is a different
        fact (and would cost a provider call on a surface whose contract is that
        it does nothing)."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)

        advisor = _StubAdvisor([], principal="human", mode=AdvisorMode.VIEW)
        advisor._last_closing = "stale"
        advisor._last_deferral = "stale"
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert calls == []
        # `None` is documented on `ClosingOutcome` as "the seam did not run"; a
        # VIEW turn must not read as NO_CLOSING — nobody asked.
        assert advisor._last_closing is None
        assert advisor._last_deferral is None

    async def test_full_repairs_and_starts_the_weave(self, monkeypatch):
        """The control. Without it the two narrow tests pass on a stub that
        never reaches the classifier for some unrelated reason."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)
        recorded = self._recording(monkeypatch)

        advisor = _StubAdvisor([], principal="human", mode=AdvisorMode.FULL)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert len(calls) == 1
        assert recorded["stance"] == "Buy him out"
        assert advisor._last_closing is ClosingOutcome.REPAIRED
        assert advisor._last_deferral is not DeferralOutcome.NOT_BUILDING

    async def test_consultant_repairs_and_withholds_the_weave(self, monkeypatch):
        """The one the surface exists for: the person's "write that down" is
        honoured, and the graph they brought here as finished stays finished."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)
        recorded = self._recording(monkeypatch)
        scheduled: list = []

        # The real scheduler is bound on the stub; wrap it to see what reaches
        # the queue. The gate must return BEFORE the queue is touched — a FULL
        # instance resuming this sid later must not find the consultant's
        # decisions waiting and weave on their behalf.
        real = _StubAdvisor._schedule_pathway_construction

        def spy(self, decision_hash):
            scheduled.append(decision_hash)
            return real(self, decision_hash)

        monkeypatch.setattr(_StubAdvisor, "_schedule_pathway_construction", spy)

        advisor = _StubAdvisor([], principal="human", mode=AdvisorMode.CONSULTANT)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert len(calls) == 1, "the consultant's seam must ask, unlike VIEW's"
        assert recorded["stance"] == "Buy him out"
        assert recorded["principal"] == "human"
        assert advisor._last_closing is ClosingOutcome.REPAIRED
        assert scheduled == ["abc1234deadbeef"], "the seam reached the scheduler"
        assert advisor._last_deferral is DeferralOutcome.NOT_BUILDING
        assert advisor._deferred_pathway_task is None, "no weave was started"

    async def test_consultant_grounds_a_model_recorded_decision_on_what_exists(
        self, monkeypatch
    ):
        """The seam's OTHER branch: the model called `record_decision` itself.
        The consultant still reads the existing pathways to ground it — that is
        a read, and the record is better for it — and still starts nothing."""
        reads: list = []

        async def fake_ensure(self):
            reads.append(True)
            return []

        # Patched on the STUB, not on `Advisor`: the stub binds the real methods
        # as class attributes at class-creation time, so a patch on `Advisor`
        # would leave the bound copy in place and the test would pass vacuously.
        monkeypatch.setattr(
            _StubAdvisor, "_ensure_pathways_before_closing", fake_ensure
        )

        from dialectical_framework.agents.execution_report import \
            ExecutionReport
        from dialectical_framework.agents.stream_events import ToolResult

        advisor = _StubAdvisor(
            [
                ToolResult(
                    tool_name="record_decision",
                    report=ExecutionReport(tool="record_decision", ok=True),
                    raw_output="{}",
                )
            ],
            mode=AdvisorMode.CONSULTANT,
        )
        await advisor._repair_unrecorded_decision("done", "recorded")

        assert reads == [True]
        assert advisor._last_closing is ClosingOutcome.MODEL_RECORDED
        assert advisor._last_deferral is DeferralOutcome.NOT_BUILDING
        assert advisor._deferred_pathway_task is None

    async def test_view_does_not_ground_a_model_recorded_decision_either(
        self, monkeypatch
    ):
        """Gating only the repair branch would leave the framework writing on a
        VIEW head whenever a host wired a write tool of its own."""
        reads: list = []

        async def fake_ensure(self):
            reads.append(True)
            return []

        monkeypatch.setattr(
            _StubAdvisor, "_ensure_pathways_before_closing", fake_ensure
        )

        from dialectical_framework.agents.execution_report import \
            ExecutionReport
        from dialectical_framework.agents.stream_events import ToolResult

        advisor = _StubAdvisor(
            [
                ToolResult(
                    tool_name="record_decision",
                    report=ExecutionReport(tool="record_decision", ok=True),
                    raw_output="{}",
                )
            ],
            mode=AdvisorMode.VIEW,
        )
        await advisor._repair_unrecorded_decision("done", "recorded")

        assert reads == []
        assert advisor._last_closing is None


class TestTheGateHasThreeSites:
    """`self._mode` is read in exactly three methods, and that is the design.

    `_settle_deferred_work` must still run on every surface (one writer per sid
    — a reading head on a half-woven graph is worse than one on a shallow graph)
    and `_refresh_context` must still run (it is a read; a turn that must see the
    graph cannot be configured into not looking). A future "not building means
    do nothing" edit would take both, and nothing else in the suite would
    notice.
    """

    def test_only_the_constructor_and_the_two_seam_sites_read_the_mode(self):
        readers = {
            name
            for name, fn in vars(Advisor).items()
            if inspect.isfunction(fn) and "self._mode" in inspect.getsource(fn)
        }
        assert readers == {
            "__init__",
            "_repair_unrecorded_decision",
            "_schedule_pathway_construction",
        }, (
            "a new read of `self._mode` — if it is a turn-loop gate, "
            "`_settle_deferred_work` and `_refresh_context` are exactly what "
            "must NOT be behind it; see this class's docstring"
        )

    def test_the_enum_says_what_each_surface_may_do(self):
        assert AdvisorMode.FULL.builds and AdvisorMode.FULL.records
        assert not AdvisorMode.CONSULTANT.builds and AdvisorMode.CONSULTANT.records
        assert not AdvisorMode.VIEW.builds and not AdvisorMode.VIEW.records
