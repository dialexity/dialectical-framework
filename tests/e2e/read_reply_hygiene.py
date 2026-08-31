"""Reply hygiene and tool integrity for archived stems, offline and free.

The machine scorers in `scoring.py` are pure functions over `SessionRecord`, and
`SessionRecord` is a Pydantic model, so any stem's stored sessions validate
straight back into one. That means the two REPLY-CONTENT scorers can be re-run
over the archive with no provider, no judge and no Memgraph — which is the only
quality evidence available for the `DIALEXITY_E2E_JUDGE_OFF=1` timing stems,
whose `comparisons` list is empty because they ran a single arm.

    poetry run python tests/e2e/read_reply_hygiene.py timing-after-audit-gather \
        timing-after-one-round

WHY THIS EXISTS
===============
Three latency changes landed after the last judged round (r26): the audit went
opt-in, the redundant extraction round was removed, and the streamed text became
the reply. The first two change what the person READS:

- Removing the extraction round means the reply is now the model's own prose
  rather than a re-render of it through `ChatResponse`. A re-render was an
  accidental hygiene filter — it gave the model a second pass in which to drop a
  stray `T+:` label. `score_machinery_leak` is how a regression there shows up.
- `score_internal_prompt_echo` should go the other way. It detects the framework's
  own `_EXTRACTION_REQUEST` being read as something the PERSON typed, and that
  message is only ever appended by `_call_with_response_model` — the call the
  change removed from the common turn. Its hits can only fall.

So this reader is not a general-purpose scoreboard; `status.py` owns that. It
answers one question: did the reply-path optimisations change the replies.

WHAT IT CANNOT TELL YOU
=======================
Nothing here judges counsel QUALITY. A leak-free reply can still be bad advice,
and these stems have no judge scores and no second arm to compare against. Two
stems are also not a controlled pair — `timing-after-one-round` elected 13 tool
calls against the other's 3, so its sessions saw a bigger graph. Treat a moved
count as a question, not a verdict, and read the snippets.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path
from typing import Any

E2E_DIR = Path(__file__).parent
if str(E2E_DIR.parent) not in sys.path:  # `python tests/e2e/read_reply_hygiene.py`
    sys.path.insert(0, str(E2E_DIR.parent))

from e2e.models import SessionRecord
from e2e.scoring import score_internal_prompt_echo, score_machinery_leak

RESULTS = E2E_DIR / "results"


def _payload(stem: str) -> dict[str, Any]:
    path = RESULTS / f"{stem}-runs.json"
    if not path.exists():
        raise SystemExit(f"no such stem: {path}")
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, dict) else {"runs": payload}


def _sessions(payload: dict[str, Any]) -> list[SessionRecord]:
    out: list[SessionRecord] = []
    for run in payload.get("runs", []):
        for session in run.get("sessions", []) or []:
            out.append(SessionRecord.model_validate(session))
    return out


def _solo(session: SessionRecord, turn: Any) -> SessionRecord:
    """The session with exactly one turn, so a scorer answers per-turn.

    `model_copy` rather than a rebuild: the scorers read only `turns`, but a
    hand-built stand-in would silently diverge if they ever read anything else.
    """
    return session.model_copy(update={"turns": [turn]})


def _stats(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    sessions = _sessions(payload)
    leaks = [hit for s in sessions for hit in score_machinery_leak(s)]
    echoes = [hit for s in sessions for hit in score_internal_prompt_echo(s)]

    # Hits are ±40-char windows, and both a machinery TERM and a position LABEL
    # can match inside one sentence — so a single leaking sentence can report as
    # three hits. Turn counts are the comparable figure; hit counts measure
    # density within a turn. Reading 3-vs-5 hits as "two more leaks" when it is
    # one leaking turn against four is the mistake this row exists to prevent.
    def _turns_with(scorer) -> int:
        return sum(1 for s in sessions for t in s.turns if scorer(_solo(s, t)))

    leak_turns = _turns_with(score_machinery_leak)
    echo_turns = _turns_with(score_internal_prompt_echo)

    outcomes: collections.Counter[str] = collections.Counter()
    swallowed = 0
    turn_errors = 0
    replies = 0
    empty_replies = 0
    for session in sessions:
        for turn in session.turns:
            replies += 1
            if not (turn.assistant or "").strip():
                empty_replies += 1
            # `tool_outcomes` entries are `name:ok` or `name:FAILED — reason`.
            for entry in turn.tool_outcomes or []:
                name, _, rest = str(entry).partition(":")
                outcomes[f"{name}:{'ok' if rest == 'ok' else 'FAILED'}"] += 1
            if turn.swallowed_errors:
                swallowed += len(turn.swallowed_errors)
            if turn.error:
                turn_errors += 1

    verdicts: collections.Counter[str] = collections.Counter()
    for run in payload.get("runs", []):
        for verdict in run.get("decision_verdicts", []) or []:
            # `hash:passed` / `hash:failed: reason` — the coherence check's own
            # words. A `failed` is the check WORKING, not a defect.
            verdicts["failed" if ":failed" in str(verdict) else "passed"] += 1

    failed_tools = sorted(k for k in outcomes if k.endswith("FAILED"))
    return (
        {
            "build": (payload.get("build") or {}).get("git_sha", "?")[:7],
            "judge_off": payload.get("judge_off"),
            "sessions": len(sessions),
            "replies scored": replies,
            "empty replies": empty_replies,
            "turns leaking machinery": f"{leak_turns}/{replies}",
            "machinery leak hits": len(leaks),
            "turns echoing the framework": f"{echo_turns}/{replies}",
            "internal-prompt echo hits": len(echoes),
            "tool calls": sum(outcomes.values()),
            "tool calls FAILED": sum(outcomes[k] for k in failed_tools),
            "swallowed errors": swallowed,
            "turns with an error": turn_errors,
            "decisions checked": sum(verdicts.values()),
            "decisions failing coherence": verdicts["failed"],
        },
        leaks,
        echoes,
    )


def main(stems: list[str]) -> None:
    if not stems:
        raise SystemExit(__doc__)
    columns = {stem: _stats(_payload(stem)) for stem in stems}
    keys = list(next(iter(columns.values()))[0].keys())
    width = max(len(k) for k in keys) + 2
    header = "quantity".ljust(width) + "".join(s.rjust(30) for s in stems)
    print(header)
    print("-" * len(header))
    for key in keys:
        row = key.ljust(width)
        for stem in stems:
            row += str(columns[stem][0][key]).rjust(30)
        print(row)

    # The counts are the headline; the snippets are what makes a moved count
    # actionable, so they are printed rather than summarised away.
    for stem in stems:
        _, leaks, echoes = columns[stem]
        for label, hits in (("machinery leak", leaks), ("internal-prompt echo", echoes)):
            if hits:
                print(f"\n{stem} — {label} ({len(hits)}):")
                for hit in hits:
                    print(f"  · {hit!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
