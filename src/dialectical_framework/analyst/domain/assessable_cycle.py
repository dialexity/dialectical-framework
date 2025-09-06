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
        Pr(Cycle) = product of ALL transition probabilities, in order.
        - If any transition Pr is 0.0 -> 0.0 (hard veto)
        - If any transition Pr is None -> None (unknown)
        - Else product of all
        No cycle-level opinions here.
        """
        transitions: list[Transition] = self.graph.first_path()  # ensure this is the ordered full cycle
        if not transitions:
            prob = None
        else:
            prob = 1.0
            for tr in transitions:
                p = tr.calculate_probability(mutate=mutate)
                if p is None:
                    prob = None
                    break
                if p == 0.0:
                    prob = 0.0
                    break
                prob *= p

        if mutate:
            self.probability = prob
        return prob

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
