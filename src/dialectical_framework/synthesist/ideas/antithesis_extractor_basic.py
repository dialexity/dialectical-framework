from __future__ import annotations

from typing import Self

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import DialecticalComponentsDeckDto
from dialectical_framework.graph.nodes.wisdom_unit import POSITION_A as ALIAS_A
from dialectical_framework.protocols.antithesis_extractor import AntithesisExtractor
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.synthesist.ideas.thesis_extractor_basic import ThesisExtractorBasic
from dialectical_framework.utils.use_brain import use_brain


class AntithesisExtractorBasic(AntithesisExtractor, HasBrain, SettingsAware):
    """
    LLM-powered antithesis generation from thesis statements.

    This class handles the AI interaction for generating antitheses.
    It inherits the text context handling from ThesisExtractorBasic pattern.
    """

    def __init__(self, *, text: str | None = ""):
        self.__text = text if text else ""

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
        MESSAGES:
        {thesis_extraction}

        ASSISTANT:
        Thesis (it might look irrelevant, but this is what I got, so let's use it):
        T = {thesis}

        USER:
        A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.

        Generate a dialectical opposition (A) of the thesis "{thesis}" (T). Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

        Output the dialectical component A within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A" in the explanation.

        {rule_out}
        """
    )
    def prompt_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) -> "Messages.Type":
        rule_out = ""

        if not_like_these:
            rule_out = "**Rules**\nIMPORTANT: The antithesis A must be different than these already known statements:\n\n- " + "\n- ".join(not_like_these)

        # Create a temporary thesis extractor to get the thesis prompt
        thesis_extractor = ThesisExtractorBasic(text=self.__text)

        return {
            "computed_fields": {
                'thesis_extraction': thesis_extractor.prompt_single_thesis(),
                "thesis": thesis,
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    @prompt_template(
        """
        MESSAGES:
        {theses_extraction}

        ASSISTANT:
        Theses (they might look irrelevant, but this is what I got, so let's use them):
        {theses}

        USER:
        A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.

        For each thesis, generate a dialectical opposition (A). Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

        **Output Format:**
        A1 = [antithesis of T1 in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]

        A2 = [antithesis of T2 in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]

        ...

        Ax = [antithesis of Tx in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]

        **Rules**
        Make sure to output {count} antitheses, i.e. one for each thesis, no more no less.
        {rule_out}
        """
    )
    def prompt_multiple_antitheses(self, *, theses: list[str], not_like_these: list[str] | None = None) -> "Messages.Type":
        rule_out = ""

        if not_like_these:
            rule_out = "IMPORTANT: The antitheses A1 ... Ax must be different than these statements:\n\n- " + "\n- ".join(
                not_like_these)

        theses_str = "\n".join(f"T{i + 1} = {thesis}" for i, thesis in enumerate(theses))

        # Create a temporary thesis extractor to get the theses prompt
        thesis_extractor = ThesisExtractorBasic(text=self.__text)

        return {
            "computed_fields": {
                "theses_extraction": thesis_extractor.prompt_multiple_theses(count=len(theses)),
                "theses": theses_str,
                "count": len(theses),
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    async def extract_single_antithesis(
        self, *, thesis: str, not_like_these: list[str] | None = None
    ) -> DialecticalComponentDto:
        """
        Extract a single antithesis for the given thesis.
        """
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_antithesis():
            return self.prompt_single_antithesis(thesis=thesis, not_like_these=not_like_these)

        return await _find_antithesis()

    async def extract_multiple_antitheses(
        self, *, theses: list[str], not_like_these: list[str] | None = None
    ) -> DialecticalComponentsDeckDto:
        """
        Extract antitheses for multiple theses in batch.
        """
        count = len(theses)

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeckDto)
        async def _find_antitheses():
            return self.prompt_multiple_antitheses(theses=theses, not_like_these=not_like_these)

        deck_dto = await _find_antitheses()

        # Filter DTOs for antitheses only (AI might return theses too)
        antithesis_dtos = []
        for dto in deck_dto.dialectical_components:
            if dto.alias.startswith(ALIAS_A):
                antithesis_dtos.append(dto)

        if len(antithesis_dtos) < count:
            raise ValueError(f"AI returned {len(antithesis_dtos)} antitheses but {count} were requested.")

        # Take only the requested count if AI returned more
        result_deck = DialecticalComponentsDeckDto(dialectical_components=antithesis_dtos[:count])

        # For single component, set human_friendly_index to 0 (no numeric suffix)
        if count == 1 and len(result_deck.dialectical_components) == 1:
            dc_dto: DialecticalComponentDto = result_deck.dialectical_components[0]
            dc_dto.set_human_friendly_index(0)

        return result_deck
