"""
Protocol for resolving Input nodes to text content.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input


class InputResolver(Protocol):
    """
    Resolves Input.content_uri to text content.

    Apps implement this protocol to handle their specific content sources
    (uploaded files, URLs, session storage, etc.).

    The resolver receives the Input node and can traverse the graph to access
    related context (e.g., Ideas.intent for RAG relevance hints).

    Example:
        class MyAppResolver(InputResolver):
            async def resolve(self, input_node: Input) -> str:
                uri = input_node.content_uri
                if uri.startswith("session://"):
                    return await self._cache.get(uri)
                raise ValueError(f"Unknown scheme: {uri}")

        container.input_resolver.override(providers.Singleton(MyAppResolver))
    """

    @abstractmethod
    async def resolve(self, input_node: Input) -> str:
        """
        Resolve Input.content_uri to text content.

        Args:
            input_node: Input node with content_uri to resolve.
                        Can traverse to Ideas via input_node.ideas for intent hints.

        Returns:
            Text content from the URI

        Raises:
            ValueError: If content_uri is missing or unsupported
        """
        ...
