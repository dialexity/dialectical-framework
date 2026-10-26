"""
Build a case set of REAL multi-claim inputs, and screen it blind.

Why this exists
===============
`THESIS_IS_A_STANCE`'s last sentence (which claim is T when the words hold
several) and `_OPPOSING_POSITION_ASK`'s mirror (an opposition the words already
concede is not an opposition) shipped on 2026-10-20 UNMEASURED, because every
case set in this bench is one sentence and one claim: `probe_tetrad_quality.SET_A`
is "I should quit my job and start my own company." and nineteen more like it. On
such inputs both rules are structurally inert — there is no second claim to
prefer and no concession to refuse — so no existing probe can gate them.

Why the inputs are not written here
===================================
Authoring the polemics would author the result: inputs written by someone who
knows the rule pass the rule. This bench has been burned by instrument problems
twice (the pairwise judge carrying set size and position; four extraction A/Bs
with four verdicts), and a green gate on self-authored inputs would be worse
than no gate because it would look like evidence.

So the inputs are real public text: UK Parliament petitions, fetched from the
site's own JSON API, written by members of the public with no knowledge of this
framework. All content there is Open Government Licence v3.0
(https://petition.parliament.uk/help), so each item is kept with its petition id
and URL for attribution and re-fetching.

The property that makes them a usable instrument: **every petition carries the
author's OWN one-line demand** in its `action` field, stated separately from the
argument in `background` / `additional_details`. The case set feeds the framework
only the argument and holds the `action` back as ground truth, so "is the drawn T
the claim the person would sign" is checked against a label the author wrote, not
against anyone's reading of their text.

Known limitation, to be stated wherever a figure from this set is quoted: the
register is institutional ("We call on the Government to ...") rather than the
first-person polemic a person pastes into a card. It tests the rule's mechanism
on the right STRUCTURE in the wrong VOICE.

The screen
==========
One structured call per candidate, asked in plain discourse-analysis terms and
NEVER shown this framework's vocabulary or rules — no tetrad, no thesis, no
"claim they would sign". It counts the distinct claims, reports whether a
call-to-action is present and whether weaker claims surround it, and quotes the
clause that names and concedes an opposing view, if any. Blindness is the point:
a screen that knew the rule would select for it.

    poetry run pytest tests/e2e/screen_multiclaim_inputs.py --real-llm -q -s

Writes `tests/e2e/results/multiclaim/screen-<stamp>.json`. The model is the one
the environment configures (`DIALEXITY_REASONING_MODEL`, via the framework's own
structured-call seam) — no model id appears in this file.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import time
from typing import Any, Optional

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]

#: How many candidates to screen. Each is one structured call.
SCREEN_LIMIT = int(os.environ.get("MULTICLAIM_SCREEN_LIMIT", "150"))

#: Shortest argument worth screening. Below this there is no room for several
#: claims of differing force.
MIN_WORDS = 70

#: Concurrent screening calls.
MAX_CONCURRENT = 6

RESULTS = pathlib.Path(__file__).parent / "results" / "multiclaim"

#: Lexical markers of a conceded opposing view — a free pre-filter, since the
#: mirror rule needs words that NAME and CONCEDE the other side. Deliberately
#: generous: the structured screen decides, this only orders the queue.
CONCESSION_MARKERS = (
    "not only", "but also", "however", "even if", "even though", "although",
    "while we", "while it", "we accept", "we acknowledge", "admittedly",
    "of course", "granted", "it is true", "no doubt", "whilst",
    "agree that", "understand that", "recognise that", "recognize that",
)

PETITION_SOURCES = (
    "https://petition.parliament.uk/petitions.json?state=open",
    "https://petition.parliament.uk/petitions.json?state=closed",
    "https://petition.parliament.uk/archived/petitions.json?state=closed",
    "https://petition.parliament.uk/archived/petitions.json?state=rejected",
)


class ClaimStructureDto(BaseModel):
    """A plain structural read of a piece of argumentative writing.

    Field order is the order to answer in: the claims first, then what role
    they play. No field names anything from this framework — see the module
    docstring on why the screen is blind.
    """

    distinct_claims: list[str] = Field(
        description=(
            "Each separate claim the text makes, one short phrase each, in the "
            "order they appear. A claim restated in different words is ONE claim."
        )
    )
    call_to_action: Optional[str] = Field(
        default=None,
        description=(
            "The text's clearest demand or call to action, quoted from it. null "
            "if the text only describes or explains and demands nothing."
        ),
    )
    has_weaker_surrounding_claims: bool = Field(
        description=(
            "True if, besides that demand, the text also makes claims that are "
            "weaker or more cautious than it — background, premises, hedges, "
            "things it merely asks or wonders about."
        )
    )
    conceded_opposing_view: Optional[str] = Field(
        default=None,
        description=(
            "A clause in which the text names a view OPPOSED to its own and "
            "grants that it has some truth, quoted from the text (e.g. 'X is "
            "partly right, but ...', 'not only X but also Y'). null if the text "
            "never concedes anything to the other side."
        ),
    )
    is_one_claim_restated: bool = Field(
        description="True if the whole text is a single claim said several ways."
    )


_SCREEN_PROMPT = """Read this piece of argumentative writing and describe its structure.

<text>
{text}
</text>

Report only what the text does. Do not judge whether it is right, well argued or agreeable, and do not add claims it does not make."""


class _Screen:
    """One structured call per text, on the configured reasoning model."""

    async def read(self, text: str) -> ClaimStructureDto:
        return await ConversationFacilitator().submit(
            response_model=ClaimStructureDto,
            user_content=_SCREEN_PROMPT.format(text=text),
        )


def _fetch(url: str) -> Optional[dict[str, Any]]:
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "30", url], capture_output=True, text=True
    )
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def fetch_pool(pages: int = 40) -> list[dict[str, Any]]:
    """Candidates from the petitions API, pre-filtered on length only.

    The concession markers are recorded but not applied: the ordering below
    puts marked items first so the screen sees them within its limit, while the
    unmarked ones still serve the which-claim stratum, which needs several
    claims of differing force and not necessarily a concession.
    """
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    for base in PETITION_SOURCES:
        for page in range(1, pages + 1):
            data = _fetch(f"{base}&page={page}")
            if not data or not data.get("data"):
                break
            for item in data["data"]:
                pid = str(item["id"])
                if pid in seen:
                    continue
                seen.add(pid)
                attrs = item["attributes"]
                body = " ".join(
                    t.strip()
                    for t in (attrs.get("background"), attrs.get("additional_details"))
                    if t
                ).strip()
                if len(body.split()) < MIN_WORDS:
                    continue
                low = body.lower()
                pool.append(
                    {
                        "id": pid,
                        "url": f"https://petition.parliament.uk/petitions/{pid}",
                        # Held BACK from the framework: the author's own demand.
                        "action": attrs["action"],
                        "text": body,
                        "words": len(body.split()),
                        "markers": [m for m in CONCESSION_MARKERS if m in low],
                    }
                )
            time.sleep(0.2)
    pool.sort(key=lambda c: (not c["markers"], -c["words"]))
    return pool


#: Words too common to count as agreement between two phrasings of one demand.
_STOPWORDS = frozenset(
    "a an and are as at be been for from have in into is it its of on or should "
    "that the their them they this to uk us we will with would must need needs "
    "make made all any more most not no new now give given get all every each "
    "government people public".split()
)


def _content_words(phrase: str) -> set[str]:
    return {
        w
        for w in "".join(c.lower() if c.isalnum() else " " for c in phrase).split()
        if len(w) > 2 and w not in _STOPWORDS
    }


def demand_is_in_the_text(action: str, call_to_action: Optional[str]) -> bool:
    """Does the author's own one-line demand actually appear in the argument?

    The gate holds `action` back as ground truth for "the claim the person
    would sign", which only works if that claim is IN the text the framework
    reads. It is not always: petition 305554 demands suspending rent and
    council tax, and its argument never says so — the blind screen read its
    call to action as "Share, Sign, Share." Such an item cannot test the rule
    (no writer could draw a claim that is absent), so it is filtered out here
    rather than counted as a failure later.

    Compared as content-word overlap between the author's phrasing and the
    screen's, since the two are never word for word: half the author's content
    words, or at least two of them, is agreement. Crude on purpose — it is a
    FILTER on the case set, never a measurement, and it is computed from two
    independent phrasings of the same demand, not from the framework's output.
    """
    if not call_to_action:
        return False
    author = _content_words(action)
    if not author:
        return False
    shared = author & _content_words(call_to_action)
    # Two shared content words, after stopwords. A FRACTION of the author's
    # phrasing was tried first and was too strict on a long demand: "Get 80%
    # pay scheme for those whose contract started after 28/02/2020" against the
    # screen's "get the 80% wage scheme" shares two words out of seven, and the
    # demand plainly is in the text. One word is too loose; two, of words this
    # common list does not cover, is the bar a filter can carry.
    need = 1 if len(author) <= 2 else 2
    return len(shared) >= need


def qualifies(read: ClaimStructureDto, action: str) -> tuple[bool, bool]:
    """(usable for the which-claim stratum, usable for the mirror stratum)."""
    multi = (
        len(read.distinct_claims) >= 3
        and not read.is_one_claim_restated
        and bool(read.call_to_action)
        and read.has_weaker_surrounding_claims
        and demand_is_in_the_text(action, read.call_to_action)
    )
    return multi, multi and bool(read.conceded_opposing_view)


@pytest.mark.asyncio
async def test_screen_builds_the_case_set():
    """Fetch, screen, record. Prints the counts and writes the JSON."""
    pool = fetch_pool()
    assert pool, "no candidates fetched — is the petitions API reachable?"
    candidates = pool[:SCREEN_LIMIT]
    print(f"\npool {len(pool)} candidates; screening {len(candidates)}")

    screen = _Screen()
    gate = asyncio.Semaphore(MAX_CONCURRENT)

    async def one(candidate: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            try:
                read = await screen.read(candidate["text"])
            except Exception as e:  # a screen failure is data, not a stop
                return {**candidate, "error": f"{type(e).__name__}: {e}"}
        multi, mirror = qualifies(read, candidate["action"])
        return {
            **candidate,
            "read": read.model_dump(),
            "usable_which_claim": multi,
            "usable_mirror": mirror,
        }

    started = time.monotonic()
    rows = await asyncio.gather(*(one(c) for c in candidates))
    seconds = time.monotonic() - started

    errors = [r for r in rows if r.get("error")]
    which = [r for r in rows if r.get("usable_which_claim")]
    mirror = [r for r in rows if r.get("usable_mirror")]
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"screen-{time.strftime('%Y%m%d-%H%M%S')}.json"
    json.dump(
        {
            "screened": len(rows),
            "errors": len(errors),
            "usable_which_claim": len(which),
            "usable_mirror": len(mirror),
            "seconds": round(seconds, 1),
            "rows": rows,
        },
        out.open("w"),
        indent=1,
    )
    print(
        f"screened {len(rows)} in {seconds:.0f}s | errors {len(errors)} | "
        f"multi-claim with a demand and weaker claims {len(which)} | "
        f"of those, with a conceded opposition {len(mirror)}"
    )
    for row in which[:5]:
        read = row["read"]
        print(f"\n-- {row['id']} ({row['words']}w) claims={len(read['distinct_claims'])}")
        print(f"   author's demand (held back): {row['action']}")
        print(f"   screen's call to action:     {read['call_to_action']}")
        print(f"   conceded opposition:         {read['conceded_opposing_view']}")
    print(f"\nwrote {out}")
    assert len(which) >= 40, (
        f"only {len(which)} usable items; raise MULTICLAIM_SCREEN_LIMIT or widen MIN_WORDS"
    )
