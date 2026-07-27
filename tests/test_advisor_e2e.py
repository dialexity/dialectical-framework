"""
End-to-end smoke test for the Advisor's guaranteed graph-building.

The code-level invariant under test: after a multi-turn counsel-shaped
conversation, a committed graph EXISTS — regardless of whether the model
chose to call graph-building tools (model-initiated path) or the background
analysis hook fired (guaranteed path).

This doubles as the A2 != A1 instrumentation required by issue #57: an
Advisor arm whose graph is empty after a rich conversation would silently
degrade to a bare persona-prompted model.
"""

from __future__ import annotations

import pytest
from conftest import traced

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import COUNSELOR_APP
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)
from dialectical_framework.graph.scope_context import scope

pytestmark = pytest.mark.real_llm


TURNS = [
    (
        "My son is 16 and I found out he's been skipping school to work on "
        "his startup idea. Part of me is furious — school matters — but "
        "part of me remembers being his age and hating every minute of it."
    ),
    (
        "The thing is, his grades were never great anyway, but this project "
        "of his actually has paying customers. My wife says we must shut it "
        "down until he graduates. I'm torn between backing his drive and "
        "protecting his future."
    ),
]


class TestAdvisorGuaranteedGraphBuilding:
    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    @traced
    async def test_advisor_multiturn_builds_graph_regardless_of_tools(self):
        case = Case()
        case.commit()

        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_APP)

            tool_calls_per_turn: list[list[str]] = []
            for turn in TURNS:
                reply = await advisor.chat(turn)
                assert isinstance(reply, str) and reply.strip()
                tool_calls_per_turn.append(
                    list(advisor._conversation.last_tool_calls)
                )
                # Drain so this turn's analysis lands before the next turn
                # (and before assertions).
                await advisor.flush_analysis()

            perspectives = PerspectiveRepository().find_all_active()

            # Instrumentation for issue #57: record which path built the graph.
            print(f"\nTool calls per turn: {tool_calls_per_turn}")
            print(f"Committed active perspectives: {len(perspectives)}")

            assert perspectives, (
                "After a multi-turn counsel-shaped conversation, a committed "
                "graph must exist — via model tool calls or the background "
                f"hook. Tool calls per turn were: {tool_calls_per_turn}"
            )
