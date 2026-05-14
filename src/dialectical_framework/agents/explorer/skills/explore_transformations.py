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

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
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

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.protocols.input_resolver import InputResolver


@dataclass
class _EdgeProcessingData:
    """Typed intermediate data for edge pair processing."""

    existing: bool = False
    skip: bool = False
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
            self._report.summary = f"No edge pairs found for Wheel {wheel.short_hash}"
            return ExploreTransformationsResult()

        # 3. Get input text from scope
        input_text = await self._get_input_text()

        # 4. Process each edge pair — both edges get Transformations
        all_existing: list[Transformation] = []
        all_new: list[Transformation] = []
        last_apexes: Optional[ApexDerivationResultDto] = None

        for edge_a, edge_b in edge_pairs:
            existing, new, apexes = await self._process_edge_pair(
                wheel, nexus, edge_a, edge_b, input_text
            )
            all_existing.extend(existing)
            all_new.extend(new)
            if apexes:
                last_apexes = apexes

        # 5. Audit new transformations for feasibility
        if all_new:
            from dialectical_framework.concerns.transformation_audit import TransformationAudit
            for tr in all_new:
                auditor = TransformationAudit()
                await auditor.resolve(tr, input_text)
                self._report = self._report.merge(auditor.report)

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

        return ExploreTransformationsResult(
            existing=all_existing,
            new=all_new,
            apexes=last_apexes,
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

        Phase 1: Extract Ac+ candidates for both edges independently.
        Phase 2: Generate tetrads for each edge, passing the opposite Ac+ for Re-side.

        Returns:
            Tuple of (existing, new, apexes)
        """
        from dialectical_framework.graph.repositories.transformation_repository import TransformationRepository

        tr_repo = TransformationRepository()
        all_existing: list[Transformation] = []
        all_new: list[Transformation] = []
        last_apexes: Optional[ApexDerivationResultDto] = None

        # Phase 1: Extract Ac+ for both edges (check existing first)
        edge_data: dict[str, _EdgeProcessingData] = {}
        for edge in (edge_a, edge_b):
            assert edge.hash is not None
            existing = tr_repo.find_by_edge(edge=edge)
            if existing:
                all_existing.extend(existing)
                edge_data[edge.hash] = _EdgeProcessingData(existing=True)
                continue

            source_segment = edge.get_source_wheel_segment()
            target_segment = edge.get_target_wheel_segment()
            if not source_segment or not target_segment:
                edge_data[edge.hash] = _EdgeProcessingData(skip=True)
                continue
            if not source_segment.is_complete() or not target_segment.is_complete():
                edge_data[edge.hash] = _EdgeProcessingData(skip=True)
                continue

            apex_service = ApexDerivation()
            apexes = await apex_service.resolve(edge, input_text)
            self._report = self._report.merge(apex_service.report)
            last_apexes = apexes

            extractor = ActionExtraction()
            ac_candidates = await extractor.resolve(
                edge, input_text,
                not_like_these=wheel.transformations,
            )
            self._report = self._report.merge(extractor.report)

            edge_data[edge.hash] = _EdgeProcessingData(
                ac_candidates=ac_candidates or [],
                apexes=apexes,
                source_segment=source_segment,
                target_segment=target_segment,
            )

        # Phase 2: Generate tetrads using opposite Ac+ for Re-side
        for edge, opposite_edge in [(edge_a, edge_b), (edge_b, edge_a)]:
            assert edge.hash is not None
            assert opposite_edge.hash is not None
            data = edge_data.get(edge.hash)
            if not data or data.existing or data.skip:
                continue

            if not data.ac_candidates:
                continue

            source_segment = data.source_segment
            target_segment = data.target_segment
            apexes = data.apexes
            if not source_segment or not target_segment or not apexes:
                continue

            # Get opposite edge's Ac+ candidates for Re-side context
            opp_data = edge_data.get(opposite_edge.hash)
            opp_ac_candidates = opp_data.ac_candidates if opp_data else []

            for ac_plus in data.ac_candidates:
                opposite_ac = self._find_matching_category(
                    opp_ac_candidates, ac_plus.insight_label
                )
                if not opposite_ac:
                    continue

                generator = TransformationGeneration()
                tetrad = await generator.resolve(
                    edge, ac_plus, opposite_ac, apexes, input_text
                )
                self._report = self._report.merge(generator.report)

                transformation = self._create_transformation(
                    nexus, edge, source_segment, target_segment, tetrad,
                )
                all_new.append(transformation)

        return all_existing, all_new, last_apexes

    @staticmethod
    def _find_matching_category(
        candidates: list[ActionCandidateResultDto],
        insight_label: str,
    ) -> Optional[ActionCandidateResultDto]:
        """Find an Ac+ candidate matching the given insight category."""
        if not candidates:
            return None

        # Determine category from insight label
        from dialectical_framework.concerns.ac_re_taxonomy import insight_label_to_value
        try:
            target_value = insight_label_to_value(insight_label)
        except ValueError:
            return candidates[0]

        # Categories: Generative (0.6-1.0), Configurational (0.4-0.5), Corrective (0.0-0.3)
        if target_value >= 0.6:
            target_category = "generative"
        elif target_value >= 0.4:
            target_category = "configurational"
        else:
            target_category = "corrective"

        for candidate in candidates:
            try:
                val = insight_label_to_value(candidate.insight_label)
            except ValueError:
                continue
            if val >= 0.6 and target_category == "generative":
                return candidate
            elif 0.4 <= val < 0.6 and target_category == "configurational":
                return candidate
            elif val < 0.4 and target_category == "corrective":
                return candidate

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
        """Get concatenated text from all inputs in scope."""
        from dialectical_framework.graph.repositories.input_repository import \
            InputRepository

        repo = InputRepository()
        inputs = repo.get_all()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)

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

        # === Ac-side (this edge's segments) ===

        # Ac (neutral): T → A
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

        # Commit transformation
        transformation.commit()
        self._report.node_created(transformation)

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
            statement: Fuller statement (1-15 words) - stored on Transition.summary
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
    wheel_hash: str = Field(description="Hash of the Wheel to generate transformations for"),
    edge_hash: Optional[str] = Field(default=None, description="Specific edge hash to process. If None, processes all edges."),
) -> str:
    """Generate Action-Reflection transformations for a Wheel's edges — practical navigation recipes showing how to move between dialectical positions. Each transformation has 6 positions (Ac, Ac+, Ac-, Re, Re+, Re-) describing actions and reflections at different insight levels."""
    concern = ExploreTransformations(wheel_hash=wheel_hash, edge_hash=edge_hash)
    await concern.resolve()
    return str(concern.report)
