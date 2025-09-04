from __future__ import annotations

from statistics import geometric_mean
from typing import List, Union

from pydantic import ConfigDict, Field, field_validator

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.wheel_segment import WheelSegment


class Transition(Assessable):
    model_config = ConfigDict(
        extra="forbid",
    )

    source_aliases: List[str] = Field(
        default_factory=list, description="Aliases of the source segment of the wheel."
    )
    source: Union[WheelSegment, DialecticalComponent] = Field(
        description="Source segment of the wheel or dialectical component."
    )
    target_aliases: List[str] = Field(
        default_factory=list, description="Aliases of the target segment of the wheel."
    )
    target: Union[WheelSegment, DialecticalComponent] = Field(
        description="Target segment of the wheel or dialectical component."
    )

    predicate: Predicate = Field(
        ...,
        description="The type of relationship between the source and target, e.g. T1 => causes => T2.",
    )

    @property
    def advice(self) -> str | None:
        r = self.best_rationale
        if r:
            return r.text
        else:
            return None

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Calculate contextual fidelity from rationales/opinions AND from source/target components.
        """
        all_fidelities = []

        # Collect fidelities from rationales/opinions (existing logic)
        all_fidelities.extend(self._calculate_contextual_fidelity_for_rationale_rated())

        # Process source aliases
        for alias in self.source_aliases:
            dc = self.source.find_component_by_alias(alias)
            if dc:
                fidelity = dc.calculate_contextual_fidelity(mutate=mutate)
                if fidelity is not None and fidelity > 0.0:
                    all_fidelities.append(fidelity)

        # Process target aliases  
        for alias in self.target_aliases:
            dc = self.target.find_component_by_alias(alias)
            if dc:
                fidelity = dc.calculate_contextual_fidelity(mutate=mutate)
                if fidelity is not None and fidelity > 0.0:
                    all_fidelities.append(fidelity)

        # If no valid fidelities were collected, return a neutral fidelity (1.0)
        if not all_fidelities:
            fidelity = 1.0
        else:
            # Calculate geometric mean of all valid (and weighted) fidelities
            fidelity = geometric_mean(all_fidelities)

        if mutate:
            self.contextual_fidelity = fidelity
        return fidelity

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        """
        Calculate transition probability from all rationales and their critique trees.
        """
        # Base case: no rationales, use directly assigned probability
        probability = self.probability
        if self.rationales:
            # Collect probabilities from all rationales
            all_probabilities = []

            for rationale in self.rationales:
                rationale_prob = rationale.calculate_probability(mutate=mutate)
                if rationale_prob is not None and rationale_prob > 0.0:
                    rationale_prob = rationale_prob * rationale.confidence
                    if rationale_prob > 0.0:
                        all_probabilities.append(rationale_prob)

            if all_probabilities:
                # Calculate geometric mean of all rationale probabilities
                probability = geometric_mean(all_probabilities)

        if mutate:
            self.probability = probability
        return probability

    @field_validator("source_aliases")
    def validate_source_aliases(cls, v: list[str], info) -> list[str]:
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
    def validate_target_aliases(cls, v: list[str], info) -> list[str]:
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
        """
        Merge fields from self into a new one, preserving non-None values from self
        """
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
            f"Summary: {self.advice if self.advice else 'N/A'}",
        ]
        return "\n".join(str_pieces)

    def __str__(self):
        return self.pretty()
