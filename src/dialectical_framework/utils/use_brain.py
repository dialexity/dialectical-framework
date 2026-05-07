from __future__ import annotations

import asyncio
from functools import wraps
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, TypeVar, overload

from dependency_injector.wiring import Provide, inject
from langfuse import get_client, observe
from mirascope import llm
from mirascope.llm.exceptions import ParseError

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.utils.bedrock_provider import ensure_bedrock_provider

if TYPE_CHECKING:
    from mirascope.llm.responses import AsyncResponse

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


@overload
def use_brain(
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    *,
    format: type[T],
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[T]]]: ...


@overload
def use_brain(
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[AsyncResponse]]]: ...


def use_brain(
    ai_model: Optional[str] = None,
    retry_max: int = 10,
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
        **llm_call_kwargs: Additional kwargs for @llm.call (temperature, max_tokens, etc.)
    """

    def decorator(method: F) -> Callable[..., Any]:
        @wraps(method)
        @observe(as_type="generation")
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            resolved = ai_model
            if resolved is None:
                resolved = _get_ai_model()

            if resolved.startswith("bedrock/"):
                ensure_bedrock_provider()

            call_params: dict[str, Any] = {}
            if "response_model" in llm_call_kwargs:
                call_params["format"] = llm_call_kwargs["response_model"]
            elif "format" in llm_call_kwargs:
                call_params["format"] = llm_call_kwargs["format"]
            if "tools" in llm_call_kwargs:
                call_params["tools"] = llm_call_kwargs["tools"]

            for key in ("temperature", "max_tokens", "top_p", "top_k", "seed", "stop_sequences", "thinking"):
                if key in llm_call_kwargs:
                    call_params[key] = llm_call_kwargs[key]

            has_format = "format" in call_params
            format_name = call_params["format"].__name__ if has_format else None

            @llm.call(resolved, **call_params)
            async def _llm_call() -> Any:
                return await method(*args, **kwargs)

            attempts = max(1, retry_max)
            delay = 10.0
            last_error: Optional[ParseError] = None

            for attempt in range(attempts):
                try:
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
                        await asyncio.sleep(delay)
                        delay = min(delay * 2.0, 120.0)

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

        input_messages = [_serialize_message(m) for m in response.input_messages]
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
    except Exception:
        pass


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


@inject
def _get_ai_model(settings: Settings = Provide[DI.settings]) -> str:
    return settings.ai_model
