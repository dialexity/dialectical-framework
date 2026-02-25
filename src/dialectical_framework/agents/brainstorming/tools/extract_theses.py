"""
ExtractTheses: Tool wrapper for ThesisExtractor service.

Thin wrapper that:
1. Calls ThesisExtractor service with parameters
2. Formats RunReport for LLM orchestrator

The service (ThesisExtractor) contains all business logic and returns RunReport.
This tool just adapts it for LLM consumption.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mirascope import BaseTool
from pydantic import Field

from dialectical_framework.agents.brainstorming.services.thesis_extractor import (
    ThesisExtractor,
)

if TYPE_CHECKING:
    pass


class ExtractTheses(BaseTool):
    """
    Extract thesis concepts following polarity-finder Phase 1 algorithm.

    Handles both direct thesis and content extraction:
    - Short input ("Love") → treated as direct thesis
    - Long input → extract multiple theses from content

    Returns formatted report for LLM orchestrator.
    """

    text: str = Field(
        description="Source content to extract from, OR direct thesis statement"
    )
    count: int = Field(
        default=3, description="Maximum number of theses to extract (1-4)"
    )
    focus: str = Field(
        default="",
        description="Filter for extraction: 'security', 'design decisions', etc.",
    )
    domain_hint: str = Field(
        default="", description="Taxonomy domain hint: 'Engineering', 'Love', etc."
    )
    not_like_these: list[str] = Field(
        default_factory=list, description="Existing statements to avoid"
    )

    async def call(self) -> str:
        """Extract theses and return JSON report."""
        # Call service
        service = ThesisExtractor()
        report = await service.extract(
            text=self.text,
            count=self.count,
            focus=self.focus,
            domain_hint=self.domain_hint,
            not_like_these=self.not_like_these,
        )

        # Return JSON for LLM to parse
        return report.model_dump_json(indent=2)
