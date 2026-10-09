"""What is on the wire, and what comes back, with the constraint on and off.

Captures the request kwargs `BedrockAnthropicProvider._create_async` sends and
the raw message it receives for the shipped `TransformationSketch` call on a
few tetrads, in both shapes. Reads: the request diff (anything beyond
`output_config.format`?), the reply's content blocks (prose before the JSON?
thinking?), output tokens.

Found (2026-10-09, Sonnet 5.5, 6 tetrads each): the two requests differ in
`output_config.format` and nothing else — same system text (Mirascope's JSON
instruction with the schema, docstring included, is there in both), same
`thinking: between_tools`. Neither reply has prose before the JSON or a
thinking block. What the constraint changes is the REGISTER: the constrained
reply is one compact line (0 newlines, ~290-350 output tokens) with terser
lines; the unconstrained reply is pretty-printed (~320-390 tokens) and ends
with the trailing comma that cost 2.0.7 its parse re-asks. The S- read under
the constraint is `probe_structured_s_minus.py`.

    PROBE_N=6 poetry run pytest tests/e2e/probe_structured_wire.py --real-llm -q -s
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import transformation_sketch as ts
from dialectical_framework.utils import bedrock_provider
from e2e.modelctx import using_model
from e2e.probe_structured_s_minus import WRITER, _constraint
from e2e.probe_transformation_sketch import (_CASES, _RESULTS, _SYNTHESIS_WORDS,
                                             _TRANSITION_WORDS, _view)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_wire(di_container, monkeypatch) -> None:
    n = int(os.getenv("PROBE_N", "6"))
    tetrads = [json.loads(x) for x in _CASES.read_text().splitlines() if x.strip()][:n]
    captured: list[dict[str, Any]] = []
    original = bedrock_provider.BedrockAnthropicProvider._create_async

    async def spy(self, kwargs, params):
        message = await original(self, kwargs, params)
        captured.append({
            "request": {k: v for k, v in bedrock_provider.with_thinking_compat(kwargs["model"], kwargs, params).items()
                        if k not in ("messages",)},
            "last_user": kwargs["messages"][-1],
            "content": [b.model_dump() for b in message.content],
            "usage": message.usage.model_dump(),
            "stop_reason": message.stop_reason,
        })
        return message

    monkeypatch.setattr(bedrock_provider.BedrockAnthropicProvider, "_create_async", spy)
    rows = []
    with using_model(di_container, WRITER):
        for arm in ("structured", "json_only"):
            with _constraint(arm == "structured"):
                for t in tetrads:
                    captured.clear()
                    conversation = ConversationFacilitator()
                    conversation.set_system_prompt(ts.SYSTEM_PROMPT)
                    try:
                        out = await conversation.submit(
                            ts.TransformationSketchDto,
                            ts.transformation_sketch_prompt(_view(t), t["utterance"], _TRANSITION_WORDS, _SYNTHESIS_WORDS),
                        )
                        s_minus = out.s_minus
                    except Exception as exc:  # noqa: BLE001
                        s_minus = f"ERROR {type(exc).__name__}: {exc}"
                    rows.append({"arm": arm, "id": t["id"], "s_minus": s_minus, "calls": list(captured)})
    out_path = _RESULTS / f"structured_wire-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    print(f"\n--- {out_path.name}")
    for r in rows:
        for c in r["calls"]:
            kinds = [b["type"] for b in c["content"]]
            text = "".join(b.get("text", "") for b in c["content"] if b["type"] == "text")
            pre = text[: text.find("{")] if "{" in text else text
            print(f"  {r['arm']:10} {r['id'][:28]:28} out_tok {c['usage'].get('output_tokens')} blocks {kinds} "
                  f"stop {c['stop_reason']} preamble {len(pre.strip())}ch | S-: {r['s_minus']}")
    first = {arm: next(r for r in rows if r["arm"] == arm)["calls"][0]["request"] for arm in ("structured", "json_only")}
    s, j = first["structured"], first["json_only"]
    print("\n  request keys structured:", sorted(s))
    print("  request keys json_only :", sorted(j))
    for k in sorted(set(s) | set(j)):
        if s.get(k) != j.get(k) and k != "system":
            print(f"  differs: {k}: structured={json.dumps(s.get(k))[:300]} json_only={json.dumps(j.get(k))[:300]}")
    print("  system same:", s.get("system") == j.get("system"))
    sys_text = s.get("system")
    print("  system (structured):", json.dumps(sys_text)[:3000])
