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
