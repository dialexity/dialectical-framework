"""
ExecutionReport: Structured mutation log + real-time event source.

Every tool/concern records its graph mutations here as Effect objects.
These serve two purposes:

1. LLM feedback — serialized as JSON in the tool response so the orchestrator
   LLM knows what changed (node hashes, positions, etc.)
2. UI event bus — each Effect is also published to the GraphEventBus in real-time
   so the frontend can reactively update its graph visualization.

Event Bus Integration
---------------------
When the DI container starts, it calls `ExecutionReport.set_event_bus(bus)`.
After that, every mutation method (node_created, etc.) automatically publishes
the Effect to subscribers on the matching sid channel.

Publishing is fire-and-forget via `loop.create_task()`. It's a no-op when:
- No event bus is configured (tests, CLI usage)
- No asyncio event loop is running (rare edge case)
- No sid is set in the scope context (code running outside `with scope(...)`)

App-layer subscription example:
    async with bus.subscribe(sid=orchestrator.sid) as subscriber:
        async for event in subscriber:
            # event.message is a GraphEvent(sid, effect, timestamp)
            await websocket.send_json(event.message.effect.model_dump())
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

if TYPE_CHECKING:
    from dialectical_framework.events.graph_event_bus import GraphEventBus
    from dialectical_framework.graph.nodes.base_node import BaseNode
    from dialectical_framework.graph.relationship_manager import (
        BoundRelationshipManager, RelationshipManager)
    from dialectical_framework.utils.effect_logger import EffectLogger

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
    "node_committed",
    "node_updated",
    "node_deleted",
    "relationship_created",
    "relationship_updated",
    "relationship_deleted",
]


class NodeRef(BaseModel):
    """
    Lightweight node identity for effects.

    Captures just enough to identify the node in the UI without
    carrying the full node object across the event bus.
    """

    model_config = ConfigDict(frozen=True)

    label: str  # Node class name: "Statement", "Perspective", etc.
    hash: Optional[str] = None  # 7-char short hash (None if uncommitted/draft)
    db_id: Optional[int] = None  # DB internal ID (available after save)

    @classmethod
    def from_node(cls, node: BaseNode) -> NodeRef:
        return cls(
            label=node.__class__.__name__,
            hash=node.short_hash,
            db_id=node._id,
        )


class RelationshipRef(BaseModel):
    """Lightweight relationship identity for effects."""

    model_config = ConfigDict(frozen=True)

    type: str  # Relationship type: "T_PLUS", "OPPOSITE_OF", "HAS_POLARITY", etc.
    from_node: NodeRef
    to_node: NodeRef


class Effect(BaseModel):
    """
    A single atomic graph mutation.

    Fields:
        seq: Ordering within a single report (0, 1, 2, ...).
        effect_type: What happened — created/updated/deleted for node or relationship.
        node: Which node was affected (set for node effects).
        relationship: Which edge was affected (set for relationship effects).
        patch: New/current values after mutation.
            - node_created: {"text": "Remote work"} (auto-populated from node.text)
            - node_updated: {"discarded": "not relevant"} (the changed fields)
            - relationship_created: {"heuristic_similarity": 0.82} (rel properties)
        previous: Old values before mutation (enables undo).
            - Only present on _updated and _deleted effects.
            - E.g., {"discarded": None} before a discard.
        meta: Contextual info that isn't a property change.
            - E.g., {"position": "T+"} when an aspect is placed in a Perspective.
            - Helps the UI understand structural context without re-querying.
    """

    model_config = ConfigDict(frozen=True)

    seq: int
    effect_type: EffectType
    node: Optional[NodeRef] = None
    relationship: Optional[RelationshipRef] = None
    patch: dict[str, Any] = Field(default_factory=dict)
    previous: Optional[dict[str, Any]] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(BaseModel):
    """
    Structured output from a tool/concern execution.

    Dual purpose:
    1. Returned as JSON to the LLM (via __str__) so it knows what changed.
    2. Each Effect is published to the GraphEventBus for real-time UI updates.

    Fields:
        tool: Name of the tool/concern that produced this report.
        ok: Whether the operation succeeded.
        summary: Human-readable one-liner for the LLM.
        effects: Ordered list of atomic graph mutations.
        artifacts: Free-form tool-specific outputs (hashes, counts, etc.).
    """

    _event_bus: ClassVar[Optional[GraphEventBus]] = None
    _effect_logger: ClassVar[Optional[EffectLogger]] = None

    tool: str
    ok: bool = True
    summary: str = ""
    effects: list[Effect] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)

    _seq_counter: int = PrivateAttr(default=0)
    _finalized: bool = PrivateAttr(default=False)

    @classmethod
    def set_event_bus(cls, bus: Optional[GraphEventBus]) -> None:
        """
        Set the class-level event bus reference.

        Called once at DI container setup. All subsequent ExecutionReport
        instances will publish effects to this bus automatically.
        Pass None to disable (tests, teardown).
        """
        cls._event_bus = bus

    @classmethod
    def set_effect_logger(cls, logger: Optional[EffectLogger]) -> None:
        """
        Set the class-level effect logger.

        Called at DI container setup when DIALEXITY_GRAPH_LOG_DIR is configured.
        Pass None to disable.
        """
        cls._effect_logger = logger

    def _emit(self, effect: Effect) -> None:
        """
        Publish an effect to the event bus (fire-and-forget).

        Reads the current sid from scope context and schedules an async
        publish on the running event loop. Safe to call from sync code
        since it only schedules — doesn't await.

        No-op when: bus is None, no running loop, or no sid in scope.
        """
        if self._event_bus is None:
            return
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        from dialectical_framework.graph.scope_context import get_current_sid
        sid = get_current_sid()
        if sid:
            loop.create_task(self._event_bus.publish(sid, effect))

    def _log(self, effect: Effect) -> None:
        """Write effect to file log. No-op when logger is None or sid is missing."""
        if self._effect_logger is None:
            return
        from dialectical_framework.agents.agent_context import get_current_agent
        from dialectical_framework.graph.scope_context import get_current_sid
        sid = get_current_sid()
        if not sid:
            return
        agent = get_current_agent() or "pipeline"
        self._effect_logger.log_effect(sid, agent, self.tool, effect)

    def finalize(self) -> None:
        """Log report-complete marker. Idempotent — only logs once."""
        if self._finalized:
            return
        self._finalized = True
        if self._effect_logger is None:
            return
        from dialectical_framework.agents.agent_context import get_current_agent
        from dialectical_framework.graph.scope_context import get_current_sid
        sid = get_current_sid()
        if not sid:
            return
        agent = get_current_agent() or "pipeline"
        self._effect_logger.log_tool_result(
            sid, agent, self.tool, self.ok, self.summary, len(self.effects)
        )

    def _next_seq(self) -> int:
        seq = self._seq_counter
        self._seq_counter += 1
        return seq

    # --- Node effects ---

    def node_created(
        self,
        node: BaseNode,
        patch: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a node creation. Auto-includes node.text in patch."""
        default_patch = {"text": getattr(node, "text", None)}
        if patch:
            default_patch.update(patch)
        effect = Effect(
            seq=self._next_seq(),
            effect_type="node_created",
            node=NodeRef.from_node(node),
            patch=default_patch,
            meta=meta or {},
        )
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    def node_committed(
        self,
        node: BaseNode,
        patch: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record that a draft node was committed (hash now available)."""
        default_patch = {"text": getattr(node, "text", None)}
        if patch:
            default_patch.update(patch)
        effect = Effect(
            seq=self._next_seq(),
            effect_type="node_committed",
            node=NodeRef.from_node(node),
            patch=default_patch,
            meta=meta or {},
        )
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    def node_updated(
        self,
        node: BaseNode,
        patch: dict[str, Any],
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a node property change. Patch = new values, previous = old values."""
        effect = Effect(
            seq=self._next_seq(),
            effect_type="node_updated",
            node=NodeRef.from_node(node),
            patch=patch,
            previous=previous,
            meta=meta or {},
        )
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    def node_deleted(
        self,
        node: BaseNode,
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a node deletion or soft-delete (discard)."""
        effect = Effect(
            seq=self._next_seq(),
            effect_type="node_deleted",
            node=NodeRef.from_node(node),
            previous=previous,
            meta=meta or {},
        )
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    # --- Relationship effects ---

    def relationship_created(
        self,
        rel_type: RelType,
        from_node: BaseNode,
        to_node: BaseNode,
        patch: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a new edge. Patch = relationship properties if any."""
        effect = Effect(
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
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    def relationship_updated(
        self,
        rel_type: RelType,
        from_node: BaseNode,
        to_node: BaseNode,
        patch: dict[str, Any],
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record a relationship property change."""
        effect = Effect(
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
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    def relationship_deleted(
        self,
        rel_type: RelType,
        from_node: BaseNode,
        to_node: BaseNode,
        previous: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an edge removal."""
        effect = Effect(
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
        self.effects.append(effect)
        self._emit(effect)
        self._log(effect)

    # --- Utilities ---

    def __str__(self) -> str:
        """JSON representation returned to the LLM as tool output."""
        self.finalize()
        return self.model_dump_json(indent=2, exclude_none=True)

    def merge(self, other: ExecutionReport) -> ExecutionReport:
        """
        Merge another report into this one (for skills that compose concerns).

        Re-sequences the other report's effects to maintain a single timeline.
        Note: merged effects are NOT re-emitted to the bus (they were already
        emitted when originally recorded by the sub-concern).
        """
        for effect in other.effects:
            new_effect = effect.model_copy(update={"seq": self._next_seq()})
            self.effects.append(new_effect)

        merged_artifacts = {**self.artifacts, **other.artifacts}

        return ExecutionReport(
            tool=self.tool,
            ok=self.ok and other.ok,
            summary=f"{self.summary}\n{other.summary}".strip(),
            effects=self.effects,
            artifacts=merged_artifacts,
        )
