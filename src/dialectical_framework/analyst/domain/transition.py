from __future__ import annotations

from typing import Tuple, Union

from pydantic import ConfigDict, Field, field_validator

from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.protocols.ratable import Ratable
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled


class Transition(Ratable):
    model_config = ConfigDict(
        extra="forbid",
    )

    source_aliases: list[str] = Field(
        default_factory=list, description="Aliases of the source segment of the wheel."
    )
    source: Union[WheelSegment, DialecticalComponent] = Field(
        description="Source segment of the wheel or dialectical component."
    )

    target_aliases: list[str] = Field(
        default_factory=list, description="Aliases of the target segment of the wheel."
    )
    target: Union[WheelSegment, DialecticalComponent] = Field(
        description="Target segment of the wheel or dialectical component."
    )

    predicate: Predicate = Field(
        ...,
        description="The type of relationship between the source and target, e.g. T1 => causes => T2.",
    )

    def _get_sub_assessables(self) -> list[Assessable]:
        """
        Don't add source/target here, as these are part of the wheel, and we'll end up infinitely recursing.
        """
        return super()._get_sub_assessables()

    def get_key(self) -> Tuple[frozenset[str], frozenset[str]]:
        """Get the key used to uniquely identify this transition based on source and target aliases."""
        return (
            frozenset(self.source_aliases),
            frozenset(self.target_aliases),
        )

    @field_validator("source_aliases")
    def validate_source_aliases(cls, v: list[str], info) -> list[str]: # Change list[str] from list[str]
        if "source" in info.data and info.data["source"]:
            source = info.data["source"]
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
                raise ValueError(
                    f"Invalid source aliases: {invalid_aliases}. Valid aliases: {valid_aliases}"
                )
        return v

    @field_validator("target_aliases")
    def validate_target_aliases(cls, v: list[str], info) -> list[str]: # Change list[str] from list[str]
        if "target" in info.data and info.data["target"]:
            target = info.data["target"]
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
                raise ValueError(
                    f"Invalid target aliases: {invalid_aliases}. Valid aliases: {valid_aliases}"
                )
        return v

    def new_with(self, other: Transition) -> Transition:
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
        rationale = self.best_rationale
        str_pieces = [
            f"{', '.join(self.source_aliases)} → {', '.join(self.target_aliases)}",
            f"Summary: {rationale.text if rationale else 'N/A'}",
        ]
        return "\n".join(str_pieces)

    def __str__(self):
        return self.pretty()
