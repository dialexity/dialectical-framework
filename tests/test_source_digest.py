"""
Tests for the Input digest infrastructure:
- digest field on Input node
- SourceDigest concern
- input_context utility
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.input import Input


class TestInputDigestField:
    """Tests for the digest field on Input node."""

    def test_digest_excluded_from_hash(self):
        """Digest field does not affect the content hash."""
        i1 = Input(content="Same content")
        i1.commit()

        i2 = Input(content="Same content")
        i2.digest = "Some analytical understanding"
        hash2 = i2.compute_hash()

        assert i1.hash == hash2

    def test_digest_defaults_to_none(self):
        """New Input nodes have digest=None."""
        node = Input(content="Test")
        assert node.digest is None

    def test_digest_mutable_after_commit(self):
        """Digest can be set after commit without raising."""
        node = Input(content="Test content")
        node.commit()
        assert node.digest is None

        node.digest = "Updated understanding"
        assert node.digest == "Updated understanding"

    def test_digest_preserved_on_save(self):
        """Digest is preserved through save (hash unchanged)."""
        node = Input(content="Test content")
        node.commit()
        original_hash = node.hash

        node.digest = "My digest"
        recomputed = node.compute_hash()

        assert recomputed == original_hash


class TestSourceDigestConcern:
    """Tests for the SourceDigest concern."""

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_initial_digest_generation(self):
        """SourceDigest generates an initial digest from content."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        concern = SourceDigest()
        result = await concern.resolve(
            content="Remote work increases productivity but reduces team cohesion."
        )

        assert isinstance(result, str)
        assert len(result) > 0
        assert concern.report.ok is True
        assert "initial" in concern.report.summary.lower()

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_digest_refinement(self):
        """SourceDigest refines an existing digest with context."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        concern = SourceDigest()
        result = await concern.resolve(
            content="Remote work increases productivity but reduces team cohesion.",
            existing_digest="The source discusses remote work trade-offs.",
            context="Focus on the tension between individual productivity and collective culture.",
        )

        assert isinstance(result, str)
        assert len(result) > 0
        assert concern.report.ok is True
        assert "refine" in concern.report.summary.lower()

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_digest_with_context_only(self):
        """SourceDigest incorporates context into initial digest."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        concern = SourceDigest()
        result = await concern.resolve(
            content="AI is transforming healthcare through diagnostics and drug discovery.",
            context="User says: focus on ethical implications, not technical capabilities.",
        )

        assert isinstance(result, str)
        assert len(result) > 0


class TestGetInputDigests:
    """Tests for the input_context utility."""

    @pytest.mark.asyncio
    async def test_prefers_digest_over_resolution(self):
        """Uses digest when available instead of resolving."""
        from unittest.mock import AsyncMock

        from dialectical_framework.utils.input_context import input_context

        node = Input(content="Full long content here")
        node.commit()
        node.digest = "Compact digest"

        mock_resolver = AsyncMock()

        result = await input_context([node], mock_resolver)

        assert "Compact digest" in result
        assert "Full long content" not in result
        mock_resolver.resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_resolver_when_no_digest(self):
        """Falls back to input_resolver.resolve() when digest is None."""
        from unittest.mock import AsyncMock

        from dialectical_framework.utils.input_context import input_context

        node = Input(content="Some content")
        node.commit()
        # digest is None

        mock_resolver = AsyncMock()
        mock_resolver.resolve.return_value = "Resolved content from source"

        result = await input_context([node], mock_resolver)

        assert "Resolved content from source" in result
        mock_resolver.resolve.assert_called_once_with(node)

    @pytest.mark.asyncio
    async def test_wraps_in_input_tags_with_hash(self):
        """Output wraps each input in <Input id="..."> tags."""
        from unittest.mock import AsyncMock

        from dialectical_framework.utils.input_context import input_context

        node = Input(content="Test")
        node.commit()
        node.digest = "My digest"

        mock_resolver = AsyncMock()

        result = await input_context([node], mock_resolver)

        assert f'<Input id="{node.hash}">' in result
        assert "</Input>" in result

    @pytest.mark.asyncio
    async def test_empty_inputs_returns_empty_string(self):
        """Returns empty string for empty input list."""
        from unittest.mock import AsyncMock

        from dialectical_framework.utils.input_context import input_context

        result = await input_context([], AsyncMock())
        assert result == ""

    @pytest.mark.asyncio
    async def test_multiple_inputs_joined(self):
        """Multiple inputs are joined with double newlines."""
        from unittest.mock import AsyncMock

        from dialectical_framework.utils.input_context import input_context

        n1 = Input(content="Content A")
        n1.commit()
        n1.digest = "Digest A"

        n2 = Input(content="Content B")
        n2.commit()
        n2.digest = "Digest B"

        mock_resolver = AsyncMock()

        result = await input_context([n1, n2], mock_resolver)

        assert "Digest A" in result
        assert "Digest B" in result
        assert "\n\n" in result
