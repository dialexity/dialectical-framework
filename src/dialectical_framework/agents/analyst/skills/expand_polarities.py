"""
ExpandPolarity: Orchestrator for creating Perspectives from a Polarity.

Takes a Polarity (T-A pair) and creates Perspectives by adding aspects (T+, T-, A+, A-).

Usage:
    agent = ExpandPolarity(polarity_hash="abc123...")
    pps = await agent.resolve()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.aspect_generation import (
    AspectGeneration,
    AspectResult,
)
from dialectical_framework.concerns.statement_deduplication import (
    StatementDeduplication,
)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.relationships.explains_relationship import \
    ROLE_GROUNDING
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    Perspective,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship,
    APlusRelationship,
    HasPolarityRelationship,
    TMinusRelationship,
    TPlusRelationship,
)
from dialectical_framework.graph.repositories.statement_repository import (
    StatementRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver

logger = logging.getLogger(__name__)


class ExpandPolarity(ReasonableConcern[list[Perspective]]):
    """
    Orchestrate Perspective creation for a single Polarity (T-A tension).

    Creates Perspectives from a Polarity by generating and connecting aspects
    (T+, T-, A+, A-).

    Each call produces `count` NEW perspectives (alternative tetrads) for the
    Polarity, generated sequentially so each uses `not_like_these` (existing +
    already-generated-this-call) to ensure diversity. Any pre-existing partial
    Perspective counts toward `count`.

    Flow:
    1. Resolve Polarity by hash
    2. Look up existing Perspectives for this Polarity
    3. Create new partial Perspectives so `count` are generated this call
    4. Complete all partial PPs sequentially by generating aspects
    5. Return list of completed Perspectives (existing + new)
    """

    def __init__(
        self,
        polarity_hash: str,
        count: int = 1,
        grounding_context: Optional[str] = None,
    ) -> None:
        self.polarity_hash = polarity_hash
        self.count = max(1, count)
        #: Conversational material the tension was drawn from. Attached to each
        #: committed tetrad as grounding (`TetradGrounding`) so the case
        #: particulars survive the abstraction into ~7-word poles. Optional:
        #: pipeline callers working from Inputs have their particulars in the
        #: Input digest already; the `anchor` path does not, and used to
        #: discard this text after using it for classification.
        self.grounding_context = (grounding_context or "").strip() or None

    async def resolve(self) -> list[Perspective]:
        """
        Resolve Perspective creation for a single Polarity.

        Returns:
            List of complete, committed Perspectives
        """

        # Resolve Polarity
        polarity = self._resolve_polarity()
        if polarity is None:
            return []

        # Get input text for context
        input_text = await self._get_input_text()

        # Look up existing Perspectives for this Polarity
        pp_repo = PerspectiveRepository()
        existing_pps = pp_repo.find_by_polarity(polarity)

        complete_pps = [pp for pp in existing_pps if pp.is_complete()]
        partial_pps = [pp for pp in existing_pps if not pp.is_complete()]

        # Complete any existing partials, then create additional new ones so that
        # `count` fresh Perspectives are produced this call (a pre-existing partial
        # counts as one of them).
        additional_needed = self.count - len(partial_pps)
        for _ in range(max(0, additional_needed)):
            partial_pps.append(self._create_perspective_for_polarity(polarity))

        # Complete all partial PPs sequentially (each sees prior results)
        completed_pps: list[Perspective] = []

        for pp in partial_pps:
            not_like_these = complete_pps + completed_pps

            generator = AspectGeneration()
            aspects = await generator.resolve(
                perspective=pp,
                text=input_text,
                not_like_these=not_like_these,
            )
            self._report = self._report.merge(generator.report)

            # Deduplicate aspects against vocabulary
            aspects = await self._deduplicate_aspects(aspects, input_text, polarity)

            # Connect aspects to Perspective
            for aspect in aspects:
                self._connect_aspect(pp, aspect)

            # Check if PP is identical to an existing complete PP
            duplicate_of = self._find_duplicate(pp, complete_pps + completed_pps)
            if duplicate_of:
                pp_repo.discard_uncommitted(pp)
                self._report.artifacts.setdefault("duplicates_discarded", []).append(
                    {
                        "discarded": pp.short_hash if pp.hash else "uncommitted",
                        "duplicate_of": duplicate_of.short_hash,
                    }
                )
                continue

            # Name this reading of the tension: the generation already made
            # the LLM name the axis of each diagonal pair (TetradDto) —
            # persist it as the perspective's intent (the guiding question
            # of THIS tetrad). Sibling tetrads on one polarity differ by
            # exactly this. Set BEFORE commit: intent participates in the
            # hash, so distinct readings are structurally distinct nodes.
            if pp.intent is None:
                reading = self._compose_reading(generator.axes)
                if reading:
                    pp.intent = reading

            pp.commit()
            self._report.node_committed(pp)
            completed_pps.append(pp)

        # Attach the case particulars these tetrads were abstracted from, so
        # the conversation can later be held against the person's own facts
        # instead of the universal wording. Before validation: cheap, and a
        # validation crash must not cost the grounding.
        await self._ground_tetrads(completed_pps)

        # Validate newly generated tetrads (CC + empirical inequalities) and
        # flag the verdict — non-blocking: a failed perspective stays usable,
        # prompts deprioritize it via the rendered flag.
        await self._validate_and_flag(completed_pps, input_text)

        # Return all PPs: existing complete + newly completed
        all_pps = complete_pps + completed_pps

        # No perspectives means the tension was not expanded — the caller
        # (`anchor`, AnalysisPipeline) must not read that as success. Reachable
        # whenever every generated tetrad deduped into an existing one and
        # there was no pre-existing complete PP to return.
        self._report.ok = bool(all_pps)
        if not all_pps:
            self._report.summary = (
                f"No Perspective produced for polarity "
                f"[[{self.polarity_hash}]] — nothing was added to the graph."
            )
            return all_pps
        self._report.artifacts["perspective_hashes"] = [
            pp.hash for pp in all_pps if pp.hash
        ]
        self._report.artifacts["total_count"] = len(all_pps)
        self._report.artifacts["existing_count"] = len(complete_pps)
        self._report.artifacts["new_count"] = len(completed_pps)
        self._report.artifacts["perspectives"] = [
            self._perspective_final_state(pp) for pp in all_pps
        ]

        self._report.summary = f"{len(all_pps)} Perspective(s) ({len(complete_pps)} existing, {len(completed_pps)} new)"

        return all_pps

    async def _ground_tetrads(self, perspectives: list[Perspective]) -> None:
        """Attach case particulars from `grounding_context` to each new tetrad.

        One extraction for the whole call, reused across the perspectives: the
        particulars describe the SITUATION, not one reading of it, and
        `Rationale` dedups on (text, target) so N tetrads sharing one context
        yield N edges to N nodes without redundant LLM work.

        Fail-soft and no-op without context: grounding is enrichment, never a
        gate. Sequential because GQLAlchemy graph writes are not
        concurrency-safe (CLAUDE.md) — the single LLM call happens once, up
        front, so there is nothing to parallelize anyway.
        """
        if not self.grounding_context or not perspectives:
            return

        from dialectical_framework.concerns.tetrad_grounding import \
            TetradGrounding

        # Extract ONCE, then attach to each tetrad. Re-extracting per
        # perspective would spend N LLM calls to produce the same text from the
        # same material.
        first = TetradGrounding()
        try:
            rationale = await first.resolve(
                perspective=perspectives[0], context=self.grounding_context
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Grounding failed softly: %s", e)
            return
        self._report = self._report.merge(first.report)
        if rationale is None:
            return

        grounded = [perspectives[0].short_hash]
        for pp in perspectives[1:]:
            try:
                extra = Rationale(text=rationale.text)
                extra.set_explanation_target(pp, role=ROLE_GROUNDING)
                extra.commit()
                self._report.node_created(extra)
                grounded.append(pp.short_hash)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Grounding attach failed softly for %s: %s", pp.short_hash, e
                )

        self._report.artifacts["grounded"] = grounded

    async def _validate_and_flag(
        self, perspectives: list[Perspective], input_text: str
    ) -> None:
        """
        Run PerspectiveValidation on each new tetrad and persist the verdict
        on Perspective.validation (metadata field, hash-neutral).

        Fail-soft: a crashing validator leaves validation=None (unvalidated),
        never blocks the perspective. Sequential on purpose: the underlying
        ControlStatementsCheck commits Estimation/Rationale nodes inside its
        resolve(), and GQLAlchemy graph writes are not concurrency-safe.
        (Its two control-statement LLM calls already gather internally.)
        """
        if not perspectives:
            return

        from dialectical_framework.concerns.perspective_validation import \
            PerspectiveValidation

        validation_summary: list[dict] = []
        for pp in perspectives:
            try:
                result = await PerspectiveValidation().resolve(
                    perspective=pp, text=input_text
                )
            except Exception as e:
                logger.warning(
                    "Perspective validation failed softly for %s: %s",
                    pp.short_hash,
                    e,
                )
                continue
            if result.is_valid:
                pp.validation = "passed"
            elif result.is_empirically_valid is None and (
                result.is_conceptually_coherent
            ):
                # EI couldn't run (missing complementarity data) and CC held —
                # inconclusive, not a failure. Leave unvalidated.
                continue
            else:
                reasons = "; ".join(result.failure_reasons)
                pp.validation = f"failed: {reasons}"
            pp.save()
            self._report.node_updated(pp, patch={"validation": pp.validation})
            validation_summary.append(
                {"hash": pp.short_hash, "validation": pp.validation}
            )

        if validation_summary:
            self._report.artifacts["validation"] = validation_summary

    def _resolve_polarity(self) -> Optional[Polarity]:
        """Resolve Polarity by hash."""
        repo = NodeRepository()
        node = repo.find_by_hash(self.polarity_hash, node_type=Polarity)
        if node is None:
            self._report.ok = False
            self._report.summary = f"Polarity '{self.polarity_hash}' not found"
            return None
        return node

    def _create_perspective_for_polarity(self, polarity: Polarity) -> Perspective:
        """Create a partial Perspective referencing a Polarity."""
        pp = Perspective()
        pp.save()
        pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
        self._report.node_created(pp)
        self._report.relationship_created(pp.polarity, pp, polarity)
        return pp

    def _connect_aspect(self, pp: Perspective, aspect: AspectResult) -> None:
        """Connect a generated aspect to the Perspective."""
        relationship_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        rel_class = relationship_classes[aspect.position]
        manager = pp.get_relationship_manager_by_position(aspect.position)

        manager.connect(
            aspect.component,
            relationship=rel_class(
                alias=aspect.position,
                heuristic_similarity=aspect.heuristic_similarity,
                complementarity_t=aspect.complementarity_t,
                complementarity_a=aspect.complementarity_a,
            ),
        )

        self._report.relationship_created(
            manager,
            aspect.component,
            pp,
            meta={
                "position": aspect.position,
                "hs": aspect.heuristic_similarity,
                "k_t": aspect.complementarity_t,
                "k_a": aspect.complementarity_a,
            },
        )

    def _perspective_final_state(self, pp: Perspective) -> dict[str, str | None]:
        """Build a dict with the final post-dedup text and hash at each position.

        Each aspect carries its Statement `short_hash` because an aspect is an
        ADDRESSABLE node, and the caller may need to reference one before any
        context dump exists. `record_decision` asks for the chosen side's `-`
        aspect hash as the `accepted_cost` ground, and a decision reached in
        the first session has only this artifact to read: measured, every
        recorded cost in `claim1-weak-r2` grounded on the Perspective — the
        tension, not the price — because the Perspective's was the sole hash on
        offer. Same reasoning as `DialecticalContext._dump_one_perspective`
        (see `test_aspect_lines_are_addressable`); do not drop these hashes to
        compact the artifact.
        """
        positions = [
            POSITION_T_PLUS,
            POSITION_T_MINUS,
            POSITION_A_PLUS,
            POSITION_A_MINUS,
        ]
        state: dict[str, str | None] = {"hash": pp.short_hash}
        if pp.intent:
            state["reading"] = pp.intent
        for pos in positions:
            manager = pp.get_relationship_manager_by_position(pos)
            pairs = manager.all()
            if pairs:
                node, _rel = pairs[0]
                state[pos] = node.text
                state[f"{pos}_hash"] = node.short_hash
            else:
                state[pos] = None
        return state

    async def _deduplicate_aspects(
        self, aspects: list[AspectResult], text: str, polarity: Polarity
    ) -> list[AspectResult]:
        """Deduplicate generated aspects against vocabulary.

        The tetrad's OWN poles are excluded from that vocabulary. An aspect is a
        development OF a pole, so it is by construction the most similar thing in
        the graph to it — and Rule 1 requires them to stay distinct nodes (T- is
        what T degenerates into when A+ is absent, not T itself). Left in, the
        deduplicator does exactly what it is built to do and replaces the aspect
        WITH the pole, silently collapsing the tetrad.

        Measured: a live weak-tier run recorded an `accepted_cost` on a Statement
        sitting at `T/T-` — one node serving as both the neutral thesis and its
        own overdevelopment. Same signature in `claim2-weak-r4` (`T/T-` on
        f142e3c). A collapsed tetrad breaks everything downstream that reads the
        positions apart: the control statement degenerates to "T without A+
        yields T", the diagonal contradictions vanish, `area`/`rectangularity`
        compare an aspect to itself, and a decision's accepted cost names the
        choice instead of its price.
        """
        if not aspects:
            return aspects

        repo = StatementRepository()
        pole_hashes = {
            node.hash
            for manager in (polarity.t, polarity.a)
            for node, _rel in manager.all()
            if node.hash
        }
        vocab = [
            entry
            for entry in repo.get_vocabulary_with_rationales()
            if entry.get("hash") not in pole_hashes
        ]
        if not vocab:
            return aspects

        generated_hashes = [a.component.hash for a in aspects if a.component.hash]
        if not generated_hashes:
            return aspects

        deduplicator = StatementDeduplication()
        dedup_result = await deduplicator.resolve(
            extracted_hashes=generated_hashes,
            vocabulary=vocab,
            text=text,
        )
        self._report = self._report.merge(deduplicator.report)

        if not dedup_result.replacements:
            return aspects

        updated_aspects: list[AspectResult] = []
        for aspect in aspects:
            if aspect.component.hash in dedup_result.replacements:
                replacement = dedup_result.replacements[aspect.component.hash]
                updated_aspects.append(
                    AspectResult(
                        component=replacement,
                        position=aspect.position,
                        apex_concept=aspect.apex_concept,
                        heuristic_similarity=aspect.heuristic_similarity,
                        complementarity_t=aspect.complementarity_t,
                        complementarity_a=aspect.complementarity_a,
                    )
                )
                self._report.artifacts.setdefault("deduped_aspects", []).append(
                    {
                        "position": aspect.position,
                        "original": aspect.component.short_hash,
                        "replaced_with": replacement.short_hash,
                    }
                )
            else:
                updated_aspects.append(aspect)

        return updated_aspects

    def _find_duplicate(
        self, pp: Perspective, existing_pps: list[Perspective]
    ) -> Optional[Perspective]:
        """Find an existing committed PP with same components."""
        for existing in existing_pps:
            if existing.is_committed and pp.is_same(existing):
                return existing
        return None

    @staticmethod
    def _compose_reading(axes: dict[str, str]) -> Optional[str]:
        """Compose AspectGeneration's captured axes into the perspective's
        reading (intent). Both axes when they name different dimensions,
        one when they agree or only one survived the disclaimer filter."""
        constructive = axes.get("t_plus_vs_a_minus")
        reflective = axes.get("a_plus_vs_t_minus")
        named = [a for a in (constructive, reflective) if a]
        if not named:
            return None
        if len(named) == 2 and named[0].lower() != named[1].lower():
            return f"Reading along: {named[0]} / {named[1]}"
        return f"Reading along: {named[0]}"

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
async def expand_polarities(
    polarity_hashes: Annotated[
        list[str],
        Field(description="Hashes of Polarities to expand into full Perspectives"),
    ],
    count: Annotated[
        int,
        Field(
            description="Number of new Perspectives to generate per Polarity (each is diverse from prior ones)"
        ),
    ] = 1,
) -> str:
    """Build complete Perspectives from Polarities by generating evaluative aspects (T+, T-, A+, A-) for each. Generates `count` new Perspectives per Polarity sequentially — each sees prior tetrads to ensure diversity. The Polarities must already exist in the graph."""
    import asyncio

    async def _expand_one(h: str) -> str:
        concern = ExpandPolarity(polarity_hash=h, count=count)
        await concern.resolve()
        return str(concern.report)

    unique_hashes = list(dict.fromkeys(polarity_hashes))
    results = await asyncio.gather(*[_expand_one(h) for h in unique_hashes])
    return "\n---\n".join(results)
