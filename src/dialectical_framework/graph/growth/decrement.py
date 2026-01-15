"""
Decrement input node - removes WisdomUnits to reduce a wheel.
"""

from __future__ import annotations

from dialectical_framework.graph.growth.input import Input


class Decrement(Input):
    """
    Removes WisdomUnits to reduce a wheel.

    When a Wheel branches to a Decrement, a subset of existing WisdomUnits
    is selected for the new wheel. The resulting wheel has fewer WUs than
    the source. HAS_STATEMENT may be empty (just selection) or contain
    statements explaining the reduction rationale.

    Example:
        # Wheel 1 branches to focus on subset
        decrement = Decrement()
        decrement.save()
        wheel1.branches.connect(decrement)

        # Build reduced wheel (application selects which WUs to keep)
        wheel2 = Wheel(input_uri=decrement.uid)
        wheel2.save()
        # wheel2 has subset of wheel1's WUs
    """

    pass  # Inherits content_uri, statements from Input
