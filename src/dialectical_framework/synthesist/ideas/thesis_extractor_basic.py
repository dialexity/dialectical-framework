from __future__ import annotations

from typing import TYPE_CHECKING, Union

from dependency_injector.wiring import Provide, inject
from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.enums.di import DI
from dialectical_framework.ai_dto.graph_mapper import component_from_dto
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    pass


class ThesisExtractorBasic(ThesisExtractor, HasBrain, SettingsAware):
    """
    SOA-ready thesis extractor service.

    Extracts thesis concepts from Input or Ideas source, creates graph nodes,
    and connects them to source.statements.
    """

    @inject
    def __init__(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ):
        self._input_resolver = input_resolver

    async def _resolve_text(self, source: Union[Input, Ideas]) -> str:
        """Resolve source to text content."""
        if isinstance(source, Ideas):
            input_result = source.input.get()
            if not input_result:
                raise ValueError("Ideas node is not connected to an Input")
            input_node, _ = input_result
            return await self._input_resolver.resolve(input_node)
        else:
            return await self._input_resolver.resolve(source)

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        Extract the central idea or the primary thesis (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

        Output the dialectical component T within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" in the explanation.

        {rule_out}
        """
    )
    def prompt_single_thesis(self, *, text: str, not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "**Rules**\nIMPORTANT: The output must be different than these already known theses:\n\n- " + "\n- ".join(not_like_these)

        return {
            "computed_fields": {
                "text": text,
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        For the given context extract **{count}** distinct, essential **concepts** that best capture the core dynamics of the text.

        **For strategic/philosophical texts, focus on:**
        - Big-picture or recurring ideas that reflect the **essence** of the content
        - **Abstract or strategic drivers** of the text
        - Terms that **structure the argument** or explain system-level dynamics

        **For technical/operational texts, focus on:**
        - **Process stages, steps, or functional components** that form the system
        - **Sequential elements** that flow into or cause each other
        - **Operational phases** or mechanisms that drive the system forward

        **Guidelines:**
        - Let the content guide whether to extract high-level themes or operational stages
        - If the text describes processes/systems, identify functional components
        - If the text presents arguments/strategies, identify conceptual themes
        - Aim for concepts that are **interdependent** and form a coherent framework

        **Output Format:**
        T1 = [concept in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]

        T2 = [concept in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]

        ...

        Tx = [concept in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]

        **Rules**
        Make sure to output {count} concepts, no more no less.
        {rule_out}
        """
    )
    def prompt_multiple_theses(self, *, text: str, count: int, not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "IMPORTANT: The output concepts must be different than these already known theses:\n\n- " + "\n- ".join(
                not_like_these)

        return {
            "computed_fields": {
                "text": text,
                "count": count,
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }


    async def extract_multiple_theses(
        self,
        *,
        source: Union[Input, Ideas],
        count: int = 2,
        not_like_these: list[str] | None = None,
    ) -> list[DialecticalComponent]:
        """
        Extract multiple thesis concepts from source.

        Creates graph nodes and connects them to source.statements.
        """
        if count > 4 or count < 1:
            raise ValueError(
                f"Incorrect number of theses requested. Max 4 theses are supported."
            )

        text = await self._resolve_text(source)

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeckDto)
        async def _find_theses():
            return self.prompt_multiple_theses(text=text, count=count, not_like_these=not_like_these)

        # AI returns DTO
        deck_dto = await _find_theses()

        if len(deck_dto.dialectical_components) < count:
            raise ValueError(f"AI returned {len(deck_dto.dialectical_components)} components but {count} were requested.")

        # Take only the requested count if AI returned more
        if len(deck_dto.dialectical_components) > count:
            deck_dto = DialecticalComponentsDeckDto(dialectical_components=deck_dto.dialectical_components[:count])

        # For single component, set human_friendly_index to 0 (no numeric suffix)
        if count == 1 and len(deck_dto.dialectical_components) == 1:
            dc_dto: DialecticalComponentDto = deck_dto.dialectical_components[0]
            dc_dto.set_human_friendly_index(0)

        # Convert DTOs to graph nodes and connect to source
        components: list[DialecticalComponent] = []
        for dto in deck_dto.dialectical_components:
            component = component_from_dto(dto)
            component.input.connect(source)

        return components

    async def extract_single_thesis(
        self,
        *,
        source: Union[Input, Ideas],
        not_like_these: list[str] | None = None,
    ) -> DialecticalComponent:
        """
        Extract a single thesis concept from source.

        Creates graph node and connects it to source.statements.
        """
        text = await self._resolve_text(source)

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_thesis():
            return self.prompt_single_thesis(text=text, not_like_these=not_like_these)

        # AI returns DTO
        dto = await _find_thesis()

        # Convert DTO to graph node and connect to source
        component = component_from_dto(dto)
        component.input.connect(source)

        return component
