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
from dialectical_framework.exceptions.provider_errors import ModelRefusal
from dialectical_framework.settings import Settings
from dialectical_framework.utils.format_compat import (
    learn_format_mode_from_error,
    structured_output_format,
    with_format_compat,
)
from dialectical_framework.utils.thinking_compat import (
    learn_thinking_shape_from_error,
    with_thinking_compat,
    without_earlier_turn_thinking,
)

if TYPE_CHECKING:
    from mirascope.llm.formatting import FormatSpec, FormattableT
    from mirascope.llm.messages import Message
    from mirascope.llm.models import Params
    from mirascope.llm.tools import AsyncToolkit, Toolkit


def _client_timeout(
    connect_timeout_s: float | None, read_timeout_s: float | None = None
) -> httpx.Timeout:
    """SDK default timeouts with the CONNECT and READ phases set by the framework.

    Connect: the SDK's 5s assumes a warm datacenter link. A cold TLS handshake
    over a tethered/VPN/mobile connection measured 7.7s, so the first call on
    every fresh connection failed — and the parallel stages failed hardest,
    since each concurrent call opens its own cold connection while a sequential
    one reuses a handshaked socket.

    Read: the SDK's 600s is the length of a stall nobody asked for. A provider
    call that stops sending holds its caller for ten minutes with no error, and
    where callers are gathered (the view turn's best-of-3) one stalled draw
    holds the two that finished (a 300s card where the same case took 20-31s,
    2026-10-09). `Settings.llm_read_timeout_s` sets it; a timeout raises
    `APITimeoutError`, which the ladder classifies as a stall and re-asks once.
    Write and pool keep the SDK defaults: nothing has stalled on either.
    """
    connect = connect_timeout_s if connect_timeout_s is not None else 30.0
    read = read_timeout_s if read_timeout_s is not None else 120.0
    default = DEFAULT_TIMEOUT
    return httpx.Timeout(
        connect=connect,
        read=read,
        write=default.write,
        pool=default.pool,
    )


#: The Anthropic SDK's own retry is OFF: every retry the framework makes is one
#: it can see. The SDK defaults to two retries of a timeout, a connection error
#: or a 408/409/429/5xx with its own backoff, BELOW `use_brain`'s ladder and
#: `retry_transient` — so a stalled call cost three read timeouts before the
#: ladder saw one failure, and `retry_accounting`/`call_census` recorded none of
#: it (a 610s turn with `retry_count` 0, `prompt-vs-machinery`). With this at 0
#: the bound on one call is the ladder's: a stall is (`_STALL_RETRY_MAX`) × the
#: read timeout plus its flat delay, and the retry is on the account. Every
#: provider request the framework makes passes a retry layer of its own — the
#: ladder (`use_brain`), the streamed open and resume (`retry_transient` in
#: `_start_stream_round`) and, since this went to 0, the awaited resume too
#: (`ConversationFacilitator.submit`), which until then had only the SDK's.
_SDK_MAX_RETRIES = 0


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

#: How long a cache entry on a STABLE part of the request lives.
#:
#: The provider's default is five minutes, which is shorter than the gap
#: between two sessions of a product with few users: measured on the first app
#: (2026-10-06), a card's three parallel draws each WROTE the ~12k-token system
#: head on a cold cache — $0.089 of writes where a warm card pays $0.007 of
#: reads — and for a single early user every session started cold. An hour of
#: idle survives at 2x the write rate instead of 1.25x, so the break-even is
#: three reads of the entry; a conversation reaches that in three turns, and a
#: host serving more than one person an hour reaches it on the shared engine
#: alone. The loss case is a one-turn session on a cold cache, which pays 0.75x
#: of one prefill more than it would have.
#:
#: Applied to the system prompt and the tools only — the two parts that are
#: identical across the turns of a session. A message-level breakpoint moves
#: every turn, so a longer TTL there would buy a 2x write on an entry nothing
#: reads twice. That split also keeps the provider's ordering rule satisfied:
#: longer-TTL entries must come BEFORE shorter ones in the request, and the
#: order is tools, then system, then messages.
#:
#: Bedrock accepts the field on Claude 4.x and later, and a model that did not
#: would reject EVERY request rather than quietly fall back — so the risk is
#: liveness, not a silent loss of caching, and it is checked against the live
#: provider by `tests/test_prompt_cache_split.py::TestTheProviderAcceptsTheTtl`
#: (`--real-llm`). The census cannot confirm the lifetime itself: Mirascope
#: reports one `cache_write_tokens` number and not the provider's
#: `cache_creation.ephemeral_1h_input_tokens` breakdown, so what the hour buys
#: is read off a cache HIT after an idle gap longer than five minutes, which is
#: the app's paired eval, not a unit test.
_CACHE_TTL = "1h"


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
            # No `ttl` here: this function decides WHERE the breakpoint goes,
            # and `_lengthen_stable_ttl` decides how long it lives — for the
            # system block it splits and the one Mirascope emits alike.
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


def _lengthen_stable_ttl(kwargs: dict[str, Any]) -> None:
    """Give the request's STABLE breakpoints the longer TTL (`_CACHE_TTL`).

    Mirascope writes `{"type": "ephemeral"}` with no TTL, which is the
    provider's five-minute default. The system prompt and the tool list are the
    same bytes on every turn of a session, so five minutes is simply the wrong
    lifetime for them — see `_CACHE_TTL` for what that cost and what the longer
    one costs. Message breakpoints are left alone on purpose: they move every
    turn, and the ordering rule (longer TTLs first) holds because tools and
    system precede messages in the request.

    Stamps a COPY of each block and of the tool, never the dict it was handed:
    the tool params come from Mirascope's `@lru_cache`d converter and are
    aliased into every in-flight request that uses the same tool, which is the
    same trap `_normalize_tool_breakpoints` documents at length.

    Runs after the split, so the system block it stamps is whichever one
    carries the breakpoint — the head on a split prompt, the single block
    otherwise. Idempotent, and a no-op wherever there is no breakpoint to
    lengthen.
    """

    def stamped(block: Any) -> Any:
        if not isinstance(block, dict):
            return block
        control = block.get("cache_control")
        if not isinstance(control, dict) or control.get("ttl") == _CACHE_TTL:
            return block
        return {**block, "cache_control": {**control, "ttl": _CACHE_TTL}}

    system = kwargs.get("system")
    if isinstance(system, list):
        kwargs["system"] = [stamped(block) for block in system]

    tools = kwargs.get("tools")
    if isinstance(tools, list):
        kwargs["tools"] = [stamped(tool) for tool in tools]


def _fix_cache_breakpoints(kwargs: dict[str, Any]) -> None:
    """Put the request's cache breakpoints where they were meant to go.

    Three independent repairs, all on the encoded request rather than upstream,
    because all three live in the encoder: the system prompt's breakpoint sits
    behind the Advisor's mutable dump, stale tool breakpoints leak between
    requests, and the breakpoints on the request's stable parts are written with
    the five-minute default TTL. None is specific to Bedrock; this is simply the
    only seam this tree owns.

    `system` is guarded on presence rather than read with `.get()`: a request with
    no system prompt must not acquire a `system=None` key it never had. Two of the
    five `@use_brain` call sites in the tree send no system prompt at all.
    """
    if "system" in kwargs:
        kwargs["system"] = split_system_for_cache(kwargs["system"])
    _normalize_tool_breakpoints(kwargs)
    _lengthen_stable_ttl(kwargs)


def _bedrock_model_name(model_id: str) -> str:
    """Strip scope prefix(es) to get the raw Bedrock model identifier.

    Handles both 'bedrock/model' and 'bedrock/anthropic/model'.
    """
    return model_id.removeprefix("bedrock/").removeprefix("anthropic/")


class _LearningStreamManager:
    """`messages.stream(...)` that learns the thinking shape from a 400, once.

    The request is made when the manager is ENTERED (Mirascope's decoder does
    `async with` on the first chunk), before anything has been yielded, so a
    rejected shape can be re-sent without replaying a token — and the streamed
    conversational round is exactly where an unset level goes out as "off",
    so without this a wrong name heuristic would fail every streamed turn until
    some awaited call taught the process. Thinking only: a learned FORMAT mode
    would change the response's parser, which the caller already holds.
    """

    def __init__(
        self, client: Any, kwargs: dict[str, Any], params: Mapping[str, Any]
    ) -> None:
        self._client = client
        self._kwargs = kwargs
        self._params = params
        self._manager: Any = None

    def _open(self) -> Any:
        return self._client.messages.stream(
            **with_thinking_compat(self._kwargs["model"], self._kwargs, self._params)
        )

    async def __aenter__(self) -> Any:
        self._manager = self._open()
        try:
            return await self._manager.__aenter__()
        except Exception as e:
            if not learn_thinking_shape_from_error(self._kwargs["model"], e):
                raise
            self._manager = self._open()
            return await self._manager.__aenter__()

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._manager.__aexit__(*exc)


def raise_on_refusal(response: Any, model_name: str) -> None:
    """Raise `ModelRefusal` when the provider stopped on a refusal.

    Raised at the provider, below `use_brain`, so no retry ladder ever re-asks
    it (an unknown exception re-raises there) and the tool loop's resumes —
    Mirascope's own requests, which reach this provider too — are covered.
    """
    if getattr(response, "stop_reason", None) != "refusal":
        return
    details = getattr(response, "stop_details", None)
    raise ModelRefusal(
        model_name,
        category=getattr(details, "category", None),
        explanation=getattr(details, "explanation", None),
    )


class BedrockAnthropicProvider(AnthropicProvider):
    """Mirascope v2 provider that routes through AnthropicBedrock client (async-native).

    Bedrock does not support the beta structured output API (client.beta.messages.parse),
    so we override _call_async to always use the standard path.
    """

    id = "bedrock"
    default_scope = "bedrock/"

    def __init__(
        self,
        *,
        connect_timeout_s: float | None = None,
        read_timeout_s: float | None = None,
        **kwargs,  # noqa: ARG002
    ) -> None:
        # Skip super().__init__() — parent creates Anthropic/AsyncAnthropic clients we don't need
        timeout = _client_timeout(connect_timeout_s, read_timeout_s)
        self.client = AnthropicBedrock(timeout=timeout, max_retries=_SDK_MAX_RETRIES)
        self.async_client = AsyncAnthropicBedrock(
            timeout=timeout, max_retries=_SDK_MAX_RETRIES
        )
        self._beta_provider = None

    @staticmethod
    def _encode(
        model_id: str,
        messages: Sequence[Message],
        toolkit: AsyncToolkit | Toolkit,
        format: FormatSpec[FormattableT] | None,
        params: Mapping[str, Any],
    ) -> tuple[Any, Any, dict[str, Any]]:
        """Encode a request in the formatting mode this model can take.

        Forced tool use is re-asked as JSON for a model that refuses it (Claude
        5.5); see format_compat. Encoding happens here, BEFORE the request is
        built, because the mode decides the request's shape — tools and
        tool_choice for one, system instructions for the other — and the
        decoded response's parser follows the resolved format. A JSON-mode
        call to such a model also carries its schema as a structured output
        (`output_config.format`, see `structured_output_format`). Earlier turns'
        thinking blocks are dropped here too, for a model that binds them to
        their prefix (see `without_earlier_turn_thinking`).

        A call moved OFF forced tool use is also sent with thinking off unless
        it asked for thinking: forced tool choice is what kept every structured
        call from thinking by default (0 thinking tokens with no parameter,
        2026-09-24), and JSON mode with nothing sent is the provider's default,
        thinking on. Without this every concern on a 5.5 model would think —
        a cost, latency and behaviour change no figure was taken under.
        `with_thinking_compat` turns "disabled" into the model's own off.
        """
        model_name = _bedrock_model_name(model_id)
        compatible = with_format_compat(model_name, format)
        input_messages, resolved_format, kwargs = _utils.encode_request(
            model_id=model_id,
            messages=messages,
            tools=toolkit,
            format=compatible,
            params=params,
        )
        kwargs["model"] = model_name
        # A structured call is never a round of the tool loop: no tools, and in
        # JSON mode extra system text, so even THIS turn's blocks are bound to a
        # prefix the request no longer has. Drop them all there.
        kwargs["messages"] = without_earlier_turn_thinking(
            model_name, kwargs["messages"], every_turn=format is not None
        )
        if compatible is not format and "thinking" not in kwargs:
            kwargs["thinking"] = {"type": "disabled"}
        # A JSON-mode call to a model whose structured calls go in JSON mode
        # is constrained to its schema (`output_config.format`): JSON asked for
        # in prose came back with trailing commas often enough to cost a whole
        # re-ask per 2.5 cards on Sonnet 5.5 (see format_compat). The thinking
        # layer merges its `effort` into the same `output_config` later.
        constraint = structured_output_format(model_name, compatible)
        if constraint is not None:
            output_config = dict(kwargs.get("output_config") or {})
            output_config["format"] = constraint
            kwargs["output_config"] = output_config
        _fix_cache_breakpoints(kwargs)
        return input_messages, resolved_format, kwargs

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
        input_messages, resolved_format, kwargs = self._encode(
            model_id, messages, toolkit, format, params
        )
        try:
            anthropic_response = cast(
                AnthropicMessage, await self._create_async(kwargs, params)
            )
        except Exception as e:
            if not learn_format_mode_from_error(kwargs["model"], format, e):
                raise
            input_messages, resolved_format, kwargs = self._encode(
                model_id, messages, toolkit, format, params
            )
            anthropic_response = cast(
                AnthropicMessage, await self._create_async(kwargs, params)
            )
        raise_on_refusal(anthropic_response, kwargs["model"])
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
        input_messages, resolved_format, kwargs = self._encode(
            model_id, messages, toolkit, format, params
        )
        anthropic_stream = _LearningStreamManager(self.async_client, kwargs, params)
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
        input_messages, resolved_format, kwargs = self._encode(
            model_id, messages, toolkit, format, params
        )
        try:
            anthropic_response = cast(
                AnthropicMessage, self._create_sync(kwargs, params)
            )
        except Exception as e:
            if not learn_format_mode_from_error(kwargs["model"], format, e):
                raise
            input_messages, resolved_format, kwargs = self._encode(
                model_id, messages, toolkit, format, params
            )
            anthropic_response = cast(
                AnthropicMessage, self._create_sync(kwargs, params)
            )
        raise_on_refusal(anthropic_response, kwargs["model"])
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

    Registration happens on the first call, so `llm_connect_timeout_s` and
    `llm_read_timeout_s` are read from DI here rather than in `__init__`
    (Mirascope constructs providers with no arguments). Consequence of the
    idempotence: changing either setting after the first LLM call of the
    process has no effect.
    """
    global _registered
    if _registered:
        return
    llm.register_provider(
        BedrockAnthropicProvider(
            connect_timeout_s=getattr(settings, "llm_connect_timeout_s", None),
            read_timeout_s=getattr(settings, "llm_read_timeout_s", None),
        ),
        scope="bedrock/",
    )
    _registered = True
