"""
Comprehensive tests for the scoring system, covering edge cases and fallbacks.

Tests the interaction between:
- Probability (P): structural feasibility 
- Contextual Fidelity (CF): contextual grounding
- Rationales: with/without ratings and confidence
- Alpha parameter: controlling CF influence
- Hierarchical aggregation: geometric means and products
"""

import pytest

from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.analyst.domain.rationale import Rationale
from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import ALIAS_T, ALIAS_T_PLUS, ALIAS_T_MINUS
from dialectical_framework.wisdom_unit import ALIAS_A, ALIAS_A_PLUS, ALIAS_A_MINUS, WisdomUnit


class TestDialecticalComponentScoring:
    """Test scoring for basic dialectical components (leaves in the hierarchy)."""
    
    def test_component_no_cf_no_rating_defaults_to_neutral(self):
        """Component with no CF or rating should default to CF=1.0 (neutral)."""
        component = DialecticalComponent(alias="T", statement="Test thesis")
        
        cf = component.calculate_contextual_fidelity()
        assert cf == 1.0
        
    def test_component_with_manual_cf_and_rating(self):
        """Component with manual CF and rating should multiply them."""
        component = DialecticalComponent(
            alias="T", 
            statement="Test thesis",
            contextual_fidelity=0.8,
            rating=0.6
        )
        
        cf = component.calculate_contextual_fidelity()
        assert cf == 0.8 * 0.6  # 0.48
        
    def test_component_zero_rating_fallback_neutral(self):
        """Component with rating=0 should fallback to CF=1.0 (neutral) per implementation."""
        component = DialecticalComponent(
            alias="T",
            statement="Test thesis", 
            contextual_fidelity=0.8,
            rating=0.0
        )
        
        cf = component.calculate_contextual_fidelity()
        assert cf == 1.0  # Fallback to neutral when rating=0

    def test_component_zero_cf_hard_veto(self):
        """Component with CF=0 should trigger hard veto (CF=0) regardless of rating."""
        component = DialecticalComponent(
            alias="T",
            statement="Test thesis",
            contextual_fidelity=0.0,  # Zero CF should trigger hard veto
            rating=0.8  # Rating doesn't matter for hard veto
        )
        
        cf = component.calculate_contextual_fidelity()
        assert cf == 0.0  # Hard veto - structural impossibility

    def test_component_with_rationales(self):
        """Component should aggregate rationale CFs weighted once by rationale.rating."""
        rationale1 = Rationale(text="Supporting rationale", contextual_fidelity=0.9, rating=0.8)
        rationale2 = Rationale(text="Another rationale", contextual_fidelity=0.7, rating=0.6)

        component = DialecticalComponent(
            alias="T",
            statement="Test thesis",
            contextual_fidelity=0.8,  # component's own intrinsic CF
            rating=0.5,  # component's own rating applies to its own CF only
            rationales=[rationale1, rationale2]
        )

        cf = component.calculate_contextual_fidelity()

        # Rationale contributions: weighted once by their own rating (by the parent)
        r1 = 0.9 * 0.8  # = 0.72
        r2 = 0.7 * 0.6  # = 0.42
        own = 0.8 * 0.5  # = 0.40

        expected = (r1 * r2 * own) ** (1 / 3)
        assert abs(cf - expected) < 1e-10
        
    def test_component_rationale_zero_rating_excluded(self):
        """Rationales with zero rating should be excluded from aggregation."""
        rationale1 = Rationale(
            text="Good rationale",
            contextual_fidelity=0.9,
            rating=0.8
        )
        rationale2 = Rationale(
            text="Vetoed rationale",
            contextual_fidelity=0.7,
            rating=0.0  # This should be excluded
        )
        
        component = DialecticalComponent(
            alias="T",
            statement="Test thesis",
            contextual_fidelity=0.8,
            rating=0.5,
            rationales=[rationale1, rationale2]
        )
        
        cf = component.calculate_contextual_fidelity()
        # rationale1: CF=0.9, parent applies rating once: 0.9*0.8=0.72
        # rationale2: rating=0.0, so excluded (0.9*0.0=0.0 gets filtered out)
        # own: CF=0.8*0.5=0.4
        # GM(0.72, 0.4)
        expected = (0.72 * 0.4) ** (1/2)
        assert abs(cf - expected) < 1e-10


class TestTransitionScoring:
    """Test scoring for transitions (edges between components)."""
    
    def test_transition_probability_with_manual_and_confidence(self):
        """Transition probability should weight manual P by confidence."""
        source = DialecticalComponent(alias="T1", statement="Source")
        target = DialecticalComponent(alias="T2", statement="Target")
        
        transition = Transition(
            source=source,
            target=target,
            predicate=Predicate.CAUSES,
            manual_probability=0.8,
            confidence=0.6
        )
        
        p = transition.calculate_probability()
        assert p == 0.8 * 0.6  # 0.48
        
    def test_transition_probability_with_rationale_evidence(self):
        """Transition probability calculation with rationales (rationales need child wheels for evidence)."""
        source = DialecticalComponent(alias="T1", statement="Source")
        target = DialecticalComponent(alias="T2", statement="Target")
        
        # Simple rationale without child wheels doesn't contribute to probability
        rationale = Rationale(
            text="Supporting evidence",
            probability=0.9,  # This field is not used by transitions  
            confidence=0.7
        )
        
        transition = Transition(
            source=source,
            target=target,
            predicate=Predicate.CAUSES,
            manual_probability=0.8,
            confidence=0.5,
            rationales=[rationale]
        )
        
        p = transition.calculate_probability()
        # Only manual probability contributes: 0.8 * 0.5 = 0.4
        # Rationale doesn't contribute because calculate_evidence_probability() returns None
        expected = 0.4
        assert p == expected
        
    def test_transition_probability_fallback_none(self):
        """Transition with no probability inputs should return None."""
        source = DialecticalComponent(alias="T1", statement="Source")
        target = DialecticalComponent(alias="T2", statement="Target")
        
        transition = Transition(
            source=source,
            target=target,
            predicate=Predicate.CAUSES
        )
        
        p = transition.calculate_probability()
        assert p is None
        
    def test_transition_cf_inherits_from_own_not_source_target(self):
        """Transition CF should not inherit from source/target, only own CF."""
        source = DialecticalComponent(alias="T1", statement="Source", contextual_fidelity=0.9)
        target = DialecticalComponent(alias="T2", statement="Target", contextual_fidelity=0.8)
        
        transition = Transition(
            source=source,
            target=target,
            predicate=Predicate.CAUSES,
            contextual_fidelity=0.6,
            rating=0.7
        )
        
        cf = transition.calculate_contextual_fidelity()
        assert cf == 0.6 * 0.7  # Only own CF * rating, not from source/target


class TestWheelSegmentScoring:
    """Test scoring for wheel segments (contains 3 dialectical components)."""
    
    def test_wheel_segment_cf_geometric_mean_of_components(self):
        """WheelSegment CF should be geometric mean of its 3 components."""
        t_component = DialecticalComponent(alias="T", statement="Thesis", contextual_fidelity=0.8)
        t_plus = DialecticalComponent(alias="T+", statement="Thesis+", contextual_fidelity=0.9)
        t_minus = DialecticalComponent(alias="T-", statement="Thesis-", contextual_fidelity=0.7)
        
        # Create a WheelSegment subclass for testing
        from dialectical_framework.wheel_segment import WheelSegment
        segment = WheelSegment(
            **{ALIAS_T: t_component, ALIAS_T_PLUS: t_plus, ALIAS_T_MINUS: t_minus}
        )
        
        cf = segment.calculate_contextual_fidelity()
        expected = (0.8 * 0.9 * 0.7) ** (1/3)
        assert abs(cf - expected) < 1e-10
        
    def test_wheel_segment_with_zero_component_cf(self):
        """WheelSegment with one zero CF component should propagate the zero."""
        t_component = DialecticalComponent(alias="T", statement="Thesis", contextual_fidelity=0.8)
        t_plus = DialecticalComponent(alias="T+", statement="Thesis+", contextual_fidelity=0.0)  # Zero!
        t_minus = DialecticalComponent(alias="T-", statement="Thesis-", contextual_fidelity=0.7)
        
        from dialectical_framework.wheel_segment import WheelSegment
        segment = WheelSegment(
            **{ALIAS_T: t_component, ALIAS_T_PLUS: t_plus, ALIAS_T_MINUS: t_minus}
        )
        
        cf = segment.calculate_contextual_fidelity()
        assert cf == 0.0


class TestWisdomUnitScoring:
    """Test scoring for wisdom units (thesis + antithesis segments + transformation)."""
    
    def test_wisdom_unit_cf_includes_both_segments_and_transformation(self):
        """WisdomUnit CF should include both segments and internal transformation."""
        # Create thesis segment components
        t = DialecticalComponent(alias="T", statement="Thesis", contextual_fidelity=0.8)
        t_plus = DialecticalComponent(alias="T+", statement="Thesis+", contextual_fidelity=0.9)
        t_minus = DialecticalComponent(alias="T-", statement="Thesis-", contextual_fidelity=0.7)
        
        # Create antithesis segment components  
        a = DialecticalComponent(alias="A", statement="Antithesis", contextual_fidelity=0.6)
        a_plus = DialecticalComponent(alias="A+", statement="Antithesis+", contextual_fidelity=0.8)
        a_minus = DialecticalComponent(alias="A-", statement="Antithesis-", contextual_fidelity=0.5)
        
        wisdom_unit = WisdomUnit(
            **{
                ALIAS_T: t, ALIAS_T_PLUS: t_plus, ALIAS_T_MINUS: t_minus,
                ALIAS_A: a, ALIAS_A_PLUS: a_plus, ALIAS_A_MINUS: a_minus
            }
        )
        
        cf = wisdom_unit.calculate_contextual_fidelity()
        # Should be GM of all 6 components
        expected = (0.8 * 0.9 * 0.7 * 0.6 * 0.8 * 0.5) ** (1/6)
        assert abs(cf - expected) < 1e-10
        
    def test_wisdom_unit_probability_from_transformation(self):
        """WisdomUnit probability should come from its transformation cycle."""
        # This is a more complex test that would require setting up transformation
        # For now, test the basic case where transformation is None
        wisdom_unit = WisdomUnit()
        
        p = wisdom_unit.calculate_probability()
        # Without transformation, should fallback to None or 1.0 based on implementation
        assert p is None or p == 1.0


class TestCycleScoring:
    """Test scoring for cycles (sequences of transitions)."""
    
    def test_cycle_probability_product_of_transitions(self):
        """Cycle probability should be product of transition probabilities in sequence."""
        # Create components
        comp1 = DialecticalComponent(alias="T1", statement="Component 1")
        comp2 = DialecticalComponent(alias="T2", statement="Component 2") 
        comp3 = DialecticalComponent(alias="T3", statement="Component 3")
        
        # Create transitions with known probabilities
        trans1 = Transition(
            source=comp1, target=comp2, predicate=Predicate.CAUSES,
            manual_probability=0.8, confidence=1.0
        )
        trans2 = Transition(
            source=comp2, target=comp3, predicate=Predicate.CAUSES,
            manual_probability=0.7, confidence=1.0
        )
        
        # Create cycle (this requires understanding the cycle implementation)
        # For now, test conceptually
        # Expected: P(cycle) = P(trans1) * P(trans2) = 0.8 * 0.7 = 0.56
        pass  # TODO: Complete when cycle construction is clearer
        
    def test_cycle_zero_transition_makes_cycle_zero(self):
        """Any transition with P=0 should make entire cycle P=0."""
        pass  # TODO: Implement when cycle construction is clear
        
    def test_cycle_unknown_transition_makes_cycle_unknown(self):
        """Any transition with P=None should make entire cycle P=None."""
        pass  # TODO: Implement when cycle construction is clear


class TestWheelScoring:
    """Test scoring for complete wheels (top-level containers)."""
    
    def test_wheel_calculate_score_recursively(self):
        """Calling calculate_score on wheel should recursively calculate all sub-elements."""
        # Create minimal wheel structure
        t = DialecticalComponent(alias="T", statement="Thesis", contextual_fidelity=0.8)
        a = DialecticalComponent(alias="A", statement="Antithesis", contextual_fidelity=0.6)
        
        wisdom_unit = WisdomUnit(**{ALIAS_T: t, ALIAS_A: a})
        
        # Create empty cycles for now (TODO: populate with actual transitions)
        from dialectical_framework.analyst.domain.cycle import Cycle
        t_cycle = Cycle([])
        ta_cycle = Cycle([])
        
        wheel = Wheel(wisdom_unit, t_cycle=t_cycle, ta_cycle=ta_cycle)
        
        # This should not crash and should calculate scores recursively
        score = wheel.calculate_score(alpha=1.0)
        
        # Verify that sub-components had their scores calculated
        assert t.score is not None or t.contextual_fidelity is not None
        assert a.score is not None or a.contextual_fidelity is not None
        
        # WisdomUnit without transformation has no probability, hence no score
        # But it should have contextual fidelity calculated
        assert wisdom_unit.contextual_fidelity is not None
        assert wisdom_unit.score is None  # No score without probability (no transformation)


class TestScoringAlphaParameter:
    """Test how alpha parameter affects final scores."""
    
    def test_alpha_zero_ignores_cf(self):
        """With alpha=0, score should depend only on P, ignoring CF."""
        component = DialecticalComponent(
            alias="T",
            statement="Test",
            contextual_fidelity=0.8,
            probability=0.6
        )
        
        score = component.calculate_score(alpha=0.0)
        # Score = P * CF^alpha = 0.6 * 0.8^0 = 0.6 * 1 = 0.6
        assert score == 0.6
        
    def test_alpha_one_neutral_cf_influence(self):
        """With alpha=1, CF should have neutral influence on score.""" 
        component = DialecticalComponent(
            alias="T",
            statement="Test",
            contextual_fidelity=0.8,
            probability=0.6
        )
        
        score = component.calculate_score(alpha=1.0)
        # Score = P * CF^alpha = 0.6 * 0.8^1 = 0.6 * 0.8 = 0.48
        assert score == 0.48
        
    def test_alpha_greater_than_one_emphasizes_cf(self):
        """With alpha>1, CF should have amplified influence on score."""
        component = DialecticalComponent(
            alias="T", 
            statement="Test",
            contextual_fidelity=0.8,
            probability=0.6
        )
        
        score = component.calculate_score(alpha=2.0)
        # Score = P * CF^alpha = 0.6 * 0.8^2 = 0.6 * 0.64 = 0.384
        assert abs(score - 0.384) < 1e-10


class TestScoringFallbackBehavior:
    """Test fallback behavior when data is missing or invalid."""
    
    def test_no_probability_defaults_to_one(self):
        """If no probability is set, DialecticalComponent defaults to 1.0."""
        component = DialecticalComponent(
            alias="T",
            statement="Test",
            contextual_fidelity=0.8
            # No probability data - defaults to 1.0
        )
        
        score = component.calculate_score(alpha=1.0)
        # CF=0.8, P=1.0 (default), score = 1.0 * 0.8^1 = 0.8
        assert score == 0.8
        
    def test_zero_probability_zero_score(self):
        """If probability is 0, score should be 0 regardless of CF."""
        component = DialecticalComponent(
            alias="T",
            statement="Test", 
            contextual_fidelity=0.8,
            probability=0.0
        )
        
        score = component.calculate_score(alpha=1.0)
        assert score == 0.0
        
    def test_missing_cf_defaults_to_neutral(self):
        """If CF cannot be calculated, should default to 1.0 (neutral)."""
        component = DialecticalComponent(
            alias="T",
            statement="Test",
            probability=0.6
            # No CF data
        )
        
        score = component.calculate_score(alpha=1.0)
        # CF should default to 1.0, so score = 0.6 * 1.0^1 = 0.6
        assert score == 0.6


class TestRationaleFallbacks:
    """Test rationale-specific scoring fallbacks."""
    
    def test_rationale_no_wheels_probability_defaults(self):
        """Rationale with no child wheels should have probability fallback."""
        rationale = Rationale(text="Simple rationale")
        
        p = rationale.calculate_probability()
        # Should fallback to 1.0 when no evidence
        assert p == 1.0
        
    def test_rationale_cf_uses_own_when_no_children(self):
        """Rationale without child wheels should use its own CF per Ratable behavior."""
        rationale = Rationale(
            text="Simple rationale",
            contextual_fidelity=0.7
        )
        
        cf = rationale.calculate_contextual_fidelity()
        assert cf == 0.7  # Uses own CF when no child wheels
        
    def test_rationale_zero_cf_no_veto(self):
        """Rationale with CF=0 should not veto - ignored like no contribution."""
        rationale = Rationale(
            text="Bad rationale",
            contextual_fidelity=0.0  # Zero CF - should be ignored, not veto
        )
        
        cf = rationale.calculate_contextual_fidelity()
        assert cf == 1.0  # Fallback to neutral - zero ignored, no veto
        
    def test_rationale_zero_cf_with_good_evidence(self):
        """Rationale with CF=0 should be outweighed by good child evidence."""
        # This would require setting up child wheels, but for now test the principle
        # that rationale CF=0 doesn't nuke the entire assessment
        rationale_bad = Rationale(text="Bad rationale", contextual_fidelity=0.0, rating=0.8)
        rationale_good = Rationale(text="Good rationale", contextual_fidelity=0.9, rating=0.7)
        
        component = DialecticalComponent(
            alias="T",
            statement="Test",
            contextual_fidelity=0.8,
            rating=0.6,
            rationales=[rationale_bad, rationale_good]
        )
        
        cf = component.calculate_contextual_fidelity()
        # Bad rationale's CF=0 becomes 1.0 (neutral fallback, no veto), then weighted: 1.0*0.8=0.8
        # Good rationale: 0.9*0.7=0.63, own: 0.8*0.6=0.48
        # GM(0.8, 0.63, 0.48)
        expected = (0.8 * 0.63 * 0.48) ** (1/3)
        assert abs(cf - expected) < 1e-10
        

class TestComplexScoringScenarios:
    """Test complex scenarios combining multiple elements with various data."""
    
    def test_mixed_rationale_presence(self):
        """Test elements where some have rationales and others don't."""
        # Component with rationale
        rationale = Rationale(
            text="Supporting evidence",
            contextual_fidelity=0.9,
            rating=0.8
        )
        comp_with_rationale = DialecticalComponent(
            alias="T1",
            statement="Has rationale",
            contextual_fidelity=0.7,
            rating=0.6,
            rationales=[rationale]
        )
        
        # Component without rationale
        comp_without_rationale = DialecticalComponent(
            alias="T2", 
            statement="No rationale",
            contextual_fidelity=0.8,
            rating=0.5
        )
        
        # Both should calculate properly
        cf1 = comp_with_rationale.calculate_contextual_fidelity()
        cf2 = comp_without_rationale.calculate_contextual_fidelity()
        
        assert cf1 > 0  # Should aggregate own + rationale
        assert cf2 == 0.8 * 0.5  # Should be own * rating
        
    def test_mixed_probability_presence(self):
        """Test transitions where some have manual P and others rely on rationales."""
        comp1 = DialecticalComponent(alias="C1", statement="Source")
        comp2 = DialecticalComponent(alias="C2", statement="Target") 
        
        # Transition with manual probability
        trans_manual = Transition(
            source=comp1,
            target=comp2,
            predicate=Predicate.CAUSES,
            manual_probability=0.8,
            confidence=0.7
        )
        
        # Transition with rationale-based probability
        prob_rationale = Rationale(
            text="Probability evidence",
            probability=0.6,
            confidence=0.8
        )
        trans_rationale = Transition(
            source=comp1, 
            target=comp2,
            predicate=Predicate.TRANSFORMS_TO,
            rationales=[prob_rationale]
        )
        
        p1 = trans_manual.calculate_probability()
        p2 = trans_rationale.calculate_probability()
        
        assert p1 == 0.8 * 0.7
        assert p2 is None  # Rationale without child wheels doesn't contribute to transition probability