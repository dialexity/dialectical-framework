"""
Reject: Concern + tool for marking statements/perspectives as rejected.

Blocking rules:
- Statement: blocked if used by any non-rejected Perspective.
- Perspective: blocked if it participates in any Cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository


@dataclass
class RejectResult:
    node_type: str
    hash: str
    affected_perspectives: list[tuple[Perspective, str]]
    blocked: bool = False
    block_reason: str = ""


class Reject(ReasonableConcern[RejectResult]):
    """
    Marks a Statement or Perspective as rejected.

    For Statements: blocked if any non-rejected PP uses it. Reject the PPs first.
    For Perspectives: blocked if in a Cycle. Discards uncommitted, soft-rejects committed.

    Programmatic usage:
        concern = Reject()
        result = await concern.resolve(hash="abc123", reason="doesn't resonate")
        if result.blocked:
            print(f"Cannot reject: {result.block_reason}")
    """

    @inject
    async def resolve(
        self,
        hash: str,
        reason: str = "rejected",
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> RejectResult:
        repo = NodeRepository()

        # Try Statement first
        node = repo.find_by_hash(hash, node_type=Statement)
        if node is not None:
            return self._reject_statement(node, reason)

        # Try Perspective
        node = repo.find_by_hash(hash, node_type=Perspective)
        if node is not None:
            return self._reject_perspective(node, reason)

        raise ValueError(f"No Statement or Perspective found with hash: {hash}")

    def _reject_statement(self, statement: Statement, reason: str) -> RejectResult:
        pp_repo = PerspectiveRepository()
        affected = pp_repo.find_by_statement(statement)

        blocking_pps = [
            pp for pp, _ in affected
            if pp.is_committed and not pp.rejected
        ]

        if blocking_pps:
            hashes = ", ".join(pp.short_hash for pp in blocking_pps)
            block_reason = (
                f"Cannot reject: statement is used by non-rejected Perspective(s) [{hashes}]. "
                f"Reject or edit those Perspectives first."
            )
            self._report.ok = False
            self._report.summary = block_reason
            return RejectResult(
                node_type="Statement",
                hash=statement.short_hash,
                affected_perspectives=affected,
                blocked=True,
                block_reason=block_reason,
            )

        statement.rejected = reason
        statement.save()
        self._report.node_updated(statement, patch={"rejected": reason})

        self._report.ok = True
        self._report.summary = f"Rejected statement '{statement.text}'"
        self._report.artifacts["node_type"] = "Statement"
        self._report.artifacts["hash"] = statement.short_hash
        self._report.artifacts["text"] = statement.text
        self._report.artifacts["affected_perspectives"] = len(affected)

        return RejectResult(
            node_type="Statement",
            hash=statement.short_hash,
            affected_perspectives=affected,
        )

    def _reject_perspective(self, perspective: Perspective, reason: str) -> RejectResult:
        pp_hash = perspective.short_hash
        pp_repo = PerspectiveRepository()

        if perspective.is_committed and pp_repo.is_in_use_by_cycle(perspective):
            block_reason = (
                f"Cannot reject: Perspective {pp_hash} participates in Cycles. "
                f"Use edit_perspective to replace it, or delete the downstream "
                f"Cycles/Wheels first."
            )
            self._report.ok = False
            self._report.summary = block_reason
            return RejectResult(
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
            perspective.rejected = reason
            perspective.save()
            self._report.node_updated(perspective, patch={"rejected": reason})
            self._report.summary = f"Marked Perspective {pp_hash} as rejected"

        self._report.ok = True
        self._report.artifacts["node_type"] = "Perspective"
        self._report.artifacts["hash"] = pp_hash

        return RejectResult(
            node_type="Perspective",
            hash=pp_hash,
            affected_perspectives=[],
        )


@llm.tool
async def reject(
    hash: Annotated[str, Field(description="Hash (or prefix) of the Statement or Perspective to reject")],
    reason: Annotated[str, Field(description="Why it's being rejected")] = "rejected",
) -> str:
    """Mark a Statement or Perspective as rejected when the user disagrees with it or finds it irrelevant. Uncommitted Perspectives are discarded entirely; committed ones are soft-rejected and filtered from future queries. Will refuse if the target participates in existing Cycles/Wheels — in that case, use edit_perspective to replace it."""
    concern = Reject()
    await concern.resolve(hash=hash, reason=reason)
    return str(concern.report)
