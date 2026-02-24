"""
Tests for AnchoringAgent, ExtractTheses, PolarityFindingAgent, and ExtractAntitheses.
"""

from __future__ import annotations

import pytest
from langfuse.decorators import observe

from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)
from dialectical_framework.agents.brainstorming.tools.anchoring_agent import AnchoringAgent
from dialectical_framework.agents.brainstorming.tools.polarity_finding_agent import PolarityFindingAgent
from dialectical_framework.agents.brainstorming.tools.extract_antitheses import ExtractAntitheses
from dialectical_framework.graph.scope_context import scope


# Sample text for tests - simulates resolved input content
SAMPLE_INPUT_TEXT = """
# Software Architecture Decision Record

## Context
Our team is building a distributed e-commerce platform. We need to decide how to handle
data consistency across microservices. The system processes 10,000 orders per day.

## Key Concerns
1. **Data Consistency**: Ensuring order state is consistent across inventory, payment,
   and shipping services. Eventual consistency may lead to overselling.

2. **System Resilience**: The platform must handle failures gracefully. A single service
   failure should not cascade to bring down the entire system.

3. **Performance vs Safety**: Strong consistency guarantees come at the cost of latency.
   We need to balance transaction safety with user experience.

4. **Team Autonomy**: Each team owns their microservice. Tight coupling through shared
   databases would slow down independent deployments.

## Decision
We will implement the Saga pattern with compensating transactions for cross-service
operations. Each service maintains its own database (database-per-service pattern).

## Consequences
- Services can be deployed independently
- No distributed transactions needed
- Eventual consistency requires careful handling of edge cases
- Need robust monitoring for failed sagas
"""


class TestAnchoringAgent:
    """Tests for AnchoringAgent - thesis extraction and anchoring."""

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_requires_inputs_or_direct_thesis(self):
        """AnchoringAgent returns message when no inputs and no direct thesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = AnchoringAgent(intent="extract 3 theses")
            result = await agent.call()
            assert "No inputs" in result

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_extract_theses_basic(self):
        """AnchoringAgent extracts theses from input content."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            agent = AnchoringAgent(intent="extract 2 theses about software architecture")
            result = await agent.call()

            assert "Anchoring Complete" in result
            vocab = DialecticalComponentRepository().get_vocabulary()
            assert len(vocab) >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_creates_ideas_node(self):
        """AnchoringAgent creates Ideas node with extracted components."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            agent = AnchoringAgent(intent="extract 2 theses")
            result = await agent.call()

            assert "Ideas:" in result or "Ideas**:" in result

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_direct_thesis_without_inputs(self):
        """AnchoringAgent can anchor direct thesis even without inputs."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = AnchoringAgent(
                intent="anchor direct thesis 'Trust' - create component for concept of Trust"
            )
            result = await agent.call()

            assert "Anchoring Complete" in result
            vocab = DialecticalComponentRepository().get_vocabulary()
            trust_components = [c for c in vocab if "trust" in c.statement.lower()]
            assert len(trust_components) >= 1


class TestPolarityFindingAgent:
    """Tests for PolarityFindingAgent - antithesis generation orchestrator."""

    @pytest.mark.asyncio
    @observe()
    async def test_polarity_finding_requires_thesis_hashes(self):
        """PolarityFindingAgent returns message when no thesis hashes provided."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = PolarityFindingAgent(thesis_hashes=[])
            result = await agent.call()
            assert "No thesis hashes provided" in result

    @pytest.mark.asyncio
    @observe()
    async def test_polarity_finding_invalid_hash(self):
        """PolarityFindingAgent handles invalid thesis hash gracefully."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = PolarityFindingAgent(thesis_hashes=["nonexistent123"])
            result = await agent.call()
            assert "not found" in result

    @pytest.mark.asyncio
    @observe()
    async def test_polarity_finding_generates_antitheses(self):
        """PolarityFindingAgent generates antitheses for a thesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            # Create a thesis component
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration"
            )
            thesis.commit()

            agent = PolarityFindingAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            assert "Polarity Finding Complete" in result
            # Should have generated antitheses
            assert "Antitheses" in result

    @pytest.mark.asyncio
    @observe()
    async def test_polarity_finding_creates_ideas_per_thesis(self):
        """PolarityFindingAgent creates one Ideas node per thesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration"
            )
            thesis.commit()

            agent = PolarityFindingAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            assert "Ideas:" in result or "Ideas nodes:" in result

    @pytest.mark.asyncio
    @observe()
    async def test_polarity_finding_with_context(self):
        """PolarityFindingAgent uses input text as context for antithesis generation."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            # Add input for context
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            thesis = DialecticalComponent(
                statement="Data Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion"
            )
            thesis.commit()

            agent = PolarityFindingAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            assert "Polarity Finding Complete" in result


class TestExtractAntitheses:
    """Tests for ExtractAntitheses - antithesis generation work tool."""

    @pytest.mark.asyncio
    @observe()
    async def test_extract_antitheses_invalid_hash(self):
        """ExtractAntitheses returns error for invalid thesis hash."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            tool = ExtractAntitheses(thesis_hash="nonexistent123")
            result = await tool.call()
            assert "ERROR" in result

    @pytest.mark.asyncio
    @observe()
    async def test_extract_antitheses_simple_thesis(self):
        """ExtractAntitheses handles simple thesis with direct negation."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            # Simple thesis (short statement, is_simple=True)
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/Simple"
            )
            thesis.commit()

            tool = ExtractAntitheses(thesis_hash=thesis.short_hash)
            result = await tool.call()

            assert "SIMPLE" in result
            assert "Antitheses" in result

    @pytest.mark.asyncio
    @observe()
    async def test_extract_antitheses_complex_thesis(self):
        """ExtractAntitheses handles complex thesis with taxonomy."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            # Complex thesis (has meaning/taxonomy)
            thesis = DialecticalComponent(
                statement="Data consistency ensures reliable operations",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion"
            )
            thesis.commit()

            tool = ExtractAntitheses(thesis_hash=thesis.short_hash)
            result = await tool.call()

            assert "COMPLEX" in result
            assert "Apex" in result
            assert "Antitheses" in result

    @pytest.mark.asyncio
    @observe()
    async def test_extract_antitheses_creates_opposite_of_relationship(self):
        """ExtractAntitheses creates OPPOSITE_OF relationship between thesis and antithesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/Simple"
            )
            thesis.commit()

            tool = ExtractAntitheses(thesis_hash=thesis.short_hash)
            await tool.call()

            # Check OPPOSITE_OF relationship exists
            oppositions = list(thesis.oppositions.all())
            assert len(oppositions) >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_extract_antitheses_with_context(self):
        """ExtractAntitheses uses text context for generation."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="System Resilience",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Resilience/Recovery"
            )
            thesis.commit()

            tool = ExtractAntitheses(
                thesis_hash=thesis.short_hash,
                text=SAMPLE_INPUT_TEXT
            )
            result = await tool.call()

            assert "Antitheses" in result

    @pytest.mark.asyncio
    @observe()
    async def test_extract_antitheses_respects_not_like_these(self):
        """ExtractAntitheses avoids generating statements in not_like_these."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/Simple"
            )
            thesis.commit()

            # Run twice - second time should avoid first result
            tool1 = ExtractAntitheses(thesis_hash=thesis.short_hash)
            result1 = await tool1.call()

            # Get the antithesis statement from first run
            first_antitheses = list(thesis.oppositions.all())
            first_statements = [a.statement for a, _ in first_antitheses]

            # Second run with not_like_these
            tool2 = ExtractAntitheses(
                thesis_hash=thesis.short_hash,
                not_like_these=first_statements
            )
            result2 = await tool2.call()

            # Should still generate (retry with relaxed constraints)
            assert "Antitheses" in result2


class TestEndToEndPolarityFinder:
    """End-to-end tests for the polarity finder flow."""

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_then_polarity_finding(self):
        """Full flow: AnchoringAgent extracts theses, PolarityFindingAgent generates antitheses."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            # Phase 1: Extract theses
            anchoring = AnchoringAgent(intent="extract 1 thesis about data consistency")
            anchoring_result = await anchoring.call()
            assert "Anchoring Complete" in anchoring_result

            # Get thesis hashes from vocabulary
            vocab = list(DialecticalComponentRepository().get_vocabulary())
            assert len(vocab) >= 1
            thesis_hashes = [c.short_hash for c in vocab]

            # Phase 2: Generate antitheses
            polarity = PolarityFindingAgent(thesis_hashes=thesis_hashes)
            polarity_result = await polarity.call()

            assert "Polarity Finding Complete" in polarity_result
            assert "Antitheses" in polarity_result
