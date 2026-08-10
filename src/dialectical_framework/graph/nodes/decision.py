"""
Decision node for the dialectical framework.

A Decision records a user's confirmed stance on a question — the durable
artifact of the propose-and-confirm recording ceremony run by the Advisor.
It is a speech act, not an extraction: it exists only because the person
explicitly confirmed it.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, ClassVar

from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import (
    RelationshipManager,
    RelationshipTo,
)
from dialectical_framework.graph.relationships.grounded_in_relationship import (
    GroundedInRelationship,
)


class Decision(IntentMixin, AssessableEntity, label="Decision"):
    """
    A recorded decision: the question decided (intent), the stance taken,
    and typed links to the graph nodes that grounded it.

    Thin by design — the record points at the reasoning rather than
    restating it:
    - The question rides `intent` (IntentMixin); REQUIRED at commit.
    - The distilled why is a Rationale attached via the standard EXPLAINS
      machinery (inherited `rationales`), which also buys ratings/
      estimations/critiques on decisions. Its `agent` names the confirming
      principal: "human" iff a person confirmed the ceremony; a delegated
      driver records "agent:<name>" (host-attested via
      Advisor(principal=...), never LLM-supplied).
    - Grounds are GROUNDED_IN edges to committed nodes (perspectives,
      statements, wheels, transformations) with an optional role
      ("accepted_cost" — the chosen side's minus aspect, i.e. the risk
      accepted; "adopted_pathway"; or None for a plain ground).

    Immutable + standard discard: commit() freezes intent/stance; changing
    a decision = record a new one, then soft-discard the old (reason
    references the new decision, e.g. "superseded by [[hash]]").

    Hash: two constraints, both load-bearing —
    - The nonce means identical decision text recorded twice is TWO records:
      recording again is a new speech act, never a dedup.
    - committed_at is EXCLUDED from the hash (do not add it back): it is a
      pure timestamp here — the decision's decided-at — and excluding it
      keeps the post-commit save() integrity re-check stable while the
      mutable metadata fields change.
    There is no separate decided_at field.

    Anchored at Case level via sid; no structural container.

    Lifecycle (atomic commit — no member-adding phase):
        decision = Decision(intent="Which job offer to take?",
                            stance="Accept the startup offer")
        decision.commit()
        decision.grounds.connect(pp, relationship=GroundedInRelationship(role=None))
    """

    # The stance taken, in the user's confirmed words
    stance: str

    # Nonce for hash uniqueness — same question + stance recorded twice is
    # two decisions (a new speech act), never a dedup. See compute_hash().
    nonce: str

    # metadata (mutable post-commit, NOT part of hash)
    # Standard soft-discard (same field/semantics as Statement/Perspective);
    # "superseded by [[hash]]" is just a discard reason.
    discarded: str | None = None
    # Coherence verdict (Perspective.validation pattern):
    # None = not checked; "passed" = no contradiction found;
    # "failed: <reasons>" = flagged, record stands (soft gate).
    validation: str | None = None

    def __init__(self, **data: Any) -> None:
        if "nonce" not in data:
            data["nonce"] = str(uuid.uuid4())
        super().__init__(**data)

    def clone(self, destination_sid: str | None = None) -> Decision:
        """Clone with a FRESH nonce. BaseNode.clone() copies all non-identity
        fields — a copied nonce would make clone().commit() dedup back into
        the original node (committed_at is not in this hash), silently
        aliasing instead of copying."""
        cloned = super().clone(destination_sid)
        cloned.nonce = str(uuid.uuid4())
        return cloned

    # What grounded this decision (analytical edges to committed nodes)
    grounds: ClassVar[RelationshipManager[AssessableEntity]] = RelationshipTo(
        "AssessableEntity",
        model=GroundedInRelationship,
        cardinality=(0, None),
    )

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Parts: stance + nonce. The question (intent) is appended by this
        class's compute_hash() override below (which replicates BaseNode's
        IntentMixin handling while dropping committed_at).
        """
        return [self.stance, self.nonce]

    def compute_hash(self) -> str:
        """
        Compute content hash for this Decision.

        committed_at is NOT included: the nonce already guarantees
        uniqueness per recording act, and committed_at itself serves as
        the decision timestamp rather than a hash input.

        Returns:
            sha256 hex string of stance + nonce + intent
        """
        parts = self._collect_structure_hash_parts()
        if isinstance(self, IntentMixin) and self.intent:
            parts.append(self.intent)
        combined = "\n".join(parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def commit(self, *args: Any, **kwargs: Any) -> Decision:
        """
        Commit this decision. The question (intent) is required — a
        decision without its question is unreadable in every consumer
        (ledger, re-audit, inspect).
        """
        if not self.intent:
            raise ValueError(
                "Decision requires intent (the question being decided) "
                "before commit. Set intent first."
            )
        super().commit(*args, **kwargs)
        return self

    def __repr__(self) -> str:
        """Debug representation (may truncate)."""
        stance_preview = self.stance[:47] + "..." if len(self.stance) > 50 else self.stance
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Decision({hash_str}, stance='{stance_preview}')"

    def __str__(self) -> str:
        """Human-readable representation. LLM-visible — never truncate."""
        return f"{self.intent} → {self.stance}"
