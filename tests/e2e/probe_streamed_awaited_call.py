"""
Does the awaited call survive being sent as a stream? (`llm_stream_awaited_calls`)

The gate for the streamed path on a model: a structured call (forced tool on
Claude 5, JSON + structured output on 5.5), a thinking JSON call (the view
turn's shape) and a tool round must come back parsed through
`_stream_to_message`, with usage recorded, in about the time the whole-body
call takes. Run it before trusting the default on a model not listed here.
Whether streaming pays was measured on the app's promise run, not here.

    poetry run pytest tests/e2e/probe_streamed_awaited_call.py --real-llm -s
"""

from __future__ import annotations

import time

import pytest
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.settings_context import using_settings
from dialectical_framework.utils.call_census import call_census
from e2e.modelctx import using_model

MODELS = [
    "bedrock/global.anthropic.claude-sonnet-5-5",
    "bedrock/global.anthropic.claude-sonnet-5",
]


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class Pair(BaseModel):
    thesis: str = Field(description="A position someone might hold, in a few words")
    antithesis: str = Field(description="A genuine opposing position, in a few words")


class Reply(BaseModel):
    message: str


@llm.tool
async def word_count(text: str) -> int:
    """Counts the words in a text."""
    return len(text.split())


async def _three_shapes(model: str) -> list[str]:
    seen = []
    with call_census() as census:
        plain = await ConversationFacilitator().submit(
            Pair, "Give one tension about remote work."
        )
        seen.append(f"plain: {plain.thesis!r} / {plain.antithesis!r}")
        thinking = await ConversationFacilitator(
            format_mode="json", thinking="low"
        ).submit(Pair, "Give one tension about parenting.")
        seen.append(f"thinking: {thinking.thesis!r}")
        tools = ConversationFacilitator(tools=[word_count])
        reply = await tools.submit(
            Reply,
            "Use the tool to count the words in 'the quick brown fox', then say the number.",
        )
        assert tools.last_tool_calls, "the tool round never ran"
        seen.append(f"tools: {reply.message[:80]!r}")
    assert census.calls, "no call recorded"
    assert all(c.uncached_input_tokens is not None or c.cache_read_tokens is not None
               for c in census.calls), "usage lost in assembly"
    return seen


@pytest.mark.real_llm
@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("arm", [True, False], ids=["streamed", "whole"])
async def test_the_awaited_call_survives_streaming(di_container, model, arm, monkeypatch):
    from dialectical_framework.utils import bedrock_provider

    streamed_calls = []
    original = bedrock_provider._stream_to_message

    async def counting(*args, **kwargs):
        streamed_calls.append(args[1])
        return await original(*args, **kwargs)

    monkeypatch.setattr(bedrock_provider, "_stream_to_message", counting)
    streamed = di_container.settings().model_copy(update={"llm_stream_awaited_calls": arm})
    started = time.monotonic()
    with using_settings(streamed), using_model(di_container, model):
        for line in await _three_shapes(model):
            print(model, line)
    print(model, "streamed" if arm else "whole", f"{time.monotonic() - started:.1f}s")
    # plain + thinking + the tool round and its final answer
    if arm:
        assert len(streamed_calls) >= 4, streamed_calls
    else:
        assert not streamed_calls
