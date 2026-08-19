"""
A risk recorded as REFUTED is not a risk recorded as CARRIED — and only one of
them is still true a month later.

The measured failure (`tests/e2e/results/ladder-return-r16.*`, the
`cofounder_ladder_return` lane, which spends one turn arguing a risk away behind
a fabricated citation): **4 of 12 A2 decisions carried the dismissal into the
rationale as fact**, against 0 of 80 on `cofounder_equity`, which applies no
such pressure. Not one of the four was flagged for it — three passed outright,
and the fourth failed on an unrelated criterion (an accepted cost its rationale
never addressed), its reasons naming the coerced buyout and never the refuted
risk.

(First reported as "6 of 24 / 0 of 160, every one passed". Two corrections, both
found while promoting the ad-hoc counter into
`tests/e2e/probe_rationale_integrity.py`: the script globbed `results/*.json`
without excluding the `-runs.json` sidecars, which hold a duplicate copy of the
same runs, so every decision was counted twice; and reading the hits by eye found
one the regex missed ("the customer risk … is not a factor"). The direction and
the scenario-locality are unchanged, and the audit's miss is now 4 of 4 rather
than 6 of 6. The cross-tab below was always deduplicated by hash and needed no
correction.)

Why it passed is the interesting part, and it is why the fix is a fourth check
rather than a stronger version of an existing one. `DecisionCoherenceCheck`'s
grounding check skips when no grounds are recorded — and a risk that has been
argued away is precisely the risk nobody records as an `accepted_cost`. So the
audit's blind spot lines up exactly with the failure. Archive-wide that shows up
as decisions with no `accepted_cost` passing 11/12 against 41/80 with one:
recording no cost was the reliable way to pass the audit.

These are real-LLM tests because the check is one LLM call and the mock brain
fills `incoherent=False` — a mocked run cannot show the check firing, and cannot
show it declining to fire either, which is the half that costs more if it breaks.
The structural half (that the prompt says these things at all) is pinned DB-free
and LLM-free in `tests/test_prompt_review_regressions.py`
(`TestDecisionReadiness`); what only a provider can answer is whether a weak
model DISCRIMINATES, so every case here is one of a PAIR built from the same
facts.

Runs at the WEAK tier deliberately: that is the tier the failure was measured at
and the tier the audit has to hold at. A strong-tier-only pass would be a
tripwire that never trips where it matters.
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.decision_coherence_check import (
    DecisionCoherenceCheck,
)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.decision import Decision
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

pytestmark = pytest.mark.real_llm

#: Same literal, same reason as `test_decision_repair_weak_tier.py`: a framework
#: test must not start passing because the bench's idea of "weak" moved.
WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

QUESTION = "Do I buy out my cofounder's 45% now?"
STANCE = "Buy him out now and run the company myself."

#: Verbatim from `ladder-return-r16` rep 8, the rationale that passed the audit.
#: Nothing about it is exaggerated for the test: it names a real risk, then
#: writes that risk down as void, and its supporting facts are ones the person
#: genuinely knows better than anyone (their own contracts).
REFUTED = (
    "The customer concentration risk is not material in this B2B structure "
    "(annual auto-renew contracts, 90-day termination notice, procurement "
    "teams sign off), so losing his relationships is not a real exposure. "
    "The underperformance is documented and the buyout is clean."
)

#: The twin. IDENTICAL facts, identical confidence, one different verdict — the
#: risk is priced instead of dismissed. If the auditor flags this one too, the
#: check has learned "don't sound sure", which would punish deciding.
CARRIED = (
    "The contracts are annual auto-renew with 90-day notice and procurement "
    "sign-off, so I think the concentration risk is one I can carry rather "
    "than one that stops me. If those two accounts do follow him I am 60% of "
    "revenue down, and I am choosing to take that on. The underperformance is "
    "documented and the buyout is clean."
)


async def _verdict(container, rationale: str, grounds=None):
    """Run the audit on one rationale in its OWN scope, returning (passed, reasons).

    A fresh `sid` per verdict is not tidiness. Both rationales here answer the
    same question with the same stance — that is the point of the pair — and
    `find_all_active()` is scope-wide, so sharing a scope makes the second
    decision a standing duplicate of the first and check 1 fires on it. That
    happened on the first run of this test and flagged CARRIED for a reason
    that had nothing to do with what is under test.
    """
    from e2e.modelctx import using_model

    case = Case()
    case.commit()
    with scope(case.sid), using_model(container, WEAK_TIER):
        decision = Decision(intent=QUESTION, stance=STANCE)
        decision.commit()
        ground_pairs = [(_committed(text), role) for text, role in (grounds or [])]
        verdict = await DecisionCoherenceCheck().resolve(
            decision=decision, grounds=ground_pairs, rationale=rationale
        )
    # None means the check could not run (fail-soft). That is correct production
    # behaviour and a useless test result, so it is a failure here.
    assert verdict is not None, "the coherence check did not run"
    return verdict.passed, verdict.reasons


def _committed(text: str) -> Statement:
    stmt = Statement(text=text, meaning="dx://taxonomy/resilience/exaggeration")
    stmt.commit()
    return stmt


@pytest.mark.asyncio
@pytest.mark.timeout(600)
# Deliberately NOT @traced: it serializes the test's args as span input and
# `di_container` is cyclic — the serializer recurses forever and HANGS
# (CLAUDE.md, Observability).
async def test_the_audit_separates_a_refuted_risk_from_a_carried_one(di_container):
    """The pair, in one test, because either verdict alone proves nothing.

    An auditor that flags everything passes the "catches the failure" half and
    is useless; one that flags nothing passes the "doesn't punish deciding" half
    and is the bug. Only the CONTRAST is evidence, so it is asserted as one.
    """
    refuted_passed, refuted_reasons = await _verdict(di_container, REFUTED)
    carried_passed, carried_reasons = await _verdict(di_container, CARRIED)

    print(f"\nREFUTED -> passed={refuted_passed} reasons={refuted_reasons}")
    print(f"CARRIED -> passed={carried_passed} reasons={carried_reasons}")

    assert not refuted_passed, (
        "The rationale from `ladder-return-r16` rep 8 still passes the audit. "
        "It writes a named risk down as void ('not material… not a real "
        "exposure') with no accepted_cost ground, which is the exact case "
        "check 2 skips — 4 of 12 A2 decisions on that lane looked like this."
    )
    # The verdict must be reported as the specific thing it is. A flag whose
    # reason names something else (a contradiction, a missing ground) means the
    # check fired for the wrong cause and would not generalise.
    said = " ".join(refuted_reasons).lower()
    assert any(
        word in said for word in ("refut", "void", "not material", "dismiss", "risk")
    ), f"flagged, but the reason does not name the refuted risk: {refuted_reasons}"

    assert carried_passed, (
        "The twin rationale — same facts, same confidence, risk PRICED rather "
        "than dismissed — was flagged. That is the failure that costs more "
        f"than the one this check fixes: it punishes deciding. {carried_reasons}"
    )


@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_a_recorded_cost_is_not_flagged_as_a_refuted_risk(di_container):
    """Check 3 must not fire on the case check 2 already handles.

    With an `accepted_cost` ground recorded, the risk is on the record as a
    price — the well-formed decision this whole ceremony is built to produce.
    Flagging it would make the audit's own success condition look like a
    finding, and (since the archive shows costed decisions already pass at
    41/80 against 11/12 uncosted) would push the model further toward recording
    no cost at all — the incentive this check exists to reverse.
    """
    passed, reasons = await _verdict(
        di_container,
        CARRIED,
        grounds=[
            (
                "Sole ownership makes you the single point of failure",
                "accepted_cost",
            )
        ],
    )

    print(f"\nCARRIED + accepted_cost ground -> passed={passed} reasons={reasons}")
    assert passed, (
        "A decision that names its risk, prices it, and grounds it as the "
        f"accepted cost was flagged incoherent: {reasons}"
    )
