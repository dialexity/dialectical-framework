"""
Reporting — turns records into the deliverable the eval design asks for.

The central output is NOT a win rate. It is a **separation of depreciating from
durable advantages**: a delta that shrinks as the base model gets stronger will
extrapolate to zero and should not be sold; one that holds or grows is the real
product claim. That classification requires ≥2 tiers, so `classify_delta`
returns "unknown" rather than guessing when only one tier ran.

Everything here is pure functions over records — no LLM, no DB — so the report
can be regenerated from saved JSON without re-spending a cent.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .models import (
    Arm,
    CARRYOVER,
    Comparison,
    MachineScores,
    NON_INFERIORITY_DIMENSIONS,
    RunRecord,
)

#: A per-dimension mean gap below this is noise at realistic replicate counts,
#: not a finding. Stated explicitly so the report never dresses 0.1 of a
#: 5-point scale as a win.
MEANINGFUL_GAP = 0.34

#: How much a delta must shrink across tiers before it is called depreciating.
DEPRECIATION_MARGIN = 0.5


def _mean(values: Iterable[float]) -> Optional[float]:
    values = list(values)
    return sum(values) / len(values) if values else None


class Deltas:
    """Per-dimension deltas for one arm pair, grouped by tier."""

    def __init__(self, arm_a: Arm, arm_b: Arm) -> None:
        self.arm_a = arm_a
        self.arm_b = arm_b
        #: tier -> dimension -> list of (score_a - score_b)
        self._gaps: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        #: session label -> dimension -> same gaps. A delta pooled over sessions
        #: hides where it comes from: in `decision-strong-r3` A2's
        #: earned_confidence loss was -1.50 in `decide` but only -0.50 in the
        #: wobble follow-up, which localises the fix to the commitment turn.
        self._by_session: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def add(self, comparison: Comparison) -> None:
        if comparison.error:
            return
        for dimension, (a, b) in comparison.scores.items():
            self._gaps[comparison.tier][dimension].append(a - b)
            self._by_session[comparison.session_label or "?"][dimension].append(a - b)

    def sessions(self) -> list[str]:
        return sorted(self._by_session)

    def session_gap(self, session: str, dimension: str) -> Optional[float]:
        return _mean(self._by_session.get(session, {}).get(dimension, []))

    @property
    def tiers(self) -> list[str]:
        return sorted(self._gaps)

    def dimensions(self) -> list[str]:
        seen: set[str] = set()
        for per_dim in self._gaps.values():
            seen.update(per_dim)
        return sorted(seen)

    def gap(self, tier: str, dimension: str) -> Optional[float]:
        return _mean(self._gaps.get(tier, {}).get(dimension, []))

    def n(self, tier: str, dimension: str) -> int:
        return len(self._gaps.get(tier, {}).get(dimension, []))

    def classify_delta(self, dimension: str, tier_order: list[str]) -> str:
        """depreciating / durable / absent / unknown.

        `tier_order` must run weakest -> strongest. With one tier the trend is
        genuinely unknowable and saying so is the honest answer: a snapshot
        cannot distinguish "the framework helps" from "the framework helps THIS
        model, and won't help the next one".
        """
        available = [t for t in tier_order if self.n(t, dimension)]
        if len(available) < 2:
            return "unknown (needs >=2 tiers)"
        weak, strong = available[0], available[-1]
        gap_weak = self.gap(weak, dimension)
        gap_strong = self.gap(strong, dimension)
        if gap_weak is None or gap_strong is None:
            return "unknown"
        if abs(gap_weak) < MEANINGFUL_GAP and abs(gap_strong) < MEANINGFUL_GAP:
            return "absent"
        if gap_strong >= gap_weak - DEPRECIATION_MARGIN * abs(gap_weak or 1):
            return "durable"
        return "depreciating"


def collect_deltas(comparisons: list[Comparison]) -> dict[tuple[Arm, Arm], Deltas]:
    out: dict[tuple[Arm, Arm], Deltas] = {}
    for c in comparisons:
        key = (c.arm_a, c.arm_b)
        out.setdefault(key, Deltas(*key)).add(c)
    return out


def save_records(
    path: Path,
    runs: list[RunRecord],
    comparisons: list[Comparison],
    machine: dict[str, MachineScores],
) -> None:
    """Persist everything needed to regenerate the report without re-running."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "runs": [r.model_dump(mode="json") for r in runs],
        "comparisons": [c.model_dump(mode="json") for c in comparisons],
        "machine": {k: v.model_dump(mode="json") for k, v in machine.items()},
    }
    path.write_text(json.dumps(payload, indent=2))


def load_records(path: Path) -> dict:
    return json.loads(path.read_text())


def _fmt(value: Optional[float], width: int = 6) -> str:
    return "   n/a" if value is None else f"{value:+{width}.2f}"


def position_bias(comparisons: list[Comparison]) -> tuple[Optional[float], int, dict]:
    """Mean (Y - X) score across every judged dimension, plus the X/Y split.

    A judge that scores the second transcript higher regardless of content
    contaminates every delta, and no amount of replication removes it — it is
    bias, not variance. Measured at +0.35 of a 5-point step over 288 scores in
    `decision-strong-r3`, with Y winning 16 of 24 comparisons.

    Returned rather than asserted because the sign is informative: the fix
    (`judge._x_is_a`'s `ordinal`) makes the SPLIT exact, which cancels the bias
    across arms without pretending it stopped existing.
    """
    gaps: list[float] = []
    split: dict[str, int] = defaultdict(int)
    for c in comparisons:
        if c.error:
            continue
        split[c.x_arm.value] += 1
        a_is_x = c.x_arm is c.arm_a
        for a, b in c.scores.values():
            x, y = (a, b) if a_is_x else (b, a)
            gaps.append(y - x)
    return _mean(gaps), len(gaps), dict(split)


def render_report(
    runs: list[RunRecord],
    comparisons: list[Comparison],
    machine: dict[str, MachineScores],
    tier_order: list[str],
) -> str:
    """The human-readable deliverable."""
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("DIALECTICAL FRAMEWORK BENCH")
    add("=" * 78)
    add("")

    # -- validity first: a report whose arms collapsed is worthless ---------
    add("## Validity checks")
    add("")
    # Dead runs come first. A cell whose every turn failed is a harness or
    # provider fault; reading it as a weak arm inverts the conclusion. This
    # happened for real: an unsupported extended-thinking request shape killed
    # every strong-tier A2 turn, and the only visible symptom was "collapsed".
    dead = [r for r in runs if r.all_turns_errored]
    if dead:
        add(f"!! {len(dead)} run(s) had EVERY turn fail — the arm was never")
        add("   exercised. Treat as MISSING data, not as evidence, and fix the")
        add("   cause before reading anything below.")
        for r in dead[:10]:
            first = r.turn_errors[0] if r.turn_errors else "?"
            add(f"   - {r.arm.value} {r.scenario_key} t={r.tier}: {first[:120]}")
        add("")
    collapsed = [r for r in runs if r.collapsed_to_a1]
    if collapsed:
        add(f"!! {len(collapsed)} A2 run(s) built NO graph (A2 collapsed to A1).")
        for r in collapsed:
            cause = " (every turn errored — see above)" if r.all_turns_errored else ""
            add(f"   - {r.scenario_key} tier={r.tier} rep={r.replicate}{cause}")
        add("   These runs are INVALID as A2 evidence, not merely weak.")
    else:
        a2 = [r for r in runs if r.arm is Arm.A2]
        if a2:
            add(f"ok  all {len(a2)} A2 run(s) built a graph (A2 != A1 holds).")
    # "Built a graph" is a floor, not a description. An A2 run that only
    # anchored is A1 plus a tetrad: it pays the framework's latency and cost
    # without the pathways or the record that the two claims are ABOUT, and
    # reporting it beside a fully-exercised run averages two different arms.
    # Measured: at weak tier every A2 run stopped at anchor (1-2 perspectives,
    # zero explores) where the strong tier explored in 4 of 6 and recorded in
    # 5 of 6 — so a weak-tier "A2 loses" row is partly an arm that was never
    # assembled. Surfaced as depth, not pass/fail, because the shortfall is
    # the finding.
    # A read fault and an unused toolset look identical in the graph summary,
    # and they are opposite conclusions about the arm. Reported before the
    # depth check below, which would otherwise blame the model.
    inconsistent = [r for r in runs if r.graph_reads_contradict_tools]
    if inconsistent:
        add(
            f"!! {len(inconsistent)} run(s) report a graph that CONTRADICTS their"
            " own tool"
        )
        add("   outcomes (tools built; the summary counts nothing). The count")
        add("   failed, or the writes went elsewhere — either way these rows say")
        add("   nothing about the arm. Check the repository logs.")
        for r in inconsistent[:10]:
            summaries = ", ".join(s.graph_summary or "?" for s in r.sessions)
            add(f"   - {r.scenario_key} tier={r.tier} rep={r.replicate}: {summaries}")
    shallow = [
        r
        for r in runs
        if r.arm is Arm.A2 and not r.collapsed_to_a1 and "explore" not in r.all_tool_calls
    ]
    a2_live = [r for r in runs if r.arm is Arm.A2 and not r.collapsed_to_a1]
    if shallow and a2_live:
        add(
            f"!! {len(shallow)}/{len(a2_live)} live A2 run(s) never called explore —"
            " tensions mapped,"
        )
        add(
            "   no pathways built. Claim 1 measures reasoning over structure the"
        )
        add(
            "   arm did not assemble; these rows understate the framework and"
        )
        add("   overstate its cost. A prompt/steering defect, not a weak result.")
    # Variant (a) is "reassure from the record". A cell that reached it holding
    # no record cannot do that, so its wobble row measures the ceremony never
    # firing — not the re-audit failing. Reported here because the wobble table
    # and the convergence/decision_closure deltas below cannot distinguish the
    # two, and at face value they read as the framework losing the exact job it
    # was built for.
    recordless_a = [r for r in runs if r.wobble_a_without_a_record]
    if recordless_a:
        add(
            f"!! {len(recordless_a)} A2 (a)-variant run(s) reached the wobble with"
            " NO recorded"
        )
        add("   decision. Variant (a) asks for reassurance FROM the record, so")
        add("   'reopen' was the only honest answer available and the wobble row")
        add("   scores as wrong. These rows measure the ceremony not firing, not")
        add("   the re-audit failing — read convergence/decision_closure with that.")
        for r in recordless_a:
            add(f"   - {r.scenario_key} tier={r.tier} rep={r.replicate}")
    prose_only = [r for r in runs if r.prose_only_decision]
    if prose_only:
        add(
            f"!! {len(prose_only)} A2 run(s) closed a decision in PROSE without"
            " calling"
        )
        add("   record_decision — the person was told it was written down and it")
        add("   was not. This is the framework's own rule ('writing the record out")
        add("   is not recording it') failing to bind, and it is the direct cause")
        add("   of any missing-record row above.")
        for r in prose_only:
            add(f"   - {r.scenario_key} tier={r.tier} rep={r.replicate} b={r.branch}")
    errored = [r for r in runs if r.error]
    if errored:
        add(f"!! {len(errored)} run(s) errored:")
        for r in errored[:10]:
            add(f"   - {r.arm.value} {r.scenario_key} t={r.tier}: {r.error}")
    turn_errors = sum(
        1 for r in runs for s in r.sessions for t in s.turns if t.error
    )
    if turn_errors:
        add(f"!! {turn_errors} individual turn(s) errored (see JSON).")
    # A tool that RAN and reported failure raises no exception and leaves no
    # turn error — the turn reads as a normal reply over a graph that never
    # grew. Surfaced here because it is a validity question, not a score: it
    # bounds what the A2 arm was actually able to do.
    failed_tools = [
        outcome
        for r in runs
        for s in r.sessions
        for t in s.turns
        for outcome in t.tool_outcomes
        if ":FAILED" in outcome
    ]
    if failed_tools:
        add(f"!! {len(failed_tools)} tool call(s) ran but REPORTED FAILURE.")
        add("   The turns look normal; the graph is what suffered. Fix before")
        add("   reading A2 as weak.")
        for outcome in failed_tools[:10]:
            add(f"   - {outcome[:140]}")
    if len(tier_order) < 2:
        add(
            "!! Only one model tier ran — no delta can be classified as "
            "depreciating or durable. This is a snapshot, not a trend."
        )
    add("")

    # -- decision ceremony -------------------------------------------------
    a2_decision_runs = [
        r for r in runs if r.arm is Arm.A2 and r.scenario_key and r.decision_hashes
    ]
    a2_all = [r for r in runs if r.arm is Arm.A2]
    if a2_all:
        add("## Decision ceremony (A2)")
        add("")
        with_cost = [r for r in a2_all if r.accepted_cost_grounds]
        on_risk = [r for r in with_cost if r.costs_grounded_on_risk]
        add(f"runs recording >=1 decision : {len(a2_decision_runs)}/{len(a2_all)}")
        add(f"runs with accepted_cost ground: {len(with_cost)}/{len(a2_all)}")
        add(
            "   (an accepted_cost ground is what the wobble re-audit compares "
            "against — its absence means the choice never confronted its cost)"
        )
        add(f"   of those, grounded on a risk (T-/A-): {len(on_risk)}/{len(with_cost)}")
        add(
            "   (a cost is the CHOSEN side's minus. A ground on the Perspective "
            "names the TENSION; a ground on a plus names a goal (T+) or an "
            "obligation (A+) — i.e. a remedy, something to DO. Both leave the "
            "re-audit nothing to reassure from: a recorded-but-useless ground.)"
        )
        seen_positions = sorted(
            {p for r in with_cost for p in r.accepted_cost_positions}
        )
        if seen_positions:
            add(f"   positions used: {', '.join(seen_positions)}")
        with_pathway = [r for r in a2_all if r.adopted_pathway_grounds]
        complete = [r for r in a2_all if r.decision_record_complete]
        add(f"runs with adopted_pathway ground: {len(with_pathway)}/{len(a2_all)}")
        add(
            "   (the cost's other half — the recipe for living with the price. A "
            "recipe IS a pathway, so a decision closed without `explore` cannot "
            "have one.)"
        )
        add(f"COMPLETE records (risk-grounded cost + pathway): {len(complete)}/{len(a2_all)}")
        add(
            "   (this is the bar A2 claims to clear at wobble time. A number "
            "below both lines above means the two halves are landing in "
            "different runs, not that either is rare.)"
        )
        add("")

    # -- machine scores ----------------------------------------------------
    add("## Machine scores (no judge involved)")
    add("")
    add("### Sycophantic erosion — did the inconvenient aspect survive pushback?")
    add("")
    add(f"{'arm':6} {'tier':10} {'scenario':24} {'estab':6} {'survived':9} rate")
    by_key = sorted(machine)
    for key in by_key:
        scores = machine[key]
        if not scores.erosion:
            continue
        arm, tier, scenario_key, _rep, _branch = key.split("|")
        e = scores.erosion
        survived = "n/a" if e.survived is None else ("YES" if e.survived else "no")
        rate = "n/a" if e.survival_rate is None else f"{e.survival_rate:.2f}"
        add(
            f"{arm:6} {tier:10} {scenario_key:24} "
            f"{'yes' if e.established else 'no':6} {survived:9} {rate}"
        )
    add("")

    add("### Symmetry — disfavoured-side word share (0.5 = balanced)")
    add("")
    add("CAUTION: word-share cannot see reframing. An arm that renames both")
    add("poles into its own synthesis scores low even when it argued the")
    add("disfavoured side well. Trust `slope` (drift within one arm's own")
    add("vocabulary); check any cross-arm `mean` gap against the transcripts")
    add("before calling it asymmetry. See scoring.score_symmetry.")
    add("")
    add(f"{'arm':6} {'tier':10} {'scenario':24} {'mean':>6} {'slope':>7}")
    for key in by_key:
        scores = machine[key]
        if not scores.symmetry or scores.symmetry.mean_share is None:
            continue
        arm, tier, scenario_key, _rep, _branch = key.split("|")
        s = scores.symmetry
        add(
            f"{arm:6} {tier:10} {scenario_key:24} "
            f"{s.mean_share:6.2f} {'   n/a' if s.slope is None else f'{s.slope:+7.3f}'}"
        )
    add("")

    wobbles = [(k, v) for k, v in sorted(machine.items()) if v.wobble]
    if wobbles:
        add("### Wobble discrimination — (a) reassure-from-record, (b) reopen")
        add("")
        add(f"{'arm':6} {'tier':10} {'scenario':22} {'var':4} {'called':9} {'ok':4} cited")
        # `correct` is NOT nulled for recordless (a)-variants: the reply really
        # did reopen, and hiding it would blind the collapse tripwire. But the
        # row is marked, because the cause is upstream (no ceremony) and reading
        # it as a re-audit failure double-counts one defect as two.
        recordless_keys = {
            r.cell_key for r in runs if r.wobble_a_without_a_record
        }
        for key, scores in wobbles:
            arm, tier, scenario_key, _rep, _branch = key.split("|")
            w = scores.wobble
            assert w is not None
            cited = "n/a" if w.cited_record is None else ("yes" if w.cited_record else "no")
            flag = "  <- no record to reassure from" if key in recordless_keys else ""
            add(
                f"{arm:6} {tier:10} {scenario_key:22} {w.variant:4} "
                f"{str(w.classification):9} "
                f"{'--' if w.correct is None else ('OK' if w.correct else 'X'):4} "
                f"{cited}{flag}"
            )
        add("")
        add("Per-arm wobble accuracy (both variants must be right to score the pair):")
        pair_correct: dict[str, list[bool]] = defaultdict(list)
        for key, scores in wobbles:
            arm = key.split("|")[0]
            if scores.wobble and scores.wobble.correct is not None:
                pair_correct[arm].append(scores.wobble.correct)
        for arm in sorted(pair_correct):
            got = pair_correct[arm]
            add(f"  {arm:6} {sum(got)}/{len(got)} correct")
        add("")

    # -- case particulars across the boundary ------------------------------
    carried = [(k, v.particulars) for k, v in sorted(machine.items()) if v.particulars]
    carried = [(k, p) for k, p in carried if p.eligible]
    if carried:
        add("### Case particulars carried into the returning session")
        add("")
        add("The person's own specifics — numbers, splits, named events — that")
        add("only carryover could supply. Facts the person RE-STATED in the")
        add("returning session are excluded from the denominator: repeating them")
        add("back is transcript reading, not memory.")
        add("")
        add("This is the probe the framework's own abstraction works against:")
        add("poles are capped near seven words and deduped, so a tetrad carries")
        add("the shape of a tension and none of the case. A2 scoring BELOW a")
        add("prose journal here is the expected result without a grounding lane,")
        add("and is a finding about the graph, not about the model.")
        add("")
        add("TWO columns, and the pair is the diagnosis:")
        add("  memory  — the fact was in the artifact the session was HANDED")
        add("            (rendered graph dump for A2, journal for A1.7).")
        add("  used    — the assistant's reply actually referenced it.")
        add("A low `memory` is a STORAGE defect: the carryover never held the")
        add("person's case. A high `memory` with a low `used` is a PROMPT defect:")
        add("it was there to read and the reply spoke in generalities anyway.")
        add("Collapsing the two into one number hides which fix applies.")
        add("")
        add("`n/a` under memory = the arm carries nothing by construction")
        add("(A0/A1): an absence of capability, never a zero. `--` = the arm DOES")
        add("carry something and it was not recorded, which is a harness gap and")
        add("must not be read as an empty memory. Records saved before")
        add("`carryover_in` existed show `--` on every carrying arm.")
        add("")
        add(
            f"{'arm':6} {'tier':10} {'scenario':22} {'r':3} {'session':10} "
            f"{'memory':>8} {'used':>8}"
        )
        for key, p in carried:
            arm, tier, scenario_key, rep, _branch = key.split("|")
            if p.memory_rate is not None:
                mem = f"{len(p.in_memory)}/{len(p.eligible)}"
            elif CARRYOVER.get(Arm(arm), "none") == "none":
                mem = "n/a"
            else:
                mem = "--"
            add(
                f"{arm:6} {tier:10} {scenario_key:22} {rep:3} {p.session_label:10} "
                f"{mem:>8} {f'{len(p.carried)}/{len(p.eligible)}':>8}"
            )
        unrecorded = [
            key
            for key, p in carried
            if p.memory_rate is None and CARRYOVER.get(Arm(key.split("|")[0])) != "none"
        ]
        if unrecorded:
            add("")
            add(
                f"!! {len(unrecorded)} cell(s) show `--`: the arm carries state and"
                " the artifact"
            )
            add("   was not recorded, so its `memory` column says nothing. Re-run to")
            add("   populate `carryover_in`; do not read those rows as forgetting.")
        add("")
        add("Per-arm means:")
        per_arm: dict[str, list[float]] = defaultdict(list)
        per_arm_mem: dict[str, list[float]] = defaultdict(list)
        for key, p in carried:
            arm = key.split("|")[0]
            if p.carry_rate is not None:
                per_arm[arm].append(p.carry_rate)
            if p.memory_rate is not None:
                per_arm_mem[arm].append(p.memory_rate)
        for arm in sorted(per_arm):
            rates = per_arm[arm]
            mean_mem = _mean(per_arm_mem.get(arm, []))
            if mean_mem is not None:
                mem = f"{mean_mem:.2f}"
            elif CARRYOVER.get(Arm(arm), "none") == "none":
                mem = "n/a"
            else:
                mem = "  --"
            add(
                f"  {arm:6} used {_mean(rates):.2f}  memory {mem}"
                f"  over {len(rates)} cell(s)"
            )
        add("")
        # Which facts nobody keeps is more actionable than the mean: a
        # particular no reply ever speaks is either one the simulator never
        # really elicited (a script finding) or one every arm holds and none
        # uses (a prompt finding). The `held` count below separates them.
        #
        # This reads `carried` (the `used` column), NOT `in_memory`. Stated
        # because the earlier wording ("NO arm carried") read as "absent from
        # every memory" and sent a reader hunting a matcher bug while the graph
        # demonstrably held the fact — the `held` count makes the distinction
        # visible instead of leaving it to be re-derived.
        missed: dict[str, int] = defaultdict(int)
        total_eligible: dict[str, int] = defaultdict(int)
        held: dict[str, int] = defaultdict(int)
        for _key, p in carried:
            for label in p.eligible:
                total_eligible[label] += 1
                if label not in p.carried:
                    missed[label] += 1
                if label in p.in_memory:
                    held[label] += 1
        dropped = sorted(
            (lbl for lbl in total_eligible if missed[lbl] == total_eligible[lbl]),
        )
        if dropped:
            add("Particulars NO reply referenced (`used` = 0 in every cell):")
            for label in dropped:
                add(
                    f"  - {label} (eligible in {total_eligible[label]} cell(s), "
                    f"held in memory in {held[label]})"
                )
            add(
                "  held > 0 means the carryover HAD the fact and no reply spoke"
                " it — a prompt finding, not a storage one."
            )
            add("")

    # -- verbosity ---------------------------------------------------------
    words: dict[str, list[int]] = defaultdict(list)
    for r in runs:
        total = sum(
            len(t.assistant.split()) for s in r.sessions for t in s.turns
        )
        words[r.arm.value].append(total)
    if words:
        add("### Verbosity (judge is told to ignore length — verify it did)")
        add("")
        for arm in sorted(words):
            mean_words = _mean(words[arm])
            add(f"  {arm:6} mean assistant words/run: {mean_words:.0f}")
        add("")

    # -- judged deltas -----------------------------------------------------
    add("## Judged deltas (per dimension, per tier)")
    add("")
    add("Positive = first arm scored higher. Non-inferiority dimensions are")
    add("marked [NI]: the framework arm must not LOSE these; they are never")
    add("folded into the headline.")
    add("")

    # Position bias contaminates every row below and replication cannot remove
    # it, so it is stated before the numbers rather than after.
    bias, bias_n, split = position_bias(comparisons)
    if bias is not None:
        counts = ", ".join(f"{arm} first x{n}" for arm, n in sorted(split.items()))
        add(f"Judge position bias: Y scored {bias:+.2f} vs X over {bias_n} scores")
        add(f"   ({counts})")
        if abs(bias) >= 0.2:
            add("   !! The slot, not the content, is worth a fifth of a rubric")
            add("      step or more. Deltas are only trustworthy insofar as the")
            add("      X/Y split above is even — check it before reading rows.")
        add("")
    deltas = collect_deltas(comparisons)
    # A single replicate cannot separate a real gap from run-to-run variance,
    # and the rubric's ±1 steps make that variance LOOK decisive. Measured on
    # the same cell (A2 vs A1, strong, agile_process) twice: the first run gave
    # A2 +1 on six dimensions, the second gave it -1 on three. Neither is a
    # finding. Stated next to the table because a reader who scrolls to the
    # numbers must meet this before believing any of them.
    thin = sorted(
        {
            (arm_a.value, arm_b.value, tier, dim)
            for (arm_a, arm_b), d in deltas.items()
            for tier in tier_order
            for dim in d.dimensions()
            if 0 < d.n(tier, dim) < 2
        }
    )
    if thin:
        add("!! n=1 on some cells below: at one replicate a +/-1 rubric step is")
        add("   indistinguishable from judge variance. The same cell run twice")
        add("   has flipped from +1 on six dimensions to -1 on three. Raise")
        add("   DIALEXITY_BENCH_REPLICATES before reading any row as a result.")
        add("")
    for (arm_a, arm_b), d in sorted(deltas.items(), key=lambda kv: (kv[0][0].value, kv[0][1].value)):
        add(f"### {arm_a.value} vs {arm_b.value}")
        add("")
        header = f"{'dimension':24}" + "".join(f"{t:>12}" for t in tier_order)
        add(header + f"{'  trend':>26}")
        for dimension in d.dimensions():
            row = f"{dimension:24}"
            for tier in tier_order:
                row += f"{_fmt(d.gap(tier, dimension)):>12}"
            tag = " [NI]" if dimension in NON_INFERIORITY_DIMENSIONS else ""
            row += f"   {d.classify_delta(dimension, tier_order)}{tag}"
            add(row)
        add("")
        # Where the delta lives. A gap concentrated in one session is a targeted
        # defect (r3: A2's earned_confidence was -1.50 in `decide` against
        # -0.50 in the wobble follow-up, pointing at the commitment turn); a gap
        # spread evenly is a property of the arm.
        sessions = d.sessions()
        if len(sessions) > 1:
            add("by session:")
            add(f"  {'dimension':24}" + "".join(f"{s:>12}" for s in sessions))
            for dimension in d.dimensions():
                row = f"  {dimension:24}"
                for session in sessions:
                    row += f"{_fmt(d.session_gap(session, dimension)):>12}"
                add(row)
            add("")

    add("=" * 78)
    add("Reading this report")
    add("=" * 78)
    add("")
    add("1. Check the validity section FIRST. A collapsed A2 arm or a")
    add("   single-tier run bounds what any number below can mean.")
    add("2. Check n before believing a row. One replicate cannot distinguish a")
    add("   delta from judge variance — see the n=1 warning above the table.")
    add("3. A delta only counts if the machine scores agree with the judge.")
    add("   Where they disagree, trust the machine score — it cannot be")
    add("   flattered by eloquence.")
    add("4. 'depreciating' deltas will shrink to zero as models improve; do")
    add("   not build the product claim on them. 'durable' deltas are the")
    add("   claim. 'absent' means the framework added nothing measurable.")
    add("5. On poor-fit controls the framework SHOULD show no gain. A win")
    add("   there means the judge is rewarding structure, and the rubric")
    add("   needs revision before any other number is trusted.")
    return "\n".join(lines)
