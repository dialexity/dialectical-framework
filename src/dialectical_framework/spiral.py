from typing import List

from pydantic import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wheel_segment import WheelSegment


class Spiral(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    graph: DirectedGraph[TransitionSegmentToSegment] = Field(default=None, description="Directed graph representing the spiral.")

    def __init__(self, graph: DirectedGraph[TransitionSegmentToSegment] = None,  **data):
        super().__init__(**data)
        if self.graph is None:
            self.graph = graph if graph is not None else DirectedGraph[TransitionSegmentToSegment]()

    def pretty(self, *, start_wheel_segment: WheelSegment) -> str:
        output = []

        source_aliases_list = self.graph.find_outbound_source_aliases(start=start_wheel_segment)
        for source_aliases in source_aliases_list:
            output.append(self.graph.pretty(start_aliases=source_aliases))
            path = self.graph.first_path(start_aliases=source_aliases)
            if path:
                for transition in path:
                    output.append(str(transition))
            else:
                raise ValueError(f"No path found from {source_aliases}.")

        return "\n".join(output)

    def __str__(self):
        return self.pretty(start_wheel_segment=self.graph.get_all_transitions()[0].source)