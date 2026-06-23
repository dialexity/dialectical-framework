"""
read_digest: Tool for inspecting the current analytical digest of an Input source.

Used by conversational agents to see the current understanding before deciding
whether to refine it or pull full content.
"""

from __future__ import annotations

from typing import Annotated, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository


@inject
def _read_digest(
    input_hash: str,
    graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
) -> str:
    repo = NodeRepository()
    input_node = repo.find_by_hash(input_hash, node_type=Input)

    if not input_node:
        return f"Input not found: {input_hash}"

    if not input_node.digest:
        return f"No digest yet for input {input_node.short_hash}. Use digest_input to generate one."

    return input_node.digest


@llm.tool
async def read_digest(
    input_hash: Annotated[str, Field(description="Hash of the Input node")],
) -> str:
    """Read the current analytical digest of an input source. Use to see what the framework currently understands about a source before deciding to refine or pull full content."""
    return _read_digest(input_hash)
