from typing import Union

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.dto_mapper import (map_from_dto,
                                                     map_list_from_dto)
from dialectical_framework.protocols.polarity_extractor import PolarityExtractor
from dialectical_framework.synthesist.concepts.thesis_extractor_basic import ThesisExtractorBasic
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.synthesist.domain.wheel_segment import ALIAS_T
from dialectical_framework.synthesist.domain.wisdom_unit import ALIAS_A
from dialectical_framework.utils.use_brain import use_brain


class PolarityExtractorBasic(ThesisExtractorBasic, PolarityExtractor):

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
    def prompt_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "**Rules**\nIMPORTANT: The antithesis A must be different than these already known statements:\n\n- " + "\n- ".join(not_like_these)

        return {
            "computed_fields": {
                'thesis_extraction': self.prompt_single_thesis(),
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
    def prompt_multiple_antitheses(self, *, theses: list[str], not_like_these: list[str] | None = None) -> Messages.Type:
        rule_out = ""

        if not_like_these:
            rule_out = "IMPORTANT: The antitheses A1 ... Ax must be different than these statements:\n\n- " + "\n- ".join(
                not_like_these)

        theses_str = "\n".join(f"T{i + 1} = {thesis}" for i, thesis in enumerate(theses))

        return {
            "computed_fields": {
                "theses_extraction": self.prompt_multiple_theses(count=len(theses)),
                "theses": theses_str,
                "count": len(theses),
                "rule_out": rule_out,
                "component_length": self.settings.component_length,
            },
        }

    async def extract_polarities(self, *,
         given: Union[str, list[str | None], list[tuple[str | None, str | None]]] = None) \
            -> list[tuple[DialecticalComponent, DialecticalComponent]]:

        if not given or len(given) == 0:
            given = None

        count = len(given) if isinstance(given, list) else 1
        if count > 4 or count < 1:
            raise ValueError(
                f"Incorrect number of polarities requested. Max 4 are supported."
            )

        # Normalize given parameter into tuples
        if given is None:
            given = [(None, None)]
        elif isinstance(given, str):
            given = [(given, None)]
        else:
            if not isinstance(given[0], tuple):
                given = [(t, None) for t in given]


        # Collect all provided statements to avoid duplicates
        not_like_these = []
        for thesis, antithesis in given:
            if thesis:
                not_like_these.append(thesis)
            if antithesis:
                not_like_these.append(antithesis)

        theses_to_find = []
        theses_indices = []

        # For every tuple that has both None, we want to first find theses
        empty_count = 0
        for i, (thesis, antithesis) in enumerate(given):
            if thesis is None and antithesis is None:
                empty_count += 1
                theses_indices.append(i)

        # Extract missing theses for empty positions
        if empty_count == 1:
            t = await self.extract_single_thesis(not_like_these=not_like_these)
            not_like_these.append(t.statement)
            theses_to_find = [t]
        elif empty_count > 1:
            ts = await self.extract_multiple_theses(count=empty_count, not_like_these=not_like_these)
            not_like_these.extend(t.statement for t in ts.dialectical_components)
            theses_to_find = ts.dialectical_components

        # Initialize result list with placeholders
        result: list[tuple[DialecticalComponent | None, DialecticalComponent | None]] = [(None, None) for _ in range(len(given))]

        # Determine the index to use: 0 if only one tuple, otherwise 1-based index
        def get_friendly_index(i: int) -> int:
            return 0 if count == 1 else i + 1

        # Helper to get the correct alias
        def get_alias(base_alias: str, j: int) -> str:
            return base_alias if count == 1 else f"{base_alias}{j + 1}"

        # Fill in known statements and place found theses in correct positions
        thesis_counter = 0
        for i, (thesis, antithesis) in enumerate(given):
            friendly_idx = get_friendly_index(i)
            if thesis is not None and antithesis is not None:
                # Both provided - just create components with correct aliases
                t = DialecticalComponent(alias=get_alias(ALIAS_T, i), statement=thesis)
                t.set_human_friendly_index(friendly_idx)
                a = DialecticalComponent(alias=get_alias(ALIAS_A, i), statement=antithesis)
                a.set_human_friendly_index(friendly_idx)
                result[i] = (t, a)
            elif thesis is not None:
                # Thesis provided, need to find antithesis
                t = DialecticalComponent(alias=get_alias(ALIAS_T, i), statement=thesis)
                t.set_human_friendly_index(friendly_idx)
                result[i] = (t, None)
            elif antithesis is not None:
                # Antithesis provided, need to find its opposite (which goes in thesis position)
                a = DialecticalComponent(alias=get_alias(ALIAS_A, i), statement=antithesis)
                a.set_human_friendly_index(friendly_idx)
                result[i] = (None, a)
            elif i in theses_indices:
                # Both empty - use found thesis
                t = theses_to_find[thesis_counter]
                t.alias = get_alias(ALIAS_T, i)
                t.set_human_friendly_index(friendly_idx)
                result[i] = (t, None)
                thesis_counter += 1

        # Collect all statements that need opposites
        statements_needing_opposites = []
        indices_needing_opposites = []
        is_thesis_position = []  # Track which position the opposite should go to

        for i, (t, a) in enumerate(result):
            if t is None:
                # Need to find opposite for the provided antithesis
                statements_needing_opposites.append(a.statement)
                indices_needing_opposites.append(i)
                is_thesis_position.append(True)  # Opposite goes to thesis position
            elif a is None:
                # Need to find opposite for the provided thesis
                statements_needing_opposites.append(t.statement)
                indices_needing_opposites.append(i)
                is_thesis_position.append(False)  # Opposite goes to antithesis position

        # Extract all opposites in one batch
        if len(statements_needing_opposites) == 1:
            opposite = await self.extract_single_antithesis(
                thesis=statements_needing_opposites[0],
                not_like_these=not_like_these
            )
            opposites = [opposite]
        elif len(statements_needing_opposites) > 1:
            deck = await self.extract_multiple_antitheses(
                theses=statements_needing_opposites,
                not_like_these=not_like_these
            )
            opposites = deck.dialectical_components
        else:
            opposites = []

        # Place the opposites in the correct positions with correct aliases
        for idx, opposite, is_t_pos in zip(indices_needing_opposites, opposites, is_thesis_position):
            friendly_idx = get_friendly_index(idx)
            if is_t_pos:
                # Opposite goes to thesis position
                opposite.alias = get_alias(ALIAS_T, idx)
                opposite.set_human_friendly_index(friendly_idx)
                result[idx] = (opposite, result[idx][1])
            else:
                # Opposite goes to antithesis position
                opposite.alias = get_alias(ALIAS_A, idx)
                opposite.set_human_friendly_index(friendly_idx)
                result[idx] = (result[idx][0], opposite)

        return result

    async def extract_multiple_antitheses(self, *, theses: list[str], not_like_these: list[str] | None = None) \
            -> DialecticalComponentsDeck:
        count = len(theses)

        @with_langfuse()
        @use_brain(
            brain=self.brain,
            response_model=DialecticalComponentsDeckDto,
        )
        async def _find_antitheses():
            return self.prompt_multiple_antitheses(theses=theses, not_like_these=not_like_these)

        deck_dto = await _find_antitheses()
        components = map_list_from_dto(deck_dto.dialectical_components, DialecticalComponent)
        # It may happen that AI will return theses as well, so let's be prepared to filter out only the antitheses
        antitheses = []
        for dc in components:
            if dc.alias.startswith(ALIAS_A):
                antitheses.append(dc)

        if len(antitheses) < count:
            raise ValueError(f"AI returned {len(antitheses)} antitheses but {count} were requested.")

        # Take only the requested count if AI returned more
        deck = DialecticalComponentsDeck(dialectical_components=antitheses[:count])
        if count == 1 and len(deck.dialectical_components) == 1:
            dc: DialecticalComponent = deck.dialectical_components[0]
            dc.set_human_friendly_index(0)
        return deck

    async def extract_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) \
            -> DialecticalComponent:
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_antithesis():
            return self.prompt_single_antithesis(thesis=thesis, not_like_these=not_like_these)

        dc_dto = await _find_antithesis()
        return map_from_dto(dc_dto, DialecticalComponent)
