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


class Estimation(BaseNode, label="Estimation"):
    """
    Base class for estimations associated with assessable entities.

    Estimations capture quantitative measurements like probability, relevance,
    feasibility, and cost. They are stored as separate nodes connected to
    assessable entities via ESTIMATES relationships.

    The scoring architecture uses two primary dimensions:
    - Probability (P): Likelihood of truth/occurrence
    - Relevance (R): Importance/significance

    Formula: Score = P × R^α

    Additional estimations like feasibility and cost can be used for
    specialized analysis and filtering.

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
        est = ProbabilityEstimation(value=0.8)
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


class ProbabilityEstimation(Estimation, label="Probability"):
    """
    Probability estimation (P dimension in scoring formula).

    Represents the likelihood that a component/assessment is true or
    will occur. Values typically range from 0.0 (impossible) to 1.0 (certain).

    This is a MANUAL estimation - set by users or agents.
    """

    pass


class RelevanceEstimation(Estimation, label="Relevance"):
    """
    Relevance estimation (R dimension in scoring formula).

    Represents the importance or significance of a component/assessment.
    Values typically range from 0.0 (irrelevant) to 1.0 (highly relevant).

    This is a MANUAL estimation - set by users or agents.
    """

    pass


class CalculatedEstimation(Estimation, label="CalculatedEstimation"):
    """
    Base class for TaroRank-computed estimations.

    Calculated estimations are algorithm outputs, not user/agent inputs.
    They have validity tracking via invalidated_at timestamp.

    Validity logic:
    - Valid if invalidated_at is None (never invalidated)
    - Valid if committed_at > invalidated_at (recomputed after invalidation)
    - Invalid otherwise (upstream data changed, needs recomputation)

    Subclasses:
    - CalculatedProbabilityEstimation: Aggregated P from TaroRank
    - CalculatedRelevanceEstimation: Aggregated R from TaroRank
    - CalculatedScoreEstimation: Final Score = P × R^α from TaroRank
    """

    # metadata
    # Unix timestamp (float) for consistency with committed_at
    invalidated_at: Optional[float] = None

    def is_valid(self) -> bool:
        """
        Check if this calculated estimation is still valid.

        Returns:
            True if valid (not invalidated or recomputed after invalidation)
        """
        if self.invalidated_at is None:
            return True
        if self.committed_at is None:
            return False
        return self.committed_at > self.invalidated_at


class CalculatedProbabilityEstimation(CalculatedEstimation, label="CalculatedProbability"):
    """
    Calculated probability from TaroRank aggregation.

    This is TaroRank's output, representing the aggregated probability
    from all manual estimations and rationales.

    Typically there is at most one calculated estimation per node.
    """

    pass


class CalculatedRelevanceEstimation(CalculatedEstimation, label="CalculatedRelevance"):
    """
    Calculated relevance from TaroRank aggregation.

    This is TaroRank's output, representing the aggregated relevance
    from all manual estimations and rationales.

    Typically there is at most one calculated estimation per node.
    """

    pass


class CalculatedScoreEstimation(CalculatedEstimation, label="CalculatedScore"):
    """
    Calculated score from TaroRank aggregation.

    This is TaroRank's final output: Score = P × R^α

    The score estimation replaces the score/score_computed_at/score_invalidated_at
    fields that were previously on AssessableEntity. This keeps all scoring
    artifacts as separate Estimation nodes for cleaner separation.

    Typically there is at most one calculated score estimation per node.
    """

    pass


class FeasibilityEstimation(Estimation, label="Feasibility"):
    """
    Feasibility estimation for practical constraints.

    Represents how achievable or practical an outcome is.
    Values typically range from 0.0 (infeasible) to 1.0 (easily achievable).

    **TaroRank Semantics**:
    FeasibilityEstimation is treated semantically the same as RelevanceEstimation.

    Priority order for relevance calculation:
    1. CalculatedRelevanceEstimation (TaroRank output)
    2. RelevanceEstimation (manual)
    3. FeasibilityEstimation (manual fallback)

    When both RelevanceEstimation and FeasibilityEstimation exist on the same node,
    RelevanceEstimation takes priority for relevance calculation, and FeasibilityEstimation
    becomes additional metadata.

    Example:
        # FeasibilityEstimation used as relevance fallback on a component
        est = FeasibilityEstimation(value=0.7)
        est.set_target(component)
        est.commit()
        rel = component.relevance  # Returns 0.7

        # RelevanceEstimation takes priority
        est2 = RelevanceEstimation(value=0.9)
        est2.set_target(component)
        est2.commit()
        rel = component.relevance  # Returns 0.9 (FeasibilityEstimation ignored)
    """

    pass

class ModeEstimation(Estimation, label="Mode"):
    """
    Mode estimation for T-A opposition.

    Stored on the antithesis DialecticalComponent since it
    characterizes the opposition direction (how A opposes T).
    """

    pass


class ArousalEstimation(Estimation, label="Arousal"):
    """
    Arousal estimation for T-A opposition.

    Stored on the antithesis DialecticalComponent since it
    characterizes the opposition intensity.
    """

    pass


class ConceptualCoherenceEstimation(Estimation, label="ConceptualCoherence"):
    """
    Conceptual coherence estimation for WisdomUnit validation.

    Tests the logical coherence of a tetrad structure using control statements:
    - t_plus_without_a_plus_yields_t_minus: "{T+} without {A+} yields {T-}"
    - a_plus_without_t_plus_yields_a_minus: "{A+} without {T+} yields {A-}"

    The main `value` field stores the average of both scores.
    Individual scores are stored in the named fields.

    Validation threshold: Both scores must be >= 0.7 for coherence.

    Stored on WisdomUnit as it validates the entire tetrad structure.
    """

    t_plus_without_a_plus_yields_t_minus: float
    a_plus_without_t_plus_yields_a_minus: float

    @property
    def is_coherent(self) -> bool:
        """True if both control statements pass the 0.7 threshold."""
        return (
            self.t_plus_without_a_plus_yields_t_minus >= 0.7
            and self.a_plus_without_t_plus_yields_a_minus >= 0.7
        )


