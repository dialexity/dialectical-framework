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
        from dialectical_framework.concerns.create_dx_input import \
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
        from dialectical_framework.concerns.create_dx_input import \
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
        from dialectical_framework.concerns.create_dx_input import \
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
        from dialectical_framework.concerns.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            concern = CreateDxInput()
            with pytest.raises(ValueError):
                await concern.resolve(transition_hash="nonexistent" * 8)


def _build_transformation_with_nexus(uid: str):
    """Build the minimal committed structure a real Ac+ Transition sits in:
    PP → Nexus, Cycle, Wheel with 2 edges, Transformation with Ac+/Re+.

    Returns (nexus, transformation, ac_plus_transition).
    """
    import test_graph as tg
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.relationships.polarity_relationship import (
        AcPlusRelationship, RePlusRelationship)

    components = []
    for stmt in ["T", "T+", "T-", "A", "A+", "A-"]:
        c = Statement(text=f"RT {stmt} {uid}", meaning=f"meaning:{stmt}")
        c.commit()
        components.append(c)

    pp, _ = tg.create_pp_from_components(
        t=components[0],
        a=components[3],
        t_plus=components[1],
        t_minus=components[2],
        a_plus=components[4],
        a_minus=components[5],
        intent=f"pp_{uid}",
    )
    pp.commit()

    nexus = Nexus(intent=f"scaling culture {uid}")
    nexus.commit()
    pp.nexus.connect(nexus)

    cycle = Cycle(intent="preset:balanced")
    cycle.set_perspectives([pp])
    cycle.commit()

    wheel = Wheel(intent=f"wheel_{uid}")
    wheel.save()
    edge1 = Transition()
    edge1.set_source(components[0]).set_target(components[3])
    edge1.commit()
    edge1.cycle.connect(wheel)
    edge2 = Transition()
    edge2.set_source(components[3]).set_target(components[0])
    edge2.commit()
    edge2.cycle.connect(wheel)
    cycle.wheels.connect(wheel)
    wheel.commit()

    transformation = Transformation(intent=f"tr_{uid}")
    transformation.set_nexus(nexus)
    transformation.set_on_edge(edge1)
    transformation.save()

    ac_plus = Transition()
    ac_plus.set_source(components[2]).set_target(components[4])
    ac_plus.summary = "Turn rigidity into shared autonomy"
    ac_plus.commit()
    transformation.ac_plus.connect(
        ac_plus, relationship=AcPlusRelationship(alias="Ac+")
    )
    re_plus = Transition()
    re_plus.set_source(components[5]).set_target(components[1])
    re_plus.commit()
    transformation.re_plus.connect(
        re_plus, relationship=RePlusRelationship(alias="Re+")
    )
    transformation.commit()

    return nexus, transformation, ac_plus


class TestRoundTripProvenance:
    """The dx:// round-trip must be closable: the created Input carries its
    origin (source exploration) in the digest, the Transition is inspectable
    with lineage, and pending inputs are discoverable in both orientation
    surfaces (present_analysis for the Analyst, dialectical_context for the
    Advisor)."""

    @pytest.mark.asyncio
    async def test_dx_input_digest_carries_origin_nexus(self):
        from dialectical_framework.concerns.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            nexus, _, ac_plus = _build_transformation_with_nexus("prov1")

            concern = CreateDxInput()
            input_node = await concern.resolve(transition_hash=ac_plus.hash)

            assert input_node.digest is not None
            assert "Turn rigidity into shared autonomy" in input_node.digest
            assert f"[[{nexus.short_hash}]]" in input_node.digest
            assert "scaling culture" in input_node.digest
            assert concern.report.artifacts["source_nexus_hash"] == nexus.hash

    @pytest.mark.asyncio
    async def test_dx_input_without_container_still_has_pathway_origin(self):
        """A bare Transition (no Transformation/Wheel) degrades gracefully."""
        from dialectical_framework.concerns.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            s1 = Statement(text="Source", meaning="test")
            s1.commit()
            s2 = Statement(text="Target", meaning="test")
            s2.commit()
            t = Transition(nonce="bare")
            t.summary = "Standalone insight"
            t.save()
            t.source.connect(s1)
            t.target.connect(s2)
            t.commit()

            concern = CreateDxInput()
            input_node = await concern.resolve(transition_hash=t.hash)

            assert input_node.digest is not None
            assert "Standalone insight" in input_node.digest
            assert f"[[{t.short_hash}]]" in input_node.digest
            assert "source_nexus_hash" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_inspect_node_renders_transition_with_lineage(self):
        from dialectical_framework.agents.orchestrator.tools.inspect_node import \
            InspectNode

        sid = _new_sid()
        with scope(sid):
            nexus, transformation, ac_plus = _build_transformation_with_nexus(
                "insp1"
            )

            result = await InspectNode().resolve(node_hash=ac_plus.hash)

            assert "## Transition" in result
            assert "Turn rigidity into shared autonomy" in result
            assert "Ac+" in result
            assert transformation.short_hash in result
            assert nexus.short_hash in result
            # never the repr fallback
            assert "Transition(" not in result

    @pytest.mark.asyncio
    async def test_present_analysis_lists_pending_dx_input(self):
        from dialectical_framework.agents.orchestrator.tools.present_analysis import \
            PresentAnalysis
        from dialectical_framework.concerns.create_dx_input import \
            CreateDxInput

        sid = _new_sid()
        with scope(sid):
            nexus, _, ac_plus = _build_transformation_with_nexus("pres1")
            await CreateDxInput().resolve(transition_hash=ac_plus.hash)

            summary = await PresentAnalysis().resolve()

            assert "## Sources" in summary
            assert "pending" in summary
            assert "(from exploration)" in summary
            assert f"[[{nexus.short_hash}]]" in summary  # origin line surfaced

    @pytest.mark.asyncio
    async def test_dialectical_context_lists_pending_inputs(self):
        """Empty-graph branch: no perspectives, but a pending input exists —
        the dump must surface it instead of claiming a blank slate."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        sid = _new_sid()
        with scope(sid):
            inp = Input(content="Some captured but unprocessed material")
            inp.commit()

            dump = await DialecticalContext().resolve()

            assert "Pending" in dump
            assert inp.short_hash in dump
            assert "No tensions identified yet" in dump
            assert "No prior understanding" not in dump

    @pytest.mark.asyncio
    async def test_dialectical_context_pending_inputs_with_perspectives(self):
        """Populated-graph branch: pending inputs are listed alongside
        existing tensions (the other half of the _dump_inputs change)."""
        import test_dialectical_context as tdc
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        sid = _new_sid()
        with scope(sid):
            tdc._create_perspective_with_aspects()
            inp = Input(content="Captured mid-conversation, not yet analyzed")
            inp.commit()

            dump = await DialecticalContext().resolve()

            assert "Pending" in dump
            assert inp.short_hash in dump
            assert "Control" in dump  # the perspective still renders

    @pytest.mark.asyncio
    async def test_repeat_capture_is_idempotent(self):
        """Capturing the same transition twice must reuse the existing Input:
        no digest clobber (SourceDigest may have refined it), no duplicate
        HAS_INPUT edge, no second node_created effect."""
        from dialectical_framework.concerns.create_dx_input import \
            CreateDxInput
        from dialectical_framework.graph.repositories.input_repository import \
            InputRepository

        sid = _new_sid()
        with scope(sid):
            _, _, ac_plus = _build_transformation_with_nexus("idem1")

            first = CreateDxInput()
            input_node = await first.resolve(transition_hash=ac_plus.hash)

            # Simulate a later digest refinement by the Analyst side.
            input_node.digest = "REFINED understanding of the insight"
            input_node.save()

            second = CreateDxInput()
            reused = await second.resolve(transition_hash=ac_plus.hash)

            assert reused.hash == input_node.hash
            assert "reused" in second.report.summary
            # refined digest survives
            assert reused.digest == "REFINED understanding of the insight"
            # artifacts still delivered on the reuse path
            assert second.report.artifacts["input_hash"] == input_node.hash
            assert "source_nexus_hash" in second.report.artifacts
            # no second node_created effect
            created_effects = [
                e for e in second.report.effects
                if e.effect_type == "node_created"
            ]
            assert not created_effects
            # exactly one Input node, one HAS_INPUT edge
            dx_inputs = [
                i for i in InputRepository().get_all()
                if i.content.startswith("dx://")
            ]
            assert len(dx_inputs) == 1
            from dialectical_framework.graph.repositories.case_repository import \
                CaseRepository

            case = CaseRepository().find_by_sid()
            edges = [
                (n, r) for n, r in case.inputs.all()
                if n.hash == input_node.hash
            ]
            assert len(edges) == 1


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
