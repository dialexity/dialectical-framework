"""Does the framework's product reach the reply? Free, over the saved archive.

    poetry run python tests/e2e/probe_readside_reach.py

Sixteen rounds asked "is A2 better?" This asks the prior question: **when A2
built a wheel, did any of it get INTO the answer the person read?** It is
answerable from saved records because `SessionRecord.carryover_in` stores the
rendered Current Understanding dump verbatim, so the dump and the replies written
with it in context sit side by side on disk.

The answer is no, and it is specific about which part fails.

WHAT REACHES THE REPLY, AND WHAT DOES NOT
=========================================
Overlap = share of a dump line's content words that appear anywhere in the
session's replies, taking the best-matching line of each kind. Not a semantic
measure — it cannot see paraphrase — so read it as a floor on the DIFFERENCE
between sections of the SAME dump, which is what makes it informative here:

    r16, 6 sessions with a dump    best S+/S- overlap   best Ac+ overlap   best Decision overlap
    rep1 wobble_a  (24 Ac+ lines)          0.17               0.38               0.67
    rep1 wobble_b  (12)                    0.14               0.12               0.59
    rep2 wobble_a  (30)                    0.17               0.33               0.80
    rep2 wobble_b  (30)                    0.38               0.30               0.69
    rep3 wobble_a  (24)                    0.29               0.22               0.50
    rep3 wobble_b  (42)                    0.50               0.56               0.83

Every session reaches into the SAME dump and pulls the **decision ledger** out of
it (0.50-0.83) while stepping over 12-42 transformations (0.12-0.56) and the
synthesis (0.14-0.50). r14 is the same shape. **Hashes cited across all 12
sessions with a dump: zero.**

So the read side is not broken in general — the memory section lands, reliably.
It is broken for exactly the sections that carry the framework's differentiator.
That is a rendering/prioritisation defect, and it is a different bug from
"dialectics do not help".

THE ORDERING BUG UNDERNEATH IT
==============================
Worse: for the first session of every cell, the content was **not in the model's
context at all** when the reply was written. Two facts in `src/`, both verified:

  * `Advisor.chat` (`advisor/advisor.py:204-207`) awaits `submit()` — the reply
    the person receives — and only THEN runs `_repair_unrecorded_decision`, which
    is where `_ensure_pathways_before_closing` weaves. Its own docstring says so:
    "their reply has already been delivered".
  * `{dialectical_context}` was rendered ONCE, at construction, and the deferred
    render was a no-op unless the Advisor was built scoped without a context. The
    bench builds it UNSCOPED (`driver.py`), so session 1 carried
    `EMPTY_UNDERSTANDING` for all 8 turns.

BOTH HALVES ARE NOW FIXED IN `src/`, which is why this probe reads the archive in
the past tense. The closing no longer builds (it cost a measured 387.7s on the
person's wait), and `Advisor._refresh_context` re-reads the graph into the prompt
EVERY turn in both modes, rewriting only when the dump changed. The numbers below
are therefore a record of what the archived runs did, not a description of current
behaviour — and they are the baseline the next round measures against. The guard
against regression is `test_advisor_context_render.py`.

Measured consequence in r16: every `decide` session built 12-42 transformations
with **no dump in context**, and the structure only became visible in the
following session:

    rep1 decide   no dump   built 24 transformations
    rep1 wobble_a DUMP      built 30
    rep3 decide   no dump   built 42
    rep3 wobble_b DUMP      built 42

The framework builds its differentiator AFTER the turn that needed it, into a
buffer the current session cannot read. `sync` is the only in-session escape and
it fired in 5 of 36 sessions.

WHAT THIS DOES NOT SHOW
=======================
Two corrections to the tempting over-reading, both measured here so nobody has to
re-derive them:

  * **Depth does not predict the score — it is a NULL, not an inversion.**
    corr(transformations, judged delta) = **-0.107** over 36 cells (woven -0.107,
    perspectives -0.009). It is tempting to say "the deepest cell scored worst"
    because r16 rep3/wobble_b has 42 transformations and -1.00; r14 rep1/wobble_b
    has 36 and **+0.33**. Anecdote in both directions, correlation in neither.
    The honest statement is that **building more structure buys nothing**, which
    is exactly what a read side that ignores it predicts.
  * The machinery DOES run now. 6/6 r16 cells woven, 12-42 transformations,
    syntheses generated. The r7 "A2 never ran the framework" finding is retired
    for the current build — and only 2 of 6 cells got there by the model electing
    `explore`; the rest came through the closing seam.

The depth ceiling is real but separate: no nexus in r14-r16 exceeded **2
perspectives** (`advisor_max_perspectives_per_exploration = 2`) so every judged
cell is a layer 1-2 wheel. The archive has never judged the combinatorics the
framework advertises.

A measurement script: prints and exits, reads only saved records, costs nothing.
Pinned by `TestTheProductDoesNotReachTheReply`.
"""

from __future__ import annotations

import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e.models import Comparison, RunRecord  # noqa: E402
from e2e.report import load_records  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

# Rounds whose A2 arm is the current architecture. Earlier rounds are excluded on
# purpose: before `cb2b4a0` the graph summary was read off `tool_calls`, so
# "built N transformations" is not comparable with these.
ROUNDS = (
    "claim2-weak-r14-accretion",
    "claim2-weak-r15-voice",
    "claim2-weak-r16-floor",
)

_STOPWORDS = frozenset(
    """the a an and or of to in is are was for with that this it as on at by be
    been from not you your we our their his its if then than but so what which
    who how have has had will would could should do does did they them there
    here about into more most some any all can may might must one two""".split()
)
_HASH_CITATION = re.compile(r"\[\[[0-9a-f]{6,}")
_SUMMARY_FIELD = re.compile(r"(\w+)=(\d+)")


def _content_words(text: str | None) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z]{4,}", (text or "").lower())
        if word not in _STOPWORDS
    }


def _best_overlap(lines: list[str], reply_words: set[str]) -> float:
    """Highest share of any line's content words that appear in the replies.

    BEST, not mean: the question is whether ANY of 42 pathways landed, and a mean
    over 42 lines would be low even if the reply quoted one of them exactly.
    Lines under 3 content words are skipped — "S+: trust" would score 1.0 off a
    single common word.
    """
    best = 0.0
    for line in lines:
        line_words = _content_words(line)
        if len(line_words) >= 3:
            best = max(best, len(line_words & reply_words) / len(line_words))
    return best


def graph_summary_fields(summary: str | None) -> dict[str, int]:
    """`'perspectives=5 woven=4 transformations=24'` -> dict of ints."""
    return {key: int(value) for key, value in _SUMMARY_FIELD.findall(summary or "")}


def reach_rows(rounds: tuple[str, ...] = ROUNDS) -> list[dict]:
    """One row per A2 session that had a dump in context."""
    rows: list[dict] = []
    for stem in rounds:
        for raw in load_records(RESULTS / f"{stem}-runs.json").get("runs") or []:
            run = RunRecord.model_validate(raw)
            if run.arm.value != "A2" or run.tier != "weak" or run.error:
                continue
            for session in run.sessions:
                if not session.carryover_in:
                    continue
                dump = session.carryover_in
                lines = dump.splitlines()
                synthesis = [ln.strip() for ln in lines if re.search(r"\bS[+-]", ln)]
                pathways = [ln.strip() for ln in lines if "Ac+" in ln]
                decisions = [
                    ln.strip() for ln in lines if "ecision" in ln or "Stance" in ln
                ]
                reply = " ".join(turn.assistant or "" for turn in session.turns)
                reply_words = _content_words(reply)
                rows.append(
                    {
                        "round": stem,
                        "replicate": run.replicate,
                        "label": session.label,
                        "dump_chars": len(dump),
                        "pathway_lines": len(pathways),
                        "synthesis": _best_overlap(synthesis, reply_words),
                        "pathways": _best_overlap(pathways, reply_words),
                        "decisions": _best_overlap(decisions, reply_words),
                        "hashes": len(_HASH_CITATION.findall(reply)),
                    }
                )
    return rows


def build_without_context(rounds: tuple[str, ...] = ROUNDS) -> list[dict]:
    """One row per A2 session, with whether a dump was in context while building.

    The ordering bug's fingerprint: sessions that built the most structure while
    holding EMPTY_UNDERSTANDING in the system prompt for every turn.
    """
    rows: list[dict] = []
    for stem in rounds:
        for raw in load_records(RESULTS / f"{stem}-runs.json").get("runs") or []:
            run = RunRecord.model_validate(raw)
            if run.arm.value != "A2" or run.tier != "weak" or run.error:
                continue
            for session in run.sessions:
                fields = graph_summary_fields(session.graph_summary)
                rows.append(
                    {
                        "round": stem,
                        "replicate": run.replicate,
                        "label": session.label,
                        "had_dump": bool(session.carryover_in),
                        "transformations": fields.get("transformations", 0),
                        "woven": fields.get("woven", 0),
                        "perspectives": fields.get("perspectives", 0),
                    }
                )
    return rows


def depth_against_score(rounds: tuple[str, ...] = ROUNDS) -> tuple[dict, int]:
    """(correlation per depth measure, n) between structure built and judged delta.

    The check that kills the flattering story AND the damning one: if depth
    predicted the score either way there would be something to act on. It does
    not, which is what "the reply ignores the structure" predicts.
    """
    paired: list[tuple[dict[str, int], float]] = []
    for stem in rounds:
        depth: dict[tuple[int, str], dict[str, int]] = {}
        for raw in load_records(RESULTS / f"{stem}-runs.json").get("runs") or []:
            run = RunRecord.model_validate(raw)
            if run.arm.value != "A2" or run.tier != "weak" or run.error:
                continue
            for session in run.sessions:
                depth[(run.replicate, session.label)] = graph_summary_fields(
                    session.graph_summary
                )
        for raw in load_records(RESULTS / f"{stem}.json").get("comparisons") or []:
            comparison = Comparison.model_validate(raw)
            if comparison.error or comparison.tier != "weak":
                continue
            arms = (comparison.arm_a.value, comparison.arm_b.value)
            if "A2" not in arms:
                continue
            mine_is_a = comparison.arm_a.value == "A2"
            gaps = [
                (a - b) if mine_is_a else (b - a)
                for a, b in comparison.scores.values()
            ]
            key = (comparison.replicate, comparison.session_label)
            if gaps and key in depth:
                paired.append((depth[key], st.mean(gaps)))

    deltas = [value for _fields, value in paired]
    correlations: dict[str, float] = {}
    for measure in ("transformations", "woven", "perspectives"):
        values = [fields.get(measure, 0) for fields, _value in paired]
        correlations[measure] = _correlation(values, deltas)
    return correlations, len(paired)


def _correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    mean_x, mean_y = st.mean(xs), st.mean(ys)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    spread = math_sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    return covariance / spread if spread else float("nan")


def math_sqrt(value: float) -> float:
    import math

    return math.sqrt(value)


def main() -> int:
    rows = reach_rows()
    if not rows:
        print("no saved A2 sessions with a rendered dump in", RESULTS)
        return 1

    print("WHICH SECTION OF THE DUMP REACHES THE REPLY (best line overlap)")
    print(
        f"  {'round':12}{'rep':>4}{'session':>10}{'dump':>8}{'Ac+':>6}"
        f"{'synth':>8}{'pathwy':>8}{'decisn':>8}{'hash':>6}"
    )
    for row in rows:
        print(
            f"  {row['round'][13:25]:12}{row['replicate']:>4}{row['label']:>10}"
            f"{row['dump_chars']:>8}{row['pathway_lines']:>6}"
            f"{row['synthesis']:>8.2f}{row['pathways']:>8.2f}"
            f"{row['decisions']:>8.2f}{row['hashes']:>6}"
        )
    print(
        f"  {'mean':12}{'':>4}{'':>10}{'':>8}{'':>6}"
        f"{st.mean([r['synthesis'] for r in rows]):>8.2f}"
        f"{st.mean([r['pathways'] for r in rows]):>8.2f}"
        f"{st.mean([r['decisions'] for r in rows]):>8.2f}"
        f"{sum(r['hashes'] for r in rows):>6}"
    )
    print(
        "  Same dump, every session: the decision ledger lands and the pathways\n"
        "  and synthesis do not. A read-side defect, not a theory defect."
    )

    print()
    print("BUILT WITH NO DUMP IN CONTEXT (the ordering bug's fingerprint)")
    blind = [r for r in build_without_context() if not r["had_dump"]]
    built_blind = [r for r in blind if r["transformations"]]
    print(
        f"  {len(built_blind)} of {len(blind)} first sessions built structure while the\n"
        f"  system prompt held EMPTY_UNDERSTANDING for all 8 turns; "
        f"{sum(r['transformations'] for r in built_blind)} transformations total."
    )

    print()
    correlations, n = depth_against_score()
    print(f"DOES DEPTH PREDICT THE SCORE?  n={n} cells")
    for measure, value in correlations.items():
        print(f"  corr({measure:15}, judged delta) = {value:+.3f}")
    print(
        "  A null. Not an inversion — r16's 42-transformation cell scored -1.00 and\n"
        "  r14's 36-transformation cell scored +0.33. Building more structure buys\n"
        "  nothing, which is precisely what an unread structure predicts."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
