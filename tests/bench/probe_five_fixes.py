"""Can the five r17 prompt fixes be seen by a machine, and what is the baseline?

    poetry run python tests/bench/probe_five_fixes.py

Commit 423d88a changed five things in the Advisor engine, each because the judge's
own rationales named it. Every one is a claim about a COUNTABLE behaviour in the
reply text, so there is a free step before paying for a judged run: measure the
behaviour on the 22 saved runs, see whether the pattern separates the arms at all,
and size r17 only on the ones that do.

WHY THIS RUNS BEFORE r17 AND NOT AFTER
======================================
A judged run cannot distinguish "the fix did not help" from "the fix did not
fire". The archive's own history is the argument: r15 and r16 both met their
structural goal completely and moved no judged row, and in both cases the useful
question afterwards was a machine count, not a rubric mean. A behaviour the arm
never exhibited is unmeasurable at any n, and finding that out costs nothing here
and ~3 hours there.

WHAT IT FOUND — FOUR OF THE FIVE ARE NOT MEASURABLE THIS WAY (2026-08-13)
=========================================================================
Kept as a probe rather than deleted, because the negative results are the
findings and each one is a trap the next reader would otherwise re-enter.

**1. Concession (a correction conceded in the first clause) — no room to move.**
The person corrects the assistant in only 12 of 704 A2 turns (1.7%), against 6 of
736 prose turns (0.8%; Fisher p=0.14 on cells). And A2 already opens with a
concession in 4 of its 12 — reading them, several of the "misses" are concessions
the regex cannot see ("You've named the real constraint", "You've made your
call"). So the judged warmth complaint (62-67 of 120 cells praising the base arm
for conceding) is NOT about these rare explicit corrections; it is about ordinary
disagreement, where "concede first" has no crisp trigger. The rule is still right
and it stays in the prompt; it is just not a countable event.

**2/3b. Bridging a dropped frame, and building on the newest words — semantic.**
Never attempted here. Whether a frame was AMENDED rather than vanished, and
whether a turn builds on the person's latest phrasing, are the semantics; a regex
sees neither. They print as `unmeasurable` and stay judge-only. A count that
reports 0 for "I cannot see this" is worse than no count, because it averages in.

**3a. Re-asking an answered question — the pattern found ~1%, in both arms.**
Two versions were tried: the assistant repeating its OWN question (A2 6/1467,
prose 1/1205) and the assistant asking for content the user had ALREADY SUPPLIED
(A2 11/1467 at 80% coverage). Both are near-zero everywhere. Content-word overlap
is genuinely weak at this — "who owns the customer relationships?" and "which
customers does he hold?" are the same question with almost no shared words — so
this is a limit of the method, not evidence the behaviour is absent. The judge's
own de-randomised notes DO attribute circling to A2 (23 of 105 cells), and the
person complains about repetition in 51 of 88 A2 cells... but in 60 of 92 prose
cells too, and in 4 of 4 A0 cells. **The complaint is the scenario, not the arm**:
every hit sits on the `pushback_2` beat (94 of 118), which instructs the simulator
to say the advice is generic and it was hoping to avoid it. So the archive cannot
be used as a baseline for this fix at all — a run comparing arms on it is
comparing two responses to the same script.

**5a. Answering a record request with homework — the archive says A2 does it
LESS.** 6 of 67 requests against a prose arm's 13 of 68. The judged complaint
(15 of 90 losing closure cells, against 1 of 51 won — so it IS selective, the
`--all-cells` check passes) turns out to describe something broader than a gate
on recording: the CLOSING TURN leaving the person owing work. Measured that way
A2 is still cleaner (9 of 176 closing turns vs A1.7's 14 of 144). The fix's
narrow wording ("a request to close is never answered with homework") therefore
targets a real but rare event, and the judged mass is elsewhere.

**4. Unpriced menus — MEASURABLE, and the diagnosis was backwards.** Promoted to
`scoring.score_menu` with the full numbers in `MenuScore`. The short version: A2
hands back a genuine choice-menu 3.5x more often (14 cells vs 4), which is the
structure surfacing and is the real defect — but it PRICES them 57% of the time
while the prose arm never does. So "unpriced" was the wrong noun; frequency is
the endpoint. The first version of this pattern matched bare enumeration and
reported 158 A2 menus, nearly all of them recipes and question lists — counting
the framework arm's `paired_recipe` output as a defect. That inversion is why the
scorer requires an option label AND a hand-back.

NET FOR r17
===========
One of five fixes has a machine endpoint. The other four are judge-only or have
no denominator, which means r17 is a JUDGED run sized on the composite (see the
README's sizing block: ~19 pairs for 0.5 steps) and the menu rate rides along as
a tripwire. It also means a null result on those four will be uninterpretable,
and that must be said before the run rather than after it.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR.parent))

from bench.models import RunRecord, SessionRecord  # noqa: E402
from bench.report import load_records  # noqa: E402
from bench.scoring import _RECORD_REQUEST, score_menu  # noqa: E402

RESULTS = BENCH_DIR / "results"


def _stems() -> list[str]:
    return sorted(
        p.stem
        for p in RESULTS.glob("*.json")
        if not p.stem.endswith(("-runs", "-rejudged"))
        and not p.stem.startswith("smoke")
    )


# ---------------------------------------------------------------------------
# Fix 1 — a correction is conceded in the first clause
# ---------------------------------------------------------------------------

#: The person pushing back on what the reply just said — not on the situation.
#: "that's not what I said" is a correction; "that's not going to work" is
#: ordinary disagreement about the world and must not count, or every hard
#: conversation scores as a correction.
_CORRECTION = re.compile(
    r"that'?s not what i (said|meant)"
    r"|i (already|just) (told|said|answered)"
    r"|i didn'?t say"
    r"|you'?re (not listening|missing)"
    r"|you keep (asking|saying)"
    r"|(no|nope),? (that'?s|thats) (not|wrong)"
    r"|i said( that)? (already|before)"
    r"|asked (you )?(this|that) (already|before)",
    re.I,
)

#: Conceding, in the FIRST CLAUSE — the rule's actual content. Applied to the
#: first sentence only (and its first 120 chars), because a concession three
#: paragraphs down is what the prompt was changed to stop. Known to UNDERCOUNT:
#: "You've named the real constraint" concedes and matches nothing here, which is
#: part of why fix 1 is reported as unmeasurable rather than as a miss rate.
_CONCEDES = re.compile(
    r"^\W*(you'?re right"
    r"|right[,.—]"
    r"|fair"
    r"|true[,.—]"
    r"|(i|my) (had|got) (that|it) wrong"
    r"|i misread"
    r"|i did[,.]"
    r"|yes[,.—]"
    r"|noted"
    r"|point taken"
    r"|apolog"
    r"|sorry"
    r"|(that'?s|thats) (fair|on me)"
    r"|(my|the) mistake"
    r"|i (was|am) wrong"
    r"|okay[,.—]"
    r"|ok[,.—]"
    r"|understood)",
    re.I,
)


def _first_clause(text: str) -> str:
    head = re.sub(r"^([#>*_\s]+)", "", text.strip())
    return re.split(r"(?<=[.!?])\s|\n", head, maxsplit=1)[0][:120]


def fix1_concession(sessions: list[SessionRecord]) -> tuple[int, int]:
    """(explicit corrections, corrections conceded in the first clause)."""
    corrections = conceded = 0
    for session in sessions:
        for turn in session.turns:
            if not _CORRECTION.search(turn.user or ""):
                continue
            corrections += 1
            if _CONCEDES.search(_first_clause(turn.assistant or "")):
                conceded += 1
    return corrections, conceded


# ---------------------------------------------------------------------------
# Fix 3a — never re-ask what they have answered
# ---------------------------------------------------------------------------

_STOP = frozenset(
    """a an and are as at be been but by can could do does for from had has have
he her him his how i if in is it its me my no not of on or our she so than that
the their them then there these they this to too us was we were what when where
which who why will with would you your about am don t s re ve ll just really very
much more most any some all both each every""".split()
)


def _question_keys(text: str) -> list[frozenset[str]]:
    """Content-word sets of each question sentence in a reply.

    A question is REPEATED when its content recurs, not when its wording does, and
    content-word overlap is the only free approximation. It is a WEAK one — see the
    module docstring, fix 3a — kept because it is applied symmetrically across arms
    so its weakness does not favour either.
    """
    keys = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        if "?" not in sentence:
            continue
        words = {w for w in re.findall(r"[a-z']+", sentence.lower()) if w not in _STOP}
        if len(words) >= 3:
            keys.append(frozenset(words))
    return keys


def fix3_reasking(
    sessions: list[SessionRecord], *, overlap: float = 0.6
) -> tuple[int, int]:
    """(questions asked after the first, questions substantially re-asked).

    Scoped WITHIN a session: re-asking across a session boundary is a memory
    failure, which the bench measures separately (`cofounder_memory`), and
    conflating the two lets a memory bug score as a rudeness.
    """
    asked = repeated = 0
    for session in sessions:
        seen: list[frozenset[str]] = []
        for turn in session.turns:
            keys = _question_keys(turn.assistant or "")
            for key in keys:
                if seen:
                    asked += 1
                    best = max(
                        (len(key & prior) / max(1, len(key | prior)) for prior in seen),
                        default=0.0,
                    )
                    if best >= overlap:
                        repeated += 1
            seen.extend(keys)
    return asked, repeated


#: The person saying, in their own words, that the assistant is going in circles.
#: Reported with the loud caveat that 94 of 118 hits sit on the `pushback_2` beat,
#: whose instruction tells the simulator to say exactly this — so it measures the
#: SCRIPT, not the arm.
_CIRCLING = re.compile(
    r"going in circles|circled? back|circling"
    r"|(third|second|fourth) time you'?ve"
    r"|rounds deep"
    r"|i already told you|i'?ve already (told|said)"
    r"|(asked|answered) (this|that) (already|before)"
    r"|you keep (asking|coming back|circling)",
    re.I,
)


def fix3_complaints(sessions: list[SessionRecord]) -> tuple[int, int]:
    """(scorable turns, turns where the person complains of repetition)."""
    turns = complaints = 0
    for session in sessions:
        for turn in session.turns:
            if not (turn.assistant or "").strip():
                continue
            turns += 1
            if _CIRCLING.search(turn.user or ""):
                complaints += 1
    return turns, complaints


# ---------------------------------------------------------------------------
# Fix 5a — "write this down" IS the confirmation, not a prompt for homework
# ---------------------------------------------------------------------------

#: A precondition placed between the person and the record they just asked for.
#: The tell is a gate ON THE RECORDING, so every branch names the writing.
_HOMEWORK = re.compile(
    r"before (i|we) (write|record|put)"
    r"|(once|after) (you|we|you'?ve)[^.?!]{0,60}(i'?ll|then i) (write|record)"
    r"|(i need|tell me|give me|run)[^.?!]{0,80}(before|first)[^.?!]{0,40}(record|write)"
    r"|not ready to (write|record)"
    r"|(let'?s|we should) (do|check|run|confirm)[^.?!]{0,60}first",
    re.I,
)

#: The judge's actual complaint, which is broader: the CLOSING turn leaves the
#: person owing work before anything is settled. Not gated on a record request.
_OWES = re.compile(
    r"once (you|i) (have|get|know|run)"
    r"|(when|after) you'?ve (run|done|checked|talked|spoken)"
    r"|(i|we) (need|'?ll need) (the|those|your) (numbers|figures|spreadsheet|answer)"
    r"|(run|check|pull|model) (the|those|your) (numbers|spreadsheet|figures)"
    r"|(before|until) (we|you) (can|do)"
    r"|(then|and) (i|we) can (show|build|map|give)"
    r"|(come back|report back|let me know) (once|when|after)"
    r"|tell me (those|the) (numbers|figures)",
    re.I,
)


def fix5a_homework(sessions: list[SessionRecord]) -> tuple[int, int]:
    """(explicit record requests, requests answered with a precondition)."""
    requests = homework = 0
    for session in sessions:
        for turn in session.turns:
            if not _RECORD_REQUEST.search(turn.user or ""):
                continue
            requests += 1
            if _HOMEWORK.search(turn.assistant or ""):
                homework += 1
    return requests, homework


def fix5a_owing(sessions: list[SessionRecord]) -> tuple[int, int]:
    """(sessions with a reply, sessions whose LAST reply leaves work owing)."""
    closes = owing = 0
    for session in sessions:
        turns = [t for t in session.turns if (t.assistant or "").strip()]
        if not turns:
            continue
        closes += 1
        if _OWES.search(turns[-1].assistant or ""):
            owing += 1
    return closes, owing


# ---------------------------------------------------------------------------
# Fix 5b — a record they were never told about is a record they do not have
# ---------------------------------------------------------------------------
# The judged half is `across_runs.visibility_rows`; this is the raw count, so the
# probe prints all five behaviours in one table.

_SPOKEN = re.compile(
    r"that'?s the record"
    r"|i'?ll (write|note|record) (it|this|that)"
    r"|recording your decision"
    r"|decision recorded"
    r"|^\W*\**decision:"
    r"|(it'?s|this is) (now )?(on|in) the record"
    r"|(written|recorded|logged) (it|this|that|your decision)"
    r"|i'?ve (written|recorded|logged)",
    re.I | re.M,
)


def fix5b_silent_record(run: RunRecord) -> tuple[int, int]:
    """(requests in a cell that HAS a record, requests answered without saying so).

    Cell-level `record_exists`, the same honest limit as `score_phantom_record`:
    the graph read-back is per cell, so a request is credited against whatever the
    cell holds.
    """
    if not run.decision_hashes:
        return 0, 0
    requests = silent = 0
    for session in run.sessions:
        for turn in session.turns:
            if not _RECORD_REQUEST.search(turn.user or ""):
                continue
            requests += 1
            if not _SPOKEN.search(turn.assistant or ""):
                silent += 1
    return requests, silent


# ---------------------------------------------------------------------------

_ARM_ORDER = ("A0", "A1", "A1.5", "A1.7", "A2")

_LABELS = (
    ("concede", "conceded/corrected"),
    ("reask", "re-asked/asked"),
    ("circling", "complaints/turns"),
    ("menu", "unpriced/menus"),
    ("homework", "homework/requests"),
    ("owing", "owing/closes"),
    ("silent", "silent/requests"),
)


def main() -> int:
    tally: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    cells: dict[str, int] = defaultdict(int)
    for stem in _stems():
        payload = load_records(RESULTS / f"{stem}.json")
        for raw in payload.get("runs") or []:
            record = RunRecord.model_validate(raw)
            if record.tier != "weak" or record.error:
                continue
            arm = record.arm.value
            cells[arm] += 1
            menu = score_menu(record.sessions)
            turns, complaints = fix3_complaints(record.sessions)
            for label, (denominator, numerator) in {
                "concede": fix1_concession(record.sessions),
                "reask": fix3_reasking(record.sessions),
                "circling": (turns, complaints),
                "menu": (menu.menus, menu.unpriced),
                "homework": fix5a_homework(record.sessions),
                "owing": fix5a_owing(record.sessions),
                "silent": fix5b_silent_record(record),
            }.items():
                tally[arm][label][0] += denominator
                tally[arm][label][1] += numerator

    print("=" * 100)
    print("CAN A MACHINE SEE THE FIVE FIXES?  weak tier, all poolable runs")
    print("=" * 100)
    print(
        "\nEach cell is <hits>/<opportunities>. The DENOMINATOR is the finding: a\n"
        "pattern with no opportunities cannot be the mechanism behind a judged loss,\n"
        "however good the rule sounds. Read the module docstring before quoting any\n"
        "of these — four of the five columns are traps, each for a different reason.\n"
    )
    header = f"{'arm':<6}{'cells':>6}"
    for _, title in _LABELS:
        header += f"{title:>21}"
    print(header)
    for arm in _ARM_ORDER:
        if arm not in tally:
            continue
        row = f"{arm:<6}{cells[arm]:>6}"
        for key, _ in _LABELS:
            denominator, numerator = tally[arm][key]
            cell = f"{numerator}/{denominator}" if denominator else "—"
            row += f"{cell:>21}"
        print(row)

    print(
        "\nMEASURABLE: menu only — promoted to `scoring.score_menu`, and its\n"
        "  diagnosis inverted on contact with the data (A2 offers menus 3.5x more\n"
        "  often AND prices them more often; frequency is the endpoint).\n"
        "\nNOT MEASURABLE, and each for its own reason:\n"
        "  concede  — 12 events in 704 A2 turns, and the regex undercounts the\n"
        "             concessions that are there. No room to move.\n"
        "  reask    — ~1% in every arm; content overlap cannot see a rephrased\n"
        "             question, so this is a method limit, not an absence.\n"
        "  circling — 94 of 118 complaints sit on the `pushback_2` beat, which\n"
        "             INSTRUCTS the simulator to say it. Measures the script.\n"
        "  homework — A2 already does it LESS than the prose arm (6/67 vs 13/68),\n"
        "             and so does the broader `owing` reading (9/176 vs 14/144).\n"
        "  bridging a dropped frame, and building on the newest words — semantic.\n"
        "             Judge-only, named 37 and 23 times, deliberately NOT counted:\n"
        "             a scorer that prints 0 for 'I cannot see this' gets averaged.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
