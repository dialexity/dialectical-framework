"""The theory-in-prompt arm: one call derives Ac+/Re+/Ac-/Re-/S+/S- from the six
corners by the framework's own rule, then writes the pill — against the machinery.

Owner's question (2026-10-05): "if T-→A+ and A-→T+ give S+, and T+→A- and
A+→T- give S-, a prompt that knows that produces the same without machinery —
so why the framework?" This arm is that prompt, on the same 17 tetrads as
`probe_wisdom_machinery.py`, 5 s a call. Side by side: S+/S- from the wheel
(`GenerateSynthesis`, ~88 s) vs S+/S- from the one call; and a blind pairwise
judge on S- only (the line the corner pill could not say), order randomised
and persisted. Parity here is expected and would be a finding about WHERE the
machinery's leverage is (N ≥ 2, checks, memory), not a verdict against it.

    poetry run pytest tests/e2e/probe_wisdom_theory_prompt.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.probe_wisdom_line import _prompt as _corner_prompt

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_MACHINERY = _RESULTS / "wisdom_machinery-20261005-082435.json"


class TheoryPillDto(BaseModel):
    ac_plus: str = Field(description="Ac+: the ACTION that turns T's trap (T-) into A's strength (A+). One line, at most 15 words, in their particulars.")
    re_plus: str = Field(description="Re+: the REFLECTION that turns A's trap (A-) into T's strength (T+). One line, at most 15 words.")
    ac_minus: str = Field(description="Ac-: how the action degrades when T+ slides into A- — the one-sided version. At most 15 words.")
    re_minus: str = Field(description="Re-: how the reflection degrades when A+ slides into T-. At most 15 words.")
    s_plus: str = Field(description="S+: what becomes possible ONLY when Ac+ and Re+ happen together — a new quality, not a compromise. At most 10 words.")
    s_minus: str = Field(description="S-: what the situation collapses into when Ac- and Re- run together. At most 10 words.")
    your_side: str = Field(description="ONE sentence, second person, at most 25 words: their T+ WITHOUT the A+ becomes their T-. Their particulars. No labels.")
    other_side: str = Field(description="ONE sentence, second person, at most 25 words: the A+ WITHOUT their T+ becomes A-. Same rules.")
    paragraph: str = Field(description="At most 60 words, second person. Hold the tension, credit what is right in their position, then say the move — your Ac+ and Re+ — and what your S+ names as possible only with both; one clause on what your S- warns of. Their particulars. No framework words, no capitalised labels.")


SYSTEM = """You write for ONE person who just said one thing, and you were handed the tetrad around it: their position (T), what it stands against (A), each side developed well (T+, A+) and each side's trap (T-, A-). The tetrad is given and final.

From it, derive the dynamics by this rule and no other: the constructive action Ac+ carries T- into A+; the constructive reflection Re+ carries A- into T+; S+ is what emerges only when both run together (a gain in dimension, not a middle). Their degradations: Ac- carries T+ into A-, Re- carries A+ into T-; S- is what the two degradations collapse into (dominance or oscillation).

Then put it into words that land: plain, specific, second person, their own vocabulary, no jargon, no therapy voice, no hedging. Short beats complete."""


class _SMinusVerdict(BaseModel):
    sharper: Literal["A", "B", "same"] = Field(description="Which S- names the more specific, more recognisable way of going wrong for THIS person — not the more dramatic one. SAME when they say the same thing.")
    reasoning: str = Field(description="One sentence.")


_SMINUS_JUDGE = "You compare two one-line statements of how a person's situation collapses when they do the right thing badly. Judge specificity to the situation and recognisability, not drama or length."


async def _derive(r: dict) -> dict:
    conversation = ConversationFacilitator()
    conversation.set_system_prompt(SYSTEM)
    started = time.perf_counter()
    try:
        dto = await conversation.submit(TheoryPillDto, _corner_prompt(r))
        return {**dto.model_dump(), "seconds": round(time.perf_counter() - started, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"error": repr(exc)}


async def _judge_sminus(container, judge_model: str, a: str, b: str) -> dict:
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_SMINUS_JUDGE)
        with using_model(container, judge_model):
            v = await conversation.submit(_SMinusVerdict, f'A: "{a}"\nB: "{b}"\n\nWhich is sharper?')
        return {"sharper": v.sharper, "reasoning": v.reasoning}
    except Exception as exc:  # noqa: BLE001
        return {"sharper": None, "error": repr(exc)}


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_theory_in_prompt_against_the_machinery(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    rows = [r for r in json.loads(_MACHINERY.read_text()) if not r.get("error")]
    out = _RESULTS / f"wisdom_theory_prompt-{time.strftime('%Y%m%d-%H%M%S')}.json"
    derived = await asyncio.gather(*(_derive(r) for r in rows))
    rng = random.Random(20261005)
    results = []
    for r, d in zip(rows, derived):
        item = {"utterance": r["utterance"], "machinery": {k: r.get(k) for k in ("pathways", "s_plus", "s_minus", "paragraph")}, "prompt": d}
        if not d.get("error"):
            flip = rng.random() < 0.5
            a, b = (d["s_minus"], r["s_minus"]) if flip else (r["s_minus"], d["s_minus"])
            verdict = await _judge_sminus(di_container, judge, a, b)
            who = {"A": "prompt" if flip else "machinery", "B": "machinery" if flip else "prompt", "same": "same", None: None}[verdict.get("sharper")]
            item["sminus_judge"] = {"order": "prompt-first" if flip else "machinery-first", **verdict, "winner": who}
        results.append(item)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for i, it in enumerate(results, 1):
        p, m = it["prompt"], it["machinery"]
        print(f"\n{i}. **{it['utterance']}**")
        if p.get("error"):
            print(f"   ERROR {p['error']}"); continue
        print(f"   S+ machinery: {m['s_plus']}\n   S+ prompt   : {p['s_plus']}")
        print(f"   S- machinery: {m['s_minus']}\n   S- prompt   : {p['s_minus']}   → judge: {it['sminus_judge'].get('winner')}")
        print(f"   Ac+ prompt  : {p['ac_plus']}\n   Re+ prompt  : {p['re_plus']}")
        print(f"   PROMPT PILL : {p['paragraph']}")
    wins = [it["sminus_judge"]["winner"] for it in results if it.get("sminus_judge")]
    print(f"\n--- S- blind pairwise (n={len(wins)}): machinery {wins.count('machinery')}, prompt {wins.count('prompt')}, same {wins.count('same')}")
    print(f"    prompt arm median {sorted(p['seconds'] for p in derived if 'seconds' in p)[len(derived)//2]}s a call (machinery: ~88 s)  → {out}")
