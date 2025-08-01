from __future__ import annotations
from typing import List, Literal

from pydantic import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.synthesist.factories.config_wheel_builder import CausalityType
from dialectical_framework.transition import Predicate
from dialectical_framework.transition_cell_to_cell import TransitionCellToCell


class Cycle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    causality_type: CausalityType = Field(..., description="The type of causality in the cycle.")
    causality_direction: Literal["clockwise", "counterclockwise"] = Field(default="clockwise", description="The direction of causality in the ring.")

    probability: float = Field(default=0, description="The probability 0 to 1 of the cycle to exist in reality.")
    reasoning_explanation: str = Field(default="", description="Explanation why/how this cycle might occur.")
    argumentation: str = Field(default="", description="Circumstances or contexts where this cycle would be most applicable or useful.")

    graph: DirectedGraph[TransitionCellToCell] = Field(default=None, description="Directed graph representing the cycle of dialectical components.")

    def __init__(self, dialectical_components: List[DialecticalComponent], causality_type: CausalityType = CausalityType.REALISTIC, **data):
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

                self.graph.add_transition(TransitionCellToCell(
                    source=source,
                    predicate=Predicate.CAUSES,
                    target=target,
                    # TODO: how do we set the transition text?
                ))

    @property
    def dialectical_components(self) -> List[DialecticalComponent]:
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

    def pretty(self, *, skip_dialectical_component_explanation = False,  start_alias: str | DialecticalComponent  | None = None) -> str:
        output = [self.graph.pretty() + f" | Probability: {self.probability}"]

        path = self.graph.first_path(start_aliases=[start_alias] if start_alias else None)
        if not path:
            raise ValueError(
                f"No path found between {start_alias} and the first dialectical component in the cycle."
            )
        for transition in path:
            dc = transition.source
            output.append(dc.pretty(skip_explanation=skip_dialectical_component_explanation))

        output.append(f"Reasoning: {self.reasoning_explanation}")
        output.append(f"Argumentation: {self.argumentation}")

        return "\n".join(output)

    def __str__(self):
        return self.pretty()