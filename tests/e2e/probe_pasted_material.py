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

No bars: nothing shipped claims to handle this input kind, so there is nothing
to pass or fail. The figures are the finding, and the dev note says what they
mean for routing (the documents ladder exists for material) and for the prompt.

    poetry run pytest tests/e2e/probe_pasted_material.py --real-llm -q -s
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
    same_party: bool = Field(description="True if the two names refer to the same person or body.")
    reasoning: str = Field(description="One sentence.")


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


async def _draw_one(case: PastedMaterialCase) -> dict[str, Any]:
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
        return {"case_id": case.case_id, "kind": case.kind, "error": repr(exc),
                "seconds": round(time.perf_counter() - started, 1)}
    first = view.perspectives[0] if view.perspectives else None
    row: dict[str, Any] = {
        "case_id": case.case_id, "kind": case.kind,
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
