"""Does the Advisor actually keep the machinery quiet? Asked of the REPLY.

The silent-framework contract is asserted all over
`test_prompt_review_regressions.py` — but only ever as "the prompt contains the
ban". `claim2-weak-r10` shows what that is worth: 6 A2 cells printed framework
vocabulary at the person 15 times (against 1 in A1.7), including

    **T+: Solo leadership with unified strategic vision** — Yes, this is real.
    ...which the framework flagged as avoidance, not acceptance.

with every prompt test green. A2 is the consultant *replacement*; a consultant
who narrates their own method has stopped being one, and the bench's
`conversational_fit` (-1.33) was measuring the leak rather than the counsel.

Weak tier deliberately: format imitation is a small-model failure, and the
strong tier already paraphrases. Uses the SAME detector as the bench
(`score_machinery_leak`) so the tripwire and the report can never disagree.

    poetry run pytest tests/test_machinery_silence_weak_tier.py --real-llm -s
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

pytestmark = [pytest.mark.real_llm, pytest.mark.seam]

WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: The bench persona verbatim in spirit: warm, direct, and granting NO
#: terminology disclosure — so any framework term in a reply is a violation.
PERSONA = """## Persona

You are a thoughtful advisor helping someone navigate a difficult situation.
You are warm but direct. You take their intelligence seriously — no
hand-holding, no platitudes."""

#: Turn 3 is the one that leaked in r10: enough mapped structure to be tempted
#: to lay it out, and an explicit request for the shape of the thing.
TURNS = [
    (
        "My cofounder has checked out — still on 50%, hasn't shipped in four "
        "months, and I'm carrying the company. I'm thinking of buying him out."
    ),
    (
        "Our two biggest customers came through his relationships, maybe 60% of "
        "revenue. And I'd be self-funding the buyout out of the runway that "
        "pays for the hire I actually need."
    ),
    "Lay it out for me — what am I actually trading off here?",
]


class TestTheMachineryStaysQuiet:
    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    # KNOWN OPEN DEFECT, not a flake. The counter-example added to
    # `_HOW_YOU_SPEAK` took the measured leak from 15 hits across 6 cells to 1 in
    # 3 turns — the labelled-table form and "the framework flagged" are gone, and
    # what survives is a bare position label in running prose ("you're stuck in
    # exactly the A- position"). It is xfail rather than a lowered threshold
    # because the contract IS zero: `strict=False` so an XPASS is reported
    # instead of failing, since a prompt-level fix cannot be reliable at this
    # tier by construction.
    #
    # The durable fix is a code seam, per the project's own "prune, don't
    # instruct" rule — the same reasoning that made `record_decision` a
    # post-turn repair after three rounds of prompt strengthening moved it 0/6.
    # Deliberately NOT attempted here: the only seam available rewrites the
    # person-facing reply, and a silent rewrite that changes what the counsel
    # MEANS is a worse defect than the label it removes ("stuck in exactly the
    # A- position" cannot be repaired by deletion — it needs the statement text
    # the label refers to). That needs its own design, not a regex.
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Bare position labels still reach the person at the weak tier "
            "(15 -> 1 after the prompt counter-example). Needs a code seam, "
            "not more prompt text."
        ),
    )
    async def test_no_framework_vocabulary_reaches_the_person(self, di_container):
        from e2e.modelctx import using_model
        from e2e.scoring import score_machinery_leak
        from e2e.models import SessionRecord, TurnRecord

        case = Case()
        case.commit()

        replies: list[str] = []
        with scope(case.sid), using_model(di_container, WEAK_TIER):
            advisor = Advisor(app_preamble=PERSONA)
            for turn in TURNS:
                replies.append(await advisor.chat(turn))

        session = SessionRecord(
            label="decide",
            turns=[
                TurnRecord(index=i, user=u, assistant=a)
                for i, (u, a) in enumerate(zip(TURNS, replies))
            ],
        )
        leaks = score_machinery_leak(session)

        for i, reply in enumerate(replies):
            print(f"\n--- reply {i} ---\n{reply}")
        print(f"\nleaks: {len(leaks)}")
        for snippet in leaks:
            print(f"   ...{snippet}...")

        assert not leaks, (
            f"{len(leaks)} framework term(s) reached the person. The persona "
            "grants no terminology disclosure, so the silent-framework contract "
            "is broken and any conversational_fit score over this transcript is "
            "measuring the leak, not the counsel.\n"
            + "\n".join(f"  - {s}" for s in leaks)
        )
