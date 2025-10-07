from __future__ import annotations

from typing import Optional, List

from pydantic import Field

from dialectical_framework.protocols.ratable import Ratable
from dialectical_framework.synthesist.domain.wheel import Wheel
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled


class Rationale(Ratable):
    headline: Optional[str] = Field(default=None)
    haiku: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None)
    text: Optional[str] = Field(default=None)
    theses: list[str] = Field(default_factory=list, description="Theses of the rationale text.")
    wheels: list[Wheel] = Field(default_factory=list, description="Wheels that are digging deeper into the rationale.")

    def _hard_veto_on_own_zero(self) -> bool:
        """
        Why not veto Rationale by default

        Rationale is commentary/evidence, not structure. It can be refuted by critiques or outweighed by spawned wheels. One mistaken rationale with CF=0 shouldn’t nuke the parent.

        You already have a safe “off” switch: set rationale.rating = 0 → its contribution is ignored without collapsing CF to 0.

        True veto belongs at structural leaves (Components, Transitions), where “this is contextually impossible” should indeed zero things.
        """
        return False

    def _apply_own_rating_in_cf(self) -> bool:
        return False  # parent applies rationale.rating

    def _get_deepest_critiques(self) -> list['Rationale']:
        """
        Get all critiques at the deepest recursion level.

        Auditor-wins semantics:
        - If critiques have their own critiques, those are deeper (recursive audits)
        - Returns all critiques at the deepest level
        - Filters out critiques with rating=0 (explicitly ignored)
        """
        if not self.rationales:
            return []

        # Filter out explicitly ignored critiques (rating=0)
        valid_critiques = [r for r in self.rationales if r.rating != 0.0]
        if not valid_critiques:
            return []

        # Check if any critique has been further audited (has its own critiques)
        audited_critiques = [r for r in valid_critiques if r.rationales]

        if audited_critiques:
            # Use deepest level - recursively get critiques from audited critiques
            all_deep_critiques = []
            for critique in audited_critiques:
                all_deep_critiques.extend(critique._get_deepest_critiques())
            return all_deep_critiques if all_deep_critiques else valid_critiques
        else:
            # This is the deepest level (direct children)
            return valid_critiques

    def _aggregate_critique_values(self, critiques: list['Rationale'], value_getter) -> float | None:
        """
        Aggregate values from multiple critiques.

        Rules:
        - If all unrated (rating=None): GM of all critique values (equal weight)
        - If some/all rated: weighted average by rating
        """
        if not critiques:
            return None

        values = []
        weights = []
        has_explicit_ratings = False

        for critique in critiques:
            val = value_getter(critique)
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
            from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled
            return gm_with_zeros_and_nones_handled(values)
        else:
            # Some/all rated → weighted average
            total_weight = sum(weights)
            if total_weight == 0:
                return None
            weighted_sum = sum(v * w for v, w in zip(values, weights))
            return weighted_sum / total_weight

    def calculate_probability(self) -> float | None:
        # AUDIT SEMANTICS: If this rationale has critiques, they override at deepest level
        deepest_critiques = self._get_deepest_critiques()
        if deepest_critiques:
            # Aggregate deepest critique probabilities (weighted or GM)
            critique_p = self._aggregate_critique_values(
                deepest_critiques,
                lambda c: c.calculate_probability()
            )
            if critique_p is not None:
                self.calculated_probability = critique_p
                return self.calculated_probability

        # No critiques or critiques have no value → use own evidence
        parts: List[float] = []

        if self.probability is not None:
            if self._hard_veto_on_own_zero() and self.probability == 0:
                self.calculated_probability = self.probability
                return self.calculated_probability
            if self.probability > 0.0:
                parts.append(self.probability)

        # Wheels spawned by this rationale
        for w in (self.wheels or []):
            p = w.calculate_probability()
            if p is not None:
                parts.append(p)

        # Don't fall back to 1.0 to not improve scores for free
        self.calculated_probability = gm_with_zeros_and_nones_handled(parts) if parts else None
        return self.calculated_probability

    def calculate_relevance(self) -> float | None:
        """
        Override parent to implement audit-wins semantics for relevance.
        If this rationale has critiques, they override at deepest level.
        """
        # AUDIT SEMANTICS: If this rationale has critiques, they override at deepest level
        deepest_critiques = self._get_deepest_critiques()
        if deepest_critiques:
            # Aggregate deepest critique relevances (weighted or GM)
            critique_r = self._aggregate_critique_values(
                deepest_critiques,
                lambda c: c.calculate_relevance()
            )
            if critique_r is not None:
                self.calculated_relevance = critique_r
                return self.calculated_relevance

        # No critiques or critiques have no value → use parent's normal aggregation logic
        return super().calculate_relevance()

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        parts = []
        # Wheels spawned by this rationale — include as-is
        for w in (self.wheels or []):
            cf = w.calculate_relevance()
            if cf is not None:
                if self._hard_veto_on_own_zero() and cf == 0.0:
                    parts.append(cf)
                if cf > 0:
                    parts.append(cf)
        return parts