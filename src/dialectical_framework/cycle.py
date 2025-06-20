from typing import List, Literal

from pydantic import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.transition_cell_to_cell import TransitionCellToCell


class Cycle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    causality_direction: Literal["clockwise", "counterclockwise"] = Field(default="clockwise", description="The direction of causality in the ring.")

    probability: float = Field(default=0, description="The probability 0 to 1 of the cycle to exist in reality.")
    reasoning_explanation: str = Field(default="", description="Explanation why/how this cycle might occur.")
    argumentation: str = Field(default="", description="Circumstances or contexts where this cycle would be most applicable or useful.")

    ring: DirectedGraph[TransitionCellToCell] = Field(default=None, description="Directed graph representing the cycle of dialectical components.")

    def __init__(self, dialectical_components: List[DialecticalComponent],  **data):
        super().__init__(**data)
        if self.ring is None:
            self.ring = DirectedGraph[TransitionCellToCell]()
            for i in range(len(dialectical_components)):
                next_i = (i + 1) % len(dialectical_components)
                if self.causality_direction == "clockwise":
                    source = dialectical_components[i]
                    target = dialectical_components[next_i]
                else:
                    source = dialectical_components[next_i]
                    target = dialectical_components[i]

                self.ring.add_transition(TransitionCellToCell(
                    source=source,
                    target=target,
                    # TODO: how do we set the transition text?
                ))
    
    @property
    def dialectical_components(self) -> List[DialecticalComponent]:
        """Returns list of dialectical components from the first path of the ring."""
        path = self.ring.first_path()
        return [transition.source for transition in path] if path else []

    def pretty(self, *, skip_dialectical_component_explanation = False,  start_alias: str | DialecticalComponent  | None = None) -> str:
        output = [self.ring.pretty() + f" | Probability: {self.probability}"]

        path = self.ring.first_path(start_aliases=[start_alias] if start_alias else None)
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