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

        Args:
            rationale: Rationale to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        auditor = RationaleAuditor(self.scorer)
        p = auditor.get_probability(rationale)

        # Soft exclusion: rationales with P=0 return None
        if p == 0:
            return None

        return p

    def calculate_relevance(self, rationale: Rationale) -> Optional[float]:
        """
        Calculate R for a Rationale.

        Uses audit-wins semantics: deepest critiques override parent values.

        Args:
            rationale: Rationale to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        auditor = RationaleAuditor(self.scorer)
        r = auditor.get_relevance(rationale)

        # Soft exclusion: rationales with R=0 return None
        if r == 0:
            return None

        return r
