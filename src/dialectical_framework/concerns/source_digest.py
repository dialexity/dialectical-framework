"""
SourceDigest: Concern for generating and refining the living digest of an Input source.

The digest is the framework's evolving understanding of a source — not a naked summary,
but a directed analytical document shaped by both the source material and user/framework
guidance. It focuses on dialectical material: tensions, oppositions, values, assertions.

Usage:
    # Initial digest
    concern = SourceDigest()
    digest = await concern.resolve(content="Full text of the article...")

    # Refine with context
    concern = SourceDigest()
    digest = await concern.resolve(
        content="Full text...",
        existing_digest="Previous understanding...",
        context="User says: focus on regulatory tensions",
    )
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.protocols.has_config import SettingsAware

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
        description="The analytical digest text — focused on dialectical material"
    )
    reasoning: str = Field(
        description="Brief explanation of what was emphasized and why"
    )


class SourceDigest(ReasonableConcern[str], SettingsAware):
    """
    Generates or refines the analytical digest of an Input source.

    The digest captures the framework's evolving understanding of a source,
    shaped by both the content itself and any direction from the user or
    framework state (perspectives discovered, user guidance, etc.).
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        content: str,
        existing_digest: str | None = None,
        context: str = "",
    ) -> str:
        """
        Generate or refine a digest for source content.

        Args:
            content: The full resolved source text
            existing_digest: Current digest if refining (None for initial creation)
            context: Direction from user or framework state that should shape
                     the digest (e.g., "focus on ethical arguments",
                     "we've identified tension between growth and stability")

        Returns:
            The new digest text
        """
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        prompt = self._build_prompt(content, existing_digest, context)

        result = await self._conversation.submit(
            response_model=DigestDto,
            user_content=prompt,
        )

        self._report.ok = True
        self._report.artifacts["reasoning"] = result.reasoning
        if existing_digest:
            self._report.summary = "Refined existing digest"
        else:
            self._report.summary = "Generated initial digest"

        return result.digest

    def _build_prompt(
        self,
        content: str,
        existing_digest: str | None,
        context: str,
    ) -> str:
        """Build the user prompt based on whether this is creation or refinement."""
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
