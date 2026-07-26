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
    from mirascope.llm import UserContent

    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.nodes.input import Input

# Mime types Mirascope accepts as native image/document parts. Anything else
# (text, unknown binary) falls back to text resolution.
_IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif", "image/heic", "image/heif"}
)
_DOCUMENT_MIME_TYPES = frozenset({"application/pdf"})


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

    async def resolve_native(self, input_node: Input) -> UserContent:
        """
        Resolve content to native model content, preserving image/PDF modality.

        For a `data:` URI whose mime type is a supported image or PDF format,
        returns a Mirascope `Image` / `Document` part carrying the base64 bytes,
        so the model reads the source natively instead of a transcription. All
        other content (text, `data:text/*`, non-base64, unsupported binary)
        falls back to `resolve()` text.

        Args:
            input_node: Input node with content (plain text or data: URI).

        Returns:
            A multimodal part (`Image`/`Document`) for supported binary media,
            otherwise the resolved text `str`.
        """
        content = input_node.content
        if content and content.startswith("data:"):
            part = self._decode_data_uri_native(content)
            if part is not None:
                return part

        return await self.resolve(input_node)

    async def resolve_all(self, source: Union[Case, list[Input]]) -> str:
        """
        Resolve multiple inputs to combined text content.

        Combines all input contents with XML-style delineation:
        <input content="...">resolved text</input>

        Args:
            source: Either a Case node (resolves all connected Inputs)
                   or a list of Input nodes to resolve

        Returns:
            Combined text content with each input wrapped in <input> tags

        Raises:
            ValueError: If no inputs provided
        """
        from dialectical_framework.graph.nodes.case import Case

        # Get inputs list
        if isinstance(source, Case):
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
    def _decode_data_uri_native(uri: str) -> UserContent | None:
        """
        Build a native image/document part from a data: URI, if it is one.

        Returns an `Image`/`Document` for a base64 data: URI whose mime type is a
        supported image or PDF format. Returns None for anything that should be
        handled as text (text mime types, non-base64 payloads, unsupported types),
        letting the caller fall back to text resolution.
        """
        # data:<mime>[;base64],<data>
        content_part = uri[5:]
        if "," not in content_part:
            return None

        metadata, data = content_part.split(",", 1)
        if ";base64" not in metadata.lower():
            # Text data: URIs (or non-base64 binary) are handled as text.
            return None

        mime_type = metadata.split(";", 1)[0].strip().lower()

        from mirascope.llm import (Base64DocumentSource, Base64ImageSource,
                                   Document, Image)

        if mime_type in _IMAGE_MIME_TYPES:
            return Image(
                source=Base64ImageSource(
                    type="base64_image_source", data=data, mime_type=mime_type
                )
            )

        if mime_type in _DOCUMENT_MIME_TYPES:
            return Document(
                source=Base64DocumentSource(
                    type="base64_document_source", data=data, media_type=mime_type
                )
            )

        return None

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
