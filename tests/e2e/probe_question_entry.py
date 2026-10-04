"""Does the view turn find a STANCE in a QUESTION? — the intake-gate probe.

The pre-MVP (`examples/blindspots.ipynb`) takes whatever the person types and
asks the Consultant's view turn for the tetrad around it. The 40 bench
utterances are 36 statements and 4 questions, and on the 4 the turn drew a
coherent tetrad every time — by picking the option the question NAMED ("Should
I move to Berlin?" → "Take the Berlin job"). Whether that is the person's lean
or a guess is what an intake gate would exist to decide, so before writing one:
20 questions, pre-registered by what they CARRY, drawn exactly the way the
pre-MVP draws (`Consultant(app_preamble=COUNSELOR_PERSONA)`,
`exploration_view(focus=FOCUS)`, best-of-3), then three reads per draw:

- the pipeline's own coherence judge (`_judge`, comparable with the archive),
- the antithesis-kind auditor (`_audit_kind`, same),
- a NEW stance auditor: how does the drawn thesis relate to the question —
  the lean the question carried, an option it named (a guess the person can
  `misread`), a stance it neither carried nor named (imputed), or not a
  stance at all — and is it the asker's own position or a claim about others.

Pre-registered expectations per category (the gate's job is the gap):
  leaning   → `carried_lean`; a drawn tetrad is right.
  neutral   → `option_named` is the best the turn can do; this is where the
              gate's "which way are you leaning?" belongs.
  complaint → the asker's own stance, not a claim about the other party.
  none      → nothing drawn, or `not_a_stance`; a confident tetrad here is
              the failure (an imputed position shown as the person's own).
  belief    → `carried_lean` (the belief is the stance).

    poetry run pytest tests/e2e/probe_question_entry.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import time
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.probe_aspect_variants import _judge
from e2e.probe_tetrad_quality import _audit_kind, _wilson
from e2e.probe_view_turn_ask import FOCUS

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"

#: (question, category) — category pre-registered BEFORE any draw.
QUESTIONS: list[tuple[str, str]] = [
    # leaning: the wording carries which way the person leans
    ("Is it crazy to turn down a promotion because I don't want to manage people?", "leaning"),
    ("Why should I keep paying for my adult son's phone when he never calls?", "leaning"),
    ("Isn't it time we stopped doing daily standups?", "leaning"),
    ("How do I tell my co-founder I want to leave without blowing up the company?", "leaning"),
    ("Am I wrong to want my mother to move in with us?", "leaning"),
    ("Why do I keep hiring people who are just like me?", "leaning"),
    # neutral: a fork with no lean in the wording
    ("Should I take the Zurich offer or stay in Vilnius?", "neutral"),
    ("Should we build this in-house or buy it?", "neutral"),
    ("Do I tell my sister that her husband is cheating?", "neutral"),
    ("Should I go back to university at forty?", "neutral"),
    ("Rent or buy, in this market?", "neutral"),
    # complaint: a "why" about someone else / the system
    ("Why does my manager take credit for everything I do?", "complaint"),
    ("Why do our customers churn after the first month?", "complaint"),
    ("Why won't my daughter talk to me anymore?", "complaint"),
    # none: informational, no stance to find
    ("What's the best way to learn Spanish in six months?", "none"),
    ("How much runway should a seed-stage startup keep?", "none"),
    ("What should I cook for twelve people on Saturday?", "none"),
    ("What is dialectical thinking?", "none"),
    # belief: "is it normal / does anyone" — the belief is the stance
    ("Is it normal to feel nothing when your startup gets acquired?", "belief"),
    ("Does anyone actually enjoy networking events?", "belief"),
]


class _StanceVerdict(BaseModel):
    relation: Literal["carried_lean", "option_named", "imputed", "not_a_stance"] = Field(
        description=(
            "CARRIED_LEAN: the question's own wording signals which way the asker "
            "leans (a rhetorical 'isn't it time', 'am I wrong to want', 'why should I "
            "keep', a 'how do I' that presupposes the intent) and the thesis is that "
            "lean. OPTION_NAMED: the question is genuinely open between alternatives "
            "and the thesis is one of the alternatives the question itself names — a "
            "reasonable guess, not something the asker said. IMPUTED: the thesis is a "
            "position the question neither leans toward nor names — supplied by the "
            "writer. NOT_A_STANCE: the thesis restates the question, describes a "
            "situation, or is informational — nobody is taking a position in it."
        )
    )
    askers_own: bool = Field(
        description=(
            "True when the thesis is a position the ASKER holds or would act on "
            "(first-person stance, even if phrased impersonally). False when it is a "
            "claim about another party or the world that the asker merely observes "
            "('my manager takes credit', 'customers churn')."
        )
    )
    reasoning: str = Field(description="One or two sentences: which test decided it.")


_STANCE_SYSTEM = """You audit ONE thesis against the QUESTION it was distilled from.
The thesis was written by a system that must find the asker's POSITION inside what they typed. Judge only the relation between the question's wording and the thesis: did the wording carry that lean, did it merely name that option, was it supplied, or is it not a position at all. Then say whether the thesis is the asker's own stance or a claim about someone else. Do not judge whether the thesis is wise."""


async def _audit_stance(container, judge_model: str, question: str, thesis: str) -> dict:
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_STANCE_SYSTEM)
        with using_model(container, judge_model):
            verdict = await conversation.submit(
                _StanceVerdict,
                f'Question: "{question}"\nThesis: "{thesis}"\n\nClassify the relation.',
            )
        return {
            "stance": verdict.relation,
            "askers_own": bool(verdict.askers_own),
            "stance_reasoning": verdict.reasoning,
        }
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        return {"stance": None, "stance_error": repr(exc)}


def _fmt(k: int, n: int) -> str:
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)"


async def _draw(text: str, category: str, attempts: int) -> dict:
    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant

    head = Consultant(
        app_preamble=COUNSELOR_PERSONA, messages=[{"role": "user", "content": text}]
    )
    started = time.perf_counter()
    row = {"utterance": text, "category": category}
    try:
        view = await head.exploration_view(focus=FOCUS, attempts=attempts)
    except Exception as exc:  # noqa: BLE001
        row.update(error=repr(exc), seconds=round(time.perf_counter() - started, 1))
        return row
    first = view.perspectives[0] if view.perspectives else None
    row.update(seconds=round(time.perf_counter() - started, 1), drawn=first is not None)
    if first is not None:
        for name, pole in (
            ("thesis", first.t), ("antithesis", first.a), ("t_plus", first.t_plus),
            ("t_minus", first.t_minus), ("a_plus", first.a_plus), ("a_minus", first.a_minus),
        ):
            row[name] = pole.text if pole else None
        row["intent"] = first.intent
    return row


_POLES = ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_questions_through_the_view_turn(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    # The pre-MVP draws best-of-3 (`DEFAULT_SKETCH_ATTEMPTS`); same here unless told otherwise.
    attempts = int(os.environ.get("VIEW_TURN_ATTEMPTS", "3") or 3)
    out = _RESULTS / f"question_entry-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"\n=== {len(QUESTIONS)} questions through the view turn, attempts={attempts} → {out}", flush=True)

    rows: list[dict] = []
    batch = max(1, 10 // attempts)
    for start in range(0, len(QUESTIONS), batch):
        rows += await asyncio.gather(
            *(_draw(q, c, attempts) for q, c in QUESTIONS[start : start + batch])
        )
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"  drawn {len(rows)}/{len(QUESTIONS)}", flush=True)

    complete = [r for r in rows if all(r.get(k) for k in _POLES)]
    verdicts = await asyncio.gather(*(_judge(r) for r in complete))
    for row, verdict in zip(complete, verdicts):
        row.update(verdict)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    # Auditors run under `using_model`, which re-points the container: one at a time.
    with_thesis = [r for r in rows if r.get("thesis")]
    for index, row in enumerate(with_thesis, 1):
        row.update(await _audit_stance(di_container, judge, row["utterance"], row["thesis"]))
        if row.get("antithesis"):
            row.update(await _audit_kind(di_container, judge, row["thesis"], row["antithesis"]))
        print(
            f"  [{index}/{len(with_thesis)}] {row['category']:9} {row.get('stance')!s:13} "
            f"own={row.get('askers_own')!s:5} {row.get('a_kind')!s:9} "
            f"{'PASS' if row.get('pass') else 'fail'}  «{row['thesis']}» vs «{row.get('antithesis')}»",
            flush=True,
        )
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    print("\n--- questions through the view turn ---")
    print(f"  drawn complete  {len(complete)}/{len(QUESTIONS)}; nothing drawn {sum(1 for r in rows if r.get('drawn') is False)}; errors {sum(1 for r in rows if r.get('error'))}")
    print(f"  CC pass         {_fmt(sum(bool(r.get('pass')) for r in complete), len(complete))}   (statements, best-of-3: 36/40)")
    kinds = collections.Counter(r.get("a_kind") for r in complete)
    print(f"  A kind          {dict(kinds)}   position {_fmt(kinds.get('position', 0), len(complete))}   (statements: 36/40)")
    print(f"  stance          {dict(collections.Counter(r.get('stance') for r in with_thesis))}")
    print(f"  asker's own     {_fmt(sum(bool(r.get('askers_own')) for r in with_thesis), len(with_thesis))}")
    print("  per category (drawn / stance kinds / own):")
    for cat in ("leaning", "neutral", "complaint", "none", "belief"):
        group = [r for r in rows if r["category"] == cat]
        drawn = [r for r in group if r.get("thesis")]
        stance = dict(collections.Counter(r.get("stance") for r in drawn))
        own = sum(bool(r.get("askers_own")) for r in drawn)
        cc = sum(bool(r.get("pass")) for r in drawn)
        print(f"    {cat:9} drawn {len(drawn)}/{len(group)}  CC {cc}/{len(drawn)}  {stance}  own {own}/{len(drawn)}")
    print(f"  latency median  {sorted(r['seconds'] for r in rows if 'seconds' in r)[len(rows)//2]}s")
