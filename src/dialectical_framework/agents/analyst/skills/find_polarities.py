"""
FindPolarities: Orchestrator for creating Polarities (T-A pairs).

Extracts antitheses for theses and creates Polarity nodes (T-A pairs).
Returns Ideas containing all T and A components with HS metadata.

Flow:
    SurfaceTheses → Theses (Ideas with all T)
           ↓
    FindPolarities → Polarity nodes (T-A pairs with HS) + Ideas with all T and A
           ↓
    ExpandPolarities → Creates Perspectives from Polarities by adding aspects (T+, T-, A+, A-)

Usage:
    # Programmatic (web app)
    agent = FindPolarities(thesis_hashes=["abc123", "def456"])
    ideas = await agent.execute()

    # Access T-A pairs from Ideas
    for comp, _ in ideas.statements.all():
        for antithesis, _ in comp.oppositions.all():
            print(f"{comp.statement} vs {antithesis.statement}")

    # LLM tool use (returns JSON with HS data)
    agent = FindPolarities(thesis_hashes=[...])
    json_result = await agent.call()  # Includes antithesis_data with HS values
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.executable_capability import \
    ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.enums.di import DI
from dialectical_framework.features.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.features.statement_deduplication import (
    DedupResult, StatementDeduplication)
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.polarity import (POSITION_A, POSITION_T,
                                                        Polarity)
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.relationships.polarity_relationship import (
    ARelationship, TRelationship)
from dialectical_framework.graph.repositories.dialectical_component_repository import \
    DialecticalComponentRepository
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- Result container for tracking ---


class ThesisResult:
    """Container for tracking results per thesis."""

    def __init__(self, thesis: DialecticalComponent):
        self.thesis = thesis
        self.antithesis_data: list[dict] = []  # [{hash, heuristic_similarity}, ...]
        self.error: Optional[str] = None


# --- Main Orchestrator ---


class FindPolarities(BaseTool, ExecutableCapability[Optional[Ideas]]):
    """
    Orchestrate Polarity creation (T-A pairs).

    For each thesis hash:
    1. Use AntithesisExtraction to generate antitheses
    2. Create Polarity nodes (T-A pairs) with HS metadata
    3. Return Ideas containing all T and A components

    The HS (Heuristic Similarity) for each T-A pair is available in:
    - Report artifacts: polarity_data[{thesis_hash, antithesis_hash, heuristic_similarity}]
    - Polarity nodes: ARelationship.heuristic_similarity

    Dual interface:
    - execute() returns Ideas for programmatic use
    - call() returns JSON string for LLM tool use (includes HS data)
    """

    thesis_hashes: list[str] = Field(
        description="Hashes of theses to generate antitheses for"
    )

    _report: ExecutionReport = PrivateAttr()

    async def call(self) -> str:
        """Execute polarity creation and return ExecutionReport as JSON (for LLM tool use)."""
        await self.execute()
        return str(self._report)

    async def execute(self) -> Optional[Ideas]:
        """
        Execute polarity creation: extract antitheses and create Polarities + Ideas.

        Returns:
            Ideas containing all T and A components (with OPPOSITE_OF relationships)
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not self.thesis_hashes:
            self._report.ok = True
            self._report.summary = "No thesis hashes provided"
            self._report.artifacts["antithesis_data"] = []
            return None

        # Get input text for context
        input_text = await self._get_input_text()

        # Get existing vocabulary to avoid and for dedup comparison
        comp_repo = DialecticalComponentRepository()
        vocab = comp_repo.get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        results: list[ThesisResult] = []
        all_existing: list[DialecticalComponent] = []
        newly_extracted: list[DialecticalComponent] = []

        # Phase 1: For each thesis, collect existing oppositions + extract new ones
        for thesis_hash in self.thesis_hashes:
            thesis = self._resolve_component(thesis_hash)
            if thesis is None:
                result = ThesisResult(thesis=DialecticalComponent(statement=""))
                result.error = f"Thesis with hash '{thesis_hash}' not found"
                results.append(result)
                continue

            result = ThesisResult(thesis=thesis)

            # 1a. Collect existing oppositions from database
            existing_antitheses, existing_data = await self._get_existing_oppositions(
                thesis, input_text
            )
            result.antithesis_data.extend(existing_data)
            all_existing.extend(existing_antitheses)

            # Add existing to not_like_these to avoid re-extraction
            for comp in existing_antitheses:
                if comp.statement not in not_like_these:
                    not_like_these.append(comp.statement)

            # 1b. Extract new antitheses (with retry if none found)
            antitheses, antithesis_data, extraction_reports = (
                await self._extract_with_retry(
                    thesis=thesis,
                    text=input_text,
                    not_like_these=not_like_these,
                )
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
        newly_extracted_hashes = [c.hash for c in newly_extracted]
        if newly_extracted_hashes and vocab:
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.execute(
                extracted_hashes=newly_extracted_hashes,
                vocabulary=vocab,
                text=input_text,
            )

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

        # Phase 3: Create Polarity nodes for each T-A pair
        total_antitheses = sum(len(r.antithesis_data) for r in results if not r.error)

        if total_antitheses == 0:
            self._report.ok = True
            self._report.summary = "No polarities found"
            self._report.artifacts["polarity_data"] = []
            return None

        # Phase 4: Create Polarities and Ideas with all T-A pairs
        ideas = self._create_ideas(results)
        self._create_polarities(results)

        # Build polarity_data for report (includes HS for each T-A pair)
        polarity_data = []
        for result in results:
            if result.error:
                continue
            for data in result.antithesis_data:
                polarity_data.append(
                    {
                        "thesis_hash": result.thesis.hash,
                        "antithesis_hash": data["hash"],
                        "heuristic_similarity": data["heuristic_similarity"],
                        "existing": data.get("existing", False),
                        "deduped": data.get("deduped", False),
                    }
                )

        # Build summary
        existing_count = len(all_existing)
        new_count = len(newly_extracted)

        self._report.ok = True
        self._report.artifacts["thesis_count"] = len(self.thesis_hashes)
        self._report.artifacts["existing_antitheses"] = existing_count
        self._report.artifacts["new_antitheses"] = new_count
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["polarity_data"] = polarity_data
        pol_created = self._report.artifacts.get("created_polarity_count", 0)
        pol_existing = self._report.artifacts.get("existing_polarity_count", 0)
        self._report.summary = (
            f"Found {existing_count} existing + {new_count} new antithesis(es) "
            f"for {len(self.thesis_hashes)} thesis(es). "
            f"Polarities: {pol_created} created, {pol_existing} existing."
        )

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
        """
        reports: list[ExecutionReport] = []

        # First attempt: with not_like_these constraints
        service = AntithesisExtraction()
        results = await service.execute(
            thesis=thesis,
            text=text,
            not_like_these=not_like_these,
        )
        reports.append(service.report)

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
        """Build antithesis data dicts from AntithesisResult objects."""
        return [
            {"hash": r.component.hash, "heuristic_similarity": r.heuristic_similarity}
            for r in results
        ]

    # --- Helpers ---

    async def _get_existing_oppositions(
        self, thesis: DialecticalComponent, text: str = ""
    ) -> tuple[list[DialecticalComponent], list[dict]]:
        """Get existing oppositions for a thesis from the database."""
        from dialectical_framework.features.antithesis_classification import \
            AntithesisClassification

        existing_components: list[DialecticalComponent] = []
        existing_data: list[dict] = []

        for antithesis, _ in thesis.oppositions.all():
            existing_components.append(antithesis)

            # Try to find HS from existing Polarity
            hs = self._lookup_hs_from_polarity(thesis, antithesis)

            if hs is None:
                # No Perspective found - estimate HS
                classifier = AntithesisClassification()
                result = await classifier.execute(
                    thesis=thesis,
                    antithesis_statement=antithesis.statement,
                    text=text,
                )
                hs = result.heuristic_similarity
                self._report.artifacts.setdefault("estimated_hs_count", 0)
                self._report.artifacts["estimated_hs_count"] += 1

            existing_data.append(
                {
                    "hash": antithesis.hash,
                    "heuristic_similarity": hs,
                    "existing": True,
                }
            )

        return existing_components, existing_data

    def _lookup_hs_from_polarity(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
    ) -> Optional[float]:
        """Look up HS from existing Polarity."""
        pol_repo = PolarityRepository()
        polarities = pol_repo.find_by_tension(thesis, antithesis)

        for polarity in polarities:
            a_result = polarity.a.get()
            if a_result:
                _, a_rel = a_result
                if (
                    isinstance(a_rel, ARelationship)
                    and a_rel.heuristic_similarity is not None
                ):
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

    def _reconnect_oppositions(
        self,
        results: list[ThesisResult],
        dedup_result: DedupResult,
    ) -> None:
        """Reconnect OPPOSITE_OF for deduped antitheses."""
        hash_to_thesis: dict[str, DialecticalComponent] = {}
        for result in results:
            if result.error:
                continue
            for data in result.antithesis_data:
                hash_to_thesis[data["hash"]] = result.thesis

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

    def _create_polarities(self, results: list[ThesisResult]) -> list[Polarity]:
        """Create Polarity nodes (T-A pairs) for each T-A pair."""
        pol_repo = PolarityRepository()
        created_polarities: list[Polarity] = []

        for result in results:
            if result.error:
                continue

            for data in result.antithesis_data:
                antithesis = self._resolve_component(data["hash"])
                if antithesis is None:
                    continue

                # Check if Polarity already exists for this T-A pair
                existing_pols = pol_repo.find_by_tension(result.thesis, antithesis)
                if existing_pols:
                    # Polarity already exists - skip creation
                    self._report.artifacts.setdefault("existing_polarity_count", 0)
                    self._report.artifacts["existing_polarity_count"] += 1
                    continue

                # Create new Polarity (atomic creation)
                polarity = Polarity()
                polarity.set_t(result.thesis, heuristic_similarity=1.0)
                polarity.set_a(
                    antithesis, heuristic_similarity=data["heuristic_similarity"]
                )
                polarity.commit()

                created_polarities.append(polarity)
                self._report.node_created(
                    polarity, meta={"hs": data["heuristic_similarity"]}
                )

        self._report.artifacts["created_polarity_count"] = len(created_polarities)
        return created_polarities

    def _create_ideas(self, results: list[ThesisResult]) -> Optional[Ideas]:
        """Create Ideas node with all theses and their antitheses."""
        valid_results = [r for r in results if not r.error and r.antithesis_data]
        if not valid_results:
            return None

        thesis_statements = [r.thesis.statement for r in valid_results]
        intent = f"Tensions for: {', '.join(thesis_statements[:3])}"
        if len(thesis_statements) > 3:
            intent += f" (+{len(thesis_statements) - 3} more)"

        ideas = Ideas(intent=intent)
        ideas.save()

        # Connect to inputs
        input_repo = InputRepository()
        for inp in input_repo.get_all():
            ideas.inputs.connect(inp)

        # Connect all theses and antitheses
        for result in valid_results:
            ideas.statements.connect(result.thesis)
            for data in result.antithesis_data:
                comp = self._resolve_component(data["hash"])
                if comp:
                    ideas.statements.connect(comp)

        ideas.commit()
        self._report.node_created(ideas)

        # Add rationale
        total_theses = len(valid_results)
        total_antitheses = sum(len(r.antithesis_data) for r in valid_results)
        all_hs = [
            d["heuristic_similarity"] for r in valid_results for d in r.antithesis_data
        ]
        max_hs = max(all_hs) if all_hs else 0.0

        rationale = Rationale(
            text=f"Found {total_antitheses} antitheses for {total_theses} theses. Max HS: {max_hs:.2f}"
        )
        rationale.set_explanation_target(ideas)
        rationale.commit()
        self._report.node_created(rationale)

        return ideas
