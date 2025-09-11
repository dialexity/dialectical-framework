from abc import abstractmethod
from itertools import permutations
from typing import Union

from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.reloadable import Reloadable
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


class CausalitySequencer(Reloadable):
    @abstractmethod
    async def arrange(
        self, thoughts: Union[list[str], list[WisdomUnit], list[DialecticalComponent]]
    ) -> list[Cycle]:
        """
        Arranges items in multiple sequences and arranges them as cycles.
        IMPORTANT: we don't do single sequence estimation isolated, because they all depend on each other.
        Isolated estimation would lead to some sort of unnormalized probabilities, which is not good.
        """
        ...


def generate_permutation_sequences(
    dialectical_components: list[DialecticalComponent],
) -> list[list[DialecticalComponent]]:
    if len(dialectical_components) < 2:
        return []

    first, rest = dialectical_components[0], dialectical_components[1:]
    sequences = list([first, *p] for p in permutations(rest))
    return sequences


def generate_compatible_sequences(
    ordered_wisdom_units: list[WisdomUnit],
) -> list[list[DialecticalComponent]]:
    """
    Generate all circular, diagonally symmetric arrangements for T/A pairs.

    Each wisdom unit consists of a thesis (`T`) and its antithesis (`A`). This function arranges them
    around a circle (of length 2n, where n is the number of units) such that:

    1. **Circular Symmetry**: For each pair, if `T_i` is at position `p`, then `A_i` is at position `(p + n) % (2n)`.
    2. **Order Preservation**: The order of all `T`s matches their input order and is strictly increasing
       in placement (i.e., `T1` before `T2`, etc.).
    3. **Start Condition**: The sequence always starts with the first thesis (`T1`) at position 0.

    Parameters:
        ordered_wisdom_units (list): List of wisdom units, each having `.t.alias` (thesis) and `.a.alias` (antithesis).

    Returns:
        list of list: Each inner list is a possible arrangement; positions 0..n-1 represent the 'top row'
        (or first semi-circle), and positions n..2n-1 represent the 'bottom row' (or mirrored second semi-circle),
        such that the diagonal relationship and thesis order constraints are always met.

    Example:
        For input units T1/A1, T2/A2, T3/A3, T4/A4, a valid output can be:
            [T1, T2, A4, T3, A1, A2, T4, A3]
        Which means:
            Top:    T1 -> T2 -> A4 -> T3
            Bottom: A1 -> A2 -> T4 -> A3 (mirrored on the circle)
    """

    n = len(ordered_wisdom_units)
    ts = [u.t for u in ordered_wisdom_units]
    as_ = [u.a for u in ordered_wisdom_units]
    size = 2 * n

    results = []

    # Step 1: set T1 at 0, its diagonal A1 at n
    def backtrack(t_positions, next_t_idx):
        if next_t_idx == n:
            # Fill arrangement based on t_positions
            arrangement = [None] * size
            occupied = set()
            for t_idx, pos in enumerate(t_positions):
                arrangement[pos] = ts[t_idx]
                diag = (pos + n) % size
                arrangement[diag] = as_[t_idx]
                occupied.add(pos)
                occupied.add(diag)
            results.append(arrangement)
            return

        # Next ti to place: always in order, always > previous ti's position
        # Skip positions already assigned (to ensure symmetry and distinctness)
        prev_pos = t_positions[-1]
        for pos in range(prev_pos + 1, size):
            diag = (pos + n) % size

            # Check if pos or diag are used by previous Ts/A's
            collision = False
            for prev_t_pos in t_positions:
                if pos == prev_t_pos or diag == prev_t_pos:
                    collision = True
                    break
                prev_diag = (prev_t_pos + n) % size
                if pos == prev_diag or diag == prev_diag:
                    collision = True
                    break
            if collision:
                continue

            # Place next T at pos, corresponding A at diag
            backtrack(t_positions + [pos], next_t_idx + 1)

    # T1 fixed at position 0
    backtrack([0], 1)
    return results
