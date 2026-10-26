"""
The gate for the two prompt rules of 2026-10-20, on real multi-claim inputs.

WHAT IS BEING MEASURED
======================
Both rules shipped unmeasured because no case set could reach them (see
`multiclaim_cases.py`). They are two sentences, each removable, each read by the
view turn at call time:

* rule 1, `view_sketch.THESIS_IS_A_STANCE`'s last sentence — when the words hold
  SEVERAL claims, T is the one the person would sign, not a premise, a hedge, or
  a claim conceded in passing.
* rule 2, `antithesis_extraction._OPPOSING_POSITION_ASK`'s mirror — an opposition
  the thesis's own words already name AND concede is seen, not missing; rate it
  low and oppose the claim actually made.

Arms are WITH (as shipped) and WITHOUT (both sentences cut), paired on the same
40 cases, in ONE run on ONE transport. Deliberately not against the archive: the
archive's cases are single-claim, and its figures predate the 2026-10-26
transport fix, so neither is comparable. Everything a reader needs is inside
this run.

`attempts=1`, which is NOT the shipped default (3). The rules are PROMPT rules
and act on the writer; best-of-N acts on the selection, and the selection term
that reads the same shape (`ThesisFitCheck`) already has its own measured gate
(`probe_thesis_fit_judge.py`: self-agreement 40/40, nearly inert on single-claim
input). One draw per case isolates what these two sentences do, at a third of
the cost. A best-of-3 replication is the next run if this one lands borderline.

THE GROUND TRUTH IS THE AUTHOR'S
================================
Each case is a real petition: the writer sees only the argument, and the
author's own one-line demand is held back. So "did the writer draw the claim the
person would sign" is scored against a label the author wrote, by a judge shown
the drawn T and that demand and nothing else — not the arm, not the rule, not the
other arm's answer. The mirror rule is scored the same way against the clause the
blind screen quoted as the text's own concession.

PRE-REGISTERED, before the first call
=====================================
Primary (rule 1): T states the author's demand, counted over 40 paired cases.
    The WITH arm must win by at least +7 of 40, with the sign test over
    discordant pairs reported beside it.
Secondary (rule 2): on the 22 conceding cases, A+ restates the conceded clause.
    The WITH arm must be LOWER by at least +4 of 22 (fewer already-granted A+).
Side conditions, both of which must hold or the primary does not count:
    coherence (CC pass) must not fall by more than 3 of 40, and the antithesis
    being a genuine position must not fall by more than 3 of 40.
A result that misses a bar is reported as a miss. The bars are pinned by
`test_registered_bars_cannot_drift` so a disappointing run cannot move them.

    poetry run pytest tests/e2e/probe_multiclaim_thesis.py --real-llm -q -s

Models come from the environment and the bench config; no model id is written
here.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time
from typing import Any, Optional

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.multiclaim_cases import MULTI_CLAIM_CASES, MultiClaimCase
from e2e.probe_aspect_variants import _judge
from e2e.probe_tetrad_quality import _audit_kind
# `_texts` reused rather than rewritten: the view's fields are `t`/`a`, not
# `thesis`/`antithesis`, and one copy of that mapping is enough.
from e2e.probe_view_turn_ask import FOCUS, _texts

#: NOT `real_llm` at module level: the instrument's own guards (`TestTheInstrument`)
#: must run in the ordinary mocked suite, or a reworded rule constant would only
#: be caught by someone paying for a run. The run itself carries the mark.
pytestmark = [pytest.mark.llm]

RESULTS = pathlib.Path(__file__).parent / "results" / "multiclaim"

#: Pre-registered bars. Read by the report AND by the drift test.
BARS: dict[str, int] = {
    "primary_demand_as_thesis_min_gain": 7,
    "secondary_granted_a_plus_min_drop": 4,
    "max_coherence_loss": 3,
    "max_antithesis_kind_loss": 3,
}

#: The first words of each rule's sentence. The ablation cuts from here to the
#: end of the constant, and REFUSES to run if the cut changes nothing — a
#: reworded constant must fail loudly rather than give two identical arms.
RULE_1_FROM = "When the words hold SEVERAL claims"
RULE_2_FROM = "The mirror failure:"


def _without(text: str, marker: str) -> str:
    assert marker in text, (
        f"the rule's text has moved: {marker!r} is no longer in the constant, so "
        "this probe would run two identical arms and report a null"
    )
    return text[: text.index(marker)].rstrip()


class _Ablation:
    """The WITHOUT arm, as a patch on the view turn's own two bindings.

    Both constants are read inside `view_sketch_prompt` at call time, and
    `_OPPOSING_POSITION_ASK` is imported INTO that module, so the local binding
    is the one that matters for this surface.
    """

    def __enter__(self) -> "_Ablation":
        from dialectical_framework.concerns import view_sketch

        self._module = view_sketch
        self._stance = view_sketch.THESIS_IS_A_STANCE
        self._ask = view_sketch._OPPOSING_POSITION_ASK
        view_sketch.THESIS_IS_A_STANCE = _without(self._stance, RULE_1_FROM)
        view_sketch._OPPOSING_POSITION_ASK = _without(self._ask, RULE_2_FROM)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._module.THESIS_IS_A_STANCE = self._stance
        self._module._OPPOSING_POSITION_ASK = self._ask


def prompts_differ() -> tuple[str, str]:
    """The two arms' actual prompts — the instrument's own wiring check.

    Asserts the rule text is in one and not the other. If the prompt were
    assembled at import time this would catch it, and a run that cannot show
    two different prompts has nothing to report.
    """
    from dialectical_framework.concerns.view_sketch import view_sketch_prompt

    with_rules = view_sketch_prompt(None, 7)
    with _Ablation():
        without_rules = view_sketch_prompt(None, 7)
    assert RULE_1_FROM in with_rules and RULE_1_FROM not in without_rules
    assert RULE_2_FROM in with_rules and RULE_2_FROM not in without_rules
    return with_rules, without_rules


class SameClaimDto(BaseModel):
    """Blind read: does the drawn position state the author's own demand?"""

    states_the_same_claim: bool = Field(
        description=(
            "True only if the two statements commit to the SAME thing — the same "
            "course of action or the same conclusion. A statement about the same "
            "topic, or a weaker version that stops short of the demand (asking "
            "whether, calling for a review, saying it matters), is False."
        )
    )
    reasoning: str = Field(description="One sentence.")


class RestatesDto(BaseModel):
    """Blind read: does this position restate what the clause already grants?"""

    restates_the_clause: bool = Field(
        description=(
            "True if the position says substantially what the clause already "
            "concedes — the same good, the same consideration — so that offering "
            "it back would tell the writer something their own words already say."
        )
    )
    reasoning: str = Field(description="One sentence.")


async def _same_claim(drawn: str, demand: str) -> Optional[bool]:
    """One call, both statements unlabelled and in a fixed order.

    Unlabelled because "the author's real demand" would prime agreement; a
    fixed order because position bias is a known hazard of these judges in this
    tree (the joint judge crowned the first-listed draft 29/40) and a fixed
    order at least makes the bias identical in both arms.
    """
    try:
        dto = await ConversationFacilitator().submit(
            response_model=SameClaimDto,
            user_content=(
                "Two statements. Do they commit to the same thing?\n\n"
                f'Statement 1: "{drawn}"\n'
                f'Statement 2: "{demand}"'
            ),
        )
    except Exception:  # a failed judging is missing data, never a verdict
        return None
    return dto.states_the_same_claim


async def _restates(drawn: str, clause: str) -> Optional[bool]:
    try:
        dto = await ConversationFacilitator().submit(
            response_model=RestatesDto,
            user_content=(
                "A clause from something a person wrote, and a position offered "
                "back to them. Does the position restate what the clause already "
                "grants?\n\n"
                f'The clause: "{clause}"\n'
                f'The position: "{drawn}"'
            ),
        )
    except Exception:
        return None
    return dto.restates_the_clause


async def _draw_one(case: MultiClaimCase) -> dict[str, Any]:
    """One view-turn draw over one case's argument. Never sees `case.demand`."""
    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant

    head = Consultant(
        app_preamble=COUNSELOR_PERSONA,
        messages=[{"role": "user", "content": case.text}],
    )
    started = time.perf_counter()
    try:
        view = await head.exploration_view(focus=FOCUS, attempts=1)
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        return {
            "petition_id": case.petition_id,
            "error": repr(exc),
            "seconds": round(time.perf_counter() - started, 1),
        }
    first = view.perspectives[0] if view.perspectives else None
    row: dict[str, Any] = {
        "petition_id": case.petition_id,
        "seconds": round(time.perf_counter() - started, 1),
        "drawn": first is not None,
        "failed_draws": [f.kind for f in view.failed_draws],
    }
    if first is not None:
        row.update(_texts(first))
    return row


async def _run_arm(name: str, cases: tuple[MultiClaimCase, ...], batch: int) -> list[dict]:
    rows: list[dict] = []
    for start in range(0, len(cases), batch):
        chunk = cases[start : start + batch]
        if name == "without_rules":
            with _Ablation():
                rows += await asyncio.gather(*(_draw_one(c) for c in chunk))
        else:
            rows += await asyncio.gather(*(_draw_one(c) for c in chunk))
        print(f"  {name}: drawn {len(rows)}/{len(cases)}", flush=True)
    return rows


def _demand_positions(cases: tuple[MultiClaimCase, ...]) -> dict[str, int]:
    """Where each case's demand sits in its own text, by thirds.

    A demand in the opening sentence is drawn correctly by position alone, so
    this is the difficulty of the set: the rule under test is about choosing
    the signable claim over the hedges that precede it.
    """
    buckets = {"first third": 0, "middle": 0, "last third": 0, "not located": 0}
    for case in cases:
        head = " ".join(case.demand.split()[:4]).lower()
        position = case.text.lower().find(head) if head else -1
        if position < 0:
            # The demand is reworded in the text rather than quoted; fall back
            # to the most distinctive word it shares with the text.
            words = sorted(
                (w for w in head.split() if len(w) > 5), key=len, reverse=True
            )
            position = next(
                (case.text.lower().find(w) for w in words if w in case.text.lower()), -1
            )
        if position < 0:
            buckets["not located"] += 1
            continue
        fraction = position / max(1, len(case.text))
        key = (
            "first third" if fraction < 1 / 3
            else "middle" if fraction < 2 / 3
            else "last third"
        )
        buckets[key] += 1
    return buckets


def _count(rows: list[dict], key: str) -> int:
    return sum(1 for r in rows if r.get(key) is True)


def _sign_test(with_rows: list[dict], without_rows: list[dict], key: str) -> dict:
    """Discordant pairs and the one-sided tail, by case."""
    from math import comb

    by_id = {r["petition_id"]: r for r in without_rows}
    wins = losses = 0
    for row in with_rows:
        other = by_id.get(row["petition_id"])
        if other is None:
            continue
        a, b = row.get(key), other.get(key)
        if a is True and b is False:
            wins += 1
        elif a is False and b is True:
            losses += 1
    n = wins + losses
    if not n:
        return {"wins": 0, "losses": 0, "discordant": 0, "two_sided_p": None}
    tail = sum(comb(n, k) for k in range(max(wins, losses), n + 1)) / 2 ** n
    # Capped: doubling a tail that already covers more than half the mass gives
    # a "p" above 1 (the first run printed 1.375 at 2-2 of 4), which is not a
    # probability and makes a null look like a broken instrument.
    return {
        "wins": wins,
        "losses": losses,
        "discordant": n,
        "two_sided_p": round(min(1.0, 2 * tail), 4),
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_two_prompt_rules_on_multi_claim_input(di_container) -> None:
    with_prompt, without_prompt = prompts_differ()
    print(
        f"\n=== the two 2026-10-20 rules on {len(MULTI_CLAIM_CASES)} real multi-claim "
        f"inputs ({len(with_prompt) - len(without_prompt)} chars of rule text)"
    )
    print(f"    bars: {BARS}", flush=True)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"rules-{time.strftime('%Y%m%d-%H%M%S')}.json"
    batch = int(os.environ.get("MULTICLAIM_BATCH", "8"))
    # A smoke run on the first few cases, for checking the wiring without
    # paying for the whole set. A capped run is NOT the gate: the bars above
    # are stated over 40 and 22, and the report says so.
    limit = int(os.environ.get("MULTICLAIM_LIMIT", "0")) or len(MULTI_CLAIM_CASES)
    cases = MULTI_CLAIM_CASES[:limit]
    if limit < len(MULTI_CLAIM_CASES):
        print(f"    SMOKE RUN on {limit} of {len(MULTI_CLAIM_CASES)} cases — not the gate")

    arms = {
        name: await _run_arm(name, cases, batch)
        for name in ("with_rules", "without_rules")
    }

    demand = {c.petition_id: c.demand for c in cases}
    conceded = {c.petition_id: c.conceded for c in cases if c.conceded}

    for name, rows in arms.items():
        complete = [r for r in rows if r.get("thesis")]
        claims = await asyncio.gather(
            *(_same_claim(r["thesis"], demand[r["petition_id"]]) for r in complete)
        )
        for row, verdict in zip(complete, claims):
            row["thesis_is_the_demand"] = verdict
        mirror_rows = [
            r for r in complete if r["petition_id"] in conceded and r.get("a_plus")
        ]
        grants = await asyncio.gather(
            *(_restates(r["a_plus"], conceded[r["petition_id"]]) for r in mirror_rows)
        )
        for row, verdict in zip(mirror_rows, grants):
            row["a_plus_already_granted"] = verdict
        full = [
            r
            for r in complete
            if all(r.get(k) for k in ("antithesis", "t_plus", "t_minus", "a_plus", "a_minus"))
        ]
        for row, verdict in zip(full, await asyncio.gather(*(_judge(r) for r in full))):
            row.update(verdict)
        judge_model = E2EConfig.from_env().judge_model
        for row in full:  # `using_model` re-points the container: one at a time
            row.update(
                await _audit_kind(di_container, judge_model, row["thesis"], row["antithesis"])
            )
        out.write_text(json.dumps({"bars": BARS, "arms": arms}, indent=1, ensure_ascii=False))
        print(f"  {name}: scored {len(complete)} complete, {len(mirror_rows)} mirror", flush=True)

    w, wo = arms["with_rules"], arms["without_rules"]
    report = {
        "bars": BARS,
        "cases": len(cases),
        "is_the_gate": len(cases) == len(MULTI_CLAIM_CASES),
        "drawn": {k: _count(v, "drawn") for k, v in arms.items()},
        "thesis_is_the_demand": {k: _count(v, "thesis_is_the_demand") for k, v in arms.items()},
        "a_plus_already_granted": {
            k: _count(v, "a_plus_already_granted") for k, v in arms.items()
        },
        # The reused judges' own key names: `_judge` writes `pass`, `_audit_kind`
        # writes `a_kind` with the verdict word "position". Guessing them cost a
        # smoke run that reported 0 and 0 in both arms.
        "coherence_pass": {k: _count(v, "pass") for k, v in arms.items()},
        "antithesis_a_position": {
            k: sum(1 for r in v if r.get("a_kind") == "position") for k, v in arms.items()
        },
        # The first run's lesson: in 35 of 40 cases the demand sits in the
        # text's FIRST THIRD, because a petition opens with it. The handoff's
        # case buried its demand last, after the hedges — so a set this
        # front-loaded cannot show what rule 1 is for, and any null from it is
        # partly a fact about the set. Reported on every run from now on.
        "demand_position": _demand_positions(cases),
        "sign_test_demand": _sign_test(w, wo, "thesis_is_the_demand"),
        "sign_test_granted": _sign_test(w, wo, "a_plus_already_granted"),
    }
    out.write_text(
        json.dumps({"report": report, "arms": arms}, indent=1, ensure_ascii=False)
    )
    print("\n" + json.dumps(report, indent=1))
    print(f"\nwrote {out}")


class TestTheInstrument:
    """What must hold whether or not the run is affordable today."""

    def test_registered_bars_cannot_drift(self):
        """The bars were set before the first call; a disappointing run does
        not get to move them."""
        assert BARS == {
            "primary_demand_as_thesis_min_gain": 7,
            "secondary_granted_a_plus_min_drop": 4,
            "max_coherence_loss": 3,
            "max_antithesis_kind_loss": 3,
        }

    def test_the_two_arms_really_send_different_prompts(self):
        """The whole run is a null if they do not — and they would, silently,
        if either rule were reworded or moved to import-time interpolation."""
        with_rules, without_rules = prompts_differ()
        assert len(with_rules) > len(without_rules) + 500

    def test_the_ablation_restores_what_it_patched(self):
        from dialectical_framework.concerns import view_sketch

        before = (view_sketch.THESIS_IS_A_STANCE, view_sketch._OPPOSING_POSITION_ASK)
        with _Ablation():
            assert view_sketch.THESIS_IS_A_STANCE != before[0]
        assert (view_sketch.THESIS_IS_A_STANCE, view_sketch._OPPOSING_POSITION_ASK) == before

    def test_the_writer_never_sees_the_ground_truth(self):
        """`_draw_one` is handed a whole case and must read only its `text`
        (and `petition_id`, to label the row). Checked on the parsed tree
        rather than on the source text, because a prose mention of the held-back
        field — this very docstring, the first time — trips a substring check.
        """
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(_draw_one)))
        read = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "case"
        }
        assert read == {"text", "petition_id"}, (
            f"the writer's arm reads {read - {'text', 'petition_id'}} off the case; "
            "the author's demand is the ground truth and must stay held back"
        )

    def test_the_report_counts_the_keys_the_judges_actually_write(self):
        """A guessed key name reports a silent zero, which reads as "the rules
        broke coherence" rather than as "this probe is miswired"."""
        import inspect

        from e2e.probe_aspect_variants import _judge as cc_judge
        from e2e.probe_tetrad_quality import _audit_kind as kind_judge

        assert '"pass"' in inspect.getsource(cc_judge)
        assert '"a_kind"' in inspect.getsource(kind_judge)
        report = inspect.getsource(test_the_two_prompt_rules_on_multi_claim_input)
        assert '_count(v, "pass")' in report
        assert 'r.get("a_kind") == "position"' in report

    def test_the_sign_test_pairs_by_case(self):
        a = [{"petition_id": "1", "k": True}, {"petition_id": "2", "k": False}]
        b = [{"petition_id": "1", "k": False}, {"petition_id": "2", "k": False}]
        assert _sign_test(a, b, "k") == {
            "wins": 1, "losses": 0, "discordant": 1, "two_sided_p": 1.0,
        }
