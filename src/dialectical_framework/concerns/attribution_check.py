"""
AttributionCheck: do the words bear the holder a drawn pole names?

WHY A CHECK IN CODE
===================
The view turn names WHO holds each pole when it is not the person's own
(`ViewSketchPerspectiveDto.thesis_held_by` / `antithesis_held_by`, carried as
`PoleView.held_by`, since 2026-10-26), and a prompt rule says a party is
named only for a position its own words take (`view_sketch.HOLDER_FROM_THE_WORDS`,
2026-10-27). Measured on 37 pieces of pasted material, two draws each, the
rule HALVED the misquotation and did not end it: about one draw in twenty
still named a party for words the text does not bear — a speaker given the
inverse of their own position, two sides swapped — and a screen shows that
as "the Minister's position" over words the Minister never said. Prompt
enforcement scales with compliance (CLAUDE.md, the machinery leak), so the
last step is the same shape as the thesis pin: enforced by code after the
draw, not asked for again.

WHAT IT DOES
============
One structured call per NAMED holder, shown the person's words and one pole,
asked whether the text attributes that position to that party — stated in
their own words or reported as theirs (a role and the person in it are one
party). NOT attributed: the holder is dropped, so the pole reads as a built
opposition (A) or as unattributed (T) instead of a misquotation. Attributed:
kept. Never a replacement: the judge is not handed the right to put a
different name on the screen. Free where it matters most — on the person's
own words every holder is empty and no call is made.

Fail-soft the way the fit judge is: a failed judging KEEPS the holder. The
alternative, dropping on error, would turn "the Minister's position" into
"your position" on a provider hiccup, which is the 2026-10-26 defect back.
A missing holder is also what `held_by` means on the graph path, so a host
must already handle None.

THE VERDICT'S WORDING IS VERSION 2. Version 1 asked whether the text
"attributes this position" to the party and, applied to the 130 named
holders of the gate's WITH-arm draws, dropped 28 — 18 of the 27 the probe's
own judge had flagged, and 10 it had grounded: it read an elaboration as a
misquotation ("opponents of trophy hunting" refused "killing for pleasure is
wrong" because the text says only that the controversy is about the morality
of hunting for pleasure; a rhetorical question that takes a side was "no
stance"). A dropped true holder costs what this check exists to prevent in
reverse — "the Minister's position" shown as "your position" — so version 2
says a fair condensation of the stance the text gives them is theirs, and
NOT_ATTRIBUTED is no stance at all, the opposite side, or someone else's.

MEASURED (2026-10-27, `tests/e2e/rescore_attribution_check.py`): see
`docs/dev-notes/views.md`, "A name on words never said" — applied to the
saved WITH-arm draws of the holder-rule gate and then live on the 37-case
finding run.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator

logger = logging.getLogger(__name__)


class AttributionDto(BaseModel):
    """One verdict; the safe value first (the mocked suite fills the first)."""

    verdict: Literal["attributed", "not_attributed"] = Field(
        description=(
            "ATTRIBUTED: the text gives that party this position — stated in their "
            "own words, reported as what they hold, argue, claim or did, or a fair "
            "condensation of the stance the text gives them (an opponent of X holds "
            "that X is wrong; a rhetorical question that takes a side takes it; a "
            "role and the person in it, or a group and a member named as its voice, "
            "are one party). Wording that goes a little beyond their words while "
            "keeping their side is still theirs. NOT_ATTRIBUTED: the text gives that "
            "party no stance on this at all, gives them the OPPOSITE side, or gives "
            "this position to someone else; a party who is only described, who "
            "disagrees with it, or who is merely asked about it does not hold it."
        )
    )
    reasoning: str = Field(
        description="One sentence: the words that attribute it, or that none do."
    )


class AttributionCheck:
    """Text-only, graph-free, no report: a check the view turn runs."""

    async def score_texts(
        self, *, position: str, held_by: str, text: str
    ) -> AttributionDto:
        prompt = f"""<text>
{text}
</text>

Does this text attribute the following position to {held_by.strip()} — stated in their own words, or reported as what they hold, argue, claim or did?

"{position.strip()}\""""
        return await ConversationFacilitator().submit(
            response_model=AttributionDto, user_content=prompt
        )


#: The (pole, holder) attribute pairs a tension carries.
_POLES = (("thesis", "thesis_held_by"), ("antithesis", "antithesis_held_by"))


async def drop_unborne_holders(tensions: Sequence[Any], text: str) -> list[str]:
    """Blank every named holder the text does not bear, IN PLACE, on every
    tension given (the winner and the spares alike — a host serving a
    runner-up must not get the misquotation back). Returns one line per
    holder dropped, for the log. No call where no holder is named; a failed
    judging keeps the holder (fail-soft, see the module)."""
    words = (text or "").strip()
    if not words:
        return []
    jobs: list[tuple[Any, str, str, str]] = []
    for tension in tensions:
        for pole, holder_attr in _POLES:
            holder = (getattr(tension, holder_attr, "") or "").strip()
            position = (getattr(tension, pole, "") or "").strip()
            if holder and position:
                jobs.append((tension, pole, holder_attr, holder))

    async def one(job: tuple[Any, str, str, str]) -> bool:
        tension, pole, _attr, holder = job
        try:
            dto = await AttributionCheck().score_texts(
                position=getattr(tension, pole), held_by=holder, text=words
            )
        except Exception as exc:  # noqa: BLE001 — not judged, the holder stays
            logger.warning("Checking a pole's holder failed; it stays: %s", exc)
            return False
        if not isinstance(dto, AttributionDto):
            return False
        return dto.verdict == "not_attributed"

    verdicts = await asyncio.gather(*(one(j) for j in jobs))
    dropped: list[str] = []
    for (tension, pole, holder_attr, holder), unborne in zip(jobs, verdicts):
        if unborne:
            setattr(tension, holder_attr, "")
            dropped.append(f"{pole} held_by {holder!r}: the words do not bear it")
    return dropped
