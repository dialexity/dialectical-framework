from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.ideas import Ideas
    from dialectical_framework.graph.nodes.input import Input


class ThesisExtractor(Protocol):
    """
    Protocol for extracting thesis concepts from Input or Ideas.

    Extractors are standalone services that:
    1. Resolve content from source (Input or Ideas) via InputResolver
    2. Extract thesis concepts from content
    3. Create DialecticalComponent graph nodes
    4. Connect components to source.statements (HAS_STATEMENT)
    5. Return the created graph nodes
    """

    @abstractmethod
    async def extract_multiple_theses(
        self,
        *,
        source: Union[Input, Ideas],
        count: int = 2,
        not_like_these: list[str] | None = None,
    ) -> list[DialecticalComponent]:
        """
        Extract multiple thesis concepts from source.

        Args:
            source: Input or Ideas node to extract from and attach results to
            count: Number of theses to extract (1-4)
            not_like_these: Statements to avoid duplicating

        Returns:
            List of DialecticalComponent graph nodes (connected to source.statements)
        """
        ...

    @abstractmethod
    async def extract_single_thesis(
        self,
        *,
        source: Union[Input, Ideas],
        not_like_these: list[str] | None = None,
    ) -> DialecticalComponent:
        """
        Extract a single thesis concept from source.

        Args:
            source: Input or Ideas node to extract from and attach results to
            not_like_these: Statements to avoid duplicating

        Returns:
            DialecticalComponent graph node (connected to source.statements)
        """
        ...
