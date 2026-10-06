"""A retry card should cost three view-turn calls. Does it?

The regression check for a defect that shipped for one day. Reported by the
first app (2026-10-06, retry-routing v3): a retry's best-of-3 cost ~4.6 draw
calls instead of 3, +17 s of wait. Cause: that morning's cache lever moved the
view turn's long request (definitions, rules, procedure, "Answer with ONE JSON
object") onto the SYSTEM prompt and left only "What to show: <focus>" as the
user message. First cards did not notice. A retry did: its history already
holds "Show me: ..." and the previous drawing as PROSE, and with a bare focus as
the last user turn the model answered in prose too, failing to parse — the
request->prose trap `view_sketch.history_ask` already keeps out of the history.

Measured with this probe in two arms before the fix
(`view_turn_retry_calls-20261006-160055.json`, Sonnet 5, 8 utterances):

| retry card                         | view calls | parse retries | seconds |
|------------------------------------|------------|---------------|---------|
| instructions on the system prompt  | 4.75       | 1.75          | 33.1    |
| the whole request as the user turn | 3.00       | 0.00          | 19.9    |

First cards were 3.00 / 0.00 in both. The request went back into the user
message (`Consultant.exploration_view`), so the second arm is what ships and
this probe now checks it alone: a first card and a retry per utterance, the
app's own asks, a NEW Consultant per card as the app builds them.

    poetry run pytest tests/e2e/probe_view_turn_retry_calls.py --real-llm -q -s
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.retry_accounting import retry_account
from e2e.config import E2EConfig
from e2e.modelctx import using_model

_HERE = Path(__file__).resolve().parent
_RESULTS = _HERE / "results" / "tetrad_quality"

#: The app's asks (alsotrue-app `alsotrue/tetrad.py`), copied so this probe
#: needs no app on the path.
_FIRST = (
    "the perspective for what I just said: my position, what it stands against, "
    "and above all the constructive side of that opposing view that I am not seeing"
)


def _retry(position: str, against: str) -> str:
    return (
        f'The person set aside the card "{position}" against "{against}". '
        "Draw one tension they have NOT seen yet: keep their position as it "
        "stands and find a different opposition to it in what they said — not "
        "the shown one re-worded — and above all the constructive side of the "
        "opposing view they are not seeing."
    )


async def _card(messages: list, focus: str) -> dict[str, Any]:
    head = Consultant(app_preamble=COUNSELOR_PERSONA, messages=list(messages))
    started = time.monotonic()
    error = None
    with call_census() as census, retry_account() as retries:
        try:
            view = await head.exploration_view(focus=focus, attempts=3)
        except Exception as exc:  # noqa: BLE001 - a failed card is a row
            view, error = None, f"{type(exc).__name__}: {exc}"
    first = view.perspectives[0] if view and view.perspectives else None
    return {
        "view_calls": sum(1 for c in census.calls if "ViewSketchDto" in c.label),
        "parse_retries": retries.kinds.get("parse", 0),
        "all_retries": dict(retries.kinds),
        "seconds": round(time.monotonic() - started, 1),
        "drawn": bool(first),
        "position": first.t.text if first and first.t else None,
        "against": first.a.text if first and first.a else None,
        "messages": head.messages,
        "error": error,
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_a_retry_card_costs_three_view_calls(di_container) -> None:
    from mirascope import llm

    writer = E2EConfig.from_env().tiers["strong"]
    n = int(os.getenv("PROBE_N", "8"))
    utterances = [json.loads(x)["utterance"] for x in (_HERE / "fixtures" / "transformation_tetrads.jsonl").read_text().splitlines() if x.strip()][:n]
    out = _RESULTS / f"view_turn_retry_calls-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rows: list[dict[str, Any]] = []

    with using_model(di_container, writer):
        for u in utterances:
            first = await _card([llm.messages.user(u)], _FIRST)
            retry = None
            if first["drawn"]:
                retry = await _card(first["messages"], _retry(first["position"], first["against"] or ""))
            for kind, card in (("first", first), ("retry", retry)):
                if card is None:
                    continue
                row = {k: v for k, v in card.items() if k != "messages"}
                rows.append({"card": kind, "utterance": u, **row})
                print(f"  {kind:5} view calls {row['view_calls']} parse retries {row['parse_retries']} "
                      f"{row['seconds']:5.1f}s {'ERR ' + row['error'] if row['error'] else ''} «{u[:40]}»", flush=True)
            out.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str))

    print(f"\n--- {out.name} (writer {writer}) ---")
    for kind in ("first", "retry"):
        sel = [r for r in rows if r["card"] == kind]
        if sel:
            print(f"  {kind:5} n={len(sel)}  view calls/card {sum(r['view_calls'] for r in sel) / len(sel):.2f}  "
                  f"parse retries/card {sum(r['parse_retries'] for r in sel) / len(sel):.2f}  "
                  f"{sum(r['seconds'] for r in sel) / len(sel):.1f}s  failed {sum(1 for r in sel if r['error'])}")
