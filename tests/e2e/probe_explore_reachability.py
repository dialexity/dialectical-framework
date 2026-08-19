"""Probe: can the WEAK tier reach `explore` at all, and what gates it?

Pooled over every saved bench run, weak-tier A2 calls `explore` in 6/55 runs
(11%) against strong's 17/25 (68%). At p=0.11, P(0 of 6) = 0.50 — so r7's 0/6 is
the modal outcome and r6's 2/6 was the outlier. The question is not "what
regressed" but "what gates the weak tier".

The Advisor's system prompt is STATIC after construction, so in a fresh session
the Current Understanding dump reads "No prior understanding" for the whole
conversation. The model's only view of what it just built is the `anchor` tool
result — measured at ~1.2k tokens (thesis-only) to ~2.7k (both sides), with
`perspective_hashes` at 62%/94% depth and the `summary` line naming no hash.

Two candidate gates, distinguished by the second condition below:
  A. RETRIEVAL — the model cannot get hashes out of the payload. If so, a
     `sync` (which re-renders the graph as prose, hashes included) immediately
     before the ask should unblock it.
  B. INTENT — the model does not judge exploration necessary, in which case
     handing it the hashes changes nothing.

Run with --real-llm. Costs money; this is a diagnostic, not a test.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

from e2e.config import E2EConfig
from e2e.modelctx import using_model

PERSONA = (
    "You are a thoughtful advisor helping someone navigate a difficult "
    "situation. Be direct and concrete."
)

OPENER = (
    "I need to decide whether to buy out my cofounder. He holds 45% equity. "
    "Two anchor accounts are 60% of our revenue and both CEOs call him, not "
    "me. I gave him feedback in March and nothing changed since. I keep going "
    "back and forth on this."
)

# An explicit, unmistakable request for what `explore` does. If the weak tier
# will not call it HERE, no ordinary conversational beat will trigger it.
FOLLOW = (
    "Map this out properly for me: I want to see how these tensions connect "
    "causally, and what the paired path forward looks like — not just the "
    "tensions listed one by one."
)


async def _run(label: str, model: str, container, *, nudge_sync: bool) -> list[str]:
    case = Case()
    case.commit()
    with scope(case.sid):
        with using_model(container, model):
            advisor = Advisor(app_preamble=PERSONA, principal="agent:probe")
            tools: list[str] = []

            await advisor.chat(OPENER)
            t1 = list(advisor._conversation.last_tool_calls)
            tools += t1

            if nudge_sync:
                await advisor.chat(
                    "Before you answer: re-read what you have on file so far."
                )
                tools += list(advisor._conversation.last_tool_calls)

            reply = await advisor.chat(FOLLOW)
            t_last = list(advisor._conversation.last_tool_calls)
            tools += t_last

    print(f"\n=== {label} (nudge_sync={nudge_sync})")
    print(f"    tools: {tools}")
    print(f"    explore called: {'explore' in tools}")
    print(f"    reply head: {reply[:400]!r}")
    return tools


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_weak_vs_strong_explore(di_container):
    cfg = E2EConfig.from_env()
    weak = cfg.tiers["weak"]
    strong = cfg.tiers["strong"]
    print(f"\nweak={weak}\nstrong={strong}")

    results = {}
    results["weak/no-nudge"] = await _run("WEAK", weak, di_container, nudge_sync=False)
    results["weak/sync-nudge"] = await _run("WEAK", weak, di_container, nudge_sync=True)
    results["strong/no-nudge"] = await _run(
        "STRONG", strong, di_container, nudge_sync=False
    )

    print("\n=== SUMMARY ===")
    for k, v in results.items():
        print(f"  {k:18} explore={'explore' in v}  tools={v}")
