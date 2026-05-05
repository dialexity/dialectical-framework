"""
Shared helper for building LLM prompt context from wheel edge segments.

A wheel edge (Transition) connects two main statements. Each main statement
belongs to a PP's T-side or A-side. The source segment becomes the
Transformation's "T context" and the target becomes its "A context".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.wheel_segment import WheelSegment


def build_edge_context(source_segment: WheelSegment, target_segment: WheelSegment) -> str:
    """
    Build LLM prompt context from two WheelSegments.

    The source segment is presented as the T-side (thesis context) and
    the target segment as the A-side (antithesis context), regardless
    of which actual PP side they come from.

    Args:
        source_segment: The segment containing the edge's source (becomes T-side)
        target_segment: The segment containing the edge's target (becomes A-side)

    Returns:
        Multi-line context string with T, T+, T-, A, A+, A- labels
    """
    parts = []

    source_t = source_segment.t.get()
    source_t_plus = source_segment.t_plus.get()
    source_t_minus = source_segment.t_minus.get()
    target_t = target_segment.t.get()
    target_t_plus = target_segment.t_plus.get()
    target_t_minus = target_segment.t_minus.get()

    if source_t:
        parts.append(f"T: {source_t[0].prompt_text}")
    if source_t_plus:
        parts.append(f"T+: {source_t_plus[0].prompt_text}")
    if source_t_minus:
        parts.append(f"T-: {source_t_minus[0].prompt_text}")
    if target_t:
        parts.append(f"A: {target_t[0].prompt_text}")
    if target_t_plus:
        parts.append(f"A+: {target_t_plus[0].prompt_text}")
    if target_t_minus:
        parts.append(f"A-: {target_t_minus[0].prompt_text}")

    return "\n".join(parts)
