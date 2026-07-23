"""
StatementHeadline: Condense a verbatim statement into a headline-length label.

Generation/extraction paths (thesis_extraction, aspect_generation, synthesis_
generation, ...) already clamp their output to `settings.component_length`. The
`anchor` path does NOT — it hands the agent's raw string straight to
StatementClassification, which only classifies and echoes the text verbatim. A
chatty agent can therefore anchor a 25-word paragraph as a "thesis".

This concern closes that gap: it condenses over-long statements to a headline of
~component_length words while preserving the core assertion. Statements already
within budget are returned unchanged with NO LLM call — so anchoring a bare
concept like "Trust" stays free.

Does NOT create any database nodes — caller decides what to do with the result.

Usage:
    headliner = StatementHeadline()
    headline = await headliner.resolve(statement=long_text, text=context)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.protocols.has_config import SettingsAware

# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical statement editor.

Your task is to condense a verbose statement into a short, memorable headline
that names the same position — without softening, neutralizing, or negating it.

Rules:
- Keep the ORIGINAL claim and its direction. A thesis stays a thesis; do not
  turn "X should lead" into "X vs Y" or into a neutral topic label.
- Drop supporting detail, enumerated mechanisms, and em-dash asides. Those live
  elsewhere; the headline is the essence.
- Produce a declarative fragment, not an instruction and not a question.
- No trailing punctuation, no quotes."""


# --- DTO ---


class HeadlineDto(BaseModel):
    """Condensed headline for a statement."""

    headline: str = Field(
        description="Short declarative headline naming the same position as the original"
    )


# --- Concern ---


class StatementHeadline(ReasonableConcern[str], SettingsAware):
    """
    Condense an over-long statement into a headline of ~component_length words.

    Statements already within the word budget are returned unchanged without an
    LLM call. Never creates database nodes.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(self, statement: str, text: str = "") -> str:
        """
        Condense `statement` to a headline if it exceeds the word budget.

        Args:
            statement: The statement text to condense.
            text: Optional source context to disambiguate domain terms.

        Returns:
            The original text (if already within budget) or a condensed headline.
        """
        original = statement.strip() if statement else ""

        if not original:
            self._report.ok = True
            self._report.summary = "Empty statement — nothing to condense"
            return original

        max_words = self.settings.component_length

        # Short-circuit: already a headline, no LLM call needed.
        if len(original.split()) <= max_words:
            self._report.ok = True
            self._report.summary = "Statement already within word budget"
            return original

        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        result = await self._conversation.submit(
            response_model=HeadlineDto,
            user_content=self._prompt(original, text, max_words),
        )

        headline = (result.headline or "").strip() if result else ""
        if not headline:
            # Fall back to the original rather than dropping the statement.
            self._report.ok = True
            self._report.summary = "Condensation returned empty — kept original"
            return original

        self._report.ok = True
        self._report.summary = f'Condensed statement to headline: "{headline}"'
        return headline

    def _prompt(self, statement: str, text: str, max_words: int) -> str:
        """Build the condensation prompt."""
        text_section = ""
        if text:
            text_section = f"""
**Background context (for understanding only — do not summarize it):**
{text[:1500]}{"..." if len(text) > 1500 else ""}
"""

        return f"""Condense this statement into a headline of approximately {max_words} words.

Statement: "{statement}"
{text_section}
Preserve the claim and its direction; strip mechanisms, examples, and em-dash
asides. Return a declarative fragment of about {max_words} words."""
