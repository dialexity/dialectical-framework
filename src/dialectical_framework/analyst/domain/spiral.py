from statistics import geometric_mean

from pydantic import ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.analyst.domain.assessable_cycle import AssessableCycle
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.wheel_segment import WheelSegment


class Spiral(AssessableCycle):
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

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Calculates the path fidelity (CF_S) as the geometric mean of the context_fidelity_scores
        of all dialectical components within the spiral's transitions.

        Components with a context_fidelity_score of 0.0 or None are excluded from the calculation,
        as they represent concepts not grounded in the source context, which should not
        zero out the overall fidelity unless all components are ungrounded.
        """
        transitions = self.graph.first_path()
        score = 1.0 # If no transitions, assume perfect fidelity (neutral effect)
        if transitions:
            # Collect all unique dialectical components by resolving aliases
            dialectical_components = []

            for transition in transitions:
                # Process source aliases
                for alias in transition.source_aliases:
                    dc = transition.source.find_component_by_alias(alias)
                    if dc and not any(dc.is_same(udc) for udc in dialectical_components):
                        dialectical_components.append(dc)

                # Process target aliases
                for alias in transition.target_aliases:
                    dc = transition.target.find_component_by_alias(alias)
                    if dc and not any(dc.is_same(c) for c in dialectical_components):
                        dialectical_components.append(dc)

            # Filter for components with positive context_fidelity_score
            scores_for_gm = [
                c.contextual_fidelity
                for c in dialectical_components
                if isinstance(c, DialecticalComponent)
                   and c.contextual_fidelity is not None
                   and c.contextual_fidelity > 0.0
            ]

            if not scores_for_gm:
                # If no components have positive fidelity scores, return 1.0 (neutral effect)
                score = 1.0
            else:
                score = geometric_mean(scores_for_gm)

        if mutate:
            self.contextual_fidelity = score

        return score

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
