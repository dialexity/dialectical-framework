"""
The tripwire for the tier-gated ceremony: a weak model must still leave a record.

This is the real-LLM counterpart to `test_decision_confirmation_repair.py` (which
pins the seam DB-free). It reproduces the exact measured failure and asserts the
repair closes it.

The measurement, from `tests/e2e/README.md`:

| tier | model | runs recording >=1 decision |
|------|-------|-----------------------------|
| strong | claude-sonnet-5 | 6/6 |
| weak | claude-haiku-4-5 | **0/6** |

The weak tier's failure was identical every run: asked to "write that down as the
decision", it produced a formatted "Your Decision" section in prose with
`tool_calls == []`. The person was told it was recorded. It was not.

Runs at the WEAK tier deliberately — at the strong tier the model calls
`record_decision` itself and the repair never fires, so a strong-tier version of
this test would pass without exercising anything.

If this test fails, a Decision node did not reach the graph after an explicit
confirmation, which is the one failure the record exists to prevent.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.rendering import decision_ground_line
from dialectical_framework.graph.repositories.decision_repository import (
    DecisionRepository,
)
from dialectical_framework.graph.scope_context import scope

pytestmark = [pytest.mark.real_llm, pytest.mark.seam]

#: The tier the ceremony provably fails at without the repair. Kept literal
#: rather than imported from bench config: this is a framework test, and it must
#: not start passing because someone raised the bench's idea of "weak".
WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Condensed from the bench's `cofounder_equity` transcript — the beats that
#: matter are a real deliberation followed by an UNAMBIGUOUS confirmation.
TURNS = [
    (
        "My cofounder has checked out. He's still on 50% equity but hasn't "
        "shipped anything in four months, and I'm carrying the whole company. "
        "I'm thinking about buying him out."
    ),
    (
        "The complication is that our two biggest customers came through his "
        "relationships. They're maybe 60% of revenue. If he leaves badly, "
        "I could lose them and then I own 100% of nothing."
    ),
    (
        "Yeah, that lands. I'm doing the buyout — that's settled, I'm not "
        "second-guessing it. Write that down as the decision, because I don't "
        "want to relitigate this every time his notes annoy me."
    ),
]


class TestWeakTierStillLeavesARecord:
    @pytest.mark.asyncio
    @pytest.mark.timeout(900)
    # Deliberately NOT @traced: it serializes the test's args as span input, and
    # `di_container` is cyclic — the serializer recurses forever and HANGS
    # (CLAUDE.md, Observability). The Advisor's own spans still trace.
    async def test_confirmed_decision_reaches_the_graph_on_a_weak_model(
        self, di_container
    ):
        from e2e.modelctx import using_model

        case = Case()
        case.commit()

        with scope(case.sid), using_model(di_container, WEAK_TIER):
            advisor = Advisor(app_preamble=COUNSELOR_PERSONA)

            tool_calls_per_turn: list[list[str]] = []
            for turn in TURNS:
                reply = await advisor.chat(turn)
                assert isinstance(reply, str) and reply.strip()
                tool_calls_per_turn.append(
                    list(advisor._conversation.last_tool_calls)
                )

            decisions = DecisionRepository().find_all_active()
            ground_lines = [
                decision_ground_line(node, getattr(rel, "role", None))
                for d in decisions
                for node, rel in d.grounds.all()
            ]

        # Instrumentation first — a failure here should say WHY, and whether
        # the model recorded it itself or the repair did is the whole point.
        print(f"\nTool calls per turn: {tool_calls_per_turn}")
        print(f"Active decisions: {len(decisions)}")
        for d in decisions:
            print(f"  [[{d.short_hash}]] {d.intent} -> {d.stance}")
        for line in ground_lines:
            print(f"  {line}")
        model_called_it = "record_decision" in tool_calls_per_turn[-1]
        print(f"Recorded by the model itself: {model_called_it}")
        print(f"Recorded by the repair seam: {not model_called_it}")

        assert decisions, (
            "The person explicitly confirmed a decision and NO Decision node "
            "reached the graph. Either the confirmation check failed to detect "
            "an unambiguous 'write that down as the decision', or the repair "
            "did not run. Measured baseline without the repair: 0/6 at this "
            "tier — see tests/e2e/README.md."
        )

        # The record must carry the person's actual choice, not a paraphrase of
        # the conversation: a record naming the wrong stance is worse than none.
        stances = " ".join((d.stance or "").lower() for d in decisions)
        assert "buy" in stances or "buyout" in stances, (
            f"A decision was recorded but its stance does not name the choice "
            f"the person confirmed (buying the cofounder out): {stances!r}"
        )

        # Whether a cost ground attaches is NOT asserted: it requires the model
        # to have anchored a tension whose pole the stance actually matches, and
        # an unmatched stance grounding nothing is correct behaviour, not a
        # regression. What IS asserted is the invariant that holds whenever one
        # does attach — a cost is a price, so it can never be a plus (a plus is
        # a goal or an obligation, i.e. a remedy). A ground landing on T+/A+
        # would be the defect the bench caught in 4 of 6 strong-tier runs.
        costs = [line for line in ground_lines if "accepted cost:" in line]
        for line in costs:
            assert " (T+)" not in line and " (A+)" not in line, (
                f"An accepted_cost ground names a remedy, not a price: {line!r}"
            )
