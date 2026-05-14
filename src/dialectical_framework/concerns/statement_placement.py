"""
StatementPlacement: Concern for recognizing where a statement exists or could belong
in the dialectical graph.

Pure search/recognition — does NOT create Statements or modify the graph.

Flow:
1. Semantic dedup check against existing vocabulary
2. If match found → graph lookup: what Perspectives/positions reference it?
3. If no match → return "not found" (caller routes to surface_theses, etc.)

Usage:
    placer = StatementPlacement()
    result = await placer.resolve(statement="Hate", text="context...")

    if result.found:
        print(f"Matched: '{result.statement.text}' at positions: {result.positions}")
    else:
        print("Not in graph — introduce via surface_theses or find_polarities")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.statement_deduplication import (
    StatementDeduplication,
)
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)
from dialectical_framework.graph.repositories.statement_repository import (
    StatementRepository,
)


@dataclass
class StatementPosition:
    """Where a Statement sits in the graph."""

    perspective_hash: str
    position: str  # T, A, T+, T-, A+, A-, S+, S-


@dataclass
class StatementPlacementResult:
    """Result of statement recognition."""

    query: str
    found: bool
    statement: Optional[Statement] = None
    positions: list[StatementPosition] = field(default_factory=list)


class StatementPlacement(ReasonableConcern[StatementPlacementResult]):
    """
    Recognizes whether a statement already exists in the graph and where it sits.

    Uses StatementDeduplication.check_idea() for semantic matching,
    then PerspectiveRepository for positional lookup.
    """

    async def resolve(
        self,
        statement: str,
        text: str = "",
    ) -> StatementPlacementResult:
        if not statement or not statement.strip():
            raise ValueError("Cannot look up empty statement")

        statement = statement.strip()

        stmt_repo = StatementRepository()
        vocabulary = stmt_repo.get_vocabulary_with_rationales()

        if not vocabulary:
            self._report.ok = True
            self._report.summary = f"No vocabulary in scope — '{statement}' is new"
            return StatementPlacementResult(query=statement, found=False)

        dedup = StatementDeduplication()
        match = await dedup.check_idea(idea=statement, vocabulary=vocabulary, text=text)
        self._report = self._report.merge(dedup.report)

        if not match:
            self._report.ok = True
            self._report.summary = f"'{statement}' not found in graph"
            return StatementPlacementResult(query=statement, found=False)

        positions = self._lookup_positions(match)

        self._report.ok = True
        if positions:
            pos_summary = ", ".join(f"{p.position} in {p.perspective_hash[:7]}" for p in positions)
            self._report.summary = f"'{statement}' matches '{match.text}' — {pos_summary}"
        else:
            self._report.summary = f"'{statement}' matches '{match.text}' (not in any Perspective)"

        self._report.artifacts["statement_hash"] = match.hash
        self._report.artifacts["positions"] = [
            {"perspective": p.perspective_hash, "position": p.position}
            for p in positions
        ]

        return StatementPlacementResult(
            query=statement,
            found=True,
            statement=match,
            positions=positions,
        )

    def _lookup_positions(self, statement: Statement) -> list[StatementPosition]:
        """Find all Perspectives that use this Statement and at what position."""
        pp_repo = PerspectiveRepository()
        usages = pp_repo.find_by_statement(statement)

        positions = []
        for pp, rel_type in usages:
            if pp.rejected:
                continue
            positions.append(StatementPosition(
                perspective_hash=pp.hash,
                position=rel_type,
            ))
        return positions
