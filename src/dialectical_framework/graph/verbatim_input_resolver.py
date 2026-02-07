"""
Default InputResolver that handles data: URIs or plain text.

This is the framework's minimal default - useful for tests and simple cases.
Apps should override with their own InputResolver for production use.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Union
from urllib.parse import unquote

from dialectical_framework.protocols.input_resolver import InputResolver

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.brainstorm import Brainstorm
    from dialectical_framework.graph.nodes.input import Input


class VerbatimInputResolver(InputResolver):
    """
    Default InputResolver that returns content as-is or decodes data: URIs.

    Accepts:
    - Plain text: content="My test content" → returns "My test content"
    - data: URI: content="data:,Hello%20World" → returns "Hello World"
    - base64 data: URI: content="data:;base64,SGVsbG8=" → returns "Hello"

    This is the framework's minimal default. Apps should provide their own
    InputResolver for production use cases (file uploads, URLs, etc.).

    Example:
        # Plain text (simplest)
        input_node = Input(content="My test content")

        # data: URI (standard format)
        input_node = Input(content="data:,My%20test%20content")

        # For production - override with app's resolver
        container.input_resolver.override(providers.Singleton(MyAppResolver))
    """

    async def resolve(self, input_node: Input) -> str:
        """
        Resolve content to text.

        The content field can contain:
        - None or empty (returns empty string)
        - Plain text (returned as-is)
        - data: URI (decoded and returned)
        - Other formats (handled by custom InputResolver implementations)

        Args:
            input_node: Input node with content (plain text or data: URI)

        Returns:
            Text content (empty string if content is None)
        """
        content = input_node.content
        if not content:
            return ""

        # If it's a data: URI, decode it
        if content.startswith("data:"):
            return self._decode_data_uri(content)

        # Otherwise, treat as plain text
        return content

    async def resolve_all(self, source: Union[Brainstorm, list[Input]]) -> str:
        """
        Resolve multiple inputs to combined text content.

        Combines all input contents with XML-style delineation:
        <input content="...">resolved text</input>

        Args:
            source: Either a Brainstorm node (resolves all connected Inputs)
                   or a list of Input nodes to resolve

        Returns:
            Combined text content with each input wrapped in <input> tags

        Raises:
            ValueError: If no inputs provided
        """
        from dialectical_framework.graph.nodes.brainstorm import Brainstorm

        # Get inputs list
        if isinstance(source, Brainstorm):
            inputs = [inp for inp, _ in source.inputs.all()]
        else:
            inputs = source

        if not inputs:
            raise ValueError("No inputs provided to resolve")

        # Combine all inputs with delineation (skip inputs with no content)
        parts = []
        for input_node in inputs:
            if not input_node.content:
                continue  # Skip inputs with None/empty content
            resolved_text = await self.resolve(input_node)
            parts.append(f'<Input id="{input_node.hash}">\n{resolved_text}\n</Input>')

        return "\n\n".join(parts)

    @staticmethod
    def _decode_data_uri(uri: str) -> str:
        """Decode a data: URI to text."""
        # Remove 'data:' prefix
        content_part = uri[5:]

        # Split on first comma to separate metadata from data
        if "," not in content_part:
            raise ValueError(f"Invalid data URI, missing comma separator: {uri}")

        metadata, data = content_part.split(",", 1)

        # Check if base64 encoded
        is_base64 = ";base64" in metadata.lower()

        if is_base64:
            # Decode base64
            decoded_bytes = base64.b64decode(data)
            return decoded_bytes.decode("utf-8")
        else:
            # URL-decode plain text
            return unquote(data)
