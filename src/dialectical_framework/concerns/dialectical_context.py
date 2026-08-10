"""
DialecticalContext: Reads graph state and produces a structured dump.

Designed for injection into the Advisor agent's system prompt.
Dumps the graph as structured text with scores inline — pre-pruned:
perspectives below the quality floors (settings.advisor_polarity_quality_min_hs /
advisor_perspective_quality_min_sp / advisor_perspective_quality_min_dv — the SP+DV
pair mirrors the paper's acceptance criterion, all mirroring the prompt's own scales) and failed-validation
perspectives are suppressed with a count line, and wheels are capped to the
top-% few per cycle (settings.advisor_wheel_quality_top_plausible). Pre-computed pruning
beats prioritization rules the model must self-apply; a weak tetrad
delivered with full counsel choreography is confident bad advice.
inspect_node still reaches everything suppressed.
"""

from __future__ import annotations

from typing import Optional

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.protocols.has_config import SettingsAware
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
from dialectical_framework.graph.repositories.decision_repository import (
    DecisionRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.nexus_repository import NexusRepository
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)
from dialectical_framework.graph.repositories.wheel_repository import WheelRepository


class DialecticalContext(ReasonableConcern[str], SettingsAware):
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

    Nexus-scoped usage (renders only one nexus + inputs; perspectives outside
    the nexus appear only as a one-line count):
        context = DialecticalContext(nexus_hash="abc1234")
        dump = await context.resolve()
    """

    def __init__(self, nexus_hash: str | None = None) -> None:
        self._nexus_hash = nexus_hash

    async def resolve(self) -> str:
        if self._nexus_hash:
            return await self._resolve_scoped()

        pp_repo = PerspectiveRepository()
        nexus_repo = NexusRepository()

        perspectives = pp_repo.find_all_active()
        inputs_dump = self._dump_inputs()
        decisions_dump = self._dump_decisions()

        if not perspectives:
            if inputs_dump or decisions_dump:
                # No structure yet, but captured material and/or recorded
                # decisions exist — surface them so the model can pick them
                # up instead of assuming a blank slate.
                self._report.ok = True
                self._report.summary = "No perspectives yet, inputs/decisions pending"
                parts = [p for p in (inputs_dump, decisions_dump) if p]
                parts.append(
                    "No tensions identified yet — sources above (if any) are "
                    "captured but not yet analyzed; standing decisions (if "
                    "any) remain in force."
                )
                return "\n\n".join(parts)
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

        if inputs_dump:
            sections.append(inputs_dump)
        if decisions_dump:
            sections.append(decisions_dump)

        # Quality floor applies to standalone (unexplored) perspectives only —
        # nexus members are load-bearing (wheels reference their indices) and
        # stay visible with their scores/Validation line.
        standalone, suppressed_count = self._apply_quality_floor(standalone)

        # Cross-references need at least two groups to correspond across:
        # several explorations, or one-plus with unexplored tensions beside it
        # (a fresh anchor echoing an explored tension is exactly the moment
        # a correspondence line earns its keep).
        cross_refs: dict = {}
        if len(nexuses) > 1 or (nexuses and standalone):
            cross_refs = self._build_cross_nexus_refs(nexuses, standalone)

        if standalone:
            sections.append(
                self._dump_standalone_perspectives(standalone, cross_refs)
            )
        if suppressed_count:
            sections.append(
                f"{suppressed_count} unexplored tension(s) suppressed for low "
                f"quality (weak opposition, blurred structure, unnatural/"
                f"distorted framing, or failed validation) — reachable via "
                f"inspect_node if needed."
            )

        if len(nexuses) > 1:
            sections.append(
                "Multiple explorations below. Indices (T1, A1, ...) are "
                "per-exploration — T1 in one nexus is unrelated to T1 in "
                "another. When referring across explorations, qualify the "
                "index with its nexus: \"T2 in [[hash]]\"."
            )

        for nexus in nexuses:
            nexus_dump = self._dump_nexus(nexus, cross_refs)
            if nexus_dump:
                sections.append(nexus_dump)

        self._report.ok = True
        self._report.summary = f"{len(perspectives)} perspectives, {len(nexuses)} nexuses"
        return "\n\n".join(sections)

    async def _resolve_scoped(self) -> str:
        """Render one nexus only; outside tensions appear as a count line."""
        nexus_repo = NexusRepository()
        nexus = nexus_repo.find_by_hash_prefix(self._nexus_hash)
        if nexus is None:
            raise ValueError(f"Nexus not found: {self._nexus_hash}")

        sections: list[str] = []

        inputs_dump = self._dump_inputs()
        if inputs_dump:
            sections.append(inputs_dump)

        # Decisions are Case-level facts — the counsel head must see them
        # even when pinned to one exploration.
        decisions_dump = self._dump_decisions()
        if decisions_dump:
            sections.append(decisions_dump)

        nexus_dump = self._dump_nexus(nexus)
        if nexus_dump:
            sections.append(nexus_dump)

        member_ids = {
            pp._id for pp, _ in nexus.perspectives.all() if not pp.discarded
        }
        all_active = PerspectiveRepository().find_all_active()
        outside_count = sum(1 for pp in all_active if pp._id not in member_ids)
        if outside_count:
            sections.append(
                f"{outside_count} other tension(s) exist outside this "
                f"exploration (not shown)."
            )

        self._report.ok = True
        self._report.summary = (
            f"Nexus [[{nexus.short_hash}]]: {len(member_ids)} perspectives, "
            f"{outside_count} outside"
        )
        return "\n\n".join(sections)

    @staticmethod
    def _dump_inputs() -> Optional[str]:
        """List input hashes — processed ones plus pending (not yet analyzed).

        Pending inputs matter: without them the model cannot see material
        that was captured but never processed (e.g. a fresh dx:// insight),
        so it could never pick it up.
        """
        input_repo = InputRepository()
        inputs = input_repo.get_all()
        if not inputs:
            return None

        used = [inp for inp in inputs if list(inp.statements.all())]
        pending = [inp for inp in inputs if not list(inp.statements.all())]

        lines = ["# Sources"]
        if used:
            hashes = ", ".join(f"[[{inp.short_hash}]]" for inp in used)
            lines.append(f"Inputs: {hashes}")
        if pending:
            hashes = ", ".join(f"[[{inp.short_hash}]]" for inp in pending)
            lines.append(
                f"Pending (captured, not yet analyzed): {hashes} — "
                f"use read_digest for content."
            )
        return "\n".join(lines)

    @staticmethod
    def _dump_decisions() -> Optional[str]:
        """Render the # Decisions ledger: active (non-discarded) decisions
        with their grounds, ground-status flags, and coherence verdict.

        Decisions are Case-level facts, shown in both the unscoped and
        nexus-scoped dumps.
        """
        from datetime import datetime, timezone

        from dialectical_framework.graph.rendering import (
            decision_ground_line, one_line)

        decisions = DecisionRepository().find_all_active()
        if not decisions:
            return None

        lines = ["# Decisions"]
        for d in decisions:
            lines.append("")
            date = ""
            if d.committed_at:
                date = datetime.fromtimestamp(
                    d.committed_at, tz=timezone.utc
                ).strftime(" (%Y-%m-%d)")
            lines.append(f"## Decision [[{d.short_hash}]]{date}")
            # one_line: user-confirmed text may contain newlines — rendered
            # raw they could fabricate sibling ledger lines (injection).
            lines.append(f"Question: {one_line(d.intent)}")
            lines.append(f"Stance: {one_line(d.stance)}")
            # Ledger shows only the ceremony-confirmed why; machine rationales
            # (critiques etc.) stay one inspect_node away — deliberate
            # divergence from _inspect_decision, which shows all. "human" =
            # a person confirmed; "agent:<name>" = a delegated driver
            # confirmed (rendered with attribution so a human reading the
            # ledger never mistakes it for their own confirmation).
            for rationale, _ in d.rationales.all():
                if rationale.agent == "human":
                    lines.append(f"Why: {one_line(rationale.text)}")
                elif rationale.agent and rationale.agent.startswith("agent:"):
                    lines.append(
                        f"Why (confirmed by {rationale.agent}): "
                        f"{one_line(rationale.text)}"
                    )
            if d.validation:
                lines.append(f"Validation: {one_line(d.validation)}")
            grounds = d.grounds.all()
            if grounds:
                lines.append("Grounds:")
                ground_nodes = [n for n, _ in grounds]
                for node, rel in grounds:
                    lines.append(
                        decision_ground_line(node, rel.role, siblings=ground_nodes)
                    )
        return "\n".join(lines)

    def _dump_standalone_perspectives(
        self,
        perspectives: list[Perspective],
        cross_refs: dict[tuple[str, int], list[str]] | None = None,
    ) -> str:
        lines = ["# Unexplored Tensions"]
        for pp in perspectives:
            block = self._dump_one_perspective(pp)
            refs = (cross_refs or {}).get((self._STANDALONE_KEY, pp._id), [])
            if refs:
                block = "\n".join([block, *refs])
            lines.append(block)
        return "\n\n".join(lines)

    def _dump_one_perspective(self, pp: Perspective, index: int | None = None) -> str:
        idx = str(index) if index is not None else ""
        header = f"## Perspective {idx} [[{pp.short_hash}]]" if idx else f"## Perspective [[{pp.short_hash}]]"
        lines = [header]

        # The reading (intent): which dimension THIS tetrad opposes along —
        # what distinguishes sibling tetrads on one polarity.
        if pp.intent:
            from dialectical_framework.graph.rendering import one_line

            lines.append(one_line(pp.intent))

        t_result = self._safe_get(pp.t)
        a_result = self._safe_get(pp.a)

        # Statement hashes are rendered because a Statement is an addressable
        # AssessableEntity and readers are asked to reference these specific
        # positions — most sharply `record_decision`, whose "accepted_cost"
        # ground is the CHOSEN side's minus aspect (T- or A-; see
        # GroundedInRelationship for why the cost is a minus). Without an
        # address here the only hash in view is the whole Perspective's, so
        # that instruction is unfollowable: observed in the bench, every
        # recorded accepted_cost grounded on a Perspective/Polarity instead —
        # the tension rather than the cost — leaving the wobble re-audit
        # nothing specific to reassure from. The minus lines below are
        # addressed for exactly this reason: do not drop any of these hashes
        # without re-checking that path.
        if t_result:
            stmt, rel = t_result
            lines.append(f"T{idx} [[{stmt.short_hash}]]: \"{stmt.text}\"")
        if a_result:
            stmt, rel = a_result
            if stmt.is_simple:
                # SIMPLE path: the antithesis is a mechanical negation and its
                # HS is hardcoded 1.0 — not an earned score. Say so instead of
                # rendering a fake perfect number.
                hs = " (mechanical opposition — HS not evaluated)"
            elif rel.heuristic_similarity:
                hs = f" (HS={rel.heuristic_similarity:.2f})"
            else:
                hs = ""
            lines.append(f"A{idx} [[{stmt.short_hash}]]: \"{stmt.text}\"{hs}")

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
                lines.append(
                    f"{position} [[{stmt.short_hash}]]: \"{stmt.text}\"{scores}"
                )

        if pp.area is not None:
            quality = f"Quality: area={pp.area:.2f}, rectangularity={pp.rectangularity:.2f}"
            dv = self._get_dialectical_validity(pp)
            if dv is not None:
                quality += f", DV={dv:.2f}"
            lines.append(quality)

        # Post-generation validation verdict (CC + empirical inequalities).
        if pp.validation == "passed":
            lines.append("Validation: passed")
        elif pp.validation and pp.validation.startswith("failed"):
            lines.append(f"Validation: {pp.validation}")

        return "\n".join(lines)

    # Sentinel group key for perspectives outside any nexus. Correspondences
    # are computed across GROUPS (nexus↔nexus, nexus↔unexplored), never within
    # one group — within a nexus the members already sit side by side.
    _STANDALONE_KEY = "__standalone__"

    def _build_cross_nexus_refs(
        self,
        nexuses: list[Nexus],
        standalone: list[Perspective] | None = None,
    ) -> dict[tuple[str, int], list[str]]:
        """
        Machine-stated cross-group facts, keyed by (group key, pp._id) where
        the group key is a nexus short_hash or _STANDALONE_KEY. Two kinds,
        both derived from data already persisted:
        - the same perspective woven into several nexuses;
        - two perspectives in different groups anchored to the same
          taxonomy branch (same opposition family) — including a fresh
          unexplored anchor echoing an already-explored tension.
        The parallels themselves stay the LLM's free interpretation — the
        dump only surfaces the raw correspondence.
        """
        # (group key, index within nexus or None, display label, pp._id,
        # thesis branch); the label is how OTHER groups' lines point at this
        # perspective. Standalone perspectives never trigger "Also woven into"
        # (standalone = not in any nexus, by construction).
        entries: list[tuple[str, Optional[int], str, int, Optional[str]]] = []
        for nexus in nexuses:
            pp_index = build_pp_index(nexus)
            for pp, _ in nexus.perspectives.all():
                if pp.discarded:
                    continue
                idx = pp_index[pp._id]
                entries.append(
                    (
                        nexus.short_hash,
                        idx,
                        f"{idx} in [[{nexus.short_hash}]]",
                        pp._id,
                        self._get_thesis_branch(pp),
                    )
                )
        for pp in standalone or []:
            entries.append(
                (
                    self._STANDALONE_KEY,
                    None,
                    f"[[{pp.short_hash}]] (unexplored)",
                    pp._id,
                    self._get_thesis_branch(pp),
                )
            )

        refs: dict[tuple[str, int], list[str]] = {}

        def add(group: str, pp_id: int, line: str) -> None:
            refs.setdefault((group, pp_id), []).append(line)

        for group, _, _, pp_id, branch in entries:
            same_branch: list[str] = []
            for other_group, other_idx, other_label, other_pp, other_branch in entries:
                if other_group == group:
                    continue
                if other_pp == pp_id:
                    add(
                        group,
                        pp_id,
                        f"Also woven into Nexus [[{other_group}]] "
                        f"(as perspective {other_idx} there).",
                    )
                elif branch and branch == other_branch and branch != "Apex":
                    same_branch.append(other_label)
            if same_branch:
                # One compact line per perspective — branches are few (5), so
                # collisions are common; per-pair lines would bloat the dump.
                add(
                    group,
                    pp_id,
                    f"Same opposition family ({branch}) as perspective(s) "
                    f"{', '.join(same_branch)}.",
                )
        return refs

    def _get_thesis_branch(self, pp: Perspective) -> Optional[str]:
        """Taxonomy branch of the thesis meaning URI (None for Simple/unset)."""
        from dialectical_framework.concerns.statement_classification import \
            parse_meaning_uri

        t_result = self._safe_get(pp.t)
        if not t_result:
            return None
        stmt, _ = t_result
        if not stmt.meaning or stmt.is_simple:
            return None
        _, _, branch, _ = parse_meaning_uri(stmt.meaning)
        return branch

    def _dump_nexus(
        self,
        nexus: Nexus,
        cross_refs: dict[tuple[str, int], list[str]] | None = None,
    ) -> Optional[str]:
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
            for ref in (cross_refs or {}).get((nexus.short_hash, pp._id), []):
                lines.append(ref)

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

        # Wheels under this cycle — capped to the top-% few. The % denominator
        # stays the FULL sibling set (ranking is over all alternatives, not
        # just the rendered ones). The cap applies to the UNSCOPED dump only:
        # a scoped (counsel-mode) render shows the user-built exploration in
        # full — same load-bearing exemption as nexus members in the quality
        # floor; the counsel head must not be blind to parts of the
        # deliverable the user assembled deliberately.
        wheels = self._get_cycle_wheels(cycle, wheel_repo)
        if wheels:
            wheel_probs = self._collect_raw_probabilities(wheels)
            total_wheel_prob = sum(p for p in wheel_probs.values() if p is not None)

            max_wheels = 0 if self._nexus_hash else self.settings.advisor_wheel_quality_top_plausible
            # Hash tiebreaker: with probability-only keys, tied (or unscored)
            # wheels resolve by arrival order — unspecified in Cypher — so
            # which wheel makes the rendered top-N could differ between two
            # renders of the SAME graph. The hash pins it.
            rendered = sorted(
                wheels,
                key=lambda w: (-(wheel_probs.get(w._id) or -1.0), w.hash or ""),
            )
            hidden = 0
            if max_wheels > 0 and len(rendered) > max_wheels:
                hidden = len(rendered) - max_wheels
                rendered = rendered[:max_wheels]

            for wheel in rendered:
                wheel_dump = self._dump_wheel(wheel, wheel_probs, total_wheel_prob, pp_index)
                if wheel_dump:
                    lines.append(wheel_dump)

            if hidden:
                lines.append(
                    f"({hidden} lower-probability wheel(s) not shown — "
                    f"reachable via inspect_node on the cycle)"
                )

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

    def _apply_quality_floor(
        self, perspectives: list[Perspective]
    ) -> tuple[list[Perspective], int]:
        """
        Split perspectives into (kept, suppressed_count) by the quality floor:
        antithesis HS < advisor_polarity_quality_min_hs, SP (`area`) <
        advisor_perspective_quality_min_sp, DV <
        advisor_perspective_quality_min_dv, or a failed validation verdict.
        The SP + DV pair mirrors the paper's acceptance criterion (SP AND DV
        [P0 p.12]) as soft context-pruning. Missing scores never suppress
        (unscored ≠ bad). Floors of 0 disable the respective check.
        """
        min_hs = self.settings.advisor_polarity_quality_min_hs
        min_sp = self.settings.advisor_perspective_quality_min_sp
        min_dv = self.settings.advisor_perspective_quality_min_dv

        kept: list[Perspective] = []
        suppressed = 0
        for pp in perspectives:
            if pp.validation and pp.validation.startswith("failed"):
                suppressed += 1
                continue
            hs = self._get_antithesis_hs(pp)
            if min_hs > 0 and hs is not None and hs < min_hs:
                suppressed += 1
                continue
            sp = pp.area
            if min_sp > 0 and sp is not None and sp < min_sp:
                suppressed += 1
                continue
            dv = self._get_dialectical_validity(pp)
            if min_dv > 0 and dv is not None and dv < min_dv:
                suppressed += 1
                continue
            kept.append(pp)
        return kept, suppressed

    def _get_antithesis_hs(self, pp: Perspective) -> Optional[float]:
        """HS on the A relationship (how genuine the opposition is)."""
        a_result = self._safe_get(pp.a)
        if not a_result:
            return None
        _, rel = a_result
        return rel.heuristic_similarity

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
    def _get_dialectical_validity(perspective) -> Optional[float]:
        from dialectical_framework.graph.nodes.estimation import \
            DialecticalValidityEstimation

        for est, _ in perspective.estimations.all():
            if isinstance(est, DialecticalValidityEstimation):
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
