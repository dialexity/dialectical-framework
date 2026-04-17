"""
Tests for NexusAgent.

Tests cover the NexusAgent's ability to create Nexuses from Perspectives.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.explorer.skills.nexus_agent import (
    NexusAgent,
    NexusAgentResult,
)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A,
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    Perspective,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship,
    APlusRelationship,
    ARelationship,
    TMinusRelationship,
    TPlusRelationship,
    TRelationship,
)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture
def case_node():
    """Create a committed case for scoping."""
    bs = Case()
    bs.commit()
    return bs


def create_complete_perspective(index: int = 0) -> Perspective:
    """Create a complete Perspective with all 6 positions filled."""
    pp = Perspective()
    pp.save()

    # Create and connect all 6 components
    t = DialecticalComponent(statement=f"Thesis {index}", meaning=f"thesis:test:{index}")
    t.commit()
    pp.t.connect(t, relationship=TRelationship(alias=POSITION_T, heuristic_similarity=1.0))

    a = DialecticalComponent(statement=f"Antithesis {index}", meaning=f"antithesis:test:{index}")
    a.commit()
    pp.a.connect(a, relationship=ARelationship(alias=POSITION_A, heuristic_similarity=0.8))

    t_plus = DialecticalComponent(statement=f"T+ benefit {index}", meaning=f"thesis:positive:{index}")
    t_plus.commit()
    pp.t_plus.connect(t_plus, relationship=TPlusRelationship(
        alias=POSITION_T_PLUS, heuristic_similarity=0.9
    ))

    t_minus = DialecticalComponent(statement=f"T- drawback {index}", meaning=f"thesis:negative:{index}")
    t_minus.commit()
    pp.t_minus.connect(t_minus, relationship=TMinusRelationship(
        alias=POSITION_T_MINUS, heuristic_similarity=0.9
    ))

    a_plus = DialecticalComponent(statement=f"A+ benefit {index}", meaning=f"antithesis:positive:{index}")
    a_plus.commit()
    pp.a_plus.connect(a_plus, relationship=APlusRelationship(
        alias=POSITION_A_PLUS, heuristic_similarity=0.9
    ))

    a_minus = DialecticalComponent(statement=f"A- drawback {index}", meaning=f"antithesis:negative:{index}")
    a_minus.commit()
    pp.a_minus.connect(a_minus, relationship=AMinusRelationship(
        alias=POSITION_A_MINUS, heuristic_similarity=0.9
    ))

    pp.commit()
    return pp


class TestNexusAgent:
    """Tests for NexusAgent."""

    @pytest.mark.asyncio
    async def test_create_nexus_from_single_pp(self, case_node):
        """Test creating a Nexus from a single Perspective."""
        with scope(case_node.case_id):
            pp = create_complete_perspective(0)

            agent = NexusAgent(perspective_hashes=[pp.hash])
            result = await agent.execute()

            assert isinstance(result, NexusAgentResult)
            assert result.nexus is not None
            assert result.perspective_count == 1

    @pytest.mark.asyncio
    async def test_create_nexus_from_multiple_pps(self, case_node):
        """Test creating a Nexus from multiple Perspectives."""
        with scope(case_node.case_id):
            pp1 = create_complete_perspective(0)
            pp2 = create_complete_perspective(1)

            agent = NexusAgent(perspective_hashes=[pp1.hash, pp2.hash])
            result = await agent.execute()

            assert result.nexus is not None
            assert result.perspective_count == 2

    @pytest.mark.asyncio
    async def test_create_nexus_with_intent(self, case_node):
        """Test creating a Nexus with an intent."""
        with scope(case_node.case_id):
            pp = create_complete_perspective(0)

            agent = NexusAgent(
                perspective_hashes=[pp.hash],
                intent="economic_vs_social",
            )
            result = await agent.execute()

            assert result.nexus is not None
            assert result.nexus.intent == "economic_vs_social"

    @pytest.mark.asyncio
    async def test_nexus_agent_report(self, case_node):
        """Test that NexusAgent produces correct report."""
        with scope(case_node.case_id):
            pp = create_complete_perspective(0)

            agent = NexusAgent(
                perspective_hashes=[pp.hash],
                intent="test_intent",
            )
            await agent.execute()

            report = agent._report
            assert report.ok is True
            assert "nexus_hash" in report.artifacts
            assert report.artifacts["perspective_count"] == 1
            assert report.artifacts["intent"] == "test_intent"
            assert "Created Nexus" in report.summary

    @pytest.mark.asyncio
    async def test_nexus_agent_call_returns_json(self, case_node):
        """Test that call() returns JSON string."""
        with scope(case_node.case_id):
            pp = create_complete_perspective(0)

            agent = NexusAgent(perspective_hashes=[pp.hash])
            json_result = await agent.call()

            assert isinstance(json_result, str)
            assert "nexus_hash" in json_result

    @pytest.mark.asyncio
    async def test_nexus_agent_empty_hashes_raises(self, case_node):
        """Test that empty hashes list raises ValueError."""
        with scope(case_node.case_id):
            agent = NexusAgent(perspective_hashes=[])

            with pytest.raises(ValueError, match="At least one Perspective hash is required"):
                await agent.execute()

    @pytest.mark.asyncio
    async def test_nexus_agent_with_hash_prefix(self, case_node):
        """Test that NexusAgent works with hash prefixes."""
        with scope(case_node.case_id):
            pp = create_complete_perspective(0)
            prefix = pp.hash[:7]

            agent = NexusAgent(perspective_hashes=[prefix])
            result = await agent.execute()

            assert result.nexus is not None
            assert result.perspective_count == 1
