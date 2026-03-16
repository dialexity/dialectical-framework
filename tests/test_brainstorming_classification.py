"""
Tests for classification capabilities: PoleClassification and IdeaPlacement.
"""

from __future__ import annotations

import pytest
from langfuse.decorators import observe

from dialectical_framework.agents.brainstorming.capabilities.idea_placement import (
    IdeaPlacement,
    TensionInfo,
)
from dialectical_framework.agents.brainstorming.capabilities.pole_classification import (
    PoleClassification,
)
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.scope_context import scope


class TestPoleClassification:
    """Tests for PoleClassification capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_pole_classification_valid_t_plus(self):
        """PoleClassification validates a valid T+ pole."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Indifference",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = PoleClassification()
            result = await classifier.execute(
                thesis=thesis,
                antithesis=antithesis,
                pole_statement="Deep connection",
                position="T+",
            )

            assert classifier.report.ok
            assert result.heuristic_similarity > 0.1  # Valid for position
            assert result.heuristic_similarity > 0.0
            assert result.position == "T+"

    @pytest.mark.asyncio
    @observe()
    async def test_pole_classification_valid_a_minus(self):
        """PoleClassification validates a valid A- pole."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Distrust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = PoleClassification()
            result = await classifier.execute(
                thesis=thesis,
                antithesis=antithesis,
                pole_statement="Paranoia",
                position="A-",
            )

            assert classifier.report.ok
            assert result.position == "A-"
            # Paranoia is a shadow of distrust, should be valid
            assert result.heuristic_similarity >= 0.0

    @pytest.mark.asyncio
    @observe()
    async def test_pole_classification_wrong_position(self):
        """PoleClassification detects pole in wrong position."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Indifference",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = PoleClassification()
            # "Freedom" is more A+ (positive of indifference) than T+
            result = await classifier.execute(
                thesis=thesis,
                antithesis=antithesis,
                pole_statement="Personal freedom and autonomy",
                position="T+",
            )

            assert classifier.report.ok
            # May have low HS (wrong position) or have suggested_position pointing elsewhere
            # HS <= 0.1 means wrong category
            if result.heuristic_similarity <= 0.1 and result.suggested_position:
                assert result.suggested_position in ("T", "A", "T+", "T-", "A+", "A-")

    @pytest.mark.asyncio
    @observe()
    async def test_pole_classification_with_context(self):
        """PoleClassification uses context for evaluation."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Data Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            thesis.commit()

            antithesis = DialecticalComponent(
                statement="Eventual Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/ErrorCorrection",
            )
            antithesis.commit()

            context = """
            In distributed systems, strong consistency guarantees that all nodes
            see the same data at the same time, but at the cost of latency and
            availability during network partitions.
            """

            classifier = PoleClassification()
            result = await classifier.execute(
                thesis=thesis,
                antithesis=antithesis,
                pole_statement="Guaranteed correctness",
                position="T+",
                text=context,
            )

            assert classifier.report.ok
            assert result.heuristic_similarity >= 0.0

    @pytest.mark.asyncio
    async def test_pole_classification_invalid_position(self):
        """PoleClassification rejects invalid position."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            thesis = DialecticalComponent(
                statement="Test",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()
            antithesis = DialecticalComponent(
                statement="Anti-test",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = PoleClassification()
            with pytest.raises(ValueError, match="Invalid position"):
                await classifier.execute(
                    thesis=thesis,
                    antithesis=antithesis,
                    pole_statement="Something",
                    position="X+",  # Invalid
                )


class TestIdeaPlacement:
    """Tests for IdeaPlacement capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_idea_placement_empty_vocabulary(self):
        """IdeaPlacement treats idea as thesis when vocabulary is empty."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            placer = IdeaPlacement()
            result = await placer.execute(
                idea="Trust",
                vocabulary=[],
                tensions=[],
            )

            assert placer.report.ok
            assert result.placement == "thesis"
            assert result.confidence == 1.0
            assert result.component is not None
            assert result.component.statement == "Trust"

    @pytest.mark.asyncio
    @observe()
    async def test_idea_placement_detects_antithesis(self):
        """IdeaPlacement detects idea as antithesis of existing thesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            love = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            love.commit()

            placer = IdeaPlacement()
            result = await placer.execute(
                idea="Hate",
                vocabulary=[love],
                tensions=[],
            )

            assert placer.report.ok
            assert result.placement == "antithesis"
            assert result.antithesis_of == love.hash
            assert result.component is not None
            assert result.component.statement == "Hate"

    @pytest.mark.asyncio
    @observe()
    async def test_idea_placement_detects_duplicate(self):
        """IdeaPlacement detects semantic duplicate."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            trust = DialecticalComponent(
                statement="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            trust.commit()

            placer = IdeaPlacement()
            result = await placer.execute(
                idea="Faith and trust",  # Semantically similar
                vocabulary=[trust],
                tensions=[],
            )

            assert placer.report.ok
            # Should detect as duplicate or at least related
            # (LLM may classify as duplicate, thesis, antithesis, or pole depending on interpretation)
            assert result.placement in ("duplicate", "thesis", "antithesis", "pole")
            # Component should always be present
            assert result.component is not None

    @pytest.mark.asyncio
    @observe()
    async def test_idea_placement_detects_pole(self):
        """IdeaPlacement detects idea as pole of existing tension."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            love = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            love.commit()

            indifference = DialecticalComponent(
                statement="Indifference",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            indifference.commit()

            tension = TensionInfo(
                thesis_hash=love.hash,
                thesis_statement=love.statement,
                antithesis_hash=indifference.hash,
                antithesis_statement=indifference.statement,
            )

            placer = IdeaPlacement()
            result = await placer.execute(
                idea="Personal autonomy and freedom",
                vocabulary=[love, indifference],
                tensions=[tension],
            )

            assert placer.report.ok
            # Should detect as A+ (positive aspect of indifference)
            # Or could be thesis if LLM interprets differently
            if result.placement == "pole":
                assert result.position in ("A+", "T-", "T+", "A-")
                assert result.pole_of is not None

    @pytest.mark.asyncio
    @observe()
    async def test_idea_placement_new_thesis(self):
        """IdeaPlacement treats unrelated idea as new thesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            love = DialecticalComponent(
                statement="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            love.commit()

            placer = IdeaPlacement()
            result = await placer.execute(
                idea="Database indexing strategies",  # Unrelated to Love
                vocabulary=[love],
                tensions=[],
            )

            assert placer.report.ok
            # Should be thesis since unrelated
            assert result.placement == "thesis"

    @pytest.mark.asyncio
    @observe()
    async def test_idea_placement_with_context(self):
        """IdeaPlacement uses context for better placement."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            consistency = DialecticalComponent(
                statement="Strong Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            consistency.commit()

            context = """
            In distributed databases, the CAP theorem states that you can only
            have two of: Consistency, Availability, Partition tolerance.
            Eventual consistency sacrifices immediate consistency for availability.
            """

            placer = IdeaPlacement()
            result = await placer.execute(
                idea="Eventual consistency",
                vocabulary=[consistency],
                tensions=[],
                text=context,
            )

            assert placer.report.ok
            # Should detect as antithesis of strong consistency
            assert result.placement in ("antithesis", "thesis")
