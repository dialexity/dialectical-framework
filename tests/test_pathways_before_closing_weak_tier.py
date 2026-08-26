"""The tripwire for the OTHER tier-gated ceremony: what a closing may cost.

Real-LLM counterpart to `TestPathwaysBeforeClosing` in
`test_decision_confirmation_repair.py` (which pins the seam DB-free). This file
used to assert that the closing WOVE the tensions it closed over. It no longer
does, and the inversion is the point: per-turn timing on a real provider
(`timing-check-building`, weak tier, 16 turns) measured two turns that made ZERO
tool calls costing 141.9s and 402.0s, of which 127.7s and 387.7s were
`_ensure_pathways_before_closing` — and both landed on the turn immediately
before the closing, the one turn that has to feel exact. Construction moved off
the turn; see that method's docstring for the quality debt this leaves.

So the two things that must hold on the SAME turn are now:

1. a decision the person confirmed reaches the graph, and
2. the closing did not BUILD its way there.

(2) is asserted against what the model itself did, not flatly. `explore` is a
wired tool here, so a weave is legitimate when the MODEL elected it and a defect
when only the closing could have caused it — a distinction the old flat
`assert woven` could not draw. The measurement that makes this worth splitting,
from `tests/e2e/README.md`: `explore` fires in 6/55 weak-tier runs (11%) against
17/25 strong (68%), and in all six cells of `claim2-weak-r7-readside` it fired
ZERO times while `anchor` built 5-7 tensions each. So on this tier the
model-explored branch is the rare one, and the no-build assertion is usually the
live one.

It also still guards the regression the DB-free tests cannot see. Something runs
BETWEEN the confirmation verdict and `RecordDecision`; it used to be a long
graph-writing exploration and is now a pathway LOOKUP, and a read can raise where
a write used to. If it leaves the scope, the DI container or the conversation in a
state `RecordDecision` cannot survive, the record disappears.
`claim2-weak-r8-pathways` / wobble_b closed on an unambiguous "write that down as
the decision" and recorded NOTHING, while a replay of that turn's classifier
(`tests/e2e/probe_confirmation_on_r8_wobble_b.py`) returns
`confirmed=True, is_recordable=True` on this same tier. So the loss is
downstream of the verdict, and this test is where that gets caught.

Weak tier deliberately: at the strong tier the model explores and records on its
own and neither seam fires.

Run with logs, since the failure mode is a swallowed fail-soft exception:

    poetry run pytest tests/test_pathways_before_closing_weak_tier.py \
        --real-llm -s -o log_cli=true -o log_cli_level=INFO
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.decision_repository import \
    DecisionRepository
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository
from dialectical_framework.graph.scope_context import scope

pytestmark = [pytest.mark.real_llm, pytest.mark.seam]

#: Kept literal, not read from bench config: this is a framework test and must
#: not start passing because someone raised the bench's idea of "weak".
WEAK_TIER = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Two DIFFERENT tensions before the closing — a pathway needs a second
#: opposition to be an arrangement rather than one tension restated, so a script
#: that only ever surfaces one cannot exercise the seam.
TURNS = [
    (
        "My cofounder has checked out. Still on 50% equity, hasn't shipped in "
        "four months, and I'm carrying the company. I'm thinking of buying "
        "him out."
    ),
    (
        "Two complications. Our two biggest customers came through his "
        "relationships — maybe 60% of revenue — so if he leaves badly I own "
        "100% of nothing. And separately, I'd be self-funding the buyout, "
        "which means burning the runway that pays for the hire I actually "
        "need."
    ),
    (
        "Yeah, that lands. I'm doing the buyout — settled, not "
        "second-guessing. Write that down as the decision, because I don't "
        "want to relitigate it every time his notes annoy me."
    ),
]


class TestWeakTierClosesWithoutBuilding:
    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    # Deliberately NOT @traced: it serializes the test's args as span input and
    # `di_container` is cyclic — the serializer recurses forever and HANGS
    # (CLAUDE.md, Observability).
    async def test_a_confirmed_decision_leaves_a_record_without_building_one(
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
            perspectives = PerspectiveRepository().find_all_active()
            repo = PerspectiveRepository()
            woven = [p for p in perspectives if repo.is_in_use_by_cycle(p)]
            # Read inside the scope: `grounds` is a live relationship query.
            grounds = {d.short_hash: len(list(d.grounds.all())) for d in decisions}

        print(f"\nTool calls per turn: {tool_calls_per_turn}")
        print(f"Perspectives: {len(perspectives)} (woven into a cycle: {len(woven)})")
        print(f"Active decisions: {len(decisions)}")
        for d in decisions:
            print(f"  [[{d.short_hash}]] {d.intent} -> {d.stance}")
            print(f"      grounds: {grounds[d.short_hash]}")
        model_explored = any("explore" in calls for calls in tool_calls_per_turn)
        print(f"Explored by the model itself: {model_explored}")

        # (1) The record. Asserted FIRST and separately: whatever sits between
        # the verdict and `RecordDecision` must not cost the person the one thing
        # they were promised. That slot used to hold a long weave and now holds a
        # pathway lookup, so the assertion outlives the change.
        assert decisions, (
            "The person explicitly confirmed a decision and no Decision node "
            "reached the graph. The confirmation classifier is NOT the suspect "
            "— it returns confirmed=True on this exact turn at this exact tier "
            "(tests/e2e/probe_confirmation_on_r8_wobble_b.py). Look for a "
            "fail-soft exception logged between the verdict and RecordDecision, "
            "which is where the pathway LOOKUP now sits."
        )

        # (2) Who built, if anyone. No skip on perspective count any more: under
        # the read-only closing, "nothing was woven" is assertable however few
        # tensions the anchor prompt happened to produce. The old skip fired on
        # this test's first run and made it a report on anchor productivity.
        if model_explored:
            # The model elected `explore`, so a weave is its work, not the
            # closing's — and this is the branch that proves the read side
            # reaches real structure through a real conversation.
            assert woven, (
                "The model called `explore` itself and NOT ONE perspective is "
                "in a cycle — the tool reported success and left nothing "
                "`is_in_use_by_cycle` can see. The closing's only source of a "
                "ground is that same read, so this breaks grounding for every "
                "decision, not just this one."
            )
        else:
            assert not woven, (
                f"No turn called `explore`, yet {len(woven)} perspective(s) are "
                "woven into a cycle. Nothing but the closing could have built "
                "that, so construction is back on the person's wait — the 387.7s "
                "turn. Check `_ensure_pathways_before_closing` for a re-added "
                "`run_exploration` call."
            )
            # The priced debt this branch leaves: with nothing woven there is no
            # pathway to ground on, so the closing rests on tensions alone —
            # the -0.25-vs--0.69 quality cost recorded in
            # `_ensure_pathways_before_closing`. Printed, NOT asserted: grounds
            # legitimately target perspectives and statements as well as
            # pathways (`record_decision.py` — the framework-derived path grounds
            # the perspective), so a count of zero is not what "no pathway" looks
            # like and `grounds == 0` would be a false alarm. The precise
            # behaviour is pinned DB-free in `test_decision_confirmation_repair.py`,
            # including the WARNING this case must log.
