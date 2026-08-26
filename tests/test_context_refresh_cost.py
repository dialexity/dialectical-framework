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

#: The reply path this cost has to be judged against. Measured, not assumed:
#: `anchor` ran 42.0s / 39.1s / 804.5s across `timing-check-building`, so 42s is
#: the median single tool round a turn already pays for.
MEDIAN_TOOL_ROUND_S = 42.0


@pytest.mark.asyncio
async def test_the_refresh_is_cheap_against_the_reply_path():
    """A budget, not a benchmark.

    The assertion is deliberately loose — this runs on developer laptops and CI
    boxes against a containerised Memgraph, so a tight bound would be a flake
    generator. What it actually guards is the ORDER OF MAGNITUDE: the refresh must
    stay a rounding error against the 42s median tool round, because a per-turn
    read that crept into seconds would have quietly traded the read-side fix for
    the latency problem this whole line of work started from.
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
