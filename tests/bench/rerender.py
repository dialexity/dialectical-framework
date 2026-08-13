"""Re-render a saved run's report with the CURRENT report code.

    poetry run python tests/bench/rerender.py claim2-weak-r16-floor
    poetry run python tests/bench/rerender.py --all --write

Every `results/<stem>.json` carries the runs, comparisons and machine scores
needed to regenerate `<stem>.txt` without an LLM call, which makes this free.
It exists because the report's *reading* changes more often than the runs do:
`--write` rewrites the saved `.txt` in place so a prose-only fix (a warning,
a flag, an interval) reaches the reports that were read under the old rendering.

Never touches `.json`. The records are the measurement; the `.txt` is a view of
them, and only the view is regenerated. Re-rendering does NOT re-judge — a
scoring change needs `DIALEXITY_BENCH_REJUDGE`, which costs money.

Standing caveat, and the reason `--write` prints a reminder: a re-rendered
report carries today's ANALYSIS of an older run, so a prose claim inside it
("the fix landed", "this is the largest component") was written against
whatever the code did that day. Statistical framing regenerates honestly;
narrative does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
RESULTS = BENCH_DIR / "results"
sys.path.insert(0, str(BENCH_DIR.parent))

from bench.models import Comparison, MachineScores, RunRecord  # noqa: E402
from bench.report import load_records, render_report  # noqa: E402


def rerender(stem: str) -> str:
    d = load_records(RESULTS / f"{stem}.json")
    runs = [RunRecord.model_validate(r) for r in d["runs"]]
    comparisons = [Comparison.model_validate(c) for c in d["comparisons"]]
    machine = {
        k: MachineScores.model_validate(v) for k, v in (d.get("machine") or {}).items()
    }
    # Tier order is weakest -> strongest, which for this bench's two tiers is
    # alphabetical ("strong" < "weak" is wrong, so reverse-sort puts weak first).
    tiers = sorted({r.tier for r in runs}, reverse=True)
    return render_report(
        runs=runs, comparisons=comparisons, machine=machine, tier_order=tiers
    )


def _stems() -> list[str]:
    return sorted(
        p.stem for p in RESULTS.glob("*.json") if not p.stem.endswith("-runs")
    )


def main(argv: list[str]) -> int:
    write = "--write" in argv
    args = [a for a in argv if not a.startswith("--")]
    stems = _stems() if "--all" in argv else args
    if not stems:
        print(__doc__)
        print("available:", ", ".join(_stems()))
        return 1

    for stem in stems:
        try:
            text = rerender(stem)
        except Exception as exc:  # noqa: BLE001 — a bad record must not stop the sweep
            print(f"!! {stem}: {type(exc).__name__}: {exc}")
            continue
        if write:
            (RESULTS / f"{stem}.txt").write_text(text)
            print(f"rewrote {stem}.txt")
        elif len(stems) == 1:
            print(text)
        else:
            print(f"-- {stem}: {len(text.splitlines())} lines (use --write to save)")

    if write:
        print(
            "\nNote: prose inside a re-rendered report was written against the "
            "code of its own day. Statistical framing regenerates honestly; "
            "narrative claims do not."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
