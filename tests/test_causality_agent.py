"""
Tests for MapCausalities.

Tests cover the MapCausalities's ability to create causal cycles from a Nexus.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.explorer.skills.causality import (
    MapCausalities, MapCausalitiesResult)
from dialectical_framework.agents.explorer.skills.nexus_agent import NexusAgent
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.wisdom_unit import (POSITION_A,
                                                           POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           WisdomUnit)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, ARelationship, TMinusRelationship,
    TPlusRelationship, TRelationship)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture
def brainstorm():
    """Create a committed brainstorm for scoping."""
    bs = Brainstorm()
    bs.commit()
    return bs


def create_complete_wisdom_unit(index: int = 0) -> WisdomUnit:
    """Create a complete WisdomUnit with all 6 positions filled."""
    wu = WisdomUnit()
    wu.save()

    # Create and connect all 6 components
    t = DialecticalComponent(
        statement=f"Thesis {index}", meaning=f"thesis:test:{index}"
    )
    t.commit()
    wu.t.connect(
        t, relationship=TRelationship(alias=POSITION_T, heuristic_similarity=1.0)
    )

    a = DialecticalComponent(
        statement=f"Antithesis {index}", meaning=f"antithesis:test:{index}"
    )
    a.commit()
    wu.a.connect(
        a, relationship=ARelationship(alias=POSITION_A, heuristic_similarity=0.8)
    )

    t_plus = DialecticalComponent(
        statement=f"T+ benefit {index}", meaning=f"thesis:positive:{index}"
    )
    t_plus.commit()
    wu.t_plus.connect(
        t_plus,
        relationship=TPlusRelationship(alias=POSITION_T_PLUS, heuristic_similarity=0.9),
    )

    t_minus = DialecticalComponent(
        statement=f"T- drawback {index}", meaning=f"thesis:negative:{index}"
    )
    t_minus.commit()
    wu.t_minus.connect(
        t_minus,
        relationship=TMinusRelationship(
            alias=POSITION_T_MINUS, heuristic_similarity=0.9
        ),
    )

    a_plus = DialecticalComponent(
        statement=f"A+ benefit {index}", meaning=f"antithesis:positive:{index}"
    )
    a_plus.commit()
    wu.a_plus.connect(
        a_plus,
        relationship=APlusRelationship(alias=POSITION_A_PLUS, heuristic_similarity=0.9),
    )

    a_minus = DialecticalComponent(
        statement=f"A- drawback {index}", meaning=f"antithesis:negative:{index}"
    )
    a_minus.commit()
    wu.a_minus.connect(
        a_minus,
        relationship=AMinusRelationship(
            alias=POSITION_A_MINUS, heuristic_similarity=0.9
        ),
    )

    wu.commit()
    return wu


class TestMapCausalities:
    """Tests for MapCausalities.

    Note: Full integration tests for causality sequencing require complex setup
    with transformations and wheels. These tests focus on:
    - Agent initialization and field validation
    - Error handling for invalid nexus
    - Integration with existing tests covered in test_synthesist.py
    """

    def test_causality_agent_has_correct_fields(self):
        """Test MapCausalities has expected fields."""
        agent = MapCausalities(
            nexus_hash="test-hash",
            intent="preset:balanced",
            estimate=False,
        )

        assert agent.nexus_hash == "test-hash"
        assert agent.intent == "preset:balanced"
        assert agent.estimate is False

    def test_causality_agent_default_values(self):
        """Test MapCausalities default field values."""
        agent = MapCausalities(nexus_hash="test-hash")

        assert agent.intent == "preset:balanced"
        assert agent.estimate is True

    @pytest.mark.asyncio
    async def test_causality_agent_invalid_nexus(self, brainstorm):
        """Test that invalid nexus hash raises ValueError."""
        with scope(brainstorm.sid):
            agent = MapCausalities(
                nexus_hash="invalid-hash-that-does-not-exist",
                estimate=False,
            )

            with pytest.raises(ValueError, match="Nexus not found"):
                await agent.execute()

    @pytest.mark.asyncio
    async def test_causality_agent_resolves_nexus(self, brainstorm):
        """Test that MapCausalities can resolve a valid nexus."""
        with scope(brainstorm.sid):
            # Create a nexus
            wu = create_complete_wisdom_unit(0)
            nexus_agent = NexusAgent(wisdom_unit_hashes=[wu.hash])
            nexus_result = await nexus_agent.execute()

            # Verify agent can resolve it
            causality_agent = MapCausalities(
                nexus_hash=nexus_result.nexus.hash,
                estimate=False,
            )

            # _resolve_nexus should work
            resolved = causality_agent._resolve_nexus()
            assert resolved is not None
            assert resolved.hash == nexus_result.nexus.hash

    @pytest.mark.asyncio
    async def test_causality_agent_resolves_nexus_by_prefix(self, brainstorm):
        """Test that MapCausalities can resolve nexus by hash prefix."""
        with scope(brainstorm.sid):
            wu = create_complete_wisdom_unit(0)
            nexus_agent = NexusAgent(wisdom_unit_hashes=[wu.hash])
            nexus_result = await nexus_agent.execute()

            prefix = nexus_result.nexus.hash[:7]

            causality_agent = MapCausalities(
                nexus_hash=prefix,
                estimate=False,
            )

            resolved = causality_agent._resolve_nexus()
            assert resolved is not None
