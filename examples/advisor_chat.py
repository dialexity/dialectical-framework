"""A complete console chat over the Advisor — the five host obligations, running.

Run it:

    cp .env.example .env      # then fill in DIALEXITY_DEFAULT_MODEL
    poetry run python examples/advisor_chat.py

    # or continue a conversation whose Case already exists:
    poetry run python examples/advisor_chat.py --sid <sid>

It needs a reachable graph database and a real LLM provider, so it costs
provider tokens. Type `/quit` (or Ctrl-D) to end the conversation.

`docs/agents.md` lists five things the host application owns and the framework
does not. Every one of them is here, marked `# OBLIGATION n`, because a chat
loop is the smallest program in which all five are load-bearing:

1. DI setup — once at startup.
2. Scope — every turn runs inside `with scope(sid)`, one writer per sid.
3. Message persistence — the host carries the conversation forward.
4. Phase handoff & live updates — not exercised here (single head, no canvas);
   see `docs/agents.md` for the `GraphEventBus`.
5. Draining deferred work — once, after the last turn.

What this file is NOT: a rendering reference. It prints to a terminal because
that keeps the obligations visible. The stream-event contract it relies on
(render the deltas, do not wait for `ResponseComplete`) is the same one a web
host relies on.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import aclosing

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.stream_events import (ResponseComplete,
                                                        TextDelta, ToolResult,
                                                        ToolStart)
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.settings import Settings

PERSONA = """
You are a thinking partner for people facing a genuine dilemma — a choice where
both sides have a real claim. You speak plainly, in the person's own vocabulary,
and you never name your methods.
""".strip()


async def run_turn(advisor: Advisor, user_message: str) -> None:
    """One turn, rendered as it arrives.

    `aclosing` because a host that stops MID-TURN must CLOSE the generator: that
    is what releases the provider's open HTTP response and records the turn's
    seconds. This loop happens to always run to exhaustion, so nothing here
    strictly needs it — which is exactly why it is here. The shape that leaks is
    a bare `async for` with a `break` in it, and the guard belongs in the
    skeleton people copy, not in a footnote about the day they add one.
    """
    streamed_any_text = False
    async with aclosing(advisor.chat_stream(user_message)) as events:
        async for event in events:
            if isinstance(event, TextDelta):
                # Render deltas as they arrive. Waiting for `ResponseComplete`
                # costs the person the whole turn (~18s measured) for text that
                # started arriving in about a second.
                print(event.text, end="", flush=True)
                streamed_any_text = True

            elif isinstance(event, ToolStart):
                # Text yielded before a ToolStart is the model saying what it is
                # about to do. Fine on screen as progress, never persisted as
                # counsel — and never part of the reply.
                if streamed_any_text:
                    print()
                    streamed_any_text = False
                print(f"  … {event.tool_name}", flush=True)

            elif isinstance(event, ToolResult):
                # `error` first: Mirascope turns a raised tool exception into a
                # plain string result, so without this check a crashed tool is
                # indistinguishable from a read-only one that returned prose.
                if event.error:
                    print(f"  ! {event.tool_name} failed: {event.error}", flush=True)

            elif isinstance(event, ResponseComplete):
                # `streamed=True` means `message` is byte-for-byte the deltas
                # already printed — there is nothing left to show. `False` means
                # the deltas were not the reply and this is.
                if not event.streamed:
                    print(event.message)
                elif streamed_any_text:
                    print()
                # Breaking here would be safe (the turn's closing work runs
                # before this event goes out), but the generator is done anyway.


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sid",
        help="Continue an existing Case instead of creating one.",
    )
    args = parser.parse_args()

    # OBLIGATION 1 — DI setup, once at startup. Reads .env.
    DialecticalReasoning.setup(Settings.from_env())

    if args.sid:
        sid = args.sid
    else:
        # A Case owns the sid; every graph write is scoped to it.
        case = Case()
        case.commit()
        sid = case.sid
        print(f"New conversation. Resume it later with --sid {sid}\n")

    # OBLIGATION 3 — message persistence. The host carries the conversation, and
    # `Advisor(messages=...)` is how it hands it back. Held in memory here, which
    # is all a single process needs; a web host puts its store in this variable's
    # place. Note that these are provider message objects, not plain data — a
    # host writing them to disk projects them (role + content is the common
    # choice) and loses tool calls and results in the process.
    saved_messages: list = []
    advisor: Advisor | None = None

    print("Advisor ready. /quit to end.\n")
    try:
        while True:
            try:
                # `input` blocks, and blocking the loop would stall the deferred
                # weave running in the background on this very loop.
                user_message = (await asyncio.to_thread(input, "you › ")).strip()
            except EOFError:
                print()
                break
            if not user_message:
                continue
            if user_message in ("/quit", "/exit"):
                break

            # OBLIGATION 2 — scope. An unscoped turn raises MissingScopeError
            # rather than silently writing nodes with sid=None.
            with scope(sid):
                # A FRESH Advisor per turn, resumed from the saved messages: the
                # stateless shape a web host has, where every request builds its
                # own instance. Nothing leaks — the off-turn weave is keyed by
                # sid, so this instance waits for the weave its predecessor
                # started and cannot begin a second one on the same conversation.
                # Holding one long-lived Advisor for the whole loop works
                # identically; this way round is the one worth showing.
                advisor = Advisor(
                    app_preamble=PERSONA,
                    messages=saved_messages,
                    # A real person is on the other end. That is what lets a
                    # decision they confirm be recorded as THEIR confirmation;
                    # the default attests nobody.
                    principal="human",
                )
                print("advisor › ", end="", flush=True)
                await run_turn(advisor, user_message)
                saved_messages = advisor.messages
    finally:
        # OBLIGATION 5 — drain deferred work, once, after the last turn. Only the
        # host knows there is no next turn. The Advisor weaves a decision's
        # pathway OFF the turn (measured at 127.7s and 387.7s inline), and this
        # is where that finishes. It waits for the CONVERSATION, not for this
        # object — the weave a turn or two back started is drained here too.
        #
        # The timeout is for a shutdown path that must not hang on a slow
        # provider. `False` means work is still running; it is NOT cancelled, so
        # keep waiting, carry on, or drop the loop. Skipping the drain entirely
        # loses nothing but the pathway: every deferred write is fail-soft, and
        # the decision keeps the grounds it was recorded with.
        if advisor is not None:
            with scope(sid):
                drained = await advisor.wait_for_deferred_work(timeout=120)
            if not drained:
                print("(still weaving in the background — leaving it unfinished)")
            print(f"\nConversation saved. Resume with --sid {sid}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
