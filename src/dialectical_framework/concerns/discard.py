"""
Discard: Concern for marking statements/perspectives as discarded.

Blocking rules:
- Statement: blocked if used by any non-discarded Perspective.
- Perspective: blocked if it participates in any Cycle.
- Decision: never blocked (nothing structural depends on a Decision).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.decision import Decision
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository


@dataclass
class DiscardResult:
    node_type: str
    hash: str
    affected_perspectives: list[tuple[Perspective, str]]
    blocked: bool = False
    block_reason: str = ""


class Discard(ReasonableConcern[DiscardResult]):
    """
    Marks a Statement, Perspective, or Decision as discarded.

    For Statements: blocked if any non-discarded PP uses it. Discard the PPs first.
    For Perspectives: blocked if in a Cycle. Deletes uncommitted, soft-discards committed.
    For Decisions: never blocked — replacing a decision is record-new + discard-old
    with a reason referencing the new one (e.g. "superseded by [[hash]]").

    Programmatic usage:
        concern = Discard()
        result = await concern.resolve(hash="abc123", reason="doesn't resonate")
        if result.blocked:
            print(f"Cannot discard: {result.block_reason}")
    """

    @inject
    async def resolve(
        self,
        hash: str,
        reason: str = "discarded",
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> DiscardResult:
        repo = NodeRepository()

        # An empty reason would exclude the node from active queries (NULL
        # check) while suppressing truthiness-based "discarded" flags in
        # renderers — normalize to the default.
        reason = reason.strip() if reason and reason.strip() else "discarded"

        # find_by_hash(node_type=...) raises TypeError on a type mismatch
        # (it does not return None), so resolve untyped and dispatch here.
        node = repo.find_by_hash(hash)
        if isinstance(node, Statement):
            return self._discard_statement(node, reason)
        if isinstance(node, Perspective):
            return self._discard_perspective(node, reason)
        if isinstance(node, Decision):
            return self._discard_decision(node, reason)

        raise ValueError(f"No Statement, Perspective, or Decision found with hash: {hash}")

    def _discard_statement(self, statement: Statement, reason: str) -> DiscardResult:
        pp_repo = PerspectiveRepository()
        affected = pp_repo.find_by_statement(statement)

        blocking_pps = [
            pp for pp, _ in affected
            if pp.is_committed and not pp.discarded
        ]

        if blocking_pps:
            hashes = ", ".join(pp.short_hash for pp in blocking_pps)
            block_reason = (
                f"Cannot discard: statement is used by non-discarded Perspective(s) [{hashes}]. "
                f"Discard or edit those Perspectives first."
            )
            self._report.ok = False
            self._report.summary = block_reason
            return DiscardResult(
                node_type="Statement",
                hash=statement.short_hash,
                affected_perspectives=affected,
                blocked=True,
                block_reason=block_reason,
            )

        statement.discarded = reason
        statement.save()
        self._report.node_updated(statement, patch={"discarded": reason})

        self._report.ok = True
        self._report.summary = f"Discarded statement '{statement.text}'"
        self._report.artifacts["node_type"] = "Statement"
        self._report.artifacts["hash"] = statement.short_hash
        self._report.artifacts["text"] = statement.text
        self._report.artifacts["affected_perspectives"] = len(affected)

        return DiscardResult(
            node_type="Statement",
            hash=statement.short_hash,
            affected_perspectives=affected,
        )

    def _discard_decision(self, decision: Decision, reason: str) -> DiscardResult:
        # Decisions commit atomically, so only the committed path exists;
        # nothing structural depends on a Decision — no dependency guards.
        decision.discarded = reason
        decision.save()
        self._report.node_updated(decision, patch={"discarded": reason})

        self._report.ok = True
        self._report.summary = f"Discarded decision '{decision}'"
        self._report.artifacts["node_type"] = "Decision"
        self._report.artifacts["hash"] = decision.short_hash

        return DiscardResult(
            node_type="Decision",
            hash=decision.short_hash,
            affected_perspectives=[],
        )

    def _discard_perspective(self, perspective: Perspective, reason: str) -> DiscardResult:
        pp_hash = perspective.short_hash
        pp_repo = PerspectiveRepository()

        if perspective.is_committed and pp_repo.is_in_use_by_cycle(perspective):
            block_reason = (
                f"Cannot discard: Perspective {pp_hash} participates in Cycles. "
                f"Use edit_perspective to replace it, or delete the downstream "
                f"Cycles/Wheels first."
            )
            self._report.ok = False
            self._report.summary = block_reason
            return DiscardResult(
                node_type="Perspective",
                hash=pp_hash,
                affected_perspectives=[],
                blocked=True,
                block_reason=block_reason,
            )

        if not perspective.committed_at:
            pp_repo.discard_uncommitted(perspective)
            self._report.node_deleted(perspective)
            self._report.summary = f"Discarded uncommitted Perspective {pp_hash}"
        else:
            perspective.discarded = reason
            perspective.save()
            self._report.node_updated(perspective, patch={"discarded": reason})
            self._report.summary = f"Marked Perspective {pp_hash} as discarded"

        self._report.ok = True
        self._report.artifacts["node_type"] = "Perspective"
        self._report.artifacts["hash"] = pp_hash

        return DiscardResult(
            node_type="Perspective",
            hash=pp_hash,
            affected_perspectives=[],
        )
