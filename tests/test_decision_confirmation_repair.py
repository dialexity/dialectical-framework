"""
The decision record is a user-driven artefact, so it cannot be elective.

Measured before this seam existed (`tests/bench/README.md`, "the ceremony is
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

    def __init__(self, tool_results=None, principal: str = "human") -> None:
        self._principal = principal

        class _Conv:
            last_tool_results = list(tool_results or [])

        self._conversation = _Conv()

    _repair_unrecorded_decision = Advisor._repair_unrecorded_decision
    _recorded_decision_this_turn = Advisor._recorded_decision_this_turn


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
    async def test_no_grounds_are_guessed(self, monkeypatch):
        """A fabricated accepted_cost invents the very confrontation the ledger
        reports. The repair secures existence; grounding stays the model's."""
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
