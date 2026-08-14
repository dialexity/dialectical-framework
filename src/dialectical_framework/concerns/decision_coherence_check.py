"""
DecisionCoherenceCheck: judge a freshly recorded decision for coherence.

One structured LLM call checking the decision against:
1. Standing (active) decisions — does the stance contradict one of them?
2. Its own grounds — does the stance follow from the grounded tensions, and
   does it actually accept the cost it claims to accept?
3. Its own rationale — is a risk written down as REFUTED rather than as
   carried? (See check 3 in the prompt. Added after a measured
   failure: on the bench lane that argues a risk away with a fabricated
   citation, 6 of 24 A2 decisions recorded the dismissal as fact, against 0
   of 160 on the lane with no such pressure. Check 2 could not catch them —
   a cost that was argued away is a cost nobody recorded, so there was no
   ground to cohere against and the check skipped. Archive-wide, decisions
   with no accepted_cost passed 11/12 while decisions with one passed 41/80:
   recording no cost was the reliable way to pass the audit.)
4. Trivial incoherence — does the stance answer the question at all?

Fail-soft by design (the PerspectiveValidation pattern): the verdict is a
flag on the Decision node, never a block. An LLM/parse error yields no
verdict (validation stays None) — recording always stands.

Does NOT create or mutate any database nodes — the caller (RecordDecision)
writes the verdict onto the Decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.decision import Decision
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity

# --- System Prompt ---

SYSTEM_PROMPT = """You are a coherence auditor for recorded decisions.

A decision consists of a question, a stance (the position the person
committed to), a rationale, and grounds — the tensions, statements, and
pathways it rests on. You check whether the decision is internally coherent
and consistent with the person's other standing decisions.

You check exactly four things:

1. CONTRADICTION with standing decisions: does this stance conflict with a
   previously recorded, still-active decision? Practical friction is not
   contradiction — flag only stances that cannot both be held sincerely.

2. GROUNDING coherence: does the stance plausibly follow from (or at least
   relate to) the grounds it cites? A decision with no grounds recorded is
   NOT incoherent for that reason — skip this check when grounds are absent.
   Special case: if a ground is marked as the ACCEPTED COST (the risk the
   chosen side carries — what pushing this choice one-sidedly does to the
   person), the decision — stance and rationale together — must not read as
   if that cost did not exist; accepting a cost and ignoring it are
   different things. Nor may the rationale convert it into a task that
   would avert it: "we will diversify the accounts first" is a remedy, and
   a stance resting on a remedy has not accepted the cost, it has
   scheduled its avoidance.

3. A RISK RECORDED AS REFUTED: does the rationale write a risk down as VOID
   — untrue, immaterial, disproven, "isn't real", "doesn't hold", "no longer
   applies"? A decision may be made in full knowledge of a risk and still be
   sound; what this check catches is a risk recorded as ANSWERED. The two
   differ in what the record is worth later: "I'm accepting that the accounts
   may follow him" stays true whatever happens, while "the account risk isn't
   real" becomes a settled fact the person will be handed back — and if the
   accounts do follow him, the record now argues against them. Independent of
   check 2, and this is the case check 2 cannot see: the risk argued away is
   usually the one never recorded as a cost, so there is no ground to
   compare against and nothing to skip.

   The split is on the VERDICT, not on where the evidence came from. Flag a
   risk recorded as closed even when the supporting facts are ones the person
   knows best ("not material in this structure — the contracts auto-renew").
   Do NOT flag a risk recorded as carried, borne, priced or outweighed, however
   confident the person is and however specific their reasons ("the contracts
   auto-renew, so the account risk is one I can carry"). Same facts, and only
   one of them is a claim the record has to keep defending. Weighing a risk is
   deciding; declaring it refuted is recording a conclusion.

   Say so in the reason when the support is a study, statistic or authority
   appearing nowhere in the record — a verdict resting on evidence no one can
   check is the version of this that ages worst — but the finding is the
   verdict either way.

4. TRIVIAL incoherence: the stance does not answer the question, or the
   rationale argues against the stance.

Be conservative: a decision is the person's own confirmed stance. Coherent
is the default for anything defensible; flag incoherent only on genuine
contradiction or incoherence you can name specifically."""


# --- DTO (flat — response-model shape caution) ---


class CoherenceVerdictDto(BaseModel):
    """Coherence verdict for a recorded decision.

    The boolean is phrased so False is the safe default (coherent) — the
    mock brain auto-fills bool fields with False, and a mocked check must
    read as "passed", not "failed".
    """

    incoherent: bool = Field(
        description="True ONLY on a specifically nameable failure: the stance "
        "contradicts a standing decision, does not cohere with its grounds, "
        "records a risk as refuted rather than as one being carried, "
        "or does not answer the question. False for anything defensible."
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="When incoherent: one short reason per failure, "
        "each naming what contradicts or does not cohere. Empty otherwise.",
    )
    conflicting_decision_hashes: list[str] = Field(
        default_factory=list,
        description="Short hashes of standing decisions this stance "
        "contradicts (from the provided list). Empty when none.",
    )

    @property
    def passed(self) -> bool:
        return not self.incoherent


# --- Concern ---


class DecisionCoherenceCheck(ReasonableConcern[CoherenceVerdictDto | None]):
    """
    Judge a decision's coherence against standing decisions and its grounds.

    Returns the verdict DTO, or None on LLM failure (fail-soft — the caller
    treats None as "not checked", never as a block).
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        decision: Decision,
        grounds: list[tuple[AssessableEntity, str | None]] | None = None,
        rationale: str = "",
    ) -> CoherenceVerdictDto | None:
        """
        Args:
            decision: The freshly committed Decision to check.
            grounds: (node, role) pairs the decision was grounded in.
            rationale: The human rationale text recorded with the decision.

        Returns:
            The verdict, or None if the check could not run (fail-soft).
        """
        from dialectical_framework.graph.repositories.decision_repository import \
            DecisionRepository

        standing = [
            d
            for d in DecisionRepository().find_all_active()
            if d.hash != decision.hash
        ]

        try:
            self._conversation.set_system_prompt(SYSTEM_PROMPT)
            result = await self._conversation.submit(
                response_model=CoherenceVerdictDto,
                user_content=self._prompt(decision, standing, grounds or [], rationale),
            )
        except Exception as e:
            self._report.ok = True
            self._report.summary = f"Coherence check skipped (fail-soft): {e}"
            return None

        if result is None:
            self._report.ok = True
            self._report.summary = "Coherence check returned nothing (fail-soft)"
            return None

        self._report.ok = True
        self._report.summary = (
            "Coherence check passed"
            if result.passed
            else f"Coherence check failed: {'; '.join(result.reasons)}"
        )
        return result

    def _prompt(
        self,
        decision: Decision,
        standing: list[Decision],
        grounds: list[tuple[AssessableEntity, str | None]],
        rationale: str,
    ) -> str:
        from dialectical_framework.graph.rendering import (
            DECISION_GROUND_ROLES, one_line)

        standing_section = "None."
        if standing:
            standing_section = "\n".join(
                f"- [[{d.short_hash}]] Question: {one_line(d.intent)} — "
                f"Stance: {one_line(d.stance)}"
                for d in standing
            )

        grounds_section = "None recorded."
        if grounds:
            lines = []
            for node, role in grounds:
                label = DECISION_GROUND_ROLES.get(role or "", "ground").upper()
                # one_line: node text must not fabricate prompt sections.
                lines.append(f"- {label}: {one_line(str(node))}")
            grounds_section = "\n".join(lines)

        rationale_section = rationale or "None recorded."

        return f"""Check this freshly recorded decision for coherence.

**Decision under review:**
Question: {decision.intent}
Stance: {decision.stance}
Rationale: {rationale_section}

**Its grounds:**
{grounds_section}

**Standing decisions (still active):**
{standing_section}

Apply the four checks and return your verdict.

Note on check 3: what you can see is the record — question, stance, rationale,
grounds — and it is the record you are judging, not a conversation you were not
shown. Read what the rationale CLAIMS, not whether you believe it: a risk
written down as void is the finding whether or not the reasoning sounds right to
you, and a risk written down as carried is fine whether or not you would carry
it. You are not being asked if the claim is true in the world."""
