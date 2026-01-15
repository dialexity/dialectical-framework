"""
Sprout input node - branches from Rationale or Transition.
"""

from __future__ import annotations

from dialectical_framework.graph.growth.input import Input


class Sprout(Input):
    """
    A branch from Rationale or Transition that spawns new statements.

    When a Rationale or Transition branches to a Sprout, new statements
    are extracted (via HAS_STATEMENT) that extend the dialectical analysis.
    This allows reasoning chains to grow organically from existing arguments.

    Example:
        # Rationale spawns new insight
        sprout = Sprout()
        sprout.save()
        rationale.branches.connect(sprout)

        # Extract derived statements
        sprout.statements.connect(derived_component1)
        sprout.statements.connect(derived_component2)

        # These components can form new WUs in evolved wheels
    """

    pass  # Inherits content_uri, statements from Input
