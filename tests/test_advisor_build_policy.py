"""
`Advisor(build=..., records=...)` — when the head builds, whether it writes,
and what holds the surfaces together.

    build=ON_ELECTION   builds on the turn (the model elects) and off it.  the Advisor as shipped
    build=ON_CONSENT    builds off the turn only, on the person's word.     `note`, and a confirmed decision
    build=NEVER         never builds.                                       a graph something else finished
    records=False       reads, nothing else.                                a seat that is not doing the work

The contract is enforced in two places and nowhere else: the TOOLSET (what the
head is never handed it cannot reach) and the closing seam — which DECLINES
without `records` (`_repair_unrecorded_decision` returns before the classifier
is asked) and under NEVER records the decision, grounds it on what exists, and
WITHHOLDS the weave (`_schedule_pathway_construction` returns `NOT_BUILDING`
before touching the queue). Under ON_CONSENT the seam starts the weave a
confirmed decision is entitled to, and the `note` tool queues what the person
asked to keep for the same off-turn task. The prompt is told which surface it is
on so the head does not spend turns reaching for what it does not have — but the
prompt is not what stops it, which is the same division of labour as the nexus
pin.

Three things in here are worth knowing before editing them.

`_BUILD_TOOL_NAMES` / `_CONSENT_TOOL_NAMES` / `_WRITE_TOOL_NAMES` (the prompt's
name sets) and the toolset factories are lists that must agree, and nothing but
`TestTheListsAreOne` holds them together: a tool added to one and not the other
gives a head that holds a build tool while being told it has none, or a full
Advisor whose own prompt renders as a sealed head's.

The seam tests assert what was CONCLUDED, not merely what was written — a repair
that ran and then failed to write looks identical from the outside, and it is not
the same fact.

And `_settle_deferred_work` / `_refresh_context` deliberately still run on every
surface: settling honours one-writer-per-sid (a reading head on a half-woven
graph is worse than one on a shallow graph) and the refresh is a read.
`TestTheGatesHaveTheirSites` is what keeps a well-meaning "not building means do
nothing" edit from taking them.
"""

from __future__ import annotations

import inspect

import pytest

from dialectical_framework.agents.advisor.advisor import (_DEFERRED_WORK,
                                                          Advisor,
                                                          _build_tools)
from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.advisor.system_prompts import (
    DEFAULT_TOOL_NAMES, _BUILD_TOOL_NAMES, _CONSENT_TOOL_NAMES,
    _REJECTION_HANDLING_CONSENT, _REJECTION_HANDLING_CONSENT_SCOPED,
    _REJECTION_HANDLING_SEALED, _REJECTION_HANDLING_SEALED_SCOPED,
    _WRITE_TOOL_NAMES, system_prompt)
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
NOTING = {"note"}

MANDATE = "## What Is Not Available Here"
CONSENT_MANDATE = "builds only on the person's word"
SEALED_MANDATE = "This surface consults; it does not build."
VIEW_MANDATE = "This surface reads."


async def _sink(thesis, antithesis, context) -> str:
    return "kept"


def _names(tools: list) -> set[str]:
    return {t.__name__ for t in tools}


def _tool_by_name(tools: list, name: str):
    return next(t for t in tools if t.__name__ == name)


def _new_nexus() -> Nexus:
    """A committed nexus in a fresh scope, for the pinned factory."""
    nexus = Nexus(intent="advisor build policy test")
    nexus.save()
    nexus.commit()
    return nexus


class TestTheToolsetsAreTheSurfaces:
    """What the head is handed, which is the whole enforcement."""

    async def test_a_seat_without_records_holds_the_three_reading_tools(self):
        assert _names(Advisor(build=BuildPolicy.NEVER, records=False)._tools) == READING

    async def test_never_holds_reading_plus_deciding_and_no_build_tool(self):
        names = _names(Advisor(build=BuildPolicy.NEVER)._tools)
        assert names == READING | DECIDING
        assert not names & (BUILDING | NOTING)

    async def test_on_consent_adds_exactly_the_note(self):
        names = _names(Advisor(build=BuildPolicy.ON_CONSENT)._tools)
        assert names == READING | DECIDING | NOTING
        assert not names & BUILDING

    async def test_on_election_holds_everything_and_no_note(self):
        """`note` is `anchor` deferred; a head that holds `anchor` has no use
        for it, and two names for one act is a turn spent choosing."""
        assert _names(Advisor()._tools) == READING | DECIDING | BUILDING

    async def test_the_policy_accepts_its_string_value(self):
        """A host reading the policy from config passes a string; the
        constructor normalises it."""
        assert _names(Advisor(build="never")._tools) == READING | DECIDING
        assert Advisor(build="on_consent")._build is BuildPolicy.ON_CONSENT

    async def test_consent_without_records_raises(self):
        """Not silently NEVER: both consent triggers are writes, so the
        combination has no way to ever build, and a host that wrote it meant
        something else."""
        with pytest.raises(ValueError, match="records=True"):
            Advisor(build=BuildPolicy.ON_CONSENT, records=False)

    async def test_election_without_records_builds_and_keeps_no_ledger(self):
        """Coherent, and allowed: what the model elects is built, nothing is
        recorded, and the closing seam does not run (`records` gates it)."""
        assert _names(Advisor(records=False)._tools) == READING | BUILDING

    async def test_the_factory_alone_says_the_same(self):
        """Called directly, so a future `__init__` branch cannot be the only
        thing keeping a surface narrow."""
        assert _names(_build_tools(build=BuildPolicy.NEVER, records=False)) == READING
        assert _names(_build_tools(build=BuildPolicy.NEVER)) == READING | DECIDING
        assert _names(_build_tools(build=BuildPolicy.ON_CONSENT, note_sink=_sink)) == (
            READING | DECIDING | NOTING
        )
        assert _names(_build_tools()) == READING | DECIDING | BUILDING

    async def test_the_note_needs_a_queue_to_be_built(self):
        """The tool closes over the Advisor's queue; a bare factory call has
        none, and a `note` that queues nowhere would tell the model "kept"
        about something nothing will ever plant."""
        assert _names(_build_tools(build=BuildPolicy.ON_CONSENT)) == READING | DECIDING

    @pytest.mark.parametrize(
        "build, records, expected",
        [
            (BuildPolicy.NEVER, False, READING),
            (BuildPolicy.NEVER, True, READING | DECIDING),
            (BuildPolicy.ON_CONSENT, True, READING | DECIDING | NOTING),
            (BuildPolicy.ON_ELECTION, True, READING | DECIDING | (BUILDING - {"ingest"})),
            # Pinned, the build tools are writes into someone's deliverable,
            # so the permission gates them too (unlike the unscoped factory).
            (BuildPolicy.ON_ELECTION, False, READING),
        ],
    )
    async def test_the_scoped_head_keeps_the_pin_on_every_surface(
        self, build, records, expected
    ):
        """The pinned `sync`, not the unscoped one, on every surface.

        The discriminator is the SIGNATURE, not the name: both are called
        `sync`, and only the unscoped one exposes `nexus_hash` for the model to
        redirect. Asserting on the name would pass with the pin gone. (`ingest`
        is never wired when pinned — bulk extraction belongs to the unscoped
        flow.)
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            tools = build_scoped_tools(
                _new_nexus().hash[:7], build=build, records=records, note_sink=_sink
            )

        assert _names(tools) == expected
        sync = _tool_by_name(tools, "sync")
        assert list(inspect.signature(sync).parameters) == [], (
            "the scoped head got the UNSCOPED sync — it can be pointed at any "
            "exploration in the case"
        )

    async def test_app_tools_are_still_merged_on_the_narrow_surfaces(self):
        """Deliberate, and documented at the parameter: the framework cannot
        tell a host's chart lookup from a host's write, so the policy governs
        the framework's own surface and the host owns its own."""
        from mirascope import llm

        @llm.tool
        async def lookup_natal_chart(person: str) -> str:
            """Look up the natal chart for a person."""
            return f"chart for {person}"

        seat = Advisor(build=BuildPolicy.NEVER, records=False, app_tools=[lookup_natal_chart])
        assert _names(seat._tools) == READING | {"lookup_natal_chart"}
        never = Advisor(build=BuildPolicy.NEVER, app_tools=[lookup_natal_chart])
        assert _names(never._tools) == READING | DECIDING | {"lookup_natal_chart"}


class TestTheListsAreOne:
    """The toolset factory and the prompt's name sets are halves of one list.

    `system_prompt` derives the render from `_BUILD_TOOL_NAMES`,
    `_CONSENT_TOOL_NAMES` and `_WRITE_TOOL_NAMES` while the factory decides
    what is actually handed over, and nothing else compares them. Drift in
    either direction is silent and bad in a different way: a build tool missing
    from the set gives a head holding it and a prompt saying it has none; a
    read tool wrongly in a set makes the full Advisor's own prompt render as a
    narrower surface's.
    """

    def test_the_default_toolset_splits_exactly_into_reads_and_writes(self):
        """The consent tool is the one write the shipped head does not hold."""
        assert set(DEFAULT_TOOL_NAMES) == READING | (_WRITE_TOOL_NAMES - _CONSENT_TOOL_NAMES)

    def test_build_and_consent_are_disjoint_strict_subsets_of_write(self):
        assert _BUILD_TOOL_NAMES < _WRITE_TOOL_NAMES
        assert _CONSENT_TOOL_NAMES < _WRITE_TOOL_NAMES
        assert not _BUILD_TOOL_NAMES & _CONSENT_TOOL_NAMES
        assert _BUILD_TOOL_NAMES == BUILDING
        assert _CONSENT_TOOL_NAMES == NOTING

    def test_the_reading_seat_gets_exactly_what_is_not_a_write(self):
        assert set(DEFAULT_TOOL_NAMES) - _names(
            _build_tools(build=BuildPolicy.NEVER, records=False)
        ) == (_WRITE_TOOL_NAMES - _CONSENT_TOOL_NAMES)

    def test_never_gets_exactly_what_is_not_a_build(self):
        assert set(DEFAULT_TOOL_NAMES) - _names(_build_tools(build=BuildPolicy.NEVER)) == (
            _BUILD_TOOL_NAMES
        )

    def test_consent_gets_what_never_gets_plus_the_consent_names(self):
        never = _names(_build_tools(build=BuildPolicy.NEVER))
        consent = _names(_build_tools(build=BuildPolicy.ON_CONSENT, note_sink=_sink))
        assert consent - never == _CONSENT_TOOL_NAMES

    def test_audit_feasibility_is_a_write_and_not_a_build(self):
        """It reads like a read and is not: a FeasibilityEstimation plus a
        critique Rationale, two provider calls per pathway. But it adds no
        structure, so the never-building head keeps it. Pinned by name because
        it is the one member a reader would move."""
        assert "audit_feasibility" in _WRITE_TOOL_NAMES
        assert "audit_feasibility" not in _BUILD_TOOL_NAMES
        assert "audit_feasibility" not in _names(_build_tools(build=BuildPolicy.NEVER, records=False))
        assert "audit_feasibility" in _names(_build_tools(build=BuildPolicy.NEVER))

    def test_discard_is_a_write_and_not_a_build(self):
        """A write with the softest possible name — a soft-marked node is out of
        every active query afterwards — and the consulting head's way of
        honouring a rejection."""
        assert "discard" in _WRITE_TOOL_NAMES
        assert "discard" not in _BUILD_TOOL_NAMES
        assert "discard" not in _names(_build_tools(build=BuildPolicy.NEVER, records=False))
        assert "discard" in _names(_build_tools(build=BuildPolicy.NEVER))


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

    def _consent(self, scoped: bool = False) -> str:
        return system_prompt(
            tool_names=sorted(READING | DECIDING | NOTING),
            scoped_nexus_hash="abc1234" if scoped else None,
        )

    def test_each_narrow_surface_renders_its_own_mandate(self):
        view, sealed, consent = self._view(), self._consultant(), self._consent()
        assert MANDATE in view and VIEW_MANDATE in view
        assert MANDATE in sealed and SEALED_MANDATE in sealed
        assert MANDATE in consent and CONSENT_MANDATE in consent
        assert SEALED_MANDATE not in view and CONSENT_MANDATE not in view
        assert VIEW_MANDATE not in sealed and CONSENT_MANDATE not in sealed
        assert VIEW_MANDATE not in consent and SEALED_MANDATE not in consent

    def test_the_full_render_has_no_mandate(self):
        assert MANDATE not in system_prompt()

    def test_one_build_name_turns_the_narrow_renders_off(self):
        """Derived from the names rather than passed as a flag: a scoped session
        wiring a single build tool is a building surface — even beside `note`."""
        assert MANDATE not in system_prompt(tool_names=sorted(READING | DECIDING | {"anchor"}))
        assert MANDATE not in system_prompt(
            tool_names=sorted(READING | DECIDING | NOTING | {"anchor"})
        )

    def test_one_write_name_turns_the_view_render_into_the_consultant_one(self):
        render = system_prompt(tool_names=sorted(READING | {"discard"}))
        assert SEALED_MANDATE in render
        assert VIEW_MANDATE not in render

    def test_the_note_name_turns_the_consultant_render_into_the_consent_one(self):
        render = system_prompt(tool_names=sorted(READING | {"note"}))
        assert CONSENT_MANDATE in render
        assert SEALED_MANDATE not in render and VIEW_MANDATE not in render

    def test_the_consent_render_documents_the_note_and_the_others_do_not(self):
        assert "- `note`" in self._consent()
        assert "- `note`" not in self._consultant()
        assert "- `note`" not in self._view()
        assert "- `note`" not in system_prompt()

    def test_the_consent_render_says_the_closing_builds_after_the_reply(self):
        """Decision Readiness' record-on-what-exists note: under NEVER the
        pathway never comes; under consent it comes after the reply, and the
        prompt must not tell the model otherwise."""
        assert "built after this reply" in self._consent()
        assert "built after this reply" not in self._consultant()
        assert "record on what exists." in self._consultant()

    def test_the_consultant_mandate_still_says_nothing_is_built_afterwards(self):
        """The sentence the consent shape exists to replace stays true where
        it renders."""
        assert "nothing is\nbuilt after the conversation either" in self._consultant()
        assert "built after the conversation either" not in self._consent()

    def test_the_consent_rejection_sections_are_derived_and_the_replacement_took(self):
        assert _REJECTION_HANDLING_CONSENT != _REJECTION_HANDLING_SEALED
        assert "`note` it" in _REJECTION_HANDLING_CONSENT
        assert "you cannot add it to the understanding" not in _REJECTION_HANDLING_CONSENT
        assert _REJECTION_HANDLING_CONSENT_SCOPED != _REJECTION_HANDLING_SEALED_SCOPED
        assert "`note` it" in _REJECTION_HANDLING_CONSENT_SCOPED
        assert "`note` it" in self._consent()
        assert "`note` it" in self._consent(scoped=True)
        assert "`note`" not in self._consultant(scoped=True)

    def test_the_scoped_consent_render_says_where_a_note_lands(self):
        render = self._consent(scoped=True)
        assert "joins this exploration only\non the person's word" in render
        # `explore` still appears mid-paragraph in Reading Your Understanding,
        # on every narrow shape, by design — the mandate covers it (see the
        # comment above `mandate` in `system_prompt`). `anchor` must not.
        assert "`anchor`" not in render
        assert "The exploration grows elsewhere" not in render
        assert "The exploration grows elsewhere" in self._consultant(scoped=True)

    def test_an_unknown_app_tool_name_does_not_widen_any_surface(self):
        """App tools are never in any set — a host's own lookup must not
        turn the framework's narrow render off."""
        assert VIEW_MANDATE in system_prompt(tool_names=sorted(READING | {"lookup_natal_chart"}))
        assert SEALED_MANDATE in system_prompt(
            tool_names=sorted(READING | DECIDING | {"lookup_natal_chart"})
        )
        assert CONSENT_MANDATE in system_prompt(
            tool_names=sorted(READING | DECIDING | NOTING | {"lookup_natal_chart"})
        )

    def test_the_building_arc_is_dropped_on_all_three(self):
        """Same reason it is dropped when scoped: the arc IS the building
        sequence, and there is nothing here to build with on the turn."""
        for render in (self._view(), self._consultant(), self._consent()):
            assert "## Default Arc" not in render
        assert "## Default Arc" in system_prompt()

    def test_the_convergence_engine_renders_where_decisions_are_wired(self):
        assert "Decision Readiness" not in self._view()
        assert "Decision Readiness" in self._consultant()
        assert "Decision Readiness" in self._consent()
        assert "Decision Readiness" in system_prompt()

    @pytest.mark.parametrize("scoped", [False, True])
    def test_no_narrow_render_instructs_an_absent_build_tool(self, scoped):
        """The gap this feature is really about: gating the toolset does NOT
        gate the prompt. Each phrase names a build tool the head does not have,
        in a section that renders regardless of the toolset."""
        for render in (self._view(scoped), self._consultant(scoped), self._consent(scoped)):
            assert "After explore" not in render
            assert "anchor or ingest" not in render
            assert "announce additions and removals" not in render
            assert "`anchor` plants it" not in render
            assert "offer to `anchor`" not in render

    def test_the_consulting_surfaces_may_still_discard_and_the_view_may_not(self):
        assert "silently `discard`" in self._consultant()
        assert "silently `discard`" in self._consent()
        assert "`discard`" not in self._view()
        assert "You cannot retract it" in self._view()

    def test_the_scoped_consultant_keeps_the_consent_rule(self):
        """Retractions are consented inside an exploration whichever surface
        is pinned to it — both consulting variants keep the confirm-then-discard
        shape and drop only the `anchor` offer."""
        for render in (self._consultant(scoped=True), self._consent(scoped=True)):
            assert "retractions are consented, not silent" in render
            assert "`anchor`" not in render

    @pytest.mark.parametrize("scoped", [False, True])
    def test_the_cache_seam_survives(self, scoped):
        """One breakpoint sentinel and the context slot LAST — the invariant
        `split_system_for_cache` rests on, asserted here because a new section
        appended after `_CONTEXT_SLOT` would break caching silently."""
        for render in (self._view(scoped), self._consultant(scoped), self._consent(scoped)):
            assert render.count("\n\n## Current Understanding\n\n") == 1
            assert render.rstrip().endswith("{dialectical_context}")


class TestTheClosingSeamOnEachSurface:
    """The framework's own initiative, which is the half no toolset can gate.

    `_repair_unrecorded_decision` writes a Decision the model never recorded and
    schedules the weave that builds perspectives, cycles and wheels off the turn.
    Without `records` it does not run at all. Under NEVER it records, grounds on
    what exists, and does not weave. Under ON_CONSENT it records and weaves —
    the confirmed decision is the person's word.
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

    def _capture_drain(self, monkeypatch) -> list:
        """Replace the real drain with one that records it ran, so a started
        task neither touches a DB this file does not have nor outlives its
        test."""
        drained: list = []

        async def fake_drain(self):
            drained.append(True)

        monkeypatch.setattr(_StubAdvisor, "_run_deferred_pathway_construction", fake_drain)
        return drained

    async def test_a_seat_without_records_never_asks_the_classifier(self, monkeypatch):
        """Not "nothing was written" — nothing was CONCLUDED. A seam that ran
        and then failed to write looks the same from outside and is a different
        fact (and would cost a provider call on a surface whose contract is that
        it does nothing)."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)

        advisor = _StubAdvisor([], principal="human", build=BuildPolicy.NEVER, records=False)
        advisor._last_closing = "stale"
        advisor._last_deferral = "stale"
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert calls == []
        # `None` is documented on `ClosingOutcome` as "the seam did not run"; a
        # turn without the permission must not read as NO_CLOSING — nobody asked.
        assert advisor._last_closing is None
        assert advisor._last_deferral is None

    async def test_election_repairs_and_starts_the_weave(self, monkeypatch):
        """The control. Without it the narrow tests pass on a stub that never
        reaches the classifier for some unrelated reason."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)
        recorded = self._recording(monkeypatch)
        drained = self._capture_drain(monkeypatch)

        advisor = _StubAdvisor([], principal="human", build=BuildPolicy.ON_ELECTION)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )
        await advisor.wait_for_deferred_work()

        assert len(calls) == 1
        assert recorded["stance"] == "Buy him out"
        assert advisor._last_closing is ClosingOutcome.REPAIRED
        assert advisor._last_deferral is DeferralOutcome.STARTED
        assert drained == [True]

    async def test_never_repairs_and_withholds_the_weave(self, monkeypatch):
        """The person's "write that down" is honoured, and the graph they
        brought here as finished stays finished."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)
        recorded = self._recording(monkeypatch)
        scheduled: list = []

        # The real scheduler is bound on the stub; wrap it to see what reaches
        # the queue. The gate must return BEFORE the queue is touched — a
        # building instance resuming this sid later must not find this head's
        # decisions waiting and weave on their behalf.
        real = _StubAdvisor._schedule_pathway_construction

        def spy(self, decision_hash):
            scheduled.append(decision_hash)
            return real(self, decision_hash)

        monkeypatch.setattr(_StubAdvisor, "_schedule_pathway_construction", spy)

        advisor = _StubAdvisor([], principal="human", build=BuildPolicy.NEVER)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert len(calls) == 1, "the never-building seam must ask, unlike the reading seat's"
        assert recorded["stance"] == "Buy him out"
        assert recorded["principal"] == "human"
        assert advisor._last_closing is ClosingOutcome.REPAIRED
        assert scheduled == ["abc1234deadbeef"], "the seam reached the scheduler"
        assert advisor._last_deferral is DeferralOutcome.NOT_BUILDING
        assert advisor._deferred_pathway_task is None, "no weave was started"
        assert advisor._decisions_awaiting_pathway == [], "the queue was never touched"

    async def test_on_consent_repairs_and_starts_the_weave(self, monkeypatch):
        """The confirmed decision IS the person's word: under consent the seam
        does what election's does — records on the turn, weaves off it."""
        calls: list = []
        self._confirming_classifier(monkeypatch, calls)
        recorded = self._recording(monkeypatch)
        drained = self._capture_drain(monkeypatch)

        advisor = _StubAdvisor([], principal="human", build=BuildPolicy.ON_CONSENT)
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )
        assert advisor._last_deferral is DeferralOutcome.STARTED
        await advisor.wait_for_deferred_work()

        assert len(calls) == 1
        assert recorded["stance"] == "Buy him out"
        assert advisor._last_closing is ClosingOutcome.REPAIRED
        assert drained == [True]

    async def test_never_grounds_a_model_recorded_decision_on_what_exists(
        self, monkeypatch
    ):
        """The seam's OTHER branch: the model called `record_decision` itself.
        The never-building head still reads the existing pathways to ground it
        — that is a read, and the record is better for it — and still starts
        nothing."""
        reads: list = []

        async def fake_ensure(self):
            reads.append(True)
            return []

        # Patched on the STUB, not on `Advisor`: the stub binds the real methods
        # as class attributes at class-creation time, so a patch on `Advisor`
        # would leave the bound copy in place and the test would pass vacuously.
        monkeypatch.setattr(_StubAdvisor, "_ensure_pathways_before_closing", fake_ensure)

        from dialectical_framework.agents.execution_report import ExecutionReport
        from dialectical_framework.agents.stream_events import ToolResult

        advisor = _StubAdvisor(
            [
                ToolResult(
                    tool_name="record_decision",
                    report=ExecutionReport(tool="record_decision", ok=True),
                    raw_output="{}",
                )
            ],
            build=BuildPolicy.NEVER,
        )
        await advisor._repair_unrecorded_decision("done", "recorded")

        assert reads == [True]
        assert advisor._last_closing is ClosingOutcome.MODEL_RECORDED
        assert advisor._last_deferral is DeferralOutcome.NOT_BUILDING
        assert advisor._deferred_pathway_task is None

    async def test_a_seat_without_records_does_not_ground_a_model_recorded_decision_either(
        self, monkeypatch
    ):
        """Gating only the repair branch would leave the framework writing on a
        reading seat whenever a host wired a write tool of its own."""
        reads: list = []

        async def fake_ensure(self):
            reads.append(True)
            return []

        monkeypatch.setattr(_StubAdvisor, "_ensure_pathways_before_closing", fake_ensure)

        from dialectical_framework.agents.execution_report import ExecutionReport
        from dialectical_framework.agents.stream_events import ToolResult

        advisor = _StubAdvisor(
            [
                ToolResult(
                    tool_name="record_decision",
                    report=ExecutionReport(tool="record_decision", ok=True),
                    raw_output="{}",
                )
            ],
            build=BuildPolicy.NEVER,
            records=False,
        )
        await advisor._repair_unrecorded_decision("done", "recorded")

        assert reads == []
        assert advisor._last_closing is None


class TestTheNoteQueuesAndTheTaskPlantsIt:
    """`note` (`tools/note.py`): the consent surface's own way in.

    On the turn it queues and says so; after the reply the off-turn task plants
    each note with `anchor`'s body and weaves what it planted, the same task and
    the same single flight a closing uses. DB-free: the repositories, the anchor
    body and the weave are patched, so what is pinned is WHEN the anchor fires,
    WHAT it is asked to plant, and that the weave follows.
    """

    @staticmethod
    def _pp(h: str):
        class _PP:
            def __init__(self) -> None:
                self.hash = h
                self.in_cycle = False

        return _PP()

    def _graph(self, monkeypatch, perspectives: list) -> list:
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        monkeypatch.setattr(
            PerspectiveRepository, "find_all_active", lambda self: list(perspectives)
        )
        monkeypatch.setattr(
            PerspectiveRepository, "is_in_use_by_cycle", lambda self, pp: pp.in_cycle
        )
        return perspectives

    def _anchor(self, monkeypatch, perspectives: list, *, fail_on: str | None = None) -> list[dict]:
        import dialectical_framework.agents.advisor.tools.anchor as anchor_mod

        calls: list[dict] = []

        async def fake_anchor(*, thesis, antithesis, context, utterance=None):
            if thesis == fail_on:
                raise RuntimeError("provider down")
            calls.append({"thesis": thesis, "antithesis": antithesis, "context": context})
            h = f"pp{len(calls):04d}"
            perspectives.append(self._pp(h))
            return '{"artifacts": {"perspective_hashes": ["%s"]}}' % h

        monkeypatch.setattr(anchor_mod, "_anchor", fake_anchor)
        return calls

    def _weave(self, monkeypatch, perspectives: list) -> list[dict]:
        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        woven: list[dict] = []

        async def fake_run(*, perspective_hashes, intent, nexus_hash):
            woven.append({"hashes": list(perspective_hashes), "nexus": nexus_hash})
            for pp in perspectives:
                pp.in_cycle = True
            return "{}", ["tr0001"]

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", fake_run)
        return woven

    def _no_nexus(self, monkeypatch, hashes: list[str] = ()) -> None:
        from types import SimpleNamespace

        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        monkeypatch.setattr(
            NexusRepository,
            "find_all",
            lambda self: [SimpleNamespace(hash=h) for h in hashes],
        )

    async def test_the_tool_queues_and_plants_nothing_on_the_turn(self, monkeypatch):
        anchors = self._anchor(monkeypatch, [])
        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)

        reply = await advisor._queue_note("Keep the Berlin office", None, "12 people there")

        assert reply.startswith("Kept.")
        assert "written down" in reply
        assert advisor._notes_awaiting_anchor == [("Keep the Berlin office", None, "12 people there", None)]
        assert anchors == [], "nothing is planted while the person waits"
        assert advisor._deferred_pathway_task is None, "the tool starts no task"
        advisor._notes_awaiting_anchor.clear()

    async def test_an_empty_note_keeps_nothing(self, monkeypatch):
        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        reply = await advisor._queue_note("   ", None, "")
        assert reply.startswith("Nothing kept")
        assert advisor._notes_awaiting_anchor == []

    async def test_the_note_tool_is_the_queue(self):
        """The wired tool's body IS `_queue_note`: calling it through the tool
        lands on the same per-sid list the task drains."""
        advisor = Advisor(build=BuildPolicy.ON_CONSENT)
        note = _tool_by_name(advisor._tools, "note")
        reply = await note(thesis="Keep the Berlin office", context="12 people there")
        assert reply.startswith("Kept.")
        assert advisor._notes_awaiting_anchor == [("Keep the Berlin office", None, "12 people there", None)]
        advisor._notes_awaiting_anchor.clear()

    async def test_a_noted_turn_without_a_closing_starts_the_task_that_plants_it(
        self, monkeypatch
    ):
        """In an exploration (here: the case holds exactly one), a note is
        planted and woven INTO it."""
        perspectives = self._graph(monkeypatch, [])
        anchors = self._anchor(monkeypatch, perspectives)
        woven = self._weave(monkeypatch, perspectives)
        self._no_nexus(monkeypatch, ["nx0001"])
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: grounded.append(h)
        )

        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Keep the Berlin office", "Close it", "12 people there")
        advisor._last_deferral = None  # what a NO_CLOSING seam leaves behind
        advisor._schedule_noted_tensions()
        assert advisor._last_deferral is DeferralOutcome.STARTED
        await advisor.wait_for_deferred_work()

        assert anchors == [
            {"thesis": "Keep the Berlin office", "antithesis": "Close it", "context": "12 people there"}
        ]
        assert woven == [{"hashes": ["pp0001"], "nexus": "nx0001"}], (
            "the weave ran over what the note planted, into the one exploration"
        )
        assert grounded == [], "a note is not a decision; nothing was grounded"
        # Registry first: reading the queue through its property CREATES an
        # entry, so the order of these two assertions is load-bearing.
        assert advisor._deferred_work_key() not in _DEFERRED_WORK, "the entry was retired"
        assert advisor._notes_awaiting_anchor == []

    @pytest.mark.parametrize("hashes", [[], ["nx0001", "nx0002"]])
    async def test_a_note_outside_any_exploration_is_kept_as_a_tension_only(
        self, monkeypatch, hashes
    ):
        """Not in an exploration — none, or several with no pin — the note is
        the ANALYSIS part alone: planted, read from the next turn on, never
        woven. A note is "keep this", not "build me a map"; the exploration is
        born at a closing."""
        perspectives = self._graph(monkeypatch, [])
        anchors = self._anchor(monkeypatch, perspectives)
        woven = self._weave(monkeypatch, perspectives)
        self._no_nexus(monkeypatch, hashes)

        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Keep the Berlin office", None, "12 people there")
        advisor._last_deferral = None
        advisor._schedule_noted_tensions()
        await advisor.wait_for_deferred_work()

        assert [a["thesis"] for a in anchors] == ["Keep the Berlin office"]
        assert woven == [], "nothing to join and no closing: no weave"

    async def test_a_pinned_note_is_woven_into_the_pin(self, monkeypatch):
        perspectives = self._graph(monkeypatch, [])
        self._anchor(monkeypatch, perspectives)
        woven = self._weave(monkeypatch, perspectives)
        self._no_nexus(monkeypatch, ["nx0001", "nx0002"])

        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT, nexus_hash="pinned1")
        await advisor._queue_note("Keep the Berlin office", None, "")
        advisor._last_deferral = None
        advisor._schedule_noted_tensions()
        await advisor.wait_for_deferred_work()

        assert woven == [{"hashes": ["pp0001"], "nexus": "pinned1"}]

    async def test_nothing_noted_schedules_nothing(self, monkeypatch):
        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        advisor._last_deferral = None
        advisor._schedule_noted_tensions()
        assert advisor._last_deferral is None
        assert advisor._deferred_pathway_task is None

    async def test_a_closing_that_started_the_task_is_not_started_twice(self, monkeypatch):
        """The closing's task drains both queues; the note rides along."""
        started: list = []

        def spy(self, decision_hash):
            started.append(decision_hash)

        monkeypatch.setattr(_StubAdvisor, "_schedule_pathway_construction", spy)
        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Keep the Berlin office", None, "")
        for outcome in (DeferralOutcome.STARTED, DeferralOutcome.JOINED):
            advisor._last_deferral = outcome
            advisor._schedule_noted_tensions()
        assert started == []
        advisor._last_deferral = DeferralOutcome.NOTHING_TO_DEFER
        advisor._schedule_noted_tensions()
        assert started == [None], "a closing that deferred nothing does not carry the note"
        advisor._notes_awaiting_anchor.clear()

    async def test_a_note_and_a_closing_in_one_round_ground_the_decision_on_the_woven_pathway(
        self, monkeypatch
    ):
        """Notes are planted FIRST, so the weave in the same round covers them
        and a decision closed on the noted tension rests on its pathway."""
        perspectives = self._graph(monkeypatch, [self._pp("h0000")])
        anchors = self._anchor(monkeypatch, perspectives)
        woven = self._weave(monkeypatch, perspectives)
        self._no_nexus(monkeypatch)
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append((h, list(p))),
        )
        monkeypatch.setattr(_StubAdvisor, "_audit_adopted_pathways", _noop_audit)

        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Keep the Berlin office", None, "")
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert [a["thesis"] for a in anchors] == ["Keep the Berlin office"]
        assert woven == [{"hashes": ["h0000", "pp0001"], "nexus": None}]
        assert grounded == [("dec00001", ["tr0001"])]

    async def test_a_closing_outside_any_exploration_still_weaves_and_the_note_rides_along(
        self, monkeypatch
    ):
        """The closing is what creates the exploration on this surface; a note
        queued in the same round is woven with it."""
        perspectives = self._graph(monkeypatch, [self._pp("h0000")])
        self._anchor(monkeypatch, perspectives)
        woven = self._weave(monkeypatch, perspectives)
        self._no_nexus(monkeypatch)
        monkeypatch.setattr(_StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None)
        monkeypatch.setattr(_StubAdvisor, "_audit_adopted_pathways", _noop_audit)

        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Keep the Berlin office", None, "")
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert woven == [{"hashes": ["h0000", "pp0001"], "nexus": None}]

    async def test_a_failing_note_does_not_cost_the_others(self, monkeypatch):
        perspectives = self._graph(monkeypatch, [])
        anchors = self._anchor(monkeypatch, perspectives, fail_on="Close it now")
        woven = self._weave(monkeypatch, perspectives)
        self._no_nexus(monkeypatch, ["nx0001"])

        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Close it now", None, "")
        await advisor._queue_note("Keep the Berlin office", None, "")
        advisor._last_deferral = None
        advisor._schedule_noted_tensions()
        await advisor.wait_for_deferred_work()

        assert [a["thesis"] for a in anchors] == ["Keep the Berlin office"]
        assert woven == [{"hashes": ["pp0001"], "nexus": "nx0001"}]

    async def test_the_registry_entry_stays_while_a_note_is_queued(self):
        """`idle` must see the notes: an entry with a queued note and no task is
        not empty, and sweeping it would lose what the person asked to keep."""
        advisor = _StubAdvisor([], build=BuildPolicy.ON_CONSENT)
        await advisor._queue_note("Keep the Berlin office", None, "")
        entry = _DEFERRED_WORK[advisor._deferred_work_key()]
        assert not entry.idle
        entry.notes.clear()
        assert entry.idle


async def _noop_audit(self, hashes):
    return None


class TestWhereTheWeaveLands:
    """`_weave_target_nexus`: which exploration the off-turn weave joins.

    The pin where there is one. Unpinned, the election policy keeps the
    measured behaviour (a new exploration). Under consent a note is "add this
    to what you know", so a case with exactly ONE exploration is expanded
    rather than forked; several or none fall back to creating one.
    """

    def _nexuses(self, monkeypatch, hashes: list[str]) -> None:
        from types import SimpleNamespace

        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        monkeypatch.setattr(
            NexusRepository, "find_all", lambda self: [SimpleNamespace(hash=h) for h in hashes]
        )

    def test_the_pin_wins_on_every_policy(self, monkeypatch):
        self._nexuses(monkeypatch, ["nx0001"])
        for build in BuildPolicy:
            advisor = _StubAdvisor([], build=build, nexus_hash="pinned1")
            assert advisor._weave_target_nexus() == "pinned1"

    def test_consent_joins_the_one_exploration(self, monkeypatch):
        self._nexuses(monkeypatch, ["nx0001"])
        assert _StubAdvisor([], build=BuildPolicy.ON_CONSENT)._weave_target_nexus() == "nx0001"

    @pytest.mark.parametrize("hashes", [[], ["nx0001", "nx0002"]])
    def test_consent_has_no_target_when_there_is_none_or_several(self, monkeypatch, hashes):
        """None: a closing creates, notes alone are kept as tensions."""
        self._nexuses(monkeypatch, hashes)
        assert _StubAdvisor([], build=BuildPolicy.ON_CONSENT)._weave_target_nexus() is None

    def test_election_keeps_the_measured_behaviour(self, monkeypatch):
        """Every benched A2 cell wove unpinned into a NEW exploration; changing
        that is a bench round, not a side effect of this policy."""
        self._nexuses(monkeypatch, ["nx0001"])
        assert _StubAdvisor([], build=BuildPolicy.ON_ELECTION)._weave_target_nexus() is None

    def test_a_failing_lookup_falls_back_to_creating(self, monkeypatch):
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        def boom(self):
            raise RuntimeError("db down")

        monkeypatch.setattr(NexusRepository, "find_all", boom)
        assert _StubAdvisor([], build=BuildPolicy.ON_CONSENT)._weave_target_nexus() is None

    def test_the_weave_reads_the_target_once_per_drain(self):
        """Read before the round loop, not inside it: a case whose exploration
        count changes mid-drain must not have its rounds land in two places."""
        src = inspect.getsource(Advisor._weave_unwoven_perspectives)
        assert "target_nexus = self._weave_target_nexus()" in src
        assert "nexus_hash=target_nexus" in src
        assert "nexus_hash=self._nexus_hash" not in src


class TestTheGatesHaveTheirSites:
    """`self._build` and `self._records` are read in exactly these methods, and
    that is the design.

    `_settle_deferred_work` must still run on every surface (one writer per sid
    — a reading head on a half-woven graph is worse than one on a shallow graph)
    and `_refresh_context` must still run (it is a read; a turn that must see the
    graph cannot be configured into not looking). A future "not building means
    do nothing" edit would take both, and nothing else in the suite would
    notice.
    """

    @staticmethod
    def _readers(needle: str) -> set[str]:
        """Whole-word: `self._build` must not match `self._build_system_prompt`."""
        import re

        pattern = re.compile(re.escape(needle) + r"\b")
        return {
            name
            for name, fn in vars(Advisor).items()
            if inspect.isfunction(fn) and pattern.search(inspect.getsource(fn))
        }

    def test_the_policy_is_read_at_the_constructor_and_the_two_off_turn_sites(self):
        assert self._readers("self._build") == {
            "__init__",
            "_schedule_pathway_construction",
            "_weave_target_nexus",
        }, (
            "a new read of `self._build` — if it is a turn-loop gate, "
            "`_settle_deferred_work` and `_refresh_context` are exactly what "
            "must NOT be behind it; see this class's docstring"
        )

    def test_the_permission_is_read_at_the_constructor_and_the_seam(self):
        assert self._readers("self._records") == {
            "__init__",
            "_repair_unrecorded_decision",
        }

    def test_both_turn_loops_schedule_the_notes_after_the_seam(self):
        """The seam's NO_CLOSING exit schedules nothing, so the note's task is
        started by the loop, on both entry points, right after the seam."""
        for loop in (Advisor.chat, Advisor.chat_stream):
            src = inspect.getsource(loop)
            assert src.index("_repair_unrecorded_decision(") < src.index(
                "self._schedule_noted_tensions()"
            )

    def test_the_enum_says_when_each_policy_builds(self):
        assert BuildPolicy.ON_ELECTION.on_turn and BuildPolicy.ON_ELECTION.off_turn
        assert not BuildPolicy.ON_CONSENT.on_turn and BuildPolicy.ON_CONSENT.off_turn
        assert not BuildPolicy.NEVER.on_turn and not BuildPolicy.NEVER.off_turn
