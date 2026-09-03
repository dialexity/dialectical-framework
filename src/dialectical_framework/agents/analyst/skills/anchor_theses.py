"""
AnchorTheses: Anchors explicit statements as theses without LLM intent parsing.

Takes literal statement texts from the Analyst agent and classifies + commits them
as Statement nodes. No extraction from inputs, no intent re-interpretation.

Usage:
    skill = AnchorTheses(statements=["Trust", "Remote work"])
    ideas = await skill.resolve()
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.statement_classification import (
    ClassificationResult, StatementClassification)
from dialectical_framework.concerns.statement_headline import StatementHeadline
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.utils.progress import (expect_progress,
                                                 report_progress)

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class AnchorTheses(ReasonableConcern[Optional[Ideas]]):
    """
    Anchors explicit statements as theses.

    Takes literal statement texts, classifies each via StatementClassification,
    creates Statement nodes, and wraps them in an Ideas container.

    No LLM intent parsing — the caller already decided these are literal statements.
    """

    #: ONE step regardless of how many statements were handed in: they are all
    #: classified in a single gathered stage, so a per-statement denominator would
    #: jump from 0 to N at one instant and tell the person nothing.
    PROGRESS_STEPS = 1

    def __init__(
        self, statements: list[str], input_hashes: list[str] | None = None
    ) -> None:
        self.statements = statements
        self.input_hashes = input_hashes

    async def resolve(self) -> Optional[Ideas]:
        if not self.statements:
            self._report.ok = True
            self._report.summary = "No statements provided"
            self._report.artifacts["thesis_hashes"] = []
            return None

        text = await self._get_input_text()

        expect_progress(self.PROGRESS_STEPS)
        report_progress("Taking in the position you named")
        components = await self._classify_and_create(self.statements, text=text)

        if not components:
            self._report.ok = True
            self._report.summary = "No statements created"
            self._report.artifacts["thesis_hashes"] = []
            return None

        ideas = self._create_ideas(components)

        self._report.artifacts["thesis_hashes"] = [c.hash for c in components]
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["theses"] = [
            {"hash": c.hash, "text": c.text} for c in components
        ]
        self._report.summary = f"Anchored {len(components)} thesis(es)"

        return ideas

    async def _classify_and_create(
        self,
        statements: list[str],
        text: str = "",
    ) -> list[Statement]:
        # Condense in parallel with classification. The agent may hand this skill
        # verbose prose (there is no extraction step to clamp length), so the
        # stored text becomes a headline while classification reads the full text.
        classifiers = [StatementClassification() for _ in statements]
        headliners = [StatementHeadline() for _ in statements]
        tasks = [
            classifier.resolve(
                statement=stmt,
                text=text,
                domain_hint="",
            )
            for classifier, stmt in zip(classifiers, statements)
        ]
        headline_tasks = [
            headliner.resolve(statement=stmt, text=text)
            for headliner, stmt in zip(headliners, statements)
        ]

        # ONE gather over both lists, not one per list. A coroutine does not start
        # until something awaits it, so two sequential `gather`s ran every
        # classification to completion and only then every headline, where the two
        # are independent: each concern gets `stmt` and `text`, neither reads the
        # other's output, and `_create_component` consumes both only after this
        # line.
        #
        # Worth ~1.0s AT MOST, and usually nothing — `HeadlineDto` is ~1.0s and it
        # fired once in five `anchor` calls, because `StatementHeadline`
        # short-circuits without an LLM call at `component_length` (7) and a
        # thesis the model hands this skill is normally already that short
        # (`probe_anchor_retry_cost.py`). Structural correctness is the reason to
        # do it, not the saving. Do NOT read the ~2.8s + ~3.0s pair from that
        # probe's table as this stage's cost: both of those are
        # `StatementClassification`'s own two submits, i.e. both live in `tasks`.
        both = await asyncio.gather(
            asyncio.gather(*tasks), asyncio.gather(*headline_tasks)
        )
        results: list[ClassificationResult] = both[0]
        headlines: list[str] = both[1]

        components: list[Statement] = []
        for classifier, headliner, result, headline in zip(
            classifiers, headliners, results, headlines
        ):
            component = self._create_component(result, headline)
            components.append(component)
            self._report = self._report.merge(classifier.report)
            self._report = self._report.merge(headliner.report)

        return components

    def _create_component(
        self, result: ClassificationResult, headline: str
    ) -> Statement:
        component = Statement(text=headline, meaning=result.meaning)
        component.commit()

        classification_label = "SIMPLE" if result.is_simple else "COMPLEX"
        self._report.node_created(
            component,
            patch={"meaning": result.meaning, "text": headline},
            meta={"classification": classification_label},
        )

        rationale_text = (
            f"Classification: {classification_label}. {result.classification_reasoning}"
        )
        if result.taxonomy_reasoning:
            rationale_text += f" {result.taxonomy_reasoning}"

        rationale = Rationale(text=rationale_text)
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)
        self._report.relationship_created(rationale.explains, rationale, component)

        return component

    def _create_ideas(self, components: list[Statement]) -> Optional[Ideas]:
        if not components:
            return None

        intent = ", ".join(self.statements)
        ideas = Ideas(intent=intent)
        ideas.save()
        self._report.node_created(ideas)

        for input_node in self._get_inputs():
            ideas.inputs.connect(input_node)
            self._report.relationship_created(ideas.inputs, ideas, input_node)

        for comp in components:
            ideas.statements.connect(comp)
            self._report.relationship_created(ideas.statements, ideas, comp)

        ideas.commit()
        self._report.node_committed(ideas)

        return ideas

    def _get_inputs(self) -> list:
        """Inputs to attach as this Ideas container's provenance.

        Unresolved hashes are recorded, not raised: anchoring an explicit thesis
        does not depend on the material, so a miss here costs provenance edges
        rather than the analysis. It was silent before, which is how `anchor`
        carried the same `find_by_hashes` prefix bug as `ingest` without anyone
        noticing — `ingest` at least reported a (misleading) summary.
        """
        if self.input_hashes:
            from dialectical_framework.graph.nodes.input import Input

            repo = NodeRepository()
            inputs = repo.find_by_hashes(self.input_hashes, node_type=Input)
            unresolved = len(self.input_hashes) - len(inputs)
            if unresolved > 0:
                self._report.artifacts["unresolved_input_hashes"] = unresolved
            return inputs
        return InputRepository().get_all()

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        from dialectical_framework.utils.input_context import input_context

        inputs = self._get_inputs()
        return await input_context(inputs, input_resolver)


@llm.tool
async def anchor_theses(
    statements: Annotated[
        list[str],
        Field(
            description="Statement texts to anchor as theses (e.g., ['Trust'], ['Remote work', 'Freedom'])"
        ),
    ],
    input_hashes: Annotated[
        list[str] | None,
        Field(
            description="Optional input hashes for contextual classification. If None, uses all inputs in scope."
        ),
    ] = None,
) -> str:
    """Anchor explicit statements as theses. Use when the user names specific concepts
    to explore — single words, short phrases, or enumerated topics.
    Does NOT extract from inputs; takes statements literally and classifies them."""
    skill = AnchorTheses(statements=statements, input_hashes=input_hashes)
    await skill.resolve()
    return str(skill.report)
