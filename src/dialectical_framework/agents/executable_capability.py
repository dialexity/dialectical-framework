"""
ExecutableCapability: Abstract base for capabilities with report tracking.

All capabilities inherit from this and implement execute().
The report is reset on each execution, allowing instance reuse.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import ExecutionReport

R_co = TypeVar("R_co", covariant=True)


class ExecutableCapability(ABC, Generic[R_co]):
    """
    Base class for capabilities.

    Subclasses implement execute() with specific parameters and return type.
    Report is available via .report property after execution.

    Usage:
        # Programmatic (web app)
        service = ThesisExtraction()
        theses = await service.execute(text=text, count=4)
        for t in theses:
            print(t.statement)

        # With report access
        service = AntithesisExtraction()
        antitheses = await service.execute(thesis=t, text=text)
        print(service.report.heuristic_similarity_by_hash)

        # LLM orchestrator
        service = ThesisExtraction()
        await service.execute(text=text, count=4)
        return service.report.model_dump_json()
    """

    _report: ExecutionReport

    @property
    def report(self) -> ExecutionReport:
        """Access the report from the last execution."""
        return self._report

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> R_co:
        """
        Run the capability.

        Subclasses define specific parameters via overloaded signatures.
        Must reset self._report at the start of execution.

        Returns:
            Domain objects (type specified by generic parameter)
        """
        raise NotImplementedError
