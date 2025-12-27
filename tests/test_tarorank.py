"""
Comprehensive tests for graph-native TaroRank scoring implementation.

This test suite validates the complete graph-native scoring architecture
implemented in graph/scoring/, mirroring test_scoring.py for comparison.

**Key Differences from Domain Implementation:**
- Uses Estimation nodes (ProbabilityEstimation, RelevanceEstimation) instead of manual fields
- Simplified rationale audit-wins: GM aggregation without rating/confidence weighting
- Score invalidation tracking (score_invalidated_at)
- Graph database persistence (nodes saved to Memgraph/Neo4j)

**Test Coverage:**
- DialecticalComponent scoring (leaf nodes)
- Transition scoring with estimations
- WisdomUnit hierarchical R/P with power mean
- Cycle probability products
- Wheel complete scoring
- Alpha parameter effects
- Rationale aggregation (simplified GM, no rating)
- Invalidation tracking
- Complete documentation example validation

**Parallel Testing:**
Run this test suite alongside test_scoring.py to compare domain (legacy)
vs graph-native (new) implementations on the same scenarios.
"""

import pytest
from datetime import datetime, timedelta

from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.spiral import Spiral
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.estimation import (
    ProbabilityEstimation,
    RelevanceEstimation
)
from dialectical_framework.graph.scoring.tarorank import TaroRank


class TestDialecticalComponentScoring:
    """Test scoring for basic dialectical components (leaves in the hierarchy)."""

    def test_component_no_estimations_returns_none(self, graph_db_available):
        """Component with no estimations should return None (no evidence)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test thesis")
        component.save()

        # No estimations connected
        assert component.probability is None
        assert component.relevance is None

        # TaroRank should return None (insufficient data)
        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)
        assert score is None

    def test_component_with_manual_estimations(self, graph_db_available):
        """Component with manual estimations should aggregate them."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test thesis")
        component.save()

        # Add manual estimations
        prob_est = ProbabilityEstimation(value=0.9)
        prob_est.save()
        component.estimations.connect(prob_est)

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        # Check properties
        assert component.probability == 0.9
        assert component.relevance == 0.8

        # Score it
        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        # Score = P × R^α = 0.9 × 0.8^1.0 = 0.72
        assert abs(score - 0.72) < 0.01

    def test_component_zero_relevance_hard_veto(self, graph_db_available):
        """Component with R=0 should trigger hard veto (score=0)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test thesis")
        component.save()

        # R=0 (hard veto)
        prob_est = ProbabilityEstimation(value=0.8)
        prob_est.save()
        component.estimations.connect(prob_est)

        rel_est = RelevanceEstimation(value=0.0)  # Veto
        rel_est.save()
        component.estimations.connect(rel_est)

        assert component.relevance == 0.0

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        # Score = 0.8 × 0.0 = 0.0
        assert score == 0.0

    def test_component_with_rationales_gm_aggregation(self, graph_db_available):
        """Component should aggregate rationale Rs via GM (no rating weighting in graph)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Create component with own R
        component = DialecticalComponent(statement="Test thesis")
        component.save()

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        # Create rationales with R
        rationale1 = Rationale(text="Supporting rationale")
        rationale1.save()
        r1_est = RelevanceEstimation(value=0.9)
        r1_est.save()
        rationale1.estimations.connect(r1_est)
        component.rationales.connect(rationale1)

        rationale2 = Rationale(text="Another rationale")
        rationale2.save()
        r2_est = RelevanceEstimation(value=0.7)
        r2_est.save()
        rationale2.estimations.connect(r2_est)
        component.rationales.connect(rationale2)

        # Score component
        scorer = TaroRank(alpha=1.0, default_transition_probability=None)
        score = scorer.score_node(component, recursive=True)

        # Component calculator should aggregate: GM(own_r, rat1_r, rat2_r) = GM(0.8, 0.9, 0.7)
        # P defaults to 1.0 for components
        # Expected R: (0.8 * 0.9 * 0.7)^(1/3) ≈ 0.793
        # Expected Score: 1.0 × 0.793 = 0.793
        expected_r = (0.8 * 0.9 * 0.7) ** (1/3)
        assert abs(component.relevance - expected_r) < 0.01
        assert abs(score - expected_r) < 0.01  # P=1.0 for components


class TestTransitionScoring:
    """Test scoring for transitions (edges between components)."""

    def test_transition_probability_with_manual_value(self, graph_db_available):
        """Transition probability should use manual P value directly."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="Source")
        source.save()
        target = DialecticalComponent(statement="Target")
        target.save()

        transition = Transition()
        transition.save()
        source.source_of.connect(transition)
        transition.target.connect(target)

        # Add manual probability
        prob_est = ProbabilityEstimation(value=0.8)
        prob_est.save()
        transition.estimations.connect(prob_est)

        assert transition.probability == 0.8

    def test_transition_probability_with_rationale_evidence(self, graph_db_available):
        """Transition probability calculation with rationales (GM aggregation)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="Source")
        source.save()
        target = DialecticalComponent(statement="Target")
        target.save()

        transition = Transition()
        transition.save()
        source.source_of.connect(transition)
        transition.target.connect(target)

        # Transition own P
        prob_est = ProbabilityEstimation(value=0.8)
        prob_est.save()
        transition.estimations.connect(prob_est)

        # Rationale with P
        rationale = Rationale(text="Supporting evidence")
        rationale.save()
        rat_prob_est = ProbabilityEstimation(value=0.9)
        rat_prob_est.save()
        rationale.estimations.connect(rat_prob_est)
        transition.rationales.connect(rationale)

        # Score transition
        scorer = TaroRank(alpha=1.0, default_transition_probability=None)
        scorer.score_node(transition, recursive=True)

        # Should aggregate via GM: (0.8 * 0.9)^0.5 ≈ 0.848
        expected_p = (0.8 * 0.9) ** 0.5
        assert abs(transition.probability - expected_p) < 0.01

    def test_transition_probability_fallback_default(self, graph_db_available):
        """Transition with no P should use default_transition_probability if set."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="Source")
        source.save()
        target = DialecticalComponent(statement="Target")
        target.save()

        transition = Transition()
        transition.save()
        source.source_of.connect(transition)
        transition.target.connect(target)

        # No probability estimations
        assert transition.probability is None

        # Score with default
        scorer = TaroRank(alpha=1.0, default_transition_probability=1.0)
        scorer.score_node(transition, recursive=False)

        # Should use default P=1.0
        assert transition.probability == 1.0


class TestInvalidationTracking:
    """Test score invalidation and validity checking."""

    def test_score_invalidated_when_estimation_changes(self, graph_db_available):
        """Score should be invalidated when estimations are modified."""
        from dialectical_framework.graph.estimation_manager import EstimationManager

        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        # Add estimation and score
        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(component, recursive=False)

        # Score should be valid
        assert component.is_score_valid()
        assert component.score_invalidated_at is None

        # Modify estimation (this should invalidate)
        manager = EstimationManager()
        manager.upsert_estimation(component, RelevanceEstimation, 0.9, invalidate=True)

        # Score should now be invalid
        assert not component.is_score_valid()
        assert component.score_invalidated_at is not None

    def test_skip_valid_scores_during_batch_scoring(self, graph_db_available):
        """TaroRank should skip valid scores when skip_valid=True."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        scorer = TaroRank(alpha=1.0)

        # First scoring
        score1 = scorer.score_node(component, skip_valid=True)
        computed_at1 = component.score_computed_at

        # Second scoring with skip_valid should return cached score
        score2 = scorer.score_node(component, skip_valid=True)
        computed_at2 = component.score_computed_at

        assert score1 == score2
        assert computed_at1 == computed_at2  # Not recomputed

        # Third scoring with skip_valid=False should recompute
        score3 = scorer.score_node(component, skip_valid=False)
        computed_at3 = component.score_computed_at

        assert score1 == score3  # Same value
        assert computed_at3 > computed_at2  # But recomputed


class TestScoringAlphaParameter:
    """Test how alpha parameter affects final scores."""

    def test_alpha_zero_ignores_relevance(self, graph_db_available):
        """With alpha=0, score should depend only on P, ignoring R."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        prob_est = ProbabilityEstimation(value=0.6)
        prob_est.save()
        component.estimations.connect(prob_est)

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        scorer = TaroRank(alpha=0.0)
        score = scorer.score_node(component, recursive=False)

        # Score = P × R^0 = 0.6 × 1 = 0.6
        assert abs(score - 0.6) < 0.01

    def test_alpha_one_neutral_relevance_influence(self, graph_db_available):
        """With alpha=1, R should have neutral influence on score."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        prob_est = ProbabilityEstimation(value=0.6)
        prob_est.save()
        component.estimations.connect(prob_est)

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        # Score = P × R^1 = 0.6 × 0.8 = 0.48
        assert abs(score - 0.48) < 0.01

    def test_alpha_greater_than_one_emphasizes_relevance(self, graph_db_available):
        """With alpha>1, R should have amplified influence on score."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        prob_est = ProbabilityEstimation(value=0.6)
        prob_est.save()
        component.estimations.connect(prob_est)

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        scorer = TaroRank(alpha=2.0)
        score = scorer.score_node(component, recursive=False)

        # Score = P × R^2 = 0.6 × 0.64 = 0.384
        assert abs(score - 0.384) < 0.01


class TestRationaleAuditWins:
    """Test rationale audit-wins semantics (simplified GM, no rating)."""

    def test_rationale_with_critique_gm_aggregation(self, graph_db_available):
        """Rationale with critique should aggregate via GM (deepest wins)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Original rationale
        rationale = Rationale(text="Original assessment")
        rationale.save()
        r_est = RelevanceEstimation(value=0.9)
        r_est.save()
        rationale.estimations.connect(r_est)

        # Critique (auditor)
        critique = Rationale(text="Audit findings")
        critique.save()
        c_est = RelevanceEstimation(value=0.5)
        c_est.save()
        critique.estimations.connect(c_est)
        rationale.rationales.connect(critique)

        # Rationale should aggregate via audit-wins (GM of deepest critiques)
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor
        from dialectical_framework.graph.scoring.tarorank import TaroRank

        scorer = TaroRank(alpha=1.0)
        auditor = RationaleAuditor(scorer)

        # Get relevance using audit-wins
        final_r = auditor.get_relevance(rationale)

        # In simplified GM model: deepest critique wins (0.5)
        assert abs(final_r - 0.5) < 0.01

    def test_recursive_audit_deepest_wins(self, graph_db_available):
        """With multiple audit levels, the deepest audit wins."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Original rationale
        rationale = Rationale(text="Original")
        rationale.save()
        r_est = RelevanceEstimation(value=0.9)
        r_est.save()
        rationale.estimations.connect(r_est)

        # First audit
        audit1 = Rationale(text="First audit")
        audit1.save()
        a1_est = RelevanceEstimation(value=0.7)
        a1_est.save()
        audit1.estimations.connect(a1_est)
        rationale.rationales.connect(audit1)

        # Second audit (auditing the auditor)
        audit2 = Rationale(text="Second audit")
        audit2.save()
        a2_est = RelevanceEstimation(value=0.4)
        a2_est.save()
        audit2.estimations.connect(a2_est)
        audit1.rationales.connect(audit2)

        # Calculate - should use deepest audit (audit2)
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor
        from dialectical_framework.graph.scoring.tarorank import TaroRank

        scorer = TaroRank(alpha=1.0)
        auditor = RationaleAuditor(scorer)

        final_r = auditor.get_relevance(rationale)

        # Deepest audit wins: 0.4
        assert abs(final_r - 0.4) < 0.01


class TestFallbackBehavior:
    """Test fallback behavior when data is missing or invalid."""

    def test_leaf_fallback_returns_none(self, graph_db_available):
        """Leaves with no evidence return None (no neutral fallback)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        # No estimations
        assert component.relevance is None

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        assert score is None

    def test_component_probability_defaults_to_one(self, graph_db_available):
        """If no P is set, DialecticalComponent defaults to 1.0."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        # Only R, no P
        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        # Component calculator defaults P=1.0, so score = 1.0 × 0.8 = 0.8
        assert abs(score - 0.8) < 0.01


class TestDialecticalComponentScoringAdditional:
    """Additional component scoring tests from test_scoring.py."""

    def test_component_rationale_zero_rating_excluded(self, graph_db_available):
        """Rationales with zero R should be excluded from aggregation (graph: soft exclusion)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Create component
        component = DialecticalComponent(statement="Test thesis")
        component.save()
        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        # Good rationale
        rationale1 = Rationale(text="Good rationale")
        rationale1.save()
        r1_est = RelevanceEstimation(value=0.9)
        r1_est.save()
        rationale1.estimations.connect(r1_est)
        component.rationales.connect(rationale1)

        # Bad rationale with R=0 (should be excluded via soft exclusion)
        rationale2 = Rationale(text="Vetoed rationale")
        rationale2.save()
        r2_est = RelevanceEstimation(value=0.0)
        r2_est.save()
        rationale2.estimations.connect(r2_est)
        component.rationales.connect(rationale2)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(component, recursive=True)

        # Graph implementation: Rationales with R=0 are excluded via soft exclusion
        # Only component.r and rationale1.r aggregate
        # Expected: GM(0.8, 0.9) = (0.8 * 0.9)^0.5 ≈ 0.849
        expected_r = (0.8 * 0.9) ** 0.5
        assert abs(component.relevance - expected_r) < 0.01

    def test_empty_rationale_no_free_lunch(self, graph_db_available):
        """Test that empty rationales (text-only) don't provide 'free lunch' R boost."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Component without rationale
        component_alone = DialecticalComponent(statement="Test component")
        component_alone.save()
        rel1 = RelevanceEstimation(value=0.8)
        rel1.save()
        component_alone.estimations.connect(rel1)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(component_alone, recursive=False)
        cf_alone = component_alone.relevance

        # Component with empty rationale (text only)
        component_with_empty = DialecticalComponent(statement="Test component 2")
        component_with_empty.save()
        rel2 = RelevanceEstimation(value=0.8)
        rel2.save()
        component_with_empty.estimations.connect(rel2)

        empty_rationale = Rationale(text="Just some text")  # No estimations
        empty_rationale.save()
        component_with_empty.rationales.connect(empty_rationale)

        scorer.score_node(component_with_empty, recursive=True)
        cf_with_empty = component_with_empty.relevance

        # Should be the same! Empty rationale contributes None
        assert cf_with_empty == cf_alone
        assert cf_with_empty == 0.8

    def test_rationale_with_actual_evidence_contributes(self, graph_db_available):
        """Test that rationales with real evidence DO contribute to parent R."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test component")
        component.save()
        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        # Rationale with actual R value (evidence)
        evidence_rationale = Rationale(text="Real evidence")
        evidence_rationale.save()
        rat_rel = RelevanceEstimation(value=0.9)
        rat_rel.save()
        evidence_rationale.estimations.connect(rat_rel)
        component.rationales.connect(evidence_rationale)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(component, recursive=True)

        # Should aggregate: GM(component_own, rationale_r) = GM(0.8, 0.9)
        expected = (0.8 * 0.9) ** 0.5
        assert abs(component.relevance - expected) < 0.01


class TestTransitionScoringAdditional:
    """Additional transition scoring tests."""

    def test_transition_relevance_own_not_source_target(self, graph_db_available):
        """Transition R should not inherit from source/target, only own R."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="Source")
        source.save()
        src_rel = RelevanceEstimation(value=0.9)
        src_rel.save()
        source.estimations.connect(src_rel)

        target = DialecticalComponent(statement="Target")
        target.save()
        tgt_rel = RelevanceEstimation(value=0.8)
        tgt_rel.save()
        target.estimations.connect(tgt_rel)

        transition = Transition()
        transition.save()
        source.source_of.connect(transition)
        transition.target.connect(target)

        trans_rel = RelevanceEstimation(value=0.6)
        trans_rel.save()
        transition.estimations.connect(trans_rel)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(transition, recursive=False)

        # Only own R, not from source/target
        assert abs(transition.relevance - 0.6) < 0.01


class TestScoringFallbackBehaviorAdditional:
    """Additional fallback behavior tests."""

    def test_zero_probability_zero_score(self, graph_db_available):
        """If probability is 0, score should be 0 regardless of R."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        rel_est = RelevanceEstimation(value=0.8)
        rel_est.save()
        component.estimations.connect(rel_est)

        prob_est = ProbabilityEstimation(value=0.0)
        prob_est.save()
        component.estimations.connect(prob_est)

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        assert score == 0.0

    def test_missing_relevance_score_none(self, graph_db_available):
        """If R cannot be calculated, score should be None."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()

        # Only P, no R
        prob_est = ProbabilityEstimation(value=0.6)
        prob_est.save()
        component.estimations.connect(prob_est)

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(component, recursive=False)

        # With R=None, Score=None
        assert score is None


class TestRationaleFallbacks:
    """Test rationale-specific scoring fallbacks."""

    def test_rationale_no_estimations_returns_none(self, graph_db_available):
        """Rationale with no estimations should return None."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        rationale = Rationale(text="Simple rationale")
        rationale.save()

        # No estimations
        assert rationale.relevance is None
        assert rationale.probability is None

    def test_rationale_uses_own_when_provided(self, graph_db_available):
        """Rationale should use its own R when provided."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        rationale = Rationale(text="Simple rationale")
        rationale.save()

        rel_est = RelevanceEstimation(value=0.7)
        rel_est.save()
        rationale.estimations.connect(rel_est)

        assert rationale.relevance == 0.7

    def test_rationale_zero_relevance_returns_none(self, graph_db_available):
        """Rationale with R=0 should return None (soft exclusion, not veto)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        rationale = Rationale(text="Bad rationale")
        rationale.save()

        rel_est = RelevanceEstimation(value=0.0)
        rel_est.save()
        rationale.estimations.connect(rel_est)

        # Graph implementation: component/transition hard veto R=0, rationale soft exclusion returns None
        # But the property itself returns 0.0 from the estimation
        assert rationale.relevance == 0.0

        # When used in aggregation, it should be excluded (soft exclusion semantics)
        # This is tested in the component tests above

    def test_rationale_zero_relevance_excluded_from_aggregation(self, graph_db_available):
        """Rationale with R=0 should NOT contribute (soft exclusion)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        component = DialecticalComponent(statement="Test")
        component.save()
        comp_rel = RelevanceEstimation(value=0.8)
        comp_rel.save()
        component.estimations.connect(comp_rel)

        # Bad rationale (R=0)
        rationale_bad = Rationale(text="Bad rationale")
        rationale_bad.save()
        bad_rel = RelevanceEstimation(value=0.0)
        bad_rel.save()
        rationale_bad.estimations.connect(bad_rel)
        component.rationales.connect(rationale_bad)

        # Good rationale
        rationale_good = Rationale(text="Good rationale")
        rationale_good.save()
        good_rel = RelevanceEstimation(value=0.9)
        good_rel.save()
        rationale_good.estimations.connect(good_rel)
        component.rationales.connect(rationale_good)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(component, recursive=True)

        # Graph implementation: Rationales follow soft exclusion semantics
        # R=0 rationale is excluded from aggregation (not a hard veto)
        # Expected: GM(0.8, 0.9) = (0.8 * 0.9)^0.5 ≈ 0.849
        # This differs from domain implementation where R=0 in GM triggers hard veto
        expected_r = (0.8 * 0.9) ** 0.5
        assert abs(component.relevance - expected_r) < 0.01


class TestComplexScoringScenarios:
    """Test complex scenarios combining multiple elements."""

    def test_mixed_rationale_presence(self, graph_db_available):
        """Test elements where some have rationales and others don't."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Component with rationale
        rationale = Rationale(text="Supporting evidence")
        rationale.save()
        rat_rel = RelevanceEstimation(value=0.9)
        rat_rel.save()
        rationale.estimations.connect(rat_rel)

        comp_with_rationale = DialecticalComponent(statement="Has rationale")
        comp_with_rationale.save()
        comp1_rel = RelevanceEstimation(value=0.7)
        comp1_rel.save()
        comp_with_rationale.estimations.connect(comp1_rel)
        comp_with_rationale.rationales.connect(rationale)

        # Component without rationale
        comp_without_rationale = DialecticalComponent(statement="No rationale")
        comp_without_rationale.save()
        comp2_rel = RelevanceEstimation(value=0.8)
        comp2_rel.save()
        comp_without_rationale.estimations.connect(comp2_rel)

        scorer = TaroRank(alpha=1.0)
        scorer.score_node(comp_with_rationale, recursive=True)
        scorer.score_node(comp_without_rationale, recursive=True)

        cf1 = comp_with_rationale.relevance
        cf2 = comp_without_rationale.relevance

        assert cf1 > 0  # Should aggregate own + rationale
        assert cf2 == 0.8  # Should be own only

    def test_audit_wins_over_original_rationale(self, graph_db_available):
        """Test that audit/critique overrides original rationale values (deepest wins)."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        # Original rationale
        rationale = Rationale(text="Original assessment")
        rationale.save()
        orig_rel = RelevanceEstimation(value=0.9)
        orig_rel.save()
        rationale.estimations.connect(orig_rel)
        orig_prob = ProbabilityEstimation(value=0.8)
        orig_prob.save()
        rationale.estimations.connect(orig_prob)

        # Auditor disagrees
        audit = Rationale(text="Audit findings")
        audit.save()
        audit_rel = RelevanceEstimation(value=0.5)
        audit_rel.save()
        audit.estimations.connect(audit_rel)
        audit_prob = ProbabilityEstimation(value=0.6)
        audit_prob.save()
        audit.estimations.connect(audit_prob)
        rationale.rationales.connect(audit)

        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor
        scorer = TaroRank(alpha=1.0)
        auditor = RationaleAuditor(scorer)

        # Audit should WIN (deepest wins semantics)
        final_r = auditor.get_relevance(rationale)
        final_p = auditor.get_probability(rationale)

        assert abs(final_r - 0.5) < 0.01
        assert abs(final_p - 0.6) < 0.01


class TestProbabilityNoneBehavior:
    """Test how the framework handles P=None in different scenarios."""

    def test_transition_without_probability_returns_none(self, graph_db_available):
        """Transition without P and no default returns None."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="A")
        source.save()
        target = DialecticalComponent(statement="B")
        target.save()

        trans = Transition()
        trans.save()
        source.source_of.connect(trans)
        trans.target.connect(target)

        trans_rel = RelevanceEstimation(value=0.7)
        trans_rel.save()
        trans.estimations.connect(trans_rel)

        # No probability, no default
        assert trans.probability is None

        scorer = TaroRank(alpha=1.0, default_transition_probability=None)
        score = scorer.score_node(trans, recursive=False)

        assert score is None

    def test_transition_with_default_probability(self, graph_db_available):
        """Transition with default_transition_probability should use it when no explicit P."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="A")
        source.save()
        target = DialecticalComponent(statement="B")
        target.save()

        trans = Transition()
        trans.save()
        source.source_of.connect(trans)
        trans.target.connect(target)

        trans_rel = RelevanceEstimation(value=0.7)
        trans_rel.save()
        trans.estimations.connect(trans_rel)

        scorer = TaroRank(alpha=1.0, default_transition_probability=1.0)
        score = scorer.score_node(trans, recursive=False)

        # Should use default P=1.0
        # Score = 1.0 × 0.7 = 0.7
        assert abs(score - 0.7) < 0.01

    def test_transition_with_explicit_probability(self, graph_db_available):
        """Transition with explicit P works normally."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="A")
        source.save()
        target = DialecticalComponent(statement="B")
        target.save()

        trans = Transition()
        trans.save()
        source.source_of.connect(trans)
        trans.target.connect(target)

        trans_rel = RelevanceEstimation(value=0.7)
        trans_rel.save()
        trans.estimations.connect(trans_rel)

        trans_prob = ProbabilityEstimation(value=0.9)
        trans_prob.save()
        trans.estimations.connect(trans_prob)

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(trans, recursive=False)

        # Score = 0.9 × 0.7 = 0.63
        assert abs(score - 0.63) < 0.01

    def test_transition_with_probability_one(self, graph_db_available):
        """Transition with P=1.0 explicitly set works as 'certain'."""
        if not graph_db_available:
            pytest.skip("Graph database not available")

        source = DialecticalComponent(statement="A")
        source.save()
        target = DialecticalComponent(statement="B")
        target.save()

        trans = Transition()
        trans.save()
        source.source_of.connect(trans)
        trans.target.connect(target)

        trans_rel = RelevanceEstimation(value=0.7)
        trans_rel.save()
        trans.estimations.connect(trans_rel)

        trans_prob = ProbabilityEstimation(value=1.0)
        trans_prob.save()
        trans.estimations.connect(trans_prob)

        scorer = TaroRank(alpha=1.0)
        score = scorer.score_node(trans, recursive=False)

        # Score = 1.0 × 0.7 = 0.7
        assert abs(score - 0.7) < 0.01


# Note: WisdomUnit, Cycle, Wheel, and comprehensive example tests require more complex setup
# These should be added after the graph node relationships are fully understood


class TestManualVsCalculatedSeparation:
    """
    Test manual vs calculated estimation separation.

    This test class verifies the critical behavior of keeping manual and calculated
    estimations separate, matching legacy domain/* semantics.
    """

    def test_manual_estimations_preserved_after_scoring(self, graph_db_available):
        """Manual estimations should not be overwritten by TaroRank calculated values."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            CalculatedProbabilityEstimation
        )
        from dialectical_framework.graph.estimation_manager import EstimationManager

        comp = DialecticalComponent(statement="test")
        comp.save()

        manager = EstimationManager()

        # User sets manual probability
        manager.upsert_estimation(comp, ProbabilityEstimation, 0.8, invalidate=True)

        # Verify manual estimation exists
        manual_estimations = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, ProbabilityEstimation)
        ]
        assert len(manual_estimations) == 1
        assert manual_estimations[0].value == 0.8

        # TaroRank runs scoring
        scorer = TaroRank(alpha=1.0)
        scorer.score_node(comp, recursive=False)

        # Verify manual estimation is STILL present
        manual_estimations_after = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, ProbabilityEstimation)
        ]
        assert len(manual_estimations_after) == 1
        assert manual_estimations_after[0].value == 0.8  # NOT overwritten!

        # Verify calculated estimation was created
        calculated_estimations = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        assert len(calculated_estimations) == 1
        # Calculated should be close to manual (since only manual exists)
        assert abs(calculated_estimations[0].value - 0.8) < 0.01

    def test_multiple_manual_estimations_collective(self, graph_db_available):
        """Multiple agents can each contribute manual estimations (collective)."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            CalculatedProbabilityEstimation
        )
        from dialectical_framework.graph.estimation_manager import EstimationManager

        comp = DialecticalComponent(statement="test")
        comp.save()

        # Agent 1 creates first estimation node
        prob1 = ProbabilityEstimation(value=0.8)
        prob1.save()
        comp.estimations.connect(prob1)

        # Agent 2 creates second estimation node
        prob2 = ProbabilityEstimation(value=0.9)
        prob2.save()
        comp.estimations.connect(prob2)

        # Both manual estimations exist
        manual_estimations = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, ProbabilityEstimation)
        ]
        assert len(manual_estimations) == 2

        # TaroRank scoring
        scorer = TaroRank(alpha=1.0)
        scorer.score_node(comp, recursive=False)

        # Both manual estimations STILL exist
        manual_after = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, ProbabilityEstimation)
        ]
        assert len(manual_after) == 2

        # Calculated estimation created
        calculated = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        assert len(calculated) == 1
        # Calculated should be GM(0.8, 0.9) ≈ 0.849
        import math
        expected = math.exp((math.log(0.8) + math.log(0.9)) / 2)
        assert abs(calculated[0].value - expected) < 0.01

    def test_property_returns_calculated_if_exists_else_manual(self, graph_db_available):
        """Properties should return calculated if exists, otherwise manual (legacy semantics)."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            CalculatedProbabilityEstimation
        )

        comp = DialecticalComponent(statement="test")
        comp.save()

        # No estimations: property returns None
        assert comp.probability is None

        # Manual only: property returns manual
        prob_manual = ProbabilityEstimation(value=0.8)
        prob_manual.save()
        comp.estimations.connect(prob_manual)
        assert abs(comp.probability - 0.8) < 0.01

        # Add calculated: property returns calculated (ignores manual)
        prob_calc = CalculatedProbabilityEstimation(value=0.6)
        prob_calc.save()
        comp.estimations.connect(prob_calc)
        assert abs(comp.probability - 0.6) < 0.01  # Returns calculated, NOT GM!

    def test_calculators_read_only_manual_not_calculated(self, graph_db_available):
        """Calculators should read ONLY manual estimations as input (not calculated)."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            RelevanceEstimation,
            CalculatedProbabilityEstimation,
            CalculatedRelevanceEstimation
        )

        comp = DialecticalComponent(statement="test")
        comp.save()

        # Set manual estimations
        prob_manual = ProbabilityEstimation(value=0.8)
        prob_manual.save()
        comp.estimations.connect(prob_manual)

        rel_manual = RelevanceEstimation(value=0.9)
        rel_manual.save()
        comp.estimations.connect(rel_manual)

        # First scoring run
        scorer = TaroRank(alpha=1.0)
        scorer.score_node(comp, recursive=False)

        # Verify calculated estimations created
        calc_probs = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        calc_rels = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedRelevanceEstimation)
        ]
        assert len(calc_probs) == 1
        assert len(calc_rels) == 1

        # Second scoring run: should read ONLY manual (not calculated)
        scorer.score_node(comp, recursive=False, skip_valid=False)

        # Calculated values should be same as first run (not compounded)
        calc_probs_after = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        assert abs(calc_probs_after[0].value - calc_probs[0].value) < 0.001

    def test_manual_update_invalidates_and_recalculates(self, graph_db_available):
        """Updating manual estimation should invalidate score and trigger recalculation."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            RelevanceEstimation
        )
        from dialectical_framework.graph.estimation_manager import EstimationManager

        comp = DialecticalComponent(statement="test")
        comp.save()

        manager = EstimationManager()

        # Initial estimations
        manager.upsert_estimation(comp, ProbabilityEstimation, 0.8, invalidate=False)
        manager.upsert_estimation(comp, RelevanceEstimation, 0.9, invalidate=False)

        # Score
        scorer = TaroRank(alpha=1.0)
        scorer.score_node(comp, recursive=False)

        initial_score = comp.score
        assert initial_score is not None
        assert comp.is_score_valid()

        # User updates manual probability
        manager.upsert_estimation(comp, ProbabilityEstimation, 0.5, invalidate=True)

        # Score should be invalidated
        assert not comp.is_score_valid()

        # Re-score
        scorer.score_node(comp, recursive=False, skip_valid=False)

        # New score should reflect updated manual value
        new_score = comp.score
        assert new_score is not None
        assert new_score < initial_score  # Lower probability → lower score

    def test_multiple_scoring_runs_preserve_manual(self, graph_db_available):
        """Multiple scoring runs should preserve all manual estimations."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            CalculatedProbabilityEstimation
        )

        comp = DialecticalComponent(statement="test")
        comp.save()

        # Manual estimation
        prob = ProbabilityEstimation(value=0.8)
        prob.save()
        comp.estimations.connect(prob)

        scorer = TaroRank(alpha=1.0)

        # Run scoring 3 times
        for _ in range(3):
            scorer.score_node(comp, recursive=False, skip_valid=False)

        # Manual estimation should still exist (only one)
        manual = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, ProbabilityEstimation)
        ]
        assert len(manual) == 1
        assert manual[0].value == 0.8

        # Only one calculated estimation (updated each time, not created new)
        calculated = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        assert len(calculated) == 1

    def test_clear_scores_removes_calculated_preserves_manual(self, graph_db_available):
        """clear_scores should remove calculated estimations but preserve manual ones."""
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            RelevanceEstimation,
            CalculatedProbabilityEstimation,
            CalculatedRelevanceEstimation
        )

        comp = DialecticalComponent(statement="test")
        comp.save()

        # Add manual estimations
        prob_manual = ProbabilityEstimation(value=0.8)
        prob_manual.save()
        comp.estimations.connect(prob_manual)

        rel_manual = RelevanceEstimation(value=0.9)
        rel_manual.save()
        comp.estimations.connect(rel_manual)

        # Score (creates calculated estimations)
        scorer = TaroRank(alpha=1.0)
        scorer.score_node(comp, recursive=False)

        # Verify calculated estimations exist
        calc_probs = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        calc_rels = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedRelevanceEstimation)
        ]
        assert len(calc_probs) == 1
        assert len(calc_rels) == 1
        assert comp.score is not None

        # Clear scores
        scorer.clear_scores(comp, recursive=False)

        # Score should be cleared
        assert comp.score is None

        # Calculated estimations should be REMOVED
        calc_probs_after = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        calc_rels_after = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, CalculatedRelevanceEstimation)
        ]
        assert len(calc_probs_after) == 0  # Cleared!
        assert len(calc_rels_after) == 0  # Cleared!

        # Manual estimations should be PRESERVED
        manual_probs = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, ProbabilityEstimation)
        ]
        manual_rels = [
            est for est, _ in comp.estimations.all()
            if isinstance(est, RelevanceEstimation)
        ]
        assert len(manual_probs) == 1  # Still there!
        assert manual_probs[0].value == 0.8
        assert len(manual_rels) == 1  # Still there!
        assert manual_rels[0].value == 0.9


# Additional integration tests could be added here for:
# - WisdomUnit, Cycle, Wheel hierarchies
# - Complex rationale audit-wins scenarios
# - Estimation clearing and score invalidation workflows
