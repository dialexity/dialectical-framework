"""
Migrating a Consultant session into a Case: what is mined, and from whom.

A person who talked to the tool-less `Consultant` and then upgrades to an
Advisor brings one thing with them — `messages`. The Advisor resumes them like
any head (`Advisor(messages=)`), but resumption alone leaves the Case empty:
nothing was ever written, and the closing seam only runs on NEW turns, so a
decision the person settled in prose is just a reply in the history.
`Advisor.migrate_conversation` closes that gap, and this module holds the two
pure pieces of it — WHICH words are mined, and how an exchange is paired for the
seam — so they can be pinned DB-free.

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

from dataclasses import dataclass, field
from typing import Any, Iterator


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
    """What `Advisor.migrate_conversation` did, for the host to show or log."""

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
