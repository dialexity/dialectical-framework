"""
SemanticDeduplicator: Service for semantic deduplication of components.

Compares newly extracted components against existing vocabulary using LLM
to find semantic equivalents (same concept, different wording).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.repositories.statement_repository import \
    StatementRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

if TYPE_CHECKING:
    pass


from dialectical_framework.concerns.statement_classification import (
    parse_meaning_uri)

SIMPLE_MEANING = "dx://taxonomy/Simple"


def _extract_meaning_prefix(meaning: Optional[str]) -> Optional[str]:
    """
    Extract taxonomy prefix from meaning URI (everything except the leaf).

    Uses parse_meaning_uri from StatementClassification for consistent parsing.

    Empty string or None meaning returns None, which means "matches everything".
    The prefix includes domain, taxonomy version, category, and branch.

    Special case: Simple meaning (dx://taxonomy/Simple) returns the full URI
    since there's no leaf to strip - Simple components only match other Simple.

    Example:
        "dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling"
        → "dx://taxonomy/System(General.v1)/Viability/Fidelity"

        "dx://taxonomy/Simple"
        → "dx://taxonomy/Simple" (full URI, Simple only matches Simple)
    """
    if not meaning:
        return None  # No meaning = matches everything

    # Remove trailing slash if present
    meaning = meaning.rstrip("/")

    # Simple meaning: return full URI (Simple only matches Simple)
    if meaning == SIMPLE_MEANING:
        return meaning

    # Use centralized parsing from StatementClassification
    domain, category, branch, _ = parse_meaning_uri(meaning)

    # If we successfully parsed the URI, reconstruct prefix (without leaf)
    if domain and category and branch:
        return f"dx://taxonomy/System({domain}.v1)/{category}/{branch}"

    # If we have category and branch but no domain, still construct prefix
    if category and branch:
        return f"dx://taxonomy/{category}/{branch}"

    # Fallback: strip last segment manually
    last_slash = meaning.rfind("/")
    if last_slash <= 0:
        return None  # Malformed URI, treat as matching everything

    return meaning[:last_slash]


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


class IdeaMatchDto(BaseModel):
    """Result of checking a raw idea against vocabulary."""

    is_duplicate: bool = Field(
        description="Is the idea semantically equivalent to an existing component?"
    )
    matched_hash: Optional[str] = Field(
        default=None,
        description="If duplicate, hash of the matching component (null if not duplicate)",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Confidence in the match (0.0-1.0)",
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

    # Maps extracted hash -> DB component that replaces it
    replacements: dict[str, Statement]
    # Components that were deleted (had DB equivalent)
    deleted_count: int
    # Original extracted components that were kept (no DB equivalent)
    originals: list[Statement]

    @property
    def components(self) -> list[Statement]:
        """All unique components: originals + unique replacements."""
        seen: set[str] = set()
        result: list[Statement] = []

        for comp in self.originals:
            if comp.hash not in seen:
                seen.add(comp.hash)
                result.append(comp)

        for comp in self.replacements.values():
            if comp.hash not in seen:
                seen.add(comp.hash)
                result.append(comp)

        return result


# --- Service ---


class StatementDeduplication(ReasonableConcern[DedupResult]):
    """
    Concern for semantic deduplication of components against vocabulary.

    Usage:
        deduplicator = StatementDeduplication()
        result = await deduplicator.resolve(
            extracted_hashes=["abc123", "def456"],
            vocabulary=vocab_list,
            text="source context for deduplication",
        )
        # result.replacements: {"abc123": <Statement>}  # DB equivalent
        # result.deleted_count: 1
        # result.originals: [<Statement>]  # kept extractions
        # deduplicator.report contains effects
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        extracted_hashes: list[str],
        vocabulary: list[dict],
        text: str = "",
    ) -> DedupResult:
        """
        Find and apply semantic deduplication.

        Args:
            extracted_hashes: Hashes of newly extracted components
            vocabulary: Existing vocabulary as list of dicts with keys:
                        hash, statement, meaning, rejected, rationale
            text: Source context for contextualized deduplication

        Returns:
            DedupResult with replacements, deleted_count, and kept_hashes
        """
        self._text = text

        if not extracted_hashes or not vocabulary:
            self._report.ok = True
            self._report.summary = "No deduplication needed"
            # Resolve all extracted to components (they're all kept)
            originals = [
                comp
                for h in extracted_hashes
                if (comp := self._resolve_component(h)) is not None
            ]
            return DedupResult(
                replacements={},
                deleted_count=0,
                originals=originals,
            )

        # CRITICAL: Filter out extracted hashes from vocabulary to prevent self-matching
        # The extracted components may have been committed to DB before this call,
        # making them appear in vocabulary. Matching a component to itself is wrong.
        extracted_set = set(extracted_hashes)
        filtered_vocabulary = [
            v for v in vocabulary if v.get("hash") not in extracted_set
        ]

        if not filtered_vocabulary:
            self._report.ok = True
            self._report.summary = (
                "No vocabulary to compare against (after excluding extracted)"
            )
            originals = [
                comp
                for h in extracted_hashes
                if (comp := self._resolve_component(h)) is not None
            ]
            return DedupResult(
                replacements={},
                deleted_count=0,
                originals=originals,
            )

        # Get semantic matches from LLM
        dedup_dto = await self._find_semantic_matches(
            extracted_hashes, filtered_vocabulary
        )

        # Apply matches: delete duplicates, track replacements
        result = self._apply_matches(extracted_hashes, dedup_dto)

        # Fill out report summary
        self._report.ok = True
        self._report.summary = (
            f"Deduplication complete: {result.deleted_count} duplicate(s) removed, "
            f"{len(result.originals)} kept"
        )

        return result

    async def _find_semantic_matches(
        self,
        extracted_hashes: list[str],
        vocabulary: list[dict],
    ) -> SemanticDedupDto:
        """Call LLM to find semantic equivalents."""
        # Build extraction descriptions and collect meaning prefixes
        extraction_lines = []
        extracted_prefixes: set[Optional[str]] = set()
        for h in extracted_hashes:
            comp = self._resolve_component(h)
            if comp and comp.is_committed:
                extraction_lines.append(
                    f"[{comp.short_hash}] {comp.prompt_text} (meaning: {comp.meaning or 'none'})"
                )
                extracted_prefixes.add(_extract_meaning_prefix(comp.meaning))

        # Filter vocabulary by meaning prefix
        # None prefix (no meaning) matches everything
        non_rejected = [v for v in vocabulary if not v.get("rejected")]
        if extracted_prefixes and None not in extracted_prefixes:
            # All extracted have meaning - filter vocab to matching prefixes
            # Include vocab items with no meaning (match everything) or matching prefix
            non_rejected = [
                v
                for v in non_rejected
                if _extract_meaning_prefix(v.get("meaning"))
                is None  # No meaning = matches all
                or _extract_meaning_prefix(v.get("meaning")) in extracted_prefixes
            ]

        # Build vocabulary descriptions (limit tokens)
        vocab_lines = []
        for v in non_rejected[:100]:
            rationale_hint = (
                f" - {v['rationale'][:80]}..." if v.get("rationale") else ""
            )
            vocab_lines.append(
                f"[{v['hash'][:7]}] {v['statement']} (meaning: {v.get('meaning', 'none')}){rationale_hint}"
            )

        if not extraction_lines or not vocab_lines:
            return SemanticDedupDto(matches=[])

        context_section = ""
        if self._text:
            context_section = f"""
**Source Context:**
{self._text}

"""

        prompt = f"""Compare these newly extracted statements against existing vocabulary.
Find semantic equivalents (same concept, possibly different wording).
{context_section}
**Newly Extracted Statements:**
{chr(10).join(extraction_lines)}

**Existing Vocabulary:**
{chr(10).join(vocab_lines)}

For each extraction, determine if there's a semantically equivalent
statement in the existing vocabulary. Consider same core concept (even if worded differently).
Use the source context to understand the intended meaning of extracted statements.

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
        replacements: dict[str, Statement] = {}
        originals: list[Statement] = []
        deleted_count = 0
        repo = StatementRepository()

        for ext_hash in extracted_hashes:
            # Find match for this extraction
            match = self._find_match(ext_hash, dedup_dto.matches)

            if match and match.db_hash and match.confidence >= 0.7:
                # Resolve replacement FIRST - only delete if replacement exists
                db_comp = self._resolve_component(match.db_hash)
                if db_comp:
                    # Has valid replacement - safe to delete extraction
                    ext_comp = self._resolve_component(ext_hash)
                    if ext_comp and repo.safe_delete(ext_comp):
                        deleted_count += 1
                        self._report.node_deleted(
                            ext_comp, meta={"replaced_by": match.db_hash}
                        )
                    replacements[ext_hash] = db_comp
                else:
                    # Replacement not found (LLM hallucinated hash?) - keep original
                    ext_comp = self._resolve_component(ext_hash)
                    if ext_comp:
                        originals.append(ext_comp)
            else:
                # No equivalent - keep extraction
                ext_comp = self._resolve_component(ext_hash)
                if ext_comp:
                    originals.append(ext_comp)

        return DedupResult(
            replacements=replacements,
            deleted_count=deleted_count,
            originals=originals,
        )

    def _find_match(
        self, ext_hash: str, matches: list[SemanticMatchDto]
    ) -> Optional[SemanticMatchDto]:
        """Find matching SemanticMatchDto for an extracted hash."""
        for m in matches:
            if ext_hash.startswith(m.extraction_hash) or m.extraction_hash.startswith(
                ext_hash
            ):
                return m
        return None

    def _resolve_component(self, hash: str) -> Optional[Statement]:
        """Resolve hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash)
            if isinstance(comp, Statement):
                return comp
        except ValueError:
            pass
        return None

    async def check_idea(
        self,
        idea: str,
        vocabulary: list[dict],
        text: str = "",
    ) -> Optional[Statement]:
        """
        Check if a raw idea string is a semantic duplicate of existing vocabulary.

        Unlike execute(), this works with raw strings (no committed component needed)
        and does NOT filter by meaning - it checks against ALL vocabulary.

        Args:
            idea: The raw idea string to check
            vocabulary: Existing vocabulary as list of dicts with keys:
                        hash, statement, meaning, rejected, rationale
            text: Source context for contextualized matching

        Returns:
            The matching Statement if duplicate found, None otherwise
        """
        if not idea or not idea.strip() or not vocabulary:
            return None

        idea = idea.strip()

        # Build vocabulary descriptions (no meaning filtering - check ALL)
        non_rejected = [v for v in vocabulary if not v.get("rejected")]
        vocab_lines = []
        for v in non_rejected[:100]:  # Limit for token budget
            meaning_hint = (
                f" (meaning: {v.get('meaning', 'none')})" if v.get("meaning") else ""
            )
            vocab_lines.append(f"[{v['hash']}] {v['statement']}{meaning_hint}")

        if not vocab_lines:
            return None

        context_section = ""
        if text:
            context_section = f"""
**Source Context:**
{text}

"""

        prompt = f"""Check if this idea is semantically equivalent to any existing component.
{context_section}
**Idea:** "{idea}"

**Existing vocabulary:**
{chr(10).join(vocab_lines)}

Determine if "{idea}" means the same thing as any existing component.
Consider the same core concept even if worded differently.

Only mark as duplicate if confidence >= 0.8 (clearly the same concept).
If not a duplicate, set is_duplicate=false and matched_hash=null."""

        result = await self._conversation.submit(
            response_model=IdeaMatchDto,
            user_content=prompt,
        )

        if result.is_duplicate and result.matched_hash and result.confidence >= 0.8:
            return self._resolve_component(result.matched_hash)

        return None
