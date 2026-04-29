"""
Utility functions for generating statement sequences.

These functions produce ordered arrangements of Statements for
cycle generation in the causality sequencing pipeline.
"""

from __future__ import annotations

from itertools import permutations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.perspective import Perspective


def generate_permutation_sequences(
    statements: list[Statement],
) -> list[list[Statement]]:
    """
    Generate all permutations of components with a fixed first element.

    Creates permutation sequences where the first component is fixed and the
    remaining components are permuted. This reduces redundant cycles since
    circular sequences starting at different points are equivalent.

    Args:
        statements: Statements to arrange into sequences.

    Returns:
        List of statement sequences. For a single statement, returns [[statement]].
        For multiple statements, each sequence starts with the first input
        statement followed by a unique permutation of remaining statements.
        Returns empty list if no statements provided.

    Example:
        Given statements [A, B, C]:
        - Returns [[A, B, C], [A, C, B]]
        - First element A is fixed, B and C are permuted
    """
    if len(statements) == 0:
        return []

    if len(statements) == 1:
        return [statements]

    first, rest = statements[0], statements[1:]
    sequences = list([first, *p] for p in permutations(rest))
    return sequences


def generate_compatible_sequences(
    ordered_perspectives: list[Perspective],
) -> list[list[Statement]]:
    """
    Generate circular arrangements with diagonal symmetry for thesis/antithesis pairs.

    Each Perspective contains a thesis (T) and antithesis (A). This function arranges
    all T/A components around a conceptual circle of size 2n (where n = number of units)
    such that:

    1. **Diagonal Symmetry**: For each pair, if T_i is at position p, then A_i is at
       position (p + n) % (2n). This ensures each thesis is "opposite" its antithesis.

    2. **Order Preservation**: Theses maintain their relative input order with strictly
       increasing positions (T1 before T2 before T3, etc.).

    3. **Fixed Start**: The sequence always begins with T1 at position 0 to eliminate
       rotationally equivalent arrangements.

    Args:
        ordered_perspectives: Perspectives in desired priority order. Each must have
            both T and A components connected.

    Returns:
        List of valid arrangements. Each arrangement is a list of 2n components where
        positions 0 to n-1 form the "top half" and positions n to 2n-1 form the "bottom
        half" (diagonally mirrored).

    Raises:
        ValueError: If any Perspective is missing its T or A component.

    Example:
        For units [PP1(T1/A1), PP2(T2/A2), PP3(T3/A3), PP4(T4/A4)], a valid output:
            [T1, T2, A4, T3, A1, A2, T4, A3]

        Interpreted as a circle:
            Top:    T1 → T2 → A4 → T3
            Bottom: A1 → A2 → T4 → A3  (diagonally opposite)

        Here T1↔A1, T2↔A2, T3↔A3, T4↔A4 are all diagonal pairs.

    Note:
        The number of valid arrangements grows combinatorially. For practical use,
        this function is designed for small unit counts (2-4 units).
    """
    n = len(ordered_perspectives)

    # Extract T and A components from graph-native Perspectives
    ts: list[Statement] = []
    as_: list[Statement] = []
    for u in ordered_perspectives:
        # Get T component (returns tuple of (component, relationship) or None)
        t_result = u.t.get()
        if t_result:
            ts.append(t_result[0])  # Extract component from tuple
        else:
            raise ValueError(f"Perspective {u.hash} missing T component")

        # Get A component (returns tuple of (component, relationship) or None)
        a_result = u.a.get()
        if a_result:
            as_.append(a_result[0])  # Extract component from tuple
        else:
            raise ValueError(f"Perspective {u.hash} missing A component")

    size = 2 * n

    results: list[list[Statement]] = []

    def backtrack(t_positions: list[int], next_t_idx: int) -> None:
        """Recursively place theses while respecting constraints."""
        if next_t_idx == n:
            # All theses placed - build the complete arrangement
            arrangement: list[Statement | None] = [None] * size
            for t_idx, pos in enumerate(t_positions):
                arrangement[pos] = ts[t_idx]
                diag = (pos + n) % size
                arrangement[diag] = as_[t_idx]
            # Type narrowing: we know all positions are filled
            results.append([c for c in arrangement if c is not None])
            return

        # Try placing next thesis at each valid position after the previous thesis
        prev_pos = t_positions[-1]
        for pos in range(prev_pos + 1, size):
            diag = (pos + n) % size

            # Check for collisions with previously placed components
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

    # T1 fixed at position 0, start recursion for remaining theses
    backtrack([0], 1)
    return results
