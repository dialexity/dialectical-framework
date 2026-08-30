"""
The structured-extraction step must not speak as the person.

`_call_with_response_model` appends a user-role message before the extraction
call, because Bedrock rejects a conversation that ends on an assistant turn.
That slot is the ONLY place the framework writes human-readable prose in the
user role, and the old wording ("Provide your structured response.") was read
by the model as the person's own words — then reasoned about as their motive:

    I asked: *Can you say that's the price you're taking on?*
    You answered: *Provide your structured response.*
    That's a deflection, and I'm not going to record a decision on a deflection.

Measured across four bench runs (r7, r10, r11, r14): 8 turns, all in the
tools-wired arm — the prompt-only arms never reach this call at all, so 0 of
944 of their turns show it. The worst instance answered emotional pushback with
a numbered menu of internal operations ("the 'provide structured response'
signal tells me you want more than conversation") and scored 1/5 on the judge's
cross-turn coherence dimension, the lowest cell in that run.

Only the framing changes here: the message declares itself machinery, disclaims
the person, and forbids referring to itself. The call itself is now the FALLBACK
(`_reuse_written_reply` answers the common turn from the text the model already
wrote), so what still reaches this wording are the turns already going badly —
budget exhausted, no usable text. The framing matters more there, not less.

These tests call the real `_call_with_response_model` directly and so are
unaffected by that shortcut, on purpose: they are about this call's behaviour
whenever it runs.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from dialectical_framework.agents import conversation_facilitator as cf_mod
from dialectical_framework.agents.conversation_facilitator import (
    _EXTRACTION_REQUEST, ConversationFacilitator)

# Captured at import (collection) time, BEFORE the autouse `mock_llm` fixture
# replaces it with a stub — these tests are about the real method's behaviour.
_REAL_CALL = ConversationFacilitator._call_with_response_model


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _Chat(BaseModel):
    message: str


def _message_text(message) -> str:
    content = message.content
    parts = list(content) if isinstance(content, (list, tuple)) else [content]
    out = []
    for part in parts:
        if isinstance(part, str):
            out.append(part)
        else:
            out.append(getattr(part, "text", "") or "")
    return "\n".join(out)


@pytest.fixture
def captured(monkeypatch) -> list:
    """Intercept the extraction call and keep the messages it would send."""
    seen: list = []

    def fake_use_brain(*, format=None, **kwargs):
        def decorator(method):
            async def wrapper(*args, **kwargs):
                # Snapshot: on the no-injection path the returned list IS
                # `self._messages`, which the caller then appends to.
                seen.append(list(await method(*args, **kwargs)))
                return format(message="ok")

            return wrapper

        return decorator

    monkeypatch.setattr(cf_mod, "use_brain", fake_use_brain)
    return seen


class TestExtractionRequestWording:
    """Properties of the constant itself — cheap, and they pin the intent."""

    def test_it_disclaims_the_person(self):
        """The whole defect was misattribution, so it must say outright that
        the person did not write it."""
        lowered = _EXTRACTION_REQUEST.lower()
        assert "the person did not write this" in lowered
        assert "not a message from the person" in lowered

    def test_it_forbids_mentioning_itself(self):
        """A model that merely knows the truth still leaked the phrase into
        the reply ('the provide structured response signal tells me...')."""
        lowered = _EXTRACTION_REQUEST.lower()
        assert "never refer to this notice" in lowered
        assert "structured responses" in lowered

    def test_it_is_not_bare_prose_the_person_could_have_said(self):
        """The regression guard: the old value was a plausible human sentence.
        This one opens with an explicit machinery marker."""
        assert _EXTRACTION_REQUEST.startswith("[FRAMEWORK NOTICE")
        assert _EXTRACTION_REQUEST.strip() != "Provide your structured response."

    def test_it_still_asks_for_the_structured_format(self):
        """The caller parses the result into `ChatResponse` — reframing must
        not lose the ask."""
        assert "structured format" in _EXTRACTION_REQUEST.lower()


class TestExtractionRequestInjection:
    @pytest.mark.llm
    async def test_assistant_ending_history_gets_the_notice(self, captured):
        """The Bedrock constraint is real, so the injection must still happen."""
        facilitator = ConversationFacilitator()
        facilitator.add_user_message("what should I do about the buyout?")
        facilitator._messages.append(
            cf_mod.llm.messages.assistant(
                "Here is what I think.", model_id=None, provider_id=None
            )
        )

        await _REAL_CALL(facilitator, _Chat)

        sent = captured[-1]
        assert sent[-1].role == "user"
        assert _message_text(sent[-1]) == _EXTRACTION_REQUEST

    @pytest.mark.llm
    async def test_the_notice_is_not_persisted_into_history(self, captured):
        """It is a per-call artefact. Persisting it would replay a fake user
        turn on every later turn, compounding the misattribution."""
        facilitator = ConversationFacilitator()
        facilitator.add_user_message("hello")
        facilitator._messages.append(
            cf_mod.llm.messages.assistant("hi", model_id=None, provider_id=None)
        )

        await _REAL_CALL(facilitator, _Chat)

        texts = [_message_text(m) for m in facilitator._messages]
        assert _EXTRACTION_REQUEST not in texts
        assert not any("structured" in t.lower() for t in texts)

    @pytest.mark.llm
    async def test_user_ending_history_is_left_alone(self, captured):
        """The no-tools path already ends on the person's real message; adding
        anything there would put words in their mouth for no reason."""
        facilitator = ConversationFacilitator()
        facilitator.add_user_message("what should I do?")

        await _REAL_CALL(facilitator, _Chat)

        sent = captured[-1]
        assert _message_text(sent[-1]) == "what should I do?"

    @pytest.mark.llm
    async def test_the_structured_result_still_comes_back(self, captured):
        """The reason the call exists at all: the caller needs the object,
        and on this path there is no already-written reply to reuse."""
        facilitator = ConversationFacilitator()
        facilitator.add_user_message("hello")
        facilitator._messages.append(
            cf_mod.llm.messages.assistant("hi", model_id=None, provider_id=None)
        )

        result = await _REAL_CALL(facilitator, _Chat)

        assert isinstance(result, _Chat)
        assert result.message == "ok"
