"""
Root input node - the original starting point for dialectical analysis.
"""

from __future__ import annotations

from dialectical_framework.graph.growth.input import Input


class Root(Input):
    """
    The original starting point for dialectical analysis.

    Root is where analysis begins - external content is provided via content_uri,
    statements are extracted via HAS_STATEMENT, and initial wheels are built.

    Example:
        root = Root(content_uri="https://example.com/article")
        root.save()

        # Extract statements from content
        root.statements.connect(component1)
        root.statements.connect(component2)

        # Build wheel from statements
        wheel = Wheel(input_uri=root.uid)
        wheel.save()
    """

    pass  # Inherits content_uri, statements from Input
