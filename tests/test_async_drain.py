"""The `gather` barrier cost 45.6s of dead air, and these are the ways removing it could lie.

`drain_completed` replaced `asyncio.gather(..., return_exceptions=True)` at the
Transformation write loop so each result is written as it lands rather than after the
slowest sibling. Two properties carry that, and both are load-bearing:

1. **Results really do arrive in completion order.** If they did not — if the helper
   quietly reintroduced a barrier — the change would be a no-op that reads as a fix,
   and the 120-effect burst would still be a burst. `TestCompletionOrderIsRealNotNominal`
   asserts on observed TIMING, not just on sequence, because a correct order with a
   barrier still yields the right sequence at the wrong moments.
2. **A failure is still a skip, never a propagation.** The call site it replaced used
   `return_exceptions=True`; one bad edge must not take down its siblings. Losing that
   would turn a logged gap the resume machinery tops up into a failed tool call.

DB-free and LLM-free: tasks, sleeps and arithmetic.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dialectical_framework.utils.async_drain import (drain_completed,
                                                     drain_completed_awaitables)


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


async def _after(delay: float, value):
    await asyncio.sleep(delay)
    return value


async def _raising(delay: float, error: BaseException):
    await asyncio.sleep(delay)
    raise error


def _tasks(*pairs: tuple[float, object]) -> dict[asyncio.Task, object]:
    """`{task: context}` where context is the value, so order is checkable."""
    return {asyncio.ensure_future(_after(delay, value)): value for delay, value in pairs}


class TestCompletionOrderIsRealNotNominal:
    """The point of the helper: the first result is usable before the last arrives."""

    @pytest.mark.asyncio
    async def test_results_arrive_in_completion_order_not_submission_order(self):
        tasks = _tasks((0.06, "slow"), (0.01, "fast"), (0.03, "middle"))

        seen = [context async for context, _ in drain_completed(tasks)]

        assert seen == ["fast", "middle", "slow"]

    @pytest.mark.asyncio
    async def test_the_first_result_is_delivered_before_the_slowest_finishes(self):
        """The barrier test, and the reason this file asserts on a clock.

        A helper that gathered internally and then yielded in the right order would
        pass the ordering test above while delivering nothing early — which is
        exactly the defect being fixed, since the person's dead air is set by WHEN
        the write happens, not by what order the writes are in.
        """
        started = time.monotonic()
        tasks = _tasks((0.40, "slow"), (0.01, "fast"))

        arrivals: list[tuple[str, float]] = []
        async for context, _ in drain_completed(tasks):
            arrivals.append((context, time.monotonic() - started))

        first_label, first_at = arrivals[0]
        assert first_label == "fast"
        assert first_at < 0.20, (
            f"the first result took {first_at:.3f}s to arrive while the slowest task"
            " needed 0.40s — a barrier has been reintroduced and the dead air is back"
        )

    @pytest.mark.asyncio
    async def test_the_consumer_body_runs_between_completions(self):
        """Writes must be spread across the work, which is the whole UX claim.

        Recording when the BODY ran (not when the task finished) is the closest
        DB-free analogue of "when did the effect reach the bus".
        """
        started = time.monotonic()
        tasks = _tasks((0.02, "a"), (0.12, "b"), (0.24, "c"))

        body_ran_at: list[float] = []
        async for _, _ in drain_completed(tasks):
            body_ran_at.append(time.monotonic() - started)

        spread = body_ran_at[-1] - body_ran_at[0]
        assert spread > 0.10, (
            f"all three writes happened within {spread:.3f}s of each other, so they"
            " bunched at the end instead of tracking the work"
        )

    @pytest.mark.asyncio
    async def test_every_task_is_delivered_exactly_once(self):
        tasks = _tasks(*[(0.01 * (i % 4), i) for i in range(12)])

        seen = [context async for context, _ in drain_completed(tasks)]

        assert sorted(seen) == list(range(12))
        assert len(seen) == len(set(seen))

    @pytest.mark.asyncio
    async def test_the_result_travels_with_its_own_context(self):
        """The bug `as_completed` invites: a result paired with the wrong context.

        Under `as_completed` the yielded future is not identity-equal to the input,
        so a `dict` lookup keyed by task fails or mismatches. Silent when it
        mismatches, which is why this is pinned rather than trusted.
        """
        tasks = {
            asyncio.ensure_future(_after(0.05, "SLOW-RESULT")): "slow-context",
            asyncio.ensure_future(_after(0.01, "FAST-RESULT")): "fast-context",
        }

        pairs = {context: result async for context, result in drain_completed(tasks)}

        assert pairs == {"slow-context": "SLOW-RESULT", "fast-context": "FAST-RESULT"}

    @pytest.mark.asyncio
    async def test_an_empty_task_map_yields_nothing_and_does_not_hang(self):
        assert [x async for x in drain_completed({})] == []

    @pytest.mark.asyncio
    async def test_simultaneous_completions_are_all_delivered(self):
        """`asyncio.wait` returns a SET when several land in one tick — none may drop."""
        tasks = _tasks(*[(0.02, i) for i in range(6)])

        seen = [context async for context, _ in drain_completed(tasks)]

        assert sorted(seen) == list(range(6))


class TestAFailureIsASkipNotAPropagation:
    """Preserving `gather(..., return_exceptions=True)` — one bad edge, not a dead pair."""

    @pytest.mark.asyncio
    async def test_a_raising_task_does_not_propagate(self):
        tasks: dict[asyncio.Task, str] = {
            asyncio.ensure_future(_raising(0.01, ValueError("nope"))): "bad",
            asyncio.ensure_future(_after(0.02, "ok")): "good",
        }

        seen = [context async for context, _ in drain_completed(tasks)]

        assert seen == ["good"], "the failure must be skipped, not raised or yielded"

    @pytest.mark.asyncio
    async def test_the_error_is_reported_with_its_context(self):
        """Without the context the log line cannot name the edge that failed."""
        reported: list[tuple[str, str]] = []
        tasks: dict[asyncio.Task, str] = {
            asyncio.ensure_future(_raising(0.01, ValueError("boom"))): "edge-a",
        }

        async for _ in drain_completed(tasks, on_error=lambda c, e: reported.append((c, str(e)))):
            pass

        assert reported == [("edge-a", "boom")]

    @pytest.mark.asyncio
    async def test_siblings_still_land_when_several_fail(self):
        tasks: dict[asyncio.Task, str] = {
            asyncio.ensure_future(_raising(0.01, ValueError("a"))): "bad-1",
            asyncio.ensure_future(_after(0.02, "x")): "good-1",
            asyncio.ensure_future(_raising(0.03, RuntimeError("b"))): "bad-2",
            asyncio.ensure_future(_after(0.04, "y")): "good-2",
        }

        seen = [context async for context, _ in drain_completed(tasks)]

        assert seen == ["good-1", "good-2"]

    @pytest.mark.asyncio
    async def test_omitting_on_error_still_skips_rather_than_raises(self):
        """`on_error` is optional, and the default must not be "propagate"."""
        tasks: dict[asyncio.Task, str] = {
            asyncio.ensure_future(_raising(0.01, ValueError("quiet"))): "bad",
        }

        assert [x async for x in drain_completed(tasks)] == []

    @pytest.mark.asyncio
    async def test_a_cancelled_task_is_reported_and_skipped(self):
        """`task.exception()` RAISES on a cancelled task, so it needs its own branch.

        Without the `cancelled()` check this helper would turn one cancelled sibling
        into a `CancelledError` escaping the drain — which reads as the whole tool
        being cancelled.
        """
        victim = asyncio.ensure_future(_after(5.0, "never"))
        tasks: dict[asyncio.Task, str] = {
            victim: "cancelled-one",
            asyncio.ensure_future(_after(0.01, "ok")): "good",
        }
        victim.cancel()

        reported: list[str] = []
        seen = [
            context
            async for context, _ in drain_completed(
                tasks, on_error=lambda c, e: reported.append(c)
            )
        ]

        assert seen == ["good"]
        assert reported == ["cancelled-one"]

    @pytest.mark.asyncio
    async def test_a_task_that_returns_an_exception_is_a_result_not_a_failure(self):
        """The distinction `gather(return_exceptions=True)` could not make.

        `isinstance(result, Exception)` cannot tell "raised" from "returned an
        exception object". Rare, and silent when it bites, which is the kind of
        thing worth pinning while the behaviour is deliberate.
        """
        returned = ValueError("I am data, not a failure")
        tasks: dict[asyncio.Task, str] = {
            asyncio.ensure_future(_after(0.01, returned)): "ctx",
        }

        pairs = [(c, r) async for c, r in drain_completed(tasks)]

        assert pairs == [("ctx", returned)]


class TestTheAwaitableConvenienceWrapper:
    @pytest.mark.asyncio
    async def test_bare_coroutines_are_scheduled_for_the_caller(self):
        """`asyncio.wait` rejects bare coroutines in 3.11+, so the wrapper exists."""
        seen = [
            context
            async for context, _ in drain_completed_awaitables(
                {_after(0.03, "s"): "slow", _after(0.01, "f"): "fast"}
            )
        ]

        assert seen == ["fast", "slow"]

    @pytest.mark.asyncio
    async def test_failures_are_skipped_here_too(self):
        seen = [
            context
            async for context, _ in drain_completed_awaitables(
                {_raising(0.01, ValueError("x")): "bad", _after(0.02, "y"): "good"}
            )
        ]

        assert seen == ["good"]
