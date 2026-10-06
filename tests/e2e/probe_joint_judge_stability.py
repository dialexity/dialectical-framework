"""Is a cheaper coherence judge as trustworthy as the per-statement one?

On 2026-10-06 best-of-N judging went, for one day, from a call per control
statement per draft (6 calls for 3 drafts) to one call for the whole field, for
cost, unmeasured. This measured it, and the per-draft fallback, on drafts
already stored, so nothing is generated: every utterance with three or more
stored drafts that carry the per-statement judge's `cc` pair gives one triple
(the first three, in a fixed order). Both were REJECTED and the per-statement
judge restored (`tetrad_candidates.judge_sketches`); the candidate judge lives
below in this file only, so the measurement can be re-run.

Result (`joint_judge_stability-20261006-122506.json`,
`per_draft_judge-20261006-122730.json`, 40 triples / 120 drafts):
- joint: pass/fail agreement with the stored verdict 70% against the old
  judge's own re-run 92%; mean floor shift 0.113 against 0.025; the same winner
  across a reversed order in 7/40; the first-listed draft won 29/40 forward and
  21/40 reversed (old judge 11/40); 18/40 winners decided by a tie.
- per draft (same lean prompt, one tetrad a call): 73% against 90%; floor
  shift 0.101 against 0.024; the same winner as the old judge in 23/40; stable
  with itself (96%) but measuring something else.

Per triple:
- the OLD judge re-run once per draft (`score_texts`, two calls each), as the
  baseline: the per-statement judge's own repeatability on THESE drafts, so the
  joint judge is not compared against a 92% measured on a different set;
- the JOINT judge three times: order 1-2-3 (A), 1-2-3 again (B, self-stability),
  3-2-1 (C, position).

Reads, each against the old judge's figure on the same items:
- pass/fail agreement with the stored verdict (old re-run vs joint A);
- self-agreement (joint A vs B) on pass/fail and on the winner;
- position: does the winner survive the reversed order (A vs C), and how often
  the winner sits in the FIRST slot (1/3 by chance);
- tie-breaks: `ranking()` resolves ties toward the earlier draft, so a coarse
  judge that ties more often would look position-biased through the tie-break
  alone. Every winner decided by a tie-break is counted.

The decision rule carried from the dev note: joint stability below ~85% means
falling back to one call per draft (both statements in one DTO). Per-item
verdicts are persisted.

    poetry run pytest tests/e2e/probe_joint_judge_stability.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import glob
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.control_statements_check import (
    _CC_SCALE, _PATTERN, ControlStatementsCheck, control_statements)
from dialectical_framework.concerns.tetrad_candidates import (SketchVerdict,
                                                              ranking)
from dialectical_framework.graph.nodes.estimation import \
    CONCEPTUAL_COHERENCE_THRESHOLD

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_ASPECTS = ("t_plus", "t_minus", "a_plus", "a_minus")
_CONCURRENCY = 6


# --- The candidate judge, as it shipped in src/ for one day ------------------
# Kept HERE, not in the library: it was measured against the per-statement
# judge and rejected (the module docstring's result, and
# `tetrad_candidates.judge_sketches`). Library code that looks usable and was
# measured not to be is a trap; a probe that can still run what it measured
# is the record.


class TetradCoherenceDto(BaseModel):
    """One tetrad's two control statements, CC only (no DV, a short note)."""

    tetrad: int = Field(description="The number of the tetrad this verdict scores, exactly as labelled in the request.")
    t_plus_without_a_plus_yields_t_minus: float = Field(ge=0.0, le=1.0, description="Conceptual Coherence (0.0-1.0) of that tetrad's statement (a).")
    a_plus_without_t_plus_yields_a_minus: float = Field(ge=0.0, le=1.0, description="Conceptual Coherence (0.0-1.0) of that tetrad's statement (b).")
    reasoning: str = Field(description="One sentence on the weaker of that tetrad's two statements. A note, not an essay.")


class JointCoherenceEvaluationDto(BaseModel):
    verdicts: list[TetradCoherenceDto] = Field(description="One entry per tetrad in the request, in the request's order. Score every tetrad; omit none.")


async def score_texts_many(tetrads: list[dict[str, str]], text: str = "") -> list[Optional[TetradCoherenceDto]]:
    """Several tetrads' control statements in ONE call, placed by the echoed
    tetrad number (an omitted, out-of-range or repeated number is `None`)."""
    if not tetrads:
        return []
    blocks = []
    for n, t in enumerate(tetrads, 1):
        stmt_a, stmt_b = control_statements(**{k: t[k] for k in _ASPECTS})
        blocks.append(f"Tetrad {n}:\n(a) {stmt_a}\n(b) {stmt_b}")
    context_section = f"<context>\n{text}\n</context>\n\n" if text else ""
    joined = "\n\n".join(blocks)
    prompt = f"""{context_section}Rate the control statements of {len(tetrads)} tetrads. Each tetrad has two statements, (a) and (b).

{joined}

{_PATTERN}

Rate every statement on one scale:

{_CC_SCALE}

Score each tetrad on its own, against the pattern above and nothing else. These are independent drafts: do not compare them with each other, do not rank them, do not pick a best, and do not let one tetrad's wording move another's score. The order they appear in carries no information. Return one verdict per tetrad, labelled with that tetrad's number."""
    result = await ConversationFacilitator().submit(response_model=JointCoherenceEvaluationDto, user_content=prompt)
    placed: list[Optional[TetradCoherenceDto]] = [None] * len(tetrads)
    for verdict in result.verdicts:
        index = verdict.tetrad - 1
        if 0 <= index < len(placed) and placed[index] is None:
            placed[index] = verdict
    return placed


def _triples() -> list[dict[str, Any]]:
    """Utterance -> its first three stored drafts with a `cc` pair, in file order."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(glob.glob(str(_RESULTS / "*.json"))):
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            for draft in [row] + [p for p in row.get("perspectives", []) if isinstance(p, dict)]:
                if all(isinstance(draft.get(k), str) and draft[k].strip() for k in _ASPECTS) \
                        and isinstance(draft.get("cc"), list) and len(draft["cc"]) == 2:
                    by[row.get("utterance") or ""].append({
                        "source": Path(path).name,
                        **{k: draft[k] for k in _ASPECTS},
                        "stored_cc": [float(x) for x in draft["cc"]],
                    })
    return [{"utterance": u, "drafts": d[:3]} for u, d in by.items() if u and len(d) >= 3]


def _passes(pair: Optional[list[float]]) -> Optional[bool]:
    return None if pair is None else min(pair) >= CONCEPTUAL_COHERENCE_THRESHOLD


async def _old(draft: dict[str, Any]) -> Optional[list[float]]:
    try:
        first, second = await ControlStatementsCheck().score_texts(**{k: draft[k] for k in _ASPECTS})
        return [first.coherence_score, second.coherence_score]
    except Exception:  # noqa: BLE001 - recorded as unjudged
        return None


async def _joint(drafts: list[dict[str, Any]], order: list[int]) -> list[Optional[list[float]]]:
    """Scores per ORIGINAL draft index, whatever order the drafts were shown in."""
    try:
        got = await score_texts_many([drafts[i] for i in order])
    except Exception:  # noqa: BLE001
        return [None] * len(drafts)
    out: list[Optional[list[float]]] = [None] * len(drafts)
    for slot, original in enumerate(order):
        v = got[slot]
        if v is not None:
            out[original] = [v.t_plus_without_a_plus_yields_t_minus, v.a_plus_without_t_plus_yields_a_minus]
    return out


def _winner(scores: list[Optional[list[float]]], order: list[int]) -> tuple[Optional[int], bool]:
    """(original index of the winner, whether a tie-break decided it). Ranked in
    SHOWN order, exactly as production ranks what it was handed."""
    shown = [scores[i] for i in order]
    verdicts = [None if s is None else SketchVerdict(*s) for s in shown]
    if all(v is None for v in verdicts):
        return None, False
    best = ranking(verdicts)[0]
    key = lambda v: (v.floor, (v.t_plus_without_a_plus + v.a_plus_without_t_plus) / 2)  # noqa: E731
    top = key(verdicts[best])
    tied = sum(1 for v in verdicts if v is not None and key(v) == top) > 1
    return order[best], tied


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_joint_judge_stability(di_container) -> None:
    triples = _triples()
    assert triples, "no stored drafts with per-statement verdicts to re-judge"
    out = _RESULTS / f"joint_judge_stability-{time.strftime('%Y%m%d-%H%M%S')}.json"
    gate = asyncio.Semaphore(_CONCURRENCY)
    forward, reverse = [0, 1, 2], [2, 1, 0]

    async def one(t: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            old = await asyncio.gather(*(_old(d) for d in t["drafts"]))
            a, b, c = await asyncio.gather(
                _joint(t["drafts"], forward), _joint(t["drafts"], forward), _joint(t["drafts"], reverse)
            )
        stored = [d["stored_cc"] for d in t["drafts"]]
        row = {
            "utterance": t["utterance"],
            "sources": [d["source"] for d in t["drafts"]],
            "stored": stored, "old_rerun": old, "joint_a": a, "joint_b": b, "joint_c": c,
        }
        for name, scores, order in (("stored", stored, forward), ("old_rerun", old, forward),
                                    ("joint_a", a, forward), ("joint_b", b, forward),
                                    ("joint_c", c, reverse)):
            row[f"winner_{name}"], row[f"tied_{name}"] = _winner(scores, order)
        print(f"  win stored {row['winner_stored']} old {row['winner_old_rerun']} "
              f"A {row['winner_joint_a']} B {row['winner_joint_b']} C {row['winner_joint_c']}"
              f"  «{t['utterance'][:50]}»", flush=True)
        return row

    rows = await asyncio.gather(*(one(t) for t in triples))
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    def pass_agree(x: str, y: str) -> str:
        pairs = [(_passes(r[x][i]), _passes(r[y][i])) for r in rows for i in range(3)]
        judged = [(p, q) for p, q in pairs if p is not None and q is not None]
        same = sum(1 for p, q in judged if p == q)
        return f"{same}/{len(judged)} ({100 * same / max(1, len(judged)):.0f}%)"

    def winner_agree(x: str, y: str) -> str:
        judged = [r for r in rows if r[f"winner_{x}"] is not None and r[f"winner_{y}"] is not None]
        same = sum(1 for r in judged if r[f"winner_{x}"] == r[f"winner_{y}"])
        return f"{same}/{len(judged)} ({100 * same / max(1, len(judged)):.0f}%)"

    def first_slot(name: str, first_index: int) -> str:
        judged = [r for r in rows if r[f"winner_{name}"] is not None]
        k = sum(1 for r in judged if r[f"winner_{name}"] == first_index)
        ties = sum(1 for r in judged if r[f"tied_{name}"])
        return f"{k}/{len(judged)} in slot 1, {ties} decided by tie-break"

    def mean_abs(x: str, y: str) -> str:
        diffs = [abs(min(r[x][i]) - min(r[y][i])) for r in rows for i in range(3)
                 if r[x][i] is not None and r[y][i] is not None]
        return f"{sum(diffs) / max(1, len(diffs)):.3f}"

    print(f"\n--- {len(rows)} triples, {3 * len(rows)} drafts -> {out.name} ---")
    print("  pass/fail agreement with the stored per-statement verdict:")
    print(f"    old judge re-run : {pass_agree('stored', 'old_rerun')}   |floor diff| {mean_abs('stored', 'old_rerun')}")
    print(f"    joint judge (A)  : {pass_agree('stored', 'joint_a')}   |floor diff| {mean_abs('stored', 'joint_a')}")
    print("  self-agreement:")
    print(f"    joint A vs B pass/fail {pass_agree('joint_a', 'joint_b')}, winner {winner_agree('joint_a', 'joint_b')}, |floor diff| {mean_abs('joint_a', 'joint_b')}")
    print(f"    old stored vs re-run winner {winner_agree('stored', 'old_rerun')}")
    print("  position (A forward vs C reversed):")
    print(f"    pass/fail {pass_agree('joint_a', 'joint_c')}, winner {winner_agree('joint_a', 'joint_c')}")
    print(f"    A: {first_slot('joint_a', 0)};  C: {first_slot('joint_c', 2)};  B: {first_slot('joint_b', 0)}")
    print(f"    old re-run (shown 1-2-3): {first_slot('old_rerun', 0)}")
    print("  winner agreement with the old judge:")
    print(f"    joint A vs old re-run {winner_agree('joint_a', 'old_rerun')}, joint A vs stored {winner_agree('joint_a', 'stored')}")


async def _per_draft(draft: dict[str, Any]) -> Optional[list[float]]:
    """The fallback rung: ONE call per draft, both statements in it — the joint
    prompt and DTO handed a single tetrad, so no draft is ever beside another."""
    try:
        (v,) = await score_texts_many([draft])
    except Exception:  # noqa: BLE001
        return None
    return None if v is None else [v.t_plus_without_a_plus_yields_t_minus, v.a_plus_without_t_plus_yields_a_minus]


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_per_draft_judge(di_container) -> None:
    """The rung below the joint call (2026-10-06: the joint judge picked by
    position — 18% winner agreement across the reversed order, 29/40 first-slot
    wins). Same triples, same reads, minus position (independent calls have
    none): agreement with the stored verdict against the old judge's own re-run,
    self-agreement, winner agreement, and how many winners a tie decides."""
    triples = _triples()
    out = _RESULTS / f"per_draft_judge-{time.strftime('%Y%m%d-%H%M%S')}.json"
    gate = asyncio.Semaphore(_CONCURRENCY)
    order = [0, 1, 2]

    async def one(t: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            old, a, b = await asyncio.gather(
                asyncio.gather(*(_old(d) for d in t["drafts"])),
                asyncio.gather(*(_per_draft(d) for d in t["drafts"])),
                asyncio.gather(*(_per_draft(d) for d in t["drafts"])),
            )
        row = {"utterance": t["utterance"], "stored": [d["stored_cc"] for d in t["drafts"]],
               "old_rerun": list(old), "per_draft_a": list(a), "per_draft_b": list(b)}
        for name in ("stored", "old_rerun", "per_draft_a", "per_draft_b"):
            row[f"winner_{name}"], row[f"tied_{name}"] = _winner(row[name], order)
        return row

    rows = await asyncio.gather(*(one(t) for t in triples))
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    def pass_agree(x: str, y: str) -> str:
        judged = [(_passes(r[x][i]), _passes(r[y][i])) for r in rows for i in range(3)
                  if r[x][i] is not None and r[y][i] is not None]
        same = sum(1 for p, q in judged if p == q)
        return f"{same}/{len(judged)} ({100 * same / max(1, len(judged)):.0f}%)"

    def winner_agree(x: str, y: str) -> str:
        judged = [r for r in rows if r[f"winner_{x}"] is not None and r[f"winner_{y}"] is not None]
        same = sum(1 for r in judged if r[f"winner_{x}"] == r[f"winner_{y}"])
        return f"{same}/{len(judged)} ({100 * same / max(1, len(judged)):.0f}%)"

    def shift(x: str, y: str) -> str:
        d = [min(r[y][i]) - min(r[x][i]) for r in rows for i in range(3)
             if r[x][i] is not None and r[y][i] is not None]
        return f"mean {sum(d) / max(1, len(d)):+.3f}, |mean| {sum(abs(v) for v in d) / max(1, len(d)):.3f}"

    ties = lambda name: sum(1 for r in rows if r[f"tied_{name}"])  # noqa: E731
    print(f"\n--- per-draft judge, {len(rows)} triples -> {out.name} ---")
    print(f"  pass/fail vs stored : old re-run {pass_agree('stored', 'old_rerun')}, per-draft {pass_agree('stored', 'per_draft_a')}")
    print(f"  floor shift vs stored: old re-run {shift('stored', 'old_rerun')}; per-draft {shift('stored', 'per_draft_a')}")
    print(f"  self: per-draft A vs B pass/fail {pass_agree('per_draft_a', 'per_draft_b')}, winner {winner_agree('per_draft_a', 'per_draft_b')}"
          f"; old stored vs re-run winner {winner_agree('stored', 'old_rerun')}")
    print(f"  winner vs old re-run: per-draft {winner_agree('per_draft_a', 'old_rerun')}; vs stored {winner_agree('per_draft_a', 'stored')}")
    print(f"  winners decided by a tie: old re-run {ties('old_rerun')}, per-draft A {ties('per_draft_a')}, B {ties('per_draft_b')}")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_short_reasoning_judge(di_container, monkeypatch) -> None:
    """The third candidate: the SAME per-statement prompt and DTO, only the two
    reasoning fields capped at one short sentence. Why it might be free: the
    DTO asks for `coherence_score` BEFORE `reasoning`, so the reasoning is
    written after the score selection reads; ~550 output tokens a call may be
    post-hoc explanation. Two phases, never interleaved (the DTO swap is a
    module attribute): the old judge re-run (baseline), then the short one.
    Reads: pass/fail agreement with the stored verdict for each, floor shift,
    winner agreement with the old re-run, and output tokens per call."""
    from dialectical_framework.concerns import control_statements_check as csc
    from dialectical_framework.utils.call_census import call_census

    class ShortCoherenceEvaluationDto(csc.CoherenceEvaluationDto):
        reasoning: str = Field(description="One short sentence on the coherence assessment — at most 20 words.")
        dv_reasoning: str = Field(description="One short sentence on the dialectical-validity assessment — at most 20 words.")

    triples = _triples()
    out = _RESULTS / f"short_reasoning_judge-{time.strftime('%Y%m%d-%H%M%S')}.json"
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def judge_all() -> tuple[list[list[Optional[list[float]]]], list[int]]:
        async def one(t: dict[str, Any]) -> list[Optional[list[float]]]:
            async with gate:
                return list(await asyncio.gather(*(_old(d) for d in t["drafts"])))
        with call_census() as census:
            scores = list(await asyncio.gather(*(one(t) for t in triples)))
        tokens = [c.output_tokens for c in census.calls if "CoherenceEvaluationDto" in c.label and c.output_tokens]
        return scores, tokens

    old, old_tokens = await judge_all()
    with monkeypatch.context() as mp:
        mp.setattr(csc, "CoherenceEvaluationDto", ShortCoherenceEvaluationDto)
        short, short_tokens = await judge_all()

    rows = []
    for t, o, s in zip(triples, old, short):
        row = {"utterance": t["utterance"], "stored": [d["stored_cc"] for d in t["drafts"]], "old_rerun": o, "short": s}
        for name in ("stored", "old_rerun", "short"):
            row[f"winner_{name}"], row[f"tied_{name}"] = _winner(row[name], [0, 1, 2])
        rows.append(row)
    out.write_text(json.dumps({"rows": rows, "old_tokens": old_tokens, "short_tokens": short_tokens}, indent=2, ensure_ascii=False))

    def pass_agree(x: str, y: str) -> str:
        judged = [(_passes(r[x][i]), _passes(r[y][i])) for r in rows for i in range(3)
                  if r[x][i] is not None and r[y][i] is not None]
        same = sum(1 for p, q in judged if p == q)
        return f"{same}/{len(judged)} ({100 * same / max(1, len(judged)):.0f}%)"

    def winner_agree(x: str, y: str) -> str:
        judged = [r for r in rows if r[f"winner_{x}"] is not None and r[f"winner_{y}"] is not None]
        same = sum(1 for r in judged if r[f"winner_{x}"] == r[f"winner_{y}"])
        return f"{same}/{len(judged)} ({100 * same / max(1, len(judged)):.0f}%)"

    def shift(x: str, y: str) -> str:
        d = [min(r[y][i]) - min(r[x][i]) for r in rows for i in range(3) if r[x][i] is not None and r[y][i] is not None]
        return f"mean {sum(d) / max(1, len(d)):+.3f}, |mean| {sum(abs(v) for v in d) / max(1, len(d)):.3f}"

    mean = lambda xs: sum(xs) / max(1, len(xs))  # noqa: E731
    print(f"\n--- short-reasoning judge, {len(rows)} triples -> {out.name} ---")
    print(f"  pass/fail vs stored : old re-run {pass_agree('stored', 'old_rerun')}, short {pass_agree('stored', 'short')}")
    print(f"  pass/fail short vs old re-run: {pass_agree('old_rerun', 'short')}")
    print(f"  floor shift vs stored: old re-run {shift('stored', 'old_rerun')}; short {shift('stored', 'short')}")
    print(f"  winner: short vs old re-run {winner_agree('short', 'old_rerun')}; short vs stored {winner_agree('short', 'stored')}; "
          f"old re-run vs stored {winner_agree('old_rerun', 'stored')}")
    print(f"  winners decided by a tie: old re-run {sum(1 for r in rows if r['tied_old_rerun'])}, short {sum(1 for r in rows if r['tied_short'])}")
    print(f"  output tokens per call: old {mean(old_tokens):.0f} (n={len(old_tokens)}), short {mean(short_tokens):.0f} (n={len(short_tokens)})")
