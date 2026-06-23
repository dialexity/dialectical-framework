"""
DigestInput: Concern + tool for generating/refining the living digest of an Input source.
"""

from __future__ import annotations

from typing import Annotated, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.source_digest import SourceDigest
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.protocols.input_resolver import InputResolver


# Content shorter than this is used as its own digest (no LLM call needed)
DIGEST_THRESHOLD = 1500


class DigestInput(ReasonableConcern[Input]):
    """
    Generates or refines the digest for an Input node.

    Resolves the full content, runs SourceDigest with any provided context,
    and persists the result to the Input's digest field.

    Short content (under ~1500 chars) is used directly as the digest
    without an LLM call — it's already compact enough.
    """

    @inject
    async def resolve(
        self,
        input_hash: str,
        context: str = "",
        input_resolver: InputResolver = Provide[DI.input_resolver],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Input:
        repo = NodeRepository()
        input_node = repo.find_by_hash(input_hash, node_type=Input)

        if not input_node:
            raise ValueError(f"Input not found: {input_hash}")

        resolved_content = await input_resolver.resolve(input_node)
        if not resolved_content:
            raise ValueError(f"Input {input_hash} has no resolvable content")

        if len(resolved_content) <= DIGEST_THRESHOLD and not input_node.digest:
            new_digest = resolved_content
            self._report.summary = f"Content compact enough to use as digest for input {input_node.short_hash}"
        else:
            concern = SourceDigest()
            new_digest = await concern.resolve(
                content=resolved_content,
                existing_digest=input_node.digest,
                context=context,
            )
            self._report = self._report.merge(concern.report)
            self._report.summary = f"Digest {'refined' if input_node.digest else 'created'} for input {input_node.short_hash}"

        input_node.digest = new_digest
        input_node.save()

        self._report.ok = True
        self._report.artifacts["input_hash"] = input_node.short_hash
        self._report.artifacts["digest"] = new_digest

        return input_node


@llm.tool
async def digest_input(
    input_hash: Annotated[str, Field(description="Hash of the Input node to digest")],
    context: Annotated[
        str,
        Field(
            description="Direction for the digest: user guidance, framework state, or focus instructions"
        ),
    ] = "",
) -> str:
    """Generate or refine the analytical digest of an input source. Use to build initial understanding of new inputs, or to sharpen the digest with user direction or framework learnings."""
    concern = DigestInput()
    await concern.resolve(input_hash=input_hash, context=context)
    return str(concern.report)
