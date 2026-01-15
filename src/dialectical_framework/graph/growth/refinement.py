"""
Refinement input node - changes components within WisdomUnits.
"""

from __future__ import annotations

from dialectical_framework.graph.growth.input import Input


class Refinement(Input):
    """
    Changes components within WisdomUnits.

    When a Wheel branches to a Refinement, new/replacement statements are
    extracted (via HAS_STATEMENT) and used to swap components in existing
    WisdomUnits. The structure stays the same but component content changes.

    Example:
        # Wheel 1 branches to refine a component
        refinement = Refinement()
        refinement.save()
        wheel1.branches.connect(refinement)

        # Extract replacement statement
        refinement.statements.connect(better_component)

        # Build refined wheel
        wheel2 = Wheel(input_uri=refinement.uid)
        wheel2.save()
        # wheel2 has same structure but with swapped component
    """

    pass  # Inherits content_uri, statements from Input
