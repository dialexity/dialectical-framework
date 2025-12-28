"""
Calculator for Rationale nodes.

Rationales are special leaf nodes with audit-wins semantics.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.rationale import Rationale


class RationaleCalculator(BaseCalculator):
    """
    Calculator for Rationale nodes.

    Rationales are special leaf nodes with audit-wins semantics.

    P calculation:
    - Delegates to RationaleAuditor for audit-wins
    - Soft exclusion: P=0 → return None (not 0)

    R calculation:
    - Delegates to RationaleAuditor for audit-wins
    - Soft exclusion: R=0 → return None (not 0)

    Note: This calculator is primarily used for rationale self-scoring.
    When rationales are used as evidence for other nodes, the RationaleAuditor
    is used directly by those node's calculators.
    """

    def calculate_probability(self, rationale: Rationale) -> Optional[float]:
        """
        Calculate P for a Rationale.

        Uses audit-wins semantics: deepest critiques override parent values.

        Matches legacy: No hard veto on P=0 (_hard_veto_on_own_zero = False).
        Rationales with P=0 are handled via filtering in parent aggregation.

        Args:
            rationale: Rationale to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        auditor = RationaleAuditor(self.scorer)
        return auditor.get_probability(rationale)

    def calculate_relevance(self, rationale: Rationale) -> Optional[float]:
        """
        Calculate R for a Rationale.

        Uses audit-wins semantics: deepest critiques override parent values.

        Matches legacy: No hard veto on R=0 (_hard_veto_on_own_zero = False).
        Rationales with R=0 are handled via filtering in parent aggregation.

        Args:
            rationale: Rationale to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        auditor = RationaleAuditor(self.scorer)
        return auditor.get_relevance(rationale)
