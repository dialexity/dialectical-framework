"""
ReasonableConcern: Base for all concerns, skills, and tools.

Concern = standalone service, wrappable as a tool.
Skill = workflow that uses concerns, itself exposed as a tool.
Agent = orchestrator with tools + skills, itself a tool.

All three levels inherit from ReasonableConcern — same interface (resolve + report).
"""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod
from functools import wraps
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from langfuse import get_client, observe

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import ExecutionReport

R_co = TypeVar("R_co", covariant=True)


def _conditional_observe(name: str, fn: Any) -> Any:
    """Wrap fn with @observe only when an active Langfuse trace exists."""
    observed = observe(name=name)(fn)

    if asyncio.iscoroutinefunction(fn):
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_client().get_current_trace_id():
                return await observed(*args, **kwargs)
            return await fn(*args, **kwargs)
    else:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if get_client().get_current_trace_id():
                return observed(*args, **kwargs)
            return fn(*args, **kwargs)

    return wrapper


class ReasonableConcern(ABC, Generic[R_co]):
    """
    Base class for concerns, skills, and tools.

    Subclasses implement resolve() with specific parameters and return type.
    Report is available via .report property after resolution.

    Usage:
        concern = ThesisExtraction()
        theses = await concern.resolve(text=text, count=4)
        print(concern.report)
    """

    _report: ExecutionReport

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "resolve" in cls.__dict__:
            original = cls.__dict__["resolve"]
            cls.resolve = _conditional_observe(cls.__name__, original)  # type: ignore[assignment]

    def __getattr__(self, name: str) -> Any:
        if name == "_report":
            from dialectical_framework.agents.execution_report import ExecutionReport
            report = ExecutionReport(tool=self.__class__.__name__)
            object.__setattr__(self, "_report", report)
            return report
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @property
    def report(self) -> ExecutionReport:
        """Access the report. Lazily initialized with class name."""
        return self._report

    @abstractmethod
    async def resolve(self, *args: Any, **kwargs: Any) -> R_co:
        """
        Resolve the concern.

        Subclasses define specific parameters via overloaded signatures.

        Returns:
            Domain objects (type specified by generic parameter)
        """
        raise NotImplementedError
