"""
Abstract base class for resolving Input nodes to text content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.brainstorm import Brainstorm
    from dialectical_framework.graph.nodes.input import Input


class InputResolver(ABC):
    """
    Resolves Input or Brainstorm nodes to text content.

    Apps implement this class to handle their specific content sources
    (uploaded files, URLs, session storage, etc.).

    The resolver receives the Input node and can traverse the graph to access
    related context (e.g., Ideas.intent for RAG relevance hints).

    Example:
        class MyAppResolver(InputResolver):
            async def resolve(self, input_node: Input) -> str:
                content = input_node.content
                if content.startswith("session://"):
                    return await self._cache.get(content)
                raise ValueError(f"Unknown scheme: {content}")

        container.input_resolver.override(providers.Singleton(MyAppResolver))
    """

    @abstractmethod
    async def resolve(self, input_node: Input) -> str:
        """
        Resolve single Input.content to text content.

        Args:
            input_node: Input node with content to resolve (plain text, URI, etc.).
                        Can traverse to Ideas via input_node.ideas for intent hints.

        Returns:
            Text content (either as-is or resolved from URI).
            May return empty string if content is None (implementation-dependent).

        Raises:
            ValueError: If content format is unsupported (implementation-dependent)
        """
        ...

    @abstractmethod
    async def resolve_all(self, source: Brainstorm | list[Input]) -> str:
        """
        Resolve multiple inputs to combined text content.

        Args:
            source: Either a Brainstorm node (resolves all connected Inputs)
                   or a list of Input nodes to resolve

        Returns:
            Combined text content from all inputs.
            Implementation decides how to format/combine the content.

        Raises:
            ValueError: If no inputs provided to resolve
        """
        ...
