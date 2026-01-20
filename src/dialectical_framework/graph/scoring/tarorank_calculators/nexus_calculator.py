"""
Calculator for scoring Nexus nodes.

Nexus score is derived from its constituent WisdomUnits using geometric mean.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus


class NexusCalculator(BaseCalculator):
    """
    Calculator for scoring Nexus nodes.

    A Nexus aggregates WisdomUnits, so its P and R are derived from
    the geometric mean of its constituent WisdomUnits' P and R values.

    Scoring Logic:
    - P = GM(WU probabilities) - structural coherence of the pool
    - R = GM(WU relevances) - collective quality of the pool

    Veto Semantics:
    - If any WU has P=0 or R=0, GM handles it appropriately
    - Empty Nexus returns None (insufficient data)
    """

    def calculate_probability(self, node: Nexus) -> Optional[float]:
        """
        Calculate probability for a Nexus.

        P = Geometric Mean of all WisdomUnit probabilities.

        Args:
            node: Nexus to calculate P for

        Returns:
            P value (0.0-1.0) or None if no WUs or insufficient data
        """
        wu_probs = []
        for wu, _ in node.wisdom_units.all():
            if wu.probability is not None:
                wu_probs.append(wu.probability)

        if not wu_probs:
            return None

        return gm_with_zeros_and_nones_handled(wu_probs)

    def calculate_relevance(self, node: Nexus) -> Optional[float]:
        """
        Calculate relevance for a Nexus.

        R = Geometric Mean of all WisdomUnit relevances.

        Args:
            node: Nexus to calculate R for

        Returns:
            R value (0.0-1.0) or None if no WUs or insufficient data
        """
        wu_rels = []
        for wu, _ in node.wisdom_units.all():
            if wu.relevance is not None:
                wu_rels.append(wu.relevance)

        if not wu_rels:
            return None

        return gm_with_zeros_and_nones_handled(wu_rels)

    def score_children(self, node: Nexus, force: bool = False) -> None:
        """
        Recursively score all WisdomUnits in this Nexus.

        Args:
            node: Nexus whose WisdomUnits should be scored
            force: If True, force rescore even if WUs appear valid
        """
        for wu, _ in node.wisdom_units.all():
            self.scorer.calculate_score(wu, force=force)

    def clear_children(self, node: Nexus) -> None:
        """
        Recursively clear scores from all WisdomUnits in this Nexus.

        Args:
            node: Nexus whose WisdomUnits should be cleared
        """
        for wu, _ in node.wisdom_units.all():
            self.scorer.clear_scores(wu)
