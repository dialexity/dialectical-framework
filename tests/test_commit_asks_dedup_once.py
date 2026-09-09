"""Committing a node asks the dedup question once, not twice.

`BaseNode.commit()` and `BaseNode.save()` both dedup by hash, and `commit()` calls
`save()`. So every commit through this path used to issue two IDENTICAL `find_by_hash`
lookups: `commit()` computes the hash and asks, misses, calls `save()`, whose own guard
(`self.hash and self._id is None`) is still true, so it asks the same question again.
Nothing between them can change the answer — autocommit, and GQLAlchemy is not
concurrency-safe, so there is no other writer. It was 688 of the 4,099 hash lookups in
one k=4 `build_wheels`, 17% of the framework's most frequent read.

`commit()` now delegates to `save()` when `_id is None` instead of asking first. That is
only worth doing if DEDUP ITSELF still works, which is the whole reason the lookup is
there — a Rationale or Estimation with the same content must resolve onto the existing
node rather than create a second one. So both halves are pinned here: the count (the
saving, invisible in results) and the behaviour (which must not change).

The `_id is not None` branch keeps its own lookup and is pinned too, because `save()`
would skip dedup entirely there — its guard requires `_id is None`.

WHY THE BEHAVIOUR HALF USES `Statement` AND THE COUNT HALF USES `Estimation`
===========================================================================
Estimation is where the duplicated lookups actually were (552 of the 688), so the count
is pinned there. But an Estimation cannot demonstrate a dedup HIT: `Estimation.commit()`
re-connects `_target_ref` after delegating up, and on a hit `self._id` is now the
EXISTING node, which already holds that edge — so it raises `ValueError: maximum
cardinality 1 already reached`. That is pre-existing (it raises identically without this
change) and unreached in practice, because `EstimationManager._get_or_create_estimation`
looks for an `(e {value})-[:ESTIMATES]->(target)` match before it ever constructs one.
Statement is the reachable content-addressable case: same text and meaning give the same
hash, and its `commit()` adds nothing after `super().commit()`.
"""

from __future__ import annotations

import random

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.estimation import \
    CausalityProbabilityEstimation
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.scope_context import scope


def _count_lookups(monkeypatch) -> list[str]:
    """Record the hash handed to every `find_by_hash` call."""
    asked: list[str] = []
    original = NodeRepository.find_by_hash

    def wrapper(self, hash_value, *args, **kwargs):
        asked.append(hash_value)
        return original(self, hash_value, *args, **kwargs)

    monkeypatch.setattr(NodeRepository, "find_by_hash", wrapper)
    return asked


def _count_writes(db, monkeypatch) -> list[object]:
    """Record every node written."""
    written: list[object] = []
    save_node = db.save_node

    def wrapper(node, *args, **kwargs):
        written.append(node)
        return save_node(node, *args, **kwargs)

    monkeypatch.setattr(db, "save_node", wrapper)
    return written


@pytest.fixture
def target(di_container):
    """A committed Statement to hang estimations on, in its own scope."""
    case = Case()
    case.commit()
    with scope(case.sid):
        statement = Statement(
            text=f"Dedup target {random.random()}", meaning="test"
        )
        statement.commit()
        yield statement, case.sid


def _estimation(target_statement, value: float) -> CausalityProbabilityEstimation:
    estimation = CausalityProbabilityEstimation(value=value)
    estimation.set_target(target_statement)
    return estimation


class TestTheQuestionIsAskedOnce:
    def test_a_fresh_commit_issues_exactly_one_hash_lookup(
        self, target, monkeypatch
    ):
        """The miss path — where all 688 duplicated lookups were.

        Asserted as exactly one rather than "fewer than before" so that
        re-introducing a second dedup check anywhere on this path fails here.
        """
        statement, sid = target
        with scope(sid):
            asked = _count_lookups(monkeypatch)
            estimation = _estimation(statement, 0.42)
            estimation.commit()

        assert estimation._id is not None, "the node was not written"
        assert asked == [estimation.hash], (
            f"expected one dedup lookup for the node's own hash, got {len(asked)}:"
            f" {asked}"
        )

    def test_a_statement_commit_asks_only_for_its_own_collision_check(
        self, target, monkeypatch
    ):
        """Statement has a SECOND, unrelated caller, and it must be the only extra.

        `Statement.commit()` looks the hash up itself before delegating, to reject a
        collision with an `Input` carrying the same content. That check asks a different
        question of the same row, so it stays — but it means a Statement commit was
        THREE identical lookups and is now two. Pinned so that the dedup one cannot
        quietly come back and read as this one.
        """
        _, sid = target
        with scope(sid):
            asked = _count_lookups(monkeypatch)
            fresh = Statement(text=f"Counted {random.random()}", meaning="test")
            fresh.commit()

        assert asked == [fresh.hash, fresh.hash], (
            f"expected exactly two lookups (Input-collision check, then dedup),"
            f" got {len(asked)}: {asked}"
        )


class TestDedupStillDedups:
    """The reason the lookup exists at all. If this breaks, the saving is worthless."""

    def test_the_same_content_resolves_onto_the_existing_node(self, target):
        _, sid = target
        with scope(sid):
            text = f"Deduped {random.random()}"

            first = Statement(text=text, meaning="test")
            first.commit()

            second = Statement(text=text, meaning="test")
            second.commit()

        assert second.hash == first.hash, (
            "same text and meaning must produce the same content hash"
        )
        assert second._id == first._id, (
            "the duplicate got its own row instead of resolving onto the existing node"
        )

    def test_a_dedup_hit_writes_nothing(self, di_container, target, monkeypatch):
        """Resolving onto an existing node must not touch the database."""
        _, sid = target
        db = di_container.graph_db()

        with scope(sid):
            text = f"Written once {random.random()}"
            Statement(text=text, meaning="test").commit()

            written = _count_writes(db, monkeypatch)
            Statement(text=text, meaning="test").commit()

        assert written == [], (
            f"a dedup hit wrote {len(written)} node(s); it should reuse, not write"
        )

    def test_different_content_is_not_deduped(self, target):
        """The counter-case: dedup must not collapse genuinely different nodes."""
        _, sid = target
        with scope(sid):
            first = Statement(text=f"Distinct A {random.random()}", meaning="test")
            first.commit()

            other = Statement(text=f"Distinct B {random.random()}", meaning="test")
            other.commit()

        assert other.hash != first.hash
        assert other._id != first._id, "two distinct statements collapsed onto one node"

    def test_an_estimation_dedup_hit_raises_and_that_is_not_new(self, target):
        """Documented, not asserted-as-desirable: the hit path is unreachable.

        Committing a duplicate Estimation directly raises, because `commit()`
        re-connects the target onto what is now the EXISTING node. It raises the same
        way without this change. It is pinned so that if someone ever makes Estimation
        dedup work, this test fails and points them at the count tests above.
        `EstimationManager` is what keeps production off this path.
        """
        statement, sid = target
        with scope(sid):
            _estimation(statement, 0.42).commit()

            with pytest.raises(ValueError, match="maximum cardinality"):
                _estimation(statement, 0.42).commit()


class TestTheAlreadySavedBranchKeepsItsOwnLookup:
    def test_a_saved_then_committed_node_still_dedups(self, di_container, target):
        """`save()` cannot do this one: its dedup guard requires `_id is None`.

        A node saved before commit already has an `_id`, so `commit()` must keep
        asking for itself. Statement is the reachable case — content-addressable
        (committed_at is not in its hash) and saveable while uncommitted.
        """
        _, sid = target
        with scope(sid):
            text = f"Saved then committed {random.random()}"

            first = Statement(text=text, meaning="test")
            first.commit()

            second = Statement(text=text, meaning="test")
            second.save()
            saved_id = second._id
            assert saved_id is not None, "save() did not persist the uncommitted node"
            assert second.hash is None, "save() must not commit"

            second.commit()

        assert second.hash == first.hash
        assert second._id == first._id, (
            "the already-saved node did not adopt the existing node's id — the"
            " `_id is not None` branch in commit() has lost its dedup check"
        )
        assert second._id != saved_id, "it kept its own row instead of deduping"
