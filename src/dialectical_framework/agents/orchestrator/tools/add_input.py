"""
Input tool for the Orchestrator.

AddInput is for adding SOURCE MATERIAL (user-provided content) for analysis.
It is NOT for storing analytical outputs - those go through agent tools.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import BaseTool
from pydantic import Field

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input


class AddInput(BaseTool):
    """
    Add SOURCE MATERIAL for analysis to the current brainstorm.

    ONLY use this for external content the user wants to analyze:
    - Text the user pastes or provides
    - URLs to articles/documents
    - Uploaded file contents

    DO NOT use this for:
    - Your own summaries or analysis
    - Generated outputs or conclusions
    - Anything YOU wrote (use the appropriate agent tools instead)

    Think of Input as "what goes IN for analysis", not "where to store results".
    """

    content: str = Field(
        description="External source material to analyze (user-provided text or URL). NOT for storing your outputs."
    )

    @inject
    async def call(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
        """Add input content to the current brainstorm."""
        # Find the brainstorm
        query = """
        MATCH (b:Brainstorm {sid: $sid})
        RETURN b
        """
        results = list(graph_db.execute_and_fetch(query, {"sid": sid}))

        if not results:
            return f"Brainstorm not found: {sid}"

        brainstorm = results[0]["b"]

        # Create and connect input
        input_node = Input(content=self.content)
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        # Preview for response
        preview = (
            self.content[:100] + "..." if len(self.content) > 100 else self.content
        )

        return (
            f"Added input to brainstorm.\n"
            f"Input hash: {input_node.short_hash}\n"
            f"Preview: {preview}\n"
            f"You can now extract theses using SurfaceTheses."
        )
