from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.ideas import Ideas
    from dialectical_framework.graph.nodes.input import Input


class AntithesisExtractor(ABC):
    """
    Abstract base class for extracting antithesis concepts from thesis statements.

    Extractors are standalone services that:
    1. Resolve content from source (Input or Ideas) via InputResolver
    2. Extract antithesis concepts for given thesis
    3. Create DialecticalComponent graph nodes
    4. Connect components to source.statements (HAS_STATEMENT)
    5. Return the created graph nodes
    """

    @abstractmethod
    async def extract_single_antithesis(
        self,
        *,
        source: Input | Ideas,
        thesis: DialecticalComponent | str,
        not_like_these: list[str] | None = None,
    ) -> DialecticalComponent:
        """
        Extract a single antithesis for the given thesis.

        Args:
            source: Input or Ideas node to extract from and attach results to
            thesis: The thesis to generate an antithesis for (graph node or string)
            not_like_these: Optional list of statements to avoid duplicating

        Returns:
            DialecticalComponent graph node (connected to source.statements)
        """
        ...

    @abstractmethod
    async def extract_multiple_antitheses(
        self,
        *,
        source: Input | Ideas,
        theses: list[DialecticalComponent | str],
        not_like_these: list[str] | None = None,
    ) -> list[DialecticalComponent]:
        """
        Extract antitheses for multiple theses in batch.

        Args:
            source: Input or Ideas node to extract from and attach results to
            theses: List of thesis statements to generate antitheses for
            not_like_these: Optional list of statements to avoid duplicating

        Returns:
            List of DialecticalComponent graph nodes (connected to source.statements)
        """
        ...
