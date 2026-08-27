"""
ExploreTransformations: Subagent for generating Action-Reflection transformations for Wheel edge pairs.

Orchestrates the transformation generation pipeline at the wheel level:
1. Resolves the wheel and its edge pairs (diametrically opposite edges)
2. For each pair, checks for reusable Transformations in the same Nexus
3. If not found: derives context from the edge pair's source/target PPs
4. Runs ApexDerivation → ActionExtraction → TransformationGeneration
5. Creates Transformation nodes scoped to the Nexus

Usage:
    # Programmatic use
    agent = ExploreTransformations(wheel_hash="abc123...")
    result = await agent.resolve()
    for t in result.all:
        print(f"{t}")

    # Target a specific edge pair
    agent = ExploreTransformations(wheel_hash="abc123...", edge_hash="def456...")
    result = await agent.resolve()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.ac_re_taxonomy import (
    INSIGHT_CATEGORIES, insight_category_of_label)
from dialectical_framework.concerns.action_extraction import (
    ActionCandidateResultDto, ActionExtraction)
from dialectical_framework.concerns.positive_ac_re_apex_derivation import (
    ApexDerivation, ApexDerivationResultDto)
from dialectical_framework.concerns.transformation_generation import (
    TransformationGeneration, TransformationTetradDto)
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transformation import (
    POSITION_AC, POSITION_AC_MINUS, POSITION_AC_PLUS, POSITION_RE,
    POSITION_RE_MINUS, POSITION_RE_PLUS, Transformation)
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.relationships.polarity_relationship import (
    AcMinusRelationship, AcPlusRelationship, AcRelationship,
    ReMinusRelationship, RePlusRelationship, ReRelationship)
from dialectical_framework.utils.async_drain import drain_completed

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.protocols.input_resolver import InputResolver


@dataclass
class _EdgeProcessingData:
    """Typed intermediate data for edge pair processing."""

    #: Edge already carries one Transformation per insight category — nothing to do.
    complete: bool = False
    skip: bool = False
    #: Insight categories this edge still needs. Empty on a complete or skipped
    #: edge; all of INSIGHT_CATEGORIES on a fresh one; a subset when an earlier
    #: run was interrupted part-way through the write loop.
    missing_categories: set[str] = field(default_factory=set)
    ac_candidates: list = field(default_factory=list)
    apexes: Optional[ApexDerivationResultDto] = None
    source_segment: Optional[WheelSegment] = None
    target_segment: Optional[WheelSegment] = None


@dataclass
class ExploreTransformationsResult:
    """Result from the ExploreTransformations."""

    existing: list[Transformation] = field(default_factory=list)
    new: list[Transformation] = field(default_factory=list)
    apexes: Optional[ApexDerivationResultDto] = None

    @property
    def all(self) -> list[Transformation]:
        """Get all transformations (existing + new)."""
        return self.existing + self.new


class ExploreTransformations(ReasonableConcern[ExploreTransformationsResult]):
    """
    Subagent for generating Action-Reflection transformations at wheel level.

    This agent orchestrates the full transformation generation pipeline,
    producing Transformations for wheel edge pairs (diametrically opposite edges).
    Transformations are scoped by Nexus and reusable across wheels sharing the
    same logical edge pairs.
    """

    def __init__(self, wheel_hash: str, edge_hash: Optional[str] = None) -> None:
        self.wheel_hash = wheel_hash
        self.edge_hash = edge_hash
        #: short_hash -> the insight categories a partly-built edge was topped up
        #: WITH. Populated only when an edge already carried some Transformations,
        #: so the report can say "resumed" rather than "new". Written after the
        #: graph writes, never before: bands owed and bands built are different
        #: facts, and reporting the first as the second turned a failed top-up
        #: into a claimed one.
        self._resumed_edges: dict[str, list[str]] = {}
        #: short_hash -> categories still owed after this call. A top-up can come
        #: back short (the LLM picks the level within a band and can land outside
        #: the one it was asked for, and a generation can fail), and silence there
        #: read as success — the wheel simply stayed partial with no one saying
        #: why, across unlimited retries.
        self._resume_shortfall: dict[str, list[str]] = {}
        #: short_hashes of edges that owe bands but cannot be built — their own
        #: segments are unfinished, or their pair partner's are. Reported so the
        #: Explorer's own tool output says why an edge stayed empty; the Advisor
        #: learns the same fact from derived status (`blocked_edges`).
        self._blocked_edges: set[str] = set()

    async def resolve(self) -> ExploreTransformationsResult:
        """
        Resolve the transformation generation pipeline at wheel level.

        Returns:
            ExploreTransformationsResult with existing and new transformations
        """

        # 1. Resolve wheel and nexus
        wheel = self._resolve_wheel()
        nexus = self._resolve_nexus(wheel)

        # 2. Get edge pairs (optionally filtered to pair containing a specific edge)
        edge_pairs = self._get_target_edge_pairs(wheel)

        if not edge_pairs:
            # Every well-formed Wheel has edge pairs (N PPs -> 2N edges -> N
            # pairs), so this is a structural fault, not "nothing to do". Left
            # ok=True it told the agent the wheel was deepened.
            self._report.ok = False
            self._report.summary = (
                f"No edge pairs found for Wheel {wheel.short_hash} — nothing "
                f"could be transformed (a well-formed wheel always has pairs)"
            )
            return ExploreTransformationsResult()

        # 3. Get input text from scope
        input_text = await self._get_input_text()

        # 4. Process edge pairs in parallel — both edges get Transformations
        pair_results = await asyncio.gather(
            *[
                self._process_edge_pair(wheel, nexus, edge_a, edge_b, input_text)
                for edge_a, edge_b in edge_pairs
            ],
            return_exceptions=True,
        )

        all_existing: list[Transformation] = []
        all_new: list[Transformation] = []
        last_apexes: Optional[ApexDerivationResultDto] = None

        failed_pairs: list[str] = []
        for result in pair_results:
            if isinstance(result, Exception):
                logging.getLogger(__name__).warning("Edge pair failed: %s", result)
                # A log line is not a report line. The caller
                # (ExplorationPipeline, `deepen`) reads only `str(report)`, so
                # without this a wheel whose every edge pair failed rendered as
                # "0 new, 0 existing" with ok=True — indistinguishable from a
                # wheel that was already fully transformed.
                failed_pairs.append(f"{type(result).__name__}: {result}")
                continue
            existing, new, apexes = result
            all_existing.extend(existing)
            all_new.extend(new)
            if apexes:
                last_apexes = apexes

        # 5. Audit new transformations in parallel
        if all_new:
            from dialectical_framework.concerns.transformation_audit import TransformationAudit

            async def _audit_one(tr: Transformation) -> TransformationAudit:
                auditor = TransformationAudit()
                await auditor.resolve(tr, input_text)
                return auditor

            audit_results = await asyncio.gather(
                *[_audit_one(tr) for tr in all_new],
                return_exceptions=True,
            )
            for result in audit_results:
                if isinstance(result, Exception):
                    logging.getLogger(__name__).warning("Audit failed: %s", result)
                    continue
                self._report = self._report.merge(result.report)

        # Summary
        self._report.artifacts["wheel_hash"] = wheel.short_hash
        self._report.artifacts["nexus_hash"] = nexus.short_hash
        self._report.artifacts["edge_pairs_processed"] = len(edge_pairs)
        self._report.artifacts["existing_count"] = len(all_existing)
        self._report.artifacts["new_count"] = len(all_new)
        self._report.summary = (
            f"Processed {len(edge_pairs)} edge pair(s) for Wheel {wheel.short_hash}: "
            f"{len(all_new)} new, {len(all_existing)} existing"
        )
        self._report_resume_state()
        if failed_pairs:
            # Partial success stays ok — the transformations that WERE built are
            # real and the agent should use them. Total failure is not ok.
            self._report.ok = bool(all_new or all_existing)
            self._report.summary += (
                f" — {len(failed_pairs)} edge pair(s) FAILED "
                f"({'; '.join(failed_pairs)})"
            )
            self._report.artifacts["failed_edge_pairs"] = failed_pairs

        return ExploreTransformationsResult(
            existing=all_existing,
            new=all_new,
            apexes=last_apexes,
        )

    def _report_resume_state(self) -> None:
        """Decorate the report with what was resumed and what is still owed.

        Its own method so the resume accounting can be driven (and asserted) on
        the real code path — `resolve()` needs a live wheel, an edge pair does
        not.
        """
        if self._resumed_edges:
            # A top-up must read as a top-up. Without this the agent sees only
            # "N new" and cannot tell a fresh build from the completion of an
            # interrupted one — which is exactly the state the user left behind.
            self._report.artifacts["resumed_categories"] = dict(self._resumed_edges)
            self._report.summary += (
                f" — resumed {len(self._resumed_edges)} partly-built edge(s)"
            )
        if self._resume_shortfall:
            # A top-up that came back short says so. Otherwise the wheel just
            # stays partial and every retry looks like a successful resume.
            self._report.artifacts["still_missing"] = dict(self._resume_shortfall)
            shortfall_str = "; ".join(
                f"{edge_hash}: {', '.join(categories)}"
                for edge_hash, categories in self._resume_shortfall.items()
            )
            self._report.summary += (
                f" — {len(self._resume_shortfall)} edge(s) still short "
                f"({shortfall_str})"
            )
        if self._blocked_edges:
            # Nothing was spent on these and nothing can be until the segments
            # they run between are finished. Said out loud, because an edge that
            # is merely absent from the output reads as an edge that failed.
            blocked = sorted(self._blocked_edges)
            self._report.artifacts["blocked_edges"] = blocked
            self._report.summary += (
                f" — {len(blocked)} edge(s) blocked, segments unfinished "
                f"({', '.join(blocked)})"
            )

    async def _process_edge_pair(
        self,
        wheel: Wheel,
        nexus: Nexus,
        edge_a: Transition,
        edge_b: Transition,
        input_text: str,
    ) -> tuple[list[Transformation], list[Transformation], Optional[ApexDerivationResultDto]]:
        """
        Process a diametrically opposite edge pair.

        Phase 1: Extract Ac+ candidates for both edges in parallel.
        Phase 2: Generate tetrads for all candidates in parallel.

        Returns:
            Tuple of (existing, new, apexes)
        """
        from dialectical_framework.graph.repositories.transformation_repository import TransformationRepository

        tr_repo = TransformationRepository()
        all_existing: list[Transformation] = []
        last_apexes: Optional[ApexDerivationResultDto] = None

        # Phase 1: Extract Ac+ for both edges in parallel (check existing first)
        phase1_tasks: list[tuple[Transition, asyncio.Task]] = []
        edge_data: dict[str, _EdgeProcessingData] = {}
        #: edge hash -> the bands that edge itself still owes (empty when it is
        #: complete or unworkable). Kept beside `edge_data` because Phase 1's
        #: scope depends on BOTH edges of the pair, not just its own.
        owed: dict[str, set[str]] = {}
        workable: dict[str, bool] = {}
        #: edge hash -> whether THIS edge already carried Transformations. Per
        #: edge, not per pair: an untouched edge opposite a part-built one is a
        #: fresh build, and calling it a resume misdescribes both.
        had_existing: dict[str, bool] = {}

        for edge in (edge_a, edge_b):
            assert edge.hash is not None
            existing = tr_repo.find_by_edge(edge=edge)
            all_existing.extend(existing)
            had_existing[edge.hash] = bool(existing)

            # An edge is done when it carries one Transformation per insight
            # category — NOT merely when it carries any. The write loop below
            # commits one Transformation at a time, so a session that closed
            # mid-drain leaves an edge with some categories committed and the rest
            # missing; treating non-empty as done stranded such an edge forever.
            # That partial state is now reached SOONER (the drain writes in
            # completion order rather than after a barrier), which changes nothing
            # about correctness — this resume path is exactly what makes writing
            # incrementally safe rather than a new class of half-built edge.
            missing = self._missing_categories(existing)
            source_segment = edge.get_source_wheel_segment()
            target_segment = edge.get_target_wheel_segment()
            can_build = bool(
                source_segment
                and target_segment
                and source_segment.is_complete()
                and target_segment.is_complete()
            )
            workable[edge.hash] = can_build

            if not missing:
                edge_data[edge.hash] = _EdgeProcessingData(complete=True)
                owed[edge.hash] = set()
                continue
            if not can_build:
                edge_data[edge.hash] = _EdgeProcessingData(skip=True)
                owed[edge.hash] = set()
                self._blocked_edges.add(edge.short_hash)
                continue

            edge_data[edge.hash] = _EdgeProcessingData(
                source_segment=source_segment,
                target_segment=target_segment,
                missing_categories=missing,
            )
            owed[edge.hash] = missing

        # Phase 1 is scoped to what EITHER side of the pair owes. A tetrad pairs
        # an edge's Ac+ with the opposite edge's Ac+ in the same band (that Ac+
        # becomes its Re+), so an edge whose partner is already complete must
        # still extract candidates — as support, without earning Transformations
        # of its own. Without this the commonest interrupted state could never
        # resume: the write loop finishes edge A, dies part-way through edge B,
        # and B's top-up then finds nobody to pair with (`_find_matching_category`
        # returns None on an empty candidate list) and silently generates nothing.
        #
        # Buildability is a property of the PAIR for the same reason: if either
        # edge's segments are unfinished, neither edge can earn a Transformation,
        # because the missing side has no Ac+ to lend. Extracting anyway burned
        # an ApexDerivation + one ActionExtraction per band on every attempt and
        # wrote nothing — and the derived status then invited another `deepen`,
        # so the same cost repeated for as long as the user kept trying.
        pair_buildable = workable[edge_a.hash] and workable[edge_b.hash]
        for edge, partner in ((edge_a, edge_b), (edge_b, edge_a)):
            assert edge.hash is not None and partner.hash is not None
            wanted = owed[edge.hash] | owed[partner.hash]
            if not wanted or not pair_buildable:
                if owed[edge.hash] and not pair_buildable:
                    # Blocked BY THE PARTNER, not by itself. Named as blocked so
                    # the report says unbuildable rather than leaving it to read
                    # as a top-up that produced nothing.
                    edge_data[edge.hash] = _EdgeProcessingData(skip=True)
                    owed[edge.hash] = set()
                    self._blocked_edges.add(edge.short_hash)
                continue
            phase1_tasks.append((edge, asyncio.ensure_future(
                self._phase1_for_edge(edge, wheel, input_text, wanted)
            )))

        # Await Phase 1 tasks in parallel
        if phase1_tasks:
            results = await asyncio.gather(
                *[t for _, t in phase1_tasks],
                return_exceptions=True,
            )
            for (edge, _), result in zip(phase1_tasks, results):
                assert edge.hash is not None
                if isinstance(result, Exception):
                    logging.getLogger(__name__).warning(
                        "Phase 1 failed for edge %s: %s", edge.short_hash, result
                    )
                    # A support-only edge (already complete, extracted purely to
                    # pair with its partner) stays complete — it owes nothing, so
                    # calling it skipped would misreport a finished edge.
                    if not edge_data[edge.hash].complete:
                        edge_data[edge.hash] = _EdgeProcessingData(skip=True)
                    continue
                apexes, ac_candidates, report = result
                self._report = self._report.merge(report)
                if apexes:
                    last_apexes = apexes
                data = edge_data[edge.hash]
                data.apexes = apexes
                data.ac_candidates = ac_candidates or []

        # Phase 2: Generate tetrads in parallel
        generation_tasks: list[tuple[Transition, _EdgeProcessingData, ActionCandidateResultDto, asyncio.Task]] = []

        for edge, opposite_edge in [(edge_a, edge_b), (edge_b, edge_a)]:
            assert edge.hash is not None
            assert opposite_edge.hash is not None
            data = edge_data.get(edge.hash)
            if not data or data.complete or data.skip:
                continue
            if not data.ac_candidates:
                continue
            if not data.source_segment or not data.target_segment or not data.apexes:
                continue

            opp_data = edge_data.get(opposite_edge.hash)
            opp_ac_candidates = opp_data.ac_candidates if opp_data else []

            # Phase 1 was already asked for only the missing categories, but the
            # LLM picks the level within a category and can land outside the band
            # it was prompted for. Filter here too, so a top-up cannot re-add a
            # band the edge already has.
            for ac_plus in self._only_missing(data.ac_candidates, data.missing_categories):
                opposite_ac = self._find_matching_category(
                    opp_ac_candidates, ac_plus.insight_label
                )
                if not opposite_ac:
                    continue

                task = asyncio.ensure_future(
                    self._generate_tetrad(edge, ac_plus, opposite_ac, data.apexes, input_text)
                )
                generation_tasks.append((edge, data, ac_plus, task))

        # Write each tetrad AS IT LANDS, not after all of them land. Writes are
        # still strictly one at a time — `_create_transformation` is synchronous,
        # so two can never interleave and the GQLAlchemy constraint holds exactly
        # as it did under `gather`.
        #
        # **This did NOT fix the silence it was aimed at, and the honest figure
        # belongs here rather than only in a commit message.**
        # `probe_explore_progress.py` measured this phase as 45.6s of dead air
        # ending in 120 effects at once; after the switch from `gather` to a
        # completion-order drain it measured 42.9s of dead air ending in 120 effects
        # over 2.0s. Essentially nothing, because these are six IDENTICAL 4-call
        # chains started together — they finish together, so there is no early
        # result to deliver early. Completion-order draining only pays on
        # heterogeneous work, which the cost probe's per-caller table (6 each of
        # five DTOs) says this is not.
        #
        # Kept rather than reverted, for the case it does serve: one tetrad hitting
        # a ParseError retry used to hold back the writes of all five siblings, and
        # now holds back only its own. Tail behaviour, not median — do not cite it
        # as a latency fix. Closing the real hole needs a progress signal emitted
        # INSIDE `_generate_tetrad`, between its four sequential calls, where there
        # is no node to report yet.
        #
        # Failure semantics unchanged from `gather(..., return_exceptions=True)`:
        # a failed tetrad is a logged skip that the resume machinery below tops up
        # on a later call, never something that takes down its siblings.
        all_new: list[Transformation] = []
        #: edge hash -> bands that actually reached the graph on this call.
        built: dict[str, set[str]] = {}
        if generation_tasks:
            def _log_failure(
                context: tuple[int, Transition, _EdgeProcessingData, ActionCandidateResultDto],
                error: BaseException,
            ) -> None:
                logging.getLogger(__name__).warning(
                    "Tetrad generation failed for edge %s: %s", context[1].short_hash, error
                )

            #: (submission index, transformation), sorted back at the end.
            landed: list[tuple[int, Transformation]] = []
            async for (index, edge, data, ac_plus), (tetrad, report) in drain_completed(
                {
                    task: (index, edge, data, ac_plus)
                    for index, (edge, data, ac_plus, task) in enumerate(generation_tasks)
                },
                on_error=_log_failure,
            ):
                self._report = self._report.merge(report)
                assert data.source_segment is not None
                assert data.target_segment is not None
                transformation = self._create_transformation(
                    nexus, edge, data.source_segment, data.target_segment, tetrad,
                )
                landed.append((index, transformation))
                assert edge.hash is not None
                try:
                    built.setdefault(edge.hash, set()).add(
                        insight_category_of_label(ac_plus.insight_label)
                    )
                except ValueError:
                    # An off-scale label still produced a real Transformation;
                    # it just cannot be attributed to a band.
                    pass
            # Emission order is now completion order, which is the point — but the
            # REPORT's order stays submission order, so nothing downstream starts
            # depending on which provider call happened to finish first.
            all_new = [t for _, t in sorted(landed, key=lambda pair: pair[0])]

        # Resume accounting, AFTER the writes: what a part-built edge was topped
        # up with, and what it still owes. Both are needed — a top-up that came
        # back short otherwise looked identical to one that finished the edge.
        for edge in (edge_a, edge_b):
            assert edge.hash is not None
            if not had_existing[edge.hash] or not owed[edge.hash]:
                continue
            got = built.get(edge.hash, set())
            if got:
                self._resumed_edges[edge.short_hash] = sorted(got)
            still_owed = owed[edge.hash] - got
            if still_owed:
                self._resume_shortfall[edge.short_hash] = sorted(still_owed)

        return all_existing, all_new, last_apexes

    @staticmethod
    def _missing_categories(existing: list[Transformation]) -> set[str]:
        """Which insight categories an edge still owes, given what it carries.

        Bounded by COUNT as well as by category: an edge gets
        `len(INSIGHT_CATEGORIES)` Transformations total, so three existing ones
        that all landed in the same band return nothing to do rather than
        growing the edge past its budget (which would break the 6N cardinality
        the docs and cost math are bound to). Uncategorisable Transformations —
        no Ac+, or no stored insight value — consume budget without covering a
        category, which is the honest reading: something is there, but resume
        cannot tell what.
        """
        budget = len(INSIGHT_CATEGORIES) - len(existing)
        if budget <= 0:
            return set()
        covered = {
            category
            for category in (t.insight_category for t in existing)
            if category
        }
        # Declaration order, not set order: Generative first, so an interrupted
        # top-up spends its budget on the deepest band it still lacks.
        return {
            category
            for category in [c for c in INSIGHT_CATEGORIES if c not in covered][:budget]
        }

    @staticmethod
    def _only_missing(
        candidates: list[ActionCandidateResultDto],
        missing_categories: set[str],
    ) -> list[ActionCandidateResultDto]:
        """Keep at most one candidate per insight band the edge still lacks.

        Two filters, and both are the contract rather than tidiness. The band
        must be one the edge lacks, so a top-up cannot re-add what it already
        has. And AT MOST ONE candidate per band, because `ActionExtraction`
        asks per band but the LLM picks the level inside it and can answer two
        prompts with the same band: unfiltered, an edge could end up with three
        Configurational Transformations and none Generative — reading 3/3 done
        while two of its three documented depth alternatives are permanently
        absent, and permanently invisible, since the derived count is per row.
        Keeping one makes the drift show up as a shortfall the next `deepen`
        can top up.

        A candidate whose label maps to no category is kept — dropping it would
        silently lose generation work over a taxonomy gap — but only one such,
        for the same reason.
        """
        if not missing_categories:
            return []

        kept: list[ActionCandidateResultDto] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                category = insight_category_of_label(candidate.insight_label)
            except ValueError:
                # One sentinel for every off-scale label: they cannot be told
                # apart as bands, so they share a single slot.
                category = "unmapped"
            else:
                if category not in missing_categories:
                    continue
            if category in seen:
                continue
            seen.add(category)
            kept.append(candidate)
        return kept

    async def _phase1_for_edge(
        self,
        edge: Transition,
        wheel: Wheel,
        input_text: str,
        only_categories: Optional[set[str]] = None,
    ) -> tuple[Optional[ApexDerivationResultDto], list[ActionCandidateResultDto], Any]:
        """Run ApexDerivation + ActionExtraction for a single edge. Returns (apexes, candidates, merged_report)."""
        from dialectical_framework.agents.execution_report import ExecutionReport

        merged_report = ExecutionReport(tool=self.__class__.__name__)

        apex_service = ApexDerivation()
        apexes = await apex_service.resolve(edge, input_text)
        merged_report = merged_report.merge(apex_service.report)

        extractor = ActionExtraction()
        ac_candidates = await extractor.resolve(
            edge, input_text,
            not_like_these=wheel.transformations,
            only_categories=only_categories,
        )
        merged_report = merged_report.merge(extractor.report)

        return apexes, ac_candidates or [], merged_report

    async def _generate_tetrad(
        self,
        edge: Transition,
        ac_plus: ActionCandidateResultDto,
        opposite_ac: ActionCandidateResultDto,
        apexes: ApexDerivationResultDto,
        input_text: str,
    ) -> tuple[TransformationTetradDto, Any]:
        """Run TransformationGeneration for one candidate. Returns (tetrad, report)."""
        generator = TransformationGeneration()
        tetrad = await generator.resolve(edge, ac_plus, opposite_ac, apexes, input_text)
        return tetrad, generator.report

    @staticmethod
    def _find_matching_category(
        candidates: list[ActionCandidateResultDto],
        insight_label: str,
    ) -> Optional[ActionCandidateResultDto]:
        """Find an Ac+ candidate matching the given insight category."""
        if not candidates:
            return None

        from dialectical_framework.concerns.ac_re_taxonomy import \
            insight_category_of_label

        try:
            target_category = insight_category_of_label(insight_label)
        except ValueError:
            return candidates[0]

        for candidate in candidates:
            try:
                if insight_category_of_label(candidate.insight_label) == target_category:
                    return candidate
            except ValueError:
                continue

        # Fallback: return first available
        return candidates[0]

    def _resolve_wheel(self) -> Wheel:
        """Resolve Wheel from hash or prefix."""
        from dialectical_framework.graph.nodes.wheel import Wheel
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        repo = NodeRepository()
        node = repo.find_by_hash(self.wheel_hash, node_type=Wheel)
        if node is None:
            raise ValueError(f"Wheel not found: {self.wheel_hash}")
        return node

    @staticmethod
    def _resolve_nexus(wheel: Wheel) -> Nexus:
        """
        Resolve Nexus from Wheel → Cycle → Perspectives → Nexus.

        Traverses: Wheel's parent Cycle has perspective_hashes → find a PP → get its Nexus.
        """

        # Get PPs from the wheel (via edges)
        pps = wheel._perspectives
        if not pps:
            raise ValueError(
                f"Wheel {wheel.short_hash} has no Perspectives, cannot determine Nexus"
            )

        # Find the Nexus from the first PP
        for pp in pps:
            nexus_result = pp.nexus.get()
            if nexus_result:
                nexus_node, _ = nexus_result
                return nexus_node

        raise ValueError(
            f"No Nexus found for Wheel {wheel.short_hash}'s Perspectives"
        )

    def _get_target_edge_pairs(self, wheel: Wheel) -> list[tuple[Transition, Transition]]:
        """Get edge pairs to process, optionally filtered to pair containing edge_hash."""
        all_pairs = wheel.edge_pairs

        if self.edge_hash is None:
            return all_pairs

        # Filter to the pair containing the specified edge
        for ac_edge, re_edge in all_pairs:
            if (ac_edge.hash and ac_edge.hash.startswith(self.edge_hash)) or \
               (re_edge.hash and re_edge.hash.startswith(self.edge_hash)):
                return [(ac_edge, re_edge)]

        raise ValueError(
            f"Edge {self.edge_hash} not found in Wheel edge pairs"
        )

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get input context from digests (falls back to full content if no digest)."""
        from dialectical_framework.graph.repositories.input_repository import \
            InputRepository
        from dialectical_framework.utils.input_context import input_context

        repo = InputRepository()
        inputs = repo.get_all()

        return await input_context(inputs, input_resolver)

    def _create_transformation(
        self,
        nexus: Nexus,
        ac_edge: Transition,
        source_segment: WheelSegment,
        target_segment: WheelSegment,
        tetrad: TransformationTetradDto,
    ) -> Transformation:
        """
        Create a Transformation node with all 6 positions, scoped to Nexus and edge.

        Ac-side (Ac, Ac+, Ac-) uses this edge's segments:
        - source_segment → T-side, target_segment → A-side

        Re-side (Re, Re+, Re-) uses opposite segments:
        - source_segment.opposite → Re source, target_segment.opposite → Re target
        """
        # Ac-side components from this edge
        t_result = source_segment.t.get()
        t_minus_result = source_segment.t_minus.get()
        t_plus_result = source_segment.t_plus.get()
        a_result = target_segment.t.get()
        a_plus_result = target_segment.t_plus.get()
        a_minus_result = target_segment.t_minus.get()

        # Re-side components from opposite edge
        opp_source = source_segment.opposite
        opp_target = target_segment.opposite
        re_source_result = opp_source.t.get()
        re_source_minus_result = opp_source.t_minus.get()
        re_source_plus_result = opp_source.t_plus.get()
        re_target_result = opp_target.t.get()
        re_target_plus_result = opp_target.t_plus.get()
        re_target_minus_result = opp_target.t_minus.get()

        if not all([
            t_result, t_minus_result, t_plus_result,
            a_result, a_plus_result, a_minus_result,
            re_source_result, re_source_minus_result, re_source_plus_result,
            re_target_result, re_target_plus_result, re_target_minus_result,
        ]):
            raise ValueError(
                "Segments missing required components for transformation"
            )

        assert t_result is not None
        assert t_minus_result is not None
        assert t_plus_result is not None
        assert a_result is not None
        assert a_plus_result is not None
        assert a_minus_result is not None
        assert re_source_result is not None
        assert re_source_minus_result is not None
        assert re_source_plus_result is not None
        assert re_target_result is not None
        assert re_target_plus_result is not None
        assert re_target_minus_result is not None

        t, _ = t_result
        t_minus, _ = t_minus_result
        t_plus, _ = t_plus_result
        a, _ = a_result
        a_plus, _ = a_plus_result
        a_minus, _ = a_minus_result

        re_src, _ = re_source_result
        re_src_minus, _ = re_source_minus_result
        re_src_plus, _ = re_source_plus_result
        re_tgt, _ = re_target_result
        re_tgt_plus, _ = re_target_plus_result
        re_tgt_minus, _ = re_target_minus_result

        # Create Transformation node scoped to Nexus + edge
        transformation = Transformation()
        transformation.set_nexus(nexus)
        transformation.set_on_edge(ac_edge)
        transformation.save()
        self._report.node_created(transformation)

        # === Ac-side (this edge's segments) ===

        # Ac (neutral): T → A
        # Note: tetrad.ac has insight/proactiveness from generation, but we intentionally
        # don't store them. Neutral positions are category reference points — their
        # proactiveness is derivable from Ac+'s label, and insight is less meaningful here.
        # AcRelationship/ReRelationship extend PolarityRelationship (no scoring fields)
        # to preserve the semantic distinction from scored +/- positions.
        ac_transition = self._create_transition(
            headline=tetrad.ac.headline,
            statement=tetrad.ac.statement,
            source=t,
            target=a,
            explanation=tetrad.ac.explanation,
            haiku=tetrad.ac.haiku,
        )
        transformation.ac.connect(
            ac_transition,
            relationship=AcRelationship(
                alias=POSITION_AC,
                heuristic_similarity=None,
            ),
        )
        self._report.node_created(ac_transition, meta={"position": POSITION_AC})
        self._report.relationship_created(
            transformation.ac, transformation, ac_transition,
            meta={"position": POSITION_AC},
        )

        # Ac+: T- → A+
        ac_plus_transition = self._create_transition(
            headline=tetrad.ac_plus.headline,
            statement=tetrad.ac_plus.statement,
            source=t_minus,
            target=a_plus,
            explanation=tetrad.ac_plus.explanation,
            haiku=tetrad.ac_plus.haiku,
        )
        transformation.ac_plus.connect(
            ac_plus_transition,
            relationship=AcPlusRelationship(
                alias=POSITION_AC_PLUS,
                heuristic_similarity=tetrad.ac_plus_hs,
                insight=tetrad.ac_plus.insight,
                proactiveness=tetrad.ac_plus.proactiveness,
            ),
        )
        self._report.node_created(
            ac_plus_transition, meta={"position": POSITION_AC_PLUS}
        )
        self._report.relationship_created(
            transformation.ac_plus, transformation, ac_plus_transition,
            meta={"position": POSITION_AC_PLUS},
        )

        # Ac-: T+ → A-
        ac_minus_transition = self._create_transition(
            headline=tetrad.ac_minus.headline,
            statement=tetrad.ac_minus.statement,
            source=t_plus,
            target=a_minus,
            explanation=tetrad.ac_minus.explanation,
            haiku=tetrad.ac_minus.haiku,
        )
        transformation.ac_minus.connect(
            ac_minus_transition,
            relationship=AcMinusRelationship(
                alias=POSITION_AC_MINUS,
                heuristic_similarity=None,
                insight=tetrad.ac_minus.insight,
                proactiveness=tetrad.ac_minus.proactiveness,
            ),
        )
        self._report.node_created(
            ac_minus_transition, meta={"position": POSITION_AC_MINUS}
        )
        self._report.relationship_created(
            transformation.ac_minus, transformation, ac_minus_transition,
            meta={"position": POSITION_AC_MINUS},
        )

        # === Re-side (opposite edge's segments) ===

        # Re (neutral): opp_source → opp_target
        re_transition = self._create_transition(
            headline=tetrad.re.headline,
            statement=tetrad.re.statement,
            source=re_src,
            target=re_tgt,
            explanation=tetrad.re.explanation,
            haiku=tetrad.re.haiku,
        )
        transformation.re.connect(
            re_transition,
            relationship=ReRelationship(
                alias=POSITION_RE,
                heuristic_similarity=None,
            ),
        )
        self._report.node_created(re_transition, meta={"position": POSITION_RE})
        self._report.relationship_created(
            transformation.re, transformation, re_transition,
            meta={"position": POSITION_RE},
        )

        # Re+: opp_source.neg → opp_target.pos
        re_plus_transition = self._create_transition(
            headline=tetrad.re_plus.headline,
            statement=tetrad.re_plus.statement,
            source=re_src_minus,
            target=re_tgt_plus,
            explanation=tetrad.re_plus.explanation,
            haiku=tetrad.re_plus.haiku,
        )
        transformation.re_plus.connect(
            re_plus_transition,
            relationship=RePlusRelationship(
                alias=POSITION_RE_PLUS,
                heuristic_similarity=tetrad.re_plus_hs,
                insight=tetrad.re_plus.insight,
                proactiveness=tetrad.re_plus.proactiveness,
            ),
        )
        self._report.node_created(
            re_plus_transition, meta={"position": POSITION_RE_PLUS}
        )
        self._report.relationship_created(
            transformation.re_plus, transformation, re_plus_transition,
            meta={"position": POSITION_RE_PLUS},
        )

        # Re-: opp_source.pos → opp_target.neg
        re_minus_transition = self._create_transition(
            headline=tetrad.re_minus.headline,
            statement=tetrad.re_minus.statement,
            source=re_src_plus,
            target=re_tgt_minus,
            explanation=tetrad.re_minus.explanation,
            haiku=tetrad.re_minus.haiku,
        )
        transformation.re_minus.connect(
            re_minus_transition,
            relationship=ReMinusRelationship(
                alias=POSITION_RE_MINUS,
                heuristic_similarity=None,
                insight=tetrad.re_minus.insight,
                proactiveness=tetrad.re_minus.proactiveness,
            ),
        )
        self._report.node_created(
            re_minus_transition, meta={"position": POSITION_RE_MINUS}
        )
        self._report.relationship_created(
            transformation.re_minus, transformation, re_minus_transition,
            meta={"position": POSITION_RE_MINUS},
        )

        # Commit transformation
        transformation.commit()
        self._report.node_committed(transformation)

        return transformation

    def _create_transition(
        self,
        headline: str,
        statement: str,
        source: Statement,
        target: Statement,
        explanation: str,
        haiku: str,
    ) -> Transition:
        """
        Create a Transition node between components.

        Args:
            headline: Short headline (~7 words) - stored on Transition.instruction
            statement: Fuller statement (longer than headline) - stored on Transition.summary
            source: The source component (e.g., T-)
            target: The target component (e.g., A+)
            explanation: Full reasoning - stored on Rationale.text (evidence/justification)
            haiku: 3-line poem - stored on Transition.haiku

        Returns:
            The committed Transition node
        """
        transition = Transition(
            instruction=headline,
            summary=statement,
            haiku=haiku,
        )
        transition.set_source(source)
        transition.set_target(target)
        transition.commit()

        rationale = Rationale(text=explanation)
        rationale.set_explanation_target(transition)
        rationale.commit()
        self._report.node_created(rationale)

        return transition


@llm.tool
async def explore_transformations(
    wheel_hash: Annotated[str, Field(description="Hash of the Wheel to generate transformations for")],
    edge_hash: Annotated[str | None, Field(description="Specific edge hash to process. If None, processes all edges.")] = None,
) -> str:
    """Generate Action-Reflection transformations for a Wheel's edges — practical navigation recipes showing how to move between dialectical positions. Each transformation has 6 positions (Ac, Ac+, Ac-, Re, Re+, Re-) describing actions and reflections at different insight levels."""
    concern = ExploreTransformations(wheel_hash=wheel_hash, edge_hash=edge_hash)
    await concern.resolve()
    return str(concern.report)
