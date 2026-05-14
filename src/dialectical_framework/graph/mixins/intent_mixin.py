"""
Mixin providing intent field for reasoning nodes.

Intent captures the guiding question or purpose for a node's analysis.
Maps to the "What? → So What? → Now What?" framework.
"""

from __future__ import annotations

from typing import Optional

from dialectical_framework.graph.mixins.persistable_mixin import PersistableMixin


class IntentMixin(PersistableMixin):
    """
    Mixin providing an intent field for reasoning nodes.

    Intent is a free-text field that captures the guiding question or purpose
    for a node's analysis. It helps document why this node exists and what
    question it's trying to answer.

    Used by: Case, Ideas, Perspective, Cycle, Wheel,
             Transformation

    Example:
        case = Case(intent="Explore remote work dynamics")
        ideas = Ideas(intent="Extract productivity claims")
        pp = Perspective(intent="Analyze work-life balance tension")
    """

    intent: Optional[str] = None
