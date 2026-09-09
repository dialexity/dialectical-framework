"""What `immutable=True` on a RelationshipManager may and may not do.

The flag memoises a relationship read on the source node INSTANCE. That is a
read-volume lever with real teeth — `Transition.source`/`.target` were 61,197 of
122,893 graph charges in one k=4 `build_wheels`, because `Wheel.statements` reads
`self.edges`, `edges` runs `order_transitions` which pulls both endpoints to walk
the chain, and the `statements` loop then pulls the SAME endpoints off the SAME
objects again.

It is also the kind of thing that fails silently. A stale memo does not raise; it
returns a confident wrong answer, and every caller downstream believes it. So the
properties below are pinned rather than trusted, and the two that matter most are
the NEGATIVE ones: an empty read must not be memoised, and a relationship that did
not ask for the flag must not be cached at all.

Counting queries rather than asserting on internals, because the point of the flag
is the round-trip that does not happen.
"""

from __future__ import annotations

import random

import pytest

from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.graph.nodes.case import Case


def _count_endpoint_queries(db, monkeypatch) -> list[str]:
    """Record every IS_SOURCE_OF / IS_TARGET_OF query the client sends."""
    seen: list[str] = []
    fetch = db.execute_and_fetch

    def wrapper(*args, **kwargs):
        query = str(args[0] if args else kwargs.get("query", ""))
        if "IS_SOURCE_OF" in query or "IS_TARGET_OF" in query:
            seen.append(query)
        return fetch(*args, **kwargs)

    monkeypatch.setattr(db, "execute_and_fetch", wrapper)
    return seen


@pytest.fixture
def transition(di_container):
    """A committed Transition with both endpoints, inside a scope."""
    case = Case()
    case.commit()
    with scope(case.sid):
        source = Statement(text=f"Source {random.random()}", meaning="test")
        source.commit()
        target = Statement(text=f"Target {random.random()}", meaning="test")
        target.commit()

        trans = Transition()
        trans.set_source(source).set_target(target)
        trans.commit()
        yield trans, source, target, case.sid


class TestAnImmutableEdgeIsReadOnce:
    def test_the_second_read_sends_no_query(self, di_container, transition, monkeypatch):
        trans, source, target, sid = transition
        db = di_container.graph_db()

        with scope(sid):
            seen = _count_endpoint_queries(db, monkeypatch)

            first_source, _ = trans.source.get()
            first_target, _ = trans.target.get()
            after_first = len(seen)

            second_source, _ = trans.source.get()
            second_target, _ = trans.target.get()

        assert after_first == 2, f"expected one query per endpoint, got {after_first}"
        assert len(seen) == 2, (
            f"the second read went to the database: {len(seen)} queries total"
        )
        # Memoised, not merely quiet — the answer has to still be right.
        assert first_source.hash == source.hash
        assert first_target.hash == target.hash
        assert second_source.hash == source.hash
        assert second_target.hash == target.hash

    def test_a_second_instance_of_the_same_node_reads_for_itself(
        self, di_container, transition, monkeypatch
    ):
        """The memo is per OBJECT, and that bound is deliberate.

        Caching per node id across a process would need invalidation on writes made
        through any other object for the same node — which the manager cannot see.
        Per-instance keeps the guarantee local to something it can actually observe.
        """
        trans, source, target, sid = transition
        db = di_container.graph_db()

        with scope(sid):
            trans.source.get()
            seen = _count_endpoint_queries(db, monkeypatch)

            other = Transition()
            other._id = trans._id
            other.hash = trans.hash
            fresh_source, _ = other.source.get()

        assert len(seen) == 1, "a distinct instance must do its own read"
        assert fresh_source.hash == source.hash


class TestAnEmptyReadIsNotMemoised:
    """The one way an immutable-edge memo can lie, and the reason for the guard.

    The write path on this tree is `save_node` -> `connect` -> `commit`, so a read
    landing between those steps legitimately sees no edge. Memoising that would
    freeze a transient truth into a permanent one, and the node would report itself
    endpoint-less for the rest of its life.

    TWO guards stop it and mutation testing showed they are REDUNDANT here, which is
    worth writing down rather than discovering later: refusing to store an empty read
    (`_store_all`) and dropping the memo on connect (`_connect_internal`). Removing
    either one alone leaves this test green — the survivor covers for it — and only
    removing BOTH turns the post-commit read back into `None`. So do not read a green
    run as evidence that a particular guard is exercised, and do not delete one on the
    grounds that the suite still passes. They are cheap and they fail independently:
    invalidation misses a write made through a different manager for the same node,
    and the empty-read refusal misses nothing but only helps if a read happened first.
    """

    def test_reading_after_save_but_before_connect_does_not_poison_the_memo(
        self, di_container
    ):
        """The node must be SAVED for this to bite, and that is the whole point.

        With no `_id`, `all()` short-circuits before the query and stores nothing, so
        a read there cannot poison anything and testing it proves nothing. The real
        window is the one `commit()` itself opens: `save_node` assigns an `_id`, and
        only then does `connect` run. A read in between issues a genuine query, gets
        a genuine empty answer, and is exactly what must not be remembered.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            source = Statement(text=f"Source {random.random()}", meaning="test")
            source.commit()
            target = Statement(text=f"Target {random.random()}", meaning="test")
            target.commit()

            trans = Transition()
            trans.set_source(source).set_target(target)
            trans.save()
            assert trans._id is not None, "test needs a saved-but-unconnected node"

            # Real queries, legitimately empty — the edges do not exist yet.
            assert trans.source.get() is None
            assert trans.target.get() is None

            trans.commit()

            got_source = trans.source.get()
            got_target = trans.target.get()

        assert got_source is not None, "the pre-connect empty read was memoised"
        assert got_target is not None, "the pre-connect empty read was memoised"
        assert got_source[0].hash == source.hash
        assert got_target[0].hash == target.hash


class TestTheFlagIsWhatGatesIt:
    def test_a_relationship_without_the_flag_still_goes_to_the_database(
        self, di_container, transition, monkeypatch
    ):
        """Otherwise this suite would pass with the memo applied to everything."""
        trans, _, _, sid = transition
        db = di_container.graph_db()

        with scope(sid):
            wheel = Wheel(intent="immutable-flag-gate")
            wheel.save()
            trans.cycle.connect(wheel)

            seen: list[str] = []
            fetch = db.execute_and_fetch

            def wrapper(*args, **kwargs):
                query = str(args[0] if args else kwargs.get("query", ""))
                if "BELONGS_TO_CYCLE" in query:
                    seen.append(query)
                return fetch(*args, **kwargs)

            monkeypatch.setattr(db, "execute_and_fetch", wrapper)

            wheel.edges
            wheel.edges

        assert Transition.cycle.immutable is False, "cycle must not be declared immutable"
        assert len(seen) >= 2, (
            f"an undeclared relationship was cached anyway: {len(seen)} queries"
        )

    def test_the_declarations_that_carry_the_flag_are_the_expected_two(self):
        """A guard on the blast radius, not a style check.

        Every declaration marked immutable is a promise that no code path rewires
        that edge after commit. Adding one is a review decision, so widening the
        set has to fail here first.
        """
        assert Transition.source.immutable is True
        assert Transition.target.immutable is True


@pytest.fixture
def wheel_of_four(di_container):
    """A committed wheel whose four transitions form a closed chain."""
    case = Case()
    case.commit()
    with scope(case.sid):
        statements = []
        for i in range(4):
            statement = Statement(text=f"Component {i} {random.random()}", meaning="test")
            statement.commit()
            statements.append(statement)

        wheel = Wheel(intent=f"prefetch-{random.random()}")
        wheel.save()
        for i in range(4):
            trans = Transition()
            trans.set_source(statements[i]).set_target(statements[(i + 1) % 4])
            trans.commit()
            trans.cycle.connect(wheel)

        yield wheel, statements, case.sid


class TestABatchedReadCostsTheSameWhateverTheEdgeCount:
    """`prefetch` is the lever the per-instance memo could not reach.

    `Wheel.edges` builds a FRESH list of Transitions every call, so nothing an
    earlier call memoised is available to this one — and ordering the chain reads
    both endpoints of every edge before `statements` reads the same endpoints off
    the same objects. The memo made the second pass free; only a batched read
    makes the first pass cheap.
    """

    def test_reading_a_wheel_costs_two_endpoint_queries_not_two_per_edge(
        self, di_container, wheel_of_four, monkeypatch
    ):
        wheel, statements, sid = wheel_of_four
        db = di_container.graph_db()

        with scope(sid):
            seen = _count_endpoint_queries(db, monkeypatch)
            ordered = wheel.edges
            after_ordering = len(seen)
            components = wheel.statements

        assert len(ordered) == 4, "the wheel should have four edges"
        assert after_ordering == 2, (
            f"one query per direction, whatever the edge count: got {after_ordering}"
        )
        # `statements` traverses `edges` again — deliberately, it re-reads the
        # graph — so it pays for its own batch and nothing more. Two traversals
        # is 4 queries; it was 16 with only the per-instance memo and 27 without.
        assert len(seen) == 4, (
            f"`statements` re-read endpoints its own batch already had: {len(seen)}"
        )
        # Cheaper, and still the same chain.
        assert [c.hash for c in components] == [s.hash for s in statements]

    def test_the_chain_order_is_what_it_was_before_prefetching(
        self, di_container, wheel_of_four, monkeypatch
    ):
        """What the memo holds must be what that node's own read would have held.

        Drives both paths and compares. This catches the failure that actually
        threatens a batched read — rows landing under the wrong source, verified by
        cross-wiring them and watching this fail.

        It does NOT pin the `ORDER BY`, and cannot: both declarations carrying
        `immutable=True` are 1:1, so each source has exactly one row and no order
        is observable. The clause is there for the general case, where consumers
        treat relationship order as canonical (`build_pp_index`'s T1/T2 indices,
        rendered component sequences) — unpinned insurance, not a tested claim.
        """
        wheel, _, sid = wheel_of_four

        with scope(sid):
            prefetched = [
                (t.hash, t.source.get()[0].hash, t.target.get()[0].hash)
                for t in wheel.edges
            ]

            # The same edges, each reading for itself with no memo in the way.
            unprimed = []
            for edge, _rel in wheel._edges.all():
                fresh = Transition()
                fresh._id = edge._id
                fresh.hash = edge.hash
                unprimed.append(
                    (fresh.hash, fresh.source.get()[0].hash, fresh.target.get()[0].hash)
                )

        assert sorted(prefetched) == sorted(unprimed), "prefetch changed an endpoint"
        assert prefetched[0][2] == prefetched[1][1], "the chain is no longer ordered"


class TestPrefetchRefusesWhatItCannotGuarantee:
    def test_a_mutable_edge_set_cannot_be_prefetched(self, di_container, transition):
        """A memo on a mutable edge set is written and never read.

        `all()` only consults the cache when the declaration is immutable, so
        priming one elsewhere would look like a cache and do nothing — the kind of
        dead lever that gets cited as evidence a path is already optimised.
        """
        trans, _, _, sid = transition

        with scope(sid):
            with pytest.raises(ValueError, match="not declared immutable"):
                Transition.cycle.prefetch([trans])

    def test_an_unconnected_node_is_left_to_read_for_itself(
        self, di_container, monkeypatch
    ):
        """Absent rows must not become a memoised absence.

        Same hazard as `_store_all`'s empty-read refusal, reached a different way:
        one node in the batch has no endpoints yet, so the query returns nothing
        for it. Priming that as "no endpoints" would outlive the connect.

        The assertion has to be that the read STILL GOES TO THE DATABASE, not that
        the answer is right after committing — mutation testing showed the latter
        passes even when absent rows are primed empty, because `connect` drops the
        memo on the way through and covers for it. Redundant guards again, same as
        `TestAnEmptyReadIsNotMemoised` records.
        """
        db = di_container.graph_db()
        case = Case()
        case.commit()
        with scope(case.sid):
            source = Statement(text=f"Source {random.random()}", meaning="test")
            source.commit()
            target = Statement(text=f"Target {random.random()}", meaning="test")
            target.commit()

            connected = Transition()
            connected.set_source(source).set_target(target)
            connected.commit()

            pending = Transition()
            pending.set_source(source).set_target(target)
            pending.save()
            assert pending._id is not None

            unsaved = Transition()
            assert unsaved._id is None

            # The unsaved one must not break the batch it is in.
            Transition.source.prefetch([connected, pending, unsaved])

            seen = _count_endpoint_queries(db, monkeypatch)
            assert connected.source.get() is not None, "the connected one was skipped"
            assert not seen, "the connected one was not primed"

            assert pending.source.get() is None, "the pending edge does not exist yet"
            assert len(seen) == 1, (
                "an absent row was memoised as an absent edge — this read should"
                " have gone to the database"
            )

            pending.commit()
            assert pending.source.get() is not None


class TestTheCallerCannotCorruptTheMemo:
    def test_a_memo_hit_is_a_copy(self, di_container, transition):
        """`all()` results get sorted and sliced by callers all over this tree.

        Mutate the result of a CACHED read, not the first one. The first read's list
        is already distinct from the memo because `_store_all` copies on the way in,
        so clearing it proves nothing — the exposed path is every read after it.
        """
        trans, source, _, sid = transition

        with scope(sid):
            trans.source.all()          # populates the memo
            from_memo = trans.source.all()
            assert len(from_memo) == 1, "second read should be the memo"
            from_memo.clear()
            after = trans.source.all()

        assert len(after) == 1, "a caller mutating a memo hit emptied the memo"
        assert after[0][0].hash == source.hash
