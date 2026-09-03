"""
SourceDigest: Concern for generating and refining the living digest of an Input source.

The digest is the framework's evolving understanding of a source — not a naked summary,
but a directed analytical document shaped by both the source material and user/framework
guidance.

A source larger than one prompt is READ IN PARTS (`utils/chunking.py`): a reading
per window, then one reduce over the readings. Coverage is the guarantee — a
digest of the first few pages that presents itself as the understanding of the
source is a lie nothing downstream can detect, since the digest is what every
other concern reasons from.

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

import asyncio
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
from dialectical_framework.utils.chunking import chunk_text

logger = logging.getLogger(__name__)

DIGEST_THRESHOLD = 1500

#: How many part-readings may be in flight at once when a long source is read in
#: parts. A module constant, not a setting, per "Policy is not config".
#:
#: Every other fan-out in the tree gathers without a private bound, and rightly:
#: their width comes from graph structure the framework itself produced (edge
#: pairs, candidates, wheels), so it is bounded by `max_wheel_layer` and the
#: like. This one's width is the SIZE OF A FILE SOMEBODY PASTED — 1.2 MB is 30
#: windows and a 10 MB source is 250, all opened in the same instant. Past the
#: provider's ceiling that is not parallelism, it is the throttle ladder: 10
#: attempts backing off to 60s, paid on most of the calls, so a wider gather
#: finishes LATER than a narrower one while costing the same tokens. 8 keeps the
#: overlap that makes this fast (the reduce still waits for the slowest window)
#: without turning file size into request rate.
#:
#: `DIALEXITY_MAX_CONCURRENT_LLM_CALLS` remains the process-wide lever and
#: composes with this: it is disabled by default, and it cannot express "bound
#: THIS fan-out" without bounding every other one too.
MAX_CONCURRENT_PART_READINGS = 8

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

PART_SYSTEM_PROMPT = """You are an analytical reader working through ONE PART of a longer source.

Read the part you are given and report what it contains:

1. The key claims, arguments, and positions stated in THIS part
2. Important details, examples, and data points that ground them
3. Any domain, stakeholder, or discourse signals visible here

Two rules matter more than concision:

- Report only what this part says. You cannot see the rest of the source, so do
  not infer what the whole document argues, and do not present a conclusion the
  part does not state.
- Preserve specifics exactly: numbers, shares, dates, named events, quoted
  wording. A later pass combines these part-readings and cannot recover a figure
  you rounded away or a name you generalised.

Parts overlap slightly, so material may repeat from the previous part. That is
expected — report it as you find it."""

COMBINE_SYSTEM_PROMPT = """You are an analytical reader assembling ONE digest of a source you have read in parts.

You are given the part-readings in document order. Produce the digest of the
whole source:

1. Capture the key claims, arguments, and positions of the source as a whole
2. Keep the details, examples, and data points that ground them
3. Identify the domain, stakeholders, and discourse context
4. Preserve enough specificity that the source can be reasoned about without re-reading it in full

The parts overlapped, so the same claim may appear in two readings — merge such
repetitions rather than listing them twice. Where the readings genuinely disagree
or a position develops across the source, say so; a source that argues with
itself is a finding, not a defect to smooth over.

Never invent a synthesis the parts do not support, and never drop a figure, date
or name a part preserved.

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
        # Only text can be chunked — a window into an image or a PDF part is
        # meaningless, and `SourceDigest` is the sole `resolve_native` consumer,
        # so media always takes the single native pass below.
        if isinstance(content, str):
            chunks = chunk_text(content)
            if len(chunks) > 1:
                return await self._generate_digest_from_parts(
                    chunks, existing_digest, context
                )

        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        prompt = self._build_prompt(content, existing_digest, context)

        result = await self._conversation.submit(
            response_model=DigestDto,
            user_content=prompt,
        )

        self._report.artifacts["reasoning"] = result.reasoning
        return result.digest

    async def _generate_digest_from_parts(
        self,
        chunks: list[str],
        existing_digest: str | None,
        context: str,
    ) -> str:
        """Map a reading over every part, then reduce the readings to one digest.

        A source too big for one prompt used to be interpolated whole anyway
        (`_build_prompt` f-strings it in), so three 400 KB files meant ~300k
        tokens per call and, past the provider's window, an error instead of a
        digest. Truncating to the head would be worse than the error: the digest
        is what every downstream concern reasons from, and one describing the
        first few pages while presenting itself as the understanding of the
        source is a lie the rest of the pipeline cannot detect.

        So every part is read, and coverage is the guarantee (`chunk_text`), not
        best-effort. The reduce step is where the source becomes one thing again.
        """
        total = len(chunks)

        # A FRESH facilitator per part, and this is the load-bearing detail of the
        # whole method: `self._conversation` is one conversation, so reusing it
        # would accumulate every part in its history and the last call would
        # carry the entire document — exactly the send this exists to avoid,
        # arrived at by a longer road.
        # Bounded, because this fan-out's width is a pasted file's size — see
        # MAX_CONCURRENT_PART_READINGS. The semaphore is built here rather than
        # module-level: one bound per digest, and an `asyncio.Semaphore` created
        # at import binds to whichever loop happens to be running.
        slots = asyncio.Semaphore(MAX_CONCURRENT_PART_READINGS)

        async def _read_part(index: int, chunk: str) -> str:
            async with slots:
                conversation = ConversationFacilitator()
                conversation.set_system_prompt(PART_SYSTEM_PROMPT)
                result = await conversation.submit(
                    response_model=DigestDto,
                    user_content=self._build_part_prompt(chunk, index, total, context),
                )
                return result.digest

        # `gather` preserves ARGUMENT order, not completion order, and the reduce
        # depends on that: readings shuffled into completion order would hand the
        # model a document whose argument develops backwards.
        part_digests = await asyncio.gather(
            *[_read_part(i, chunk) for i, chunk in enumerate(chunks, start=1)]
        )

        # The reduce may reuse `self._conversation`: it sees the readings, which
        # are short, and never the parts.
        self._conversation.set_system_prompt(COMBINE_SYSTEM_PROMPT)
        result = await self._conversation.submit(
            response_model=DigestDto,
            user_content=self._build_combine_prompt(
                list(part_digests), existing_digest, context
            ),
        )

        self._report.artifacts["chunks"] = total
        self._report.artifacts["reasoning"] = result.reasoning
        return result.digest

    def _build_part_prompt(
        self,
        chunk: str,
        index: int,
        total: int,
        context: str,
    ) -> str:
        """Prompt for ONE part, framed so it cannot mistake itself for the whole.

        The position is stated twice — in the instruction and on the tag — because
        a model handed a few thousand words with no frame writes "this document
        argues X", and that sentence survives into the combined digest as a claim
        about the source.
        """
        sections = [
            f"You are reading part {index} of {total} of a source that was split "
            f"because it does not fit in one reading. This is a PART, not the "
            f"whole source: earlier and later material exists that you cannot see."
        ]

        if context:
            sections.append(f"<context>\n{context}\n</context>")

        sections.append(
            f'<source_part index="{index}" of="{total}">\n{chunk}\n</source_part>'
        )
        sections.append(
            "Report what this part contains, preserving its specifics. Do not "
            "summarise the source as a whole — you have not seen it."
        )

        return "\n\n".join(sections)

    def _build_combine_prompt(
        self,
        part_digests: list[str],
        existing_digest: str | None,
        context: str,
    ) -> str:
        """Prompt for the reduce step: the readings, in document order."""
        sections = []

        if existing_digest:
            sections.append(f"<existing_digest>\n{existing_digest}\n</existing_digest>")

        if context:
            sections.append(f"<context>\n{context}\n</context>")

        total = len(part_digests)
        readings = "\n\n".join(
            f'<part index="{i}" of="{total}">\n{digest}\n</part>'
            for i, digest in enumerate(part_digests, start=1)
        )
        sections.append(f"<source_read_in_parts>\n{readings}\n</source_read_in_parts>")

        if existing_digest:
            sections.append(
                "Refine the existing digest using these part-readings and the "
                "context provided. Sharpen focus, add relevant details, remove "
                "irrelevant parts."
            )
        else:
            sections.append(
                "Produce one analytical digest of the whole source from these "
                "part-readings."
            )

        return "\n\n".join(sections)

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
