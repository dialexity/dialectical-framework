"""Restatement: can a flagged plus be REPAIRED without turning into a compromise?

The one-shot surfaces restate a plus — almost always A+ stating A's own
benefit — in 7–12% of plus slots. The lever that removed it at the source
(take-up fields) cost coherence 25/40 → 15/40 by manufacturing compromise pluses.
This tries the other shape: build as today, audit the two pluses with the archive's
parentage judge, and regenerate ONLY a flagged plus with a repair instruction —
then judge the repaired tetrad's coherence and re-audit the plus.

Pre-registered (docs/dev-notes/antithesis-selection.md): a production repair step
is worth its call only if, over the repaired tetrads, restatement drops by at
least half, CC does not fall, and the T+/A+ `same_compromise` share does not rise.

DB-free, plain script (not pytest — it may run beside a graph probe):

    poetry run python tests/e2e/probe_plus_repair.py            # 40 utterances
    poetry run python tests/e2e/probe_plus_repair.py --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402

from dialectical_framework.dialectical_reasoning import \
    DialecticalReasoning  # noqa: E402
from dialectical_framework.settings import Settings  # noqa: E402

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"


class _RepairedPlus(BaseModel):
    statement: str = Field(description="The repaired plus, in the person's own terms, a few words.")


def _repair_prompt(position: str, row: dict, max_words: int) -> str:
    own, other = ("T", "A") if position == "t_plus" else ("A", "T")
    own_text = row["thesis"] if own == "T" else row["antithesis"]
    other_text = row["antithesis"] if own == "T" else row["thesis"]
    from dialectical_framework.concerns.aspect_generation import \
        PLUS_RESTATEMENT_CHECK

    return f"""Thesis (T): "{row['thesis']}"
Antithesis (A): "{row['antithesis']}"

The draft {own}+ was: "{row[position]}". It RESTATES {own} — it names what {own} already delivers ("{own_text}") and takes up nothing {other} is for ("{other_text}").

Write a new {own}+: {own} developed constructively so that {own} stays the generative act AND its result also supplies what {other} is for. Not a compromise between the two, not {other} in {own}'s clothes, not a condition bolted on. {PLUS_RESTATEMENT_CHECK}

{max_words} words or fewer, in the person's own terms."""


async def _run(limit: int) -> None:
    from e2e.config import E2EConfig
    from e2e.modelctx import using_model
    from e2e.probe_aspect_variants import _judge
    from e2e.probe_tetrad_quality import (SET_A, SET_B, _audit_parentage,
                                          _audit_pluses, _wilson)

    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from dialectical_framework.concerns.tetrad_sketch import TetradSketch

    container = DialecticalReasoning.setup(Settings.from_env())
    judge = E2EConfig.from_env().judge_model
    max_words = container.settings().component_length
    utterances = (list(SET_A) + list(SET_B))[: limit or None]
    out = _RESULTS / f"plus_repair-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rows: list[dict] = []
    print(f"=== plus repair on {len(utterances)} utterances, judge {judge} → {out}", flush=True)

    for index, text in enumerate(utterances, 1):
        tension = await TetradSketch().resolve(text)
        row: dict[str, Any] = {"utterance": text, **{k: getattr(tension, k) for k in
                               ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")}}
        row["before"] = await _judge(row)
        row["before"].update(await _audit_pluses(container, judge, row))
        row["before"].update(await _audit_parentage(container, judge, row))
        flagged = [
            pos for pos in ("t_plus", "a_plus")
            if row["before"].get(f"{pos}_parent") == "own_pole" and row["before"].get(f"{pos}_valence_ok") is False
        ]
        row["flagged"] = flagged
        if flagged:
            repaired = dict(row)
            for pos in flagged:
                conversation = ConversationFacilitator()
                result = await conversation.submit(_RepairedPlus, _repair_prompt(pos, row, max_words))
                repaired[pos] = result.statement.strip()
                row[f"{pos}_repaired"] = repaired[pos]
            after = await _judge(repaired)
            after.update(await _audit_pluses(container, judge, repaired))
            after.update(await _audit_parentage(container, judge, repaired))
            row["after"] = after
        rows.append(row)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"  [{index}/{len(utterances)}] flagged {flagged or '-'}  "
              f"CC {'PASS' if row['before']['pass'] else 'fail'}"
              + (f" → {'PASS' if row['after']['pass'] else 'fail'}" if flagged else ""), flush=True)

    # --- summary ---
    n = len(rows)
    restated_before = sum(len(r["flagged"]) for r in rows)
    repaired_rows = [r for r in rows if r["flagged"]]
    still = sum(
        1 for r in repaired_rows for pos in r["flagged"]
        if r["after"].get(f"{pos}_parent") == "own_pole" and r["after"].get(f"{pos}_valence_ok") is False
    )
    cc_before = sum(bool(r["before"]["pass"]) for r in rows)
    cc_rep_before = sum(bool(r["before"]["pass"]) for r in repaired_rows)
    cc_rep_after = sum(bool(r["after"]["pass"]) for r in repaired_rows)
    comp_before = sum(1 for r in repaired_rows if r["before"].get("plus_relation") == "same_compromise")
    comp_after = sum(1 for r in repaired_rows if r["after"].get("plus_relation") == "same_compromise")
    lo, hi = _wilson(restated_before, 2 * n)
    print("\n--- plus repair ---")
    print(f"  tetrads {n}; CC before {cc_before}/{n}; restated plus slots {restated_before}/{2*n} "
          f"({100*restated_before/max(1,2*n):.1f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)")
    print(f"  repaired tetrads {len(repaired_rows)}: still restated after repair {still}/{restated_before}; "
          f"CC {cc_rep_before}/{len(repaired_rows)} → {cc_rep_after}/{len(repaired_rows)}; "
          f"same_compromise {comp_before} → {comp_after}")
    for r in repaired_rows[:8]:
        for pos in r["flagged"]:
            print(f"    {pos}: «{r[pos]}» → «{r[f'{pos}_repaired']}»  "
                  f"({'PASS' if r['before']['pass'] else 'fail'} → {'PASS' if r['after']['pass'] else 'fail'})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(_run(args.limit))


if __name__ == "__main__":
    main()
