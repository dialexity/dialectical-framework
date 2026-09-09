"""Probe: does a hash lookup cost the same whatever the case holds?

WHY THIS EXISTS
===============
`find_by_hash` is the framework's most-used read. In one k=4 `build_wheels` it ran
4,099 times and was the second most expensive query shape in the run, and almost
every one of those calls comes from `BaseNode.commit` handing over a node's OWN full
hash to dedup it.

It used to ask `n.hash STARTS WITH $hash`. Memgraph cannot make a point lookup out of
`STARTS WITH` against a parameter, so the planner fell back to
`ScanAllByLabelProperties (n :Node {sid})` — every node in the case, then filtered.
That is O(case size) per lookup, and a case only grows.

Switching to `n.hash = $hash` when the needle is already 64 characters is not a
behaviour change (all hashes are sha256 hexdigests, so equal length, so no string is
a strict prefix of another) but it IS an index change: equality is a point lookup.

The k=4 probe showed the per-query cost fall 0.617ms -> 0.374ms and the shape's total
1.0s lower, on a database holding roughly 2,100 nodes. That is a real saving but a
small one, and quoting it alone would UNDERSELL the fix while sounding like the whole
story. The claim worth pinning is the SHAPE of the curve: one predicate degrades with
the case and the other does not. That cannot be read off a single small run, so this
measures both at several sizes.

WHAT IT MEASURES
================
Builds one case, then at each checkpoint times the same batch of lookups twice —
once with each predicate, against the identical data — and reports microseconds per
lookup. Interleaved on purpose: a run-to-run comparison on this box swings enough to
swallow the effect.

    poetry run pytest tests/probe_hash_lookup_scaling.py -s
    DIALEXITY_PROBE_HASH_SIZES=500,2000,8000 poetry run pytest tests/probe_hash_lookup_scaling.py -s

**Run it by path — it is NOT part of the default suite.** Nothing named `probe_*.py`
is: pytest's default `python_files` is `test_*.py`/`*_test.py` and this repo does not
override it, so every probe here is opt-in and none of them guards a regression. The
assertions below exist so that a run which no longer shows the effect FAILS loudly
instead of printing a flat table nobody reads, not because CI will catch it.

The default sizes are small so a by-hand run stays under a minute. Raise them to see
the curve open up.

RESULTS
=======
2026-09-09, Memgraph in docker on the same box, sizes 200,1000,4000, 60 lookups each:

    nodes in case      STARTS WITH        equality       ratio
              200          904 us          823 us         1.1x
             1000         1408 us          875 us         1.6x
             4000         2997 us          805 us         3.7x

**Equality is flat and the prefix scan is not.** 823 -> 875 -> 805 us against
904 -> 1408 -> 2997 us: 20x the nodes cost equality nothing and cost the prefix form
3.3x.

Read the ratio column with care, because the raw times are dominated by something
neither predicate controls. Roughly 810 us of every figure here is fixed per-lookup
overhead — round-trip, parse, plan, and this probe's own `list()` — which is why even
the losing side is only 1.1x at 200 nodes, and why the same query measured inside
`build_wheels` costs 374 us rather than 800. Subtract that floor and the scan
component alone is 81 -> 533 -> 2192 us, i.e. 0.40 -> 0.53 -> 0.55 us per node in the
case: linear, as the plan says it must be.

Extrapolating that measured slope (~0.55 us per node, and only the slope —
per-round-trip cost is a constant added to both), a case holding 50,000 nodes would
pay ~27 ms of scanning per lookup, so the 4,099 lookups in one k=4 `build_wheels`
would be ~110 s of index scanning by themselves. That is an extrapolation, not a
measurement, and it assumes lookups stay as frequent as they are today.

So the honest summary of this fix is NOT "1 second faster", which is all the k=4
probe could see. It is that the framework's most frequent read stopped being
O(case size). One second is what that was worth on a 2,100-node case; it grows with
every node a case accumulates, and nothing else in the current profile has that
property.
"""

from __future__ import annotations

import os
import random
import time

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

#: Node counts to sample the curve at. Small by default so a by-hand run stays quick;
#: the shape is already visible at these sizes and the assertions already bite.
SIZES = [
    int(s) for s in os.getenv("DIALEXITY_PROBE_HASH_SIZES", "200,1000,4000").split(",")
]

#: Lookups per timing. Enough to average out per-query jitter, small enough that the
#: slowest configuration here stays well under a second.
LOOKUPS = int(os.getenv("DIALEXITY_PROBE_HASH_LOOKUPS", "60"))

_PREFIX_QUERY = """
    MATCH (n:Node)
    WHERE n.hash STARTS WITH $hash AND n.sid = $sid
    RETURN n
"""

_EQUALITY_QUERY = """
    MATCH (n:Node)
    WHERE n.hash = $hash AND n.sid = $sid
    RETURN n
"""


def _time_lookups(db, query: str, hashes: list[str], sid: str) -> float:
    """Microseconds per lookup, consuming each result the way a caller would."""
    started = time.monotonic()
    for hash_value in hashes:
        rows = list(db.execute_and_fetch(query, {"hash": hash_value, "sid": sid}))
        assert len(rows) == 1, f"expected exactly one node, got {len(rows)}"
    return (time.monotonic() - started) / len(hashes) * 1_000_000


@pytest.mark.llm
def test_probe_hash_lookup_cost_against_case_size(di_container):
    db = di_container.graph_db()
    case = Case()
    case.commit()

    print(f"\n### Cost of one hash lookup as the case grows"
          f" ({LOOKUPS} lookups per timing)")
    print(f"    {'nodes in case':>14}  {'STARTS WITH':>14}  {'equality':>14}"
          f"  {'ratio':>8}")

    measured: list[tuple[int, float, float]] = []
    with scope(case.sid):
        created: list[str] = []
        for target in SIZES:
            while len(created) < target:
                statement = Statement(
                    text=f"Filler {len(created)} {random.random()}", meaning="probe"
                )
                statement.commit()
                created.append(statement.hash)

            # Same needles for both predicates, spread through the case rather than
            # clustered at one end, so neither form gets a lucky scan order.
            step = max(1, len(created) // LOOKUPS)
            needles = created[::step][:LOOKUPS]

            prefix_us = _time_lookups(db, _PREFIX_QUERY, needles, case.sid)
            equality_us = _time_lookups(db, _EQUALITY_QUERY, needles, case.sid)
            measured.append((len(created), prefix_us, equality_us))
            print(f"    {len(created):>14}  {prefix_us:>11.0f} us"
                  f"  {equality_us:>11.0f} us  {prefix_us / equality_us:>7.1f}x")

    smallest, largest = measured[0], measured[-1]

    print("\n    Equality is a point lookup on the `Node(hash)` index, so its cost"
          " does not\n    depend on how much the case holds. `STARTS WITH` against a"
          " parameter is not,\n    so the planner scans — and that is the cost that"
          " grows.")

    # The property is that one curve is flat and the other is not. Asserted with
    # loose bounds because this runs on a developer box and in CI: the direction and
    # order of magnitude are the claim, never the microseconds.
    growth_equality = largest[2] / smallest[2]
    growth_prefix = largest[1] / smallest[1]
    assert growth_equality < 2.0, (
        f"equality lookups got {growth_equality:.1f}x slower as the case grew from"
        f" {smallest[0]} to {largest[0]} nodes — it should be flat, so either the"
        f" `Node(hash)` index is missing or the planner stopped using it"
    )
    assert growth_prefix > growth_equality * 2, (
        f"the prefix scan grew {growth_prefix:.1f}x and equality {growth_equality:.1f}x"
        f" — too close to demonstrate anything. If both are flat, this database is too"
        f" small to show the effect: raise DIALEXITY_PROBE_HASH_SIZES."
    )
    assert largest[1] > largest[2], (
        f"at {largest[0]} nodes the prefix scan was not slower than the point lookup,"
        f" which contradicts the plans both queries produce under PROFILE"
    )
