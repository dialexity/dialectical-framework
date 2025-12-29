from __future__ import annotations

from abc import abstractmethod

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.protocols.reloadable import Reloadable


class ThesisExtractor(Reloadable):
    """
    Protocol for extracting thesis concepts from text.

    All methods return DTOs - conversion to graph nodes happens in the reasoning layer.
    """

    @abstractmethod
    async def extract_multiple_theses( self, *, count: int = 2, not_like_these: list[str] | None = None) -> DialecticalComponentsDeckDto: ...

    @abstractmethod
    async def extract_single_thesis(self, *, not_like_these: list[str] | None = None) -> DialecticalComponentDto: ...
