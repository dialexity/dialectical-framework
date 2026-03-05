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
from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository

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


class PolarityFindingAgent(BaseTool, ExecutableCapability[Optional[Ideas]]):
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

    async def execute(self) -> Optional[Ideas]:
        """Execute polarity finding: orchestrate AntithesisExtraction for each thesis. Returns Ideas container."""
        # Reset report on each execution (allows instance reuse)
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Initialize conversation with system prompt
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        if not self.thesis_hashes:
            self._report.ok = True
            self._report.summary = "No thesis hashes provided"
            self._report.artifacts["antithesis_hashes"] = []
            self._report.artifacts["total_antitheses"] = 0
            return None

        # Get input text for context
        input_text = await self._get_input_text()

        # Get existing vocabulary to avoid and for dedup comparison
        vocab = self._get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        results: list[ThesisResult] = []
        all_existing: list[DialecticalComponent] = []  # Track existing oppositions
        newly_extracted: list[DialecticalComponent] = []  # Track newly extracted (for dedup)

        # Phase 1: For each thesis, collect existing oppositions + extract new ones
        for thesis_hash in self.thesis_hashes:
            thesis = self._resolve_component(thesis_hash)
            if thesis is None:
                result = ThesisResult(thesis=DialecticalComponent(statement=""))
                result.error = f"Thesis with hash '{thesis_hash}' not found"
                results.append(result)
                continue

            result = ThesisResult(thesis=thesis)

            # 1a. Collect existing oppositions from database (no dedup needed)
            existing_antitheses, existing_data = await self._get_existing_oppositions(thesis, input_text)
            result.antithesis_data.extend(existing_data)
            all_existing.extend(existing_antitheses)

            # Add existing to not_like_these to avoid re-extraction
            for comp in existing_antitheses:
                if comp.statement not in not_like_these:
                    not_like_these.append(comp.statement)

            # 1b. Extract new antitheses (with retry if none found)
            antitheses, antithesis_data, extraction_reports = await self._extract_with_retry(
                thesis=thesis,
                text=input_text,
                not_like_these=not_like_these,
            )
            for r in extraction_reports:
                self._report = self._report.merge(r)

            result.antithesis_data.extend(antithesis_data)
            newly_extracted.extend(antitheses)

            # Track extracted for not_like_these
            for comp in antitheses:
                if comp.statement not in not_like_these:
                    not_like_these.append(comp.statement)

            results.append(result)

        # Phase 2: Semantic deduplication (only newly extracted, not existing)
        existing_hashes = [c.hash for c in all_existing]
        newly_extracted_hashes = [c.hash for c in newly_extracted]
        if newly_extracted_hashes and vocab:
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.execute(
                extracted_hashes=newly_extracted_hashes,
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

        # Phase 3: Create ONE Ideas with all theses and their antitheses
        total_antitheses = sum(len(r.antithesis_data) for r in results if not r.error)

        if total_antitheses == 0:
            self._report.ok = True
            self._report.summary = "No antitheses found"
            self._report.artifacts["thesis_hashes"] = self.thesis_hashes
            self._report.artifacts["existing_antitheses_hashes"] = []
            self._report.artifacts["new_antitheses_hashes"] = []
            self._report.artifacts["total_antitheses"] = 0
            return None

        # Create Ideas containing all theses + antitheses (OPPOSITE_OF already exists)
        ideas = self._create_ideas(results)

        # Build final artifacts
        self._report.artifacts["thesis_hashes"] = self.thesis_hashes
        self._report.artifacts["existing_antitheses_hashes"] = existing_hashes
        self._report.artifacts["new_antitheses_hashes"] = newly_extracted_hashes
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["total_antitheses"] = total_antitheses
        self._report.summary = f"Found {len(existing_hashes)} existing + generated {len(newly_extracted_hashes)} new antithesis(es) for {len(self.thesis_hashes)} thesis(es)"

        return ideas

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

    async def _get_existing_oppositions(
        self, thesis: DialecticalComponent, text: str = ""
    ) -> tuple[list[DialecticalComponent], list[dict]]:
        """Get existing oppositions for a thesis from the database.

        For each antithesis:
        1. Look up HS from WisdomUnit's ARelationship where T=thesis AND A=antithesis
        2. Otherwise estimate using AntithesisClassification

        Returns:
            Tuple of (antithesis components, antithesis data dicts)
        """
        from dialectical_framework.agents.brainstorming.capabilities.antithesis_classification import (
            AntithesisClassification,
        )

        existing_components: list[DialecticalComponent] = []
        existing_data: list[dict] = []
        wu_repo = WisdomUnitRepository()

        for antithesis, _ in thesis.oppositions.all():
            existing_components.append(antithesis)

            # Try to find HS from WisdomUnit where T=thesis AND A=antithesis
            hs = self._lookup_hs_from_wisdom_unit(thesis, antithesis, wu_repo)

            if hs is None:
                # No WisdomUnit found for this T-A pair - estimate using AntithesisClassification
                classifier = AntithesisClassification()
                result = await classifier.execute(
                    thesis=thesis,
                    antithesis_statement=antithesis.statement,
                    text=text,
                )
                hs = result.heuristic_similarity
                self._report.artifacts.setdefault("estimated_hs_count", 0)
                self._report.artifacts["estimated_hs_count"] += 1

            existing_data.append({
                "hash": antithesis.hash,
                "heuristic_similarity": hs,
                "existing": True,
            })

        if existing_components:
            self._report.artifacts["existing_oppositions_count"] = len(existing_components)

        return existing_components, existing_data

    def _lookup_hs_from_wisdom_unit(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        wu_repo: WisdomUnitRepository
    ) -> Optional[float]:
        """Look up heuristic_similarity from WisdomUnit where T=thesis AND A=antithesis."""
        from dialectical_framework.graph.relationships.polarity_relationship import ARelationship

        # Find WisdomUnits where T=thesis AND A=antithesis
        wus = wu_repo.find_by_polarity(thesis, antithesis)

        for wu in wus:
            # Get the A relationship to access heuristic_similarity
            a_result = wu.a.get()
            if a_result:
                _, a_rel = a_result
                if isinstance(a_rel, ARelationship) and a_rel.heuristic_similarity is not None:
                    return a_rel.heuristic_similarity

        return None

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

    def _create_ideas(self, results: list[ThesisResult]) -> Optional[Ideas]:
        """Create Ideas node with all theses and their antitheses. Records effects in self._report."""
        # Collect all valid theses and antithesis data
        valid_results = [r for r in results if not r.error and r.antithesis_data]
        if not valid_results:
            return None

        # Build intent summary
        thesis_statements = [r.thesis.statement for r in valid_results]
        intent = f"Polarities for: {', '.join(thesis_statements[:3])}"
        if len(thesis_statements) > 3:
            intent += f" (+{len(thesis_statements) - 3} more)"

        ideas = Ideas(intent=intent)
        ideas.save()

        # Connect to all inputs in scope
        input_repo = InputRepository()
        for inp in input_repo.get_all():
            ideas.inputs.connect(inp)

        # Connect all theses AND their antitheses
        for result in valid_results:
            # Connect thesis
            ideas.statements.connect(result.thesis)

            # Connect antitheses (OPPOSITE_OF relationship already exists from extraction)
            for data in result.antithesis_data:
                comp = self._resolve_component(data["hash"])
                if comp:
                    ideas.statements.connect(comp)

        ideas.commit()
        self._report.node_created(ideas)

        # Attach Rationale summarizing the generation
        total_theses = len(valid_results)
        total_antitheses = sum(len(r.antithesis_data) for r in valid_results)
        all_hs = [d["heuristic_similarity"] for r in valid_results for d in r.antithesis_data]
        max_hs = max(all_hs) if all_hs else 0.0

        rationale = Rationale(
            text=f"Generated {total_antitheses} antitheses for {total_theses} theses. Max Heuristic Similarity: {max_hs:.2f}"
        )
        rationale.set_explanation_target(ideas)
        rationale.commit()
        self._report.node_created(rationale)
        self._report.relationship_created(
            rationale.explains, rationale, ideas,
        )

        return ideas

