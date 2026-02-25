"""
SemanticDeduplicator: Service for semantic deduplication of components.

Compares newly extracted components against existing vocabulary using LLM
to find semantic equivalents (same concept, different wording).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository,
)
from dialectical_framework.graph.repositories.node_repository import NodeRepository

if TYPE_CHECKING:
    pass


# --- DTOs ---


class SemanticMatchDto(BaseModel):
    """A single semantic match between extraction and DB component."""

    extraction_hash: str = Field(description="Hash of the extracted component")
    db_hash: Optional[str] = Field(
        default=None,
        description="Hash of semantically equivalent DB component, or null if no match",
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence of the match (0.0-1.0)",
    )


class SemanticDedupDto(BaseModel):
    """Result of batch semantic deduplication."""

    matches: list[SemanticMatchDto] = Field(
        default_factory=list,
        description="List of matches between extractions and DB components",
    )


@dataclass
class DedupResult:
    """Result of applying deduplication."""

    # Maps old extracted hash -> replacement DB hash (for matched components)
    replacements: dict[str, str]
    # Components that were deleted (had DB equivalent)
    deleted_count: int
    # Components that were kept (no DB equivalent)
    kept_hashes: list[str]


# --- Service ---


class StatementDeduplication:
    """
    Service for semantic deduplication of components against vocabulary.

    Usage:
        deduplicator = SemanticDeduplicator()
        result = await deduplicator.deduplicate(
            extracted_hashes=["abc123", "def456"],
            vocabulary=vocab_list,
        )
        # result.replacements: {"abc123": "existing_xyz"}
        # result.deleted_count: 1
        # result.kept_hashes: ["def456"]
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def deduplicate(
        self,
        extracted_hashes: list[str],
        vocabulary: list[dict],
    ) -> DedupResult:
        """
        Find and apply semantic deduplication.

        Args:
            extracted_hashes: Hashes of newly extracted components
            vocabulary: Existing vocabulary as list of dicts with keys:
                        hash, statement, meaning, rejected, rationale

        Returns:
            DedupResult with replacements, deleted_count, and kept_hashes
        """
        if not extracted_hashes or not vocabulary:
            return DedupResult(
                replacements={},
                deleted_count=0,
                kept_hashes=extracted_hashes,
            )

        # Get semantic matches from LLM
        dedup_dto = await self._find_semantic_matches(
            extracted_hashes, vocabulary
        )

        # Apply matches: delete duplicates, track replacements
        return self._apply_matches(extracted_hashes, dedup_dto)

    async def _find_semantic_matches(
        self,
        extracted_hashes: list[str],
        vocabulary: list[dict],
    ) -> SemanticDedupDto:
        """Call LLM to find semantic equivalents."""
        # Build extraction descriptions
        extraction_lines = []
        for h in extracted_hashes:
            comp = self._resolve_component(h)
            if comp:
                extraction_lines.append(
                    f"[{comp.short_hash}] {comp.statement} (meaning: {comp.meaning or 'none'})"
                )

        # Build vocabulary descriptions (exclude rejected, limit tokens)
        vocab_lines = []
        non_rejected = [v for v in vocabulary if not v.get("rejected")]
        for v in non_rejected[:100]:
            rationale_hint = f" - {v['rationale'][:80]}..." if v.get("rationale") else ""
            vocab_lines.append(
                f"[{v['hash'][:7]}] {v['statement']} (meaning: {v.get('meaning', 'none')}){rationale_hint}"
            )

        if not extraction_lines or not vocab_lines:
            return SemanticDedupDto(matches=[])

        prompt = f"""Compare these newly extracted statements against existing vocabulary.
Find semantic equivalents (same concept, possibly different wording).

**Newly Extracted Statements:**
{chr(10).join(extraction_lines)}

**Existing Vocabulary:**
{chr(10).join(vocab_lines)}

For each extraction, determine if there's a semantically equivalent
statement in the existing vocabulary. Consider same core concept (even if worded differently).

Only match if confidence >= 0.7 (clearly the same concept).
If no match, set db_hash to null."""

        return await self._conversation.submit(
            response_model=SemanticDedupDto,
            user_content=prompt,
        )

    def _apply_matches(
        self,
        extracted_hashes: list[str],
        dedup_dto: SemanticDedupDto,
    ) -> DedupResult:
        """Apply dedup matches: delete duplicates, return result."""
        replacements: dict[str, str] = {}
        kept_hashes: list[str] = []
        deleted_count = 0
        repo = DialecticalComponentRepository()

        for ext_hash in extracted_hashes:
            # Find match for this extraction
            match = self._find_match(ext_hash, dedup_dto.matches)

            if match and match.db_hash and match.confidence >= 0.7:
                # Has equivalent in DB - delete extraction
                ext_comp = self._resolve_component(ext_hash)
                if ext_comp and repo.safe_delete(ext_comp):
                    deleted_count += 1

                # Record replacement
                replacements[ext_hash] = match.db_hash
            else:
                # No equivalent - keep extraction
                kept_hashes.append(ext_hash)

        return DedupResult(
            replacements=replacements,
            deleted_count=deleted_count,
            kept_hashes=kept_hashes,
        )

    def _find_match(
        self, ext_hash: str, matches: list[SemanticMatchDto]
    ) -> Optional[SemanticMatchDto]:
        """Find matching SemanticMatchDto for an extracted hash."""
        for m in matches:
            if ext_hash.startswith(m.extraction_hash) or m.extraction_hash.startswith(ext_hash):
                return m
        return None

    def _resolve_component(self, hash: str) -> Optional[DialecticalComponent]:
        """Resolve hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash)
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None
