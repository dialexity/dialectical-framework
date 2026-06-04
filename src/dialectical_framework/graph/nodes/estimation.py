"""
Estimation nodes for the dialectical framework.

This module provides the Estimation class and its subclasses which represent
quantitative measurements associated with assessable entities.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar, Optional, TYPE_CHECKING, Union, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.estimates_relationship import (
    EstimatesRelationship,
)
from dialectical_framework.graph.relationships.provides_relationship import (
    ProvidesRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
    from dialectical_framework.graph.nodes.rationale import Rationale


# --- Validation Thresholds ---

# Minimum score for valid diagonal opposition (T+ vs A-, A+ vs T-)
# >= threshold means mutually exclusive (valid contradiction)
ORTHOGONALITY_THRESHOLD = 0.7

# Minimum score for valid constructive coherence (control statements)
# >= threshold means logically coherent tetrad structure
CONCEPTUAL_COHERENCE_THRESHOLD = 0.7


class Estimation(BaseNode, label="Estimation"):
    """
    Base class for estimations associated with assessable entities.

    Estimations capture quantitative measurements like probability, relevance,
    feasibility, and cost. They are stored as separate nodes connected to
    assessable entities via ESTIMATES relationships.

    Estimation types serve different purposes:
    - CausalityProbabilityEstimation: Causality ordering likelihood (on Cycles/Wheels and Transitions)
    - FeasibilityEstimation: Practical achievability (on Transitions in Transformations)
    - ModeEstimation / ArousalEstimation: T-A opposition characterization
    - ConceptualCoherenceEstimation / DiagonalContradictionEstimation: Tetrad validation

    Estimation is an analytical artifact - it points TO its target entity.
    Hash is based on: type + value + target hash. This means:
    - Same estimation on different entities produces different hashes
    - Use set_target() before save() to specify the target entity

    Provenance (optional):
    Estimations can optionally track their source Rationale via set_source().
    This creates a PROVIDES relationship: Rationale -[PROVIDES]-> Estimation.
    The source is NOT included in the hash - it's provenance metadata only.
    Same (type, value, target) = same hash regardless of source.

    Graph structure:
        Component <─ESTIMATES─ Estimation(P=0.8) <─PROVIDES─ Rationale ─EXPLAINS→ Component

    Lifecycle:
        entity.commit()  # Target committed first
        rationale.commit()  # Optional: provider rationale committed
        est = CausalityProbabilityEstimation(value=0.8)
        est.set_target(entity)  # Required: what this estimation measures
        est.set_provider(rationale)  # Optional: provenance
        est.commit()  # Hash = type|value|target_hash, auto-connects both
    """

    value: float

    # Hash input - set this before save() to include in hash
    _target_hash: Optional[str] = None
    # Transient ref for auto-connecting after save (not persisted)
    _target_ref: Optional[AssessableEntity] = None

    # Declarative relationships
    # What this estimation estimates (points TO the target)
    target: ClassVar[RelationshipManager[AssessableEntity]] = RelationshipTo(
        "AssessableEntity",
        model=EstimatesRelationship,
        cardinality=(1, 1)  # Exactly one target (estimation estimates one entity)
    )

    # Incoming: Rationale that provides this estimation (optional provenance)
    # Usage: rationale.provided_estimations.connect(estimation) creates rationale -[PROVIDES]-> estimation
    provider: ClassVar[RelationshipManager[Rationale]] = RelationshipFrom(
        "Rationale",
        model=ProvidesRelationship,
        cardinality=(0, 1)  # Zero or one provider (optional provenance)
    )

    # Provider hash - NOT included in content hash (provenance metadata only)
    _provider_hash: Optional[str] = None
    # Transient ref for auto-connecting after commit (not persisted)
    _provider_ref: Optional[Rationale] = None

    def set_provider(self, rationale: Rationale) -> Estimation:
        """
        Set the Rationale that provides this estimation (optional, before commit).

        This is optional provenance metadata - it records which rationale
        contributed this estimation, but doesn't affect the estimation's hash.
        The same (type, value, target) estimation is the same regardless of provider.

        The provider rationale must already be committed (have hash).

        Args:
            rationale: The committed rationale providing this estimation

        Returns:
            Self for chaining

        Raises:
            ValueError: If provider rationale is not committed
        """
        if not rationale.is_committed:
            raise ValueError(
                "Provider rationale must be committed before setting on estimation. "
                "Call rationale.commit() first."
            )
        self._provider_hash = rationale.hash
        self._provider_ref = rationale
        return self

    def set_target(self, entity: AssessableEntity) -> Estimation:
        """
        Set the target entity for this estimation (before save).

        This stores the reference for hash computation and auto-connection after save.
        The target must already be committed (have hash).

        Args:
            entity: The committed assessable entity this estimation is for

        Returns:
            Self for chaining

        Raises:
            ValueError: If target is not committed
        """
        if not entity.is_committed:
            raise ValueError(
                "Target entity must be committed before setting on estimation. "
                "Call entity.commit() first."
            )
        self._target_hash = entity.hash
        self._target_ref = entity
        return self

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Estimation.

        Parts: type name, value, target hash.
        This makes the same estimation (type, value) on the same target produce
        the same hash (content-addressable analytical artifact).

        Returns:
            List of strings: [type_name, value, target_hash]

        Raises:
            ValueError: If target is not set/committed
        """
        # Get target hash - prefer stored hash, fall back to relationship
        target_hash = self._target_hash
        if not target_hash:
            target_result = self.target.get()
            if target_result:
                target_node, _ = target_result
                if not target_node.is_committed:
                    raise ValueError(
                        "Target entity must be committed before computing Estimation hash. "
                        "Commit the target first."
                    )
                target_hash = target_node.hash

        if not target_hash:
            raise ValueError(
                "Estimation must have a target set before computing hash. "
                "Use set_target() first."
            )

        return [self.__class__.__name__, str(self.value), target_hash]

    def compute_hash(self) -> str:
        """
        Compute content hash for this Estimation.

        Estimation is content-addressable: same (type, value, target) = same hash.
        Unlike structural nodes, committed_at is NOT included because:
        - Deduplication is desirable (same estimation on same entity = same identity)
        - No temporal ordering needed (estimations don't critique each other)
        - Multiple agents providing the same estimation should resolve to one node
        - The target hash already provides context (same value on different targets = different hashes)

        Returns:
            sha256 hex string of type_name + value + target_hash
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
        Commit this estimation: compute hash, persist, and create relationships.

        If target was set via set_target(), the ESTIMATES relationship is
        automatically created after the node is persisted.

        If source was set via set_source(), the PROVIDES relationship is
        automatically created (rationale -> estimation).

        Returns:
            Self for chaining
        """
        # Call parent commit (computes hash and persists)
        super().commit()

        # Auto-connect target if ref was stored
        if self._target_ref:
            self.target.connect(self._target_ref)
            self._target_ref = None  # Clear transient ref

        # Auto-connect provider (rationale) if ref was stored
        # The connection is made from rationale -> estimation via provided_estimations
        if self._provider_ref:
            self._provider_ref.provided_estimations.connect(self)
            self._provider_ref = None  # Clear transient ref

        return self

    def __repr__(self) -> str:
        """String representation of the estimation."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"{self.__class__.__name__}({hash_str}, value={self.value})"


class CausalityProbabilityEstimation(Estimation, label="CausalityProbability"):
    """
    Causality probability estimation.

    Represents causality ordering likelihood. Context depends on the target node:
    - On a Cycle/Wheel: raw LLM assessment of how plausible this ordering is
    - On a Transition: normalized per-edge probability (sums to 1.0 across layer)

    Used by:
    - CausalityEstimation: stores raw AI score on Cycles/Wheels
    - CausalityNormalizer: reads raw scores from structures, writes normalized probabilities on Transitions
    """



class FeasibilityEstimation(Estimation, label="Feasibility"):
    """
    Feasibility estimation for practical constraints.

    Represents how achievable or practical an outcome is.
    Values typically range from 0.0 (infeasible) to 1.0 (easily achievable).
    """


class ModeEstimation(Estimation, label="Mode"):
    """
    Mode estimation for T-A opposition.

    Stored on the antithesis Statement since it
    characterizes the opposition direction (how A opposes T).
    """



class ArousalEstimation(Estimation, label="Arousal"):
    """
    Arousal estimation for T-A opposition.

    Stored on the antithesis Statement since it
    characterizes the opposition intensity.
    """



class ConceptualCoherenceEstimation(Estimation, label="ConceptualCoherence"):
    """
    Conceptual coherence estimation for Perspective validation.

    Tests the logical coherence of a tetrad structure using control statements:
    - t_plus_without_a_plus_yields_t_minus: "{T+} without {A+} yields {T-}"
    - a_plus_without_t_plus_yields_a_minus: "{A+} without {T+} yields {A-}"

    The main `value` field stores the average of both scores.
    Individual scores are stored in the named fields.

    Validation threshold: Both individual scores must be >= CONCEPTUAL_COHERENCE_THRESHOLD.

    Stored on Perspective as it validates the entire tetrad structure.
    """

    t_plus_without_a_plus_yields_t_minus: float
    a_plus_without_t_plus_yields_a_minus: float

    @property
    def is_coherent(self) -> bool:
        """True if both control statement scores individually pass the threshold."""
        return (
            self.t_plus_without_a_plus_yields_t_minus >= CONCEPTUAL_COHERENCE_THRESHOLD
            and self.a_plus_without_t_plus_yields_a_minus >= CONCEPTUAL_COHERENCE_THRESHOLD
        )


class DiagonalContradictionEstimation(Estimation, label="DiagonalContradiction"):
    """
    Diagonal contradiction estimation for Perspective validation.

    Tests the contradiction validity of diagonal aspect pairs:
    - t_plus_vs_a_minus: Does T+ contradict A-? (They should be mutually exclusive)
    - a_plus_vs_t_minus: Does A+ contradict T-? (They should be mutually exclusive)

    The main `value` field stores the average of both scores.
    Individual scores are stored in the named fields.

    Validation threshold: Both scores must be >= ORTHOGONALITY_THRESHOLD for valid contradictions.

    These diagonals represent core tensions in the tetrad:
    - T+ (positive thesis aspect) vs A- (negative antithesis aspect)
    - A+ (positive antithesis aspect) vs T- (negative thesis aspect)

    Strong contradiction means the aspects cannot both be true/good simultaneously.
    Weak contradiction suggests the tetrad structure may need refinement.

    Stored on Perspective as it validates the entire tetrad structure.
    """

    t_plus_vs_a_minus: float
    a_plus_vs_t_minus: float

    @property
    def is_valid(self) -> bool:
        """True if both diagonal pairs show valid orthogonal opposition."""
        return (
            self.t_plus_vs_a_minus >= ORTHOGONALITY_THRESHOLD
            and self.a_plus_vs_t_minus >= ORTHOGONALITY_THRESHOLD
        )


