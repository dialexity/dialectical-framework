"""
Migrating a Consultant session into a Case: what is mined, and from whom.

A person who talked to the tool-less `Consultant` and then upgrades to an
Advisor brings one thing with them — `messages`. The Advisor resumes them like
any head (`Advisor(messages=)`), but resumption alone leaves the Case empty:
nothing was ever written, and the closing seam only runs on NEW turns, so a
decision the person settled in prose is just a reply in the history.
`advisor_from_consultation` is the factory that closes that gap: it makes the
Advisor, seeds the Case from the conversation, and then lets the Advisor SAY
what it kept — the migration ends as one more exchange in the history (the
person's request to keep the conversation, the Advisor's reply over the graph
it now holds), and the conversation simply goes on from there, graph-backed.
A factory rather than a method on the Advisor because a migration is a way of
MAKING an Advisor, not something an Advisor does to itself — and because the
seam and the weave it composes are the Advisor's own private machinery, which
this module, living beside it, may reach.

SPEAKER-AWARE, BY RULE
======================
Only the person's turns are material for structure. The model's replies are
counsel about the situation, not statements of it, and a transcript mined
speaker-blind would plant the counselor's framings as the person's positions —
the reason a transcript-ingesting "ghost Advisor" was rejected in review
(`rounds.md`, critics' review, 2026-09-24). The replies are still READ, once
each, by the decision seam: `DecisionConfirmationCheck` judges the person's
words first and uses the reply only to state the closing, which is exactly the
pairing a live turn gets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator, Optional

from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.conversation_facilitator import FROM_SETTINGS
from dialectical_framework.agents.turn_timing import ClosingOutcome
from dialectical_framework.concerns.record_decision import UNATTESTED_PRINCIPAL
from dialectical_framework.graph.scope_context import require_current_sid

if TYPE_CHECKING:
    from dialectical_framework.agents.advisor.advisor import Advisor
    from dialectical_framework.agents.app_spec import AppSpec

logger = logging.getLogger(__name__)


def message_text(message: Any) -> str:
    """The plain text of one message, whatever shape the history holds it in.

    Both spellings reach `messages`: Mirascope's own objects (content as a
    `Text` part or a list of parts) and plain dicts from a serialized
    conversation. Non-text parts (tool calls, images) contribute nothing.
    """
    content = message.get("content") if isinstance(message, dict) else getattr(
        message, "content", None
    )
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    try:
        parts = list(content)
    except TypeError:
        return ""
    out: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("type") == "text":
                out.append(str(part.get("text") or ""))
        elif getattr(part, "type", None) == "text":
            out.append(str(getattr(part, "text", "") or ""))
    return "".join(out)


def _role(message: Any) -> str | None:
    if isinstance(message, dict):
        return message.get("role")
    return getattr(message, "role", None)


def person_turns(messages: list) -> list[str]:
    """What the person said, in order, empty turns dropped."""
    return [
        text
        for m in messages
        if _role(m) == "user" and (text := message_text(m).strip())
    ]


def exchanges(messages: list) -> Iterator[tuple[str, str]]:
    """(person's message, the reply that answered it), in order.

    The pairing the closing seam is built for. A user turn with no reply after
    it (the conversation ended on the person's words) is paired with an empty
    reply — the classifier judges the person's words first, so a closing stated
    in the last message is still seen. A reply with no user turn before it
    (a greeting the model opened with) is skipped.
    """
    pending: str | None = None
    for m in messages:
        role = _role(m)
        if role == "user":
            if pending is not None:
                yield pending, ""
            pending = message_text(m).strip()
        elif role == "assistant" and pending is not None:
            yield pending, message_text(m).strip()
            pending = None
    if pending is not None:
        yield pending, ""


#: What the analysis is asked to look for in the person's words. Neutral on
#: purpose: the person's turns are the whole material, and a narrower focus
#: would decide for them what their situation was about.
MIGRATION_INTENT = (
    "Everything this person said in a consultation about their situation. "
    "Find the tensions they are actually holding, in their terms."
)


#: The person's turn that closes the migration — what the upgrade button
#: says, in the person's voice, so the Advisor's first reply is its account of
#: what it kept. A host may pass its own wording (`request=`); the reply is
#: whatever the Advisor says over the graph it now holds, and it is the last
#: message in `advisor.messages` when the factory returns.
MIGRATION_REQUEST = (
    "Keep what we have talked through so far as my case, and tell me what you "
    "have kept: the tensions you see, and anything I decided."
)


@dataclass
class MigrationReport:
    """What the seeding did, logged; the person's account of it is the Advisor's
    own reply to `MIGRATION_REQUEST`."""

    #: The person's turns that were mined (0 = nothing to migrate).
    turns: int = 0
    #: Perspectives the analysis planted from those turns.
    perspectives: list[str] = field(default_factory=list)
    #: Pathways woven over them, synchronously, before the seam ran.
    pathways: list[str] = field(default_factory=list)
    #: Exchanges the decision seam recorded a closing from.
    decisions_recorded: int = 0
    #: Exchanges the seam saw a closing in and could not write (its own
    #: `FAILED` outcome) — worth surfacing, never worth raising.
    decisions_failed: int = 0


async def advisor_from_consultation(
    messages: list,
    *,
    app: Optional[AppSpec] = None,
    app_preamble: Optional[str] = None,
    app_tools: Optional[list] = None,
    principal: str = UNATTESTED_PRINCIPAL,
    build: BuildPolicy = BuildPolicy.ON_ELECTION,
    thinking: Any = FROM_SETTINGS,
    request: str = MIGRATION_REQUEST,
) -> Advisor:
    """Make an Advisor over a fresh Case, seeded from a Consultant's conversation.

    The upgrade path, as one host call inside the new Case's scope (the Case is
    the host's to create; nothing in `src/` makes one):

        with scope(case.sid):
            advisor = await advisor_from_consultation(
                consultant.messages, app=spec, principal="human"
            )
        advisor.messages[-1]   # the Advisor's own account of what it kept
        # then `advisor.chat(...)` as usual — the conversation goes on, graph-backed

    What it does, once, in order:

    1. constructs the Advisor resumed with `messages` — the same head a host
       would build by hand, with `records=True` because there is nothing to
       migrate into otherwise;
    2. plants structure from the PERSON's turns only (`person_turns`; the
       module docstring says why speaker-aware): one ingest over their words;
    3. weaves what that planted, synchronously — the same bounded weave a
       closing runs off the turn, so step 4 has pathways to ground on;
    4. runs the closing seam over every (person, reply) exchange in order, so
       a decision confirmed in the Consultant session is recorded with the
       grounds a live closing gets, and a re-affirmation is filed as such;
    5. drains the off-turn work those closings started, and clears the turn
       fields;
    6. runs ONE ordinary turn on `request` — the person's ask to keep the
       conversation — so the Advisor's first reply, over the graph it now
       holds, is its account of what was kept. That exchange is the last two
       messages in `advisor.messages`; nothing else reports to the person.

    Takes as long as one ingest, one classifier call per exchange, and one
    turn. Refuses `build=NEVER`: it would plant tensions the head may never
    weave — migrate into `ON_ELECTION` or `ON_CONSENT`. Elections are not
    relied on anywhere in the seeding: the person's whole reason to upgrade is
    that they want it kept. Nothing is skipped when the history holds no
    person's turn — the Advisor is still made and still asked, and says so.
    """
    from dialectical_framework.agents.advisor.advisor import Advisor

    require_current_sid()
    build = BuildPolicy(build)
    if not build.off_turn:
        raise ValueError(
            "advisor_from_consultation needs build=ON_ELECTION or ON_CONSENT: "
            "build=NEVER would plant tensions the Advisor may never weave."
        )
    advisor = Advisor(
        app=app,
        app_preamble=app_preamble,
        app_tools=app_tools,
        messages=messages,
        principal=principal,
        build=build,
        records=True,
        thinking=thinking,
    )
    report = MigrationReport()
    turns = person_turns(messages)
    report.turns = len(turns)
    if turns:
        await _seed(advisor, turns, messages, report)
    logger.info(
        "Migrated a consultation: %d turn(s), %d perspective(s), %d pathway(s), "
        "%d decision(s) recorded, %d failed",
        report.turns, len(report.perspectives), len(report.pathways),
        report.decisions_recorded, report.decisions_failed,
    )
    await advisor.chat(request)
    return advisor


async def _seed(advisor: Advisor, turns: list[str], messages: list, report: MigrationReport) -> None:
    """Steps 2–5 of `advisor_from_consultation`, on the Advisor it made."""
    from dialectical_framework.agents.advisor.tools.ingest import _ingest

    ingest_json = await _ingest(
        text="\n\n".join(turns), intent=MIGRATION_INTENT, input_hashes=None
    )
    try:
        report.perspectives = list(
            (json.loads(ingest_json).get("artifacts") or {}).get("perspective_hashes")
            or []
        )
    except (ValueError, AttributeError):
        report.perspectives = []
    report.pathways = await advisor._weave_unwoven_perspectives()

    for person_said, reply in exchanges(messages):
        await advisor._repair_unrecorded_decision(person_said, reply)
        if advisor._last_closing is ClosingOutcome.REPAIRED:
            report.decisions_recorded += 1
        elif advisor._last_closing is ClosingOutcome.FAILED:
            report.decisions_failed += 1
    await advisor.wait_for_deferred_work()
    # A turn's fields, left over from calls that were not turns. Cleared so the
    # first upgraded turn does not inherit the last exchange's verdict as its
    # own (`None` between turns is load-bearing).
    advisor._last_closing = None
    advisor._last_deferral = None
