"""
Input tool for the Orchestrator.

AddInput is for adding SOURCE MATERIAL (user-provided content) for analysis.
It is NOT for storing analytical outputs - those go through agent tools.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.protocols.base_tool import BaseTool


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
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
        query = """
        MATCH (c:Case {sid: $sid})
        RETURN c
        """
        results = list(graph_db.execute_and_fetch(query, {"sid": sid}))

        if not results:
            return f"Case not found: {sid}"

        case = results[0]["c"]

        input_node = Input(content=self.content)
        input_node.commit()
        case.inputs.connect(input_node)

        preview = (
            self.content[:100] + "..." if len(self.content) > 100 else self.content
        )

        return (
            f"Added input to case.\n"
            f"Input hash: {input_node.short_hash}\n"
            f"Preview: {preview}\n"
            f"You can now extract theses using SurfaceTheses."
        )


@llm.tool
async def add_input(content: str) -> str:
    """Add external source material (user-provided text or URL) for analysis to the current case. Not for storing analytical outputs."""
    tool = AddInput(content=content)
    return await tool.call()
