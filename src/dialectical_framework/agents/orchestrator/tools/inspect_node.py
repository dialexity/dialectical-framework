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
"""

from __future__ import annotations

from typing import Annotated, Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.nodes.nexus import Nexus


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
    lines.append(f"## Nexus [{_node_id(nexus)}]{_status_tag(nexus)}")
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


class InspectNode(ReasonableConcern[str]):
    """Inspects a node by hash and returns detailed formatted output based on type."""

    @inject
    async def resolve(
        self,
        node_hash: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
        from dialectical_framework.graph.nodes.perspective import Perspective
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.nodes.polarity import Polarity
        from dialectical_framework.graph.nodes.nexus import Nexus

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
    """Inspect any node by hash to see full details. Routes display based on node type: Perspective shows positions with explanations, scores, lineage, and nexus memberships; Statement shows text, meaning, rationale, and which Perspectives use it; Polarity shows T-A pair with HS and referencing Perspectives; Nexus shows member Perspectives."""
    concern = InspectNode()
    return await concern.resolve(node_hash=node_hash)
