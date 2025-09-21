import math
from typing import Tuple


def pm_with_zeros_and_nones_handled(pair: Tuple[float | None, float | None], p = 4) -> float | None:
    """
    This is intended for calculating power mean of relevance score for symmetrical components
    """
    one = pair[0]
    two = pair[1]
    if one is None and two is None:
        return None
    elif one is None or two is None:
        return one or two
    elif one == 0 or two == 0:
        return 0
    else:
        values = [one, two]

        if p == 0:
            return math.exp(sum(math.log(x) for x in values) / len(values))
        elif p == float('inf'):
            return max(values)
        elif p == float('-inf'):
            return min(values)
        else:
            return (sum(x ** p for x in values) / len(values)) ** (1 / p)