"""
What the view turn does with material that is not the person's stance.

A FINDING run, one arm (the shipped prompts), over `pasted_material_cases.py`:
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
    rows: list[dict] = []
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
    for r, pick in zip(a_rows, a_picks):
        r["a_position_index"] = pick
        positions = by_id[r["case_id"]].positions
        t_i, a_i = r.get("t_position_index"), pick
        r["t_and_a_are_two_holders"] = (
            bool(t_i) and bool(a_i) and positions[t_i - 1][0] != positions[a_i - 1][0]
        )

    report: dict[str, Any] = {"cases": len(cases), "is_the_finding": not limit}
    for kind in ("reportage", "dialogue"):
        k = [r for r in rows if r["kind"] == kind]
        kd = [r for r in k if r.get("thesis")]
        report[kind] = {
            "cases": len(k),
            "drawn": len(kd),
            "t_attributed_to_reader": _count(kd, "attributed_to", "reader"),
            "t_attributed_to_someone_else": _count(kd, "attributed_to", "someone_else"),
            "t_is_a_held_position": _count(kd, "t_is_a_held_position"),
            "t_and_a_are_two_holders": _count(kd, "t_and_a_are_two_holders"),
            "median_seconds": sorted(r["seconds"] for r in k)[len(k) // 2] if k else None,
        }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"finding-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"report": report, "rows": rows}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    for r in drawn[:4]:
        print(f"\n[{r['kind']} {r['case_id']}] T: {r['thesis']}\n    A: {r.get('antithesis')}\n    attributed to: {r['attributed_to']} | T is held position #{r['t_position_index']}")
    print(f"\nwrote {out}")


class TestTheInstrument:
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
