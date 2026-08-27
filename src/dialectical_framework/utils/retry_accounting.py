"""Seconds a call spent failing and waiting, kept apart from seconds it spent working.

WHY THIS EXISTS
===============
`use_brain` used to retry a `ParseError` on a curve doubling from 10s to a 120s
cap over 10 attempts. Run to exhaustion that is **750 seconds of `asyncio.sleep`**
— and until this module existed, nothing anywhere recorded that it had happened.

That curve is flat at 2s now (`_PARSE_RETRY_DELAY_S`), which does NOT retire this
module — it is what made the flattening arguable in the first place. The throttle
and 5xx curves still double, and the next expensive retry will be discovered the
same way: by something recording where the seconds went. The measurement outlives
the defect that motivated it.

Bench round r26 measured `anchor` at a 282.8s median and 812.5s max and wrote it
up as the tool's price. Four of its ten `anchor` rounds came in at 807.9s /
808.2s / 812.3s / 812.5s — a four-way tie inside 5 seconds, which is a ceiling
rather than a workload. The ceiling is the retry ladder: ~40s of real work (the
same round's fast values were 36.5–43.5s) plus 750s asleep. All four reported
`ok`, because the retry eventually succeeded. The whole 2.5-hour run logged zero
warnings, since the ParseError branch was the one retry branch that logged
nothing at all.

So the archive could not tell 40 seconds of work from 13 minutes of sleep, and
two separate write-ups quoted the blend as a cost of the framework. This module
makes the split recordable: an accumulator per tool round, mutated by whatever
`use_brain` calls happen inside it.

WHY A MUTABLE OBJECT IN THE CONTEXTVAR, AND NOT A FLOAT
=======================================================
`ToolOutput` rounds are gathered — `execute_tools()` runs a round's calls
concurrently, and several pipelines (`ExploreTransformations`,
`AnalysisPipeline`) fan out further inside a single tool. An `asyncio` task
inherits a COPY of the context at creation, so a `ContextVar.set()` inside a
child task is invisible to the parent that spawned it: a float counter would
silently lose every retry that happened in a gathered call, which is most of
them.

Holding one mutable accumulator means children inherit a copy of the *reference*
and mutate the same object, so the parent sees the total. This is the same reason
the counter is not a return value: the retry happens ten frames below the code
that wants the number, across an API (`llm.call`) that has nowhere to put it.

Not merged into `TurnTiming`: that module describes a conversational turn, and
retries happen under every `use_brain` caller including pipelines that no
conversation ever drives.
"""

from __future__ import annotations

import contextvars
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class RetryAccount:
    """Time lost to attempts that did not produce the answer.

    Deliberately splits the two, because they have different fixes: `sleep_s` is
    a policy number (the backoff curve, which is ours to choose) while
    `failed_attempt_s` is provider work we paid for and threw away (which
    shrinks only by asking for something the model can return).
    """

    #: Seconds spent in `asyncio.sleep` between attempts.
    sleep_s: float = 0.0
    #: Seconds spent inside attempts that then raised a retryable error.
    failed_attempt_s: float = 0.0
    #: How many attempts were retried (NOT how many were made — a call that
    #: succeeded first time contributes 0).
    count: int = 0
    #: Retries per kind: "parse", "rate_limit", "connection", "server".
    kinds: Counter = field(default_factory=Counter)

    @property
    def wasted_s(self) -> float:
        """Seconds that bought nothing — the number to subtract from a round."""
        return self.sleep_s + self.failed_attempt_s


#: A STACK, and every installed account gets every retry — not a single slot that
#: nested blocks replace. `ConversationFacilitator` wants both numbers at once: a
#: per-tool-round account (what did `anchor` waste?) nested inside a per-turn one
#: (what did the whole turn waste?). With replacement semantics the outer account
#: would go blind for the duration of the inner one, and the turn's total would
#: silently exclude its own tool rounds — reporting less waste the more carefully
#: you measured. Adding to every level makes "generation retries" derivable as
#: outer minus the sum of the inners, with nothing double-counted WITHIN a level.
_stack: contextvars.ContextVar[tuple[RetryAccount, ...]] = contextvars.ContextVar(
    "retry_accounts", default=()
)


@contextmanager
def retry_account(account: Optional[RetryAccount] = None) -> Iterator[RetryAccount]:
    """Install an accumulator for the enclosed work and yield it.

    Re-entrant: nesting is normal and both levels see the retry.

    Pass an existing `account` to keep accumulating into it across several
    separate blocks — which is how the streaming path totals a turn. It cannot
    wrap the whole generator instead: an async generator's body runs in the
    context of whoever resumes it (PEP 568 was never implemented), so a `set()`
    that spans a `yield` installs itself in the CONSUMER's context and the
    matching `reset` never runs if the consumer stops iterating early. Every
    block here opens and closes without a yield in between, which is the
    property that keeps that from happening.
    """
    account = RetryAccount() if account is None else account
    token = _stack.set(_stack.get() + (account,))
    try:
        yield account
    finally:
        _stack.reset(token)


def record_retry(kind: str, *, sleep_s: float, attempt_s: float) -> None:
    """Attribute one retried attempt to every installed account.

    A no-op when nothing is installed, which is the common case: most `use_brain`
    callers are pipelines and tests that nobody is timing. Costing nothing when
    unobserved is what lets this sit on the hot path.
    """
    for account in _stack.get():
        account.sleep_s += sleep_s
        account.failed_attempt_s += attempt_s
        account.count += 1
        account.kinds[kind] += 1


def current_retry_account() -> Optional[RetryAccount]:
    """The innermost installed account, or None. For readers that must not create one."""
    stack = _stack.get()
    return stack[-1] if stack else None
