from abc import ABC
from typing import TypeVar, Generic

from pydantic import ConfigDict, Field

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.synthesist.domain.directed_graph import DirectedGraph
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.decompose_probability_uniformly import decompose_probability_uniformly


T = TypeVar('T', bound=Transition)


class AssessableCycle(Assessable, Generic[T], ABC):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    graph: DirectedGraph[T] = Field(
        default=None,
        description="Directed graph representing the cycle of dialectical components.",
    )

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        result.extend(self.graph.get_all_transitions())
        return result

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        """
        Calculates the cycle relevance (R) as the geometric mean of:
        1. All dialectical components' relevance scores within the cycle's transitions
        2. All cycle-level rationales/opinions (weighted by their rating)

        Components/rationales with relevance of 0.0 or None are excluded from the calculation.
        """
        parts = []

        # Collect fidelities from dialectical components
        transitions = self.graph.get_all_transitions()
        if transitions:
            for transition in transitions:
                relevance = transition.calculate_relevance()
                if relevance is not None:
                    parts.append(relevance)

        return parts

    def calculate_probability(self) -> float | None:
        """
        Pr(Cycle) = product of ALL transition probabilities, in order.
        - If any transition Pr is 0.0 -> 0.0 (hard veto)
        - If any transition Pr is None -> None (unknown)
        - Else product of all
        No cycle-level opinions here.
        """
        transitions: list[T] = self.graph.first_path()  # ensure this is the ordered full cycle
        if not transitions:
            prob = None
        else:
            prob = 1.0
            for tr in transitions:
                p = tr.calculate_probability()
                if p is None:
                    prob = None
                    break
                if p == 0.0:
                    prob = 0.0
                    break
                prob *= p

        # Save the calculation as this object is derivative composition
        self.calculated_probability = prob
        return self.probability

def decompose_probability_into_transitions(
        probability: float,
        transitions: list[Transition],
        overwrite_existing_transition_probabilities: bool = False
) -> None:
    """
    **Case 1: No existing probabilities**
    - Uses uniform decomposition: `cycle_prob^(1/n)` for all transitions

    **Case 2: All transitions have probabilities**
    - Does nothing - respects existing assignments

    **Case 3: Mixed (some have, some don't)**
    - Calculates "remaining probability" after accounting for assigned ones
    - Distributes remaining probability uniformly among unassigned transitions

    """
    if not transitions:
        return

    if overwrite_existing_transition_probabilities:
        for t in transitions:
            t.probability = None

    # Check which transitions already have probabilities
    transitions_with_probs = [t for t in transitions if t.probability is not None]
    transitions_without_probs = [t for t in transitions if t.probability is None]

    if not transitions_without_probs:
        # All transitions already have probabilities - don't override
        return

    if not transitions_with_probs:
        # No transitions have probabilities - use uniform decomposition
        individual_prob = decompose_probability_uniformly(
            probability,
            len(transitions)
        )
        for transition in transitions:
            transition.probability = individual_prob
    else:
        # Mixed case: some have probabilities, some don't
        # Calculate what's "left over" for the unassigned transitions
        assigned_prob_product = 1.0
        for transition in transitions_with_probs:
            assigned_prob_product *= transition.probability

        # Remaining probability to distribute
        remaining_prob = probability / assigned_prob_product if assigned_prob_product > 0 else probability

        # Distribute remaining probability uniformly among unassigned transitions
        if transitions_without_probs and remaining_prob > 0:
            individual_prob = decompose_probability_uniformly(
                remaining_prob,
                len(transitions_without_probs)
            )
            for transition in transitions_without_probs:
                transition.probability = individual_prob
