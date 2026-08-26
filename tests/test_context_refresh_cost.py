"""What the per-turn context refresh actually costs, measured on a real graph.

`Advisor._refresh_context` re-reads the whole Current Understanding dump on every
turn. That is a recurring cost the framework imposes whether the model asks for
anything or not, and this session's whole method is that such a cost gets measured
rather than asserted to be small — the last thing a comment claimed about the
reply path (`chat` "never delays the person's reply") was wrong by 387.7 seconds.

No LLM here by design: `DialecticalContext.resolve()` is repository reads plus
string assembly, so the number this prints is pure graph-read time and is
comparable across runs. The graph is built with plain `commit()` calls at a size
the archive actually produced (`claim2-weak-r7-readside` anchored 5-7 tensions per
cell; the bench cap is `advisor_max_perspectives_per_exploration = 2` per explore
call, so unexplored standalone tensions accumulate — which is the shape rendered
under "Unexplored Tensions").

    poetry run pytest tests/test_context_refresh_cost.py -s
"""

from __future__ import annotations

import time

import pytest
from test_dialectical_context import _create_perspective_with_aspects

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

#: The archive's observed per-cell anchor productivity, upper end.
TENSION_COUNT = 7

#: What one `anchor` round costs when it WORKS — the thing the refresh has to be
#: a rounding error against. Measured, not assumed, and revised twice in one day,
#: which is why the whole history is here rather than just the current number.
#:
#: 42.0s → 282.8s → 41.4s.
#:
#: The first figure was a median of three observations from one afternoon
#: (42.0 / 39.1 / 804.5s), reported to a decimal place as if it were a property
#: of the tool. r26 ran ten rounds on the same scenario and tier and found a
#: median of 282.8s (max 812.5s), so 42.0 looked low by 6.7x.
#:
#: Then `tests/e2e/probe_anchor_retry_cost.py` decomposed it with the retry
#: accountant installed and found that ALL THREE of its calls laddered: waited
#: 123.5 / 321.3 / 809.8s, of which **46.8 / 41.4 / 40.1s was work** and 70 / 270
#: / 750s was `asyncio.sleep` in the ParseError retry curve (exact ladder sums),
#: every one of them reporting `ok`. r26's 282.8s was real waiting and NOT the
#: tool's cost — the two are different quantities and the archive had no way to
#: tell them apart until the accounting landed.
#:
#: So this is the median WORKING round: 41.4s. Landing back within 0.6s of the
#: original 42.0 is a coincidence, not a vindication — that figure was right by
#: accident, off a sample of three that happened to contain two clean calls.
#:
#: Using the working figure is the conservative choice: the refresh is a LARGER
#: share of 41.4s than of 282.8s (this laptop's 0.25-0.34s median reads as
#: 0.6-0.8% against 41.4s, and 0.09-0.12% against 282.8s), and a baseline padded
#: with the framework's own sleeping would excuse any refresh cost at all. The
#: budget below is unchanged either way — it is an absolute bound on the refresh,
#: not a ratio, and the share is printed for judgement, never asserted.
MEDIAN_TOOL_ROUND_S = 41.4


@pytest.mark.asyncio
async def test_the_refresh_is_cheap_against_the_reply_path():
    """A budget, not a benchmark.

    The assertion is deliberately loose — this runs on developer laptops and CI
    boxes against a containerised Memgraph, so a tight bound would be a flake
    generator. What it actually guards is the ORDER OF MAGNITUDE: the refresh must
    stay a rounding error against a WORKING tool round (`MEDIAN_TOOL_ROUND_S`),
    because a per-turn read that crept into seconds would have quietly traded the
    read-side fix for the latency problem this whole line of work started from.
    """
    case = Case()
    case.commit()

    with scope(case.sid):
        for i in range(TENSION_COUNT):
            _create_perspective_with_aspects(
                thesis_text=f"Tension {i} thesis",
                antithesis_text=f"Tension {i} antithesis",
                thesis_meaning="test",
            )

        # Warm: the first read pays for connection setup and any lazy schema
        # work, which a per-turn refresh from turn 2 on does not.
        await DialecticalContext().resolve()

        timings: list[float] = []
        for _ in range(5):
            started = time.monotonic()
            dump = await DialecticalContext().resolve()
            timings.append(time.monotonic() - started)

    median = sorted(timings)[len(timings) // 2]
    print(f"\nPerspectives rendered: {TENSION_COUNT}")
    print(f"Dump size: {len(dump)} chars")
    print(f"Refresh seconds (5 reads): {[round(t, 4) for t in timings]}")
    print(f"Median: {median:.4f}s")
    print(f"Share of one {MEDIAN_TOOL_ROUND_S}s tool round: "
          f"{median / MEDIAN_TOOL_ROUND_S:.2%}")

    assert dump, "rendered an empty dump over a graph with 7 tensions"
    assert median < 2.0, (
        f"the per-turn context refresh takes {median:.2f}s at "
        f"{TENSION_COUNT} tensions. That is no longer a rounding error on the "
        "person's wait, and it is paid on EVERY turn — including turns that "
        "changed nothing. Either the dump grew a per-node query or the graph "
        "read needs its own budget."
    )
