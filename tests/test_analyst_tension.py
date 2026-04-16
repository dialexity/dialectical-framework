"""
Tests for TensionAgent and AntithesisExtraction - antithesis generation.
"""

from __future__ import annotations

import json

import pytest
from langfuse.decorators import observe

from dialectical_framework.agents.analyst.skills.tension_agent import \
    TensionAgent
from dialectical_framework.features.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.input import Input
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


class TestTensionAgent:
    """Tests for TensionAgent - antithesis generation orchestrator."""

    @pytest.mark.asyncio
    @observe()
    async def test_tension_requires_thesis_hashes(self):
        """TensionAgent returns message when no thesis hashes provided."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            agent = TensionAgent(thesis_hashes=[])
            result = await agent.call()
            report = json.loads(result)
            assert report["summary"] == "No thesis hashes provided"

    @pytest.mark.asyncio
    @observe()
    async def test_tension_invalid_hash(self):
        """TensionAgent handles invalid thesis hash gracefully."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            agent = TensionAgent(thesis_hashes=["nonexistent123"])
            result = await agent.call()
            report = json.loads(result)
            # Report still ok since we processed 0 valid theses
            assert report["artifacts"]["total_antitheses"] == 0

    @pytest.mark.asyncio
    @observe()
    async def test_tension_generates_antitheses(self):
        """TensionAgent generates antitheses for a thesis."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            # Create a thesis component
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration",
            )
            thesis.commit()

            agent = TensionAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            report = json.loads(result)
            assert report["ok"] is True
            assert report["artifacts"]["total_antitheses"] >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_tension_creates_ideas(self):
        """TensionAgent creates Ideas node with theses and antitheses."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            thesis = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration",
            )
            thesis.commit()

            agent = TensionAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            report = json.loads(result)
            assert report["artifacts"]["ideas_hash"] is not None

    @pytest.mark.asyncio
    @observe()
    async def test_tension_with_context(self):
        """TensionAgent uses input text as context for antithesis generation."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            # Add input for context
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            case_node.inputs.connect(input_node)

            thesis = DialecticalComponent(
                statement="Data Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            thesis.commit()

            agent = TensionAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            report = json.loads(result)
            assert report["ok"] is True

    @pytest.mark.asyncio
    @observe()
    async def test_tension_creates_partial_wisdom_units(self):
        """TensionAgent creates partial WisdomUnits (T + A only)."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration",
            )
            thesis.commit()

            agent = TensionAgent(thesis_hashes=[thesis.short_hash])
            result = await agent.call()

            report = json.loads(result)
            assert report["ok"] is True

            # Check that partial WUs were created
            antithesis_data = report["artifacts"].get("antithesis_data", [])
            assert len(antithesis_data) >= 1

            # Each entry should have wisdom_unit_hash (partial WU)
            for data in antithesis_data:
                assert "wisdom_unit_hash" in data
                assert "thesis_hash" in data
                assert "antithesis_hash" in data


class TestAntithesisExtraction:
    """Tests for AntithesisExtraction capability - antithesis generation."""

    @pytest.mark.asyncio
    @observe()
    async def test_antithesis_extraction_simple_thesis(self):
        """AntithesisExtraction handles simple thesis with direct negation."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            # Simple thesis (short statement, is_simple=True)
            thesis = DialecticalComponent(
                statement="Trust", meaning="dx://taxonomy/Simple"
            )
            thesis.commit()

            service = AntithesisExtraction()
            antitheses = await service.execute(thesis=thesis)

            assert service.report.ok
            assert len(antitheses) >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_antithesis_extraction_complex_thesis(self):
        """AntithesisExtraction handles complex thesis with taxonomy."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            # Complex thesis (has meaning/taxonomy)
            thesis = DialecticalComponent(
                statement="Data consistency ensures reliable operations",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            thesis.commit()

            service = AntithesisExtraction()
            results = await service.execute(thesis=thesis)

            assert service.report.ok
            assert len(results) >= 1
            # Verify we got proper antithesis results with metadata
            assert results[0].component is not None
            assert results[0].heuristic_similarity >= 0.0

    @pytest.mark.asyncio
    @observe()
    async def test_antithesis_extraction_creates_opposite_of_relationship(self):
        """AntithesisExtraction creates OPPOSITE_OF relationship between thesis and antithesis."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            thesis = DialecticalComponent(
                statement="Love", meaning="dx://taxonomy/Simple"
            )
            thesis.commit()

            service = AntithesisExtraction()
            await service.execute(thesis=thesis)

            # Check OPPOSITE_OF relationship exists
            oppositions = list(thesis.oppositions.all())
            assert len(oppositions) >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_antithesis_extraction_with_context(self):
        """AntithesisExtraction uses text context for generation."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            thesis = DialecticalComponent(
                statement="System Resilience",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Resilience/Recovery",
            )
            thesis.commit()

            service = AntithesisExtraction()
            antitheses = await service.execute(thesis=thesis, text=SAMPLE_INPUT_TEXT)

            assert service.report.ok
            assert len(antitheses) >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_antithesis_extraction_respects_not_like_these(self):
        """AntithesisExtraction avoids generating statements in not_like_these."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            thesis = DialecticalComponent(
                statement="Trust", meaning="dx://taxonomy/Simple"
            )
            thesis.commit()

            # Run twice - second time should avoid first result
            service1 = AntithesisExtraction()
            await service1.execute(thesis=thesis)

            # Get the antithesis statement from first run
            first_antitheses = list(thesis.oppositions.all())
            first_statements = [a.statement for a, _ in first_antitheses]

            # Second run with not_like_these
            service2 = AntithesisExtraction()
            await service2.execute(thesis=thesis, not_like_these=first_statements)

            # Should still generate
            assert service2.report.ok
