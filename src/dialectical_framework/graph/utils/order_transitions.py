"""
Utility functions for ordering transitions in cycles and spirals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition


def order_transitions(transitions: list[Transition]) -> list[Transition]:
    """
    Order transitions by following source->target chain.

    Algorithm:
    1. Build adjacency map: source_uid -> Transition
    2. Start from first transition
    3. Follow source->target chain until loop completes

    Args:
        transitions: List of Transition nodes to order

    Returns:
        List of Transition nodes in order, or empty list if no transitions
    """
    if not transitions:
        return []

    # Build adjacency map: source_uid -> Transition
    adjacency = {}
    for trans in transitions:
        source_nodes = [src for src, _ in trans.source.all()]
        if source_nodes:
            source_uid = source_nodes[0].uid
            adjacency[source_uid] = trans

    # Start from first transition and follow the chain
    ordered = []
    current_trans = transitions[0]
    visited = set()

    while current_trans and current_trans.uid not in visited:
        visited.add(current_trans.uid)
        ordered.append(current_trans)

        # Get target of current transition
        target_nodes = [tgt for tgt, _ in current_trans.target.all()]
        if not target_nodes:
            break

        target_uid = target_nodes[0].uid

        # Find next transition that starts from this target
        current_trans = adjacency.get(target_uid)

        # Break if we've returned to start (completed the cycle)
        if current_trans and current_trans.uid in visited:
            break

    return ordered
