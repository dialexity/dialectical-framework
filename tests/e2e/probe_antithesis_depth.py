"""Is the opposing view drawn from the SURFACE of the person's text — and can
this repo's own judge see it?

The first app's sixth handoff (2026-11-23, "the opposing view is drawn from
the surface of the text"; the file lives in the app repo and is retired once
this is taken up — its record is `docs/dev-notes/antithesis-selection.md`).
Its finding: on 52 shipped wheels the antithesis was, most of the time, a view
the person had already voiced or been told, the other party's demand as they
would put it, or prudence about HOW to do what they intend; a stricter sentence
in the app's focus moved "A new to the person" from 11 to 28 of 52 ratings on
Sonnet 5.5 and 11 to 43 on Opus 5.5, while Opus under the current ask moved
nothing. Its judges were Fable 5.2 subagents reading a hidden brief, which
nothing here can reproduce — so before any arm is drawn, this repo needs a
judge of its own that reads the person's WORDS alone, and that judge has to be
calibrated on the wheels the app already drew.

THE JUDGE (`_DepthVerdict`, one call per wheel, text-grounded)
==============================================================
Shown the person's words, T, A and A+; knows nothing else about them. Reads:
- `a_kind`, decided in order: not an opposition; a CAUTION about how to do T;
  the COUNTERPARTY'S DEMAND as the words report it; a view ALREADY VOICED in
  the words (a doubt, a concession, something they were told); a CARICATURE or
  MIRROR of T; else NEW — a position held for its own value that the words
  neither state nor report. The handoff's three unexcluded shapes are the
  three middle kinds, kept apart so an ablation of the exclusions can be read
  one at a time.
- `far_fetched`: A cannot be recognised as bearing on this matter from the
  words (the handoff's side condition: "no wheel in any arm was judged
  far-fetched").
- `a_plus_kind`: a good someone would choose for its own sake even if T cost
  nothing (OWN_GOOD), or a means to the person's aim / advice to them
  (MEANS_OR_ADVICE), or A restated.

ARM 1 — CALIBRATION, nothing drawn (`ANTITHESIS_DEPTH_APP_ROWS`)
================================================================
The app's `backend/cases/wow/r5/rows.jsonl`: 26 conversations × 4 arms (base
Sonnet 5.5, plain Opus 5.5, strict Sonnet 5.5, strict Opus 5.5), judged
`ANTITHESIS_DEPTH_REPLICATES` times each (default 2, so 52 reads an arm — the
same denominator as the handoff's two judges × 26). Reported beside the
handoff's own table: A new / already said (voiced + counterparty) / caution per
arm, A+ a good in its own right, far-fetched; and the judge's SELF-agreement
across replicates on `a_kind` and on new-against-not. The question this arm
answers is whether a words-only judge reproduces the GRADIENT the app's
brief-reading judges saw (base ≈ plain-opus << strict-sonnet < strict-opus).
It cannot reproduce their row-level verdicts: those were never persisted.
The judge model is the bench's judge (`E2EConfig.from_env().judge_model`,
override `ANTITHESIS_DEPTH_JUDGE`), not the app's.

    DIALEXITY_LLM_STREAM_HEADERS_TIMEOUT_S=15 \\
    ANTITHESIS_DEPTH_APP_ROWS=../alsotrue-app/backend/cases/wow/r5/rows.jsonl \\
      poetry run pytest tests/e2e/probe_antithesis_depth.py --real-llm -q -s -k calibration

Writes `results/antithesis_depth/calibration-<stamp>.json`; never overwrites.
The generation arms (the pre-registered rule × model 2×2 with the sentence
ablated by part) are added once this arm says the instrument transfers.
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import time
from pathlib import Path
from typing import Any, Literal, Optional

import pytest
from pydantic import BaseModel, Field

from e2e.probe_thesis_fit_judge import _fmt

pytestmark = [pytest.mark.llm]

_RESULTS = Path(__file__).resolve().parent / "results" / "antithesis_depth"
#: Six lost 151 of 208 calls to Bedrock on the first run (stream openings past
#: the 5s budget, 503s); three with a 15s opening budget is the working figure.
_CONCURRENCY = int(os.environ.get("ANTITHESIS_DEPTH_CONCURRENCY", "3") or 3)

#: The handoff's table for the same 26 conversations, 52 ratings an arm (two
#: blind judges), copied so the calibration prints beside it. `already` is the
#: handoff's one column; this judge splits it into voiced + counterparty.
HANDOFF_TABLE: dict[str, dict[str, int]] = {
    "base": {"new": 11, "already": 33, "caution": 6, "a_plus_own_good": 33},
    "plain-opus": {"new": 11, "already": 33, "caution": 8, "a_plus_own_good": 37},
    "strict-sonnet": {"new": 28, "already": 24, "caution": 0, "a_plus_own_good": 49},
    "strict-opus": {"new": 43, "already": 9, "caution": 0, "a_plus_own_good": 52},
}
ARMS = tuple(HANDOFF_TABLE)


class _DepthVerdict(BaseModel):
    a_kind: Literal[
        "caution",
        "counterparty_demand",
        "already_voiced",
        "obvious_counter",
        "caricature_or_mirror",
        "not_an_opposition",
        "new",
    ] = Field(
        description=(
            "Decide IN THIS ORDER and stop at the first that fits. NOT_AN_OPPOSITION: A "
            "does not oppose T (restates it, is unrelated, changes the subject). "
            "CAUTION: A is prudence about HOW to do what T intends — be careful, plan "
            "it, get it in writing, do it in steps, think it over, check first — not a "
            "position against T. COUNTERPARTY_DEMAND: A is what the other party in the "
            "matter wants, asks or argues, as the person's own words report or plainly "
            "imply it. ALREADY_VOICED: A is a view the person's own words already state "
            "or name — a doubt they raise, a concession they make, a worry they voice, "
            "an objection they report having been told. OBVIOUS_COUNTER: A is the other "
            "horn of the fork the person is already weighing, or the stock objection "
            "anyone in their position has already heard — not in the words, but plainly "
            "already met by them (the words answer it, or it is the first thing anyone "
            "would say to them). CARICATURE_OR_MIRROR: A is T's "
            "absence or degradation dressed as a stance, or T reversed with nothing of "
            "its own; nobody would hold it. NEW: a position someone would hold for its "
            "own value, against T, that the words neither state nor report, that the "
            "person has not plainly already met, and that is recognisable as true of "
            "this matter from the words."
        )
    )
    far_fetched: bool = Field(
        description=(
            "True when A cannot be recognised as bearing on THIS matter from the "
            "person's words — it needs facts the words do not give or contradict. "
            "Independent of a_kind: a NEW view can be far-fetched, a voiced one cannot."
        )
    )
    a_plus_kind: Literal["means_or_advice", "restates_a", "other", "own_good"] = Field(
        description=(
            "MEANS_OR_ADVICE: A+ is a way to do T well, a step the person should take, "
            "a safeguard on their aim, or advice addressed to them. RESTATES_A: A+ says "
            "what A says in other words. OWN_GOOD: A+ names a good that someone would "
            "choose for its own sake even if T cost nothing — the thing the person would "
            "lose by getting everything T wants. OTHER: none of these."
        )
    )
    reasoning: str = Field(
        description="Two sentences at most: which test decided a_kind, and which words."
    )


_JUDGE_SYSTEM = """You audit ONE dialectical tetrad against the words of the person it was drawn for.
You are shown the person's words, their position (T), the opposing view a writer drew for them (A), and the constructive side of that opposing view (A+). You know nothing about the person beyond the words shown; judge from the words alone, and quote the words when a kind depends on them.
Do not judge whether anything is wise, kind or correct. Judge only what A IS relative to the words — a view already in them, a caution about carrying T out, the other party's demand, a caricature, or a position the words do not contain — and what A+ is for: a good in its own right, or a means to the person's own aim."""


def _judge_model() -> str:
    from e2e.config import E2EConfig

    return os.environ.get("ANTITHESIS_DEPTH_JUDGE") or E2EConfig.from_env().judge_model


async def judge_depth(
    gate: asyncio.Semaphore, *, said: str, thesis: str, antithesis: str, a_plus: str
) -> dict[str, Any]:
    """One judge call. Fail-soft: a failed read is recorded, never dropped."""
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator

    prompt = (
        f"<words>\n{said.strip()}\n</words>\n\n"
        f'T (the person\'s position): "{thesis}"\n'
        f'A (the opposing view drawn): "{antithesis}"\n'
        f'A+ (the constructive side of A): "{a_plus}"\n\n'
        "Classify A and A+ against the words."
    )
    async with gate:
        try:
            conversation = ConversationFacilitator()
            conversation.set_system_prompt(_JUDGE_SYSTEM)
            verdict = await conversation.submit(_DepthVerdict, prompt)
        except Exception as exc:  # noqa: BLE001 — a probe records failure
            return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {
        "a_kind": verdict.a_kind,
        "far_fetched": bool(verdict.far_fetched),
        "a_plus_kind": verdict.a_plus_kind,
        "reasoning": verdict.reasoning[:500],
    }


def _app_rows(path: str) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return [r for r in rows if r.get("said") and r.get("arms")]


def _counts(reads: list[dict]) -> dict[str, int]:
    kinds = collections.Counter(r.get("a_kind") for r in reads if "error" not in r)
    return {
        "n": sum(1 for r in reads if "error" not in r),
        "errors": sum(1 for r in reads if "error" in r),
        "new": kinds["new"],
        "already": kinds["already_voiced"] + kinds["counterparty_demand"],
        "already_voiced": kinds["already_voiced"],
        "counterparty_demand": kinds["counterparty_demand"],
        "caution": kinds["caution"],
        "obvious_counter": kinds["obvious_counter"],
        "caricature_or_mirror": kinds["caricature_or_mirror"],
        "not_an_opposition": kinds["not_an_opposition"],
        "far_fetched": sum(1 for r in reads if r.get("far_fetched") is True),
        "a_plus_own_good": sum(1 for r in reads if r.get("a_plus_kind") == "own_good"),
        "a_plus_means_or_advice": sum(
            1 for r in reads if r.get("a_plus_kind") == "means_or_advice"
        ),
    }


def _self_agreement(per_item: list[list[dict]]) -> dict[str, Any]:
    """`per_item[i]` = the replicates' reads of item i."""
    pairs = [reads for reads in per_item if len(reads) >= 2 and all("error" not in r for r in reads)]
    exact = sum(1 for reads in pairs if len({r["a_kind"] for r in reads}) == 1)
    new_split = sum(
        1 for reads in pairs if len({r["a_kind"] == "new" for r in reads}) > 1
    )
    plus = sum(1 for reads in pairs if len({r["a_plus_kind"] for r in reads}) == 1)
    return {
        "items": len(pairs),
        "a_kind_unanimous": exact,
        "new_vs_not_split": new_split,
        "a_plus_kind_unanimous": plus,
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_calibration_on_the_apps_drawn_wheels(di_container) -> None:
    from e2e.modelctx import using_model

    path = os.environ.get("ANTITHESIS_DEPTH_APP_ROWS")
    if not path or not Path(path).exists():
        pytest.skip("ANTITHESIS_DEPTH_APP_ROWS not set or missing")
    replicates = int(os.environ.get("ANTITHESIS_DEPTH_REPLICATES", "2") or 2)
    rows = _app_rows(path)
    model = _judge_model()
    print(f"\n[antithesis-depth calibration] rows={len(rows)} arms={ARMS} replicates={replicates} judge={model}", flush=True)

    gate = asyncio.Semaphore(_CONCURRENCY)
    jobs: list[tuple[str, str, int]] = []
    coros = []
    for row in rows:
        for arm in ARMS:
            wheel = (row["arms"] or {}).get(arm)
            if not wheel:
                continue
            for rep in range(replicates):
                jobs.append((row["id"], arm, rep))
                coros.append(
                    judge_depth(
                        gate,
                        said=row["said"],
                        thesis=wheel.get("T", ""),
                        antithesis=wheel.get("A", ""),
                        a_plus=wheel.get("A+", ""),
                    )
                )
    t0 = time.time()
    with using_model(di_container, model):
        reads = await asyncio.gather(*coros)
    elapsed = time.time() - t0

    by_arm: dict[str, list[dict]] = collections.defaultdict(list)
    by_item: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    records = []
    for (case_id, arm, rep), read in zip(jobs, reads):
        by_arm[arm].append(read)
        by_item[(case_id, arm)].append(read)
        wheel = next(r for r in rows if r["id"] == case_id)["arms"][arm]
        records.append({"id": case_id, "arm": arm, "rep": rep, "T": wheel.get("T"), "A": wheel.get("A"), "A+": wheel.get("A+"), **read})

    print(f"  {len(reads)} judge calls in {elapsed:.0f}s\n", flush=True)
    header = f"  {'arm':14} {'reads':>5} | {'new':>12} {'already':>12} {'caution':>10} {'farfetch':>8} {'A+ own good':>12} | handoff new/already/caution/A+own"
    print(header)
    summary: dict[str, Any] = {}
    for arm in ARMS:
        c = _counts(by_arm[arm])
        h = HANDOFF_TABLE[arm]
        summary[arm] = c
        print(
            f"  {arm:14} {c['n']:>5} | {c['new']:>5}/{c['n']:<6} {c['already']:>5}/{c['n']:<6} {c['caution']:>4}/{c['n']:<5} {c['far_fetched']:>8} {c['a_plus_own_good']:>5}/{c['n']:<6} | "
            f"{h['new']}/{h['already']}/{h['caution']}/{h['a_plus_own_good']} of 52"
            f"   (voiced {c['already_voiced']}, counterparty {c['counterparty_demand']}, obvious {c['obvious_counter']}, caricature {c['caricature_or_mirror']}, not-opp {c['not_an_opposition']}, errors {c['errors']})",
            flush=True,
        )
    agreement = {
        arm: _self_agreement([by_item[(r["id"], arm)] for r in rows]) for arm in ARMS
    }
    all_items = [by_item[(r["id"], arm)] for r in rows for arm in ARMS]
    agreement["all"] = _self_agreement(all_items)
    a = agreement["all"]
    print(
        f"\n  self-agreement across {replicates} replicates, all arms: a_kind unanimous "
        f"{_fmt(a['a_kind_unanimous'], a['items'])}; new-vs-not split on {a['new_vs_not_split']}/{a['items']}; "
        f"A+ kind unanimous {_fmt(a['a_plus_kind_unanimous'], a['items'])}",
        flush=True,
    )
    print("\n  for the hand read — one line per (case, arm) where the replicates disagree on new-vs-not:")
    for (case_id, arm), item_reads in by_item.items():
        kinds = [r.get("a_kind") for r in item_reads if "error" not in r]
        if len(kinds) >= 2 and len({k == "new" for k in kinds}) > 1:
            wheel = next(r for r in rows if r["id"] == case_id)["arms"][arm]
            print(f"    {case_id} / {arm}: {kinds}  A={wheel.get('A')!r}")

    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"calibration-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps(
            {
                "judge_model": model,
                "replicates": replicates,
                "source": path,
                "elapsed_s": round(elapsed, 1),
                "handoff_table": HANDOFF_TABLE,
                "summary": summary,
                "self_agreement": agreement,
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\n  wrote {out}", flush=True)


# --- ARM 2: the pre-registered rule × model 2×2, the sentence ablated by part -----
#
# PRE-REGISTERED 2026-11-23, before any cell was drawn, after the calibration
# above said the words-only judge reproduces the app's gradient (base 18/38 and
# plain Opus 22/42 NEW against strict Sonnet 29/42 and strict Opus 36/39; a_kind
# self-agreement 68/73). The judge is LENIENT at the base against the app's
# brief-reading judges (47% new where they read 21%), so an Opus arm can sit
# near its ceiling; every figure is quoted with that.
#
# CASES: the 26 `WOW_R5_ROWS` as the app drew them — the conversation as
# `messages`, the stance QUOTED in the focus (`tetrad.focus_for(stance)`), T
# NOT pinned, best of three (the framework default), `Consultant(app_preamble=
# COUNSELOR_PERSONA)` — so the `control` cell on Sonnet 5.5 is the app's `base`
# wheel drawn again and `focus-deep` is its `strict-*` arm, replicated in this
# harness before any framework-side arm is read.
#
# ARMS (one request shape each; `ask-*` arms append to `_OPPOSING_POSITION_ASK`
# by monkeypatch, so they reach the view turn's request at the slot the mirror
# rule occupies — the position test the handoff's item 2 asks for):
#   control          the request as shipped
#   focus-deep       the app's sentence, first person, appended to the focus
#   ask-full         the whole sentence, third person, at the ask slot
#   ask-exclusions   the three exclusions only (caution / counterparty / own doubt)
#   ask-positive     the positive half only (the good lost; A+ a good in itself)
# MODELS: Sonnet 5.5 and Opus 5.5 on the app's transport (`ANTITHESIS_DEPTH_WRITER_MODELS`).
#
# PRIMARY READ: cards whose A the judge calls NEW, per cell (one judge read of
# the winner). An arm CLEARS on a model when its paired net gain over `control`
# on that model is >= +6 cards of 26 (the judge's own disagreement is 4 of 73
# on new-vs-not, so a net of 6 is above two sigmas of that).
# SIDE CONDITIONS (must not fall): coherence pass (`_judge`, CC >= 0.7 both
# statements) down by no more than 3 cards; antithesis a POSITION
# (`_audit_kind`) down by no more than 3; far-fetched up by no more than 2;
# drawn cards down by no more than 2.
# SECONDARY (read, not gated): A+ own good, caution, already voiced,
# counterparty demand, seconds a card. One run a cell; a bar within 2 of its
# line gets a second replicate before anything is decided.
#
# WHERE THE RULE LIVES, decided by which arm clears: `ask-exclusions` alone →
# `_OPPOSING_POSITION_ASK` (all three sites; the ladder site re-measured on
# documents); `ask-positive` → `TETRAD_BUILD_PROCEDURE` step 1 /
# `PLUS_RESTATEMENT_CHECK`, gated on `probe_decided_stance.py`; `focus-deep`
# clearing where `ask-full` does not → the request's STRUCTURE, not its words.
#
# AMENDMENT, 2026-11-23 20:20, after stage 1 (control + focus-deep, both models)
# was drawn and BEFORE any ask arm: the hand read of the 104 stage-1 cards found
# the words-only judge counting the OBVIOUS counter as NEW — "Keep the steady
# bank income and craft" for a person whose words say they saved nine months of
# runway, "Stay in Vilnius" on a Zurich-or-Vilnius fork, "Our choices are really
# ours to author" on free will — which is why control read 16–17/26 new here
# where the app's dialectician read 7 of 52 wheels as new to the person. The
# judge gains one kind, OBVIOUS_COUNTER (the other horn of the fork already
# weighed, or the stock objection anyone in that position has heard), decided
# after ALREADY_VOICED and before CARICATURE, and NEW now excludes it. The
# correction cuts AGAINST the arms' chance of clearing on the lenient read and
# for it on the strict one, so both reads are reported for stage 1: the
# pre-registered one (above, kept as `new + obvious_counter`) and the amended
# one (`new`), and stage 2 is decided on the amended one. The judge is
# re-calibrated on the app's 104 wheels and the stage-1 draws are RE-READ, not
# redrawn (`test_rejudge_the_cells`).
#
#     DIALEXITY_LLM_STREAM_HEADERS_TIMEOUT_S=15 \
#     ANTITHESIS_DEPTH_WRITER_MODELS=bedrock/global.anthropic.claude-sonnet-5-5,bedrock/global.anthropic.claude-opus-5-5 \
#     ANTITHESIS_DEPTH_ARMS=control,focus-deep \
#       poetry run pytest tests/e2e/probe_antithesis_depth.py --real-llm -q -s -k arms
#     poetry run pytest tests/e2e/probe_antithesis_depth.py -q -s -k summary   # reads the cell files, no LLM

#: The app's sentence, verbatim (`alsotrue/tetrad.py::DEEP`), first person,
#: appended to the focus.
APP_DEEP = (
    ". The opposing view must be one I have NOT already voiced and have not "
    "already been told: never a caution about how to do what I intend (be "
    "careful, plan it, get it in writing, do it in steps), never the other "
    "party's demand as they would put it, never a doubt I named myself. Find the "
    "opposition that makes this matter hard underneath what I said: the view "
    "whose good I would lose by getting everything I want. Its constructive side "
    "is a good someone would choose for its own sake even if my position cost "
    "nothing — never a means to my aim, never advice to me. It has to be "
    "recognisable as true of my matter from my own words, not far-fetched"
)

#: The three exclusions, third person: SHIPPED as `view_sketch.OPPOSITION_NOT_ALREADY_HELD`
#: on 2026-11-23 (the `focus-exclusions` arm below is the shipped request; every
#: other arm turns the shipped rule OFF by monkeypatch so `control` stays the
#: request as it was before this change). Imported, not copied, so the arm and
#: the product cannot drift apart.
from dialectical_framework.concerns.view_sketch import \
    OPPOSITION_NOT_ALREADY_HELD as ASK_EXCLUSIONS  # noqa: E402

#: The positive half, third person: what A is and what its plus is.
ASK_POSITIVE = (
    "Find the opposition that makes this matter hard underneath what was said: "
    "the view whose good the person would lose by getting everything the thesis "
    "wants. Its constructive side is a good someone would choose for its own "
    "sake even if the thesis cost nothing — never a means to the person's aim, "
    "never advice to them."
)

ASK_FULL = (
    ASK_EXCLUSIONS
    + " "
    + ASK_POSITIVE
    + " It has to be recognisable as true of the matter from the person's own "
    "words, not far-fetched."
)

#: arm -> (appended to the FOCUS line, appended to the ASK slot). Stage 3 arms
#: (2026-11-23 21:10, pre-registered after stage 2 read: the whole sentence at
#: the ask slot +3 / exclusions +4 on Opus against the app's focus sentence +7,
#: nothing at the ask slot on Sonnet): the third-person texts at the FOCUS
#: position, so position is read apart from voice — `focus-deep` differs from
#: `ask-full` in both. Same primary, same bar, same side conditions.
ARM_SPEC: dict[str, tuple[Optional[str], Optional[str]]] = {
    "control": (None, None),
    "focus-deep": (APP_DEEP, None),
    "ask-full": (None, ASK_FULL),
    "ask-exclusions": (None, ASK_EXCLUSIONS),
    "ask-positive": (None, ASK_POSITIVE),
    "focus-full": (". " + ASK_FULL, None),
    "focus-exclusions": (None, None),  # the shipped request: the rule rides on the focus line itself
}
#: Arms drawn with the shipped focus-line rule ON; every other arm patches it to "".
ARMS_WITH_SHIPPED_RULE = frozenset({"focus-exclusions"})
ARM_ASK_EXTENSION: dict[str, Optional[str]] = {arm: ask for arm, (_, ask) in ARM_SPEC.items()}
GENERATION_ARMS = tuple(ARM_SPEC)
#: `ANTITHESIS_DEPTH_TAG=@r2` labels a REPLICATE run's cells (`control@r2`); the
#: summary pairs a tagged arm against the control with the same tag.
_TAG = os.environ.get("ANTITHESIS_DEPTH_TAG", "")
_CARDS_IN_FLIGHT = int(os.environ.get("ANTITHESIS_DEPTH_CARDS_IN_FLIGHT", "2") or 2)


def app_focus(stance: str, arm: str) -> str:
    """`alsotrue/tetrad.py::focus_for(stance)` byte for byte, no reader."""
    focus = (
        f"the perspective for the position I hold — «{stance}» — what it stands "
        "against, and above all the constructive side of that opposing view that "
        "I am not seeing"
    )
    return focus + (ARM_SPEC[arm.split("@")[0]][0] or "")


def _pole_texts(view) -> dict[str, Optional[str]]:
    poles = ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")
    return {
        name: (pole.text if pole else None)
        for name, pole in zip(poles, (view.t, view.a, view.t_plus, view.t_minus, view.a_plus, view.a_minus))
    }


async def _draw_card(container, model: str, row, arm: str, gate: asyncio.Semaphore) -> dict:
    from e2e.modelctx import using_model

    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant

    messages = [{"role": role, "content": content} for role, content in row.messages]
    record: dict[str, Any] = {"id": row.id, "arm": arm, "model": model, "said": row.said}
    async with gate:
        started = time.perf_counter()
        try:
            head = Consultant(app_preamble=COUNSELOR_PERSONA, messages=messages)
            with using_model(container, model):
                view = await head.exploration_view(focus=app_focus(row.stance, arm))
        except Exception as exc:  # noqa: BLE001 — a probe records failure
            record.update(error=f"{type(exc).__name__}: {str(exc)[:200]}", seconds=round(time.perf_counter() - started, 1))
            return record
    record["seconds"] = round(time.perf_counter() - started, 1)
    first = view.perspectives[0] if view.perspectives else None
    record["drawn"] = first is not None
    record["failed_draws"] = [f.kind for f in view.failed_draws]
    if first is not None:
        record.update(_pole_texts(first))
        record["spares"] = [_pole_texts(r) for r in view.runners_up]
    return record


async def _read_card(container, judge: str, record: dict, gate: asyncio.Semaphore) -> None:
    """The three reads on one drawn card, all under the judge model."""
    from e2e.modelctx import using_model
    from e2e.probe_aspect_variants import _judge
    from e2e.probe_tetrad_quality import _audit_kind

    if not record.get("drawn") or not all(
        record.get(k) for k in ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")
    ):
        return
    with using_model(container, judge):
        depth = await judge_depth(
            gate,
            said=record["said"],
            thesis=record["thesis"],
            antithesis=record["antithesis"],
            a_plus=record["a_plus"],
        )
        if "error" in depth:  # one re-ask: Bedrock dropped 23% of the calibration's calls
            depth = await judge_depth(gate, said=record["said"], thesis=record["thesis"], antithesis=record["antithesis"], a_plus=record["a_plus"])
        record["depth"] = depth
        async with gate:
            try:
                record.update(await _judge({k: record[k] for k in ("t_plus", "t_minus", "a_plus", "a_minus")}))
            except Exception as exc:  # noqa: BLE001
                record["cc_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            record.update(await _audit_kind(container, judge, record["thesis"], record["antithesis"]))


def _short(model: str) -> str:
    return model.rsplit("/", 1)[-1].replace("global.anthropic.", "")


def _cell_counts(records: list[dict]) -> dict[str, Any]:
    drawn = [r for r in records if r.get("drawn")]
    read = [r for r in drawn if r.get("depth") and "error" not in r["depth"]]
    kinds = collections.Counter(r["depth"]["a_kind"] for r in read)
    return {
        "cards": len(records),
        "errors": sum(1 for r in records if r.get("error")),
        "drawn": len(drawn),
        "read": len(read),
        "new": kinds["new"],
        "already_voiced": kinds["already_voiced"],
        "counterparty_demand": kinds["counterparty_demand"],
        "caution": kinds["caution"],
        "obvious_counter": kinds["obvious_counter"],
        "caricature_or_mirror": kinds["caricature_or_mirror"],
        "not_an_opposition": kinds["not_an_opposition"],
        "far_fetched": sum(1 for r in read if r["depth"].get("far_fetched")),
        "a_plus_own_good": sum(1 for r in read if r["depth"].get("a_plus_kind") == "own_good"),
        "cc_pass": sum(1 for r in drawn if r.get("pass")),
        "cc_judged": sum(1 for r in drawn if "pass" in r),
        "a_position": sum(1 for r in drawn if r.get("a_kind") == "position"),
        "a_kind_judged": sum(1 for r in drawn if r.get("a_kind")),
        "median_seconds": sorted(r["seconds"] for r in drawn)[len(drawn) // 2] if drawn else None,
    }


def _paired(control: list[dict], arm: list[dict], key) -> tuple[int, int, int]:
    """(arm only, control only, both) on `key(record) -> bool`, by case id."""
    c = {r["id"]: key(r) for r in control}
    a = {r["id"]: key(r) for r in arm}
    both = sum(1 for i in a if i in c and a[i] and c[i])
    arm_only = sum(1 for i in a if i in c and a[i] and not c[i])
    control_only = sum(1 for i in a if i in c and c[i] and not a[i])
    return arm_only, control_only, both


def _is_new(r: dict) -> bool:
    return bool(r.get("depth")) and r["depth"].get("a_kind") == "new"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_arms_rule_by_model(di_container) -> None:
    from e2e.promise_cases import WOW_R5_ROWS

    from dialectical_framework.concerns import view_sketch

    models = [m for m in (os.environ.get("ANTITHESIS_DEPTH_WRITER_MODELS") or "").split(",") if m.strip()]
    if not models:
        pytest.skip("ANTITHESIS_DEPTH_WRITER_MODELS not set (comma-separated writer model ids)")
    arms = [a for a in (os.environ.get("ANTITHESIS_DEPTH_ARMS") or ",".join(GENERATION_ARMS)).split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARM_SPEC]
    assert not unknown, f"unknown arms {unknown}; known {GENERATION_ARMS}"
    judge = _judge_model()
    rows = list(WOW_R5_ROWS)
    limit = int(os.environ.get("ANTITHESIS_DEPTH_CASES", "0") or 0)
    if limit:
        rows = rows[:limit]
    _RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    print(f"\n[antithesis-depth arms] cases={len(rows)} arms={arms} models={[_short(m) for m in models]} judge={_short(judge)} cards_in_flight={_CARDS_IN_FLIGHT}", flush=True)

    shipped_ask = view_sketch._OPPOSING_POSITION_ASK
    shipped_rule = view_sketch.OPPOSITION_NOT_ALREADY_HELD
    draw_gate = asyncio.Semaphore(_CARDS_IN_FLIGHT)
    judge_gate = asyncio.Semaphore(3)
    for arm in arms:  # arms run one at a time: the ask slot is module state
        extension = ARM_ASK_EXTENSION[arm]
        label = arm + _TAG
        try:
            if extension:
                view_sketch._OPPOSING_POSITION_ASK = shipped_ask + "\n\n" + extension
            if arm not in ARMS_WITH_SHIPPED_RULE:
                view_sketch.OPPOSITION_NOT_ALREADY_HELD = ""
            for model in models:
                t0 = time.time()
                records = await asyncio.gather(*(_draw_card(di_container, model, row, label, draw_gate) for row in rows))
                await asyncio.gather(*(_read_card(di_container, judge, r, judge_gate) for r in records))
                counts = _cell_counts(records)
                out = _RESULTS / f"cell-{_short(model)}-{label}-{stamp}.json"
                out.write_text(json.dumps({"model": model, "arm": label, "judge": judge, "ask_extension": extension, "elapsed_s": round(time.time() - t0, 1), "counts": counts, "records": records}, indent=2, ensure_ascii=False))
                print(
                    f"  {_short(model):22} {label:18} drawn {counts['drawn']}/{counts['cards']} (errors {counts['errors']}) | "
                    f"new {counts['new']}/{counts['read']} voiced {counts['already_voiced']} counterparty {counts['counterparty_demand']} obvious {counts['obvious_counter']} caution {counts['caution']} farfetch {counts['far_fetched']} | "
                    f"A+ own good {counts['a_plus_own_good']}/{counts['read']} | CC pass {counts['cc_pass']}/{counts['cc_judged']} | A position {counts['a_position']}/{counts['a_kind_judged']} | "
                    f"median {counts['median_seconds']}s | {out.name}",
                    flush=True,
                )
        finally:
            view_sketch._OPPOSING_POSITION_ASK = shipped_ask
            view_sketch.OPPOSITION_NOT_ALREADY_HELD = shipped_rule
    assert view_sketch._OPPOSING_POSITION_ASK == shipped_ask
    assert view_sketch.OPPOSITION_NOT_ALREADY_HELD == shipped_rule


def _latest_cells() -> dict[tuple[str, str], dict]:
    cells: dict[tuple[str, str], dict] = {}
    for path in sorted(_RESULTS.glob("cell-*.json")):
        data = json.loads(path.read_text())
        data["_file"] = path.name
        cells[(data["model"], data["arm"])] = data  # newest file wins
    return cells


def test_summary_of_the_cells() -> None:
    """No LLM: the latest cell per (model, arm), paired against that model's control."""
    cells = _latest_cells()
    if not cells:
        pytest.skip("no cell files yet")
    print()
    for model in sorted({m for m, _ in cells}):
        print(f"== {_short(model)}")
        print(f"  {'arm':18} {'drawn':>6} {'new':>7} {'paired +/-':>11} {'voiced':>6} {'cparty':>6} {'obvious':>7} {'caution':>7} {'farfetch':>8} {'A+own':>7} {'CC':>7} {'A pos':>7} {'median s':>8}")
        present = [a for _, a in cells if _ == model]
        order = sorted(present, key=lambda a: (a.split("@")[1] if "@" in a else "", GENERATION_ARMS.index(a.split("@")[0])))
        for arm in order:
            cell = cells[(model, arm)]
            tag = "@" + arm.split("@")[1] if "@" in arm else ""
            control = cells.get((model, "control" + tag))
            c = cell["counts"]
            pair = ""
            if control and not arm.startswith("control"):
                up, down, _ = _paired(control["records"], cell["records"], _is_new)
                net = up - down
                pair = f"+{up}/-{down} ={net:+d}" + (" CLEARS" if net >= 6 else "")
            print(
                f"  {arm:18} {c['drawn']:>3}/{c['cards']:<2} {c['new']:>3}/{c['read']:<3} {pair:>11} {c['already_voiced']:>6} {c['counterparty_demand']:>6} {c['obvious_counter']:>7} {c['caution']:>7} {c['far_fetched']:>8} "
                f"{c['a_plus_own_good']:>3}/{c['read']:<3} {c['cc_pass']:>3}/{c['cc_judged']:<3} {c['a_position']:>3}/{c['a_kind_judged']:<3} {str(c['median_seconds']):>8}"
            )
        print()


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_rejudge_the_cells(di_container) -> None:
    """Re-read `depth` on the latest cell per (model, arm) with the CURRENT judge
    — nothing redrawn, CC and the kind auditor kept — and write a new cell file
    (the summary reads the newest). For a judge amendment after a stage."""
    from e2e.modelctx import using_model

    if not os.environ.get("ANTITHESIS_DEPTH_REJUDGE"):
        pytest.skip("ANTITHESIS_DEPTH_REJUDGE not set")
    judge = _judge_model()
    gate = asyncio.Semaphore(_CONCURRENCY)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for (model, arm), cell in _latest_cells().items():
        records = cell["records"]
        drawn = [r for r in records if r.get("drawn") and all(r.get(k) for k in ("thesis", "antithesis", "a_plus"))]
        with using_model(di_container, judge):
            reads = await asyncio.gather(*(judge_depth(gate, said=r["said"], thesis=r["thesis"], antithesis=r["antithesis"], a_plus=r["a_plus"]) for r in drawn))
        for r, read in zip(drawn, reads):
            r["depth_before"] = r.get("depth")
            r["depth"] = read
        counts = _cell_counts(records)
        out = _RESULTS / f"cell-{_short(model)}-{arm}-{stamp}.json"
        out.write_text(json.dumps({**{k: v for k, v in cell.items() if k != "_file"}, "judge": judge, "rejudged_from": cell["_file"], "counts": counts, "records": records}, indent=2, ensure_ascii=False))
        print(f"  rejudged {_short(model):22} {arm:15} new {counts['new']}/{counts['read']} obvious {counts['obvious_counter']} voiced {counts['already_voiced']} counterparty {counts['counterparty_demand']} caution {counts['caution']} -> {out.name}", flush=True)
