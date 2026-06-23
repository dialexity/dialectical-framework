"""
Tests for the Input digest infrastructure:
- digest field on Input node
- SourceDigest concern
- input_context utility
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    import uuid

    return f"test-{uuid.uuid4().hex[:8]}"


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
        """SourceDigest generates an initial digest for long content."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        sid = _new_sid()
        with scope(sid):
            input_node = Input(content="A" * 2000)
            input_node.commit()

            concern = SourceDigest()
            result = await concern.resolve(input_hash=input_node.hash)

            assert result.digest is not None
            assert len(result.digest) > 0
            assert concern.report.ok is True
            assert "created" in concern.report.summary.lower()

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_digest_refinement(self):
        """SourceDigest refines an existing digest with context."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        sid = _new_sid()
        with scope(sid):
            input_node = Input(content="A" * 2000)
            input_node.commit()
            input_node.digest = "The source discusses remote work trade-offs."
            input_node.save()

            concern = SourceDigest()
            result = await concern.resolve(
                input_hash=input_node.hash,
                context="Focus on the tension between individual productivity and collective culture.",
            )

            assert result.digest is not None
            assert len(result.digest) > 0
            assert concern.report.ok is True
            assert "refined" in concern.report.summary.lower()

    @pytest.mark.asyncio
    async def test_short_content_skips_llm(self):
        """Short content is used as its own digest without LLM call."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        sid = _new_sid()
        with scope(sid):
            short_content = "Remote work increases productivity but reduces team cohesion."
            input_node = Input(content=short_content)
            input_node.commit()

            concern = SourceDigest()
            result = await concern.resolve(input_hash=input_node.hash)

            assert result.digest == short_content
            assert concern.report.ok is True
            assert "compact" in concern.report.summary.lower()

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_short_content_with_existing_digest_calls_llm(self):
        """Short content WITH existing digest still calls LLM to refine."""
        from dialectical_framework.concerns.source_digest import SourceDigest

        sid = _new_sid()
        with scope(sid):
            input_node = Input(content="Short content here.")
            input_node.commit()
            input_node.digest = "Existing understanding"
            input_node.save()

            concern = SourceDigest()
            result = await concern.resolve(
                input_hash=input_node.hash,
                context="Refine this",
            )

            assert result.digest is not None
            assert concern.report.ok is True
            assert "refined" in concern.report.summary.lower()


class TestInputContext:
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
