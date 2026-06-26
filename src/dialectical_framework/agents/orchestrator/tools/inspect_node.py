"""
Inspect node tool for the Orchestrator.

Provides detailed inspection of any node by hash, routing display
logic based on node type (Perspective, Statement, Polarity, Nexus).

Example outputs (what the LLM receives):
-----------------------------------------

No status shown for normal committed nodes. Only DRAFT (uncommitted) or
DISCARDED get tagged in the header.

--- Perspective ---

## Perspective [a3f82c1]
Intent: navigating remote work tensions

T- = Isolation
Explanation: Lack of social connection from working alone
T = Remote Work
Explanation: Working from a location other than the office
T+ = Flexibility
Explanation: Freedom to choose when and where to work
A- = Rigidity
Explanation: Fixed schedules and mandatory presence
A = Office Work
Explanation: Traditional co-located workplace
A+ = Collaboration
Explanation: Spontaneous interaction and team cohesion

Heuristic Similarity (HS): 0.823
Score: 0.7142 (P=0.8500, R=0.8400)
Quality: diff_t=0.156, diff_a=0.203, area=0.712, rect=0.8834
Derived from: [f9c12ab]
Nexus memberships: [f1234ab (Exploring remote vs office...)]

--- Statement ---

## Statement [d9a1b3c]

Work-life balance
Explanation: The equilibrium between professional demands and personal life

Meaning: dx://taxonomy/System(General.v1)/Viability/Integrity/Balance
Score: 0.6200 (P=0.7800, R=0.7950)

Used in Perspectives:
  - [a3f82c1] as T+
  - [b7d91e4] as A

--- Polarity ---

## Polarity [c42fe88]

T: Remote Work ↔ A: Office Work, HS=0.82

Active Perspectives using this Polarity:
  - [a3f82c1] intent=navigating remote work tensions
  - [b7d91e4]
  (1 discarded perspective(s) also reference this Polarity)

--- Nexus ---

## Nexus [f1234ab]
Nexus(f1234ab, pps=2, preset=balanced, intent=Exploring remote vs office tradeoffs)

Perspectives (2):
  - [a3f82c1] intent=navigating remote work tensions
  - [b7d91e4]

--- Cycle ---

## Cycle [c9e2f01]
Intent: preset:balanced

Sequence: T1 → T2 → T1...

Perspectives:
  T1 = [a3f82c1] — "Remote Work"
  T2 = [b7d91e4] — "Office Work"

Causality probability: 0.720

Rationale: Remote work flexibility enables office collaboration patterns...

Wheels (2):
  - [w88a3f2]
  - [w99b4c1]

--- Wheel ---

## Wheel [w88a3f2]

TA-sequence: T1 → A2 → A1 → T2 → T1...
Spiral: T1- → A2+, A2+ → A1-, A1- → T2+, T2+ → T1-

Parent Cycle: [c9e2f01] T1 → T2 → T1...
Causality probability: 0.680

Perspectives (2):
  T1 = [a3f82c1] — "Remote Work"
  T2 = [b7d91e4] — "Office Work"

Transformations (2):
  - [t44bc12] (T1- → A2+)
  - [t55de34] (A1- → T2+)

Synthesis (1):
  - [s12ab34]

Rationale: This arrangement places isolation's resolution through collaboration...

--- Transformation ---

## Transformation [t44bc12]
Edge: T1- → A2+

Ac+ (T1- → A2+): "Give structured choices within safe boundaries"
  scores: insight=0.45, proactiveness=0.72, HS=0.80, feasibility=0.82
Re+ (A2- → T1+): "Recognize that safety serves growth"
  scores: insight=0.52, proactiveness=0.25, HS=0.75, feasibility=0.70
Ac- (T1+ → A2-): "Impose boundaries without voice"
  scores: insight=0.20, proactiveness=0.70
Re- (A2+ → T1-): "Convince yourself that control IS love"
  scores: insight=0.10, proactiveness=0.15

Rationale: The action pathway transforms over-control into structured autonomy...

--- Synthesis ---

## Synthesis [s12ab34]
Spiral: T1- → A2+, A2+ → A1-, A1- → T2+, T2+ → T1-
Parent Wheel: [w88a3f2]

S+: "Graduated autonomy within a holding environment"
S-: "Oscillation between smothering and sudden withdrawal"

Rationale: The positive synthesis emerges from simultaneous operation...
"""

from __future__ import annotations

from typing import Annotated, Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.rendering import (
    build_pp_index,
    component_alias,
    format_edge_label,
    format_spiral,
    find_nexus_for_cycle,
    find_nexus_for_wheel,
    find_nexus_for_transformation,
)
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.wheel import Wheel


def _status_tag(node) -> str:
    """Return status tag only for non-normal states."""
    if getattr(node, "discarded", None):
        return " DISCARDED"
    if not node.is_committed:
        return " DRAFT"
    return ""


def _node_id(node) -> str:
    """Format node identifier."""
    return node.short_hash or "DRAFT"


def _inspect_perspective(pp: Perspective) -> str:
    """Build detailed inspection output for a Perspective."""
    lines: list[str] = []

    # Header
    lines.append(f"## Perspective [{_node_id(pp)}]{_status_tag(pp)}")
    if pp.discarded:
        lines.append(f"Discarded: {pp.discarded}")
    if pp.intent:
        lines.append(f"Intent: {pp.intent}")
    lines.append("")

    # Full formatted positions with rationale explanations
    lines.append(f"{pp:positions:1}")
    lines.append("")

    # Heuristic similarity from Polarity
    polarity_result = pp.polarity.get()
    if polarity_result:
        pol, _ = polarity_result
        hs = pol.heuristic_similarity
        if hs is not None:
            lines.append(f"Heuristic Similarity (HS): {hs:.3f}")

    # Tetrad quality metrics
    diff_t = pp.diff_t
    diff_a = pp.diff_a
    area = pp.area_normalized
    rect = pp.rectangularity
    metrics: list[str] = []
    if diff_t is not None:
        metrics.append(f"diff_t={diff_t:.3f}")
    if diff_a is not None:
        metrics.append(f"diff_a={diff_a:.3f}")
    if area is not None:
        metrics.append(f"area={area:.3f}")
    if rect is not None:
        metrics.append(f"rect={rect:.4f}")
    if metrics:
        lines.append(f"Quality: {', '.join(metrics)}")

    # CHANGED_TO lineage
    derived_from_items = pp.derived_from.all()
    changed_to_items = pp.changed_to.all()
    if derived_from_items:
        sources = [f"[{src.short_hash}]" for src, _ in derived_from_items]
        lines.append(f"Derived from: {', '.join(sources)}")
    if changed_to_items:
        targets = [f"[{tgt.short_hash}]" for tgt, _ in changed_to_items]
        lines.append(f"Changed to: {', '.join(targets)}")

    # Nexus memberships
    nexus_items = pp.nexus.all()
    if nexus_items:
        nexus_strs = []
        for nexus_node, _ in nexus_items:
            label = nexus_node.short_hash
            if nexus_node.intent:
                label += f" ({nexus_node.intent[:30]})"
            nexus_strs.append(f"[{label}]")
        lines.append(f"Nexus memberships: {', '.join(nexus_strs)}")

    return "\n".join(lines)


def _inspect_statement(stmt: Statement) -> str:
    """Build detailed inspection output for a Statement."""
    lines: list[str] = []

    # Header
    lines.append(f"## Statement [{_node_id(stmt)}]{_status_tag(stmt)}")
    if stmt.discarded:
        lines.append(f"Discarded: {stmt.discarded}")
    lines.append("")

    # Full text with rationale (long format)
    lines.append(f"{stmt:long}")
    lines.append("")

    # Meaning
    if stmt.meaning:
        lines.append(f"Meaning: {stmt.meaning}")

    # Which Perspectives use this statement
    repo = PerspectiveRepository()
    usages = repo.find_by_statement(stmt)
    if usages:
        lines.append("")
        lines.append("Used in Perspectives:")
        for pp, rel_type in usages:
            discarded_marker = " [DISCARDED]" if pp.discarded else ""
            lines.append(f"  - [{pp.short_hash}] as {rel_type}{discarded_marker}")

    return "\n".join(lines)


def _inspect_polarity(pol: Polarity) -> str:
    """Build detailed inspection output for a Polarity."""
    lines: list[str] = []

    # Header
    lines.append(f"## Polarity [{_node_id(pol)}]{_status_tag(pol)}")
    lines.append("")

    # T-A display
    lines.append(str(pol))
    lines.append("")

    # Perspectives referencing this Polarity (non-discarded only)
    repo = PerspectiveRepository()
    perspectives = repo.find_by_polarity(pol)
    active_pps = [pp for pp in perspectives if not pp.discarded]
    discarded_pps = [pp for pp in perspectives if pp.discarded]

    if active_pps:
        lines.append("Active Perspectives using this Polarity:")
        for pp in active_pps:
            intent_str = f" intent={pp.intent}" if pp.intent else ""
            lines.append(f"  - [{pp.short_hash}]{intent_str}")

    if discarded_pps:
        lines.append(f"  ({len(discarded_pps)} discarded perspective(s) also reference this Polarity)")

    if not active_pps and not discarded_pps:
        lines.append("No Perspectives reference this Polarity.")

    return "\n".join(lines)


def _inspect_nexus(nexus: Nexus) -> str:
    """Build detailed inspection output for a Nexus."""
    lines: list[str] = []

    # Header
    title_suffix = f" — {nexus.title}" if nexus.title else ""
    lines.append(f"## Nexus [{_node_id(nexus)}]{title_suffix}{_status_tag(nexus)}")
    lines.append(repr(nexus))
    lines.append("")

    # List member PPs compactly
    pp_items = nexus.perspectives.all()
    if pp_items:
        lines.append(f"Perspectives ({len(pp_items)}):")
        for pp, _ in pp_items:
            discarded_marker = " [DISCARDED]" if pp.discarded else ""
            intent_str = f" intent={pp.intent}" if pp.intent else ""
            lines.append(f"  - [{pp.short_hash}]{intent_str}{discarded_marker}")
    else:
        lines.append("No Perspectives in this Nexus.")

    return "\n".join(lines)


def _inspect_cycle(cycle: Cycle) -> str:
    """Build detailed inspection output for a Cycle."""
    lines: list[str] = []

    lines.append(f"## Cycle [{_node_id(cycle)}]{_status_tag(cycle)}")
    if cycle.intent:
        lines.append(f"Intent: {cycle.intent}")
    lines.append("")

    # Resolve nexus for consistent indexing
    nexus = find_nexus_for_cycle(cycle)
    pp_index = build_pp_index(nexus) if nexus else None

    # T-causality sequence with nexus indices
    pps = cycle.perspectives
    if pps and pp_index:
        labels = [f"T{pp_index.get(pp._id, 0)}" for pp in pps]
        sequence = " → ".join(labels) + f" → {labels[0]}..."
        lines.append(f"Sequence: {sequence}")
    else:
        lines.append(f"Sequence: {cycle}")
    lines.append("")

    # Perspectives with labels
    if pps:
        lines.append("Perspectives:")
        for pp in pps:
            idx = pp_index.get(pp._id, 0) if pp_index else "?"
            t_result = pp.t.get() if pp.t else None
            t_text = f" — \"{t_result[0].text}\"" if t_result else ""
            lines.append(f"  T{idx} = [{pp.short_hash}]{t_text}")
    lines.append("")

    # Causality probability
    from dialectical_framework.graph.nodes.estimation import CausalityProbabilityEstimation
    for est, _ in cycle.estimations.all():
        if isinstance(est, CausalityProbabilityEstimation):
            lines.append(f"Causality probability: {est.value:.3f}")
            break

    # Rationales
    rationales = list(cycle.rationales.all())
    if rationales:
        lines.append("")
        for rationale, _ in rationales:
            if rationale.text:
                lines.append(f"Rationale: {rationale.text}")

    # Child wheels
    wheel_items = list(cycle.wheels.all())
    if wheel_items:
        lines.append("")
        lines.append(f"Wheels ({len(wheel_items)}):")
        for wheel, _ in wheel_items:
            lines.append(f"  - [{wheel.short_hash}]")

    return "\n".join(lines)


def _inspect_wheel(wheel: Wheel) -> str:
    """Build detailed inspection output for a Wheel."""
    lines: list[str] = []

    lines.append(f"## Wheel [{_node_id(wheel)}]{_status_tag(wheel)}")
    lines.append("")

    # Resolve nexus for consistent indexing
    nexus = find_nexus_for_wheel(wheel)
    pp_index = build_pp_index(nexus) if nexus else None

    # TA-sequence using nexus indices
    if pp_index:
        try:
            segs = wheel.segments
            if segs:
                labels = []
                for seg in segs:
                    idx = pp_index.get(seg._perspective._id, 0)
                    labels.append(f"{seg._side}{idx}")
                ta_seq = " → ".join(labels) + f" → {labels[0]}..."
                lines.append(f"TA-sequence: {ta_seq}")
        except (ValueError, AttributeError):
            pass
    else:
        ta_seq = wheel._format_edges("ta_sequence")
        if ta_seq:
            lines.append(f"TA-sequence: {ta_seq}")

    # Spiral (discrete edges with nexus indices)
    spiral_seq = format_spiral(wheel, pp_index)
    if spiral_seq:
        lines.append(f"Spiral: {spiral_seq}")
    lines.append("")

    # Parent cycle
    cycle_result = wheel.cycle.get()
    if cycle_result:
        cycle_obj, _ = cycle_result
        if pp_index:
            pps = cycle_obj.perspectives
            labels = [f"T{pp_index.get(pp._id, 0)}" for pp in pps]
            cycle_seq = " → ".join(labels) + f" → {labels[0]}..."
            lines.append(f"Parent Cycle: [{cycle_obj.short_hash}] {cycle_seq}")
        else:
            lines.append(f"Parent Cycle: [{cycle_obj.short_hash}] {cycle_obj}")

    # Causality probability
    from dialectical_framework.graph.nodes.estimation import CausalityProbabilityEstimation
    for est, _ in wheel.estimations.all():
        if isinstance(est, CausalityProbabilityEstimation):
            lines.append(f"Causality probability: {est.value:.3f}")
            break

    lines.append("")

    # Perspectives
    pps = wheel._perspectives
    if pps:
        lines.append(f"Perspectives ({len(pps)}):")
        for pp in pps:
            idx = pp_index.get(pp._id, 0) if pp_index else "?"
            t_result = pp.t.get() if pp.t else None
            t_text = f" — \"{t_result[0].text}\"" if t_result else ""
            lines.append(f"  T{idx} = [{pp.short_hash}]{t_text}")
        lines.append("")

    # Transformations
    transformations = wheel.transformations
    if transformations:
        lines.append(f"Transformations ({len(transformations)}):")
        for tr in transformations:
            edge_result = tr.edge.get()
            edge_str = ""
            if edge_result:
                label = format_edge_label(edge_result[0], pp_index)
                if label:
                    edge_str = f" ({label})"
            lines.append(f"  - [{tr.short_hash}]{edge_str}")
        lines.append("")

    # Synthesis
    synth_items = list(wheel.synthesis.all())
    if synth_items:
        lines.append(f"Synthesis ({len(synth_items)}):")
        for synth, _ in synth_items:
            lines.append(f"  - [{synth.short_hash}]")
        lines.append("")

    # Rationales
    rationales = list(wheel.rationales.all())
    if rationales:
        for rationale, _ in rationales:
            if rationale.text:
                lines.append(f"Rationale: {rationale.text}")

    return "\n".join(lines)


def _inspect_transformation(tr: Transformation) -> str:
    """Build detailed inspection output for a Transformation."""
    lines: list[str] = []

    lines.append(f"## Transformation [{_node_id(tr)}]{_status_tag(tr)}")

    # Resolve nexus for consistent indexing
    nexus = find_nexus_for_transformation(tr)
    pp_index = build_pp_index(nexus) if nexus else None

    # Edge context: which spiral step this transformation belongs to
    edge_result = tr.edge.get()
    if edge_result:
        edge_label = format_edge_label(edge_result[0], pp_index)
        if edge_label:
            lines.append(f"Edge: {edge_label}")
    lines.append("")

    # Positions with transition labels and scores
    from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation

    for position, manager in [
        ("Ac+", tr.ac_plus),
        ("Re+", tr.re_plus),
        ("Ac-", tr.ac_minus),
        ("Re-", tr.re_minus),
    ]:
        result = manager.get()
        if result:
            transition, rel = result
            text = transition.instruction or transition.summary or ""

            transition_label = format_edge_label(transition, pp_index)
            pos_display = f"{position} ({transition_label})" if transition_label else position
            lines.append(f"{pos_display}: \"{text}\"")

            # Scores
            scores = []
            if hasattr(rel, "insight") and rel.insight is not None:
                scores.append(f"insight={rel.insight:.2f}")
            if hasattr(rel, "proactiveness") and rel.proactiveness is not None:
                scores.append(f"proactiveness={rel.proactiveness:.2f}")
            if hasattr(rel, "heuristic_similarity") and rel.heuristic_similarity is not None:
                scores.append(f"HS={rel.heuristic_similarity:.2f}")
            for est, _ in transition.estimations.all():
                if isinstance(est, FeasibilityEstimation):
                    scores.append(f"feasibility={est.value:.2f}")
                    break
            if scores:
                lines.append(f"  scores: {', '.join(scores)}")

    # Rationales
    rationales = list(tr.rationales.all())
    if rationales:
        lines.append("")
        for rationale, _ in rationales:
            if rationale.text:
                lines.append(f"Rationale: {rationale.text}")

    return "\n".join(lines)


def _inspect_synthesis(synth: Synthesis) -> str:
    """Build detailed inspection output for a Synthesis."""
    lines: list[str] = []

    lines.append(f"## Synthesis [{_node_id(synth)}]{_status_tag(synth)}")

    # Parent wheel + spiral
    target_result = synth.target.get()
    pp_index = None
    if target_result:
        wheel, _ = target_result
        nexus = find_nexus_for_wheel(wheel)
        pp_index = build_pp_index(nexus) if nexus else None
        spiral = format_spiral(wheel, pp_index)
        if spiral:
            lines.append(f"Spiral: {spiral}")
        lines.append(f"Parent Wheel: [{wheel.short_hash}]")
    lines.append("")

    # S+ and S-
    s_plus = synth.s_plus.get()
    s_minus = synth.s_minus.get()
    if s_plus:
        stmt, _ = s_plus
        lines.append(f"S+: \"{stmt.text}\"")
    if s_minus:
        stmt, _ = s_minus
        lines.append(f"S-: \"{stmt.text}\"")

    # Rationales
    rationales = list(synth.rationales.all())
    if rationales:
        lines.append("")
        for rationale, _ in rationales:
            if rationale.text:
                lines.append(f"Rationale: {rationale.text}")

    return "\n".join(lines)


class InspectNode(ReasonableConcern[str]):
    """Inspects a node by hash and returns detailed formatted output based on type."""

    @inject
    async def resolve(
        self,
        node_hash: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
        from dialectical_framework.graph.nodes.cycle import Cycle
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.perspective import Perspective
        from dialectical_framework.graph.nodes.polarity import Polarity
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.nodes.synthesis import Synthesis
        from dialectical_framework.graph.nodes.transformation import Transformation
        from dialectical_framework.graph.nodes.wheel import Wheel

        repo = NodeRepository()

        try:
            node = repo.find_by_hash(node_hash)
        except ValueError as e:
            # Ambiguous prefix
            return str(e)

        if node is None:
            return f"No node found with hash '{node_hash}' in current scope."

        if isinstance(node, Perspective):
            result = _inspect_perspective(node)
        elif isinstance(node, Statement):
            result = _inspect_statement(node)
        elif isinstance(node, Polarity):
            result = _inspect_polarity(node)
        elif isinstance(node, Nexus):
            result = _inspect_nexus(node)
        elif isinstance(node, Cycle):
            result = _inspect_cycle(node)
        elif isinstance(node, Wheel):
            result = _inspect_wheel(node)
        elif isinstance(node, Transformation):
            result = _inspect_transformation(node)
        elif isinstance(node, Synthesis):
            result = _inspect_synthesis(node)
        else:
            # Fallback for other node types
            result = f"## {node.__class__.__name__} [{_node_id(node)}]{_status_tag(node)}\n\n{repr(node)}"

        self._report.ok = True
        self._report.summary = f"Inspected {node.__class__.__name__} [{node.short_hash}]"
        return result


@llm.tool
async def inspect_node(
    node_hash: Annotated[str, Field(description="Full hash or unique prefix (7+ chars) of the node to inspect")],
) -> str:
    """Inspect any node by hash to see full details. Routes display based on node type: Perspective shows positions with explanations, scores, lineage, and nexus memberships; Statement shows text, meaning, rationale, and which Perspectives use it; Polarity shows T-A pair with HS and referencing Perspectives; Nexus shows member Perspectives; Cycle shows T-causality sequence, perspectives, probability, rationale, and child wheels; Wheel shows TA-sequence, probability, perspectives, transformations, synthesis, and rationale; Transformation shows Ac/Re structure with scores per position and rationale; Synthesis shows S+/S- text, parent wheel, and rationale."""
    concern = InspectNode()
    return await concern.resolve(node_hash=node_hash)
