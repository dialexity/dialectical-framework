"""Relationship model linking a Decision to the graph nodes that ground it."""
from __future__ import annotations

from typing import Optional

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class GroundedInRelationship(AnalyticalStructure, type="GROUNDED_IN"):
    """
    Links a Decision to a node that grounded it.

    Direction: decision -[GROUNDED_IN]-> target (Perspective, Statement,
    Wheel, Synthesis, Transformation, ... — any AssessableEntity).

    Analytical layer — connects to already-committed nodes and does not
    affect hashes. Targets must be committed (validated by the creating
    concern), so a grounding edge can never dangle; a target later being
    soft-discarded is a visible fact for the re-audit, not a broken link.

    Properties:
        role: Optional semantic role of this ground. Open vocabulary — a
            role exists iff a consumer (renderer, re-audit prompt, query)
            branches on it; plain grounds carry None. Seed values:
            - "accepted_cost": the unchosen side's constructive aspect (A+)
              that the person confronted and accepted when deciding
            - "adopted_pathway": the Transformation adopted as the ongoing
              management recipe for the tension being decided on
    """

    role: Optional[str] = None
