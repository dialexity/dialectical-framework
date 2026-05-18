"""
Orchestrator: Router and coordinator for the dialectical framework.

Two modes:
- default: Autonomous agents do the heavy lifting. User steers at high level.
- advanced: User co-pilots with granular tools. Full graph control.

The host application sets mode + app_preamble to match the user type.

Run directly:
    python -m dialectical_framework.agents.orchestrator.orchestrator
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator, Literal, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.orchestrator.system_prompts import \
    DEFAULT_SYSTEM_PROMPT, ADVANCED_SYSTEM_PROMPT
from dialectical_framework.agents.stream_events import StreamEvent

from dialectical_framework.agents.analyst.analyst import analyze
from dialectical_framework.agents.explorer.explorer import explore
from dialectical_framework.agents.orchestrator.tools.add_input import add_input
from dialectical_framework.agents.analyst.skills.surface_theses import \
    surface_theses
from dialectical_framework.agents.analyst.skills.find_polarities import \
    find_polarities
from dialectical_framework.agents.analyst.skills.introduce_polarity import \
    introduce_polarity
from dialectical_framework.agents.analyst.skills.expand_polarities import \
    expand_polarities
from dialectical_framework.agents.analyst.skills.edit_perspective import \
    edit_perspective
from dialectical_framework.agents.analyst.tools.place_statement import \
    place_statement
from dialectical_framework.agents.orchestrator.tools.reject import reject
from dialectical_framework.agents.explorer.tools.create_nexus import \
    create_nexus
from dialectical_framework.agents.explorer.skills.build_wheels import \
    build_wheels
from dialectical_framework.agents.explorer.skills.explore_transformations import \
    explore_transformations
from dialectical_framework.agents.orchestrator.tools.present_analysis import \
    present_analysis
from dialectical_framework.agents.orchestrator.tools.inspect_node import \
    inspect_node
from dialectical_framework.agents.orchestrator.tools.query_graph import \
    query_graph
from dialectical_framework.agents.orchestrator.tools.get_schema import \
    get_schema
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

if TYPE_CHECKING:
    pass


class ChatResponse(BaseModel):
    """Response from the orchestrator chat."""

    message: str = Field(description="The assistant's response message")


class Orchestrator:
    """
    Router and coordinator for dialectical framework.

    Two modes:
    - "default": Autonomous agents (Analyst, Explorer) handle full pipelines.
      User describes situation → gets structured findings → steers high-level.
      For: CEOs, students, anyone seeking advice.

    - "advanced": User co-pilots with granular tools. Full step-by-step control.
      User drives each operation explicitly.
      For: Systems thinkers, consultants, psychologists, power users.

    Usage:
        # Advice-seeker (default mode)
        Orchestrator(app_preamble="You are a wise counselor...")

        # Power user (advanced mode)
        Orchestrator(mode="advanced", app_preamble="Show the tetrad structure...")
    """

    def __init__(
        self,
        sid: Optional[str] = None,
        mode: Literal["default", "advanced"] = "default",
        app_preamble: Optional[str] = None,
    ) -> None:
        if sid:
            self._sid: str = sid
        else:
            case = Case()
            case.commit()
            assert case.sid is not None
            self._sid = case.sid

        self._mode = mode
        self._app_preamble = app_preamble
        self._tools = self._build_tool_list(mode)
        self._conversation = ConversationFacilitator(tools=self._tools)
        self._conversation.set_system_prompt(self._build_system_prompt())

    def _build_system_prompt(self) -> str:
        parts = []
        if self._app_preamble:
            parts.append(self._app_preamble)
        if self._mode == "advanced":
            parts.append(ADVANCED_SYSTEM_PROMPT)
        else:
            parts.append(DEFAULT_SYSTEM_PROMPT)
        return "\n\n".join(parts)

    @staticmethod
    def _build_tool_list(mode: str) -> list:
        if mode == "advanced":
            return _advanced_tools()
        return _default_tools()

    async def chat(self, user_message: str) -> str:
        with scope(self._sid):
            result = await self._conversation.submit(ChatResponse, user_message)
        return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        with scope(self._sid):
            async for event in self._conversation.submit_stream(ChatResponse, user_message):
                yield event

    @property
    def sid(self) -> str:
        return self._sid

    @property
    def mode(self) -> str:
        return self._mode

    def run(self) -> None:
        asyncio.run(self._run_loop())

    async def _run_loop(self) -> None:
        print(f"Dialectical Orchestrator ({self._mode} mode)")
        print(f"Session: {self._sid}")
        print("Type 'exit' to quit.\n")

        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("You: ").strip()
                )
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            response = await self.chat(user_input)
            print(f"\nAssistant: {response}\n")


def _default_tools() -> list:
    """Tools for default mode: autonomous agents + steering + queries."""
    return [
        analyze,
        explore,
        edit_perspective,
        reject,
        present_analysis,
        inspect_node,
        query_graph,
        get_schema,
    ]


def _advanced_tools() -> list:
    """Tools for advanced mode: all granular tools + queries."""
    return [
        add_input,
        surface_theses,
        find_polarities,
        introduce_polarity,
        expand_polarities,
        place_statement,
        edit_perspective,
        reject,
        create_nexus,
        build_wheels,
        explore_transformations,
        present_analysis,
        inspect_node,
        query_graph,
        get_schema,
    ]


if __name__ == "__main__":
    from dialectical_framework.dialectical_reasoning import \
        DialecticalReasoning
    from dialectical_framework.settings import Settings

    DialecticalReasoning.setup(Settings.from_env())
    Orchestrator().run()
