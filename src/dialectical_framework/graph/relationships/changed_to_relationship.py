"""Relationship model for Perspective lineage (evolution, not replacement)."""
from __future__ import annotations

from typing import Optional

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class ChangedToRelationship(AnalyticalStructure, type="CHANGED_TO"):
    """
    Links an old Perspective to its evolved successor.

    Direction: old_pp -[CHANGED_TO]-> new_pp

    Analytical layer — does not affect hashes. Captures lineage so that:
    - If old PP is not rejected, lineage is meaningful (evolution chain)
    - If old PP is rejected, the new PP lives as a first-class citizen

    Properties:
        changed_positions: Which positions were modified (e.g. ["T+", "A-"])
    """

    changed_positions: Optional[list] = None
