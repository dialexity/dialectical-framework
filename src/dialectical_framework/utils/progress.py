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

    with progress_scope("transformation", key=wheel.short_hash):
        expect_progress(len(tasks) * STEPS)      # denominator, once known
        ...                                      # deep inside the gathered work:
        report_progress("Deriving the reflective counter-move")

Both of the calls inside are free functions reading the ContextVar, which is why the
scope object itself is usually discarded: `ProgressScope.expect` exists because
`expect_progress` needs something to call, and no site in the tree uses the bound form.
Deep code should never be handed a scope — a parameter would just be a second way to
get it wrong.

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

AND ONE AWAIT, FOR THE ONE PHASE THAT CANNOT YIELD ON ITS OWN
=============================================================
`flush_progress` publishes nothing. It buys the loop the turns a fire-and-forget
publish needs, and it is required in exactly one shape: immediately before a stretch
that is SYNCHRONOUS all the way down, where the announcing coroutine will not suspend
again until the stretch it just announced is over. `build_wheels`' combination phase is
that shape and is the widest silence measured in this tree. Everywhere else the next
await is real work and no flush is wanted.

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
import hashlib
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional, TYPE_CHECKING, Union

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

    The exit event carries the count of steps that were ANNOUNCED — see
    `report_progress` for why that is not the same as completed, and for what a
    shortfall does and does not prove. Deliberately not rounded up to `total`:
    "22 of 24" is a fact a host should be able to show, and claiming 24 would hide
    work that was declared and never reached.

    WHEN A SCOPE IS ALREADY INSTALLED this installs nothing and publishes nothing —
    see "THE OUTERMOST SCOPE OWNS THE STREAM" in the module docstring. `total` is
    folded into the outer denominator so a deferring skill's declared work still
    counts, while `stage` and `key` are DISCARDED: one tool call is one stream, and
    the outer names it.

    **THE CLOSING EVENT CARRIES AN EMPTY `detail`, and that is deliberate.** It used
    to read `f"{stage} finished"`, which was wrong three ways. It carried no
    information — its only content was `stage`, which the event already has in its own
    field, so a host was being handed the same string twice. It leaked machinery into
    prose: `stage` is an internal name, and the one that reaches a person on the silent
    Advisor path is `"synthesis finished"` — `synthesis` being a word this tree's
    progress vocabulary bans, since `GenerateSynthesis` opens its own scope under
    `explore`, which owns none. And every replacement wording was worse: anything
    naming the stage is machinery, and anything cheerful (`"Done"`, `"Finished"`) is a
    success claim that `done` cannot back — `report_progress` counts steps ANNOUNCED,
    so a run whose last step raised still closes at 24/24.

    So the closing event says what it actually knows: `final=True`, plus the counters.
    The label beside a host's spinner is the host's to write, and it has `stage`,
    `key`, `done` and `total` to write it from. The side benefit is that the
    banned-vocabulary tests no longer need to exempt `final` — they cover every event
    on the channel now, which is where a leak like `"synthesis finished"` should have
    been caught in the first place.
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
        # Empty on purpose — see the docstring. `stage` is already its own field.
        _publish(scope, detail="", final=True)


def report_progress(detail: str) -> None:
    """Report that a step is STARTING, described by `detail`.

    Publishes with the count of steps ANNOUNCED before this one, then counts this
    one. No-op with no scope installed.

    **`done` COUNTS STEPS ANNOUNCED, NOT STEPS COMPLETED**, and the distinction is
    this function's own doing: it publishes and *then* increments, so a step that
    raises after announcing has already been counted and nothing ever decrements it.
    A run whose 24th step dies still closes at 24/24. The consequence a host has to
    live with is asymmetric and worth stating in both directions: a shortfall
    (`22/24`) proves that two declared steps were never REACHED, which is real
    information; but `24/24` does NOT prove 24 steps succeeded. Failures on this path
    surface as errors in the report, not as a short count.

    The reading "3 of 24 done, now <detail>" was written here for a long time and is
    wrong in exactly that way; it is now "3 announced, now <detail>". Fixing the
    number rather than the sentence would need a completion signal — a second call at
    every site, or a `finally` the seam cannot see into — which is a design change and
    not a docstring's business. It stays deliberately unbuilt while `done` is only
    ever read as motion.

    **`done/total` IS NOT A COMPLETION BAR either, and this was measured rather than
    reasoned.** No event published HERE ever shows `done == total` (again the publish
    precedes the increment), which is why this once claimed the counter never reaches
    its denominator mid-run — a claim the seventh live ingest falsified. The
    denominator is additive, so whenever the last declared step finishes before the
    next site declares one, the STATE sits at `done == total`; there it sat at 19/19
    for 1.9s at 63% of the wall, and the 34 notes streaming in that window put a full
    bar in front of the person before it dropped back to 19/20
    (`tests/e2e/probe_ingest_progress.py`). Notes cannot cause this — they publish the
    counters unchanged — they only make it VISIBLE, which is an argument for them
    rather than against. A host wanting a monotone fraction has to render this as
    "step N, more coming" until `final`.
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

    **WHETHER A NOTE MAY COUNT depends on the caller, not on this site**, which the
    two above settled in opposite directions. The digest's parts say `"3 of 4 parts
    read"`, because exactly one digest runs per ingest, so 4 is the whole of what the
    person is waiting for. The angles say `"Another angle weighed"` with no number,
    because `find_polarities` gathers one such chain PER thesis and each chain can
    only count its own calls: with ten in flight the line read "5 of 11" and then "1
    of 11", each true of its own tension and together a bar falling backwards. **A
    fraction shown to a person is a promise about the whole, so a window that does not
    know the whole may not make one** — report the bare fact instead, that one more
    just came back. Before adding a count, ask who gathers YOUR gather.

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


#: Loop turns `flush_progress` yields. One per hop the in-memory bus needs to carry a
#: publish from `_publish`'s task into a subscriber's hands: the `_send` task itself,
#: the broadcaster backend's listener draining its published queue, then the
#: subscriber's own queue. The fourth is slack.
#:
#: One turn would be enough to fix the TIMESTAMP, since `_send` stamps the event as
#: soon as it runs. It is not enough to fix what the person sees: on the path this
#: exists for, the loop does not get another turn for seconds, so an event sitting in
#: the backend's queue is an event nobody has. Three is the measured floor and the
#: assertion is behavioural for that reason — `test_explore_progress_scope.py`
#: subscribes a real bus and requires the event to have ARRIVED when the flush returns,
#: which fails at 1 and at 2.
_FLUSH_TURNS = 4


async def flush_progress() -> None:
    """Give the loop the turns a just-announced step needs to be DELIVERED.

    `_publish` is fire-and-forget — it hands the send to `loop.create_task` — so an
    announced step does not leave this process until the announcing coroutine suspends.
    Almost everything suspends almost immediately (one provider call, one `gather`),
    which is why no other site in this tree needs this. The exception is a phase that is
    SYNCHRONOUS all the way down, and `build_wheels` owns the widest one measured
    anywhere here: `PerspectiveCombination` builds 24 cycles and 96 wheels at k=4
    without a single await, and that stretch was 110.9s of a 163.2s wall with no event
    of any kind on either channel (`tests/e2e/probe_build_wheels_progress.py`).
    Announcing that phase without this would publish its label only once the phase it
    describes had already ended, then be replaced at once by the next step's — the
    0.0s flash, i.e. worse than silence, because it names the wait as over while the
    person is still in it.

    So: `report_progress(...)` then `await flush_progress()` immediately BEFORE a fully
    synchronous stretch, and nowhere else. A yield in front of real awaited work would
    read as if the seam required one.

    This does NOT make such a phase narratable. Steps announced from INSIDE synchronous
    code have the same delivery problem and no boundary left to flush at, and the graph
    effects it writes arrive in one burst at the end for the same reason. Giving the
    inside of that phase a voice is a redesign of the phase, not of this seam.

    Cheap and safe with no scope installed: it yields either way, which is why callers
    need not ask whether anything is listening.
    """
    for _ in range(_FLUSH_TURNS):
        await asyncio.sleep(0)


def current_progress_scope() -> Optional[ProgressScope]:
    """The installed scope, or None. For tests and for probes."""
    return _current.get()


def progress_key(*parts: Union[str, None, Iterable[str]]) -> str:
    """A stable, opaque id for ONE tool call's progress stream.

    Two reasons, and a tool needs only one of them to want this: **content-derived**,
    so a retried call keys the same stream rather than opening a second one (a retry
    is not new work — `probe_ingest_progress.py`'s first retrying run doubled a digest
    part with no event saying so, which is correct by design); and **hashed**, because
    a key is a host-rendered surface and most of these tools are handed the person's
    own words. `ingest`'s text is whole pasted documents; `anchor`'s and
    `add_input`'s are the person's situation in their own sentences.

    Lists are joined with `,` and the parts with `\\n`, which is byte-for-byte what
    the four private copies built by hand before this existed — pinned by
    `tests/test_progress.py::TestOneKeyConstructionForEveryStream` against the
    literal digests, because a change of construction silently rekeys every stream
    in the tree and nothing else in the suite would notice. Neither delimiter is
    escaped; that is fine because each caller's parts are fixed in position and
    meaning, and a key only ever has to be stable against ITSELF.

    NOT for keys made of hashes. `audit_feasibility` keys on the pathway short hashes
    themselves, joined and sorted and NOT digested, and its comment says why: a short
    hash is already opaque, the model read it off its own prompt, so hashing it again
    hides nothing and costs a host the one thing a key is good for — matching a bar to
    the thing the person just asked about. The dividing line that emerged from the
    tools that followed: name the node when there is ONE the person would recognise
    (`digest_input`, `deepen`, `edit_perspective`), digest when the input is a LIST of
    them (`find_polarities`' ten theses name nothing a person would recognise, and 80
    characters of joined hashes buys a host nothing over 10).

    This is the hoist `analyst._progress_key`'s comment asked the fourth caller to do
    instead of copying the one-liner again. The four private copies remain as thin
    delegates: each is imported by name in tests, each documents what its OWN
    arguments mean, and collapsing them into direct calls would only move that prose
    somewhere less useful.
    """
    # Lists and tuples only, deliberately not sets: iteration order is what makes a
    # key stable, and a set would hand out a different key for the same work.
    material = "\n".join(
        ",".join(part) if isinstance(part, (list, tuple)) else (part or "")
        for part in parts
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


def progress_hash_key(raw: Optional[str]) -> str:
    """Sanitise ONE raw model-supplied hash into a key.

    The counterpart of `progress_key`, for the other half of the tools: where the
    argument identifying the work is a hash rather than the person's text, the key
    is the short hash itself — a hash is already opaque, so digesting it hides
    nothing and costs a host the one thing a key is good for, lining a bar up with
    the node the person just asked about (`audit_feasibility`'s comment argues this
    at length for the list case).

    **A key built from a tool ARGUMENT is built from raw model output.** The scope
    opens above any attempt to resolve the hash, and this framework renders hashes
    into prompts as `[[abc1234]]`, so a model echoing the brackets back — the most
    common malformed-hash shape here, which is why `audit_feasibility` already
    strips them — keyed one stream `"[[a1b2"`: prompt-template punctuation in front
    of a person, and two spellings of ONE node getting two keys, which is the single
    thing a key exists to prevent.

    Only the KEY is sanitised. What a malformed hash should do to the reasoning is
    the resolving skill's decision, never this function's — callers pass the
    argument on untouched.
    """
    return (raw or "").strip().strip("[]")[:7]


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
