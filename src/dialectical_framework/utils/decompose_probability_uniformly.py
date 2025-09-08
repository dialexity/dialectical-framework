def decompose_probability_uniformly(probability: float, num_transitions: int) -> float:
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
