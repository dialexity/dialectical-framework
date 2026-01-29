from __future__ import annotations

from typing import TYPE_CHECKING, Union

from dependency_injector.wiring import Provide, inject
from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import DialecticalComponentsDeckDto
from dialectical_framework.enums.di import DI
from dialectical_framework.ai_dto.graph_mapper import component_from_dto
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.wisdom_unit import POSITION_A as ALIAS_A
from dialectical_framework.protocols.antithesis_extractor import AntithesisExtractor
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    pass


class AntithesisExtractorBasic(AntithesisExtractor, HasBrain, SettingsAware):
    """
    SOA-ready antithesis extractor service.

    Extracts antithesis concepts from Input or Ideas source, creates graph nodes,
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

    def _get_thesis_statement(self, thesis: Union[DialecticalComponent, str]) -> str:
        """Extract statement string from thesis (graph node or string)."""
        if isinstance(thesis, DialecticalComponent):
            return thesis.statement
        return thesis

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.

        Generate a dialectical opposition (A) of the thesis "{thesis}" (T). Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

        Output the dialectical component A within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A" in the explanation.

        {rule_out}
        """
    )
    def prompt_single_antithesis(self, *, text: str, thesis: str, not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "**Rules**\nIMPORTANT: The antithesis A must be different than these already known statements:\n\n- " + "\n- ".join(not_like_these)

        return {
            "computed_fields": {
                "text": text,
                "thesis": thesis,
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.

        For each thesis below, generate a dialectical opposition (A). Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

        {theses}

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
    def prompt_multiple_antitheses(self, *, text: str, theses: list[str], not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "IMPORTANT: The antitheses A1 ... Ax must be different than these statements:\n\n- " + "\n- ".join(
                not_like_these)

        theses_str = "\n".join(f"T{i + 1} = {thesis}" for i, thesis in enumerate(theses))

        return {
            "computed_fields": {
                "text": text,
                "theses": theses_str,
                "count": len(theses),
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    async def extract_single_antithesis(
        self,
        *,
        source: Union[Input, Ideas],
        thesis: Union[DialecticalComponent, str],
        not_like_these: list[str] | None = None,
    ) -> DialecticalComponent:
        """
        Extract a single antithesis for the given thesis.

        Creates graph node and connects it to source.statements.
        """
        text = await self._resolve_text(source)
        thesis_statement = self._get_thesis_statement(thesis)

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_antithesis():
            return self.prompt_single_antithesis(text=text, thesis=thesis_statement, not_like_these=not_like_these)

        # AI returns DTO
        dto = await _find_antithesis()

        # Convert DTO to graph node and connect to source
        component = component_from_dto(dto)
        component.input.connect(source)

        # Create OPPOSITE_OF relationship if thesis is a graph node
        if isinstance(thesis, DialecticalComponent):
            component.oppositions.connect(thesis)

        return component

    async def extract_multiple_antitheses(
        self,
        *,
        source: Union[Input, Ideas],
        theses: list[Union[DialecticalComponent, str]],
        not_like_these: list[str] | None = None,
    ) -> list[DialecticalComponent]:
        """
        Extract antitheses for multiple theses in batch.

        Creates graph nodes and connects them to source.statements.
        """
        text = await self._resolve_text(source)
        thesis_statements = [self._get_thesis_statement(t) for t in theses]
        count = len(thesis_statements)

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeckDto)
        async def _find_antitheses():
            return self.prompt_multiple_antitheses(text=text, theses=thesis_statements, not_like_these=not_like_these)

        deck_dto = await _find_antitheses()

        # Filter DTOs for antitheses only (AI might return theses too)
        antithesis_dtos = []
        for dto in deck_dto.dialectical_components:
            if dto.alias.startswith(ALIAS_A):
                antithesis_dtos.append(dto)

        if len(antithesis_dtos) < count:
            raise ValueError(f"AI returned {len(antithesis_dtos)} antitheses but {count} were requested.")

        # Take only the requested count if AI returned more
        antithesis_dtos = antithesis_dtos[:count]

        # For single component, set human_friendly_index to 0 (no numeric suffix)
        if count == 1 and len(antithesis_dtos) == 1:
            antithesis_dtos[0].set_human_friendly_index(0)

        # Convert DTOs to graph nodes and connect to source
        # Pair each antithesis with its corresponding thesis
        components: list[DialecticalComponent] = []
        for i, dto in enumerate(antithesis_dtos):
            component = component_from_dto(dto)
            component.input.connect(source)

            # Create OPPOSITE_OF relationship if thesis is a graph node
            if i < len(theses) and isinstance(theses[i], DialecticalComponent):
                component.oppositions.connect(theses[i])

            components.append(component)

        return components
