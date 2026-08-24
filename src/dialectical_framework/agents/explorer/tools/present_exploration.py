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
from dialectical_framework.graph.rendering import WheelCompleteness
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
    def _causality_label(wheel: Wheel, probs: dict, totals: dict) -> str:
        """Render 'P=0.72, 61.5%' — % normalized across the wheel's siblings
        within its parent Cycle (same denominator convention as the
        dialectical_context dump: competing arrangements of one cycle)."""
        raw = probs.get(wheel._id)
        if raw is None:
            return ""
        label = f"P={raw:.2f}"
        total = totals.get(PresentExploration._cycle_key(wheel), 0.0)
        if total > 0:
            label += f", {raw / total * 100:.1f}%"
        return label

    @staticmethod
    def _cycle_key(wheel: Wheel):
        """Parent-cycle id for normalization grouping (None if unresolvable)."""
        try:
            cycle_result = wheel.cycle.get()
        except (ValueError, AttributeError):
            return None
        if not cycle_result:
            return None
        cycle, _ = cycle_result
        return cycle._id

    @staticmethod
    def _collect_wheel_probabilities(wheels: list[Wheel]) -> dict:
        from dialectical_framework.graph.nodes.estimation import \
            CausalityProbabilityEstimation

        probs: dict = {}
        for wheel in wheels:
            value = None
            for est, _ in wheel.estimations.all():
                if isinstance(est, CausalityProbabilityEstimation):
                    value = est.value
                    break
            probs[wheel._id] = value
        return probs

    @staticmethod
    def _format_wheels(
        wheels: list[Wheel], transformations: list[Transformation]
    ) -> str:
        lines = [f"## Wheels ({len(wheels)})"]

        tr_by_wheel: dict[int, list[Transformation]] = {}
        # Per-edge tally, harvested from the same pass: it is the denominator
        # input below, so completeness costs no extra queries on a path that
        # renders every wheel of the nexus.
        tr_by_edge: dict[int, int] = {}
        for tr in transformations:
            edge_result = tr.edge.get()
            if not edge_result:
                continue
            edge, _ = edge_result
            if edge._id is not None:
                tr_by_edge[edge._id] = tr_by_edge.get(edge._id, 0) + 1
            cycle_result = edge.cycle.get()
            if not cycle_result:
                continue
            wheel_node, _ = cycle_result
            if wheel_node._id not in tr_by_wheel:
                tr_by_wheel[wheel_node._id] = []
            tr_by_wheel[wheel_node._id].append(tr)

        # Causality scores: raw P per wheel, % normalized across the wheel's
        # siblings within its parent Cycle (the competing arrangements) —
        # same convention as the dialectical_context dump.
        probs = PresentExploration._collect_wheel_probabilities(wheels)
        totals: dict = {}
        for wheel in wheels:
            p = probs.get(wheel._id)
            if p is not None:
                key = PresentExploration._cycle_key(wheel)
                totals[key] = totals.get(key, 0.0) + p

        # Most plausible first: layer (deepest), then raw P.
        wheels = sorted(
            wheels,
            key=lambda w: (w.polarity_count, probs.get(w._id) or -1.0),
            reverse=True,
        )

        for wheel in wheels:
            layer = wheel.polarity_count
            causality = PresentExploration._causality_label(wheel, probs, totals)
            causality_str = f", causality {causality}" if causality else ""
            lines.append(
                f"\n  Wheel [{wheel.short_hash}] (layer {layer}{causality_str})"
            )

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

            # The denominator for the transformations below. Without it a wheel
            # killed mid-build reads exactly like a finished one — the same
            # 6N fraction the Advisor and `deepen` speak (docs/graph.md).
            # Silent when complete, so the common path stays uncluttered.
            completeness = WheelCompleteness.from_edge_counts(
                [tr_by_edge.get(e._id, 0) for e in edges]
            )
            if completeness.expected and not completeness.is_complete:
                lines.append(f"    Pathways: {completeness.fraction}")

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
