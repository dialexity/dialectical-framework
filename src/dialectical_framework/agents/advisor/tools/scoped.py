"""
Tool factory for the Advisor mode of an exploration session.

This is the "counsel mode" head of an Explorer↔Advisor toggle: the host
hands the Explorer conversation (messages + nexus_hash) to an Advisor so
the user can discuss what the exploration MEANS, then may hand back to
Explorer for technical work. Same conversation, same exploration,
different head.

The nexus pin is enforced IN CODE, not prompt: the hash is closed over by
the tool functions — never an LLM-supplied parameter. This makes sibling
nexus creation unreachable and keeps sync/discard pinned to the exploration,
regardless of what the model decides to pass.

The Advisor keeps its full analytical power in this mode (it IS
Analyst+Explorer behind one voice): anchor plants new tensions (standalone),
the pinned explore weaves them into the exploration, deepen develops an
alternative arrangement of the pinned exploration on demand (guarded by
wheel-membership), sync/inspect_node/read_digest read, discard retracts
(members of the pinned nexus and standalone perspectives — e.g. its own
rejected anchors — but never members of OTHER explorations), and
record_decision persists confirmed decisions (Case-level, unguarded by the
pin). Only `ingest` is excluded — bulk extraction belongs to the unscoped
flow.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field


def build_scoped_tools(nexus_hash: str, principal: str = "human") -> list:
    """
    Build the tool set for an exploration-pinned Advisor (counsel mode).

    The nexus_hash is captured by closure — the LLM cannot redirect any of
    these tools to another nexus or create a new one. Validation that the
    nexus exists happens in Advisor.__init__, not here (keeps the factory
    DB-free for signature tests). `principal` (host-attested confirmer
    identity, closed over the same way) reaches record_decision — see
    tools/record_decision.py.
    """
    from dialectical_framework.agents.advisor.tools.anchor import anchor
    from dialectical_framework.agents.advisor.tools.record_decision import \
        build_record_decision
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest

    record_decision = build_record_decision(principal)
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
        hash: Annotated[str, Field(description="Hash (or prefix) of the Statement, Perspective, or Decision to discard")],
        reason: Annotated[str, Field(description="Why it's being discarded")] = "discarded",
    ) -> str:
        """Mark a Statement, Perspective, or Decision as discarded when the user disagrees with it or finds it irrelevant. Works on members of this exploration, on standalone perspectives (e.g. a freshly anchored framing the user rejected), and on recorded decisions the person retracts or replaces; refuses members of other explorations. Will refuse if the target participates in existing Cycles/Wheels."""
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

    @llm.tool
    async def deepen(
        wheel_hash: Annotated[
            str,
            Field(
                description="Hash of the shallow wheel (causal arrangement) within this exploration to develop"
            ),
        ],
    ) -> str:
        """Develop an alternative causal arrangement of THIS exploration: generates its action-reflection pathways and synthesis. Use when the person's lived reality points at an arrangement whose pathways don't exist yet. Idempotent on already-deepened wheels."""
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen

        refusal = _wheel_outside_scope_refusal(pinned_hash, wheel_hash)
        if refusal:
            return refusal

        return await run_deepen(wheel_hash)

    # record_decision is appended as-is: decisions are Case-level facts, not
    # exploration members — no nexus-scope guard applies (grounds may be
    # exploration members; grounding is read-only w.r.t. the exploration).
    return [anchor, sync, inspect_node, read_digest, discard, explore, deepen, record_decision]


def _outside_scope_refusal(nexus_hash: str, target_hash: str) -> str | None:
    """
    Return a refusal message if the target is a Perspective belonging to a
    DIFFERENT exploration; None if the discard may proceed.

    The pin protects explorations (deliverables), not standalone garbage:
    - member of the pinned nexus → allowed (consent handled by the preamble)
    - member of another nexus → refused (someone else's deliverable)
    - member of no nexus → allowed (e.g. a framing this head anchored during
      the conversation and the user rejected — must be retractable)

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
        # Not a perspective (a statement or a decision) — let Discard's own
        # guards handle it; decisions are Case-level, so no nexus pin applies.
        return None
    pp = node

    nexus = NexusRepository().find_by_hash_prefix(nexus_hash)
    if nexus is None:
        return (
            f"Cannot discard: pinned exploration {nexus_hash} not found."
        )

    membership_ids = {n._id for n, _ in pp.nexus.all()}
    if not membership_ids:
        # Standalone perspective (no exploration) — retractable.
        return None

    if membership_ids - {nexus._id}:
        # Lives in another exploration (possibly in addition to the pinned
        # one) — discarding is global and would prune that deliverable too.
        also = "also " if nexus._id in membership_ids else ""
        return (
            f"Refused: perspective [[{target_hash}]] {also}belongs to another "
            f"exploration — discarding is global and would remove it there "
            f"too, so it cannot be discarded from here."
        )
    return None


def _wheel_outside_scope_refusal(nexus_hash: str, wheel_hash: str) -> str | None:
    """
    Return a refusal message if the wheel does not belong to the pinned
    exploration; None if deepening may proceed.

    A wheel's exploration is derived through its perspectives (same traversal
    ExploreTransformations uses): every wheel perspective must be a member of
    the pinned nexus.
    """
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.repositories.nexus_repository import \
        NexusRepository
    from dialectical_framework.graph.repositories.node_repository import \
        NodeRepository

    node = NodeRepository().find_by_hash(wheel_hash)
    if not isinstance(node, Wheel):
        return f"Cannot deepen: [[{wheel_hash}]] is not a wheel."

    nexus = NexusRepository().find_by_hash_prefix(nexus_hash)
    if nexus is None:
        return f"Cannot deepen: pinned exploration {nexus_hash} not found."

    member_ids = {pp._id for pp, _ in nexus.perspectives.all()}
    wheel_pps = node._perspectives
    if not wheel_pps or any(pp._id not in member_ids for pp in wheel_pps):
        return (
            f"Refused: wheel [[{wheel_hash}]] is outside this exploration's "
            f"scope and cannot be deepened from here."
        )
    return None
