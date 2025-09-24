from abc import abstractmethod


from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.protocols.reloadable import Reloadable


class ThesisExtractor(Reloadable):
    @abstractmethod
    async def extract_multiple_theses( self, *, count: int = 2, not_like_these: list[str] | None = None) -> DialecticalComponentsDeck: ...

    @abstractmethod
    async def extract_single_thesis(self, *, not_like_these: list[str] | None = None) -> DialecticalComponent: ...
