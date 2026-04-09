"""
Tests for SurfaceTheses - thesis extraction and anchoring.
"""

from __future__ import annotations

import json

import pytest
from langfuse.decorators import observe

from dialectical_framework.agents.analyst.skills.surface_theses import \
    SurfaceTheses
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.dialectical_component_repository import \
    DialecticalComponentRepository
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


class TestSurfaceTheses:
    """Tests for SurfaceTheses - thesis extraction and anchoring."""

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_requires_inputs_or_direct_thesis(self):
        """SurfaceTheses returns message when no inputs and no direct thesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = SurfaceTheses(intent="extract 3 theses")
            result = await agent.call()
            assert "No inputs" in result

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_extract_theses_basic(self):
        """SurfaceTheses extracts theses from input content."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            agent = SurfaceTheses(intent="extract 2 theses about software architecture")
            result = await agent.call()

            report = json.loads(result)
            assert report["ok"] is True
            vocab = DialecticalComponentRepository().get_vocabulary()
            assert len(vocab) >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_creates_ideas_node(self):
        """SurfaceTheses creates Ideas node with extracted components."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            input_node = Input(content=SAMPLE_INPUT_TEXT)
            input_node.commit()
            brainstorm.inputs.connect(input_node)

            agent = SurfaceTheses(intent="extract 2 theses")
            result = await agent.call()

            report = json.loads(result)
            assert report["artifacts"]["ideas_hash"] is not None

    @pytest.mark.asyncio
    @observe()
    async def test_anchoring_direct_thesis_without_inputs(self):
        """SurfaceTheses can anchor direct thesis even without inputs."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = SurfaceTheses(
                intent="anchor direct thesis 'Trust' - create component for concept of Trust"
            )
            result = await agent.call()

            report = json.loads(result)
            assert report["ok"] is True
            vocab = DialecticalComponentRepository().get_vocabulary()
            trust_components = [c for c in vocab if "trust" in c.statement.lower()]
            assert len(trust_components) >= 1
