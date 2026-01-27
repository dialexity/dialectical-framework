"""
Tests for InputResolver.
"""

from __future__ import annotations

import base64

import pytest

from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.verbatim_input_resolver import VerbatimInputResolver


class TestVerbatimInputResolver:
    """Tests for the default VerbatimInputResolver."""

    @pytest.fixture
    def resolver(self) -> VerbatimInputResolver:
        return VerbatimInputResolver()

    # -- Plain text tests --

    @pytest.mark.asyncio
    async def test_resolve_plain_text(self, resolver: VerbatimInputResolver):
        """Returns plain text content_uri as-is."""
        input_node = Input(content_uri="My test content")
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == "My test content"

    @pytest.mark.asyncio
    async def test_resolve_plain_text_multiline(self, resolver: VerbatimInputResolver):
        """Returns multiline plain text as-is."""
        content = "Line 1\nLine 2\nLine 3"
        input_node = Input(content_uri=content)
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == content

    @pytest.mark.asyncio
    async def test_resolve_plain_text_unicode(self, resolver: VerbatimInputResolver):
        """Returns unicode plain text as-is."""
        content = "Unicode: éàü 中文 🎉"
        input_node = Input(content_uri=content)
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == content

    # -- data: URI tests --

    @pytest.mark.asyncio
    async def test_resolve_data_uri_plain(self, resolver: VerbatimInputResolver):
        """Decodes URL-encoded data: URI."""
        input_node = Input(content_uri="data:text/plain,Hello%20World")
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_resolve_data_uri_minimal(self, resolver: VerbatimInputResolver):
        """Decodes minimal data: URI without mediatype."""
        input_node = Input(content_uri="data:,Simple%20text")
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == "Simple text"

    @pytest.mark.asyncio
    async def test_resolve_data_uri_base64(self, resolver: VerbatimInputResolver):
        """Decodes base64-encoded data: URI."""
        content = "Hello World"
        encoded = base64.b64encode(content.encode()).decode()
        input_node = Input(content_uri=f"data:text/plain;base64,{encoded}")
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == content

    @pytest.mark.asyncio
    async def test_resolve_data_uri_special_characters(self, resolver: VerbatimInputResolver):
        """Decodes URL-encoded special characters in data: URI."""
        input_node = Input(content_uri="data:text/plain,%C3%A9%C3%A0%C3%BC")  # éàü
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == "éàü"

    # -- Error cases --

    @pytest.mark.asyncio
    async def test_no_content_uri_raises(self, resolver: VerbatimInputResolver):
        """Raises ValueError when Input has no content_uri."""
        input_node = Input()
        input_node.save()

        with pytest.raises(ValueError, match="has no content_uri"):
            await resolver.resolve(input_node)

    @pytest.mark.asyncio
    async def test_invalid_data_uri_raises(self, resolver: VerbatimInputResolver):
        """Raises ValueError for malformed data: URI."""
        input_node = Input(content_uri="data:text/plain")  # Missing comma
        input_node.save()

        with pytest.raises(ValueError, match="missing comma separator"):
            await resolver.resolve(input_node)


class TestInputResolverDI:
    """Tests for DI integration."""

    @pytest.mark.asyncio
    async def test_default_resolver_is_verbatim(self, di_container):
        """Default resolver is VerbatimInputResolver."""
        resolver = di_container.input_resolver()
        assert isinstance(resolver, VerbatimInputResolver)

    @pytest.mark.asyncio
    async def test_default_resolver_handles_plain_text(self, di_container):
        """Default resolver returns plain text as-is."""
        resolver = di_container.input_resolver()

        input_node = Input(content_uri="Plain text content")
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == "Plain text content"

    @pytest.mark.asyncio
    async def test_default_resolver_handles_data_uri(self, di_container):
        """Default resolver decodes data: URIs."""
        resolver = di_container.input_resolver()

        input_node = Input(content_uri="data:,test%20content")
        input_node.save()

        result = await resolver.resolve(input_node)
        assert result == "test content"

    @pytest.mark.asyncio
    async def test_app_can_override_resolver(self, di_container):
        """App can override with custom resolver."""
        from dependency_injector import providers
        from dialectical_framework.protocols.input_resolver import InputResolver

        class MyAppResolver(InputResolver):
            async def resolve(self, input_node):
                return f"Custom: {input_node.content_uri}"

        di_container.input_resolver.override(
            providers.Singleton(MyAppResolver)
        )

        try:
            resolver = di_container.input_resolver()

            input_node = Input(content_uri="session://user/doc")
            input_node.save()

            result = await resolver.resolve(input_node)
            assert result == "Custom: session://user/doc"
        finally:
            di_container.input_resolver.reset_override()
