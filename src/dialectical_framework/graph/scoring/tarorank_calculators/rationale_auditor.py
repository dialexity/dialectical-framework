"""
Implements audit-wins semantics for rationale hierarchies.

Audit-wins logic:
- Rationales can have child rationales (critiques)
- Critiques override parent rationale values
- Deepest level critiques win (recursive)
- Critiques with rating=0 are ignored (explicit exclusion)
- Multiple critiques aggregate via GM (if unrated) or weighted average (if rated)
"""

from __future__ import annotations

from typing import Optional, Type, TypeVar, TYPE_CHECKING

from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.rationale import Rationale
    from dialectical_framework.graph.nodes.estimation import Estimation
    from dialectical_framework.graph.scoring.tarorank import TaroRank

T = TypeVar('T', bound='Estimation')


class RationaleAuditor:
    """
    Implements audit-wins semantics for rationale hierarchies.

    Matches legacy domain/rationale.py implementation exactly:
    - Filter critiques with rating=0
    - Use deepest level critiques (recursive)
    - Aggregate via GM if unrated, weighted average if rated
    - Filter values <= 0
    """

    def __init__(self, scorer: TaroRank):
        """
        Initialize auditor with scorer reference.

        Args:
            scorer: TaroRank instance
        """
        self.scorer = scorer

    def get_probability(self, rationale: Rationale) -> Optional[float]:
        """
        Get probability from rationale using audit-wins semantics.

        Matches legacy Rationale.calculate_probability() exactly:
        1. Get deepest critiques (filter rating=0)
        2. If critiques exist, aggregate them (GM or weighted avg)
        3. Otherwise use own manual probability
        4. No hard veto on P=0 (soft exclusion)

        Args:
            rationale: Rationale node to evaluate

        Returns:
            P value or None if no probability evidence
        """
        from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation

        # Get deepest critiques (matching legacy _get_deepest_critiques)
        deepest_critiques = self._get_deepest_critiques(rationale)

        if deepest_critiques:
            # Aggregate deepest critique probabilities
            critique_p = self._aggregate_critique_values(
                deepest_critiques,
                lambda c: self._get_manual_value(c, ProbabilityEstimation)
            )
            if critique_p is not None:
                return critique_p

        # No critiques or critiques have no value → use own manual probability
        return self._get_manual_value(rationale, ProbabilityEstimation)

    def get_relevance(self, rationale: Rationale) -> Optional[float]:
        """
        Get relevance from rationale using audit-wins semantics.

        Matches legacy Rationale.calculate_relevance() exactly:
        1. Get deepest critiques (filter rating=0)
        2. If critiques exist, aggregate them (GM or weighted avg)
        3. Otherwise use parent's normal aggregation logic
        4. No hard veto on R=0 (soft exclusion)

        Note: FeasibilityEstimation is used as fallback for relevance
        (same priority as in AssessableEntity.relevance property).

        Args:
            rationale: Rationale node to evaluate

        Returns:
            R value or None if no relevance evidence
        """

        # Get deepest critiques (matching legacy _get_deepest_critiques)
        deepest_critiques = self._get_deepest_critiques(rationale)

        if deepest_critiques:
            # Aggregate deepest critique relevances
            # Try RelevanceEstimation first, then FeasibilityEstimation as fallback
            critique_r = self._aggregate_critique_values(
                deepest_critiques,
                lambda c: self._get_manual_relevance_with_fallback(c)
            )
            if critique_r is not None:
                return critique_r

        # No critiques or critiques have no value → use own manual relevance
        # (Simplified: no wheels support, just own value)
        return self._get_manual_relevance_with_fallback(rationale)

    def _get_deepest_critiques(self, rationale: Rationale) -> list[Rationale]:
        """
        Get all critiques at the deepest recursion level.

        Matches legacy Rationale._get_deepest_critiques() exactly:
        - Filter out critiques with rating=0 (explicitly ignored)
        - If critiques have their own critiques, recurse
        - Return all critiques at deepest level

        Args:
            rationale: Rationale to search

        Returns:
            List of critique nodes at deepest level
        """
        critiques_list = [crit for crit, _ in rationale.critiques.all()]

        if not critiques_list:
            return []

        # Filter out explicitly ignored critiques (rating=0)
        valid_critiques = [r for r in critiques_list if r.rating != 0.0]
        if not valid_critiques:
            return []

        # Check if any critique has been further audited (has its own critiques)
        audited_critiques = [r for r in valid_critiques if list(r.critiques.all())]

        if audited_critiques:
            # Use deepest level - recursively get critiques from audited critiques
            all_deep_critiques = []
            for critique in audited_critiques:
                all_deep_critiques.extend(self._get_deepest_critiques(critique))
            return all_deep_critiques if all_deep_critiques else valid_critiques
        else:
            # This is the deepest level (direct children)
            return valid_critiques

    def _aggregate_critique_values(
        self,
        critiques: list[Rationale],
        value_getter
    ) -> Optional[float]:
        """
        Aggregate values from multiple critiques.

        Matches legacy Rationale._aggregate_critique_values() exactly:
        - If all unrated (rating=None): GM of all critique values (equal weight)
        - If some/all rated: weighted average by rating
        - Filter out values <= 0

        Args:
            critiques: List of critique rationales
            value_getter: Function to extract value from critique

        Returns:
            Aggregated value or None
        """
        if not critiques:
            return None

        values = []
        weights = []
        has_explicit_ratings = False

        for critique in critiques:
            val = value_getter(critique)
            # Filter out None and <= 0 values (matches legacy line 82)
            if val is None or val <= 0:
                continue

            values.append(val)
            rating = critique.rating
            if rating is not None:
                has_explicit_ratings = True
                weights.append(rating)
            else:
                weights.append(1.0)  # Default weight

        if not values:
            return None

        if not has_explicit_ratings:
            # All unrated → geometric mean (equal weight)
            return gm_with_zeros_and_nones_handled(values)
        else:
            # Some/all rated → weighted average
            total_weight = sum(weights)
            if total_weight == 0:
                return None
            weighted_sum = sum(v * w for v, w in zip(values, weights))
            return weighted_sum / total_weight

    def _get_manual_relevance_with_fallback(self, rationale: Rationale) -> Optional[float]:
        """
        Get manual relevance with FeasibilityEstimation fallback.

        Priority order (matches AssessableEntity.relevance):
        1. RelevanceEstimation (manual)
        2. FeasibilityEstimation (manual fallback)

        Args:
            rationale: Rationale to get relevance from

        Returns:
            Relevance value or None if no evidence
        """
        from dialectical_framework.graph.nodes.estimation import RelevanceEstimation, FeasibilityEstimation

        # Try RelevanceEstimation first
        relevance = self._get_manual_value(rationale, RelevanceEstimation)
        if relevance is not None:
            return relevance

        # Fallback to FeasibilityEstimation
        return self._get_manual_value(rationale, FeasibilityEstimation)

    def _get_manual_value(self, rationale: Rationale, estimation_type: Type[T]) -> Optional[float]:
        """
        Get MANUAL estimation value provided by this rationale (not calculated).

        This reads from rationale.provided_estimations which contains
        estimations that this rationale provides as evidence.

        Args:
            rationale: Rationale to get value from
            estimation_type: Type of estimation (ProbabilityEstimation or RelevanceEstimation)

        Returns:
            GM of manual estimations or None
        """
        # Get estimations PROVIDED by this rationale (not calculated)
        provided = rationale.provided_estimations.all()
        manual_estimations = [
            est for est, _ in provided
            if isinstance(est, estimation_type)
            and not est.__class__.__name__.startswith('Calculated')
        ]

        if not manual_estimations:
            return None

        # If multiple manual estimations, aggregate via GM
        if len(manual_estimations) == 1:
            return manual_estimations[0].value

        values = [est.value for est in manual_estimations]
        return gm_with_zeros_and_nones_handled(values)
