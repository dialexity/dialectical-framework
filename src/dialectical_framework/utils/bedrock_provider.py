from __future__ import annotations

from anthropic import AnthropicBedrock, AsyncAnthropicBedrock
from mirascope import llm
from mirascope.llm.providers.anthropic import _utils
from mirascope.llm.providers.anthropic.provider import AnthropicProvider
from mirascope.llm.responses import AsyncResponse


def _bedrock_model_name(model_id: str) -> str:
    """Strip scope prefix(es) to get the raw Bedrock model identifier.

    Handles both 'bedrock/model' and 'bedrock/anthropic/model'.
    """
    return model_id.removeprefix("bedrock/").removeprefix("anthropic/")


class BedrockAnthropicProvider(AnthropicProvider):
    """Mirascope v2 provider that routes through AnthropicBedrock client (async-native).

    Bedrock does not support the beta structured output API (client.beta.messages.parse),
    so we override _call_async to always use the standard path.
    """

    id = "bedrock"
    default_scope = "bedrock/"

    def __init__(self, **kwargs):
        self.client = AnthropicBedrock()
        self.async_client = AsyncAnthropicBedrock()
        self._beta_provider = None

    async def _call_async(self, *, model_id, messages, toolkit, format=None, **params):
        """Always use standard path — bedrock doesn't support beta structured outputs."""
        input_messages, resolved_format, kwargs = _utils.encode_request(
            model_id=model_id,
            messages=messages,
            tools=toolkit,
            format=format,
            params=params,
        )
        kwargs["model"] = _bedrock_model_name(model_id)
        anthropic_response = await self.async_client.messages.create(**kwargs)
        include_thoughts = _utils.get_include_thoughts(params)
        assistant_message, finish_reason, usage = _utils.decode_response(
            anthropic_response, model_id, include_thoughts=include_thoughts
        )
        return AsyncResponse(
            raw=anthropic_response,
            provider_id="bedrock",
            model_id=model_id,
            provider_model_name=_bedrock_model_name(model_id),
            params=params,
            tools=toolkit,
            input_messages=input_messages,
            assistant_message=assistant_message,
            finish_reason=finish_reason,
            usage=usage,
            format=resolved_format,
        )

    def _call(self, *, model_id, messages, toolkit, format=None, **params):
        """Always use standard path — bedrock doesn't support beta structured outputs."""
        from mirascope.llm.responses import Response

        input_messages, resolved_format, kwargs = _utils.encode_request(
            model_id=model_id,
            messages=messages,
            tools=toolkit,
            format=format,
            params=params,
        )
        kwargs["model"] = _bedrock_model_name(model_id)
        anthropic_response = self.client.messages.create(**kwargs)
        include_thoughts = _utils.get_include_thoughts(params)
        assistant_message, finish_reason, usage = _utils.decode_response(
            anthropic_response, model_id, include_thoughts=include_thoughts
        )
        return Response(
            raw=anthropic_response,
            provider_id="bedrock",
            model_id=model_id,
            provider_model_name=_bedrock_model_name(model_id),
            params=params,
            tools=toolkit,
            input_messages=input_messages,
            assistant_message=assistant_message,
            finish_reason=finish_reason,
            usage=usage,
            format=resolved_format,
        )


_registered = False


def ensure_bedrock_provider():
    """Register the bedrock provider if not already registered. Idempotent."""
    global _registered
    if _registered:
        return
    llm.register_provider(BedrockAnthropicProvider(), scope="bedrock/")
    _registered = True
