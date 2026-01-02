from __future__ import annotations

from typing import Union

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.protocols.polarity_extractor import PolarityExtractor
from dialectical_framework.synthesist.concepts.thesis_extractor_basic import ThesisExtractorBasic
from dialectical_framework.domain.wheel_segment import ALIAS_T
from dialectical_framework.domain.wisdom_unit import ALIAS_A
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
    def prompt_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) -> "Messages.Type":
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
    def prompt_multiple_antitheses(self, *, theses: list[str], not_like_these: list[str] | None = None) -> "Messages.Type":
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

    async def extract_polarities(
        self,
        *,
        given: Union[str, list[str | None], list[tuple[str | None, str | None]]] = None,
        at: None | int | list[int] = None,
        not_like_these: list[str] | None = None
    ) -> list[tuple[DialecticalComponentDto, DialecticalComponentDto]]:
        """
        Implementation Notes
        -------------------
        1. **Two-phase generation:** First generates missing theses for `(None, None)`
           entries, then generates missing antitheses/opposites in batch.

        2. **Batch optimization:** Multiple missing components are generated in a single
           AI call when possible for efficiency.

        3. **Alias assignment:** Components receive proper aliases:
           - Single polarity: `T`, `A`
           - Multiple polarities: `T1`, `A1`, `T2`, `A2`, etc.

        4. **Index tracking:** Each component tracks its human-friendly index (1-based)
           for display purposes.

        5. **Safe with complete tuples:** Specifying an index in `at` with an already
           complete tuple is harmless—it's preserved with no generation.

        6. **DTO-only approach:** Works with DTOs throughout and returns DTOs.
           Conversion to graph happens in the reasoning layer.
        """
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

        # Normalize 'at' parameter into a list of indices
        indices_to_generate: list[int] | None = None
        if at is not None:
            if isinstance(at, int):
                indices_to_generate = [at]
            else:
                indices_to_generate = at

            # Validate indices are within bounds
            for idx in indices_to_generate:
                if idx < 0 or idx >= len(given):
                    raise IndexError(
                        f"Index {idx} is out of bounds for given list of length {len(given)}"
                    )

        # Collect all provided statements to avoid duplicates
        if not_like_these is None:
            not_like_these = []
        for thesis, antithesis in given:
            if thesis:
                not_like_these.append(thesis)
            if antithesis:
                not_like_these.append(antithesis)

        theses_to_find_dtos: list[DialecticalComponentDto] = []
        theses_indices = []

        # For every tuple that has both None, we want to first find theses
        # If indices_to_generate is specified, only process those indices
        empty_count = 0
        for i, (thesis, antithesis) in enumerate(given):
            # Skip if not in indices_to_generate (when specified)
            if indices_to_generate is not None and i not in indices_to_generate:
                continue

            if thesis is None and antithesis is None:
                empty_count += 1
                theses_indices.append(i)

        # Extract missing theses for empty positions (returns DTOs)
        if empty_count == 1:
            t_dto = await self._extract_single_thesis_dto(not_like_these=not_like_these)
            not_like_these.append(t_dto.statement)
            theses_to_find_dtos = [t_dto]
        elif empty_count > 1:
            ts_dto = await self._extract_multiple_theses_dto(count=empty_count, not_like_these=not_like_these)
            not_like_these.extend(t_dto.statement for t_dto in ts_dto.dialectical_components)
            theses_to_find_dtos = ts_dto.dialectical_components

        # Determine the index to use: 0 if only one tuple, otherwise 1-based index
        def get_friendly_index(i: int) -> int:
            return 0 if count == 1 else i + 1

        # Helper to get the correct alias
        def get_alias(base_alias: str, j: int) -> str:
            return base_alias if count == 1 else f"{base_alias}{j + 1}"

        # Initialize result list with empty DTO placeholders
        result_dtos: list[tuple[DialecticalComponentDto, DialecticalComponentDto]] = [
            (
                DialecticalComponentDto(alias=get_alias(ALIAS_T, i), statement="", explanation=""),
                DialecticalComponentDto(alias=get_alias(ALIAS_A, i), statement="", explanation="")
            )
            for i in range(len(given))
        ]

        # Fill in known statements and place found theses in correct positions
        # When indices_to_generate is specified, only process those indices
        thesis_counter = 0
        for i, (thesis, antithesis) in enumerate(given):
            friendly_idx = get_friendly_index(i)

            # If selective generation is enabled and this index is not in the list, skip processing
            if indices_to_generate is not None and i not in indices_to_generate:
                # Keep existing values if any, otherwise use empty strings
                if thesis is not None or antithesis is not None:
                    # Preserve existing known values, use empty string for missing
                    t_dto = DialecticalComponentDto(alias=get_alias(ALIAS_T, i), statement=thesis if thesis else "", explanation="")
                    t_dto.set_human_friendly_index(friendly_idx)
                    a_dto = DialecticalComponentDto(alias=get_alias(ALIAS_A, i), statement=antithesis if antithesis else "", explanation="")
                    a_dto.set_human_friendly_index(friendly_idx)
                    result_dtos[i] = (t_dto, a_dto)
                # Otherwise keep the empty placeholder DTOs from initialization
                continue

            if thesis is not None and antithesis is not None:
                # Both provided - just create DTOs with correct aliases
                t_dto = DialecticalComponentDto(alias=get_alias(ALIAS_T, i), statement=thesis, explanation="")
                t_dto.set_human_friendly_index(friendly_idx)
                a_dto = DialecticalComponentDto(alias=get_alias(ALIAS_A, i), statement=antithesis, explanation="")
                a_dto.set_human_friendly_index(friendly_idx)
                result_dtos[i] = (t_dto, a_dto)
            elif thesis is not None:
                # Thesis provided, need to find antithesis
                t_dto = DialecticalComponentDto(alias=get_alias(ALIAS_T, i), statement=thesis, explanation="")
                t_dto.set_human_friendly_index(friendly_idx)
                # Use empty DTO for missing antithesis
                a_dto = DialecticalComponentDto(alias=get_alias(ALIAS_A, i), statement="", explanation="")
                a_dto.set_human_friendly_index(friendly_idx)
                result_dtos[i] = (t_dto, a_dto)
            elif antithesis is not None:
                # Antithesis provided, need to find its opposite (which goes in thesis position)
                # Use empty DTO for missing thesis
                t_dto = DialecticalComponentDto(alias=get_alias(ALIAS_T, i), statement="", explanation="")
                t_dto.set_human_friendly_index(friendly_idx)
                a_dto = DialecticalComponentDto(alias=get_alias(ALIAS_A, i), statement=antithesis, explanation="")
                a_dto.set_human_friendly_index(friendly_idx)
                result_dtos[i] = (t_dto, a_dto)
            elif i in theses_indices:
                # Both empty - use found thesis DTO
                t_dto = theses_to_find_dtos[thesis_counter]
                t_dto.alias = get_alias(ALIAS_T, i)
                t_dto.set_human_friendly_index(friendly_idx)
                # Use empty DTO for missing antithesis
                a_dto = DialecticalComponentDto(alias=get_alias(ALIAS_A, i), statement="", explanation="")
                a_dto.set_human_friendly_index(friendly_idx)
                result_dtos[i] = (t_dto, a_dto)
                thesis_counter += 1

        # Collect all statements that need opposites
        # Only process indices in indices_to_generate if specified
        statements_needing_opposites = []
        indices_needing_opposites = []
        is_thesis_position = []  # Track which position the opposite should go to

        for i, (t_dto, a_dto) in enumerate(result_dtos):
            # Skip if not in indices_to_generate (when specified)
            if indices_to_generate is not None and i not in indices_to_generate:
                continue

            # Check for empty statements (not generated yet)
            if t_dto.statement == "" and a_dto.statement != "":
                # Need to find opposite for the provided antithesis
                statements_needing_opposites.append(a_dto.statement)
                indices_needing_opposites.append(i)
                is_thesis_position.append(True)  # Opposite goes to thesis position
            elif a_dto.statement == "" and t_dto.statement != "":
                # Need to find opposite for the provided thesis
                statements_needing_opposites.append(t_dto.statement)
                indices_needing_opposites.append(i)
                is_thesis_position.append(False)  # Opposite goes to antithesis position

        # Extract all opposites in one batch (returns DTOs)
        opposites_dtos: list[DialecticalComponentDto] = []
        if len(statements_needing_opposites) == 1:
            opposite_dto = await self._extract_single_antithesis_dto(
                thesis=statements_needing_opposites[0],
                not_like_these=not_like_these
            )
            opposites_dtos = [opposite_dto]
        elif len(statements_needing_opposites) > 1:
            deck_dto = await self._extract_multiple_antitheses_dto(
                theses=statements_needing_opposites,
                not_like_these=not_like_these
            )
            opposites_dtos = deck_dto.dialectical_components

        # Place the opposites in the correct positions with correct aliases
        for idx, opposite_dto, is_t_pos in zip(indices_needing_opposites, opposites_dtos, is_thesis_position):
            friendly_idx = get_friendly_index(idx)
            current_t_dto, current_a_dto = result_dtos[idx]
            if is_t_pos:
                # Opposite goes to thesis position
                opposite_dto.alias = get_alias(ALIAS_T, idx)
                opposite_dto.set_human_friendly_index(friendly_idx)
                result_dtos[idx] = (opposite_dto, current_a_dto)
            else:
                # Opposite goes to antithesis position
                opposite_dto.alias = get_alias(ALIAS_A, idx)
                opposite_dto.set_human_friendly_index(friendly_idx)
                result_dtos[idx] = (current_t_dto, opposite_dto)

        # Return DTOs directly - conversion to graph happens in reasoning layer
        return result_dtos

    # Private helper methods that return DTOs (used internally)
    async def _extract_single_thesis_dto(self, *, not_like_these: list[str] | None = None) -> DialecticalComponentDto:
        """Internal method that returns thesis as DTO"""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_thesis():
            return self.prompt_single_thesis(not_like_these=not_like_these)

        return await _find_thesis()

    async def _extract_multiple_theses_dto(self, *, count: int, not_like_these: list[str] | None = None) -> DialecticalComponentsDeckDto:
        """Internal method that returns theses as DTO deck"""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeckDto)
        async def _find_theses():
            return self.prompt_multiple_theses(count=count, not_like_these=not_like_these)

        return await _find_theses()

    async def _extract_single_antithesis_dto(self, *, thesis: str, not_like_these: list[str] | None = None) -> DialecticalComponentDto:
        """Internal method that returns antithesis as DTO"""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentDto)
        async def _find_antithesis():
            return self.prompt_single_antithesis(thesis=thesis, not_like_these=not_like_these)

        return await _find_antithesis()

    async def _extract_multiple_antitheses_dto(self, *, theses: list[str], not_like_these: list[str] | None = None) -> DialecticalComponentsDeckDto:
        """Internal method that returns antitheses as DTO deck"""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeckDto)
        async def _find_antitheses():
            return self.prompt_multiple_antitheses(theses=theses, not_like_these=not_like_these)

        return await _find_antitheses()

    async def extract_multiple_antitheses(self, *, theses: list[str], not_like_these: list[str] | None = None) \
            -> DialecticalComponentsDeckDto:
        """
        Protocol method: Extracts multiple antitheses and returns them as DTO deck.
        Now returns DialecticalComponentsDeckDto instead of legacy DialecticalComponentsDeck.
        """
        count = len(theses)

        # Use internal DTO method
        deck_dto = await self._extract_multiple_antitheses_dto(theses=theses, not_like_these=not_like_these)

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

    async def extract_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) \
            -> DialecticalComponentDto:
        """
        Protocol method: Extracts single antithesis and returns it as DTO.
        """
        # Get DTO from AI and return it directly
        return await self._extract_single_antithesis_dto(thesis=thesis, not_like_these=not_like_these)
