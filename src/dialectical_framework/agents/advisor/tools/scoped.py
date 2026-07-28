"""
Scoped tool factory for the nexus-scoped Advisor variant.

Scope is enforced IN CODE, not prompt: the pinned nexus hash is closed over
by the tool functions — never an LLM-supplied parameter. This makes sibling
nexus creation unreachable and keeps sync/discard pinned to the exploration,
regardless of what the model decides to pass.

The scoped Advisor keeps its full analytical power (it IS Analyst+Explorer
behind one voice): anchor plants new tensions (standalone), the scoped
explore weaves them into the pinned nexus, sync/inspect_node/read_digest
read, discard retracts (nexus members only). Only `ingest` is excluded —
bulk extraction belongs to the unscoped flow.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field


def build_scoped_tools(nexus_hash: str) -> list:
    """
    Build the tool set for a nexus-scoped Advisor.

    The nexus_hash is captured by closure — the LLM cannot redirect any of
    these tools to another nexus or create a new one. Validation that the
    nexus exists happens in Advisor.__init__, not here (keeps the factory
    DB-free for signature tests).
    """
    from dialectical_framework.agents.advisor.tools.anchor import anchor
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest

    pinned_hash = nexus_hash

    @llm.tool
    async def sync() -> str:
        """Re-read this exploration's state. Use when you need a fresh picture after changes — e.g., after enriching the exploration. Not needed after every tool call."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        concern = DialecticalContext(nexus_hash=pinned_hash)
        return await concern.resolve()

    @llm.tool
    async def discard(
        hash: Annotated[str, Field(description="Hash (or prefix) of the Statement or Perspective to discard")],
        reason: Annotated[str, Field(description="Why it's being discarded")] = "discarded",
    ) -> str:
        """Mark a Statement or Perspective as discarded when the user disagrees with it or finds it irrelevant. Only nodes within this exploration can be discarded. Will refuse if the target participates in existing Cycles/Wheels."""
        from dialectical_framework.concerns.discard import Discard

        refusal = _outside_scope_refusal(pinned_hash, hash)
        if refusal:
            return refusal

        concern = Discard()
        await concern.resolve(hash=hash, reason=reason)
        return str(concern.report)

    @llm.tool
    async def explore(
        perspective_hashes: Annotated[
            list[str],
            Field(description="Hashes of perspectives to weave into this exploration"),
        ],
    ) -> str:
        """Enrich this exploration with new perspectives: builds causal arrangements, action-reflection pathways, and synthesis for what's new. Call when a newly anchored tension should join the exploration."""
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        # intent is irrelevant on the expand path (nexus already exists)
        return await run_exploration(
            perspective_hashes, intent="", nexus_hash=pinned_hash
        )

    return [anchor, sync, inspect_node, read_digest, discard, explore]


def _outside_scope_refusal(nexus_hash: str, target_hash: str) -> str | None:
    """
    Return a refusal message if the target is a Perspective outside the
    pinned nexus; None if the discard may proceed.

    Statements are delegated to Discard's own statement-in-use blocking (a
    statement used by any live perspective won't discard anyway).
    """
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.repositories.nexus_repository import \
        NexusRepository
    from dialectical_framework.graph.repositories.node_repository import \
        NodeRepository

    node = NodeRepository().find_by_hash(target_hash)
    if not isinstance(node, Perspective):
        # Not a perspective (likely a statement) — let Discard's own
        # guards handle it.
        return None
    pp = node

    nexus = NexusRepository().find_by_hash_prefix(nexus_hash)
    if nexus is None:
        return (
            f"Cannot discard: pinned exploration {nexus_hash} not found."
        )

    member_ids = {member._id for member, _ in nexus.perspectives.all()}
    if pp._id not in member_ids:
        return (
            f"Refused: perspective [[{target_hash}]] is outside this "
            f"exploration's scope and cannot be discarded from here."
        )
    return None
