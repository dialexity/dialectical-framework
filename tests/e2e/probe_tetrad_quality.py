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
    TETRAD_PROBE_OFFSET=5 TETRAD_PROBE_LIMIT=5 ...   # a SLICE: utterances 5..9
    TETRAD_PROBE_MODE=context|given_a ...            # see MODES below

SLICES. A 20-utterance run is ~20–40 min and has been killed twice (the
background time limit, the machine's memory reaper). `TETRAD_PROBE_OFFSET` +
`TETRAD_PROBE_LIMIT` run a slice; the file name carries mode and offset so
slices never overwrite each other, and

    python tests/e2e/probe_tetrad_quality.py --summarise 'tests/e2e/results/tetrad_quality/set_a-context-off*.json'

prints the same summary over every file the glob matches (an utterance seen
twice keeps its LAST reading).

MODES (`TETRAD_PROBE_MODE`, default `default` = behaviour unchanged)
====================================================================
  default   `_anchor(thesis=text, antithesis=None, context="")` — the bare
            thesis-only path every earlier run measured.
  context   `_anchor(thesis=text, antithesis=None, context=text)` — the same
            path with the person's whole utterance passed as context: does the
            utterance reaching the pipeline change anything end to end?
  given_a   ONE cheap structured call first reads the whole utterance and names
            what the position stands against, as the other side of the
            person's own dilemma; then `_anchor(thesis=text, antithesis=<that>,
            context=text)` — the EXISTING thesis-plus-antithesis path
            (`IntroducePolarity` → `ExpandPolarity`), no ladder, no selector.
  ingest    `AnalysisPipeline(text=text)` — the headless path the Advisor's
            `ingest` tool runs: the utterance is an Input, theses are EXTRACTED
            from it (`SurfaceTheses`), every expanded perspective is recorded
            with the same fields, and `extracted_theses` keeps what extraction
            made of the sentence (text + SIMPLE flag per thesis).
  oneshot   `capture_input(text)` + `SketchTetrad(input_hashes=[…])` — item 3: ONE thinking call writes
            T, A and the four aspects from the utterance, then
            `IntroducePolarity` + `ExpandPolarity(given_tetrad=)` score, dedup,
            ground, validate and persist it. Pre-registered bar before it
            replaces the staged thesis-only `anchor`: first-tetrad CC ≥ 20/40
            on sets A+B, antithesis a position ≥ 30/40, restatement ≤ 3/80.
  oneshot_persona  the same with `COUNSELOR_PERSONA` above the method — the
            bundle the 26/40 harness arm carried; a gap ≥ 5 against `oneshot`
            says the persona did work (a finding to record, not to ship).
"""

from __future__ import annotations

import asyncio
import collections
import glob as glob_module
import json
import os
import sys
import time
from pathlib import Path
from typing import Literal, Optional

# `python tests/e2e/probe_tetrad_quality.py --summarise …` puts tests/e2e on the
# path, not tests/; under pytest tests/ is already there and this is a no-op.
_TESTS_DIR = str(Path(__file__).resolve().parent.parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.tools.anchor import _anchor
from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.estimation import (
    ArousalEstimation, ConceptualCoherenceEstimation,
    DialecticalValidityEstimation, ModeEstimation, TetradPotentialEstimation)
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.statement import Statement
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


_MODES = ("default", "context", "given_a", "ingest", "oneshot", "oneshot_persona")


class _NamedAntithesis(BaseModel):
    antithesis: str = Field(
        description=(
            "What this position stands against — the OTHER side of the person's own "
            "dilemma, as a position someone holds for its own value, in the person's "
            "terms. 7 words or fewer, no explanation."
        )
    )


async def _name_antithesis(text: str) -> str:
    """`given_a` mode's one cheap call: the other side of the person's dilemma.

    Forced-tool structured call on the generator model, no thinking — the same
    shape every concern uses. Deliberately NOT the ladder: the question is what
    the existing thesis-plus-antithesis path builds when it is handed the kind
    of antithesis the Consultant's view turn names.
    """
    conversation = ConversationFacilitator()
    conversation.set_system_prompt(
        "You read one thing a person said and name what their position stands against."
    )
    verdict = await conversation.submit(
        _NamedAntithesis,
        f'The person said: "{text}"\n\n'
        "Name what this position stands against: the other side of the person's own "
        "dilemma, as a position someone holds for its own value — not the position's "
        "absence, not a caricature. In the person's terms, 7 words or fewer.",
    )
    return verdict.antithesis.strip()


def _print_summary(items: list[dict], out: Optional[Path] = None) -> None:
    """The run's summary, over ALL expanded perspectives and over the FIRST per
    utterance. Module-level so `--summarise` prints the same thing over slices."""
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
    secs = sorted(it["seconds"] for it in items if it.get("seconds") is not None)
    if secs:
        print(f"\n  latency median {secs[len(secs)//2]}s  max {secs[-1]}s;  errors "
              f"{sum('error' in it for it in items)}/{len(items)}"
              + (f"\n  written: {out}" if out else ""), flush=True)


def _load_slices(pattern: str) -> list[dict]:
    """Every item of every file the glob matches, in file-name order; an
    utterance read twice keeps its LAST reading, in its first position."""
    by_utterance: dict[str, dict] = {}
    for path in sorted(glob_module.glob(pattern)):
        for item in json.loads(Path(path).read_text()):
            by_utterance[item["utterance"]] = item
    return list(by_utterance.values())


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_tetrad_quality(di_container) -> None:
    which = os.environ.get("TETRAD_PROBE_SET", "a").lower()
    mode = os.environ.get("TETRAD_PROBE_MODE", "default").lower()
    if mode not in _MODES:
        raise ValueError(f"TETRAD_PROBE_MODE={mode!r}; expected one of {_MODES}")
    utterances = list(_SETS[which])
    # TETRAD_PROBE_ATTEMPTS=N: the build draws N sketches and keeps the best
    # (`concerns/tetrad_candidates.py`); the module default is what production
    # runs. The probe's own validation read is a FRESH judge pass.
    import dialectical_framework.concerns.tetrad_candidates as cands

    cands.DEFAULT_SKETCH_ATTEMPTS = int(os.environ.get("TETRAD_PROBE_ATTEMPTS", str(cands.DEFAULT_SKETCH_ATTEMPTS)))
    offset = int(os.environ.get("TETRAD_PROBE_OFFSET", "0") or 0)
    limit = int(os.environ.get("TETRAD_PROBE_LIMIT", "0") or 0)
    if offset or limit:
        end = offset + limit if limit else len(utterances)
        print(f"\n!! SLICE of set {which}: utterances [{offset}:{end}) — PARTIAL RUN",
              flush=True)
        utterances = utterances[offset:end]
    config = E2EConfig.from_env()
    judge_model = config.judge_model
    out_dir = Path(os.environ.get("TETRAD_PROBE_OUT", str(_DEFAULT_OUT)))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    # The historical name is kept for the unsliced default run, so the archive's
    # globs still mean what they meant; anything else names its mode and offset.
    if mode == "default" and not offset and not os.environ.get("TETRAD_PROBE_ATTEMPTS"):
        out = out_dir / f"set_{which}-{stamp}.json"
    else:
        variant = "-oneshot" if mode == "ingest" and os.environ.get("TETRAD_PROBE_ONESHOT_PER_THESIS") else ""
        if os.environ.get("TETRAD_PROBE_ATTEMPTS"):
            variant += f"-att{os.environ['TETRAD_PROBE_ATTEMPTS']}"
        out = out_dir / f"set_{which}-{mode}{variant}-off{offset:02d}-{stamp}.json"
    gen_model = di_container.settings().ai_model
    print(f"\n=== tetrad quality: set {which}, mode {mode}, {len(utterances)} utterances, "
          f"generator {gen_model}, auditor {judge_model} ===\n→ {out}", flush=True)

    items: list[dict] = []
    for index, text in enumerate(utterances, 1):
        case = Case()
        case.commit()
        started = time.monotonic()
        item: dict = {"utterance": text, "sid": case.sid, "mode": mode, "perspectives": []}
        with scope(case.sid):
            try:
                if mode == "given_a":
                    item["named_antithesis"] = await _name_antithesis(text)
                    raw = await _anchor(
                        thesis=text, antithesis=item["named_antithesis"], context=text
                    )
                elif mode in ("oneshot", "oneshot_persona"):
                    from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
                        SketchTetrad
                    from dialectical_framework.agents.apps import COUNSELOR_PERSONA

                    from dialectical_framework.concerns.add_input import capture_input

                    source = await capture_input(text)
                    skill = SketchTetrad(
                        input_hashes=[source.hash] if source and source.hash else [],
                        persona=COUNSELOR_PERSONA if mode == "oneshot_persona" else None,
                    )
                    await skill.resolve()
                    raw = str(skill.report)
                    item["sketch"] = skill.report.artifacts.get("sketch")
                elif mode == "ingest":
                    # The pipeline's own capture adds the Input and digests it
                    # (a one-sentence Input is under the digest threshold, so
                    # the digest IS the sentence); `intent` left to its default.
                    # TETRAD_PROBE_ONESHOT_PER_THESIS=1 flips the pipeline's
                    # per-thesis build to the one-shot writer (consolidation 2).
                    if os.environ.get("TETRAD_PROBE_ONESHOT_PER_THESIS"):
                        # HISTORICAL: the per-thesis one-shot route was measured
                        # (set_*-ingest-oneshot-off*-20261002-*.json) and removed;
                        # see the dev note, "Consolidation 2".
                        raise RuntimeError("TETRAD_PROBE_ONESHOT_PER_THESIS is historical: the route was removed")
                    pipeline = AnalysisPipeline(text=text)
                    await pipeline.resolve()
                    raw = str(pipeline.report)
                elif mode == "context":
                    raw = await _anchor(thesis=text, antithesis=None, context=text)
                else:
                    raw = await _anchor(thesis=text, antithesis=None, context="")
                report = json.loads(raw)
                item["report_ok"] = report.get("ok")
                item["report_summary"] = report.get("summary")
                hashes = (report.get("artifacts") or {}).get("perspective_hashes") or []
                item["polarity_quality"] = (report.get("artifacts") or {}).get("polarity_quality")
                repo = NodeRepository()
                if mode == "ingest":
                    thesis_hashes = (report.get("artifacts") or {}).get("thesis_hashes") or []
                    item["extracted_theses"] = [
                        {"hash": h, "text": s.text, "simple": bool(getattr(s, "is_simple", False))}
                        for h in thesis_hashes
                        if (s := repo.find_by_hash(h, node_type=Statement)) is not None
                    ]
                for rank, h in enumerate(hashes, 1):
                    pp = repo.find_by_hash(h, node_type=Perspective)
                    if pp is not None:
                        item["perspectives"].append(_row(pp, rank))
            except Exception as exc:  # noqa: BLE001
                item["error"] = repr(exc)
        item["seconds"] = round(time.monotonic() - started, 1)
        # the auditor, outside the scope: it reads text, writes nothing
        # Gathered: the three auditors read text and write nothing, and run
        # sequentially they were most of a slice's wall time (~1 min/utterance).
        async def _audit(row: dict) -> None:
            verdicts = await asyncio.gather(
                _audit_kind(di_container, judge_model, row["thesis"], row["antithesis"]),
                _audit_pluses(di_container, judge_model, row),
                _audit_parentage(di_container, judge_model, row),
            )
            for verdict in verdicts:
                row.update(verdict)

        # ONE outer `using_model` around the gather: each auditor enters its own,
        # and interleaved exits would otherwise restore another auditor's
        # override — leaving the NEXT utterance generating on the judge model.
        # The outer exit is the one that restores the generator's settings.
        with using_model(di_container, judge_model):
            await asyncio.gather(*(
                _audit(row) for row in item["perspectives"]
                if row.get("thesis") and row.get("antithesis")
            ))
        assert di_container.settings().ai_model == gen_model, (
            "the auditors left the judge model installed"
        )
        items.append(item)
        out.write_text(json.dumps(items, indent=1, ensure_ascii=False))  # incremental
        first = item["perspectives"][0] if item["perspectives"] else None
        line = (f"  [{index}/{len(utterances)}] {item['seconds']}s  {len(item['perspectives'])} pp  "
                + (f"A[{first.get('a_kind')}/{first.get('a_rung')}/pot {first.get('a_tetrad_potential')}] "
                   f"CC {first.get('cc_t')}/{first.get('cc_a')} {'PASS' if first.get('cc_pass') else 'fail'}  "
                   f"«{first.get('antithesis')}»" if first else item.get("error", "nothing drawn")))
        print(line, flush=True)

    _print_summary(items, out)


if __name__ == "__main__":
    # Summarise one or more saved slice files. No provider, no graph.
    if len(sys.argv) == 3 and sys.argv[1] == "--summarise":
        loaded = _load_slices(sys.argv[2])
        print(f"{len(loaded)} utterances from {len(glob_module.glob(sys.argv[2]))} "
              f"file(s) matching {sys.argv[2]}")
        _print_summary(loaded)
    else:
        print("usage: python tests/e2e/probe_tetrad_quality.py --summarise '<glob>'")
        sys.exit(2)
