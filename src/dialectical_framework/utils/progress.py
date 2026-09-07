"""Report work in flight from code that has no graph node to announce yet.

WHAT THIS IS FOR
================
`probe_explore_progress.py` measured `explore`'s transformation phase as **45.6s of
total silence covering 33 of 50 provider calls**, ending in 120 graph effects at
once. The bus was live and the subscription worked; the problem was that a
Transformation is only written once its whole four-call generation chain finishes,
so for those 45.6s there was nothing to *announce*. Optimisation cannot fix that —
`explore` is 85% busy and ~11 stages deep — but a person watching the work happen
sits through 70s and 104s far more alike than either resembles 104s of nothing.

So: two calls at the emission site.

    with progress_scope("transformation", key=wheel.short_hash) as progress:
        progress.expect(len(tasks) * STEPS)      # denominator, once known
        ...                                      # deep inside the gathered work:
        report_progress("Deriving the reflective counter-move")

`report_progress` is a NO-OP when no scope is installed, which is why it can sit on
a hot path and why installing it required no changes to any existing test.

A THIRD CALL, FOR ONE SHAPE THE OTHER TWO CANNOT DESCRIBE
=========================================================
`note_progress` publishes without claiming a step. It exists because a step event says
"this is starting", and that has nothing to say about **N gathered single calls**: they
all start at one instant, so N step events carry one timestamp, and each is one call,
so there is nothing to subdivide. What differs is when they come BACK. Read
`note_progress`'s docstring before adding a second site — the condition is narrow and
the measurement that bounds it is there.

WHY A MUTABLE OBJECT IN THE ContextVar
======================================
Same reason as `retry_accounting` and `call_census`, and it is the whole reason this
works: **an asyncio task inherits a COPY of the context**, so a `ContextVar.set()`
inside a gathered child is invisible to its parent and to its siblings. The var
therefore holds a reference to one MUTABLE `ProgressScope`, and every child mutates
the object all of them can see. `expect()` from one edge pair and
`report_progress()` from another land in the same counter.

The corollary is an ordering requirement that is easy to get wrong: **a task created
BEFORE the scope is installed will never see it**, because it captured the context
at creation. `asyncio.ensure_future` inside the scope, always.

THE OUTERMOST SCOPE OWNS THE STREAM
===================================
Unlike the two measurement instruments — which are stacks, so an inner per-tool
measurement never blinds an outer per-turn one — a nested `progress_scope` does not
install anything. It DEFERS: it folds its `total` into the installed scope, hands
that scope back, and publishes no `final` of its own. A measurement is a fact and two
observers can both want it; a progress event is a *statement to a person*, and one
statement per action beats two competing ones.

This is what makes a skill that can be either an entry point or a sub-step safe to
compose. `ExploreTransformations` and `GenerateSynthesis` each open a scope because
each is reachable directly (`explore`, `explorer.py`, the `generate_synthesis` tool),
and `deepen` calls BOTH — which published two `final` events for one tool call, so a
host cleared its indicator halfway through and started again. Dropping the skills'
scopes was not an option (five call sites, and every future one silent by default);
neither was letting the tool add a third. Deferral makes the tool the owner without
either skill knowing it is nested.

The earlier rule here was the opposite — innermost wins, outer resumes on exit — and
it never described a real nesting in this tree. The only real one was that defect.

An already-CLOSED scope is deferred to as well, which drops the inner events: a task
that outlives the tool's scope still holds a context copy pointing at it, and the
alternative — opening a fresh stream, `final` and all, after the tool has returned —
is the same straggler problem `report_progress` already refuses.

Concurrent SIBLING scopes (two wheels deepened at once) are separate context
branches and neither shadows the other, so both publish. That is what `key` is
for — see `events/progress_event.py`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.events.graph_event_bus import GraphEventBus

#: Set once at DI container setup, next to `ExecutionReport.set_event_bus`. Held
#: module-level rather than reusing `ExecutionReport._event_bus` on purpose: the
#: point of this whole seam is that progress is NOT a graph mutation, and hanging
#: the emitter off the mutation log would blur the line the same day it was drawn.
_event_bus: Optional[GraphEventBus] = None


def set_event_bus(bus: Optional[GraphEventBus]) -> None:
    """Wire the bus progress publishes to. `None` disables (tests, teardown)."""
    global _event_bus
    _event_bus = bus


@dataclass
class ProgressScope:
    """One stage's progress counters, shared by reference across gathered tasks."""

    stage: str
    key: Optional[str] = None
    total: int = 0
    done: int = 0
    #: Guards the final publish so an exception on the way out cannot double it.
    _closed: bool = field(default=False, repr=False)

    def expect(self, steps: int) -> None:
        """Add `steps` to the denominator.

        Additive, not assignment, because the work is discovered concurrently and
        lazily: `explore` learns how many tetrads an edge pair owes only after that
        pair's Phase 1 has run, and pairs run at the same time. Whoever discovers
        work declares it; nobody needs to know the global total.
        """
        if steps > 0:
            self.total += steps


_current: ContextVar[Optional[ProgressScope]] = ContextVar(
    "dialexity_progress_scope", default=None
)


@contextmanager
def progress_scope(
    stage: str, *, key: Optional[str] = None, total: int = 0
) -> Iterator[ProgressScope]:
    """Install a progress scope for `stage`, publishing a `final` event on exit.

    `total` may be left at 0 and grown with `expect()` as work is discovered — the
    common case, since no caller of this knows its step count up front.

    The exit event carries the count that actually COMPLETED, which is below
    `total` when steps failed. Deliberately not rounded up: "22 of 24" is a fact a
    host should be able to show, and claiming 24 would hide a partial build.

    WHEN A SCOPE IS ALREADY INSTALLED this installs nothing and publishes nothing —
    see "THE OUTERMOST SCOPE OWNS THE STREAM" in the module docstring. `total` is
    folded into the outer denominator so a deferring skill's declared work still
    counts, while `stage` and `key` are DISCARDED: one tool call is one stream, and
    the outer names it.
    """
    outer = _current.get()
    if outer is not None:
        outer.expect(total)
        yield outer
        return

    scope = ProgressScope(stage=stage, key=key, total=max(0, total))
    token = _current.set(scope)
    try:
        yield scope
    finally:
        _current.reset(token)
        scope._closed = True
        _publish(scope, detail=f"{stage} finished", final=True)


def report_progress(detail: str) -> None:
    """Report that a step is STARTING, described by `detail`.

    Publishes with the count of steps already finished, then counts this one. So
    an event reads "3 of 24 done, now <detail>", and `done` does not reach `total`
    during the run — the `final` event closes it out. No-op with no scope
    installed.
    """
    scope = _current.get()
    # `_closed` matters for a straggler: a task that outlives the scope still holds a
    # context copy pointing at this object, and a step arriving after the `final`
    # event would tell a host that had already cleared its indicator to start again.
    if scope is None or scope._closed:
        return
    _publish(scope, detail=detail, final=False)
    scope.done += 1


def note_progress(detail: str) -> None:
    """Report that something FINISHED, without claiming a step.

    Publishes the counters unchanged — same `done`, same `total`, `note=True` on the
    event — so a host refreshes its label and leaves its bar alone. No-op with no
    scope installed, and dropped after the scope closes, exactly like
    `report_progress`.

    ONE CONDITION EARNS A NOTE, and it is narrow on purpose: **N single provider
    calls that are gathered, whose window produces no graph effect either.** They all
    start at one instant, so per-item step reporting says nothing; each is one call,
    so there is nothing to subdivide; and they return at DIFFERENT times, which is
    the only remaining fact worth publishing. TWO sites qualify, both on the ingest
    path and both measured: `SourceDigest`'s parts — **25.4s of silence** covering
    four gathered `DigestDto` calls, the widest hole of a 120 KB ingest and one a
    person meets seconds after pasting their document — and
    `AntithesisExtraction._extract_candidates`, an `asyncio.gather` of up to 11
    `ModePointResultDto` calls that writes nothing and is the largest provider-time
    block of that same run (22 calls, 94.2s, mean 4.3s). Both in
    `probe_ingest_progress.py`.

    The second one carries a limit the first does not, worth reading before copying
    it: its own caller gathers one such chain per thesis, so several counters run at
    once and consecutive notes can step BACKWARDS. Each line stays true of its own
    item and the bar never moves, but a numerator is only monotone where the fan-out
    is single-instance.

    Where the gathered calls also FINISH together this buys nothing, and the
    measurement says so: `expand_polarities`' five tetrads start within 0.2s of each
    other and return within 1.5s of each other, and the graph effects they write
    arrive at the same moment as the first completion — so a note there would land on
    top of an event a host already has. Do not add one out of consistency.
    """
    scope = _current.get()
    if scope is None or scope._closed:
        return
    _publish(scope, detail=detail, final=False, note=True)


def expect_progress(steps: int) -> None:
    """Add `steps` to the installed scope's denominator. No-op with no scope.

    The free-function form exists so deep code never has to be handed a scope
    object or thread one through a signature — the ContextVar already carries it,
    and a parameter would just be a second way to get it wrong.
    """
    scope = _current.get()
    if scope is None:
        return
    scope.expect(steps)


def current_progress_scope() -> Optional[ProgressScope]:
    """The installed scope, or None. For tests and for probes."""
    return _current.get()


def _publish(
    scope: ProgressScope, *, detail: str, final: bool, note: bool = False
) -> None:
    """Fire-and-forget publish, mirroring `ExecutionReport._emit`.

    No-op when: no bus is wired, no loop is running (sync callers), or no sid is in
    scope. A progress signal is the most droppable message in the system — it
    describes a moment that has already passed — so every one of those is a silent
    return rather than a raise.
    """
    if _event_bus is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    from dialectical_framework.graph.scope_context import get_current_sid

    sid = get_current_sid()
    if not sid:
        return

    # SNAPSHOT the counters here, not inside `_send`. The scope is mutable and
    # shared, and the task below does not run until the next suspension point — so
    # reading `scope.done` in there reported the count at DELIVERY time, which after
    # a `gather` means every one of a dozen events arrived carrying the same final
    # number. Measured, not theorised: it is what the first version did.
    done, total = scope.done, scope.total

    async def _send() -> None:
        try:
            await _event_bus.publish_progress(
                sid,
                stage=scope.stage,
                done=done,
                total=total,
                detail=detail,
                key=scope.key,
                final=final,
                note=note,
            )
        except Exception:
            # A progress signal must never be able to fail the work it describes.
            # `create_task` would otherwise surface this as an unretrieved-exception
            # warning at GC time, far from here and impossible to attribute.
            logging.getLogger(__name__).debug(
                "progress publish failed for stage %s", scope.stage, exc_info=True
            )

    loop.create_task(_send())
