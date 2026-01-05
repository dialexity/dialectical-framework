"""
Utility functions for ordering transitions in cycles and spirals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel


def order_transitions(transitions: list[Transition], wheel: Optional[Wheel] = None) -> list[Transition]:
    """
    Order transitions by their source segment's position in wheel.segments_ordered.

    Works for both Cycles and Spirals:
    - Orders transitions by which segment they originate from
    - Segments are ordered by wheel.segments_ordered (based on ta_cycle)
    - Works whether transitions are continuous (Cycle) or discrete (Spiral)

    Args:
        transitions: List of Transition nodes to order
        wheel: Optional Wheel for segment-based ordering. If None, uses component chain ordering.

    Returns:
        List of Transition nodes in order, or empty list if no transitions

    Example:
        Cycle: T1 → A1 → T2 → A2 (ordered by source segment: T1, A1, T2, A2)
        Spiral: T1- → A1+, A1- → T2+, T2- → A2+ (ordered by source segment: T1, A1, T2, A2)
    """
    if not transitions:
        return []

    if not wheel:
        # No wheel context yet (e.g., during wheel building)
        # Fall back to component chain ordering
        return _order_by_component_chain(transitions)

    return _order_by_wheel_segments(transitions, wheel)


def _order_by_wheel_segments(transitions: list[Transition], wheel: Wheel) -> list[Transition]:
    """
    Order transitions by their source segment's position in wheel.segments_ordered.

    Used for Spirals where transitions connect segments (not exact components):
    - Transition from segment 1 should come before transition from segment 2
    - Segments are ordered by wheel.segments_ordered (based on ta_cycle)

    Algorithm:
    1. Get wheel.segments_ordered - ordered list of WheelSegments
    2. For each transition, find which segment its source component belongs to
    3. Sort transitions by their source segment's position in segments_ordered
    """
    try:
        # Get ordered segments from wheel
        segments = wheel.segments_ordered
    except (ValueError, AttributeError):
        # Fallback if segments_ordered not available - return unsorted
        return transitions

    # Build map: (wisdom_unit_uid, side) -> segment position
    segment_position = {}
    for i, seg in enumerate(segments):
        key = (seg.wisdom_unit.uid, seg.side)
        segment_position[key] = i

    # For each transition, find its source segment's position
    transition_positions = []
    for trans in transitions:
        source_result = trans.source.get()
        if not source_result:
            continue

        source_comp, _ = source_result

        # Find which segment this source component belongs to
        source_segment = trans.get_source_wheel_segment(wheel=wheel)

        if not source_segment:
            # Can't find segment, put at end
            transition_positions.append((len(segments), trans))
            continue

        # Get segment position
        key = (source_segment.wisdom_unit.uid, source_segment.side)
        position = segment_position.get(key, len(segments))
        transition_positions.append((position, trans))

    # Sort by segment position
    transition_positions.sort(key=lambda x: x[0])

    return [trans for _, trans in transition_positions]


def _order_by_component_chain(transitions: list[Transition]) -> list[Transition]:
    """
    Order transitions by following the source→target chain.

    Used when wheel context is not available (e.g., during wheel construction).
    Works for Cycles where transitions form a continuous chain.

    Algorithm:
    1. Start with first transition's source component
    2. Find transition whose source matches current target
    3. Continue until all transitions are ordered

    Note: For Spirals with discrete transitions, this may not produce
    a meaningful order. Prefer wheel segment ordering when available.
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
