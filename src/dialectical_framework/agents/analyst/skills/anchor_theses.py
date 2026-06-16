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
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class AnchorTheses(ReasonableConcern[Optional[Ideas]]):
    """
    Anchors explicit statements as theses.

    Takes literal statement texts, classifies each via StatementClassification,
    creates Statement nodes, and wraps them in an Ideas container.

    No LLM intent parsing — the caller already decided these are literal statements.
    """

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
        classifiers = [StatementClassification() for _ in statements]
        tasks = [
            classifier.resolve(
                statement=stmt,
                text=text,
                domain_hint="",
            )
            for classifier, stmt in zip(classifiers, statements)
        ]

        results: list[ClassificationResult] = await asyncio.gather(*tasks)

        components: list[Statement] = []
        for classifier, result in zip(classifiers, results):
            component = self._create_component(result)
            components.append(component)
            self._report = self._report.merge(classifier.report)

        return components

    def _create_component(self, result: ClassificationResult) -> Statement:
        component = Statement(text=result.statement, meaning=result.meaning)
        component.commit()

        classification_label = "SIMPLE" if result.is_simple else "COMPLEX"
        self._report.node_created(
            component,
            patch={"meaning": result.meaning, "text": result.statement},
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
        if self.input_hashes:
            from dialectical_framework.graph.nodes.input import Input

            repo = NodeRepository()
            return repo.find_by_hashes(self.input_hashes, node_type=Input)
        return InputRepository().get_all()

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        inputs = self._get_inputs()
        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)


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
