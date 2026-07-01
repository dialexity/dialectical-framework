"""
PresentExploration: Concern + tool for showing exploration state within a Nexus.

Shows:
- Nexus intent and perspectives
- Wheels (with edge summaries)
- Transformations (Ac+ and Re+ highlights — the synthetic wisdom)
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.nexus_repository import \
    NexusRepository
from dialectical_framework.graph.repositories.transformation_repository import \
    TransformationRepository
from dialectical_framework.graph.repositories.wheel_repository import \
    WheelRepository


class PresentExploration(ReasonableConcern[str]):
    """
    Generates a readable summary of exploration state within a Nexus.

    Programmatic usage:
        concern = PresentExploration(nexus_hash="abc123")
        summary = await concern.resolve()
        print(summary)
    """

    def __init__(self, nexus_hash: str) -> None:
        self.nexus_hash = nexus_hash

    async def resolve(self) -> str:
        nexus_repo = NexusRepository()
        nexus = nexus_repo.find_by_hash_prefix(self.nexus_hash)

        if nexus is None:
            self._report.ok = False
            self._report.summary = f"Nexus not found: {self.nexus_hash}"
            return f"Nexus not found: {self.nexus_hash}"

        sections: list[str] = []

        sections.append(self._format_nexus_header(nexus))

        perspectives = [
            (pp, rel) for pp, rel in nexus.perspectives.all() if not pp.discarded
        ]
        if perspectives:
            sections.append(self._format_perspectives(perspectives))

        wheel_repo = WheelRepository()
        tr_repo = TransformationRepository()

        all_wheels = self._find_nexus_wheels(nexus, wheel_repo)
        transformations = tr_repo.find_by_nexus(nexus)

        if all_wheels:
            sections.append(self._format_wheels(all_wheels, transformations))

        if not perspectives and not all_wheels:
            sections.append(
                "No exploration data yet. Use `build_wheels` to generate structures."
            )

        self._report.ok = True
        self._report.summary = (
            f"Nexus {nexus.short_hash}: {len(perspectives)} perspectives, "
            f"{len(all_wheels)} wheels, {len(transformations)} transformations"
        )
        return "\n\n".join(sections)

    @staticmethod
    def _format_nexus_header(nexus: Nexus) -> str:
        lines = [f"## Nexus [{nexus.short_hash}]"]
        if nexus.title:
            lines.append(f"Title: {nexus.title}")
        if nexus.intent:
            lines.append(f"Intent: {nexus.intent}")
        if nexus.preset:
            lines.append(f"Preset: {nexus.preset}")
        return "\n".join(lines)

    @staticmethod
    def _format_perspectives(perspectives: list) -> str:
        lines = [f"## Perspectives ({len(perspectives)})"]
        for i, (pp, _) in enumerate(perspectives, 1):
            intent_str = f" ({pp.intent})" if pp.intent else ""
            lines.append(f"  Perspective {i} [{pp.short_hash}]{intent_str}: {pp:positions:0}")
        return "\n".join(lines)

    @staticmethod
    def _find_nexus_wheels(nexus: Nexus, wheel_repo: WheelRepository) -> list[Wheel]:
        perspectives = [pp for pp, _ in nexus.perspectives.all() if not pp.discarded]
        if not perspectives:
            return []

        from itertools import combinations

        all_wheels: list[Wheel] = []
        seen_ids: set = set()

        for r in range(1, len(perspectives) + 1):
            for combo in combinations(perspectives, r):
                wheels = wheel_repo.find_by_layer(list(combo), nexus=nexus)
                for w in wheels:
                    if w._id not in seen_ids:
                        seen_ids.add(w._id)
                        all_wheels.append(w)

        return all_wheels

    @staticmethod
    def _format_wheels(
        wheels: list[Wheel], transformations: list[Transformation]
    ) -> str:
        lines = [f"## Wheels ({len(wheels)})"]

        tr_by_wheel: dict[int, list[Transformation]] = {}
        for tr in transformations:
            edge_result = tr.edge.get()
            if not edge_result:
                continue
            edge, _ = edge_result
            cycle_result = edge.cycle.get()
            if not cycle_result:
                continue
            wheel_node, _ = cycle_result
            if wheel_node._id not in tr_by_wheel:
                tr_by_wheel[wheel_node._id] = []
            tr_by_wheel[wheel_node._id].append(tr)

        for wheel in wheels:
            layer = wheel.polarity_count
            lines.append(f"\n  Wheel [{wheel.short_hash}] (layer {layer})")

            edges = wheel.edges
            if edges:
                edge_strs = []
                for edge in edges:
                    source_result = edge.source.get()
                    target_result = edge.target.get()
                    if source_result and target_result:
                        src, _ = source_result
                        tgt, _ = target_result
                        edge_strs.append(f"{src.text} -> {tgt.text}")
                if edge_strs:
                    lines.append(f"    Edges: {' | '.join(edge_strs)}")

            wheel_trs = tr_by_wheel.get(wheel._id, [])
            if wheel_trs:
                lines.append(f"    Transformations ({len(wheel_trs)}):")
                for tr in wheel_trs:
                    lines.append(PresentExploration._format_transformation_summary(tr))

        if transformations:
            lines.append(
                f"\n## Total: {len(transformations)} transformations across {len(wheels)} wheels"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_transformation_summary(tr: Transformation) -> str:
        lines = []
        tag = f"[{tr.short_hash}]" if tr.is_committed else "[DRAFT]"

        ac_plus_result = tr.ac_plus.get()
        re_plus_result = tr.re_plus.get()

        ac_plus_str = ""
        if ac_plus_result:
            transition, rel = ac_plus_result
            ac_plus_str = f"Ac+: {transition.instruction or transition.summary or '?'}"

        re_plus_str = ""
        if re_plus_result:
            transition, rel = re_plus_result
            re_plus_str = f"Re+: {transition.instruction or transition.summary or '?'}"

        parts = [s for s in [ac_plus_str, re_plus_str] if s]
        lines.append(
            f"      {tag} {' | '.join(parts) if parts else '(no positions yet)'}"
        )

        return "\n".join(lines)


@llm.tool
async def present_exploration(
    nexus_hash: Annotated[str, Field(description="Hash of the Nexus to present")],
) -> str:
    """Show the exploration state within a Nexus: perspectives grouped for exploration, wheels (structural combinations), and transformation summaries highlighting Ac+ and Re+ pathways."""
    concern = PresentExploration(nexus_hash=nexus_hash)
    summary = await concern.resolve()
    return summary
