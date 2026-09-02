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

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, NamedTuple, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.statement_classification import \
    ClassificationResult, StatementClassification
from dialectical_framework.concerns.statement_headline import StatementHeadline
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.estimation import (ArousalEstimation,
                                                          ModeEstimation)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository
from dialectical_framework.utils.progress import (expect_progress,
                                                 report_progress)

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class _StatementDraft(NamedTuple):
    """One pole's two concern results, before anything has been written.

    Exists to keep `_classify_statement` free of side effects. Both poles' LLM
    work runs in gathered tasks; everything that touches the graph or the report
    is done afterwards by `_commit_statement`, on the parent, one pole at a time.
    """

    classifier: StatementClassification
    headliner: StatementHeadline
    classification: ClassificationResult
    headline: str


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

    #: Steps `resolve()` reports, for callers sizing a progress denominator.
    #: Pinned against the actual `report_progress` calls by `tests/test_progress.py`.
    PROGRESS_STEPS = 2

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

        # 1-2. Create or find both Statements. The two poles are resolved
        # CONCURRENTLY: neither reads the other, each builds its own concerns with
        # its own conversation, and the `OPPOSITE_OF` connect below is the first
        # thing that needs both. They were sequential `await`s purely because the
        # code was written for one pole and called twice, which cost a whole stage
        # of the tool's ~40s wall clock.
        #
        # Two measurements, and they disagree — quote whichever matches the question.
        # THIS STAGE frees ~6.2s: the two poles' provider intervals overlap almost
        # perfectly (12.5s serial -> 6.3s gathered, median, `probe_pole_overlap.py`),
        # slightly MORE than the ~5.8s the per-DTO arithmetic predicted. The TOOL
        # moved ~3.3s (median working 40.1s -> 36.8s, parallelism 1.15 -> 1.33,
        # `probe_anchor_retry_cost.py`). The difference is ~2.5s against the
        # PREDICTION (5.8 - 3.3, which is the base the probe pre-registered) or
        # ~2.9s against this measurement (6.2 - 3.3) — say which.
        #
        # Either way it is NOT in this stage. The poles cost near-identically
        # (median |A-B| 0.15s over 5 rows; the min-vs-mean bias is 0.33s, which
        # is mean spread 0.66s / 2 on the retry-free same-DTO-mix subgroup — a
        # different statistic on a different subgroup, NOT half the median).
        # There is no interference: median gathered wall equals median max(busy),
        # within 0.1s on every row, at 0.000s start skew. Contention is small and
        # not zero: +9% of provider time, which works out to ~0.5s of wall on the
        # larger of a gathered pair (derived, not printed), against a reference
        # pooled from a different Case regime. What is left is downstream overhead
        # growth, or imprecision in the 3.3s itself — a difference of medians at
        # n=3 with two retrying calls, against a directly measured 6.2s here.
        #
        # Only the LLM half is gathered. The commits and the report merges run
        # after, on this task, one pole at a time — GQLAlchemy is not
        # concurrency-safe, and `merge` returns a NEW report rather than mutating,
        # so two tasks assigning `self._report` would silently drop one pole's
        # nodes from the report. Same reason the order below is thesis-then-
        # antithesis: it keeps the report's node sequence identical to before.
        #
        # No `return_exceptions=True`, deliberately: a failing pole must abort the
        # whole tool, exactly as the sequential version did. The one thing it costs
        # is that the surviving pole's calls run on to completion in the background
        # and are discarded — wasted spend on an error path, never a wrong result,
        # since nothing has been committed at that point.
        expect_progress(self.PROGRESS_STEPS)
        report_progress("Taking in both sides of what you described")
        thesis_draft, antithesis_draft = await asyncio.gather(
            self._classify_statement(self.thesis_text, context),
            self._classify_statement(self.antithesis_text, context),
        )
        thesis_stmt = self._commit_statement(thesis_draft)
        antithesis_stmt = self._commit_statement(antithesis_draft)

        # 3. Connect OPPOSITE_OF
        thesis_stmt.oppositions.connect(antithesis_stmt)
        self._report.relationship_created(
            thesis_stmt.oppositions, thesis_stmt, antithesis_stmt
        )

        # 4. Classify the antithesis against the thesis (get HS)
        report_progress("Weighing how strongly the two pull against each other")
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
                primary_polarity.t,
                thesis_stmt,
                primary_polarity,
                patch={"heuristic_similarity": 1.0, "alias": "T"},
            )
            self._report.relationship_created(
                primary_polarity.a,
                antithesis_stmt,
                primary_polarity,
                patch={
                    "heuristic_similarity": classification.heuristic_similarity,
                    "alias": "A",
                },
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
            self._report.node_updated(
                mode_est, patch={"value": classification.mode_value}
            )
        if arousal_est:
            self._report.node_updated(
                arousal_est, patch={"value": classification.arousal_value}
            )

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
                "mode": classification.mode_value,
            }
        ]
        self._report.summary = (
            f"Introduced polarity: {thesis_stmt.text} vs {antithesis_stmt.text} "
            f"(HS: {classification.heuristic_similarity:.2f}, "
            f"Mode: {classification.mode_value:.1f})"
        )

        return result

    async def _classify_statement(self, text: str, context: str) -> _StatementDraft:
        """The LLM half of placing a Statement: NO graph writes and NO report
        mutation, so this is safe to run for both poles at once.

        This and `_commit_statement` replace `_resolve_statement`, which did both
        halves for one pole and was called twice. Deliberately NOT kept as a
        composition wrapper: nothing calls it, and a dead method still satisfies
        the class-scoped grep in
        `test_prompt_review_regressions.py::test_both_anchor_legs_condense_the_stored_text`,
        so leaving it would let that tripwire pass on code the tool no longer runs.

        The agent may pass verbose prose (the anchor path has no extraction step
        to clamp length), so condense to a headline in parallel with
        classification. Classification reads the full text for richer taxonomy
        anchoring; only the stored ``text`` becomes the headline. Both concerns
        therefore receive ``statement=text`` — the FULL text, not the headline.
        Feeding the classifier the condensed form instead would be invisible here
        and would degrade the meaning URI, which is a hash input and selects the
        taxonomy row every downstream aspect is generated against.
        """
        classifier = StatementClassification()
        headliner = StatementHeadline()
        result, headline = await asyncio.gather(
            classifier.resolve(statement=text, text=context),
            headliner.resolve(statement=text, text=context),
        )
        return _StatementDraft(classifier, headliner, result, headline)

    def _commit_statement(self, draft: _StatementDraft) -> Statement:
        """The graph half: MUST run on the parent task, one pole at a time.

        `commit()` is an upsert — a Statement with the same text reuses the
        existing node rather than duplicating it.

        Synchronous on purpose — there is nothing to await here, and a coroutine
        would invite a future caller to gather it, which is exactly what must not
        happen: `Statement.commit()` and `Rationale.commit()` go through
        GQLAlchemy, which is not concurrency-safe, and each `merge` below returns
        a new report that is then assigned to `self._report`.
        """
        classifier, headliner, result, headline = draft
        self._report = self._report.merge(classifier.report)
        self._report = self._report.merge(headliner.report)

        stmt = Statement(text=headline, meaning=result.meaning)
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
    text: Annotated[
        str, Field(description="Additional context for classification")
    ] = "",
) -> str:
    """Introduce a known thesis-antithesis tension directly as a Polarity. Classifies both statements, creates the Polarity node (T-A pair) with HS score. Use when the tension is already clear from conversation rather than needing extraction from source material."""
    concern = IntroducePolarity(thesis=thesis, antithesis=antithesis, text=text)
    await concern.resolve()
    return str(concern.report)
