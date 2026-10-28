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
2026-10-20 (`docs/dev-notes/antithesis-selection.md`, "The hedge wins on coherence") found exactly that:
the writer drew the demand twice among three draws and the ranking threw it
away, and the chosen A+ was a clause the person had typed and conceded
("not only schools, but also"), handed back to them as their blind spot.

This judge reads T, A and A+ against the person's own words and scores three
things: whether T is the claim they would SIGN (the conclusion or demand, not
a premise or a hedge on the way to it), whether A is a view their words
already GRANT (the pole; since 2026-10-28, below), and whether A+ is
something their words do NOT already grant. The fit is the weakest of
the three. It is a SELECTION term — it ranks draws the writer already made,
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

WHOSE claim (2026-10-27). Both reads presupposed authorship — "the claim the
PERSON would sign", "the PERSON's own words" — and the words a host hands as
`fit_against` are whatever the person pasted, which may carry only other
people's positions (`docs/dev-notes/views.md`, "Pasted material"). The view
turn names the holder of a T that is not the person's own
(`ViewSketchPerspectiveDto.thesis_held_by`), so `score_texts(held_by=)` takes
it and the two reads are asked about THAT party: the claim they would sign in
the words that report them, what their words concede. With no holder the
holder is the person speaking, as before — the shipped behaviour on the
person's own words is unchanged in substance, and the stability arm of the
gate below was re-run on the reworded judge the same day.

THE POLE, NOT ONLY ITS DEVELOPMENT (2026-10-28, the first app's third
handoff, retired into `docs/dev-notes/antithesis-selection.md`, "A is the view the
author granted"). The second read
asked about A+ alone, because the 2026-10-20 case had A+ as the typed clause.
The app's eval over the framework's own petition sets (29 rows whose conceded
clause grants a POSITION, two reps, Sonnet 5.5, Opus judge) found the failure
one level up: A itself is the view the author granted on 16 of 29, while A+
escapes it on 26 of 29 — "X is true, however Y" comes back with A = X. The
framework's own 2026-10-26 gate could not see this because its secondary read
scored A+ against the clause and never A. So the judge now reads the POLE too:
`antithesis_already_granted` — do the holder's words name AND grant the
position A states (set down as true or legitimate before arguing past it; a
view named only to reject it is not granted) — and `fit` is the weakest of
the three reads. Still a selection term inside the pass rule, with the same
limit as before, now measured rather than suspected: the N draws of one card
are one tension reworded, and in the app's run A was conceded in BOTH reps or
NEITHER on 12 of 13 petitions with two reps — so where every draw bears the
granted view this read ranks nothing — and neither of the two levers tried
the same day moved it: one re-ask naming the granted view (off, its gate
missed) or the writer on Opus 5.5 (the same four petitions, 4 of 22 against
5). The record: the dev note section named below. What it does do is make the verdict TRUE: a card whose A is the
person's own concession is no longer scored as fitting. Measured offline
before it shipped, nothing drawn (`tests/e2e/rescore_conceded_a.py`): the A
read agrees with the app's reviewed judge on 21/29 rows (the A+ read 27/29),
flags the same petitions on this repo's own `attempts=1` draws (6 of 22, in
both prompt arms — the mirror rule in `_OPPOSING_POSITION_ASK` is inert at the
pole as it was at A+), and flips 14 of the 29 app rows from fitting to not.
Figures and the hand read of the disagreements:
`docs/dev-notes/antithesis-selection.md`, "A is the view the author granted".

This judge does not think, so it parses on either transport. The view-turn
arm of the same gate did not, until the Mirascope floor moved to 2.8.2 on
2026-10-26: the view turn is the one structured call that THINKS, the
framework's thinking-shape translation is applied in
`utils/bedrock_provider.py::_encode` alone, and Mirascope 2.5 sent every
level as the legacy token budget — 40/40 draws came back 400
("thinking.type.enabled is not supported for this model"). 2.8.2 emits the
adaptive shape itself, and the rest of the compat layer then moved to a
provider-neutral seam (`bedrock_provider._AnthropicTransport`), so the two
transports send the same request. Figures taken BEFORE that, this judge's
included, came off whichever transport ran them: the stored draws it was
measured on are Bedrock's.
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
            "Is the thesis the claim its HOLDER would SIGN — the conclusion or "
            "demand the holder's words lead to? The holder is the person when "
            "they speak for themselves, or the party the words report it from. "
            "1.0: it is that claim. 0.0: it is a premise, a hedge or a "
            "concession on the way to it ('we have the right to ask' when they "
            "go on to demand; 'X matters, but' when they then argue against X)."
        ),
    )
    antithesis_already_granted: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Do the HOLDER's own words ALREADY name and GRANT the position A states — "
            "set it down as true or legitimate before arguing past it ('X is true, "
            "however Y'; 'whilst X may be needed, we think Y'; 'although intended to "
            "X')? 1.0: A is that granted view, X. 0.0: A is an opposition their words "
            "do not name, or name only to reject it without granting it."
        ),
    )
    a_plus_already_granted: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Do the HOLDER's own words ALREADY name and concede what A+ says? "
            "1.0: they said it themselves ('not only X but also Y' concedes X). "
            "0.0: it is a constructive side of the opposition they have not seen."
        ),
    )
    reasoning: str = Field(
        description=(
            "Three sentences: which claim they would sign, whether A is a view "
            "their words grant, and whether A+ is in their words."
        )
    )

    @property
    def fit(self) -> float:
        """The weakest of the three reads, as the control statements take the
        weaker statement: a draw on the right claim against a granted
        opposition fits no better than a draw on the wrong claim, whether the
        grant is read at the pole (A) or at its development (A+)."""
        return min(
            self.thesis_is_the_claim,
            1.0 - self.antithesis_already_granted,
            1.0 - self.a_plus_already_granted,
        )


class ThesisFitCheck:
    """Text-only, graph-free, no report: a judge the selector gathers."""

    async def score_texts(
        self,
        *,
        thesis: str,
        antithesis: str,
        a_plus: str,
        text: str,
        held_by: str = "",
    ) -> ThesisFitDto:
        """Both reads in one call. `text` is the words handed to the judge (the
        view turn's `judge_context`, the build's material) and is required:
        with nothing to read against, neither question can be answered, and
        the caller skips the judge instead of asking it blind. `held_by` is
        the party T is attributed to when it is not the person's own
        (`thesis_held_by` on the draw); empty = the person speaking."""
        holder = (held_by or "").strip()
        whose = (
            f"T is {holder}'s position, which the words REPORT: its holder is "
            f"{holder}, not the person who pasted the words. Judge both questions "
            f"by what {holder} says in them."
            if holder
            else "Its holder is the person speaking above."
        )
        prompt = f"""<context>
{text}
</context>

A dialectical tetrad was drawn from the words above. {whose} Read its thesis, its antithesis and the constructive side of the antithesis against the holder's words, and rate three things independently.

Thesis (T): "{thesis}"
Antithesis (A): "{antithesis}"
Constructive side of A (A+): "{a_plus}"

1. Is T the claim its holder would sign? When the holder's words hold several claims, the one they would sign is the conclusion or demand the rest leads to — not a premise, not a hedge on the way to it, and not a claim they concede in passing ("not only X but also Y" concedes X and argues for Y).

2. Do the holder's own words already name AND grant the position A states? Granting is setting a view down as true or legitimate before arguing past it: "X is true, however Y", "whilst X may be needed, we think Y", "although intended to X, this punishes Y" — the holder wrote X down to get past it, and A is X. A view the words name only to reject it is not granted; a fact or a sympathy that takes no side is not a position. An opposition they have granted themselves is seen, not missing; a tetrad on it shows them their own sentence as the other side.

3. Do the holder's own words already name AND concede what A+ says? The same reading at the constructive side: a tetrad on it shows them their own sentence as a blind spot."""
        return await ConversationFacilitator().submit(
            response_model=ThesisFitDto, user_content=prompt
        )
