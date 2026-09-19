"""
probe_format_mode_thinking — can a structured concern call THINK, and at what price?

Every one of the framework's 33 structured DTOs reaches the provider through
`ConversationFacilitator._call_with_response_model`, which asks Mirascope for
the DTO with its default formatting mode: FORCED TOOL USE. The provider rejects
extended thinking on that shape outright ("Thinking may not be enabled when
tool_choice forces tool use", verified 2026-09-18), so the framework's own
reasoning — tetrads, classification, HS, transformations, extraction, the
decision classifier — has never thought at all, whatever the level says.

Mirascope 2.5 offers other modes (`llm.format(Model, mode="json" | "strict")`).
This measures, on a real DTO-shaped call, whether each mode (a) parses as
reliably as tool mode, (b) accepts thinking, and (c) what thinking costs there
— so the extraction-faithfulness question (13% invented claims) can be asked
with thinking on, and so a mode switch is a measured change rather than a hope.

NOT free: `--real-llm`, REPS x (tool, json, json+thinking, strict, strict+thinking).

    DIALEXITY_PROBE_REPS=4 poetry run pytest \
        tests/e2e/probe_format_mode_thinking.py --real-llm -s
"""

from __future__ import annotations

import os
import statistics
import time

import pytest
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.use_brain import use_brain

REPS = int(os.getenv("DIALEXITY_PROBE_REPS", "4"))


class TetradLikeDto(BaseModel):
    """A DTO of the shape the framework's concerns actually use: several
    constrained strings plus a score, not a one-field toy."""

    t_plus: str = Field(description="How the thesis, developed well, balances the antithesis; ~7 words")
    t_minus: str = Field(description="How the thesis, overdone, undermines the antithesis; ~7 words")
    a_plus: str = Field(description="How the antithesis, developed well, balances the thesis; ~7 words")
    a_minus: str = Field(description="How the antithesis, overdone, undermines the thesis; ~7 words")
    balance: float = Field(description="0.0-1.0: how symmetric the four aspects are")


PROMPT = (
    "Thesis: 'Ship a release every week.' Antithesis: 'Ship only when the release "
    "is complete.' Give the four aspects and a balance score in the schema."
)


def _condition(mode: str | None, thinking: str | None):
    fmt = TetradLikeDto if mode is None else llm.format(TetradLikeDto, mode=mode)
    kwargs = {"thinking": thinking} if thinking else {}

    @use_brain(format=fmt, retry_max=1, **kwargs)
    async def call():
        return [llm.messages.user(PROMPT)]

    return call


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_format_mode_thinking():
    conditions = {
        "tool (default)": (None, None),
        "json": ("json", None),
        "json + thinking medium": ("json", "medium"),
        "strict": ("strict", None),
        "strict + thinking medium": ("strict", "medium"),
    }
    results: dict[str, list[dict]] = {k: [] for k in conditions}
    for rep in range(REPS):
        for name, (mode, thinking) in conditions.items():
            call = _condition(mode, thinking)
            with call_census() as census:
                t0 = time.monotonic()
                try:
                    out = await call()
                    err = None
                except Exception as e:  # noqa: BLE001
                    out, err = None, f"{type(e).__name__}: {str(e)[:110]}"
                dt = time.monotonic() - t0
            rec = census.calls[0] if census.calls else None
            row = {
                "s": dt,
                "ok": out is not None and isinstance(out.balance, float),
                "out": getattr(rec, "output_tokens", None),
                "prefill": getattr(rec, "prefill_tokens", None),
                "err": err,
            }
            results[name].append(row)
            print(
                f"  rep {rep + 1} {name:26s} {dt:5.1f}s ok={row['ok']} "
                f"out={row['out']} prefill={row['prefill']} {err or ''}"
            )

    print("\ncondition                   n  parsed  median s  out tok  prefill")
    for name, rows in results.items():
        ok = sum(r["ok"] for r in rows)
        secs = [r["s"] for r in rows]
        outs = [r["out"] for r in rows if r["out"] is not None]
        pre = [r["prefill"] for r in rows if r["prefill"] is not None]
        print(
            f"{name:26s} {len(rows):2d}  {ok}/{len(rows)}   "
            f"{statistics.median(secs):6.2f}  "
            f"{statistics.median(outs) if outs else '-':>7}  "
            f"{statistics.median(pre) if pre else '-':>7}"
        )
    errors = {name: [r["err"] for r in rows if r["err"]] for name, rows in results.items()}
    for name, errs in errors.items():
        if errs:
            print(f"  {name}: {errs[0]}")
