"""Does the MOVE keep a decided position, or hand the person back what they refused?

THE OPEN HALF
=============
`probe_decided_stance.py` repaired A+ on decided stances (a good A itself is for,
39% -> 94%, coherence 59% -> 91%, shipped 2026-10-12) and the decision went on
being undone at exactly the same rate: `decision_stands` 62% before, 62% after,
the action corners attaching a condition in 38% of draws either way. With the
clean A+ "The sibling bond outlasts this one rupture" the same writer still
produced Ac+ "Give her a clear route back: apologise to Marco and she's
welcome." — to a person who had written "after what she said about Marco at
christmas she doesnt get to be there. done."

So the undoing has a second site, in the layer the move is written in, and
repairing the corner it reads does not reach it. Two suspects, both in
`transformation_sketch.TRANSFORMATION_POSITIONS`:

- **line 1** defines Ac as "the concrete move that carries T toward A". With a
  decided T, "carry my position toward the other side" reads as *concede part
  of it*. The direction is right (Ac lives in Not-A space, Re in Not-T space);
  the WORDING invites the concession.
- **line 2** has Ac+ "turn T's trap (T-) into A's strength (A+)", which even
  with a correct A+ reads as *go and get the other side some of what it wants*,
  and says nothing about a T the person has settled.

Neither is wrong as theory. What is missing is the distinction the first app put
in its own card text, where it fixed 4 of 7 decided cases: a decided position is
already carried out, and what the other side gets right shapes HOW it is carried
out, never WHETHER or HOW MUCH. This probe asks whether that distinction belongs
in the derivation instead of in the text written from it.

ARMS (each ONE change from `current`, so the two suspects are separable)

    current   what ships; every delta is paired against it
    reach     line 1 only: the action is "the concrete move, made from T, that
              reaches what A is for", the reflection its mirror — both
              directions kept, "carries T toward A" gone
    decided   line 1 as it ships + one sentence on point 2: where T is decided
              or refused, the action is that decision carried out; a condition,
              a trial, one option among others, a partial amount of what was
              refused or a postponement is not the action developed well

A combined arm is deliberately NOT in this run. If both single changes move, the
combination is the follow-up; nesting them here would leave a win unattributable,
which is the mistake `one-shot-transformation.md` records for its arm 1.

PRE-REGISTRATION (written before the run)

  Population: `fixtures/decided_tetrads.jsonl` — the 32 tetrads the SHIPPED
  layer-1 text drew for the 16 decided stances (2 reps each), frozen. The
  corners are held byte-identical across arms, so a move in the endpoint is the
  transformation text's and nothing else's. No outcome selection: all 32 are
  carried, including the 2 whose A+ the layer-1 judge still called a blend.
  3 arms x 32 tetrads x 1 rep = 96 writes.

  PRIMARY  `decision_stands` — the action corners (Ac, Ac+) treat the decision
           as already made and shape HOW it is carried out, rather than
           attaching a condition, a trial, a partial amount, a postponement or a
           trade (`probe_decided_stance._DecisionVerdict`, the same judge and
           the same prompt that measured the 62%).
           Worth shipping iff the paired delta is >= +20 points with its 95% CI
           clear of zero, on at least one arm.
  SECOND   `reflection_stands` — the same of Re/Re+. Expected to move less; the
           app reported it as the occasional second site.
  GUARD 1  Ac- and Re- must still land where the theory says: `ac_valid` /
           `re_valid` (`probe_transformation_sketch.TransitionVerdict`, the
           auditor validated against three blind theory panels at 54/60).
           Neither may fall: paired CI lower bound > -0.15. This is the gate
           this text already has, and the reason the arms touch lines 1-2 only.
  GUARD 2  S- stays ONE named third failure (`_third_trap`), same bound.

  INDETERMINATE is a result: at 32 paired rows the CI on a 20-point move is
  about +/- 15, so a smaller real effect will not resolve here, and the
  registered consequence is to say so rather than re-read the run.

  IF AN ARM WINS, IT IS NOT YET SHIPPABLE. `TRANSFORMATION_POSITIONS` is read by
  three callers (this concern, the synthesis prompt, and any host embedding
  `TRANSFORMATION_BUILD_PROCEDURE` — the first app does), and its registered
  gate is `probe_transformation_sketch.py` on 25 frozen tetrads that are NOT
  all decided positions. The decided rule is written to be inert on a tetrad
  whose T is not settled; that is a claim, and the gate run is where it gets
  tested. Phase 2, winning arm only.

    poetry run python tests/e2e/probe_decided_move.py
    poetry run python tests/e2e/probe_decided_move.py --arms current,decided
    poetry run python tests/e2e/probe_decided_move.py --report <file>

Plain script, no graph. Writer `DIALEXITY_E2E_TIER_STRONG` (set it to the model
the host runs: the structured-output constraint changes the writing on 5.5),
judge `DIALEXITY_E2E_JUDGE`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field, create_model  # noqa: E402

from dialectical_framework.dialectical_reasoning import \
    DialecticalReasoning  # noqa: E402
from dialectical_framework.settings import Settings  # noqa: E402

_HERE = Path(__file__).resolve().parent
_CASES = _HERE / "fixtures" / "decided_tetrads.jsonl"
_RESULTS = _HERE / "results" / "tetrad_quality"
_CONCURRENCY = 5
_TRANSITION_WORDS, _SYNTHESIS_WORDS = 15, 7  # the settings defaults

ARMS = ("current", "decided_fields", "decided_scoped")


# --- The arms ------------------------------------------------------------------
#
# Built by replacement on the shipped lines, as arguments to a write — never as a
# module global, because the writes run concurrently (`probe_decided_stance`
# discarded a run to learn that).

_LINE1_SHIPPED = (
    "1. The action (Ac): the concrete move that carries T toward A. The "
    "reflection (Re): the re-reading that carries A back toward T. These are "
    "the two poles of the transformation."
)

#: Both directions kept — the action is made FROM T and reaches what A is for,
#: the reflection the mirror — with the "carries T toward A" phrasing gone. The
#: theory's spaces are unchanged (Ac in Not-A, Re in Not-T); what goes is the
#: reading in which the move's job is to travel part of the way to A.
_LINE1_REACH = (
    "1. The action (Ac): the concrete move, made from T, that reaches what A is "
    "for. The reflection (Re): the re-reading, made from A, that reaches what T "
    "is for. These are the two poles of the transformation."
)

_LINE2_SHIPPED = (
    "2. Each developed well — Ac+ turns T's trap (T-) into A's strength (A+); "
    "Re+ turns A's trap (A-) into T's strength (T+)."
)

#: The distinction the first app had to add downstream, stated where the move is
#: derived. Conditional in its own words, so it should be inert on a tetrad
#: whose T is not a settled position — which phase 2 is for. It stops short of
#: claiming such a line IS Ac-: that would be a theory claim this probe has not
#: checked, and the archive's own warning is that a gloss hardened into a rule
#: gets argued with.
#:
#: ROUND 1 (`decided_move-20261012-101408.json`): stated like this, in point 2,
#: it WON the endpoint and BROKE the gate — decision stands 72% -> 100% (+28,
#: +12..+44) and reflection 81% -> 100% (+19), with `ac_valid` 91% -> 66%
#: (-25, -45..-5, a resolved fall through the registered bound). The cause is in
#: the 11 failures, and it is one shape: told the action must not dilute toward
#: A, the writer makes Ac- the decision carried out COLDLY — "Announce it, book
#: the move, and fly home before she has absorbed it" — which lands in T-, the
#: person's own trap, not in A-. The auditor said so on 10 of the 11
#: (`ac_minus_is_degenerated_action` true, `ends_in_a_minus` false). That is the
#: failure shape `transformation_sketch`'s own docstring records for the makeup
#: half of the definition, re-introduced by a rule pushing the action away from
#: A. So round 2 keeps the rule and takes Ac- out from under it.
_DECIDED_RULE = (
    " Where T is something the person has DECIDED or refused, the action is "
    "that decision carried out: what A is for shapes HOW they carry it out, "
    "never whether or how much. A condition attached to it, a trial of it, one "
    "option among others, a smaller or partial amount of exactly what they "
    "refused, or a postponement is not the action developed well — it is the "
    "decision undone."
)

#: Round 2, arm A: the SAME rule, moved to the two field descriptions it governs
#: — the writer reads it immediately before writing those two lines, and the
#: minus fields keep their own instruction ("carries T's strength into A's
#: trap") as the only thing said about Ac-. Placing a rule on the line that
#: reads it, rather than cross-referencing it, is the archive's own repair shape.
_DECIDED_FIELDS = (
    " Where the person has DECIDED or refused, this is that decision carried "
    "out: what A is for shapes HOW it is carried out, never whether or how "
    "much — never a condition on it, a trial of it, one option among others, a "
    "smaller or partial amount of what they refused, or a postponement."
)

#: Round 2, arm B: the rule stays in point 2, positively stated (the enumeration
#: of failures goes, since a ready-made bad action is what Ac- reached for), and
#: ends by naming what it does NOT govern. Weaker by construction than arm A —
#: it is a cross-reference — and worth measuring because it is one sentence.
_DECIDED_SCOPED = (
    " Where T is something the person has DECIDED or refused, Ac and Ac+ are "
    "that decision carried out: what A is for shapes HOW they carry it out, "
    "never whether or how much. This governs the action and the action "
    "developed well only — Ac- still ends in A's trap, as point 3 says."
)


def _positions_for(arm: str) -> str:
    """The arm's `TRANSFORMATION_POSITIONS`."""
    from dialectical_framework.concerns import transformation_sketch as ts

    shipped = ts.TRANSFORMATION_POSITIONS
    assert _LINE1_SHIPPED in shipped, "line 1 of TRANSFORMATION_POSITIONS changed"
    assert _LINE2_SHIPPED in shipped, "line 2 of TRANSFORMATION_POSITIONS changed"
    if arm in ("current", "decided_fields"):
        return shipped  # `decided_fields` carries its rule on the DTO instead
    if arm == "reach":
        return shipped.replace(_LINE1_SHIPPED, _LINE1_REACH)
    if arm == "decided_scoped":
        return shipped.replace(_LINE2_SHIPPED, _LINE2_SHIPPED + _DECIDED_SCOPED)
    return shipped.replace(_LINE2_SHIPPED, _LINE2_SHIPPED + _DECIDED_RULE)


def _system_for(arm: str) -> str:
    """The concern's own system prompt with the arm's positions in it.

    Rebuilt by replacement rather than re-typed, so the rest of the prompt — the
    synthesis shape, the build order, the closing instruction — is byte-identical
    across arms.
    """
    from dialectical_framework.concerns import transformation_sketch as ts

    assert ts.TRANSFORMATION_POSITIONS in ts.SYSTEM_PROMPT
    return ts.SYSTEM_PROMPT.replace(
        ts.TRANSFORMATION_POSITIONS, _positions_for(arm)
    )


def _dto_for(arm: str) -> type[BaseModel]:
    """The arm's response model: same fields, same order, same descriptions —
    except `decided_fields`, which carries the decided rule on `action` and
    `ac_plus`, the two lines it governs.

    A clone is built for every non-shipped arm so no arm can mutate the shipped
    class, and a field description is an instruction like any other.
    """
    from dialectical_framework.concerns.transformation_sketch import \
        TransformationSketchDto

    if arm == "current":
        return TransformationSketchDto
    fields: dict[str, Any] = {}
    for name, info in TransformationSketchDto.model_fields.items():
        description = info.description or ""
        if arm == "decided_fields" and name in ("action", "ac_plus"):
            description += _DECIDED_FIELDS
        fields[name] = (str, Field(description=description))
    return create_model(f"TransformationSketch_{arm}", **fields)


# --- The write -----------------------------------------------------------------


def _view(case: dict[str, Any]):
    from dialectical_framework.graph.views import PerspectiveView, PoleView

    return PerspectiveView(
        **{
            k: PoleView(text=case[k])
            for k in ("t", "a", "t_plus", "t_minus", "a_plus", "a_minus")
        },
        complete=True,
    )


async def _write(arm: str, case: dict[str, Any]) -> dict[str, Any]:
    """One transformation from frozen corners, on the arm's system text."""
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator
    from dialectical_framework.concerns.transformation_sketch import \
        transformation_sketch_prompt

    row: dict[str, Any] = {"arm": arm, "id": case["id"], "utterance": case["utterance"]}
    started = time.monotonic()
    try:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_system_for(arm))
        dto = await conversation.submit(
            _dto_for(arm),
            transformation_sketch_prompt(
                _view(case), case["utterance"], _TRANSITION_WORDS, _SYNTHESIS_WORDS
            ),
        )
        row["transformation"] = dto.model_dump()
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["write_s"] = round(time.monotonic() - started, 1)
    return row


# --- Reading the rows ----------------------------------------------------------

_METRICS = ("decision_stands", "reflection_stands", "ac_valid", "re_valid", "third_failure")


def _report(rows: list[dict[str, Any]], arms: list[str]) -> None:
    from e2e.probe_decided_stance import _paired

    print("\n--- the move on a decided position ---")
    for arm in arms:
        mine = [r for r in rows if r["arm"] == arm]
        errors = sum(1 for r in mine if r.get("error"))
        rates = " | ".join(
            f"{m} {100 * sum(r[m] for r in mine if r.get(m) is not None) / max(1, sum(1 for r in mine if r.get(m) is not None)):.0f}%"
            for m in _METRICS
        )
        print(f"  {arm:9} {rates}  (errors {errors}, n={len(mine)})")
    for arm in arms:
        if arm == "current":
            continue
        print(f"\n  {arm} - current:")
        for metric in _METRICS:
            print(f"    {metric:18} {_paired(rows, arm, metric)}")
    print("\n  the action, where the decision was undone (first 12):")
    shown = 0
    for r in rows:
        if r.get("decision_stands") == 0.0 and shown < 12:
            how = (r.get("decision_verdict") or {}).get("action_failure") or "?"
            print(f"    {r['arm']:9} {r['id']:38} [{how}] «{(r.get('transformation') or {}).get('ac_plus')}»")
            shown += 1


async def _run(arms: list[str], limit: int, out: Path) -> None:
    from e2e.config import E2EConfig
    from e2e.modelctx import using_model
    from e2e.probe_decided_stance import _judge_decision
    from e2e.probe_synthesis_arms_theory2 import _third_trap
    from e2e.probe_transformation_sketch import _transitions

    container = DialecticalReasoning.setup(Settings.from_env())
    config = E2EConfig.from_env()
    writer, judge = config.tiers["strong"], config.judge_model
    cases = [json.loads(x) for x in _CASES.read_text().splitlines() if x.strip()]
    cases = cases[: limit or None]
    gate = asyncio.Semaphore(_CONCURRENCY)
    print(
        f"=== the move on a decided position: writer {writer} | judge {judge}\n"
        f"    arms {arms} | {len(cases)} frozen tetrads = "
        f"{len(arms) * len(cases)} writes -> {out}",
        flush=True,
    )

    async def write(arm: str, case: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            row = await _write(arm, case)
            print(
                f"  {arm:9} {case['id']:38} "
                f"{row.get('error', 'written')} {row.get('write_s')}s",
                flush=True,
            )
            return row

    with using_model(container, writer):  # phase A — never interleaved with B
        rows = list(
            await asyncio.gather(*(write(a, c) for a in arms for c in cases))
        )
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\n  phase A written: {out}", flush=True)

    by_id = {c["id"]: c for c in cases}

    async def judge_row(row: dict[str, Any]) -> None:
        if row.get("error"):
            return
        case, written = by_id[row["id"]], row["transformation"]
        # The decision judge reads the person's words and the tetrad's T/A, so
        # it needs the frozen corners, not only the written lines.
        for name, key in (("thesis", "t"), ("antithesis", "a")):
            row[name] = case[key]
        async with gate:
            decision, transitions, trap = await asyncio.gather(
                _judge_decision(row),
                _transitions(case, written),
                _third_trap(container, judge, case["t_minus"], case["a_minus"], written["s_minus"]),
            )
        row["decision_verdict"] = decision
        if decision and "error" not in decision:
            row["decision_stands"] = float(decision["action_keeps_it"])
            row["reflection_stands"] = float(decision["reflection_keeps_it"])
        if transitions is not None:
            row["transition_verdict"] = transitions.model_dump()
            row["ac_valid"] = float(transitions.ac_valid)
            row["re_valid"] = float(transitions.re_valid)
        row["third_trap"] = trap
        if trap.get("kind"):
            row["third_failure"] = float(trap["kind"] == "third_failure")
        print(
            f"  judged {row['arm']:9} {row['id']:38} "
            f"decision {'stands' if row.get('decision_stands') else 'UNDONE'} | "
            f"Ac- {'ok' if row.get('ac_valid') else 'bad'} "
            f"Re- {'ok' if row.get('re_valid') else 'bad'}",
            flush=True,
        )

    with using_model(container, judge):  # phase B
        await asyncio.gather(*(judge_row(r) for r in rows))
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    _report(rows, arms)
    print(f"\n  {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if args.report:
        rows = json.loads(Path(args.report).read_text())
        _report(rows, sorted({r["arm"] for r in rows}, key=lambda a: a != "current"))
        return
    arms = [a for a in args.arms.split(",") if a]
    assert "current" in arms, "every delta is paired against `current`"
    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"decided_move-{time.strftime('%Y%m%d-%H%M%S')}.json"
    asyncio.run(_run(arms, args.limit, out))


if __name__ == "__main__":
    main()
