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

        Args:
            given: Input specification for polarities:
                - None: Extract a single polarity
                - str: Extract a single polarity for that thesis
                - [str]: Extract a single polarity for that thesis
                - [None, str]: Extract two polarities for theses
                - [(None, None)]: Extract a single polarity
                - [(None, some_thesis)]: A thesis will be extracted
                - More tuples: All given theses/antitheses will be taken into account

            at: Selective generation control:
                - None (default): Generate all missing components in the given matrix
                - int: Generate only at that specific index (0-based)
                - list[int]: Generate only at those specific indices (0-based)

                When at is specified, all other known theses/antitheses from the given matrix
                are passed as not_like_these to avoid duplicates.

        Returns:
            List of (thesis, antithesis) tuples

        Raises:
            IndexError: If any index in 'at' is out of bounds
        """
        ...

    @abstractmethod
    async def extract_multiple_antitheses( self, *, theses: list[str], not_like_these: list[str] | None = None) -> DialecticalComponentsDeck: ...

    @abstractmethod
    async def extract_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) -> DialecticalComponent: ...