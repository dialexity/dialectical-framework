"""
Default InputResolver that handles data: URIs or plain text.

This is the framework's minimal default - useful for tests and simple cases.
Apps should override with their own InputResolver for production use.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from urllib.parse import unquote

from dialectical_framework.protocols.input_resolver import InputResolver

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input


class VerbatimInputResolver(InputResolver):
    """
    Default InputResolver that returns content_uri as-is or decodes data: URIs.

    Accepts:
    - Plain text: content_uri="My test content" → returns "My test content"
    - data: URI: content_uri="data:,Hello%20World" → returns "Hello World"
    - base64 data: URI: content_uri="data:;base64,SGVsbG8=" → returns "Hello"

    This is the framework's minimal default. Apps should provide their own
    InputResolver for production use cases (file uploads, URLs, etc.).

    Example:
        # Plain text (simplest)
        input_node = Input(content_uri="My test content")

        # data: URI (standard format)
        input_node = Input(content_uri="data:,My%20test%20content")

        # For production - override with app's resolver
        container.input_resolver.override(providers.Singleton(MyAppResolver))
    """

    async def resolve(self, input_node: Input) -> str:
        """
        Resolve content_uri to text content.

        Args:
            input_node: Input node with content_uri (plain text or data: URI)

        Returns:
            Text content

        Raises:
            ValueError: If content_uri is missing
        """
        if not input_node.content_uri:
            raise ValueError(
                f"Input {input_node.uid} has no content_uri. "
                f"Provide plain text or a data: URI."
            )

        uri = input_node.content_uri

        # If it's a data: URI, decode it
        if uri.startswith("data:"):
            return self._decode_data_uri(uri)

        # Otherwise, treat as plain text
        return uri

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
