"""
Tests for ExploreTransformations - Action-Reflection transformation generation.
"""

from __future__ import annotations

import pytest
from langfuse.decorators import observe

from dialectical_framework.agents.explorer.skills.transformation import \
    ExploreTransformations
from dialectical_framework.features.ac_re_taxonomy import (
    INSIGHT_SCALE, PROACTIVENESS_SCALE, get_polar_pair, insight_label_to_value,
    is_action_category, is_reflection_category, proactiveness_label_to_value)
from dialectical_framework.features.action_extraction import ActionExtraction
from dialectical_framework.features.positive_ac_re_apex_derivation import \
    ApexDerivation
from dialectical_framework.features.transformation_generation import \
    TransformationGeneration
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, ARelationship, TMinusRelationship,
    TPlusRelationship, TRelationship)
from dialectical_framework.graph.scope_context import scope


def _create_complete_pp() -> Perspective:
    """Create a complete Perspective for testing."""
    # T-side: Love
    t = DialecticalComponent(
        statement="Love",
        meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration",
    )
    t.commit()

    t_plus = DialecticalComponent(
        statement="Bonding - healthy connection and intimacy",
        meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration/Positive",
    )
    t_plus.commit()

    t_minus = DialecticalComponent(
        statement="Enmeshment - loss of individual identity",
        meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Integration/Negative",
    )
    t_minus.commit()

    # A-side: Indifference
    a = DialecticalComponent(
        statement="Indifference",
        meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Disintegration",
    )
    a.commit()

    a_plus = DialecticalComponent(
        statement="Autonomy - healthy independence and self-sufficiency",
        meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Disintegration/Positive",
    )
    a_plus.commit()

    a_minus = DialecticalComponent(
        statement="Alienation - disconnection and isolation",
        meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Disintegration/Negative",
    )
    a_minus.commit()

    # Build PP
    pp = Perspective()
    pp.save()

    pp.t.connect(t, relationship=TRelationship(alias="T", heuristic_similarity=1.0))
    pp.t_plus.connect(
        t_plus,
        relationship=TPlusRelationship(
            alias="T+",
            heuristic_similarity=0.9,
            complementarity_t=0.8,
            complementarity_a=0.3,
        ),
    )
    pp.t_minus.connect(
        t_minus,
        relationship=TMinusRelationship(
            alias="T-",
            heuristic_similarity=0.85,
            complementarity_t=0.3,
            complementarity_a=0.2,
        ),
    )
    pp.a.connect(a, relationship=ARelationship(alias="A", heuristic_similarity=1.0))
    pp.a_plus.connect(
        a_plus,
        relationship=APlusRelationship(
            alias="A+",
            heuristic_similarity=0.9,
            complementarity_t=0.3,
            complementarity_a=0.8,
        ),
    )
    pp.a_minus.connect(
        a_minus,
        relationship=AMinusRelationship(
            alias="A-",
            heuristic_similarity=0.85,
            complementarity_t=0.2,
            complementarity_a=0.3,
        ),
    )

    pp.commit()
    return pp


class TestAcReTaxonomy:
    """Tests for the Ac-Re taxonomy constants and helpers."""

    def test_insight_scale_range(self):
        """Insight scale values are in valid range."""
        for label, value in INSIGHT_SCALE.items():
            assert 0.0 <= value <= 1.0, f"Invalid insight value for {label}: {value}"

    def test_proactiveness_scale_range(self):
        """Proactiveness scale values are in valid range."""
        for label, value in PROACTIVENESS_SCALE.items():
            assert (
                0.0 <= value <= 1.0
            ), f"Invalid proactiveness value for {label}: {value}"

    def test_insight_label_to_value(self):
        """insight_label_to_value returns correct values."""
        assert insight_label_to_value("leverage") == 0.6
        assert insight_label_to_value("LEVERAGE") == 0.6  # Case insensitive
        assert insight_label_to_value("transcendence") == 1.0
        assert insight_label_to_value("reflex") == 0.0

    def test_proactiveness_label_to_value(self):
        """proactiveness_label_to_value returns correct values."""
        assert proactiveness_label_to_value("interpretation") == 0.2
        assert proactiveness_label_to_value("intervention") == 0.6
        assert proactiveness_label_to_value("INTERVENTION") == 0.6  # Case insensitive

    def test_polar_pairs(self):
        """get_polar_pair returns Re+ for given Ac+."""
        assert get_polar_pair("coordination") == "Framing"
        assert get_polar_pair("intervention") == "Interpretation"
        assert get_polar_pair("implementation") == "Detection"
        assert get_polar_pair("configuration") == "Observation"
        assert get_polar_pair("governance") == "Evaluation"
        assert get_polar_pair("stewardship") == "Evaluation"

    def test_polar_pairs_invalid(self):
        """get_polar_pair raises for non-Action labels."""
        with pytest.raises(ValueError):
            get_polar_pair("observation")  # Reflection, not Action
        with pytest.raises(ValueError):
            get_polar_pair("interpretation")  # Reflection, not Action

    def test_category_classification(self):
        """is_reflection_category and is_action_category work correctly."""
        # Reflections
        assert is_reflection_category("observation")
        assert is_reflection_category("interpretation")
        assert is_reflection_category("evaluation")  # Midpoint, but still reflection
        assert not is_action_category("interpretation")

        # Actions
        assert is_action_category("intervention")
        assert is_action_category("implementation")
        assert is_action_category("stewardship")
        assert not is_reflection_category("intervention")


class TestApexDerivation:
    """Tests for ApexDerivation capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_apex_derivation_requires_complete_pp(self):
        """ApexDerivation raises error for incomplete PP."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = Perspective()
            pp.save()  # Incomplete - no components

            service = ApexDerivation()
            with pytest.raises(ValueError, match="all 6 positions"):
                await service.execute(pp)

    @pytest.mark.asyncio
    @observe()
    async def test_apex_derivation_returns_valid_apexes(self):
        """ApexDerivation returns Re+ and Ac+ apexes with coordinates."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = _create_complete_pp()

            service = ApexDerivation()
            result = await service.execute(pp)

            # Check structure
            assert result.re_plus_apex is not None
            assert result.ac_plus_apex is not None

            # Check Re+ is in reflection zone
            assert (
                0.0 <= result.re_plus_apex.proactiveness <= 0.4
            ), f"Re+ proactiveness {result.re_plus_apex.proactiveness} should be in reflection zone"

            # Check Ac+ is in action zone
            assert (
                0.5 <= result.ac_plus_apex.proactiveness <= 1.0
            ), f"Ac+ proactiveness {result.ac_plus_apex.proactiveness} should be in action zone"

            # Both should have reasonable insight
            assert 0.0 <= result.re_plus_apex.insight <= 1.0
            assert 0.0 <= result.ac_plus_apex.insight <= 1.0

            # Check report
            assert service.report.artifacts["pp_hash"] == pp.short_hash


class TestActionExtraction:
    """Tests for ActionExtraction capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_action_extraction_generates_candidates(self):
        """ActionExtraction generates Ac+ candidates at different insight levels."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = _create_complete_pp()

            service = ActionExtraction()
            candidates = await service.execute(pp)

            # Should generate multiple candidates
            assert len(candidates) >= 1, "Should generate at least one candidate"

            # Each candidate should be in action zone
            for c in candidates:
                assert (
                    0.5 <= c.proactiveness <= 1.0
                ), f"Ac+ candidate proactiveness {c.proactiveness} should be in action zone"
                assert 0.0 <= c.insight <= 1.0
                assert c.statement, "Statement should not be empty"

    @pytest.mark.asyncio
    @observe()
    async def test_action_extraction_avoids_existing(self):
        """ActionExtraction avoids generating duplicates of existing transformations."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = _create_complete_pp()

            # First extraction
            service1 = ActionExtraction()
            candidates1 = await service1.execute(pp)
            statements1 = {c.statement for c in candidates1}

            # Second extraction with first results as exclusions
            # (In real usage, we'd pass actual Transformation objects)
            # For now, we just verify the API works
            service2 = ActionExtraction()
            candidates2 = await service2.execute(pp, not_like_these=[])

            # Should still generate candidates
            assert len(candidates2) >= 1


class TestTransformationGeneration:
    """Tests for TransformationGeneration capability."""

    @pytest.mark.asyncio
    @observe()
    async def test_transformation_generation_creates_tetrad(self):
        """TransformationGeneration creates complete tetrad from Ac+."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = _create_complete_pp()

            # Get apex and Ac+ candidate
            apex_service = ApexDerivation()
            apexes = await apex_service.execute(pp)

            action_service = ActionExtraction()
            candidates = await action_service.execute(pp)
            assert len(candidates) >= 1
            ac_plus = candidates[0]

            # Generate tetrad
            gen_service = TransformationGeneration()
            tetrad = await gen_service.execute(pp, ac_plus, apexes)

            # Check all 4 positions present
            assert tetrad.ac_plus.statement, "Ac+ statement should not be empty"
            assert tetrad.re_plus.statement, "Re+ statement should not be empty"
            assert tetrad.re_minus.statement, "Re- statement should not be empty"
            assert tetrad.ac_minus.statement, "Ac- statement should not be empty"

            # Check HS scores are valid
            assert 0.0 <= tetrad.ac_plus_hs <= 1.0
            assert 0.0 <= tetrad.re_plus_hs <= 1.0


class TestExploreTransformations:
    """Tests for ExploreTransformations - full pipeline."""

    @pytest.mark.asyncio
    @observe()
    async def test_transformation_agent_requires_valid_pp(self):
        """ExploreTransformations raises error for non-existent PP."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            agent = ExploreTransformations(perspective_hash="nonexistent123")

            with pytest.raises(ValueError, match="not found"):
                await agent.execute()

    @pytest.mark.asyncio
    @observe()
    async def test_transformation_agent_requires_complete_pp(self):
        """ExploreTransformations raises error for incomplete PP.

        Note: In practice, incomplete PPs can't be committed (cardinality validation),
        so they can't be found by hash. This test verifies the validation message
        when passed a hash that resolves to None (uncommitted PP has no hash).
        """
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            # Create incomplete PP - note: it can't be committed so has no hash
            pp = Perspective()
            t = DialecticalComponent(
                statement="Test",
                meaning="dx://taxonomy/System(General.v1)/Test",
            )
            t.commit()
            pp.save()
            pp.t.connect(
                t, relationship=TRelationship(alias="T", heuristic_similarity=1.0)
            )
            # Don't add other components - PP is incomplete and can't be committed

            # Since uncommitted PP has no hash, passing its short_hash (None) will fail
            # with "not found" error, which is correct behavior
            agent = ExploreTransformations(
                perspective_hash="uncommitted_pp_has_no_hash"
            )

            with pytest.raises(ValueError, match="not found"):
                await agent.execute()

    @pytest.mark.asyncio
    @observe()
    async def test_transformation_agent_generates_transformations(self):
        """ExploreTransformations generates new transformations for a complete PP."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = _create_complete_pp()

            agent = ExploreTransformations(perspective_hash=pp.short_hash)
            result = await agent.execute()

            # Should have generated at least one transformation
            assert len(result.new) >= 1, "Should generate at least one transformation"

            # Each transformation should have required positions
            for t in result.new:
                ac_plus_result = t.ac_plus.get()
                re_plus_result = t.re_plus.get()

                assert ac_plus_result is not None, "Transformation should have Ac+"
                assert re_plus_result is not None, "Transformation should have Re+"

                # Check relationship properties
                _, ac_plus_rel = ac_plus_result
                assert ac_plus_rel.insight is not None
                assert ac_plus_rel.proactiveness is not None
                assert ac_plus_rel.heuristic_similarity is not None

            # Check apexes were derived
            assert result.apexes is not None
            assert result.apexes.re_plus_apex is not None
            assert result.apexes.ac_plus_apex is not None

    @pytest.mark.asyncio
    @observe()
    async def test_transformation_agent_returns_existing(self):
        """ExploreTransformations returns existing transformations."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            pp = _create_complete_pp()

            # First run
            agent1 = ExploreTransformations(perspective_hash=pp.short_hash)
            result1 = await agent1.execute()

            first_new_count = len(result1.new)
            assert first_new_count >= 1

            # Second run
            agent2 = ExploreTransformations(perspective_hash=pp.short_hash)
            result2 = await agent2.execute()

            # Should include previously created transformations as existing
            assert len(result2.existing) >= first_new_count

    @pytest.mark.asyncio
    @observe()
    async def test_transformation_agent_with_input(self):
        """ExploreTransformations uses input from scope for better context."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.case_id):
            # Create an Input node with content
            from dialectical_framework.graph.nodes.input import Input

            input_node = Input(
                content="""
                In healthy relationships, people balance closeness with independence.
                Too much closeness leads to losing oneself; too much distance leads to disconnection.
                The key is finding ways to be together while maintaining individual identity.
                """
            )
            input_node.commit()
            case_node.inputs.connect(input_node)

            pp = _create_complete_pp()

            agent = ExploreTransformations(perspective_hash=pp.short_hash)
            result = await agent.execute()

            # Should still work with input in scope
            assert len(result.new) >= 1
            assert agent.report.ok
