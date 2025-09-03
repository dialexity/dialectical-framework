from abc import ABC, abstractmethod

from pydantic import Field, ConfigDict

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.decompose_probability import decompose_probability_into_transitions


class AssessableCycle(Assessable, ABC):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    graph: DirectedGraph[Transition] = Field(
        default=None,
        description="Directed graph representing the cycle of dialectical components.",
    )

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        transitions = self.graph.first_path()
        if not transitions:
            probability = None
        else:
            probability = 1.0
            has_any_valid_probability = False
            
            for transition in transitions:
                if transition.probability is not None and transition.probability > 0.0:
                    probability *= transition.probability
                    has_any_valid_probability = True
                # Skip transitions with None or 0.0 probability (they're irrelevant)
            
            # If no transitions had valid probabilities, the overall probability is undefined
            if not has_any_valid_probability:
                probability = None

        if mutate:
            self.probability = probability

        return probability


    def decompose_probability(self, overwrite_existing_probabilities: bool = False) -> None:
        """
        Decomposes overall probability into individual transition probabilities.
        This should be called after `spiral.probability` is set.
        """
        if self.probability is None:
            # Cannot decompose if overall probability is not set
            return

        transitions = self.graph.first_path()
        if not transitions:  # If there are no transitions, nothing to decompose
            return

        decompose_probability_into_transitions(
            self.probability, transitions, overwrite_existing_probabilities
        )
