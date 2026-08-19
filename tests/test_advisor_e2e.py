"""
End-to-end smoke test for the Advisor's framework hand-off.

Graph-building is model-initiated (via the ingest/anchor/explore tools, as
steered by the system prompt). This test is the A2 != A1 instrumentation
from the judged-eval design (`tests/e2e/README.md`, "What keeps the
comparison honest"):
after a multi-turn counsel-shaped conversation, a committed
graph must exist — an Advisor whose graph is empty after a rich conversation
has silently degraded to a bare persona-prompted model.

If this test fails, that is SIGNAL, not flake: the prompt is under-steering
tool use on the current model and needs attention.
"""

from __future__ import annotations

import pytest
from conftest import traced

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
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


class TestAdvisorFrameworkHandoff:
    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    @traced
    async def test_advisor_multiturn_hands_off_to_framework(self):
        case = Case()
        case.commit()

        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_PERSONA)

            tool_calls_per_turn: list[list[str]] = []
            for turn in TURNS:
                reply = await advisor.chat(turn)
                assert isinstance(reply, str) and reply.strip()
                tool_calls_per_turn.append(
                    list(advisor._conversation.last_tool_calls)
                )

            perspectives = PerspectiveRepository().find_all_active()

            # Judged-eval instrumentation: which tools carried the hand-off.
            print(f"\nTool calls per turn: {tool_calls_per_turn}")
            print(f"Committed active perspectives: {len(perspectives)}")

            assert perspectives, (
                "After a multi-turn counsel-shaped conversation the model "
                "called no graph-building tools (or they produced nothing) — "
                "the Advisor degraded to a bare persona-prompted model "
                "(A2->A1 collapse, see tests/e2e/README.md). "
                "Tool calls per turn: "
                f"{tool_calls_per_turn}"
            )
