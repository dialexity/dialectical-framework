"""
Abstract base class for resolving Input nodes to text content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mirascope.llm import UserContent

    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.nodes.input import Input


class InputResolver(ABC):
    """
    Resolves Input or Case nodes to text content.

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

    async def resolve_native(self, input_node: Input) -> UserContent:
        """
        Resolve a single Input to native model content, preserving modality.

        Unlike `resolve()`, which always flattens to text, this returns Mirascope
        `UserContent` — either a plain `str` for text sources, or multimodal parts
        (`Image`, `Document`, or a list mixing text and such parts) for images/PDFs.
        Callers that pass content straight to the model (e.g. the `SourceDigest`
        concern's vision pass) use this to let the model read the source natively
        rather than a lossy transcription.

        The default implementation delegates to `resolve()`, so text-only resolvers
        need not override it. Resolvers that back image/PDF sources should override
        this to emit the corresponding `Image`/`Document` parts.

        Args:
            input_node: Input node with content to resolve.

        Returns:
            `UserContent` — a `str`, a single multimodal part, or a list of parts.

        Raises:
            ValueError: If content format is unsupported (implementation-dependent).
        """
        return await self.resolve(input_node)

    @abstractmethod
    async def resolve_all(self, source: Case | list[Input]) -> str:
        """
        Resolve multiple inputs to combined text content.

        Args:
            source: Either a Case node (resolves all connected Inputs)
                   or a list of Input nodes to resolve

        Returns:
            Combined text content from all inputs.
            Implementation decides how to format/combine the content.

        Raises:
            ValueError: If no inputs provided to resolve
        """
        ...
