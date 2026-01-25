from __future__ import annotations

from typing import TYPE_CHECKING, Self, Union

from dependency_injector.wiring import Provide

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import DialecticalComponentsDeckDto
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.wisdom_unit import POSITION_T as ALIAS_T, POSITION_A as ALIAS_A
from dialectical_framework.protocols.polarity_finder import PolarityFinder

if TYPE_CHECKING:
    from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
    from dialectical_framework.protocols.antithesis_extractor import AntithesisExtractor


class PolarityFinderBasic(PolarityFinder):
    """
    Orchestrates polarity extraction by coordinating thesis and antithesis extractors.

    This class handles:
    - Input normalization (strings, lists, tuples)
    - Selective generation (via `at` parameter)
    - Deduplication across the matrix
    - DTO creation with proper aliases

    Delegates actual extraction to injected ThesisExtractor and AntithesisExtractor.
    """

    def __init__(
        self,
        thesis_extractor: ThesisExtractor = Provide[DI.thesis_extractor],
        antithesis_extractor: AntithesisExtractor = Provide[DI.antithesis_extractor],
        *,
        text: str | None = "",
    ):
        self._thesis_extractor = thesis_extractor
        self._antithesis_extractor = antithesis_extractor
        self._text = text if text else ""

    @property
    def text(self) -> str:
        return self._text

    def reload(self, *, text: str) -> Self:
        self._text = text
        self._thesis_extractor.reload(text=text)
        self._antithesis_extractor.reload(text=text)
        return self

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
            t_dto = await self._thesis_extractor.extract_single_thesis(not_like_these=not_like_these)
            not_like_these.append(t_dto.statement)
            theses_to_find_dtos = [t_dto]
        elif empty_count > 1:
            ts_dto = await self._thesis_extractor.extract_multiple_theses(count=empty_count, not_like_these=not_like_these)
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
            opposite_dto = await self._antithesis_extractor.extract_single_antithesis(
                thesis=statements_needing_opposites[0],
                not_like_these=not_like_these
            )
            opposites_dtos = [opposite_dto]
        elif len(statements_needing_opposites) > 1:
            deck_dto = await self._antithesis_extractor.extract_multiple_antitheses(
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
