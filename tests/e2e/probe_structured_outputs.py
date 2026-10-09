"""Does Bedrock take structured outputs (`output_config.format`) on the models
the framework runs, and with the thinking shapes it sends?

Why: on the 5.5 models every structured call goes in JSON mode (forced tool use
is a 400 there), and a host measured the price of that — 32 parse re-asks in
80 cards on Sonnet 5.5 (trailing commas, invalid JSON), each a whole extra call.
A schema-constrained output removes the class; this probe says whether the
provider accepts it through the legacy `AnthropicBedrock` client the framework
uses, with the thinking shape each model gets, and with a real DTO's schema.

Run:
    poetry run pytest tests/e2e/probe_structured_outputs.py --real-llm -s
    DIALEXITY_PROBE_MODELS="global.anthropic.claude-opus-5-5" ...
"""

from __future__ import annotations

import json
import os

import pytest
from anthropic import AsyncAnthropicBedrock
from anthropic.lib._parse._transform import transform_schema

from dialectical_framework.concerns.transformation_sketch import TransformationSketchDto
from dialectical_framework.concerns.view_sketch import ViewSketchDto

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

SMALL = {
    "type": "object",
    "properties": {"word": {"type": "string"}, "why": {"type": "string"}},
    "required": ["word", "why"],
    "additionalProperties": False,
}


def _thinking_shapes(model: str) -> dict[str, dict]:
    shapes: dict[str, dict] = {"no thinking param": {}}
    shapes["adaptive low"] = {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}
    shapes["adaptive medium"] = {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}}
    if "sonnet-5-5" in model:
        shapes["between_tools"] = {"thinking": {"type": "between_tools"}}
    elif "5-5" not in model:
        shapes["disabled"] = {"thinking": {"type": "disabled"}}
    return shapes


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_structured_outputs_raw():
    client = AsyncAnthropicBedrock()
    schemas = {
        "small": SMALL,
        "ViewSketchDto": transform_schema(ViewSketchDto),
        "TransformationSketchDto": transform_schema(TransformationSketchDto),
    }
    asks = {
        "small": "Name a colour in one word and say why in one sentence.",
        "ViewSketchDto": (
            "The person said: 'I think I should stop lending money to my brother.' "
            "Draw one tension: their position, what it stands against, and the four "
            "developments, each under 10 words."
        ),
        "TransformationSketchDto": (
            "Tetrad: T 'Stop lending money to my brother', A 'Keep helping my brother', "
            "T+ 'A clear limit framed as care', T- 'Cut him off and let him sink', "
            "A+ 'Help him build self-sufficiency', A- 'Bail him out, no questions'. "
            "Fill every field briefly."
        ),
    }
    for model in MODELS:
        print(f"\n== {model}")
        for schema_name, schema in schemas.items():
            for shape_name, extra in _thinking_shapes(model).items():
                extra = json.loads(json.dumps(extra))
                output_config = dict(extra.pop("output_config", {}))
                output_config["format"] = {"type": "json_schema", "schema": schema}
                label = f"{schema_name} / {shape_name}"
                try:
                    r = await client.messages.create(
                        model=model,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": asks[schema_name]}],
                        output_config=output_config,
                        **extra,
                    )
                    text = next((b.text for b in r.content if b.type == "text"), "")
                    try:
                        json.loads(text)
                        parsed = "json ok"
                    except Exception as e:  # noqa: BLE001
                        parsed = f"JSON INVALID: {e}"
                    kinds = [b.type for b in r.content]
                    print(
                        f"  {label:44s} OK   stop={r.stop_reason} blocks={kinds} "
                        f"out={r.usage.output_tokens} {parsed} :: {text[:80]!r}"
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"  {label:44s} FAIL {type(e).__name__}: {str(e)[:260]}")
