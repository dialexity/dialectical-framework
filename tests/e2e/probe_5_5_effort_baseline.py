"""
probe_5_5_effort_baseline — latency and cost per thinking level, Claude 5 vs 5.5.

On 5.5 "off" is not off everywhere (`thinking_compat.off_shape`): Sonnet 5.5
says it as `between_tools`, Opus 5.5 cannot turn thinking off and gets effort
`low`. Every latency and cost figure in the archive was taken on Claude 5 or
Haiku 4.5, so before a 5.5 model is configured the per-level price has to be
re-measured rather than assumed. Two paths, because they are decided apart:

- CONVERSATION — the tool path (`conversation_thinking=` off / low / medium /
  high): the Consultant's method prompt as system, a real bench utterance
  (`probe_consultant_42s.MATERIAL` + `probe_consultant_prompt_cost.QUESTION`),
  one tool wired so the call is a conversational round.
- STRUCTURED — a tetrad-shaped DTO: the default concern path (forced tool on
  Claude 5; JSON + the model's off on 5.5, see `format_compat`) and the one
  thinking structured shape (`format_mode="json", thinking="medium"`, the
  `TetradSketch` / view-turn shape).

Cost is the first call's tokens at first-party list price (USD/MTok in/out:
Sonnet 5 and 5.5 2/10, Opus 5.5 4/20; Bedrock bills separately). A tool round
the model elects adds resumes the census cannot see, so the cost column covers
the first call only and `tools` says when there were more. One rater, no
judged quality: this prices the levels, it does not say which one is worth it.

    DIALEXITY_PROBE_REPS=3 poetry run pytest tests/e2e/probe_5_5_effort_baseline.py --real-llm -s
"""

from __future__ import annotations

import os
import statistics
import time

import pytest
from e2e.probe_consultant_42s import MATERIAL
from e2e.probe_consultant_prompt_cost import QUESTION
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.consultant.consultant import method_prompt
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.settings_context import using_settings
from dialectical_framework.utils.call_census import call_census

REPS = int(os.getenv("DIALEXITY_PROBE_REPS", "3"))
MODELS = [
    m.strip()
    for m in os.getenv(
        "DIALEXITY_PROBE_MODELS",
        "global.anthropic.claude-sonnet-5,"
        "global.anthropic.claude-sonnet-5-5,"
        "global.anthropic.claude-opus-5-5",
    ).split(",")
    if m.strip()
]
#: USD per MTok (input, output), first-party list price.
PRICE = {"sonnet-5-5": (2.0, 10.0), "opus-5-5": (4.0, 20.0), "sonnet-5": (2.0, 10.0)}


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class ReplyDto(BaseModel):
    message: str = Field(description="The reply")


class TetradLikeDto(BaseModel):
    t_plus: str = Field(description="How the thesis, developed well, balances the antithesis; ~7 words")
    t_minus: str = Field(description="How the thesis, overdone, undermines the antithesis; ~7 words")
    a_plus: str = Field(description="How the antithesis, developed well, balances the thesis; ~7 words")
    a_minus: str = Field(description="How the antithesis, overdone, undermines the thesis; ~7 words")
    balance: float = Field(description="0.0-1.0: how symmetric the four aspects are")


TETRAD_ASK = (
    "Thesis: 'Keep the cofounder and rebuild trust.' Antithesis: 'Buy the "
    "cofounder out now.' Give the four aspects and a balance score in the schema."
)


@llm.tool
async def keep_for_later(tension: str) -> str:
    """Keep a tension the person named, to work through later. Only when they ask."""
    return "Kept."


def _price(model: str) -> tuple[float, float]:
    for key in sorted(PRICE, key=len, reverse=True):
        if key in model:
            return PRICE[key]
    return (0.0, 0.0)


def _row(model: str, census, seconds: float, extra: str = "") -> dict:
    first = census.calls[0] if census.calls else None
    prefill = sum(
        (getattr(first, k, None) or 0)
        for k in ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens")
    ) if first else 0
    out = (getattr(first, "output_tokens", None) or 0) if first else 0
    p_in, p_out = _price(model)
    return {
        "s": seconds,
        "out": out,
        "prefill": prefill,
        "usd": (prefill * p_in + out * p_out) / 1e6,
        "extra": extra,
    }


def _print(label: str, rows: list[dict]) -> None:
    med = lambda k: statistics.median(r[k] for r in rows)  # noqa: E731
    extras = ",".join(r["extra"] for r in rows if r["extra"]) or "-"
    print(
        f"  {label:44s} n={len(rows)}  {med('s'):6.1f}s  out {med('out'):6.0f}  "
        f"prefill {med('prefill'):6.0f}  ${med('usd'):.4f}  tools={extras}"
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_effort_baseline(di_container):
    system = method_prompt()
    utterance = MATERIAL + "\n\n" + QUESTION
    for model in MODELS:
        print(f"\n== {model}")
        settings = di_container.settings().model_copy(
            update={"ai_model": f"bedrock/{model}", "reasoning_model": None}
        )
        with using_settings(settings):
            for level in (None, "low", "medium", "high"):
                rows = []
                for _ in range(REPS):
                    f = ConversationFacilitator(
                        tools=[keep_for_later], conversation_thinking=level
                    )
                    f.set_system_prompt(system)
                    with call_census() as census:
                        t0 = time.monotonic()
                        try:
                            await f.submit(ReplyDto, utterance)
                            extra = "+".join(f.last_tool_calls)
                        except Exception as e:  # noqa: BLE001
                            extra = f"ERR {type(e).__name__}"
                        dt = time.monotonic() - t0
                    rows.append(_row(model, census, dt, extra))
                _print(f"conversation, thinking {level or 'off'}", rows)
            for name, kwargs in (
                ("structured, default (concern path)", {}),
                ("structured, json + thinking medium", {"format_mode": "json", "thinking": "medium"}),
            ):
                rows = []
                for _ in range(REPS):
                    with call_census() as census:
                        t0 = time.monotonic()
                        try:
                            await ConversationFacilitator(**kwargs).submit(TetradLikeDto, TETRAD_ASK)
                            extra = ""
                        except Exception as e:  # noqa: BLE001
                            extra = f"ERR {type(e).__name__}"
                        dt = time.monotonic() - t0
                    rows.append(_row(model, census, dt, extra))
                _print(name, rows)
