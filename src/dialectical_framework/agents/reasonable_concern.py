"""
ReasonableConcern: Base for all concerns, skills, and tools.

Concern = standalone service, wrappable as a tool.
Skill = workflow that uses concerns, itself exposed as a tool.
Agent = orchestrator with tools + skills, itself a tool.

All three levels inherit from ReasonableConcern — same interface (resolve + report).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import ExecutionReport

R_co = TypeVar("R_co", covariant=True)


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
