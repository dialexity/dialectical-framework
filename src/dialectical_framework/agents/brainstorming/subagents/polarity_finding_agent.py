"""
PolarityFindingAgent: Orchestrator for Phase 2 of polarity-finder.

Uses conversational pattern: all steps share context through conversation history,
enabling prompt caching.

Symmetric to AnchoringAgent:
- AnchoringAgent (orchestrator) uses ThesisExtraction → Ideas (all T)
- PolarityFindingAgent (orchestrator) uses AntithesisExtraction → Ideas (per T, all A)

Flow:
    AnchoringAgent → Theses (Ideas with all T)
           ↓
    PolarityFindingAgent → For each thesis, extract antitheses
           ↓
    One Ideas per T (containing all A for that T)
           ↓
    BrainstormingAgent → Reviews T/A pairs, rejects low Heuristic Similarity
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from dialectical_framework.agents.brainstorming.capabilities.antithesis_extraction import (
    AntithesisExtraction,
)
from dialectical_framework.agents.brainstorming.capabilities.statement_deduplication import (
    DedupResult,
    StatementDeduplication,
)
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.node_repository import NodeRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- System Prompt ---

SYSTEM_PROMPT = """You are a polarity finding agent for dialectical brainstorming.

Your task is to orchestrate antithesis generation for theses and perform semantic deduplication.

For semantic deduplication:
- Compare newly extracted antitheses against existing vocabulary
- Only match if confidence >= 0.7 (clearly the same concept)
- Consider same core concept even if worded differently"""


# --- Result container for tracking ---


class ThesisResult:
    """Container for tracking results per thesis."""

    def __init__(self, thesis: DialecticalComponent):
        self.thesis = thesis
        self.antithesis_data: list[dict] = []  # [{hash, heuristic_similarity}, ...]
        self.ideas: Optional[Ideas] = None
        self.error: Optional[str] = None


# --- Main Orchestrator ---


class PolarityFindingAgent(BaseTool):
    """
    Orchestrate antithesis generation (Phase 2 of polarity-finder).

    Uses conversational pattern where all steps share context through
    conversation history, enabling prompt caching.

    For each thesis hash:
    1. Use AntithesisExtraction to generate antitheses
    2. Get antithesis hashes + Heuristic Similarity values from report
    3. Create Ideas node per thesis with its antitheses
    4. Return summary report for BrainstormingAgent curation

    This is symmetric to AnchoringAgent which orchestrates Phase 1.
    """

    thesis_hashes: list[str] = Field(
        description="Hashes of theses to generate antitheses for"
    )

    _conversation: ConversationFacilitator = PrivateAttr(default_factory=ConversationFacilitator)

    async def call(self) -> str:
        """Execute polarity finding: orchestrate AntithesisExtraction for each thesis."""
        # Initialize conversation with system prompt
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

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
            thesis = self._resolve_component(thesis_hash)
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
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.deduplicate(
                extracted_hashes=all_extracted_hashes,
                vocabulary=vocab,
            )
            deleted_count = dedup_result.deleted_count

            # Reconnect OPPOSITE_OF: thesis -> DB version for replacements
            self._reconnect_oppositions(results, dedup_result)

            # Update results with deduped hashes
            for result in results:
                if result.error:
                    continue
                for data in result.antithesis_data:
                    if data["hash"] in dedup_result.replacements:
                        data["hash"] = dedup_result.replacements[data["hash"]]
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
        # Resolve thesis first
        thesis = self._resolve_component(thesis_hash)
        if thesis is None:
            return f"ERROR: Thesis with hash '{thesis_hash}' not found"

        # First attempt: with not_like_these constraints
        service = AntithesisExtraction()
        report = await service.extract(
            thesis=thesis,
            text=text,
            not_like_these=not_like_these,
        )

        antithesis_data = self._extract_data_from_report(report)

        # If we got results, return them
        if antithesis_data:
            return antithesis_data

        # Retry with empty not_like_these (relax constraints)
        service_retry = AntithesisExtraction()
        report_retry = await service_retry.extract(
            thesis=thesis,
            text=text,
            not_like_these=[],
        )

        return self._extract_data_from_report(report_retry)

    def _extract_data_from_report(self, report) -> list[dict]:
        """Extract antithesis data from RunReport artifacts."""
        antithesis_hashes = report.artifacts.get("antithesis_hashes", [])
        hs_by_hash = report.artifacts.get("heuristic_similarity_by_hash", {})

        return [
            {"hash": h, "heuristic_similarity": hs_by_hash.get(h, 0.5)}
            for h in antithesis_hashes
        ]

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

    # --- Deduplication Helpers ---

    def _reconnect_oppositions(
        self,
        results: list[ThesisResult],
        dedup_result: DedupResult,
    ) -> None:
        """Reconnect OPPOSITE_OF relationships from thesis to DB version for replacements."""
        # Build mapping: extracted_hash -> thesis
        hash_to_thesis: dict[str, DialecticalComponent] = {}
        for result in results:
            if result.error:
                continue
            for data in result.antithesis_data:
                hash_to_thesis[data["hash"]] = result.thesis

        # Connect thesis to DB version for each replacement
        for ext_hash, db_hash in dedup_result.replacements.items():
            thesis = hash_to_thesis.get(ext_hash)
            db_comp = self._resolve_component(db_hash)
            if thesis and db_comp:
                thesis.oppositions.connect(db_comp)

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
        hs_values = [d["heuristic_similarity"] for d in antithesis_data]
        max_hs = max(hs_values) if hs_values else 0.0
        rationale = Rationale(
            text=f"Generated {len(antithesis_data)} antitheses for thesis '{thesis.statement}'. Max Heuristic Similarity: {max_hs:.2f}"
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
                    lines.append(f"    [{a['hash']}] {stmt} (Heuristic Similarity={a['heuristic_similarity']:.2f})")
                total_antitheses += len(antitheses)
            else:
                lines.append("  Antitheses: None generated")

            lines.append("")

        lines.append(
            f"**Total:** {len(results)} theses processed, {total_antitheses} antitheses generated"
        )
        lines.append(f"**Ideas nodes:** {len(ideas_list)}")

        return "\n".join(lines)
