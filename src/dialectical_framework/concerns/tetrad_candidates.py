"""
Choose among several sketched tetrads by the framework's own coherence check.

Why this exists. About 40% of one-shot tetrads fail `ControlStatementsCheck`
(both control statements ≥ 0.7). Measured on the existing draws (2026-10-04,
`docs/dev-notes/antithesis-selection.md`, "Best-of-N"): the judge is stable
(92% agreement on re-judging the same text), a third to half of the failure
variance sits with the PAIR and the rest with the DRAW, and keeping any passing
draw of two raised the one-shot's pass rate from 52% to 72%, of three to 80%.
So the agent checks its own work before anyone sees it: N sketches in
parallel, the two control statements judged for each, the best kept. The
runners-up are returned, not thrown away — a person's "another" can be one of
them without a new call.

What this must NOT become: a loop that optimises against the judge. The judge
never sees the thesis or antithesis — it scores the four aspects' coherence
and passes a MIRROR antithesis more readily than a genuine position — so a
generation steered by its verdict converges on coherent mirrors (the strawman
shape of 2026-09-30). Selection among independent draws of a prompt that
already asks for a position is bounded by those draws; regeneration from the
verdict is not, and is not done here. Attempts are capped, and the antithesis
kind is measured beside the pass rate whenever this is measured.

Text-level and graph-free: a sketch is a dict until it is persisted, so every
writer selects here — the one-shot `TetradSketch` (the view turn, the thesis-only
`anchor`, `SketchTetrad`) and the staged `AspectGeneration._generate_tetrad`
(documents through `ingest`, the Analyst's pipeline, the two-pole `anchor`/`note`).
A candidate is anything with `t_plus`/`t_minus`/`a_plus`/`a_minus` attributes
holding a text or an object with `.statement` (`TetradDto`'s `AspectDto`).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from dialectical_framework.concerns.control_statements_check import \
    ControlStatementsCheck
from dialectical_framework.graph.nodes.estimation import \
    CONCEPTUAL_COHERENCE_THRESHOLD

logger = logging.getLogger(__name__)

#: Draws per tetrad, per WRITER — two constants because the two writers were
#: measured apart (docs/dev-notes/antithesis-selection.md, "Best-of-N",
#: 2026-10-04). The one-shot writer (`TetradSketch`: the thesis-only `anchor`,
#: `SketchTetrad`, the Consultant's view turn) draws THREE: on the build every
#: pre-registered condition held (CC 30/40 from 20/40, paired 13 up / 3 down,
#: positions 36/40, +6–10 s), on the view turn the primary bar held resolved
#: (36/40 from 25/40, 12 up / 0 down) with two side conditions one and two
#: counts short at n = 40. The staged writer (`AspectGeneration` for documents,
#: the pipeline and the two-pole anchor) also draws THREE since the same-day
#: replication (four runs, public + authored texts, 90 tetrads): CC 26/46 (57%)
#: against the single draw's 17/44 (39%), positions 83% against 82%, restated
#: 2/92 against 4/88, compromise pluses 12 against 22, 1.24x the seconds and
#: 1.5x the calls per document. Caveat carried, not hidden: the public set moved
#: +40 points and the authored set −11, and the single draw itself ranged 20–63%
#: across runs — the pooled difference clears the pre-registered bar and is not
#: resolved. Capped: a fourth draw buys ~3 points for a third more cost, and the
#: pairs that fail every draw need a different tension.
DEFAULT_SKETCH_ATTEMPTS = 3
DEFAULT_ASPECT_ATTEMPTS = 3
MAX_SKETCH_ATTEMPTS = 3


def clamp_attempts(attempts: Optional[int], default: Optional[int] = None) -> int:
    """None → the writer's default (`DEFAULT_SKETCH_ATTEMPTS` unless given);
    anything else clamped to 1..`MAX_SKETCH_ATTEMPTS`."""
    if attempts is None:
        attempts = DEFAULT_SKETCH_ATTEMPTS if default is None else default
    return max(1, min(int(attempts), MAX_SKETCH_ATTEMPTS))


@dataclass(frozen=True)
class SketchVerdict:
    """The two control statements' coherence scores for one sketch."""

    t_plus_without_a_plus: float
    a_plus_without_t_plus: float
    reasoning: str = ""

    @property
    def floor(self) -> float:
        """The weaker statement — what the pass/fail rule reads."""
        return min(self.t_plus_without_a_plus, self.a_plus_without_t_plus)

    @property
    def passes(self) -> bool:
        return self.floor >= CONCEPTUAL_COHERENCE_THRESHOLD


def aspect_text(value: Any) -> str:
    """The text of an aspect field: a plain string, or an `AspectDto`'s `.statement`."""
    if isinstance(value, str):
        return value
    return str(getattr(value, "statement", "") or "")


def is_complete(candidate: Any) -> bool:
    """Four non-blank aspects — the least a candidate needs to be judged."""
    return all(
        aspect_text(getattr(candidate, name, "")).strip()
        for name in ("t_plus", "t_minus", "a_plus", "a_minus")
    )


async def judge_sketches(
    candidates: Sequence[Any], context: str = ""
) -> list[Optional[SketchVerdict]]:
    """The validator's two control statements for every candidate, each draft
    judged on its own, each statement in its own call (gathered).

    Statement texts are built by the same builder `ControlStatementsCheck.resolve`
    uses, and the prompt is the one `resolve` asks, so a verdict here and one
    taken after persistence are the same question asked of the same words. The
    judge sees only the four aspects of each draft, never the thesis or the
    antithesis. Fail-soft per candidate: a judging that fails is `None` for
    that draft alone, which sorts last.

    Deliberately NOT cheaper, by measurement (2026-10-06,
    `tests/e2e/probe_joint_judge_stability.py`, 40 stored triples). Judging is
    the costliest part of a best-of-3 card (6 of its 11 calls, about a third of
    its cost), and two cheaper shapes were tried and rejected:
    - one call for the whole field: pass/fail agreement with the stored verdict
      70% against this judge's own 92% on the same drafts, the same winner
      across a reversed order in 7/40, the first-listed draft winning 29/40;
      it picked by position and ties;
    - one call per draft with both statements in it (the same lean prompt):
      73% against 90%, the same winner as this judge in 23/40 — stable with
      itself, but measuring something else.
    A cheaper judge has to be measured against this one on that probe first.
    """

    async def one(tension: Any) -> Optional[SketchVerdict]:
        # Reading the verdict is inside the `try` too: a malformed response
        # is a failed judging (sorts last), never a failed selection.
        try:
            first, second = await ControlStatementsCheck().score_texts(
                t_plus=aspect_text(tension.t_plus),
                t_minus=aspect_text(tension.t_minus),
                a_plus=aspect_text(tension.a_plus),
                a_minus=aspect_text(tension.a_minus),
                text=context,
            )
            return SketchVerdict(
                t_plus_without_a_plus=first.coherence_score,
                a_plus_without_t_plus=second.coherence_score,
                reasoning=f"{first.reasoning} / {second.reasoning}".strip(" /"),
            )
        except Exception as exc:  # noqa: BLE001 — degrade to "unjudged"
            logger.warning("Judging a sketch failed; it sorts last: %s", exc)
            return None

    return list(await asyncio.gather(*(one(c) for c in candidates)))


async def select_sketch(
    candidates: Sequence[Any], context: str = ""
) -> tuple[int, list[Optional[SketchVerdict]]]:
    """Judge every candidate (gathered) and return the index of the best plus
    all verdicts (None where judging failed).

    Ranking: the weaker control statement first (the pass rule), then the
    mean, then the earlier draw — a deterministic tie-break, not a preference.
    A candidate whose judging failed sorts last; if every judging failed the
    first draw is kept, which is exactly what `attempts=1` would have done.

    ONE candidate is never judged: there is nothing to select among, so
    `attempts=1` costs no extra call.
    """
    if len(candidates) == 1:
        return 0, [None]

    verdicts = await judge_sketches(candidates, context)
    return ranking(verdicts)[0], verdicts


def ranking(verdicts: Sequence[Optional[SketchVerdict]]) -> list[int]:
    """Candidate indices best first, by `select_sketch`'s rule: the weaker
    control statement, then the mean, then the earlier draw; unjudged last.
    `[0]` is the winner; the rest are the runners-up in order."""

    def key(index: int) -> tuple[int, float, float, int]:
        verdict = verdicts[index]
        if verdict is None:
            return (0, 0.0, 0.0, -index)
        mean = (verdict.t_plus_without_a_plus + verdict.a_plus_without_t_plus) / 2
        return (1, verdict.floor, mean, -index)

    return sorted(range(len(verdicts)), key=key, reverse=True)
