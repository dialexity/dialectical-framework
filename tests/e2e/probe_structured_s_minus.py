"""Did the structured-output constraint (2.0.8) flatten `TransformationSketch`'s S-?

The first app's wisdom eval (27 frozen tetrads x 2, Sonnet 5.5, judge Opus 4.8,
this repo's third-trap auditor) read S- as a THIRD failure in 63% of cards on
pypi-2.0.7 and in 41% / 33% on 2.0.8 under two different app text prompts
(paired v14 -> v16: -30, CI -47..-12). S- comes from `TransformationSketch`,
which no app text reaches, and 2.0.8's only change on a Sonnet 5.5 structured
call is `output_config.format` (`format_compat.structured_output_format`): the
SDK's strict transform of the DTO as a JSON-schema constraint on the reply.
The transform loses nothing here (twelve required strings; descriptions and
order intact, `required` in field order, and the API keeps required keys in
schema order), so if the constraint costs S- it is the constrained decoding or
the format prompt the API injects beside Mirascope's, not a dropped instruction.

Same 25 frozen tetrads as the gate (`probe_transformation_sketch.py`), its
shipped `current` arm (the shipped text and DTO), the SAME writer call —
`_write` — with ONE difference between the arms: whether the provider attaches
the constraint. `structured` is what ships; `json_only` is 2.0.7's shape
(the probe patches `bedrock_provider.structured_output_format` to None, as
`probe_card_replay.py` does under `DIALEXITY_PROBE_STRUCTURED=0`). Further
arms are candidate fixes, each a constraint-on variant (see `ARMS`). The patch
is process-global, so an arm's writes run as a block; blocks alternate per rep
so a provider condition lands on both arms.

Judges, per output, all on the judge model: the third-trap auditor
(`probe_synthesis_arms_theory2._third_trap`, the app's), the transition auditor
(`TransitionVerdict`), and S- crossed pairwise against `structured` in BOTH
orders. Every binary read is a paired delta against `structured` with a 95% CI.
Per-item outputs and verdicts persist to `results/tetrad_quality/`.

Result (2026-10-09, Sonnet 5.5 writer, Opus 4.8 judge, 100 pairs per arm;
the table with every arm is in `docs/dev-notes/one-shot-transformation.md`):
the constraint cost S- as a distinct third failure 57% → 42% (+15 for 2.0.7's
shape, CI +2..+28; the constrained reference replicated at 44/41/42/41) and
helped Ac-/Re- (94-98% valid against 91-93%). Naming the in-turn forms in
`SYNTHESIS_SHAPE` and the `s_minus` description (`shape_then`, now shipped)
restored S- (+15, replicated +16, both clear) with the constraint kept; on
Sonnet 5 it is neutral (−1). The pairwise "more specific" read prefers the
trap-restating headline and is not a shape read (`shape_then_particular`:
60-19 on it, +2 on the shape). The shipped text now carries the in-turn
forms, so `structured` is that text under the constraint, `pre_fix` is the
text before it (for a replication), `think_low` and `particular` are the
shipped text with one change each, and `json_only` is the constraint off.

    poetry run pytest tests/e2e/probe_structured_s_minus.py --real-llm -q -s
    DIALEXITY_PROBE_MODELS=bedrock/global.anthropic.claude-sonnet-5-5 \\
    DIALEXITY_PROBE_JUDGE_MODEL=bedrock/global.anthropic.claude-opus-4-8 \\
    PROBE_ARMS=structured,json_only,pre_fix PROBE_REPS=2
    PROBE_JUDGE_FILE=<a run's json>   # phase B only, on its saved writes
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import pytest
from pydantic import BaseModel, Field, create_model

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import transformation_sketch as ts
from dialectical_framework.utils import bedrock_provider
from dialectical_framework.utils.call_census import call_census
from e2e.modelctx import using_model
from e2e.probe_synthesis_arms_rejudge import _crossed
from e2e.probe_synthesis_arms_theory2 import _third_trap
from e2e.probe_transformation_sketch import (_CASES, _RESULTS, _SYNTHESIS_WORDS,
                                             _TRANSITION_WORDS, _transitions, _view)

WRITER = os.getenv("DIALEXITY_PROBE_MODELS", "bedrock/global.anthropic.claude-sonnet-5-5")
JUDGE = os.getenv("DIALEXITY_PROBE_JUDGE_MODEL", "bedrock/global.anthropic.claude-opus-4-8")
REPS = int(os.getenv("PROBE_REPS", "2"))
_CONCURRENCY = 6


# --- The arms ------------------------------------------------------------------

#: Arm name -> (constraint on?, DTO, system prompt, facilitator factory). The
#: DTO/system pair is the shipped one unless a candidate fix says otherwise;
#: the factory is the shipped call's (`TransformationSketch.resolve`: a plain
#: facilitator, forced tool use substituted by JSON at the provider, thinking
#: off) unless an arm sends thinking.
_Arm = tuple[bool, type[BaseModel], str, Callable[[], ConversationFacilitator]]
ARMS: dict[str, _Arm] = {
    "structured": (True, ts.TransformationSketchDto, ts.SYSTEM_PROMPT, ConversationFacilitator),
    "json_only": (False, ts.TransformationSketchDto, ts.SYSTEM_PROMPT, ConversationFacilitator),
}


def _register_fix_arms() -> None:
    """Candidate fixes, constraint ON. Added as hypotheses are formed; each one
    changes exactly one thing against `structured`."""
    # no_docstring: the DTO's class docstring (its measurement history, "S-
    # unchanged (third failure 75% / 75%)" included) is the schema's top-level
    # `description` and travels in the constraint AND in Mirascope's JSON
    # instruction. Same fields, same descriptions, no docstring.
    fields = {
        name: (str, Field(description=info.description))
        for name, info in ts.TransformationSketchDto.model_fields.items()
    }
    bare = create_model("TransformationSketchDto", **fields)
    bare.__doc__ = None
    ARMS["no_docstring"] = (True, bare, ts.SYSTEM_PROMPT, ConversationFacilitator)
    # s_scaffold: the lever that landed Ac-/Re- (name the ends BEFORE the line),
    # applied to S-: the writer describes the ONE state Ac- and Re- produce in
    # a sentence before the headline. Under the constraint the reply is compact
    # and terse, and S- came back as the two traps side by side or in turn
    # ("X, then Y") more often; a sentence written first is where the state
    # gets named as a thing in itself. Same fields, one inserted.
    scaffolded: dict[str, Any] = {}
    for name, info in ts.TransformationSketchDto.model_fields.items():
        if name == "s_minus":
            scaffolded["s_minus_state"] = (str, Field(description=(
                "What Ac- and Re- produce when both run at once — ONE state, described "
                "in a sentence as a thing in itself (what it is, what it does to the "
                "situation), and how it differs from T- and from A-. Not the two traps "
                "side by side, in turn, or as a choice."
            )))
        scaffolded[name] = (str, Field(description=info.description))
    ARMS["s_scaffold"] = (True, create_model("TransformationSketchDto", **scaffolded), ts.SYSTEM_PROMPT, ConversationFacilitator)
    # pretty: under the constraint the reply came back as ONE compact line with
    # terser texts (`probe_structured_wire.py`), where 2.0.7's reply was
    # pretty-printed. Is the register the mechanism? One line of system text.
    ARMS["pretty"] = (True, ts.TransformationSketchDto,
                      ts.SYSTEM_PROMPT + "\n\nWrite the JSON pretty-printed, one field per line.",
                      ConversationFacilitator)
    # think_low: the call thinks (adaptive, effort low) — the one opt-in the
    # structured path has (`format_mode="json", thinking=`), as the two tetrad
    # writers use it. Constraint on, explicit JSON mode. Costs latency.
    ARMS["think_low"] = (True, ts.TransformationSketchDto, ts.SYSTEM_PROMPT,
                         lambda: ConversationFacilitator(format_mode="json", thinking="low"))
    # pre_fix: the shipped text BEFORE 2026-10-09 — the shape rule and the
    # `s_minus` description without the in-turn forms — for a replication of
    # the finding against the current text (`structured`). The fix: under the
    # constraint 13-14 of ~58 failures per 100 were the two traps IN TURN
    # ("X, then Y", "X alternating with Y") against 4 of 43 without it, and
    # the rule named only the side-by-side forms.
    shipped_shape = ('"Either X or Y", "X versus Y", "X while Y", "X, then Y" and "X alternating '
                     'with Y" with X and Y the two traps are the inputs listed, side by side or in '
                     'turn, not the collapse named.')
    assert shipped_shape in ts.SYNTHESIS_SHAPE, "SYNTHESIS_SHAPE changed shape"
    pre_fix_shape = ('"Either X or Y", "X versus Y" and "X while Y" with X and Y the two traps '
                     'are the inputs listed, not the collapse named.')
    shipped_tail = "Never 'either X or Y', 'X then Y' or 'X alternating with Y'."
    pre_fix_fields: dict[str, Any] = {}
    for name, info in ts.TransformationSketchDto.model_fields.items():
        desc = info.description
        if name == "s_minus":
            assert desc.endswith(shipped_tail), "s_minus description changed"
            desc = desc[: -len(shipped_tail)] + "Never 'either X or Y'."
        pre_fix_fields[name] = (str, Field(description=desc))
    ARMS["pre_fix"] = (True, create_model("TransformationSketchDto", **pre_fix_fields),
                       ts.SYSTEM_PROMPT.replace(shipped_shape, pre_fix_shape), ConversationFacilitator)
    # particular: the shipped text with the headline asked for "in this
    # situation's own particulars". Won the pairwise specificity read 60-19
    # and lost the whole shape gain (+2): that read rewards the traps named
    # concretely, which the rule forbids. Kept as the demonstration.
    particular_fields: dict[str, Any] = {}
    for name, info in ts.TransformationSketchDto.model_fields.items():
        desc = info.description
        if name == "s_minus":
            desc = desc.replace(
                "neither T- nor A- on its own.",
                "neither T- nor A- on its own, named in this situation's own particulars "
                "(who does what, what it costs), not as an abstraction.",
            )
            assert "particulars" in desc
        particular_fields[name] = (str, Field(description=desc))
    ARMS["particular"] = (True, create_model("TransformationSketchDto", **particular_fields),
                          ts.SYSTEM_PROMPT, ConversationFacilitator)


_register_fix_arms()


@contextmanager
def _constraint(on: bool) -> Iterator[None]:
    """The provider's constraint hook, on or off. Process-global, like the
    model switch, so arms are written as blocks."""
    if on:
        yield
        return
    previous = bedrock_provider.structured_output_format
    bedrock_provider.structured_output_format = lambda *_: None  # type: ignore[assignment]
    try:
        yield
    finally:
        bedrock_provider.structured_output_format = previous  # type: ignore[assignment]


async def _write(dto: type[BaseModel], system: str, make: Callable[[], ConversationFacilitator],
                 t: dict[str, Any]) -> dict[str, Any]:
    try:
        with call_census() as census:
            conversation = make()
            conversation.set_system_prompt(system)
            out = await conversation.submit(
                dto,
                ts.transformation_sketch_prompt(_view(t), t["utterance"], _TRANSITION_WORDS, _SYNTHESIS_WORDS),
            )
        return {"out": out.model_dump(), "calls": len(census.calls)}
    except Exception as exc:  # noqa: BLE001
        return {"out": {"error": f"{type(exc).__name__}: {exc}"}, "calls": None}


def _paired(rows: list[dict[str, Any]], arm: str, metric: str, ref_arm: str = "structured") -> str:
    ref = {(r["id"], r["rep"]): r for r in rows if r["arm"] == ref_arm}
    d = [r[metric] - ref[(r["id"], r["rep"])][metric] for r in rows
         if r["arm"] == arm and (r["id"], r["rep"]) in ref
         and r.get(metric) is not None and ref[(r["id"], r["rep"])].get(metric) is not None]
    if not d:
        return "n/a"
    mean = sum(d) / len(d)
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / max(1, len(d) - 1))
    half = 1.96 * sd / math.sqrt(len(d))
    clears = "clears" if (mean - half > 0 or mean + half < 0) else "within noise"
    return f"{100 * mean:+.0f} ({100 * (mean - half):+.0f}..{100 * (mean + half):+.0f}, {clears}, n={len(d)})"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_structured_s_minus(di_container) -> None:
    arms = [a for a in os.getenv("PROBE_ARMS", "structured,json_only").split(",") if a]
    assert "structured" in arms, "every delta is paired against `structured`"
    unknown = set(arms) - set(ARMS)
    assert not unknown, f"unknown arms {unknown}; known {list(ARMS)}"
    tetrads = [json.loads(x) for x in _CASES.read_text().splitlines() if x.strip()]
    out = _RESULTS / f"structured_s_minus-{time.strftime('%Y%m%d-%H%M%S')}.json"
    gate = asyncio.Semaphore(_CONCURRENCY)
    print(f"\nwriter {WRITER} | judge {JUDGE} | arms {arms} | {len(tetrads)} tetrads x {REPS} reps")

    async def write(arm: str, t: dict[str, Any], rep: int) -> dict[str, Any]:
        _, dto, system, make = ARMS[arm]
        async with gate:
            started = time.monotonic()
            w = await _write(dto, system, make, t)
            return {"arm": arm, "id": t["id"], "rep": rep, "out": w["out"], "calls": w["calls"],
                    "write_s": round(time.monotonic() - started, 1)}

    rows: list[dict[str, Any]] = []
    saved = os.getenv("PROBE_JUDGE_FILE")  # judge an earlier run's writes (phase A done)
    if saved:
        out = Path(saved)
        rows = [r for r in json.loads(out.read_text()) if r["arm"] in arms]
        print(f"  judging {len(rows)} saved writes from {out.name}")
    else:
        with using_model(di_container, WRITER):  # phase A, arm blocks alternating per rep
            for rep in range(REPS):
                for arm in arms:
                    with _constraint(ARMS[arm][0]):
                        rows.extend(await asyncio.gather(*(write(arm, t, rep) for t in tetrads)))
                    print(f"  wrote {arm} rep {rep}: {sum(1 for r in rows if r['arm'] == arm and r['rep'] == rep and 'error' not in r['out'])}/{len(tetrads)}")
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    by_id = {t["id"]: t for t in tetrads}
    reference = {(r["id"], r["rep"]): r for r in rows if r["arm"] == "structured"}

    async def judge_row(r: dict[str, Any]) -> None:
        o, t = r["out"], by_id[r["id"]]
        if "error" in o:
            return
        async with gate:
            tt, tv = await asyncio.gather(
                _third_trap(di_container, JUDGE, t["t_minus"], t["a_minus"], o["s_minus"]),
                _transitions(t, o),
            )
            ref = reference.get((r["id"], r["rep"]))
            if r["arm"] != "structured" and ref and "error" not in ref["out"]:
                r["s_minus_vs_structured"] = await _crossed(di_container, JUDGE, o["s_minus"], ref["out"]["s_minus"])
        r["third_trap"] = tt
        r["third_failure"] = None if not tt.get("kind") else float(tt["kind"] == "third_failure")
        if tv is not None:
            r["transition_verdict"] = tv.model_dump()
            r["ac_valid"] = float(tv.ac_valid)
            r["re_valid"] = float(tv.re_valid)

    with using_model(di_container, JUDGE):  # phase B
        await asyncio.gather(*(judge_row(r) for r in rows))
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    metrics = ("third_failure", "ac_valid", "re_valid")
    print(f"\n--- {out.name} ---")
    for arm in arms:
        mine = [r for r in rows if r["arm"] == arm]
        errors = sum(1 for r in mine if "error" in r["out"])
        calls = [r["calls"] for r in mine if r["calls"] is not None]
        rates = " | ".join(
            f"{m} {100 * sum(r[m] for r in mine if r.get(m) is not None) / max(1, sum(1 for r in mine if r.get(m) is not None)):.0f}%"
            for m in metrics
        )
        kinds: dict[str, int] = {}
        for r in mine:
            k = (r.get("third_trap") or {}).get("kind") or "unjudged"
            kinds[k] = kinds.get(k, 0) + 1
        print(f"  {arm:12} {rates} | calls/write {sum(calls) / max(1, len(calls)):.2f} | errors {errors} | {kinds}")
    for arm in arms:
        if arm == "structured":
            continue
        print(f"  {arm} - structured:")
        for m in metrics:
            print(f"    {m:13} {_paired(rows, arm, m)}")
        pair = [r.get("s_minus_vs_structured") for r in rows if r["arm"] == arm]
        print(f"    S- crossed vs structured: {arm} {pair.count('x')}, structured {pair.count('y')}, "
              f"same {pair.count('same')}, order-bound {pair.count('order_bound')}")
