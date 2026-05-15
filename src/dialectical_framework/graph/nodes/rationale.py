"""
Rationale node for the dialectical framework.

This module provides the Rationale class which represents explanations
and evidence for assessments in the dialectical system.
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar, Optional, TYPE_CHECKING, Union, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.explains_relationship import (
    ExplainsRelationship,
)
from dialectical_framework.graph.relationships.critiques_relationship import (
    CritiquesRelationship,
)
from dialectical_framework.graph.relationships.provides_relationship import (
    ProvidesRelationship,
)
from dependency_injector.wiring import Provide, inject
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.estimation import Estimation
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity


class Rationale(BaseNode, label="Rationale"):
    """
    Represents an explanation or evidence for an assessment.

    Rationales provide contextual explanations for why a particular
    assessment (score, relevance, probability) was assigned to an
    assessable entity (Component, Perspective, Cycle, Wheel, etc.).

    Semantic Model (new design):
        Rationale is the SOURCE of evidence, not the TARGET of estimations.
        - Rationale EXPLAINS an AssessableEntity (what it's about)
        - Rationale PROVIDES Estimations (the evidence it contributes)
        - Estimations ESTIMATE the target entity (what they measure)

    Graph structure:
        Component <─ESTIMATES─ Estimation(P=0.8) <─PROVIDES─ Rationale ─EXPLAINS→ Component

    This design means:
        - P=0.8 describes the Component, not the Rationale
        - Rationale is the source of evidence, not what's being estimated
        - PROVIDES relationship tracks provenance (which rationale contributed which estimation)

    Note: Rationale extends BaseNode (not AssessableEntity) because rationales
    are sources of evidence, not entities that get scored themselves.

    Example:
        # Create rationale explaining a component
        rationale = Rationale(text="Because it empowers citizens...")
        rationale.set_explanation(component)
        rationale.commit()

        # Create estimation that this rationale provides
        prob_est = CausalityProbabilityEstimation(value=0.8)
        prob_est.set_target(component)      # Estimation targets the component
        prob_est.set_provider(rationale)    # Rationale is the provider of evidence
        prob_est.commit()
    """

    text: str

    # metadata
    rating: Optional[float] = None  # Importance/quality rating (0.0-1.0), used for weighting critiques
    agent: Optional[str] = None  # Agent identifier (<provider>:<model>) that generated this rationale

    def __init__(self, **data: Any) -> None:
        if "agent" not in data or data["agent"] is None:
            try:
                data["agent"] = _get_ai_model()
            except Exception:
                pass
        super().__init__(**data)

    # Declarative relationships
    # What this rationale explains
    explains: ClassVar[RelationshipManager[AssessableEntity]] = RelationshipTo(
        "AssessableEntity",
        model=ExplainsRelationship,
        cardinality=(0, 1)  # Zero or one (rationale explains one entity)
    )

    # Incoming: rationales that critique this one (audit-wins semantics)
    # Usage: parent_rationale.critiques.connect(audit_rationale) creates audit_rationale -[CRITIQUES]-> parent_rationale
    critiques: ClassVar[RelationshipManager[Rationale]] = RelationshipFrom(
        "Rationale",
        model=CritiquesRelationship,
        cardinality=(0, None)  # Zero or more critiques can target this rationale
    )

    # Inverse: the rationale this one critiques (outgoing edge)
    # A rationale can critique at most one other rationale
    _critiques_target: ClassVar[RelationshipManager[Rationale]] = RelationshipTo(
        "Rationale",
        model=CritiquesRelationship,
        cardinality=(0, 1)  # Zero or one target (can critique at most one rationale)
    )


    # Estimations that this rationale provides as evidence
    # The rationale provides P/R values for the target entity
    # This is the new semantic: Rationale PROVIDES Estimation (which ESTIMATES Component)
    provided_estimations: ClassVar[RelationshipManager[Estimation]] = RelationshipTo(
        "Estimation",
        model=ProvidesRelationship,
        cardinality=(0, None)  # Zero or more estimations
    )

    # Hash inputs - set these before save() to include in hash
    # These are used for hash computation; actual relationships are created post-save
    _explanation_target_hash: Optional[str] = None
    _critiques_target_hash: Optional[str] = None
    # Transient refs for auto-connecting after save (not persisted)
    _explanation_ref: Optional[AssessableEntity] = None
    _critiques_target_ref: Optional[Rationale] = None

    def set_explanation_target(self, target: AssessableEntity) -> Rationale:
        """
        Set the explanation target for this rationale (before save).

        This stores the reference for hash computation and auto-connection after save.
        The target must already be committed (have hash).

        Args:
            target: The committed assessable entity this rationale explains

        Returns:
            Self for chaining

        Raises:
            ValueError: If target is not committed
        """
        if not target.is_committed:
            raise ValueError(
                "Explanation target must be committed before setting on rationale. "
                "Call target.commit() first."
            )
        self._explanation_target_hash = target.hash
        self._explanation_ref = target
        return self

    def set_critiques_target(self, target: Rationale) -> Rationale:
        """
        Set the critique target for this rationale (before commit).

        This stores the reference for hash computation and auto-connection after commit.
        The target rationale must already be committed (have hash).

        Args:
            target: The committed rationale this one critiques

        Returns:
            Self for chaining

        Raises:
            ValueError: If target is not committed
        """
        if not target.is_committed:
            raise ValueError(
                "Critique target must be committed before setting on rationale. "
                "Call target.commit() first."
            )
        self._critiques_target_hash = target.hash
        self._critiques_target_ref = target
        return self

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Rationale.

        Parts: text, target hash (explanation or critique target).
        This makes the same rationale text pointing at the same target produce
        the same hash (content-addressable analytical artifact).

        Returns:
            List of strings: [text, target_hash]

        Raises:
            ValueError: If target is not set/committed
        """
        parts = [self.text]

        # Get target hash - prefer stored hash, fall back to relationship
        target_hash = None

        # Check explanation target first (stored hash or relationship)
        if self._explanation_target_hash:
            target_hash = self._explanation_target_hash
        else:
            explanation_result = self.explains.get()
            if explanation_result:
                target_node, _ = explanation_result
                if not target_node.is_committed:
                    raise ValueError(
                        f"Explanation target {target_node.__class__.__name__} must be committed "
                        "before computing Rationale structure hash. Commit the target first."
                    )
                target_hash = target_node.hash

        # Check critiques target (stored hash or relationship)
        if not target_hash:
            if self._critiques_target_hash:
                target_hash = self._critiques_target_hash
            else:
                critiques_result = self._critiques_target.get()
                if critiques_result:
                    target_rationale, _ = critiques_result
                    if not target_rationale.is_committed:
                        raise ValueError(
                            "Critique target Rationale must be committed "
                            "before computing Rationale structure hash. Commit the target first."
                        )
                    target_hash = target_rationale.hash

        if not target_hash:
            raise ValueError(
                "Rationale must have a target set before computing hash. "
                "Use set_explanation() or set_critiques_target() first."
            )

        parts.append(target_hash)
        return parts

    def compute_hash(self) -> str:
        """
        Compute content hash for this Rationale.

        Rationale is content-addressable: same text + same target = same hash.
        Unlike structural nodes, committed_at is NOT included because:
        - Deduplication is desirable (same explanation for same entity = same rationale)
        - Multiple agents providing the same rationale should resolve to one node
        - The target hash already provides context (same text on different targets = different hashes)

        Returns:
            sha256 hex string of text + target_hash
        """
        parts = self._collect_structure_hash_parts()
        combined = "\n".join(parts)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Self:
        """
        Commit this rationale: compute hash, persist, and create relationships.

        If explanation/critiques_target were set via set_explanation()/set_critiques_target(),
        relationships are automatically created after the node is persisted.

        Critique Cycle Prevention:
            A rationale can only critique another rationale that was committed earlier.
            This ensures temporal consistency and prevents cycles in the critique chain:
            - If A critiques B, then A.committed_at > B.committed_at
            - Transitively: A→B→C implies A.committed_at > B.committed_at > C.committed_at
            - Therefore A→B→C→A is impossible (would require A.committed_at > A.committed_at)

        Returns:
            Self for chaining

        Raises:
            ValueError: If critique target was committed after current time (clock skew)
        """
        # Validate critique target temporal consistency BEFORE commit
        # This prevents cycles by ensuring we can only critique older rationales
        if self._critiques_target_ref is not None:
            import time
            current_time = time.time()
            target_committed_at = self._critiques_target_ref.committed_at
            if target_committed_at is not None and target_committed_at >= current_time:
                raise ValueError(
                    f"Cannot critique a rationale from the future. "
                    f"Target committed_at ({target_committed_at}) >= current time ({current_time}). "
                    f"This could indicate clock skew or an attempt to create a critique cycle."
                )

        # Call parent commit (computes hash and persists)
        # For content-addressable nodes like Rationale, BaseNode.commit() checks
        # for existing nodes with the same hash and reuses them (dedup).
        # In that case, relationships already exist and we skip auto-connect.
        super().commit()

        # Auto-connect explanation target if ref was stored AND not already connected
        if self._explanation_ref and self.explains.count() == 0:
            self.explains.connect(self._explanation_ref)
            self._explanation_ref = None  # Clear transient ref
        # Auto-connect critiques target if ref was stored AND not already connected
        if self._critiques_target_ref and self._critiques_target.count() == 0:
            self._critiques_target.connect(self._critiques_target_ref)
            self._critiques_target_ref = None  # Clear transient ref

        return self

    def __repr__(self) -> str:
        """String representation of the rationale."""
        text_preview = self.text[:47] + "..." if len(self.text) > 50 else self.text
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Rationale({hash_str}, text='{text_preview}')"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.text[:80] if len(self.text) > 80 else self.text


@inject
def _get_ai_model(settings: Settings = Provide[DI.settings]) -> str:
    return settings.ai_model