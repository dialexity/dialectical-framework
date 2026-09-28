"""probe_tool_path_hidden_output — WHAT are the ~2,500 output tokens a tool-wired turn emits and never shows?

`probe_consultant_42s` (2026-09-24, Sonnet 5, 5-perspective graph, 11.8k-char dump):
the same prompt answered in 13s / ~700 output tokens with no tools wired and in
42-46s / 3,200-3,500 output tokens with the sealed Advisor's six tools wired — for a
reply of the same ~400 words, with no tool called, no second call, thinking unset.
So a tool-wired turn generates ~2,500 tokens the person never sees. This probe
makes ONE such call through a bare facilitator and prints the response's parts:
which block types the model returned (text / thinking / tool_use), their sizes,
the raw provider message's content types, `finish_reason`, and usage.

Two graphs, because the earlier small-graph probe saw NO hidden tokens (289 out):
the seed Case already in Memgraph (3 perspectives, tiny dump) and, with
DIALEXITY_PROBE_BUILD=1, a fresh headless build (k=2, ~3-4 min on Sonnet).

    DIALEXITY_PROBE_BUILD=1 poetry run pytest tests/e2e/probe_tool_path_hidden_output.py --real-llm -s
"""

from __future__ import annotations

import os

import pytest
from mirascope import llm

from e2e.config import DEFAULT_TIER_STRONG
from e2e.driver import E2E_PERSONA
from e2e.modelctx import using_model
from e2e.probe_consultant_42s import INTENT, K, MATERIAL
from e2e.probe_consultant_prompt_cost import QUESTION, _prompt_text

from dialectical_framework.agents.advisor.advisor import (
    Advisor, _build_tools)
from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.advisor.tools.explore import \
    run_exploration_detailed
from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census

MODEL = os.getenv("DIALEXITY_PROBE_MODEL", DEFAULT_TIER_STRONG)
SEED_SID = os.getenv("DIALEXITY_PROBE_SID", "seed-multiple-perspectives-001")
BUILD = os.getenv("DIALEXITY_PROBE_BUILD", "0") == "1"


def _describe(response) -> None:
    print(f"  response type: {type(response).__name__}")
    print(f"  finish_reason: {getattr(response, 'finish_reason', None)!r}")
    usage = getattr(response, "usage", None)
    print(f"  usage: {usage!r}")
    text = response.text()
    print(f"  text(): {len(text)} chars, {len(text.split())} words")
    content = getattr(response, "content", None)
    if content is not None:
        parts = []
        for part in content:
            kind = type(part).__name__
            size = len(getattr(part, "text", "") or getattr(part, "thought", "") or str(part))
            parts.append((kind, size))
        print(f"  content parts: {parts}")
    raw = getattr(response, "raw", None)
    if raw is not None:
        blocks = getattr(raw, "content", None)
        if blocks is not None:
            desc = []
            for b in blocks:
                btype = getattr(b, "type", type(b).__name__)
                size = len(getattr(b, "text", "") or getattr(b, "thinking", "") or "")
                desc.append((btype, size))
            print(f"  raw content blocks: {desc}")
        print(f"  raw stop_reason: {getattr(raw, 'stop_reason', None)!r}  raw usage: {getattr(raw, 'usage', None)!r}")
    else:
        print(f"  no .raw; dir: {[n for n in dir(response) if not n.startswith('_')]}")


async def _one_call(engine_prompt: str, tools) -> None:
    conversation = ConversationFacilitator(tools=tools)
    conversation.set_system_prompt(engine_prompt)
    with call_census() as census:
        response = await conversation._call_with_tools() if hasattr(conversation, "_call_with_tools") else None
    # `_call_with_tools` reads self._messages; add the user turn first.
    return response, census


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(1800)
async def test_probe_tool_path_hidden_output(di_container):
    print(f"\nmodel: {MODEL}  thinking: {di_container.settings().conversation_thinking_level!r}")
    if BUILD:
        case = Case()
        case.commit()
        sid = case.sid
    else:
        sid = SEED_SID
    with scope(sid), using_model(di_container, MODEL):
        if BUILD:
            analysis = await AnalysisPipeline(text=MATERIAL, intent=INTENT).resolve()
            hashes = list(analysis.perspective_hashes)[:K]
            created = await CreateNexus().resolve(intent=INTENT, perspective_hashes=hashes)
            await run_exploration_detailed(hashes, INTENT, created.nexus.hash)
        advisor = Advisor(app_preamble=E2E_PERSONA, build=BuildPolicy.NEVER)
        await advisor._refresh_context()
        engine_prompt = _prompt_text(advisor)
        print(f"engine prompt {len(engine_prompt)}c")
        for label, tools in (
            ("engine + sealed tools", _build_tools("agent:probe", build=BuildPolicy.NEVER)),
            ("engine, no tools", None),
        ):
            conversation = ConversationFacilitator(tools=tools)
            conversation.set_system_prompt(engine_prompt)
            conversation._messages.append(llm.messages.user(QUESTION))
            print(f"\n== {label}")
            with call_census() as census:
                response = await conversation._call_with_tools()
            print(f"  census: {[(r.label[:36], round(r.seconds, 1), r.output_tokens) for r in census.calls]}")
            _describe(response)
    assert True


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_probe_where_thinking_lands_now(di_container, monkeypatch):
    """After the scoped policy (2026-09-24): a conversational round sends
    "disabled" when unset; a structured concern call is left at the provider
    default. Prints the raw provider usage of each, captured at the provider
    seam, so both halves of "think where you build, read where you consult"
    are visible as thinking_tokens."""
    import dialectical_framework.utils.bedrock_provider as bp
    from dialectical_framework.concerns.decision_confirmation_check import \
        DecisionConfirmationCheck

    provider_cls = next(
        obj for name, obj in vars(bp).items()
        if isinstance(obj, type) and hasattr(obj, "_create_async") and name.endswith("Provider")
    )
    captured: list[tuple[dict, object]] = []
    original = provider_cls._create_async

    async def spy(self, kwargs, params):
        message = await original(self, kwargs, params)
        captured.append((dict(kwargs), message))
        return message

    monkeypatch.setattr(provider_cls, "_create_async", spy)

    def report(label):
        for kwargs, message in captured:
            usage = getattr(message, "usage", None)
            details = getattr(usage, "output_tokens_details", None)
            blocks = [getattr(b, "type", "?") for b in getattr(message, "content", [])]
            print(f"  {label}: thinking kwarg={kwargs.get('thinking')!r} tools={'tools' in kwargs} "
                  f"out={getattr(usage, 'output_tokens', None)} details={details} blocks={blocks}")
        captured.clear()

    print(f"\nmodel: {MODEL}  thinking: {di_container.settings().conversation_thinking_level!r}")
    with scope(SEED_SID), using_model(di_container, MODEL):
        advisor = Advisor(app_preamble=E2E_PERSONA, build=BuildPolicy.NEVER)
        await advisor._refresh_context()
        engine_prompt = _prompt_text(advisor)
        conversation = ConversationFacilitator(tools=_build_tools("agent:probe", build=BuildPolicy.NEVER))
        conversation.set_system_prompt(engine_prompt)
        conversation._messages.append(llm.messages.user(QUESTION))
        await conversation._call_with_tools()
        report("conversational round (tools wired, level unset)")
        await DecisionConfirmationCheck().resolve(
            user_message="Write that down as the decision: I'm doing the buyout.",
            assistant_message="Understood.",
        )
        report("structured concern call (format, level unset)")
    assert True
