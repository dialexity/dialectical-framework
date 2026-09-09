"""Why a full-length hash is matched with `=` and a short one with `STARTS WITH`.

Prefix lookup is a deliberate contract: the framework renders `short_hash` into
prompts to save tokens, so a hash it hands out must be usable to look the node back
up. `find_by_hashes` once matched on equality only, and that broke `ingest` silently
— it reported a 7-char hash, passed the same string back, matched nothing, and then
reported "No tensions extracted" as success.

So the contract stays. What changed is only the PREDICATE used when the needle is
already full length, where prefix and equality are provably the same question: every
hash here is a sha256 hexdigest, hence all the same length, and no string is a strict
prefix of another of equal length.

The reason to care is the index. `STARTS WITH` against a parameter is not a point
lookup, so Memgraph either scans every node in the case or scans the whole hash
index; `=` is a point lookup. `find_by_hash` is the framework's most-used read and
nearly all of its callers pass a node's OWN full hash to dedup it on commit, so the
hot path was paying a full-case scan — a cost that grows with the case — for a
question the index answers directly.

Both halves are pinned here: the behaviour (which must NOT change) and the predicate
(which is the whole point, and is invisible in results, so it is asserted on the
query text).
"""

from __future__ import annotations

import random

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.node_repository import (
    FULL_HASH_LENGTH,
    NodeRepository,
    hash_match,
)
from dialectical_framework.graph.scope_context import scope


def _capture_queries(db, monkeypatch) -> list[str]:
    """Record the text of every query the client sends."""
    seen: list[str] = []
    fetch = db.execute_and_fetch

    def wrapper(*args, **kwargs):
        seen.append(str(args[0] if args else kwargs.get("query", "")))
        return fetch(*args, **kwargs)

    monkeypatch.setattr(db, "execute_and_fetch", wrapper)
    return seen


@pytest.fixture
def statements(di_container):
    """Three committed Statements in their own scope."""
    case = Case()
    case.commit()
    with scope(case.sid):
        made = []
        for i in range(3):
            statement = Statement(
                text=f"Component {i} {random.random()}", meaning="test"
            )
            statement.commit()
            made.append(statement)
        yield made, case.sid


class TestTheLengthIsWhatPicksThePredicate:
    def test_a_sha256_digest_is_what_full_length_means(self):
        """The constant is derived, not written down, so it cannot drift.

        If `BaseNode.compute_hash` ever stopped being a sha256 hexdigest, the
        equality shortcut would no longer be sound — every hash being the SAME
        length is the entire argument. Pinning the number here would hide that;
        pinning the derivation surfaces it.
        """
        assert FULL_HASH_LENGTH == 64

    def test_a_full_needle_gets_equality(self):
        assert hash_match("a" * FULL_HASH_LENGTH) == "n.hash = $hash"

    def test_a_short_needle_keeps_prefix_matching(self):
        assert hash_match("abc1234") == "n.hash STARTS WITH $hash"

    def test_an_overlong_needle_is_not_treated_as_full(self):
        """Anything not exactly full length falls back to the safe predicate.

        A longer-than-full string cannot be a valid hash at all, so it must match
        nothing — and `STARTS WITH` gives that, while `=` would too. The point is
        that the branch is on EQUALITY of length, not `>=`, so no oversized input
        can smuggle itself onto the indexed path.
        """
        assert hash_match("a" * (FULL_HASH_LENGTH + 1)) == "n.hash STARTS WITH $hash"


class TestTheIndexedPredicateReachesTheDatabase:
    """The saving is invisible in results, so assert on what was sent."""

    def test_a_full_hash_lookup_sends_an_equality_query(
        self, di_container, statements, monkeypatch
    ):
        made, sid = statements
        db = di_container.graph_db()

        with scope(sid):
            seen = _capture_queries(db, monkeypatch)
            found = NodeRepository().find_by_hash(made[0].hash)

        assert found is not None and found.hash == made[0].hash
        lookups = [q for q in seen if "n.hash" in q]
        assert lookups, "no hash lookup was issued"
        assert all("n.hash = $hash" in q for q in lookups), (
            f"a full hash still went out as a prefix scan: {lookups}"
        )

    def test_a_short_hash_lookup_still_sends_a_prefix_query(
        self, di_container, statements, monkeypatch
    ):
        made, sid = statements
        db = di_container.graph_db()

        with scope(sid):
            seen = _capture_queries(db, monkeypatch)
            found = NodeRepository().find_by_hash(made[0].short_hash)

        assert found is not None and found.hash == made[0].hash, (
            "the short form must keep working — this is the `ingest` bug"
        )
        lookups = [q for q in seen if "n.hash" in q]
        assert all("STARTS WITH" in q for q in lookups), (
            f"a short hash was matched by equality, which matches nothing: {lookups}"
        )


class TestTheAnswersAreUnchanged:
    def test_both_forms_find_the_same_node(self, di_container, statements):
        made, sid = statements
        repo = NodeRepository()

        with scope(sid):
            for statement in made:
                by_full = repo.find_by_hash(statement.hash)
                by_short = repo.find_by_hash(statement.short_hash)

                assert by_full is not None, "full hash found nothing"
                assert by_short is not None, "short hash found nothing"
                assert by_full.hash == by_short.hash == statement.hash

    def test_a_hash_that_matches_nothing_returns_none(self, di_container, statements):
        _, sid = statements
        with scope(sid):
            assert NodeRepository().find_by_hash("f" * FULL_HASH_LENGTH) is None

    def test_a_batch_of_mixed_lengths_returns_everything_in_order(
        self, di_container, statements
    ):
        """The split into two queries must be invisible.

        This is the part of the change that could actually lose data: needles are
        partitioned by length, run separately, and merged. So ask with the forms
        INTERLEAVED and require the requested order back — not the order either
        query happened to return.
        """
        made, sid = statements
        asked = [made[0].hash, made[1].short_hash, made[2].hash]

        with scope(sid):
            found = NodeRepository().find_by_hashes(asked)

        assert [n.hash for n in found] == [s.hash for s in made], (
            "mixed-length batch lost a node or reordered the results"
        )

    def test_a_batch_of_only_full_hashes_is_one_query(
        self, di_container, statements, monkeypatch
    ):
        """No empty second query when a batch is homogeneous — the common case."""
        made, sid = statements
        db = di_container.graph_db()

        with scope(sid):
            seen = _capture_queries(db, monkeypatch)
            found = NodeRepository().find_by_hashes([s.hash for s in made])

        assert len(found) == 3
        unwinds = [q for q in seen if "UNWIND" in q]
        assert len(unwinds) == 1, f"expected a single batched query, got {unwinds}"
        assert "n.hash = prefix" in unwinds[0]

    def test_an_ambiguous_prefix_still_raises(self, di_container):
        """Refusing to guess is the behaviour, and it lives on the prefix path.

        Forced rather than hoped for: a hash starts with one of 16 hex digits, so
        17 nodes GUARANTEE a collision by pigeonhole. An earlier version of this
        test used three fixtures and skipped when they happened not to collide,
        which meant it asserted nothing on most runs.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            firsts: dict[str, int] = {}
            for i in range(17):
                statement = Statement(
                    text=f"Ambiguity {i} {random.random()}", meaning="test"
                )
                statement.commit()
                firsts[statement.hash[0]] = firsts.get(statement.hash[0], 0) + 1

            collision = next(c for c, n in firsts.items() if n > 1)
            with pytest.raises(ValueError, match="Ambiguous"):
                NodeRepository().find_by_hash(collision)
