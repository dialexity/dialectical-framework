"""Consume concurrent tasks in COMPLETION order, so results can be acted on as they land.

WHY THIS EXISTS
===============
CLAUDE.md's concurrency rule is `asyncio.gather` the LLM work, then write graph
nodes sequentially in a loop, because GQLAlchemy is not concurrency-safe. That rule
is about WRITES, and it is correct. But `gather` also imposes a barrier nobody asked
for: the first result to arrive waits for the last one before anything is done with
it.

`probe_explore_progress.py` measured what that barrier costs a person. Effects reach
`GraphEventBus` at graph-write time, so under `gather` the whole Transformation phase
of `explore` was **45.6s of total silence covering 33 of 50 provider calls**, ending
in 120 effects published at once — 95% of that tool's wall clock was dead air on a
stream that otherwise starts inside 1.5s. The work was concurrent and the bus was
live; the only problem was that nothing could be published while the nodes it would
describe did not exist yet.

Draining in completion order removes that barrier without touching anything else:
**writes stay strictly sequential** (the consumer's body runs one iteration at a time,
and if it is synchronous — as `_create_transformation` is — two writes cannot
interleave even in principle), no new event type is needed, and no host-facing
contract changes.

WHAT IT DID NOT FIX, MEASURED
=============================
**It did not close that 45.6s hole, and the reason is worth carrying:
completion-order draining only pays when the tasks are HETEROGENEOUS.** Re-measured
on the same probe after this landed: the gap went 45.6s → 42.9s and the 120-effect
burst spread from one instant to 2.0s. Essentially nothing, because `explore`'s six
tetrad tasks are six *identical* 4-call sequential chains started at the same moment
— so they finish at the same moment, and there is no early result for the drain to
deliver early. I predicted the burst would spread across the whole 43s; it did not,
and the prediction was wrong for a reason visible in the cost probe's own per-caller
table (6 each of five DTOs — perfectly homogeneous work).

So the hole is not caused by the barrier. It is caused by nothing being WRITABLE
until a whole Transformation's 4-call chain finishes, which means the honest signal
during that window is progress ("4 of 6 generated"), not a mutation — the conclusion
the progress probe already reached, and this change does not substitute for it. That
signal now exists on its own channel (`utils/progress.py`) and is what actually
closed the gap: 34.2s → 12.7s, re-measured.

What the drain does still buy, and why it is kept rather than reverted: it removes a
barrier that bites whenever the work ISN'T uniform. One tetrad hitting a ParseError
retry used to hold back the writes of all five siblings; now it holds back only its
own. That is tail behaviour, not median behaviour, so do not expect it to show up in
a median wall clock — and do not cite this module as a latency fix.

WHY `asyncio.wait` AND NOT `as_completed`
========================================
Each result must find its own context — which edge, which candidate, which index —
and `asyncio.wait` hands back the ORIGINAL task objects, so a `dict` keyed by task
works. `asyncio.as_completed` yields wrapper futures that are NOT identity-equal to
the inputs, so the natural `context[task]` lookup silently `KeyError`s (or worse,
matches the wrong item if someone reaches for an index instead). The dict-keyed-by-
task shape is the reason for the choice.

FAILURE SEMANTICS ARE `return_exceptions=True`, DELIBERATELY
============================================================
This replaced `gather(..., return_exceptions=True)` call sites, and preserves that
contract: a task that raised is reported to `on_error` and SKIPPED, never propagated,
because one failed branch of a fan-out must not take down its siblings. The caller
decides what a skip means — for transformations it is a logged gap that the resume
machinery later tops up.

    async for context, result in drain_completed(tasks, on_error=_log):
        write(context, result)   # runs as each task lands, one at a time
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Awaitable, Callable, Optional, TypeVar

#: The per-task context the caller wants handed back with its result.
C = TypeVar("C")
R = TypeVar("R")


async def drain_completed(
    tasks: dict[asyncio.Task, C],
    *,
    on_error: Optional[Callable[[C, BaseException], None]] = None,
) -> AsyncIterator[tuple[C, R]]:
    """Yield `(context, result)` for each task as it completes, failures skipped.

    `tasks` maps each already-scheduled task to whatever the caller needs in order
    to act on its result. Iteration order is completion order, which is the entire
    point — see this module's docstring for what the `gather` barrier was costing.

    The consumer body runs one iteration at a time, so a synchronous write inside
    the loop can never overlap another. Cancellation propagates normally: if the
    consumer breaks out early, the remaining tasks are left running and the caller
    owns them, exactly as with a partially-consumed `gather`.
    """
    pending: set[asyncio.Task] = set(tasks)
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            context = tasks[task]
            # `task.exception()` rather than an `isinstance(result, Exception)`
            # check: the latter is what `gather(return_exceptions=True)` forced,
            # and it cannot tell a raised exception from a task that legitimately
            # RETURNED one. Rare, but the confusion is silent when it happens.
            if task.cancelled():
                if on_error is not None:
                    on_error(context, asyncio.CancelledError())
                continue
            error = task.exception()
            if error is not None:
                if on_error is not None:
                    on_error(context, error)
                continue
            yield context, task.result()


async def drain_completed_awaitables(
    awaitables: dict[Awaitable, C],
    *,
    on_error: Optional[Callable[[C, BaseException], None]] = None,
) -> AsyncIterator[tuple[C, R]]:
    """`drain_completed` for coroutines that have not been scheduled yet.

    Convenience only: it wraps each awaitable with `ensure_future` first, because
    `asyncio.wait` requires Tasks and passing bare coroutines to it is an error in
    3.11+ rather than the silent auto-wrap it used to be.
    """
    tasks: dict[asyncio.Task, C] = {
        asyncio.ensure_future(awaitable): context
        for awaitable, context in awaitables.items()
    }
    async for context, result in drain_completed(tasks, on_error=on_error):
        yield context, result
