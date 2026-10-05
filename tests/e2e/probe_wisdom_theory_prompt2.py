"""Theory-in-prompt, second arm: the FULL Transformation shape in one call.

The first arm (`probe_wisdom_theory_prompt.py`) asked for Ac+/Re+/Ac-/Re-/S+/S-
from the six corners and got Ac- = T- restated, Re- = A- restated, S- = "either
T- or A-" in 14/17 — it collapsed the Transformation tetrad onto the Perspective
tetrad, because it never derived the neutral action Ac and reflection Re whose
plus and minus Ac±/Re± are. This arm asks for the Transformation AS a tetrad:
Ac and Re first, then each one's constructive and one-sided development, then
S+/S- from the pairs — the owner's hypothesis stated properly. Same 17, same
blind S- judge, plus a "third trap?" auditor on BOTH arms' S- (distinct from
T- and A-, or the two traps restated).

    poetry run pytest tests/e2e/probe_wisdom_theory_prompt2.py --real-llm -q -s
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
from e2e.probe_wisdom_theory_prompt import _judge_sminus

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_MACHINERY = _RESULTS / "wisdom_machinery-20261005-082435.json"
_ARM1 = _RESULTS / "wisdom_theory_prompt-20261005-090914.json"


class TransformationPillDto(BaseModel):
    action: str = Field(description="Ac — the neutral ACTION that carries the person from T toward A: what they would actually do. One line, at most 15 words, in their particulars.")
    reflection: str = Field(description="Re — the neutral REFLECTION that carries them from A back toward T: what they would notice or re-read. One line, at most 15 words.")
    ac_plus: str = Field(description="Ac+ — the action developed constructively: the version that turns T's trap (T-) into A's strength (A+). At most 15 words.")
    ac_minus: str = Field(description="Ac- — the SAME action overdeveloped one-sidedly, reflection absent: what this action becomes when done without the reflection. NOT T- or A- restated — it is the action itself gone wrong. At most 15 words.")
    re_plus: str = Field(description="Re+ — the reflection developed constructively: the version that turns A's trap (A-) into T's strength (T+). At most 15 words.")
    re_minus: str = Field(description="Re- — the SAME reflection overdeveloped one-sidedly, action absent: what this reflecting becomes when it never turns into the action. NOT T- or A- restated. At most 15 words.")
    s_plus: str = Field(description="S+ — what emerges only when Ac+ and Re+ run together: a new quality neither alone has. At most 10 words. Not a compromise, not 'both'.")
    s_minus: str = Field(description="S- — what Ac- and Re- running together collapse into: ONE named way of failing that is neither T- nor A-. Never 'either X or Y'. At most 10 words.")
    your_side: str = Field(description="ONE sentence, second person, at most 25 words: their T+ WITHOUT the A+ becomes their T-. Their particulars. No labels.")
    other_side: str = Field(description="ONE sentence, second person, at most 25 words: the A+ WITHOUT their T+ becomes A-. Same rules.")
    paragraph: str = Field(description="At most 60 words, second person. Hold the tension, credit what is right in their position, then say the move — your Ac+ and Re+ — what your S+ names as possible only with both, and one clause on what your S- warns of. Their particulars. No framework words, no capitalised labels.")


SYSTEM = """You write for ONE person who just said one thing, and you were handed the tetrad around it: their position (T), what it stands against (A), each side developed well (T+, A+) and each side's trap (T-, A-). The tetrad is given and final.

From it, derive the way through as a SECOND tetrad, the transformation, in this order and no other:
1. The action (Ac): the concrete thing that carries them from their position toward the other side. The reflection (Re): the re-reading that carries them from the other side back toward their own.
2. Each developed well — Ac+ turns their trap T- into the other side's strength A+; Re+ turns the other side's trap A- into their own strength T+.
3. Each overdeveloped one-sidedly — Ac- is the action done without the reflection, Re- is the reflection without the action. These are the ACTION and the REFLECTION gone wrong, never the original traps restated.
4. S+ is what emerges only when Ac+ and Re+ run together — a gain in dimension, not a middle. S- is the ONE collapse Ac- and Re- produce together — a single named failure, not "either trap".

Then put it into words that land: plain, specific, second person, their own vocabulary, no jargon, no therapy voice, no hedging. Short beats complete."""


class _ThirdTrapVerdict(BaseModel):
    kind: Literal["third_failure", "traps_restated", "one_trap"] = Field(description="THIRD_FAILURE: S- names a way of failing that is neither T- nor A- — a distinct collapse. TRAPS_RESTATED: S- is T- and A- again (an either/or, or both listed). ONE_TRAP: S- is just T- or just A- reworded.")
    reasoning: str = Field(description="One sentence.")


_THIRD_TRAP_SYSTEM = "You audit a synthesis's negative pole (S-) against the two traps (T-, A-) it was derived beside. Decide whether it names a third, distinct failure or merely restates one or both traps."


async def _derive(r: dict) -> dict:
    conversation = ConversationFacilitator()
    conversation.set_system_prompt(SYSTEM)
    started = time.perf_counter()
    try:
        dto = await conversation.submit(TransformationPillDto, _corner_prompt(r))
        return {**dto.model_dump(), "seconds": round(time.perf_counter() - started, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"error": repr(exc)}


async def _third_trap(container, judge_model: str, t_minus: str, a_minus: str, s_minus: str) -> dict:
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_THIRD_TRAP_SYSTEM)
        with using_model(container, judge_model):
            v = await conversation.submit(_ThirdTrapVerdict, f'T-: "{t_minus}"\nA-: "{a_minus}"\nS-: "{s_minus}"\n\nClassify S-.')
        return {"kind": v.kind, "reasoning": v.reasoning}
    except Exception as exc:  # noqa: BLE001
        return {"kind": None, "error": repr(exc)}


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_full_transformation_shape_in_one_call(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    rows = [r for r in json.loads(_MACHINERY.read_text()) if not r.get("error")]
    arm1 = {it["utterance"]: it["prompt"] for it in json.loads(_ARM1.read_text())}
    out = _RESULTS / f"wisdom_theory_prompt2-{time.strftime('%Y%m%d-%H%M%S')}.json"
    derived = await asyncio.gather(*(_derive(r) for r in rows))
    rng = random.Random(20261005)
    results = []
    for r, d in zip(rows, derived):
        item = {"utterance": r["utterance"], "machinery": {k: r.get(k) for k in ("s_plus", "s_minus")}, "arm1": {k: arm1.get(r["utterance"], {}).get(k) for k in ("s_minus",)}, "prompt2": d}
        if not d.get("error"):
            flip = rng.random() < 0.5
            a, b = (d["s_minus"], r["s_minus"]) if flip else (r["s_minus"], d["s_minus"])
            v = await _judge_sminus(di_container, judge, a, b)
            item["sminus_judge"] = {"order": "prompt-first" if flip else "machinery-first", **v,
                                   "winner": {"A": "prompt2" if flip else "machinery", "B": "machinery" if flip else "prompt2", "same": "same", None: None}[v.get("sharper")]}
            item["third_trap"] = {
                "machinery": await _third_trap(di_container, judge, r["t_minus"], r["a_minus"], r["s_minus"]),
                "arm1": await _third_trap(di_container, judge, r["t_minus"], r["a_minus"], item["arm1"]["s_minus"] or ""),
                "prompt2": await _third_trap(di_container, judge, r["t_minus"], r["a_minus"], d["s_minus"]),
            }
        results.append(item)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for i, it in enumerate(results, 1):
        p = it["prompt2"]
        print(f"\n{i}. **{it['utterance']}**")
        if p.get("error"):
            print(f"   ERROR {p['error']}"); continue
        tt = it["third_trap"]
        print(f"   Ac : {p['action']}\n   Re : {p['reflection']}\n   Ac-: {p['ac_minus']}\n   Re-: {p['re_minus']}")
        print(f"   S- machinery: {it['machinery']['s_minus']}   [{tt['machinery'].get('kind')}]")
        print(f"   S- arm1     : {it['arm1']['s_minus']}   [{tt['arm1'].get('kind')}]")
        print(f"   S- prompt2  : {p['s_minus']}   [{tt['prompt2'].get('kind')}]   → sharper: {it['sminus_judge'].get('winner')}")
        print(f"   S+ prompt2  : {p['s_plus']}")
        print(f"   PILL: {p['paragraph']}")
    wins = [it["sminus_judge"]["winner"] for it in results if it.get("sminus_judge")]
    print(f"\n--- S- blind pairwise vs machinery (n={len(wins)}): machinery {wins.count('machinery')}, prompt2 {wins.count('prompt2')}, same {wins.count('same')}")
    for arm in ("machinery", "arm1", "prompt2"):
        kinds = [it["third_trap"][arm].get("kind") for it in results if it.get("third_trap")]
        print(f"    third-trap auditor, {arm:9}: third_failure {kinds.count('third_failure')}, traps_restated {kinds.count('traps_restated')}, one_trap {kinds.count('one_trap')}")
    print(f"    prompt2 median {sorted(p['seconds'] for p in derived if 'seconds' in p)[len(derived)//2]}s a call  → {out}")
