"""TetradGrounding: attach the case particulars a tetrad was abstracted from.

Why this exists
===============
The tetrad's own text is universal by construction. `component_length` caps
poles and aspects near seven words, `commit()` dedups matching wording into one
shared node, and taxonomy anchoring pulls both toward `SYSTEMIC_TAXONOMY`
apexes. That abstraction is the whole point — it is what makes a tetrad
transferable across cases — but it throws the evidence away. "Solo leadership
enables faster decisive execution" no longer knows that this founder holds 55%,
gave feedback in March, and sat through three customer calls as a plus-one.

Measured cost of that loss (`tests/bench`, `claim2-weak-r5`): across six live
counsel sessions the graph carried **0 of 15** case particulars while a plain
prompted LLM keeping its own session notes carried **11 of 15**. At the
returning-session wobble the framework contradicted its own record — "This isn't
the accepted cost resurfacing" — because it held no fact to check the panic
against. The bare LLM, holding "cofounder isn't a rainmaker; customers won't
follow him out", asked whether the person had known all along. They had.

What this is NOT
================
**Not an Input.** Input is generative: material there feeds thesis extraction,
so conversational particulars parked in it would manufacture tensions nobody
raised and sit permanently "pending analysis". Grounding is read-only context
for the conversation, never fuel for the pipeline.

**Not agent memory.** Scope is material-only: facts about the SITUATION. Facts
about the PERSON (tone, register, what push-back they respect) and
forward-looking conversational strategy ("watch for whether they are
second-guessing") are the host application's business. Admitting them here
would make the dialectical graph a general-purpose notebook.

Where it attaches
=================
Grounding rides on `ExplainsRelationship.role == ROLE_GROUNDING`, so the
mechanism reaches every `AssessableEntity` for free. Which nodes are WRITTEN to
is an editorial decision: meaning-bearing nodes, not arrangements.

  * **Perspective** — the tetrad as a whole. Primary target: this is where
    abstraction bites hardest and where the measured loss was total.
  * **Statement** — optional, for evidence specific to ONE pole. Worth more
    than it looks: `commit()` dedup makes one Statement the T- of several
    perspectives, so pole-level grounding survives reuse across tetrads.
  * **Not** Cycle/Wheel/Synthesis — those are arrangements OF perspectives;
    their particulars are their members' particulars, and copying text into
    them would multiply it across every dump.
  * **Not** Decision — already carries `intent`, `stance` and a `Why:`
    rationale with real human attestation.
  * **Not** Transition/Transformation — they already own the
    `instruction`/`summary`/`haiku` free-text lane.

Accretion, not mutation
=======================
Each call appends a NEW Rationale rather than editing one field. A person
reveals more three turns later, and `Rationale` is content-addressable on
(text, target) so it cannot be edited anyway. Appending yields a chronology of
what was revealed when, which one flat field would flatten. `commit()` dedup
means re-grounding with identical text is idempotent and free.

Programmatic usage:
    concern = TetradGrounding()
    await concern.resolve(
        perspective=pp,
        context="He closed both major customers and is on all their calls...",
    )
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.relationships.explains_relationship import \
    ROLE_GROUNDING
from dialectical_framework.protocols.has_config import SettingsAware

logger = logging.getLogger(__name__)

#: Word ceiling for a grounding note. Deliberately a module constant, not a
#: setting: no deployment would ever tune it, and the number is a
#: legibility judgement, not a policy. Generous next to
#: `component_length` (~7) because the whole point is to hold what the
#: tetrad cannot — but bounded, because this text renders on EVERY turn of
#: the counsel dump and an unbounded note would crowd out the structure it
#: is meant to support.
MAX_GROUNDING_WORDS = 60

SYSTEM_PROMPT = f"""You extract the CONCRETE PARTICULARS from what a person has said about their situation.

A dialectical tetrad states a tension in universal terms — "Solo leadership enables faster decisive execution". That abstraction is useful but it forgets the case. Your job is to preserve exactly what the abstraction dropped, so that later the tension can be discussed against the person's own facts rather than in the abstract.

**Extract ONLY:**
- Specific facts: numbers, percentages, equity splits, dates, durations, money
- Named commitments and events: what was said to whom, when, what happened after
- Concrete instances the person cited as evidence
- Structural facts about the situation: who holds what, who talks to whom

**Do NOT include:**
- Restatements of the tension itself (that is already in the tetrad)
- Interpretation, diagnosis, advice, or judgement about the situation
- Facts about the PERSON's character, mood, tone, or communication style
- What they should do next, or what to watch for later
- Anything you inferred rather than something they stated

Write terse declarative fragments in the person's own terms — no more than {MAX_GROUNDING_WORDS} words total. If the material contains no concrete particulars, return an empty string rather than padding with generalities. Do not editorialise; a reader must be able to check every fragment against what was actually said."""


class GroundingDto(BaseModel):
    """Structured output for grounding extraction."""

    particulars: str = Field(
        description=(
            "Terse declarative fragments of concrete case facts, in the "
            "person's own terms. Empty string if the material contains none."
        )
    )


class TetradGrounding(ReasonableConcern[Optional[Rationale]], SettingsAware):
    """Extract case particulars from conversational context and attach them.

    Fail-soft by contract: grounding is an enrichment, never a gate. A failed
    extraction leaves the tetrad exactly as it was — callers must not treat a
    `None` return as an error worth surfacing.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        perspective: Perspective,
        context: str,
        target_statement: Optional[object] = None,
    ) -> Optional[Rationale]:
        """Extract particulars from `context` and attach them as grounding.

        Args:
            perspective: The committed tetrad being grounded.
            context: Conversational material the tension was drawn from.
            target_statement: Optional committed Statement to ground INSTEAD of
                the perspective, when the evidence belongs to one pole.

        Returns:
            The committed grounding Rationale, or None when there was nothing
            to ground (empty context, uncommitted target, no particulars found,
            or a soft failure).
        """
        material = (context or "").strip()
        if not material:
            self._report.ok = True
            self._report.summary = "No context supplied — nothing to ground"
            return None

        target = target_statement if target_statement is not None else perspective
        if not getattr(target, "is_committed", False):
            # An uncommitted target cannot be an explanation target. Not an
            # error: ExpandPolarity grounds after commit, so this only trips
            # if a caller inverts that order.
            self._report.ok = True
            self._report.summary = "Target not committed — grounding skipped"
            return None

        try:
            particulars = await self._extract(material)
        except Exception as e:  # noqa: BLE001
            logger.warning("Grounding extraction failed softly: %s", e)
            self._report.ok = True
            self._report.summary = f"Grounding extraction failed softly: {e}"
            return None

        if not particulars:
            self._report.ok = True
            self._report.summary = "No concrete particulars in the material"
            return None

        rationale = Rationale(text=particulars)
        rationale.set_explanation_target(target, role=ROLE_GROUNDING)
        rationale.commit()
        self._report.node_created(rationale)

        self._report.ok = True
        self._report.summary = (
            f"Grounded {type(target).__name__} {target.short_hash} "
            f"in {len(particulars.split())} words of case particulars"
        )
        self._report.artifacts["grounding"] = particulars
        return rationale

    async def _extract(self, material: str) -> str:
        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        result = await self._conversation.submit(
            response_model=GroundingDto,
            user_content=self._prompt(material),
        )
        particulars = (result.particulars or "").strip() if result else ""
        if not particulars:
            return ""

        # Trim rather than reject: a slightly long note is still useful, and
        # this text renders on every counsel turn.
        words = particulars.split()
        if len(words) > MAX_GROUNDING_WORDS:
            particulars = " ".join(words[:MAX_GROUNDING_WORDS])
        return particulars

    def _prompt(self, material: str) -> str:
        return f"""**What the person has said about their situation:**

{material}

Extract the concrete particulars, at most {MAX_GROUNDING_WORDS} words. Return an empty string if there are none."""
