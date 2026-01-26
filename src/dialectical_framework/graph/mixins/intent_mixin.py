"""
Mixin providing intent field for reasoning nodes.

Intent captures the guiding question or purpose for a node's analysis.
Maps to the "What? → So What? → Now What?" framework.
"""

from __future__ import annotations

from typing import Optional


class IntentMixin:
    """
    Mixin providing an intent field for reasoning nodes.

    Intent is a free-text field that captures the guiding question or purpose
    for a node's analysis. It helps document why this node exists and what
    question it's trying to answer.

    Used by: Brainstorm, Ideas, WisdomUnit, Nexus, Cycle, Wheel,
             Transformation, Synthesis, Spiral

    Example:
        brainstorm = Brainstorm(intent="Explore remote work dynamics")
        ideas = Ideas(intent="Extract productivity claims")
        wu = WisdomUnit(intent="Analyze work-life balance tension")
    """

    intent: Optional[str] = None
