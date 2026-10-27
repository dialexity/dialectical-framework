"""
The raw text of a structured reply is kept for the host.

A DTO that validates can still carry a field the model cut mid-word and
continued in the next one: the first app's handoff of 2026-10-27 (one
Lithuanian card of two on the native transport) had `paragraph` end
mid-word and `parallel` begin with its missing tail. That reply is VALID JSON
under the schema constraint — the API rejects string length constraints and
the SDK strips them, so the boundary is where the model put the closing quote
— and no parse can see it. The framework does not guess at content; it keeps
the bytes: `use_brain` records every parsed structured reply as written
(`last_structured_reply_text()`, a DEBUG line in full) and the facilitator
copies it onto `last_structured_reply_text` for the host's own check to read.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from mirascope.llm.exceptions import ParseError
from pydantic import BaseModel

from dialectical_framework.agents import conversation_facilitator as cf_module
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.utils import use_brain as use_brain_module

#: Captured at import, before the autouse mock brain replaces it per test, so
#: the facilitator test below can run the real seam.
_REAL_CALL_WITH_RESPONSE_MODEL = ConversationFacilitator._call_with_response_model


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class Dto(BaseModel):
    paragraph: str
    parallel: str


RAW = '{"paragraph": "Keturi sakiniai. Penkt", "parallel": "as nutrūko. There\'s a story"}'


def _response(raw: str = RAW) -> SimpleNamespace:
    def parse():
        # As Mirascope raises it: the ladder's salvage reads `ParseError`.
        try:
            return Dto.model_validate_json(raw)
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Failed to parse response: {e}", original_exception=e) from e

    return SimpleNamespace(
        parse=parse,
        text=lambda sep="": raw,
        texts=[raw],
        finish_reason=None,
        usage=None,
    )


class TestUseBrainKeepsTheReplyAsWritten:
    @pytest.fixture(autouse=True)
    def mock_llm(self):
        """Opt out of the mock brain: the decorator under test is the real one;
        `llm.call` is monkeypatched so nothing is sent."""
        yield

    def _decorated(self, response, monkeypatch):
        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    return response

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)

        @use_brain_module.use_brain(ai_model="anthropic/claude-x", format=Dto)
        async def _method():
            return None

        return _method

    async def test_the_parsed_reply_is_kept_and_logged_in_full(self, monkeypatch, caplog):
        method = self._decorated(_response(), monkeypatch)
        with caplog.at_level(logging.DEBUG, logger="dialectical_framework.utils.use_brain"):
            dto = await method()
        assert dto.paragraph == "Keturi sakiniai. Penkt"
        assert use_brain_module.last_structured_reply_text() == RAW
        line = next(r for r in caplog.records if "as written" in r.getMessage())
        assert "Dto" in line.getMessage() and RAW in line.getMessage(), "whole, never clipped"

    async def test_a_salvaged_envelope_is_kept_as_written_too(self, monkeypatch):
        """The bytes are the ENVELOPE the model sent, not the unwrapped DTO."""
        wrapped = '{"result": ' + RAW + "}"
        method = self._decorated(_response(wrapped), monkeypatch)
        dto = await method()
        assert dto.parallel.startswith("as nutrūko")
        assert use_brain_module.last_structured_reply_text() == wrapped

    async def test_a_gathered_draw_never_overwrites_the_callers(self, monkeypatch):
        """Each draw of a best-of-N runs on its own task and sees its own."""
        import asyncio

        async def draw(raw):
            await self._decorated(_response(raw), monkeypatch)()
            return use_brain_module.last_structured_reply_text()

        other = RAW.replace("Penkt", "Šešt")
        seen = await asyncio.gather(draw(RAW), draw(other))
        assert seen == [RAW, other]
        assert use_brain_module.last_structured_reply_text() is None, "set in the child, not here"


class TestTheFacilitatorHandsItToTheHost:
    async def test_the_structured_call_copies_this_calls_text(self, monkeypatch):
        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_response_model", _REAL_CALL_WITH_RESPONSE_MODEL
        )

        def _fake_use_brain(*, format=None, **_kwargs):
            def decorator(method):
                async def wrapper(*args, **kw):
                    await method(*args, **kw)
                    use_brain_module._last_structured_reply.set(RAW)
                    return Dto.model_validate_json(RAW)

                return wrapper

            return decorator

        monkeypatch.setattr(cf_module, "use_brain", _fake_use_brain)
        facilitator = ConversationFacilitator()
        assert facilitator.last_structured_reply_text is None
        dto = await facilitator.submit(Dto, "Write the card.")
        assert dto.paragraph.endswith("Penkt")
        assert facilitator.last_structured_reply_text == RAW

    async def test_a_turn_without_a_structured_call_resets_it(self):
        """Under the mock brain no structured call runs: the previous turn's
        text must not be reported as this one's."""
        facilitator = ConversationFacilitator()
        facilitator.last_structured_reply_text = "stale"
        await facilitator.submit(Dto, "Again.")
        assert facilitator.last_structured_reply_text is None
