"""
Migrating a Consultant session into a Case: what is mined, and from whom.

A person who talked to the tool-less `Consultant` and then upgrades to an
Advisor brings one thing with them — `messages`. The Advisor resumes them like
any head (`Advisor(messages=)`), but resumption alone leaves the Case empty:
nothing was ever written, and the closing seam only runs on NEW turns, so a
decision the person settled in prose is just a reply in the history.
`migrate_consultation` closes that gap by filling the GRAPH, and nothing
else: the host then opens a fresh Advisor on the Case as it always does, and
the new conversation picks up where the old one left off because the memory is
already there — the tensions in the dump, the decisions in the ledger, the
person's own words in the Input's digest. No head is handed back, no synthetic
turn is written into anyone's history; the conversation the person had stays
theirs, and the one they start is new.

It composes the Advisor's own private machinery — the closing seam, the bounded
weave, the drain — because those are what give a migrated decision the grounds
a live closing gets, and duplicating them here would be a second seam to keep
in step. So the utility builds a THROWAWAY Advisor internally, resumed with the
messages, runs the machinery on it, and lets it go; the host never sees it.
This module lives beside the Advisor for exactly that reach.

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
from typing import TYPE_CHECKING, Any, Iterator

from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.turn_timing import ClosingOutcome
from dialectical_framework.concerns.record_decision import UNATTESTED_PRINCIPAL
from dialectical_framework.graph.scope_context import require_current_sid

if TYPE_CHECKING:
    from dialectical_framework.agents.advisor.advisor import Advisor

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


@dataclass
class MigrationReport:
    """What `migrate_consultation` put into the graph, for the host to log or show."""

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


async def migrate_consultation(
    messages: list,
    *,
    principal: str = UNATTESTED_PRINCIPAL,
) -> MigrationReport:
    """Fill the current Case's graph from a Consultant's conversation.

    The upgrade path, as one host call inside the new Case's scope (the Case
    is the host's to create; nothing in `src/` makes one):

        with scope(case.sid):
            report = await migrate_consultation(consultant.messages, principal="human")
            advisor = Advisor(app=spec, principal="human")   # a NEW conversation, as always

    The new conversation starts on a graph that already holds the person's
    case, so it reads as picking up where they left off. What the utility does,
    once, in order:

    1. plants structure from the PERSON's turns only (`person_turns`; the
       module docstring says why speaker-aware): one ingest over their words,
       which also keeps them as an Input the Advisor can read back in full;
    2. weaves what that planted, synchronously — the same bounded weave a
       closing runs off the turn, so step 3 has pathways to ground on;
    3. runs the closing seam over every (person, reply) exchange in order, so
       a decision confirmed in the Consultant session is recorded — under
       `principal`, with the grounds a live closing gets — and a re-affirmation
       is filed as such rather than written twice;
    4. drains the off-turn work those closings started.

    Takes as long as one ingest plus one classifier call per exchange. Returns
    what it did; the host decides whether to show it. A history with no
    person's turn plants nothing and returns an empty report — no error, since
    an empty Case is a valid place to start.
    """
    from dialectical_framework.agents.advisor.advisor import Advisor

    require_current_sid()
    report = MigrationReport()
    turns = person_turns(messages)
    report.turns = len(turns)
    if not turns:
        return report
    # The throwaway head: resumed with the conversation so the seam's classifier
    # sees the standing ledger grow as it replays; unpinned, so the weave joins
    # nothing and creates the exploration this Case starts with; ON_ELECTION
    # only so the off-turn gate is open — no turn is ever run on it.
    head = Advisor(
        messages=messages,
        principal=principal,
        build=BuildPolicy.ON_ELECTION,
        records=True,
    )
    await _seed(head, turns, messages, report)
    logger.info(
        "Migrated a consultation into the graph: %d turn(s), %d perspective(s), "
        "%d pathway(s), %d decision(s) recorded, %d failed",
        report.turns, len(report.perspectives), len(report.pathways),
        report.decisions_recorded, report.decisions_failed,
    )
    return report


async def _seed(advisor: Advisor, turns: list[str], messages: list, report: MigrationReport) -> None:
    """Steps 1–4 of `migrate_consultation`, on the throwaway head."""
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
