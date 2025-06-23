from __future__ import annotations

from typing import List, Union, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.wheel_segment import WheelSegment


class Transition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


    source_aliases: List[str] = Field(default_factory=list, description="Aliases of the source segment of the wheel.")
    source: Union[WheelSegment, DialecticalComponent] = Field(description="Source segment of the wheel or dialectical component.")
    target_aliases: List[str] = Field(default_factory=list, description="Aliases of the target segment of the wheel.")
    target: Union[WheelSegment, DialecticalComponent] = Field(description="Target segment of the wheel or dialectical component.")

    predicate: Literal["causes", "constructively_converges_to", "transforms_to"] = Field(
        ...,
        description="The type of relationship between the source and target, e.g. T1 => causes => T2.",
    )

    text: str | None = Field(default=None, description="The useful summary of the transition.")

    @field_validator('source_aliases')
    def validate_source_aliases(cls, v: list[str], info) -> list[str]:
        if 'source' in info.data and info.data['source']:
            source = info.data['source']
            valid_aliases = []
            
            if isinstance(source, DialecticalComponent):
                valid_aliases = [source.alias]
            elif isinstance(source, WheelSegment):
                # Extract aliases from all non-None components in the WheelSegment
                for component in [source.t, source.t_plus, source.t_minus]:
                    if component:
                        valid_aliases.append(component.alias)
            
            invalid_aliases = [alias for alias in v if alias not in valid_aliases]
            if invalid_aliases:
                raise ValueError(f"Invalid source aliases: {invalid_aliases}. Valid aliases: {valid_aliases}")
        return v

    @field_validator('target_aliases')
    def validate_target_aliases(cls, v: list[str], info) -> list[str]:
        if 'target' in info.data and info.data['target']:
            target = info.data['target']
            valid_aliases = []
            
            if isinstance(target, DialecticalComponent):
                valid_aliases = [target.alias]
            elif isinstance(target, WheelSegment):
                # Extract aliases from all non-None components in the WheelSegment
                for component in [target.t, target.t_plus, target.t_minus]:
                    if component:
                        valid_aliases.append(component.alias)
            
            invalid_aliases = [alias for alias in v if alias not in valid_aliases]
            if invalid_aliases:
                raise ValueError(f"Invalid target aliases: {invalid_aliases}. Valid aliases: {valid_aliases}")
        return v

    def new_with(self, other: Transition) -> Transition:
        # Merge fields from old transition into new one, preserving non-None values from self
        self_dict = self.model_dump()
        other_dict = other.model_dump()

        merged_dict = {**other_dict}  # Start with other values
        # Override with self values that are not None
        for key, value in self_dict.items():
            if value is not None:
                merged_dict[key] = value


        new_t_class: type[Transition] = type(self)
        if not isinstance(other, Transition):
            new_t_class = type(other)

        return new_t_class(**merged_dict)

    def pretty(self) -> str:
        str_pieces = [
            f"{', '.join(self.source_aliases)} → {', '.join(self.target_aliases)}",
            f"Summary: {self.text if self.text else 'N/A'}"
        ]
        return "\n".join(str_pieces)

    def __str__(self):
        return self.pretty()