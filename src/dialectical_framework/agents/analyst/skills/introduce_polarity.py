"""
IntroducePolarity: Skill for directly introducing a known T-A tension.

When the LLM recognizes a tension in conversation (e.g. "Stay married vs Get divorced"),
this skill introduces both statements into the vocabulary, creates the primary Polarity,
and computes its HS score.

Flow:
1. Classify thesis + antithesis (get meaning URIs)
2. Run AntithesisClassification to get HS for the primary pair
3. Create primary Polarity node

Usage:
    skill = IntroducePolarity(thesis="Stay married", antithesis="Get divorced")
    result = await skill.resolve()
    # result.primary_polarity_hash — the tension the LLM identified
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.estimation import (
    ArousalEstimation, ModeEstimation)
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


@dataclass
class IntroducePolarityResult:
    """Result of introducing a polarity."""

    primary_polarity_hash: Optional[str] = None
    thesis_hash: Optional[str] = None
    antithesis_hash: Optional[str] = None


class IntroducePolarity(ReasonableConcern[IntroducePolarityResult]):
    """
    Skill for directly introducing a known T-A tension into the graph.

    Classifies both statements, creates the primary Polarity with HS score.
    Use find_polarities to discover alternative antitheses separately.
    """

    def __init__(self, thesis: str, antithesis: str, text: str = "") -> None:
        self.thesis_text = thesis.strip()
        self.antithesis_text = antithesis.strip()
        self.text = text

    async def resolve(self) -> IntroducePolarityResult:
        """Introduce a single T-A tension with HS score."""

        if not self.thesis_text or not self.antithesis_text:
            self._report.ok = False
            self._report.summary = "Both thesis and antithesis text are required"
            return IntroducePolarityResult()

        input_text = await self._get_input_text()
        context = f"{input_text}\n\n{self.text}".strip() if self.text else input_text

        # 1. Create or find thesis Statement
        thesis_stmt = await self._resolve_statement(self.thesis_text, context)

        # 2. Create or find antithesis Statement
        antithesis_stmt = await self._resolve_statement(self.antithesis_text, context)

        # 3. Connect OPPOSITE_OF
        thesis_stmt.oppositions.connect(antithesis_stmt)
        self._report.relationship_created(
            thesis_stmt.oppositions, thesis_stmt, antithesis_stmt
        )

        # 4. Classify the antithesis against the thesis (get HS)
        classifier = AntithesisClassification()
        classification = await classifier.resolve(
            thesis=thesis_stmt,
            antithesis_statement=antithesis_stmt.text,
            text=context,
        )
        self._report = self._report.merge(classifier.report)

        # 5. Create primary Polarity
        pol_repo = PolarityRepository()
        existing_pols = pol_repo.find_by_tension(thesis_stmt, antithesis_stmt)

        if existing_pols:
            primary_polarity = existing_pols[0]
            self._report.artifacts["primary_polarity_source"] = "existing"
        else:
            primary_polarity = Polarity()
            primary_polarity.set_t(thesis_stmt, heuristic_similarity=1.0)
            primary_polarity.set_a(
                antithesis_stmt,
                heuristic_similarity=classification.heuristic_similarity,
            )
            primary_polarity.commit()
            self._report.node_created(primary_polarity)
            self._report.relationship_created(
                primary_polarity.t, thesis_stmt, primary_polarity,
                patch={"heuristic_similarity": 1.0, "alias": "T"},
            )
            self._report.relationship_created(
                primary_polarity.a, antithesis_stmt, primary_polarity,
                patch={"heuristic_similarity": classification.heuristic_similarity, "alias": "A"},
            )
            self._report.artifacts["primary_polarity_source"] = "created"

        # Persist Mode/Arousal estimations on the antithesis
        manager = EstimationManager()
        mode_est = manager.upsert_estimation(
            antithesis_stmt, ModeEstimation, classification.mode_value
        )
        arousal_est = manager.upsert_estimation(
            antithesis_stmt, ArousalEstimation, classification.arousal_value
        )
        if mode_est:
            self._report.node_updated(mode_est, patch={"value": classification.mode_value})
        if arousal_est:
            self._report.node_updated(arousal_est, patch={"value": classification.arousal_value})

        # Build result
        result = IntroducePolarityResult(
            primary_polarity_hash=primary_polarity.hash,
            thesis_hash=thesis_stmt.hash,
            antithesis_hash=antithesis_stmt.hash,
        )

        self._report.ok = True
        self._report.artifacts["primary_polarity_hash"] = primary_polarity.hash
        self._report.artifacts["thesis_hash"] = thesis_stmt.hash
        self._report.artifacts["antithesis_hash"] = antithesis_stmt.hash
        self._report.artifacts["polarities"] = [
            {
                "polarity_hash": primary_polarity.hash,
                "thesis_text": thesis_stmt.text,
                "antithesis_text": antithesis_stmt.text,
                "heuristic_similarity": classification.heuristic_similarity,
            }
        ]
        self._report.summary = (
            f"Introduced polarity: {thesis_stmt.text} vs {antithesis_stmt.text} "
            f"(HS: {classification.heuristic_similarity:.2f})"
        )

        return result

    async def _resolve_statement(self, text: str, context: str) -> Statement:
        """Classify and commit a Statement. Commit is an upsert — same text reuses existing node."""
        classifier = StatementClassification()
        result = await classifier.resolve(statement=text, text=context)
        self._report = self._report.merge(classifier.report)

        stmt = Statement(text=result.statement, meaning=result.meaning)
        stmt.commit()
        self._report.node_created(stmt)

        classification_label = "SIMPLE" if result.is_simple else "COMPLEX"
        rationale_text = (
            f"Classification: {classification_label}. {result.classification_reasoning}"
        )
        if result.taxonomy_reasoning:
            rationale_text += f" {result.taxonomy_reasoning}"

        rationale = Rationale(text=rationale_text)
        rationale.set_explanation_target(stmt)
        rationale.commit()
        self._report.node_created(rationale)

        return stmt

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


@llm.tool
async def introduce_polarity(
    thesis: Annotated[str, Field(description="The thesis statement text")],
    antithesis: Annotated[str, Field(description="The antithesis statement text")],
    text: Annotated[str, Field(description="Additional context for classification")] = "",
) -> str:
    """Introduce a known thesis-antithesis tension directly as a Polarity. Classifies both statements, creates the Polarity node (T-A pair) with HS score. Use when the tension is already clear from conversation rather than needing extraction from source material."""
    concern = IntroducePolarity(thesis=thesis, antithesis=antithesis, text=text)
    await concern.resolve()
    return str(concern.report)
