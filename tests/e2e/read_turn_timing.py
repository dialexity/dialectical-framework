"""Per-turn timing for one or more stems, side by side.

The archive's timing stems are comparable only when run in the same shape
(`timing-check-building`'s: A2 / weak / cofounder_equity / both branches / 1
replicate), so this reads whatever stems you name and prints them as columns
rather than pooling them. Pooling stems of different shapes is exactly the
confound `rounds.md` flags on the session-wall row.

**It does pool ARMS within a stem, and that is a live limit, not a bug you are
seeing for the first time.** A stem holding two arms reports one median over
both, so a field that only one arm can populate reads as if the whole stem were
lukewarm on it: `r26-latency-price` prints `median context_render 0.00` over 128
turns — all 128 record the field, so this is NOT the empty-sample defect the
`not recorded` marker below covers — because 64 of them are A1.7, which renders
no dialectical context and truthfully spent 0.0s on it, and the median lands on
the boundary between the arms. Read a mixed-arm stem's medians as a mixture, or
name a single-arm stem. Splitting the columns by arm would be the real fix and
would change every figure this file has published, so it has not been made.

    poetry run python tests/e2e/read_turn_timing.py timing-after-audit-gather \
        timing-after-one-round

Medians, not means: every one of these distributions has a tail that a mean
reports as if it were the ordinary turn.
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


def _tool_total(turn: dict[str, Any]) -> float:
    """`tool_seconds` entries look like `anchor:34.5s` — colon, and a unit.

    Parsed wrong ("name=seconds"), every entry raises and every turn reads as
    tool-free, which silently turns the tool-free comparison below into a copy
    of the overall median. Validated against `rounds.md`'s published anchors.
    """
    total = 0.0
    for entry in turn.get("tool_seconds", []) or []:
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


def _stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    turns = _turns(runs)
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
    return {
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
        "arithmetic closes": f"{closes}/{len(checkable)}",
    }


def main(stems: list[str]) -> None:
    if not stems:
        raise SystemExit(__doc__)
    columns = {stem: _stats(_runs(stem)) for stem in stems}
    keys = list(next(iter(columns.values())).keys())
    width = max(len(k) for k in keys) + 2
    header = "quantity".ljust(width) + "".join(s.rjust(30) for s in stems)
    print(header)
    print("-" * len(header))
    for key in keys:
        row = key.ljust(width)
        for stem in stems:
            value = columns[stem][key]
            cell = f"{value:.2f}" if isinstance(value, float) else str(value)
            row += cell.rjust(30)
        print(row)


if __name__ == "__main__":
    main(sys.argv[1:])
