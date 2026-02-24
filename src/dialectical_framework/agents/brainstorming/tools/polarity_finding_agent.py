"""
PolarityFindingAgent: Orchestrator for Phase 2 of polarity-finder.

Symmetric to AnchoringAgent:
- AnchoringAgent (orchestrator) calls ExtractTheses (work tool) → Ideas (all T)
- PolarityFindingAgent (orchestrator) calls ExtractAntitheses (work tool) → Ideas (per T, all A)

Flow:
    AnchoringAgent → Theses (Ideas with all T)
           ↓
    PolarityFindingAgent → For each thesis, call ExtractAntitheses
           ↓
    One Ideas per T (containing all A for that T)
           ↓
    BrainstormingAgent → Reviews T/A pairs, rejects low HS
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool, Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse
from pydantic import BaseModel, Field

from dialectical_framework.agents.brainstorming.tools.extract_antitheses import (
    ExtractAntitheses,
)
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- DTOs for semantic deduplication ---


class SemanticMatchDto(BaseModel):
    """A single semantic match between extraction and DB component."""

    extraction_hash: str = Field(description="Hash prefix of the extracted component")
    db_hash: Optional[str] = Field(
        default=None,
        description="Hash prefix of semantically equivalent DB component, or null if no match",
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


# --- Result container for tracking ---


class ThesisResult:
    """Container for tracking results per thesis."""

    def __init__(self, thesis: DialecticalComponent):
        self.thesis = thesis
        self.antithesis_data: list[dict] = []  # [{hash, hs}, ...]
        self.ideas: Optional[Ideas] = None
        self.error: Optional[str] = None


# --- Main Orchestrator ---


class PolarityFindingAgent(BaseTool, HasBrain, SettingsAware):
    """
    Orchestrate antithesis generation (Phase 2 of polarity-finder).

    For each thesis hash:
    1. Call ExtractAntitheses (the work tool) to generate antitheses
    2. Parse results to get antithesis hashes + HS values
    3. Create Ideas node per thesis with its antitheses
    4. Return summary report for BrainstormingAgent curation

    This is symmetric to AnchoringAgent which orchestrates Phase 1.
    """

    thesis_hashes: list[str] = Field(
        description="Hash prefixes of theses to generate antitheses for"
    )

    async def call(self) -> str:
        """Execute polarity finding: orchestrate ExtractAntitheses for each thesis."""
        if not self.thesis_hashes:
            return "No thesis hashes provided"

        # Get input text for context
        input_text = await self._get_input_text()

        # Get existing vocabulary to avoid and for dedup comparison
        vocab = self._get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        results: list[ThesisResult] = []
        all_extracted_hashes: list[str] = []  # Track all extracted for dedup

        # Phase 1: Extract antitheses for all theses (with retry if none found)
        for thesis_hash in self.thesis_hashes:
            thesis = self._resolve_thesis(thesis_hash)
            if thesis is None:
                result = ThesisResult(thesis=DialecticalComponent(statement=""))
                result.error = f"Thesis with hash '{thesis_hash}' not found"
                results.append(result)
                continue

            result = ThesisResult(thesis=thesis)

            # Try extraction with not_like_these, retry with empty if no results
            antithesis_data = await self._extract_with_retry(
                thesis_hash=thesis_hash,
                text=input_text,
                not_like_these=not_like_these,
            )

            if isinstance(antithesis_data, str):  # Error string
                result.error = antithesis_data
                results.append(result)
                continue

            result.antithesis_data = antithesis_data

            # Track extracted hashes for dedup
            for data in antithesis_data:
                all_extracted_hashes.append(data["hash"])
                comp = self._resolve_component(data["hash"])
                if comp and comp.statement not in not_like_these:
                    not_like_these.append(comp.statement)

            results.append(result)

        # Phase 2: Semantic deduplication against existing vocabulary
        deleted_count = 0
        if all_extracted_hashes and vocab:
            dedup_result = await self._semantic_dedup(all_extracted_hashes, vocab)
            hash_replacements, deleted_count = self._apply_dedup(
                all_extracted_hashes, dedup_result, results
            )

            # Update results with deduped hashes
            for result in results:
                if result.error:
                    continue
                for data in result.antithesis_data:
                    if data["hash"] in hash_replacements:
                        data["hash"] = hash_replacements[data["hash"]]
                        data["deduped"] = True

        # Phase 3: Create Ideas for each thesis with deduped components
        for result in results:
            if result.error or not result.antithesis_data:
                continue
            ideas = self._create_ideas_for_thesis(result.thesis, result.antithesis_data)
            result.ideas = ideas

        return self._build_report(results, deleted_count)

    # --- Extraction with Retry ---

    async def _extract_with_retry(
        self,
        thesis_hash: str,
        text: str,
        not_like_these: list[str],
    ) -> list[dict] | str:
        """
        Extract antitheses with retry logic.

        Goal: Find at least 1 antithesis per thesis.
        If first attempt with not_like_these yields nothing, retry with empty constraints.

        Returns list of antithesis data dicts, or error string.
        """
        # First attempt: with not_like_these constraints
        extract_tool = ExtractAntitheses(
            thesis_hash=thesis_hash,
            text=text,
            not_like_these=not_like_these,
        )
        tool_result = await extract_tool.call()

        if tool_result.startswith("ERROR:"):
            return tool_result

        antithesis_data = self._parse_antithesis_data(tool_result)

        # If we got results, return them
        if antithesis_data:
            return antithesis_data

        # Retry with empty not_like_these (relax constraints)
        extract_tool_retry = ExtractAntitheses(
            thesis_hash=thesis_hash,
            text=text,
            not_like_these=[],  # Empty - no constraints
        )
        tool_result_retry = await extract_tool_retry.call()

        if tool_result_retry.startswith("ERROR:"):
            return tool_result_retry

        return self._parse_antithesis_data(tool_result_retry)

    # --- Helpers ---

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get concatenated text from all inputs in scope."""
        repo = InputRepository()
        inputs = repo.get_all()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)

    def _get_vocabulary_with_rationales(self) -> list[dict]:
        """Get vocabulary components with their rationales."""
        repo = DialecticalComponentRepository()
        vocab = list(repo.get_vocabulary())

        result = []
        for comp in vocab:
            # Get rationale if exists
            rationale_text = ""
            for rat, _ in comp.rationales.all():
                rationale_text = rat.text
                break  # Just use first rationale

            result.append({
                "hash": comp.hash or "",
                "statement": comp.statement,
                "meaning": comp.meaning,
                "rejected": comp.rejected,
                "rationale": rationale_text,
            })

        return result

    # --- Semantic Deduplication ---

    @prompt_template(
        """
        USER:
        Compare these newly extracted antitheses against existing vocabulary.
        Find semantic equivalents (same concept, possibly different wording).

        **Newly Extracted Antitheses:**
        {extractions}

        **Existing Vocabulary:**
        {vocabulary}

        For each extraction, determine if there's a semantically equivalent
        component in the existing vocabulary. Consider same core concept (even if worded differently).

        Only match if confidence >= 0.7 (clearly the same concept).
        If no match, set db_hash to null.
        """
    )
    def _semantic_dedup_prompt(
        self, extractions: str, vocabulary: str
    ) -> Messages.Type:
        return {
            "computed_fields": {
                "extractions": extractions,
                "vocabulary": vocabulary,
            }
        }

    async def _semantic_dedup(
        self,
        extracted_hashes: list[str],
        vocab: list[dict],
    ) -> SemanticDedupDto:
        """Batch LLM call to find semantic equivalents."""
        # Build extraction descriptions
        extraction_lines = []
        for h in extracted_hashes:
            comp = self._resolve_component(h)
            if comp:
                extraction_lines.append(
                    f"[{comp.short_hash}] {comp.statement} (meaning: {comp.meaning or 'none'})"
                )

        # Build vocabulary descriptions (exclude rejected, limit to avoid token explosion)
        vocab_lines = []
        non_rejected = [v for v in vocab if not v.get("rejected")]
        for v in non_rejected[:100]:
            rationale_hint = f" - {v['rationale'][:80]}..." if v.get("rationale") else ""
            vocab_lines.append(
                f"[{v['hash'][:7]}] {v['statement']} (meaning: {v.get('meaning', 'none')}){rationale_hint}"
            )

        if not extraction_lines or not vocab_lines:
            return SemanticDedupDto(matches=[])

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=SemanticDedupDto)
        async def _dedup():
            return self._semantic_dedup_prompt(
                extractions="\n".join(extraction_lines),
                vocabulary="\n".join(vocab_lines),
            )

        return await _dedup()

    def _apply_dedup(
        self,
        extracted_hashes: list[str],
        dedup_result: SemanticDedupDto,
        results: list[ThesisResult],
    ) -> tuple[dict[str, str], int]:
        """
        Apply dedup results: delete redundant extractions, keep DB versions.

        Also reconnects OPPOSITE_OF relationship from thesis to DB version.

        Returns (hash_replacements, deleted_count) where hash_replacements maps
        old extracted hash -> new DB hash for components that were replaced.
        """
        hash_replacements: dict[str, str] = {}
        deleted_count = 0
        repo = DialecticalComponentRepository()

        # Build mapping: extracted_hash -> thesis (for reconnecting OPPOSITE_OF)
        hash_to_thesis: dict[str, DialecticalComponent] = {}
        for result in results:
            if result.error:
                continue
            for data in result.antithesis_data:
                hash_to_thesis[data["hash"]] = result.thesis

        for ext_hash in extracted_hashes:
            # Find match for this extraction
            match = None
            for m in dedup_result.matches:
                if ext_hash.startswith(m.extraction_hash) or m.extraction_hash.startswith(ext_hash):
                    match = m
                    break

            if match and match.db_hash and match.confidence >= 0.7:
                # Has equivalent in DB - delete extraction, use DB version
                ext_comp = self._resolve_component(ext_hash)
                if ext_comp:
                    if repo.safe_delete(ext_comp):
                        deleted_count += 1

                # Reconnect OPPOSITE_OF: thesis -> DB version
                thesis = hash_to_thesis.get(ext_hash)
                db_comp = self._resolve_component(match.db_hash)
                if thesis and db_comp:
                    thesis.oppositions.connect(db_comp)

                # Record replacement
                hash_replacements[ext_hash] = match.db_hash

        return hash_replacements, deleted_count

    def _resolve_thesis(self, hash_prefix: str) -> Optional[DialecticalComponent]:
        """Resolve hash prefix to thesis component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash_prefix)
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None

    def _resolve_component(self, hash_prefix: str) -> Optional[DialecticalComponent]:
        """Resolve hash prefix to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash_prefix)
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None

    def _parse_antithesis_data(self, result: str) -> list[dict]:
        """
        Parse antithesis hashes and HS values from ExtractAntitheses result.

        Looks for the machine-readable section:
        **Antithesis hashes:**
        hash1:HS=0.85, hash2:HS=0.72, ...
        """
        data: list[dict] = []

        # Look for "Antithesis hashes:" section
        match = re.search(r"\*\*Antithesis hashes:\*\*\s*\n(.+)", result, re.IGNORECASE)
        if not match:
            return data

        hash_line = match.group(1).strip()

        # Parse "hash:HS=0.XX" entries
        for entry in hash_line.split(","):
            entry = entry.strip()
            if ":HS=" in entry:
                parts = entry.split(":HS=")
                if len(parts) == 2:
                    hash_val = parts[0].strip()
                    try:
                        hs_val = float(parts[1].strip())
                    except ValueError:
                        hs_val = 0.5
                    data.append({"hash": hash_val, "hs": hs_val})

        return data

    def _create_ideas_for_thesis(
        self,
        thesis: DialecticalComponent,
        antithesis_data: list[dict],
    ) -> Optional[Ideas]:
        """Create Ideas node for a thesis with its antitheses."""
        if not antithesis_data:
            return None

        ideas = Ideas(intent=f'Antitheses for thesis "{thesis.statement}", thesis hash: {thesis.hash}')
        ideas.save()

        # Connect to all inputs in scope
        input_repo = InputRepository()
        for inp in input_repo.get_all():
            ideas.inputs.connect(inp)

        # Connect all antitheses
        for data in antithesis_data:
            comp = self._resolve_component(data["hash"])
            if comp:
                ideas.statements.connect(comp)

        ideas.commit()

        # Attach Rationale summarizing the generation
        hs_values = [d["hs"] for d in antithesis_data]
        max_hs = max(hs_values) if hs_values else 0.0
        rationale = Rationale(
            text=f"Generated {len(antithesis_data)} antitheses for thesis '{thesis.statement}'. Max HS: {max_hs:.2f}"
        )
        rationale.set_explanation_target(ideas)
        rationale.commit()

        return ideas

    def _build_report(self, results: list[ThesisResult], deleted_count: int = 0) -> str:
        """Build the result report."""
        lines = ["**Polarity Finding Complete**", ""]

        if deleted_count > 0:
            lines.append(f"**Deduplicated:** {deleted_count} (preferred existing DB versions)")
            lines.append("")

        total_antitheses = 0
        ideas_list: list[Ideas] = []

        for r in results:
            if r.error:
                lines.append(f"**[ERROR]** {r.error}")
                continue

            thesis = r.thesis
            is_simple = "SIMPLE" if thesis.is_simple else "COMPLEX"
            antitheses = r.antithesis_data

            lines.append(f"**[{thesis.short_hash}] {thesis.statement}** ({is_simple})")

            if r.ideas:
                lines.append(f"  Ideas: {r.ideas.short_hash}")
                ideas_list.append(r.ideas)

            if antitheses:
                lines.append(f"  Antitheses ({len(antitheses)}):")
                for a in antitheses:
                    comp = self._resolve_component(a["hash"])
                    stmt = comp.statement if comp else "?"
                    lines.append(f"    [{a['hash']}] {stmt} (HS={a['hs']:.2f})")
                total_antitheses += len(antitheses)
            else:
                lines.append("  Antitheses: None generated")

            lines.append("")

        lines.append(
            f"**Total:** {len(results)} theses processed, {total_antitheses} antitheses generated"
        )
        lines.append(f"**Ideas nodes:** {len(ideas_list)}")

        return "\n".join(lines)
