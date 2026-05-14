"""
Orchestrator: Main LLM orchestrator for the dialectical framework.

Provides a Claude Code-like UX where users chat with an LLM that helps them
build and navigate the dialectical knowledge graph.

The Orchestrator is initialized with an optional `app_preamble` — a system prompt
prefix set by the host application (e.g. Chainlit) to define persona, tone, and
transparency level. The framework's own instructions (BASE_SYSTEM_PROMPT) are
appended automatically.

Run directly:
    python -m dialectical_framework.agents.orchestrator.orchestrator
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.orchestrator.system_prompts import \
    BASE_SYSTEM_PROMPT
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.graph.repositories.schema_repository import \
    SchemaRepository

# Curated schema description derived from GQLAlchemy node/relationship definitions
GRAPH_SCHEMA = """
## Node Types

### Session & Input
- **Case**: Case container. The root of a case analysis session.
- **Input**: External content (text, URL) added to a case for analysis.
- **Ideas**: Collection of extracted statements from inputs.

### Dialectical Structure
- **Statement**: A statement/thesis/position. Has `text` (text) and optional `meaning` (semantic URI).
- **Perspective**: A structured interpretation built around a Polarity (T-A pair), adding evaluative aspects (T+, T-, A+, A-).
- **Cycle**: T-cycle - an ordered sequence of Perspectives defining abstract thesis causality.
- **Wheel**: Concrete T-A arrangement implementing a Cycle with flip configurations and transitions.

### Transformation & Synthesis
- **Transformation**: Action-reflection structure belonging to Wheel (Ac, Re, Ac+, Ac-, Re+, Re-).
- **Transition**: Movement between dialectical positions (e.g., T- → A+).
- **Synthesis**: Emergent S+/S- pair from transformation.

### Metadata
- **Rationale**: Explanation text attached to any node.
- **Estimation**: Numeric assessment (probability, relevance, feasibility).

## Relationship Types

### Perspective Positions (Statement → Perspective)
- **T**: Thesis position (neutral statement)
- **A**: Antithesis position (opposing statement)
- **T_PLUS**: Positive aspect of thesis
- **T_MINUS**: Negative aspect of thesis
- **A_PLUS**: Positive aspect of antithesis
- **A_MINUS**: Negative aspect of antithesis

### Semantic Relations (between Statements)
- **OPPOSITE_OF**: T ↔ A dialectical opposition
- **CONTRADICTION_OF**: Cross-polarity contradiction (T+ ↔ A-, A+ ↔ T-)
- **POSITIVE_SIDE_OF**: Aspect → neutral (T+ → T)
- **NEGATIVE_SIDE_OF**: Aspect → neutral (T- → T)
- **SIMILAR_TO**: Semantic similarity

### Structural Relations
- **HAS_INPUT**: Case → Input
- **HAS_STATEMENT**: Ideas → Statement
- **HAS_WHEEL**: Cycle → Wheel
- **HAS_TRANSFORMATION**: Wheel → Transformation
- **IS_SOURCE_OF**: Statement → Transition
- **IS_TARGET_OF**: Statement → Transition
- **AC**: Action transition → Transformation
- **RE**: Reflection transition → Transformation

### Analytical Relations
- **EXPLAINS**: Rationale → any node
- **ESTIMATES**: Estimation → any node

## Key Properties

All nodes have:
- `hash`: Content-addressable identifier (Merkle hash)
- `sid`: Session identifier (for multi-tenant isolation)
- `committed_at`: Timestamp when committed

Statement:
- `text`: The text of the thesis/position
- `meaning`: Optional semantic URI
- `rejected`: Boolean if rejected

Perspective, Cycle, Wheel, etc.:
- `intent`: Optional intent/purpose description
"""
from dialectical_framework.agents.analyst.skills.edit_perspective import \
    edit_perspective
from dialectical_framework.agents.analyst.skills.expand_polarities import \
    expand_polarities
from dialectical_framework.agents.analyst.skills.find_polarities import \
    find_polarities
from dialectical_framework.agents.analyst.skills.introduce_polarity import \
    introduce_polarity
from dialectical_framework.agents.analyst.skills.surface_theses import \
    surface_theses
from dialectical_framework.agents.explorer.skills.build_wheels import \
    build_wheels
from dialectical_framework.agents.explorer.skills.explore_transformations import \
    explore_transformations
from dialectical_framework.agents.orchestrator.tools.add_input import add_input
from dialectical_framework.agents.explorer.tools.create_nexus import \
    create_nexus
from dialectical_framework.agents.orchestrator.tools.inspect_node import \
    inspect_node
from dialectical_framework.agents.analyst.tools.place_statement import \
    place_statement
from dialectical_framework.agents.orchestrator.tools.present_analysis import \
    present_analysis
from dialectical_framework.agents.orchestrator.tools.query_graph import \
    query_graph
from dialectical_framework.agents.orchestrator.tools.reject import reject
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

if TYPE_CHECKING:
    pass


class ChatResponse(BaseModel):
    """Response from the orchestrator chat."""

    message: str = Field(description="The assistant's response message")


class Orchestrator:
    """
    Main LLM orchestrator for dialectical framework exploration.

    One orchestrator instance = one session = one sid.
    Either creates a new case or loads an existing one.

    The host application (Chainlit, API, CLI) provides an `app_preamble` —
    a system prompt prefix that defines persona, tone, and transparency level.
    The framework's own BASE_SYSTEM_PROMPT is appended automatically.

    Usage:
        # Simple advisor persona
        Orchestrator(app_preamble="You are a wise counselor. Speak warmly...")

        # Pro coach persona
        Orchestrator(
            sid="existing-sid",
            app_preamble="You are collaborating with a professional coach..."
        )

        # Expert/debug persona
        Orchestrator(app_preamble="Be maximally transparent about graph operations...")
    """

    def __init__(
        self,
        sid: Optional[str] = None,
        app_preamble: Optional[str] = None,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            sid: Optional existing session ID to load. If None, creates new session.
            app_preamble: Optional system prompt prefix from the host application.
                Defines persona, tone, transparency. The framework's own instructions
                (tool usage, phases, behavioral rules) are appended automatically.
        """
        if sid:
            self._sid: str = sid
        else:
            case = Case()
            case.commit()
            assert case.sid is not None
            self._sid = case.sid

        self._app_preamble = app_preamble
        self._tools = self._build_tool_list()
        self._conversation = ConversationFacilitator(tools=self._tools)
        self._conversation.set_system_prompt(self._build_system_prompt())

    def _build_system_prompt(self) -> str:
        """Build system prompt: app_preamble + base prompt + schema."""
        parts = []
        if self._app_preamble:
            parts.append(self._app_preamble)
        parts.append(BASE_SYSTEM_PROMPT)
        parts.append(GRAPH_SCHEMA)
        parts.append(self._query_live_schema())
        return "\n\n".join(parts)

    def _query_live_schema(self) -> str:
        """Query live schema from the database."""
        repo = SchemaRepository()
        lines = ["## Live Database Schema"]

        all_labels = repo.get_node_labels()
        if all_labels:
            lines.append("\nNode labels in DB:")
            for label in sorted(all_labels):
                lines.append(f"  - {label}")
        else:
            lines.append("\nCould not query node labels.")

        rel_types = repo.get_relationship_types()
        if rel_types:
            lines.append("\nRelationship types in DB:")
            for rel_type in rel_types:
                lines.append(f"  - {rel_type}")
        else:
            lines.append("\nCould not query relationship types.")

        return "\n".join(lines)

    @staticmethod
    def _build_tool_list() -> list:
        """Build the list of tools available to the orchestrator."""
        capture_tools = [
            add_input,
        ]

        analysis_tools = [
            surface_theses,
            find_polarities,
            introduce_polarity,
            expand_polarities,
            place_statement,
            edit_perspective,
            reject,
        ]

        exploration_tools = [
            create_nexus,
            build_wheels,
            explore_transformations,
        ]

        query_tools = [
            present_analysis,
            inspect_node,
            query_graph,
        ]

        return capture_tools + analysis_tools + exploration_tools + query_tools

    async def chat(self, user_message: str) -> str:
        """
        Process a user message and return the assistant's response.

        All operations are scoped to this orchestrator's session.

        Args:
            user_message: The user's input message

        Returns:
            The assistant's response text
        """
        with scope(self._sid):
            result = await self._conversation.submit(ChatResponse, user_message)
        return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        """
        Process a user message with streaming events.

        Yields StreamEvent instances as the agentic loop progresses:
        TextDelta, ToolStart, ToolResult, ResponseComplete.
        """
        with scope(self._sid):
            async for event in self._conversation.submit_stream(ChatResponse, user_message):
                yield event

    @property
    def sid(self) -> str:
        """Get the session ID."""
        return self._sid

    def run(self) -> None:
        """
        Run the orchestrator in interactive REPL mode.

        Type 'exit' or 'quit' to end the session.
        """
        asyncio.run(self._run_loop())

    async def _run_loop(self) -> None:
        """Internal async REPL loop."""
        print(f"Dialectical Orchestrator")
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


if __name__ == "__main__":
    from dialectical_framework.dialectical_reasoning import \
        DialecticalReasoning
    from dialectical_framework.settings import Settings

    # Initialize DI container
    DialecticalReasoning.setup(Settings.from_env())

    # Run orchestrator
    Orchestrator().run()
