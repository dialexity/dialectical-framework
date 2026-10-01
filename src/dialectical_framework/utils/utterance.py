"""
The person's own words for the turn in progress.

A conversational head sets this around its provider round, so a tool the model
elects on that turn can keep the person's turn VERBATIM as the material a
tension was built from — an `Input` (`tools/anchor.py`). Before this existed the
only trace of what the person said was the model's paraphrase in `anchor`'s
`context` argument and a ≤7-word headline; the wording itself was stored
nowhere.

A ContextVar for the same reason `scope()` is one: the tool is a module-level
function the model calls by name, so it cannot be handed the turn as a
parameter without putting the person's words in the model's hands to edit.
Not ambient magic, though — only the TOOL layer reads it, on the turn: `anchor`
(keeps it as an Input) and `note` (keeps it on the `Note`, for the plant that
comes later). Everything off the turn is handed its utterance explicitly or
None (`_anchor(utterance=)`), because a task created inside a turn inherits
that turn's context and would otherwise attribute an off-turn plant to whatever
the person said last.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_UTTERANCE: ContextVar[Optional[str]] = ContextVar("dialexity_utterance", default=None)


@contextmanager
def speaking(text: Optional[str]) -> Iterator[None]:
    """The person's turn, for the duration of the block. Blank = none."""
    previous = _UTTERANCE.get()
    token = _UTTERANCE.set((text or "").strip() or None)
    try:
        yield
    finally:
        try:
            _UTTERANCE.reset(token)
        except ValueError:
            # A host that closes `chat_stream` from another task runs this
            # finally in a Context the token was not created in; restoring
            # the previous value is the same outcome without the raise.
            _UTTERANCE.set(previous)


def current_utterance() -> Optional[str]:
    """What the person said on the turn in progress, or None outside a turn."""
    return _UTTERANCE.get()
