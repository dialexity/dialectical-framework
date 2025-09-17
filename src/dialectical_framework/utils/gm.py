from statistics import geometric_mean


def gm_with_zeros_and_nones_handled(values: list[float]) -> float | None:
    """Return GM of positives; 0.0 if any zero present; None if empty."""
    has_zero = any(v == 0.0 for v in values)
    positives = [v for v in values if v is not None and v > 0.0]
    all_nones = all(v is None for v in values)
    if not values:  # list is empty
        return None
    if all_nones:
        return None
    if has_zero:
        return 0.0
    return geometric_mean(positives) if positives else 0.0  # if only zeros, GM=0.0