"""
ExploreTransformations: Subagent for generating Action-Reflection transformations for Perspectives.

Orchestrates the transformation generation pipeline:
1. Derives contextual apexes (Re+ and Ac+) for the PP
2. Extracts Ac+ candidates along the Insight axis
3. Generates full tetrads from each Ac+ candidate
4. Creates Transformation nodes in the graph

Usage:
    # Programmatic use
    agent = ExploreTransformations(perspective_hash="abc123...")
    result = await agent.resolve()
    for t in result.all:
        print(f"{t}")

    # LLM tool use
    agent = ExploreTransformations(perspective_hash="abc123...")
    json_result = await agent.call()  # Returns JSON string
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.action_extraction import ActionExtraction
from dialectical_framework.concerns.positive_ac_re_apex_derivation import (
    ApexDerivation, ApexDerivationResultDto)
from dialectical_framework.concerns.transformation_generation import (
    TransformationGeneration, TransformationTetradDto)
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transformation import (
    POSITION_AC, POSITION_AC_MINUS, POSITION_AC_PLUS, POSITION_RE,
    POSITION_RE_MINUS, POSITION_RE_PLUS, Transformation)
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.relationships.polarity_relationship import (
    AcMinusRelationship, AcPlusRelationship, AcRelationship,
    ReMinusRelationship, RePlusRelationship, ReRelationship)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.protocols.input_resolver import InputResolver


@dataclass
class ExploreTransformationsResult:
    """Result from the ExploreTransformations."""

    existing: list[Transformation]
    new: list[Transformation]
    apexes: ApexDerivationResultDto

    @property
    def all(self) -> list[Transformation]:
        """Get all transformations (existing + new)."""
        return self.existing + self.new


class ExploreTransformations(
    BaseTool, ReasonableConcern[ExploreTransformationsResult]
):
    """
    Subagent for generating Action-Reflection transformations for Perspectives.

    This agent orchestrates the full transformation generation pipeline,
    producing multiple transformation alternatives for a single Perspective.

    Dual interface:
    - resolve() returns ExploreTransformationsResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    perspective_hash: str = Field(
        description="Hash (full or prefix) of the Perspective to transform"
    )

    _report: ExecutionReport = PrivateAttr()

    async def call(self) -> str:
        """Resolve transformation generation and return ExecutionReport as JSON (for LLM tool use)."""
        await self.resolve()
        return str(self._report)

    async def resolve(self) -> ExploreTransformationsResult:
        """
        Resolve the transformation generation pipeline.

        Returns:
            ExploreTransformationsResult with existing and new transformations
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # 1. Resolve and validate PP
        pp = self._resolve_perspective()
        if not pp.is_complete():
            raise ValueError(
                f"Perspective {pp.short_hash} must have all 6 positions to generate transformations"
            )

        # 2. Get existing committed transformations
        existing = [t for t, _ in pp.transformations.all() if t.is_committed]

        # 3. Get input text from scope
        input_text = await self._get_input_text()

        # 4. Derive apexes for this PP context
        apex_service = ApexDerivation()
        apexes = await apex_service.resolve(pp, input_text)
        self._report.merge(apex_service.report)

        # 5. Extract Ac+ candidates (avoiding existing)
        extractor = ActionExtraction()
        ac_candidates = await extractor.resolve(pp, input_text, not_like_these=existing)
        self._report.merge(extractor.report)

        if not ac_candidates:
            self._report.summary = f"No new Ac+ candidates for PP {pp.short_hash}"
            return ExploreTransformationsResult(
                existing=existing,
                new=[],
                apexes=apexes,
            )

        # 6. For each Ac+, generate full tetrad and create graph nodes
        new_transformations = []
        for ac_plus in ac_candidates:
            generator = TransformationGeneration()
            tetrad = await generator.resolve(pp, ac_plus, apexes, input_text)
            self._report.merge(generator.report)

            # 6. Create graph nodes
            transformation = self._create_transformation(pp, tetrad)
            new_transformations.append(transformation)

        # Summary
        self._report.artifacts["pp_hash"] = pp.short_hash
        self._report.artifacts["existing_count"] = len(existing)
        self._report.artifacts["new_count"] = len(new_transformations)
        self._report.summary = (
            f"Generated {len(new_transformations)} new transformation(s) for PP {pp.short_hash} "
            f"({len(existing)} existing)"
        )

        return ExploreTransformationsResult(
            existing=existing,
            new=new_transformations,
            apexes=apexes,
        )

    def _resolve_perspective(self) -> Perspective:
        """Resolve Perspective from hash or prefix."""
        from dialectical_framework.graph.nodes.perspective import Perspective
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        repo = NodeRepository()
        node = repo.find_by_hash(self.perspective_hash, node_type=Perspective)
        if node is None:
            raise ValueError(f"Perspective not found: {self.perspective_hash}")
        return node

    @inject
    async def _get_input_text(
        self,
        input_resolver: "InputResolver" = Provide[DI.input_resolver],
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
        pp: Perspective,
        tetrad: TransformationTetradDto,
    ) -> Transformation:
        """
        Create a Transformation node with all 6 positions.

        Args:
            pp: The containing Perspective
            tetrad: The generated tetrad with category reframings and aspects

        Returns:
            The committed Transformation node
        """
        # Get all PP components for transitions
        t_result = pp.t.get()
        t_minus_result = pp.t_minus.get()
        t_plus_result = pp.t_plus.get()
        a_result = pp.a.get()
        a_plus_result = pp.a_plus.get()
        a_minus_result = pp.a_minus.get()

        if not all(
            [
                t_result,
                t_minus_result,
                t_plus_result,
                a_result,
                a_plus_result,
                a_minus_result,
            ]
        ):
            raise ValueError(
                "Perspective missing required components for transformation"
            )

        t, _ = t_result
        t_minus, _ = t_minus_result
        t_plus, _ = t_plus_result
        a, _ = a_result
        a_plus, _ = a_plus_result
        a_minus, _ = a_minus_result

        # Create Transformation node
        transformation = Transformation()
        transformation.set_perspective(pp)
        transformation.save()

        # Create neutral category transitions (Ac: T → A, Re: A → T)
        # Ac (Action category): contextualized taxonomy category for T → A
        ac_transition = self._create_transition(
            headline=tetrad.ac.headline,
            statement=tetrad.ac.statement,
            source=t,
            target=a,
            explanation=tetrad.ac.explanation,
        )
        transformation.ac.connect(
            ac_transition,
            relationship=AcRelationship(
                alias=POSITION_AC,
                heuristic_similarity=None,
            ),
        )
        self._report.node_created(ac_transition, meta={"position": POSITION_AC})

        # Re (Reflection category): contextualized taxonomy category for A → T
        re_transition = self._create_transition(
            headline=tetrad.re.headline,
            statement=tetrad.re.statement,
            source=a,
            target=t,
            explanation=tetrad.re.explanation,
        )
        transformation.re.connect(
            re_transition,
            relationship=ReRelationship(
                alias=POSITION_RE,
                heuristic_similarity=None,
            ),
        )
        self._report.node_created(re_transition, meta={"position": POSITION_RE})

        # Create transitions for each position using PP aspects as source/target
        # Ac+: T- → A+ (positive action: escape T- problems toward A+ benefits)
        ac_plus_transition = self._create_transition(
            headline=tetrad.ac_plus.headline,
            statement=tetrad.ac_plus.statement,
            source=t_minus,
            target=a_plus,
            explanation=tetrad.ac_plus.explanation,
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

        # Re+: A- → T+ (positive reflection: escape A- problems toward T+ benefits)
        re_plus_transition = self._create_transition(
            headline=tetrad.re_plus.headline,
            statement=tetrad.re_plus.statement,
            source=a_minus,
            target=t_plus,
            explanation=tetrad.re_plus.explanation,
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

        # Re-: A+ → T- (negative reflection: action without reflection leads here)
        re_minus_transition = self._create_transition(
            headline=tetrad.re_minus.headline,
            statement=tetrad.re_minus.statement,
            source=a_plus,
            target=t_minus,
            explanation=tetrad.re_minus.explanation,
        )
        transformation.re_minus.connect(
            re_minus_transition,
            relationship=ReMinusRelationship(
                alias=POSITION_RE_MINUS,
                heuristic_similarity=None,  # Negative aspects don't have HS
                insight=tetrad.re_minus.insight,
                proactiveness=tetrad.re_minus.proactiveness,
            ),
        )
        self._report.node_created(
            re_minus_transition, meta={"position": POSITION_RE_MINUS}
        )

        # Ac-: T+ → A- (negative action: reflection without action leads here)
        ac_minus_transition = self._create_transition(
            headline=tetrad.ac_minus.headline,
            statement=tetrad.ac_minus.statement,
            source=t_plus,
            target=a_minus,
            explanation=tetrad.ac_minus.explanation,
        )
        transformation.ac_minus.connect(
            ac_minus_transition,
            relationship=AcMinusRelationship(
                alias=POSITION_AC_MINUS,
                heuristic_similarity=None,  # Negative aspects don't have HS
                insight=tetrad.ac_minus.insight,
                proactiveness=tetrad.ac_minus.proactiveness,
            ),
        )
        self._report.node_created(
            ac_minus_transition, meta={"position": POSITION_AC_MINUS}
        )

        # Commit transformation
        transformation.commit()
        self._report.node_created(transformation)

        return transformation

    def _create_transition(
        self,
        headline: str,
        statement: str,
        source: DialecticalComponent,
        target: DialecticalComponent,
        explanation: str,
    ) -> Transition:
        """
        Create a Transition node between PP aspects.

        Args:
            headline: Short headline (~7 words) - stored on Transition.instruction and Rationale.headline
            statement: Fuller statement (1-15 words) - stored on Rationale.summary
            source: The source component from the Perspective (e.g., T-)
            target: The target component from the Perspective (e.g., A+)
            explanation: Full explanation - stored on Rationale.text

        Returns:
            The committed Transition node
        """
        transition = Transition(instruction=headline)
        transition.set_source(source)
        transition.set_target(target)
        transition.commit()

        # Add rationale with three-tier structure:
        # - headline: short essence (~7 words)
        # - summary: fuller statement (1-15 words)
        # - text: full explanation
        rationale = Rationale(
            headline=headline,
            summary=statement,
            text=explanation,
        )
        rationale.set_explanation_target(transition)
        rationale.commit()
        self._report.node_created(rationale)

        return transition
