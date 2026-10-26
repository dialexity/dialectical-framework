"""
The native `anthropic/` transport, end to end on the real provider.

Why this exists: until 2026-10-26 the framework's whole compat layer lived in
`BedrockAnthropicProvider`, so a deployment pointed at `anthropic/` ran on
Mirascope's defaults — a different instrument, measurably (the native view-turn
run of that day, `docs/dev-notes/antithesis-selection.md`). The layer moved to
`bedrock_provider._AnthropicTransport` and both providers inherit it whole.
`tests/test_transport_parity.py` pins that the two ENCODE the same way; it
cannot show that the provider ACCEPTS what the framework now sends natively.
That is this probe: the three call shapes, each one a thing the native path
either could not do before or did differently, against the real API.

    poetry run pytest tests/e2e/probe_native_transport_smoke.py --real-llm -s

Three calls, cents in total. Models come from the environment
(`DIALEXITY_DEFAULT_MODEL` / `DIALEXITY_REASONING_MODEL`) — never from this
file — and every arm SKIPS unless the configured model is a native one, since
the point is this transport.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.thesis_fit_check import ThesisFitCheck
from dialectical_framework.utils import bedrock_provider as bp

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _native_or_skip(di_container) -> tuple[str, str]:
    """The configured (conversation, reasoning) models, or skip."""
    settings = di_container.settings()
    chat = settings.ai_model
    reasoning = settings.reasoning_model or chat
    if not (chat.startswith("anthropic/") and reasoning.startswith("anthropic/")):
        pytest.skip(
            "configured for another transport "
            f"(chat={chat}, reasoning={reasoning}); this probe is about `anthropic/`"
        )
    return chat, reasoning


@pytest.fixture
def wire(monkeypatch):
    """What the framework actually put on the wire, per call.

    Spying on `_create_async` — the one place both transports send from — so a
    pass here is evidence about the REQUEST and not only about the reply.
    """
    seen: list[dict[str, Any]] = []
    original = bp._AnthropicTransport._create_async

    async def spy(self, kwargs, params):
        sent = bp.with_thinking_compat(kwargs["model"], kwargs, params)
        seen.append(
            {
                "provider": type(self).__name__,
                "model": sent["model"],
                "thinking": sent.get("thinking"),
                "effort": (sent.get("output_config") or {}).get("effort"),
                "constrained": bool((sent.get("output_config") or {}).get("format")),
                "tool_choice": (sent.get("tool_choice") or {}).get("type"),
                "cache_blocks": sum(
                    1
                    for block in (sent.get("system") or [])
                    if isinstance(block, dict) and "cache_control" in block
                ),
            }
        )
        return await original(self, kwargs, params)

    monkeypatch.setattr(bp._AnthropicTransport, "_create_async", spy)
    return seen


class Verdict(BaseModel):
    """A DTO shaped like the framework's own: nested, with descriptions."""

    answer: str = Field(description="One short sentence.")
    confidence: float = Field(ge=0.0, le=1.0, description="0..1")


class TestTheNativeTransportTakesWhatTheFrameworkSends:
    @pytest.mark.asyncio
    async def test_a_plain_structured_concern_call(self, di_container, wire):
        """A concern, on the real DTO path. On a 5.5 model this is the arm that
        proves the formatting substitution reaches the native provider: forced
        tool use would 400, and json mode without the schema constraint is what
        cost a host 32 parse re-asks in 80 cards."""
        _native_or_skip(di_container)
        dto = await ThesisFitCheck().score_texts(
            thesis="Remote work should be the default",
            antithesis="Presence in the office should be the default",
            a_plus="Deliberate time together for the work that needs a room",
            text=(
                "I'm done commuting. Yes, some meetings are better in person, "
                "but make remote the default and let teams opt into days together."
            ),
        )
        print("\nstructured concern:", dto.model_dump_json(indent=2)[:400])
        print("wire:", json.dumps(wire[-1], indent=2))
        assert 0.0 <= dto.fit <= 1.0
        assert wire[-1]["provider"] == "NativeAnthropicProvider"
        # The two seams a native call did not have before.
        assert wire[-1]["tool_choice"] is None, "forced tool use, which 5.5 refuses"
        assert wire[-1]["constrained"], "no schema constraint = JSON asked for in prose"

    @pytest.mark.asyncio
    async def test_a_thinking_structured_call(self, di_container, wire):
        """The view turn's shape: `format_mode="json"` plus a level. This is the
        call that returned 400 on all 40 inputs natively before the Mirascope
        floor moved, and the one the framework's thinking layer now shapes."""
        _native_or_skip(di_container)
        facilitator = ConversationFacilitator(format_mode="json", thinking="medium")
        dto = await facilitator.submit(
            response_model=Verdict,
            user_content=(
                "Is 'we should ask whether to allow this' the same claim as "
                "'we should not allow this'? Answer in one sentence."
            ),
        )
        print("\nthinking structured:", dto.model_dump_json())
        print("wire:", json.dumps(wire[-1], indent=2))
        assert dto.answer
        assert wire[-1]["thinking"] == {"type": "adaptive"}, "the Claude 5 shape"
        assert wire[-1]["effort"] == "medium", "the level, as this tree maps it"

    @pytest.mark.asyncio
    async def test_a_conversational_tool_path_turn(self, di_container, wire):
        """The tool path, which is where "no hidden thinking where you consult"
        applies — a policy that was Bedrock-only, so a native conversational
        turn took the provider default (thinking ON). The assertion is that the
        model ACCEPTS its own off: on Sonnet 5.5 that is `between_tools`, which
        Sonnet 5 and Opus 5.5 reject in turn, so this arm is the only evidence
        that the per-model off shape is right for the configured model."""
        _native_or_skip(di_container)

        from mirascope import llm

        @llm.tool
        async def square(n: int) -> str:
            """Squares an integer. Async because the facilitator's toolkit is
            an `AsyncToolkit` and awaits what it executes."""
            return str(n * n)

        facilitator = ConversationFacilitator([square], conversation_thinking=None)

        class Reply(BaseModel):
            message: str

        reply = await facilitator.submit(
            response_model=Reply, user_content="What is 17 squared? Use the tool."
        )
        print("\nconversational reply:", reply.message[:200])
        print("tools called:", facilitator.last_tool_calls)
        for record in wire:
            print("wire:", json.dumps(record))
        assert "289" in reply.message or facilitator.last_tool_calls
        rounds = [r for r in wire if r["tool_choice"] is None and not r["constrained"]]
        assert rounds, "no conversational round reached the provider"
        assert rounds[0]["thinking"] is not None, (
            "an unset level on an adaptive model must be sent as the model's own "
            "off inside a conversational round, not left to the provider default"
        )
