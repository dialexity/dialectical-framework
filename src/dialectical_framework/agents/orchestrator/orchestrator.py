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

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.orchestrator.system_prompts import ORCHESTRATOR_SYSTEM_PROMPT


# Curated schema description derived from GQLAlchemy node/relationship definitions
GRAPH_SCHEMA = """
## Node Types

### Session & Input
- **Brainstorm**: Session container. The root of a brainstorming session.
- **Input**: External content (text, URL) added to a brainstorm for analysis.
- **Ideas**: Collection of extracted statements from inputs.

### Dialectical Structure
- **DialecticalComponent**: A statement/thesis/position. Has `statement` (text) and optional `meaning` (semantic URI).
- **WisdomUnit**: A dialectical tension pairing thesis (T) with antithesis (A), plus their poles (T+, T-, A+, A-).
- **Cycle**: T-cycle - an ordered sequence of WisdomUnits defining abstract thesis causality.
- **Wheel**: Concrete T-A arrangement implementing a Cycle with flip configurations and transitions.

### Transformation & Synthesis
- **Transformation**: Action-reflection structure belonging to Wheel (Ac, Re, Ac+, Ac-, Re+, Re-).
- **Transition**: Movement between dialectical positions (e.g., T- → A+).
- **Synthesis**: Emergent S+/S- pair from transformation.

### Metadata
- **Rationale**: Explanation text attached to any node.
- **Estimation**: Numeric assessment (probability, relevance, feasibility).

## Relationship Types

### WisdomUnit Positions (DialecticalComponent → WisdomUnit)
- **T**: Thesis position (neutral statement)
- **A**: Antithesis position (opposing statement)
- **T_PLUS**: Positive aspect of thesis
- **T_MINUS**: Negative aspect of thesis
- **A_PLUS**: Positive aspect of antithesis
- **A_MINUS**: Negative aspect of antithesis

### Semantic Relations (between DialecticalComponents)
- **OPPOSITE_OF**: T ↔ A dialectical opposition
- **CONTRADICTION_OF**: Cross-polarity contradiction (T+ ↔ A-, A+ ↔ T-)
- **POSITIVE_SIDE_OF**: Pole → neutral (T+ → T)
- **NEGATIVE_SIDE_OF**: Pole → neutral (T- → T)
- **SIMILAR_TO**: Semantic similarity

### Structural Relations
- **HAS_INPUT**: Brainstorm → Input
- **HAS_STATEMENT**: Ideas → DialecticalComponent
- **HAS_WHEEL**: Cycle → Wheel
- **HAS_TRANSFORMATION**: Wheel → Transformation
- **IS_SOURCE_OF**: DialecticalComponent → Transition
- **IS_TARGET_OF**: DialecticalComponent → Transition
- **AC**: Action transition → Transformation
- **RE**: Reflection transition → Transformation

### Analytical Relations
- **EXPLAINS**: Rationale → any node
- **ESTIMATES**: Estimation → any node

## Key Properties

All nodes have:
- `hash`: Content-addressable identifier (Merkle hash)
- `sid`: Session/scope identifier (for multi-tenant isolation)
- `committed_at`: Timestamp when committed

DialecticalComponent:
- `statement`: The text of the thesis/position
- `meaning`: Optional semantic URI
- `rejected`: Boolean if rejected

WisdomUnit, Cycle, Wheel, etc.:
- `intent`: Optional intent/purpose description
"""
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.scope_context import scope

# Import existing subagents
from dialectical_framework.agents.brainstorming.subagents.anchoring_agent import AnchoringAgent
from dialectical_framework.agents.brainstorming.subagents.polarity_agent import PolarityAgent
from dialectical_framework.agents.brainstorming.subagents.wisdom_agent import WisdomAgent
from dialectical_framework.agents.brainstorming.subagents.polarity_editor import PolarityEditor
from dialectical_framework.agents.sensemaking.subagents.transformation_agent import TransformationAgent

# Import orchestrator tools
from dialectical_framework.agents.orchestrator.tools.add_input import AddInput
from dialectical_framework.agents.orchestrator.tools.query_graph import QueryGraph

if TYPE_CHECKING:
    from mirascope import BaseTool


class ChatResponse(BaseModel):
    """Response from the orchestrator chat."""

    message: str = Field(description="The assistant's response message")


class Orchestrator:
    """
    Main LLM orchestrator for dialectical framework exploration.

    One orchestrator instance = one session = one sid.
    Either creates a new brainstorm or loads an existing one.

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
            brainstorm = Brainstorm()
            brainstorm.commit()
            self._sid = brainstorm.sid

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
            results = list(graph_db.execute_and_fetch(
                "MATCH (n) RETURN DISTINCT labels(n) AS labels"
            ))
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
            results = list(graph_db.execute_and_fetch(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rel_type"
            ))
            if results:
                rel_types = sorted(row["rel_type"] for row in results)
                lines.append("\nRelationship types in DB:")
                for rel_type in rel_types:
                    lines.append(f"  - {rel_type}")
        except Exception:
            lines.append("\nCould not query relationship types.")

        return "\n".join(lines)

    @staticmethod
    def _build_tool_list() -> list[type[BaseTool]]:
        """Build the list of tools available to the orchestrator."""
        session_tools = [
            AddInput,
        ]

        query_tools = [
            QueryGraph,
        ]

        build_tools = [
            AnchoringAgent,
            PolarityAgent,
            WisdomAgent,
            PolarityEditor,
            TransformationAgent,
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
    from dialectical_framework.dialectical_reasoning import DialecticalReasoning
    from dialectical_framework.settings import Settings

    # Initialize DI container
    DialecticalReasoning.setup(Settings.from_env())

    # Run orchestrator
    Orchestrator().run()
