"""
probe_claude_5_5_compat — which request shapes do the 5.5 models accept?

Reported 2026-10-08 (handoff): on Bedrock, Sonnet 5.5 and Opus 5.5 reject two
shapes the framework sends by default — forced tool use (Mirascope's default
structured format) and `thinking: {"type": "disabled"}` (what
`with_thinking_compat` sends for an unset level inside a conversational round).
This probe sends each shape RAW, straight to the Bedrock client with no
compatibility layer in between, and prints the provider's verdict per model, so
`format_compat` / `thinking_compat` are written against the provider's own error
texts rather than a paraphrase of them. Then it runs the framework's own two
paths (`submit(Dto)` and `_call_with_tools` with thinking off) through the fixed
layers.

NOT free, but small: ~6 tiny calls per model.

    DIALEXITY_PROBE_MODELS="global.anthropic.claude-sonnet-5,global.anthropic.claude-sonnet-5-5,global.anthropic.claude-opus-5-5" \
        poetry run pytest tests/e2e/probe_claude_5_5_compat.py --real-llm -s
"""

from __future__ import annotations

import os

import pytest
from anthropic import AsyncAnthropicBedrock
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.settings_context import using_settings
from dialectical_framework.utils.call_census import call_census

MODELS = [
    m.strip()
    for m in os.getenv(
        "DIALEXITY_PROBE_MODELS",
        "global.anthropic.claude-sonnet-5,"
        "global.anthropic.claude-sonnet-5-5,"
        "global.anthropic.claude-opus-5-5",
    ).split(",")
    if m.strip()
]

_TOOL = {
    "name": "answer",
    "description": "Give the answer.",
    "input_schema": {
        "type": "object",
        "properties": {"word": {"type": "string"}},
        "required": ["word"],
    },
}

RAW_SHAPES = {
    "plain": {},
    "tool_choice tool": {"tools": [_TOOL], "tool_choice": {"type": "tool", "name": "answer"}},
    "tool_choice any": {"tools": [_TOOL], "tool_choice": {"type": "any"}},
    "thinking disabled": {"thinking": {"type": "disabled"}},
    "thinking between_tools": {"thinking": {"type": "between_tools"}},
    "adaptive + effort low": {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
    },
}


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class SmallDto(BaseModel):
    word: str = Field(description="One word")


class ReplyDto(BaseModel):
    message: str = Field(description="The reply")


@llm.tool
async def look_up_colour() -> str:
    """Returns a colour, if one is needed."""
    return "teal"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_raw_shapes():
    client = AsyncAnthropicBedrock()
    for model in MODELS:
        print(f"\n== {model}")
        for name, extra in RAW_SHAPES.items():
            try:
                r = await client.messages.create(
                    model=model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": "Name a colour in one word."}],
                    **extra,
                )
                kinds = [b.type for b in r.content]
                print(f"  {name:24s} OK   stop={r.stop_reason} blocks={kinds}")
            except Exception as e:  # noqa: BLE001
                print(f"  {name:24s} FAIL {type(e).__name__}: {str(e)[:300]}")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_framework_paths(di_container):
    for model in MODELS:
        print(f"\n== {model} (framework paths)")
        settings = di_container.settings().model_copy(
            update={"ai_model": f"bedrock/{model}", "reasoning_model": None}
        )
        with using_settings(settings):
            try:
                with call_census() as census:
                    out = await ConversationFacilitator().submit(
                        SmallDto, "Name a colour in one word."
                    )
                # Output tokens tell a thinking structured call from one that
                # does not: a one-word DTO is ~10-20 tokens without thinking.
                tokens = [c.output_tokens for c in census.calls]
                print(f"  {'submit(SmallDto)':34s} OK   {out!r} output_tokens={tokens}")
            except Exception as e:  # noqa: BLE001
                print(f"  {'submit(SmallDto)':34s} FAIL {type(e).__name__}: {str(e)[:300]}")
            for level in (None, "low", "medium"):
                await _tool_loop(level)


async def _tool_loop(level):
    """A tool round and its resume, awaited and streamed: with thinking on, the
    resume replays the first round's thinking blocks (the preserved-thinking
    rule), and the streamed path cannot learn a shape from a 400."""
    for streamed in (False, True):
        label = f"tools{' streamed' if streamed else ''}, thinking {level or 'off'}"
        f = ConversationFacilitator(tools=[look_up_colour], conversation_thinking=level)
        try:
            if streamed:
                final = None
                async for event in f.submit_stream(ReplyDto, "Look up a colour and name it."):
                    final = event
                text = str(getattr(final, "response", final))[:50]
            else:
                text = (await f.submit(ReplyDto, "Look up a colour and name it.")).message[:50]
            print(f"  {label:34s} OK   {text!r} tools={f.last_tool_calls}")
        except Exception as e:  # noqa: BLE001
            print(f"  {label:34s} FAIL {type(e).__name__}: {str(e)[:300]}")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_thinking_binding_across_turns(di_container, monkeypatch):
    """The Advisor rebuilds its system prompt every turn (the graph dump lives
    there). On 5.5 a thinking block is bound to the prefix that produced it, so
    replaying turn 1's blocks under turn 2's new system prompt fails the check —
    a 400 for accounts created on/after 2026-08-31. Older accounts opt in to the
    same check with `thinking.block_binding.prefix_mismatch_behavior`, which is
    what this probe sends, so the verdict does not depend on account age."""
    from dialectical_framework.utils import bedrock_provider

    real = bedrock_provider.with_thinking_compat

    def _enforced(model_name, kwargs, params):
        out = real(model_name, kwargs, params)
        thinking = out.get("thinking")
        if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
            out["thinking"] = {**thinking, "block_binding": {"prefix_mismatch_behavior": "error"}}
            out["extra_body"] = {"anthropic_beta": ["thinking-binding-controls-2026-08-01"]}
        return out

    monkeypatch.setattr(bedrock_provider, "with_thinking_compat", _enforced)
    for model in [m for m in MODELS if "5-5" in m]:
        settings = di_container.settings().model_copy(
            update={"ai_model": f"bedrock/{model}", "reasoning_model": None}
        )
        with using_settings(settings):
            f = ConversationFacilitator(tools=[look_up_colour], conversation_thinking="medium")
            f.set_system_prompt("You are terse. Context version 1.")
            try:
                await f.submit(
                    ReplyDto,
                    "Look up a colour, then reason carefully about which of three "
                    "named paints (Teal Dream, Ocean Mist, Pine Shadow) it best matches and why.",
                )
                for m in f._messages:
                    raw = getattr(m, "raw_message", None)
                    content = getattr(m, "content", None) or []
                    if not isinstance(content, (list, tuple)):
                        content = [content]
                    parts = [type(p).__name__ for p in content]
                    raw_types = (
                        [b.get("type") for b in raw.get("content", []) if isinstance(b, dict)]
                        if isinstance(raw, dict)
                        else type(raw).__name__
                    )
                    print(f"    {type(m).__name__}: parts={parts} raw={raw_types}")
                blocks = sum(
                    1
                    for m in f._messages
                    for b in ((getattr(m, "raw_message", None) or {}).get("content") or [])
                    if isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking")
                )
                f.set_system_prompt("You are terse. Context version 2 (the graph moved).")
                out = await f.submit(ReplyDto, "Look it up again and compare.")
                print(f"  {model}: turn 2 OK ({blocks} thinking blocks in history) {out.message[:40]!r}")
            except Exception as e:  # noqa: BLE001
                print(f"  {model}: FAIL {type(e).__name__}: {str(e)[:300]}")


@llm.tool
async def paint_stock(paint: str) -> str:
    """Stock level for one named paint."""
    return {"Teal Dream": "3 tins", "Ocean Mist": "0 tins", "Pine Shadow": "12 tins"}.get(paint, "unknown")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_thinking_before_a_tool_call(di_container, monkeypatch):
    """Thinking BEFORE a tool call, replayed on the same turn's resume (after
    `_strip_caller_from_messages` edited that message) and then across a
    rebuilt system prompt, under enforcement, awaited and streamed."""
    from dialectical_framework.utils import bedrock_provider

    real = bedrock_provider.with_thinking_compat

    def _enforced(model_name, kwargs, params):
        out = real(model_name, kwargs, params)
        thinking = out.get("thinking")
        if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
            out["thinking"] = {**thinking, "block_binding": {"prefix_mismatch_behavior": "error"}}
            out["extra_body"] = {"anthropic_beta": ["thinking-binding-controls-2026-08-01"]}
        return out

    monkeypatch.setattr(bedrock_provider, "with_thinking_compat", _enforced)
    ask = (
        "A client wants the paint whose name is an anagram-free pair of a sea word and "
        "a colour, and which is NOT a tree. Of Teal Dream, Ocean Mist and Pine Shadow, "
        "work out which one that is, then check its stock with the tool."
    )
    for model in [m for m in MODELS if "5-5" in m]:
        settings = di_container.settings().model_copy(
            update={"ai_model": f"bedrock/{model}", "reasoning_model": None}
        )
        for streamed in (False, True):
            with using_settings(settings):
                f = ConversationFacilitator(tools=[paint_stock], conversation_thinking="high")
                f.set_system_prompt("You are terse. Context version 1.")
                label = f"{model}{' streamed' if streamed else ''}"
                try:
                    for turn, text in enumerate((ask, "Now check the other two as well."), 1):
                        if turn == 2:
                            f.set_system_prompt("You are terse. Context version 2.")
                        if streamed:
                            async for _ in f.submit_stream(ReplyDto, text):
                                pass
                        else:
                            await f.submit(ReplyDto, text)
                        before_tool = sum(
                            1
                            for m in f._messages
                            for b in ((getattr(m, "raw_message", None) or {}).get("content") or [])
                            if isinstance(b, dict) and b.get("type") == "thinking"
                            and any(
                                isinstance(x, dict) and x.get("type") == "tool_use"
                                for x in (m.raw_message or {}).get("content", [])
                            )
                        )
                        print(f"  {label} turn {turn} OK, thinking-with-tool_use messages so far: {before_tool}, tools={f.last_tool_calls}")
                except Exception as e:  # noqa: BLE001
                    print(f"  {label}: FAIL {type(e).__name__}: {str(e)[:300]}")
