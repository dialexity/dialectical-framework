"""
probe_consultant_prompt_cost — WHY is a Consultant turn ~16s when A1.5 answers in ~6s?

`consultant-cache` (2026-09-18) left one difference standing between the two
arms over the SAME graph and model: the render is cached (0.01s), tools cost
7s over 16 turns, reply length matches — so what remains is the prompt itself,
the full engine (~17k tokens) plus six tool schemas against A1.5's rewritten
method text. That is a hypothesis, and a trimmed consultant render built on it
would be a prompt-design change with a quality risk. So this measures the
mechanism first, with a 2x2 that holds everything else fixed:

    A  engine prompt  + tools      the Consultant as shipped (`Advisor.chat`)
    B  method text    + no tools   A1.5 as the bench runs it
    C  engine prompt  + no tools   is it the TEXT?
    D  method text    + tools      is it the TOOLS (schemas, tool-use mode)?

Same built graph (the richest Case still in Memgraph, or `DIALEXITY_PROBE_SID`),
same dump, same persona, same question, same weak-tier model, fresh conversation
per rep, conditions interleaved so provider drift falls on all four alike.
Seconds are the person's wait for the reply (`reply_path_s` for A, which
excludes the off-path closing seam; `last_submit_seconds` for the rest), and
prefill tokens come from the call census so the size difference is a number
and not a guess.

    E  engine prompt  + tools      A through a bare facilitator — isolates the
                                   Advisor's own plumbing from the provider call

NOT free: `--real-llm`, ~REPS x 5 calls of ~3-15s each.

    DIALEXITY_PROBE_REPS=5 poetry run pytest \
        tests/e2e/probe_consultant_prompt_cost.py --real-llm -s

RESULT (2026-09-18, haiku weak tier, seed graph of 3 perspectives, 2,380c dump;
median of 4-5 reps, conditions interleaved):

    condition               DIALEXITY_CONVERSATION_THINKING_LEVEL=medium      unset
                            turn s   call s  out tok  tools    turn s  out tok
    A engine+tools          12.18     9.5     674     0.5       5.80    191
    B method+no tools        2.88     2.9     152     0.0       3.08    163
    C engine+no tools        3.58     3.6     190     0.0       3.99    231
    D method+tools           7.05     4.4     348     1.0       4.87     59*
    E engine+tools (bare)    9.27     9.3     700     0.2       5.44    258
    (* D's recorded call is the tool-electing first round; its reply came on
       the unrecorded resume.)

THE PROMPT-SIZE HYPOTHESIS IS REFUTED. The full engine prompt (16.6k prefill,
64k chars) without tools answers in 3.6s against the method text's 2.9s — the
text costs well under a second. What costs the Consultant its turn is the TOOL
PATH THINKING: `ConversationFacilitator._call_with_tools` passes the configured
`conversation_thinking_level` and `_call_with_response_model` (the path every prompt arm
answers through) never does, so with `medium` set — as it is in this
environment — the tool-enabled call generates ~450 output tokens the reply does
not contain (674 against 190 for ~150 words) and takes 9.5s instead of 3.6s.
Unset, the Consultant lands at 5.8s: ~1s for the engine text over the method
text, ~0.5s render + settle, and 0.3 tool elections a turn (`read_digest`).

ON SONNET 5 (2026-09-19, `DIALEXITY_PROBE_MODEL`) the Haiku finding does NOT
transfer: the main call is ~5-6s with thinking at medium or unset (289 vs 264
output tokens — Sonnet 5's adaptive shape spends almost nothing at "medium"),
and the turn is made of TOOL ROUND TRIPS at ~5s each, 0.8-2.2 elections a turn
(`rounds.md`, `sonnet-thinking`). On a stronger model the lever is elections,
not thinking.

Two consequences. (1) Every bench comparison of an Advisor arm against a prompt
arm in this environment compared a THINKING arm against non-thinking ones, on
latency and on quality alike; the bench never controlled or recorded the level,
and now records it on every cell (`RunRecord.conversation_thinking_level`). (2) Whether
`medium` earns its 6s a turn in counsel quality is unmeasured on this path —
that is the next pre-registered round, not a default to flip here.
"""

from __future__ import annotations

import os
import statistics

import pytest

from dialectical_framework.agents.advisor.advisor import (
    Advisor, ChatResponse, _build_consultant_tools)
from dialectical_framework.agents.advisor.mode import AdvisorMode
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census
from e2e.arms import _STATIC_CONTEXT_INTRO, method_prompt
from e2e.config import DEFAULT_TIER_WEAK
from e2e.driver import E2E_PERSONA
from e2e.modelctx import using_model

QUESTION = (
    "Given everything we've mapped so far, what would you actually do about "
    "the cofounder this month, and what would it cost me?"
)
REPS = int(os.getenv("DIALEXITY_PROBE_REPS", "5"))
#: The model under test; every figure here is model-conditional.
MODEL = os.getenv("DIALEXITY_PROBE_MODEL", DEFAULT_TIER_WEAK)


def _richest_sid(graph_db) -> tuple[str, int, int]:
    forced = os.getenv("DIALEXITY_PROBE_SID")
    query = """
    MATCH (c:Case)
    OPTIONAL MATCH (p:Perspective {sid: c.sid}) WHERE p.hash IS NOT NULL
    WITH c.sid AS sid, count(p) AS pps
    OPTIONAL MATCH (t:Transformation {sid: sid}) WHERE t.hash IS NOT NULL
    RETURN sid, pps, count(t) AS trs
    ORDER BY pps DESC, trs DESC LIMIT 1
    """
    if forced:
        rows = list(
            graph_db.execute_and_fetch(
                query.replace("MATCH (c:Case)", "MATCH (c:Case {sid: $sid})"),
                {"sid": forced},
            )
        )
    else:
        rows = list(graph_db.execute_and_fetch(query))
    assert rows and rows[0]["pps"] > 0, "no built Case in the database to consult"
    return rows[0]["sid"], rows[0]["pps"], rows[0]["trs"]


def _prompt_text(advisor: Advisor) -> str:
    content = advisor._conversation._messages[0].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(getattr(part, "text", str(part)) for part in content)
    return content.text


def _main_call(census):
    """The reply call: the one that asked for ChatResponse, else the largest."""
    chats = [r for r in census.calls if r.format_name == "ChatResponse"]
    pool = chats or list(census.calls)
    return max(pool, key=lambda r: r.prefill_tokens or 0) if pool else None


async def _run_advisor(dump: str) -> dict:
    advisor = Advisor(
        app_preamble=E2E_PERSONA,
        mode=AdvisorMode.CONSULTANT,
        principal="agent:probe",
    )
    with call_census() as census:
        reply = await advisor.chat(QUESTION)
    timing = advisor.last_turn_timing
    main = _main_call(census)
    return {
        "seconds": timing.reply_path_s if timing else None,
        "call_s": main.seconds if main else None,
        "output": main.output_tokens if main else None,
        "render": timing.context_render_s if timing else None,
        "prefill": main.prefill_tokens if main else None,
        "words": len(reply.split()),
        "prompt_chars": len(_prompt_text(advisor)),
        "tools": list(advisor._conversation.last_tool_calls),
    }


async def _run_facilitator(system: str, tools) -> dict:
    conversation = ConversationFacilitator(tools=tools)
    conversation.set_system_prompt(system)
    with call_census() as census:
        result = await conversation.submit(ChatResponse, QUESTION)
    main = _main_call(census)
    return {
        "seconds": conversation.last_submit_seconds,
        "call_s": main.seconds if main else None,
        "output": main.output_tokens if main else None,
        "render": 0.0,
        "prefill": main.prefill_tokens if main else None,
        "words": len(result.message.split()),
        "prompt_chars": len(system),
        "tools": list(conversation.last_tool_calls),
    }


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_consultant_prompt_cost(di_container):
    sid, pps, trs = _richest_sid(di_container.graph_db())
    print(f"\ngraph: sid={sid[:8]} perspectives={pps} transformations={trs}")

    print(f"model: {MODEL}  conversation thinking: {di_container.settings().conversation_thinking_level!r}")
    with scope(sid), using_model(di_container, MODEL):
        dump = await DialecticalContext().resolve()
        # The engine text the Consultant actually carries, with THIS dump in it.
        engine_advisor = Advisor(
            app_preamble=E2E_PERSONA, mode=AdvisorMode.CONSULTANT
        )
        await engine_advisor._refresh_context()
        engine_prompt = _prompt_text(engine_advisor)
        method = "\n\n".join(
            [E2E_PERSONA, method_prompt(), _STATIC_CONTEXT_INTRO + dump]
        )
        print(
            f"dump {len(dump)}c | engine prompt {len(engine_prompt)}c | "
            f"method prompt {len(method)}c"
        )

        conditions = {
            "A engine+tools (Consultant)": lambda: _run_advisor(dump),
            "B method+no tools (A1.5)": lambda: _run_facilitator(method, None),
            "C engine+no tools": lambda: _run_facilitator(engine_prompt, None),
            "D method+tools": lambda: _run_facilitator(
                method, _build_consultant_tools("agent:probe")
            ),
            # E isolates the Advisor's own plumbing (settle, refresh, seam) from
            # the provider call: same text and tools as A, bare facilitator.
            "E engine+tools (bare)": lambda: _run_facilitator(
                engine_prompt, _build_consultant_tools("agent:probe")
            ),
        }
        results: dict[str, list[dict]] = {k: [] for k in conditions}
        for rep in range(REPS):
            for name, run in conditions.items():
                out = await run()
                results[name].append(out)
                print(
                    f"  rep {rep + 1} {name:30s} {out['seconds']:6.1f}s  "
                    f"call={out['call_s']:.1f}s out={out['output']} "
                    f"prefill={out['prefill']}  words={out['words']}  "
                    f"render={out['render']:.2f}  tools={out['tools']}"
                )

    print("\ncondition                        n   median s    min    max   prefill  words  prompt chars  tool calls/turn  main call s  output tok")
    for name, rows in results.items():
        secs = [r["seconds"] for r in rows if r["seconds"] is not None]
        print(
            f"{name:30s} {len(rows):3d}   {_median(secs):7.2f}  "
            f"{min(secs):5.1f}  {max(secs):5.1f}   "
            f"{_median([r['prefill'] for r in rows])!s:>7}  "
            f"{_median([r['words'] for r in rows])!s:>5}  {rows[0]['prompt_chars']:>11}  "
            f"{sum(len(r['tools']) for r in rows) / len(rows):.1f}  "
            f"{_median([r['call_s'] for r in rows])!s:>11}  "
            f"{_median([r['output'] for r in rows])!s:>10}"
        )
    print(
        "\nread: A-C = the tools' price at fixed text; A-D = the engine text's "
        "price at fixed tools; B is the floor A1.5 measured."
    )
