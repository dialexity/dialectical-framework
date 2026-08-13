"""Pull the judge's own rationale for the cells an arm LOST, de-randomised.

    poetry run python tests/bench/judge_notes.py            # the 5 worst dimensions
    poetry run python tests/bench/judge_notes.py warmth     # one, named
    poetry run python tests/bench/judge_notes.py --all-cells      # won cells too
    poetry run python tests/bench/judge_notes.py --dump /tmp/out  # file per dimension

Every judged comparison carries a `notes[dimension]` rationale and an
`overall_note`, and until now nothing read them. `report.py` prints the numbers,
`across_runs.py` pools them — but the numbers only say WHICH dimension a run lost,
never what the arm did to lose it, and that is the whole diagnostic content of a
paid judging pass sitting unused in `results/`.

Free: pure text extraction over saved records, no LLM and no DB.

X/Y ARE DE-RANDOMISED HERE, AND THAT IS THE POINT
=================================================
The judge sees two anonymous transcripts as X and Y, in a randomised order, and
writes about "X" and "Y". Reading the raw notes therefore tells you nothing about
which ARM was criticised — and worse, reads as if it does, because half the notes
happen to praise X. `Comparison.x_arm` records which side was which, so every
mention is rewritten to the arm's own name before anything reaches a human (or a
subagent). Getting this backwards would not fail loudly; it would produce a
confident, thoroughly-quoted diagnosis of the wrong arm.

WHAT THIS IS FOR, AND ITS ONE HONEST LIMIT
==========================================
Written after two hypotheses about the archive-wide weak-tier loss were refuted by
their own probes (document formatting: no within-run correlation; verbatim repeats:
3 instances archive-wide, the worst of them a prose arm's). Both were MY guesses at
what A2 does wrong. The judge had already written 531 rationales on exactly that
question and nobody had read them.

The limit: these are the notes from cells the arm LOST, selected on that basis, so
they are evidence about what a loss LOOKS like and not about how often it happens.
A behaviour appearing in 60 of 131 losing cells may appear just as often in the
winning ones. `--all-cells` prints won and lost side by side for exactly that
check, and any behaviour promoted to a finding needs it — the frequency in the
losing set alone is a lead, not a result.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
RESULTS = BENCH_DIR / "results"
sys.path.insert(0, str(BENCH_DIR.parent))

from bench.across_runs import _stems  # noqa: E402
from bench.models import Comparison  # noqa: E402
from bench.report import load_records  # noqa: E402

#: The five dimensions carrying the archive-wide weak-tier loss, worst first.
#: Hardcoded rather than computed so this script stays free of the pooling code —
#: it is a text tool, and `across_runs.py` is where the ranking is derived.
LOSING_DIMENSIONS = (
    "conversational_fit",
    "cross_turn_coherence",
    "warmth",
    "decision_closure",
    "convergence",
)


def _derandomise(note: str, *, subject: str, opponent: str, subject_is_x: bool) -> str:
    """Rewrite the judge's X/Y into arm names.

    Word-boundary anchored: the notes contain ordinary prose, and an unanchored
    replace turns "explicitly" into "explicitl(A2)ly". Applied in one pass over
    both letters so a note mentioning both does not get its second substitution
    applied to the output of the first.
    """
    mapping = {
        "X": subject if subject_is_x else opponent,
        "Y": opponent if subject_is_x else subject,
    }
    return re.sub(r"\b([XY])\b", lambda m: mapping[m.group(1)], note)


def notes_for(
    dimensions: tuple[str, ...] = LOSING_DIMENSIONS,
    *,
    subject: str = "A2",
    tier: str = "weak",
    only_losses: bool = True,
) -> dict[str, list[tuple[str, str, str, int, int, str]]]:
    """dimension -> [(stem, session, opponent, subject score, opponent score, note)].

    `only_losses` defaults True because that is the diagnostic question, but the
    flag exists so the same call can produce the comparison set — see the module
    docstring on why a frequency from the losing cells alone is only a lead.
    """
    out: dict[str, list[tuple[str, str, str, int, int, str]]] = defaultdict(list)
    for stem in _stems():
        payload = load_records(RESULTS / f"{stem}.json")
        for raw in payload.get("comparisons") or []:
            comparison = Comparison.model_validate(raw)
            if tier and comparison.tier != tier:
                continue
            arms = (comparison.arm_a.value, comparison.arm_b.value)
            if subject not in arms or arms[0] == arms[1]:
                continue
            opponent = arms[1] if arms[0] == subject else arms[0]
            for dimension in dimensions:
                if dimension not in comparison.scores:
                    continue
                score_a, score_b = comparison.scores[dimension]
                mine, theirs = (
                    (score_a, score_b)
                    if comparison.arm_a.value == subject
                    else (score_b, score_a)
                )
                if only_losses and mine >= theirs:
                    continue
                note = comparison.notes.get(dimension, "")
                if not note:
                    continue
                out[dimension].append(
                    (
                        stem,
                        comparison.session_label,
                        opponent,
                        mine,
                        theirs,
                        _derandomise(
                            note,
                            subject=subject,
                            opponent=opponent,
                            subject_is_x=comparison.x_arm.value == subject,
                        ),
                    )
                )
    return out


def _print(dimensions: tuple[str, ...], *, only_losses: bool) -> None:
    grouped = notes_for(dimensions, only_losses=only_losses)
    for dimension in dimensions:
        rows = grouped.get(dimension) or []
        if not rows:
            continue
        header = "LOST" if only_losses else "all"
        print("=" * 74)
        print(f"{dimension} — {len(rows)} {header} cells, weak tier, X/Y de-randomised")
        print("=" * 74)
        for stem, session, opponent, mine, theirs, note in rows:
            print(f"\n[{stem} {session}] A2={mine} {opponent}={theirs}")
            print(note)
        print()


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    dump = None
    if "--dump" in argv:
        index = argv.index("--dump")
        dump = Path(argv[index + 1])
        argv = argv[:index] + argv[index + 2 :]
    only_losses = "--all-cells" not in argv
    named = tuple(a for a in argv if not a.startswith("-"))
    dimensions = named or LOSING_DIMENSIONS
    if dump:
        # One file per dimension: the whole set is ~130k characters, which is
        # more than a single reader (human or subagent) handles well in one pass,
        # and the dimensions have different causes anyway.
        dump.mkdir(parents=True, exist_ok=True)
        grouped = notes_for(dimensions, only_losses=only_losses)
        for dimension, rows in grouped.items():
            target = dump / f"notes_{dimension}.txt"
            target.write_text(
                "\n\n".join(
                    f"[{dimension}] {stem} {session} A2={mine} {opponent}={theirs}\n{note}"
                    for stem, session, opponent, mine, theirs, note in rows
                )
            )
            print(f"-- {target} ({len(rows)} cells, {target.stat().st_size} bytes)")
        return 0
    _print(dimensions, only_losses=only_losses)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
