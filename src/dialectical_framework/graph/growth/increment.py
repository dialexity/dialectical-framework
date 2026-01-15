"""
Increment input node - adds WisdomUnits to extend a wheel.
"""

from __future__ import annotations

from dialectical_framework.graph.growth.input import Input


class Increment(Input):
    """
    Adds WisdomUnits to extend a wheel.

    When a Wheel branches to an Increment, new statements are extracted
    (via HAS_STATEMENT) and combined with existing components to form
    additional WisdomUnits. The resulting wheel has more WUs than the source.

    Example:
        # Wheel 1 branches to add more content
        increment = Increment(content_uri="https://example.com/supplement")
        increment.save()
        wheel1.branches.connect(increment)

        # Extract new statements
        increment.statements.connect(new_component1)
        increment.statements.connect(new_component2)

        # Build expanded wheel
        wheel2 = Wheel(input_uri=increment.uid)
        wheel2.save()
        # wheel2 has wheel1's WUs + new WUs from increment
    """

    pass  # Inherits content_uri, statements from Input
