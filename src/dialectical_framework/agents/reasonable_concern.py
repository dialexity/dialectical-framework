"""
ReasonableConcern: Abstract base for concerns with report tracking.

All concerns inherit from this and implement resolve().
The report is reset on each resolution, allowing instance reuse.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import ExecutionReport

R_co = TypeVar("R_co", covariant=True)


class ReasonableConcern(ABC, Generic[R_co]):
    """
    Base class for concerns.

    Subclasses implement resolve() with specific parameters and return type.
    Report is available via .report property after resolution.

    Usage:
        # Programmatic (web app)
        concern = ThesisExtraction()
        theses = await concern.resolve(text=text, count=4)
        for t in theses:
            print(t.statement)

        # With report access
        concern = AntithesisExtraction()
        antitheses = await concern.resolve(thesis=t, text=text)
        print(concern.report.heuristic_similarity_by_hash)

        # LLM orchestrator
        concern = ThesisExtraction()
        await concern.resolve(text=text, count=4)
        return concern.report.model_dump_json()
    """

    _report: ExecutionReport

    @property
    def report(self) -> ExecutionReport:
        """Access the report from the last resolution."""
        return self._report

    @abstractmethod
    async def resolve(self, *args: Any, **kwargs: Any) -> R_co:
        """
        Resolve the concern.

        Subclasses define specific parameters via overloaded signatures.
        Must reset self._report at the start of resolution.

        Returns:
            Domain objects (type specified by generic parameter)
        """
        raise NotImplementedError
