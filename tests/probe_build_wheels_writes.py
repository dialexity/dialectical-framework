"""Probe: how many writes does `build_wheels` make, and how many are the SAME node?

WHY THIS EXISTS
===============
`tests/probe_build_wheels_offprovider.py` established that the read side of this path
is now roughly a quarter of what it was, and that the largest remaining call site
(`transition.py:commit`) is a WRITE path. It counts writes in aggregate — 2,144
`save_node`, 2,821 `save_relationship` — and that pair of numbers cannot answer the
only question worth asking about them: **is that 2,144 distinct nodes, or fewer nodes
written more than once?**

The distinction decides whether anything is compressible. A write per node is the
floor; a node written twice is a round-trip that a different order might not need.
And aggregate counts hide it completely, because `save_node` is BOTH the create and
the update — GQLAlchemy has no separate call for the second one.

So this attributes every write to the node OBJECT that made it and reports
writes-per-node by label. Ratio 1.0 = every node written once. Ratio 2.0 = every node
written twice, which is a whole round-trip per node available to whoever can justify
reordering the commit.

**Identity is `id()` plus a STRONG REFERENCE, and the reference is the load-bearing
half.** CPython recycles an `id()` as soon as the object is collected, and most nodes
on this path are dropped the moment they are committed — an Estimation is created,
committed and returned into a value nobody keeps. Counting by bare `id()` therefore
merges unrelated objects into one row, and it does not fail loudly: a first run of this
probe reported `CausalityProbabilityEstimation` at 5.06x with 376 writes landing on a
handful of ids, which reads exactly like a node being rewritten in a loop. It was 109
separate estimations written once each, reusing 109 addresses. `_seen` below pins every
wrapped object alive for the run so an id cannot be reused; the `commit()` path raises
`ImmutableNodeError` on a second commit, so any ratio above 1.0 that survives this is a
real repeat write by design rather than a recycled address.

Relationships get the same treatment by TYPE, plus the DB's own count of surviving
edges, because a repeated directed `connect()` does not dedup (see the "Idempotent
connect" note in CLAUDE.md) — so writes above the surviving-edge count are duplicate
edges in the graph, not just duplicate traffic.

WHAT IT DOES NOT MEASURE
========================
Seconds. `save_node` timing is in the other probe and is honest there; this one wraps
per-object bookkeeping around every write and would inflate them. Read this for
COUNTS and go there for cost.

It also cannot say a second write is unnecessary — only that it exists. Whether the
order can change is a question about crash safety (a node carrying a hash but not yet
its edges is `committed` while structurally incomplete, which is exactly what the
`saved_at`/`hash IS NULL` garbage signal exists to make impossible), and that argument
is not in a measurement.

    poetry run pytest tests/probe_build_wheels_writes.py -s
    DIALEXITY_PROBE_BW_K=4 poetry run pytest tests/probe_build_wheels_writes.py -s

RESULTS
=======
2026-09-09, k=4, after the four read levers:

    class                             writes  objects  per obj
    Transition                          1264      632    2.00x
    CausalityProbabilityEstimation       552      552    1.00x
    Wheel                                192       96    2.00x
    Rationale                            112      112    1.00x
    Cycle                                 24       24    1.00x
    TOTAL                               2144     1416    1.51x

**2,144 writes for 1,416 nodes, so 728 (34%) are a second write — and they come from
exactly two places, one of which is not a defect.**

`Wheel` must be written twice. It is an `IncrementalBuildMixin` container: `save()`,
attach members, `commit()`. Its hash is computed FROM the members, and a member cannot
attach to a node that does not exist yet, so the two writes are the lifecycle rather
than a cost. The two sites in the breakdown say so (`incremental_build_mixin.py:save`
then `incremental_build_mixin.py:commit`).

`Transition`'s 632 are structurally avoidable and were NOT removed. `commit()` saves to
get an `_id`, connects both endpoints, then saves again carrying the hash — but the hash
does not need the endpoints to exist: `_collect_structure_hash_parts` prefers the
`_source_hash`/`_target_hash` that `set_source`/`set_target` already stored. So the
order could be compute-hash, save once, then connect. What that trades away is the
garbage signal: a crash between the two writes currently leaves `hash IS NULL`, which
`saved_at` accounting treats as abandoned and `scripts/cleanup_stale_nodes.py` reaps,
whereas saving the hash first leaves a COMMITTED Transition with no endpoints — which
nothing reaps and which `order_transitions` would later walk into. It is one write per
transition against a permanent structural hole after a crash. Worth ~0.9-1.5s at k=4.
(The fallback in `_collect_structure_hash_parts` also means the no-read property is not
guaranteed by construction, only by how every current caller happens to build them.)

**No duplicate edges.** Every relationship write count is at or below the surviving
edge count, so nothing on this path connects the same pair twice. The gaps the other
way (`ESTIMATES` 552 written / 560 in db) are edges written during `_perspectives`
setup, before the wrappers install.

**632 transitions for 96 wheels is the design, not waste.** `Transition.nonce` exists
to make identical `T1- -> A2+` pairs in different containers different nodes, because a
Transition is independently assessable and belongs to exactly one container. So write
volume tracks wheel count by construction; sharing them is a reasoning change.

**The compressible thing this probe found is a READ, and it is free.** `BaseNode.commit()`
computes the hash, calls `find_by_hash` to dedup, and on a miss calls `self.save()` —
which immediately asks `find_by_hash` for the SAME hash again, because its own guard is
`self.hash and self._id is None` and both still hold. Nothing between the two can change
the answer. Confirmed by arithmetic that closes: the off-provider probe attributes 1,376
charges to `find_by_hash < base_node.py:save < base_node.py:commit`, and a miss is 2
charges (open + StopIteration), so 688 calls — exactly the 552 + 112 + 24 nodes committed
through this path. 688 of the run's 4,099 hash lookups (17%) are asked twice.

**Fixed, and the prediction held to the unit.** `BaseNode.commit()` now delegates to
`save()` when `_id is None` instead of asking first; removing 688 double misses had to
remove exactly 1,376 charges, and the shape went 4,099 -> 2,723. Writing the number down
before the change is what made it evidence rather than a fitted result. (The `_id is not
None` branch keeps its own lookup — `save()`'s guard requires `_id is None` and would
skip dedup entirely there. Pinned in `tests/test_commit_asks_dedup_once.py`.)

One thing that surfaced while pinning it, and was NOT changed: **committing a duplicate
Estimation directly raises** `ValueError: maximum cardinality 1 already reached`, because
`Estimation.commit()` re-connects the target after delegating up and on a dedup hit
`self._id` is the EXISTING node, which already holds that edge. It raises identically
without the change above, so it is pre-existing rather than introduced, and production
never reaches it: `EstimationManager._get_or_create_estimation` looks for an
`(e {value})-[:ESTIMATES]->(target)` match before constructing one. So Estimation's dedup
HIT path is effectively dead code guarded by the manager. Recorded, not fixed — making it
work is a reasoning-layer decision about what a duplicate estimation means.

**Run it by path — it is NOT part of the default suite.** Nothing named `probe_*.py`
is: pytest's default `python_files` is `test_*.py`/`*_test.py` and this repo does not
override it, so every probe here is opt-in and none of them guards a regression.

It shares `DIALEXITY_PROBE_BW_K` and the tension fixtures with the off-provider probe
by importing them, so the two describe the SAME run at the same k.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import defaultdict

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.agents.explorer.skills.build_wheels import BuildWheels
from dialectical_framework.concerns.create_nexus import CreateNexus

from probe_build_wheels_offprovider import INTENT, K, _perspectives


def _label_of(node) -> str:
    """The node's CLASS name, not its graph label.

    Deliberately not `_labels`: every node here carries the shared `Node` label
    alongside its own, so any set-based pick collapses distinct types into one row —
    which is how a first run of this probe reported "Node 4.33x" for what turned out
    to be three different classes with three different write patterns.
    """
    return type(node).__name__


#: Layers that only pass a write through; the interesting frame is above them.
_PLUMBING = ("relationship_manager.py", "database_client.py", "memgraph.py")


def _site() -> str:
    """The nearest framework frames above the client, innermost first."""
    frames: list[str] = []
    frame = sys._getframe(1)
    walked = 0
    while frame is not None and walked < 30 and len(frames) < 3:
        walked += 1
        name = frame.f_code.co_filename
        if "dialectical_framework" in name:
            base = name.rsplit("/", 1)[-1]
            if base not in _PLUMBING:
                frames.append(f"{base}:{frame.f_code.co_name}")
        frame = frame.f_back
    return " < ".join(frames) or "?"


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_how_many_writes_are_the_same_node(di_container, monkeypatch):
    print(f"\n### Writes during build_wheels at k = {K} perspectives, LLM mocked")

    db = di_container.graph_db()

    #: label -> {id(obj): write count}
    node_writes: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    #: label -> writes that already carried a hash (i.e. updates of a committed node)
    with_hash: dict[str, int] = defaultdict(int)
    rel_writes: dict[str, int] = defaultdict(int)
    #: "<label> write #N" -> {call site: count}
    repeat_sites: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    #: Strong refs. Without these CPython reuses addresses and the ratios are fiction
    #: — see the identity note in the module docstring.
    seen: list = []

    case = Case()
    case.commit()
    with scope(case.sid):
        hashes = await _perspectives(K)
        created = await CreateNexus().resolve(
            intent=INTENT, perspective_hashes=hashes
        )

        save_node = db.save_node
        save_relationship = db.save_relationship

        def node_wrapper(node, *args, **kwargs):
            label = _label_of(node)
            seen.append(node)
            node_writes[label][id(node)] += 1
            nth = node_writes[label][id(node)]
            if getattr(node, "hash", None):
                with_hash[label] += 1
            # Attribute by WHICH write this is for the object. The first write is the
            # floor and uninteresting; it is the 2nd and beyond that are the question,
            # and they are only answerable at the call site — the aggregate count
            # cannot distinguish "many nodes" from "one node, many times".
            repeat_sites[f"{label} write #{min(nth, 5)}"][_site()] += 1
            return save_node(node, *args, **kwargs)

        def rel_wrapper(rel, *args, **kwargs):
            seen.append(rel)
            rel_writes[getattr(rel, "_type", type(rel).__name__)] += 1
            return save_relationship(rel, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(db, "save_node", node_wrapper)
            patch.setattr(db, "save_relationship", rel_wrapper)

            started = time.monotonic()
            result = await BuildWheels(
                nexus_hash=created.nexus.short_hash
            ).resolve()
            wall = time.monotonic() - started

        await asyncio.sleep(0.2)

        # The DB's own view, for the relationship comparison below. Read AFTER the
        # measured window so these queries are not counted as part of the run.
        surviving_rels: dict[str, int] = {}
        for row in db.execute_and_fetch(
            "MATCH (a {sid: $sid})-[r]->(b {sid: $sid})"
            " RETURN type(r) AS t, count(r) AS n",
            {"sid": case.sid},
        ):
            surviving_rels[row["t"]] = row["n"]

        surviving_nodes: dict[str, int] = {}
        for row in db.execute_and_fetch(
            "MATCH (n {sid: $sid}) RETURN labels(n) AS l, count(n) AS n",
            {"sid": case.sid},
        ):
            for label in row["l"]:
                if label.startswith("___"):
                    continue
                surviving_nodes[label] = surviving_nodes.get(label, 0) + row["n"]

    print(f"  built {len(result.new_cycles)} cycle(s),"
          f" {len(result.new_wheels)} wheel(s) in {wall:.2f}s")

    total_writes = sum(sum(d.values()) for d in node_writes.values())
    total_objects = sum(len(d) for d in node_writes.values())

    print("\n  NODE WRITES — is a node written once, or more than once?")
    print(f"    {'label':<16} {'writes':>7} {'objects':>8} {'per obj':>8}"
          f" {'w/ hash':>8} {'in db':>7}")
    for label in sorted(node_writes, key=lambda k: -sum(node_writes[k].values())):
        per_object = node_writes[label]
        writes = sum(per_object.values())
        # `in db` is keyed by graph LABEL while the rows are keyed by CLASS, so a
        # class whose label differs prints `-` rather than a misleading 0.
        in_db = surviving_nodes.get(label)
        print(f"    {label:<16} {writes:>7} {len(per_object):>8}"
              f" {writes / len(per_object):>7.2f}x {with_hash[label]:>8}"
              f" {'-' if in_db is None else in_db:>7}")
    print(f"    {'TOTAL':<16} {total_writes:>7} {total_objects:>8}"
          f" {total_writes / total_objects:>7.2f}x")

    print("\n  RELATIONSHIP WRITES — writes above `in db` are DUPLICATE edges")
    print(f"    {'type':<24} {'writes':>7} {'in db':>7}")
    for rel_type in sorted(rel_writes, key=lambda k: -rel_writes[k]):
        print(f"    {rel_type:<24} {rel_writes[rel_type]:>7}"
              f" {surviving_rels.get(rel_type, 0):>7}")
    print(f"    {'TOTAL':<24} {sum(rel_writes.values()):>7}"
          f" {sum(surviving_rels.values()):>7}")

    print("\n  WHERE THE REPEAT WRITES COME FROM (#1 is the floor; #2+ is the question)")
    for bucket in sorted(repeat_sites):
        rows = sorted(repeat_sites[bucket].items(), key=lambda kv: -kv[1])
        print(f"    {bucket}")
        for site, count in rows[:3]:
            print(f"      {count:>6}x  {site}")

    # The floor is one write per object. Anything at 1.00x is already minimal and
    # nothing but writing fewer NODES would help it; anything at 2.00x is paying a
    # whole extra round-trip per node, which is what makes it worth naming here.
    assert total_writes >= total_objects, "fewer writes than objects is impossible"
    assert node_writes, "no writes recorded — the wrapper did not install"
