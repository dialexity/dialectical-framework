from abc import abstractmethod

from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import DialecticalComponentsDeck


class PolarityExtractor(ThesisExtractor):
    @abstractmethod
    async def extract_polarities( self, *, given: list[tuple[str | None, str | None]]) -> list[tuple[DialecticalComponent, DialecticalComponent]]:
        """
        Given tuple of (None, None) a single polarity will be extracted.
        Given tuple of (None, some_thesis) a theses will be extracted.
        Given more tuples, all the given theses/antitheses will be taken into account.
        """
        ...

    @abstractmethod
    async def extract_multiple_antitheses( self, *, theses: list[str], not_like_these: list[str] | None = None) -> DialecticalComponentsDeck: ...

    @abstractmethod
    async def extract_single_antithesis(self, *, thesis: str, not_like_these: list[str] | None = None) -> DialecticalComponent: ...