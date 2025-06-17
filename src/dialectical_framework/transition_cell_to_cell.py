from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.transition import Transition

class TransitionCellToCell(Transition):
    source: DialecticalComponent = Field(description="Source dialectical component of the wheel.")
    target: DialecticalComponent = Field(description="Target dialectical component of the wheel.")

    @model_validator(mode='after')
    def auto_populate_aliases(self) -> Self:
        # Auto-populate source_aliases if empty
        if not self.source_aliases and self.source:
            self.source_aliases = [self.source.alias]
        
        # Auto-populate target_aliases if empty
        if not self.target_aliases and self.target:
            self.target_aliases = [self.target.alias]
        
        return self