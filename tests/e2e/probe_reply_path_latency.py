"""Where do A2's extra 530 seconds go, and how many of them are on the reply path?

    poetry run python tests/e2e/probe_reply_path_latency.py
    poetry run python tests/e2e/probe_reply_path_latency.py ladder-return

Free — reads `duration_s` and per-turn `tool_calls` off the saved archive, calls
no model.

WHY THIS IS A DIFFERENT QUESTION FROM `probe_cell_cost.py`
=========================================================
`probe_cell_cost.py` answers "what does a cell cost" and stops at 5.1x/6.0x. That
multiplier is the right number for sizing a RUN and the wrong number for a UX
decision, because a second the person waits and a second spent after their reply
was delivered are the same second to the budget and opposite seconds to them.

The reply path is narrower than the tool list suggests, and the code says so:

- `Advisor.chat` (`advisor.py:205`) awaits `_conversation.submit(...)`, so every
  tool round the MODEL elects runs before the reply text exists. Those are
  on-path, and `TurnRecord.tool_calls` is exactly their record.
- `_repair_unrecorded_decision` runs at `advisor.py:206`, AFTER the reply — its
  own comment says "so the person's reply is never delayed by the repair". Its
  `DecisionConfirmationCheck` call and its `_ensure_pathways_before_closing` are
  therefore off-path already. Confirmed by call sites: the seam is called from
  nowhere else (`advisor.py:290`, `advisor.py:329`, both inside the repair).

So on-path cost is model-elected tool rounds; everything else is off-path or
overhead. This probe splits the archive on that line.

WHAT IT CANNOT DO, STATED UP FRONT
==================================
**`TurnRecord` has no timing field.** Timing exists only per cell
(`RunRecord.duration_s`, `models.py:490`). So this is run-level ATTRIBUTION, not
measurement: it regresses each A2 run's machinery seconds onto its tool-call
histogram. A per-tool figure here is an average marginal cost across 187 runs,
not a stopwatch reading, and two tools that nearly always co-occur cannot be told
apart no matter how many runs there are (the condition number is printed for
exactly this reason).

**That fix landed on 2026-08-26**: `TurnRecord` now carries `duration_s`,
`reply_path_s`, `off_path_s` and per-round `tool_seconds`, so any run recorded
after it reports the split instead of having it inferred. This probe prefers the
measured fields when a run has them and falls back to attribution when it does
not, because the 32 archive files that already exist never will — and the
fallback's answer to "is the 530s concentrated on the reply path or spread across
off-path work" is still worth having for them.

The two paths are labelled MEASURED and ATTRIBUTED in the output. Never average
them together.

The baseline is MEASURED, not fitted: A1 has zero tools by construction, so its
seconds-per-turn is the pure reply cost at that tier. A1.7 is reported beside it
as a cross-check but is NOT the baseline — it pays an extra `write_journal` LLM
call per session that is not a turn, which inflates its seconds-per-turn.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

E2E_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.models import Arm, RunRecord  # noqa: E402
from e2e.report import load_records  # noqa: E402

RESULTS = E2E_DIR / "results"

#: Bootstrap resamples for the per-tool intervals. Resampled over RUNS, which is
#: the independent unit here (turns inside a run share a graph and an afternoon —
#: the unit-shopping error `716d124` was committed to catch).
BOOTSTRAP = 2000

#: Tools that only READ. Kept separate in the report because a read-only round
#: still costs a full model round-trip on the reply path, so "cheap" in graph
#: terms is not cheap in latency terms — and that distinction is the whole point
#: of this probe.
READ_ONLY = frozenset({"inspect_node", "sync"})

#: Below this many observed calls, a fitted coefficient is one run's noise wearing
#: a number's clothes. `ingest` was called ONCE in 187 A2 runs and the first
#: version of this probe printed `-900s [-1511, 0]` for it, which is not a slow
#: tool but a regression with nothing to regress on. Flagged rather than dropped:
#: "we cannot say" is a finding, and a silently missing row reads as a missing
#: tool.
MIN_CALLS = 10


def _stems(needle: str | None) -> list[str]:
    return sorted(
        p.stem
        for p in RESULTS.glob("*.json")
        # `-runs.json` duplicates the same runs; including it doubles every count.
        if not p.stem.endswith(("-runs", "-rejudged"))
        and not p.stem.startswith("smoke")
        and (needle is None or needle in p.stem)
    )


def _load(stems: list[str]) -> list[RunRecord]:
    runs: list[RunRecord] = []
    for stem in stems:
        payload = load_records(RESULTS / f"{stem}.json")
        for raw in payload.get("runs", []):
            try:
                runs.append(RunRecord.model_validate(raw))
            except Exception:  # noqa: BLE001
                continue
    return runs


def _turns(run: RunRecord) -> int:
    return sum(len(s.turns) for s in run.sessions)


def _all_turns(run: RunRecord) -> list:
    return [t for s in run.sessions for t in s.turns]


def sum_tool_seconds(turn) -> float:
    """Seconds this turn spent inside tool rounds, from the recorded strings.

    Concurrent rounds are INCLUDED here, unlike the per-tool table below: the
    question there is "what does `anchor` cost", which a multi-tool round cannot
    answer, but the question here is "how much of this turn was tools", which it
    answers fine — a round's seconds are the person's wait whether one tool ran
    or three.
    """
    total = 0.0
    for entry in turn.tool_seconds:
        _, _, secs = entry.rpartition(":")
        try:
            total += float(secs.rstrip("s"))
        except ValueError:
            continue
    return total


def retry_seconds_by_round(turn) -> list[float]:
    """This turn's per-round retry waste, aligned with `turn.tool_seconds`.

    Returns zeros when `tool_retry_seconds` is absent or short, which is what
    every run archived before 2026-08-26 looks like: those runs did retry — r26
    almost certainly slept 12.5 minutes on four separate `anchor` calls — and
    nothing recorded it. Zero here means "not recorded" for them and "clean" for
    later runs, and only the run's own vintage tells the two apart. Never quote a
    working-seconds figure from a run without the field.
    """
    parsed: list[float] = []
    for entry in getattr(turn, "tool_retry_seconds", []) or []:
        _, _, secs = entry.rpartition(":")
        try:
            parsed.append(float(secs.rstrip("s")))
        except ValueError:
            parsed.append(0.0)
    parsed.extend([0.0] * max(0, len(turn.tool_seconds) - len(parsed)))
    return parsed


def _is_measured(run: RunRecord) -> bool:
    """True when this run's turns carry their own timing.

    Any turn with a non-zero `reply_path_s` is enough: the field defaults to 0.0,
    so every run archived before the field existed reads as unmeasured, and a run
    recorded after it cannot have a whole cell of zero-second turns.
    """
    return any(t.reply_path_s for t in _all_turns(run))


def _report_measured(runs: list[RunRecord]) -> None:
    """Read the split straight off the turns — no regression involved."""
    per_tier: dict[str, list[RunRecord]] = defaultdict(list)
    for run in runs:
        per_tier[run.tier].append(run)

    for tier in sorted(per_tier):
        cells = per_tier[tier]
        turns = [t for r in cells for t in _all_turns(r)]
        reply = [t.reply_path_s for t in turns]
        off = [t.off_path_s for t in turns]
        total = sum(t.duration_s for t in turns) or 1.0
        print(f"=== {tier} tier, MEASURED, n={len(cells)} runs / {len(turns)} turns ===")
        print(
            f"  median turn {statistics.median([t.duration_s for t in turns]):.1f}s"
            f"  =  reply path {statistics.median(reply):.1f}s"
            f"  +  off path {statistics.median(off):.1f}s"
        )
        print(
            f"  share of wall clock: reply path {sum(reply) / total * 100:.0f}%,"
            f" off path {sum(off) / total * 100:.0f}%,"
            f" harness overhead {(1 - (sum(reply) + sum(off)) / total) * 100:.0f}%"
        )
        # The reply path's own composition. `context_render_s` is a COMPONENT of
        # `reply_path_s`, not a third addend — printing it beside the split above
        # would otherwise read as if the arithmetic no longer closed. The residual
        # is generation plus whatever the framework does that nothing times yet,
        # which is the only honest label for it.
        rendered = [t.context_render_s for t in turns]
        if any(rendered):
            firing = sum(1 for t in rendered if t) / len(rendered) * 100
            print(
                f"  reply path composition (median): context refresh"
                f" {statistics.median(rendered):.2f}s"
                f"  +  tools {statistics.median([sum_tool_seconds(t) for t in turns]):.1f}s"
                f"  +  generation/residual"
                f" {statistics.median([t.reply_path_s - t.context_render_s - sum_tool_seconds(t) for t in turns]):.1f}s"
            )
            print(
                f"  context refresh: fired on {firing:.0f}% of turns,"
                f" {sum(rendered) / (sum(reply) or 1.0) * 100:.1f}% of all"
                f" reply-path seconds, worst turn"
                f" {max(rendered):.2f}s"
            )
        # Retry waste, reported as a share of the reply path rather than beside
        # it: it is INSIDE the tools and the generation printed above, so adding
        # it as another term would double-count the same seconds. The question it
        # answers is the one r26 could not — of the wait, how much was working?
        wasted = [getattr(t, "retry_seconds", 0.0) or 0.0 for t in turns]
        retried = [t for t in turns if (getattr(t, "retry_count", 0) or 0)]
        if any(wasted):
            in_tools = sum(sum(retry_seconds_by_round(t)) for t in turns)
            print(
                f"  retry waste: {sum(wasted) / (sum(reply) or 1.0) * 100:.0f}% of all"
                f" reply-path seconds, on {len(retried)}/{len(turns)} turns"
                f" (worst turn {max(wasted):.1f}s,"
                f" {sum(t.retry_count for t in retried)} attempts retried in total)"
            )
            print(
                f"    of which {in_tools:.0f}s inside tool rounds and"
                f" {max(0.0, sum(wasted) - in_tools):.0f}s during generation"
                " (which otherwise reads as the model thinking)"
            )
        else:
            # NOT the same claim as "these turns ran clean" for older archives.
            print(
                "  retry waste: none recorded"
                " (clean turns, or a run older than the field — see"
                " `retry_seconds_by_round`)"
            )
        # The off-path tail is the whole reason this probe exists: pre-fix, the
        # pathway weave put 127.7s and 387.7s AFTER two zero-tool replies. Report
        # the tail, never just the median — a median hid that defect for weeks.
        tail = sorted(off)[-3:]
        print(
            f"  off-path tail (3 worst turns): {[round(t, 1) for t in reversed(tail)]}"
            f"   over 60s: {sum(1 for t in off if t > 60.0)}/{len(off)} turns"
        )
        # Per-tool seconds, from single-tool rounds only. A concurrent round took
        # as long as its slowest call, so folding it in would credit every name
        # in it with the whole round.
        attributable: dict[str, list[float]] = defaultdict(list)
        working: dict[str, list[float]] = defaultdict(list)
        concurrent = 0
        for turn in turns:
            waste = retry_seconds_by_round(turn)
            for index, entry in enumerate(turn.tool_seconds):
                names, _, secs = entry.rpartition(":")
                try:
                    value = float(secs.rstrip("s"))
                except ValueError:
                    continue
                if "+" in names:
                    concurrent += 1
                    continue
                attributable[names].append(value)
                working[names].append(max(0.0, value - waste[index]))
        if attributable:
            # Two columns, because r26 proved one is misreadable: `anchor` at a
            # 282.8s median went into two write-ups as the tool's price, and the
            # working column would have said ~40s. WAITED is what the person
            # feels and what a UX decision turns on; WORKING is what the tool
            # costs and what an optimisation could move. Neither replaces the
            # other, so neither is printed alone.
            #
            # Withheld entirely on runs older than the field: there the two
            # columns would print identical numbers, which reads as "measured, no
            # waste" when it means "never looked". Those are the runs where the
            # 810s anchors actually happened.
            print("\n  Seconds per tool, from single-tool rounds (median):")
            if any(wasted):
                print(f"    {'':16}{'':11}{'waited':>8}{'working':>9}")
            for name, values in sorted(
                attributable.items(), key=lambda kv: -statistics.median(kv[1])
            ):
                flag = " [read-only]" if name in READ_ONLY else ""
                work = (
                    f"{statistics.median(working[name]):>8.1f}s"
                    if any(wasted)
                    else ""
                )
                print(
                    f"    {name:16}n={len(values):<9}"
                    f"{statistics.median(values):>8.1f}s{work}{flag}"
                )
            if not any(wasted):
                print(
                    "    (working column withheld — no run in this tier recorded"
                    " retries, so it would only echo the waited column)"
                )
        if concurrent:
            print(
                f"  ({concurrent} concurrent round(s) excluded — their seconds"
                " belong to no single tool)"
            )
        print()


def _tool_counts(run: RunRecord) -> Counter:
    counts: Counter = Counter()
    for session in run.sessions:
        for turn in session.turns:
            counts.update(turn.tool_calls)
    return counts


def _baselines(runs: list[RunRecord]) -> dict[str, dict[str, float]]:
    """Seconds per turn for the tool-free arms, per tier."""
    per_tier: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for run in runs:
        if run.arm not in (Arm.A0, Arm.A1, Arm.A1_7):
            continue
        turns = _turns(run)
        if not turns or not run.duration_s:
            continue
        per_tier[run.tier][run.arm.value].append(run.duration_s / turns)
    return {
        tier: {arm: statistics.median(v) for arm, v in arms.items()}
        for tier, arms in per_tier.items()
    }


def _fit(
    design: np.ndarray, target: np.ndarray, names: list[str]
) -> tuple[dict[str, tuple[float, float, float]], float, float]:
    """OLS with bootstrap intervals over rows (runs).

    Returns per-tool (point, lo, hi), the explained fraction of total machinery
    seconds, and the design's condition number.
    """
    point, *_ = np.linalg.lstsq(design, target, rcond=None)
    draws = np.empty((BOOTSTRAP, design.shape[1]))
    rng = np.random.default_rng(0)  # fixed: a probe must reproduce
    rows = design.shape[0]
    for i in range(BOOTSTRAP):
        idx = rng.integers(0, rows, rows)
        try:
            draws[i], *_ = np.linalg.lstsq(design[idx], target[idx], rcond=None)
        except np.linalg.LinAlgError:
            draws[i] = np.nan
    lo = np.nanpercentile(draws, 2.5, axis=0)
    hi = np.nanpercentile(draws, 97.5, axis=0)
    explained = float((design @ point).sum() / target.sum()) if target.sum() else 0.0
    condition = float(np.linalg.cond(design))
    return (
        {n: (point[j], lo[j], hi[j]) for j, n in enumerate(names)},
        explained,
        condition,
    )


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else None
    stems = _stems(needle)
    if not stems:
        print(f"no saved runs match {needle!r}")
        return 1

    runs = _load(stems)
    baselines = _baselines(runs)
    a2 = [r for r in runs if r.arm is Arm.A2 and r.duration_s and _turns(r)]
    if not a2:
        print("no A2 runs with timing")
        return 1

    measured = [r for r in a2 if _is_measured(r)]
    inferred = [r for r in a2 if not _is_measured(r)]
    print(
        f"{len(stems)} archive file(s), {len(a2)} A2 run(s) with timing"
        f" — {len(measured)} measured, {len(inferred)} attributed\n"
    )

    if measured:
        _report_measured(measured)
    if not inferred:
        print("Every run carries its own timing. Nothing left to infer.")
        return 0
    if measured:
        print(
            f"The {len(inferred)} run(s) below predate per-turn timing, so their"
            " split is\nregressed rather than read. Do not average these figures"
            " with the measured\nones above.\n"
        )

    print("Reply cost per turn, measured on the tool-free arms (median):")
    for tier in sorted(baselines):
        row = "  ".join(
            f"{arm}={secs:.0f}s" for arm, secs in sorted(baselines[tier].items())
        )
        print(f"  {tier:8}{row}")
    print("  (A1 is the baseline — zero tools. A1.7 shown for cross-check only:")
    print("   its per-session write_journal call is not a turn, so it reads high.)\n")

    by_tier: dict[str, list[RunRecord]] = defaultdict(list)
    for run in inferred:
        by_tier[run.tier].append(run)

    for tier in sorted(by_tier):
        cells = by_tier[tier]
        base = baselines.get(tier, {}).get("A1")
        if base is None:
            print(f"{tier}: no A1 baseline at this tier — skipping attribution\n")
            continue

        names = sorted({t for r in cells for t in _tool_counts(r)})
        design = np.array(
            [[_tool_counts(r).get(n, 0) for n in names] for r in cells], dtype=float
        )
        machinery = np.array(
            [r.duration_s - base * _turns(r) for r in cells], dtype=float
        )
        total = np.array([r.duration_s for r in cells], dtype=float)

        print(f"=== {tier} tier, ATTRIBUTED, n={len(cells)} A2 runs " + "=" * 12)
        print(
            f"  median run {statistics.median(total):.0f}s"
            f"  =  reply {base * statistics.median([_turns(r) for r in cells]):.0f}s"
            f"  +  machinery {statistics.median(machinery):.0f}s"
        )
        calls = statistics.median([sum(_tool_counts(r).values()) for r in cells])
        print(
            f"  median {statistics.median([_turns(r) for r in cells]):.0f} turns,"
            f" {calls:.0f} model-elected tool calls"
        )

        coeffs, explained, condition = _fit(design, machinery, names)
        observed = {n: int(design[:, j].sum()) for j, n in enumerate(names)}
        print("\n  Marginal seconds per ON-PATH tool call (bootstrap 95%):")
        for name in sorted(names, key=lambda n: -coeffs[n][0]):
            pt, lo, hi = coeffs[name]
            flags = " [read-only]" if name in READ_ONLY else ""
            if observed[name] < MIN_CALLS:
                flags += f" [only {observed[name]} call(s) — not interpretable]"
            resolves = "" if lo <= 0 <= hi else "  *"
            print(
                f"    {name:16}n={observed[name]:<5}{pt:>8.0f}s"
                f"  [{lo:>7.0f},{hi:>7.0f}]{resolves}{flags}"
            )
        print("    * = interval excludes zero")
        print(
            f"\n  On-path tool rounds explain {explained * 100:.0f}% of machinery"
            f" seconds; {(1 - explained) * 100:.0f}% is off-path or overhead."
        )
        onpath_share = explained * float(machinery.sum()) / float(total.sum())
        print(
            f"  As a share of the WHOLE run: reply"
            f" {float((total - machinery).sum()) / float(total.sum()) * 100:.0f}%,"
            f" on-path machinery {onpath_share * 100:.0f}%,"
            f" off-path/overhead"
            f" {(1 - onpath_share - float((total - machinery).sum()) / float(total.sum())) * 100:.0f}%"
        )
        print(f"  Design condition number {condition:.1f}", end="")
        print(
            " — tools co-occur, read per-tool figures as a group"
            if condition > 30
            else " — tools vary independently enough to separate"
        )
        print()

    print(
        "The figures above are attribution, not measurement: these runs predate\n"
        "per-turn timing, so the split is regressed out of cell-level duration.\n"
        "`TurnRecord` carries it directly now — re-run any lane and read the\n"
        "MEASURED block instead of quoting these."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
