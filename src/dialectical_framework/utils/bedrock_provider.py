from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

import httpx
from anthropic import AnthropicBedrock, AsyncAnthropicBedrock
from anthropic import types as anthropic_types
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


#: Start of the Advisor's mutable graph dump inside its system prompt.
#:
#: `_CONTEXT_SLOT` (`agents/advisor/system_prompts.py`) is the LAST section and the
#: sections are joined with "\n\n", so this string is the exact seam between the
#: stable engine and the part that changes whenever the graph does. Verified as
#: appearing exactly once across all 2,048 render combinations of tool sets ×
#: scoped/unscoped, and as surviving `encode_request` byte-for-byte.
CACHE_SPLIT_SENTINEL = "\n\n## Current Understanding\n\n"

#: Below this, splitting would produce a head too short for the provider to cache
#: at all. haiku-4.5's minimum cacheable prefix is 4,096 tokens (NOT 1,024; the
#: minimum is not monotonic across model generations), and under it the provider
#: does not error — it silently declines to cache and bills at full rate.
#:
#: 20,480 = 4,096 x 5 chars/token, deliberately the PESSIMISTIC end of the ratio.
#: At the usual ~4 chars/token this reserves 25% more than needed, which costs
#: nothing: the Advisor's head is 33k chars at its smallest, so the guard never
#: fires in practice. Sizing it at 4 chars/token instead would let a 16.4k-char
#: head through on prose that tokenizes badly, and then the split would move the
#: only breakpoint BELOW the threshold — strictly less caching than before.
#:
#: A guard rather than an assertion because this helper runs on EVERY request
#: through three provider entry points. What it protects against is a future prompt
#: in which the sentinel lands near the front, leaving a single-turn request — one
#: with no message-level breakpoint to fall back on — worse off than before. A
#: latency fix must not be able to make latency worse.
_MIN_CACHEABLE_HEAD_CHARS = 20_480


def split_system_for_cache(system: Any) -> Any:
    """Move the system prompt's cache breakpoint off the mutable graph dump.

    Mirascope emits the system prompt as ONE text block with `cache_control` at its
    very end (`anthropic/_utils/encode.py`). For every other agent that is right,
    but the Advisor ends its prompt with the Current Understanding dump — so the
    breakpoint sat *after* content that changes on every graph write, and the
    cached prefix missed whenever the dump moved. The whole ~15.6k-token engine
    was re-prefilled at full rate to deliver a few hundred changed tokens.

    Splitting at the sentinel puts the breakpoint at the end of the STABLE half:
    the engine is read from cache (~0.1x) even when the dump changed, and the dump
    itself is ordinary input. This RELOCATES a breakpoint rather than adding one —
    block 0-of-1 becomes block 0-of-2 — so the count is unchanged and the split
    cannot be what pushes a request over the provider's limit of four. It does not
    follow that there is headroom: see `_normalize_tool_breakpoints`.

    The tail is deliberately left UNcached. On a turn whose dump did not change,
    that costs roughly 600 tokens of full-rate input the single-block form would
    have read from cache — measured at ~2,470 against ~1,910 billed-equivalent. The
    trade is taken because the changed-dump turn is the common one after any tool
    write and it goes the other way by ~20,000, and because buying both would need a
    second breakpoint at the end of the tail, which the budget above does not have.
    The win therefore shrinks as the dump grows relative to the engine.

    Passthrough — unchanged input — in every case where the split would be wrong or
    pointless: no system prompt, an already-split list, a non-text block, no
    sentinel (which is every other agent in the tree; the Advisor is the only one
    that puts mutable state in a system prompt), an empty tail (the provider
    rejects empty text blocks), or a head too short to cache.

    `find` rather than `rfind` deliberately. If a future prompt edit put a second
    "## Current Understanding" heading in the prose, `find` splits at the earlier
    one and the consequence is that stable text lands in the uncached tail — a
    smaller win. `rfind` would split at the later one and could put MUTABLE text in
    the cached head, which is a wrong answer rather than a weaker one. When both
    directions are imperfect, take the one that degrades.
    """
    if not isinstance(system, list) or len(system) != 1:
        return system
    block = system[0]
    if not isinstance(block, dict) or block.get("type") != "text":
        return system
    text = block.get("text")
    if not isinstance(text, str):
        return system

    seam = text.find(CACHE_SPLIT_SENTINEL)
    if seam == -1:
        return system
    cut = seam + len(CACHE_SPLIT_SENTINEL)
    head, tail = text[:cut], text[cut:]
    if not tail or len(head) < _MIN_CACHEABLE_HEAD_CHARS:
        return system

    # `cache_control` is OMITTED from the tail rather than set to None. Mirascope
    # itself passes an explicit None on message blocks (`encode.py:257`) and those
    # requests succeed, so this is not a correctness requirement — an absent key is
    # simply what "no breakpoint here" should look like, and it keeps the block
    # byte-identical to one the encoder would have produced.
    return [
        anthropic_types.TextBlockParam(
            type="text",
            text=head,
            cache_control=anthropic_types.CacheControlEphemeralParam(type="ephemeral"),
        ),
        anthropic_types.TextBlockParam(type="text", text=tail),
    ]


def _normalize_tool_breakpoints(kwargs: dict[str, Any]) -> None:
    """Leave a cache breakpoint on the LAST tool only, which is the encoder's intent.

    Mirascope stamps the last tool (`anthropic/_utils/encode.py:456-461`) but builds
    tool params through an `@lru_cache`d converter (`:380`) that returns a SHARED
    dict — so `last_tool["cache_control"] = ...` mutates the cached entry and the
    stamp survives for the rest of the process. Any later request whose tool list
    contains that tool NOT last therefore carries an extra breakpoint it never asked
    for, and the provider's hard limit is four.

    This is reachable in this tree today. The Advisor's last tool is `discard`
    (`advisor/advisor.py`), which the Analyst carries mid-list while ending on
    `get_schema` — so an Advisor-then-Analyst process sends 2 tool breakpoints +
    system + last message = exactly 4, with zero headroom. `merge_app_tools`
    (`agents/toolsets.py`) appends host tools LAST, so one registered app tool makes
    `get_schema` non-last-but-still-stamped and the request becomes 5 breakpoints,
    which the API rejects with a 400.

    Copies rather than popping from the shared dict on purpose. Popping would heal
    the `lru_cache` entry, but the entry is aliased into the tools list of every
    in-flight request that also uses that tool, so healing it mid-flight would
    silently strip a breakpoint from a request already on its way — trading a loud
    failure for a quiet loss of caching. A shallow copy per request keeps each list
    self-consistent and touches nothing shared. Safe to run unconditionally: the
    encoder re-stamps whichever tool is last on every single encode.
    """
    tools = kwargs.get("tools")
    if not isinstance(tools, list) or len(tools) < 2:
        return
    last = len(tools) - 1
    kwargs["tools"] = [
        {k: v for k, v in tool.items() if k != "cache_control"}
        if isinstance(tool, dict) and i != last and "cache_control" in tool
        else tool
        for i, tool in enumerate(tools)
    ]


def _fix_cache_breakpoints(kwargs: dict[str, Any]) -> None:
    """Put the request's cache breakpoints where they were meant to go.

    Two independent repairs, both on the encoded request rather than upstream,
    because both defects live in the encoder: the system prompt's breakpoint sits
    behind the Advisor's mutable dump, and stale tool breakpoints leak between
    requests. Neither is specific to Bedrock; this is simply the only seam this
    tree owns.

    `system` is guarded on presence rather than read with `.get()`: a request with
    no system prompt must not acquire a `system=None` key it never had. Two of the
    five `@use_brain` call sites in the tree send no system prompt at all.
    """
    if "system" in kwargs:
        kwargs["system"] = split_system_for_cache(kwargs["system"])
    _normalize_tool_breakpoints(kwargs)


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
        _fix_cache_breakpoints(kwargs)
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
        _fix_cache_breakpoints(kwargs)
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
        _fix_cache_breakpoints(kwargs)
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
