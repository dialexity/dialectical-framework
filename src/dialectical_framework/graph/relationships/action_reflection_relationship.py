"""Relationship model for Transformation pointing to its wheel edge."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class ActionReflectionRelationship(AnalyticalStructure, type="ACTION_REFLECTION"):
    """
    Links a Transformation to its wheel edge (Transition).

    Direction: Transformation --ACTION_REFLECTION--> Transition

    A wheel's edges define the causality sequence. Each edge can have multiple
    Transformation alternatives at different insight/proactiveness levels.
    The Transformation IS an action-reflection analysis OF that edge.

    Part of the analytical layer - Transformations are derived artifacts that don't
    affect the Transition's structural hash.
    """

    pass
