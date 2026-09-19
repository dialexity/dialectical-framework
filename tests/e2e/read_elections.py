"""
read_elections — what each arm ELECTED, per stem, beside the thinking regime it ran under.

    poetry run python tests/e2e/read_elections.py consultant-latency consultant-cache thinking-off

Free: reads `results/<stem>-runs.json`. Exists because the tool-election rate is
the archive's most machine-countable endpoint and the one the thinking regime
is most likely to move: `record_decision` fired 0/6 at the weak tier, `explore`
2/6, `deepen` 0/6, and every one of those figures was measured with
`DIALEXITY_CONVERSATION_THINKING_LEVEL=medium` in the environment (`rounds.md`,
`probe-consultant-prompt-cost`). A run with the level unset is read against them
here, arm by arm.

Columns are per (stem, arm): cells, turns, the thinking level the cells recorded
(`not recorded` on stems that predate the field — which means UNKNOWN, and for
anything after 2026-09-02 in this environment most likely `medium`), tool calls
by name with the number of CELLS in which each fired, closing and deferral
outcomes, decisions on the record, and the median reply path.

Elections are counted per cell as well as per turn because a tool that fires
once in every cell and a tool that fires six times in one cell are different
facts, and "fired in N/M cells" is the shape the archive's earlier figures use.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def _runs(stem: str) -> list[dict]:
    payload = json.loads((RESULTS / f"{stem}-runs.json").read_text())
    return payload if isinstance(payload, list) else payload.get("runs", [])


def _tool_seconds(turn: dict) -> float:
    """`tool_seconds` is archived as `["anchor:30.5s", ...]`."""
    total = 0.0
    for entry in turn.get("tool_seconds") or []:
        try:
            total += float(str(entry).rsplit(":", 1)[1].rstrip("s"))
        except (IndexError, ValueError):
            continue
    return total


def _median(values: list[float]) -> str:
    values = [v for v in values if v is not None]
    return f"{statistics.median(values):.2f}" if values else "-"


def read(stems: list[str]) -> None:
    for stem in stems:
        by_arm: dict[str, list[dict]] = defaultdict(list)
        for run in _runs(stem):
            by_arm[str(run["arm"])].append(run)
        for arm, runs in sorted(by_arm.items()):
            turns = [t for r in runs for s in r["sessions"] for t in s["turns"]]
            # Raw JSON, so the one-day-old key is read here as well (the
            # RunRecord loader maps it; this reader does not go through it).
            levels = {
                r.get("conversation_thinking_level", r.get("thinking_level", "not recorded"))
                for r in runs
            }
            level = ", ".join(str(l) for l in sorted(levels, key=str))
            calls: Counter = Counter()
            cells_with: Counter = Counter()
            for r in runs:
                seen: set[str] = set()
                for s in r["sessions"]:
                    for t in s["turns"]:
                        for name in t.get("tool_calls") or []:
                            calls[name] += 1
                            seen.add(name)
                for name in seen:
                    cells_with[name] += 1
            closings = Counter(t.get("closing") for t in turns if t.get("closing"))
            deferrals = Counter(t.get("deferral") for t in turns if t.get("deferral"))
            decisions = sum(len(r.get("decision_hashes") or []) for r in runs)
            grounded = sum(len(r.get("adopted_pathway_grounds") or []) for r in runs)
            print(f"\n{stem} :: {arm}  cells={len(runs)} turns={len(turns)}  thinking={level}")
            print(f"  median reply path {_median([t.get('reply_path_s') for t in turns])}s   "
                  f"worst {max((t.get('reply_path_s') or 0) for t in turns):.1f}s   "
                  f"tool seconds {sum(_tool_seconds(t) for t in turns):.1f}")
            if calls:
                print("  elections:  " + "  ".join(
                    f"{name} x{n} (in {cells_with[name]}/{len(runs)} cells)"
                    for name, n in calls.most_common()))
            else:
                print("  elections:  none")
            print(f"  closings:   {dict(closings) or '-'}")
            print(f"  deferrals:  {dict(deferrals) or '-'}")
            print(f"  decisions on record {decisions}, with an adopted pathway {grounded}")


if __name__ == "__main__":
    read(sys.argv[1:] or ["consultant-latency", "consultant-cache"])
