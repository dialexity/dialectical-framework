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

from typing import Any, Optional, get_args, get_origin
from unittest.mock import AsyncMock

from pydantic import BaseModel
from pydantic.fields import FieldInfo


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
    response_model is set, auto-constructs it instead of calling the LLM.
    """
    from dialectical_framework.agents import conversation_facilitator as cf_mod
    from dialectical_framework.utils import use_brain as ub_mod

    # --- Patch ConversationFacilitator ---

    async def _mock_call_with_response_model(self: Any, response_model: type) -> Any:
        result = build_mock_response(response_model)
        from mirascope import Messages
        self._messages.append(Messages.Assistant(str(result)))
        return result

    monkeypatch.setattr(
        cf_mod.ConversationFacilitator,
        "_call_with_response_model",
        _mock_call_with_response_model,
    )

    # --- Patch use_brain ---

    def mock_use_brain(brain=None, retry_max=10, **llm_call_kwargs):
        response_model = llm_call_kwargs.get("response_model")

        def decorator(method):
            async def wrapper(*args, **kwargs):
                if response_model is not None and isinstance(response_model, type) and issubclass(response_model, BaseModel):
                    return build_mock_response(response_model)
                # No response_model — return a mock CallResponse-like object
                mock = AsyncMock()
                mock.content = "mocked response"
                mock.tools = []
                return mock

            return wrapper

        return decorator

    monkeypatch.setattr(ub_mod, "use_brain", mock_use_brain)
