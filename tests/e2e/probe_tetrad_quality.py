"""
Tetrad quality on the thesis-only build path — the instrument the antithesis
finding was missing.

WHY THIS EXISTS
===============
The bench judges COUNSEL. Nothing measured whether the tetrads under it were
any good: the only number on an antithesis was HS, and a uniform 0.95 read as
"all genuine" when it was the broken gauge (`docs/dev-notes/antithesis-selection.md`).
This probe records, for every perspective the thesis-only `anchor` path
expands from a free utterance, everything a later argument needs — and
persists it per item, incrementally, so a killed run still leaves its rows.

Per utterance → per expanded perspective:
- thesis text and whether it classified SIMPLE (mechanical negation, HS 1.0,
  no ladder, no potential) or COMPLEX;
- the antithesis text, its ladder rung / Mode, HS, Arousal, `tetrad_potential`
  (read off the Estimations the pipeline persisted, never re-derived);
- the four aspects, the reading (`intent`), SP;
- CC per control statement, DV per control statement, the validation verdict;
- an auditor verdict on the antithesis KIND under the operational definition
  below, from the bench's judge model, with its reasoning kept.

OPERATIONAL DEFINITION OF ANTITHESIS KIND (fixed before the population was run)
===============================================================================
  POSITION            a stance a reasonable person holds for its own value that
                      functionally opposes the role the thesis plays; it could
                      be developed constructively (an A+ exists).
  MIRROR              the thesis reversed along its own variable — same axis,
                      opposite direction ("raise prices" ↔ "lower prices") —
                      with no independent value named.
  CARICATURE          the thesis's absence or degradation dressed as a stance;
                      an extreme nobody would hold ("never risk anything, ever").
  NOT_AN_OPPOSITION   restates the thesis, is unrelated, or changes the subject.

POPULATIONS
===========
SET_A is the 20 utterances of `tests/probe_blindspot_paths.py` — the set the
finding was made on, kept for replication. SET_B is 20 fresh utterances under
the same rule (one free utterance a person might type into a blindspot app:
statements, complaints, questions, decisions; no reuse of SET_A's subjects).
Tuning on SET_A and confirming on SET_B is the honest order.

    poetry run pytest tests/e2e/probe_tetrad_quality.py --real-llm -q -s
    TETRAD_PROBE_SET=b ...     # the fresh set; ab for both
    TETRAD_PROBE_LIMIT=5 ...   # a partial run, announced as such
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import time
from pathlib import Path
from typing import Literal, Optional

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.tools.anchor import _anchor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.estimation import (
    ArousalEstimation, ConceptualCoherenceEstimation,
    DialecticalValidityEstimation, ModeEstimation, TetradPotentialEstimation)
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.graph.views import perspective_view
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.probe_tetrad_pole import _PoleVerdict, _audit_prompt  # the restatement/parentage auditor

pytestmark = [pytest.mark.llm]

SET_A = [
    "I should quit my job and start my own company.",
    "My co-founder never listens to me.",
    "Should I move to Berlin for this job offer?",
    "Remote work is killing our culture.",
    "I need to be more disciplined.",
    "We're going to cut the marketing budget in half.",
    "My teenage son spends all his time gaming and I have to stop it.",
    "I always say yes to my clients and it's exhausting.",
    "The team needs a proper process; everything is chaos.",
    "I don't trust my new manager.",
    "We should hire senior people only, juniors slow us down.",
    "I want to move my parents into a care home.",
    "I keep postponing the difficult conversation with my partner.",
    "Our product needs more features to compete.",
    "I think I should stop lending money to my brother.",
    "Why does every meeting end without a decision?",
    "I'm going to homeschool my kids.",
    "My best engineer wants to become a manager and I think it's a mistake.",
    "I should stop checking work email on weekends.",
    "We need to raise prices, we're too cheap.",
]

SET_B = [
    "I'm going to fire our agency and bring design in-house.",
    "My daughter wants to drop out of university to travel.",
    "Should we open a second restaurant while the first is barely profitable?",
    "I never take holidays because the business can't run without me.",
    "Our church should stop accepting donations from the casino owner.",
    "I want to move back to my hometown to be near family.",
    "We're switching the whole company to a four-day week.",
    "My father refuses to stop driving and he's eighty-four.",
    "I should stop giving free advice to friends who never act on it.",
    "The board wants quarterly targets; we build long-term products.",
    "I'm thinking of telling my boss I'm looking elsewhere.",
    "Our village should ban cars from the centre.",
    "I keep saying I'll write the book but I never start.",
    "We should stop hiring remote people and go office-first.",
    "My sister expects me to host every family holiday.",
    "I'm going to sell the flat and rent instead.",
    "Why do I always end up leading projects I never volunteered for?",
    "We need to open-source the core product.",
    "I should confront my neighbour about the noise.",
    "Our team should stop doing estimates altogether.",
]

_SETS = {"a": SET_A, "b": SET_B, "ab": SET_A + SET_B}

_DEFAULT_OUT = Path(__file__).resolve().parent / "results" / "tetrad_quality"


class _KindVerdict(BaseModel):
    kind: Literal["position", "mirror", "caricature", "not_an_opposition"] = Field(
        description=(
            "POSITION: a stance a reasonable person holds for its own value that "
            "functionally opposes the role the thesis plays; it could be developed "
            "constructively. MIRROR: the thesis reversed along its own variable — "
            "same axis, opposite direction — with no independent value named. "
            "CARICATURE: the thesis's absence or degradation dressed as a stance; an "
            "extreme nobody would hold. NOT_AN_OPPOSITION: restates the thesis, is "
            "unrelated, or changes the subject."
        )
    )
    reasoning: str = Field(description="One or two sentences: which test decided it.")


class _PlusVerdict(BaseModel):
    relation: Literal["distinct", "same_compromise", "one_is_the_other_parent", "unreadable"] = Field(
        description=(
            "DISTINCT: T+ and A+ are two different moves — each develops its OWN parent, "
            "and one could hold without the other. SAME_COMPROMISE: both describe the same "
            "sensible middle (each is its parent moderated by the other's constraint), so "
            "they are one move written twice. ONE_IS_THE_OTHER_PARENT: one plus is really "
            "the other pole developed. UNREADABLE: cannot tell."
        )
    )
    reasoning: str = Field(description="One or two sentences: which test decided it.")


_PLUS_AUDIT_SYSTEM = """You audit the two POSITIVE aspects of a dialectical tetrad.
T+ is the thesis developed constructively; A+ is the antithesis developed constructively. They must be two DIFFERENT moves from two different parents — the synthesis emerges BETWEEN them. The failure to detect: both pluses have converged on the same compromise (the thesis hedged by the antithesis's concern, and the antithesis hedged by the thesis's concern), so "T+ without A+" is meaningless because T+ already contains A+.
Judge only the relation between T+ and A+ given T and A. Do not judge whether either is wise."""


_AUDIT_SYSTEM = """You audit ONE antithesis against ONE thesis and classify the antithesis's kind.
Judge only the relation between the two statements. Do not judge whether either is wise.
Decide in this order: is it an opposition at all? if so, is it the same variable reversed with nothing of its own (mirror)? if not, would a reasonable person hold it for its own value (position)? if nobody would hold it and it only exaggerates absence (caricature)."""


def _num(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(float(x), 3)


def _estimations(node) -> dict:
    out: dict = {}
    try:
        for est, _ in node.estimations.all():
            if isinstance(est, ModeEstimation):
                out["mode"] = _num(est.value)
            elif isinstance(est, ArousalEstimation):
                out["arousal"] = _num(est.value)
            elif isinstance(est, TetradPotentialEstimation):
                out["tetrad_potential"] = _num(est.value)
            elif isinstance(est, ConceptualCoherenceEstimation):
                out["cc_t"] = _num(est.t_plus_without_a_plus_yields_t_minus)
                out["cc_a"] = _num(est.a_plus_without_t_plus_yields_a_minus)
                out["cc_pass"] = bool(est.is_coherent)
            elif isinstance(est, DialecticalValidityEstimation):
                out["dv"] = _num(est.value)
    except Exception as exc:  # noqa: BLE001 — a probe records, never hides
        out["estimation_error"] = repr(exc)
    return out


def _rung(mode: Optional[float]) -> Optional[str]:
    if mode is None:
        return None
    names = {1.0: "negation", 0.9: "inversion", 0.8: "devaluation", 0.7: "hollowing",
             0.6: "corruption", 0.5: "distortion", 0.4: "skew", 0.3: "blocking",
             0.2: "suppression", 0.1: "distancing", 0.0: "privation"}
    return names.get(round(mode, 1))


def _row(pp: Perspective, rank: int) -> dict:
    view = perspective_view(pp)
    t_stmt = pp.t.get()[0] if pp.t.get() else None
    a_stmt = pp.a.get()[0] if pp.a.get() else None
    a_est = _estimations(a_stmt) if a_stmt is not None else {}
    pp_est = _estimations(pp)
    return {
        "rank": rank,
        "perspective_hash": pp.hash,
        "thesis": view.t.text if view.t else None,
        "thesis_simple": bool(t_stmt.is_simple) if t_stmt is not None else None,
        "antithesis": view.a.text if view.a else None,
        "a_hs": _num(view.a.hs) if view.a else None,
        "a_mode": a_est.get("mode"),
        "a_rung": _rung(a_est.get("mode")),
        "a_arousal": a_est.get("arousal"),
        "a_tetrad_potential": a_est.get("tetrad_potential"),
        "t_plus": view.t_plus.text if view.t_plus else None,
        "t_minus": view.t_minus.text if view.t_minus else None,
        "a_plus": view.a_plus.text if view.a_plus else None,
        "a_minus": view.a_minus.text if view.a_minus else None,
        "intent": view.intent,
        "sp": _num(view.metrics.sp) if view.metrics else None,
        "cc_t": pp_est.get("cc_t"),
        "cc_a": pp_est.get("cc_a"),
        "cc_pass": pp_est.get("cc_pass"),
        "dv": pp_est.get("dv"),
        "validation": view.validation,
        "complete": view.complete,
    }


async def _audit_kind(container, judge_model: str, thesis: str, antithesis: str) -> dict:
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_AUDIT_SYSTEM)
        with using_model(container, judge_model):
            verdict = await conversation.submit(
                _KindVerdict,
                f'Thesis: "{thesis}"\nAntithesis: "{antithesis}"\n\nClassify the antithesis\'s kind.',
            )
        return {"a_kind": verdict.kind, "a_kind_reasoning": verdict.reasoning}
    except Exception as exc:  # noqa: BLE001
        return {"a_kind": None, "a_kind_error": repr(exc)}


async def _audit_parentage(container, judge_model: str, row: dict) -> dict:
    """The map's OTHER direction: does each plus develop its OWN parent (or
    restate it / cross to the other pole)? Reuses `probe_tetrad_pole`'s auditor
    verbatim so the number is comparable with the archive's 13.3% / 7.8%."""
    out: dict = {}
    for position, key, own, other in (
        ("T+", "t_plus", row.get("thesis"), row.get("antithesis")),
        ("A+", "a_plus", row.get("antithesis"), row.get("thesis")),
    ):
        aspect = row.get(key)
        if not (aspect and own and other):
            out[f"{key}_parent"] = None
            continue
        try:
            conversation = ConversationFacilitator()
            conversation.set_system_prompt(_audit_prompt(own, other, position, aspect))
            with using_model(container, judge_model):
                verdict = await conversation.submit(_PoleVerdict, "Audit the aspect against the structural rule.")
            out[f"{key}_parent"] = verdict.parent
            out[f"{key}_valence_ok"] = bool(verdict.valence_matches_claim)
        except Exception as exc:  # noqa: BLE001
            out[f"{key}_parent"] = None
            out[f"{key}_parent_error"] = repr(exc)
    return out


async def _audit_pluses(container, judge_model: str, row: dict) -> dict:
    if not all(row.get(k) for k in ("thesis", "antithesis", "t_plus", "a_plus")):
        return {"plus_relation": None}
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_PLUS_AUDIT_SYSTEM)
        with using_model(container, judge_model):
            verdict = await conversation.submit(
                _PlusVerdict,
                f'T: "{row["thesis"]}"\nA: "{row["antithesis"]}"\n'
                f'T+: "{row["t_plus"]}"\nA+: "{row["a_plus"]}"\n\n'
                "Classify the relation between T+ and A+.",
            )
        return {"plus_relation": verdict.relation, "plus_reasoning": verdict.reasoning}
    except Exception as exc:  # noqa: BLE001
        return {"plus_relation": None, "plus_error": repr(exc)}


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _pct(k: int, n: int) -> str:
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_tetrad_quality(di_container) -> None:
    which = os.environ.get("TETRAD_PROBE_SET", "a").lower()
    utterances = list(_SETS[which])
    limit = int(os.environ.get("TETRAD_PROBE_LIMIT", "0") or 0)
    if limit:
        print(f"\n!! TETRAD_PROBE_LIMIT={limit}: PARTIAL RUN of set {which}", flush=True)
        utterances = utterances[:limit]
    config = E2EConfig.from_env()
    judge_model = config.judge_model
    out_dir = Path(os.environ.get("TETRAD_PROBE_OUT", str(_DEFAULT_OUT)))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"set_{which}-{stamp}.json"
    gen_model = di_container.settings().ai_model
    print(f"\n=== tetrad quality: set {which}, {len(utterances)} utterances, "
          f"generator {gen_model}, auditor {judge_model} ===\n→ {out}", flush=True)

    items: list[dict] = []
    for index, text in enumerate(utterances, 1):
        case = Case()
        case.commit()
        started = time.monotonic()
        item: dict = {"utterance": text, "sid": case.sid, "perspectives": []}
        with scope(case.sid):
            try:
                report = json.loads(await _anchor(thesis=text, antithesis=None, context=""))
                hashes = (report.get("artifacts") or {}).get("perspective_hashes") or []
                item["polarity_quality"] = (report.get("artifacts") or {}).get("polarity_quality")
                repo = NodeRepository()
                for rank, h in enumerate(hashes, 1):
                    pp = repo.find_by_hash(h, node_type=Perspective)
                    if pp is not None:
                        item["perspectives"].append(_row(pp, rank))
            except Exception as exc:  # noqa: BLE001
                item["error"] = repr(exc)
        item["seconds"] = round(time.monotonic() - started, 1)
        # the auditor, outside the scope: it reads text, writes nothing
        for row in item["perspectives"]:
            if row.get("thesis") and row.get("antithesis"):
                row.update(await _audit_kind(di_container, judge_model, row["thesis"], row["antithesis"]))
                row.update(await _audit_pluses(di_container, judge_model, row))
                row.update(await _audit_parentage(di_container, judge_model, row))
        items.append(item)
        out.write_text(json.dumps(items, indent=1, ensure_ascii=False))  # incremental
        first = item["perspectives"][0] if item["perspectives"] else None
        line = (f"  [{index}/{len(utterances)}] {item['seconds']}s  {len(item['perspectives'])} pp  "
                + (f"A[{first.get('a_kind')}/{first.get('a_rung')}/pot {first.get('a_tetrad_potential')}] "
                   f"CC {first.get('cc_t')}/{first.get('cc_a')} {'PASS' if first.get('cc_pass') else 'fail'}  "
                   f"«{first.get('antithesis')}»" if first else item.get("error", "nothing drawn")))
        print(line, flush=True)

    # --- summary over ALL expanded perspectives, and over the FIRST per utterance ---
    rows = [r for it in items for r in it["perspectives"]]
    firsts = [it["perspectives"][0] for it in items if it["perspectives"]]

    def summarise(label: str, rs: list[dict]) -> None:
        n = len(rs)
        cc = sum(1 for r in rs if r.get("cc_pass"))
        kinds = collections.Counter(r.get("a_kind") for r in rs)
        rungs = collections.Counter(r.get("a_rung") for r in rs)
        simple = sum(1 for r in rs if r.get("thesis_simple"))
        print(f"\n--- {label}: {n} perspectives ---", flush=True)
        print(f"  CC pass       {_pct(cc, n)}", flush=True)
        print(f"  A kind        {dict(kinds)}", flush=True)
        print(f"  A rung        {dict(rungs)}", flush=True)
        print(f"  SIMPLE theses {simple}/{n}", flush=True)
        for kind in ("position", "mirror", "caricature", "not_an_opposition"):
            sub = [r for r in rs if r.get("a_kind") == kind]
            if sub:
                print(f"  CC pass | {kind:18s} {_pct(sum(1 for r in sub if r.get('cc_pass')), len(sub))}", flush=True)
        rels = collections.Counter(r.get("plus_relation") for r in rs)
        print(f"  T+/A+ relation {dict(rels)}", flush=True)
        for rel in ("distinct", "same_compromise", "one_is_the_other_parent"):
            sub = [r for r in rs if r.get("plus_relation") == rel]
            if sub:
                print(f"  CC pass | {rel:24s} {_pct(sum(1 for r in sub if r.get('cc_pass')), len(sub))}", flush=True)
        for key in ("t_plus", "a_plus"):
            par = collections.Counter(r.get(f"{key}_parent") for r in rs)
            print(f"  {key} parentage  {dict(par)}", flush=True)
        pots = [r["a_tetrad_potential"] for r in rs if r.get("a_tetrad_potential") is not None]
        if pots:
            passed = [r["a_tetrad_potential"] for r in rs if r.get("cc_pass") and r.get("a_tetrad_potential") is not None]
            failed = [r["a_tetrad_potential"] for r in rs if not r.get("cc_pass") and r.get("a_tetrad_potential") is not None]
            mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
            print(f"  potential mean  all {mean(pots):.2f}  CC-pass {mean(passed):.2f}  CC-fail {mean(failed):.2f}", flush=True)

    summarise("ALL expanded", rows)
    summarise("FIRST per utterance (what a blindspot screen shows)", firsts)
    secs = sorted(it["seconds"] for it in items)
    print(f"\n  latency median {secs[len(secs)//2]}s  max {secs[-1]}s;  errors "
          f"{sum('error' in it for it in items)}/{len(items)}\n  written: {out}", flush=True)
