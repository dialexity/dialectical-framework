from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from dialectical_framework.analyst.domain.assessable_cycle import \
    AssessableCycle
from dialectical_framework.analyst.domain.transition_cell_to_cell import \
    TransitionCellToCell
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.synthesist.domain.directed_graph import DirectedGraph
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.enums.predicate import Predicate


class Cycle(AssessableCycle[TransitionCellToCell]):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    causality_type: CausalityType = Field(
        ..., description="The type of causality in the cycle."
    )
    causality_direction: Literal["clockwise", "counterclockwise"] = Field(
        default="clockwise", description="The direction of causality in the ring."
    )

    argumentation: str = Field(
        default="",
        description="Circumstances or contexts where this cycle would be most applicable or useful.",
    )

    def __init__(
        self,
        dialectical_components: list[DialecticalComponent],
        causality_type: CausalityType = CausalityType.REALISTIC,
        **data,
    ):
        data["causality_type"] = causality_type
        super().__init__(**data)
        if self.graph is None:
            self.graph = DirectedGraph[TransitionCellToCell]()
            for i in range(len(dialectical_components)):
                next_i = (i + 1) % len(dialectical_components)
                if self.causality_direction == "clockwise":
                    source = dialectical_components[i]
                    target = dialectical_components[next_i]
                else:
                    source = dialectical_components[next_i]
                    target = dialectical_components[i]

                self.graph.add_transition(
                    TransitionCellToCell(
                        source=source,
                        predicate=Predicate.CAUSES,
                        target=target,
                        # TODO: how do we set the transition text?
                    )
                )

    @property
    def dialectical_components(self) -> list[DialecticalComponent]:
        """Returns list of dialectical components from the first path of the ring."""
        path = self.graph.first_path()
        return [transition.source for transition in path] if path else []

    def cycle_str(self) -> str:
        """Returns a string representation of the cycle sequence."""
        aliases = [dc.alias for dc in self.dialectical_components]
        if not aliases:
            return ""
        if len(aliases) == 1:
            return f"{aliases[0]} → {aliases[0]}..."
        return " → ".join(aliases) + f" → {aliases[0]}..."

    def is_same_structure(self, other: Cycle) -> bool:
        """Check if cycles represent the same sequence regardless of starting point."""
        self_aliases = DialecticalComponentsDeck(
            dialectical_components=self.dialectical_components
        ).get_aliases()

        other_aliases = DialecticalComponentsDeck(
            dialectical_components=other.dialectical_components
        ).get_aliases()

        # Same length check
        if len(self_aliases) != len(other_aliases):
            return False

        # Convert to sets for same elements check
        if set(self_aliases) != set(other_aliases):
            return False

        # Check rotations only if sets are equal
        if len(self_aliases) <= 1:
            return True

        return any(
            self_aliases == other_aliases[i:] + other_aliases[:i]
            for i in range(len(other_aliases))
        )

    def pretty(
        self,
        *,
        skip_dialectical_component_explanation=False,
        start_alias: str | DialecticalComponent | None = None,
    ) -> str:
        output = [self.graph.pretty() + f" | Probability: {self.probability}"]

        path = self.graph.first_path(
            start_aliases=[start_alias] if start_alias else None
        )
        if not path:
            raise ValueError(
                f"No path found between {start_alias} and the first dialectical component in the cycle."
            )
        for transition in path:
            dc = transition.source
            output.append(
                dc.pretty(skip_explanation=skip_dialectical_component_explanation)
            )

        output.append(f"Rationale: {self.best_rationale.text if self.best_rationale else ''}")

        return "\n".join(output)

    def __str__(self):
        return self.pretty()
