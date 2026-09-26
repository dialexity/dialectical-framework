"""probe_consultant_42s — where do the Consultant's 38 seconds go on a REAL-sized graph?

`ladder-sonnet` (Sonnet 5, 4 perspectives / 42 transformations, ~26k-char dump):
the Consultant's turns that elected NO tool took a median 38.5s of reply path
against 9.8s for the static dump of the same graph, same model, same persona
(recomputed 2026-09-24 from `ladder-sonnet-judged.json`: 16 no-tool A2c turns,
reply 20% longer). `probe_consultant_prompt_cost.py` attributed the Consultant's
turn on Sonnet to tool round trips at ~5s each — but it measured on a 3-perspective
seed with a 2.4k dump, where the main call was 5-6s. Nothing has measured the
no-tool call on a graph the size the bench actually consults.

So: build a real graph with the headless pipeline (the documented recipe), then
the same 2x2 the earlier probe used, plus the census columns that tell a double
call from a slow call:

    A  Consultant as shipped         engine + tools, `Advisor.chat`
    B  A1.5 as the bench runs it     method text + dump, no tools
    C  engine text, no tools         is it the TEXT at this size?
    E  engine + tools, bare          A without the Advisor's plumbing

Per rep and condition: seconds, the reply call's seconds, `calls` (every
provider call the census saw — a clean no-tool turn is 1, plus the off-path
repair for A), `extractions` (ChatResponse-format calls — 0 means the reply was
reused, 1 means the structured fallback fired and the turn paid twice),
prefill split into uncached / cache read / cache write, output tokens, tools.

NOT free: `--real-llm`; one headless build (~5-8 min on Sonnet) + REPS x 4 turns.

    DIALEXITY_PROBE_REPS=3 poetry run pytest tests/e2e/probe_consultant_42s.py --real-llm -s

RESULT (2026-09-24, Sonnet 5, 5 perspectives / 36 transformations, medians of 3):

    condition                        BEFORE turn  call  out tok     AFTER turn  call  out tok
    A Consultant (engine+tools)         45.9s  42.4s   3192          24.4s  15.7s   778
    B A1.5 (method+dump, no tools)      13.1s  13.1s    733          13.3s  13.3s   740
    C engine, no tools                  13.0s  13.0s    668          13.1s  13.1s   673
    E engine+tools, bare                46.3s  46.3s   3544          14.1s  14.1s   762

One call, no fallback, no tool elected, prefill within 10%: the tool-wired call emitted
~2,500 output tokens the reply did not contain. `probe_tool_path_hidden_output.py` showed
them to be a `thinking` block — Bedrock's DEFAULT for Claude 5 is adaptive thinking on,
and the framework sent no `thinking` key when no level was set. `with_thinking_compat`
now sends "disabled" where unset would think (AFTER column). The Consultant's remaining
gap over the dump is ~2s on the call; A's `turn` also carries a fresh Advisor's first
render and the off-path closing check.
"""

from __future__ import annotations

import os
import statistics
import time

import pytest

from e2e.arms import _STATIC_CONTEXT_INTRO, method_prompt
from e2e.config import DEFAULT_TIER_STRONG
from e2e.driver import E2E_PERSONA
from e2e.modelctx import using_model
from e2e.probe_consultant_prompt_cost import QUESTION, _prompt_text
from e2e.scenarios import COFOUNDER

from dialectical_framework.agents.advisor.advisor import (
    Advisor, ChatResponse, _build_tools)
from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.advisor.tools.explore import \
    run_exploration_detailed
from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census

REPS = int(os.getenv("DIALEXITY_PROBE_REPS", "3"))
MODEL = os.getenv("DIALEXITY_PROBE_MODEL", DEFAULT_TIER_STRONG)
K = int(os.getenv("DIALEXITY_PROBE_K", "3"))

#: The person's situation as material — the scenario persona plus its literal
#: opener, which is what the bench's builder hears in session 1.
MATERIAL = COFOUNDER.persona + "\n\n" + COFOUNDER.sessions[0].beats[0].text
INTENT = "Should the founder buy out the checked-out cofounder, and at what price?"


def _census_columns(census) -> dict:
    chats = [r for r in census.calls if r.format_name == "ChatResponse"]
    main = max(census.calls, key=lambda r: (r.prefill_tokens or 0)) if census.calls else None
    return {
        "calls": census.count,
        "extractions": len(chats),
        "call_s": round(main.seconds, 1) if main else None,
        "uncached": main.uncached_input_tokens if main else None,
        "cache_read": main.cache_read_tokens if main else None,
        "cache_write": main.cache_write_tokens if main else None,
        "output": main.output_tokens if main else None,
        "all_calls": [(r.label[:40], round(r.seconds, 1), r.output_tokens) for r in census.calls],
    }


async def _run_advisor() -> dict:
    advisor = Advisor(app_preamble=E2E_PERSONA, build=BuildPolicy.NEVER, principal="agent:probe")
    with call_census() as census:
        reply = await advisor.chat(QUESTION)
    timing = advisor.last_turn_timing
    out = _census_columns(census)
    out.update(
        seconds=timing.reply_path_s if timing else None,
        render=timing.context_render_s if timing else None,
        words=len(reply.split()),
        prompt_chars=len(_prompt_text(advisor)),
        tools=list(advisor._conversation.last_tool_calls),
    )
    return out


async def _run_facilitator(system: str, tools) -> dict:
    conversation = ConversationFacilitator(tools=tools)
    conversation.set_system_prompt(system)
    with call_census() as census:
        result = await conversation.submit(ChatResponse, QUESTION)
    out = _census_columns(census)
    out.update(
        seconds=conversation.last_submit_seconds,
        render=0.0,
        words=len(result.message.split()),
        prompt_chars=len(system),
        tools=list(conversation.last_tool_calls),
    )
    return out


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(2400)
async def test_probe_consultant_42s(di_container):
    case = Case()
    case.commit()
    print(f"\nmodel: {MODEL}  thinking: {di_container.settings().conversation_thinking_level!r}")
    with scope(case.sid), using_model(di_container, MODEL):
        started = time.monotonic()
        analysis = await AnalysisPipeline(text=MATERIAL, intent=INTENT).resolve()
        hashes = list(analysis.perspective_hashes)[:K]
        created = await CreateNexus().resolve(intent=INTENT, perspective_hashes=hashes)
        _report, transformations = await run_exploration_detailed(hashes, INTENT, created.nexus.hash)
        print(
            f"build: {len(analysis.perspective_hashes)} perspectives ({len(hashes)} woven), "
            f"{len(transformations)} transformations in {time.monotonic() - started:.0f}s"
        )

        dump = await DialecticalContext().resolve()
        engine_advisor = Advisor(app_preamble=E2E_PERSONA, build=BuildPolicy.NEVER)
        await engine_advisor._refresh_context()
        engine_prompt = _prompt_text(engine_advisor)
        method = "\n\n".join([E2E_PERSONA, method_prompt(), _STATIC_CONTEXT_INTRO + dump])
        print(f"dump {len(dump)}c | engine prompt {len(engine_prompt)}c | method prompt {len(method)}c")

        conditions = {
            "A Consultant (engine+tools)": _run_advisor,
            "B A1.5 (method+dump, no tools)": lambda: _run_facilitator(method, None),
            "C engine, no tools": lambda: _run_facilitator(engine_prompt, None),
            "E engine+tools, bare": lambda: _run_facilitator(engine_prompt, _build_tools("agent:probe", build=BuildPolicy.NEVER)),
        }
        results: dict[str, list[dict]] = {k: [] for k in conditions}
        for rep in range(REPS):
            for name, run in conditions.items():
                out = await run()
                results[name].append(out)
                print(
                    f"  rep {rep + 1} {name:32s} {out['seconds']:6.1f}s  call={out['call_s']}s "
                    f"calls={out['calls']} extractions={out['extractions']} "
                    f"prefill u/r/w={out['uncached']}/{out['cache_read']}/{out['cache_write']} "
                    f"out={out['output']} words={out['words']} tools={out['tools']}"
                )
                if out["calls"] > 1:
                    print(f"        calls: {out['all_calls']}")

        print("\nmedians:")
        for name, rows in results.items():
            print(
                f"  {name:32s} turn {_median([r['seconds'] for r in rows]):6.1f}s  "
                f"call {_median([r['call_s'] for r in rows])}s  "
                f"extractions {_median([r['extractions'] for r in rows])}  "
                f"prefill {_median([(r['uncached'] or 0) + (r['cache_read'] or 0) + (r['cache_write'] or 0) for r in rows])}  "
                f"out {_median([r['output'] for r in rows])}  words {_median([r['words'] for r in rows])}"
            )
    assert all(results[k] for k in results)
