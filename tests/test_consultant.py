"""
`Consultant` — the method as a prompt, with nothing behind it.

DB-free on purpose: the head's whole contract is that it needs no Case, no
scope, no graph and no tools, so these tests run with the graph fixtures
overridden and would fail the contract if anything here reached for a
repository. The prompt's own fairness guards (the rewrite table, the tool-name
leak, the dangling cross-references) live in `tests/e2e/test_e2e.py::
TestMethodPrompt`, because their subject is the A1 baseline; what is pinned
here is the HEAD: what it composes, what it refuses, and what it carries.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.consultant.consultant import (Consultant,
                                                         method_prompt)
from dialectical_framework.agents.app_spec import AppSpec
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.agents.stream_events import ResponseComplete
from dialectical_framework.graph.scope_context import get_current_sid


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _system_prompt(advisor: Consultant) -> str:
    """The installed system message as text (Mirascope stores it as parts)."""
    content = advisor._conversation._messages[0].content
    if isinstance(content, str):
        return content
    if hasattr(content, "text"):
        return content.text
    return "".join(getattr(part, "text", "") for part in content)


class TestWhatTheHeadComposes:
    def test_persona_then_method_and_nothing_else(self):
        advisor = Consultant(app_preamble=COUNSELOR_PERSONA)
        prompt = _system_prompt(advisor)
        assert prompt.startswith(COUNSELOR_PERSONA)
        assert prompt.endswith(method_prompt())
        assert "## Current Understanding" not in prompt, "no graph, no dump"
        assert "{dialectical_context}" not in prompt

    def test_no_tools_by_construction(self):
        advisor = Consultant(app_preamble=COUNSELOR_PERSONA)
        assert not advisor._conversation._tools
        assert "You have no tools." in _system_prompt(advisor)

    def test_an_app_spec_supplies_the_advisor_persona(self):
        spec = AppSpec(advisor_persona="## Persona\n\nYou are a blunt friend.")
        advisor = Consultant(app=spec)
        assert _system_prompt(advisor).startswith("## Persona\n\nYou are a blunt friend.")

    def test_app_tools_are_refused_not_dropped(self):
        """The prompt says "You have no tools"; a tool the model could call
        would make that a lie, and a silently dropped tool list is the defect."""
        from mirascope import llm

        @llm.tool
        async def lookup(x: str) -> str:
            """Look something up."""
            return x

        with pytest.raises(ValueError, match="no tools"):
            Consultant(app=AppSpec(advisor_persona="p", tools=[lookup]))

    def test_the_decision_section_is_optional(self):
        with_it = _system_prompt(Consultant(app_preamble="p"))
        without = _system_prompt(Consultant(app_preamble="p", include_decision=False))
        assert "## Decision Readiness" in with_it and "## Recording Decisions" in with_it
        assert "## Decision Readiness" not in without and "## Recording Decisions" not in without

    def test_no_persona_is_the_method_alone(self):
        assert _system_prompt(Consultant()) == method_prompt()


class TestWhatTheHeadCarries:
    def test_messages_resume_a_conversation(self):
        first = Consultant(app_preamble="p")
        first._conversation._messages.append({"role": "user", "content": "hello"})
        second = Consultant(app_preamble="p", messages=first.messages)
        assert second.messages[-1] == {"role": "user", "content": "hello"}
        assert second.messages is not first.messages, "a copy, as on every head"

    def test_thinking_is_the_per_session_toggle(self):
        assert Consultant(thinking=None)._conversation._thinking_kwargs() == {}
        assert Consultant(thinking="low")._conversation._thinking_kwargs() == {
            "thinking": "low"
        }

    @pytest.mark.llm
    async def test_chat_needs_no_scope(self):
        """The contract: no Case, no sid. `Advisor.chat` refuses without a scope;
        this head must not even look."""
        assert get_current_sid() is None
        reply = await Consultant(app_preamble=COUNSELOR_PERSONA).chat(
            "I have a problem with my wife."
        )
        assert isinstance(reply, str) and reply

    @pytest.mark.llm
    async def test_chat_stream_ends_on_response_complete(self):
        events = []
        async for event in Consultant(app_preamble="p").chat_stream("hi"):
            events.append(event)
        assert isinstance(events[-1], ResponseComplete)

    @pytest.mark.llm
    async def test_the_turn_timing_is_all_reply_path(self):
        advisor = Consultant(app_preamble="p")
        await advisor.chat("hi")
        timing = advisor.last_turn_timing
        assert timing.off_path_s == 0.0
        assert timing.closing is None and timing.deferral is None
        assert timing.retry_count == 0
