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
        """Returns plain text content as-is."""
        input_node = Input(content="My test content")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "My test content"

    @pytest.mark.asyncio
    async def test_resolve_plain_text_multiline(self, resolver: VerbatimInputResolver):
        """Returns multiline plain text as-is."""
        content = "Line 1\nLine 2\nLine 3"
        input_node = Input(content=content)
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == content

    @pytest.mark.asyncio
    async def test_resolve_plain_text_unicode(self, resolver: VerbatimInputResolver):
        """Returns unicode plain text as-is."""
        content = "Unicode: éàü 中文 🎉"
        input_node = Input(content=content)
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == content

    # -- data: URI tests --

    @pytest.mark.asyncio
    async def test_resolve_data_uri_plain(self, resolver: VerbatimInputResolver):
        """Decodes URL-encoded data: URI."""
        input_node = Input(content="data:text/plain,Hello%20World")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_resolve_data_uri_minimal(self, resolver: VerbatimInputResolver):
        """Decodes minimal data: URI without mediatype."""
        input_node = Input(content="data:,Simple%20text")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "Simple text"

    @pytest.mark.asyncio
    async def test_resolve_data_uri_base64(self, resolver: VerbatimInputResolver):
        """Decodes base64-encoded data: URI."""
        content = "Hello World"
        encoded = base64.b64encode(content.encode()).decode()
        input_node = Input(content=f"data:text/plain;base64,{encoded}")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == content

    @pytest.mark.asyncio
    async def test_resolve_data_uri_special_characters(self, resolver: VerbatimInputResolver):
        """Decodes URL-encoded special characters in data: URI."""
        input_node = Input(content="data:text/plain,%C3%A9%C3%A0%C3%BC")  # éàü
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "éàü"

    # -- Error cases --

    @pytest.mark.asyncio
    async def test_no_content_returns_empty(self, resolver: VerbatimInputResolver):
        """Returns empty string when Input has no content."""
        input_node = Input()
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == ""

    @pytest.mark.asyncio
    async def test_invalid_data_uri_raises(self, resolver: VerbatimInputResolver):
        """Raises ValueError for malformed data: URI."""
        input_node = Input(content="data:text/plain")  # Missing comma
        input_node.commit()

        with pytest.raises(ValueError, match="missing comma separator"):
            await resolver.resolve(input_node)


class TestVerbatimInputResolverResolveAll:
    """Tests for VerbatimInputResolver.resolve_all()."""

    @pytest.fixture
    def resolver(self) -> VerbatimInputResolver:
        return VerbatimInputResolver()

    @pytest.mark.asyncio
    async def test_resolve_all_with_input_list(self, resolver: VerbatimInputResolver):
        """Resolves list of Inputs with XML delineation."""
        input1 = Input(content="Content one")
        input1.commit()
        input2 = Input(content="Content two")
        input2.commit()

        result = await resolver.resolve_all([input1, input2])

        assert '<Input id="' in result
        assert "Content one" in result
        assert "Content two" in result

    @pytest.mark.asyncio
    async def test_resolve_all_with_case(self, resolver: VerbatimInputResolver):
        """Resolves Case's connected Inputs."""
        from dialectical_framework.graph.nodes.case import Case

        case_node = Case()
        case_node.commit()

        input1 = Input(content="First input content")
        input1.commit()
        input2 = Input(content="Second input content")
        input2.commit()

        case_node.inputs.connect(input1)
        case_node.inputs.connect(input2)

        result = await resolver.resolve_all(case_node)

        assert "First input content" in result
        assert "Second input content" in result

    @pytest.mark.asyncio
    async def test_resolve_all_empty_list_raises(self, resolver: VerbatimInputResolver):
        """Raises ValueError when no inputs provided."""
        with pytest.raises(ValueError, match="No inputs provided"):
            await resolver.resolve_all([])


class TestInputResolverDI:
    """Tests for DI integration."""

    @pytest.mark.asyncio
    async def test_default_resolver_is_composite(self, di_container):
        """Default resolver is CompositeInputResolver."""
        from dialectical_framework.graph.composite_input_resolver import CompositeInputResolver
        resolver = di_container.input_resolver()
        assert isinstance(resolver, CompositeInputResolver)

    @pytest.mark.asyncio
    async def test_default_resolver_handles_plain_text(self, di_container):
        """Default resolver returns plain text as-is."""
        resolver = di_container.input_resolver()

        input_node = Input(content="Plain text content")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "Plain text content"

    @pytest.mark.asyncio
    async def test_default_resolver_handles_data_uri(self, di_container):
        """Default resolver decodes data: URIs."""
        resolver = di_container.input_resolver()

        input_node = Input(content="data:,test%20content")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "test content"

    @pytest.mark.asyncio
    async def test_app_can_override_resolver(self, di_container):
        """App can override with custom resolver."""
        from dependency_injector import providers
        from dialectical_framework.protocols.input_resolver import InputResolver

        class MyAppResolver(InputResolver):
            async def resolve(self, input_node):
                return f"Custom: {input_node.content}"

            async def resolve_all(self, source):
                from dialectical_framework.graph.nodes.case import Case
                if isinstance(source, Case):
                    inputs = [inp for inp, _ in source.inputs.all()]
                else:
                    inputs = source
                parts = [await self.resolve(inp) for inp in inputs]
                return "\n".join(parts)

        di_container.input_resolver.override(
            providers.Singleton(MyAppResolver)
        )

        try:
            resolver = di_container.input_resolver()

            input_node = Input(content="session://user/doc")
            input_node.commit()

            result = await resolver.resolve(input_node)
            assert result == "Custom: session://user/doc"
        finally:
            di_container.input_resolver.reset_override()


class TestDialexityInputResolverParsing:
    """Tests for dx:// URI parsing."""

    @pytest.fixture
    def resolver(self):
        from dialectical_framework.graph.dialexity_input_resolver import DialexityInputResolver
        return DialexityInputResolver()

    def test_parse_two_segments(self, resolver):
        """Parses dx://sid/hash correctly."""
        sid, branch, hash_part = resolver.parse_uri("dx://scope-123/abc1234def")
        assert sid == "scope-123"
        assert branch is None
        assert hash_part == "abc1234def"

    def test_parse_three_segments(self, resolver):
        """Parses dx://sid/branch/hash correctly."""
        sid, branch, hash_part = resolver.parse_uri("dx://scope-123/main/abc1234def")
        assert sid == "scope-123"
        assert branch == "main"
        assert hash_part == "abc1234def"

    def test_parse_uuid_sid(self, resolver):
        """Parses UUID-style sid."""
        sid, branch, hash_part = resolver.parse_uri("dx://a1b2c3d4-e5f6-7890-abcd-ef1234567890/abc1234def")
        assert sid == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert branch is None
        assert hash_part == "abc1234def"

    def test_parse_full_hash(self, resolver):
        """Parses full 64-char hash."""
        full_hash = "abc1234def567890" * 4  # 64 chars
        sid, branch, hash_part = resolver.parse_uri(f"dx://scope/{full_hash}")
        assert hash_part == full_hash

    def test_parse_rejects_missing_scheme(self, resolver):
        """Rejects URI without dx:// scheme."""
        from dialectical_framework.exceptions.resolver_errors import MalformedDxUriError
        with pytest.raises(MalformedDxUriError, match="must start with 'dx://'"):
            resolver.parse_uri("http://scope/abc1234")

    def test_parse_rejects_empty_uri(self, resolver):
        """Rejects empty dx:// URI."""
        from dialectical_framework.exceptions.resolver_errors import MalformedDxUriError
        with pytest.raises(MalformedDxUriError, match="cannot be empty"):
            resolver.parse_uri("dx://")

    def test_parse_rejects_hash_only(self, resolver):
        """Rejects hash-only URI (no sid)."""
        from dialectical_framework.exceptions.resolver_errors import MalformedDxUriError
        with pytest.raises(MalformedDxUriError, match="requires at least sid and hash"):
            resolver.parse_uri("dx://abc1234def")

    def test_parse_rejects_short_hash(self, resolver):
        """Rejects hash shorter than 7 characters."""
        from dialectical_framework.exceptions.resolver_errors import MalformedDxUriError
        with pytest.raises(MalformedDxUriError, match="at least 7 characters"):
            resolver.parse_uri("dx://scope/abc123")  # 6 chars

    def test_parse_rejects_too_many_segments(self, resolver):
        """Rejects URI with too many segments."""
        from dialectical_framework.exceptions.resolver_errors import MalformedDxUriError
        with pytest.raises(MalformedDxUriError, match="too many segments"):
            resolver.parse_uri("dx://scope/branch/extra/abc1234")

    def test_parse_handles_trailing_slash(self, resolver):
        """Handles trailing slash correctly."""
        sid, branch, hash_part = resolver.parse_uri("dx://scope-123/abc1234def/")
        assert sid == "scope-123"
        assert branch is None
        assert hash_part == "abc1234def"


class TestDialexityInputResolverLookup:
    """Tests for dx:// node lookup and validation."""

    @pytest.fixture
    def resolver(self):
        from dialectical_framework.graph.dialexity_input_resolver import DialexityInputResolver
        return DialexityInputResolver()

    @pytest.mark.asyncio
    async def test_resolve_rationale_by_full_hash(self, resolver):
        """Resolves rationale by full hash."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
        from dialectical_framework.graph.nodes.rationale import Rationale

        comp = DialecticalComponent(statement="Target", sid="test-scope-123", meaning="test")
        comp.commit()

        rationale = Rationale(
            text="Test rationale for dx://",
            sid="test-scope-123"
        )
        rationale.set_explanation_target(comp)
        rationale.commit()

        uri = f"dx://test-scope-123/{rationale.hash}"
        result = await resolver.resolve(uri)
        assert result == "Test rationale for dx://"

    @pytest.mark.asyncio
    async def test_resolve_rationale_by_prefix(self, resolver):
        """Resolves rationale by hash prefix."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
        from dialectical_framework.graph.nodes.rationale import Rationale

        comp = DialecticalComponent(statement="Target", sid="test-scope-456", meaning="test")
        comp.commit()

        rationale = Rationale(
            text="Test rationale for prefix lookup",
            sid="test-scope-456"
        )
        rationale.set_explanation_target(comp)
        rationale.commit()

        # Use first 10 chars as prefix (>= 7)
        prefix = rationale.hash[:10]
        uri = f"dx://test-scope-456/{prefix}"
        result = await resolver.resolve(uri)
        assert result == "Test rationale for prefix lookup"

    @pytest.mark.asyncio
    async def test_resolve_rejects_wrong_sid(self, resolver):
        """Rejects URI with mismatched sid."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
        from dialectical_framework.graph.nodes.rationale import Rationale
        from dialectical_framework.exceptions.resolver_errors import ScopeMismatchError

        comp = DialecticalComponent(statement="Target", sid="correct-scope", meaning="test")
        comp.commit()

        rationale = Rationale(text="Test rationale", sid="correct-scope")
        rationale.set_explanation_target(comp)
        rationale.commit()

        uri = f"dx://wrong-scope/{rationale.hash}"
        with pytest.raises(ScopeMismatchError, match="sid mismatch"):
            await resolver.resolve(uri)

    @pytest.mark.asyncio
    async def test_resolve_rejects_nonexistent_hash(self, resolver):
        """Rejects URI with nonexistent hash."""
        from dialectical_framework.exceptions.resolver_errors import NodeNotFoundError

        uri = "dx://some-scope/abc1234def5678901234567890123456789012345678901234567890123456"
        with pytest.raises(NodeNotFoundError, match="No node found"):
            await resolver.resolve(uri)


class TestDialexityInputResolverContentExtraction:
    """Tests for content extraction from different node types."""

    @pytest.fixture
    def resolver(self):
        from dialectical_framework.graph.dialexity_input_resolver import DialexityInputResolver
        return DialexityInputResolver()

    @pytest.mark.asyncio
    async def test_extract_from_rationale(self, resolver):
        """Extracts text from Rationale."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
        from dialectical_framework.graph.nodes.rationale import Rationale

        comp = DialecticalComponent(statement="Test", sid="rationale-test", meaning="test")
        comp.commit()

        rationale = Rationale(
            text="This is the detailed explanation",
            sid="rationale-test"
        )
        rationale.set_explanation_target(comp)
        rationale.commit()

        result = await resolver.resolve(f"dx://rationale-test/{rationale.hash}")
        assert result == "This is the detailed explanation"

    @pytest.mark.asyncio
    async def test_extract_from_rationale_ignores_headline(self, resolver):
        """Extracts only text from Rationale, ignoring headline."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
        from dialectical_framework.graph.nodes.rationale import Rationale

        comp = DialecticalComponent(statement="Test", sid="rationale-headline-test", meaning="test")
        comp.commit()

        rationale = Rationale(
            text="Detailed explanation here",
            headline="Key Point",
            sid="rationale-headline-test"
        )
        rationale.set_explanation_target(comp)
        rationale.commit()

        result = await resolver.resolve(f"dx://rationale-headline-test/{rationale.hash}")
        assert result == "Detailed explanation here"
        assert "Key Point" not in result

    @pytest.mark.asyncio
    async def test_extract_from_component(self, resolver):
        """Extracts statement from DialecticalComponent."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        comp = DialecticalComponent(
            statement="Democracy enables participation",
            sid="comp-extract-test",
            meaning="test",
        )
        comp.commit()

        result = await resolver.resolve(f"dx://comp-extract-test/{comp.hash}")
        assert result == "Democracy enables participation"

    @pytest.mark.asyncio
    async def test_unsupported_node_type_fails(self, resolver):
        """Unsupported node types raise error."""
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.exceptions.resolver_errors import UnsupportedNodeTypeError

        # Input is not a supported target for dx://
        input_node = Input(
            content="Some content",
            sid="unsupported-test"
        )
        input_node.commit()

        with pytest.raises(UnsupportedNodeTypeError, match="cannot reference node type"):
            await resolver.resolve(f"dx://unsupported-test/{input_node.hash}")

    @pytest.mark.asyncio
    async def test_ideas_not_supported(self, resolver):
        """Ideas is not a supported target for dx://."""
        from dialectical_framework.graph.nodes.ideas import Ideas
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.exceptions.resolver_errors import UnsupportedNodeTypeError

        input_node = Input(content="Test", sid="ideas-unsupported-test")
        input_node.commit()

        ideas = Ideas(intent="Extract", sid="ideas-unsupported-test")
        ideas.save()
        input_node.ideas.connect(ideas)
        ideas.commit()

        with pytest.raises(UnsupportedNodeTypeError, match="cannot reference node type"):
            await resolver.resolve(f"dx://ideas-unsupported-test/{ideas.hash}")


class TestCompositeInputResolver:
    """Tests for CompositeInputResolver delegation."""

    @pytest.fixture
    def resolver(self, di_container):
        return di_container.input_resolver()

    @pytest.mark.asyncio
    async def test_delegates_plain_text_to_verbatim(self, resolver):
        """Delegates plain text to VerbatimInputResolver."""
        input_node = Input(content="Plain text content")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "Plain text content"

    @pytest.mark.asyncio
    async def test_delegates_data_uri_to_verbatim(self, resolver):
        """Delegates data: URI to VerbatimInputResolver."""
        input_node = Input(content="data:,Hello%20World")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_delegates_dx_uri_to_dialexity(self, resolver):
        """Delegates dx:// URI to DialexityInputResolver."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        # Create a component to reference
        comp = DialecticalComponent(
            statement="Referenced component content",
            sid="composite-test",
            meaning="test",
        )
        comp.commit()

        # Create Input that references the component via dx://
        input_node = Input(content=f"dx://composite-test/{comp.hash}")
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == "Referenced component content"

    @pytest.mark.asyncio
    async def test_resolve_all_with_mixed_schemes(self, resolver):
        """Resolves multiple inputs with different schemes."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        # Plain text input
        input1 = Input(content="Plain text")
        input1.commit()

        # data: URI input
        input2 = Input(content="data:,Data%20URI%20content")
        input2.commit()

        # dx:// URI input - use DialecticalComponent
        comp = DialecticalComponent(statement="Graph content from component", sid="mixed-test", meaning="test")
        comp.commit()
        input3 = Input(content=f"dx://mixed-test/{comp.hash}")
        input3.commit()

        result = await resolver.resolve_all([input1, input2, input3])

        assert "Plain text" in result
        assert "Data URI content" in result
        assert "Graph content from component" in result

    @pytest.mark.asyncio
    async def test_empty_content_returns_empty(self, resolver):
        """Returns empty string for empty content."""
        input_node = Input(content=None)
        input_node.commit()

        result = await resolver.resolve(input_node)
        assert result == ""
