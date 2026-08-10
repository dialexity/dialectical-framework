"""
DecisionConfirmationCheck: did the person just confirm a decision for the record?

Why this exists as a host-driven check and not a prompt rule
------------------------------------------------------------
A decision is a **user-driven artefact**: it exists because the person declared
it. That declaration is an *observable event in their message*, not something
the assistant has to infer at its own discretion — so whether a record gets
written must not depend on the conversational model electing to call a tool at
exactly the moment it is most inclined to simply answer well.

Measured (`tests/bench/README.md`, "the ceremony is tier-gated"): with the same
prompt, the same tools and the same scenario, `record_decision` fired 6/6 at the
strong tier and **0/6** at the weak tier. The weak tier's failure was identical
every time — asked to "write that down as the decision", it produced a
beautifully formatted "Your Decision" section in prose with no tool call at all.
The person was told it was recorded; it was not, and the next session opened on
an empty ledger. Three rounds of prompt strengthening (the `_DECISION_READINESS`
prose, the `record_decision` tool doc, the `explore` call threshold) did not move
the weak tier at all.

`record_decision` already treats WHO confirmed as a host attestation rather than
an LLM parameter (`principal`). This check applies the same principle to
WHETHER: the host asks, after the turn, whether the person's own words confirmed
a decision that then went unrecorded. That is a small, bounded classification of
the user's message — not the open-ended judgement of when to close a
conversation — so it is the same kind of work a weak model does reliably.

Deliberately NOT a gate and NOT a silent recorder
-------------------------------------------------
This concern only *reports*. It creates no nodes and mutates nothing. It answers
"the person confirmed and nothing was written" so the caller can repair the turn
(see `Advisor._repair_unrecorded_decision`). Recording still runs through
`RecordDecision`, still carries the person's confirmed wording, and still stamps
the host-attested principal. Consent is not being bypassed — it is being
*honoured*: the person already said yes, and the framework's own rule is that
refusing to write down a decision the person has stated "is the one failure the
record exists to prevent".

Fail-soft (the PerspectiveValidation / DecisionCoherenceCheck pattern): an LLM
or parse failure yields None, which the caller reads as "no repair", never as a
block on the turn the person actually receives.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern

# --- System Prompt ---

SYSTEM_PROMPT = """You detect one specific speech act: a person CONFIRMING a
decision so that it gets written down as a record.

You are given the person's latest message and the assistant's reply to it. You
decide whether the person's own words confirmed a decision — not whether the
decision is wise, well-founded, or fully explored. That is someone else's job.

CONFIRMED (`confirmed: true`) looks like:
- "Write that down as the decision", "note that as decided", "log it"
- "That's settled", "I'm not second-guessing this", "decision made"
- A clear yes to the assistant's offer to record it ("yes, do that", "go ahead")
- Declaring the choice as closed rather than as a leaning: "I'm doing X — that's
  settled", "I've decided: X"
Confirmation does not have to be polite, complete, or well-phrased, and it does
NOT require the assistant to have offered first.

NOT confirmed (`confirmed: false`):
- Thinking aloud, leaning, weighing: "I'm probably going to X", "I'm leaning X",
  "X feels right but..."
- Asking for advice or a recommendation, even a pointed one
- Agreeing with a piece of REASONING rather than closing the choice ("that makes
  sense", "good point about the customers")
- Planning to decide later: "I'll decide by Friday", "let me sit with it"
- Talking about a decision they already made elsewhere, as background

The distinction is COMMITMENT, not certainty: a person can confirm a decision
they feel uneasy about, and can sound very sure while still only leaning.

When confirmed, extract the record from what was actually said, in the person's
own words — never invent, upgrade or tidy their reasoning:
- `question`: what was being decided
- `stance`: the position they committed to
- `rationale`: the why, as they and the assistant established it — include the
  cost or price they acknowledged accepting, if any was named. Do NOT convert a
  cost into a task that would avert it: "accepting that the accounts may follow
  him" is a cost; "diversify the accounts first" is a remedy, and a rationale
  resting on a remedy has not accepted anything.

Be conservative. A false "confirmed" writes a record the person never asked for,
which is worse than a missing one: it puts words in their mouth."""


# --- DTO (flat — response-model shape caution) ---


class ConfirmationVerdictDto(BaseModel):
    """Whether the person's message confirmed a decision for the record.

    Field order matters for the mocked suite: `confirmed` is a bool, which the
    mock brain fills with False, so a mocked run reads as "nothing to repair"
    and never fabricates a Decision node in tests that don't ask for one.
    """

    confirmed: bool = Field(
        default=False,
        description="True ONLY when the person's own words closed the choice "
        "and asked for or agreed to it being written down. False for leanings, "
        "requests for advice, agreement with reasoning, or intent to decide "
        "later."
    )
    question: str = Field(
        default="",
        description="What was being decided, in the person's words. Empty when "
        "not confirmed.",
    )
    stance: str = Field(
        default="",
        description="The position committed to, in the person's words. Empty "
        "when not confirmed.",
    )
    rationale: str = Field(
        default="",
        description="The distilled why as established in the conversation, "
        "including any cost the person acknowledged accepting. Empty when not "
        "confirmed.",
    )

    @property
    def is_recordable(self) -> bool:
        """Confirmed AND carrying the two fields a record cannot omit.

        `RecordDecision` refuses an empty question or stance in-band; checking
        here keeps that refusal out of the repair path, where it would look
        like a framework error rather than a non-event.
        """
        return self.confirmed and bool(self.question.strip()) and bool(
            self.stance.strip()
        )


# --- Concern ---


class DecisionConfirmationCheck(ReasonableConcern[ConfirmationVerdictDto | None]):
    """
    Classify whether a conversational turn contained a decision confirmation.

    Returns the verdict DTO, or None when the check could not run (fail-soft —
    the caller treats None as "no repair needed", never as a block).

    Creates and mutates nothing: the caller decides what to do with the verdict.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        user_message: str,
        assistant_message: str,
    ) -> ConfirmationVerdictDto | None:
        """
        Args:
            user_message: The person's latest message — where the speech act
                lives. This is the only place a confirmation can come from.
            assistant_message: The reply, for context (it may hold the record
                the person was agreeing to, and the reasoning behind it).

        Returns:
            The verdict, or None if the check could not run (fail-soft).
        """
        if not (user_message or "").strip():
            self._report.ok = True
            self._report.summary = "No user message to check"
            return None

        try:
            self._conversation.set_system_prompt(SYSTEM_PROMPT)
            result = await self._conversation.submit(
                response_model=ConfirmationVerdictDto,
                user_content=self._prompt(user_message, assistant_message),
            )
        except Exception as e:
            self._report.ok = True
            self._report.summary = f"Confirmation check skipped (fail-soft): {e}"
            return None

        if result is None:
            self._report.ok = True
            self._report.summary = "Confirmation check returned nothing (fail-soft)"
            return None

        self._report.ok = True
        self._report.summary = (
            f"Decision confirmed: {result.stance}"
            if result.is_recordable
            else "No decision confirmation in this turn"
        )
        return result

    @staticmethod
    def _prompt(user_message: str, assistant_message: str) -> str:
        return f"""Did the person confirm a decision for the record in this turn?

## The person said
{user_message}

## The assistant replied
{assistant_message or "(nothing)"}

Judge the PERSON's words for the confirmation. Use the reply only as context \
for what was being decided and why."""
