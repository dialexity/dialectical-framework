"""
note tool: keep what the person asked to have written down — off the turn.

The `BuildPolicy.ON_CONSENT` surface's one way of growing the graph on its own
turn, and it does not grow it ON the turn: the call queues, and the tension is
planted after the reply by the Advisor's off-turn task (`_anchor_noted_tensions`),
which then weaves it as a closing's weave would. So a reply on this surface is
never made to wait for a pipeline, and nothing is planted without the person
saying so — the two properties the policy exists for.

The parameters are `anchor`'s, deliberately: a note IS an anchor whose moment
has moved. Literal values only (thesis, an optional antithesis, the person's own
specifics as context) — no instruction string for an inner model to
re-interpret (CLAUDE.md, "Tool Parameter Clarity").
"""

from __future__ import annotations

from typing import Annotated, Awaitable, Callable

from mirascope import llm
from pydantic import Field

#: What the Advisor hands the factory: queues one note for the off-turn task
#: and returns what the model is told.
NoteSink = Callable[[str, str | None, str], Awaitable[str]]


def build_note(sink: NoteSink):
    """The `note` tool, closed over the Advisor's queue.

    A factory rather than a module-level tool because the queue is per sid and
    reached through the Advisor (`_DEFERRED_WORK`), and the model must never
    hold a parameter that addresses it.
    """

    @llm.tool
    async def note(
        thesis: Annotated[
            str,
            Field(description="The position the person asked to keep — what they hold or champion, in their terms"),
        ],
        antithesis: Annotated[
            str | None,
            Field(
                description="The opposing force, if they named one; omit to have it discovered"
            ),
        ] = None,
        context: Annotated[
            str,
            Field(
                description=(
                    "The person's own specifics behind it — numbers, dates, "
                    "named events, concrete instances they cited, in their "
                    "terms. Facts they stated, not interpretation or advice."
                )
            ),
        ] = "",
    ) -> str:
        """Keep something the person asked to have written down — a position, a tension, a fact of their situation — so the understanding grows around it BETWEEN turns. Nothing is built while they wait; the next turn's understanding holds it. Not for decisions: a confirmed decision goes to record_decision."""
        return await sink(thesis, antithesis, context)

    return note
