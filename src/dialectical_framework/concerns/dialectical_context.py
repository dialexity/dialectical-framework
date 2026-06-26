"""
DialecticalContext: Reads graph state and produces a structured dump.

Designed for injection into the Advisor agent's system prompt.
Dumps the full graph as structured text with scores inline.
The LLM interprets and prioritizes based on quality signals.
"""

from __future__ import annotations

from typing import Optional

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.rendering import (
    build_pp_index,
    format_edge_label,
    format_spiral,
)
from dialectical_framework.graph.repositories.cycle_repository import CycleRepository
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.nexus_repository import NexusRepository
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)
from dialectical_framework.graph.repositories.wheel_repository import WheelRepository


class DialecticalContext(ReasonableConcern[str]):
    """
    Reads the full graph state for the current Case (sid) and produces a
    structured dump suitable for injection into an advisor's context.

    Hierarchy (matches graph ownership):
    - Standalone perspectives (not in any nexus) → listed under "Unexplored Tensions"
    - Nexus → owns Perspectives (indexed 1, 2, 3...) → Cycles → Wheels
      - Components referenced by index: T1, A1, T1+, T1-, A1+, A1-
      - Transformations and Synthesis belong to Wheels

    Programmatic usage:
        context = DialecticalContext()
        dump = await context.resolve()
    """

    async def resolve(self) -> str:
        pp_repo = PerspectiveRepository()
        nexus_repo = NexusRepository()

        perspectives = pp_repo.find_all_active()

        if not perspectives:
            self._report.ok = True
            self._report.summary = "Empty graph"
            return "No prior understanding — this is a fresh conversation."

        nexuses = nexus_repo.find_all()

        nexused_pp_ids: set = set()
        for nexus in nexuses:
            for pp, _ in nexus.perspectives.all():
                if not pp.discarded:
                    nexused_pp_ids.add(pp._id)

        standalone = [pp for pp in perspectives if pp._id not in nexused_pp_ids]

        sections: list[str] = []

        inputs_dump = self._dump_inputs()
        if inputs_dump:
            sections.append(inputs_dump)

        if standalone:
            sections.append(self._dump_standalone_perspectives(standalone))

        for nexus in nexuses:
            nexus_dump = self._dump_nexus(nexus)
            if nexus_dump:
                sections.append(nexus_dump)

        self._report.ok = True
        self._report.summary = f"{len(perspectives)} perspectives, {len(nexuses)} nexuses"
        return "\n\n".join(sections)

    @staticmethod
    def _dump_inputs() -> Optional[str]:
        """List used input hashes (those with extracted statements)."""
        input_repo = InputRepository()
        inputs = input_repo.get_all()
        if not inputs:
            return None

        used = [inp for inp in inputs if list(inp.statements.all())]
        if not used:
            return None

        hashes = ", ".join(f"[[{inp.short_hash}]]" for inp in used)
        return f"# Sources\nInputs: {hashes}"

    def _dump_standalone_perspectives(self, perspectives: list[Perspective]) -> str:
        lines = ["# Unexplored Tensions"]
        for pp in perspectives:
            lines.append(self._dump_one_perspective(pp))
        return "\n\n".join(lines)

    def _dump_one_perspective(self, pp: Perspective, index: int | None = None) -> str:
        idx = str(index) if index is not None else ""
        header = f"## Perspective {idx} [[{pp.short_hash}]]" if idx else f"## Perspective [[{pp.short_hash}]]"
        lines = [header]

        t_result = self._safe_get(pp.t)
        a_result = self._safe_get(pp.a)

        if t_result:
            stmt, rel = t_result
            lines.append(f"T{idx}: \"{stmt.text}\"")
        if a_result:
            stmt, rel = a_result
            hs = f" (HS={rel.heuristic_similarity:.2f})" if rel.heuristic_similarity else ""
            lines.append(f"A{idx}: \"{stmt.text}\"{hs}")

        for position, manager in [
            (f"T{idx}+", pp.t_plus),
            (f"T{idx}-", pp.t_minus),
            (f"A{idx}+", pp.a_plus),
            (f"A{idx}-", pp.a_minus),
        ]:
            result = self._safe_get(manager)
            if result:
                stmt, rel = result
                scores = self._format_aspect_scores(rel)
                lines.append(f"{position}: \"{stmt.text}\"{scores}")

        if pp.area is not None:
            lines.append(f"Quality: area={pp.area:.2f}, rectangularity={pp.rectangularity:.2f}")

        return "\n".join(lines)

    def _dump_nexus(self, nexus: Nexus) -> Optional[str]:
        cycle_repo = CycleRepository()
        wheel_repo = WheelRepository()

        lines = [f"# Nexus [[{nexus.short_hash}]]"]
        if nexus.intent:
            lines.append(f"Intent: {nexus.intent}")

        pp_index = build_pp_index(nexus)

        pp_list = [pp for pp, _ in nexus.perspectives.all() if not pp.discarded]

        # Perspectives indexed under nexus
        for pp in pp_list:
            lines.append("")
            lines.append(self._dump_one_perspective(pp, index=pp_index[pp._id]))

        # Cycles and Wheels (reference perspectives by index)
        cycles = self._find_top_layer_cycles(nexus, pp_list, cycle_repo)

        if cycles:
            cycle_probs = self._collect_raw_probabilities(cycles)
            total_cycle_prob = sum(p for p in cycle_probs.values() if p is not None)

            for cycle in cycles:
                cycle_dump = self._dump_cycle(
                    cycle, wheel_repo, cycle_probs, total_cycle_prob, pp_index
                )
                if cycle_dump:
                    lines.append("")
                    lines.append(cycle_dump)

        return "\n".join(lines) if len(lines) > 1 else None

    def _dump_cycle(
        self,
        cycle: Cycle,
        wheel_repo: WheelRepository,
        cycle_probs: dict,
        total_cycle_prob: float,
        pp_index: dict[int, int],
    ) -> Optional[str]:
        lines = [f"## Cycle [[{cycle.short_hash}]]"]

        # T-causality sequence using nexus indices
        pps = cycle.perspectives
        if pps:
            labels = [f"T{pp_index.get(pp._id, 0)}" for pp in pps]
            sequence = " → ".join(labels) + f" → {labels[0]}..."
            lines.append(f"Sequence: {sequence}")

        # Probability (raw + normalized)
        raw_prob = cycle_probs.get(cycle._id)
        if raw_prob is not None:
            normalized = raw_prob / total_cycle_prob if total_cycle_prob > 0 else None
            prob_str = f"P={raw_prob:.2f}"
            if normalized is not None:
                prob_str += f", {normalized * 100:.1f}%"
            lines.append(f"Causality: {prob_str}")

        # Wheels under this cycle
        wheels = self._get_cycle_wheels(cycle, wheel_repo)
        if wheels:
            wheel_probs = self._collect_raw_probabilities(wheels)
            total_wheel_prob = sum(p for p in wheel_probs.values() if p is not None)

            for wheel in wheels:
                wheel_dump = self._dump_wheel(wheel, wheel_probs, total_wheel_prob, pp_index)
                if wheel_dump:
                    lines.append(wheel_dump)

        return "\n".join(lines) if len(lines) > 1 else None

    def _dump_wheel(
        self,
        wheel: Wheel,
        wheel_probs: dict,
        total_wheel_prob: float,
        pp_index: dict[int, int],
    ) -> Optional[str]:
        lines = [f"### Wheel [[{wheel.short_hash}]]"]

        # TA-sequence using nexus indices
        ta_sequence = self._format_ta_sequence(wheel, pp_index)
        if ta_sequence:
            lines.append(f"Sequence: {ta_sequence}")

        # Probability (raw + normalized)
        raw_prob = wheel_probs.get(wheel._id)
        if raw_prob is not None:
            normalized = raw_prob / total_wheel_prob if total_wheel_prob > 0 else None
            prob_str = f"P={raw_prob:.2f}"
            if normalized is not None:
                prob_str += f", {normalized * 100:.1f}%"
            lines.append(f"Causality: {prob_str}")

        # Transformations (belong to wheel)
        for tr in wheel.transformations:
            tr_dump = self._dump_transformation(tr, pp_index)
            if tr_dump:
                lines.append(tr_dump)

        # Synthesis (belongs to wheel)
        synth_dump = self._dump_synthesis(wheel, pp_index)
        if synth_dump:
            lines.append(synth_dump)

        return "\n".join(lines) if len(lines) > 1 else None

    def _dump_transformation(
        self, tr: Transformation, pp_index: dict[int, int]
    ) -> Optional[str]:
        edge_result = tr.edge.get()
        edge_label = ""
        if edge_result:
            edge_label = format_edge_label(edge_result[0], pp_index)

        header = f"#### Transformation [[{tr.short_hash}]]"
        if edge_label:
            header += f" ({edge_label})"
        lines = [header]

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
                if not text:
                    continue
                scores = self._format_transition_scores(rel, transition)
                transition_label = format_edge_label(transition, pp_index)
                pos_display = f"{position} ({transition_label})" if transition_label else position
                lines.append(f"{pos_display}: \"{text}\"{scores}")

        return "\n".join(lines) if len(lines) > 1 else None

    def _dump_synthesis(self, wheel: Wheel, pp_index: dict[int, int]) -> Optional[str]:
        lines = []
        spiral = format_spiral(wheel, pp_index)
        for synth, _ in wheel.synthesis.all():
            header = f"#### Synthesis [[{synth.short_hash}]]"
            if spiral:
                header += f" ({spiral})"
            lines.append(header)
            s_plus = synth.s_plus.get()
            s_minus = synth.s_minus.get()
            if s_plus:
                stmt, _ = s_plus
                lines.append(f"S+: \"{stmt.text}\"")
            if s_minus:
                stmt, _ = s_minus
                lines.append(f"S-: \"{stmt.text}\"")
        return "\n".join(lines) if lines else None

    def _format_aspect_scores(self, rel) -> str:
        parts = []
        if hasattr(rel, "heuristic_similarity") and rel.heuristic_similarity is not None:
            parts.append(f"HS={rel.heuristic_similarity:.2f}")
        if hasattr(rel, "complementarity_s") and rel.complementarity_s is not None:
            parts.append(f"Ks={rel.complementarity_s:.2f}")
        return f" ({', '.join(parts)})" if parts else ""

    def _format_transition_scores(self, rel, transition) -> str:
        parts = []
        if hasattr(rel, "insight") and rel.insight is not None:
            parts.append(f"insight={rel.insight:.2f}")
        if hasattr(rel, "proactiveness") and rel.proactiveness is not None:
            parts.append(f"proactiveness={rel.proactiveness:.2f}")
        if hasattr(rel, "heuristic_similarity") and rel.heuristic_similarity is not None:
            parts.append(f"HS={rel.heuristic_similarity:.2f}")
        feasibility = self._get_feasibility(transition)
        if feasibility is not None:
            parts.append(f"feasibility={feasibility:.2f}")
        return f" ({', '.join(parts)})" if parts else ""

    @staticmethod
    def _format_ta_sequence(wheel: Wheel, pp_index: dict[int, int]) -> str:
        """Format TA-sequence using nexus-level indices."""
        try:
            segs = wheel.segments
        except (ValueError, AttributeError):
            return ""

        if not segs:
            return ""

        labels = []
        for seg in segs:
            pp = seg._perspective
            idx = pp_index.get(pp._id, 0)
            labels.append(f"{seg._side}{idx}")

        if len(labels) <= 1:
            return labels[0] if labels else ""

        return " → ".join(labels) + f" → {labels[0]}..."

    def _collect_raw_probabilities(self, entities: list) -> dict:
        """Collect raw CausalityProbabilityEstimation values keyed by _id."""
        result = {}
        for entity in entities:
            result[entity._id] = self._get_causality_probability(entity)
        return result

    @staticmethod
    def _get_causality_probability(entity) -> Optional[float]:
        from dialectical_framework.graph.nodes.estimation import CausalityProbabilityEstimation

        for est, _ in entity.estimations.all():
            if isinstance(est, CausalityProbabilityEstimation):
                return est.value
        return None

    @staticmethod
    def _get_feasibility(transition) -> Optional[float]:
        from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation

        for est, _ in transition.estimations.all():
            if isinstance(est, FeasibilityEstimation):
                return est.value
        return None

    @staticmethod
    def _find_top_layer_cycles(
        nexus: Nexus, pp_list: list[Perspective], cycle_repo: CycleRepository
    ) -> list[Cycle]:
        """Find cycles at the highest layer (most perspectives)."""
        if not pp_list:
            return []

        cycles = cycle_repo.find_by_layer(pp_list, nexus=nexus)
        if cycles:
            return cycles

        # Fall back to largest layer that has cycles
        from itertools import combinations

        for r in range(len(pp_list) - 1, 0, -1):
            for combo in combinations(pp_list, r):
                cycles = cycle_repo.find_by_layer(list(combo), nexus=nexus)
                if cycles:
                    return cycles

        return []

    @staticmethod
    def _get_cycle_wheels(cycle: Cycle, wheel_repo: WheelRepository) -> list[Wheel]:
        """Get all wheels belonging to a cycle."""
        wheels = []
        for wheel, _ in cycle.wheels.all():
            wheels.append(wheel)
        return wheels

    @staticmethod
    def _safe_get(manager) -> Optional[tuple]:
        try:
            return manager.get()
        except (ValueError, AttributeError):
            return None
