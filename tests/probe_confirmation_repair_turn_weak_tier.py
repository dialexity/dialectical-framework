"""Probe: is the confirmation classifier stochastic on the repair guard's closing turn?

    poetry run pytest tests/probe_confirmation_repair_turn_weak_tier.py --real-llm -s

`test_decision_repair_weak_tier.py` failed 5 of 9 runs on 2026-09-23 with no
Decision node reaching the graph and NONE of the repair seam's logged exits
firing (refusal, empty verdict, unstatable closing), which leaves the classifier
answering "no closing" or "re-affirms" on an unambiguous "write that down as the
decision". This runs `DecisionConfirmationCheck` alone, at the weak tier, on that
exact user turn against a stand-in reply, several times, and prints each verdict.
A probe, not a guard: it asserts nothing but that the check ran.
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.decision_confirmation_check import (
    DecisionConfirmationCheck,
)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from test_decision_repair_weak_tier import TURNS, WEAK_TIER

pytestmark = [pytest.mark.real_llm]

ASSISTANT_REPLY = (
    "Understood. Your decision: buy out your cofounder, structured with a "
    "milestone-tied holdback so the two anchor accounts are handed over before "
    "the final tranche. The cost you are accepting is that the handoff may not "
    "transfer the relationships and revenue could still drop. Recorded."
)


@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_probe_confirmation_on_the_repair_turn(di_container):
    from e2e.modelctx import using_model

    case = Case()
    case.commit()
    verdicts = []
    with scope(case.sid), using_model(di_container, WEAK_TIER):
        for i in range(6):
            check = DecisionConfirmationCheck()
            v = await check.resolve(user_message=TURNS[-1], assistant_message=ASSISTANT_REPLY)
            row = (
                None
                if v is None
                else {
                    "confirmed": v.confirmed,
                    "recordable": v.is_recordable,
                    "reaffirms": v.reaffirms_standing,
                    "question": (v.question or "")[:60],
                    "stance": (v.stance or "")[:60],
                }
            )
            verdicts.append(row)
            print(f"\nrun {i + 1}: {row}")
    assert verdicts
