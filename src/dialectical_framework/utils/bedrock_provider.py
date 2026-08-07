from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

import httpx
from anthropic import AnthropicBedrock, AsyncAnthropicBedrock
from anthropic._constants import DEFAULT_TIMEOUT
from anthropic.types import Message as AnthropicMessage
from dependency_injector.wiring import Provide, inject
from mirascope import llm
from mirascope.llm.providers.anthropic import _utils  # noqa: PLC2701
from mirascope.llm.providers.anthropic.provider import AnthropicProvider
from mirascope.llm.responses import AsyncResponse, AsyncStreamResponse, Response
from typing_extensions import Unpack

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.utils.thinking_compat import (
    learn_thinking_shape_from_error,
    with_thinking_compat,
)

if TYPE_CHECKING:
    from mirascope.llm.formatting import FormatSpec, FormattableT
    from mirascope.llm.messages import Message
    from mirascope.llm.models import Params
    from mirascope.llm.tools import AsyncToolkit, Toolkit


def _connect_timeout(connect_timeout_s: float | None) -> httpx.Timeout:
    """SDK default timeouts with a widened CONNECT phase only.

    The SDK's 5s connect timeout assumes a warm datacenter link. A cold TLS
    handshake over a tethered/VPN/mobile connection measured 7.7s, so the first
    call on every fresh connection failed — and the parallel stages failed
    hardest, since each concurrent call opens its own cold connection while a
    sequential one reuses a handshaked socket. Read/write keep the SDK defaults:
    a slow-to-connect link is a different problem from a slow generation, and
    conflating them would mask real hangs.
    """
    seconds = connect_timeout_s if connect_timeout_s is not None else 30.0
    default = DEFAULT_TIMEOUT
    return httpx.Timeout(
        connect=seconds,
        read=default.read,
        write=default.write,
        pool=default.pool,
    )


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

    def __init__(self, *, connect_timeout_s: float | None = None, **kwargs) -> None:  # noqa: ARG002
        # Skip super().__init__() — parent creates Anthropic/AsyncAnthropic clients we don't need
        timeout = _connect_timeout(connect_timeout_s)
        self.client = AnthropicBedrock(timeout=timeout)
        self.async_client = AsyncAnthropicBedrock(timeout=timeout)
        self._beta_provider = None

    async def _create_async(
        self, kwargs: dict[str, Any], params: Mapping[str, Any]
    ) -> AnthropicMessage:
        """messages.create with the model's thinking shape, learning once on 400.

        Mirascope encodes extended thinking as a token budget, which Claude 5
        models reject. `with_thinking_compat` translates by model name; if the
        name heuristic is wrong the 400 itself says which shape is wanted, so
        one retry is both sufficient and self-correcting. See thinking_compat.
        """
        model_name = kwargs["model"]
        try:
            return await self.async_client.messages.create(
                **with_thinking_compat(model_name, kwargs, params)
            )
        except Exception as e:
            if not learn_thinking_shape_from_error(model_name, e):
                raise
            return await self.async_client.messages.create(
                **with_thinking_compat(model_name, kwargs, params)
            )

    def _create_sync(
        self, kwargs: dict[str, Any], params: Mapping[str, Any]
    ) -> AnthropicMessage:
        """Synchronous twin of `_create_async`."""
        model_name = kwargs["model"]
        try:
            return self.client.messages.create(
                **with_thinking_compat(model_name, kwargs, params)
            )
        except Exception as e:
            if not learn_thinking_shape_from_error(model_name, e):
                raise
            return self.client.messages.create(
                **with_thinking_compat(model_name, kwargs, params)
            )

    async def _call_async(
        self,
        *,
        model_id: str,
        messages: Sequence[Message],
        toolkit: AsyncToolkit,
        format: FormatSpec[FormattableT] | None = None,
        **params: Unpack[Params],
    ) -> AsyncResponse | AsyncResponse[FormattableT]:
        """Always use standard path — bedrock doesn't support beta structured outputs."""
        input_messages, resolved_format, kwargs = _utils.encode_request(
            model_id=model_id,
            messages=messages,
            tools=toolkit,
            format=format,
            params=params,
        )
        kwargs["model"] = _bedrock_model_name(model_id)
        anthropic_response = cast(
            AnthropicMessage, await self._create_async(kwargs, params)
        )
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

    async def _stream_async(
        self,
        *,
        model_id: str,
        messages: Sequence[Message],
        toolkit: AsyncToolkit,
        format: FormatSpec[FormattableT] | None = None,
        **params: Unpack[Params],
    ) -> AsyncStreamResponse | AsyncStreamResponse[FormattableT]:
        """Stream responses from Bedrock Anthropic."""
        input_messages, resolved_format, kwargs = _utils.encode_request(
            model_id=model_id,
            messages=messages,
            tools=toolkit,
            format=format,
            params=params,
        )
        kwargs["model"] = _bedrock_model_name(model_id)
        # Streaming cannot learn from a 400: the error surfaces when the caller
        # consumes the iterator, by which point retrying would replay tokens
        # already yielded. The name heuristic is applied, and a genuine mismatch
        # raises to the caller.
        kwargs = with_thinking_compat(kwargs["model"], kwargs, params)
        anthropic_stream = self.async_client.messages.stream(**kwargs)
        include_thoughts = _utils.get_include_thoughts(params)
        chunk_iterator = _utils.decode_async_stream(
            anthropic_stream, include_thoughts=include_thoughts
        )
        return AsyncStreamResponse(
            provider_id="bedrock",
            model_id=model_id,
            provider_model_name=_bedrock_model_name(model_id),
            params=params,
            tools=toolkit,
            input_messages=input_messages,
            chunk_iterator=chunk_iterator,
            format=resolved_format,
        )

    def _call(
        self,
        *,
        model_id: str,
        messages: Sequence[Message],
        toolkit: Toolkit,
        format: FormatSpec[FormattableT] | None = None,
        **params: Unpack[Params],
    ) -> Response | Response[FormattableT]:
        """Always use standard path — bedrock doesn't support beta structured outputs."""
        input_messages, resolved_format, kwargs = _utils.encode_request(
            model_id=model_id,
            messages=messages,
            tools=toolkit,
            format=format,
            params=params,
        )
        kwargs["model"] = _bedrock_model_name(model_id)
        anthropic_response = cast(AnthropicMessage, self._create_sync(kwargs, params))
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


@inject
def ensure_bedrock_provider(
    settings: Settings = Provide[DI.settings],
) -> None:
    """Register the bedrock provider if not already registered. Idempotent.

    Registration happens on the first call, so `llm_connect_timeout_s` is read
    from DI here rather than in `__init__` (Mirascope constructs providers with
    no arguments). Consequence of the idempotence: changing the setting after
    the first LLM call of the process has no effect.
    """
    global _registered
    if _registered:
        return
    llm.register_provider(
        BedrockAnthropicProvider(
            connect_timeout_s=getattr(settings, "llm_connect_timeout_s", None)
        ),
        scope="bedrock/",
    )
    _registered = True
