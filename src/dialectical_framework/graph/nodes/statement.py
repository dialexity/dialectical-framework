"""
Statement node with declarative relationships.

This version uses the RelationshipManager layer for clean, neomodel-like syntax.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar, Optional, TYPE_CHECKING, Union, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipTo,
    RelationshipBoth,
    RelationshipManager,
)
from dialectical_framework.graph.relationships.opposite_of_relationship import (
    OppositeOfRelationship,
)
from dialectical_framework.graph.relationships.contradiction_of_relationship import (
    ContradictionOfRelationship,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
)
from dialectical_framework.graph.relationships.is_source_of_relationship import (
    IsSourceOfRelationship,
)
from dialectical_framework.graph.relationships.is_target_of_relationship import (
    IsTargetOfRelationship,
)
from dialectical_framework.graph.relationships.has_statement_relationship import (
    HasStatementRelationship,
)
from dialectical_framework.graph.relationships.positive_side_of_relationship import (
    PositiveSideOfRelationship,
)
from dialectical_framework.graph.relationships.negative_side_of_relationship import (
    NegativeSideOfRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.ideas import Ideas


class Statement(AssessableEntity, label="Statement"):
    """
    Represents an atomic dialectical statement or concept.

    Statements are the building blocks of the dialectical framework.
    They can play different roles in different contexts:

    Core Perspective positions (6):
    - T (neutral thesis), T+ (positive thesis), T- (negative thesis)
    - A (neutral antithesis), A+ (positive antithesis), A- (negative antithesis)

    Synthesis positions (on separate Synthesis node):
    - S+ (positive synthesis), S- (negative synthesis)

    Statements are connected via PolarityRelationship, which stores
    the contextual alias (e.g., "T1+", "A2-") on the relationship edge.
    This allows the same statement to have different positions in different contexts.

    Analysis:
    - Statements can be marked as rejected during analysis via the `rejected` field
    - Rejected statements are excluded from suggestions but remain in vocabulary
    - The rejection reason (if provided) can be used for UX feedback
    """

    text: str

    # User-facing cosmetic override for text.
    # Does NOT affect hash computation — mutable post-commit.
    # When set, UI/reports/prompts render this instead of `text`.
    display_text: Optional[str] = None

    # Optional rejection marker for analyst suggestions
    # When set, this statement is excluded from future suggestions
    # The value can be a reason string or just "rejected" to indicate rejection
    # Does NOT affect hash computation (analytical metadata)
    rejected: Optional[str] = None

    # Semantic meaning pointer - typically a taxonomy reference (e.g., "systemic:engineering:integrity")
    # Can also be a verbatim meaning, but usually points to an agreed taxonomy.
    # REQUIRED for commit - participates in hash computation.
    meaning: Optional[str] = None

    @property
    def prompt_text(self) -> str:
        """Text for LLM prompts: includes both display_text and canonical text when they differ."""
        if self.display_text and self.display_text != self.text:
            return f"{self.display_text} (derived from: {self.text})"
        return self.text

    # Symmetric relationship: if A opposes B, then B opposes A
    # Used for T vs A (thesis vs antithesis) dialectical opposition
    oppositions: ClassVar[RelationshipManager[Statement]] = RelationshipBoth(
        "Statement",
        model=OppositeOfRelationship,
    )

    # Symmetric relationship for mutually exclusive/contradicting statements
    # Used for T+ vs A- and A+ vs T- (positive vs negative cross-polarity)
    contradictions: ClassVar[RelationshipManager[Statement]] = RelationshipBoth(
        "Statement",
        model=ContradictionOfRelationship,
    )

    # Semantic relationship: T+ → T, A+ → A (positive aspect of neutral)
    # A component can be the positive side of many components
    positive_side_of: ClassVar[RelationshipManager[Statement]] = RelationshipTo(
        "Statement",
        model=PositiveSideOfRelationship,
        cardinality=(0, None)
    )

    # Reverse: A component can have many positive sides
    positive_sides: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=PositiveSideOfRelationship,
        cardinality=(0, None)
    )

    # Semantic relationship: T- → T, A- → A (negative aspect of neutral)
    # A component can be the negative side of many components
    negative_side_of: ClassVar[RelationshipManager[Statement]] = RelationshipTo(
        "Statement",
        model=NegativeSideOfRelationship,
        cardinality=(0, None)
    )

    # Reverse: A component can have many negative sides
    negative_sides: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=NegativeSideOfRelationship,
        cardinality=(0, None)
    )

    source_of: ClassVar[RelationshipManager[Transition]] = RelationshipTo(
        "Transition",
        model=IsSourceOfRelationship,
    )
    target_of: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=IsTargetOfRelationship,
    )

    # Reverse relationships - find sources that created this statement via HAS_STATEMENT.
    # A component can be extracted from multiple sources (same insight from different texts).
    # Use is_in_vocabulary() to check if component belongs to a specific vocabulary context.
    inputs: ClassVar[RelationshipManager[Input]] = RelationshipFrom(
        "Input",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more source Inputs
    )

    ideas: ClassVar[RelationshipManager[Ideas]] = RelationshipFrom(
        "Ideas",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more source Ideas
    )

    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=HasStatementRelationship,
        cardinality=(0, None),
    )

    # Note: Inverse relationships for polarity positions (T, A) and aspect positions (T+, T-, A+, A-)
    # are NOT defined here because Statements have no cardinality
    # constraints - the same statement can be used in unlimited Perspectives.
    # No inverse = implicit (0, None) cardinality.

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this statement.

        Parts: normalized statement text + meaning.
        Normalization (strip + lowercase) ensures case/whitespace variations
        produce the same hash while preserving original text for display.

        Returns:
            List with normalized statement and meaning
        """
        # Normalize for hash: same concept = same hash regardless of casing
        normalized_statement = self.text.strip().lower()
        normalized_meaning = (self.meaning or "").strip().lower()
        return [normalized_statement, normalized_meaning]

    def compute_hash(self) -> str:
        """
        Compute content hash for this Statement.

        Statement is content-addressable: same text + meaning = same hash.
        Unlike structural nodes, committed_at is NOT included because:
        - Deduplication is desirable (same concept should have same identity)
        - No temporal ordering needed (statements don't critique each other)
        - Multiple users creating the same statement should get the same node

        Returns:
            sha256 hex string of text + meaning
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
        Commit this Statement: compute hash and persist.

        Requires `meaning` to be set before committing - this field participates
        in the hash and provides semantic categorization for the statement.

        Before committing, checks for hash collision with Input nodes.
        If an Input exists with the same hash (same content as this statement),
        raises an error - the Input should be cleaned up or transformed first.

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
            ValueError: If meaning is not set, or hash collision with existing Input node
        """
        # Require both text and meaning before commit
        if not self.text:
            raise ValueError(
                "Cannot commit Statement without 'text'."
            )
        if not self.meaning:
            raise ValueError(
                f"Cannot commit Statement without 'meaning'. "
                f"Set meaning to a taxonomy pointer (e.g., 'systemic:engineering:integrity') "
                f"or a verbatim meaning before committing."
            )

        # Compute what hash will be
        potential_hash = self.compute_hash()

        # Check for Input collision (not Statement - dedup is OK)
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.repositories.node_repository import NodeRepository
        repo = NodeRepository()
        existing = repo.find_by_hash(potential_hash)

        # TODO: we probably need to do the same check with Rationale (all content-addressable nodes)
        if existing is not None and isinstance(existing, Input):
            raise ValueError(
                f"Hash collision with Input: An Input exists with content matching this statement. "
                f"Hash: {potential_hash[:8]}... "
                f"The Input should use dx:// reference instead of raw text content."
            )

        # Delegate to parent commit
        return super().commit()

    @property
    def is_simple(self) -> bool:
        """
        Check if this statement is considered "simple".

        A statement is simple if:
        - meaning is not set (None or empty string), OR
        - meaning starts with "dx://taxonomy/Simple"

        Returns:
            True if statement is simple, False otherwise
        """
        if not self.meaning:
            return True
        return self.meaning.lower().startswith("dx://taxonomy/Simple".lower())

    def __repr__(self) -> str:
        """String representation of the statement."""
        display = self.display_text or self.text
        statement_preview = (
            display[:47] + "..." if len(display) > 50 else display
        )
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Statement({hash_str}, text='{statement_preview}')"

    def __format__(self, format_spec: str) -> str:
        """
        Format this statement using Python's format string protocol.

        Format Specifications:
        ----------------------
        [mode][:width]

        Mode (optional):
            "short" - Just the statement (no explanation)
            "long"  - Statement + explanation from the best rationale (default)
            ""      - Empty spec defaults to "long"

        Width (optional, only for "short" mode):
            :N - Truncate statement to N characters and add "..." if truncated
            Example: "short:30" - Statement truncated to 30 chars

        Examples:
        ---------
        f"{comp}"          - Long format (statement + explanation)
        f"{comp:long}"     - Long format (explicit)
        f"{comp:short}"    - Short format (statement only)
        f"{comp:short:30}" - Short format, truncated to 30 chars with "..."

        Usage with label:
        -----------------
        f"{label} = {comp:long}"     - "T = Democracy\nExplanation: Representative system"
        f"{label} = {comp:short}"    - "T = Democracy"
        f"{label} = {comp:short:30}" - "T = Democracy"

        Returns:
            Formatted string
        """
        # Parse format spec: [mode][:width]
        if ":" in format_spec:
            mode, width_str = format_spec.split(":", 1)
            try:
                width = int(width_str)
            except ValueError:
                width = None
        else:
            mode = format_spec
            width = None

        # Default to "long" if no mode provided
        if not mode:
            mode = "long"

        # Start with user-facing text (display_text if set, else text)
        result = self.display_text or self.text

        # Apply width truncation for short mode
        if mode == "short" and width is not None:
            if len(result) > width:
                result = result[:width] + "..."

        # Add explanation if in long mode
        if mode == "long":
            rationales = list(self.rationales.all())
            if rationales:
                # Multiple rationales - number them
                if len(rationales) > 1:
                    explanations = []
                    for idx, (rationale, _) in enumerate(rationales, 1):
                        if rationale.text:
                            explanations.append(f"Explanation {idx}: {rationale.text}")
                    if explanations:
                        result = f"{result}\n" + "\n".join(explanations)
                # Single rationale - no number
                else:
                    rationale, _ = rationales[0]
                    if rationale.text:
                        result = f"{result}\nExplanation: {rationale.text}"
            else:
                # No rationales
                result = f"{result}\nExplanation: N/A"

        return result

    def __str__(self) -> str:
        """Human-readable string representation (defaults to long format)."""
        return self.__format__("")

    def get_alias(self, perspective: Perspective) -> str:
        """
        Get the alias of this component within a specific Perspective's context.

        This method searches all relationship managers on the Perspective (6 core positions)
        and the optional Synthesis node (S+, S-) to find where this component is connected
        and returns the alias from the edge properties. If no custom alias is set, returns
        the position constant as the default alias.

        Args:
            perspective: The Perspective to look up the alias in

        Returns:
            The alias string (e.g., "T1", "A2+") or position constant (e.g., "T", "T+", "A-")

        Raises:
            ValueError: If component is not connected to the perspective

        Example:
            from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
            comp = Statement(text="Democracy")
            pp = Perspective(...)
            pp.t.connect(comp, relationship=TRelationship(alias='T1'))

            alias = comp.get_alias(pp)  # Returns "T1"

            # If alias not set on relationship:
            pp2.t.connect(comp2, relationship=TRelationship(alias=None))
            alias2 = comp2.get_alias(pp2)  # Returns "T" (position constant)
        """
        # Get position first to use as fallback
        position = self.get_position(perspective)
        if not position:
            raise ValueError(f"Component {self.hash} is not connected to Perspective {perspective.hash}")

        # Search through all 6 core position relationship managers on the perspective
        rel_managers = [
            perspective.t,
            perspective.t_plus,
            perspective.t_minus,
            perspective.a,
            perspective.a_plus,
            perspective.a_minus,
        ]

        for manager in rel_managers:
            components = manager.all()  # Returns [(node, rel)]

            for comp, rel in components:
                # Check if this is the component we're looking for
                if comp.hash == self.hash:
                    # Use isinstance for type-safe property access
                    if isinstance(rel, PolarityRelationship):
                        # Return custom alias if set, otherwise position constant
                        return rel.alias if rel.alias else position
                    return position  # Non-polarity relationship, use position

        # Also check synthesis on PP (synthesis is now on Perspective, not Transformation)
        for synthesis, _ in perspective.synthesis.all():
            # Check S+ and S- on the Synthesis node
            for manager in [synthesis.s_plus, synthesis.s_minus]:
                components = manager.all()
                for comp, rel in components:
                    if comp.hash == self.hash:
                        # Use isinstance for type-safe property access
                        if isinstance(rel, PolarityRelationship):
                            # Return custom alias if set, otherwise position constant
                            return rel.alias if rel.alias else position
                        return position  # Non-polarity relationship, use position

        # Should not reach here since get_position() already validated connection
        return position

    def get_position(self, perspective: Perspective) -> Optional[str]:
        """
        Get the position name of this component within a specific Perspective's context.

        This method searches all relationship managers on the Perspective (6 core positions)
        and the optional Synthesis node (S+, S-) to find where this component is connected
        and returns the position constant.

        Args:
            perspective: The Perspective to look up the position in

        Returns:
            The position constant (e.g., "T", "T+", "A-", "S+", "S-") or None if not connected

        Example:
            from dialectical_framework.graph.nodes.polarity import POSITION_T
            from dialectical_framework.graph.nodes.perspective import POSITION_T_PLUS
            comp = Statement(text="Democracy")
            pp = Perspective(...)
            pp.t.connect(comp, relationship=TRelationship(alias='T1'))

            position = comp.get_position(pp)  # Returns "T" (POSITION_T)

            comp2 = Statement(text="Trust")
            pp.t_plus.connect(comp2, relationship=TPlusRelationship(alias='T1+'))
            position2 = comp2.get_position(pp)  # Returns "T+" (POSITION_T_PLUS)
        """
        from dialectical_framework.graph.nodes.polarity import POSITION_T, POSITION_A
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_T_PLUS, POSITION_T_MINUS,
            POSITION_A_PLUS, POSITION_A_MINUS,
        )
        from dialectical_framework.graph.nodes.synthesis import (
            POSITION_S_PLUS, POSITION_S_MINUS
        )

        # Search through all 6 core position relationship managers on the perspective
        positions = [
            (POSITION_T, perspective.t),
            (POSITION_T_PLUS, perspective.t_plus),
            (POSITION_T_MINUS, perspective.t_minus),
            (POSITION_A, perspective.a),
            (POSITION_A_PLUS, perspective.a_plus),
            (POSITION_A_MINUS, perspective.a_minus),
        ]

        for position_name, manager in positions:
            components = manager.all()  # Returns [(node, rel)]

            for comp, rel in components:
                # Check if this is the component we're looking for
                if comp.hash == self.hash:
                    return position_name

        # Also check synthesis on PP (synthesis is now on Perspective, not Transformation)
        for synthesis, _ in perspective.synthesis.all():
            # Check S+ and S- on the Synthesis node
            synth_positions = [
                (POSITION_S_PLUS, synthesis.s_plus),
                (POSITION_S_MINUS, synthesis.s_minus),
            ]
            for position_name, manager in synth_positions:
                components = manager.all()
                for comp, rel in components:
                    if comp.hash == self.hash:
                        return position_name

        return None
