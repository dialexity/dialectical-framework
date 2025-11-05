from abc import abstractmethod
from typing import Union

from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import DialecticalComponentsDeck


class PolarityExtractor(ThesisExtractor):
    @abstractmethod
    async def extract_polarities(
        self,
        *,
        given: Union[str, list[str | None], list[tuple[str | None, str | None]]] = None,
        at: None | int | list[int] = None
    ) -> list[tuple[DialecticalComponent, DialecticalComponent]]:
        """
        Extract polarities (thesis-antithesis pairs) with optional selective generation.

        This method provides flexible polarity extraction with support for partial inputs and
        selective generation control. It intelligently generates missing components while avoiding
        duplicates across the entire matrix.

        Parameters
        ----------
        given : Union[str, list[str | None], list[tuple[str | None, str | None]]], optional
            Input specification for polarities. Supports multiple formats:

            **Simple formats:**
            - `None` or `[]`: Generate a single complete polarity pair from scratch
            - `"text"`: Use "text" as thesis, generate its antithesis

            **List formats:**
            - `["thesis1", "thesis2"]`: Each string becomes a thesis, generate antitheses
            - `[None, "text"]`: Generate thesis for first, use "text" for second
            - `[(None, None)]`: Generate one complete polarity pair
            - `[("thesis", None)]`: Use provided thesis, generate antithesis
            - `[(None, "antithesis")]`: Generate thesis (opposite) for provided antithesis
            - `[("thesis", "antithesis")]`: Both provided, no generation needed

            **Mixed formats:**
            - `[("Love", None), (None, "Hate"), ("Peace", "War"), (None, None)]`
              Handles any combination of complete, partial, or empty tuples

            Maximum 4 polarities supported.

        at : None | int | list[int], optional
            Selective generation control (0-based indices):

            - `None` (default): Generate ALL missing components across the matrix.
              Returns complete polarities with no empty statements.

            - `int` (e.g., `at=0`): Generate ONLY at that specific index.
              Other indices preserve provided values but leave missing parts empty.

            - `list[int]` (e.g., `at=[0, 2]`): Generate at multiple specific indices.
              Only specified indices are completed; others remain incomplete.

            **Deduplication:** When `at` is specified, all known statements from the
            entire `given` matrix are passed as `not_like_these` to avoid duplicate
            concepts during generation.

            **Complete tuples:** If an index in `at` has both thesis and antithesis
            already provided, no generation occurs—the tuple is simply preserved.

        Returns
        -------
        list[tuple[DialecticalComponent, DialecticalComponent]]
            List of (thesis, antithesis) tuples with proper aliases and indices.

            **When `at=None` (default):**
            All tuples are complete (no empty statements).

            **When `at` is specified:**
            - Indices in `at`: Complete tuples (both components have statements)
            - Indices NOT in `at`: May contain empty components:
                - `(DialecticalComponent(statement="thesis"), DialecticalComponent(statement=""))`
                  if only thesis was provided
                - `(DialecticalComponent(statement=""), DialecticalComponent(statement="antithesis"))`
                  if only antithesis was provided
                - `(DialecticalComponent(statement=""), DialecticalComponent(statement=""))`
                  if neither was provided

        Raises
        ------
        IndexError
            If any index in `at` is out of bounds (negative or >= length of `given`)
        ValueError
            If more than 4 polarities are requested
        """
        ...

    @abstractmethod
    async def extract_multiple_antitheses( self, *, theses: list[str], not_like_these: list[str] | None = None) -> DialecticalComponentsDeck: ...

    @abstractmethod
    async def extract_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) -> DialecticalComponent: ...