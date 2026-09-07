"""Probe: does gathering the two poles ADD non-provider overhead at the tool?

WHAT IS OPEN, AND WHICH HALF OF IT THIS CAN ANSWER
==================================================
`IntroducePolarity` gathers its two poles' LLM work. Two measurements of that one
change disagree and the difference has never been accounted for:

* the STAGE frees a directly measured ~6.2s (12.5s serial -> 6.3s gathered,
  `probe_pole_overlap.py`, near-perfect overlap at 0.000s start skew);
* the TOOL moved ~3.3s (median working 40.1s -> 36.8s,
  `probe_anchor_retry_cost.py`).

`probe_pole_overlap.py` refuted the mechanism it was built to test (min-vs-mean
bias explains 0.33s) and bounded contention at ~0.5s of wall, leaving TWO
candidates that it explicitly could not separate:

  (a) **overhead growth** — the freed provider time reappears as non-provider
      wall, so the tool sees less than the stage frees;
  (b) **the 3.3s is simply low** — a difference of medians at n=3 with two
      retrying calls, against a directly measured 6.2s, which makes it the loose
      figure in the comparison.

Both of those earlier probes need `--real-llm` and cost minutes. **Candidate (a)
does not.** "Non-provider wall" is python: graph writes, report merges, event-loop
scheduling. Whether making two coroutines concurrent adds any of it is a
structural question about this code, and a constant, injected per-call delay
answers it deterministically and for free — including at **D = 0**, where there is
no simulated provider at all and every second measured is real framework overhead.

So this probe is scoped to (a), and it is scoped to REFUTING it. If gathering the
poles adds no measurable overhead, (a) is out and (b) is what is left, which
settles the open question by elimination without spending a real-LLM run.

WHY THIS PATH IS THE CLEAN ONE TO ASK ON
========================================
`IntroducePolarity` has exactly ONE caller — the `antithesis` branch of the
`anchor` tool — and there it is `await`ed on its own, with `ExpandPolarity` strictly
after it. Nothing overlaps it, so a stage saved inside it has an unobstructed path
to the tool's wall clock. Any shortfall measured here is overhead, not a fan-out
absorbing the saving in some other branch's critical path.

WHAT THIS CANNOT ANSWER, STATED UP FRONT
========================================
A constant D is not a provider. It removes the pole-cost spread (measured at 0.15s
median, so small), removes retries, and cannot reproduce provider-side contention
— which is exactly what `probe_pole_overlap.py` already bounded at ~0.5s and
explicitly called weak evidence rather than absence. **A null result here does not
say "the poles do not contend at the provider"; it says the framework does not add
overhead when it gathers them.** Those are different claims and only the second
one is in scope.

The mock's call graph is also not the real one. The probe prints its own call count
so it can be checked against the 10-13 that `probe_anchor_retry_cost.py` measured
on this branch; if that number drifts, the harness has stopped modelling the path
and its overhead figures are about something else.

RESULT (2026-09-07, three runs)
===============================
                    run 1 & 2 (quiet machine)      run 3 (loaded)
    overhead, D=0   A 0.31s      B 0.31s           A 0.39-0.59s  B 0.40-0.62s
    median A-B      +0.000 / -0.001 / -0.006s      -0.009 / -0.060 / +0.100s
    union saved     +0.398s (D=0.2) +1.001 (0.5)   +0.400s / +0.999s
    calls 10 in every condition of every run; _fix_cache_breakpoints ~12 us

**(a) is refuted on a BUDGET argument, and that is the part that survives the
noise.** Total non-provider wall for the whole both-poles path is 0.3-0.6s
depending on machine load — and total overhead is a hard CEILING on overhead
GROWTH, since gathering cannot add more of it than exists. Either figure is an
order of magnitude below the 2.2-2.9s being explained.

The A/B difference is the weaker reading and must be quoted with its noise floor:
tight (<=6ms, non-scaling) on a quiet machine, but +-0.1s and non-monotone in D on
a loaded one (-0.060s at D=0.2 against +0.100s at D=0.5 — a trend would not change
sign). So this probe bounds gather-attributable overhead at roughly +-0.1s, about
4% of the gap. What is unaffected across all three runs is `union saved` landing on
2xD to within 2ms, which is the depth reading.

What is left is (b), plus provider-side contention, which is not measurable here.

Run: poetry run pytest tests/probe_pole_gather_overhead.py -s
"""

from __future__ import annotations

import asyncio
import statistics
import time

import pytest

from dialectical_framework.agents.advisor.tools.anchor import anchor
from dialectical_framework.agents.analyst.skills.introduce_polarity import \
    IntroducePolarity
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

THESIS = "Buy out the cofounder now"
ANTITHESIS = "Keep him and reset the terms"
CONTEXT = (
    "Cofounder holds 45% equity. Two anchor accounts are 60% of revenue and "
    "both CEOs call him, not me. Feedback given in March, no change since."
)

#: Per-provider-call delay, in seconds. **0.0 is the load-bearing row**: with no
#: simulated provider at all, every second of wall is framework overhead, so a
#: difference there is candidate (a) and nothing else — though read the RESULT block
#: on how much load-dependent noise that row carries. The larger rows exist to show
#: the SAVING scaling with D, which proves the saving is not being flattened by the
#: harness, and reads out how DEEP the pole stage is: measured at 2xD to within 2ms
#: in every run (~0.399s at D=0.2, ~1.000s at D=0.5), i.e. two dependency stages,
#: which is `StatementClassification`'s own two submits and the origin of the
#: 2.8 + 3.0 = 5.8s arithmetic the tool-level saving was predicted from. That row is
#: the robust one here; the A-B overhead row is the fragile one.
DELAYS = (0.0, 0.2, 0.5)

#: Paired reps per delay. Small on purpose: the reading is a within-rep DIFFERENCE
#: (A and B run back to back against the same graph state), not a mean, so reps
#: buy noise bounds rather than precision.
REPS = 3


class _CallLog:
    """Intervals of every provider call, for a union that is not a sum.

    The quantity this probe needs is `wall - union(call intervals)`: summing call
    durations would count two concurrent poles twice and report the gathered
    condition as having NEGATIVE overhead. Same inclusion-exclusion reasoning as
    `probe_pole_overlap.py`, one level up.
    """

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.intervals: list[tuple[float, float]] = []

    async def wrap(self) -> None:
        started = time.perf_counter()
        if self.delay:
            await asyncio.sleep(self.delay)
        self.intervals.append((started, time.perf_counter()))

    @property
    def count(self) -> int:
        return len(self.intervals)

    @property
    def union(self) -> float:
        """Wall covered by at least one call. 0.0 at D=0 by construction."""
        if not self.intervals:
            return 0.0
        merged: list[list[float]] = []
        for start, end in sorted(self.intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return sum(end - start for start, end in merged)


def _install(monkeypatch, delay: float) -> _CallLog:
    """Delay every concern provider call, and record when it ran.

    `ConversationFacilitator._call_with_response_model` is the choke point every
    concern's structured call goes through under mock brain — the concerns
    themselves do not touch `use_brain` — so one wrapper here covers the whole
    tool. `install_mock_brain` (autouse) has already replaced this method, so the
    wrapper chains onto the mock rather than the real call.
    """
    from dialectical_framework.agents import conversation_facilitator as cf_mod

    log = _CallLog(delay)
    mocked = cf_mod.ConversationFacilitator._call_with_response_model

    async def timed(self, response_model):
        await log.wrap()
        return await mocked(self, response_model)

    monkeypatch.setattr(
        cf_mod.ConversationFacilitator, "_call_with_response_model", timed
    )
    return log


def _serialize_poles(monkeypatch) -> None:
    """Force `_classify_statement`'s two calls to run one after the other.

    A lock rather than an edit to the gather: the shipped `asyncio.gather` still
    runs, both coroutines are still created, and the only thing removed is the
    OVERLAP. So the difference between conditions cannot be some second effect of
    restructuring the call — it is the concurrency and nothing else. Patching the
    module's `asyncio` name instead would also serialize the classification and
    headline pair INSIDE each pole, which is a different (and deeper) change.
    """
    original = IntroducePolarity._classify_statement
    lock = asyncio.Lock()

    async def serialized(self, text: str, context: str):
        async with lock:
            return await original(self, text, context)

    monkeypatch.setattr(IntroducePolarity, "_classify_statement", serialized)


async def _run_anchor() -> None:
    case = Case()
    case.commit()
    with scope(case.sid):
        await anchor.fn(thesis=THESIS, antithesis=ANTITHESIS, context=CONTEXT)


async def _measure(monkeypatch, *, delay: float, serialized: bool) -> dict:
    with monkeypatch.context() as patch:
        log = _install(patch, delay)
        if serialized:
            _serialize_poles(patch)
        started = time.perf_counter()
        await _run_anchor()
        wall = time.perf_counter() - started
    return {
        "wall": wall,
        "calls": log.count,
        "union": log.union,
        "overhead": wall - log.union,
    }


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_whether_gathering_the_poles_costs_overhead(monkeypatch):
    # One discarded run first. Mock brain returns identical DTOs, so `commit()`
    # (an upsert) CREATES the statements on the first run of the process and
    # REUSES them afterwards — a warm-up keeps that asymmetry out of rep 1's
    # difference, where it would land entirely on whichever condition ran first.
    await _measure(monkeypatch, delay=0.0, serialized=False)

    print("\n### Does gathering the two poles add non-provider overhead?")
    print(
        "    D = injected per-provider-call delay; union = wall covered by at "
        "least one call;\n    overhead = wall - union (framework: graph writes, "
        "report merges, scheduling).\n    A = gathered (as shipped), "
        "B = pole pair serialized by a lock."
    )

    for delay in DELAYS:
        rows: list[tuple[dict, dict]] = []
        for _ in range(REPS):
            # Interleaved, A then B, so both conditions in a rep see the same
            # graph state. Comparing all A runs against all B runs afterwards
            # would let any monotone drift (a growing graph) land on B.
            gathered = await _measure(monkeypatch, delay=delay, serialized=False)
            serial = await _measure(monkeypatch, delay=delay, serialized=True)
            rows.append((gathered, serial))

        print(f"\n  D = {delay:.2f}s")
        for i, (a, b) in enumerate(rows, start=1):
            print(
                f"    rep {i}:  A wall {a['wall']:.3f}  union {a['union']:.3f}  "
                f"overhead {a['overhead']:.3f}  calls {a['calls']}"
                f"   |   B wall {b['wall']:.3f}  union {b['union']:.3f}  "
                f"overhead {b['overhead']:.3f}  calls {b['calls']}"
            )

        overhead_delta = statistics.median(
            a["overhead"] - b["overhead"] for a, b in rows
        )
        union_saving = statistics.median(b["union"] - a["union"] for a, b in rows)
        wall_saving = statistics.median(b["wall"] - a["wall"] for a, b in rows)
        print(
            f"    median: overhead A-B {overhead_delta:+.3f}s   "
            f"union saved {union_saving:+.3f}s   wall saved {wall_saving:+.3f}s"
            + (f"   (one stage = {delay:.2f}s)" if delay else "")
        )

        # The call count is the harness's own honesty check, not a result.
        counts = {r["calls"] for pair in rows for r in pair}
        print(
            f"    calls {sorted(counts)} — compare 10-13 measured on this branch "
            "by `probe_anchor_retry_cost.py`; a drift here means the mock path "
            "is no longer the path that was priced"
        )

    _report_request_construction_cost()


def _report_request_construction_cost() -> None:
    """The one python-side mechanism the rows above CANNOT see, measured directly.

    A gather saves nothing on work that is CPU-bound: two poles doing their own
    per-call request construction serialize on the GIL, so the pair would cost the
    SUM and the saving would be eaten. The rows above cannot detect that, because
    `install_mock_brain` replaces the call and takes request construction with it —
    so the mechanism has to be priced on its own.

    `CallRecord.first_token_seconds`' docstring cites `_fix_cache_breakpoints`
    "scanning a ~60k-char prompt" as part of what that interval contains, which is
    true and reads as though it were material. It is `str.find` plus two slices.
    """
    from dialectical_framework.utils.bedrock_provider import (
        CACHE_SPLIT_SENTINEL, _fix_cache_breakpoints)

    text = ("engine prose. " * 4000) + CACHE_SPLIT_SENTINEL + ("## dump line\n" * 500)
    reps = 500
    started = time.perf_counter()
    for _ in range(reps):
        _fix_cache_breakpoints({"system": [{"type": "text", "text": text}], "tools": None})
    per = (time.perf_counter() - started) / reps

    print(
        f"\n  per-call request construction (framework's own, {len(text):,}-char "
        f"prompt): _fix_cache_breakpoints {per * 1e6:.1f} us"
    )
    print(
        "    This is the GIL-contention ceiling for the framework's share of it: "
        "two poles\n    cannot overlap CPU, so at most ~2x this is unavailable to "
        "the gather. Mirascope's\n    own `encode_request` is not measured here and "
        "is the remaining unpriced piece."
    )
