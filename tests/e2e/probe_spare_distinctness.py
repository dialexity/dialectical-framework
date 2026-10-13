"""Do the runners-up of a best-of-N name a DIFFERENT opposition, or the same one reworded?

The read behind the different-opposition ask (`view_sketch.different_opposition_ask`,
2026-10-13; `docs/dev-notes/antithesis-selection.md`, "Best-of-3 drew the same tetrad
three times"). `probe_view_turn_ask.py` records each card's spares and a lexical
similarity, and the control arm showed the lexical proxy is not the read: the same
opposition reworded ("Trust spontaneity to find what fits best" / "Staying responsive to
how I actually feel") sits well under the 0.6 line. So this auditor asks the question in
words, per spare, and writes the verdicts back into the probe's files, then prints the
pre-registered table for every file given.

    SPARE_FILES="results/tetrad_quality/view_turn_pin_control-*.json,results/tetrad_quality/view_turn_pin_arm-*.json" \\
    poetry run pytest tests/e2e/probe_spare_distinctness.py --real-llm -q -s

Without `SPARE_FILES`: the newest file of each `view_turn_pin_control-*` and `view_turn_pin_arm-*`.
"""

from __future__ import annotations

import asyncio
import collections
import glob
import json
import os
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from e2e.config import E2EConfig
from e2e.modelctx import using_model

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"

_SYSTEM = """You audit a dialectical analysis. A thesis is a person's own position. Two antitheses were written for it, independently. Decide whether they name the SAME opposing position or DIFFERENT ones.

- same: one claim about the same thing, differing in wording, emphasis, length or detail; holding one is holding the other.
- different: a different thing someone holds against the thesis — a different axis of disagreement — such that a person could hold one of the two without holding the other.

Judge the position named, not the words used."""


class _Verdict(BaseModel):
    relation: Literal["same", "different"] = Field(description="same or different, by the rule")
    reasoning: str = Field(description="One sentence")


async def _audit(container, judge: str, thesis: str, a: str, b: str) -> dict:
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_SYSTEM)
        with using_model(container, judge):
            verdict = await conversation.submit(
                _Verdict,
                f'Thesis: "{thesis}"\nAntithesis 1: "{a}"\nAntithesis 2: "{b}"\n\nSame opposing position, or different?',
            )
        return {"relation": verdict.relation, "relation_reasoning": verdict.reasoning}
    except Exception as exc:  # noqa: BLE001
        return {"relation": None, "relation_error": repr(exc)}


def _files() -> list[Path]:
    spec = os.environ.get("SPARE_FILES")
    if spec:
        return [Path(p) for pattern in spec.split(",") for p in sorted(glob.glob(pattern.strip()))]
    out = []
    for tag in ("pin_control", "pin_arm"):
        found = sorted(_RESULTS.glob(f"view_turn_{tag}-*.json"))
        if found:
            out.append(found[-1])
    return out


def _wilson_fmt(k: int, n: int) -> str:
    from e2e.probe_tetrad_quality import _wilson

    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_spares_name_a_different_opposition(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    files = _files()
    assert files, "no probe files to audit"
    for path in files:
        rows = json.loads(path.read_text())
        complete = [r for r in rows if r.get("antithesis") and r.get("spares")]
        print(f"\n=== {path.name}: {len(complete)} cards with spares, judge {judge}", flush=True)
        for row in complete:
            for spare in row["spares"]:
                if spare.get("antithesis") and "relation" not in spare:
                    spare.update(await _audit(di_container, judge, row["thesis"], row["antithesis"], spare["antithesis"]))
            path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        # The pre-registered table, one file at a time.
        spares = [s for r in complete for s in r["spares"]]
        different = sum(1 for s in spares if s.get("relation") == "different")
        cards_distinct = sum(1 for r in complete if any(s.get("relation") == "different" for s in r["spares"]))
        kinds = collections.Counter(s.get("a_kind") for s in spares)
        judged = [r for r in rows if r.get("thesis") and "pass" in r]
        cc = sum(bool(r.get("pass")) for r in judged)
        pos = sum(1 for r in judged if r.get("a_kind") == "position")
        restated = sum(
            1 for r in judged for s in ("t_plus", "a_plus")
            if r.get(f"{s}_parent") == "own_pole" and r.get(f"{s}_valence_ok") is False
        )
        secs = sorted(r["seconds"] for r in rows if "seconds" in r)
        print(f"  cards with a DIFFERENT spare   {_wilson_fmt(cards_distinct, len(complete))}")
        print(f"  spares different               {_wilson_fmt(different, len(spares))}")
        print(f"  spares a position (kind)       {_wilson_fmt(kinds.get('position', 0), len(spares))}   {dict(kinds)}")
        print(f"  winner CC pass (fresh judge)   {_wilson_fmt(cc, len(judged))}")
        print(f"  winner A a position            {_wilson_fmt(pos, len(judged))}")
        print(f"  restated plus slots            {restated}/{2*len(judged)}")
        print(f"  latency median                 {secs[len(secs)//2] if secs else None}s")
        print(f"  failed draws                   {sum(len(r.get('failed_draws', [])) for r in rows)}")
