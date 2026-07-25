"""
AntitheticalThesisDetection: Detect when provided theses are antitheses of each other.

When a user supplies several theses, two of them may actually be dialectical
opposites (e.g. "Centralization" vs "Decentralization"). This concern detects
such pairs so they can be consolidated into a single T-A Polarity instead of
each spawning its own independent antithesis.

It is the mirror image of ``StatementDeduplication``: dedup collapses statements
that assert the *same* claim and deliberately refuses to touch opposites; this
concern surfaces the opposites.

Two-stage, read-only (creates NO database nodes — the caller decides what to do):
1. Propose candidates: one batched LLM call flags which pairs look like genuine
   dialectical opposites (not merely same-topic).
2. Score candidates: each candidate is scored with ``AntithesisClassification``
   in both directions; the higher HS wins and fixes the T/A orientation.

Results are banded by HS (reusing the framework's own thresholds):
- ``merge_pairs``   — HS >= MERGE_THRESHOLD (0.7): strong, unambiguous opposition
- ``suggest_pairs`` — SUGGEST_THRESHOLD (0.1) < HS < 0.7: valid but weak, ambiguous
- HS <= 0.1 is discarded ("wrong category", not an antithesis).

Usage:
    detector = AntitheticalThesisDetection()
    result = await detector.resolve(thesis_hashes=[...], text="context...")
    for pair in result.merge_pairs:
        # pair.thesis_hash is T, pair.antithesis_hash is A
        ...
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement


# HS bands (see module docstring). Operators intentionally asymmetric to match
# existing conventions: `>= 0.7` mirrors AnalysisPipeline._rank_polarities and
# the coherence/orthogonality gates; `> 0.1` mirrors the antithesis-validity rule
# in AntithesisClassification ("HS > 0.1 means valid antithesis").
MERGE_THRESHOLD = 0.7
SUGGEST_THRESHOLD = 0.1


# --- System Prompt (candidate proposal) ---

SYSTEM_PROMPT = """You are a dialectical analyst identifying oppositions within a set of theses.

You are given a numbered list of theses. Your task is to find pairs that are genuine
DIALECTICAL OPPOSITES of one another — where one thesis is essentially the antithesis
(T vs A) of the other along the same conceptual dimension.

A pair is a dialectical opposition when the two statements pull in opposing directions
on the same axis. Examples: "Centralization" vs "Decentralization", "Stability" vs
"Change", "Individual freedom" vs "Collective order".

Do NOT flag pairs that are merely about the same topic, complementary, or loosely
related. "Growth requires structure" and "Growth dilutes culture" share a topic but are
NOT opposites — they make different claims, not opposing ones on a single axis.

Only propose a pair when you are reasonably confident the two are true opposites.
Return candidate pairs by their list indices."""


# --- DTOs (LLM structured output) ---


class CandidatePairDto(BaseModel):
    """A pair of thesis indices proposed as dialectical opposites."""

    index_a: int = Field(description="List index of the first thesis in the pair")
    index_b: int = Field(description="List index of the second thesis in the pair")
    reasoning: str = Field(
        default="",
        description="Brief reason these two are dialectical opposites on a single axis",
    )


class CandidatePairsDto(BaseModel):
    """Result of the candidate-proposal stage."""

    pairs: list[CandidatePairDto] = Field(
        default_factory=list,
        description="Pairs of indices that appear to be dialectical opposites",
    )


# --- Result ---


@dataclass
class ThesisPair:
    """A detected antithetical pair, oriented so thesis_hash=T, antithesis_hash=A.

    Carries the antithesis Mode/Arousal from classification so the caller that
    actually creates the Polarity can persist them (per the "Antithesis
    Persistence Checklist") without re-running the LLM.
    """

    thesis_hash: str
    antithesis_hash: str
    thesis_text: str
    antithesis_text: str
    heuristic_similarity: float
    mode_value: float
    arousal_value: float
    reasoning: str = ""

    def as_dict(self) -> dict:
        return {
            "thesis_hash": self.thesis_hash,
            "antithesis_hash": self.antithesis_hash,
            "thesis_text": self.thesis_text,
            "antithesis_text": self.antithesis_text,
            "heuristic_similarity": self.heuristic_similarity,
            "reasoning": self.reasoning,
        }


@dataclass
class ConsolidationResult:
    """Detected pairs banded by HS. No DB nodes created."""

    merge_pairs: list[ThesisPair] = field(default_factory=list)
    suggest_pairs: list[ThesisPair] = field(default_factory=list)


# --- Concern ---


class AntitheticalThesisDetection(ReasonableConcern[ConsolidationResult]):
    """
    Detect antithetical pairs among a set of theses. Read-only (no DB writes).

    Mirrors AntithesisClassification / StatementDeduplication, which also return
    results without persisting anything.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        thesis_hashes: list[str],
        text: str = "",
    ) -> ConsolidationResult:
        """
        Detect which theses among ``thesis_hashes`` are antitheses of each other.

        Args:
            thesis_hashes: Hashes of the candidate thesis Statements.
            text: Optional source context for scoring.

        Returns:
            ConsolidationResult with merge_pairs (HS >= 0.7) and suggest_pairs
            (0.1 < HS < 0.7). Empty when fewer than 2 theses resolve.
        """
        self._text = text

        # Resolve and dedupe hashes to committed Statements, preserving order.
        statements: list[Statement] = []
        seen: set[str] = set()
        for h in thesis_hashes:
            if h in seen:
                continue
            seen.add(h)
            stmt = self._resolve_statement(h)
            if stmt is not None:
                statements.append(stmt)

        if len(statements) < 2:
            self._report.ok = True
            self._report.summary = "Fewer than 2 theses — no consolidation possible"
            self._report.artifacts["consolidation_merges"] = []
            self._report.artifacts["consolidation_suggestions"] = []
            return ConsolidationResult()

        # Stage A: propose candidate pairs (one batched LLM call).
        candidates = await self._propose_candidates(statements)

        # Stage B: score each candidate in both directions, take the stronger.
        scored = await self._score_candidates(statements, candidates)

        # Greedy assignment: highest HS first, each thesis used at most once.
        result = self._assign(scored)

        self._report.ok = True
        self._report.artifacts["consolidation_merges"] = [
            p.as_dict() for p in result.merge_pairs
        ]
        self._report.artifacts["consolidation_suggestions"] = [
            p.as_dict() for p in result.suggest_pairs
        ]
        self._report.summary = (
            f"Detected {len(result.merge_pairs)} merge pair(s) and "
            f"{len(result.suggest_pairs)} suggestion(s) among {len(statements)} theses"
        )
        return result

    # --- Stage A: candidate proposal ---

    async def _propose_candidates(
        self, statements: list[Statement]
    ) -> list[tuple[int, int]]:
        """One batched LLM call: which index pairs look like dialectical opposites."""
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        lines = [f"[{i}] {s.prompt_text}" for i, s in enumerate(statements)]
        context_section = f"\n<context>\n{self._text}\n</context>\n" if self._text else ""
        prompt = f"""{context_section}
Theses:
{chr(10).join(lines)}

Identify pairs that are genuine dialectical opposites of one another (T vs A on the
same axis). Return each as a pair of list indices. Return an empty list if none are
true opposites."""

        dto = await self._conversation.submit(
            response_model=CandidatePairsDto,
            user_content=prompt,
        )

        # Validate and normalize indices; drop out-of-range / self-pairs / dupes.
        n = len(statements)
        candidates: list[tuple[int, int]] = []
        seen_pairs: set[tuple[int, int]] = set()
        for p in dto.pairs:
            a, b = p.index_a, p.index_b
            if a == b or not (0 <= a < n) or not (0 <= b < n):
                continue
            key = (min(a, b), max(a, b))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            candidates.append(key)
        return candidates

    # --- Stage B: HS scoring (both directions) ---

    async def _score_candidates(
        self,
        statements: list[Statement],
        candidates: list[tuple[int, int]],
    ) -> list[ThesisPair]:
        """Score each candidate pair in both directions; keep the higher-HS orientation."""
        if not candidates:
            return []

        async def _score_one(i: int, j: int) -> Optional[ThesisPair]:
            s_i, s_j = statements[i], statements[j]

            # AntithesisClassification is asymmetric (the thesis defines the apex),
            # so score both orientations and take whichever reads as stronger.
            clf_ij = AntithesisClassification()
            clf_ji = AntithesisClassification()
            res_ij, res_ji = await asyncio.gather(
                clf_ij.resolve(
                    thesis=s_i, antithesis_statement=s_j.prompt_text, text=self._text
                ),
                clf_ji.resolve(
                    thesis=s_j, antithesis_statement=s_i.prompt_text, text=self._text
                ),
            )
            self._report = self._report.merge(clf_ij.report)
            self._report = self._report.merge(clf_ji.report)

            if res_ij.heuristic_similarity >= res_ji.heuristic_similarity:
                thesis, antithesis, res = s_i, s_j, res_ij
            else:
                thesis, antithesis, res = s_j, s_i, res_ji

            return ThesisPair(
                thesis_hash=thesis.hash,
                antithesis_hash=antithesis.hash,
                thesis_text=thesis.text,
                antithesis_text=antithesis.text,
                heuristic_similarity=res.heuristic_similarity,
                mode_value=res.mode_value,
                arousal_value=res.arousal_value,
                reasoning=res.reasoning,
            )

        scored = await asyncio.gather(*[_score_one(i, j) for i, j in candidates])
        return [p for p in scored if p is not None]

    # --- Greedy assignment + banding ---

    def _assign(self, scored: list[ThesisPair]) -> ConsolidationResult:
        """Highest HS first; each thesis consumed at most once. Then band by HS."""
        result = ConsolidationResult()
        consumed: set[str] = set()

        for pair in sorted(
            scored, key=lambda p: p.heuristic_similarity, reverse=True
        ):
            if pair.heuristic_similarity <= SUGGEST_THRESHOLD:
                continue  # wrong category — not an antithesis
            if pair.thesis_hash in consumed or pair.antithesis_hash in consumed:
                continue
            consumed.add(pair.thesis_hash)
            consumed.add(pair.antithesis_hash)

            if pair.heuristic_similarity >= MERGE_THRESHOLD:
                result.merge_pairs.append(pair)
            else:
                result.suggest_pairs.append(pair)

        return result

    # --- Helpers ---

    def _resolve_statement(self, hash: str) -> Optional[Statement]:
        """Resolve a hash to a committed Statement (as FindPolarities does)."""
        from dialectical_framework.graph.nodes.statement import Statement

        repo = NodeRepository()
        try:
            node = repo.find_by_hash(hash)
        except ValueError:
            return None
        if isinstance(node, Statement):
            return node
        return None
