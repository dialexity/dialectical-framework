"""
AddInput: Concern + tool for capturing source material into the case.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input


class AddInput(ReasonableConcern[Input]):
    """
    Captures source material (text or URL) and links it to the current Case.

    Programmatic usage:
        concern = AddInput()
        input_node = await concern.resolve(content="...")
        print(input_node.short_hash)
    """

    @inject
    async def resolve(
        self,
        content: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> Input:
        query = """
        MATCH (c:Case {sid: $sid})
        RETURN c
        """
        results = list(graph_db.execute_and_fetch(query, {"sid": sid}))

        if not results:
            raise ValueError(f"Case not found for sid: {sid}")

        case = results[0]["c"]

        input_node = Input(content=content)
        input_node.commit()
        case.inputs.connect(input_node)

        self._report.node_created(input_node)
        self._report.ok = True
        self._report.summary = f"Added input {input_node.short_hash}"
        self._report.artifacts["input_hash"] = input_node.short_hash

        return input_node


@llm.tool
async def add_input(
    content: str = Field(description="Source material: user-provided text, URL, or captured conversation fragment"),
) -> str:
    """Add source material for analysis — user-provided text, URL, or captured conversation fragment. Use proactively when the user describes their situation. Not for storing your analytical outputs."""
    concern = AddInput()
    input_node = await concern.resolve(content=content)
    return str(concern.report)
