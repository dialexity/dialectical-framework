"""
Reconsideration input node - rearranges WU configuration with different causality.
"""

from __future__ import annotations

from dialectical_framework.graph.growth.input import Input


class Reconsideration(Input):
    """
    Rearranges WU configuration with different causality logic.

    When a Cycle branches to a Reconsideration, the same WisdomUnits are
    arranged in a different causal order. This creates new wheels with
    different ta_cycles representing alternative interpretations.

    HAS_STATEMENT may be empty (pure rearrangement) or contain statements
    explaining the reconsideration rationale.

    Example:
        # T-cycle branches to explore alternative arrangement
        reconsideration = Reconsideration()
        reconsideration.save()
        t_cycle.branches.connect(reconsideration)

        # Build wheel with different causality
        wheel2 = Wheel(input_uri=reconsideration.uid)
        wheel2.save()
        # wheel2 has same WUs but different ta_cycle arrangement
    """

    pass  # Inherits content_uri, statements from Input
