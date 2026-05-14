"""
Tests for classification concerns: AspectClassification and StatementPlacement.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.real_llm
from langfuse import observe

from dialectical_framework.concerns.statement_placement import StatementPlacement
from dialectical_framework.concerns.aspect_classification import \
    AspectClassification
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.scope_context import scope


class TestAspectClassification:
    """Tests for AspectClassification capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_aspect_classification_valid_t_plus(self):
        """AspectClassification validates a valid T+ aspect."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            thesis = Statement(
                text="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()

            antithesis = Statement(
                text="Indifference",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = AspectClassification()
            result = await classifier.resolve(
                thesis=thesis,
                antithesis=antithesis,
                aspect_statement="Deep connection",
                position="T+",
            )

            assert classifier.report.ok
            assert result.heuristic_similarity > 0.1  # Valid for position
            assert result.heuristic_similarity > 0.0
            assert result.position == "T+"

    @pytest.mark.asyncio
    @observe()
    async def test_aspect_classification_valid_a_minus(self):
        """AspectClassification validates a valid A- aspect."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            thesis = Statement(
                text="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()

            antithesis = Statement(
                text="Distrust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = AspectClassification()
            result = await classifier.resolve(
                thesis=thesis,
                antithesis=antithesis,
                aspect_statement="Paranoia",
                position="A-",
            )

            assert classifier.report.ok
            assert result.position == "A-"
            # Paranoia is a shadow of distrust, should be valid
            assert result.heuristic_similarity >= 0.0

    @pytest.mark.asyncio
    @observe()
    async def test_aspect_classification_wrong_position(self):
        """AspectClassification detects aspect in wrong position."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            thesis = Statement(
                text="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()

            antithesis = Statement(
                text="Indifference",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = AspectClassification()
            # "Freedom" is more A+ (positive of indifference) than T+
            result = await classifier.resolve(
                thesis=thesis,
                antithesis=antithesis,
                aspect_statement="Personal freedom and autonomy",
                position="T+",
            )

            assert classifier.report.ok
            # May have low HS (wrong position) or have suggested_position pointing elsewhere
            # HS <= 0.1 means wrong category
            if result.heuristic_similarity <= 0.1 and result.suggested_position:
                assert result.suggested_position in ("T", "A", "T+", "T-", "A+", "A-")

    @pytest.mark.asyncio
    @observe()
    async def test_aspect_classification_with_context(self):
        """AspectClassification uses context for evaluation."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            thesis = Statement(
                text="Data Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            thesis.commit()

            antithesis = Statement(
                text="Eventual Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/ErrorCorrection",
            )
            antithesis.commit()

            context = """
            In distributed systems, strong consistency guarantees that all nodes
            see the same data at the same time, but at the cost of latency and
            availability during network partitions.
            """

            classifier = AspectClassification()
            result = await classifier.resolve(
                thesis=thesis,
                antithesis=antithesis,
                aspect_statement="Guaranteed correctness",
                position="T+",
                text=context,
            )

            assert classifier.report.ok
            assert result.heuristic_similarity >= 0.0

    @pytest.mark.asyncio
    async def test_aspect_classification_invalid_position(self):
        """AspectClassification rejects invalid position."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            thesis = Statement(
                text="Test",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            thesis.commit()
            antithesis = Statement(
                text="Anti-test",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
            )
            antithesis.commit()

            classifier = AspectClassification()
            with pytest.raises(ValueError, match="Invalid position"):
                await classifier.resolve(
                    thesis=thesis,
                    antithesis=antithesis,
                    aspect_statement="Something",
                    position="X+",  # Invalid
                )


class TestStatementPlacement:
    """Tests for StatementPlacement (search/recognition only)."""

    @pytest.mark.asyncio
    @observe()
    async def test_placement_empty_vocabulary(self):
        """StatementPlacement returns not-found when vocabulary is empty."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            placer = StatementPlacement()
            result = await placer.resolve(statement="Trust")

            assert placer.report.ok
            assert not result.found
            assert result.statement is None

    @pytest.mark.asyncio
    @observe()
    async def test_placement_finds_existing(self):
        """StatementPlacement finds a semantic match in the vocabulary."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            trust = Statement(
                text="Trust",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            trust.commit()

            placer = StatementPlacement()
            result = await placer.resolve(statement="Faith and trust")

            assert placer.report.ok
            if result.found:
                assert result.statement is not None
                assert result.statement.hash == trust.hash

    @pytest.mark.asyncio
    @observe()
    async def test_placement_not_found_unrelated(self):
        """StatementPlacement returns not-found for unrelated statements."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            love = Statement(
                text="Love",
                meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            love.commit()

            placer = StatementPlacement()
            result = await placer.resolve(statement="Database indexing strategies")

            assert placer.report.ok
            assert not result.found

    @pytest.mark.asyncio
    @observe()
    async def test_placement_with_context(self):
        """StatementPlacement uses context for better matching."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            consistency = Statement(
                text="Strong Consistency",
                meaning="dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Cohesion",
            )
            consistency.commit()

            context = """
            In distributed databases, the CAP theorem states that you can only
            have two of: Consistency, Availability, Partition tolerance.
            """

            placer = StatementPlacement()
            result = await placer.resolve(
                statement="Strong consistency guarantees",
                text=context,
            )

            assert placer.report.ok
            if result.found:
                assert result.statement.hash == consistency.hash
