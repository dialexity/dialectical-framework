"""
FindPolarities: Orchestrator for creating Polarities (T-A pairs).

Extracts antitheses for theses and creates Polarity nodes (T-A pairs).
Returns Ideas containing all T and A components with HS metadata.

Flow:
    SurfaceTheses → Theses (Ideas with all T)
           ↓
    FindPolarities → Polarity nodes (T-A pairs with HS) + Ideas with all T and A
           ↓
    expand_polarities → Creates Perspectives from Polarities by adding aspects (T+, T-, A+, A-)

Usage:
    # Programmatic (web app)
    agent = FindPolarities(thesis_hashes=["abc123", "def456"])
    ideas = await agent.resolve()

    # Access T-A pairs from Ideas
    for comp, _ in ideas.statements.all():
        for antithesis, _ in comp.oppositions.all():
            print(f"{comp.text} vs {antithesis.text}")

    # LLM tool use (returns JSON with HS data)
    agent = FindPolarities(thesis_hashes=[...])
    json_result = await agent.call()  # Includes antithesis_data with HS values
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.concerns.antithetical_thesis_detection import \
    AntitheticalThesisDetection
from dialectical_framework.concerns.statement_deduplication import (
    DedupResult, StatementDeduplication)
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.estimation import (ArousalEstimation,
                                                          ModeEstimation)
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.relationships.polarity_relationship import (
    ARelationship)
from dialectical_framework.graph.repositories.statement_repository import \
    StatementRepository
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- Result container for tracking ---


class ThesisResult:
    """Container for tracking results per thesis."""

    def __init__(self, thesis: Statement):
        self.thesis = thesis
        self.antithesis_data: list[dict] = []  # [{hash, heuristic_similarity}, ...]
        self.error: Optional[str] = None
        self.extracted: list[Statement] = []
        self.existing: list[Statement] = []


# --- Main Orchestrator ---


class FindPolarities(ReasonableConcern[Optional[Ideas]]):
    """
    Orchestrate Polarity creation (T-A pairs).

    For each thesis hash:
    1. Use AntithesisExtraction to generate antitheses
    2. Create Polarity nodes (T-A pairs) with HS metadata
    3. Return Ideas containing all T and A components

    The HS (Heuristic Similarity) for each T-A pair is available in:
    - Report artifacts: polarity_data[{thesis_hash, antithesis_hash, heuristic_similarity}]
    - Polarity nodes: ARelationship.heuristic_similarity
    """

    def __init__(self, thesis_hashes: list[str], count: int = 5) -> None:
        self.thesis_hashes = thesis_hashes
        self.count = count

    async def resolve(self) -> Optional[Ideas]:
        """
        Resolve polarity creation: extract antitheses and create Polarities + Ideas.

        Returns:
            Ideas containing all T and A components (with OPPOSITE_OF relationships)
        """

        if not self.thesis_hashes:
            self._report.ok = True
            self._report.summary = "No thesis hashes provided"
            self._report.artifacts["antithesis_data"] = []
            return None

        # Get input text for context
        input_text = await self._get_input_text()

        # Get existing vocabulary to avoid and for dedup comparison
        comp_repo = StatementRepository()
        vocab = comp_repo.get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        results: list[ThesisResult] = []
        newly_extracted: list[Statement] = []

        # Phase 0: Consolidate theses that are antitheses of each other. Strongly
        # opposed pairs (HS >= 0.7) are merged into a single Polarity here and
        # removed from extraction; weaker pairs are surfaced as suggestions for
        # the agent to confirm (leaving both theses to proceed independently).
        unique_hashes = list(dict.fromkeys(self.thesis_hashes))
        unique_hashes, consolidated_data = await self._consolidate_antithetical(
            unique_hashes, input_text
        )

        # Phase 1: For each thesis, collect existing oppositions + extract new ones (parallel)
        import asyncio

        async def _process_thesis(thesis_hash: str) -> ThesisResult:
            thesis = self._resolve_component(thesis_hash)
            if thesis is None:
                result = ThesisResult(thesis=Statement(text=""))
                result.error = f"Thesis with hash '{thesis_hash}' not found"
                return result

            result = ThesisResult(thesis=thesis)

            # Collect existing oppositions from database
            existing_antitheses, existing_data = await self._get_existing_oppositions(
                thesis, input_text
            )
            result.antithesis_data.extend(existing_data)

            # Extract new antitheses (not_like_these = vocab only, no cross-thesis coordination)
            antitheses, antithesis_data, extraction_reports = (
                await self._extract_with_retry(
                    thesis=thesis,
                    text=input_text,
                    not_like_these=not_like_these + [c.prompt_text for c in existing_antitheses],
                )
            )
            for r in extraction_reports:
                self._report = self._report.merge(r)

            result.antithesis_data.extend(antithesis_data)
            result.extracted = antitheses
            result.existing = existing_antitheses
            return result

        # return_exceptions: one thesis whose extraction raises must not take
        # the other theses' polarities with it. `ThesisResult.error` already
        # exists for the per-thesis failure this converts to — and the whole
        # skill raising is how `claim2-weak-r14` turned one bad Mode estimation
        # into "polarity extraction failed" for a five-thesis fan-out.
        gathered = await asyncio.gather(
            *[_process_thesis(h) for h in unique_hashes],
            return_exceptions=True,
        )

        thesis_results: list[ThesisResult] = []
        for thesis_hash, outcome in zip(unique_hashes, gathered):
            if isinstance(outcome, BaseException):
                thesis = self._resolve_component(thesis_hash)
                failed = ThesisResult(thesis=thesis or Statement(text=""))
                failed.error = (
                    f"{type(outcome).__name__}: {outcome}"
                )
                thesis_results.append(failed)
                continue
            thesis_results.append(outcome)

        for result in thesis_results:
            results.append(result)
            newly_extracted.extend(result.extracted)

        # Phase 2: Semantic deduplication (only newly extracted, not existing)
        newly_extracted_hashes = [c.hash for c in newly_extracted]
        if newly_extracted_hashes and vocab:
            # Exclude theses from dedup vocabulary — an antithesis must never
            # be "deduped" to its own thesis (they're dialectically opposed, not equivalent)
            thesis_hash_set = set(self.thesis_hashes)
            dedup_vocab = [v for v in vocab if v.get("hash") not in thesis_hash_set]

            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.resolve(
                extracted_hashes=newly_extracted_hashes,
                vocabulary=dedup_vocab,
                text=input_text,
            )
            self._report = self._report.merge(deduplicator.report)

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

        # Deduplicate antithesis_data entries per thesis — dedup can merge an
        # extracted antithesis into one already present from existing oppositions,
        # producing duplicate (thesis, antithesis) pairs in the same result.
        for result in results:
            if result.error:
                continue
            seen: set[str] = set()
            unique_data: list[dict] = []
            for data in result.antithesis_data:
                if data["hash"] not in seen:
                    seen.add(data["hash"])
                    unique_data.append(data)
            result.antithesis_data = unique_data

        # Phase 3: Create Polarity nodes for each T-A pair
        total_antitheses = sum(len(r.antithesis_data) for r in results if not r.error)

        if total_antitheses == 0 and not consolidated_data:
            self._report.ok = True
            self._report.summary = "No polarities found"
            self._report.artifacts["polarity_data"] = []
            return None

        # Phase 4: Create Polarities and Ideas with all T-A pairs (consolidated
        # pairs already have their Polarities created in Phase 0).
        ideas = self._create_ideas(results, consolidated_data)
        polarity_map = self._create_polarities(results)

        # Build polarity_data for report (includes HS for each T-A pair). Start
        # with the consolidated pairs, then the extracted ones.
        polarity_data = list(consolidated_data)
        for result in results:
            if result.error:
                continue
            for data in result.antithesis_data:
                pol_hash = polarity_map.get((result.thesis.hash, data["hash"]))
                antithesis = self._resolve_component(data["hash"])
                polarity_data.append(
                    {
                        "polarity_hash": pol_hash,
                        "thesis_hash": result.thesis.hash,
                        "thesis_text": result.thesis.text,
                        "antithesis_hash": data["hash"],
                        "antithesis_text": antithesis.text if antithesis else None,
                        "heuristic_similarity": data["heuristic_similarity"],
                        "existing": data.get("existing", False),
                        "deduped": data.get("deduped", False),
                    }
                )

        # Build summary — derive counts from deduplicated antithesis_data
        existing_count = sum(
            1 for r in results if not r.error
            for d in r.antithesis_data if d.get("existing")
        )
        new_count = sum(
            1 for r in results if not r.error
            for d in r.antithesis_data if not d.get("existing")
        )

        self._report.ok = True
        self._report.artifacts["thesis_count"] = len(self.thesis_hashes)
        self._report.artifacts["existing_antitheses"] = existing_count
        self._report.artifacts["new_antitheses"] = new_count
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["polarity_data"] = polarity_data
        pol_created = self._report.artifacts.get("created_polarity_count", 0)
        pol_existing = self._report.artifacts.get("existing_polarity_count", 0)
        consolidated_count = len(consolidated_data)
        suggestion_count = len(
            self._report.artifacts.get("consolidation_suggestions", [])
        )
        summary = (
            f"Found {existing_count} existing + {new_count} new antithesis(es) "
            f"for {len(self.thesis_hashes)} thesis(es). "
            f"Polarities: {pol_created} created, {pol_existing} existing."
        )
        if consolidated_count:
            summary += (
                f" Consolidated {consolidated_count} antithetical thesis pair(s) "
                f"into single tension(s)."
            )
        if suggestion_count:
            summary += (
                f" {suggestion_count} weaker pair(s) suggested for consolidation "
                f"(acting on one merges 2 theses into 1 tension)."
            )
        # Failed theses must reach the summary. Isolating them (Phase 1's
        # return_exceptions) stops one bad thesis from killing the fan-out, but
        # silence about the survivors' missing siblings would just relocate the
        # invisibility that cost `claim2-weak-r14` its diagnosis: the agent
        # would read "Found 3 antitheses for 5 theses" as a complete answer.
        failures = [r for r in results if r.error]
        if failures:
            self._report.artifacts["failed_theses"] = [
                {"thesis_text": r.thesis.text, "error": r.error} for r in failures
            ]
            summary += (
                f" {len(failures)} thesis(es) FAILED extraction: "
                + "; ".join(f"{r.thesis.text!r} ({r.error})" for r in failures)
            )
        self._report.summary = summary

        return ideas

    # --- Extraction with Retry ---

    async def _extract_with_retry(
        self,
        thesis: Statement,
        text: str,
        not_like_these: list[str],
    ) -> tuple[list[Statement], list[dict], list[ExecutionReport]]:
        """
        Extract antitheses with retry logic.

        Goal: Find at least 1 antithesis per thesis.
        If first attempt with not_like_these yields nothing, retry with empty constraints.
        """
        reports: list[ExecutionReport] = []

        # First attempt: with not_like_these constraints
        service = AntithesisExtraction()
        results = await service.resolve(
            thesis=thesis,
            text=text,
            not_like_these=not_like_these,
            count=self.count,
        )
        reports.append(service.report)

        if results:
            components = [r.component for r in results]
            antithesis_data = self._build_antithesis_data(results)
            return components, antithesis_data, reports

        # Retry with empty not_like_these (relax constraints)
        service_retry = AntithesisExtraction()
        results_retry = await service_retry.resolve(
            thesis=thesis,
            text=text,
            not_like_these=[],
            count=self.count,
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
        self, thesis: Statement, text: str = ""
    ) -> tuple[list[Statement], list[dict]]:
        """Get existing oppositions for a thesis from the database."""
        from dialectical_framework.concerns.antithesis_classification import \
            AntithesisClassification

        existing_components: list[Statement] = []
        existing_data: list[dict] = []

        for antithesis, _ in thesis.oppositions.all():
            existing_components.append(antithesis)

            # Try to find HS from existing Polarity
            hs = self._lookup_hs_from_polarity(thesis, antithesis)

            if hs is None:
                # No Perspective found - estimate HS
                classifier = AntithesisClassification()
                result = await classifier.resolve(
                    thesis=thesis,
                    antithesis_statement=antithesis.text,
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
        thesis: Statement,
        antithesis: Statement,
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
        """Get input context from digests (falls back to full content if no digest)."""
        from dialectical_framework.utils.input_context import input_context

        repo = InputRepository()
        inputs = repo.get_all()

        return await input_context(inputs, input_resolver)

    def _reconnect_oppositions(
        self,
        results: list[ThesisResult],
        dedup_result: DedupResult,
    ) -> None:
        """Reconnect OPPOSITE_OF for deduped antitheses."""
        hash_to_thesis: dict[str, Statement] = {}
        for result in results:
            if result.error:
                continue
            for data in result.antithesis_data:
                hash_to_thesis[data["hash"]] = result.thesis

        for ext_hash, db_comp in dedup_result.replacements.items():
            thesis = hash_to_thesis.get(ext_hash)
            if thesis and db_comp:
                thesis.oppositions.connect(db_comp)
                self._report.relationship_created(
                    thesis.oppositions, thesis, db_comp
                )

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

    async def _consolidate_antithetical(
        self, unique_hashes: list[str], input_text: str
    ) -> tuple[list[str], list[dict]]:
        """Detect and merge theses that are antitheses of each other.

        Strongly-opposed pairs (HS >= 0.7) are merged into a single Polarity and
        their two hashes removed from the returned list (so they are NOT sent to
        antithesis extraction). Weaker pairs (0.1 < HS < 0.7) are recorded as
        suggestions but left in the list to proceed as independent theses.

        Returns:
            (reduced_hashes, consolidated_polarity_data) where each dict has the
            same shape FindPolarities uses in ``polarity_data``.
        """
        if len(unique_hashes) < 2:
            return unique_hashes, []

        detector = AntitheticalThesisDetection()
        detection = await detector.resolve(
            thesis_hashes=unique_hashes, text=input_text
        )
        self._report = self._report.merge(detector.report)

        # Surface weak pairs for the agent to confirm (non-destructive).
        self._report.artifacts["consolidation_suggestions"] = [
            p.as_dict() for p in detection.suggest_pairs
        ]

        if not detection.merge_pairs:
            return unique_hashes, []

        pol_repo = PolarityRepository()
        est_manager = EstimationManager()
        consolidated_data: list[dict] = []
        merged_hashes: set[str] = set()
        merged_count = 0

        for pair in detection.merge_pairs:
            thesis = self._resolve_component(pair.thesis_hash)
            antithesis = self._resolve_component(pair.antithesis_hash)
            if thesis is None or antithesis is None:
                continue

            # Record the dialectical opposition (symmetric, idempotent).
            thesis.oppositions.connect(antithesis)
            self._report.relationship_created(
                thesis.oppositions, thesis, antithesis
            )

            existing_pols = pol_repo.find_by_tension(thesis, antithesis)
            if existing_pols:
                polarity = existing_pols[0]
                self._report.artifacts.setdefault("existing_polarity_count", 0)
                self._report.artifacts["existing_polarity_count"] += 1
            else:
                polarity = self._build_polarity(
                    thesis, antithesis, pair.heuristic_similarity
                )
                merged_count += 1

            # Persist antithesis Mode/Arousal (Antithesis Persistence Checklist).
            self._persist_mode_arousal(
                est_manager, antithesis, pair.mode_value, pair.arousal_value
            )

            consolidated_data.append(
                {
                    "polarity_hash": polarity.hash,
                    "thesis_hash": thesis.hash,
                    "thesis_text": thesis.text,
                    "antithesis_hash": antithesis.hash,
                    "antithesis_text": antithesis.text,
                    "heuristic_similarity": pair.heuristic_similarity,
                    "existing": False,
                    "deduped": False,
                    "consolidated": True,
                }
            )
            merged_hashes.add(thesis.hash)
            merged_hashes.add(antithesis.hash)

        self._report.artifacts["consolidated_pairs"] = len(consolidated_data)
        if merged_count:
            self._report.artifacts["created_polarity_count"] = (
                self._report.artifacts.get("created_polarity_count", 0) + merged_count
            )

        reduced = [h for h in unique_hashes if h not in merged_hashes]
        return reduced, consolidated_data

    def _persist_mode_arousal(
        self,
        est_manager: EstimationManager,
        antithesis: Statement,
        mode_value: float,
        arousal_value: float,
    ) -> None:
        """Persist Mode/Arousal estimations on the antithesis (mirrors IntroducePolarity)."""
        mode_est = est_manager.upsert_estimation(
            antithesis, ModeEstimation, mode_value
        )
        arousal_est = est_manager.upsert_estimation(
            antithesis, ArousalEstimation, arousal_value
        )
        if mode_est:
            self._report.node_updated(mode_est, patch={"value": mode_value})
        if arousal_est:
            self._report.node_updated(arousal_est, patch={"value": arousal_value})

    def _create_polarities(self, results: list[ThesisResult]) -> dict[tuple[str, str], str]:
        """Create Polarity nodes (T-A pairs) for each T-A pair.

        Returns:
            Mapping of (thesis_hash, antithesis_hash) -> polarity_hash
        """
        pol_repo = PolarityRepository()
        created_count = 0
        polarity_map: dict[tuple[str, str], str] = {}

        for result in results:
            if result.error:
                continue

            for data in result.antithesis_data:
                # Skip if deduplication mapped the antithesis back to its own thesis
                if data["hash"] == result.thesis.hash:
                    continue

                # Skip if this T-A pair was already processed (e.g. dedup merged
                # an extracted antithesis into one already seen via existing oppositions)
                if (result.thesis.hash, data["hash"]) in polarity_map:
                    continue

                antithesis = self._resolve_component(data["hash"])
                if antithesis is None:
                    continue

                # Check if Polarity already exists for this T-A pair
                existing_pols = pol_repo.find_by_tension(result.thesis, antithesis)
                if existing_pols:
                    polarity_map[(result.thesis.hash, data["hash"])] = existing_pols[0].hash
                    self._report.artifacts.setdefault("existing_polarity_count", 0)
                    self._report.artifacts["existing_polarity_count"] += 1
                    continue

                # Create new Polarity (atomic creation)
                polarity = self._build_polarity(
                    result.thesis, antithesis, data["heuristic_similarity"]
                )
                polarity_map[(result.thesis.hash, data["hash"])] = polarity.hash
                created_count += 1

        # Accumulate — Phase 0 consolidation may already have created polarities.
        self._report.artifacts["created_polarity_count"] = (
            self._report.artifacts.get("created_polarity_count", 0) + created_count
        )
        return polarity_map

    def _build_polarity(
        self,
        thesis: Statement,
        antithesis: Statement,
        heuristic_similarity: float,
    ) -> Polarity:
        """Create and commit a Polarity from two committed Statements, recording effects.

        Shared by regular polarity creation and antithetical-thesis consolidation.
        T defines the apex (HS=1.0); the meaningful HS lives on A.
        """
        polarity = Polarity()
        polarity.set_t(thesis, heuristic_similarity=1.0)
        polarity.set_a(antithesis, heuristic_similarity=heuristic_similarity)
        polarity.commit()

        self._report.node_created(polarity, meta={"hs": heuristic_similarity})
        self._report.relationship_created(
            polarity.t, thesis, polarity,
            patch={"heuristic_similarity": 1.0, "alias": "T"},
        )
        self._report.relationship_created(
            polarity.a, antithesis, polarity,
            patch={"heuristic_similarity": heuristic_similarity, "alias": "A"},
        )
        return polarity

    def _create_ideas(
        self,
        results: list[ThesisResult],
        consolidated_data: Optional[list[dict]] = None,
    ) -> Optional[Ideas]:
        """Create Ideas node with all theses and their antitheses.

        Includes both the extracted T-A pairs (from ``results``) and the
        consolidated antithetical pairs (from ``consolidated_data``), whose
        theses were removed from the extraction set in Phase 0.
        """
        consolidated_data = consolidated_data or []
        valid_results = [r for r in results if not r.error and r.antithesis_data]
        if not valid_results and not consolidated_data:
            return None

        thesis_statements = [r.thesis.text for r in valid_results]
        thesis_statements += [d["thesis_text"] for d in consolidated_data]
        intent = f"Tensions for: {', '.join(thesis_statements[:3])}"
        if len(thesis_statements) > 3:
            intent += f" (+{len(thesis_statements) - 3} more)"

        ideas = Ideas(intent=intent)
        ideas.save()
        self._report.node_created(ideas)

        # Connect to inputs
        input_repo = InputRepository()
        for inp in input_repo.get_all():
            ideas.inputs.connect(inp)
            self._report.relationship_created(ideas.inputs, ideas, inp)

        # Connect all theses and antitheses (deduplicated across theses)
        connected_hashes: set[str] = set()

        def _connect(hash: str) -> None:
            if hash in connected_hashes:
                return
            comp = self._resolve_component(hash)
            if comp:
                connected_hashes.add(hash)
                ideas.statements.connect(comp)
                self._report.relationship_created(ideas.statements, ideas, comp)

        for result in valid_results:
            _connect(result.thesis.hash)
            for data in result.antithesis_data:
                _connect(data["hash"])

        # Consolidated pairs: both sides are theses the user supplied.
        for data in consolidated_data:
            _connect(data["thesis_hash"])
            _connect(data["antithesis_hash"])

        ideas.commit()
        self._report.node_committed(ideas)

        # Add rationale
        total_theses = len(valid_results) + len(consolidated_data)
        total_antitheses = sum(len(r.antithesis_data) for r in valid_results) + len(
            consolidated_data
        )
        all_hs = [
            d["heuristic_similarity"] for r in valid_results for d in r.antithesis_data
        ]
        all_hs += [d["heuristic_similarity"] for d in consolidated_data]
        max_hs = max(all_hs) if all_hs else 0.0

        rationale = Rationale(
            text=f"Found {total_antitheses} antitheses for {total_theses} theses. Max HS: {max_hs:.2f}"
        )
        rationale.set_explanation_target(ideas)
        rationale.commit()
        self._report.node_created(rationale)

        return ideas


@llm.tool
async def find_polarities(
    thesis_hashes: Annotated[list[str], Field(description="Hashes of thesis Statements to find antitheses for")],
    count: Annotated[int, Field(description="Number of antitheses to find per thesis")] = 5,
) -> str:
    """Find antitheses for given theses and create Polarity nodes (T-A tensions). Each thesis gets antitheses with heuristic similarity scores, truncated to count with maximum taxonomy branch coverage. Returns polarity_hash for each pair."""
    concern = FindPolarities(thesis_hashes=thesis_hashes, count=count)
    await concern.resolve()
    return str(concern.report)
