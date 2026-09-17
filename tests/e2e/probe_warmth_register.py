"""Which behaviours actually cost A2 warmth, checked against the cells it WON.

    poetry run python tests/e2e/probe_warmth_register.py
    poetry run python tests/e2e/probe_warmth_register.py conversational_fit

Free — pure text over saved judge rationales, no LLM and no DB.

WHY THIS EXISTS
===============
`across_runs.py` says warmth is the worst dimension in the archive (-0.639
[-0.81,-0.47] pooled over 18 weak-tier sets, negative in every one) and that it
is a UNIFORM TAX: A2 loses 62% of warmth cells and wins 11%, so the cause is in
every reply and no single cell will show it. Its own advice at that point is to
stop counting and read `judge_notes.py`.

Reading them, three behaviours recur so heavily in the losing notes that they
look like the answer. That is exactly the inference `judge_notes` warns against
in its own docstring: those notes were SELECTED on the loss, so a behaviour
appearing in most of them may appear just as often where A2 won. A frequency from
the losing set is a lead, not a result.

So this script computes each behaviour's rate in the LOST cells and in the WON
cells and reports the gap. A behaviour that shows up at the same rate on both
sides explains nothing, however damning it reads.

WHAT IT CANNOT DO
=================
These are keyword families over the JUDGE's prose, not over the transcripts. So
a hit means "the judge wrote about this", which is one inference away from "the
arm did this" — a judge who never names a behaviour it noticed is invisible here.
Read a gap as evidence about what the judge PENALISED, which is the quantity the
score is made of, and go to the transcripts before changing a prompt.

The model pin is re-applied here (`judge_notes.notes_for` deliberately does not
apply it, since it returns quotable rows rather than a mean). Stems whose `weak`
label ran a different model are dropped, or Sonnet cells would enter a haiku
rate — the error direction that has flattered this arm every time it slipped in.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.across_runs import fisher_exact, pooled_model, tier_model  # noqa: E402
from e2e.judge_notes import notes_for  # noqa: E402

#: Behaviour families, as the judge tends to word them. Each is a lead read off
#: the losing notes; the whole point of the script is to test them against the
#: won cells, so being generous here is safe and being narrow is not.
BEHAVIOURS: dict[str, tuple[str, ...]] = {
    "framework-speak in the reply": (
        r"framework[- ]speak",
        r"framework[- ]flavou?red",
        r"\bthe framework (found|is showing|shows|flagged)",
        r"\bthe (record|system|audit) (is |was )?(flag|caught|blunt)",
        r"\bjargon\b",
        r"process jargon",
        r"structurally different",
    ),
    "no graceful concession": (
        r"conced(e|es|ing) gracefully",
        r"grace(ful|fully) (when|conced)",
        r"owns its (mistake|error)",
        r"yields? gracefully",
        r"no (comparable|equivalent)",
        r"relapse",
        r"reasserts?",
        r"overrides? the user",
        r"doubl(e|es|ing) down",
    ),
    "heavy structure / bullets / bold": (
        r"bold(ed)? (header|structure|question)",
        r"heavy (bold|structure)",
        r"bullet[- ]head",
        r"checklist",
        r"numbered (question|demand|intake)",
        r"intake form",
        r"\bheaders?\b",
    ),
    "interrogation / gatekeeping": (
        r"interrogat",
        r"gatekeep",
        r"question batter",
        r"pre[- ]commit gating",
        r"before (you're|you are) allowed",
        r"\bdemands?\b",
        r"what I need from you",
    ),
    "clinical / lecturing tone": (
        r"clinical",
        r"lectur",
        r"transactional",
        r"condescend",
        r"managed\b",
        r"consultant",
    ),
}

_COMPILED = {
    name: tuple(re.compile(p, re.I) for p in patterns)
    for name, patterns in BEHAVIOURS.items()
}


def _hits(note: str) -> set[str]:
    return {
        name
        for name, patterns in _COMPILED.items()
        if any(p.search(note) for p in patterns)
    }


def _report(dimension: str) -> None:
    pinned = pooled_model("weak")
    rows = notes_for((dimension,), only_losses=False).get(dimension) or []
    kept: list[tuple[int, int, str]] = []
    dropped: dict[str, int] = defaultdict(int)
    for stem, _session, _opponent, mine, theirs, note in rows:
        model = tier_model(stem, "weak")
        # `None` means the stem's weak label covered more than one model, so it
        # cannot be attributed either way — dropped for the same reason as a
        # mismatch, and counted separately so the drop is never silent.
        if pinned is not None and model != pinned:
            dropped[model or "mixed"] += 1
            continue
        kept.append((mine, theirs, note))

    lost = [n for mine, theirs, n in kept if mine < theirs]
    won = [n for mine, theirs, n in kept if mine > theirs]
    tied = [n for mine, theirs, n in kept if mine == theirs]

    print("=" * 74)
    print(f"{dimension} — behaviour rates in the judge's own notes, weak tier")
    print("=" * 74)
    print(f"  model pinned to {pinned}")
    if dropped:
        detail = ", ".join(f"{n} cells on {m}" for m, n in sorted(dropped.items()))
        print(f"  dropped off-model: {detail}")
    print(f"  A2 lost {len(lost)}, won {len(won)}, tied {len(tied)}")
    if not lost or not won:
        print("  -> one side is empty; a gap cannot be computed")
        return

    # The won side is the small one by construction — a dimension A2 wins 11% of
    # is why this probe exists — so the gap gets a p-value beside it rather than
    # being read off the percentages. Without it a +12pp gap on 36 won cells is
    # indistinguishable from four cells landing differently.
    print(f"\n  {'behaviour':34}{'lost':>8}{'won':>8}{'gap':>9}{'Fisher p':>10}")
    scored = []
    for name in BEHAVIOURS:
        lost_hits = sum(name in _hits(n) for n in lost)
        won_hits = sum(name in _hits(n) for n in won)
        lost_rate = lost_hits / len(lost)
        won_rate = won_hits / len(won)
        p = fisher_exact(
            lost_hits, len(lost) - lost_hits, won_hits, len(won) - won_hits
        )
        scored.append((lost_rate - won_rate, name, lost_rate, won_rate, p))
    for gap, name, lost_rate, won_rate, p in sorted(scored, reverse=True):
        mark = " *" if p < 0.05 else ""
        print(
            f"  {name:34}{lost_rate * 100:>7.0f}%{won_rate * 100:>7.0f}%"
            f"{gap * 100:>+8.0f}pp{p:>10.3f}{mark}"
        )
    print(
        "\n  A gap near zero means the judge writes about that behaviour just as"
        "\n  often when A2 WINS, so it is not what the score is made of — however"
        "\n  much of the losing prose it occupies. * = p < 0.05, and with a won"
        f"\n  side of {len(won)} cells nothing below ~10pp can reach it."
    )
    print()


def main(argv: list[str]) -> int:
    dimensions = argv[1:] or ["warmth", "conversational_fit"]
    for dimension in dimensions:
        _report(dimension)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
