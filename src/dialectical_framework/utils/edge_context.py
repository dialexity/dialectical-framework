"""
Shared helpers for building LLM prompt context from wheel edge segments.

A wheel edge (Transition) connects two main statements. Each main statement
belongs to a PP's T-side or A-side. The source segment becomes the
Transformation's "T context" and the target becomes its "A context".

Also home to the REFINEMENT context — the coarser Transformations an edge
descends from, rendered as the broader journey the current step has to be more
concrete than. It lives here rather than in either concern because BOTH generate
against it and `transformation_generation` already imports `action_extraction`,
so the other direction would be circular. Keeping the three "refine from this"
sentences side by side is also the point: they differ deliberately, each naming
the line of the hierarchy its own position descends from, and a reviewer should
be able to see all three at once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dialectical_framework.graph.repositories.transformation_repository import \
        CoarserTransformation
    from dialectical_framework.graph.wheel_segment import WheelSegment

#: What Ac- is told to refine. Kept as the whole tetrad rather than one line
#: because this is the wording the Ac- prompt shipped with, and it is the call
#: whose history every later call in the tetrad reads.
REFINE_TETRAD = """Your tetrad details one sub-step of the most-indented transition above.
Be more concrete and specific than the broader path, while staying coherent
with its overall direction."""

#: What Ac+ is told to refine — the parents' `Action:` line. This is the position
#: the refinement recursion is FOR ("find a friend" at one perspective becoming
#: "find a colleague who could be your friend" at three), and until 2026-09-11 it
#: was the one call in the tetrad that saw no coarser context at all.
REFINE_ACTION = """The Action line of the most-indented transition above is the broader move your
action refines. Be more concrete and specific than it, while staying coherent
with its overall direction."""

#: What Re+/Re- are told to refine — the parents' `Reflection:` line. A parent
#: Transformation encodes both spiral directions, so its Reflection IS the coarser
#: reflection for this same edge, even though Re is generated from the OPPOSITE
#: edge's context.
REFINE_REFLECTION = """The Reflection line of the most-indented transition above is the broader
reflection your Re+ refines. Be more concrete and specific than it, while
staying coherent with its overall direction."""


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


def build_coarser_context(parents: list[CoarserTransformation]) -> Optional[str]:
    """
    Build hierarchical refinement context from coarser parent Transformations.

    Parents are ordered coarsest-first. Each represents a broader transition that
    the current edge is a sub-step of. Both the `Action:` and `Reflection:` line
    are rendered per parent, because a Transformation encodes both spiral
    directions and the two are refined by different calls (Ac+ reads the first,
    Re+ the second).

    Returns:
        Formatted string for LLM prompt, or None if no parents
    """
    if not parents:
        return None

    parts = []
    current_edge_id = None

    for ct in parents:
        tr = ct.transformation

        edge_result = tr.edge.get()
        if not edge_result:
            continue
        tr_edge, _ = edge_result

        edge_source = tr_edge.source.get()
        edge_target = tr_edge.target.get()
        if not edge_source or not edge_target:
            continue

        source_text = edge_source[0].prompt_text
        target_text = edge_target[0].prompt_text

        indent = "  " * (ct.layer - 1)

        if tr_edge._id != current_edge_id:
            current_edge_id = tr_edge._id
            parts.append(f"{indent}\"{source_text}\" → \"{target_text}\":")
        else:
            parts.append(f"{indent}(variant):")

        ac_plus_result = tr.ac_plus.get()
        if ac_plus_result:
            trans, _ = ac_plus_result
            parts.append(f"{indent}  Action: {trans.instruction}")

        re_plus_result = tr.re_plus.get()
        if re_plus_result:
            trans, _ = re_plus_result
            parts.append(f"{indent}  Reflection: {trans.instruction}")

    return "\n".join(parts) if parts else None


def coarser_journey_section(parent_context: Optional[str], refine: str) -> str:
    """
    Wrap rendered refinement context in the `<broader_journey>` prompt section.

    `refine` is the site-specific instruction — one of the three `REFINE_*`
    constants above — because what a call should take from the hierarchy depends
    on which position it is generating.

    Returns:
        The section (with its trailing blank line, ready to concatenate), or ""
        when there is nothing coarser. Empty rather than a "no parents" note on
        purpose: a layer-1 wheel has no ancestry to be missing, so saying so
        would invite the model to treat a complete answer as a gap.
    """
    if not parent_context:
        return ""

    return f"""
<broader_journey>
Your current edge is one detailed sub-step within a broader transition.
Below is the hierarchy from broadest to most specific (indented = more detailed):

{parent_context}

{refine}
</broader_journey>

"""
