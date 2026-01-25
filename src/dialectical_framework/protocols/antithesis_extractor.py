from __future__ import annotations

from abc import abstractmethod

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import DialecticalComponentsDeckDto
from dialectical_framework.protocols.reloadable import Reloadable


class AntithesisExtractor(Reloadable):
    """
    Protocol for extracting antithesis concepts from thesis statements.

    All methods return DTOs - conversion to graph nodes happens in the reasoning layer.
    """

    @abstractmethod
    async def extract_single_antithesis(
        self, *, thesis: str, not_like_these: list[str] | None = None
    ) -> DialecticalComponentDto:
        """
        Extract a single antithesis for the given thesis.

        Args:
            thesis: The thesis statement to generate an antithesis for
            not_like_these: Optional list of statements to avoid duplicating

        Returns:
            DialecticalComponentDto with the generated antithesis
        """
        ...

    @abstractmethod
    async def extract_multiple_antitheses(
        self, *, theses: list[str], not_like_these: list[str] | None = None
    ) -> DialecticalComponentsDeckDto:
        """
        Extract antitheses for multiple theses in batch.

        Args:
            theses: List of thesis statements to generate antitheses for
            not_like_these: Optional list of statements to avoid duplicating

        Returns:
            DialecticalComponentsDeckDto with the generated antitheses
        """
        ...
