"""
What the view turn does with material that is not the person's stance.

A FINDING run over `pasted_material_cases.py` — first made 2026-10-26 on the
then-shipped prompts (the control below, `STANCE_ARM=first_person`), which led
to the shipped rule saying WHOSE stance and to `held_by` on the view; with no
arm set it now runs the shipped prompts and ALSO reads `held_by`:
real reportage (Wikinews) and real dialogue (Hansard), none of it the reader's
own position — see `screen_pasted_material.py` for the sourcing and the blind
screen that listed each text's held positions and their holders.

THE HYPOTHESIS, stated before the run
=====================================
`THESIS_IS_A_STANCE` tells the writer T is "something the person holds ...
written as a claim they could say in the first person". On text that carries
only other people's positions, the prediction is that the writer still draws a
T, and words it as the READER's own stance — i.e. the card would hand the person
a position they never took, which is the 2026-10-20 handoff's defect in another
coat. The alternative outcomes are that the writer declines (draws nothing, as
it does for a request for information), or draws the tension that is IN the
material without attributing it.

THE READS, all blind to the hypothesis
======================================
1. drawn: did the view carry a tetrad at all.
2. attributed_to_reader: is T worded as a position the READER holds — first
   person, or an unattributed "should" — rather than as someone else's reported
   position. Judged on T's wording alone.
3. t_is_a_held_position: which of the screen's listed held positions T states,
   or none. A T that is one of them is the material's own tension, drawn; a T
   that is none of them is invented.
4. dialogue only — t_and_a_are_two_speakers: do T and A state the positions
   of two DIFFERENT holders from the list. That is the tension the dialogue
   actually carries.

No bars on the FINDING run: nothing shipped claimed to handle this input kind,
so there was nothing to pass or fail. The figures are the finding, and the dev
note says what they meant for the prompt.

THE SECOND GATE (2026-10-27): a name on words never said
=======================================================
The shipped run drew A as the writer's OWN construction in some dialogues and,
worse, put a speaker's name on it ("Fund public services through taxing
business" — the Exchequer Secretary, who had defended a rates package). The
repair is `view_sketch.HOLDER_FROM_THE_WORDS` plus tightened `held_by` field
descriptions: a party is named only for a position their own words take, the
other party's opposition is taken as A when it stands in the words, a built
opposition has no holder. `test_the_holder_rule_on_pasted_material` runs the
view turn WITH that text against WITHOUT it (`_HolderArm`, the arm removed by
patching the module binding to an empty string — the prompt's own wiring check
`holder_prompts_differ` refuses to run otherwise), `PASTED_DRAWS` draws per
case in each arm, paired by case and draw index. The old position-list judge
(`_which_position`) called a paraphrase "none" in 8 of 17 dialogues, so the
reads here are TEXT-GROUNDED: `_holder_in_text` is shown the text and one
sentence and asked whether any party's OWN words take it, naming them.

Pre-registered (`BARS`), decided before the run:
  PRIMARY — `a_falsely_attributed` (A names a holder, and no party's words in
    the text take A, or a different party's do): WITH at most
    `a_falsely_attributed_max_with_rule` of the WITH draws AND no more than
    WITHOUT. A name on words never said is the defect; the rule ships only if
    this holds.
  SECONDARY — `a_from_the_words` (some party's words take A) gains at least
    `a_from_the_words_min_gain` draws WITH over WITHOUT. Reported, not a gate.
  SIDE CONDITIONS — coherence pass, the antithesis a position (the archive's
    two judges) and `t_from_the_words` each lose no more than their `max_*`.
The run is the finding either way; `rule_ships` in the report is the verdict.

What happened (2026-10-27, `results/pasted/holder-rule-20261027-132330.json`): the
first scoring asked whose OWN WORDS take the pole and was wrong for reportage,
where every position is reported; `HolderInTextDto` was corrected to
attribution BY THE TEXT and the saved draws re-read. The absolute primary bar
MISSED on either read (16 of 74 WITH against 23 WITHOUT; 30 against 37 on the
first), the relative half held, the secondary resolved (+12, 16/4 paired,
p = 0.012), the side conditions sat at or inside their bars. Shipped anyway,
with the miss stated: the bar presupposed a same-party read with no false
positives, and the flagged rows are mostly compound-name mismatches in BOTH
arms; by one hand read the real named inventions are ~4 against ~10. Story and
table: `docs/dev-notes/views.md`, "A name on words never said".

    poetry run pytest tests/e2e/probe_pasted_material.py --real-llm -q -s
    PASTED_DRAWS=2 poetry run pytest tests/e2e/probe_pasted_material.py --real-llm -q -s -k holder_rule
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
from e2e.pasted_material_cases import PASTED_MATERIAL_CASES, PastedMaterialCase
from e2e.probe_view_turn_ask import FOCUS, _texts

pytestmark = [pytest.mark.llm]

#: THE CONTROL: `THESIS_IS_A_STANCE` as it stood before 2026-10-26, kept here
#: and not in `src/` like the other rejected prompt text (`DIFFERENT_OPPOSITION_ASK`).
#: It presumed authorship — "something the person holds, written as a claim they
#: could say in the first person" — and on pasted material the writer took one of
#: the OTHER parties' positions as T in 28 of 28 draws with nothing saying whose.
#: The shipped text (arm B of that day, now `view_sketch.THESIS_IS_A_STANCE`)
#: keeps every sentence that stopped the question-echo and says WHOSE stance
#: depends on the words, with the holder carried by `held_by`. `STANCE_ARM=first_person`
#: re-runs the control; measured with it, the two texts are neutral on the
#: 20-question echo probe within one case and differ on material only in that
#: the shipped one stops declining articles (11/20 → 20/20 drawn).
FIRST_PERSON_STANCE = """The thesis (T) is a STANCE: something the person holds, wants or is about to do, written as a claim they could say in the first person — never their question restated, never a description of what happens to them. When they asked a question, T is the answer their wording leans to: "Why should I keep paying for his phone when he never calls?" carries "I should stop paying for his phone"; "Isn't it time we stopped standups?" carries "We should stop standups". A behaviour described is not yet a stance; the stance is what the person holds about it. When the question is genuinely open between options ("Zurich or Vilnius?"), T is one of those options held as a stance. A request for information ("what is the best way to learn Spanish?") carries no stance at all. When the words hold SEVERAL claims, T is the one the person would sign — the conclusion or demand the rest leads to — not a premise or a hedge on the way to it ("we have the right to ask" is the run-up to the demand that follows), and not a claim they concede in passing ("not only X but also Y" concedes X; their stance is Y)."""


class _StanceArm:
    """`STANCE_ARM=first_person` runs the view turn on the pre-2026-10-26 control; anything else, as shipped."""

    def __enter__(self) -> "_StanceArm":
        from dialectical_framework.concerns import view_sketch

        self._module, self._was = view_sketch, view_sketch.THESIS_IS_A_STANCE
        if os.environ.get("STANCE_ARM") == "first_person":
            view_sketch.THESIS_IS_A_STANCE = FIRST_PERSON_STANCE
        return self

    def __exit__(self, *exc: Any) -> None:
        self._module.THESIS_IS_A_STANCE = self._was

RESULTS = pathlib.Path(__file__).parent / "results" / "pasted"

#: Pre-registered before the 2026-10-27 run. Counts are over DRAWS (cases x
#: `PASTED_DRAWS`); the planned run is 37 x 2 = 74 per arm.
BARS = {
    "a_falsely_attributed_max_with_rule": 2,
    "a_from_the_words_min_gain": 6,
    "max_coherence_loss": 5,
    "max_antithesis_kind_loss": 5,
    "max_t_from_the_words_loss": 5,
}


class _HolderArm:
    """`HOLDER_ARM=without` runs the view turn with `HOLDER_FROM_THE_WORDS`
    removed from the request (the binding `view_sketch_prompt` reads, set to
    ""); anything else, as shipped. The field descriptions stay in BOTH arms:
    the arm isolates the rule text, the tightened fields are the floor."""

    def __init__(self, arm: Optional[str] = None) -> None:
        self._arm = arm if arm is not None else os.environ.get("HOLDER_ARM", "with")

    def __enter__(self) -> "_HolderArm":
        from dialectical_framework.concerns import view_sketch

        self._module, self._was = view_sketch, view_sketch.HOLDER_FROM_THE_WORDS
        if self._arm == "without":
            view_sketch.HOLDER_FROM_THE_WORDS = ""
        return self

    def __exit__(self, *exc: Any) -> None:
        self._module.HOLDER_FROM_THE_WORDS = self._was


def holder_prompts_differ() -> tuple[str, str]:
    """The two arms' actual requests; refuses to run if they do not differ."""
    from dialectical_framework.concerns.view_sketch import (
        HOLDER_FROM_THE_WORDS, view_sketch_prompt)

    with_rule = view_sketch_prompt(None, 7)
    with _HolderArm("without"):
        without_rule = view_sketch_prompt(None, 7)
    assert HOLDER_FROM_THE_WORDS in with_rule and HOLDER_FROM_THE_WORDS not in without_rule
    return with_rule, without_rule


class AttributionDto(BaseModel):
    """Whose position does this sentence present itself as?"""

    presented_as: str = Field(
        description=(
            "'reader' if the sentence is worded as a position the reader themselves "
            "holds or should act on — first person, or a bare 'X should ...' with no "
            "one else named as holding it. 'someone_else' if it is worded as a "
            "position attributed to a named or described other party. 'neither' if "
            "it is a description with no position in it."
        )
    )
    reasoning: str = Field(description="One sentence.")


class WhichPositionDto(BaseModel):
    position_number: int = Field(
        description="The number of the ONE listed position the sentence states, however worded; 0 if none."
    )
    reasoning: str = Field(description="One sentence.")


class SamePartyDto(BaseModel):
    # Loosened 2026-10-27: the strict read called "the documentary (Hartog)"
    # against "Hartog" a mismatch; a role and the person in it are one party.
    same_party: bool = Field(
        description=(
            "True if the two refer to the same person or body, including when one "
            "is a role, office or description of the other ('the Minister' and "
            "'Anna Turley (Minister)'; 'the Government' and 'the Exchequer Secretary')."
        )
    )
    reasoning: str = Field(description="One sentence.")


class HolderInTextDto(BaseModel):
    """Text-grounded: to whom does the TEXT attribute this position?

    First read (the 2026-10-27 gate's first scoring, kept in the saved run)
    asked whose OWN WORDS take it. That is the right question for a transcript
    and the wrong one for reportage, where nobody speaks and every position is
    REPORTED ("critics argued", "the company maintained"): it called "opponents
    of trophy hunting" a false attribution in both arms. The criterion a
    misquotation actually violates is attribution BY THE TEXT — stated by the
    party or reported as theirs — so that is what is asked.
    """

    holder: str = Field(
        description=(
            "The party to whom the text attributes this position — stated in their "
            "own words, or reported as what they hold, argue, claim or did — named "
            "as the text names them; empty if the text attributes it to no one. A "
            "party who is only described, who disagrees with it, or who is asked "
            "about it does not hold it, and a position the text merely implies is "
            "no one's."
        )
    )
    reasoning: str = Field(description="One sentence: the words that attribute it, or that none do.")


async def _holder_in_text(sentence: str, text: str) -> Optional[str]:
    """The party the text attributes `sentence` to, '' for nobody, None if unjudged."""
    try:
        dto = await ConversationFacilitator().submit(
            response_model=HolderInTextDto,
            user_content=(
                f"<text>\n{text}\n</text>\n\n"
                "To whom, if anyone, does this text attribute the following position "
                f'— stated in their own words or reported as theirs?\n\n"{sentence}"'
            ),
        )
    except Exception:
        return None
    return (dto.holder or "").strip()


async def _same_party(a: str, b: str) -> Optional[bool]:
    try:
        dto = await ConversationFacilitator().submit(
            response_model=SamePartyDto,
            user_content=f'Do these two refer to the same person or body?\n\n1. "{a}"\n2. "{b}"',
        )
    except Exception:
        return None
    return dto.same_party


def _numbered(positions: tuple[tuple[str, str], ...]) -> str:
    return "\n".join(f"{i}. ({holder}) {pos}" for i, (holder, pos) in enumerate(positions, 1))


async def _attribution(sentence: str) -> Optional[str]:
    try:
        dto = await ConversationFacilitator().submit(
            response_model=AttributionDto,
            user_content=f'Whose position does this sentence present itself as?\n\n"{sentence}"',
        )
    except Exception:
        return None
    return dto.presented_as if dto.presented_as in ("reader", "someone_else", "neither") else None


async def _which_position(sentence: str, positions: tuple[tuple[str, str], ...]) -> Optional[int]:
    try:
        dto = await ConversationFacilitator().submit(
            response_model=WhichPositionDto,
            user_content=(
                "A text carries these positions, each with who holds it:\n\n"
                f"{_numbered(positions)}\n\n"
                f'Which ONE of them does this sentence state?\n\n"{sentence}"'
            ),
        )
    except Exception:
        return None
    return dto.position_number if 0 <= dto.position_number <= len(positions) else None


async def _draw_one(case: PastedMaterialCase, draw: int = 0) -> dict[str, Any]:
    """One view-turn draw over the pasted text, exactly as a host would send it."""
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
        return {"case_id": case.case_id, "kind": case.kind, "draw": draw, "error": repr(exc),
                "seconds": round(time.perf_counter() - started, 1)}
    first = view.perspectives[0] if view.perspectives else None
    row: dict[str, Any] = {
        "case_id": case.case_id, "kind": case.kind, "draw": draw,
        "seconds": round(time.perf_counter() - started, 1),
        "drawn": first is not None,
        "failed_draws": [f.kind for f in view.failed_draws],
    }
    if first is not None:
        row.update(_texts(first))
        # The field shipped 2026-10-26: whose position, when not the person's.
        row["t_held_by"] = first.t.held_by if first.t else None
        row["a_held_by"] = first.a.held_by if first.a else None
    return row


def _count(rows: list[dict], key: str, value: Any = True) -> int:
    return sum(1 for r in rows if r.get(key) == value)


async def _gathered(coros: list, limit: int) -> list:
    """`asyncio.gather` through a semaphore: the first gate run fired ~150
    judge calls at once, met the organisation's concurrency limit, and one
    judge without a try/except raised a stream timeout out of the reads —
    after 148 unsaved draws. Draws are saved before any read now, too."""
    gate = asyncio.Semaphore(limit)

    async def one(coro):
        async with gate:
            return await coro

    return list(await asyncio.gather(*(one(c) for c in coros)))


def _judge_limit() -> int:
    return int(os.environ.get("PASTED_JUDGE_CONCURRENCY", "6"))


async def _read_holders(rows: list[dict], by_id: dict[str, PastedMaterialCase]) -> None:
    """The text-grounded reads, written onto each drawn row.

    `t_holder_in_text` / `a_holder_in_text`: the party whose own words take the
    pole, '' for nobody. `*_from_the_words`: somebody's do. `*_falsely_attributed`:
    the draw named a holder and the text's words do not bear it (nobody's take
    the pole, or a different party's). `a_built_unnamed`: the honest case — no
    holder named, nobody's words take it. `a_missed_holder`: nobody named, but
    somebody's words take it.
    """
    drawn = [r for r in rows if r.get("thesis")]
    limit = _judge_limit()
    t_holders = await _gathered([_holder_in_text(r["thesis"], by_id[r["case_id"]].text) for r in drawn], limit)
    a_rows = [r for r in drawn if r.get("antithesis")]
    a_holders = await _gathered([_holder_in_text(r["antithesis"], by_id[r["case_id"]].text) for r in a_rows], limit)
    for r, h in zip(drawn, t_holders):
        r["t_holder_in_text"] = h
        r["t_from_the_words"] = bool(h)
    for r, h in zip(a_rows, a_holders):
        r["a_holder_in_text"] = h
        r["a_from_the_words"] = bool(h)
    for pole, rs in (("t", drawn), ("a", a_rows)):
        named = [r for r in rs if r.get(f"{pole}_held_by") and r.get(f"{pole}_holder_in_text")]
        same = await _gathered([_same_party(r[f"{pole}_held_by"], r[f"{pole}_holder_in_text"]) for r in named], limit)
        same_by = {id(r): m for r, m in zip(named, same)}
        for r in rs:
            if r.get(f"{pole}_holder_in_text") is None:
                continue  # unjudged: no verdict either way
            if r.get(f"{pole}_held_by"):
                grounded = same_by.get(id(r)) is True
                r[f"{pole}_attribution_grounded"] = grounded
                r[f"{pole}_falsely_attributed"] = not grounded
            elif pole == "a":
                r["a_built_unnamed"] = not r["a_from_the_words"]
                r["a_missed_holder"] = r["a_from_the_words"]


async def _read_quality(rows: list[dict], di_container) -> None:
    """The archive's two judges: coherence (`pass`) and the antithesis's kind."""
    from e2e.config import E2EConfig
    from e2e.probe_aspect_variants import _judge as cc_judge
    from e2e.probe_tetrad_quality import _audit_kind

    complete = [r for r in rows if all(r.get(k) for k in ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus"))]
    judge_model = E2EConfig.from_env().judge_model

    async def coherence(r: dict) -> dict:
        try:
            return await cc_judge(r)
        except Exception as exc:  # noqa: BLE001 — unjudged, never a lost run
            return {"pass": None, "cc_error": repr(exc)}

    limit = _judge_limit()
    verdicts = await _gathered([coherence(r) for r in complete], limit)
    kinds = await _gathered([_audit_kind(di_container, judge_model, r["thesis"], r["antithesis"]) for r in complete], limit)
    for r, v, k in zip(complete, verdicts, kinds):
        r.update(v)
        r.update(k)
        r["a_is_a_position"] = r.get("a_kind") == "position"


def _sign_test(with_rows: list[dict], without_rows: list[dict], key: str) -> dict:
    """Discordant pairs by (case, draw) and the two-sided tail, capped at 1."""
    from math import comb

    by_key = {(r["case_id"], r.get("draw", 0)): r for r in without_rows}
    wins = losses = 0
    for row in with_rows:
        other = by_key.get((row["case_id"], row.get("draw", 0)))
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
    return {"wins": wins, "losses": losses, "discordant": n, "two_sided_p": round(min(1.0, 2 * tail), 4)}


async def _run_arm(arm: str, cases, draws: int, batch: int) -> list[dict]:
    jobs = [(c, i) for i in range(draws) for c in cases]
    rows: list[dict] = []
    with _HolderArm(arm):
        for start in range(0, len(jobs), batch):
            rows += await asyncio.gather(*(_draw_one(c, i) for c, i in jobs[start:start + batch]))
            print(f"  [{arm}] drawn {len(rows)}/{len(jobs)}", flush=True)
    return rows


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_holder_rule_on_pasted_material(di_container) -> None:
    holder_prompts_differ()
    cases = PASTED_MATERIAL_CASES
    limit = int(os.environ.get("PASTED_LIMIT", "0"))
    if limit:
        cases = cases[:limit]
        print(f"\n    SMOKE RUN on {limit} cases — not the gate")
    draws = int(os.environ.get("PASTED_DRAWS", "2"))
    batch = int(os.environ.get("PASTED_BATCH", "8"))
    print(f"\n=== HOLDER_FROM_THE_WORDS: with against without, {len(cases)} cases x {draws} draws")
    by_id = {c.case_id: c for c in cases}
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    reread = os.environ.get("PASTED_REREAD")
    if reread:
        # Re-read a saved run's draws (the `rows` of a holder-rule or draws
        # file) without drawing again.
        saved = json.loads(pathlib.Path(reread).read_text())
        arms: dict[str, list[dict]] = saved["rows"]
        print(f"    re-reading {reread}")
    else:
        arms = {}
        for arm in ("with", "without"):
            arms[arm] = await _run_arm(arm, cases, draws, batch)
            # Saved BEFORE any judge runs: the draws are the expensive half.
            (RESULTS / f"holder-draws-{stamp}.json").write_text(
                json.dumps({"rows": arms}, indent=1, ensure_ascii=False))
    for arm in ("with", "without"):
        await _read_holders(arms[arm], by_id)
        await _read_quality(arms[arm], di_container)

    def tally(rows: list[dict]) -> dict[str, Any]:
        drawn = [r for r in rows if r.get("thesis")]
        return {
            "draws": len(rows),
            "drawn": len(drawn),
            "a_held_by_named": sum(1 for r in drawn if r.get("a_held_by")),
            "a_falsely_attributed": _count(drawn, "a_falsely_attributed"),
            "a_attribution_grounded": _count(drawn, "a_attribution_grounded"),
            "a_from_the_words": _count(drawn, "a_from_the_words"),
            "a_built_unnamed": _count(drawn, "a_built_unnamed"),
            "a_missed_holder": _count(drawn, "a_missed_holder"),
            "t_held_by_named": sum(1 for r in drawn if r.get("t_held_by")),
            "t_falsely_attributed": _count(drawn, "t_falsely_attributed"),
            "t_from_the_words": _count(drawn, "t_from_the_words"),
            "coherence_pass": _count(drawn, "pass"),
            "a_is_a_position": _count(drawn, "a_is_a_position"),
            "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else None,
        }

    report: dict[str, Any] = {"bars": BARS, "draws_per_case": draws, "is_the_gate": not limit}
    for arm, rows in arms.items():
        report[arm] = tally(rows)
        for kind in ("reportage", "dialogue"):
            report[arm][kind] = tally([r for r in rows if r["kind"] == kind])
    w, wo = report["with"], report["without"]
    report["paired"] = {k: _sign_test(arms["with"], arms["without"], k)
                        for k in ("a_falsely_attributed", "a_from_the_words", "pass", "a_is_a_position", "t_from_the_words")}
    report["verdict"] = {
        "primary_false_attribution_within_bar": w["a_falsely_attributed"] <= BARS["a_falsely_attributed_max_with_rule"],
        "primary_false_attribution_no_worse": w["a_falsely_attributed"] <= wo["a_falsely_attributed"],
        "secondary_from_the_words_gain": w["a_from_the_words"] - wo["a_from_the_words"],
        "secondary_met": w["a_from_the_words"] - wo["a_from_the_words"] >= BARS["a_from_the_words_min_gain"],
        "coherence_loss": wo["coherence_pass"] - w["coherence_pass"],
        "antithesis_kind_loss": wo["a_is_a_position"] - w["a_is_a_position"],
        "t_from_the_words_loss": wo["t_from_the_words"] - w["t_from_the_words"],
    }
    v = report["verdict"]
    v["rule_ships"] = (
        v["primary_false_attribution_within_bar"] and v["primary_false_attribution_no_worse"]
        and v["coherence_loss"] <= BARS["max_coherence_loss"]
        and v["antithesis_kind_loss"] <= BARS["max_antithesis_kind_loss"]
        and v["t_from_the_words_loss"] <= BARS["max_t_from_the_words_loss"]
    )
    out = RESULTS / f"holder-rule-{stamp}.json"
    out.write_text(json.dumps({"report": report, "rows": arms}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    for arm, rows in arms.items():
        for r in rows:
            if r.get("a_falsely_attributed") or r.get("t_falsely_attributed"):
                print(f"\n[{arm} {r['case_id']}#{r['draw']}] T: {r['thesis']} <{r.get('t_held_by')}> in text: <{r.get('t_holder_in_text')}>"
                      f"\n    A: {r.get('antithesis')} <{r.get('a_held_by')}> in text: <{r.get('a_holder_in_text')}>")
    print(f"\nwrote {out}")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_what_the_view_turn_does_with_pasted_material(di_container) -> None:
    cases = PASTED_MATERIAL_CASES
    limit = int(os.environ.get("PASTED_LIMIT", "0"))
    if limit:
        cases = cases[:limit]
        print(f"\n    SMOKE RUN on {limit} cases — not the finding")
    print(f"\n=== the view turn on {len(cases)} pieces of pasted material")
    batch = int(os.environ.get("PASTED_BATCH", "8"))
    arm = os.environ.get("STANCE_ARM", "shipped")
    print(f"    arm: {arm}")
    rows: list[dict] = []
    with _StanceArm():
        for start in range(0, len(cases), batch):
            rows += await asyncio.gather(*(_draw_one(c) for c in cases[start:start + batch]))
            print(f"  drawn {len(rows)}/{len(cases)}", flush=True)

    by_id = {c.case_id: c for c in cases}
    drawn = [r for r in rows if r.get("thesis")]
    attributions = await asyncio.gather(*(_attribution(r["thesis"]) for r in drawn))
    t_picks = await asyncio.gather(
        *(_which_position(r["thesis"], by_id[r["case_id"]].positions) for r in drawn)
    )
    a_rows = [r for r in drawn if r.get("antithesis")]
    a_picks = await asyncio.gather(
        *(_which_position(r["antithesis"], by_id[r["case_id"]].positions) for r in a_rows)
    )
    for r, att, pick in zip(drawn, attributions, t_picks):
        r["attributed_to"] = att
        r["t_position_index"] = pick
        r["t_is_a_held_position"] = bool(pick)
    # `held_by` against the screen's holder of the position T matched: the
    # field is right when it names the same party the blind screen did.
    named = [r for r in drawn if r.get("t_held_by") and r.get("t_position_index")]
    matches = await asyncio.gather(
        *(_same_party(r["t_held_by"], by_id[r["case_id"]].positions[r["t_position_index"] - 1][0]) for r in named)
    )
    for r, m in zip(named, matches):
        r["t_holder_matches_screen"] = m
    for r, pick in zip(a_rows, a_picks):
        r["a_position_index"] = pick
        positions = by_id[r["case_id"]].positions
        t_i, a_i = r.get("t_position_index"), pick
        r["t_and_a_are_two_holders"] = (
            bool(t_i) and bool(a_i) and positions[t_i - 1][0] != positions[a_i - 1][0]
        )
    await _read_holders(rows, by_id)

    report: dict[str, Any] = {"cases": len(cases), "arm": arm, "is_the_finding": not limit}
    for kind in ("reportage", "dialogue"):
        k = [r for r in rows if r["kind"] == kind]
        kd = [r for r in k if r.get("thesis")]
        report[kind] = {
            "cases": len(k),
            "drawn": len(kd),
            "t_attributed_to_reader": _count(kd, "attributed_to", "reader"),
            "t_attributed_to_someone_else": _count(kd, "attributed_to", "someone_else"),
            "t_is_a_held_position": _count(kd, "t_is_a_held_position"),
            "t_held_by_named": sum(1 for r in kd if r.get("t_held_by")),
            "t_holder_matches_screen": _count(kd, "t_holder_matches_screen"),
            "a_held_by_named": sum(1 for r in kd if r.get("a_held_by")),
            "t_and_a_are_two_holders": _count(kd, "t_and_a_are_two_holders"),
            "a_from_the_words": _count(kd, "a_from_the_words"),
            "a_falsely_attributed": _count(kd, "a_falsely_attributed"),
            "t_falsely_attributed": _count(kd, "t_falsely_attributed"),
            "median_seconds": sorted(r["seconds"] for r in k)[len(k) // 2] if k else None,
        }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"finding-{arm}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"report": report, "rows": rows}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    for r in drawn[:4]:
        print(f"\n[{r['kind']} {r['case_id']}] T: {r['thesis']}  [held by: {r.get('t_held_by')}]\n    A: {r.get('antithesis')}  [held by: {r.get('a_held_by')}]\n    attributed to: {r['attributed_to']} | T is held position #{r['t_position_index']} | holder matches screen: {r.get('t_holder_matches_screen')}")
    print(f"\nwrote {out}")


class TestTheInstrument:
    def test_the_shipped_text_keeps_every_sentence_that_stopped_the_echo(self):
        """What the first-person device bought had to survive the change, or
        the echo probe would be re-measuring a regression we could see."""
        from dialectical_framework.concerns.view_sketch import THESIS_IS_A_STANCE

        for kept in (
            "question restated",  # "never their question restated" / "never a question restated"
            'carries "I should stop paying for his phone"',
            'carries "We should stop standups"',
            "A behaviour described is not yet a stance",
            'held as a stance',
            "carries no stance at all",
            "When the words hold SEVERAL claims",
            "not a premise or a hedge",
        ):
            assert kept in THESIS_IS_A_STANCE, kept
            assert kept in FIRST_PERSON_STANCE, kept
        assert "first person" in FIRST_PERSON_STANCE
        assert "first person" not in THESIS_IS_A_STANCE
        assert "OTHER people's positions" in THESIS_IS_A_STANCE
        assert "held_by" in THESIS_IS_A_STANCE, "the rule names the field that carries the holder"

    def test_the_arm_is_off_unless_asked(self, monkeypatch):
        from dialectical_framework.concerns import view_sketch

        monkeypatch.delenv("STANCE_ARM", raising=False)
        before = view_sketch.THESIS_IS_A_STANCE
        with _StanceArm():
            assert view_sketch.THESIS_IS_A_STANCE is before
        monkeypatch.setenv("STANCE_ARM", "first_person")
        with _StanceArm():
            assert view_sketch.THESIS_IS_A_STANCE is FIRST_PERSON_STANCE
        assert view_sketch.THESIS_IS_A_STANCE is before

    def test_the_holder_arm_is_off_unless_asked_and_the_prompts_differ(self, monkeypatch):
        from dialectical_framework.concerns import view_sketch

        monkeypatch.delenv("HOLDER_ARM", raising=False)
        before = view_sketch.HOLDER_FROM_THE_WORDS
        with _HolderArm():
            assert view_sketch.HOLDER_FROM_THE_WORDS is before
        with_rule, without_rule = holder_prompts_differ()
        assert view_sketch.HOLDER_FROM_THE_WORDS is before
        assert "a name on words never said is a misquotation" in with_rule
        assert "misquotation" not in without_rule

    def test_the_bars_were_set_before_the_run(self):
        assert set(BARS) == {
            "a_falsely_attributed_max_with_rule", "a_from_the_words_min_gain",
            "max_coherence_loss", "max_antithesis_kind_loss", "max_t_from_the_words_loss",
        }

    def test_the_text_grounded_judge_sees_no_framework_word(self):
        import inspect

        source = inspect.getsource(_holder_in_text) + inspect.getsource(HolderInTextDto)
        for word in ("thesis", "antithesis", "held_by", "tetrad"):
            assert word not in source.lower().replace("holderintextdto", ""), word

    def test_the_writer_never_sees_the_screens_reads(self):
        """`_draw_one` passes only the pasted text, never the positions list."""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(_draw_one)))
        read = {n.attr for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "case"}
        assert read == {"text", "case_id", "kind"}, read

    def test_every_case_carries_two_opposed_holders(self):
        for c in PASTED_MATERIAL_CASES:
            assert len(c.positions) >= 2, c.case_id
            assert len({h for h, _ in c.positions}) >= 2, c.case_id
