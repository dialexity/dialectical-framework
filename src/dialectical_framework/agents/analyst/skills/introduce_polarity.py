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
from dialectical_framework.utils.input_context import compose_context
from dialectical_framework.utils.progress import (expect_progress,
                                                 progress_key,
                                                 progress_scope,
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

    def __init__(
        self,
        thesis: str,
        antithesis: str,
        text: str = "",
        input_hashes: list[str] | None = None,
    ) -> None:
        self.thesis_text = thesis.strip()
        self.antithesis_text = antithesis.strip()
        self.text = text
        #: The material these two poles come from — `anchor` passes the Input
        #: that keeps the person's turn verbatim. Read as the context both
        #: poles are classified against (instead of every Input in the case),
        #: and linked to both Statements as their source (`HAS_STATEMENT`), so
        #: everything downstream can find the tension's own words
        #: (`inputs_for_statements`). Same contract as `AnchorTheses`.
        self.input_hashes = input_hashes
        self._source_inputs_cache: list | None = None

    async def resolve(self) -> IntroducePolarityResult:
        """Introduce a single T-A tension with HS score: the three phases in a
        row (`prepare`, `classify_opposition`, `record_opposition`)."""
        prepared = await self.prepare()
        if not prepared.primary_polarity_hash:
            return prepared
        classification = await self.classify_opposition()
        return self.record_opposition(classification)

    # ------------------------------------------------------------------
    # The three phases `resolve()` composes. Split (2026-10-02) so a caller
    # can OVERLAP the opposition's evaluation with work that needs only the
    # committed pair: `SketchTetrad` runs `classify_opposition()` (pure LLM,
    # writes nothing) concurrently with `ExpandPolarity` (which writes), then
    # `record_opposition()` on the parent task — one writer at a time, and the
    # ~12 s of `AntithesisClassification` come off the wall clock instead of
    # standing in the chain. The Polarity can be committed before its HS is
    # known because its hash is the sorted T/A hashes alone; HS is an edge
    # property, written by `update_properties`.
    # ------------------------------------------------------------------

    async def prepare(self) -> IntroducePolarityResult:
        """Phase 1: classify both poles (gathered), commit them, connect the
        opposition, commit the Polarity with the HS still unknown."""
        if not self.thesis_text or not self.antithesis_text:
            self._report.ok = False
            self._report.summary = "Both thesis and antithesis text are required"
            return IntroducePolarityResult()
        input_text = await self._get_input_text()
        context = compose_context(self.text, input_text)
        self._context = context
        expect_progress(self.PROGRESS_STEPS)
        report_progress("Taking in both sides of what you described")
        thesis_draft, antithesis_draft = await asyncio.gather(
            self._classify_statement(self.thesis_text, context),
            self._classify_statement(self.antithesis_text, context),
        )
        thesis_stmt = self._commit_statement(thesis_draft)
        antithesis_stmt = self._commit_statement(antithesis_draft)
        thesis_stmt.oppositions.connect(antithesis_stmt)
        self._report.relationship_created(
            thesis_stmt.oppositions, thesis_stmt, antithesis_stmt
        )
        self._prepared = (thesis_stmt, antithesis_stmt)
        self._polarity, self._polarity_created = self._ensure_polarity(
            thesis_stmt, antithesis_stmt, heuristic_similarity=None
        )
        return IntroducePolarityResult(
            primary_polarity_hash=self._polarity.hash,
            thesis_hash=thesis_stmt.hash,
            antithesis_hash=antithesis_stmt.hash,
        )

    async def classify_opposition(self):
        """Phase 2: the opposition's HS, Mode and Arousal — LLM only, no
        graph writes, so it may run concurrently with a writer."""
        thesis_stmt, antithesis_stmt = self._prepared
        report_progress("Weighing how strongly the two pull against each other")
        classifier = AntithesisClassification()
        classification = await classifier.resolve(
            thesis=thesis_stmt,
            antithesis_statement=antithesis_stmt.text,
            text=self._context,
        )
        self._classifier_report = classifier.report
        return classification

    def record_opposition(self, classification) -> IntroducePolarityResult:
        """Phase 3: write what phase 2 found — the A edge's HS (on a Polarity
        this call created; an existing one keeps its own), the Mode and Arousal
        estimations — and build the report. Parent task only."""
        thesis_stmt, antithesis_stmt = self._prepared
        self._report = self._report.merge(self._classifier_report)
        primary_polarity = self._polarity
        if self._polarity_created:
            primary_polarity.a.update_properties(
                antithesis_stmt,
                {"heuristic_similarity": classification.heuristic_similarity},
            )
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
        else:
            self._report.artifacts["primary_polarity_source"] = "existing"

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

    def _ensure_polarity(
        self, thesis_stmt: Statement, antithesis_stmt: Statement, *, heuristic_similarity
    ) -> tuple[Polarity, bool]:
        """The Polarity for this pair: the existing one, or a new one committed
        now (HS may still be None — see `record_opposition`)."""
        existing = PolarityRepository().find_by_tension(thesis_stmt, antithesis_stmt)
        if existing:
            return existing[0], False
        polarity = Polarity()
        polarity.set_t(thesis_stmt, heuristic_similarity=1.0)
        polarity.set_a(antithesis_stmt, heuristic_similarity=heuristic_similarity)
        polarity.commit()
        return polarity, True

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
        for input_node in self._source_inputs():
            # Idempotent: `HAS_STATEMENT` is directed, so a repeat connect would
            # duplicate the edge — a pole shared with an earlier anchor on the
            # same turn, or the dedup upsert above returning an existing node.
            if any(n._id == stmt._id for n, _rel in input_node.statements.all()):
                continue
            input_node.statements.connect(stmt)
            self._report.relationship_created(input_node.statements, input_node, stmt)

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

    def _source_inputs(self) -> list:
        """The Inputs named by `input_hashes`, resolved once per call. Unresolved
        hashes are recorded, not raised — the tension does not depend on its
        provenance edges (same stance as `AnchorTheses._get_inputs`)."""
        if not self.input_hashes:
            return []
        cached = self._source_inputs_cache
        if cached is None:
            from dialectical_framework.graph.nodes.input import Input
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            cached = NodeRepository().find_by_hashes(self.input_hashes, node_type=Input)
            unresolved = len(self.input_hashes) - len(cached)
            if unresolved > 0:
                self._report.artifacts["unresolved_input_hashes"] = unresolved
            self._source_inputs_cache = cached
        return cached

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """The material the poles are classified against: the named source
        Inputs when there are any, every Input in the case otherwise."""
        from dialectical_framework.utils.input_context import input_context

        inputs = self._source_inputs() or InputRepository().get_all()
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
    # Stage `anchor`, matching `anchor_theses` and the Advisor's `anchor` tool — the
    # same deferral argument as there, and this is the leg that tool actually calls
    # first, so under it this scope never installs anything.
    #
    # Keyed on the two poles the person named, exactly as `advisor.anchor` keys its
    # own stream: same arguments, same digest, so calling this tool directly and
    # calling `anchor` with the same wording key the same stream.
    key = progress_key(thesis, antithesis)
    with progress_scope("anchor", key=key):
        concern = IntroducePolarity(thesis=thesis, antithesis=antithesis, text=text)
        await concern.resolve()
        return str(concern.report)
