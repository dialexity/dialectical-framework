"""
The decision record is a user-driven artefact, so it cannot be elective.

Measured before this seam existed (`tests/e2e/README.md`, "the ceremony is
tier-gated"): with identical prompt, tools and scenario, `record_decision` fired
**6/6 at the strong tier and 0/6 at the weak tier**. The weak tier failed the
same way every run — asked to "write that down as the decision", it produced a
formatted "Your Decision" section in prose with `tool_calls == []`. The person
was told the decision was recorded; it was not, and the next session opened on an
empty ledger, so the wobble re-audit had nothing to reassure from.

Three rounds of prompt strengthening (`_DECISION_READINESS` prose, the
`record_decision` tool doc, the `explore` call threshold) moved that 0/6 not at
all — which is the point: the confirmation is an observable event in the person's
own message, so whether a record gets written must not depend on the model
electing to call a tool at its least reliable moment.

These tests are DB-free and LLM-free: they pin the SEAM (when the repair fires,
when it must not, and what it records), not the classifier's judgement.
"""

from __future__ import annotations

import asyncio
import logging

from types import SimpleNamespace

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.stream_events import ToolResult
from dialectical_framework.concerns.decision_confirmation_check import (
    ConfirmationVerdictDto, DecisionConfirmationCheck)
from dialectical_framework.concerns.record_decision import UNATTESTED_PRINCIPAL


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """DB-free: override the autouse graph fixture."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _StubAdvisor:
    """The repair path in isolation.

    `Advisor.__init__` validates a nexus and renders a system prompt, both of
    which want a DB and a live DI container. The repair method itself only
    touches `_conversation.last_tool_results` and `_principal`, so binding it to
    a stub keeps these tests at the seam instead of at the constructor.
    """

    def __init__(
        self,
        tool_results=None,
        # Mirrors the real class: no attestation unless a host makes one. A
        # stub defaulting to "human" would let a repair that hardcoded the
        # sentinel pass every test in here.
        principal: str = UNATTESTED_PRINCIPAL,
        nexus_hash: str | None = None,
        automatic_feasibility_audit: bool = True,
    ) -> None:
        self._principal = principal
        self._nexus_hash = nexus_hash
        # Settings reach the real class through DI (`SettingsAware`), which wants
        # a live container these DB-free tests do not build. A per-instance
        # stand-in keeps the audit MODE switchable per test — and it defaults to
        # automatic on purpose, DELIBERATELY unlike the production default (manual
        # since 2026-09-15): default it the other way and every audit assertion in
        # this file would pass by never running the audit. Do not "fix" this to
        # match `Settings`; the one test that owns the production default asserts
        # it against `Settings.model_fields` instead of through this stub.
        self.settings = SimpleNamespace(
            automatic_feasibility_audit=automatic_feasibility_audit
        )
        # Per-instance, matching the real `__init__`: a class-level list would
        # leak one test's pending decisions into the next.
        self._deferred_pathway_task = None
        self._decisions_awaiting_pathway: list[str] = []
        # Mirrors the real `__init__`. The seam resets both on entry, so a stub
        # without them would still work — declared anyway, because a test that
        # asserts `is None` before the seam runs is asserting the constructor's
        # promise and not an AttributeError.
        self._last_closing = None
        self._last_deferral = None

        class _Conv:
            last_tool_results = list(tool_results or [])

        self._conversation = _Conv()

    _MAX_WEAVE_ROUNDS = Advisor._MAX_WEAVE_ROUNDS
    _repair_unrecorded_decision = Advisor._repair_unrecorded_decision
    _recorded_decision_this_turn = Advisor._recorded_decision_this_turn
    _ensure_pathways_before_closing = Advisor._ensure_pathways_before_closing
    _existing_pathway_hashes = Advisor._existing_pathway_hashes
    _adopted_pathway_grounds = Advisor._adopted_pathway_grounds
    _attach_adopted_pathway = Advisor._attach_adopted_pathway
    _connect_adopted_pathway = Advisor._connect_adopted_pathway
    _ground_recorded_decision = Advisor._ground_recorded_decision
    _decision_recorded_this_turn = Advisor._decision_recorded_this_turn
    _accepted_cost_ground = Advisor.__dict__["_accepted_cost_ground"]
    # The deferral. Bound like everything else so the seam tests exercise the
    # real scheduling decision rather than a stand-in — but note that a bound
    # `_schedule_pathway_construction` starts a REAL asyncio task, so a test
    # that lets it fire must await `wait_for_deferred_work`
    # (`TestDeferredPathwayConstruction`) or neutralise it
    # (`_SeamFixtures._capture_scheduling`, which every weaving test gets).
    _schedule_pathway_construction = Advisor._schedule_pathway_construction
    _run_deferred_pathway_construction = Advisor._run_deferred_pathway_construction
    _weave_unwoven_perspectives = Advisor._weave_unwoven_perspectives
    # The tail of the drain. Bound for a reason worth stating: an UNbound method
    # here fails inside the task, after the grounding, where
    # `wait_for_deferred_work` catches it and logs — so every assertion in
    # `TestDeferredPathwayConstruction` would still pass while the audit half of
    # the drain silently never ran.
    _audit_adopted_pathways = Advisor._audit_adopted_pathways
    _adopted_pathway_hash = Advisor._adopted_pathway_hash
    wait_for_deferred_work = Advisor.wait_for_deferred_work


def _ok_report() -> ExecutionReport:
    return ExecutionReport(tool="record_decision", ok=True)


def _failed_report() -> ExecutionReport:
    return ExecutionReport(
        tool="record_decision", ok=False, summary="Cannot record: stance is empty"
    )


def _tool_result(name: str, report: ExecutionReport | None) -> ToolResult:
    return ToolResult(tool_name=name, report=report, raw_output="{}")


class TestRecordedThisTurnDetection:
    """What counts as "the model already did it"."""

    def test_successful_record_call_suppresses_the_repair(self):
        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        assert advisor._recorded_decision_this_turn() is True

    def test_a_failed_record_call_still_needs_repair(self):
        """An in-band refusal leaves the person believing in a record that does
        not exist — the same defect as prose-only closure, by another route."""
        advisor = _StubAdvisor([_tool_result("record_decision", _failed_report())])
        assert advisor._recorded_decision_this_turn() is False

    def test_other_tools_do_not_suppress_the_repair(self):
        advisor = _StubAdvisor(
            [
                _tool_result("anchor", _ok_report()),
                _tool_result("explore", _ok_report()),
            ]
        )
        assert advisor._recorded_decision_this_turn() is False

    def test_no_tool_calls_at_all_does_not_suppress(self):
        """The exact weak-tier shape: a beautiful prose decision, zero calls."""
        assert _StubAdvisor([])._recorded_decision_this_turn() is False

    def test_reportless_record_result_counts_as_recorded(self):
        """An unparseable report is not evidence of failure — re-recording on
        it would risk a duplicate Decision, which is worse than a missing
        richer grounding."""
        advisor = _StubAdvisor([_tool_result("record_decision", None)])
        assert advisor._recorded_decision_this_turn() is True


class TestRepairFires:
    """When the person confirmed and nothing was written."""

    @pytest.mark.asyncio
    async def test_confirmed_decision_gets_recorded(self, monkeypatch):
        recorded = {}

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True,
                question="Buy out the cofounder or restructure?",
                stance="Buy him out",
                rationale="He is checked out; accepting that the accounts may follow him.",
            )

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "abc1234deadbeef"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        advisor = _StubAdvisor([], principal="human")
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert recorded["stance"] == "Buy him out"
        assert recorded["question"] == "Buy out the cofounder or restructure?"
        # Same attestation the tool would have carried — read off the instance,
        # never assumed, which is why the stub's own default is unattested.
        assert recorded["principal"] == "human"

    @pytest.mark.asyncio
    async def test_the_repair_records_under_a_delegated_principal(self, monkeypatch):
        """A delegated driver must not have its confirmations logged as human's."""
        recorded = {}

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="s", rationale="r"
            )

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "hash"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        advisor = _StubAdvisor([], principal="agent:bench-driver")
        await advisor._repair_unrecorded_decision("log it", "done")

        assert recorded["principal"] == "agent:bench-driver"

    @pytest.mark.asyncio
    async def test_unmatched_stance_grounds_nothing(self, monkeypatch):
        """A fabricated accepted_cost invents the very confrontation the ledger
        reports, and would send the re-audit to the wrong risk. No match, no
        ground — the record is still worth having."""
        recorded = {}

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="s", rationale="r"
            )

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "hash"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        await _StubAdvisor([])._repair_unrecorded_decision("log it", "done")

        assert recorded.get("grounds") in (None, [])

    @pytest.mark.asyncio
    async def test_no_pathway_exists_so_none_is_grounded(self, monkeypatch):
        """A pathway is grounded only when the seam actually has one.

        This test was `test_adopted_pathway_is_never_guessed` and asserted the
        stronger rule that the repair never adds the role at all, "because it
        needs a transformation the wheel may not have". The seam now BUILDS the
        wheel before recording, so it often does have one, and withholding it was
        r16's 0/6 defect. What survives from the old rule is the part that was
        actually about honesty: with no pathway in hand, the record is written
        without one rather than pointed at a guess. The grounded case is
        `TestTheClosingGroundsOnThePathwayItBuilt`.
        """
        recorded = {}

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True,
                question="q",
                stance="s",
                rationale="r",
                chosen_polarity_hash="pol123",
                chosen_side="T",
            )

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "hash"

        def fake_ground(verdict):
            from dialectical_framework.concerns.record_decision import GroundLink

            return [GroundLink(hash="cost456", role="accepted_cost")]

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        # Explicitly: the weave found nothing. Left to the DB this would raise
        # and be swallowed, so the test would pass without exercising the branch.
        async def no_pathways(self):
            return []

        monkeypatch.setattr(
            _StubAdvisor, "_ensure_pathways_before_closing", no_pathways
        )

        advisor = _StubAdvisor([])
        # Instance attribute: the resolution itself needs a graph, and what is
        # under test here is what the repair does NOT add alongside it.
        advisor._accepted_cost_ground = fake_ground
        await advisor._repair_unrecorded_decision("log it", "done")

        roles = [g.role for g in (recorded.get("grounds") or [])]
        assert "accepted_cost" in roles
        assert "adopted_pathway" not in roles


class TestCostFollowsFromTheChosenSide:
    """The cost is DERIVED from the side, never asked for separately.

    The owning definition: T is what is said, T+ its implied goal, T- its risk;
    A is the opponent's say, A+ the obligation of the T-sayer, A- a subsequent
    risk. So the price of choosing a side is that side's own MINUS — a plus is a
    goal or obligation, i.e. something to DO, which is a remedy and not a price.
    """

    def test_choosing_the_thesis_costs_t_minus(self):
        verdict = ConfirmationVerdictDto(
            confirmed=True, question="q", stance="s",
            chosen_polarity_hash="abc", chosen_side="T",
        )
        assert verdict.chosen_cost_position == "t_minus"

    def test_choosing_the_antithesis_costs_a_minus(self):
        verdict = ConfirmationVerdictDto(
            confirmed=True, question="q", stance="s",
            chosen_polarity_hash="abc", chosen_side="A",
        )
        assert verdict.chosen_cost_position == "a_minus"

    def test_a_plus_is_never_a_cost(self):
        """A plus is a goal or an obligation — grounding a cost on one yields a
        remedy (something to DO), not a price. The mapping simply cannot
        produce a plus, so no prompt wording can drift into one."""
        for side in ("T", "A"):
            verdict = ConfirmationVerdictDto(
                confirmed=True, question="q", stance="s",
                chosen_polarity_hash="abc", chosen_side=side,
            )
            assert verdict.chosen_cost_position.endswith("_minus")

    def test_side_is_case_and_whitespace_tolerant(self):
        verdict = ConfirmationVerdictDto(
            confirmed=True, question="q", stance="s",
            chosen_polarity_hash="abc", chosen_side=" t ",
        )
        assert verdict.chosen_cost_position == "t_minus"

    def test_no_polarity_match_means_no_cost_position(self):
        verdict = ConfirmationVerdictDto(
            confirmed=True, question="q", stance="s", chosen_side="T"
        )
        assert verdict.chosen_cost_position == ""

    def test_unrecognised_side_means_no_cost_position(self):
        """"between the poles" must not silently become one of them."""
        verdict = ConfirmationVerdictDto(
            confirmed=True, question="q", stance="s",
            chosen_polarity_hash="abc", chosen_side="both",
        )
        assert verdict.chosen_cost_position == ""

    def test_ground_resolution_returns_none_without_a_match(self):
        """No DB access at all when there is nothing to look up."""
        verdict = ConfirmationVerdictDto(confirmed=True, question="q", stance="s")
        assert Advisor._accepted_cost_ground(verdict) is None


class TestRepairStaysQuiet:
    """Every path that must NOT create a Decision."""

    @pytest.mark.asyncio
    async def test_model_already_recorded_skips_the_check_entirely(self, monkeypatch):
        """Cheapest guard: no second LLM call on the common (correct) path."""
        called = {"check": False}

        async def fake_check(self, **kwargs):
            called["check"] = True
            return None

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert called["check"] is False

    @pytest.mark.asyncio
    async def test_unconfirmed_turn_records_nothing(self, monkeypatch):
        async def fake_check(self, **kwargs):
            return ConfirmationVerdictDto(confirmed=False)

        recorded = {"called": False}

        async def fake_record(self, **kwargs):
            recorded["called"] = True
            return "hash"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        await _StubAdvisor([])._repair_unrecorded_decision(
            "I'm leaning toward buying him out, but I want to sit with it.",
            "That leaning is well-founded...",
        )

        assert recorded["called"] is False

    @pytest.mark.asyncio
    async def test_confirmed_but_empty_stance_records_nothing(self, monkeypatch):
        """RecordDecision would refuse in-band; keep that out of the repair
        path, where it would read as a framework error, not a non-event."""
        async def fake_check(self, **kwargs):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="   ", rationale="r"
            )

        recorded = {"called": False}

        async def fake_record(self, **kwargs):
            recorded["called"] = True
            return "hash"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        await _StubAdvisor([])._repair_unrecorded_decision("go ahead", "ok")

        assert recorded["called"] is False

    @pytest.mark.asyncio
    async def test_check_failure_is_fail_soft(self, monkeypatch):
        """None = "no repair", never a block on a turn already delivered."""
        async def fake_check(self, **kwargs):
            return None

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

    @pytest.mark.asyncio
    async def test_an_exception_never_reaches_the_person(self, monkeypatch):
        """The reply was already returned — the repair may not turn a delivered
        turn into an error."""
        async def boom(self, **kwargs):
            raise RuntimeError("bedrock throttled")

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", boom)
        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")


class TestVerdictDto:
    def test_mocked_brain_default_reads_as_nothing_to_repair(self):
        """The mock brain fills bools with False. A mocked suite must never
        fabricate Decision nodes in tests that did not ask for one.

        `confirmed` therefore carries `default=False` — the safe direction, as
        with `DecisionCoherenceCheck.incoherent`.
        """
        assert ConfirmationVerdictDto().confirmed is False
        assert ConfirmationVerdictDto().is_recordable is False

    def test_is_recordable_requires_question_and_stance(self):
        assert not ConfirmationVerdictDto(
            confirmed=True, question="q", stance=""
        ).is_recordable
        assert not ConfirmationVerdictDto(
            confirmed=True, question="", stance="s"
        ).is_recordable
        assert ConfirmationVerdictDto(
            confirmed=True, question="q", stance="s"
        ).is_recordable


class TestTurnWiring:
    """The repair is wired into BOTH turn paths, or hosts that stream lose it."""

    def test_chat_calls_the_repair(self):
        import inspect

        src = inspect.getsource(Advisor.chat)
        assert "_repair_unrecorded_decision" in src

    def test_chat_stream_calls_the_repair(self):
        import inspect

        src = inspect.getsource(Advisor.chat_stream)
        assert "_repair_unrecorded_decision" in src
        # From ResponseComplete, because that is the DURABLE reply: deltas
        # yielded before a ToolStart are the model narrating what it is about
        # to do, and repairing against those would read a preamble as counsel.
        assert "ResponseComplete" in src


class _SeamFixtures:
    """Setup shared by the two closing-seam classes.

    Deliberately not `Test*`-prefixed: pytest collects by name, so a fixture
    class the grounding tests inherit must not be one, or every weaving test
    would run twice.
    """

    @staticmethod
    def _perspectives(count: int, woven: int = 0):
        """`count` committed perspectives, the first `woven` already in a cycle."""

        class _PP:
            def __init__(self, h: str, in_cycle: bool) -> None:
                self.hash = h
                self.in_cycle = in_cycle

        return [_PP(f"h{i:04d}", i < woven) for i in range(count)]

    def _patch_repo(self, monkeypatch, perspectives):
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        monkeypatch.setattr(
            PerspectiveRepository, "find_all_active", lambda self: perspectives
        )
        monkeypatch.setattr(
            PerspectiveRepository,
            "is_in_use_by_cycle",
            lambda self, pp: pp.in_cycle,
        )

    def _capture_exploration(self, monkeypatch):
        """A tripwire on the weave call, which must never fire on a turn.

        This helper used to supply what the weave "built", because the closing
        constructed its own pathways. It no longer does, so the returned list is
        now an assertion target rather than a plumbing detail: every test in this
        file expects it EMPTY. The reason is measured, not stylistic —
        `run_exploration_detailed` cost 127.7s and 387.7s on two turns of
        `timing-check-building`, on the person's wait, on the two turns
        immediately before the closing. See
        `Advisor._ensure_pathways_before_closing`.
        """
        calls = []

        async def fake_run(*, perspective_hashes, intent, nexus_hash):
            calls.append(
                {
                    "hashes": list(perspective_hashes),
                    "intent": intent,
                    "nexus_hash": nexus_hash,
                }
            )
            return "{}", []

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", fake_run)
        # No pathways on the graph unless a test says so: the lookup runs a real
        # query otherwise, and these are DB-free tests.
        monkeypatch.setattr(
            _StubAdvisor, "_existing_pathway_hashes", lambda self: []
        )
        # The other half of the same tripwire: a closing may REQUEST an off-turn
        # weave and must not perform one here either. Left on `self` rather than
        # returned so the existing call sites keep their signature.
        self._scheduled = self._capture_scheduling(monkeypatch)
        return calls

    def _capture_scheduling(self, monkeypatch) -> list:
        """Record the OFF-turn weave requests instead of starting them.

        Two reasons, and the first is correctness rather than tidiness: the real
        `_schedule_pathway_construction` starts an asyncio task, and a task that
        outlives its test would run its weave after monkeypatch has restored the
        real `run_exploration_detailed` — i.e. against a DB this file does not
        have. Second, it makes "the closing asked for a weave" assertable
        separately from "the weave happened", which is the whole boundary this
        change draws.

        `TestDeferredPathwayConstruction` deliberately does NOT use this: it
        tests the scheduler itself and awaits what it starts.
        """
        scheduled: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_schedule_pathway_construction",
            lambda self, decision_hash: scheduled.append(decision_hash),
        )
        return scheduled

    def _graph_pathways(self, monkeypatch, hashes: list[str]):
        """Pathways ALREADY on the graph — the only source a closing now has.

        Call after `_capture_exploration`, which defaults the same lookup to
        empty. Whether these came from the model's own `explore` or from an
        earlier turn is exactly the distinction the closing cannot make and does
        not need to: it grounds on what is there.
        """
        monkeypatch.setattr(
            _StubAdvisor, "_existing_pathway_hashes", lambda self: list(hashes)
        )


class TestPathwaysBeforeClosing(_SeamFixtures):
    """A closing READS the pathways it grounds on. It must not build them.

    This class used to assert the opposite, and the reason it did still stands:
    the engine prompt requires pathways at a closing — "A decision closes on
    pathways, not on tensions alone... Without pathways there is no paired
    recipe to adopt, no trap version of the choice to name, and the counsel at
    the closing turn is a single tension restated with more emphasis" — and the
    model does not obey it, in exactly the tier-shaped way `record_decision` did
    not: `explore` fires in 6/55 weak-tier runs (11%) against 17/25 strong
    (68%), and in all 6 cells of `claim2-weak-r7-readside` it fired ZERO times
    while `anchor` built 5-7 tensions each. A direct probe
    (`tests/e2e/probe_explore_reachability.py`) confirmed the weak tier CAN call
    `explore` unprompted, so that is election, not capability.

    WHAT CHANGED, AND WHY IT IS NOT A RETREAT
    =========================================
    Building here was on the person's wait. `Advisor.chat` awaits the repair
    before returning the reply, so the weave was billed to the turn no matter
    what the comments said. Measured with per-turn timing on a real provider
    (`timing-check-building`, weak tier): two turns making ZERO tool calls cost
    141.9s and 402.0s, of which 127.7s and 387.7s were this weave — both on the
    turn immediately before the closing.

    So the pathways still matter and the weave still has to happen; it happens
    OFF the turn. What this class now guards is the boundary: the closing reads,
    grounds on what it finds, records, and never blocks. The quality cost of
    reading an unwoven graph is real and recorded in
    `test_a_lone_unwoven_tension_is_not_woven_either` — it is a debt this leaves
    visible, not a defect it denies.
    """

    @pytest.mark.asyncio
    async def test_unwoven_tensions_are_not_woven_on_the_turn(self, monkeypatch):
        """The r7 shape — five anchored tensions, no explore — must not trigger a weave.

        This is the exact input that used to produce the 387.7s turn.
        """
        self._patch_repo(monkeypatch, self._perspectives(5))
        calls = self._capture_exploration(monkeypatch)

        pathways = await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == [], (
            "the closing wove on the person's wait — the 387.7s turn is back"
        )
        assert pathways == []

    @pytest.mark.asyncio
    async def test_the_unwoven_gap_is_logged_not_swallowed(self, monkeypatch, caplog):
        """The debt has to be visible, or this is just a silent capability loss.

        Deliberately a log and not a queue: a queue nothing drains is this
        archive's signature defect (a value computed and never read). The count
        is in the message because "some perspectives" cannot be acted on.
        """
        self._patch_repo(monkeypatch, self._perspectives(5, woven=2))
        self._capture_exploration(monkeypatch)

        with caplog.at_level(logging.WARNING):
            await _StubAdvisor([])._ensure_pathways_before_closing()

        assert any(
            "3 unwoven perspective(s)" in r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        ), "an unwoven closing left no trace at warning level"

    @pytest.mark.asyncio
    async def test_a_woven_graph_logs_nothing(self, monkeypatch, caplog):
        """No debt, no warning — otherwise the log stops meaning anything."""
        self._patch_repo(monkeypatch, self._perspectives(4, woven=4))
        self._capture_exploration(monkeypatch)

        with caplog.at_level(logging.WARNING):
            await _StubAdvisor([])._ensure_pathways_before_closing()

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    @pytest.mark.asyncio
    async def test_already_woven_tensions_are_not_rewoven(self, monkeypatch):
        """Idempotence: a model that DID explore must not pay for it twice."""
        self._patch_repo(monkeypatch, self._perspectives(4, woven=4))
        calls = self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == []

    @pytest.mark.asyncio
    async def test_a_partly_woven_graph_grounds_on_what_is_woven(self, monkeypatch):
        """Two unwoven of five is still a read, and the read still returns."""
        self._patch_repo(monkeypatch, self._perspectives(5, woven=3))
        calls = self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, ["tr0042"])

        pathways = await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == []
        assert pathways == ["tr0042"]

    @pytest.mark.asyncio
    async def test_a_lone_unwoven_tension_is_not_woven_either(self, monkeypatch):
        """The recorded cost of moving construction off the turn.

        A single opposition IS a complete arrangement — `PerspectiveCombination`
        treats one PP as the circular-causality base case (W(1)=1),
        `docs/theory/generative-rules.md` Rule 8 has layer-1 wheels covering the
        within-tetrad diagonals, and it was measured on a real provider at the
        weak tier (`tests/test_single_perspective_explore_real_llm.py`): 1 cycle,
        1 DEEPENED wheel, 6 transformations, 6 named Ac+/Re+ pathways, 1
        synthesis, from one perspective. So weaving it is worth doing.

        It is worth doing OFF the turn. When the weave lived here,
        `claim2-weak-r15-voice` measured what skipping it costs — 3 of 6 cells
        called `anchor` once, closed on `woven=0 transformations=0`, and the
        judged mean over them was -0.69 against -0.25 for the woven cells, the
        single largest identified component of A2's remaining loss.

        This test therefore pins a DEBT, not a win: until deferred construction
        exists, a lone-tension closing grounds on nothing and that -0.69 is the
        exposure. If this assertion is ever inverted back, check that the weave
        moved off the reply path rather than back onto it.
        """
        self._patch_repo(monkeypatch, self._perspectives(1))
        calls = self._capture_exploration(monkeypatch)

        pathways = await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == []
        assert pathways == []

    @pytest.mark.asyncio
    async def test_a_lone_already_woven_tension_is_not_rewoven(self, monkeypatch):
        """Dropping the floor must not cost the idempotence the floor hid.

        With `< 2` gone, a one-perspective graph reaches the weave call for the
        first time — so the "already in a cycle" filter is now the only thing
        standing between a re-closing and a duplicate exploration.
        """
        self._patch_repo(monkeypatch, self._perspectives(1, woven=1))
        calls = self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == []

    @pytest.mark.asyncio
    async def test_an_empty_graph_builds_nothing(self, monkeypatch):
        self._patch_repo(monkeypatch, [])
        calls = self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == []

    @pytest.mark.asyncio
    async def test_the_scoped_nexus_pin_governs_the_read(self, monkeypatch):
        """Counsel mode reads ITS nexus, not every nexus in scope.

        The pin used to matter because the weave could fork a second nexus. With
        no weave, it still matters for the same underlying reason — a counsel
        session must not ground its decision on a pathway from an exploration the
        person is not in.
        """
        seen: list = []

        class _Nexus:
            hash = "nex1234"

        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository
        from dialectical_framework.graph.repositories.transformation_repository import \
            TransformationRepository

        def _prefix(self, h):
            seen.append(h)
            return _Nexus()

        monkeypatch.setattr(NexusRepository, "find_by_hash_prefix", _prefix)
        monkeypatch.setattr(
            NexusRepository,
            "find_all",
            lambda self: pytest.fail("a pinned counsel session read every nexus"),
        )

        class _Tr:
            hash = "tr0005"

        monkeypatch.setattr(
            TransformationRepository, "find_by_nexus", lambda self, n: [_Tr()]
        )
        self._patch_repo(monkeypatch, self._perspectives(3, woven=3))

        advisor = _StubAdvisor([], nexus_hash="nex1234")
        assert await advisor._ensure_pathways_before_closing() == ["tr0005"]
        assert seen == ["nex1234"]

    @pytest.mark.asyncio
    async def test_the_record_is_written_without_waiting_to_build(self, monkeypatch):
        """Order was the whole point, and the order is now: read, ground, record.

        There is no weave to sequence against. What still has to hold is that the
        grounds reach `RecordDecision` at commit time rather than being attached
        afterwards on this branch — the repair branch writes the record itself,
        so it can pass them in.
        """
        order = []

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="s", rationale="r"
            )

        async def fake_record(self, **kwargs):
            order.append(("record", [g.role for g in (kwargs["grounds"] or [])]))
            return "hash"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)

        self._patch_repo(monkeypatch, self._perspectives(3, woven=3))
        calls = self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, ["tr0001"])

        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

        assert calls == []
        assert order == [("record", ["adopted_pathway"])]

    @pytest.mark.asyncio
    async def test_a_model_recorded_decision_still_reads_pathways(self, monkeypatch):
        """The branch the first version of this seam missed, still covered.

        Gating pathways on the REPAIR firing skips every turn where the model
        recorded the decision itself — and that is the larger population:
        `record_decision` ran without `explore` in **50** saved A2 cells against
        48 with both. Recording is stronger evidence of closing than any
        classifier verdict, so this branch must still look for a pathway and
        ground the record on one (`TestTheClosingGroundsOnThePathwayItBuilt`).
        What it must not do is BUILD one while the person waits.
        """
        self._patch_repo(monkeypatch, self._perspectives(4))
        calls = self._capture_exploration(monkeypatch)
        looked = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_existing_pathway_hashes",
            lambda self: looked.append(True) or [],
        )

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        # No confirmation check is patched: reaching one would mean the repair
        # ran, and a recorded decision must never be re-recorded.
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert calls == []
        assert looked, "the recorded branch stopped looking for a pathway at all"

    @pytest.mark.asyncio
    async def test_a_recorded_decision_is_never_recorded_twice(self, monkeypatch):
        """Weaving on the recorded branch must not reopen the repair path."""
        self._patch_repo(monkeypatch, self._perspectives(4))
        self._capture_exploration(monkeypatch)

        async def explode(self, **kwargs):
            raise AssertionError("re-recorded an already-recorded decision")

        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", explode)

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

    @pytest.mark.asyncio
    async def test_no_pathways_are_built_when_nothing_was_confirmed(
        self, monkeypatch
    ):
        """This is not a background weaver — it fires only on a real closing.

        Weaving on every turn would burn latency and tokens on arrangements the
        conversation may never reach, and would make `explore`'s per-call
        perspective cap meaningless.
        """

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(confirmed=False, question="", stance="")

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        self._patch_repo(monkeypatch, self._perspectives(5))
        calls = self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._repair_unrecorded_decision("still thinking", "sure")

        assert calls == []

    @pytest.mark.asyncio
    async def test_a_failed_exploration_never_breaks_the_turn(self, monkeypatch):
        """The person's reply is already delivered; a pathway they never asked
        about must not surface as an error, and the record must still be written."""
        recorded = {}

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="s", rationale="r"
            )

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "hash"

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)
        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)
        self._patch_repo(monkeypatch, self._perspectives(3))

        async def boom(*, perspective_hashes, intent, nexus_hash):
            raise RuntimeError("memgraph went away")

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", boom)

        # Must not raise, and must still write the record — losing it here would
        # reintroduce exactly the defect the repair exists to prevent.
        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

        assert recorded["stance"] == "s"


class TestTheClosingGroundsOnThePathwayItBuilt(_SeamFixtures):
    """Building the pathway is not the deliverable — grounding the record on it is.

    `claim2-weak-r16-floor` is the measurement that made this a defect rather
    than a nicety. The floor fix landed and worked structurally: 6/6 A2 cells
    wove, 12-42 transformations each. And `adopted_pathway_grounds` was **0/6**
    — including the cell that called `explore` itself at t2 and
    `record_decision` at t5 with 30 pathways on the graph. So the framework
    built the artefact that distinguishes it from a prompted model and then
    recorded a decision that does not point at it: the returning session's
    re-audit has no recipe to reassure from, and `accepted_cost_condition` has
    no pathway to render.

    Three co-located causes, all in code and none in the model: `run_exploration`
    discarded the `transformation_hashes` that `ExplorationResult` publishes
    for exactly this caller; the recorded-decision branch deliberately did
    nothing with the pathways it built, on the false premise that a committed
    Decision cannot take a new ground (GROUNDED_IN is ANALYTICAL — it can);
    and `if not unwoven: return` skipped the one cell that most deserved a
    ground. This class covers all three.
    """

    @staticmethod
    def _confirming(monkeypatch):
        """Make the confirmation check say "the person closed"."""

        async def fake_check(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="s", rationale="r"
            )

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", fake_check)

    @staticmethod
    def _capture_record(monkeypatch) -> dict:
        recorded: dict = {}

        async def fake_record(self, **kwargs):
            recorded.update(kwargs)
            return "dec00001"

        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", fake_record)
        return recorded

    @pytest.mark.asyncio
    async def test_the_repair_branch_grounds_on_the_pathway_it_found(
        self, monkeypatch
    ):
        """The hashes the READ returned must reach `RecordDecision` as a ground."""
        self._confirming(monkeypatch)
        recorded = self._capture_record(monkeypatch)
        self._patch_repo(monkeypatch, self._perspectives(2))
        self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, ["tr0001", "tr0002"])

        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

        grounds = recorded["grounds"] or []
        pathways = [g for g in grounds if g.role == "adopted_pathway"]
        assert len(pathways) == 1, (
            "the closing wove pathways and recorded a decision that names none "
            "— r16's 0/6 defect"
        )
        assert pathways[0].hash == "tr0001"

    @pytest.mark.asyncio
    async def test_only_one_pathway_is_adopted(self, monkeypatch):
        """The role is singular: "the pathway adopted as the ongoing recipe".

        Grounding all six would turn the re-audit's "here is the recipe you
        adopted" back into a menu, which is the thing a decision closes.
        """
        self._confirming(monkeypatch)
        recorded = self._capture_record(monkeypatch)
        self._patch_repo(monkeypatch, self._perspectives(2))
        self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, [f"tr{i:04d}" for i in range(6)])

        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

        roles = [g.role for g in (recorded["grounds"] or [])]
        assert roles.count("adopted_pathway") == 1

    @pytest.mark.asyncio
    async def test_a_closing_with_no_pathway_records_without_one(self, monkeypatch):
        """No pathway is a non-event, never a lost record.

        A wrong or absent ground both leave the record standing; only failing to
        write it is unrecoverable.
        """
        self._confirming(monkeypatch)
        recorded = self._capture_record(monkeypatch)
        self._patch_repo(monkeypatch, self._perspectives(2))
        self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

        assert recorded["stance"] == "s"
        roles = [g.role for g in (recorded["grounds"] or [])]
        assert "adopted_pathway" not in roles

    @pytest.mark.asyncio
    async def test_nothing_to_weave_still_grounds_on_what_is_there(
        self, monkeypatch
    ):
        """The r16 rep2-wobble_b cell: the model wove, so the seam must not.

        It called `explore` at t2 and `record_decision` at t5 with 30 pathways
        in hand. Every perspective was already in a cycle, so `unwoven` was
        empty — and the old `return` handed back nothing to ground on. Nothing
        to BUILD is not nothing to GROUND.
        """
        self._patch_repo(monkeypatch, self._perspectives(3, woven=3))
        calls = self._capture_exploration(monkeypatch)
        monkeypatch.setattr(
            _StubAdvisor, "_existing_pathway_hashes", lambda self: ["tr0009"]
        )

        pathways = await _StubAdvisor([])._ensure_pathways_before_closing()

        assert calls == [], "re-wove a graph that was already woven"
        assert pathways == ["tr0009"]

    @pytest.mark.asyncio
    async def test_an_already_recorded_decision_is_grounded_after_the_fact(
        self, monkeypatch
    ):
        """GROUNDED_IN is analytical, so the committed record can still take one.

        This branch is the LARGER one — `record_decision` ran without `explore`
        in 50 saved A2 cells against 48 with both — and it used to end at the
        weave, calling itself "the weaker half" on the belief that a written
        record was closed to new grounds. `Decision`'s own docstring shows
        `commit()` then `grounds.connect(...)`.
        """
        self._patch_repo(monkeypatch, self._perspectives(2))
        self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, ["tr0007"])
        connected = _StubDecision()
        monkeypatch.setattr(
            _StubAdvisor, "_decision_recorded_this_turn", lambda self: connected
        )
        target = object()
        monkeypatch.setattr(
            "dialectical_framework.graph.repositories.node_repository."
            "NodeRepository.find_by_hash",
            lambda self, h, **kw: target if h == "tr0007" else None,
        )

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert len(connected.connected) == 1
        node, rel = connected.connected[0]
        assert node is target
        assert rel.role == "adopted_pathway"

    @pytest.mark.asyncio
    async def test_a_second_closing_does_not_double_ground(self, monkeypatch):
        """`connect` dedups only direction="any" edges, so check before adding.

        Two closings in one session would otherwise leave the record with two
        identical GROUNDED_IN edges and the re-audit naming the same recipe
        twice.
        """
        self._patch_repo(monkeypatch, self._perspectives(2))
        self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, ["tr0007"])
        decision = _StubDecision(existing_roles=["adopted_pathway"])
        monkeypatch.setattr(
            _StubAdvisor, "_decision_recorded_this_turn", lambda self: decision
        )

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert decision.connected == []

    @pytest.mark.asyncio
    async def test_the_decision_is_found_by_the_report_not_by_recency(
        self, monkeypatch
    ):
        """Which record gets grounded is a fact in the tool report, not a guess.

        A session can record more than one decision, so "the newest Decision in
        the DB" would ground the wrong one whenever a turn closes a second
        question.
        """
        looked_up = []
        monkeypatch.setattr(
            "dialectical_framework.graph.repositories.node_repository."
            "NodeRepository.find_by_hash",
            lambda self, h, **kw: looked_up.append(h),
        )
        report = _ok_report()
        report.artifacts["decision_hash"] = "dec4242"

        advisor = _StubAdvisor([_tool_result("record_decision", report)])
        advisor._decision_recorded_this_turn()

        assert looked_up == ["dec4242"]

    @pytest.mark.asyncio
    async def test_a_grounding_failure_never_breaks_the_turn(self, monkeypatch):
        """The reply is already delivered; a missing edge is not the person's problem."""
        self._patch_repo(monkeypatch, self._perspectives(2))
        self._capture_exploration(monkeypatch)
        self._graph_pathways(monkeypatch, ["tr0007"])

        def boom(self):
            raise RuntimeError("memgraph went away")

        monkeypatch.setattr(_StubAdvisor, "_decision_recorded_this_turn", boom)

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")


class _StubDecision:
    """A committed Decision's `grounds` manager, and nothing else."""

    def __init__(self, existing_roles: list[str] | None = None) -> None:
        self.hash = "dec00001"
        self.connected: list = []

        class _Rel:
            def __init__(self, role: str) -> None:
                self.role = role

        existing = [(object(), _Rel(r)) for r in (existing_roles or [])]
        outer = self

        class _Grounds:
            @staticmethod
            def all():
                return existing

            @staticmethod
            def connect(target, relationship=None):
                outer.connected.append((target, relationship))

        self.grounds = _Grounds()


class TestDeferredPathwayConstruction(_SeamFixtures):
    """The weave the closing is entitled to, moved off the person's wait.

    THE GAP THIS CLOSES
    ===================
    `_ensure_pathways_before_closing` stopped building because building cost
    127.7s and 387.7s on two turns of `timing-check-building`, both on the turn
    immediately before the closing. Removing it was right about the PLACE and
    wrong to leave the work undone: split by whether the graph was woven at
    closing, the judged mean was -0.25 woven against -0.69 unwoven over 36
    scores each (`claim2-weak-r15-voice`), and `a15-floor` reproduced it
    independently — A2's structural delta against A1 was +0.74 in the cells that
    wove and -0.32 in the cells that did not.

    Everything else the latency work left behind was delegated to a tool the
    model has to elect, and measured over the six A2 cells of `a15-floor` the
    model does not elect the deepening ones: `anchor` 6/6, `explore` 2/6,
    `audit_feasibility` 1/6, `deepen` 0/6, and the perspective cap's own
    "weave the deferred ones in a follow-up call" 0. So this seam STARTS the
    weave rather than advertising it.

    These tests are DB-free: `run_exploration_detailed` and the perspective
    repository are both patched, so what is pinned is the scheduling, the
    single-flight guard, the drain, and the bounds — not the exploration.
    """

    def _weave(self, monkeypatch, *, rounds_before_woven: int = 1, built=None):
        """A fake weave that actually WEAVES, so progress can be observed.

        The stub perspectives carry their own `in_cycle` flag and the fake flips
        them after `rounds_before_woven` calls. Without that the no-progress
        guard would stop every test after one round and nothing about the drain
        loop would be exercised.
        """
        state = {"calls": [], "perspectives": None}

        async def fake_run(*, perspective_hashes, intent, nexus_hash):
            state["calls"].append(list(perspective_hashes))
            if len(state["calls"]) >= rounds_before_woven:
                for pp in state["perspectives"]:
                    pp.in_cycle = True
            return "{}", list(built or [])

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", fake_run)
        return state

    def _with_perspectives(self, monkeypatch, state, count, woven=0):
        perspectives = self._perspectives(count, woven=woven)
        state["perspectives"] = perspectives
        self._patch_repo(monkeypatch, perspectives)
        return perspectives

    @pytest.mark.asyncio
    async def test_an_unwoven_closing_weaves_off_the_turn(self, monkeypatch):
        """The r7 shape — five anchored tensions, no explore — now gets its weave."""
        state = self._weave(monkeypatch, built=["tr0100"])
        self._with_perspectives(monkeypatch, state, 5)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert state["calls"] == [["h0000", "h0001", "h0002", "h0003", "h0004"]], (
            "the closing left five tensions unwoven and nothing built them"
        )

    @pytest.mark.asyncio
    async def test_the_decision_is_grounded_on_what_the_weave_built(
        self, monkeypatch
    ):
        """The point of the weave is the ground, not the wheel.

        `a15-floor` measured 0/4 `adopted_pathway` grounds with pathways on the
        graph, so a weave that lands and grounds nothing reproduces the defect
        it was built to fix.
        """
        state = self._weave(monkeypatch, built=["tr0100", "tr0101"])
        self._with_perspectives(monkeypatch, state, 2)
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append((h, list(p))),
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert grounded == [("dec00001", ["tr0100", "tr0101"])]

    @pytest.mark.asyncio
    async def test_a_second_closing_mid_weave_is_drained_not_dropped(
        self, monkeypatch
    ):
        """Single flight, and the queue is what makes single flight safe.

        Two concurrent explorations against one nexus is the race this seam must
        not have; silently dropping the second decision would be the cure being
        worse. So the running task re-reads the queue, which is why the queue is
        a field.
        """
        state = self._weave(monkeypatch)
        self._with_perspectives(monkeypatch, state, 4)
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append(h),
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        # Same tick, before the task has had a chance to run: the second closing
        # must join the first weave rather than start its own.
        advisor._schedule_pathway_construction("dec00002")
        first_task = advisor._deferred_pathway_task
        advisor._schedule_pathway_construction("dec00002")
        assert advisor._deferred_pathway_task is first_task, (
            "a second closing started a second concurrent weave"
        )
        await advisor.wait_for_deferred_work()

        assert sorted(grounded) == ["dec00001", "dec00002"]

    @pytest.mark.asyncio
    async def test_the_same_decision_is_queued_once(self, monkeypatch):
        """A turn can reach the seam twice; the record still takes one ground."""
        state = self._weave(monkeypatch)
        self._with_perspectives(monkeypatch, state, 2)
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append(h),
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert grounded == ["dec00001"]

    @pytest.mark.asyncio
    async def test_nothing_unwoven_means_no_exploration(self, monkeypatch):
        """A model that DID explore must not pay for it again off the turn."""
        state = self._weave(monkeypatch)
        self._with_perspectives(monkeypatch, state, 3, woven=3)
        monkeypatch.setattr(
            _StubAdvisor, "_existing_pathway_hashes", lambda self: ["tr0009"]
        )
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append((h, list(p))),
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert state["calls"] == [], "re-wove a graph that was already woven"
        # Nothing to weave is still something to ground — the r16 rep2-wobble_b
        # cell, which had 30 pathways and no `adopted_pathway`.
        assert grounded == [("dec00001", ["tr0009"])]

    @pytest.mark.asyncio
    async def test_the_loop_drains_the_perspective_cap(self, monkeypatch):
        """`advisor_max_perspectives_per_exploration` bounds a CALL, not the work.

        The cap weaves 2 and reports the rest as `deferred_perspective_hashes`
        for the model to pick up in a follow-up call, which fired 0 times in
        `a15-floor`. There is no turn here, so the loop keeps calling until
        nothing is unwoven — each call still obeying the cap.
        """
        state = self._weave(monkeypatch, rounds_before_woven=3)
        perspectives = self._with_perspectives(monkeypatch, state, 6)

        # Weave two per call, exactly as the real cap does.
        real_run = state["calls"]

        async def capped_run(*, perspective_hashes, intent, nexus_hash):
            real_run.append(list(perspective_hashes))
            for pp in perspectives:
                if pp.hash in list(perspective_hashes)[:2]:
                    pp.in_cycle = True
            return "{}", []

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", capped_run)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert [len(c) for c in state["calls"]] == [6, 4, 2], (
            "the cap's leftovers were never woven — the deferral the model "
            "never followed up on"
        )
        assert all(pp.in_cycle for pp in perspectives)

    @pytest.mark.asyncio
    async def test_a_weave_that_makes_no_progress_stops(self, monkeypatch):
        """The spin guard. A perspective the pipeline declines costs ONE round.

        Without this, a graph that cannot be woven turns the deferral into an
        unbounded loop against a provider — strictly worse than the logged gap
        it replaces.
        """
        state = self._weave(monkeypatch, rounds_before_woven=99)
        self._with_perspectives(monkeypatch, state, 3)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert len(state["calls"]) == 1, (
            f"a weave that wove nothing was repeated {len(state['calls'])} times"
        )

    @pytest.mark.asyncio
    async def test_a_failed_weave_leaves_the_record_as_it_was(self, monkeypatch):
        """Fail-soft: the reply is delivered and the record already stands.

        The decision keeps the grounds it was recorded with — the pre-deferral
        behaviour, not a new failure mode.
        """
        async def boom(*, perspective_hashes, intent, nexus_hash):
            raise RuntimeError("provider went away")

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", boom)
        self._patch_repo(monkeypatch, self._perspectives(2))
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append(h),
        )

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert grounded == []

    @pytest.mark.asyncio
    async def test_waiting_is_safe_when_nothing_was_deferred(self):
        """The host obligation must not require the host to know whether to."""
        await _StubAdvisor([]).wait_for_deferred_work()

    @pytest.mark.asyncio
    async def test_no_decision_hash_schedules_nothing(self, monkeypatch):
        """A weave with nothing to attach to is work spent on no one's behalf."""
        state = self._weave(monkeypatch)
        self._with_perspectives(monkeypatch, state, 3)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction(None)
        await advisor.wait_for_deferred_work()

        assert state["calls"] == []
        assert advisor._deferred_pathway_task is None


class TestTheAdoptedRecipeIsScored(_SeamFixtures):
    """The third audited latency-for-reasoning trade, paid at the closing.

    `settings.audit_transformations` went off because the eager pass was 40% of
    `explore`'s provider spend for an annotation, and the repair was left to a
    tool the model elects in **1 of 6** A2 cells (`a15-floor`) and **0 of 6**
    in `weave-offturn` — the same shape as `explore` 2/6 and `deepen` 0/6. So the
    drain asks for it, on ONE pathway: the recipe the record is grounded on.

    These tests are DB-free, so `_adopted_pathway_hash` is stubbed everywhere
    except in the class below it, which tests that method against a fake graph.
    What is pinned here is scope, ordering, dedup and fail-softness — never the
    audit itself, which is `test_audit_feasibility_tool.py`'s subject.
    """

    def _capture_audit(self, monkeypatch, *, boom: bool = False) -> list:
        calls: list = []

        async def fake_audit(hashes):
            calls.append(list(hashes))
            if boom:
                raise RuntimeError("provider went away")
            return "{}"

        import dialectical_framework.agents.orchestrator.tools.audit_feasibility \
            as audit_mod

        monkeypatch.setattr(audit_mod, "run_audit_feasibility", fake_audit)
        return calls

    def _adopted(self, monkeypatch, mapping: dict[str, str | None]):
        monkeypatch.setattr(
            _StubAdvisor,
            "_adopted_pathway_hash",
            lambda self, decision_hash: mapping.get(decision_hash),
        )

    def _weave(self, monkeypatch, *, rounds_before_woven: int = 1, built=None):
        """Same fake weave as the class above, with its own state dict."""
        state = {"calls": [], "perspectives": None}

        async def fake_run(*, perspective_hashes, intent, nexus_hash):
            state["calls"].append(list(perspective_hashes))
            if len(state["calls"]) >= rounds_before_woven:
                for pp in state["perspectives"]:
                    pp.in_cycle = True
            return "{}", list(built or [])

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", fake_run)
        return state

    def _with_perspectives(self, monkeypatch, state, count, woven=0):
        perspectives = self._perspectives(count, woven=woven)
        state["perspectives"] = perspectives
        self._patch_repo(monkeypatch, perspectives)
        return perspectives

    @pytest.mark.asyncio
    async def test_the_recipe_the_record_adopted_gets_a_feasibility_band(
        self, monkeypatch
    ):
        """One closing, one pathway, two provider calls — not 2 x 6N."""
        state = self._weave(monkeypatch, built=["tr0100", "tr0101"])
        self._with_perspectives(monkeypatch, state, 2)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )
        self._adopted(monkeypatch, {"dec00001": "tr0100"})
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == [["tr0100"]]

    @pytest.mark.asyncio
    async def test_the_edge_is_read_not_what_the_weave_built(self, monkeypatch):
        """Two different questions, and only one of them is the person's recipe.

        The weave knows what it BUILT; the edge knows what the record RESTS on,
        which may be a pathway the model chose with the conversation in view
        (`_adopted_pathway_grounds` calls its own pick "the floor, not the
        ceiling"). Scoring the weave's first hash would score a recipe nobody
        adopted.
        """
        state = self._weave(monkeypatch, built=["tr0100", "tr0101"])
        self._with_perspectives(monkeypatch, state, 2)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )
        self._adopted(monkeypatch, {"dec00001": "tr9999"})
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == [["tr9999"]], (
            "the audit followed the weave instead of the record's own ground"
        )

    @pytest.mark.asyncio
    async def test_a_closing_with_no_recipe_spends_nothing(self, monkeypatch):
        """No ground, no call. Same rule as the weave's own early return: work
        no record will point at is unattributed cost."""
        state = self._weave(monkeypatch, built=[])
        self._with_perspectives(monkeypatch, state, 2)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )
        self._adopted(monkeypatch, {"dec00001": None})
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == []

    @pytest.mark.asyncio
    async def test_the_audit_waits_for_the_whole_drain(self, monkeypatch):
        """Ordering, and it is a priority statement rather than a preference.

        The weave is the larger restoration and the audit is an annotation, so
        the annotation must not queue in front of it — and a task cancelled at
        shutdown should lose the cheaper half.
        """
        order: list[str] = []
        state = {"calls": [], "perspectives": None}

        async def fake_run(*, perspective_hashes, intent, nexus_hash):
            order.append("weave")
            state["calls"].append(list(perspective_hashes))
            # Weave one perspective a round, so the drain runs twice.
            for pp in state["perspectives"]:
                if not pp.in_cycle:
                    pp.in_cycle = True
                    break
            return "{}", ["tr0100"]

        import dialectical_framework.agents.advisor.tools.explore as explore_mod

        monkeypatch.setattr(explore_mod, "run_exploration_detailed", fake_run)
        perspectives = self._perspectives(2)
        state["perspectives"] = perspectives
        self._patch_repo(monkeypatch, perspectives)

        def ground(self, decision_hash, pathways):
            order.append("ground")
            # A second closing lands mid-drain, so the loop runs another round.
            if len(order) == 2:
                self._decisions_awaiting_pathway.append("dec00002")

        monkeypatch.setattr(_StubAdvisor, "_ground_recorded_decision", ground)
        self._adopted(monkeypatch, {"dec00001": "tr0100", "dec00002": "tr0100"})

        async def fake_audit(hashes):
            order.append("audit")
            return "{}"

        import dialectical_framework.agents.orchestrator.tools.audit_feasibility \
            as audit_mod

        monkeypatch.setattr(audit_mod, "run_audit_feasibility", fake_audit)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert order.count("weave") >= 2, "the drain did not run more than once"
        assert order.count("audit") == 1, "the audit ran per round, not per drain"
        assert order[-1] == "audit", "the annotation ran before the weave finished"

    @pytest.mark.asyncio
    async def test_two_decisions_on_one_recipe_score_it_once(self, monkeypatch):
        """Dedup here, idempotence in the tool — belt and braces, cheaply.

        The tool skips an already-scored pathway, so a duplicate would cost
        nothing in provider calls; it would still write a second critique
        Rationale whose prose disagrees with the surviving score, which is the
        defect that skip exists to prevent.
        """
        state = self._weave(monkeypatch, built=["tr0100"])
        self._with_perspectives(monkeypatch, state, 2)
        monkeypatch.setattr(
            _StubAdvisor, "_ground_recorded_decision", lambda self, h, p: None
        )
        self._adopted(
            monkeypatch, {"dec00001": "tr0100", "dec00002": "tr0100"}
        )
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([])
        advisor._decisions_awaiting_pathway.append("dec00002")
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == [["tr0100"]]

    @pytest.mark.asyncio
    async def test_a_failed_weave_still_scores_what_was_already_grounded(
        self, monkeypatch
    ):
        """Why the weave failure BREAKS instead of returning.

        A decision grounded in an earlier round has a recipe on the record, and
        this round's failure is about the weave rather than about that record.

        Stubs the WEAVE and not `run_exploration_detailed`, and that is the
        point of failure worth recording: the guarantee is about the drain's
        rounds, but the weave runs a loop of its OWN over the perspective cap,
        so a provider that fails on its second call fails inside drain round
        one — where nothing has been grounded yet and there is correctly
        nothing to score. Written that way first, this test asserted the break
        while exercising the return.
        """
        calls = {"n": 0}

        async def weave(self):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("provider went away")
            return ["tr0100"]

        monkeypatch.setattr(_StubAdvisor, "_weave_unwoven_perspectives", weave)

        def ground(self, decision_hash, pathways):
            if decision_hash == "dec00001":
                self._decisions_awaiting_pathway.append("dec00002")

        monkeypatch.setattr(_StubAdvisor, "_ground_recorded_decision", ground)
        self._adopted(monkeypatch, {"dec00001": "tr0100", "dec00002": None})
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert calls["n"] == 2, "the drain did not reach a second round"
        assert audited == [["tr0100"]]

    @pytest.mark.asyncio
    async def test_an_audit_failure_costs_the_band_and_nothing_else(
        self, monkeypatch
    ):
        """Fail-soft, and the grounding must survive it.

        This runs turns after the reply was delivered, so a provider error here
        may not surface to the person and must not take the recipe off the
        record with it.
        """
        state = self._weave(monkeypatch, built=["tr0100"])
        self._with_perspectives(monkeypatch, state, 2)
        grounded: list = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append(h),
        )
        self._adopted(monkeypatch, {"dec00001": "tr0100"})
        audited = self._capture_audit(monkeypatch, boom=True)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == [["tr0100"]]
        assert grounded == ["dec00001"], "an annotation failure lost the ground"

    @pytest.mark.asyncio
    async def test_nothing_grounded_means_nothing_audited(self, monkeypatch):
        """A drain that grounds nothing (no decision queued) audits nothing."""
        state = self._weave(monkeypatch)
        self._with_perspectives(monkeypatch, state, 2)
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction(None)
        await advisor.wait_for_deferred_work()

        assert audited == []


class TestTheFeasibilityAuditIsAMode(_SeamFixtures):
    """`automatic_feasibility_audit` chooses WHO initiates, not whether it exists.

    The distinction is the reason the setting is worth having, and it is easy to
    implement as the wrong thing. Turning this off must not remove feasibility
    scoring from the framework — `audit_feasibility` is a tool and stays a tool,
    so the band remains reachable by asking. What the flag switches off is the
    ELECTIVE-free route: automatic scoring at the closing, which is what makes
    the band measurable at all, since the model elected the tool in 1 of 6 A2
    cells (`a15-floor`) and 0 of 6 (`weave-offturn`).

    The cost of automatic is measured rather than assumed. `feasibility-offturn`:
    the band reached 5 of 5 records that ground a pathway against a 0/6 baseline,
    at **+46% A2 cell wall** (701.0s vs 479.1s) and one turn in 48 where the
    person waited **284.5s** for off-turn work to settle. The seam it was aimed
    at did not move — wobble discrimination 1/3 pairs before and after. Hence a
    switch, and hence these tests: a mode whose off state quietly disabled the
    tool would be a regression disguised as a configuration option.

    The DEFAULT is manual since 2026-09-15, which makes the elective route the
    one that runs — so the moments the prompt names for it are now load-bearing
    rather than advisory, and they are pinned in
    `test_prompt_review_regressions.TestTheElectiveRouteNamesItsMoments`.
    """

    # The weave/audit/adopted helpers live on the class above rather than on
    # `_SeamFixtures`, and aliasing them is preferable to moving them: this class
    # varies ONE thing against that class's setup, and a copy of the setup would
    # be free to drift away from the tests it is supposed to be comparable to.
    _capture_audit = TestTheAdoptedRecipeIsScored._capture_audit
    _adopted = TestTheAdoptedRecipeIsScored._adopted
    _weave = TestTheAdoptedRecipeIsScored._weave

    def _drain_ready(self, monkeypatch, adopted="tr0100"):
        """A weave that succeeds, so the audit is the only thing left to vary."""
        state = self._weave(monkeypatch, built=[adopted])
        perspectives = self._perspectives(2, woven=0)
        state["perspectives"] = perspectives
        self._patch_repo(monkeypatch, perspectives)
        grounded: list[str] = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_ground_recorded_decision",
            lambda self, h, p: grounded.append(h),
        )
        self._adopted(monkeypatch, {"dec00001": adopted})
        return grounded

    @pytest.mark.asyncio
    async def test_automatic_mode_scores_the_adopted_pathway(self, monkeypatch):
        self._drain_ready(monkeypatch)
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([], automatic_feasibility_audit=True)
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == [["tr0100"]]

    @pytest.mark.asyncio
    async def test_manual_mode_scores_nothing_at_the_closing(self, monkeypatch):
        self._drain_ready(monkeypatch)
        audited = self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([], automatic_feasibility_audit=False)
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert audited == [], "manual mode still spent provider calls"

    @pytest.mark.asyncio
    async def test_manual_mode_still_weaves_and_still_grounds(self, monkeypatch):
        """The switch is about the AUDIT, and about nothing else in the drain.

        Gating too much is the likelier mistake here than gating too little: the
        audit is the last thing the drain does, so a return placed one line too
        early takes the weave and the grounding with it — and both of those are
        the previous trade, already paid and not up for renegotiation.
        """
        grounded = self._drain_ready(monkeypatch)
        self._capture_audit(monkeypatch)

        advisor = _StubAdvisor([], automatic_feasibility_audit=False)
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert grounded == ["dec00001"], "manual mode also skipped the grounding"

    @pytest.mark.asyncio
    async def test_manual_mode_costs_no_graph_read_either(self, monkeypatch):
        """Return BEFORE resolving the pathway, not after.

        `_adopted_pathway_hash` is a graph read per decision. Skipping the
        provider call but still paying the read would make manual mode quietly
        non-free, which is the sort of thing that is never noticed because
        nothing it produces is visible.
        """
        self._drain_ready(monkeypatch)
        self._capture_audit(monkeypatch)
        reads: list[str] = []
        monkeypatch.setattr(
            _StubAdvisor,
            "_adopted_pathway_hash",
            lambda self, h: reads.append(h) or "tr0100",
        )

        advisor = _StubAdvisor([], automatic_feasibility_audit=False)
        advisor._schedule_pathway_construction("dec00001")
        await advisor.wait_for_deferred_work()

        assert reads == [], "manual mode resolved the pathway it never scores"

    def test_the_tool_is_not_gated_by_the_mode(self):
        """Off is not "no feasibility scoring", so the flag may gate ONE place.

        Checked against the sources rather than by wiring a container: the name
        must appear in the advisor's drain and nowhere in the tool or in the
        toolsets that publish it. A gate added inside `audit_feasibility` would
        make the off state mean "nobody can ever ask", which is exactly what
        this setting is documented not to do.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "src" / "dialectical_framework"
        flag = "automatic_feasibility_audit"

        advisor_src = (root / "agents" / "advisor" / "advisor.py").read_text()
        assert advisor_src.count(f"self.settings.{flag}") == 1

        tool_src = (
            root / "agents" / "orchestrator" / "tools" / "audit_feasibility.py"
        ).read_text()
        assert flag not in tool_src, "the tool itself is gated; off would mean off"

        toolsets_src = (root / "agents" / "toolsets.py").read_text()
        assert flag not in toolsets_src, "the tool is unwired in manual mode"

    def test_the_default_is_manual_and_the_env_can_flip_it(self, monkeypatch):
        """Default MANUAL since 2026-09-15, and the flip had a precondition.

        Automatic was the default only because flipping it would have
        un-measured `feasibility-offturn`, the round that priced it — a research
        reason, which expires once the build ships and real conversations are the
        measurement. What made manual untrustworthy was the 1/6 and 0/6 election
        rate, so the flip was paired with the prompt repair that names the two
        moments automatic mode covered (the closing, and a wobble about carrying
        the recipe out) — see `TestTheElectiveRouteNamesItsMoments`. Manual
        without those moments named would be this test asserting a regression.
        """
        from dialectical_framework.settings import Settings

        # The FIELD default, not a constructed instance: `Settings` requires
        # `ai_model`, so constructing one here would test the fixture.
        assert (
            Settings.model_fields["automatic_feasibility_audit"].default is False
        )

        monkeypatch.setenv("DIALEXITY_AUTOMATIC_FEASIBILITY_AUDIT", "false")
        assert Settings.from_env().automatic_feasibility_audit is False
        monkeypatch.setenv("DIALEXITY_AUTOMATIC_FEASIBILITY_AUDIT", "true")
        assert Settings.from_env().automatic_feasibility_audit is True


class TestTheAdoptedPathwayIsReadFromTheEdge:
    """`_adopted_pathway_hash` against a fake graph.

    Separate from the class above because that one stubs this method out: a test
    that both stubs the read and asserts on it would pin nothing.
    """

    class _Rel:
        def __init__(self, role: str) -> None:
            self.role = role

    class _Grounds:
        def __init__(self, pairs) -> None:
            self._pairs = pairs

        def all(self):
            return list(self._pairs)

    def _decision(self, pairs):
        class _Decision:
            grounds = self._Grounds(pairs)

        return _Decision()

    def _patch_lookup(self, monkeypatch, decision):
        from dialectical_framework.graph.repositories import node_repository

        class _Repo:
            def find_by_hash(self, needle, node_type=None):
                return decision

        monkeypatch.setattr(node_repository, "NodeRepository", _Repo)

    def _transformation(self, hash_value: str):
        from dialectical_framework.graph.nodes.transformation import \
            Transformation

        tr = Transformation.__new__(Transformation)
        object.__setattr__(tr, "hash", hash_value)
        return tr

    def test_the_adopted_pathway_role_is_the_one_read(self, monkeypatch):
        """A decision carries several grounds and only one is the recipe."""
        risk = self._transformation("tr0001")
        recipe = self._transformation("tr0002")
        decision = self._decision(
            [
                (risk, self._Rel("accepted_cost")),
                (recipe, self._Rel("adopted_pathway")),
            ]
        )
        self._patch_lookup(monkeypatch, decision)

        assert _StubAdvisor([])._adopted_pathway_hash("dec00001") == "tr0002"

    def test_a_decision_with_no_recipe_reads_none(self, monkeypatch):
        cost = self._transformation("tr0001")
        decision = self._decision([(cost, self._Rel("accepted_cost"))])
        self._patch_lookup(monkeypatch, decision)

        assert _StubAdvisor([])._adopted_pathway_hash("dec00001") is None

    def test_a_missing_decision_reads_none(self, monkeypatch):
        self._patch_lookup(monkeypatch, None)

        assert _StubAdvisor([])._adopted_pathway_hash("dec00001") is None

    def test_a_lookup_failure_reads_none(self, monkeypatch):
        """Fail-soft: the reply was delivered turns ago."""
        from dialectical_framework.graph.repositories import node_repository

        class _Repo:
            def find_by_hash(self, needle, node_type=None):
                raise RuntimeError("graph went away")

        monkeypatch.setattr(node_repository, "NodeRepository", _Repo)

        assert _StubAdvisor([])._adopted_pathway_hash("dec00001") is None


class TestBothClosingBranchesDefer(_SeamFixtures):
    """Neither branch may close over an unwoven graph in silence.

    The two branches split 50/48 across every saved A2 cell (`record_decision`
    without `explore` against both), so a deferral wired into one of them would
    miss about half the closings.
    """

    @pytest.mark.asyncio
    async def test_the_model_recorded_branch_defers(self, monkeypatch):
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)
        decision = _StubDecision()
        monkeypatch.setattr(
            _StubAdvisor, "_decision_recorded_this_turn", lambda self: decision
        )

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert self._scheduled == ["dec00001"]

    @pytest.mark.asyncio
    async def test_the_repair_branch_defers_on_the_hash_it_wrote(self, monkeypatch):
        TestTheClosingGroundsOnThePathwayItBuilt._confirming(monkeypatch)
        TestTheClosingGroundsOnThePathwayItBuilt._capture_record(monkeypatch)
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._repair_unrecorded_decision("write it down", "done")

        assert self._scheduled == ["dec00001"], (
            "the repair wrote a record over an unwoven graph and queued no weave"
        )

    @pytest.mark.asyncio
    async def test_an_unconfirmed_turn_defers_nothing(self, monkeypatch):
        """No closing, no entitlement. The weave is a closing's due, not upkeep."""

        async def not_confirmed(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(confirmed=False)

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", not_confirmed)
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)

        await _StubAdvisor([])._repair_unrecorded_decision("hm", "maybe")

        assert self._scheduled == []

    @pytest.mark.asyncio
    async def test_a_recorded_decision_that_cannot_be_resolved_defers_nothing(
        self, monkeypatch
    ):
        """No hash, nothing to ground: the deferral needs a target, not a hope."""
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)
        monkeypatch.setattr(
            _StubAdvisor, "_decision_recorded_this_turn", lambda self: None
        )

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert self._scheduled == [None]


class TestTheSeamSaysWhatItDid(_SeamFixtures):
    """`off_path_s` said how long the seam took. This says what it did.

    Written because a round was decided without it. `feasibility-offturn`
    measured a turn where the person waited 284.5s — 95% of their reply path —
    on `deferred_wait_s`, and the account of WHOSE closing they were waiting for
    rested on a log line the run never captured (`grep -c "left unrecorded"`
    over the whole archive returns 0). The round before it ruled the same tail
    out of being the deferral by reading `tool_calls`, which cannot see the
    framework's own writes — and this seam exists precisely to write records the
    model did not, so an absence there is evidence about the MODEL and never
    about the framework.

    Every assertion below is on a field, not a log line, for that reason.
    """

    @staticmethod
    def _timing_fields():
        from dialectical_framework.agents.turn_timing import (ClosingOutcome,
                                                              DeferralOutcome)

        return ClosingOutcome, DeferralOutcome

    @pytest.mark.asyncio
    async def test_a_model_recorded_closing_is_not_reported_as_a_repair(
        self, monkeypatch
    ):
        """The larger population, and the one an unsplit "the seam fired" would
        inflate: `record_decision` ran WITHOUT `explore` in 50 saved A2 cells
        against 48 with both, so pooling the two branches would overstate the
        repair's reach several times over."""
        ClosingOutcome, _ = self._timing_fields()
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)
        monkeypatch.setattr(
            _StubAdvisor, "_decision_recorded_this_turn", lambda self: _StubDecision()
        )

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is ClosingOutcome.MODEL_RECORDED

    @pytest.mark.asyncio
    async def test_a_repair_is_reported_as_a_repair(self, monkeypatch):
        ClosingOutcome, _ = self._timing_fields()
        TestTheClosingGroundsOnThePathwayItBuilt._confirming(monkeypatch)
        TestTheClosingGroundsOnThePathwayItBuilt._capture_record(monkeypatch)
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)

        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is ClosingOutcome.REPAIRED

    @pytest.mark.asyncio
    async def test_an_ordinary_turn_says_so_rather_than_saying_nothing(
        self, monkeypatch
    ):
        """`NO_CLOSING`, not `None`. The seam running and finding nothing to close
        is a positive result with its own rate; `None` is reserved for the turn
        that died before the seam concluded, and the two must never pool."""
        ClosingOutcome, DeferralOutcome = self._timing_fields()

        async def not_confirmed(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(confirmed=False)

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", not_confirmed)
        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision("hm", "maybe")

        assert advisor._last_closing is ClosingOutcome.NO_CLOSING
        # And nothing about the deferral: the seam never reached the scheduler,
        # which is not the same claim as "it scheduled nothing".
        assert advisor._last_deferral is None

    @pytest.mark.asyncio
    async def test_a_confirmation_with_nothing_to_write_is_a_failure(
        self, monkeypatch
    ):
        """The shape of the archive's one unexplained loss.

        `claim2-weak-r8-pathways`/wobble_b closed on an unambiguous confirmation
        and recorded NOTHING, and the cause is still unknown because nothing
        captured what its `except` blocks saw. A verdict that says the person
        confirmed and then carries no question or stance is that case from the
        inside — so it is counted as a failure, not filed beside the ordinary
        turns that had nothing to close.
        """
        ClosingOutcome, _ = self._timing_fields()

        async def confirmed_but_empty(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(
                confirmed=True, question="q", stance="   ", rationale="r"
            )

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", confirmed_but_empty)
        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision("go ahead", "ok")

        assert advisor._last_closing is ClosingOutcome.FAILED, (
            "a confirmed closing the seam could not state was filed as an "
            "ordinary turn with nothing to close"
        )

    @pytest.mark.asyncio
    async def test_a_classifier_that_answers_nothing_is_a_failure(self, monkeypatch):
        ClosingOutcome, _ = self._timing_fields()

        async def no_verdict(self, **kwargs):
            return None

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", no_verdict)
        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is ClosingOutcome.FAILED

    @pytest.mark.asyncio
    async def test_a_swallowed_exception_is_reported_as_a_failure(self, monkeypatch):
        """Every fail-soft block in `src/` logs and continues by design, which is
        why a turn can lose a decision and still look healthy in the archive:
        reply present, `error` None, tools ok. This is the field that shows it."""
        ClosingOutcome, _ = self._timing_fields()

        async def boom(self, **kwargs):
            raise RuntimeError("bedrock throttled")

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", boom)
        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is ClosingOutcome.FAILED

    @pytest.mark.asyncio
    async def test_a_record_that_writes_no_hash_is_a_failure(self, monkeypatch):
        """The person was closing and nothing was written — the exact failure the
        seam exists to prevent, so it may not archive as a quiet no-op."""
        ClosingOutcome, _ = self._timing_fields()
        TestTheClosingGroundsOnThePathwayItBuilt._confirming(monkeypatch)
        self._patch_repo(monkeypatch, self._perspectives(3))
        self._capture_exploration(monkeypatch)

        async def writes_nothing(self, **kwargs):
            return None

        from dialectical_framework.concerns.record_decision import RecordDecision

        monkeypatch.setattr(RecordDecision, "resolve", writes_nothing)

        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is ClosingOutcome.FAILED
        assert advisor._last_deferral is None, (
            "nothing was written, so nothing was scheduled — and the field must "
            "not claim a deferral the scheduler never saw"
        )

    @pytest.mark.asyncio
    async def test_a_model_recorded_branch_that_raises_is_a_failure(self, monkeypatch):
        """`FAILED` wins over the branch label. The record exists — the model
        wrote it — but the seam's own work bought nothing, and what these fields
        answer is what `off_path_s` was spent on."""
        ClosingOutcome, _ = self._timing_fields()

        def boom(self):
            raise RuntimeError("graph down")

        monkeypatch.setattr(_StubAdvisor, "_existing_pathway_hashes", boom)
        self._patch_repo(monkeypatch, self._perspectives(3))

        advisor = _StubAdvisor([_tool_result("record_decision", _ok_report())])
        await advisor._repair_unrecorded_decision("write it down", "done")

        assert advisor._last_closing is ClosingOutcome.FAILED

    @pytest.mark.asyncio
    async def test_both_fields_are_reset_before_the_seam_runs(self, monkeypatch):
        """The whole instrument rests on this. `_record_turn_timing` reads these
        fields on the statement after the seam, so a value left over from the
        last turn would be published as this turn's — and it would be published
        as a MEASUREMENT, which is worse than the gap it replaced."""
        ClosingOutcome, DeferralOutcome = self._timing_fields()

        async def not_confirmed(self, *, user_message, assistant_message):
            return ConfirmationVerdictDto(confirmed=False)

        monkeypatch.setattr(DecisionConfirmationCheck, "resolve", not_confirmed)

        advisor = _StubAdvisor([])
        advisor._last_closing = ClosingOutcome.REPAIRED
        advisor._last_deferral = DeferralOutcome.STARTED
        await advisor._repair_unrecorded_decision("hm", "maybe")

        assert advisor._last_closing is ClosingOutcome.NO_CLOSING
        assert advisor._last_deferral is None, (
            "last turn's deferral survived into a turn that never scheduled"
        )


class TestTheDeferralSaysWhoStartedIt:
    """Which turn's closing a later `deferred_wait_s` is paying for.

    `deferred_wait_s` is charged to the turn that WAITS, so a large one is a
    fact about some earlier turn and the archive could not say which. These are
    the scheduler's four exits, and `STARTED` vs `JOINED` is the load-bearing
    pair: the seam is single flight, so a closing arriving while the weave runs
    queues onto the existing task. An instrument that recorded only "work is in
    flight" would charge the wait to the wrong turn.
    """

    @staticmethod
    def _outcomes():
        from dialectical_framework.agents.turn_timing import DeferralOutcome

        return DeferralOutcome

    def test_nothing_to_ground_is_recorded_rather_than_left_blank(self):
        """No record points anywhere, so no weave is due — and the seam says so.
        `None` here would read as "the scheduler was never reached"."""
        DeferralOutcome = self._outcomes()
        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction(None)

        assert advisor._deferred_pathway_task is None
        assert advisor._last_deferral is DeferralOutcome.NOTHING_TO_DEFER

    @pytest.mark.asyncio
    async def test_the_turn_that_creates_the_task_says_started(self, monkeypatch):
        DeferralOutcome = self._outcomes()

        async def noop(self):
            return None

        monkeypatch.setattr(_StubAdvisor, "_run_deferred_pathway_construction", noop)
        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")

        assert advisor._last_deferral is DeferralOutcome.STARTED
        await advisor.wait_for_deferred_work()

    @pytest.mark.asyncio
    async def test_a_closing_that_queues_onto_a_running_weave_says_joined(
        self, monkeypatch
    ):
        """Should be unreachable from a turn — both turn loops settle deferred
        work before submitting — so this exercises the branch directly. Seeing
        `joined` in an archive is evidence about the HOST (two turns overlapping
        on one sid, which the one-writer contract forbids), which is only a
        readable signal if the value is distinct from `started`."""
        DeferralOutcome = self._outcomes()
        release = asyncio.Event()

        async def blocks(self):
            await release.wait()

        monkeypatch.setattr(_StubAdvisor, "_run_deferred_pathway_construction", blocks)
        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")
        assert advisor._last_deferral is DeferralOutcome.STARTED
        # Let the task actually start, so the second call meets a running one.
        await asyncio.sleep(0)

        advisor._schedule_pathway_construction("dec00002")
        assert advisor._last_deferral is DeferralOutcome.JOINED
        # And the second closing is genuinely queued, not dropped — the value
        # would be a lie about the graph otherwise.
        assert "dec00002" in advisor._decisions_awaiting_pathway

        release.set()
        await advisor.wait_for_deferred_work()

    def test_no_loop_to_defer_onto_is_not_reported_as_nothing_to_defer(self):
        """A synchronous caller has no running loop, so there is nowhere to put
        the weave. The closing keeps its pre-deferral behaviour — but the record
        must not say there was nothing to do, because there was."""
        DeferralOutcome = self._outcomes()
        advisor = _StubAdvisor([])
        advisor._schedule_pathway_construction("dec00001")

        assert advisor._deferred_pathway_task is None
        assert advisor._last_deferral is DeferralOutcome.UNAVAILABLE
