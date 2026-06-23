"""
SourceDigest: Concern for generating and refining the living digest of an Input source.

The digest is the framework's evolving understanding of a source — not a naked summary,
but a directed analytical document shaped by both the source material and user/framework
guidance.

Programmatic usage:
    concern = SourceDigest()
    input_node = await concern.resolve(input_hash="abc123")

    # Refine with context
    concern = SourceDigest()
    input_node = await concern.resolve(
        input_hash="abc123",
        context="User says: focus on regulatory tensions",
    )
"""

from __future__ import annotations

from typing import Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver

DIGEST_THRESHOLD = 1500

SYSTEM_PROMPT = """You are an analytical reader producing a **digest** — a living document that captures understanding of a source.

The digest should:

1. Capture the key claims, arguments, and positions in the material
2. Note important details, examples, and data points that ground the claims
3. Identify the domain, stakeholders, and discourse context
4. Preserve enough specificity that the source can be reasoned about without re-reading it in full

When refining an existing digest with new context:
- Incorporate the guidance or learnings provided
- Sharpen focus on aspects identified as relevant
- Remove or de-emphasize aspects identified as irrelevant
- Keep the digest self-contained — it should make sense on its own

Keep the digest concise but substantive — aim for the minimum text that preserves analytical utility."""


class DigestDto(BaseModel):
    """Structured output for digest generation."""

    digest: str = Field(
        description="The analytical digest text"
    )
    reasoning: str = Field(
        description="Brief explanation of what was emphasized and why"
    )


class SourceDigest(ReasonableConcern[Input], SettingsAware):
    """
    Generates or refines the analytical digest for an Input node.

    Resolves the full content, applies threshold logic (short content
    is used as its own digest without an LLM call), then persists the
    result back to the Input's digest field.

    Programmatic usage:
        concern = SourceDigest()
        input_node = await concern.resolve(input_hash="abc123", context="focus on X")
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

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
            new_digest = await self._generate_digest(
                content=resolved_content,
                existing_digest=input_node.digest,
                context=context,
            )
            self._report.summary = f"Digest {'refined' if input_node.digest else 'created'} for input {input_node.short_hash}"

        input_node.digest = new_digest
        input_node.save()

        self._report.ok = True
        self._report.artifacts["input_hash"] = input_node.short_hash
        self._report.artifacts["digest"] = new_digest

        return input_node

    async def _generate_digest(
        self,
        content: str,
        existing_digest: str | None = None,
        context: str = "",
    ) -> str:
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        prompt = self._build_prompt(content, existing_digest, context)

        result = await self._conversation.submit(
            response_model=DigestDto,
            user_content=prompt,
        )

        self._report.artifacts["reasoning"] = result.reasoning
        return result.digest

    def _build_prompt(
        self,
        content: str,
        existing_digest: str | None,
        context: str,
    ) -> str:
        sections = []

        if existing_digest:
            sections.append(f"<existing_digest>\n{existing_digest}\n</existing_digest>")
            if context:
                sections.append(f"<context>\n{context}\n</context>")
            sections.append(f"<source>\n{content}\n</source>")
            sections.append(
                "Refine the existing digest incorporating the context provided. "
                "Sharpen focus, add relevant details, remove irrelevant parts."
            )
        else:
            if context:
                sections.append(f"<context>\n{context}\n</context>")
            sections.append(f"<source>\n{content}\n</source>")
            sections.append(
                "Generate an initial analytical digest of this source."
            )

        return "\n\n".join(sections)
