from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Optional, TypeVar, overload

from dependency_injector.wiring import Provide, inject
from langfuse import get_client, observe
from mirascope import llm
from mirascope.llm.exceptions import ParseError

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

    Retries on ParseError (validation failures) with exponential backoff.
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
            rate_delay = 30.0
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
                        return response.parse()
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
                            "Rate limit hit (attempt %d/%d), backing off %.0fs",
                            attempt + 1, attempts, rate_delay,
                        )
                        if attempt < attempts - 1:
                            await asyncio.sleep(rate_delay)
                            rate_delay = min(rate_delay * 2.0, 300.0)
                    else:
                        raise

            raise last_error  # type: ignore[misc]

        return wrapper

    return decorator


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
