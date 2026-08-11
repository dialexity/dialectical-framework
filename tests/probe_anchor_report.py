"""Probe: how big is anchor's LLM-visible return, and where are the hashes?

The Advisor's system prompt is static after construction, so in a fresh session
the "Current Understanding" dump says "No prior understanding" for the entire
conversation. The model's ONLY view of what it just built is the tool result.
`explore` takes perspective hashes as arguments, so if those hashes are buried,
the model cannot call it even when the prompt tells it to.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.tools.anchor import anchor
from dialectical_framework.concerns.antithesis_extraction import (
    AntithesisExtraction, AntithesisProcessed)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

BRANCH = "dx://taxonomy/System(General.v1)/Viability/Integrity"

CONTEXT = (
    "Cofounder holds 45% equity. Two anchor accounts are 60% of revenue and "
    "both CEOs call him, not me. Feedback given in March, no change since."
)

ANTITHESES = [
    "Keep him and reset the terms",
    "Transfer the accounts before deciding",
    "Let the partnership run as is",
    "Hand him the customer relationships formally",
    "Sell the company instead",
]


def _measure(label: str, out: str) -> None:
    i = out.find('"perspective_hashes"')
    eff = out.find('"effects"')
    art = out.find('"artifacts"')
    print(f"\n### {label}")
    print(f"  chars={len(out)}  lines={out.count(chr(10))}  ~tokens={int(len(out)/3.7)}")
    if i >= 0:
        print(f"  perspective_hashes at {i} = {100*i/len(out):.0f}% depth")
    else:
        print("  perspective_hashes: ABSENT")
    if eff >= 0 and art > eff:
        print(f"  effects block = {100*(art-eff)/len(out):.0f}% of payload")
    # what does the summary line say?
    import json as _json
    try:
        print("  summary:", _json.loads(out).get("summary", "")[:200])
    except Exception:
        print("  summary: <unparseable>")


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_anchor_payload_thesis_only(monkeypatch):
    """The bench's dominant path: thesis only, which fans out to N polarities."""

    async def fake_extract(self, thesis, text="", not_like_these=None, count=5):
        out = []
        for name in ANTITHESES:
            stmt = Statement(text=name, meaning=f"{BRANCH}/Separation")
            stmt.commit()
            out.append(
                AntithesisProcessed(
                    component=stmt,
                    mode_value=0.8,
                    arousal_value=0.6,
                    heuristic_similarity=0.85,
                )
            )
        return out

    monkeypatch.setattr(AntithesisExtraction, "resolve", fake_extract)

    case = Case()
    case.commit()
    with scope(case.sid):
        out = await anchor.fn(
            thesis="Buy out the cofounder now", antithesis=None, context=CONTEXT
        )
    _measure("thesis-only (5 polarities)", out)


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_anchor_payload_both_sides():
    case = Case()
    case.commit()
    with scope(case.sid):
        out = await anchor.fn(
            thesis="Buy out the cofounder now",
            antithesis="Keep him and reset the terms",
            context=CONTEXT,
        )
    _measure("thesis+antithesis (1 polarity)", out)
