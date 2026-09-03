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

import logging
from typing import TYPE_CHECKING, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from mirascope.llm import UserContent

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver

logger = logging.getLogger(__name__)

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

        resolved_content = await input_resolver.resolve_native(input_node)
        if not resolved_content:
            raise ValueError(f"Input {input_hash} has no resolvable content")

        is_text = isinstance(resolved_content, str)

        # Only text can be used verbatim as its own digest. Native media
        # (image/PDF parts) must always go through the model's vision pass —
        # there is no meaningful "raw content" to store as a digest.
        if (
            is_text
            and len(resolved_content) <= DIGEST_THRESHOLD
            and not input_node.digest
        ):
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
        content: UserContent,
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
        content: UserContent,
        existing_digest: str | None,
        context: str,
    ) -> UserContent:
        # Text sources are interpolated inline; native media (image/PDF parts)
        # are appended as a separate content part with a text placeholder in the
        # <source> slot so the model knows where the attached source belongs.
        is_text = isinstance(content, str)
        source_text = content if is_text else "(see the attached source below)"

        sections = []

        if existing_digest:
            sections.append(f"<existing_digest>\n{existing_digest}\n</existing_digest>")
            if context:
                sections.append(f"<context>\n{context}\n</context>")
            sections.append(f"<source>\n{source_text}\n</source>")
            sections.append(
                "Refine the existing digest incorporating the context provided. "
                "Sharpen focus, add relevant details, remove irrelevant parts."
            )
        else:
            if context:
                sections.append(f"<context>\n{context}\n</context>")
            sections.append(f"<source>\n{source_text}\n</source>")
            sections.append(
                "Generate an initial analytical digest of this source."
            )

        prompt_text = "\n\n".join(sections)

        if is_text:
            return prompt_text

        # Multimodal: text instructions followed by the native source part(s).
        parts: list = [prompt_text]
        if isinstance(content, (list, tuple)):
            parts.extend(content)
        else:
            parts.append(content)
        return parts


async def ensure_digest(
    input_hash: str,
    context: str = "",
    *,
    refresh: bool = False,
) -> str:
    """Digest an Input if it needs one. Never raises; returns a status note.

    "Whoever adds the input, digests it" was a convention two of the three
    capture sites did not keep: only `ingest` digested, while the `add_input`
    tool and `AnalysisPipeline`'s own capture left `Input.digest` empty. An
    undigested Input is not a cosmetic gap — `input_context` falls back to its
    full content for every downstream concern, so the whole analysis paid the
    raw source repeatedly (that rendering is bounded now, which turns the same
    gap from a failure into lost fidelity: the model reasons from the head of
    a document instead of an understanding of all of it).

    Fail-soft, and the whole point of the helper is that the three call sites
    fail-soft the SAME way. The digest is enrichment: perspectives are built
    from the rendered context either way, so a provider hiccup on a summary
    must not cost the analysis. The wide `except` is deliberate — the narrow
    `(ValueError, RuntimeError)` this replaces caught only `SourceDigest`'s own
    guards, the least likely failures at a capture site, and let provider,
    validation and fetch errors abort the caller.

    Takes a HASH, not the node object, and that is not a style choice. On a
    dedup hit `commit()` copies the stored node's `_id` onto the fresh object
    and returns THAT (`base_node.py`), so every mutable hash-excluded field —
    `digest` among them — reads as the caller's fresh value rather than what is
    stored. `AddInput` builds a new `Input(content=...)` every time, so the node
    it hands back reports `digest=None` even for material digested an hour ago.
    Deciding from the passed object therefore re-digested on every capture,
    which is exactly the double call this helper exists to avoid.

    Args:
        input_hash: Hash of a committed Input.
        context: Focus for the digest — the user's intent, where there is one.
        refresh: Re-run even when a digest exists, letting `SourceDigest`
            REFINE it toward `context`. True only where the caller has a fresh
            intent worth spending a call on (`ingest`); gap-filling callers
            leave it False so they never pay for work already done.

    Returns:
        One of "created", "refreshed", "already present", or a
        "failed softly (...)" note. Short on purpose: callers put this in a
        report the model pays for.
    """
    stored = NodeRepository().find_by_hash(input_hash, node_type=Input)
    existing_digest = stored.digest if stored else None

    if existing_digest and not refresh:
        return "already present"

    outcome = "refreshed" if existing_digest else "created"
    try:
        await SourceDigest().resolve(input_hash=input_hash, context=context)
    except Exception as e:  # noqa: BLE001
        # Loud, unlike the `pass` this replaces: that left no trace anywhere,
        # so `read_digest` returning nothing and `input_context` falling back
        # read as "not written yet" rather than "tried and failed". No retry
        # tool is named — `ingest` is Advisor-only and the Advisor carries
        # `read_digest` but NOT `digest_input`, so pointing at one would be a
        # dead off-ramp for the caller most likely to hit this.
        logger.warning("Digest generation failed softly for an input: %s", e)
        return (
            f"failed softly ({type(e).__name__}: {e}); no digest stored for "
            f"this input, so its source context is rendered from raw content"
        )
    return outcome
