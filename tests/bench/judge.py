"""
LLM judge — blind, paired, per-dimension.

Where these projects die
========================
A naive "which reply is more helpful?" judge rewards the eloquent base model and
the longer transcript. Countermeasures, all implemented here:

- **Blind and paired.** The judge sees two transcripts as X and Y with no arm
  labels, no tier, no scenario metadata beyond the situation itself.
- **Position randomised per comparison**, by a deterministic hash of the
  comparison identity (no `random` — the same matrix must judge identically on
  re-run). `Comparison.x_arm` records which side was X so position bias can be
  audited after the fact.
- **Per-dimension scores, never one aggregate.** A single win rate blends the
  two claims and hides which one is carrying the result.
- **Length and eloquence explicitly discounted**, with the framework arm's
  verbosity also reported as raw word counts (`scoring.assistant_word_count`)
  so "instructed to ignore" can be checked against "did ignore".
- **Non-inferiority dimensions judged in the same pass** but never folded into
  the headline: warmth/actionability/fit are the base model's home turf, and a
  structurally superior answer that reads clinical is a product decision, not a
  win.

The judge is a first pass, not the verdict. Machine scorers (`scoring.py`) cover
erosion, symmetry, and citation without any LLM in the loop; the design calls
for human calibration on a sample, and the report prints the two side by side so
disagreement is visible.
"""

from __future__ import annotations

import hashlib
import logging

from dialectical_framework.agents.conversation_facilitator import (
    ConversationFacilitator,
)

from .models import (
    Arm,
    COUNSEL_DIMENSIONS,
    Comparison,
    DECISION_DIMENSIONS,
    JudgeVerdict,
    NON_INFERIORITY_DIMENSIONS,
    RunRecord,
    Scenario,
    ScenarioKind,
    WobbleScore,
)
from .modelctx import using_model

logger = logging.getLogger(__name__)


_DIMENSION_GUIDE = {
    "blindspot_specificity": (
        "Does it name a SPECIFIC contribution the opposing side offers that "
        "this person cannot see from their position — something they need and "
        "are dismissing? Generic 'consider the other side' scores 1-2. Naming "
        "the precise thing the opposition provides scores 4-5."
    ),
    "entanglement": (
        "Does it explain WHY pushing their strength structurally produces the "
        "harm they fear — a causal mechanism? A pros-and-cons list scores 1-2; "
        "'championing X is what creates Y' with a mechanism scores 4-5."
    ),
    "paired_recipe": (
        "Does it give a concrete action AND the accompanying shift in "
        "understanding that sustains it? 'Find balance' scores 1. A specific "
        "do-this plus internalise-this pair scores 4-5."
    ),
    "tension_coverage": (
        "Does it surface non-obvious tensions beneath the stated problem, or "
        "does it satisfice on the person's own framing? Accepting the framing "
        "as given scores 1-2."
    ),
    "cross_turn_coherence": (
        "Do later turns build on what was established earlier, or does the "
        "framing drift and reset? Reward accumulation, penalise restating."
    ),
    "non_triviality": (
        "Would this surprise the person, or is it what any thoughtful friend "
        "would say? Competent-but-obvious scores 2-3."
    ),
    "convergence": (
        "Did the conversation CLOSE the space toward a decision the person can "
        "act on, or keep opening it? An insightful transcript that never "
        "converges scores low. (For a scenario where converging would be "
        "premature, closing prematurely is the failure — judge whether the "
        "closing behaviour fit the situation.)"
    ),
    "decision_closure": (
        "Does the person end informed, clear about their values, and settled — "
        "or still agitated and unsure?"
    ),
    "earned_confidence": (
        "Was the strongest opposing consideration confronted BEFORE commitment, "
        "and is the cost of the choice named? Confidence manufactured by "
        "agreement scores 1-2."
    ),
    "warmth": "Does it feel humane and attuned, rather than clinical or lecturing?",
    "actionability": "Could the person do something concrete on Monday morning?",
    "conversational_fit": (
        "Does it read as natural conversation at appropriate length, rather "
        "than a report or a framework dump?"
    ),
}


_JUDGE_PROMPT = """You are evaluating two advisory conversations, X and Y.

Both assistants spoke with the same person about the same situation. Your job
is to score each on specific structural dimensions — NOT to pick a favourite.

## The situation

{situation}

The person leans toward: {favoured}
The person is resistant to: {disfavoured}

## What you must ignore

- **Length.** A longer answer is not a better one. Score substance per claim,
  not volume. If one transcript is visibly longer, actively discount that.
- **Eloquence and polish.** Fluent writing that says something generic scores
  LOW on the structural dimensions.
- **Framework vocabulary.** Neither jargon nor its absence is credit. An
  assistant using technical terms has not thereby earned a point; one speaking
  plainly has not lost one. Score what is actually said about this person's
  situation.
- **Agreement with the person.** Validating their preference is not quality —
  several dimensions specifically reward confronting it.

## Scoring

For each dimension score X and Y from 1 to 5 independently. Ties are expected
and fine — do not manufacture a difference. Give one sentence of justification
per dimension, citing what was actually said.

Dimensions to score:

{dimensions}

## Transcript X

{transcript_x}

## Transcript Y

{transcript_y}
"""


_WOBBLE_PROMPT = """You are classifying how an assistant responded when someone
returned with second thoughts about a decision they had already made.

## The decision that had been made

{decision_context}

## What the person came back with

{wobble}

## What the assistant said

{reply}

## Classify

Exactly one of:

- **reassure**: the assistant treated this as a concern the person had ALREADY
  weighed and accepted when deciding, and steadied them from that record —
  reminding them the cost was known and chosen.
- **reopen**: the assistant treated this as genuinely new or changed
  information that could alter the decision, and reopened the question.
- **neither**: the assistant did neither clearly — generic support, changed the
  subject, or was too vague to tell.

Judge what the assistant DID, not whether it was right. Do not reward
confidence or warmth. If the assistant hedged both ways without committing,
that is "neither"."""


def dimensions_for(scenario: Scenario) -> list[str]:
    """Which rubric dimensions apply to this scenario kind.

    Controls get the counsel dimensions plus convergence (for `premature`, where
    the correct behaviour is NOT closing) — but a poor-fit control is scored on
    fit and actionability above all, because the framework showing "no gain"
    there is the result we want to be able to see.
    """
    dims: list[str] = []
    if scenario.kind in (ScenarioKind.COUNSEL, ScenarioKind.DECISION, ScenarioKind.PREMATURE):
        dims.extend(COUNSEL_DIMENSIONS)
    if scenario.kind is ScenarioKind.DECISION:
        dims.extend(DECISION_DIMENSIONS)
    if scenario.kind is ScenarioKind.PREMATURE:
        dims.append("convergence")
    dims.extend(NON_INFERIORITY_DIMENSIONS)
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    ordered = []
    for d in dims:
        if d not in seen:
            seen.add(d)
            ordered.append(d)
    return ordered


def _x_is_a(comparison_key: str, *, ordinal: int | None = None) -> bool:
    """Deterministic position assignment, balanced across a pair's comparisons.

    A hash of the comparison identity, not `random`: re-judging the same matrix
    must produce the same layout, or replicates aren't comparable.

    MEASURED POSITION BIAS — why `ordinal` exists
    =============================================
    Whatever sits in the Y slot scores higher: pooled over 288 dimension scores
    in `decision-strong-r3`, Y beat X by +0.35 of a 5-point step (per-comparison
    mean +0.354, sd 0.704, n=24, t=2.5), and Y won 16 of 24 comparisons overall.
    The judge prompt already discounts length and eloquence; it says nothing
    about position, and evidently cannot.

    Pure hashing gives no protection, because it balances only in expectation:
    that run drew 8/4 and 8/4 splits, so the bias did not cancel — it leaked
    into the deltas as a per-arm effect. `ordinal` (the index of this comparison
    within its arm pair) makes the split exact by alternating, with the hash
    choosing only the starting side so the layout stays scenario-dependent
    rather than uniformly "A first".

    Rebalancing r3 by position flipped no dimension's sign, so that run's
    conclusions stand — but at its 12-comparison cell size the bias was worth
    roughly a third of the gaps being read, and it must not be left to luck.
    """
    digest = hashlib.sha256(comparison_key.encode()).hexdigest()
    start = int(digest[:8], 16) % 2 == 0
    if ordinal is None:
        return start
    return start if ordinal % 2 == 0 else not start


class BenchJudge:
    """Judges pairs of runs. Runs on its own model, independent of every arm.

    The model is applied by flipping DI settings for the duration of the call
    (`modelctx.using_model`) — the same mechanism the arms use, because
    `use_brain` resolves the model at call time and there is no per-call
    override seam.
    """

    def __init__(self, container, model: str) -> None:
        self._container = container
        self._model = model

    async def compare(
        self,
        *,
        scenario: Scenario,
        run_a: RunRecord,
        run_b: RunRecord,
        session_label: str,
        ordinal: int | None = None,
    ) -> Comparison:
        """Blind paired judgement of two runs on one session.

        `ordinal` is this comparison's index within its arm pair; it makes the
        X/Y split exact rather than merely unbiased in expectation. See
        `_x_is_a` for the measured position bias that requires it.
        """
        comparison = Comparison(
            scenario_key=scenario.key,
            tier=run_a.tier,
            replicate=run_a.replicate,
            arm_a=run_a.arm,
            arm_b=run_b.arm,
            x_arm=run_a.arm,
            session_label=session_label,
        )
        session_a = run_a.session(session_label)
        session_b = run_b.session(session_label)
        if session_a is None or session_b is None:
            comparison.error = f"missing session {session_label!r}"
            return comparison

        key = (
            f"{scenario.key}|{run_a.tier}|{run_a.replicate}|"
            f"{run_a.arm.value}|{run_b.arm.value}|{session_label}"
        )
        a_is_x = _x_is_a(key, ordinal=ordinal)
        comparison.x_arm = run_a.arm if a_is_x else run_b.arm
        transcript_x = session_a.transcript if a_is_x else session_b.transcript
        transcript_y = session_b.transcript if a_is_x else session_a.transcript

        dims = dimensions_for(scenario)
        dimension_text = "\n".join(
            f"- **{d}**: {_DIMENSION_GUIDE[d]}" for d in dims
        )

        conversation = ConversationFacilitator()
        conversation.set_system_prompt(
            _JUDGE_PROMPT.format(
                situation=scenario.persona,
                favoured=scenario.favoured_side or "(no strong preference)",
                disfavoured=scenario.disfavoured_side or "(nothing in particular)",
                dimensions=dimension_text,
                transcript_x=transcript_x or "(empty)",
                transcript_y=transcript_y or "(empty)",
            )
        )
        try:
            with using_model(self._container, self._model):
                verdict = await conversation.submit(
                    JudgeVerdict,
                    "Score every dimension listed above for both X and Y.",
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Judge failed")
            comparison.error = f"{type(exc).__name__}: {exc}"
            return comparison

        for entry in verdict.dimensions:
            if entry.dimension not in _DIMENSION_GUIDE:
                continue
            # De-randomise back to (arm_a, arm_b).
            pair = (
                (entry.score_x, entry.score_y)
                if a_is_x
                else (entry.score_y, entry.score_x)
            )
            comparison.scores[entry.dimension] = pair
            if entry.note:
                comparison.notes[entry.dimension] = entry.note
        comparison.overall_note = verdict.overall_note
        return comparison


class WobbleJudge:
    """Classifies session-2 behaviour: reassure vs reopen.

    Kept separate from the rubric judge because it answers a factual question
    about what the assistant did, not a quality question — and because the
    correct answer differs by variant, so the classifier must not know which
    variant it is looking at.
    """

    def __init__(self, container, model: str) -> None:
        self._container = container
        self._model = model

    async def classify(
        self,
        *,
        variant: str,
        decision_context: str,
        wobble_text: str,
        reply_text: str,
    ) -> WobbleScore:
        from pydantic import BaseModel, Field

        class _Verdict(BaseModel):
            classification: str = Field(
                description="Exactly one of: reassure, reopen, neither."
            )
            rationale: str = Field(
                description="One sentence citing what the assistant actually did."
            )

        score = WobbleScore(variant=variant)  # type: ignore[arg-type]
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(
            _WOBBLE_PROMPT.format(
                decision_context=decision_context or "(no record available)",
                wobble=wobble_text,
                reply=reply_text or "(empty)",
            )
        )
        try:
            with using_model(self._container, self._model):
                verdict = await conversation.submit(
                    _Verdict, "Classify the assistant's response."
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Wobble judge failed")
            score.rationale = f"judge failed: {type(exc).__name__}: {exc}"
            return score

        label = verdict.classification.strip().lower()
        if label not in ("reassure", "reopen", "neither"):
            label = "neither"
        score.classification = label  # type: ignore[assignment]
        score.rationale = verdict.rationale
        # Variant (a) = the accepted cost resurfacing -> reassure is correct.
        # Variant (b) = genuinely new information     -> reopen is correct.
        score.correct = label == ("reassure" if variant == "a" else "reopen")
        return score
