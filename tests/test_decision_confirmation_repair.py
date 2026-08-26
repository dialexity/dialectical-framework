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

import logging

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.stream_events import ToolResult
from dialectical_framework.concerns.decision_confirmation_check import (
    ConfirmationVerdictDto, DecisionConfirmationCheck)


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
        principal: str = "human",
        nexus_hash: str | None = None,
    ) -> None:
        self._principal = principal
        self._nexus_hash = nexus_hash

        class _Conv:
            last_tool_results = list(tool_results or [])

        self._conversation = _Conv()

    _repair_unrecorded_decision = Advisor._repair_unrecorded_decision
    _recorded_decision_this_turn = Advisor._recorded_decision_this_turn
    _ensure_pathways_before_closing = Advisor._ensure_pathways_before_closing
    _existing_pathway_hashes = Advisor._existing_pathway_hashes
    _adopted_pathway_grounds = Advisor._adopted_pathway_grounds
    _attach_adopted_pathway = Advisor._attach_adopted_pathway
    _decision_recorded_this_turn = Advisor._decision_recorded_this_turn
    _accepted_cost_ground = Advisor.__dict__["_accepted_cost_ground"]


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

        advisor = _StubAdvisor([])
        await advisor._repair_unrecorded_decision(
            "Write that down as the decision.", "**Your Decision** Buy him out..."
        )

        assert recorded["stance"] == "Buy him out"
        assert recorded["question"] == "Buy out the cofounder or restructure?"
        # Same attestation the tool would have carried.
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
        # From ResponseComplete, not accumulated deltas: deltas cover the tool
        # rounds, the structured message is what the person receives.
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
        return calls

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
