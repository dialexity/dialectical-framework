
from dialectical_framework.analyst.domain.transition import Transition


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
    transitions_with_probs = [t for t in transitions if t.probability is not None and t.probability != 0]
    transitions_without_probs = [t for t in transitions if t.probability is None or t.probability == 0]

    if not transitions_without_probs:
        # All transitions already have probabilities - don't override
        return

    if not transitions_with_probs:
        # No transitions have probabilities - use uniform decomposition
        individual_prob = _decompose_probability_uniformly(
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
            individual_prob = _decompose_probability_uniformly(
                remaining_prob,
                len(transitions_without_probs)
            )
            for transition in transitions_without_probs:
                transition.probability = individual_prob


def _decompose_probability_uniformly(probability: float, num_transitions: int) -> float:
    """
    Decompose probability uniformly across all transitions using nth root

    Args:
        probability: Overall probability (0.0 to 1.0)
        num_transitions: Number of transitions

    Returns:
        Individual transition probability that when multiplied gives cycle_probability
    """
    if num_transitions == 0:
        return 0.0

    return probability ** (1.0 / num_transitions)
