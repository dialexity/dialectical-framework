"""Per-turn timing for one or more stems, side by side.

The archive's timing stems are comparable only when run in the same shape
(`timing-check-building`'s: A2 / weak / cofounder_equity / both branches / 1
replicate), so this reads whatever stems you name and prints them as columns
rather than pooling them. Pooling stems of different shapes is exactly the
confound `rounds.md` flags on the session-wall row.

**It pools ARMS within a stem unless you ask it not to.** A stem holding two arms
reports one median over both, so a field only one arm can populate reads as if
the whole stem were lukewarm on it: `r26-latency-price` prints `median
context_render 0.00` over 128 turns — all 128 record the field, so this is NOT
the empty-sample defect the `not recorded` marker below covers — because 64 of
them are A1.7, which renders no dialectical context and truthfully spent 0.0s on
it, and the median lands on the boundary between the arms.

`--by-arm` splits the columns, which is what this file used to say was "the real
fix" and decline to make on the grounds that it "would change every figure this
file has published". It does not have to: the split is OPT-IN and the pooled
column is untouched, so every published figure still reproduces from the same
command that produced it. What DID change is that the pooled column now prints
an `arms present` row, because the actual defect was never the pooling — it was
that a mixture did not say it was one, leaving the reader to know which stems are
mixed from somewhere other than the table.

**Use `--by-arm` for anything comparing what an arm COSTS.** A pooled median over
two arms whose latencies differ by design answers no question anyone has: the
whole point of the ladder is that the arms are different, so their mixture
describes no assistant that exists.

    poetry run python tests/e2e/read_turn_timing.py timing-after-audit-gather \
        timing-after-one-round
    poetry run python tests/e2e/read_turn_timing.py --by-arm r26-latency-price

Medians, not means: every one of these distributions has a tail that a mean
reports as if it were the ordinary turn.

WHAT THE SPLIT SHOWED, THE FIRST TIME IT WAS RUN (2026-09-11, no new provider spend)
====================================================================================
`r26-latency-price`, 64 A1.7 turns beside 64 A2 turns, previously readable only as
one pooled column:

                            A1.7        A2
    median turn             6.15s     22.85s     3.7x
    worst turn             12.30s   1012.40s      82x
    median reply, tool-free 6.15s     16.80s     2.7x
    worst reply, tool-free 12.10s    645.70s
    cell wall             742.30s   7668.70s    10.3x
    tool calls                  0         25

Pooled, all of that read as `median turn 11.50` — a figure describing neither arm.

**The tail is the UX problem, not the median.** A1.7's worst turn is 12.3s, and a
bounded worst case is most of what "snappy" means; 22.85s against 6.15s is a real
but survivable difference, while 1012s is a different product. Two things follow
that the pooled column could not show. A2 is 2.7x slower even on turns where it
calls NO tool, so part of its cost is prompt shape rather than work. And its worst
TOOL-FREE turn is 645.7s — a turn that elected nothing and still took 10.7
minutes, which `TurnTiming.generation_retry_seconds` attributes in prose to a
retry ladder but which **this stem cannot confirm, because it predates
`retry_seconds`** (152 of the archive's 184 timed turns do). Hence the retry rows
below, and hence their `not recorded`: whether A2's tail is depth or a retry
pathology is the question the UX arc turns on, and no archived stem can answer it
yet. A2 stems that DO record retry (`timing-after-one-round`, 16 turns) put 20.0s
of waste entirely in tools and 0.00s in generation.

`timing-instrumentation-check` agrees in direction at n=4 per arm: A1 4.00s vs A2
13.10s median turn.

**The ladder rung this cannot speak to is A1.5** — the pre-built graph dumped as
static text, i.e. the arm that has the framework's structure with no live tool
call. It is the obvious candidate for "snappy and deep" and NO stem in the archive
carries timing for it. That is a gap in the data, not a finding about the arm.

Checked before trying to close that gap, and it is wider than "no timing": across
43 stems and 488 archived cells the arms present are A0 (8), A1 (105), A1.7 (173)
and A2 (202). **A1.5 has never been run at all.** It is `opt-in` in `DEFAULT_ARMS`
because it costs a full Advisor run just to make its context, and nothing has ever
opted in. So its code path had never executed either — which is why the three
`static context` rows below exist, and why the runner now shouts when a build
comes back empty: an unexercised path producing `""` would have handed this reader
64 A1 turns under an A1.5 heading, and every row here would have been perfectly
accurate about the wrong arm.

A1.5's build is reported SEPARATELY from every other row and never folded into
`cell wall`, because it is the arm's entire premise: the depth is paid for before
the conversation starts. A per-turn latency for this arm quoted without the build
beside it is not a cheaper A2, it is the same work with the bill hidden.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).parent / "results"


def _runs(stem: str) -> list[dict[str, Any]]:
    path = RESULTS / f"{stem}-runs.json"
    if not path.exists():
        raise SystemExit(f"no such stem: {path}")
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, list) else payload.get("runs", [])


def _turns(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every turn of every session of every cell."""
    turns: list[dict[str, Any]] = []
    for run in runs:
        for session in run.get("sessions", []) or []:
            turns.extend(session.get("turns", []) or [])
        turns.extend(run.get("turns", []) or [])
    return turns


#: `arm` is recorded on the RUN, never on the turn, so an arm split has to filter
#: runs and not turns. Doing it the other way round would need the turn records to
#: carry something they do not have, and the failure would be silent: every turn
#: would read as `None` and the split would print one column labelled "unknown".
_UNKNOWN_ARM = "unknown"


def _arm_label(run: dict[str, Any]) -> str:
    """The arm as the ARCHIVE spells it, whichever way the record reached us.

    `RunRecord.arm` is an `Arm` enum, and the two ways this reader is fed disagree
    about it: a JSON file on disk carries `"A1.7"`, while `model_dump()` (what the
    tests pass) carries the enum member, whose `str()` is `"Arm.A1_7"`. Taking
    `.value` first normalises both. Without it the split still "works" — it just
    labels its columns with a Python repr and no longer matches the arm names in
    every report and every row of `rounds.md`.
    """
    arm = run.get("arm")
    return str(getattr(arm, "value", arm) or _UNKNOWN_ARM)


def _arms(runs: list[dict[str, Any]]) -> list[str]:
    """Arms present, in ladder order where recognised.

    Sorted by the ladder rather than alphabetically, because `A1.5` < `A1.7` <
    `A2` is the order the ablation means and `sorted()` on the raw strings gets
    that right only by accident of the labels chosen.
    """
    present = {_arm_label(r) for r in runs}
    ladder = ["A0", "A1", "A1.5", "A1.7", "A2"]
    known = [a for a in ladder if a in present]
    return known + sorted(present - set(known))


def _with_arm(runs: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    return [r for r in runs if _arm_label(r) == arm]


def _builds(runs: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """A1.5's static-context builds, keyed by the (scenario, tier) each serves.

    One build serves every A1.5 cell of a (scenario, tier), and each of those
    cells carries a COPY of its provenance, seconds and size. Summing the column
    would therefore multiply one build by the replicate count — 4 replicates x 2
    branches reporting an 8x bill for work done once. Keying by the build's own
    identity is what makes the sum honest, and it is keyed on those two fields
    rather than deduplicated by value because two builds of different scenarios
    that happened to take the same rounded seconds would collapse into one.

    Empty for every other arm, and for A1.5 cells predating the fields — which,
    when this was written, was all of them, there being none.
    """
    builds: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        if run.get("static_context_build_s") is None:
            continue
        key = (str(run.get("scenario_key")), str(run.get("tier")))
        builds[key] = {
            "seconds": float(run["static_context_build_s"]),
            "chars": run.get("static_context_chars"),
            "provenance": run.get("static_context_provenance"),
        }
    return builds


def _tool_total(turn: dict[str, Any], key: str = "tool_seconds") -> float:
    """`tool_seconds` entries look like `anchor:34.5s` — colon, and a unit.

    Parsed wrong ("name=seconds"), every entry raises and every turn reads as
    tool-free, which silently turns the tool-free comparison below into a copy
    of the overall median. Validated against `rounds.md`'s published anchors.

    `key` also serves `tool_retry_seconds`, which `format_retry_rounds` writes in
    the SAME format and in the same order — one parser for both, because two
    would be two places for the format to drift out from under a reader.
    """
    total = 0.0
    for entry in turn.get(key, []) or []:
        _, _, seconds = str(entry).rpartition(":")
        try:
            total += float(seconds.rstrip("s"))
        except ValueError:
            continue
    return total


#: Timings are stored to one decimal, so three independently rounded values can
#: disagree by more than a hair. Observed max residual across both published
#: stems is 0.2s, and both are reported as closing on 16/16 — a tighter bar here
#: would manufacture a disagreement with the board it is meant to reproduce.
_ROUNDING_S = 0.3

#: What a statistic prints when its sample is EMPTY, instead of 0.0. A string on
#: purpose: `main()` formats floats and passes everything else through, so this
#: cannot be mistaken for a reading, cannot be averaged by eye against the column
#: beside it, and cannot be quoted into `rounds.md` as a measurement.
#:
#: It is not a cosmetic choice. `timing-check-building` carries `context_render_s`
#: on 0 of its 16 turns and `timing-after-audit-gather` on 16 of 16, so the
#: side-by-side this file exists for printed `0.00` against `0.19` — a stem that
#: predates the field reading as a stem where the refresh was free, and the newer
#: build reading as the one that introduced a cost. Same defect as the probe's
#: "fired on 72% of turns"; this is the row-wise version of it.
_NOT_RECORDED = "not recorded"


def _median(values: list[float]) -> float | str:
    return statistics.median(values) if values else _NOT_RECORDED


def _worst(values: list[float]) -> float | str:
    return max(values) if values else _NOT_RECORDED


def _total(values: list[float], measured: bool = True) -> float | str:
    """A sum, or `_NOT_RECORDED` when nothing was measured.

    `sum([])` is `0`, and for retry a zero is the exact lie this marker exists to
    prevent: "this stem ran clean" against a stem that predates the fields. Note
    the asymmetry with `tool seconds, total`, which prints a real `0` and should —
    an arm with no tools truthfully spent no time in them, so there the zero is
    the measurement. `measured` lets a caller keep a genuine zero when the sample
    is empty for a reason that IS the finding.
    """
    if not values and not measured:
        return _NOT_RECORDED
    return sum(values)


def _stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    turns = _turns(runs)
    builds = _builds(runs)
    # A turn whose split is `None` published no timing at all — it crashed
    # before reporting, or its arm does not time itself. Those turns are DROPPED
    # from every split column below rather than read as zeros, because a zero
    # here is a claim ("this turn was instant") and the turns that fail are
    # disproportionately the expensive ones. `duration_s` is still real on them,
    # so `median turn` keeps every turn and only the splits shrink — which is
    # why `untimed turns (dropped)` is printed rather than left to be inferred
    # from a row that no longer adds up.
    timed = [t for t in turns if t.get("reply_path_s") is not None]
    untimed = len(turns) - len(timed)

    def col(key: str, rows: list[dict[str, Any]] | None = None) -> list[float]:
        # `if v is not None`, NOT `or 0.0`: falsy-coercion would put the dropped
        # turns straight back in as zeros, which is the bug this guard exists
        # for, and would also flatten a genuine 0.0 into the same bucket.
        return [
            float(t[key])
            for t in (timed if rows is None else rows)
            if t.get(key) is not None
        ]

    durations = col("duration_s", turns)
    replies = col("reply_path_s")
    offs = col("off_path_s")
    renders = col("context_render_s")
    # Sparser than its neighbours even among timed turns — an awaited turn has
    # no first delta — so it gets its own count rather than sharing `timed`.
    deltas = col("first_delta_s")
    # Over `timed`, like the split columns, though the honest reason is narrower
    # than it looks: an untimed turn arrives with an empty `tool_seconds` (the
    # driver discards the rounds the facilitator DID observe when a turn crashes),
    # so including it would change none of the three count rows below — they come
    # out identical either way, today. What the scoping actually protects is
    # `median reply path, tool-free`, whose denominator would otherwise gain a
    # crashed eight-tool turn filed as a bare generation. Scoped anyway, and
    # uniformly, so the rows share one population: a table where three rows count
    # every turn and one counts a subset invites exactly the arithmetic nobody
    # should be doing across it.
    tools = [_tool_total(t) for t in timed]
    # By the ABSENCE of an entry, not by a zero total: `record_decision:0.0s` is
    # a real call that rounded to nothing, and testing the total would file its
    # turn as tool-free — quietly contaminating the one comparison below that is
    # supposed to isolate a bare generation.
    called = [bool(t.get("tool_seconds")) for t in timed]
    # Over the turns that published BOTH halves of the identity, and reported as
    # a fraction of THOSE: an untimed turn cannot close or fail to close, and
    # counting it as a failure would read as a broken invariant rather than a
    # missing measurement. `off_path_s or 0.0` would be worse than the usual
    # zero-fill here — it makes the check EASIER to pass for a record missing the
    # field, so a reader would be told the invariant held on a turn where two of
    # its three terms were never measured.
    checkable = [
        t for t in timed
        if t.get("off_path_s") is not None and t.get("duration_s") is not None
    ]
    closes = sum(
        1 for t in checkable
        if abs(
            float(t["duration_s"])
            - (float(t["reply_path_s"]) + float(t["off_path_s"]))
        ) <= _ROUNDING_S
    )
    tool_free = [
        float(t["reply_path_s"]) for t in timed if not t.get("tool_seconds")
    ]
    # Retry gets its OWN denominator, and it is not pedantry: `TurnRecord` records
    # that 152 of the archive's 184 timed turns predate these fields, so pooling
    # them against `timed` would report a stem as retry-free when it simply never
    # measured retry. `or 0.0` is forbidden here for the same reason — it is the
    # coercion the record's own comment names as reinstating the bug in the reader.
    retried = [t for t in timed if t.get("retry_seconds") is not None]
    retry_waste = [float(t["retry_seconds"]) for t in retried]
    # Of that waste, how much was the model's own generation rather than a tool
    # laddering — `TurnTiming.generation_retry_seconds`, recomputed here because
    # the archive stores the two halves and not the difference. This is the row
    # that separates "the deep arm is slow because it thinks" from "the deep arm
    # is slow because it failed and waited", which no other row can distinguish.
    generation_waste = [
        max(0.0, float(t["retry_seconds"]) - _tool_total(t, "tool_retry_seconds"))
        for t in retried
    ]
    return {
        # First row on purpose. Every figure below is a median over whatever this
        # says, and a two-arm entry here means the column describes no assistant
        # that exists — see the module docstring and `--by-arm`.
        "arms present": "+".join(_arms(runs)),
        "turns": len(turns),
        "untimed turns (dropped)": untimed,
        "median turn": _median(durations),
        "median reply path": _median(replies),
        "median off path": _median(offs),
        # Its own count row, for the same reason the probe prints its own
        # denominator: this field is younger than the archive, and 0 of 16 turns
        # carrying it is a different fact from a refresh that cost nothing.
        "turns recording context_render": len(renders),
        "median context_render": _median(renders),
        # 0 on every stem published so far: the bench calls `chat()`, which has
        # no first delta to report. Printed regardless — a blank-screen figure
        # that appears only once someone remembers to look for it is a figure
        # nobody compares across stems.
        "turns with a first delta": len(deltas),
        "median first delta": _median(deltas),
        "worst turn": _worst(durations),
        "worst reply path": _worst(replies),
        "worst off path": _worst(offs),
        # The cell's own clock, NOT the sum of its turns: a run spends time
        # between turns (simulator, setup) that no turn record covers, which is
        # why summing turns under-reports it by ~15%.
        "cell wall (run duration_s)": sum(
            float(r.get("duration_s", 0.0) or 0.0) for r in runs
        ),
        # The comparison this file exists for: a turn with no tool call is one
        # generation, so its reply path IS the prompt-shape cost with nothing
        # else in it. Mixing tool turns in hides the lever.
        # `rounds.md` quotes the CALL count ("3 tool calls against the
        # baseline's 6"); a turn may carry more than one, so both are here.
        "tool calls": sum(len(t.get("tool_seconds") or []) for t in timed),
        "turns with a tool call": sum(called),
        "tool seconds, total": sum(tools),
        # `not recorded` here means every timed turn called a tool, which is a
        # real state of a cell and NOT a zero-second generation.
        "median reply path, tool-free": _median(tool_free),
        "worst reply path, tool-free": _worst(tool_free),
        # Its own denominator, like `context_render`: `not recorded` here means the
        # stem predates the fields, which is a different fact from a stem that ran
        # clean. Most of the archive is the former.
        "turns recording retry": len(retried),
        # Every row below is `not recorded` on a stem older than the fields, never
        # 0 — see `_total`. Only the denominator above is honestly zero there.
        "turns that retried": (
            sum(1 for t in retried if (t.get("retry_count") or 0) > 0)
            if retried else _NOT_RECORDED
        ),
        "retry seconds, total": _total(retry_waste, measured=bool(retried)),
        "worst retry seconds": _worst(retry_waste),
        # The split that tells a slow reply from a failed one.
        "retry seconds in generation": _total(
            generation_waste, measured=bool(retried)
        ),
        # A1.5's bill, which no other row can carry. Every figure above is a
        # per-TURN cost, and A1.5's whole proposition is that its depth was paid
        # for before the conversation started — so its turn latency quoted alone
        # is not a cheap A2, it is an A2 with the invoice torn off. `not recorded`
        # on every other arm: they have no build, which is a different fact from a
        # build that cost nothing.
        #
        # Deliberately NOT added into `cell wall`. That row is the clock a cell
        # ran on, the build precedes every cell, and folding a shared cost into a
        # per-cell figure is how one build gets charged eight times.
        "static context builds": len(builds) or _NOT_RECORDED,
        "static context build seconds": (
            sum(b["seconds"] for b in builds.values()) if builds else _NOT_RECORDED
        ),
        "static context chars": (
            # The prefill every turn of this arm pays. Max, not sum: one build
            # per (scenario, tier), and the largest is the one that bounds a turn.
            max((b["chars"] or 0) for b in builds.values())
            if builds
            else _NOT_RECORDED
        ),
        "arithmetic closes": f"{closes}/{len(checkable)}",
    }


def main(argv: list[str]) -> None:
    by_arm = "--by-arm" in argv
    stems = [a for a in argv if not a.startswith("-")]
    unknown = [a for a in argv if a.startswith("-") and a != "--by-arm"]
    if unknown:
        raise SystemExit(f"unknown option(s): {' '.join(unknown)}\n{__doc__}")
    if not stems:
        raise SystemExit(__doc__)

    # `columns` is label -> stats. Pooled mode keeps one column per stem and the
    # label IS the stem, so the default output is what it always was.
    columns: dict[str, dict[str, Any]] = {}
    for stem in stems:
        runs = _runs(stem)
        if not by_arm:
            columns[stem] = _stats(runs)
            continue
        arms = _arms(runs)
        for arm in arms:
            # The stem prefix stays even when only one arm is present: a reader
            # comparing two stems needs to know which column came from which, and
            # a bare `A2` heading over two stems is ambiguous in exactly the way
            # the pooled column used to be.
            columns[f"{stem}:{arm}"] = _stats(_with_arm(runs, arm))

    keys = list(next(iter(columns.values())).keys())
    width = max(len(k) for k in keys) + 2
    # Was a hard 30. An arm split makes the labels longer than the stems ever
    # were, and a truncated or overflowing heading over a table of medians is how
    # a figure gets read against the wrong column.
    cell_width = max(30, max(len(label) for label in columns) + 2)
    header = "quantity".ljust(width) + "".join(
        label.rjust(cell_width) for label in columns
    )
    print(header)
    print("-" * len(header))
    for key in keys:
        row = key.ljust(width)
        for label in columns:
            value = columns[label][key]
            cell = f"{value:.2f}" if isinstance(value, float) else str(value)
            row += cell.rjust(cell_width)
        print(row)

    # Below the table rather than in it: a provenance is a sentence
    # (`perspectives=3 woven=2 ...`, or `failed: RuntimeError: ...`) and no cell
    # can hold one without truncating exactly the part that matters. It is printed
    # at all because `static context chars` says an A1.5 arm got nothing while
    # only this says WHY — a build that raised and a conversation that mapped
    # nothing both leave 0 characters and want opposite fixes.
    provenances = {}
    for stem in stems:
        for (scenario, tier), build in _builds(_runs(stem)).items():
            provenances[f"{stem} {scenario} {tier}"] = build
    if provenances:
        print("\nA1.5 static context builds:")
        for where, build in provenances.items():
            print(
                f"  {where}: {build['chars']}c in {build['seconds']:.1f}s"
                f" — {build['provenance']}"
            )


if __name__ == "__main__":
    main(sys.argv[1:])
