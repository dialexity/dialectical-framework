"""
Tests for Perspective validation concerns.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.llm
from langfuse import observe

from dialectical_framework.concerns.control_statements_check import \
    ControlStatementsCheck
from dialectical_framework.concerns.perspective_validation import \
    PerspectiveValidation
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS, POSITION_T_PLUS,
    Perspective,
)
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope


def _create_test_perspective(
    t_statement: str = "Trust",
    a_statement: str = "Distrust",
    t_plus_statement: str = "Confidence",
    t_minus_statement: str = "Naivety",
    a_plus_statement: str = "Prudence",
    a_minus_statement: str = "Paranoia",
    ks_t_plus: float = 0.6,
    ks_t_minus: float = 0.3,
    ks_a_plus: float = 0.6,
    ks_a_minus: float = 0.3,
) -> Perspective:
    """Helper to create a fully populated Perspective for testing."""
    pp = Perspective()
    pp.save()

    # Create T and A via Polarity
    t = Statement(text=t_statement, meaning=t_statement.lower())
    t.commit()

    a = Statement(text=a_statement, meaning=a_statement.lower())
    a.commit()

    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Create and connect T+
    t_plus = Statement(text=t_plus_statement, meaning=t_plus_statement.lower())
    t_plus.commit()
    pp.t_plus.connect(
        t_plus,
        relationship=TPlusRelationship(
            alias=POSITION_T_PLUS,
            heuristic_similarity=0.8,
            complementarity_t=ks_t_plus,
            complementarity_a=ks_t_plus,
        ),
    )

    # Create and connect T-
    t_minus = Statement(text=t_minus_statement, meaning=t_minus_statement.lower())
    t_minus.commit()
    pp.t_minus.connect(
        t_minus,
        relationship=TMinusRelationship(
            alias=POSITION_T_MINUS,
            heuristic_similarity=0.8,
            complementarity_t=ks_t_minus,
            complementarity_a=ks_t_minus,
        ),
    )

    # Create and connect A+
    a_plus = Statement(text=a_plus_statement, meaning=a_plus_statement.lower())
    a_plus.commit()
    pp.a_plus.connect(
        a_plus,
        relationship=APlusRelationship(
            alias=POSITION_A_PLUS,
            heuristic_similarity=0.8,
            complementarity_t=ks_a_plus,
            complementarity_a=ks_a_plus,
        ),
    )

    # Create and connect A-
    a_minus = Statement(text=a_minus_statement, meaning=a_minus_statement.lower())
    a_minus.commit()
    pp.a_minus.connect(
        a_minus,
        relationship=AMinusRelationship(
            alias=POSITION_A_MINUS,
            heuristic_similarity=0.8,
            complementarity_t=ks_a_minus,
            complementarity_a=ks_a_minus,
        ),
    )

    pp.commit()
    return pp


class TestControlStatementsCheck:
    """Tests for ControlStatementsCheck capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_evaluates_control_statements(self):
        """ControlStatementsCheck evaluates both control statements."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = _create_test_perspective(
                t_plus_statement="Confidence",
                t_minus_statement="Naivety",
                a_plus_statement="Prudence",
                a_minus_statement="Paranoia",
            )

            capability = ControlStatementsCheck()
            result = await capability.resolve(perspective=pp)

            # Check control statements were evaluated
            assert "Confidence" in result.t_plus_without_a_plus_yields_t_minus_statement
            assert "Prudence" in result.t_plus_without_a_plus_yields_t_minus_statement
            assert "Naivety" in result.t_plus_without_a_plus_yields_t_minus_statement

            assert "Prudence" in result.a_plus_without_t_plus_yields_a_minus_statement
            assert "Confidence" in result.a_plus_without_t_plus_yields_a_minus_statement
            assert "Paranoia" in result.a_plus_without_t_plus_yields_a_minus_statement

            # Check estimation is created
            assert result.estimation.is_committed
            assert 0.0 <= result.estimation.t_plus_without_a_plus_yields_t_minus <= 1.0
            assert 0.0 <= result.estimation.a_plus_without_t_plus_yields_a_minus <= 1.0

    @pytest.mark.asyncio
    @observe()
    async def test_creates_estimation_and_rationale(self):
        """ControlStatementsCheck creates estimation and rationale nodes."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = _create_test_perspective()

            capability = ControlStatementsCheck()
            result = await capability.resolve(perspective=pp)

            # Check both nodes are committed
            assert result.estimation.is_committed
            assert result.rationale.is_committed

            # Check estimation has scores
            est = result.estimation
            assert est.t_plus_without_a_plus_yields_t_minus is not None
            assert est.a_plus_without_t_plus_yields_a_minus is not None
            assert (
                est.value
                == (
                    est.t_plus_without_a_plus_yields_t_minus
                    + est.a_plus_without_t_plus_yields_a_minus
                )
                / 2
            )


class TestPerspectiveValidation:
    """Tests for PerspectiveValidation orchestrator."""

    @pytest.mark.asyncio
    @observe()
    async def test_runs_both_validations(self):
        """PerspectiveValidation runs both control statements and empirical checks."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = _create_test_perspective()

            validator = PerspectiveValidation()
            result = await validator.resolve(perspective=pp)

            # Check control statements result is present
            assert result.control_statements is not None
            assert result.control_statements.estimation.is_committed

            # Check empirical result is present (from PP property)
            assert result.is_empirically_valid is not None

    @pytest.mark.asyncio
    @observe()
    async def test_valid_perspective(self):
        """PerspectiveValidation passes for valid tetrad."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            # Create PP with valid empirical conditions
            pp = _create_test_perspective(
                t_plus_statement="Confidence",
                t_minus_statement="Naivety",
                a_plus_statement="Prudence",
                a_minus_statement="Paranoia",
                ks_t_plus=0.6,
                ks_t_minus=0.3,
                ks_a_plus=0.6,
                ks_a_minus=0.3,
            )

            validator = PerspectiveValidation()
            result = await validator.resolve(perspective=pp)

            # Empirical should definitely pass with these values
            assert result.is_empirically_valid is True

            # CC depends on LLM evaluation
            if result.is_valid:
                assert len(result.failure_reasons) == 0
            else:
                # If CC fails, there should be a reason
                assert len(result.failure_reasons) > 0

    @pytest.mark.asyncio
    @observe()
    async def test_fails_empirical_conditions(self):
        """PerspectiveValidation fails when empirical conditions not met."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            # Create PP that fails empirical conditions (KS(T+) <= 0.4)
            pp = _create_test_perspective(
                ks_t_plus=0.35,
                ks_t_minus=0.3,
                ks_a_plus=0.6,
                ks_a_minus=0.3,
            )

            validator = PerspectiveValidation()
            result = await validator.resolve(perspective=pp)

            assert result.is_empirically_valid is False
            assert not result.is_valid
            assert any("Positive aspect threshold" in r for r in result.failure_reasons)

    @pytest.mark.asyncio
    @observe()
    async def test_requires_committed_perspective(self):
        """PerspectiveValidation requires committed Perspective."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = Perspective()
            pp.save()  # Not committed

            validator = PerspectiveValidation()
            with pytest.raises(ValueError, match="must be committed"):
                await validator.resolve(perspective=pp)

    @pytest.mark.asyncio
    @observe()
    async def test_requires_complete_perspective(self):
        """Incomplete Perspective cannot be committed (cardinality enforced)."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = Perspective()
            pp.save()

            # Only add Polarity with T and A (no aspects) - incomplete
            t = Statement(text="Trust", meaning="trust")
            t.commit()
            a = Statement(text="Distrust", meaning="distrust")
            a.commit()
            polarity = Polarity()
            polarity.set_t(t, heuristic_similarity=1.0)
            polarity.set_a(a, heuristic_similarity=0.8)
            polarity.commit()
            pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

            # Committing without aspects should fail cardinality check
            with pytest.raises(ValueError, match="Cardinality constraints violated"):
                pp.commit()
