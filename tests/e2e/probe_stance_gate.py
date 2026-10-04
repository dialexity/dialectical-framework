"""The intake gate on the 20 questions — does it fire where it should?

`probe_question_entry.py` measured the WRITER on questions; this measures the
GATE (`concerns/stance_capture.py::StanceCapture`) on the same 20, against the
categories pre-registered there. Expected shape per category:

  leaning / belief / complaint → stance   (the words carry a position)
  neutral                      → fork     (one question, then the lean)
  none                         → none     (what to type instead)

Three reads: shape agreement with the category; for a captured stance, the
same stance auditor the writer probe used (`_audit_stance`: is the stance the
lean the words carried, an option, imputed, or not a stance); and the LOOP —
every fork and none gets a pre-registered scripted answer as the person's
reply, and the second pass must return a stance that matches that answer
(judged by one small call). Every item persisted.

    poetry run pytest tests/e2e/probe_stance_gate.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import collections
import json
import time
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.stance_capture import StanceCapture
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.probe_question_entry import QUESTIONS, _audit_stance

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"

EXPECTED = {"leaning": "stance", "belief": "stance", "complaint": "stance", "neutral": "fork", "none": "none"}

#: The person's scripted reply to the gate's question, pre-registered per
#: question that should draw one. Forks answer with a lean; two of the four
#: informational questions answer with a position, two with more information
#: (the gate should ask once more, and the host's cap then builds free-form).
ANSWERS = {
    "Should I take the Zurich offer or stay in Vilnius?": "Vilnius, if I'm honest — but I feel I'd regret it.",
    "Should we build this in-house or buy it?": "Build. I don't trust vendors with our core.",
    "Do I tell my sister that her husband is cheating?": "I think I have to tell her.",
    "Should I go back to university at forty?": "I want to go back.",
    "Rent or buy, in this market?": "Buy. Renting feels like throwing money away.",
    "What's the best way to learn Spanish in six months?": "I'm going to move to Madrid for the summer and just speak.",
    "How much runway should a seed-stage startup keep?": "We have 14 months and I want to spend faster.",
    "What should I cook for twelve people on Saturday?": "Something impressive, I always cook everything myself.",
    "What is dialectical thinking?": "I just wanted to know what it is.",
}


class _MatchVerdict(BaseModel):
    matches: Literal["yes", "no"] = Field(
        description="YES: the stance is the position the person's reply took (same side, their meaning). NO: a different side, or a position the reply did not take."
    )
    reasoning: str = Field(description="One sentence.")


_MATCH_SYSTEM = "You check whether a one-line stance is the position a person took in their reply. Judge the side and the meaning only, not the wording."


async def _audit_match(container, judge_model: str, reply: str, stance: str) -> dict:
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_MATCH_SYSTEM)
        with using_model(container, judge_model):
            verdict = await conversation.submit(
                _MatchVerdict, f'Reply: "{reply}"\nStance: "{stance}"\n\nDoes the stance match the reply?'
            )
        return {"second_matches": verdict.matches == "yes", "second_match_reasoning": verdict.reasoning}
    except Exception as exc:  # noqa: BLE001
        return {"second_matches": None, "second_match_error": repr(exc)}


async def _gate(question: str, category: str) -> dict:
    row = {"utterance": question, "category": category, "expected": EXPECTED[category]}
    started = time.perf_counter()
    try:
        first = await StanceCapture().resolve([question])
    except Exception as exc:  # noqa: BLE001
        row.update(error=repr(exc))
        return row
    row.update(shape=first.shape, stance=first.stance, ask=first.ask, seconds=round(time.perf_counter() - started, 1))
    row["agrees"] = first.shape == EXPECTED[category]
    reply = ANSWERS.get(question)
    if first.ask and reply:
        try:
            second = await StanceCapture().resolve([question, reply])
            row.update(reply=reply, second_shape=second.shape, second_stance=second.stance, second_ask=second.ask)
        except Exception as exc:  # noqa: BLE001
            row.update(reply=reply, second_error=repr(exc))
    return row


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_gate_on_the_twenty_questions(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    out = _RESULTS / f"stance_gate-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"\n=== the gate on {len(QUESTIONS)} questions → {out}", flush=True)

    rows: list[dict] = []
    for start in range(0, len(QUESTIONS), 10):
        rows += await asyncio.gather(*(_gate(q, c) for q, c in QUESTIONS[start : start + 10]))
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    # Auditors under `using_model`: one at a time.
    for index, row in enumerate(rows, 1):
        if row.get("stance"):
            verdict = await _audit_stance(di_container, judge, row["utterance"], row["stance"])
            row.update(stance_relation=verdict.get("stance"), stance_reasoning=verdict.get("stance_reasoning"))
        if row.get("second_stance") and row.get("reply"):
            row.update(await _audit_match(di_container, judge, row["reply"], row["second_stance"]))
        line = f"  [{index}/{len(rows)}] {row['category']:9} {row.get('shape')!s:6} {'ok ' if row.get('agrees') else 'MISS'}"
        if row.get("stance"):
            line += f"  {row.get('stance_relation')!s:13} «{row['stance']}»"
        else:
            line += f"  ask «{row.get('ask')}»"
        if row.get("reply"):
            line += f"\n        reply «{row['reply']}» → {row.get('second_shape')} «{row.get('second_stance') or row.get('second_ask')}» match={row.get('second_matches')}"
        print(line, flush=True)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    print("\n--- the gate on the twenty ---")
    print(f"  shape agrees with category  {sum(bool(r.get('agrees')) for r in rows)}/{len(rows)}; errors {sum(1 for r in rows if r.get('error'))}")
    for cat in ("leaning", "belief", "complaint", "neutral", "none"):
        group = [r for r in rows if r["category"] == cat]
        print(f"    {cat:9} expected {EXPECTED[cat]:6} got {dict(collections.Counter(r.get('shape') for r in group))}")
    with_stance = [r for r in rows if r.get("stance")]
    print(f"  asked a question            {sum(1 for r in rows if r.get('ask'))}/{len(rows)}")
    print(f"  captured stance read as     {dict(collections.Counter(r.get('stance_relation') for r in with_stance))}")
    looped = [r for r in rows if r.get("reply")]
    print(f"  second pass: stance found   {sum(1 for r in looped if r.get('second_stance'))}/{len(looped)}; matches the reply {sum(1 for r in looped if r.get('second_matches'))}/{sum(1 for r in looped if r.get('second_stance'))}")
    print(f"  latency median              {sorted(r['seconds'] for r in rows if 'seconds' in r)[len(rows)//2]}s (first pass)")
