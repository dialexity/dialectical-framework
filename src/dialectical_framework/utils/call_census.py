"""Which calls a piece of work made, and how much of its wall clock they overlapped.

WHY THIS EXISTS
===============
`retry_accounting` answered "was that wait work or sleep?". With the parse curve
flat, the answer is now "work" almost by construction, and the useful question
moved on: **is a slow tool slow because it makes MANY calls, or because it makes
few in a long CHAIN?** The two have opposite fixes and the same wall clock.

r26 measured `explore` at a 196.0s median with nothing able to tell those apart.
The framework fans out heavily on paper — `ExplorationPipeline` runs wheels
concurrently, `ExploreTransformations` parallelizes edge pairs, Phase 1 edges,
Phase 2 candidates and audits — while each Transformation is documented as **4
sequential `TransformationGeneration` calls + 2 audits**, so the depth is real
too. Which one dominates decides whether the latency work is "do less" or
"restructure the chain", and guessing between them from a wall clock is exactly
the mistake that made `anchor`'s 812.5s read as a workload.

WHAT IT MEASURES, AND THE ONE NUMBER TO READ
============================================
Every completed provider round-trip under an installed census, with its interval.
From those:

    provider_s   sum of every call's duration — total provider time bought
    busy_s       UNION of the intervals — wall time with >=1 call in flight
    parallelism  provider_s / busy_s

`parallelism` is the number to read first. Near 1.0 means the calls happened one
after another and the wall clock IS the chain: fixing it means shortening the
chain, and adding workers would do nothing. Well above 1.0 means the fan-out is
already working and the wall clock is set by the longest dependent path, so the
fix is asking for less, not asking harder. `busy_s / (provider_s / count)` is the
matching read for depth: roughly how many sequential stages deep the work went.

`wall - busy_s` is everything that was not an LLM call: graph writes, orchestration
— **and any wait for the `utils/concurrency.py` semaphore**, because a call is
timed inside its slot, not while queueing for one. Check whether
`DIALEXITY_MAX_CONCURRENT_LLM_CALLS` is set before reading that remainder as
orchestration; unset (the default) it is zero.

Overlaps `RetryAccount.failed_attempt_s` on purpose: a round-trip that then failed
to parse is provider time this module counts and that one calls wasted. Same
seconds, two questions — "what did we buy?" and "what did we throw away?".

A PROBE INSTRUMENT, NOT ALWAYS-ON
=================================
This keeps one record per call, so it is bounded by the work enclosed and is meant
to wrap one tool or one pipeline. `record_call` costs nothing when no census is
installed, which is the common case and what lets it sit on the hot path — but do
not install one around a whole bench run and expect the list to stay small.

WHY A MUTABLE OBJECT IN THE CONTEXTVAR
======================================
Same reason as `retry_accounting`, and it is load-bearing here for exactly the
calls this module exists to count: an `asyncio` task inherits a COPY of the
context, so a `ContextVar.set()` inside a gathered child is invisible to the
parent. Since the fan-out IS the subject, a design that lost gathered calls would
report every parallel stage as if it had never run — and would make any fanned-out
pipeline look perfectly sequential, which is the one conclusion this must not
manufacture.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass(frozen=True)
class CallRecord:
    """One provider round-trip: who asked, for what, how long it took, and when.

    `started`/`ended` are `time.monotonic()` values, kept because the interval —
    not just the duration — is what makes overlap computable. Two 40s calls are
    80s of provider time either way; whether they cost 40s or 80s of someone's
    turn is only answerable from when they ran.
    """

    caller: str
    seconds: float
    started: float
    ended: float
    #: The `format` DTO's name, when the call asked for structured output.
    #:
    #: Load-bearing, not decoration. `caller` alone is nearly useless for the
    #: framework's structured calls: all 33 DTOs reach the provider through ONE
    #: `@use_brain` site inside `ConversationFacilitator`, so `__qualname__` is
    #: the same string for every one of them. The first real run of
    #: `probe_explore_cost.py` proved it — 49 of 50 calls collapsed into a single
    #: `_call_with_response_model.<locals>._llm_call` row, which names the wrapper
    #: and not one thing anybody could act on. The DTO is the discriminator that
    #: survives the seam.
    format_name: Optional[str] = None

    @property
    def label(self) -> str:
        """How this call should be identified to a human reader.

        The DTO first when there is one, because that is what varies at the
        facilitator seam; the caller kept alongside it since two code paths can
        request the same DTO. `.<locals>.<fn>` is stripped — it is an artefact of
        how `use_brain` wraps the method and never distinguishes two callers.
        """
        caller = self.caller.split(".<locals>.")[0]
        return f"{self.format_name} via {caller}" if self.format_name else caller


def _union_seconds(intervals: list[tuple[float, float]]) -> float:
    """Wall time covered by at least one interval — a merge, not a sum.

    Summing would double-count concurrent calls and make a fanned-out stage look
    like it took longer than the clock allows, which is the specific way a
    parallelism figure can come out above the truth.
    """
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start > current_end:
            total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    return total + (current_end - current_start)


@dataclass
class CallCensus:
    """Every provider round-trip made under one block of work."""

    calls: list[CallRecord] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.calls)

    @property
    def provider_s(self) -> float:
        """Total provider time bought, concurrent calls counted separately."""
        return sum(c.seconds for c in self.calls)

    @property
    def busy_s(self) -> float:
        """Wall seconds with at least one call in flight."""
        return _union_seconds([(c.started, c.ended) for c in self.calls])

    @property
    def parallelism(self) -> float:
        """`provider_s / busy_s` — 1.0 is fully sequential, 0.0 means no calls.

        Read this before anything else: it says whether the wall clock is a chain
        (near 1.0, so shorten the chain) or a fan-out (well above 1.0, so ask for
        less). Deliberately not clamped — a value below 1.0 is arithmetically
        impossible and would mean the intervals are wrong, so it should be
        visible rather than rounded away.
        """
        busy = self.busy_s
        return self.provider_s / busy if busy > 0 else 0.0

    @property
    def mean_call_s(self) -> float:
        return self.provider_s / self.count if self.count else 0.0

    @property
    def depth(self) -> float:
        """Roughly how many sequential stages deep the work went.

        `busy_s / mean_call_s`: how many average-length calls would fill the time
        something was in flight. An estimate and nothing more — it cannot see
        dependencies, so a stage of unequal calls reads as a fraction. Useful for
        "about four deep" versus "about twenty deep", never for an exact chain.
        """
        mean = self.mean_call_s
        return self.busy_s / mean if mean > 0 else 0.0

    def by_caller(self) -> list[tuple[str, int, float]]:
        """`(label, count, total_s)`, most provider time first.

        Grouped by `CallRecord.label` — the DTO plus the caller — because grouping
        by caller alone puts every structured call in the framework into one row.
        Sorted by time rather than by count because the point is which concern to
        go and look at, and one 90s call outranks thirty 1s ones for that.
        """
        totals: dict[str, tuple[int, float]] = {}
        for call in self.calls:
            count, seconds = totals.get(call.label, (0, 0.0))
            totals[call.label] = (count + 1, seconds + call.seconds)
        return sorted(
            ((caller, c, s) for caller, (c, s) in totals.items()),
            key=lambda row: row[2],
            reverse=True,
        )


#: A STACK, and every installed census gets every call — same semantics as
#: `retry_accounting._stack` and for the same reason: a per-tool census nested
#: inside a per-turn one must not blind the outer one for the duration of the
#: inner, which is how measuring more carefully ends up reporting less.
_stack: contextvars.ContextVar[tuple[CallCensus, ...]] = contextvars.ContextVar(
    "call_censuses", default=()
)


@contextmanager
def call_census(census: Optional[CallCensus] = None) -> Iterator[CallCensus]:
    """Install a census for the enclosed work and yield it. Re-entrant.

    Opens and closes without a `yield` in between on purpose — see
    `retry_accounting.retry_account` for why spanning one would install into the
    consumer's context instead (PEP 568 was never implemented).
    """
    census = CallCensus() if census is None else census
    token = _stack.set(_stack.get() + (census,))
    try:
        yield census
    finally:
        _stack.reset(token)


def record_call(
    caller: str,
    *,
    seconds: float,
    started: float,
    format_name: Optional[str] = None,
) -> None:
    """Attribute one provider round-trip to every installed census.

    A no-op when nothing is installed, which is the common case: most `use_brain`
    callers are pipelines nobody is measuring.
    """
    stack = _stack.get()
    if not stack:
        return
    record = CallRecord(
        caller=caller,
        seconds=seconds,
        started=started,
        ended=started + seconds,
        format_name=format_name,
    )
    for census in stack:
        census.calls.append(record)


def current_call_census() -> Optional[CallCensus]:
    """The innermost installed census, or None. For readers that must not create one."""
    stack = _stack.get()
    return stack[-1] if stack else None
