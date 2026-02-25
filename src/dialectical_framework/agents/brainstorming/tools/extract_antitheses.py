"""
ExtractAntitheses: Tool wrapper for AntithesisExtractor service.

Thin wrapper that:
1. Resolves thesis hash to component
2. Calls AntithesisExtractor service
3. Formats RunReport for LLM orchestrator

The service (AntithesisExtractor) contains all business logic and returns RunReport.
This tool just adapts it for LLM consumption.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from mirascope import BaseTool
from pydantic import Field

from dialectical_framework.agents.brainstorming.services.antithesis_extractor import (
    AntithesisExtractor,
)
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.repositories.node_repository import NodeRepository

if TYPE_CHECKING:
    pass


class ExtractAntitheses(BaseTool):
    """
    Extract antitheses for a thesis.

    Resolves thesis hash and delegates to AntithesisExtractor service.
    Returns formatted report for LLM orchestrator.
    """

    thesis_hash: str = Field(description="Hash of thesis to generate antitheses for")
    text: str = Field(default="", description="Source content context for antithesis generation")
    not_like_these: list[str] = Field(
        default_factory=list,
        description="Statements to avoid (for dedup)"
    )

    async def call(self) -> str:
        """Extract antitheses and return formatted report."""
        # 1. Resolve thesis
        thesis = self._resolve_thesis()
        if thesis is None:
            return f"ERROR: Thesis with hash '{self.thesis_hash}' not found"

        # 2. Call service
        service = AntithesisExtractor()
        report = await service.extract(
            thesis=thesis,
            text=self.text,
            not_like_these=self.not_like_these,
        )

        # 3. Return JSON for LLM to parse
        return report.model_dump_json(indent=2)

    def _resolve_thesis(self) -> Optional[DialecticalComponent]:
        """Resolve thesis hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(
                self.thesis_hash, node_type=DialecticalComponent
            )
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None
