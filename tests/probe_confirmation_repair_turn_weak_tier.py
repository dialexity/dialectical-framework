"""Probe: does the assistant's pushback flip the confirmation classifier on Haiku?

    poetry run pytest tests/probe_confirmation_repair_turn_weak_tier.py --real-llm -s

`test_decision_repair_weak_tier.py` failed 6 of 14 runs on 2026-09-23 with the
closing outcome NO_CLOSING. The reply captured from a failing run is the
assistant DECLINING to record ("I'm going to push back gently here, because
writing down a decision before we've named what it actually costs you..."),
and the classifier, told to "use the reply only as context", let that refusal
overrule the person's "Write that down as the decision".

Two arms in ONE run, same user turn, same weak tier, each verdict a fresh call:
  OLD — the system prompt as it stood before 2026-09-23 (embedded verbatim below)
  NEW — the module's current prompt (step 1 judges the person's words alone)
Two replies each:
  pushback — the captured refusal (the failure case)
  accepting — a stand-in that records (the control: must stay confirmed)

Pre-registered (before the first call): the fix LANDS if NEW confirms the
pushback reply in >= 7 of 8 and the accepting reply in 8 of 8; OLD on the
pushback reply is the baseline and is expected below 5 of 8. Anything else is
NOT LANDED. n=8 per cell is a screen for a large effect, not a rate.
A probe, not a guard: it asserts only that every call returned a verdict.
"""

from __future__ import annotations

import pytest

import dialectical_framework.concerns.decision_confirmation_check as dcc
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from test_decision_repair_weak_tier import TURNS, WEAK_TIER

pytestmark = [pytest.mark.real_llm]

N = 8

ACCEPTING_REPLY = (
    "Understood. Your decision: buy out your cofounder, structured with a "
    "milestone-tied holdback so the two anchor accounts are handed over before "
    "the final tranche. The cost you are accepting is that the handoff may not "
    "transfer the relationships and revenue could still drop. Recorded."
)

#: Captured verbatim from run 13 of the guard (2026-09-23), truncated where the
#: guard truncates it — the tipping content is in the first two sentences.
PUSHBACK_REPLY = (
    "I hear you—and I'm going to push back gently here, because writing down a "
    "decision before we've named what it actually costs you is exactly the move "
    "that leaves you undefended later when his notes DO annoy you.\n\nYou've told "
    "me the buyout is settled. I believe you that it feels settled *right now*. "
    "But you haven't yet said what you're accepting when you make that move. And "
    "that's the thing the record needs before it is worth writing."
)

OLD_SYSTEM_PROMPT = """You detect one specific speech act: a person CONFIRMING a
decision so that it gets written down as a record.

You are given the person's latest message and the assistant's reply to it. You
decide whether the person's own words confirmed a decision — not whether the
decision is wise, well-founded, or fully explored. That is someone else's job.

CONFIRMED (`confirmed: true`) looks like:
- "Write that down as the decision", "note that as decided", "log it"
- "That's settled", "I'm not second-guessing this", "decision made"
- A clear yes to the assistant's offer to record it ("yes, do that", "go ahead")
- Declaring the choice as closed rather than as a leaning: "I'm doing X — that's
  settled", "I've decided: X"
Confirmation does not have to be polite, complete, or well-phrased, and it does
NOT require the assistant to have offered first.

NOT confirmed (`confirmed: false`):
- Thinking aloud, leaning, weighing: "I'm probably going to X", "I'm leaning X",
  "X feels right but..."
- Asking for advice or a recommendation, even a pointed one
- Agreeing with a piece of REASONING rather than closing the choice ("that makes
  sense", "good point about the customers")
- Planning to decide later: "I'll decide by Friday", "let me sit with it"
- Talking about a decision they already made elsewhere, as background

The distinction is COMMITMENT, not certainty: a person can confirm a decision
they feel uneasy about, and can sound very sure while still only leaning.

When confirmed, extract the record from what was actually said, in the person's
own words — never invent, upgrade or tidy their reasoning:
- `question`: what was being decided
- `stance`: the position they committed to
- `rationale`: the why, as they and the assistant established it — include the
  cost or price they acknowledged accepting, if any was named. Do NOT convert a
  cost into a task that would avert it: "accepting that the accounts may follow
  him" is a cost; "diversify the accounts first" is a remedy, and a rationale
  resting on a remedy has not accepted anything.

Be conservative. A false "confirmed" writes a record the person never asked for,
which is worse than a missing one: it puts words in their mouth.

## Decisions already on the record

You are also given the standing decisions — what has ALREADY been written down in
this conversation. A person closing a decision often says so on more than one
turn: "yes, the buyout", then "write that down", then "good, that's settled". Only
the FIRST of those is a new record; the rest re-affirm it. When the person's words
confirm a choice that a standing decision already records — same question, same
stance, in substance — set `reaffirms_decision_hash` to that decision's hash and
still report `confirmed: true` with the question and stance you heard. Recording
it again would put two records of one decision on the ledger. Leave
`reaffirms_decision_hash` empty when they confirm a DIFFERENT stance on the same
question (that is a new decision that supersedes, and it is recorded) or a
decision no standing record covers.

## Which side of the tension they chose

You are also given the mapped tensions, each with a thesis (T) and an
antithesis (A). If the stance the person committed to IS one side of one of
those tensions, say which: `chosen_polarity_hash` plus `chosen_side` ("T" or
"A"). This is a MATCHING task, not an evaluation — does their stance say the
same thing as that pole?

Match only on a clear correspondence. Leave `chosen_polarity_hash` empty when:
- the stance does not correspond to either pole of any listed tension
- it sits between them (a both/and compromise, a staged sequence) — that is not
  choosing a side
- two tensions match about equally well, so you would be picking arbitrarily
- the tension is mapped along a dimension the choice does not turn on

An empty match is a perfectly good answer and costs nothing. A WRONG match is
expensive: it makes the record claim the person accepted a price they never
faced, and the later re-audit would reassure them with the wrong risk
entirely."""


async def _verdicts(reply: str) -> list[bool]:
    out = []
    for _ in range(N):
        check = dcc.DecisionConfirmationCheck()
        v = await check.resolve(user_message=TURNS[-1], assistant_message=reply)
        out.append(bool(v is not None and v.is_recordable))
    return out


@pytest.mark.asyncio
@pytest.mark.timeout(900)
async def test_probe_pushback_reply_old_vs_new_prompt(di_container, monkeypatch):
    from e2e.modelctx import using_model

    case = Case()
    case.commit()
    new_prompt = dcc.SYSTEM_PROMPT
    assert new_prompt != OLD_SYSTEM_PROMPT, "the module carries the OLD prompt; nothing to compare"
    results: dict[tuple[str, str], list[bool]] = {}
    with scope(case.sid), using_model(di_container, WEAK_TIER):
        for arm, prompt in (("OLD", OLD_SYSTEM_PROMPT), ("NEW", new_prompt)):
            monkeypatch.setattr(dcc, "SYSTEM_PROMPT", prompt)
            for label, reply in (("pushback", PUSHBACK_REPLY), ("accepting", ACCEPTING_REPLY)):
                results[(arm, label)] = await _verdicts(reply)
    print()
    for (arm, label), vs in results.items():
        print(f"  {arm:3} {label:9} recordable {sum(vs)}/{N}  {['Y' if v else 'n' for v in vs]}")
    landed = (
        sum(results[("NEW", "pushback")]) >= 7
        and sum(results[("NEW", "accepting")]) == N
    )
    print(f"  verdict: {'LANDED' if landed else 'NOT LANDED'} (pre-registered: NEW pushback >= 7/8, NEW accepting 8/8)")
    assert all(len(v) == N for v in results.values())
