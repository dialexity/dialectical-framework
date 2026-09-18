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
from dialectical_framework.graph.nodes.nexus import Nexus
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

#: How many QUERIES the advisory-mode refresh may run per unattached tension.
#:
#: A count and not a second seconds-budget, and the reason is measured rather than
#: stylistic. Seconds cannot carry this claim at the size people actually hit: the
#: absolute bound above is a laptop figure a loaded box blows straight through for
#: reasons no code here controls (0.29s alone against 3.21s inside one full suite
#: run at a 15-minute load average of 18.6 — an 11x swing on a path that had not
#: changed), and a same-run RATIO, which does survive that contention, turned out
#: to be blind to the very thing worth catching: adding a relationship read PER
#: PERSPECTIVE moved it from 0.62x to 0.81x, nowhere near any bound that would not
#: also fire on noise. Seven extra round-trips are simply not visible in wall time
#: at seven tensions — they are visible at fifty, which is a graph nobody has yet.
#: The sharpest form of that: with the per-node read mutation in place, the counsel
#: refresh measured FASTER than without it (0.5665s against 0.5769s) in the same run
#: that counted its extra queries exactly. Wall time here is noise wearing a number.
#:
#: `execute_and_fetch` calls are exact, deterministic, and identical whatever else
#: the box is doing, and they are the quantity the claim at the widening site is
#: actually about: "one `find_all` plus one relationship read per nexus, per turn".
#: Per NEXUS is the contract; per PERSPECTIVE is the regression.
#:
#: But the assertion cannot be on the LEVEL, and that dead end is worth recording
#: because it looks like it works: counsel runs 193 queries against the unscoped
#: dump's 259 (it renders one exploration, not all of them), so the comparison
#: passes with 66 round-trips of headroom — and the per-perspective mutation only
#: needs 7 of them. A level test over a set the two paths render DIFFERENTLY has
#: slack in it by construction, whatever instrument measures the level.
#:
#: So the assertion is on the SLOPE: how many queries each path adds per additional
#: unattached tension. Rendering a tension legitimately costs reads — that is what
#: the widening bought — and both paths render it with the SAME renderer over the
#: same set, so their slopes must match. A read added per node on the pinned path
#: only shows up as a steeper counsel slope regardless of either level. Slack of
#: 0.5 a tension: the slopes are equal in the mechanism, and half a query per node
#: is below anything a real per-node read can cost.
#:
#: Measured, and it is an exact equality rather than an approximate one — 37.00 per
#: tension on both paths (259 -> 481 unscoped, 193 -> 415 counsel), which is the
#: widening-site comment's claim demonstrated to the query. The per-node mutation
#: reads 38.00 against 37.00 and fails.
COUNSEL_SLOPE_SLACK = 0.5

#: Unattached tensions at the two measured sizes. The step is what the slope is
#: divided by, so it wants to be large enough that one query per node is not a
#: rounding artifact and small enough to keep the fixture cheap.
UNATTACHED_SIZES = (2, 8)


async def _median_refresh(make_concern, reps: int = 5) -> tuple[float, str]:
    """Median seconds of `reps` reads, plus the last dump.

    The FIRST read is discarded rather than counted: it pays for connection setup
    and any lazy schema work, which a per-turn refresh from turn 2 on does not.
    """
    dump = await make_concern().resolve()
    timings: list[float] = []
    for _ in range(reps):
        started = time.monotonic()
        dump = await make_concern().resolve()
        timings.append(time.monotonic() - started)
    return sorted(timings)[len(timings) // 2], dump


async def _count_queries(db, monkeypatch, make_concern) -> tuple[int, str]:
    """Graph round-trips one refresh runs, plus the dump it produced.

    `execute_and_fetch` hands back the connection's own generator, so the query has
    not necessarily run when it returns — but it has certainly been ASKED, and asked
    is what this counts. Wrapping the singleton the DI container hands out is the
    same instrument `probe_build_wheels_offprovider.py` uses.
    """
    calls = 0
    fetch = db.execute_and_fetch

    def counting_fetch(*args, **kwargs):
        nonlocal calls
        calls += 1
        return fetch(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(db, "execute_and_fetch", counting_fetch)
        dump = await make_concern().resolve()
    return calls, dump


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


@pytest.mark.asyncio
async def test_the_counsel_refresh_costs_what_the_unscoped_one_costs(
    di_container, monkeypatch
):
    """The advisory-mode refresh, which the test above does not measure at all.

    This is the path the Advisor actually runs on in advisory mode, and it is the
    one the scope fence widened on 2026-09-15: `_resolve_scoped` now reads every
    nexus's members to tell an UNATTACHED tension (renderable — it is likely this
    head's own anchor) from one belonging to another exploration (fenced to a
    count). The comment at that site claims the cost is what the unscoped dump has
    always paid to compute the same set. This measures the claim.

    The assertion is on graph ROUND-TRIPS per added tension, not on seconds and not
    on a total; see `COUNSEL_SLOPE_SLACK` for both dead ends and why the slope is
    what survives them. Seconds are still measured and printed, because the absolute
    figure is worth watching even where it cannot carry an assertion.

    Bounded on purpose: this fixture has perspectives, two explorations and
    unattached tensions, but NO cycles or wheels. Advisory mode renders wheels
    without the unscoped dump's `advisor_wheel_quality_top_plausible` cap, so a
    developed graph is a different and larger question than the read set this pins.
    """
    case = Case()
    case.commit()
    small, large = UNATTACHED_SIZES

    with scope(case.sid):
        # The shape advisory mode is pinned into: the exploration under discussion,
        # a second one whose tensions must stay fenced, and unattached tensions —
        # the anchors this head planted and has not woven in yet.
        pinned = Nexus(intent="the exploration under discussion")
        pinned.save()
        pinned.commit()
        other = Nexus(intent="another exploration of the same case")
        other.save()
        other.commit()
        for i in range(3):
            _create_perspective_with_aspects(
                thesis_text=f"Pinned {i} thesis",
                antithesis_text=f"Pinned {i} antithesis",
                thesis_meaning="test",
            ).nexus.connect(pinned)
        for i in range(2):
            _create_perspective_with_aspects(
                thesis_text=f"Elsewhere {i} thesis",
                antithesis_text=f"Elsewhere {i} antithesis",
                thesis_meaning="test",
            ).nexus.connect(other)

        def seed_unattached(start: int, stop: int) -> None:
            for i in range(start, stop):
                _create_perspective_with_aspects(
                    thesis_text=f"Unattached {i} thesis",
                    antithesis_text=f"Unattached {i} antithesis",
                    thesis_meaning="test",
                )

        make_counsel = lambda: DialecticalContext(nexus_hash=pinned.short_hash)
        db = di_container.graph_db()

        seed_unattached(0, small)
        unscoped_small, _ = await _count_queries(db, monkeypatch, DialecticalContext)
        counsel_small, counsel_dump = await _count_queries(
            db, monkeypatch, make_counsel
        )

        seed_unattached(small, large)
        unscoped_large, _ = await _count_queries(db, monkeypatch, DialecticalContext)
        counsel_large, _ = await _count_queries(db, monkeypatch, make_counsel)

        unscoped_median, unscoped_dump = await _median_refresh(DialecticalContext)
        counsel_median, _ = await _median_refresh(make_counsel)

    step = large - small
    unscoped_slope = (unscoped_large - unscoped_small) / step
    counsel_slope = (counsel_large - counsel_small) / step

    print(f"\nUnattached tensions: {small} -> {large} (3 pinned, 2 elsewhere)")
    print(f"Unscoped queries: {unscoped_small} -> {unscoped_large} "
          f"({unscoped_slope:.2f} per tension), median {unscoped_median:.4f}s "
          f"({len(unscoped_dump)} chars)")
    print(f"Counsel queries:  {counsel_small} -> {counsel_large} "
          f"({counsel_slope:.2f} per tension), median {counsel_median:.4f}s")
    print(f"Share of one {MEDIAN_TOOL_ROUND_S}s tool round: "
          f"{counsel_median / MEDIAN_TOOL_ROUND_S:.2%}")

    assert counsel_dump, "rendered an empty advisory dump over a pinned exploration"
    # Non-vacuity: if the fixture stopped exercising the widened branch, the slope
    # would be measuring nothing. The unattached tensions must actually render.
    assert "# Unexplored Tensions" in counsel_dump, (
        "fixture is inert: no unattached tension reached the dump, so the reads "
        "this test is supposed to bound were never made"
    )
    assert counsel_slope > 0, (
        "fixture is inert: adding unattached tensions changed the counsel refresh's "
        "query count by nothing, so there is no slope here to bound"
    )
    assert counsel_slope <= unscoped_slope + COUNSEL_SLOPE_SLACK, (
        f"the advisory-mode refresh adds {counsel_slope:.2f} graph queries per "
        f"unattached tension against the unscoped dump's {unscoped_slope:.2f}. "
        "Both render that set with the same renderer, so the slopes must match — "
        "this says the pinned path is now asking a question per node."
    )
