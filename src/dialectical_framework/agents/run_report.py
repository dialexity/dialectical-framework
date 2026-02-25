"""
RunReport: Structured output for agent tools.

Every tool returns a RunReport containing:
- effects: standardized list of atomic mutations (for undo/audit/diff UI)
- artifacts: free-form dict of outputs for orchestration (tool-specific)

See docs for full specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode
    from dialectical_framework.graph.relationship_manager import (
        BoundRelationshipManager,
        RelationshipManager,
    )

# Type alias for relationship type parameter
RelType = Union[str, "RelationshipManager", "BoundRelationshipManager", type]


def _resolve_rel_type(rel_type: RelType) -> str:
    """
    Extract relationship type string from various sources.

    Accepts:
        - str: "OPPOSITE_OF" → returns as-is
        - RelationshipManager: component.oppositions → returns .relationship_type
        - BoundRelationshipManager: same as above
        - Relationship class: class with .type attribute → returns .type
    """
    if isinstance(rel_type, str):
        return rel_type

    # RelationshipManager or BoundRelationshipManager
    if hasattr(rel_type, "relationship_type"):
        return rel_type.relationship_type

    # Relationship class (has 'type' class attribute)
    if isinstance(rel_type, type) and hasattr(rel_type, "type"):
        return rel_type.type

    raise ValueError(
        f"Cannot resolve relationship type from {type(rel_type).__name__}. "
        f"Expected str, RelationshipManager, or relationship class with 'type' attribute."
    )


EffectType = Literal[
    "node_created",
    "node_updated",
    "node_deleted",
    "relationship_created",
    "relationship_updated",
    "relationship_deleted",
]


class NodeRef(BaseModel):
    """Node identity for effects."""

    model_config = ConfigDict(frozen=True)

    label: str
    hash: str

    @classmethod
    def from_node(cls, node: BaseNode) -> NodeRef:
        # Short hash - to save tokens
        return cls(label=node.__class__.__name__, hash=node.short_hash)


class RelationshipRef(BaseModel):
    """Relationship identity for effects."""

    model_config = ConfigDict(frozen=True)

    type: str
    from_node: NodeRef
    to_node: NodeRef


class Effect(BaseModel):
    """A single atomic mutation in the graph."""

    model_config = ConfigDict(frozen=True)

    seq: int
    effect_type: EffectType
    node: Optional[NodeRef] = None
    relationship: Optional[RelationshipRef] = None
    patch: dict[str, Any] = Field(default_factory=dict)
    previous: Optional[dict[str, Any]] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class RunReport(BaseModel):
    """Structured output from a tool run."""

    tool: str
    ok: bool = True
    summary: str = ""
    effects: list[Effect] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)

    # Internal counter for effect sequencing
    _seq_counter: int = PrivateAttr(default=0)

    def _next_seq(self) -> int:
        seq = self._seq_counter
        self._seq_counter += 1
        return seq

    # --- Node effects ---

    def node_created(
        self,
        node: BaseNode,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a node creation."""
        self.effects.append(
            Effect(
                seq=self._next_seq(),
                effect_type="node_created",
                node=NodeRef.from_node(node),
                patch={"statement": getattr(node, "statement", None)},
                meta=meta or {},
            )
        )

    def node_updated(
        self,
        node: BaseNode,
        patch: dict[str, Any],
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a node update."""
        self.effects.append(
            Effect(
                seq=self._next_seq(),
                effect_type="node_updated",
                node=NodeRef.from_node(node),
                patch=patch,
                previous=previous,
                meta=meta or {},
            )
        )

    def node_deleted(
        self,
        node: BaseNode,
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a node deletion (or soft-delete/rejection)."""
        self.effects.append(
            Effect(
                seq=self._next_seq(),
                effect_type="node_deleted",
                node=NodeRef.from_node(node),
                previous=previous,
                meta=meta or {},
            )
        )

    # --- Relationship effects ---

    def relationship_created(
        self,
        rel_type: RelType,
        from_node: BaseNode,
        to_node: BaseNode,
        patch: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record a relationship creation.

        Args:
            rel_type: Relationship type as string, RelationshipManager, or class
            from_node: Source node
            to_node: Target node
            patch: Properties set on the relationship
            meta: Optional metadata
        """
        self.effects.append(
            Effect(
                seq=self._next_seq(),
                effect_type="relationship_created",
                relationship=RelationshipRef(
                    type=_resolve_rel_type(rel_type),
                    from_node=NodeRef.from_node(from_node),
                    to_node=NodeRef.from_node(to_node),
                ),
                patch=patch or {},
                meta=meta or {},
            )
        )

    def relationship_updated(
        self,
        rel_type: RelType,
        from_node: BaseNode,
        to_node: BaseNode,
        patch: dict[str, Any],
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record a relationship property update.

        Args:
            rel_type: Relationship type as string, RelationshipManager, or class
            from_node: Source node
            to_node: Target node
            patch: Changed properties
            previous: Previous values (for undo)
            meta: Optional metadata
        """
        self.effects.append(
            Effect(
                seq=self._next_seq(),
                effect_type="relationship_updated",
                relationship=RelationshipRef(
                    type=_resolve_rel_type(rel_type),
                    from_node=NodeRef.from_node(from_node),
                    to_node=NodeRef.from_node(to_node),
                ),
                patch=patch,
                previous=previous,
                meta=meta or {},
            )
        )

    def relationship_deleted(
        self,
        rel_type: RelType,
        from_node: BaseNode,
        to_node: BaseNode,
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record a relationship deletion.

        Args:
            rel_type: Relationship type as string, RelationshipManager, or class
            from_node: Source node
            to_node: Target node
            previous: Previous values (for undo)
            meta: Optional metadata
        """
        self.effects.append(
            Effect(
                seq=self._next_seq(),
                effect_type="relationship_deleted",
                relationship=RelationshipRef(
                    type=_resolve_rel_type(rel_type),
                    from_node=NodeRef.from_node(from_node),
                    to_node=NodeRef.from_node(to_node),
                ),
                previous=previous,
                meta=meta or {},
            )
        )

    # --- Utilities ---

    def merge(self, other: RunReport) -> RunReport:
        """Merge another report into this one, adjusting seq numbers."""
        for effect in other.effects:
            # Re-sequence effects from the other report
            new_effect = effect.model_copy(update={"seq": self._next_seq()})
            self.effects.append(new_effect)

        # Merge artifacts (other overwrites on conflict)
        merged_artifacts = {**self.artifacts, **other.artifacts}

        return RunReport(
            tool=self.tool,
            ok=self.ok and other.ok,
            summary=f"{self.summary}\n{other.summary}".strip(),
            effects=self.effects,
            artifacts=merged_artifacts,
        )

