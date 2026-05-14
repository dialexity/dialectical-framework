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
## Graph Schema

### Node Types

| Node | Description | Key Properties |
|------|-------------|----------------|
| Case | Root session container | |
| Input | External content (text, URL) for analysis | `content` |
| Ideas | Collection of extracted Statements from Inputs | `intent` |
| Statement | A thesis, position, or claim | `text`, `meaning`, `rejected` |
| Polarity | A tension — structural T-A pair (thesis vs antithesis) | |
| Perspective | Full interpretation: Polarity + evaluative aspects (T+, T-, A+, A-) | `intent`, `rejected` |
| Nexus | Exploration container grouping Perspectives for combination | `intent`, `preset` |
| Cycle | Ordered sequence of Perspectives defining causality | `intent` |
| Wheel | Concrete T-A arrangement implementing a Cycle | `intent` |
| Transformation | Action-reflection structure (Ac, Re, Ac+, Ac-, Re+, Re-) on a Wheel edge | `intent` |
| Transition | Movement between two Statements (source → target) | `statement`, `headline`, `haiku` |
| Synthesis | Emergent S+/S- pair from a Wheel's circular causality | |
| Rationale | Explanation attached to any node | `text` |
| Estimation | Numeric assessment (probability, relevance, feasibility) | `value` |

All nodes share: `hash` (content-addressable ID), `sid` (session scope), `committed_at`.

### Relationship Types and Directions

**Polarity positions** (Statement → Polarity):
- `(s:Statement)-[:T]->(p:Polarity)` — thesis pole
- `(s:Statement)-[:A]->(p:Polarity)` — antithesis pole

**Perspective positions** (Statement → Perspective):
- `(s:Statement)-[:T_PLUS]->(pp:Perspective)` — positive thesis aspect
- `(s:Statement)-[:T_MINUS]->(pp:Perspective)` — negative thesis aspect
- `(s:Statement)-[:A_PLUS]->(pp:Perspective)` — positive antithesis aspect
- `(s:Statement)-[:A_MINUS]->(pp:Perspective)` — negative antithesis aspect

**Perspective structure**:
- `(pp:Perspective)-[:HAS_POLARITY]->(pol:Polarity)` — which tension this Perspective interprets
- `(pp:Perspective)-[:BELONGS_TO_NEXUS]->(nx:Nexus)` — grouped for exploration
- `(pp:Perspective)-[:CHANGED_TO]->(pp2:Perspective)` — edit lineage (old → new)

**Semantic relations** (between Statements):
- `(s1:Statement)-[:OPPOSITE_OF]->(s2:Statement)` — dialectical opposition (symmetric)
- `(s1:Statement)-[:CONTRADICTION_OF]->(s2:Statement)` — cross-polarity (T+ ↔ A-, symmetric)
- `(s:Statement)-[:POSITIVE_SIDE_OF]->(s2:Statement)` — aspect → neutral
- `(s:Statement)-[:NEGATIVE_SIDE_OF]->(s2:Statement)` — aspect → neutral

**Exploration structure**:
- `(c:Cycle)-[:HAS_WHEEL]->(w:Wheel)` — Cycle contains Wheels
- `(t:Transition)-[:BELONGS_TO_CYCLE]->(w:Wheel)` — Transition is an edge in a Wheel
- `(c:Cycle)-[:OPPOSITE_DIRECTION]->(c2:Cycle)` — reversed causal order (symmetric)
- `(w:Wheel)-[:OPPOSITE_DIRECTION]->(w2:Wheel)` — reversed arrangement (symmetric)

**Transition structure**:
- `(s:Statement)-[:IS_SOURCE_OF]->(t:Transition)` — source component
- `(t:Transition)-[:IS_TARGET_OF]->(s:Statement)` — target component

**Transformation positions** (Transition → Transformation):
- `(t:Transition)-[:AC]->(tr:Transformation)` — action (T → A)
- `(t:Transition)-[:AC_PLUS]->(tr:Transformation)` — positive action (T- → A+)
- `(t:Transition)-[:AC_MINUS]->(tr:Transformation)` — negative action (T+ → A-)
- `(t:Transition)-[:RE]->(tr:Transformation)` — reflection (A → T)
- `(t:Transition)-[:RE_PLUS]->(tr:Transformation)` — positive reflection (A- → T+)
- `(t:Transition)-[:RE_MINUS]->(tr:Transformation)` — negative reflection (A+ → T-)
- `(tr:Transformation)-[:ACTION_REFLECTION]->(t:Transition)` — which Wheel edge this Transformation belongs to
- `(tr:Transformation)-[:BELONGS_TO_NEXUS]->(nx:Nexus)` — scoped to Nexus

**Synthesis positions** (Statement → Synthesis → Wheel):
- `(s:Statement)-[:S_PLUS]->(syn:Synthesis)` — positive synthesis
- `(s:Statement)-[:S_MINUS]->(syn:Synthesis)` — negative synthesis
- `(syn:Synthesis)-[:SYNTHESIS_OF]->(w:Wheel)` — which Wheel it synthesizes

**Container membership**:
- `(case:Case)-[:HAS_INPUT]->(i:Input)` — Case owns Inputs
- `(ideas:Ideas)-[:HAS_STATEMENT]->(s:Statement)` — Ideas contains Statements
- `(ideas:Ideas)-[:DISTILLED_TO]->(i:Input)` — Ideas derived from Input

**Metadata**:
- `(r:Rationale)-[:EXPLAINS]->(n)` — explanation for any node
- `(e:Estimation)-[:ESTIMATES]->(n)` — numeric assessment of any node

### Common Query Patterns

```cypher
-- All Perspectives with T and A statements
MATCH (pp:Perspective)-[:HAS_POLARITY]->(pol:Polarity)
MATCH (t:Statement)-[:T]->(pol)
MATCH (a:Statement)-[:A]->(pol)
RETURN pp.hash, t.text AS thesis, a.text AS antithesis

-- Full Perspective (all 6 positions)
MATCH (pp:Perspective) WHERE pp.hash STARTS WITH "abc"
MATCH (pp)-[:HAS_POLARITY]->(pol)
MATCH (t:Statement)-[:T]->(pol), (a:Statement)-[:A]->(pol)
OPTIONAL MATCH (tp:Statement)-[:T_PLUS]->(pp)
OPTIONAL MATCH (tm:Statement)-[:T_MINUS]->(pp)
OPTIONAL MATCH (ap:Statement)-[:A_PLUS]->(pp)
OPTIONAL MATCH (am:Statement)-[:A_MINUS]->(pp)
RETURN t.text, a.text, tp.text, tm.text, ap.text, am.text

-- Wheel edges (transitions in order)
MATCH (w:Wheel) WHERE w.hash STARTS WITH "abc"
MATCH (t:Transition)-[:BELONGS_TO_CYCLE]->(w)
MATCH (src:Statement)-[:IS_SOURCE_OF]->(t)
MATCH (t)-[:IS_TARGET_OF]->(tgt:Statement)
RETURN src.text AS source, tgt.text AS target

-- Transformations for a Wheel
MATCH (w:Wheel) WHERE w.hash STARTS WITH "abc"
MATCH (edge:Transition)-[:BELONGS_TO_CYCLE]->(w)
MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(edge)
MATCH (ac_t:Transition)-[:AC_PLUS]->(tr)
MATCH (re_t:Transition)-[:RE_PLUS]->(tr)
RETURN tr.hash, ac_t.statement AS action, re_t.statement AS reflection

-- Vocabulary (all non-rejected Statements)
MATCH (s:Statement) WHERE s.rejected IS NULL RETURN s.text, s.hash
```
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
