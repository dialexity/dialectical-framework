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
    Add SOURCE MATERIAL for analysis to the current case.

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
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> str:
        """Add input content to the current case."""
        # Find the case
        query = """
        MATCH (c:Case {case_id: $case_id})
        RETURN c
        """
        results = list(graph_db.execute_and_fetch(query, {"case_id": case_id}))

        if not results:
            return f"Case not found: {case_id}"

        case = results[0]["c"]

        # Create and connect input
        input_node = Input(content=self.content)
        input_node.commit()
        case.inputs.connect(input_node)

        # Preview for response
        preview = (
            self.content[:100] + "..." if len(self.content) > 100 else self.content
        )

        return (
            f"Added input to case.\n"
            f"Input hash: {input_node.short_hash}\n"
            f"Preview: {preview}\n"
            f"You can now extract theses using SurfaceTheses."
        )
