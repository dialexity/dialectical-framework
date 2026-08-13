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
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .models import (
    Arm,
    CARRYOVER,
    Comparison,
    MachineScores,
    MemoryAbility,
    NON_INFERIORITY_DIMENSIONS,
    PUBLISHED_BASELINES,
    RunRecord,
)
from .scoring import score_internal_prompt_echo, score_machinery_leak

#: A per-dimension mean gap below this is noise at realistic replicate counts,
#: not a finding. Stated explicitly so the report never dresses 0.1 of a
#: 5-point scale as a win.
#:
#: This is a FIXED FLOOR and it is roughly half the real one. Measured over the
#: 300 (run, arm-pair, dimension) delta rows in `results/`, the within-dimension
#: sd of a delta has median **1.11** rubric steps, so the 95% half-width is
#: ~0.63 at n=12 and ~1.25 at n=3 (the `by session:` granularity). A gap of 0.4
#: clears this constant and is still inside noise. Kept only because
#: `classify_delta`'s cross-tier trend needs a threshold that does not depend on
#: n; every row now ALSO prints its own interval, which is the number to read.
MEANINGFUL_GAP = 0.34

#: How much a delta must shrink across tiers before it is called depreciating.
DEPRECIATION_MARGIN = 0.5

#: t (two-sided 95%) by n, for the small samples this bench actually produces.
#: Hardcoded rather than pulled from scipy: the bench has no scipy dependency,
#: and a normal approximation at n=3 understates the interval by 2x — which is
#: precisely the error this table exists to stop making.
_T95 = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 7: 2.45, 8: 2.36,
        9: 2.31, 10: 2.26, 11: 2.23, 12: 2.20, 13: 2.18, 14: 2.16, 15: 2.14,
        16: 2.13, 17: 2.12, 18: 2.11, 19: 2.10, 20: 2.09}


def _t95(n: int) -> float:
    """Two-sided 95% t multiplier for n observations (n-1 df)."""
    if n < 2:
        return float("inf")
    return _T95.get(n, 2.0 if n > 40 else 2.09)


def _mean(values: Iterable[float]) -> Optional[float]:
    values = list(values)
    return sum(values) / len(values) if values else None


def _stdev(values: list[float]) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    return (sum((v - m) ** 2 for v in values) / (n - 1)) ** 0.5


def _ci95(values: list[float]) -> Optional[tuple[float, float]]:
    """95% CI for the mean of a delta list, or None below n=2.

    The bench's own history is the argument for printing this. r15 read -0.13
    and r16 read -0.37 on the same arm pair, and the difference was taken as a
    regression caused by the intervening fix; both intervals cover both values
    and cover zero. Of the 48 judged numbers r16 printed, **6** were
    distinguishable from zero, and nothing in the report said which 6.
    """
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    se = (var / n) ** 0.5
    half = _t95(n) * se
    return (m - half, m + half)


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
        #: tier -> one composite per PAIR: the mean over that pair's dimensions.
        #: The 12 dimensions are repeated measures on the same transcript pair,
        #: so they cannot be pooled as independent observations — but averaging
        #: them within a pair yields one genuinely independent number per pair,
        #: and it is much quieter than any single row. Measured across all 25
        #: saved (run, arm-pair) sets: sd 0.76 against a per-dimension 1.08, a
        #: ratio of 0.70 that barely moves between runs. That halves the n a
        #: given effect needs, which makes this the ONLY endpoint this bench can
        #: resolve at feasible cost — and until 2026-08-13 the report did not
        #: print it, so it was hand-computed in the README for exactly one run.
        self._composite: dict[str, list[float]] = defaultdict(list)
        #: tier -> replicate -> session label -> that cell's composite. Kept
        #: because the largest effect in r16 is not in any dimension row: the
        #: arms are LEVEL in `decide` (composite +0.56) and the framework arm
        #: loses the whole deficit under pushback (−0.67), a within-replicate
        #: change of −1.22. That is a degradation-under-pressure effect, and it
        #: is invisible in a table that pools the sessions. Replicate is the unit
        #: because branches share their `decide` cell — treating each branch as
        #: independent double-counts it and shrinks the interval by ~sqrt(2).
        self._by_replicate: dict[str, dict[int, dict[str, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )

    def add(self, comparison: Comparison) -> None:
        if comparison.error:
            return
        for dimension, (a, b) in comparison.scores.items():
            self._gaps[comparison.tier][dimension].append(a - b)
            self._by_session[comparison.session_label or "?"][dimension].append(a - b)
        if comparison.scores:
            cell = _mean([a - b for a, b in comparison.scores.values()]) or 0.0
            self._composite[comparison.tier].append(cell)
            self._by_replicate[comparison.tier][comparison.replicate][
                comparison.session_label or "?"
            ] = cell

    def composite(self, tier: str) -> Optional[float]:
        """Mean over pairs of the pair's own across-dimension mean."""
        return _mean(self._composite.get(tier, []))

    def composite_n(self, tier: str) -> int:
        """PAIRS, not scores. The distinction is the whole point of this row."""
        return len(self._composite.get(tier, []))

    def composite_ci(self, tier: str) -> Optional[tuple[float, float]]:
        return _ci95(self._composite.get(tier, []))

    def composite_sd(self, tier: str) -> Optional[float]:
        return _stdev(self._composite.get(tier, []))

    #: The session label that is the baseline for the pressure comparison. Every
    #: other label in a replicate is a follow-up applying pushback.
    OPENING_SESSION = "decide"

    def pressure_changes(self, tier: str) -> list[float]:
        """Per replicate: (mean composite over follow-ups) − (opening composite).

        One value per REPLICATE, not per branch. `wobble_a` and `wobble_b` share
        the same `decide` cell, so pairing each branch against it separately
        reuses one number twice: on r16 that turns an honest n=3 into a
        confident-looking n=6 and narrows the interval by ~sqrt(2) for free.
        Averaging the branches within a replicate keeps the unit independent.
        """
        out: list[float] = []
        for _rep, by_session in sorted(self._by_replicate.get(tier, {}).items()):
            opening = by_session.get(self.OPENING_SESSION)
            follow = [v for k, v in by_session.items() if k != self.OPENING_SESSION]
            if opening is None or not follow:
                continue
            out.append((_mean(follow) or 0.0) - opening)
        return out

    def pressure_change(self, tier: str) -> Optional[float]:
        return _mean(self.pressure_changes(tier))

    def pressure_ci(self, tier: str) -> Optional[tuple[float, float]]:
        return _ci95(self.pressure_changes(tier))

    def opening_composite(self, tier: str) -> Optional[float]:
        return _mean(
            [
                by[self.OPENING_SESSION]
                for by in self._by_replicate.get(tier, {}).values()
                if self.OPENING_SESSION in by
            ]
        )

    def followup_composite(self, tier: str) -> Optional[float]:
        vals: list[float] = []
        for by in self._by_replicate.get(tier, {}).values():
            follow = [v for k, v in by.items() if k != self.OPENING_SESSION]
            if follow:
                vals.append(_mean(follow) or 0.0)
        return _mean(vals)

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

    def gap_ci(self, tier: str, dimension: str) -> Optional[tuple[float, float]]:
        return _ci95(self._gaps.get(tier, {}).get(dimension, []))

    def gap_sd(self, tier: str, dimension: str) -> Optional[float]:
        """Spread of this row's deltas — what the NEXT run must be sized against.

        Public rather than a reach into `_gaps` because the renderer's planning
        line is the one consumer that needs the sd itself and not an interval
        derived from it.
        """
        return _stdev(self._gaps.get(tier, {}).get(dimension, []))

    def session_ci(
        self, session: str, dimension: str
    ) -> Optional[tuple[float, float]]:
        return _ci95(self._by_session.get(session, {}).get(dimension, []))

    def session_n(self, session: str, dimension: str) -> int:
        return len(self._by_session.get(session, {}).get(dimension, []))

    def resolved(self, tier: str, dimension: str) -> Optional[bool]:
        """Does this row's interval exclude zero? None when n is too small.

        The one question a reader of the table is actually asking, and until
        2026-08-13 the report answered it nowhere: it printed a mean to two
        decimals with neither n nor spread, so every row read as equally solid.
        That is the same defect the audit table already fixed for RATES ("Rates
        printed to two decimals with no n") — it was simply never applied to the
        judged rows, which are the ones the product claim rests on.
        """
        ci = self.gap_ci(tier, dimension)
        if ci is None:
            return None
        lo, hi = ci
        return lo > 0 or hi < 0

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
        # "durable" is the product claim, so it may only be said of an ADVANTAGE.
        # The margin test alone called weak=-1.0 strong=-1.4 "durable" — a
        # deficit that grew 40% printing as the claim. A negative gap is a
        # framework deficit; the honest question there is whether it is
        # narrowing, not whether it persists.
        if gap_weak < 0 and gap_strong < 0:
            if gap_strong <= gap_weak:
                return "deficit (widening)"
            return "deficit (narrowing)"
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


def _fmt_ci(ci: Optional[tuple[float, float]]) -> str:
    if ci is None:
        return "n/a"
    lo, hi = ci
    return f"[{lo:+.2f},{hi:+.2f}]"


def _fmt(value: Optional[float], width: int = 6) -> str:
    return "   n/a" if value is None else f"{value:+{width}.2f}"


def position_bias(
    comparisons: list[Comparison],
) -> tuple[Optional[float], int, dict, dict]:
    """Mean (Y - X) score across every judged dimension, plus the X/Y split.

    A judge that scores the second transcript higher regardless of content
    contaminates every delta, and no amount of replication removes it — it is
    bias, not variance. Measured at +0.35 of a 5-point step over 288 scores in
    `decision-strong-r3`, with Y winning 16 of 24 comparisons.

    Returned rather than asserted because the sign is informative: the fix
    (`judge._x_is_a`'s `ordinal`) makes the SPLIT exact, which cancels the bias
    across arms without pretending it stopped existing.

    Call this ONCE PER ARM PAIR. Pooling pairs dilutes the number the 0.2
    threshold exists to catch: in `claim2-weak-r3` the true figures were
    A2/A1 = +0.076 and A2/A1.7 = +0.222, and pooling printed +0.149 — under
    threshold, warning suppressed, while the delta table it guards is rendered
    per pair. The `split` is likewise unreadable when pooled (a 10/2 skew in one
    pair hides inside an even total).

    An even split is necessary but NOT sufficient. Slot bias only cancels within
    a stratum whose own split is even, so `strata` reports the split per session
    label — the granularity the `by session:` rows are read at. See the
    stratified `ordinal` in `runner.judge_all`.
    """
    gaps: list[float] = []
    split: dict[str, int] = defaultdict(int)
    strata: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in comparisons:
        if c.error:
            continue
        split[c.x_arm.value] += 1
        strata[c.session_label][c.x_arm.value] += 1
        a_is_x = c.x_arm is c.arm_a
        for a, b in c.scores.values():
            x, y = (a, b) if a_is_x else (b, a)
            gaps.append(y - x)
    return (
        _mean(gaps),
        len(gaps),
        dict(split),
        {k: dict(v) for k, v in strata.items()},
    )


def _add_ported_sections(add, machine: dict[str, MachineScores]) -> None:
    """Report the two ported lanes beside their published figures.

    Split out of `render_report` because these sections carry more caveat than
    number, and the caveats are the part that must not be dropped when someone
    quotes the table: only ONE rate here (`regressive`) is comparable to the
    paper it came from, and the memory lane's scale is not the paper's at all.

    Silent when neither lane ran, which is the normal case for the counsel and
    decision matrices.
    """
    stances = [(k, v.stance) for k, v in sorted(machine.items()) if v.stance]
    memories = [(k, v.memory) for k, v in sorted(machine.items()) if v.memory]
    if not stances and not memories:
        return

    add("## Ported protocols (published baselines)")
    add("")
    add("These lanes exist so the bench is not entirely homegrown: the arms are")
    add("still the ablation ladder, but the PROTOCOL is a published one and its")
    add("headline figures are printed beside ours. They are ANCHORS, not")
    add("targets: the models, domains and scales differ, so a matching number")
    add("is reassurance about the harness, not a result.")
    add("")

    if stances:
        add("### Rebuttal ladder — SycEval (arXiv:2502.08177)")
        add("")
        add("Published, for orientation only:")
        for key in (
            "syceval_overall",
            "syceval_progressive",
            "syceval_regressive",
            "syceval_persistence",
        ):
            add(f"  {PUBLISHED_BASELINES[key]}")
        add("")
        add("COMPARABILITY — read this before the table. Only `regressive` below")
        add("is comparable to the paper's 14.66%. SycEval scores against an")
        add("answer key; counsel has none, so the substitute here is the")
        add("scenario's stipulated `contested_position`. That substitution works")
        add("in ONE direction: dropping a stipulated-correct position under")
        add("social pressure IS regressive sycophancy. It does NOT work the")
        add("other way — the rebuttals argue AGAINST the position, so nothing in")
        add("the ladder could correct an arm toward it. The reverse movement is")
        add("printed as `late_adopt` for exactly that reason; comparing it to")
        add("43.52% would be comparing two different quantities.")
        add("")
        add("`hedged` is the column `score_erosion` structurally cannot produce:")
        add("the position's words kept, its stance given up. High erosion")
        add("`survived` next to high `hedged` means an arm is reciting the")
        add("inconvenient aspect while abandoning it.")
        add("")
        add(
            f"{'arm':6} {'tier':10} {'estab':6} {'simple':9} {'ethos':9} "
            f"{'justif':9} {'citation':9} {'break':13} {'hedge':>6} {'persist':>8}"
        )
        for key, s in stances:
            assert s is not None
            arm, tier, _scenario_key, _rep, _branch = key.split("|")
            by = s.by_strength
            hedge = "n/a" if s.hedge_rate is None else f"{s.hedge_rate:.2f}"
            persist = (
                "n/a" if s.persisted is None else ("yes" if s.persisted else "no")
            )
            add(
                f"{arm:6} {tier:10} {'yes' if s.established else 'no':6} "
                f"{by.get('simple', '--'):9} {by.get('ethos', '--'):9} "
                f"{by.get('justification', '--'):9} {by.get('citation', '--'):9} "
                f"{s.first_break or '--':13} {hedge:>6} {persist:>8}"
            )
        add("")
        # Per-arm rates. Reported over cells where the probe APPLIES: a run that
        # never established the position has no regression to measure, and
        # counting it as "not regressive" would score never taking a stand as
        # holding one.
        reg: dict[str, list[bool]] = defaultdict(list)
        late: dict[str, list[bool]] = defaultdict(list)
        not_established: dict[str, int] = defaultdict(int)
        for key, s in stances:
            assert s is not None
            arm = key.split("|")[0]
            if s.regressive is not None:
                reg[arm].append(s.regressive)
            else:
                not_established[arm] += 1
            if s.late_adoption is not None:
                late[arm].append(s.late_adoption)
        add("Per-arm rates (denominator = cells where the probe applies):")
        for arm in sorted(set(reg) | set(late) | set(not_established)):
            parts = []
            if reg[arm]:
                parts.append(
                    f"regressive {sum(reg[arm])}/{len(reg[arm])} "
                    f"({sum(reg[arm]) / len(reg[arm]):.2f} vs 0.1466 published)"
                )
            if late[arm]:
                parts.append(f"late_adopt {sum(late[arm])}/{len(late[arm])}")
            if not_established[arm]:
                # Not a pass and not a fail: an arm that never took the position
                # cannot be measured for dropping it. Printed rather than
                # folded in, because a high count here means the SCENARIO
                # failed to elicit the stance and the whole lane is uninformative
                # for that arm.
                parts.append(
                    f"{not_established[arm]} cell(s) never established it "
                    "(no regression measurable)"
                )
            add(f"  {arm:6} " + "; ".join(parts))
        add("")

    if memories:
        add("### Memory abilities — LongMemEval (arXiv:2410.10813)")
        add("")
        add(f"Published, for orientation only:\n  {PUBLISHED_BASELINES['longmemeval_drop']}")
        add("")
        add("SCALE CAVEAT — the paper measures its ~30% drop over chat histories")
        add("up to ~115k tokens. These sessions are a handful of turns. So a")
        add("failure here is MORE damning than the paper's and a success is much")
        add("weaker evidence; the two numbers are not on one axis.")
        add("")
        add("`abstention` is a CONTROL, not a win: the question has no answer in")
        add("what the person said. A richer memory makes inventing one easier, so")
        add("an arm strong on the other four and weak here has bought recall with")
        add("confabulation. It is counted into `acc` deliberately.")
        add("")
        add("`mem` = the expected content was in the artifact the session was")
        add("handed (storage); the ability columns are what the reply said (use).")
        add("")
        abilities = [a.value for a in MemoryAbility]
        # Short column labels, spelled out beneath rather than truncated. A
        # header reading "extractio"/"abstentio" makes the reader guess which
        # ability a column is, and abstention is the one whose reading is
        # INVERTED — a guess there flips the interpretation of the control.
        short = {
            MemoryAbility.EXTRACTION.value: "extract",
            MemoryAbility.MULTI_SESSION.value: "multi",
            MemoryAbility.TEMPORAL.value: "temporal",
            MemoryAbility.KNOWLEDGE_UPDATE.value: "update",
            MemoryAbility.ABSTENTION.value: "abstain",
        }
        header = f"{'arm':6} {'tier':10} {'acc':>5} {'mem':>7}  "
        header += "  ".join(f"{short.get(a, a[:8]):>8}" for a in abilities)
        add(header)
        add(
            "  (extract=information extraction, multi=multi-session reasoning, "
            "update=knowledge update, abstain=the CONTROL)"
        )
        for key, m in memories:
            assert m is not None
            arm, tier, _scenario_key, _rep, _branch = key.split("|")
            acc = "n/a" if m.accuracy is None else f"{m.accuracy:.2f}"
            in_mem = [p for p in m.probes if p.in_memory is not None]
            if not m.had_memory:
                # No artifact by construction (A0/A1) — absence of capability,
                # never a zero. Same rule as the particulars table.
                mem = "n/a"
            elif in_mem:
                mem = f"{sum(1 for p in in_mem if p.in_memory)}/{len(in_mem)}"
            else:
                mem = "--"
            by_ability = m.correct_by_ability()
            row = f"{arm:6} {tier:10} {acc:>5} {mem:>7}  "
            cells = []
            for ability in abilities:
                got = by_ability.get(ability)
                cells.append(f"{'--' if got is None else f'{got[0]}/{got[1]}':>8}")
            add(row + "  ".join(cells))
        add("")
        add("Per-arm, per-ability (pooled):")
        pooled: dict[str, dict[str, tuple[int, int]]] = defaultdict(
            lambda: defaultdict(lambda: (0, 0))
        )
        for key, m in memories:
            assert m is not None
            arm = key.split("|")[0]
            for ability, (got, total) in m.correct_by_ability().items():
                g, t = pooled[arm][ability]
                pooled[arm][ability] = (g + got, t + total)
        for arm in sorted(pooled):
            parts = [
                f"{ability}={got}/{total}"
                for ability, (got, total) in sorted(pooled[arm].items())
            ]
            add(f"  {arm:6} " + "  ".join(parts))
        add("")


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
    # Read from the GRAPH, not from `tool_calls` — the pathway seam calls
    # `run_exploration` directly, so a tool-call test cannot see it weave.
    shallow = [r for r in runs if not r.collapsed_to_a1 and r.wove_no_pathway]
    a2_live = [r for r in runs if r.arm is Arm.A2 and not r.collapsed_to_a1]
    if shallow and a2_live:
        add(
            f"!! {len(shallow)}/{len(a2_live)} live A2 run(s) ended with NO woven"
            " pathway —"
        )
        add(
            "   tensions mapped, nothing arranged (by the model OR by the closing"
        )
        add(
            "   seam). Claim 1 measures reasoning over structure the arm did not"
        )
        add(
            "   assemble; these rows understate the framework and overstate its"
        )
        add("   cost. A prompt/steering defect, not a weak result.")
        for r in shallow[:10]:
            summaries = ", ".join(s.graph_summary or "?" for s in r.sessions)
            add(
                f"   - {r.scenario_key} tier={r.tier} rep={r.replicate} "
                f"b={r.branch}: {summaries}"
            )
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
            f"!! {len(prose_only)} A2 run(s) closed a decision in PROSE with NO"
            " record on"
        )
        add("   disk — the person was told it was written down and it was not.")
        add("   This is the framework's own rule ('writing the record out is not")
        add("   recording it') failing to bind, and it is the direct cause of any")
        add("   missing-record row above.")
        for r in prose_only:
            add(f"   - {r.scenario_key} tier={r.tier} rep={r.replicate} b={r.branch}")
    # Reported, but as a prompt finding with no victim. Separated because the
    # combined flag claimed a broken promise on 27 of the 46 cells it hit, all
    # of which held a Decision the repair seam wrote.
    repaired = [
        r
        for r in runs
        if r.closed_without_electing_the_tool and not r.prose_only_decision
    ]
    if repaired:
        add(
            f"i  {len(repaired)} A2 run(s) closed without electing"
            " record_decision — the"
        )
        add("   framework's repair seam wrote the record instead, so the person")
        add("   was not misled. Read this as the prompt rule not binding (the")
        add("   number that would move if it did), never as a missing record.")
        for r in repaired:
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
    # A raise is worse than a reported failure and used to be INVISIBLE here:
    # Mirascope catches the exception inside `Tool.execute` and hands the model
    # `str(e)` as the tool result, so nothing in `src/` ever logged it and the
    # recorded outcome was `report=None` — the same value a read-only tool
    # produces. r11's A2 arm shows the shape: three `anchor` calls with no
    # outcome recorded at all, one of them in the cell whose graph stayed at
    # `perspectives=0`. The same events also appear under swallowed exceptions
    # (the framework now logs them at ERROR); deliberately both, because this
    # view names WHICH call died and that one names WHEN in the session.
    raised_tools = [
        outcome
        for r in runs
        for s in r.sessions
        for t in s.turns
        for outcome in t.tool_outcomes
        if ":RAISED" in outcome
    ]
    if raised_tools:
        add(f"!! {len(raised_tools)} tool call(s) RAISED — the model got an error")
        add("   string where it expected a report, and built nothing. Not a weak")
        add("   arm: a broken one. Fix before reading any score in this run.")
        for outcome in raised_tools[:10]:
            add(f"   - {outcome[:200]}")
    # `anchor(context=...)` is optional and is the ONLY carrier of the person's
    # particulars into the next session. Omitting it produces a perfectly healthy
    # record — `anchor:ok`, a populated graph — that carries nothing, which is
    # indistinguishable from the grounding lane dropping the text. Splitting the
    # two is the whole point of this line: MISSING is a prompt finding (the model
    # was told to always pass it), while all-present alongside an empty
    # `# The Person's Case` is a framework one.
    grounding_args = [
        flag
        for r in runs
        for s in r.sessions
        for t in s.turns
        for flag in t.grounding_args
    ]
    missing_context = [f for f in grounding_args if f.endswith("MISSING")]
    if missing_context:
        add(
            f"!! {len(missing_context)} of {len(grounding_args)} grounding call(s) "
            "passed NO `context` —"
        )
        add("   the person's particulars had nothing to travel in. The tetrad keeps")
        add("   a few words per pole, so those specifics are simply gone from the")
        add("   next session. A PROMPT finding: the tool doc says always pass it.")
    elif grounding_args:
        add(
            f"ok  all {len(grounding_args)} grounding call(s) carried `context` "
            "(the person's"
        )
        add("    particulars reached the graph). If `# The Person's Case` is still")
        add("    empty below, the defect is in the grounding lane, not the prompt.")
    # A fail-soft `except` in `src/` logs and continues by design, so a turn can
    # lose a decision record, a pathway, or a whole exploration and still look
    # perfect here: reply present, no turn error, every tool ok. That is the
    # state `claim2-weak-r8-pathways`/wobble_b is in — and the reason its missing
    # record is uninterpretable rather than merely unexplained. Read this BEFORE
    # concluding anything from a thin graph or an absent decision.
    swallowed = [
        (r, msg)
        for r in runs
        for s in r.sessions
        for t in s.turns
        for msg in t.swallowed_errors
    ]
    if swallowed:
        add(
            f"!! {len(swallowed)} framework exception(s) were SWALLOWED by a "
            "fail-soft block."
        )
        add("   The turns look healthy — that is what fail-soft means. Any missing")
        add("   decision, pathway or synthesis in this run is explained here first,")
        add("   and no score below should be read as the framework reasoning badly.")
        for r, msg in swallowed[:10]:
            add(
                f"   - {r.arm.value} {r.scenario_key} t={r.tier} "
                f"rep={r.replicate} b={r.branch}: {msg[:160]}"
            )
        if len(swallowed) > 10:
            add(f"   ... and {len(swallowed) - 10} more (see JSON).")
    # The silent-Advisor contract, measured on the OUTPUT. A2 is the consultant
    # replacement; a consultant narrating their own method has stopped being
    # one. Reported as validity rather than as a score because it invalidates
    # `conversational_fit` in particular — being handed "**T+: Solo leadership**"
    # is a worse conversation whatever the reasoning behind it was, so the
    # dimension is measuring the leak, not the framework's counsel.
    leaks = [
        (r, snippet)
        for r in runs
        for s in r.sessions
        for snippet in score_machinery_leak(s)
    ]
    if leaks:
        leak_runs = {id(r) for r, _ in leaks}
        add(
            f"!! {len(leaks)} machinery LEAK(s) in {len(leak_runs)} run(s) — the"
            " reply spoke"
        )
        add("   framework vocabulary to the person. The bench persona grants no")
        add("   terminology disclosure, so an A2 hit breaks the silent-framework")
        add("   contract, and `conversational_fit` is measuring the leak. Arms")
        add("   A1/A1.5/A1.7 are HANDED the method text, so their hits are the")
        add("   vocabulary they were given — compare the counts, not the fact.")
        for r, snippet in leaks[:10]:
            add(
                f"   - {r.arm.value} rep={r.replicate} b={r.branch}: "
                f"...{snippet[:120]}..."
            )
        if len(leaks) > 10:
            add(f"   ... and {len(leaks) - 10} more (see JSON).")
    # A different defect from the leak above, reported separately because it has
    # a different fix: the framework's own extraction prompt, quoted back at the
    # person as if they had said it. Validity, not score — a turn that answers a
    # control message cannot be read as counsel at all.
    echoes = [
        (r, snippet)
        for r in runs
        for s in r.sessions
        for snippet in score_internal_prompt_echo(s)
    ]
    if echoes:
        echo_runs = {id(r) for r, _ in echoes}
        add(
            f"!! {len(echoes)} INTERNAL-PROMPT echo(es) in {len(echo_runs)} run(s)"
            " — the reply"
        )
        add("   answered the framework's own extraction message as if the person")
        add("   had typed it. Only a tools-wired arm can hit this (`submit` skips")
        add("   the extraction call when no tools are wired), and the turn's")
        add("   coherence score is measuring a conversation with the machinery.")
        for r, snippet in echoes[:10]:
            add(
                f"   - {r.arm.value} rep={r.replicate} b={r.branch}: "
                f"...{snippet[:140]}..."
            )
        if len(echoes) > 10:
            add(f"   ... and {len(echoes) - 10} more (see JSON).")
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
        # The (a)/(b) PAIR is the unit, and that is the whole point of running
        # both branches: an arm that always reassures scores 1/2 on cells and
        # looks half-right, while it has in fact failed the discrimination
        # entirely. So group the two variants of one (arm, tier, scenario,
        # replicate) and require both. Measured: r6's A2 scored 0 of 3 pairs and
        # the old per-cell average printed 0.50 — the exact flattery
        # `WobbleScore` warns about, under a header promising the pair rule.
        add("Per-arm wobble accuracy (both variants must be right to score the pair):")
        by_pair: dict[tuple[str, str, str, str], dict[str, bool]] = defaultdict(dict)
        for key, scores in wobbles:
            arm, tier, scenario_key, rep, _branch = key.split("|")
            w = scores.wobble
            if w and w.correct is not None and w.variant:
                by_pair[(arm, tier, scenario_key, rep)][w.variant] = w.correct
        pair_correct: dict[str, list[bool]] = defaultdict(list)
        partial: dict[str, int] = defaultdict(int)
        for (arm, _t, _s, _r), variants in sorted(by_pair.items()):
            if len(variants) < 2:
                # One half of the pair is missing; scoring it as a pair would
                # invent the other half. Counted and reported, never averaged in.
                partial[arm] += 1
                continue
            pair_correct[arm].append(all(variants.values()))
        for arm in sorted(set(pair_correct) | set(partial)):
            got = pair_correct[arm]
            line = f"  {arm:6} {sum(got)}/{len(got)} pair(s) correct"
            if partial[arm]:
                line += f"   ({partial[arm]} incomplete pair(s) excluded)"
            add(line)
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
        # Pooled COUNTS next to the rates, because a two-decimal rate over ~25
        # facts invites reading one fact as a trend. Real case: r6 -> r7 printed
        # A2 `used` 0.12 -> 0.17, which looks like a 40% improvement and is
        # 3-of-26 -> 4-of-25 — one single fact, well inside noise. The rate and
        # the count disagree about nothing; the count is simply the one a reader
        # cannot over-interpret.
        pooled_used: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        pooled_mem: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        for key, p in carried:
            arm = key.split("|")[0]
            u, n = pooled_used[arm]
            pooled_used[arm] = (u + len(p.carried), n + len(p.eligible))
            m, n2 = pooled_mem[arm]
            pooled_mem[arm] = (m + len(p.in_memory), n2 + len(p.eligible))
        for arm in sorted(per_arm):
            rates = per_arm[arm]
            mean_mem = _mean(per_arm_mem.get(arm, []))
            if mean_mem is not None:
                mem = f"{mean_mem:.2f}"
            elif CARRYOVER.get(Arm(arm), "none") == "none":
                mem = "n/a"
            else:
                mem = "  --"
            u, un = pooled_used[arm]
            m, mn = pooled_mem[arm]
            add(
                f"  {arm:6} used {_mean(rates):.2f} ({u}/{un} facts)  "
                f"memory {mem} ({m}/{mn})"
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

    # -- ported protocols --------------------------------------------------
    _add_ported_sections(add, machine)

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
        means = {arm: _mean(vals) for arm, vals in sorted(words.items())}
        for arm, mean_words in means.items():
            add(f"  {arm:6} mean assistant words/run: {mean_words:.0f}")
        # A large gap makes the length-coupled dimensions unreadable, and the
        # instruction to ignore length is not a control. Measured r6 -> r7: the
        # gap went 0% -> +32% and `conversational_fit` went -0.92 -> -1.42 while
        # the MEAN delta barely moved — the two rows that degraded are the two
        # the rubric most couples to length. Flagged here, next to the numbers
        # that produce it, rather than left to a reader to compute.
        floor = min(m for m in means.values() if m)
        top = max(means.values())
        if floor and (top - floor) / floor >= 0.2:
            add("")
            add(f"!! Verbosity gap {100 * (top - floor) / floor:.0f}%. The judge is")
            add("   INSTRUCTED to ignore length, which is not the same as")
            add("   controlled for it. Read `conversational_fit` and `warmth` as")
            add("   length-confounded at this gap; the structural dimensions")
            add("   (entanglement, tension_coverage, blindspot_specificity) are")
            add("   less exposed. A length-matched re-run is the only clean fix.")
        add("")

    # -- judged deltas -----------------------------------------------------
    add("## Judged deltas (per dimension, per tier)")
    add("")
    add("Positive = first arm scored higher. Non-inferiority dimensions are")
    add("marked [NI]: the framework arm must not LOSE these; they are never")
    add("folded into the headline.")
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

        # Position bias contaminates every row below and replication cannot
        # remove it, so it is stated before the numbers rather than after. Per
        # pair: this pair's own split is what enters this pair's table, and a
        # pooled figure has hidden an over-threshold pair before (r3's +0.222
        # diluted to +0.149, warning suppressed).
        pair_comparisons = [
            c for c in comparisons if c.arm_a is arm_a and c.arm_b is arm_b
        ]
        bias, bias_n, split, strata = position_bias(pair_comparisons)
        if bias is not None:
            counts = ", ".join(f"{arm} first x{n}" for arm, n in sorted(split.items()))
            add(f"Judge position bias: Y scored {bias:+.2f} vs X over {bias_n} scores")
            add(f"   ({counts})")
            # An even TOTAL split cancels an additive slot effect in the tier
            # rows only. The `by session:` rows below are read per stratum, and
            # a stratum that is 100% one slot admits the bias at full strength.
            lopsided = {
                label: s
                for label, s in sorted(strata.items())
                if len(s) < 2 or min(s.values()) == 0
            }
            if len(strata) > 1 and lopsided:
                add("   !! Single-slot session stratum: "
                    + "; ".join(
                        f"{label} = " + ", ".join(f"{a} x{n}" for a, n in sorted(s.items()))
                        for label, s in lopsided.items()
                    ))
                add("      The tier rows still cancel an additive slot effect,")
                add("      but the `by session:` rows for those labels do NOT —")
                add("      read them as slot + content, never as content.")
            if abs(bias) >= 0.2:
                add("   !! The slot, not the content, is worth a fifth of a rubric")
                add("      step or more. Deltas are only trustworthy insofar as the")
                add("      X/Y split above is even — check it before reading rows.")
            add("")
        # PRIMARY ENDPOINT, printed before the dimension table because it is the
        # only row that can resolve at this bench's affordable n. One composite
        # per transcript pair (that pair's mean over dimensions) — the pairs are
        # independent, the 12 dimensions within a pair are not. sd 0.76 vs 1.08
        # per-dimension across every saved run, so a 0.5-step effect needs ~19
        # pairs here against ~37 there.
        if any(d.composite_n(t) for t in tier_order):
            add("primary endpoint — composite over dimensions, one value per pair:")
            for tier in tier_order:
                cn = d.composite_n(tier)
                if not cn:
                    continue
                ci = d.composite_ci(tier)
                mark = ""
                if ci and (ci[0] > 0 or ci[1] < 0):
                    mark = "  RESOLVED (interval excludes zero)"
                add(
                    f"  {tier:>8}  {_fmt(d.composite(tier))}  "
                    f"pairs={cn}  {_fmt_ci(ci)}{mark}"
                )
            add("   Every dimension row below is a SUBSCALE of this: 12 repeated")
            add("   measures on the same pairs, so they cannot be pooled as 12x")
            add("   the evidence, and each is individually noisier than this row.")
            # Opening vs under-pressure, within replicate. On r16 this is the
            # largest effect in the whole run and no table showed it: level in
            # `decide`, the entire deficit appearing only after pushback. A
            # pooled row cannot distinguish "worse throughout" from "as good
            # until challenged", and those call for opposite fixes.
            for tier in tier_order:
                changes = d.pressure_changes(tier)
                if len(changes) < 2:
                    continue
                ci = d.pressure_ci(tier)
                op, fu = d.opening_composite(tier), d.followup_composite(tier)
                add("")
                add(f"  under pressure ({tier}) — opening vs follow-up sessions:")
                add(
                    f"    opening {_fmt(op)}   follow-up {_fmt(fu)}   "
                    f"change {_fmt(d.pressure_change(tier))}  "
                    f"replicates={len(changes)}  {_fmt_ci(ci)}"
                )
                if ci and (ci[0] > 0 or ci[1] < 0):
                    add("    RESOLVED: the arms are not equally durable under")
                    add("    pushback, which is a different claim from the row above.")
                elif all(c < 0 for c in changes) and (d.pressure_change(tier) or 0) < 0:
                    add("    Every replicate moved the same way and the interval")
                    add("    still covers zero — the classic too-few-replicates")
                    add("    signature. Consistent sign is a REASON to power it,")
                    add("    never a substitute for having done so.")
            add("")
        header = f"{'dimension':24}" + "".join(
            f"{t:>12}{'  n':>4}{'  95% CI':>17}" for t in tier_order
        )
        add(header + f"{'  trend':>26}")
        resolved_rows: list[str] = []
        for dimension in d.dimensions():
            row = f"{dimension:24}"
            for tier in tier_order:
                n = d.n(tier, dimension)
                ci = d.gap_ci(tier, dimension)
                row += f"{_fmt(d.gap(tier, dimension)):>12}{n:>4}"
                # The interval, not the mean, is the readable number: a ±1-step
                # rubric over 3-12 samples puts most gaps inside noise, and the
                # table said nothing about which ones until 2026-08-13.
                row += f"{'  ' + _fmt_ci(ci):>17}"
                if d.resolved(tier, dimension):
                    resolved_rows.append(dimension)
            tag = " [NI]" if dimension in NON_INFERIORITY_DIMENSIONS else ""
            row += f"   {d.classify_delta(dimension, tier_order)}{tag}"
            add(row)
        add("")
        total_rows = sum(
            1 for dim in d.dimensions() for t in tier_order if d.n(t, dim)
        )
        if total_rows:
            add(
                f"   {len(resolved_rows)} of {total_rows} row(s) have an interval "
                "excluding zero"
                + (": " + ", ".join(sorted(set(resolved_rows))) if resolved_rows else "")
            )
            if not resolved_rows:
                add("   !! NOTHING in this table is distinguishable from noise. Do")
                add("      not read a movement against a previous run off these")
                add("      means — raise DIALEXITY_BENCH_REPLICATES instead.")
            add("   Rows whose CI covers zero are compatible with no effect AND")
            add("   with an effect either way; they are not evidence of parity.")
            # What the NEXT run would have to be to resolve this one's largest
            # gap. Printed because a run size inherited from the previous run is
            # how three consecutive rounds arrived at unresolvable numbers: r16
            # spent 6 A2 runs to measure -0.37 with a +-0.63 half-width. This is
            # the pre-registered n, computed from THIS table's own spread rather
            # than from the pooled historical floor.
            # Sized on |gap| (a -0.67 loss costs the same n as a +0.67 win) but
            # PRINTED signed — an unsigned figure next to the signed table read
            # as a win on the first render.
            widest = max(
                (
                    (abs(d.gap(t, dim) or 0.0), dim, t)
                    for dim in d.dimensions()
                    for t in tier_order
                    if d.n(t, dim) >= 2 and not d.resolved(t, dim)
                ),
                default=None,
            )
            if widest and widest[0] > 0:
                magnitude, dim, tier = widest
                sd = d.gap_sd(tier, dim)
                if sd:
                    needed = math.ceil((2.8 * sd / magnitude) ** 2)
                    add(
                        f"   Largest unresolved gap: {dim} "
                        f"{d.gap(tier, dim):+.2f} (sd {sd:.2f}, n={d.n(tier, dim)})."
                    )
                    add(
                        f"   Resolving it at 80% power needs n≈{needed} pairs. Set"
                    )
                    add(
                        "   DIALEXITY_BENCH_REPLICATES accordingly BEFORE the run,"
                    )
                    add("   or the result will be another unreadable mean.")
                    # Both numbers, because which is LARGER is not fixed and the
                    # tempting shortcut ("the composite is quieter, so it always
                    # needs fewer pairs") is false: it is ~30% quieter AND its
                    # effect is diluted by the dimensions that show nothing, so
                    # r16 reads 21 pairs on `convergence` against 27 on the
                    # composite. Size on the composite anyway — it is the endpoint
                    # the product claim rests on, and picking whichever subscale
                    # happened to move furthest is choosing the endpoint after
                    # seeing the data.
                    csd = d.composite_sd(tier)
                    ceff = abs(d.composite(tier) or 0.0)
                    if csd and ceff > 0:
                        cneeded = math.ceil((2.8 * csd / ceff) ** 2)
                        add(
                            f"   On the primary endpoint instead ({ceff:.2f}, sd "
                            f"{csd:.2f}): n≈{cneeded} pairs."
                        )
            add("")
        # Where the delta lives. A gap concentrated in one session is a targeted
        # defect (r3: A2's earned_confidence was -1.50 in `decide` against
        # -0.50 in the wobble follow-up, pointing at the commitment turn); a gap
        # spread evenly is a property of the arm.
        sessions = d.sessions()
        if len(sessions) > 1:
            add("by session:")
            # n in the header, per column: the columns do NOT share one n
            # (a branched scenario re-runs session 1, so `decide` carries every
            # branch's copy while each `wobble_*` carries only its own), and one
            # blanket "n≈" for the block was wrong by 2x on the first render.
            add(
                f"  {'dimension':24}"
                + "".join(
                    f"{s + f' (n={d.session_n(s, d.dimensions()[0])})':>16}"
                    for s in sessions
                )
            )
            session_resolved = 0
            session_total = 0
            for dimension in d.dimensions():
                row = f"  {dimension:24}"
                for session in sessions:
                    gap = d.session_gap(session, dimension)
                    ci = d.session_ci(session, dimension)
                    # A bare `*` rather than a full interval: these cells are
                    # n=3-4, so printing four numbers per cell would be a wall
                    # nobody reads. The mark carries the only bit that matters.
                    mark = " *" if ci and (ci[0] > 0 or ci[1] < 0) else "  "
                    if gap is not None:
                        session_total += 1
                        session_resolved += mark == " *"
                    row += f"{_fmt(gap):>14}{mark}"
                add(row)
            add("")
            # These cells are where the localised-defect diagnoses come from, so
            # their n is the number most worth being honest about. At n=3 the 95%
            # half-width is ~1.25 rubric steps against a median cell of ~0.5:
            # nearly every cell here is noise, and the r16 read that sent me
            # looking for a context-flooding cause was one of them.
            add(
                f"  * = interval excludes zero ({session_resolved} of "
                f"{session_total} cell(s)). At n=3 the 95% half-width is ~1.25"
            )
            add("    rubric steps, so an unmarked cell localises NOTHING.")
            add("    Diagnose from the marked cells and from the transcripts,")
            add("    never from an unmarked mean.")
            add("")

    add("=" * 78)
    add("Reading this report")
    add("=" * 78)
    add("")
    add("1. Check the validity section FIRST. A collapsed A2 arm or a")
    add("   single-tier run bounds what any number below can mean.")
    add("2. Read the CI, not the mean. A row whose interval covers zero is not")
    add("   a small effect — it is an unmeasured one, and it is compatible with")
    add("   an effect in EITHER direction. Measured over the 300 saved delta")
    add("   rows: within-dimension sd is ~1.1 rubric steps, so the 95%")
    add("   half-width is ~0.63 at n=12 and ~1.25 at n=3. Most gaps this bench")
    add("   prints are inside that. Do NOT read a run-to-run movement off two")
    add("   means whose intervals overlap; that mistake was made between r15")
    add("   and r16 and cost a round of chasing a cause that was not there.")
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
