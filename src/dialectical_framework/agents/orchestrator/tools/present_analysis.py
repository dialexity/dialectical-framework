"""
PresentAnalysis: Concern + tool for generating readable graph state summaries.

Focuses on the analytical layer:
- Perspectives (with their T, A, aspects)
- Unconnected Statements (not in any Perspective or Polarity)
- Unconnected Polarities (not referenced by any Perspective)
- Nexus summary (which Perspectives are grouped for exploration)

Example output (what the LLM receives):
---------------------------------------

Only non-discarded items are shown. Committed is the default — only uncommitted
nodes get a [DRAFT] tag. Discarded items have their own dedicated tool.

## Perspectives

  Perspective 1 [a3f82c1] (navigating remote work tensions): T- = Isolation, T = Remote Work, T+ = Flexibility, A- = Rigidity, A = Office Work, A+ = Collaboration

  Perspective 2 [b7d91e4]: T- = Burnout, T = Productivity, T+ = Achievement, A- = Stagnation, A = Rest, A+ = Recovery

  Perspective 3 [DRAFT] (work-life): T = Balance, A = Imbalance

## Unconnected Polarities (1)
  [c42fe88] T: Trust ↔ A: Distrust, HS=0.87

## Unconnected Statements (2)
  [d9a1b3c] Work-life balance
  [e5f20d7] Commute stress

## Nexuses

  [f1234ab] Exploring remote vs office tradeoffs (2 perspectives)
    Preset: balanced
    - [a3f82c1] T- = Isolation, T = Remote Work, T+ = Flexibility, A- = Rigidity, A = Office Work, A+ = Collaboration
    - [b7d91e4] T- = Burnout, T = Productivity, T+ = Achievement, A- = Stagnation, A = Rest, A+ = Recovery
"""

from __future__ import annotations

from mirascope import llm

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.nexus_repository import NexusRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository
from dialectical_framework.graph.repositories.polarity_repository import PolarityRepository
from dialectical_framework.graph.repositories.statement_repository import StatementRepository


class PresentAnalysis(ReasonableConcern[str]):
    """
    Generates a readable summary of the current graph state.

    Programmatic usage:
        concern = PresentAnalysis()
        summary = await concern.resolve()
        print(summary)
    """

    async def resolve(self) -> str:
        sections: list[str] = []

        pp_repo = PerspectiveRepository()
        stmt_repo = StatementRepository()
        pol_repo = PolarityRepository()
        nexus_repo = NexusRepository()

        perspectives = pp_repo.find_all_active()
        unconnected_statements = stmt_repo.find_unconnected()
        unconnected_polarities = pol_repo.find_unconnected()
        nexuses = nexus_repo.find_all()

        if not perspectives and not unconnected_statements and not unconnected_polarities:
            self._report.ok = True
            self._report.summary = "Empty scope"
            return "Empty scope — no data has been built yet."

        if perspectives:
            sections.append(self._format_perspectives(perspectives))

        if unconnected_polarities:
            sections.append(self._format_unconnected_polarities(unconnected_polarities))

        if unconnected_statements:
            sections.append(self._format_unconnected_statements(unconnected_statements))

        if nexuses:
            sections.append(self._format_nexuses(nexuses))

        self._report.ok = True
        self._report.summary = (
            f"{len(perspectives)} perspectives, "
            f"{len(unconnected_statements)} unconnected statements, "
            f"{len(nexuses)} nexuses"
        )
        return "\n\n".join(sections)

    @staticmethod
    def _node_tag(node) -> str:
        """Format node identifier: [hash] or [DRAFT] for uncommitted."""
        if node.is_committed:
            return f"[{node.short_hash}]"
        return "[DRAFT]"

    @staticmethod
    def _format_perspectives(perspectives: list[Perspective]) -> str:
        lines = ["## Perspectives"]
        for i, pp in enumerate(perspectives, 1):
            tag = PresentAnalysis._node_tag(pp)
            intent_str = f" ({pp.intent})" if pp.intent else ""
            lines.append(f"\n  Perspective {i} {tag}{intent_str}: {pp:positions:0}")
        return "\n".join(lines)

    @staticmethod
    def _format_unconnected_statements(statements: list[Statement]) -> str:
        lines = [f"## Unconnected Statements ({len(statements)})"]
        for s in statements:
            tag = PresentAnalysis._node_tag(s)
            lines.append(f"  {tag} {s:short}")
        return "\n".join(lines)

    @staticmethod
    def _format_unconnected_polarities(polarities: list[Polarity]) -> str:
        lines = [f"## Unconnected Polarities ({len(polarities)})"]
        for p in polarities:
            tag = PresentAnalysis._node_tag(p)
            lines.append(f"  {tag} {p}")
        return "\n".join(lines)

    @staticmethod
    def _format_nexuses(nexuses: list[Nexus]) -> str:
        lines = ["## Nexuses"]
        for n in nexuses:
            pp_list = [(pp, _) for pp, _ in n.perspectives.all() if not pp.discarded]
            display = n.title or n.intent or "(no intent)"
            lines.append(f"\n  [{n.short_hash}] {display} ({len(pp_list)} perspectives)")
            if n.title and n.intent:
                lines.append(f"    Intent: {n.intent}")
            lines.append(f"    Preset: {n.preset or 'default'}")
            for pp, _ in pp_list:
                lines.append(f"    - [{pp.short_hash}] {pp:positions:0}")
        return "\n".join(lines)


@llm.tool
async def present_analysis() -> str:
    """Show the current state of the dialectical graph: Perspectives (with T/A/aspects), unconnected Statements and Polarities not yet in use, and Nexus exploration groups."""
    concern = PresentAnalysis()
    summary = await concern.resolve()
    return summary
