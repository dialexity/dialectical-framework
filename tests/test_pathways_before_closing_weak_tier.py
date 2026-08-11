"""The tripwire for the OTHER tier-gated ceremony: pathways before a closing.

Real-LLM counterpart to `TestPathwaysBeforeClosing` in
`test_decision_confirmation_repair.py` (which pins the seam DB-free). It asserts
two things at once, because the whole point of the seam is that they must both
hold on the SAME turn:

1. a decision the person confirmed reaches the graph, and
2. the tensions it closed over got woven into an arrangement.

The measurement that motivates (2), from `tests/bench/README.md`: `explore` fires
in 6/55 weak-tier runs (11%) against 17/25 strong (68%), and in all six cells of
`claim2-weak-r7-readside` it fired ZERO times while `anchor` built 5-7 tensions
each. Decisions closed over a graph with no nexus, no cycle, no wheel, no
transformation and no synthesis — so the arm the bench scored was a prompted
model with tetrads bolted on.

It also guards a regression the seam can plausibly cause and the DB-free tests
cannot see: pathway construction now runs BETWEEN the confirmation verdict and
`RecordDecision`, and it is a long, many-call, graph-writing operation. If it
leaves the scope, the DI container or the conversation in a state
`RecordDecision` cannot survive, the record disappears — reintroducing exactly
the failure the repair exists to prevent, on the exact path meant to enrich it.
`claim2-weak-r8-pathways` / wobble_b closed on an unambiguous "write that down as
the decision" and recorded NOTHING, while a replay of that turn's classifier
(`tests/bench/probe_confirmation_on_r8_wobble_b.py`) returns
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

pytestmark = pytest.mark.real_llm

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


class TestWeakTierClosesOnPathways:
    @pytest.mark.asyncio
    @pytest.mark.timeout(2400)
    # Deliberately NOT @traced: it serializes the test's args as span input and
    # `di_container` is cyclic — the serializer recurses forever and HANGS
    # (CLAUDE.md, Observability).
    async def test_a_confirmed_decision_leaves_a_record_and_a_pathway(
        self, di_container
    ):
        from bench.modelctx import using_model

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

        print(f"\nTool calls per turn: {tool_calls_per_turn}")
        print(f"Perspectives: {len(perspectives)} (woven into a cycle: {len(woven)})")
        print(f"Active decisions: {len(decisions)}")
        for d in decisions:
            print(f"  [[{d.short_hash}]] {d.intent} -> {d.stance}")
        model_explored = any("explore" in calls for calls in tool_calls_per_turn)
        print(f"Explored by the model itself: {model_explored}")

        # (1) The record. Asserted FIRST and separately from the pathway: if the
        # seam's exploration is what costs us the record, the two assertions
        # failing together is the signature, and the record is the one that
        # must never be traded away for the other.
        assert decisions, (
            "The person explicitly confirmed a decision and no Decision node "
            "reached the graph. The confirmation classifier is NOT the suspect "
            "— it returns confirmed=True on this exact turn at this exact tier "
            "(tests/bench/probe_confirmation_on_r8_wobble_b.py). Look for a "
            "fail-soft exception logged between the verdict and RecordDecision, "
            "which is where pathway construction now sits."
        )

        # (2) The pathway. Below two tensions the seam correctly does nothing,
        # so a run where the model surfaced only one opposition cannot judge it
        # — skip rather than fail, or this becomes a test of the anchor prompt's
        # productivity instead of the seam.
        if len(perspectives) < 2:
            pytest.skip(
                f"Only {len(perspectives)} perspective(s) mapped — one tension "
                "has no arrangement to enumerate, so the seam is correct to "
                "stay silent and there is nothing here to assert."
            )

        assert woven, (
            f"A decision closed over {len(perspectives)} mapped tensions and "
            "NOT ONE is in a cycle: the decision rests on tensions alone, which "
            "is what the engine prompt forbids and what the weak tier did in "
            "6/6 bench cells. Either the seam did not fire or its exploration "
            "failed fail-soft — check the log for 'Pathway construction'."
        )
