"""
Tests for the Explorer↔Advisor mode toggle (handover contract).

An exploration session has two registers — operator mode (Explorer) and
counsel mode (Advisor pinned to the same nexus). The toggle is a handover of
the SAME conversation between two heads, driven by the host:

    advisor  = Advisor(app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                       nexus_hash=explorer.nexus_hash,
                       messages=explorer.messages)
    explorer = Explorer(nexus_hash=nx,
                        app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
                        messages=advisor.messages)

Contract under test:
1. Constructing either head replaces ONLY the system prompt (messages[0]);
   the rest of the history survives verbatim.
2. The nexus pin survives the round trip.
3. (real-llm) A handed-over history containing tool-use blocks from tools
   NOT in the current head's tool set is accepted by the provider on replay.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.apps import (NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                                               NAVIGATOR_APP_ADVANCED_TOGGLE)
from dialectical_framework.agents.explorer.explorer import Explorer
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.scope_context import scope

# Reuse the committed-perspective helper from the context tests.
from test_dialectical_context import _create_perspective_with_aspects


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _create_nexus(intent: str = "handover test") -> Nexus:
    nexus = Nexus(intent=intent)
    nexus.save()
    nexus.commit()
    return nexus


def _message_text(msg) -> str:
    """Extract text from a message regardless of Mirascope content shape."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(getattr(part, "text", str(part)) for part in content)
    return getattr(content, "text", str(content))


class TestHandoverRoundTrip:
    """Explorer → Advisor → Explorer on one shared message store."""

    def _explorer_with_history(self, nexus: Nexus) -> Explorer:
        explorer = Explorer(
            nexus_hash=nexus.hash[:7],
            app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
        )
        explorer._conversation.add_user_message("Which wheel is most plausible?")
        explorer._conversation.add_assistant_message(
            "Wheel [[abc1234]] leads at 62%."
        )
        return explorer

    def test_advisor_head_replaces_prompt_keeps_history(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects()
            member.nexus.connect(nexus)

            explorer = self._explorer_with_history(nexus)
            history_before = list(explorer.messages)

            advisor = Advisor(
                app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                nexus_hash=explorer.nexus_hash,
                messages=explorer.messages,
            )

            # System prompt is the counsel head's now.
            sys_text = _message_text(advisor._conversation._messages[0])
            assert "## Advisory Register" in sys_text
            assert "## Scope" in sys_text  # nexus-pinned engine
            assert "build_wheels" not in sys_text  # not the Explorer engine

            # Everything after messages[0] survives verbatim.
            assert advisor.messages[1:] == history_before[1:]
            assert len(advisor.messages) == len(history_before)

    def test_round_trip_back_to_explorer(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects()
            member.nexus.connect(nexus)

            explorer = self._explorer_with_history(nexus)

            advisor = Advisor(
                app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                nexus_hash=explorer.nexus_hash,
                messages=explorer.messages,
            )
            advisor._conversation.add_user_message("What does this mean for me?")
            advisor._conversation.add_assistant_message(
                "It suggests leading with structure while protecting autonomy."
            )
            history_before = list(advisor.messages)

            explorer_again = Explorer(
                nexus_hash=explorer.nexus_hash,
                app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
                messages=advisor.messages,
            )

            # Operator head restored...
            sys_text = _message_text(explorer_again._conversation._messages[0])
            assert "build_wheels" in sys_text
            assert "## Advisory Register" not in sys_text
            # ...same exploration, full history (incl. counsel turns) intact.
            assert explorer_again.nexus_hash == explorer.nexus_hash
            assert explorer_again.messages[1:] == history_before[1:]

    def test_both_heads_pin_the_same_nexus(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            explorer = Explorer(nexus_hash=nexus.hash[:7])

            advisor = Advisor(
                app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                nexus_hash=explorer.nexus_hash,
                messages=explorer.messages,
            )

            assert advisor._nexus_hash == explorer.nexus_hash


@pytest.mark.real_llm
class TestHandoverReplayAcceptance:
    """The known unknown pinned by a real call: after the toggle, the history
    contains tool-use blocks from tools NOT in the current head's tool set
    (e.g. Explorer's present_exploration is not an Advisor tool). The provider
    must accept that history on replay in BOTH directions."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    async def test_toggle_replays_foreign_tool_blocks(self):
        case = Case()
        case.commit()

        with scope(case.sid):
            nexus = _create_nexus(intent="how do control and freedom interact")
            for t, a in [("Control", "Freedom"), ("Speed", "Thoroughness")]:
                pp = _create_perspective_with_aspects(
                    thesis_text=t, antithesis_text=a
                )
                pp.nexus.connect(nexus)

            explorer = Explorer(
                nexus_hash=nexus.hash[:7],
                app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
            )
            reply = await explorer.chat(
                "Show me the current state of this exploration."
            )
            assert isinstance(reply, str) and reply.strip()

            explorer_tools_used = list(explorer._conversation.last_tool_calls)
            if not explorer_tools_used:
                pytest.skip(
                    "Explorer called no tools this turn (LLM non-determinism) "
                    "— replay of foreign tool-use blocks not exercised"
                )

            # Toggle to counsel mode: the Advisor head must replay a history
            # containing Explorer tool-use blocks it has no tools for.
            advisor = Advisor(
                app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                nexus_hash=explorer.nexus_hash,
                messages=explorer.messages,
            )
            reply = await advisor.chat("So what does this all mean for me?")
            assert isinstance(reply, str) and reply.strip()

            # Toggle back: the Explorer head replays counsel-mode history
            # (possibly containing scoped-Advisor tool-use blocks).
            explorer_again = Explorer(
                nexus_hash=explorer.nexus_hash,
                app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
                messages=advisor.messages,
            )
            reply = await explorer_again.chat(
                "Back to the structures — which arrangement leads?"
            )
            assert isinstance(reply, str) and reply.strip()

            print(
                f"\nExplorer tools before toggle: {explorer_tools_used}; "
                f"Advisor tools during counsel: "
                f"{advisor._conversation.last_tool_calls}; "
                f"Explorer tools after toggle-back: "
                f"{explorer_again._conversation.last_tool_calls}"
            )
