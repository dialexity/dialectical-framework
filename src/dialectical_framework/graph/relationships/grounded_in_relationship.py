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
            - "accepted_cost": the CHOSEN side's overdevelopment aspect — T-
              when they chose the thesis, A- when they chose the antithesis —
              that the person confronted and accepted when deciding
            - "adopted_pathway": the Transformation adopted as the ongoing
              management recipe for the tension being decided on

    Why the cost is a MINUS, and specifically the chosen side's:
    reading the tetrad plainly — T is what is said, T+ its implied goal, T-
    its risk; A is the opponent's say, A+ the obligation that falls on the
    T-sayer, A- the risk that follows. A cost is therefore a minus. It is the
    CHOSEN side's minus because the price of a decision is what pushing your
    own choice one-sidedly does to you: choose the thesis and you pay T-.

    This was measured, not reasoned into. The role previously asked for the
    unchosen side's A+, and the bench duly recorded obligations dressed as
    costs — "Diversify client relationships before any separation", "Bind CEO
    with retention-linked exit clause" — in 4 of 6 runs whose recorded cost
    was an A+. Those are remedies: things to DO, not prices paid. The re-audit
    then had nothing to reassure from, and the judge marked the commitment
    turn down against a plain-prose baseline on `earned_confidence` in all six
    (`tests/e2e`).

    This definition is ENFORCED at the write, not only documented:
    `RecordDecision._accepted_cost_misplacement` refuses an `accepted_cost` on
    anything that is not a minus aspect — the role was stated at five sites and
    checked at none, and a bench round duly recorded every cost on the
    Perspective (the tension rather than its price). Whether it is the CHOSEN
    side's minus stays with `DecisionCoherenceCheck`: that half needs the stance
    read against the poles, and a false refusal costs a confirmed decision.
    """

    role: Optional[str] = None
