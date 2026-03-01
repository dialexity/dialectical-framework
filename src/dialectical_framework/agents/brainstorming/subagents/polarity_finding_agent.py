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

Usage:
    # Programmatic (web app)
    agent = PolarityFindingAgent(thesis_hashes=["abc123", "def456"])
    antitheses = await agent.execute()
    for a in antitheses:
        print(a.statement)

    # LLM tool use (returns JSON)
    agent = PolarityFindingAgent(thesis_hashes=[...])
    json_result = await agent.call()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from dialectical_framework.agents.brainstorming.capabilities.antithesis_extraction import (
    AntithesisExtraction,
)
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.brainstorming.capabilities.statement_deduplication import (
    DedupResult,
    StatementDeduplication,
)
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
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


class PolarityFindingAgent(BaseTool, ExecutableCapability[list[DialecticalComponent]]):
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

    Dual interface:
    - execute() returns list[DialecticalComponent] for programmatic use
    - call() returns JSON string for LLM tool use
    """

    thesis_hashes: list[str] = Field(
        description="Hashes of theses to generate antitheses for"
    )

    _conversation: ConversationFacilitator = PrivateAttr(default_factory=ConversationFacilitator)
    _report: ExecutionReport = PrivateAttr()

    async def call(self) -> str:
        """Execute polarity finding and return ExecutionReport as JSON (for LLM tool use)."""
        await self.execute()
        return str(self._report)

    async def execute(self) -> list[DialecticalComponent]:
        """Execute polarity finding: orchestrate AntithesisExtraction for each thesis. Returns antitheses."""
        # Reset report on each execution (allows instance reuse)
        self._report = ExecutionReport(tool="polarity_finding_agent")

        # Initialize conversation with system prompt
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        if not self.thesis_hashes:
            self._report.ok = True
            self._report.summary = "No thesis hashes provided"
            self._report.artifacts["antithesis_hashes"] = []
            return []

        # Get input text for context
        input_text = await self._get_input_text()

        # Get existing vocabulary to avoid and for dedup comparison
        vocab = self._get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        results: list[ThesisResult] = []
        all_antitheses: list[DialecticalComponent] = []  # Track all extracted

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
            antitheses, antithesis_data, extraction_reports = await self._extract_with_retry(
                thesis=thesis,
                text=input_text,
                not_like_these=not_like_these,
            )
            for r in extraction_reports:
                self._report = self._report.merge(r)

            result.antithesis_data = antithesis_data
            all_antitheses.extend(antitheses)

            # Track extracted for not_like_these
            for comp in antitheses:
                if comp.statement not in not_like_these:
                    not_like_these.append(comp.statement)

            results.append(result)

        # Phase 2: Semantic deduplication against existing vocabulary
        deleted_count = 0
        all_extracted_hashes = [c.hash for c in all_antitheses]
        if all_extracted_hashes and vocab:
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.execute(
                extracted_hashes=all_extracted_hashes,
                vocabulary=vocab,
                text=input_text,
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
                        data["hash"] = dedup_result.replacements[data["hash"]].hash
                        data["deduped"] = True

        # Phase 3: Create Ideas for each thesis with deduped components
        ideas_hashes: list[str] = []
        for result in results:
            if result.error or not result.antithesis_data:
                continue
            ideas = self._create_ideas_for_thesis(result.thesis, result.antithesis_data)
            result.ideas = ideas
            if ideas:
                ideas_hashes.append(ideas.hash)

        # Build final artifacts
        total_antitheses = sum(len(r.antithesis_data) for r in results if not r.error)
        self._report.artifacts["thesis_hashes"] = self.thesis_hashes
        self._report.artifacts["antithesis_hashes"] = all_extracted_hashes
        self._report.artifacts["ideas_hashes"] = ideas_hashes
        self._report.artifacts["deleted_count"] = deleted_count
        self._report.artifacts["total_antitheses"] = total_antitheses
        self._report.summary = f"Generated {total_antitheses} antithesis(es) for {len(self.thesis_hashes)} thesis(es)"

        return all_antitheses

    # --- Extraction with Retry ---

    async def _extract_with_retry(
        self,
        thesis: DialecticalComponent,
        text: str,
        not_like_these: list[str],
    ) -> tuple[list[DialecticalComponent], list[dict], list[ExecutionReport]]:
        """
        Extract antitheses with retry logic.

        Goal: Find at least 1 antithesis per thesis.
        If first attempt with not_like_these yields nothing, retry with empty constraints.

        Returns tuple of (antithesis components, antithesis data dicts, reports).
        """
        from dialectical_framework.agents.brainstorming.capabilities.antithesis_extraction import (
            AntithesisProcessed,
        )

        reports: list[ExecutionReport] = []

        # First attempt: with not_like_these constraints
        service = AntithesisExtraction()
        results = await service.execute(
            thesis=thesis,
            text=text,
            not_like_these=not_like_these,
        )
        reports.append(service.report)

        # If we got results, return them
        if results:
            components = [r.component for r in results]
            antithesis_data = self._build_antithesis_data(results)
            return components, antithesis_data, reports

        # Retry with empty not_like_these (relax constraints)
        service_retry = AntithesisExtraction()
        results_retry = await service_retry.execute(
            thesis=thesis,
            text=text,
            not_like_these=[],
        )
        reports.append(service_retry.report)

        components = [r.component for r in results_retry]
        antithesis_data = self._build_antithesis_data(results_retry)
        return components, antithesis_data, reports

    def _build_antithesis_data(self, results: list) -> list[dict]:
        """Build antithesis data dicts directly from AntithesisResult objects."""
        return [
            {"hash": r.component.hash, "heuristic_similarity": r.heuristic_similarity}
            for r in results
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
        for ext_hash, db_comp in dedup_result.replacements.items():
            thesis = hash_to_thesis.get(ext_hash)
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
        """Create Ideas node for a thesis with its antitheses. Records effects in self._report."""
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
        self._report.node_created(ideas, meta={"thesis_hash": thesis.hash})

        # Attach Rationale summarizing the generation
        hs_values = [d["heuristic_similarity"] for d in antithesis_data]
        max_hs = max(hs_values) if hs_values else 0.0
        rationale = Rationale(
            text=f"Generated {len(antithesis_data)} antitheses for thesis '{thesis.statement}'. Max Heuristic Similarity: {max_hs:.2f}"
        )
        rationale.set_explanation_target(ideas)
        rationale.commit()
        self._report.node_created(rationale)
        self._report.relationship_created(
            rationale.explains, rationale, ideas,
        )

        return ideas

