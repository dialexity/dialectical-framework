"""
read_input: Tool for pulling full resolved content from an Input source.

Used when the LLM decides the digest isn't enough and needs the full source text.
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
from dialectical_framework.protocols.input_resolver import InputResolver


@inject
async def _resolve_input(
    input_hash: str,
    input_resolver: InputResolver = Provide[DI.input_resolver],
    graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
) -> str:
    repo = NodeRepository()
    input_node = repo.find_by_hash(input_hash, node_type=Input)

    if not input_node:
        return f"Input not found: {input_hash}"

    resolved = await input_resolver.resolve(input_node)
    if not resolved:
        return f"Input {input_hash} has no content"

    return resolved


@llm.tool
async def read_input(
    input_hash: Annotated[str, Field(description="Hash of the Input node to read")],
) -> str:
    """Read the full source content of an input. Use when the digest doesn't have enough detail for your current task."""
    return await _resolve_input(input_hash)
