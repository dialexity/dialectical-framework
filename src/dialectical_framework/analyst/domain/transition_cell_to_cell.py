from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent


class TransitionCellToCell(Transition):
    source: DialecticalComponent = Field(
        description="Source dialectical component of the wheel."
    )
    target: DialecticalComponent = Field(
        description="Target dialectical component of the wheel."
    )

    @model_validator(mode="after")
    def auto_populate_aliases(self) -> Self:
        # Autopopulate source_aliases if empty
        if not self.source_aliases and self.source:
            self.source_aliases = [self.source.alias]

        # Autopopulate target_aliases if empty
        if not self.target_aliases and self.target:
            self.target_aliases = [self.target.alias]

        return self
