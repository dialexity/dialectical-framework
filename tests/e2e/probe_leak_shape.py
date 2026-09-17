"""What KIND of machinery leak is it — echoed dump, narrated method, or a label?

    poetry run python tests/e2e/probe_leak_shape.py

Free — `score_machinery_leak` over every archived A2 session, no LLM, no DB.

`_HOW_YOU_SPEAK` already bans the vocabulary at length, so the fix is not another
rule; it depends on WHERE the words come from. `score_machinery_leak` returns
snippets rather than a count for exactly this reason, and nothing had grouped
them.

Grouping them is also what caught the scorer. The first run of this script said
181 snippets over 438 sessions, 55% of them a "BARE TERM" — and reading those
showed `accepted cost` (51) and a bare `the framework` (56), neither banned by any
prompt, plus "synthesis" matching "thesis". `score_machinery_leak` was corrected
on 2026-09-17 and the same archive now reads 126 snippets, 85 of 1645 replies
(5.2%), with the shares inverted: the leak is NARRATED and LABEL, not vocabulary.
That is the whole argument for grouping before fixing.

Three shapes need three different fixes:

  * ECHOED — the reply is reading the rendered context back to the person
    ("the main wheel is 63.9% probable"). The lever is what
    `dialectical_context` puts in the prompt, not what the prompt forbids: the
    model cannot say a word it was never handed.
  * NARRATED — the machinery as an actor ("the framework found four
    oppositions"). `_HOW_YOU_SPEAK` addresses this one directly and by example,
    so a hit here is a compliance failure and the honest answer may be that a
    prompt cannot carry it.
  * LABEL — a bare `T+`/`A-` position marker. A formatting slip.

A snippet can match more than one shape; it is counted under each, so the columns
do not sum to the total. Read the shares, not the sum.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.models import SessionRecord  # noqa: E402
from e2e.report import load_records  # noqa: E402
from e2e.scoring import (  # noqa: E402
    _MACHINERY_ACTOR,
    _MACHINERY_TERM_RE,
    _POSITION_LABEL,
    score_machinery_leak,
    score_machinery_leak_unambiguous,
)

RESULTS = E2E_DIR / "results"

#: The machinery as the grammatical subject or agent of a finding — the shape
#: `_HOW_YOU_SPEAK` bans by worked example ("…found four strong oppositions").
#:
#: DELIBERATELY WIDER than the scorer's `_MACHINERY_ACTOR`. The scorer must not
#: fire on "you found the tension between them", which is what the prompt ASKS
#: for, so it is anchored on a machinery noun. Here a false positive costs a
#: misfiled row in a diagnostic, not an inflated headline metric, so the
#: subjectless form ("five tensions surfaced") is worth catching. The gap between
#: the two counts is itself the finding: it is the part of the ban no regex on the
#: scoring path can carry.
_NARRATED = re.compile(
    r"(the (framework|system|analysis|audit|record|wheel|nexus)\s+"
    r"(found|shows?|showed|is showing|flagged|flags|says?|said|caught|"
    r"surfaced|identified|suggests?|indicates?|has|gave)"
    r"|(found|surfaced|identified)\s+(?:\w+\s+){0,2}"
    r"(oppositions?|tensions?|polarit|perspectives?)"
    r"|(?:my|the)\s+(analysis|reasoning|model)\s+(found|shows?|says?))",
    re.I,
)

#: A rendered number read back out. The context dump is the only place a person
#: -facing reply could get a probability or a percentage attached to machinery
#: vocabulary, so a digit inside the snippet is the echo signal.
_ECHOED = re.compile(
    r"(\d+(\.\d+)?\s*%|\d\.\d{2,}|probab|confidence\s+of|\bscore[sd]?\b"
    r"|\bratio\b|\d+\s+of\s+\d+)",
    re.I,
)


def _sessions() -> list[tuple[str, SessionRecord]]:
    out: list[tuple[str, SessionRecord]] = []
    for path in sorted(RESULTS.glob("*.json")):
        if path.stem.endswith(("-runs", "-rejudged", "-rejudge")):
            continue
        payload = load_records(path)
        for run in payload.get("runs") or []:
            if run.get("arm") != "A2":
                continue
            for raw in run.get("sessions") or []:
                try:
                    out.append((path.stem, SessionRecord.model_validate(raw)))
                except Exception:  # noqa: BLE001
                    continue
    return out


def main() -> int:
    shapes: Counter = Counter()
    terms: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    total = 0
    leaking_sessions = 0
    hard_total = 0
    hard_sessions = 0
    turns = 0
    leaking_turns = 0
    hard_turns = 0
    sessions = _sessions()

    for stem, session in sessions:
        hits = score_machinery_leak(session)
        hard = score_machinery_leak_unambiguous(session)
        if hits:
            leaking_sessions += 1
        if hard:
            hard_sessions += 1
        hard_total += len(hard)
        # Turns are the comparable unit — see `read_reply_hygiene._turns_with`.
        # One leaking sentence can report as three snippets, so a snippet rate
        # over-reads the frequency of the failure it is measuring.
        for turn in session.turns:
            if not (turn.assistant or "").strip():
                continue
            turns += 1
            solo = session.model_copy(update={"turns": [turn]})
            if score_machinery_leak(solo):
                leaking_turns += 1
            if score_machinery_leak_unambiguous(solo):
                hard_turns += 1
        for snippet in hits:
            total += 1
            flat = " ".join(snippet.split())
            matched = False
            if _NARRATED.search(flat):
                shapes["NARRATED — machinery as actor"] += 1
                examples["NARRATED"].append(f"[{stem}] {flat}")
                matched = True
            if _ECHOED.search(flat):
                shapes["ECHOED — rendered figure read aloud"] += 1
                examples["ECHOED"].append(f"[{stem}] {flat}")
                matched = True
            if _POSITION_LABEL.search(flat):
                shapes["LABEL — bare position marker"] += 1
                examples["LABEL"].append(f"[{stem}] {flat}")
                matched = True
            if not matched:
                shapes["BARE TERM — the noun on its own"] += 1
                examples["BARE"].append(f"[{stem}] {flat}")
            # Read off the scorer's own patterns rather than a local list, which
            # is what let the two drift until the tally was counting phrases the
            # scorer no longer scores.
            for match in _MACHINERY_TERM_RE.finditer(flat):
                terms[match.group(0).lower()] += 1
            for match in _MACHINERY_ACTOR.finditer(flat):
                terms[f"[actor] {match.group(0).lower()}"] += 1
            for match in _POSITION_LABEL.finditer(flat):
                terms[f"[label] {match.group(0)}"] += 1

    print("=" * 74)
    print("machinery leaks in archived A2 replies, by shape")
    print("=" * 74)
    print(f"  {len(sessions)} A2 sessions, {leaking_sessions} with at least one leak")
    print(f"  {total} snippets (a snippet can carry more than one shape)")
    print(
        f"  unambiguous only: {hard_sessions} sessions, {hard_total} snippets"
        " — the contract minus the terms that are also ordinary English"
    )
    print(
        f"  {turns} non-empty replies: {leaking_turns} leak"
        f" ({leaking_turns / (turns or 1) * 100:.1f}%),"
        f" {hard_turns} unambiguously ({hard_turns / (turns or 1) * 100:.1f}%)\n"
    )
    for shape, count in shapes.most_common():
        print(f"  {shape:42}{count:>5}  {count / (total or 1) * 100:>5.0f}%")

    print("\n  which word leaked:")
    for term, count in terms.most_common():
        print(f"    {term:24}{count:>5}")

    for key in ("ECHOED", "NARRATED", "LABEL", "BARE"):
        rows = examples.get(key) or []
        if not rows:
            continue
        print(f"\n  --- {key}, first 8 of {len(rows)} ---")
        for row in rows[:8]:
            print(f"    {row[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
