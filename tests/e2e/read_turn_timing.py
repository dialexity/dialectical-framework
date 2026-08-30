"""Per-turn timing for one or more stems, side by side.

The archive's timing stems are comparable only when run in the same shape
(`timing-check-building`'s: A2 / weak / cofounder_equity / both branches / 1
replicate), so this reads whatever stems you name and prints them as columns
rather than pooling them. Pooling stems of different shapes is exactly the
confound `rounds.md` flags on the session-wall row.

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


def _stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    turns = _turns(runs)

    def col(key: str) -> list[float]:
        return [float(t.get(key, 0.0) or 0.0) for t in turns]

    durations = col("duration_s")
    replies = col("reply_path_s")
    offs = col("off_path_s")
    renders = col("context_render_s")
    tools = [_tool_total(t) for t in turns]
    # By the ABSENCE of an entry, not by a zero total: `record_decision:0.0s` is
    # a real call that rounded to nothing, and testing the total would file its
    # turn as tool-free — quietly contaminating the one comparison below that is
    # supposed to isolate a bare generation.
    called = [bool(t.get("tool_seconds")) for t in turns]
    closes = sum(
        1 for d, r, o in zip(durations, replies, offs)
        if abs(d - (r + o)) <= _ROUNDING_S
    )
    tool_free = [r for r, c in zip(replies, called) if not c]
    return {
        "turns": len(turns),
        "median turn": statistics.median(durations) if durations else 0.0,
        "median reply path": statistics.median(replies) if replies else 0.0,
        "median off path": statistics.median(offs) if offs else 0.0,
        "median context_render": statistics.median(renders) if renders else 0.0,
        "worst turn": max(durations) if durations else 0.0,
        "worst reply path": max(replies) if replies else 0.0,
        "worst off path": max(offs) if offs else 0.0,
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
        "tool calls": sum(len(t.get("tool_seconds") or []) for t in turns),
        "turns with a tool call": sum(called),
        "tool seconds, total": sum(tools),
        "median reply path, tool-free": statistics.median(tool_free or [0.0]),
        "worst reply path, tool-free": max(tool_free or [0.0]),
        "arithmetic closes": f"{closes}/{len(turns)}",
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
