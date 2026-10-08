"""
A refusal (`stop_reason: "refusal"`) is the provider's answer, not a fault.

Before `ModelRefusal` a refusal reached the framework as an empty or cut-off
reply: a structured call re-asked it as a ParseError ten times, and a
conversational turn fell through to a second, structured call that was refused
again. Now the provider raises a typed error that no retry ladder catches, and
the facilitator drops the refused turn from history so the next turn is not
asked inside the context that was refused.
"""

from __future__ import annotations

import pytest
from anthropic.types import Message, RefusalStopDetails, TextBlock, Usage
from mirascope import llm
from pydantic import BaseModel

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.exceptions.provider_errors import ModelRefusal
from dialectical_framework.settings_context import using_settings
from dialectical_framework.utils.bedrock_provider import (
    BedrockAnthropicProvider,
    raise_on_refusal,
)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.fixture(autouse=True)
def mock_llm():
    """The real `use_brain` and facilitator: what is under test is how they
    treat the provider's answer, and each test fakes the provider itself."""
    yield


class SmallDto(BaseModel):
    word: str


def _message(stop_reason: str, *, details=None, text: str = "") -> Message:
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="global.anthropic.claude-sonnet-5-5",
        content=[TextBlock(type="text", text=text)] if text else [],
        stop_reason=stop_reason,
        stop_details=details,
        usage=Usage(input_tokens=10, output_tokens=0),
    )


class TestTheProviderRaises:
    def test_a_refusal_raises_with_its_category(self):
        details = RefusalStopDetails(type="refusal", category="cyber", explanation="Declined.")
        with pytest.raises(ModelRefusal) as caught:
            raise_on_refusal(_message("refusal", details=details), "m")
        assert caught.value.category == "cyber"
        assert caught.value.explanation == "Declined."
        assert caught.value.model == "m"

    def test_an_unnamed_category_is_none(self):
        with pytest.raises(ModelRefusal) as caught:
            raise_on_refusal(_message("refusal"), "m")
        assert caught.value.category is None

    @pytest.mark.parametrize("reason", ["end_turn", "tool_use", "max_tokens"])
    def test_other_stops_pass(self, reason):
        raise_on_refusal(_message(reason, text="ok"), "m")


@pytest.mark.asyncio
async def test_a_refused_structured_call_is_asked_once(di_container, monkeypatch):
    """Through `use_brain` and the real provider class: one request, no
    parse-retry ladder, the typed error out."""
    calls = []

    async def _refuse(self, kwargs, params):
        calls.append(kwargs)
        return _message("refusal")

    monkeypatch.setattr(BedrockAnthropicProvider, "_create_async", _refuse)
    settings = di_container.settings().model_copy(
        update={
            "ai_model": "bedrock/global.anthropic.claude-sonnet-5-5",
            "reasoning_model": None,
        }
    )
    from dialectical_framework.utils.use_brain import use_brain

    @use_brain(format=SmallDto)
    async def _ask():
        return [llm.messages.user("Something refused.")]

    with using_settings(settings):
        with pytest.raises(ModelRefusal):
            await _ask()
    assert len(calls) == 1


class TestTheRefusedTurnIsForgotten:
    def _facilitator_with_history(self):
        f = ConversationFacilitator()
        f._messages = [llm.messages.user("earlier"), llm.messages.assistant("reply", model_id=None, provider_id=None)]
        return f

    @pytest.mark.asyncio
    async def test_awaited_structured_path(self, monkeypatch):
        f = self._facilitator_with_history()
        before = list(f._messages)

        async def _refuse(response_model):
            raise ModelRefusal("m")

        monkeypatch.setattr(f, "_call_with_response_model", _refuse)
        with pytest.raises(ModelRefusal):
            await f.submit(SmallDto, "refused words")
        assert f._messages == before

    @pytest.mark.asyncio
    async def test_awaited_tool_path(self, monkeypatch):
        @llm.tool
        async def noop() -> str:
            """Does nothing."""
            return ""

        f = ConversationFacilitator(tools=[noop])
        before = list(f._messages)

        async def _refuse():
            raise ModelRefusal("m")

        monkeypatch.setattr(f, "_call_with_tools", _refuse)
        with pytest.raises(ModelRefusal):
            await f.submit(SmallDto, "refused words")
        assert f._messages == before

    @pytest.mark.asyncio
    async def test_streamed_path(self, monkeypatch):
        f = self._facilitator_with_history()
        before = list(f._messages)

        async def _refuse(response_model):
            raise ModelRefusal("m")

        monkeypatch.setattr(f, "_call_with_response_model", _refuse)
        with pytest.raises(ModelRefusal):
            async for _ in f.submit_stream(SmallDto, "refused words"):
                pass
        assert f._messages == before


def test_a_streamed_round_that_ends_on_refusal_raises():
    """Pinned on the source: the stream says so only in its finish reason,
    after its text was yielded, and nothing else in the loop reads it."""
    import inspect

    from dialectical_framework.agents import conversation_facilitator as cf

    src = inspect.getsource(cf.ConversationFacilitator._stream_turn)
    assert 'getattr(stream, "finish_reason", None) == FinishReason.REFUSAL' in src
    assert "raise ModelRefusal(" in src


class TestARefusalIsNeverAThrottle:
    """`ModelRefusal`'s message carries the provider's free-text explanation,
    and the throttle predicate matches "rate" + "limit" anywhere in a message
    ("generate" contains "rate") — so before the explicit exits a refusal
    could ride the ten-attempt throttle ladder (reviewer finding, reproduced)."""

    EXPLANATION = "Requests to generate malware fall outside the limits of acceptable use."

    def test_the_transient_classifier_files_it_nowhere(self):
        from dialectical_framework.utils.use_brain import _transient_kind

        assert _transient_kind(ModelRefusal("m", explanation=self.EXPLANATION)) is None

    @pytest.mark.asyncio
    async def test_the_ladder_asks_once(self, monkeypatch):
        from test_llm_transport_resilience import TestConnectionRetryLoop

        method, calls = TestConnectionRetryLoop._decorated(
            [ModelRefusal("m", category="cyber", explanation=self.EXPLANATION), "never"],
            monkeypatch,
        )
        with pytest.raises(ModelRefusal):
            await method()
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_any_providers_refused_response_raises(self, monkeypatch):
        """A provider that does not raise on a refusal itself (anything but
        `bedrock/`) still hands back `finish_reason == REFUSAL`."""
        from types import SimpleNamespace

        from mirascope.llm import FinishReason
        from test_llm_transport_resilience import TestConnectionRetryLoop

        refused = SimpleNamespace(finish_reason=FinishReason.REFUSAL, usage=None)
        method, calls = TestConnectionRetryLoop._decorated([refused, "never"], monkeypatch)
        with pytest.raises(ModelRefusal):
            await method()
        assert len(calls) == 1


class TestARefusalAfterToolRounds:
    """The paths the first tests did not reach: the refusal arrives on the
    round AFTER tools ran."""

    @pytest.mark.asyncio
    async def test_streamed_refusal_after_a_tool_round(self, monkeypatch):
        from mirascope.llm import FinishReason
        from test_reply_reuse import (_assistant, _Chat, _facilitator, _FakeStream,
                                      _FakeToolCall)

        from dialectical_framework.agents.stream_events import TextDelta

        class _Refused(_FakeStream):
            finish_reason = FinishReason.REFUSAL

        facilitator = _facilitator()
        before = list(facilitator._messages)
        second = _Refused("Partial answ", [_assistant("Partial answ")])
        first = _FakeStream(
            "Looking.", [_assistant("Looking.")], tool_calls=[_FakeToolCall()], next_stream=second
        )

        async def fake_open(self):
            return first

        monkeypatch.setattr(ConversationFacilitator, "_open_tools_stream", fake_open)
        seen = []
        with pytest.raises(ModelRefusal):
            async for event in facilitator.submit_stream(_Chat, "refused words"):
                seen.append(event)
        deltas = "".join(e.text for e in seen if isinstance(e, TextDelta))
        assert "Partial answ" in deltas, "the text before the refusal was yielded"
        assert facilitator._messages == before
        assert facilitator.last_tool_calls == ["anchor"], "the tool that ran is still reported"

    @pytest.mark.asyncio
    async def test_awaited_refusal_on_the_resume(self, monkeypatch):
        from mirascope.llm import FinishReason
        from test_reply_reuse import _assistant, _Chat, _facilitator, _FakeStream, _FakeToolCall

        class _Refused(_FakeStream):
            finish_reason = FinishReason.REFUSAL
            model_id = "bedrock/x"

        facilitator = _facilitator()
        before = list(facilitator._messages)
        second = _Refused("", [_assistant("")])
        first = _FakeStream("", [_assistant("")], tool_calls=[_FakeToolCall()], next_stream=second)

        async def fake_call():
            return first

        monkeypatch.setattr(facilitator, "_call_with_tools", fake_call)
        with pytest.raises(ModelRefusal):
            await facilitator.submit(_Chat, "refused words")
        assert facilitator._messages == before


class TestTheAdvisorFollowsUpWhatTheToolsWrote:
    """A refusal on the resume after `record_decision` ran: the Decision is in
    the graph, so the seam's MODEL_RECORDED branch (which schedules the
    pathway weave) must still run, and the noted tensions must be offered."""

    @pytest.mark.asyncio
    async def test_a_recorded_decision_still_gets_its_seam(self):
        from types import SimpleNamespace

        from dialectical_framework.agents.advisor.advisor import Advisor

        calls = []

        async def repair(user_message, reply):
            calls.append(("repair", user_message, reply))

        fake = SimpleNamespace(
            _recorded_decision_this_turn=lambda: True,
            _repair_unrecorded_decision=repair,
            _schedule_noted_tensions=lambda: calls.append(("notes",)),
        )
        await Advisor._settle_refused_turn(fake, "we decided")
        assert calls == [("repair", "we decided", ""), ("notes",)]

    @pytest.mark.asyncio
    async def test_no_decision_means_no_classifier_on_a_refused_turn(self):
        from types import SimpleNamespace

        from dialectical_framework.agents.advisor.advisor import Advisor

        calls = []

        async def repair(*_):
            calls.append("repair")

        fake = SimpleNamespace(
            _recorded_decision_this_turn=lambda: False,
            _repair_unrecorded_decision=repair,
            _schedule_noted_tensions=lambda: calls.append("notes"),
        )
        await Advisor._settle_refused_turn(fake, "words")
        assert calls == ["notes"]

    def test_both_turn_loops_settle_before_re_raising(self):
        import inspect

        from dialectical_framework.agents.advisor.advisor import Advisor

        for loop in (Advisor.chat, Advisor.chat_stream):
            src = inspect.getsource(loop)
            assert "except ModelRefusal:" in src
            assert "await self._settle_refused_turn(user_message)" in src
