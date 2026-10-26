"""
Build and blind-screen a case set of PASTED MATERIAL — text that is not the
reader's own stance — for the view turn's input-kinds question.

The question (CLAUDE.md, the view turn): `THESIS_IS_A_STANCE` presupposes the
text carries the person's own position ("something the person holds ... a claim
they could say in the first person"). A host routes whatever the person pastes
to the view turn; the first app routes everything. So what does the writer do
with an article that reports others' claims, or a transcript of other people's
argument? Nothing in `src/` distinguishes the two kinds, and the fit judge's two
reads both presuppose authorship. This is a FINDING run, not a gate: one arm,
the shipped prompts, and a read of what came back.

Two kinds, two licence-clean public sources, both real and both written by
people with no knowledge of this framework:

* REPORTAGE — Wikinews articles (CC BY 2.5), category Politics and conflicts,
  120-320 words, carrying at least two markers of reported disagreement. The
  author takes no position; the positions in the text are other people's.
* DIALOGUE — Hansard (Open Parliament Licence), a window of 3-5 consecutive
  Commons contributions by at least two named members, 150-350 words. The
  positions are the speakers'; none is the reader's.

The screen, blind as `screen_multiclaim_inputs.py` is blind: for each text it
reports whether the AUTHOR of the text asserts a position of their own, and
lists the positions the text carries with who holds each. Never shown the
framework's vocabulary. Items pass when the author asserts nothing of their own
and at least two held positions are listed. The listed positions are what the
probe's reads then choose among.

    poetry run pytest tests/e2e/screen_pasted_material.py --real-llm -q -s

Pools come from `PASTED_POOLS` (JSON files, built by the fetch scripts recorded
in the dev note); writes `results/pasted/screen-<stamp>.json`. Models come from
the environment; no model id is written here.
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

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

RESULTS = pathlib.Path(__file__).parent / "results" / "pasted"
MAX_CONCURRENT = 6


class HeldPosition(BaseModel):
    holder: str = Field(description="Who holds it, as the text names them (a person, a body, 'critics', 'the government').")
    position: str = Field(description="The position, one short sentence, in the holder's terms.")


class WhoseClaimsDto(BaseModel):
    """A plain read of whose claims a piece of writing carries."""

    author_asserts_own_position: bool = Field(
        description=(
            "True if the WRITER of this text asserts a position of their own — "
            "argues, demands, recommends in their own voice. False if the text only "
            "reports, quotes or records what others say and do."
        )
    )
    author_position: Optional[str] = Field(
        default=None,
        description="If True above, the author's own position in one sentence; else null.",
    )
    held_positions: list[HeldPosition] = Field(
        description=(
            "Every distinct position the text carries, with who holds it. A "
            "position reported twice is one position."
        )
    )
    positions_are_opposed: bool = Field(
        description="True if at least two of the held positions are opposed to each other."
    )


_PROMPT = """Read this text and say whose claims it carries.

<text>
{text}
</text>

Report only what the text does. Do not judge the positions, and do not add any the text does not carry."""


async def _read(text: str) -> WhoseClaimsDto:
    return await ConversationFacilitator().submit(
        response_model=WhoseClaimsDto, user_content=_PROMPT.format(text=text)
    )


def qualifies(read: WhoseClaimsDto) -> bool:
    return (
        not read.author_asserts_own_position
        and len(read.held_positions) >= 2
        and read.positions_are_opposed
    )


@pytest.mark.asyncio
async def test_screen_builds_the_pasted_material_set() -> None:
    pools = os.environ["PASTED_POOLS"].split(":")
    candidates: list[dict[str, Any]] = []
    for path in pools:
        for item in json.load(open(path, encoding="utf-8")):
            candidates.append({**item, "kind": "dialogue" if "speakers" in item else "reportage"})
    print(f"\ncandidates: {len(candidates)} from {len(pools)} pool(s)")
    gate = asyncio.Semaphore(MAX_CONCURRENT)

    async def one(c: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            try:
                read = await _read(c["text"])
            except Exception as e:
                return {**c, "error": f"{type(e).__name__}: {e}"}
        return {**c, "read": read.model_dump(), "usable": qualifies(read)}

    started = time.monotonic()
    rows = await asyncio.gather(*(one(c) for c in candidates))
    usable = [r for r in rows if r.get("usable")]
    by_kind = {k: sum(1 for r in usable if r["kind"] == k) for k in ("reportage", "dialogue")}
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"screen-{time.strftime('%Y%m%d-%H%M%S')}.json"
    json.dump(
        {"screened": len(rows), "errors": sum(1 for r in rows if r.get("error")),
         "usable": len(usable), "usable_by_kind": by_kind,
         "seconds": round(time.monotonic() - started, 1), "rows": rows},
        out.open("w"), indent=1, ensure_ascii=False,
    )
    print(f"screened {len(rows)} | usable {len(usable)} | by kind {by_kind} | wrote {out}")
    for r in usable[:2]:
        print(f"\n-- [{r['kind']}] {r.get('title') or r.get('debate')}")
        for hp in r["read"]["held_positions"][:3]:
            print(f"   {hp['holder']}: {hp['position']}")
