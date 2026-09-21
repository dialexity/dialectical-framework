"""
read_reach — does the graph reach the reply? For NAMED stems and EVERY arm with a dump.

    poetry run python tests/e2e/read_reach.py thinking-off seam-fixes reasoning-sonnet

Free. `probe_readside_reach.py` asked this over the pre-refresh archive and found
the differentiator (pathways, synthesis) barely reaching the reply while the
decision ledger did. That probe reads only A2 and only its fixed rounds; this
reads any stem, and every arm whose sessions carry a dump — A2 (live, seeded on
returning sessions), A2c (the Consultant, seeded every session) and A1.5 (the
static dump) — with the same overlap measure, so the three can be read side by
side: does the SAME structure reach the reply more when it is static?

Overlap = share of a dump line's content words found anywhere in the session's
replies, best-matching line per section. Not semantic (cannot see paraphrase);
read it as a floor on the DIFFERENCE between sections and between arms.
`carryover_in` is the dump at session START, so for a live A2 first session
(seed None) there is no row — the structure it built mid-session is not in a
start-of-session dump. That is a limit of the record, stated rather than hidden.
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e.models import RunRecord  # noqa: E402
from e2e.report import load_records  # noqa: E402
from probe_readside_reach import (_HASH_CITATION, _best_overlap,  # noqa: E402
                                  _content_words)

RESULTS = Path(__file__).resolve().parent / "results"


def rows_for(stem: str) -> list[dict]:
    out: list[dict] = []
    for raw in load_records(RESULTS / f"{stem}-runs.json").get("runs") or []:
        run = RunRecord.model_validate(raw)
        if run.error:
            continue
        for session in run.sessions:
            dump = session.carryover_in
            if not dump:
                continue
            lines = dump.splitlines()
            synthesis = [ln.strip() for ln in lines if re.search(r"\bS[+-]", ln)]
            pathways = [ln.strip() for ln in lines if "Ac+" in ln]
            # `T1 [[hash]]: "..."`, `A2+ [[hash]]: "..."` — the tetrad lines.
            tensions = [ln.strip() for ln in lines if re.match(r"\s*[TA]\d*[+-]? \[\[", ln)]
            decisions = [ln.strip() for ln in lines if "ecision" in ln or "Stance" in ln]
            reply = " ".join(turn.assistant or "" for turn in session.turns)
            words = _content_words(reply)
            out.append(
                {
                    "stem": stem,
                    "arm": run.arm.value,
                    "rep": run.replicate,
                    "branch": run.branch or "-",
                    "label": session.label,
                    "dump_chars": len(dump),
                    "pathway_lines": len(pathways),
                    "tensions": _best_overlap(tensions, words),
                    "pathways": _best_overlap(pathways, words),
                    "synthesis": _best_overlap(synthesis, words),
                    "decisions": _best_overlap(decisions, words),
                    "hashes": len(_HASH_CITATION.findall(reply)),
                }
            )
    return out


def main(stems: list[str]) -> None:
    rows = [r for stem in stems for r in rows_for(stem)]
    print(f"{'stem':18s} {'arm':5s} rep branch    session   dump_c  paths  tens  path  synth  decis  hashes")
    for r in rows:
        print(
            f"{r['stem']:18s} {r['arm']:5s} {r['rep']:3d} {r['branch']:9s} {r['label']:9s} "
            f"{r['dump_chars']:6d} {r['pathway_lines']:6d}  {r['tensions']:.2f}  {r['pathways']:.2f}  "
            f"{r['synthesis']:.2f}   {r['decisions']:.2f}  {r['hashes']:5d}"
        )
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    print("\nmedian best-overlap per arm (sessions with a dump):")
    print(f"{'arm':5s} sessions  tensions  pathways  synthesis  decisions  hashes cited")
    for arm, rs in sorted(by_arm.items()):
        med = lambda k: statistics.median(x[k] for x in rs)  # noqa: E731
        print(
            f"{arm:5s} {len(rs):8d}  {med('tensions'):8.2f}  {med('pathways'):8.2f}  "
            f"{med('synthesis'):9.2f}  {med('decisions'):9.2f}  {sum(x['hashes'] for x in rs):12d}"
        )
    print(
        "\nread: pathways/synthesis are the differentiator; decisions are the memory. "
        "A2 rows exist only for returning sessions (seed at session start)."
    )


if __name__ == "__main__":
    main(sys.argv[1:] or ["thinking-off", "seam-fixes", "reasoning-sonnet"])
