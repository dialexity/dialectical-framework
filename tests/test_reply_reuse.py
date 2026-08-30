"""A finished reply is not re-generated: the tools call's own text IS the answer.

With tools wired, every turn used to cost TWO provider round-trips — the tools
call that wrote the reply, and a second structured call that restated that same
reply inside a one-field envelope. It ran even when the model requested no tools
at all, because the loop simply breaks and falls through. On a median 18.55s
reply path that second round was roughly half the wait, and it also put the
reply into history twice.

So the common turn now builds `ChatResponse` from the text the model already
wrote. These tests pin both halves of that: WHEN it reuses (and that nothing
calls the provider a second time), and — more important — the four cases where
it must decline and let the structured call run, because a shortcut that fires
on a half-finished turn hands the person a truncated thought.

`TestTheStreamingContract` pins the consequence a host renders against: on the
streaming path the reply is built from the DELTAS that were yielded, so
`ResponseComplete.streamed` promises that `message` is those exact bytes. A host
that trusts it starts drawing at first-token latency instead of waiting out the
turn; a host that cannot trust it has no choice but to wait, which is the whole
~18s.
"""

from __future__ import annotations

import pytest
from mirascope import llm
from pydantic import BaseModel

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import (ResponseComplete,
                                                       TextDelta, ToolResult,
                                                       ToolStart)


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _Chat(BaseModel):
    """The shape all three agents' `ChatResponse` has."""

    message: str


class _RicherDto(BaseModel):
    message: str
    confidence: float


class _NotAReply(BaseModel):
    finding: str


class _OptionalReply(BaseModel):
    message: str = ""


class _FakeToolCall:
    name = "anchor"
    args = "{}"
    id = "tc-1"


class _FakeResponse:
    """The parts of an `AsyncResponse` the reuse gate reads."""

    def __init__(self, text: str, messages: list, tool_calls: list | None = None):
        self._text = text
        self.messages = list(messages)
        self.tool_calls = list(tool_calls or [])

    def text(self, sep: str = "\n") -> str:
        return self._text


class _TextlessResponse:
    """A response object with no `text` at all — several suite fakes are this."""

    def __init__(self, messages: list):
        self.messages = list(messages)
        self.tool_calls: list = []


def _facilitator() -> ConversationFacilitator:
    facilitator = ConversationFacilitator()
    # The tool path is selected by `self._tools` being non-empty and nothing
    # else; the calls that would use the tools are replaced below.
    facilitator._tools = [object()]
    return facilitator


def _assistant(text: str):
    return llm.messages.assistant(text, model_id=None, provider_id=None)


@pytest.fixture
def extraction_calls(monkeypatch) -> list:
    """Count the structured calls, and keep the fallback answerable."""
    seen: list = []

    async def counted(self, response_model):
        seen.append(response_model)
        return response_model(**{"message": "extracted"}) \
            if "message" in response_model.model_fields else response_model()

    monkeypatch.setattr(
        ConversationFacilitator, "_call_with_response_model", counted
    )
    return seen


class TestTheGate:
    """`_reuse_written_reply` in isolation — one refusal reason per test."""

    def test_a_finished_plain_reply_is_reused(self):
        response = _FakeResponse("Here is what I think.", [])
        result = _facilitator()._reuse_written_reply(response, _Chat)
        assert isinstance(result, _Chat)
        assert result.message == "Here is what I think."

    def test_pending_tool_calls_decline(self):
        """The budget-exhaustion exit. The loop ended because it ran out of
        rounds, not because the model finished, so this text is mid-work — and
        `_close_dangling_tool_calls` has just appended a synthetic user turn,
        so reusing here would leave history on two adjacent user messages."""
        response = _FakeResponse("Let me check the graph—", [], [_FakeToolCall()])
        assert _facilitator()._reuse_written_reply(response, _Chat) is None

    def test_a_richer_model_declines(self):
        """`submit` is generic. A second field is extraction work that prose
        cannot stand in for."""
        response = _FakeResponse("Here is what I think.", [])
        assert _facilitator()._reuse_written_reply(response, _RicherDto) is None

    def test_a_model_without_a_message_field_declines(self):
        response = _FakeResponse("Here is what I think.", [])
        assert _facilitator()._reuse_written_reply(response, _NotAReply) is None

    def test_an_optional_message_declines(self):
        """A defaulted field says the caller expects the model to be able to
        omit it — that is not the plain-reply contract."""
        response = _FakeResponse("Here is what I think.", [])
        assert _facilitator()._reuse_written_reply(response, _OptionalReply) is None

    def test_empty_text_declines(self):
        """A thinking-only or tool-only response. Reusing would deliver an
        empty reply, which is worse than paying for the extraction call."""
        for empty in ("", "   \n  "):
            response = _FakeResponse(empty, [])
            assert _facilitator()._reuse_written_reply(response, _Chat) is None

    def test_a_response_with_no_text_attribute_declines_instead_of_raising(self):
        response = _TextlessResponse([])
        assert _facilitator()._reuse_written_reply(response, _Chat) is None

    def test_a_text_that_raises_declines_instead_of_raising(self):
        class _Angry:
            messages: list = []
            tool_calls: list = []

            def text(self, sep: str = "\n"):
                raise RuntimeError("no text on this shape")

        assert _facilitator()._reuse_written_reply(_Angry(), _Chat) is None

    def test_text_as_a_plain_string_attribute_is_read_too(self):
        """Not how mirascope shapes it (`text` is a method), but several test
        fakes and some provider wrappers expose a bare string."""

        class _Stringy:
            messages: list = []
            tool_calls: list = []
            text = "Here is what I think."

        result = _facilitator()._reuse_written_reply(_Stringy(), _Chat)
        assert result is not None and result.message == "Here is what I think."


class TestThroughSubmit:
    @pytest.mark.llm
    async def test_a_finished_turn_makes_no_second_call(
        self, monkeypatch, extraction_calls
    ):
        facilitator = _facilitator()

        async def fake_tools_call(self):
            return _FakeResponse(
                "The buyout is the cheaper mistake.",
                [*self._messages, _assistant("The buyout is the cheaper mistake.")],
            )

        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_tools", fake_tools_call
        )

        result = await facilitator.submit(_Chat, "what should I do?")

        assert result.message == "The buyout is the cheaper mistake."
        assert extraction_calls == [], "the reply was already written"

    @pytest.mark.llm
    async def test_the_reply_lands_in_history_exactly_once(self, monkeypatch,
                                                           extraction_calls):
        """The old shape appended it twice — once from the response chain, once
        from the extraction call — so the provider replayed two adjacent,
        near-identical assistant turns every turn thereafter."""
        facilitator = _facilitator()
        reply = "One thing at a time."

        async def fake_tools_call(self):
            return _FakeResponse(reply, [*self._messages, _assistant(reply)])

        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_tools", fake_tools_call
        )

        await facilitator.submit(_Chat, "where do I start?")

        assistants = [m for m in facilitator._messages if m.role == "assistant"]
        assert len(assistants) == 1

    @pytest.mark.llm
    async def test_an_unusable_response_still_falls_back(self, monkeypatch,
                                                         extraction_calls):
        """The structured call stays a LIVE path, not dead code."""
        facilitator = _facilitator()

        async def fake_tools_call(self):
            return _FakeResponse("", [*self._messages, _assistant("")])

        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_tools", fake_tools_call
        )

        result = await facilitator.submit(_Chat, "hello?")

        assert result.message == "extracted"
        assert extraction_calls == [_Chat]


def _chunks(text: str, size: int = 7) -> list[str]:
    """Split into arbitrary pieces, the way a provider does — not on words."""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


class _FakeStream:
    """Enough of an `AsyncStreamResponse` for the reply path.

    `own_text` defaults to the streamed text but can be set to something else,
    which is how a test proves the reply is built from the DELTAS rather than
    re-read from the response object.
    """

    def __init__(
        self,
        text: str,
        messages: list,
        tool_calls: list | None = None,
        next_stream: "_FakeStream | None" = None,
        own_text: str | None = None,
    ):
        self._text = text
        self._own_text = own_text if own_text is not None else text
        self.messages = list(messages)
        self.tool_calls = list(tool_calls or [])
        self._next = next_stream

    async def chunk_stream(self):
        for piece in _chunks(self._text):
            # No `id=` — `TextChunk` rejects it, and a `TypeError` raised in
            # here does not surface: langfuse's `@observe()` async-generator
            # wrapper catches `TypeError` around its own `create_task` call (a
            # 3.10 fallback) and retries `__anext__` on the already-failed
            # generator, so the stream just ENDS. This test silently saw zero
            # events instead of an error.
            yield llm.TextChunk(delta=piece)

    async def execute_tools(self):
        return []

    async def resume(self, outputs):
        assert self._next is not None, "resumed a stream with nothing to resume to"
        return self._next

    def text(self, sep: str = "\n") -> str:
        return self._own_text


class TestThroughSubmitStream:
    @pytest.mark.llm
    async def test_the_streamed_turn_reuses_its_own_text(self, monkeypatch,
                                                         extraction_calls):
        """Worth its own test: what this skips re-generating is exactly the
        text already delivered to the consumer as `TextDelta`s."""
        facilitator = _facilitator()
        reply = "Buy him out before the raise."

        async def fake_open(self, max_attempts: int = 3):
            return _FakeStream(reply, [*self._messages, _assistant(reply)])

        monkeypatch.setattr(
            ConversationFacilitator, "_open_stream_with_retry", fake_open
        )

        events = [e async for e in facilitator.submit_stream(_Chat, "well?")]

        deltas = "".join(e.text for e in events if isinstance(e, TextDelta))
        complete = [e for e in events if isinstance(e, ResponseComplete)]
        assert len(complete) == 1
        assert complete[0].result.message == reply
        assert deltas == reply, "the deltas and the reply agree"
        assert extraction_calls == []


class TestTheStreamingContract:
    """`ResponseComplete.streamed` is a promise a host renders against.

    A host cannot see the reply until this event unless it can trust the
    deltas, and it cannot trust them unless the framework guarantees they are
    the same bytes. Waiting instead costs the person the whole turn — ~18s
    measured — for text that started arriving in about a second.
    """

    @staticmethod
    def _run(monkeypatch, first: _FakeStream):
        async def fake_open(self, max_attempts: int = 3):
            return first

        monkeypatch.setattr(
            ConversationFacilitator, "_open_stream_with_retry", fake_open
        )
        return _facilitator()

    @pytest.mark.llm
    async def test_the_reply_is_exactly_the_bytes_the_person_saw(
        self, monkeypatch, extraction_calls
    ):
        """Byte-for-byte, not word-for-word: a host that appends deltas and
        then persists `message` must not find a whitespace or punctuation
        difference between what it drew and what it stored."""
        reply = "Two things are true at once:\n\n- the cash is real\n- so is the relationship."
        facilitator = self._run(
            monkeypatch, _FakeStream(reply, [_assistant(reply)])
        )

        events = [e async for e in facilitator.submit_stream(_Chat, "well?")]

        deltas = "".join(e.text for e in events if isinstance(e, TextDelta))
        complete = [e for e in events if isinstance(e, ResponseComplete)][0]
        assert complete.streamed is True
        assert deltas == complete.result.message == reply
        assert extraction_calls == []

    @pytest.mark.llm
    async def test_the_reply_is_built_from_the_deltas_not_re_read(
        self, monkeypatch, extraction_calls
    ):
        """The response object's own `text()` is a SECOND construction of the
        same prose — mirascope joins its text parts with a separator the deltas
        never carried. Building from the deltas is what makes the promise hold
        without reasoning about provider chunk shapes; this test would pass
        either way if the two agreed, so it makes them disagree."""
        streamed = "This is what you saw."
        facilitator = self._run(
            monkeypatch,
            _FakeStream(
                streamed, [_assistant(streamed)], own_text="SOMETHING ELSE ENTIRELY"
            ),
        )

        events = [e async for e in facilitator.submit_stream(_Chat, "well?")]

        complete = [e for e in events if isinstance(e, ResponseComplete)][0]
        assert complete.result.message == streamed

    @pytest.mark.llm
    async def test_text_before_a_tool_call_is_not_the_reply(
        self, monkeypatch, extraction_calls
    ):
        """The model narrating what it is about to do is progress, not counsel.
        A host may leave it on screen; persisting it as the reply would file
        "let me look at what you've told me" as advice."""
        preamble = "Let me look at what you've told me so far."
        answer = "Buy him out, but not before the raise closes."
        second = _FakeStream(answer, [_assistant(answer)])
        first = _FakeStream(
            preamble,
            [_assistant(preamble)],
            tool_calls=[_FakeToolCall()],
            next_stream=second,
        )
        facilitator = self._run(monkeypatch, first)

        events = [e async for e in facilitator.submit_stream(_Chat, "well?")]

        complete = [e for e in events if isinstance(e, ResponseComplete)][0]
        assert complete.streamed is True
        assert complete.result.message == answer
        assert preamble not in complete.result.message

        # And the promise is scoped exactly as documented: the deltas AFTER the
        # last tool result are the reply, the ones before it are not.
        index = max(
            i for i, e in enumerate(events) if isinstance(e, (ToolStart, ToolResult))
        )
        after = "".join(
            e.text for e in events[index:] if isinstance(e, TextDelta)
        )
        assert after == answer
        before = "".join(
            e.text for e in events[:index] if isinstance(e, TextDelta)
        )
        assert before == preamble

    @pytest.mark.llm
    async def test_an_unusable_turn_does_not_claim_to_have_streamed(
        self, monkeypatch, extraction_calls
    ):
        """`streamed=False` is the host's instruction to render `message`
        itself. Getting this wrong in the other direction is the bad one: the
        person would be left with whatever partial text was on screen."""
        facilitator = self._run(monkeypatch, _FakeStream("", [_assistant("")]))

        events = [e async for e in facilitator.submit_stream(_Chat, "well?")]

        complete = [e for e in events if isinstance(e, ResponseComplete)][0]
        assert complete.streamed is False
        assert complete.result.message == "extracted"
        assert extraction_calls == [_Chat]

    @pytest.mark.llm
    async def test_the_tool_free_path_does_not_claim_to_have_streamed(
        self, extraction_calls
    ):
        """It cannot stream: one formatted call, nothing to yield until it
        returns. A known gap rather than a design — an agent with no tools gets
        no first-token benefit at all."""
        facilitator = ConversationFacilitator()  # no tools

        events = [e async for e in facilitator.submit_stream(_Chat, "well?")]

        assert not [e for e in events if isinstance(e, TextDelta)]
        complete = [e for e in events if isinstance(e, ResponseComplete)][0]
        assert complete.streamed is False
        assert complete.result.message == "extracted"

    def test_the_flag_defaults_to_false(self):
        """Every other producer of this event — mocks, hosts, older callers —
        must default to "render it yourself", the safe direction."""
        assert ResponseComplete(result=_Chat(message="hi")).streamed is False
