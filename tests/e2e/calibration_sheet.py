"""A blind sheet for calibrating the coherence judge's 0.7 line against human reads.

The judge (`ControlStatementsCheck`) scores "T+ without A+ yields T-" and
"A+ without T+ yields A-" and passes a tetrad when both are ≥ 0.7. The line was
never calibrated. This draws 15 passing and 15 failing tetrads from the stored
probe files, the ones whose weaker score sits NEAREST the line, shuffles them
(fixed seed), and writes a sheet with the texts and two blank verdict columns
— scores hidden — plus a key. Two raters read the sheet independently; the
agreement between them and with the key says whether 0.7 is where humans draw
the line. The second rater is not a framework task.

    poetry run python tests/e2e/calibration_sheet.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_FIELDS = ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")


def _judged_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(_RESULTS.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [
            i for v in data.values() if isinstance(v, list) for i in v
        ]
        for item in items:
            if not isinstance(item, dict) or "pass" not in item:
                continue
            cc = item.get("cc")
            if not (isinstance(cc, list) and len(cc) == 2 and all(item.get(f) for f in _FIELDS)):
                continue
            rows.append({**{f: item[f] for f in _FIELDS}, "cc": cc, "pass": bool(item["pass"]),
                         "source": path.name})
    # one entry per tetrad text
    seen: set[tuple] = set()
    unique = []
    for row in rows:
        key = tuple(row[f] for f in _FIELDS)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def main() -> None:
    rows = _judged_rows()
    near = sorted(rows, key=lambda r: abs(min(r["cc"]) - 0.7))
    passing = [r for r in near if r["pass"]][:15]
    failing = [r for r in near if not r["pass"]][:15]
    sheet = passing + failing
    random.Random(7).shuffle(sheet)
    lines = [
        "# Coherence calibration sheet",
        "",
        "For each tetrad, read the two control statements and answer each with",
        "**holds** (the statement is true of these texts) or **does not hold**.",
        "Do not score; do not look for the 'right' answer — your own read is the datum.",
        "",
    ]
    for n, r in enumerate(sheet, 1):
        lines += [
            f"## {n}",
            "",
            f"- Thesis: {r['thesis']}",
            f"- Antithesis: {r['antithesis']}",
            f"- T+: {r['t_plus']}",
            f"- T-: {r['t_minus']}",
            f"- A+: {r['a_plus']}",
            f"- A-: {r['a_minus']}",
            "",
            f"1. \"{r['t_plus']}\" without \"{r['a_plus']}\" yields \"{r['t_minus']}\" — holds / does not hold: ______",
            f"2. \"{r['a_plus']}\" without \"{r['t_plus']}\" yields \"{r['a_minus']}\" — holds / does not hold: ______",
            "",
        ]
    (_RESULTS / "calibration_sheet.md").write_text("\n".join(lines))
    (_RESULTS / "calibration_key.json").write_text(json.dumps(
        [{"n": n, **r} for n, r in enumerate(sheet, 1)], indent=2, ensure_ascii=False))
    print(f"{len(sheet)} tetrads ({len(passing)} pass / {len(failing)} fail) from {len(rows)} judged; "
          f"weaker score range {min(min(r['cc']) for r in sheet):.2f}–{max(min(r['cc']) for r in sheet):.2f}")
    print(f"→ {_RESULTS / 'calibration_sheet.md'}  (key: calibration_key.json — do not open before rating)")


if __name__ == "__main__":
    main()
