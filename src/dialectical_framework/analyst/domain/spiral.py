
from pydantic import ConfigDict

from dialectical_framework.analyst.domain.assessable_cycle import \
    AssessableCycle
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.synthesist.domain.directed_graph import DirectedGraph
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class Spiral(AssessableCycle[TransitionSegmentToSegment]):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    def __init__(self, graph: DirectedGraph[TransitionSegmentToSegment] = None, **data):
        super().__init__(**data)
        if self.graph is None:
            self.graph = (
                graph
                if graph is not None
                else DirectedGraph[TransitionSegmentToSegment]()
            )

    def calculate_probability(self) -> float | None:
        """
        Pr(Spiral) = product of ALL transition probabilities, in order.
        - If any transition Pr is 0.0 -> skip
        - If any transition Pr is None -> skip
        - Else product of all
        No cycle-level opinions here.
        """
        transitions: list[TransitionSegmentToSegment] = self.graph.first_path()  # ensure this is the ordered full cycle
        prob = None
        if transitions:
            for tr in transitions:
                p = tr.calculate_probability()
                if p is not None and p > 0:
                    if prob is None:
                        prob = 1.0
                    prob *= p

        # Save the calculation as this object is derivative composition
        self.calculated_probability = prob
        return self.probability

    def pretty(self, *, start_wheel_segment: WheelSegment) -> str:
        output = []

        source_aliases_list = self.graph.find_outbound_source_aliases(
            start=start_wheel_segment
        )
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
        return self.pretty(
            start_wheel_segment=self.graph.get_all_transitions()[0].source
        )
