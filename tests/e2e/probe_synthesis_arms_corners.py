"""Render the DIAGONALS of already-drawn tetrads as sentences — does the wow live there?

The blindspot card shows corners (A+ first) and the owner's eye found them true
but flat ("too distant or formal"). The tetrad's depth is in its relations: the
control statements "T+ without A+ yields T-" / "A+ without T+ yields A-" are
computed and judged and never shown. This renders them in second person, in
the person's words, from EXISTING draws (no new reasoning), beside a ≤60-word
paragraph that holds the tension and pushes for T+/A+ complementarity — so the
line and the paragraph can be eyeballed against the bare A+.

    poetry run pytest tests/e2e/probe_synthesis_arms_corners.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_STATEMENTS = _RESULTS / "view_turn_attempts3-20261004-104227.json"
_QUESTIONS = _RESULTS / "question_entry-20261004-145135.json"

#: A mix the owner read: ones that landed, ones that felt flat.
PICK_STATEMENTS = [1, 4, 7, 8, 13, 20, 25, 28, 29, 33, 36, 39]
PICK_QUESTIONS = [2, 5, 12, 14, 19]


class WisdomDto(BaseModel):
    your_side: str = Field(description="ONE sentence, second person, at most 25 words: the person's T+ — the strength in their position — WITHOUT the A+ becomes their T-. Name all three in their own particulars. No labels, no 'thesis'.")
    other_side: str = Field(description="ONE sentence, second person, at most 25 words: the A+ WITHOUT their T+ becomes A-. Same rules.")
    paragraph: str = Field(description="At most 60 words, second person. Hold the tension (do not resolve it), credit what is right in their position, then push for holding T+ and A+ together — what becomes possible only with both. Their particulars, not generalities. No framework words.")


SYSTEM = """You write for ONE person who just said one thing, and you were handed the dialectical structure around it: their position (T), what it stands against (A), each side developed well (T+, A+) and each side's trap (T-, A-). You do not reason the structure — it is given and final. You put its RELATIONS into words that land: plain, specific, second person, their own vocabulary, no jargon, no therapy voice, no hedging, no 'it's important to'. Short beats complete."""


def _prompt(r: dict) -> str:
    return f"""They said: "{r['utterance']}"

Position (T): {r['thesis']}
Stands against (A): {r['antithesis']}
T developed well (T+): {r['t_plus']}
T's trap (T-): {r['t_minus']}
A developed well (A+): {r['a_plus']}
A's trap (A-): {r['a_minus']}

Write the three pieces."""


async def _render(r: dict) -> dict:
    conversation = ConversationFacilitator()
    conversation.set_system_prompt(SYSTEM)
    started = time.perf_counter()
    try:
        dto = await conversation.submit(WisdomDto, _prompt(r))
        return {**{k: r.get(k) for k in ("utterance", "thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus", "pass")},
                "your_side": dto.your_side, "other_side": dto.other_side, "paragraph": dto.paragraph,
                "seconds": round(time.perf_counter() - started, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"utterance": r.get("utterance"), "error": repr(exc)}


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_render_the_diagonals(di_container) -> None:
    s = json.loads(_STATEMENTS.read_text()); q = json.loads(_QUESTIONS.read_text())
    rows = [s[i - 1] for i in PICK_STATEMENTS] + [q[i - 1] for i in PICK_QUESTIONS]
    rows = [r for r in rows if r.get("a_plus")]
    out = _RESULTS / f"wisdom_line-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rendered = await asyncio.gather(*(_render(r) for r in rows))
    out.write_text(json.dumps(rendered, indent=2, ensure_ascii=False))
    for i, r in enumerate(rendered, 1):
        if r.get("error"):
            print(f"\n{i}. {r['utterance']}\n   ERROR {r['error']}"); continue
        print(f"\n{i}. **{r['utterance']}**{'' if r.get('pass') else '  (judge: incoherent)'}")
        print(f"   A+ alone : {r['a_plus']}")
        print(f"   your side: {r['your_side']}")
        print(f"   other    : {r['other_side']}")
        print(f"   paragraph: {r['paragraph']}")
    print(f"\n→ {out}  median {sorted(r['seconds'] for r in rendered if 'seconds' in r)[len(rendered)//2]}s")
