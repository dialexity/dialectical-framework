"""
Shared rendering utilities for graph nodes.

Provides consistent alias computation and formatting used by both
dialectical_context (compact dump) and inspect_node (verbose detail).
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective

_REL_TYPE_TO_LABEL: dict[str, str] = {
    "T": "T",
    "A": "A",
    "T_PLUS": "T+",
    "T_MINUS": "T-",
    "A_PLUS": "A+",
    "A_MINUS": "A-",
}


def build_pp_index(nexus: Nexus) -> dict[int, int]:
    """
    Build the canonical perspective index map from a Nexus.

    Returns a dict mapping pp._id → 1-based index, using the same ordering
    that nexus.perspectives.all() returns (active perspectives only).
    """
    pp_index: dict[int, int] = {}
    for i, (pp, _) in enumerate(nexus.perspectives.all(), 1):
        if not pp.discarded:
            pp_index[pp._id] = i
    return pp_index


def find_nexus_for_cycle(cycle) -> Optional[Nexus]:
    """Find the Nexus that owns a Cycle's perspectives."""
    pps = cycle.perspectives
    if not pps:
        return None
    nexus_result = pps[0].nexus.get()
    if nexus_result:
        return nexus_result[0]
    return None


def find_nexus_for_wheel(wheel) -> Optional[Nexus]:
    """Find the Nexus that owns a Wheel (via its parent Cycle or perspectives)."""
    cycle_result = wheel.cycle.get()
    if cycle_result:
        return find_nexus_for_cycle(cycle_result[0])
    pps = wheel._perspectives
    if pps:
        nexus_result = pps[0].nexus.get()
        if nexus_result:
            return nexus_result[0]
    return None


def find_nexus_for_transformation(tr) -> Optional[Nexus]:
    """Find the Nexus for a Transformation (direct relationship)."""
    nexus_result = tr.nexus.get()
    if nexus_result:
        return nexus_result[0]
    return None


def component_alias(stmt, pp_index: Optional[dict[int, int]] = None) -> str:
    """
    Resolve a statement (component) to its display alias.

    If pp_index is provided, produces nexus-indexed labels like 'T1-', 'A2+'.
    If pp_index is None, produces perspective-local labels like 'T-', 'A+'.
    """
    from dialectical_framework.graph.repositories.perspective_repository import (
        PerspectiveRepository,
    )

    pp_repo = PerspectiveRepository()
    for pp, rel_type in pp_repo.find_by_statement(stmt):
        base = _REL_TYPE_TO_LABEL.get(rel_type, rel_type)
        if pp_index is not None:
            idx = pp_index.get(pp._id, 0)
            if idx:
                if len(base) == 2 and base[1] in "+-":
                    return f"{base[0]}{idx}{base[1]}"
                return f"{base}{idx}"
        return base
    return "?"


def format_edge_label(edge, pp_index: Optional[dict[int, int]] = None) -> str:
    """Format 'source → target' for a Transition (wheel edge or position)."""
    source_result = edge.source.get()
    target_result = edge.target.get()
    if not source_result or not target_result:
        return ""

    src = component_alias(source_result[0], pp_index)
    tgt = component_alias(target_result[0], pp_index)
    return f"{src} → {tgt}"


def format_spiral(wheel, pp_index: Optional[dict[int, int]] = None) -> str:
    """Format the wheel's discrete spiral pairs: T1- → A2+, A2+ → A1-, ..."""
    ordered_edges = wheel.edges
    if not ordered_edges:
        return ""

    pairs = []
    for edge in ordered_edges:
        label = format_edge_label(edge, pp_index)
        if label:
            pairs.append(label)

    return ", ".join(pairs)
