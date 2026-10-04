"""
StanceCapture: the intake gate — is there a STANCE in what the person typed?

Why this exists. The blindspot card is A+ against a T the person recognises as
their own, and the one-shot writers find T in free words. Measured on 20
questions (`tests/e2e/probe_question_entry.py`, 2026-10-04): the view turn
NEVER declines — 20/20 drew, including "What is dialectical thinking?" and
"How much runway should a seed startup keep?", each with a confident tetrad
around a stance nobody took; and on the five open forks ("Zurich or
Vilnius?") it picked an option, usually the first one, as the person's
position. A card built on a guessed T hands the person the constructive side
of a position they do not hold — the reveal inverted — so the host asks ONE
question first where the words do not carry a stance.

The gate is a STRUCTURED call, not a conversation turn: it returns either a
stance or one question, never prose, because a free turn told to "just get the
point" becomes a counsellor (prompt instructions measurably do not hold —
CLAUDE.md, build policy). Exclusivity is enforced here in code, not asked of
the model. The host loops it with a cap (`MAX_INTAKE_ASKS`): on the last pass
it builds on the best guess and the card says "your position, as I heard it",
because a person stuck in intake has already lost the moment.

What a stance IS is `view_sketch.THESIS_IS_A_STANCE` — one text for the gate
and both writers, so a question the gate passes as carrying a lean is read
the same way by the call that then draws it. Nothing persisted; no graph.

Usage:
    captured = await StanceCapture().resolve(turns=["Should I take Zurich or stay?"])
    if captured.stance:   # run the algorithm, pinning captured.stance as T
    else:                 # show captured.ask, append the answer to turns, call again
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.view_sketch import THESIS_IS_A_STANCE

#: How many questions the gate may ask before the host builds on its best
#: guess. Policy, not config: tarot's one lesson is never a dead end, and a
#: third question is a dead end. Nobody deploys a different number.
MAX_INTAKE_ASKS = 2

#: The gate's own questions when the model names the shape but leaves `ask`
#: empty. Person-facing: no framework vocabulary.
FORK_ASK = "Which way are you leaning, before you think it through?"
NO_STANCE_ASK = (
    "I can only work with a position you hold. Say what you're about to do, "
    "or what you think should happen — in one line."
)

SYSTEM_PROMPT = f"""You read what a person typed and decide ONE thing: is there a position of theirs in it yet?

{THESIS_IS_A_STANCE}

Three shapes, and you name which:
- STANCE: the words carry a position the person holds, wants or is about to do — stated outright, leaning through a question, or presupposed by a complaint ("why does my manager take credit for everything I do" carries "my work deserves the credit"). Write it as one first-person line in their own words. Do not add a position they did not take.
- FORK: the words are genuinely open between options and lean to none ("Zurich or Vilnius?", "build or buy?"). Ask the one question that gets their lean.
- NONE: nothing in the words is a position anyone holds — a request for information, a definition, a recipe. Ask for a position, in one line, saying plainly what you can work with.

The question you ask, when you ask one, is chosen for THESE words, not generic:
- an open fork → which way they lean, before they think it through
- a complaint about someone else → what they think should happen
- a wish or a feeling → what they are going to do about it
- nothing at all → what to type instead: what they are about to do, or what they believe should happen
One question, one line, no advice, no preamble."""


class StanceCaptureDto(BaseModel):
    """The gate's answer: a shape, and the one field that shape fills."""

    shape: Literal["stance", "fork", "none"] = Field(
        description=(
            "STANCE: a position of the person's is in the words. FORK: open between "
            "options, no lean. NONE: no position anyone holds — informational."
        )
    )
    stance: str = Field(
        description=(
            "The position as one first-person line in the person's own words. Filled "
            "ONLY when shape is 'stance'; empty otherwise."
        )
    )
    ask: str = Field(
        description=(
            "The one question that would get their position. Filled ONLY when shape "
            "is 'fork' or 'none'; empty when shape is 'stance'."
        )
    )


@dataclass(frozen=True)
class StanceCaptured:
    """Exactly one of `stance` / `ask` is set — enforced by `StanceCapture`."""

    shape: Literal["stance", "fork", "none"]
    stance: Optional[str]
    ask: Optional[str]

    @property
    def found(self) -> bool:
        return self.stance is not None


class StanceCapture(ReasonableConcern[StanceCaptured]):
    """One structured call over the person's turns so far → a stance or one
    question. Stateless; the host keeps the turns and the ask count."""

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(self, turns: list[str]) -> StanceCaptured:
        """`turns` is everything the person has typed in this intake, oldest
        first — the opening line plus their answers to the gate's questions."""
        words = [t.strip() for t in turns if t and t.strip()]
        if not words:
            self._report.ok = True
            self._report.summary = "Nothing typed yet — asked for a position"
            return StanceCaptured(shape="none", stance=None, ask=NO_STANCE_ASK)

        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        result = await self._conversation.submit(
            response_model=StanceCaptureDto,
            user_content=self._prompt(words),
        )
        captured = self._settle(result)
        self._report.ok = True
        self._report.summary = (
            f'Stance: "{captured.stance}"' if captured.found else f"{captured.shape}: asked «{captured.ask}»"
        )
        return captured

    @staticmethod
    def _settle(result: Optional[StanceCaptureDto]) -> StanceCaptured:
        """Exclusivity in code: a stance wins when the shape says stance AND the
        line is there; anything else is a question, the model's or the gate's
        own for that shape. A 'stance' shape with an empty line is NONE — a
        blank is never built on."""
        shape = result.shape if result else "none"
        stance = (result.stance or "").strip() if result else ""
        ask = (result.ask or "").strip() if result else ""
        if shape == "stance" and stance:
            return StanceCaptured(shape="stance", stance=stance, ask=None)
        if shape == "fork":
            return StanceCaptured(shape="fork", stance=None, ask=ask or FORK_ASK)
        return StanceCaptured(shape="none", stance=None, ask=ask or NO_STANCE_ASK)

    @staticmethod
    def _prompt(words: list[str]) -> str:
        if len(words) == 1:
            typed = f'The person typed:\n"{words[0]}"'
        else:
            lines = "\n".join(f'{i}. "{w}"' for i, w in enumerate(words, 1))
            typed = f"The person typed, in order (later lines answer the questions asked in between):\n{lines}"
        return f"{typed}\n\nName the shape and fill the one field for it."
