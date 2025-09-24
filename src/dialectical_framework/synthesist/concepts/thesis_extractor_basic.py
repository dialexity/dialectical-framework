from typing import Self

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.dto_mapper import (map_from_dto,
                                                     map_list_from_dto)
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
from dialectical_framework.utils.use_brain import use_brain


class ThesisExtractorBasic(ThesisExtractor, HasBrain, SettingsAware):
    def __init__(self, *, text: str = ""):
        self.__text = text

    @property
    def text(self) -> str:
        return self.__text

    @text.setter
    def text(self, value: str):
        self.__text = value

    def reload(self, *, text: str) -> Self:
        self.text = text
        return self

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
    def prompt_single_thesis(self, *, not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "**Rules**\nIMPORTANT: The output should be different than these already known theses:\n" + "\n".join(not_like_these)

        return {
            "computed_fields": {
                "text": self.text,
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
    def prompt_multiple_theses(self, *, count: int, not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "The output should have different than these already known theses:\n" + "\n".join(
                not_like_these)

        return {
            "computed_fields": {
                "text": self.text,
                "count": count,
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    async def extract_multiple_theses(self, *, count: int = 2, not_like_these: list[str] | None = None) -> DialecticalComponentsDeck:
        if count > 4 or count < 1:
            raise ValueError(
                f"Incorrect number of theses requested. Max 4 theses are supported."
            )

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeckDto)
        async def _find_theses():
            return self.prompt_multiple_theses(count=count, not_like_these=not_like_these)

        if count <= 4:
            deck_dto = await _find_theses()
            deck = DialecticalComponentsDeck(dialectical_components=map_list_from_dto(deck_dto.dialectical_components, DialecticalComponent))
            if count == 1 and len(deck.dialectical_components) == 1:
                dc: DialecticalComponent = deck.dialectical_components[0]
                dc.set_human_friendly_index(0)
        else:
            raise ValueError(f"More than 4 theses are not supported yet.")
        return deck

    async def extract_single_thesis(self, *, not_like_these: list[str] | None = None) -> DialecticalComponent:
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_thesis():
            return self.prompt_single_thesis(not_like_these=not_like_these)

        dc_dto = await _find_thesis()
        return map_from_dto(dc_dto, DialecticalComponent)
