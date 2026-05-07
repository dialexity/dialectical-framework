"""
Orchestrator: Main LLM orchestrator for the dialectical framework.

Provides a Claude Code-like UX where users chat with an LLM that helps them
build and navigate the dialectical knowledge graph.

Run directly:
    python -m dialectical_framework.agents.orchestrator.orchestrator
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.orchestrator.system_prompts import \
    ORCHESTRATOR_SYSTEM_PROMPT

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
from dialectical_framework.agents.analyst.skills.edit_polarity import \
    edit_polarity
from dialectical_framework.agents.analyst.skills.edit_tetrad import edit_tetrad
from dialectical_framework.agents.analyst.skills.expand_polarities import \
    expand_polarities
from dialectical_framework.agents.analyst.skills.find_polarities import \
    find_polarities
from dialectical_framework.agents.analyst.skills.surface_theses import \
    surface_theses
from dialectical_framework.agents.explorer.skills.build_wheels import \
    build_wheels
from dialectical_framework.agents.explorer.skills.explore_transformations import \
    explore_transformations
from dialectical_framework.agents.orchestrator.tools.add_input import add_input
from dialectical_framework.agents.orchestrator.tools.get_scope_status import \
    get_scope_status
from dialectical_framework.agents.orchestrator.tools.query_graph import \
    query_graph
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

    Usage:
        # Interactive REPL
        Orchestrator().run()

        # Or with existing session
        Orchestrator(sid="existing-sid").run()

        # Programmatic
        orchestrator = Orchestrator()
        response = await orchestrator.chat("Extract theses about remote work")
    """

    def __init__(self, sid: Optional[str] = None) -> None:
        """
        Initialize the orchestrator.

        Args:
            sid: Optional existing session ID to load. If None, creates new session.
        """
        if sid:
            self._sid = sid
        else:
            case = Case()
            case.commit()
            self._sid = case.sid

        self._tools = self._build_tool_list()
        self._conversation = ConversationFacilitator(tools=self._tools)
        self._conversation.set_system_prompt(self._build_system_prompt())

    def _build_system_prompt(self) -> str:
        """Build system prompt with curated schema + live DB schema."""
        live_schema = self._query_live_schema()
        return f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\n{GRAPH_SCHEMA}\n\n{live_schema}"

    @inject
    def _query_live_schema(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> str:
        """Query live schema from the database."""
        lines = ["## Live Database Schema"]

        # Get node labels (works in both Memgraph and Neo4j)
        try:
            results = list(
                graph_db.execute_and_fetch(
                    "MATCH (n) RETURN DISTINCT labels(n) AS labels"
                )
            )
            if results:
                # Flatten and dedupe labels
                all_labels = set()
                for row in results:
                    all_labels.update(row["labels"])
                # Filter out base labels
                all_labels.discard("Node")
                all_labels.discard("Assessable")
                if all_labels:
                    lines.append("\nNode labels in DB:")
                    for label in sorted(all_labels):
                        lines.append(f"  - {label}")
        except Exception:
            lines.append("\nCould not query node labels.")

        # Get relationship types (works in both Memgraph and Neo4j)
        try:
            results = list(
                graph_db.execute_and_fetch(
                    "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rel_type"
                )
            )
            if results:
                rel_types = sorted(row["rel_type"] for row in results)
                lines.append("\nRelationship types in DB:")
                for rel_type in rel_types:
                    lines.append(f"  - {rel_type}")
        except Exception:
            lines.append("\nCould not query relationship types.")

        return "\n".join(lines)

    @staticmethod
    def _build_tool_list() -> list:
        """Build the list of tools available to the orchestrator."""
        session_tools = [
            add_input,
            get_scope_status,
        ]

        query_tools = [
            query_graph,
        ]

        build_tools = [
            surface_theses,
            find_polarities,
            expand_polarities,
            edit_polarity,
            edit_tetrad,
            build_wheels,
            explore_transformations,
        ]

        return session_tools + query_tools + build_tools

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
