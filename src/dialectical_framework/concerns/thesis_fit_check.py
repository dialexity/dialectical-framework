"""
ThesisFitCheck: does a drawn tetrad stand on the claim the person actually
made, against an opposition they have not already granted?

WHY A SECOND JUDGE
==================
The best-of-N selector (`concerns/tetrad_candidates.py`) ranks draws by the
control statements (`ControlStatementsCheck.score_texts`), which never see T
or A. That judge answers "does this tetrad hold?", and it answers it well
(92% agreement with itself). It cannot answer "is this the tetrad of the claim
the person made?" — and on a multi-claim input the two come apart: a tetrad
about a hedge ("society has the right to ask") degenerates more coherently
than one about the demand the person would sign ("stop mass migration"), so a
coherence-only ranking prefers the hedge. The first app's handoff of
2026-10-20 (`docs/handoff-2026-10-20-thesis-choice.md`) found exactly that:
the writer drew the demand twice among three draws and the ranking threw it
away, and the chosen A+ was a clause the person had typed and conceded
("not only schools, but also"), handed back to them as their blind spot.

This judge reads T, A and A+ against the person's own words and scores two
things, both the handoff's: whether T is the claim they would SIGN (the
conclusion or demand, not a premise or a hedge on the way to it), and whether
A+ is something their words do NOT already grant. The fit is the weaker of
the two. It is a SELECTION term — it ranks draws the writer already made,
after the coherence floor (`tetrad_candidates.ranking`) — never a signal fed
back into generation; the rule against regeneration from a verdict stands.

One call per draw, the two questions in one call, the draw judged on its
own: a comparative read of the whole field picks by position (the joint
coherence judge measured 29/40 first-listed winners, 2026-10-06), and the
two questions here are each a draw against the material, not against the
other draws. Fail-soft: a failed judging is `None`, and `None` means "not
judged", which the ranking treats as fitting — a provider error must never
demote a draw that was otherwise best.

The judge itself is MEASURED, its effect on a choice is not (2026-10-26,
`tests/e2e/probe_thesis_fit_judge.py`, Sonnet 5.5, stored view-turn draws,
nothing generated). Stable: 40/40 stored draws re-judged twice agreed on
`fits`, mean |fit| shift 0.011, no read crossing the threshold. And nearly
INERT on the single-claim sets this archive holds: of 120 stored fields
(a winner and its spares) 6 split on `fits` — only there can the term move
a choice — 114 passed unanimously and none failed unanimously, while a
spare outscored its winner in 33/120 without crossing the line. So it
cannot disturb a keep-any-passing figure here, and it cannot help here
either: the shape it was written for, a multi-claim input where one draw
bears the demand and another the hedge, is still UNMEASURED for want of
such a case set. The two prompt rules beside it are unmeasured too.

This judge does not think, so it parses on either transport. The view-turn
arm of the same gate did not, until the Mirascope floor moved to 2.8.2 on
2026-10-26: the view turn is the one structured call that THINKS, the
framework's thinking-shape translation is applied in
`utils/bedrock_provider.py::_encode` alone, and Mirascope 2.5 sent every
level as the legacy token budget — 40/40 draws came back 400
("thinking.type.enabled is not supported for this model"). 2.8.2 emits the
adaptive shape itself. The off-policy and the learned-shape retry are still
Bedrock-only (see CLAUDE.md), so say which transport a figure came from.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator

#: Below this the draw is NOT about the person's claim, or opposes it with
#: what they already granted, and sorts under every draw that fits. A float
#: because the judge scores one, a threshold because the ranking reads a
#: yes/no: among fitting draws the coherence floor decides, as before this
#: term existed. Policy, not config.
THESIS_FIT_THRESHOLD = 0.5


class ThesisFitDto(BaseModel):
    """The two reads, scored before the reasoning."""

    thesis_is_the_claim: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Is the thesis the claim the person would SIGN — the conclusion or "
            "demand their words lead to? 1.0: it is that claim. 0.0: it is a "
            "premise, a hedge or a concession on the way to it ('we have the "
            "right to ask' when they go on to demand; 'X matters, but' when "
            "they then argue against X)."
        ),
    )
    a_plus_already_granted: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Do the person's own words ALREADY name and concede what A+ says? "
            "1.0: they wrote it themselves ('not only X but also Y' concedes X). "
            "0.0: it is a constructive side of the opposition they have not seen."
        ),
    )
    reasoning: str = Field(description="Two sentences: which claim they would sign, and whether A+ is in their words.")

    @property
    def fit(self) -> float:
        """The weaker of the two reads, as the control statements take the
        weaker statement: a draw on the right claim against a granted
        opposition fits no better than a draw on the wrong claim."""
        return min(self.thesis_is_the_claim, 1.0 - self.a_plus_already_granted)


class ThesisFitCheck:
    """Text-only, graph-free, no report: a judge the selector gathers."""

    async def score_texts(
        self, *, thesis: str, antithesis: str, a_plus: str, text: str
    ) -> ThesisFitDto:
        """Both reads in one call. `text` is the person's own words (the view
        turn's `judge_context`, the build's material) and is required: with
        nothing to read against, neither question can be answered, and the
        caller skips the judge instead of asking it blind."""
        prompt = f"""<context>
{text}
</context>

A dialectical tetrad was drawn from what the person said above. Read its thesis, its antithesis and the constructive side of the antithesis against their words, and rate two things independently.

Thesis (T): "{thesis}"
Antithesis (A): "{antithesis}"
Constructive side of A (A+): "{a_plus}"

1. Is T the claim the person would sign? When their words hold several claims, the one they would sign is the conclusion or demand the rest leads to — not a premise, not a hedge on the way to it, and not a claim they concede in passing ("not only X but also Y" concedes X and argues for Y).

2. Do the person's own words already name AND concede what A+ says? An opposition they have conceded themselves is seen, not missing; a tetrad on it shows them their own sentence as a blind spot."""
        return await ConversationFacilitator().submit(
            response_model=ThesisFitDto, user_content=prompt
        )
