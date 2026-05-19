"""
Tests for selective-input processing and dx:// feedback loop.

Tests verify:
1. NodeRepository.find_by_hashes batch lookup
2. DialexityInputResolver Transition support
3. SurfaceTheses with input_hashes (selective mode)
4. CreateDxInput tool
"""

from __future__ import annotations

import pytest

from dialectical_framework.exceptions.resolver_errors import \
    UnsupportedNodeTypeError
from dialectical_framework.graph.dialexity_input_resolver import \
    DialexityInputResolver
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    """Create a Case and return its sid."""
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


class TestFindByHashes:
    """Tests for NodeRepository.find_by_hashes."""

    def test_returns_matching_nodes(self):
        """find_by_hashes returns nodes with matching hashes."""
        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="First thesis", meaning="test")
            s1.commit()
            s2 = Statement(text="Second thesis", meaning="test")
            s2.commit()

            repo = NodeRepository()
            results = repo.find_by_hashes([s1.hash, s2.hash])

            result_hashes = {n.hash for n in results}
            assert s1.hash in result_hashes
            assert s2.hash in result_hashes

    def test_skips_nonexistent_hashes(self):
        """find_by_hashes silently skips hashes that don't match."""
        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Existing thesis", meaning="test")
            s1.commit()

            repo = NodeRepository()
            results = repo.find_by_hashes([s1.hash, "nonexistent" * 8])

            assert len(results) == 1
            assert results[0].hash == s1.hash

    def test_respects_sid_scoping(self):
        """find_by_hashes only returns nodes from current scope."""
        sid1 = _new_sid()
        sid2 = _new_sid()

        with scope(sid1):
            s1 = Statement(text="Thesis in scope 1", meaning="test")
            s1.commit()

        with scope(sid2):
            repo = NodeRepository()
            results = repo.find_by_hashes([s1.hash])
            assert len(results) == 0

    def test_node_type_filter(self):
        """find_by_hashes filters by node_type when provided."""
        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="A statement", meaning="test")
            s1.commit()
            i1 = Input(content="Some input content")
            i1.commit()

            repo = NodeRepository()
            statements_only = repo.find_by_hashes(
                [s1.hash, i1.hash], node_type=Statement
            )

            assert len(statements_only) == 1
            assert statements_only[0].hash == s1.hash

    def test_empty_hashes_returns_empty(self):
        """find_by_hashes returns empty list for empty input."""
        sid = _new_sid()
        with scope(sid):
            repo = NodeRepository()
            assert repo.find_by_hashes([]) == []


class TestResolverTransitionSupport:
    """Tests for DialexityInputResolver Transition content extraction."""

    def test_extracts_summary(self):
        """Resolver extracts summary from Transition."""
        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Source statement", meaning="test")
            s1.commit()
            s2 = Statement(text="Target statement", meaning="test")
            s2.commit()

            t = Transition(nonce="test1")
            t.summary = "Balance emerges from tension"
            t.instruction = "Short label"
            t.save()
            t.source.connect(s1)
            t.target.connect(s2)
            t.commit()

            resolver = DialexityInputResolver()
            content = resolver._extract_content(t)

            assert content == "Balance emerges from tension"

    def test_falls_back_to_instruction(self):
        """Resolver falls back to instruction when summary is None."""
        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Source", meaning="test")
            s1.commit()
            s2 = Statement(text="Target", meaning="test")
            s2.commit()

            t = Transition(nonce="test2")
            t.summary = None
            t.instruction = "Action label"
            t.save()
            t.source.connect(s1)
            t.target.connect(s2)
            t.commit()

            resolver = DialexityInputResolver()
            content = resolver._extract_content(t)

            assert content == "Action label"

    def test_returns_empty_when_both_none(self):
        """Resolver returns empty string when both summary and instruction are None."""
        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Source", meaning="test")
            s1.commit()
            s2 = Statement(text="Target", meaning="test")
            s2.commit()

            t = Transition(nonce="test3")
            t.summary = None
            t.instruction = None
            t.save()
            t.source.connect(s1)
            t.target.connect(s2)
            t.commit()

            resolver = DialexityInputResolver()
            content = resolver._extract_content(t)

            assert content == ""

    def test_rejects_unsupported_type(self):
        """Resolver still rejects unsupported node types."""
        sid = _new_sid()
        with scope(sid):
            from dialectical_framework.graph.nodes.ideas import Ideas

            ideas = Ideas(intent="test")
            ideas.save()
            ideas.commit()

            resolver = DialexityInputResolver()
            with pytest.raises(UnsupportedNodeTypeError):
                resolver._extract_content(ideas)


class TestCreateDxInput:
    """Tests for CreateDxInput concern."""

    @pytest.mark.asyncio
    async def test_creates_dx_uri_input(self):
        """CreateDxInput creates Input with correct dx:// URI."""
        from dialectical_framework.agents.analyst.tools.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Source for transition", meaning="test")
            s1.commit()
            s2 = Statement(text="Target for transition", meaning="test")
            s2.commit()

            t = Transition(nonce="dx-test")
            t.summary = "Insight from exploration"
            t.save()
            t.source.connect(s1)
            t.target.connect(s2)
            t.commit()

            concern = CreateDxInput()
            input_node = await concern.resolve(transition_hash=t.hash)

            assert input_node.is_committed
            assert input_node.content == f"dx://{sid}/{t.hash}"
            assert concern.report.ok

    @pytest.mark.asyncio
    async def test_links_to_case(self):
        """CreateDxInput links the new Input to the Case."""
        from dialectical_framework.agents.analyst.tools.create_dx_input import \
            CreateDxInput
        from dialectical_framework.graph.repositories.input_repository import \
            InputRepository

        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Source", meaning="test")
            s1.commit()
            s2 = Statement(text="Target", meaning="test")
            s2.commit()

            t = Transition(nonce="link-test")
            t.summary = "Test transition"
            t.save()
            t.source.connect(s1)
            t.target.connect(s2)
            t.commit()

            concern = CreateDxInput()
            await concern.resolve(transition_hash=t.hash)

            repo = InputRepository()
            inputs = repo.get_all()
            dx_inputs = [i for i in inputs if i.content.startswith("dx://")]
            assert len(dx_inputs) == 1

    @pytest.mark.asyncio
    async def test_rejects_non_transition(self):
        """CreateDxInput raises TypeError for non-Transition nodes."""
        from dialectical_framework.agents.analyst.tools.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Not a transition", meaning="test")
            s1.commit()

            concern = CreateDxInput()
            with pytest.raises(TypeError):
                await concern.resolve(transition_hash=s1.hash)

    @pytest.mark.asyncio
    async def test_rejects_nonexistent_hash(self):
        """CreateDxInput raises ValueError for missing node."""
        from dialectical_framework.agents.analyst.tools.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            concern = CreateDxInput()
            with pytest.raises(ValueError):
                await concern.resolve(transition_hash="nonexistent" * 8)


class TestSelectiveInputProcessing:
    """Tests for SurfaceTheses with input_hashes."""

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_selective_processing_filters_inputs(self):
        """SurfaceTheses with input_hashes only processes selected inputs."""
        from dialectical_framework.agents.analyst.skills.surface_theses import \
            SurfaceTheses

        sid = _new_sid()
        with scope(sid):
            case = Case()
            case.commit()

        sid = case.sid
        with scope(sid):
            i1 = Input(content="Remote work boosts productivity")
            i1.commit()
            case.inputs.connect(i1)

            i2 = Input(content="Office culture is important for teams")
            i2.commit()
            case.inputs.connect(i2)

            # Only process i1
            concern = SurfaceTheses(intent="extract theses", input_hashes=[i1.hash])
            inputs = concern._get_inputs()

            assert len(inputs) == 1
            assert inputs[0].hash == i1.hash

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_no_filter_processes_all(self):
        """SurfaceTheses without input_hashes processes all inputs."""
        from dialectical_framework.agents.analyst.skills.surface_theses import \
            SurfaceTheses

        sid = _new_sid()
        with scope(sid):
            case = Case()
            case.commit()

        sid = case.sid
        with scope(sid):
            i1 = Input(content="First input")
            i1.commit()
            case.inputs.connect(i1)

            i2 = Input(content="Second input")
            i2.commit()
            case.inputs.connect(i2)

            concern = SurfaceTheses(intent="extract theses")
            inputs = concern._get_inputs()

            assert len(inputs) == 2
