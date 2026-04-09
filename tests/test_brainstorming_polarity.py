"""
Tests for ExpandPolarities - tetrad expansion (pole generation).
"""

from __future__ import annotations

import json

import pytest
from langfuse.decorators import observe

from dialectical_framework.agents.analyst.skills.polarity import FindPolarities
from dialectical_framework.agents.analyst.skills.wisdom import ExpandPolarities
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, ARelationship,
    HasPolarityRelationship, TMinusRelationship, TPlusRelationship,
    TRelationship)
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository
from dialectical_framework.graph.repositories.wisdom_unit_repository import \
    WisdomUnitRepository
from dialectical_framework.graph.scope_context import scope

# Sample text for tests
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
"""


class TestExpandPolarities:
    """Tests for ExpandPolarities - tetrad expansion."""

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_requires_valid_thesis(self):
        """ExpandPolarities returns error when thesis not found."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            agent = ExpandPolarities(
                thesis_hash="nonexistent123",
                antithesis_hash="nonexistent456",
            )
            result = await agent.call()
            report = json.loads(result)
            assert report["ok"] is False
            assert "not found" in report["summary"]

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_requires_valid_antithesis(self):
        """ExpandPolarities returns error when antithesis not found."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration",
            )
            thesis.commit()

            agent = ExpandPolarities(
                thesis_hash=thesis.short_hash,
                antithesis_hash="nonexistent456",
            )
            result = await agent.call()
            report = json.loads(result)
            assert report["ok"] is False
            assert "not found" in report["summary"]

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_generates_all_poles(self):
        """ExpandPolarities generates all 4 poles (T+, T-, A+, A-)."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Distrust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Disintegration",
            )
            antithesis.commit()

            agent = ExpandPolarities(
                thesis_hash=thesis.short_hash,
                antithesis_hash=antithesis.short_hash,
            )
            wus = await agent.execute()

            assert agent.report.ok
            assert len(wus) >= 1

            # Check that the WU is complete
            wu = wus[0]
            assert wu.is_complete()
            assert wu.is_committed

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_creates_wu_from_polarity(self):
        """ExpandPolarities creates WU using FindPolarities output."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Data Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            thesis.commit()

            # Use FindPolarities to create Polarity (T-A pair)
            polarity_agent = FindPolarities(thesis_hashes=[thesis.short_hash])
            await polarity_agent.execute()

            # Get the polarity data
            polarity_data = polarity_agent.report.artifacts.get("polarity_data", [])
            assert len(polarity_data) >= 1

            # Complete with ExpandPolarities
            data = polarity_data[0]
            wisdom_agent = ExpandPolarities(
                thesis_hash=data["thesis_hash"],
                antithesis_hash=data["antithesis_hash"],
            )
            wus = await wisdom_agent.execute()

            assert wisdom_agent.report.ok
            assert len(wus) >= 1
            assert wus[0].is_complete()

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_returns_existing_complete_wus(self):
        """ExpandPolarities returns existing complete WUs along with new ones."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Performance",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Efficiency/Speed",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Reliability",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Resilience/Stability",
            )
            antithesis.commit()

            # First run - creates new WU
            agent1 = ExpandPolarities(
                thesis_hash=thesis.short_hash,
                antithesis_hash=antithesis.short_hash,
            )
            wus1 = await agent1.execute()
            assert len(wus1) >= 1
            first_wu_hash = wus1[0].hash

            # Second run - should return existing + potentially new
            agent2 = ExpandPolarities(
                thesis_hash=thesis.short_hash,
                antithesis_hash=antithesis.short_hash,
            )
            wus2 = await agent2.execute()

            # Should include the existing WU
            existing_hashes = [wu.hash for wu in wus2]
            assert first_wu_hash in existing_hashes

            # Check report counts
            assert agent2.report.artifacts["existing_count"] >= 1

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_with_specific_positions(self):
        """ExpandPolarities can generate specific poles only."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Simplicity",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Efficiency/Elegance",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Complexity",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Capability/Richness",
            )
            antithesis.commit()

            # Only generate T+ and T-
            agent = ExpandPolarities(
                thesis_hash=thesis.short_hash,
                antithesis_hash=antithesis.short_hash,
                positions=["T+", "T-"],
            )
            wus = await agent.execute()

            # WU won't be complete (missing A+, A-)
            assert agent.report.ok
            # Note: The WU might not be complete if only partial positions are generated

    @pytest.mark.asyncio
    @observe()
    async def test_wisdom_detects_duplicates(self):
        """ExpandPolarities detects and discards duplicate WUs after deduplication."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Order",
                meaning="dx://taxonomy/System(General.v1)/Viability/Structure/Organization",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Chaos",
                meaning="dx://taxonomy/System(General.v1)/Viability/Structure/Entropy",
            )
            antithesis.commit()

            # First run
            agent1 = ExpandPolarities(
                thesis_hash=thesis.short_hash,
                antithesis_hash=antithesis.short_hash,
            )
            wus1 = await agent1.execute()
            initial_count = len(wus1)

            # Multiple runs should not create exact duplicates
            # (though they may create variants with different poles)
            for _ in range(2):
                agent = ExpandPolarities(
                    thesis_hash=thesis.short_hash,
                    antithesis_hash=antithesis.short_hash,
                )
                await agent.execute()

            # Check how many WUs exist for this tension
            pol_repo = PolarityRepository()
            polarities = pol_repo.find_by_tension(thesis, antithesis)
            assert len(polarities) >= 1, "Expected at least one Polarity"
            polarity = polarities[0]

            wu_repo = WisdomUnitRepository()
            all_wus = wu_repo.find_by_polarity(polarity)
            complete_wus = [
                wu for wu in all_wus if wu.is_complete() and wu.is_committed
            ]

            # Should not have exact duplicates (same 6 components)
            seen_signatures: set[frozenset[str]] = set()
            for wu in complete_wus:
                # Get all component hashes
                comp_hashes: list[str] = []
                for pos in ["t", "t_plus", "t_minus", "a", "a_plus", "a_minus"]:
                    result = getattr(wu, pos).get()
                    if result:
                        comp_hashes.append(result[0].hash)
                signature = frozenset(comp_hashes)
                assert (
                    signature not in seen_signatures
                ), "Found duplicate WU with same components"
                seen_signatures.add(signature)


class TestWisdomUnitIsSame:
    """Tests for WisdomUnit.is_same method."""

    @pytest.mark.asyncio
    async def test_is_same_identical_wu(self):
        """is_same returns True for identical WU."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = WisdomUnit()
            wu.save()

            # Same instance should be same
            assert wu.is_same(wu)

    @pytest.mark.asyncio
    async def test_is_same_different_components(self):
        """is_same returns False for WUs with different components."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            # Create components
            t1 = DialecticalComponent(statement="Trust", meaning="dx://taxonomy/Simple")
            t1.commit()
            t2 = DialecticalComponent(statement="Love", meaning="dx://taxonomy/Simple")
            t2.commit()
            a = DialecticalComponent(statement="Fear", meaning="dx://taxonomy/Simple")
            a.commit()

            # Create two Polarities with different T components
            pol1 = Polarity()
            pol1.set_t(t1, heuristic_similarity=1.0)
            pol1.set_a(a, heuristic_similarity=0.5)
            pol1.commit()

            pol2 = Polarity()
            pol2.set_t(t2, heuristic_similarity=1.0)
            pol2.set_a(a, heuristic_similarity=0.5)
            pol2.commit()

            # Create WUs referencing the different Polarities
            wu1 = WisdomUnit()
            wu1.save()
            wu1.polarity.connect(pol1, relationship=HasPolarityRelationship())

            wu2 = WisdomUnit()
            wu2.save()
            wu2.polarity.connect(pol2, relationship=HasPolarityRelationship())

            assert not wu1.is_same(wu2)

    @pytest.mark.asyncio
    async def test_is_same_swapped_orientation(self):
        """is_same returns True for WUs with swapped T-A orientation."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            # Create components
            c1 = DialecticalComponent(statement="Order", meaning="dx://taxonomy/Simple")
            c1.commit()
            c2 = DialecticalComponent(statement="Chaos", meaning="dx://taxonomy/Simple")
            c2.commit()
            c1_plus = DialecticalComponent(
                statement="Order+", meaning="dx://taxonomy/Simple"
            )
            c1_plus.commit()
            c1_minus = DialecticalComponent(
                statement="Order-", meaning="dx://taxonomy/Simple"
            )
            c1_minus.commit()
            c2_plus = DialecticalComponent(
                statement="Chaos+", meaning="dx://taxonomy/Simple"
            )
            c2_plus.commit()
            c2_minus = DialecticalComponent(
                statement="Chaos-", meaning="dx://taxonomy/Simple"
            )
            c2_minus.commit()

            # Polarity 1: T=Order, A=Chaos
            pol1 = Polarity()
            pol1.set_t(c1, heuristic_similarity=1.0)
            pol1.set_a(c2, heuristic_similarity=0.5)
            pol1.commit()

            # Polarity 2: T=Chaos, A=Order (swapped!)
            pol2 = Polarity()
            pol2.set_t(c2, heuristic_similarity=1.0)
            pol2.set_a(c1, heuristic_similarity=0.5)
            pol2.commit()

            # WU1 with Polarity 1 and Order poles for T, Chaos poles for A
            wu1 = WisdomUnit()
            wu1.save()
            wu1.polarity.connect(pol1, relationship=HasPolarityRelationship())
            wu1.t_plus.connect(
                c1_plus,
                relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.8),
            )
            wu1.t_minus.connect(
                c1_minus,
                relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.8),
            )
            wu1.a_plus.connect(
                c2_plus,
                relationship=APlusRelationship(alias="A+", heuristic_similarity=0.8),
            )
            wu1.a_minus.connect(
                c2_minus,
                relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.8),
            )

            # WU2 with Polarity 2 (swapped) and poles matching the swapped orientation
            wu2 = WisdomUnit()
            wu2.save()
            wu2.polarity.connect(pol2, relationship=HasPolarityRelationship())
            wu2.t_plus.connect(
                c2_plus,
                relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.8),
            )
            wu2.t_minus.connect(
                c2_minus,
                relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.8),
            )
            wu2.a_plus.connect(
                c1_plus,
                relationship=APlusRelationship(alias="A+", heuristic_similarity=0.8),
            )
            wu2.a_minus.connect(
                c1_minus,
                relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.8),
            )

            # They should be considered the same (same tension, swapped orientation)
            assert wu1.is_same(wu2)
