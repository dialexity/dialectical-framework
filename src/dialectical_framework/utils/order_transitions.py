"""
Utility functions for ordering transitions in cycles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition


def order_transitions(transitions: list[Transition]) -> list[Transition]:
    """
    Order transitions by following the source→target chain.

    Works for Cycles where transitions form a continuous chain,
    producing ordering based on the component chain.

    Algorithm:
    1. Start with first transition's source component
    2. Find transition whose source matches current target
    3. Continue until all transitions are ordered

    Args:
        transitions: List of Transition nodes to order

    Returns:
        List of Transition nodes in order, or empty list if no transitions

    Example:
        Cycle: T1 → A1 → T2 → A2 (ordered by source→target chain)
    """
    if not transitions:
        return []

    # Build map: source_id -> transition
    source_map = {}
    for trans in transitions:
        source_result = trans.source.get()
        if source_result:
            source_comp, _ = source_result
            source_map[source_comp._id] = trans

    # Start with first transition
    ordered = [transitions[0]]
    used_ids = {transitions[0]._id}

    # Follow chain: current target → find transition with that source
    while len(ordered) < len(transitions):
        current_trans = ordered[-1]
        target_result = current_trans.target.get()

        if not target_result:
            # Can't continue chain, add remaining in original order
            for trans in transitions:
                if trans._id not in used_ids:
                    ordered.append(trans)
            break

        target_comp, _ = target_result
        next_trans = source_map.get(target_comp._id)

        if next_trans and next_trans._id not in used_ids:
            ordered.append(next_trans)
            used_ids.add(next_trans._id)
        else:
            # Chain broken, add remaining in original order
            for trans in transitions:
                if trans._id not in used_ids:
                    ordered.append(trans)
            break

    return ordered
