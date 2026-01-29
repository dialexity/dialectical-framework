from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.ideas import Ideas
    from dialectical_framework.graph.nodes.input import Input


class PolarityFinder(Protocol):
    """
    Protocol for orchestrating polarity extraction (thesis-antithesis pair coordination).

    Extractors are standalone services that:
    1. Resolve content from source (Input or Ideas) via InputResolver
    2. Extract thesis-antithesis polarity pairs
    3. Create DialecticalComponent graph nodes
    4. Connect components to source.statements (HAS_STATEMENT)
    5. Create OPPOSITE_OF relationship between thesis and antithesis
    6. Return the created graph node pairs

    This protocol handles:
    - Input normalization (strings, lists, tuples)
    - Selective generation (via `at` parameter)
    - Deduplication across the matrix
    - Proper alias assignment
    """

    @abstractmethod
    async def extract_polarities(
        self,
        *,
        source: Union[Input, Ideas],
        given: Union[
            str,
            list[Union[str, DialecticalComponent, None]],
            list[tuple[Union[str, DialecticalComponent, None], Union[str, DialecticalComponent, None]]],
        ] = None,
        at: None | int | list[int] = None,
        not_like_these: list[str] | None = None,
    ) -> list[tuple[DialecticalComponent, DialecticalComponent]]:
        """
        Extract polarities (thesis-antithesis pairs) with optional selective generation.

        Creates graph nodes for each polarity pair with:
        - Both components connected to source.statements (HAS_STATEMENT)
        - OPPOSITE_OF relationship between thesis and antithesis

        Parameters
        ----------
        source : Input | Ideas
            Input or Ideas node to extract from and attach results to.

        given : Union[str, list[...], list[tuple[...]]], optional
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

            Can also accept DialecticalComponent graph nodes instead of strings.

            Maximum 4 polarities supported.

        at : None | int | list[int], optional
            Selective generation control (0-based indices):

            - `None` (default): Generate ALL missing components across the matrix.
              Returns complete polarities with no empty statements.

            - `int` (e.g., `at=0`): Generate ONLY at that specific index.
              Other indices preserve provided values but leave missing parts empty.

            - `list[int]` (e.g., `at=[0, 2]`): Generate at multiple specific indices.
              Only specified indices are completed; others remain incomplete.

        not_like_these : list[str] | None, optional
            Statements to avoid duplicating during generation.

        Returns
        -------
        list[tuple[DialecticalComponent, DialecticalComponent]]
            List of (thesis, antithesis) graph node tuples.
            Each pair has OPPOSITE_OF relationship set.

            **When `at=None` (default):**
            All tuples are complete (no empty statements).

            **When `at` is specified:**
            - Indices in `at`: Complete tuples
            - Indices NOT in `at`: May contain components with empty statements

        Raises
        ------
        IndexError
            If any index in `at` is out of bounds (negative or >= length of `given`)
        ValueError
            If more than 4 polarities are requested
        """
        ...
