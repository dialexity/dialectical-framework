from __future__ import annotations

import asyncio
import json
import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Optional, TypeVar, overload

from dependency_injector.wiring import Provide, inject
from langfuse import get_client, observe
from mirascope import llm
from mirascope.llm.exceptions import ParseError
from mirascope.llm.responses import _utils
from pydantic import ValidationError as PydanticValidationError

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.utils.bedrock_provider import ensure_bedrock_provider
from dialectical_framework.utils.concurrency import llm_concurrency_slot

if TYPE_CHECKING:
    from mirascope.llm.calls import AsyncCall
    from mirascope.llm.responses import AsyncResponse

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


@overload
def use_brain(
    *,
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    format: type[T],
    tools: Optional[list[Any]] = ...,
    thinking: Optional[str | dict[str, Any]] = ...,
    raw_call: bool = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[T]]]: ...


@overload
def use_brain(
    *,
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    raw_call: Literal[True],
    format: Optional[type] = ...,
    tools: Optional[list[Any]] = ...,
    thinking: Optional[str | dict[str, Any]] = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[AsyncCall]]]: ...


@overload
def use_brain(
    *,
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    tools: Optional[list[Any]] = ...,
    thinking: Optional[str | dict[str, Any]] = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[AsyncResponse]]]: ...


def use_brain(
    *,
    ai_model: Optional[str] = None,
    retry_max: int = 10,
    format: Optional[type] = None,
    tools: Optional[list[Any]] = None,
    thinking: Optional[str | dict[str, Any]] = None,
    raw_call: bool = False,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Any]]:
    """
    Decorator factory for Mirascope v2 LLM calls.

    Retries on ParseError (validation failures) with exponential backoff, on
    rate limits / throttling, and on transient connection failures (each with
    its own curve — see `_is_connection_error`).
    Automatically traces all LLM calls via Langfuse when configured.

    When ``format`` is provided, returns the parsed model instance.
    Otherwise returns the raw AsyncResponse (useful for tool calls).

    Args:
        ai_model: Model ID (e.g., 'bedrock/anthropic/claude-...'). Reads from DI if not provided.
        retry_max: Maximum attempts (default: 10). Set to 1 to disable retries.
        format: Pydantic model class for structured output.
        tools: List of tool functions/classes to make available.
        thinking: Extended thinking level string ("medium", "high", etc.)
            or a dict ({"level": "high", ...}). include_thoughts=True is added automatically.
        raw_call: If True, returns AsyncCall for caller to .stream() or await.
        **llm_call_kwargs: Additional kwargs for @llm.call (temperature, max_tokens, etc.)
    """

    def decorator(method: F) -> Callable[..., Any]:
        @wraps(method)
        @observe(as_type="generation", name=method.__qualname__, capture_input=False)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            resolved = ai_model
            if resolved is None:
                resolved = _get_ai_model()

            if resolved.startswith("bedrock/"):
                ensure_bedrock_provider()

            call_params: dict[str, Any] = {}
            if format is not None:
                call_params["format"] = format
            if tools is not None:
                call_params["tools"] = tools

            if thinking is not None:
                if isinstance(thinking, str):
                    call_params["thinking"] = {"level": thinking, "include_thoughts": True}
                else:
                    thinking.setdefault("include_thoughts", True)
                    call_params["thinking"] = thinking

            for key in ("temperature", "max_tokens", "top_p", "top_k", "seed", "stop_sequences"):
                if key in llm_call_kwargs:
                    call_params[key] = llm_call_kwargs[key]

            has_format = "format" in call_params
            format_name = call_params["format"].__name__ if has_format else None

            @llm.call(resolved, **call_params)
            async def _llm_call() -> Any:
                return await method(*args, **kwargs)

            # raw_call mode: return the AsyncCall for caller to .stream() or await.
            # Skips retry and Langfuse _trace_generation intentionally:
            # - Retry: stream lifecycle is owned by the caller (submit_stream retries
            #   at the connection level, not per-token)
            # - Tracing: @observe() on submit_stream creates the span; detailed token
            #   usage requires post-consumption stats not available here
            if raw_call:
                return _llm_call

            attempts = max(1, retry_max)
            parse_delay = 10.0
            rate_delay = 10.0
            connect_delay = _CONNECT_RETRY_BASE_S
            connect_attempts = 0
            server_delay = _SERVER_RETRY_BASE_S
            server_attempts = 0
            last_error: Exception | None = None

            for attempt in range(attempts):
                try:
                    async with llm_concurrency_slot():
                        response = await _llm_call()
                    _trace_generation(
                        response=response,
                        model=resolved,
                        format_name=format_name,
                        caller=method.__qualname__,
                        attempt=attempt + 1,
                    )
                    if has_format:
                        try:
                            return response.parse()
                        except ParseError as e:
                            salvaged = _salvage_double_encoded(
                                response, call_params["format"], e
                            )
                            if salvaged is not None:
                                return salvaged
                            raise
                    return response
                except ParseError as e:
                    last_error = e
                    if attempt < attempts - 1:
                        await asyncio.sleep(parse_delay)
                        parse_delay = min(parse_delay * 2.0, 120.0)
                except Exception as e:
                    if _is_rate_limit_error(e):
                        last_error = e
                        logging.getLogger(__name__).warning(
                            "Rate limit hit (attempt %d/%d), backing off %.0fs: %s",
                            attempt + 1, attempts, rate_delay, e,
                        )
                        if attempt < attempts - 1:
                            await asyncio.sleep(rate_delay)
                            rate_delay = min(rate_delay * 2.0, 60.0)
                    elif _is_connection_error(e):
                        # Bounded separately from `attempts`: a down endpoint must
                        # surface as an error, not consume the whole retry budget.
                        connect_attempts += 1
                        if connect_attempts >= _CONNECT_RETRY_MAX:
                            raise
                        last_error = e
                        logging.getLogger(__name__).warning(
                            "Connection error (attempt %d/%d), retrying in %.0fs: %s",
                            connect_attempts, _CONNECT_RETRY_MAX, connect_delay, e,
                        )
                        if attempt < attempts - 1:
                            await asyncio.sleep(connect_delay)
                            connect_delay *= 2.0
                    elif _is_transient_server_error(e):
                        # Bounded separately, same reasoning as connection
                        # errors: a persistent 5xx is an outage and must surface.
                        server_attempts += 1
                        if server_attempts >= _SERVER_RETRY_MAX:
                            raise
                        last_error = e
                        logging.getLogger(__name__).warning(
                            "Provider %d/%d unavailable, retrying in %.0fs: %s",
                            server_attempts, _SERVER_RETRY_MAX, server_delay, e,
                        )
                        if attempt < attempts - 1:
                            await asyncio.sleep(server_delay)
                            server_delay *= 2.0
                    else:
                        raise

            raise last_error  # type: ignore[misc]

        return wrapper

    return decorator


def _salvage_double_encoded(response: Any, format: type, error: ParseError) -> Any:
    """Recover a structured result the model returned double-encoded.

    Some models (observed: sonnet-5 on Bedrock) serialize the WHOLE response
    object a second time and hand that string back as the value of the first
    field, so the wire payload is::

        {"matches": "{\\"matches\\": [{...}]}"}

    Pydantic then rejects the field (`Input should be a valid array`,
    `input_type=str`) even though every byte of the answer is present. The
    content is right; only one layer of encoding is wrong.

    Salvaged here rather than left to the retry loop because the retry is the
    expensive part: a re-ask is a fresh sample of the same model tendency, so
    it usually fails again, and `parse_delay` (10s doubling to a 120s cap over
    `retry_max` attempts) turns one such call into 10+ minutes before it raises.
    Nested inside a pipeline that is hours, and the framework arm looks
    catastrophically slow when the model in fact answered correctly the first
    time. Measured: a single `anchor` on sonnet-5 took 857s and then failed,
    against ~33s on haiku.

    Deliberately narrow — a genuinely malformed or truncated response must still
    raise and still retry, so the inner value has to look like a re-encoding of
    this very model: it must validate against it AND name at least one of its
    fields. Validation alone is too weak a test, because DTOs whose fields all
    have defaults (`SemanticDedupDto.matches` among them) accept ANY JSON
    object — unrelated JSON in a string field would otherwise be "salvaged"
    into a silently empty result, which is worse than the parse error it
    replaces. Returns None when the shape does not match, leaving the caller's
    `raise` intact.
    """
    if not isinstance(error.original_exception, PydanticValidationError):
        return None

    try:
        raw = json.loads(_utils.extract_serialized_json(response.text("")))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None

    fields = set(format.model_fields)
    for value in raw.values():
        if not isinstance(value, str):
            continue
        try:
            inner = json.loads(value)
        except Exception:
            continue
        if not isinstance(inner, dict) or not fields & set(inner):
            continue
        try:
            salvaged = format.model_validate(inner)
        except Exception:
            continue
        logging.getLogger(__name__).warning(
            "Model returned %s double-encoded (whole object as a string inside a "
            "field); unwrapped one layer instead of retrying.",
            format.__name__,
        )
        return salvaged
    return None


def _trace_generation(
    response: Any,
    model: str,
    format_name: Optional[str],
    caller: str,
    attempt: int,
) -> None:
    """Report a completed LLM generation to Langfuse (if active)."""
    try:
        lf = get_client()

        usage_details: Optional[dict[str, int]] = None
        if response.usage:
            usage_details = {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            }
            if response.usage.cache_read_tokens:
                usage_details["cache_read"] = response.usage.cache_read_tokens
            if response.usage.cache_write_tokens:
                usage_details["cache_write"] = response.usage.cache_write_tokens

        input_messages = [_serialize_message(m) for m in response.messages[:-1]]
        output_text = response.text if response.texts else str(response.tool_calls)

        metadata: dict[str, Any] = {"caller": caller, "attempt": attempt}
        if format_name:
            metadata["format"] = format_name

        lf.update_current_generation(
            model=model,
            input=input_messages,
            output=output_text,
            usage_details=usage_details,
            metadata=metadata,
        )
    except Exception as e:
        logging.getLogger(__name__).debug("Langfuse trace failed: %s", e)


def _serialize_message(msg: Any) -> dict[str, Any]:
    """Best-effort serialization of a Mirascope message for Langfuse."""
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "role") and hasattr(msg, "content"):
        content = msg.content
        if isinstance(content, list):
            parts = []
            for part in content:
                if hasattr(part, "text"):
                    parts.append(part.text)
                else:
                    parts.append(str(part))
            content = "\n".join(parts)
        return {"role": msg.role, "content": str(content)}
    return {"content": str(msg)}


#: Retry curve for transient connection failures. Shorter and shallower than the
#: throttle curve on purpose: throttling means "the service told us to wait", so
#: waiting long is the correct response, while a connect failure is usually a
#: momentary link glitch that either clears in seconds or is a real outage no
#: amount of waiting fixes. Capped attempts so a genuinely-down endpoint still
#: surfaces as an error instead of hanging a pipeline for minutes.
_CONNECT_RETRY_MAX = 3
_CONNECT_RETRY_BASE_S = 2.0


def _is_connection_error(e: Exception) -> bool:
    """Detect transient network failures worth retrying.

    Real failure this catches: the framework's parallel stages
    (ExplorationPipeline, ExploreTransformations) open many connections at once,
    so a single cold-connect blip took down an entire agent turn — every call in
    the gather died together and the turn recorded as "the model produced
    nothing", which reads as a weak model rather than a network fault.

    Matched by class name, not by import: Mirascope re-raises provider
    exceptions as its own `mirascope.llm.exceptions.ConnectionError`/`TimeoutError`,
    and importing those shadows the builtins in this module.
    """
    name = type(e).__name__
    if name in ("ConnectionError", "TimeoutError", "APIConnectionError", "APITimeoutError"):
        return True
    # httpx raises distinct classes per phase (ConnectTimeout, ReadTimeout,
    # ConnectError, RemoteProtocolError); the shared suffix is the reliable tell.
    return name.endswith(("ConnectError", "ConnectTimeout", "ReadTimeout"))


#: Provider-side transient failures: the request was well-formed and the service
#: simply could not take it right now. Bounded like connection errors rather than
#: like throttles — a 500/503 that persists is an outage, and burning the full
#: `retry_max` budget on one would hang a pipeline for minutes.
_SERVER_RETRY_MAX = 3
_SERVER_RETRY_BASE_S = 5.0


def _is_transient_server_error(e: Exception) -> bool:
    """Detect a provider saying "not now" — 500/502/503/504.

    Real failure this catches: a single Bedrock 503 ("Bedrock is unable to
    process your request") killed three turns of a bench baseline arm, which
    records as an arm that produced nothing and reads as a weak model rather than
    a provider blip — the identical misdiagnosis `_is_connection_error` exists to
    prevent, arriving one layer higher. Silently degrading the BASELINE is worse
    than degrading the framework arm: it inflates every framework-vs-baseline
    delta with nobody touching a framework number.

    Deliberately NOT matching 4xx: those are our bug (bad request, auth, too
    large) and retrying them wastes the budget and hides the cause. 429 is
    excluded here too — it has its own, longer backoff curve.
    """
    status = getattr(e, "status_code", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    # Bedrock/Mirascope frequently surface the status only in the message
    # ("Error code: 503 - {'message': 'Bedrock is unable to process...'}"), so
    # the class name and attribute are not enough on their own.
    msg = str(e)
    if any(f"code: {code}" in msg for code in (500, 502, 503, 504)):
        return True
    return (
        "ServiceUnavailable" in msg
        or "InternalServerException" in msg
        or "ModelNotReadyException" in msg
    )


def _is_rate_limit_error(e: Exception) -> bool:
    """Detect rate-limit / throttling errors from various providers."""
    if hasattr(e, "status_code") and getattr(e, "status_code", None) == 429:
        return True
    msg = str(e)
    if "ThrottlingException" in msg or "TooManyRequests" in msg:
        return True
    if "rate" in msg.lower() and ("limit" in msg.lower() or "exceeded" in msg.lower()):
        return True
    return False


@inject
def _get_ai_model(settings: Settings = Provide[DI.settings]) -> str:
    return settings.ai_model
