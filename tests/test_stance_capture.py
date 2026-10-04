"""The intake gate: a stance or ONE question, never both, never prose.

DB-free: the gate touches no graph."""

from __future__ import annotations

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.stance_capture import (
    FORK_ASK, MAX_INTAKE_ASKS, NO_STANCE_ASK, SYSTEM_PROMPT, StanceCapture,
    StanceCaptureDto)
from dialectical_framework.concerns.view_sketch import THESIS_IS_A_STANCE

pytestmark = [pytest.mark.llm]


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _answering(monkeypatch, dto: StanceCaptureDto) -> list[str]:
    seen: list[str] = []

    async def fake(self, response_model, user_content, **kwargs):
        seen.append(user_content)
        return dto

    monkeypatch.setattr(ConversationFacilitator, "submit", fake)
    return seen


class TestExclusivityIsEnforcedInCode:
    @pytest.mark.asyncio
    async def test_a_stance_drops_any_ask_the_model_also_wrote(self, monkeypatch):
        _answering(monkeypatch, StanceCaptureDto(shape="stance", stance="I should stop paying for his phone", ask="Which way?"))
        got = await StanceCapture().resolve(["Why should I keep paying for his phone when he never calls?"])
        assert got.found and got.stance == "I should stop paying for his phone"
        assert got.ask is None

    @pytest.mark.asyncio
    async def test_a_fork_asks_the_models_question_or_the_gates_own(self, monkeypatch):
        _answering(monkeypatch, StanceCaptureDto(shape="fork", stance="", ask="Zurich or Vilnius — which pulls harder?"))
        got = await StanceCapture().resolve(["Zurich or Vilnius?"])
        assert not got.found and got.ask == "Zurich or Vilnius — which pulls harder?"
        _answering(monkeypatch, StanceCaptureDto(shape="fork", stance="", ask="  "))
        got = await StanceCapture().resolve(["Zurich or Vilnius?"])
        assert got.ask == FORK_ASK and got.shape == "fork"

    @pytest.mark.asyncio
    async def test_a_stance_shape_with_a_blank_line_is_none_not_a_blank_build(self, monkeypatch):
        _answering(monkeypatch, StanceCaptureDto(shape="stance", stance="   ", ask=""))
        got = await StanceCapture().resolve(["What is dialectical thinking?"])
        assert not got.found and got.shape == "none" and got.ask == NO_STANCE_ASK

    @pytest.mark.asyncio
    async def test_a_stance_written_under_the_wrong_shape_is_not_built_on(self, monkeypatch):
        """The shape decides; a line in the wrong slot is not a stance."""
        _answering(monkeypatch, StanceCaptureDto(shape="none", stance="I should learn Spanish", ask=""))
        got = await StanceCapture().resolve(["What's the best way to learn Spanish?"])
        assert not got.found and got.ask == NO_STANCE_ASK

    @pytest.mark.asyncio
    async def test_nothing_typed_asks_without_a_call(self, monkeypatch):
        seen = _answering(monkeypatch, StanceCaptureDto(shape="stance", stance="x", ask=""))
        got = await StanceCapture().resolve(["", "   "])
        assert seen == [] and got.ask == NO_STANCE_ASK


class TestThePrompt:
    def test_the_gate_and_the_writers_share_one_notion_of_a_stance(self):
        assert THESIS_IS_A_STANCE in SYSTEM_PROMPT

    def test_the_asks_carry_no_framework_vocabulary(self):
        for text in (FORK_ASK, NO_STANCE_ASK):
            for word in ("thesis", "antithesis", "tetrad", "T+", "A+", "dialectic"):
                assert word.lower() not in text.lower(), (word, text)

    @pytest.mark.asyncio
    async def test_the_turns_are_sent_in_order_with_the_answers_marked(self, monkeypatch):
        seen = _answering(monkeypatch, StanceCaptureDto(shape="stance", stance="Take Zurich", ask=""))
        await StanceCapture().resolve(["Zurich or Vilnius?", "Zurich, if I'm honest."])
        assert '1. "Zurich or Vilnius?"' in seen[0] and '2. "Zurich, if I\'m honest."' in seen[0]
        assert "answer the questions asked in between" in seen[0]

    def test_the_cap_is_a_policy_constant(self):
        assert MAX_INTAKE_ASKS == 2


class TestTheMockedPath:
    @pytest.mark.asyncio
    async def test_the_default_mock_yields_a_decision(self):
        """`Literal` order matters for the mock: 'stance' first, so a mocked
        gate lets the build run instead of blocking on a question."""
        got = await StanceCapture().resolve(["I should quit my job."])
        assert got.found or got.ask
