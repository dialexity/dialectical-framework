"""
Auto-construct Pydantic response models without calling an LLM.

Patches ConversationFacilitator and use_brain so that tests exercise
all internal logic (graph mutations, validation, normalization) but
skip the actual inference call.

Usage in conftest.py:
    @pytest.fixture(autouse=True)
    def mock_llm(monkeypatch):
        install_mock_brain(monkeypatch)
"""

from __future__ import annotations

from typing import Any, Literal, Optional, get_args, get_origin
from unittest.mock import AsyncMock

from pydantic import BaseModel
from pydantic.fields import FieldInfo

#: What the mocked tools call "says". Under the reply-reuse shortcut this is the
#: text a mocked `ChatResponse.message` carries, so a test asserting on a mocked
#: agent reply asserts on THIS rather than on `build_mock_response`'s field-name
#: placeholder.
MOCK_REPLY_TEXT = "mocked response"


def build_mock_response(model: type[BaseModel]) -> BaseModel:
    """
    Construct a plausible instance of a Pydantic model using field metadata.

    Handles:
    - float with ge/le constraints (picks midpoint)
    - Optional fields (uses None)
    - str fields (uses field name as placeholder)
    - bool fields (uses False)
    - int fields (uses 0)
    - list fields (uses empty list)
    - Nested BaseModel fields (recurses)
    """
    kwargs: dict[str, Any] = {}

    for name, field_info in model.model_fields.items():
        kwargs[name] = _build_field_value(name, field_info)

    return model(**kwargs)


def _build_field_value(name: str, field_info: FieldInfo) -> Any:
    annotation = field_info.annotation

    if annotation is None:
        return None

    # Unwrap Optional[X] → X, but allow None if optional
    origin = get_origin(annotation)
    if _is_optional(annotation):
        if field_info.default is not None:
            return field_info.default
        return None

    # Handle list[X]
    if origin is list:
        return []

    # Handle dict[K, V]
    if origin is dict:
        return {}

    # Handle Literal["a", "b", ...] — pick the first allowed value so
    # constrained DTO fields (e.g. taxonomy branch enums) stay valid.
    if origin is Literal:
        return get_args(annotation)[0]

    # Concrete types
    if annotation is float or annotation is int:
        return _numeric_value(name, field_info, annotation)
    if annotation is str:
        return name
    if annotation is bool:
        return False

    # Nested Pydantic model
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return build_mock_response(annotation)

    # Fallback
    if field_info.default is not None:
        return field_info.default
    return None


def _numeric_value(name: str, field_info: FieldInfo, typ: type) -> float | int:
    lo = _get_metadata_value(field_info, "ge", "gt")
    hi = _get_metadata_value(field_info, "le", "lt")

    if lo is not None and hi is not None:
        mid = (lo + hi) / 2
    elif lo is not None:
        mid = lo + 1
    elif hi is not None:
        mid = hi - 1
    else:
        mid = 0.5 if typ is float else 0

    return typ(mid)


def _get_metadata_value(field_info: FieldInfo, *attr_names: str) -> Optional[float]:
    for md in field_info.metadata:
        for attr in attr_names:
            val = getattr(md, attr, None)
            if val is not None:
                return float(val)
    return None


def _is_optional(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is not None:
        import typing
        # Union[X, None] is Optional[X]
        if origin is typing.Union:
            args = get_args(annotation)
            return type(None) in args
    return False


def install_mock_brain(monkeypatch: Any) -> None:
    """
    Patch ConversationFacilitator and use_brain to skip real LLM calls.

    ConversationFacilitator._call_with_response_model is replaced with
    a function that auto-constructs the response_model.

    use_brain decorator is replaced with a passthrough that, when
    format/response_model is set, auto-constructs it instead of calling the LLM.
    """
    from mirascope import llm

    from dialectical_framework.agents import conversation_facilitator as cf_mod
    from dialectical_framework.utils import use_brain as ub_mod

    # --- Patch ConversationFacilitator ---

    async def _mock_call_with_response_model(self: Any, response_model: type) -> Any:
        result = build_mock_response(response_model)
        self._messages.append(
            llm.messages.assistant(
                cf_mod.ConversationFacilitator._assistant_history_text(result),
                model_id=None,
                provider_id=None,
            )
        )
        return result

    monkeypatch.setattr(
        cf_mod.ConversationFacilitator,
        "_call_with_response_model",
        _mock_call_with_response_model,
    )

    # --- Patch use_brain ---

    def mock_use_brain(*, ai_model=None, retry_max=10, format=None, tools=None, thinking=None, raw_call=False, **llm_call_kwargs):
        format_model = format

        def decorator(method):
            async def wrapper(*args, **kwargs):
                if format_model is not None and isinstance(format_model, type) and issubclass(format_model, BaseModel):
                    return build_mock_response(format_model)

                # No format — an AsyncResponse-like stand-in for the tools call.
                #
                # `messages` and `text()` are faithful on purpose. The tool path
                # now BUILDS its reply from this response
                # (`ConversationFacilitator._reuse_written_reply`) rather than
                # paying a second structured call, so a stand-in with
                # `messages = []` would wipe mocked conversation history — the
                # facilitator syncs `self._messages` from here — and a stand-in
                # with no text would route every mocked test down the fallback,
                # hiding the path production actually takes. The decorated
                # function returns its own input messages, which is how this
                # learns what the conversation was.
                input_messages = await method(*args, **kwargs)
                mock = AsyncMock()
                mock.text = lambda: MOCK_REPLY_TEXT
                mock.tool_calls = []
                mock.content = MOCK_REPLY_TEXT
                mock.messages = [
                    *(input_messages if isinstance(input_messages, list) else []),
                    llm.messages.assistant(
                        MOCK_REPLY_TEXT, model_id=None, provider_id=None
                    ),
                ]
                return mock

            return wrapper

        return decorator

    monkeypatch.setattr(ub_mod, "use_brain", mock_use_brain)

    # Also patch use_brain where it's imported by name (direct binding)
    from dialectical_framework.agents import conversation_facilitator as cf_use_brain_mod
    from dialectical_framework.agents.explorer.skills import build_wheels as bw_mod
    from dialectical_framework.concerns.causality import causality_estimator_balanced as ceb_mod

    monkeypatch.setattr(cf_use_brain_mod, "use_brain", mock_use_brain)
    monkeypatch.setattr(bw_mod, "use_brain", mock_use_brain)
    monkeypatch.setattr(ceb_mod, "use_brain", mock_use_brain)
