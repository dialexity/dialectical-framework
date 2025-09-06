from abc import ABC
from statistics import geometric_mean

from pydantic import ConfigDict, Field

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.decompose_probability import \
    decompose_probability_into_transitions


class AssessableCycle(Assessable, ABC):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    graph: DirectedGraph[Transition] = Field(
        default=None,
        description="Directed graph representing the cycle of dialectical components.",
    )

    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, *, mutate: bool = True) -> list[float]:
        """
        Calculates the cycle fidelity (CF_S) as the geometric mean of:
        1. All dialectical components' contextual fidelity scores within the cycle's transitions
        2. All cycle-level rationales/opinions (weighted by their rating)

        Components/rationales with contextual_fidelity of 0.0 or None are excluded from the calculation.
        """
        parts = []

        # Collect fidelities from dialectical components
        transitions = self.graph.get_all_transitions()
        if transitions:
            for transition in transitions:
                parts.append(transition.calculate_contextual_fidelity(mutate=mutate))

        return parts

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        """
        Calculates the overall probability as the multiplication of all transition probabilities.
        Transitions with None or 0.0 probability are skipped (treated as irrelevant).
        If no transitions have positive probabilities, returns None.

        IMPORTANT: we don't use opinion probabilities here, because only the structural relationship matters.
        """
        transitions: list[Transition] = self.graph.first_path()
        if not transitions:
            cycle_multiplied_probability = None
        else:
            cycle_multiplied_probability = 1.0
            has_any_valid_probability = False
            
            for transition in transitions:
                tr_prob = transition.calculate_probability(mutate=mutate)
                if tr_prob is not None and tr_prob > 0.0:
                    cycle_multiplied_probability *= tr_prob
                    has_any_valid_probability = True
                # Skip transitions with None or 0.0 probability (they're irrelevant)
            
            # If no transitions had valid probabilities, the overall probability is undefined
            if not has_any_valid_probability:
                cycle_multiplied_probability = None

        if mutate:
            self.probability = cycle_multiplied_probability

        return cycle_multiplied_probability


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
