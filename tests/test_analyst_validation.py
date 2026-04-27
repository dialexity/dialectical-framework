"""
Tests for Perspective validation capabilities.
"""

from __future__ import annotations

import pytest
from langfuse.decorators import observe

from dialectical_framework.features.control_statements_check import \
    ControlStatementsCheck
from dialectical_framework.features.perspective_validation import \
    PerspectiveValidation
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, TMinusRelationship,
    TPlusRelationship)
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

    # Create and connect T
    t = DialecticalComponent(statement=t_statement)
    t.commit()
    pp.t.connect(t)

    # Create and connect A
    a = DialecticalComponent(statement=a_statement)
    a.commit()
    pp.a.connect(a)

    # Create and connect T+ with complementarity
    t_plus = DialecticalComponent(statement=t_plus_statement)
    t_plus.commit()
    pp.t_plus.connect(
        t_plus,
        TPlusRelationship(
            heuristic_similarity=0.8,
            complementarity_t=ks_t_plus,
            complementarity_a=ks_t_plus,
        ),
    )

    # Create and connect T-
    t_minus = DialecticalComponent(statement=t_minus_statement)
    t_minus.commit()
    pp.t_minus.connect(
        t_minus,
        TMinusRelationship(
            heuristic_similarity=0.8,
            complementarity_t=ks_t_minus,
            complementarity_a=ks_t_minus,
        ),
    )

    # Create and connect A+
    a_plus = DialecticalComponent(statement=a_plus_statement)
    a_plus.commit()
    pp.a_plus.connect(
        a_plus,
        APlusRelationship(
            heuristic_similarity=0.8,
            complementarity_t=ks_a_plus,
            complementarity_a=ks_a_plus,
        ),
    )

    # Create and connect A-
    a_minus = DialecticalComponent(statement=a_minus_statement)
    a_minus.commit()
    pp.a_minus.connect(
        a_minus,
        AMinusRelationship(
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
            result = await capability.execute(perspective=pp)

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
            result = await capability.execute(perspective=pp)

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
            result = await validator.execute(perspective=pp)

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
            result = await validator.execute(perspective=pp)

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
            result = await validator.execute(perspective=pp)

            assert result.is_empirically_valid is False
            assert not result.is_valid
            assert any("Empirical synthesis" in r for r in result.failure_reasons)

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
                await validator.execute(perspective=pp)

    @pytest.mark.asyncio
    @observe()
    async def test_requires_complete_perspective(self):
        """PerspectiveValidation requires complete Perspective."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = Perspective()
            pp.save()

            # Only add T - incomplete
            t = DialecticalComponent(statement="Trust")
            t.commit()
            pp.t.connect(t)
            pp.commit()

            validator = PerspectiveValidation()
            with pytest.raises(ValueError, match="must be complete"):
                await validator.execute(perspective=pp)
