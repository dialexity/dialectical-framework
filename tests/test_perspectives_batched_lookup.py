"""`Wheel._perspectives` asks for its perspectives once, not once per endpoint.

`_perspectives` walks the wheel's edges, reads both endpoints of each, and used to call
`PerspectiveRepository.find_by_statement` PER ENDPOINT — 2N round-trips for an
N-perspective wheel — then discarded every answer outside the cycle's
`perspective_hashes`, which it already held before the loop. In one k=4 `build_wheels`
this was the most expensive query shape in the whole run, and ~20 call sites recompute
the property per wheel.

The endpoint reads themselves were already free (`Wheel.edges` prefetches source and
target into their memos); only the perspective lookup was paying per component. It is
now one batched `find_by_statements`.

WHY THIS IS TESTED DIFFERENTIALLY
================================
The order of `_perspectives` is load-bearing — it becomes `polar_segments`, i.e. the
wheel's arrangement, and `sequence_generation` documents its input as "priority order".
So the claim is not "returns the right perspectives", it is "returns the IDENTICAL list".
Rather than argue that from the query, these tests run the old per-component loop
alongside the new batched one against the same graph and require the same list, in the
same order, in every shape that could distinguish them:

- endpoints repeat (each statement is the source of one edge and the target of another),
  so the first-seen dedup has to behave the same;
- a statement shared by TWO perspectives, so a single component yields two rows and
  their relative order is observable;
- a perspective outside the cycle, so the `allowed_hashes` filter still bites.
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    Perspective,
)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.relationships.polarity_relationship import (
    APlusRelationship,
    AMinusRelationship,
    HasPolarityRelationship,
    TMinusRelationship,
    TPlusRelationship,
)
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository
from dialectical_framework.graph.scope_context import scope


def _statement(text: str) -> Statement:
    statement = Statement(text=text, meaning="test")
    statement.commit()
    return statement


def _perspective(
    t: Statement,
    a: Statement,
    tag: str,
    t_plus: Statement | None = None,
) -> Perspective:
    """A committed Perspective over the given T and A statements.

    The four aspect positions are required (minimum cardinality 1 each) and are also
    what makes the FIRST leg of the lookup non-empty, so they are not decoration: a real
    wheel's causality chain runs over aspect statements, which is why that leg was the
    most expensive shape in the run. They are exposed on the returned object so a chain
    can be built through either leg.
    """
    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    pp = Perspective()
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
    for text, rel_cls, alias, attr in (
        (f"T+ {tag}", TPlusRelationship, POSITION_T_PLUS, "t_plus"),
        (f"T- {tag}", TMinusRelationship, POSITION_T_MINUS, "t_minus"),
        (f"A+ {tag}", APlusRelationship, POSITION_A_PLUS, "a_plus"),
        (f"A- {tag}", AMinusRelationship, POSITION_A_MINUS, "a_minus"),
    ):
        # `t_plus` can be supplied so a statement already used as some polarity's T can
        # ALSO be an aspect position, which is the only way one component gets rows from
        # both query legs.
        aspect = t_plus if (attr == "t_plus" and t_plus is not None) \
            else _statement(text)
        getattr(pp, attr).connect(
            aspect,
            relationship=rel_cls(alias=alias, heuristic_similarity=0.85),
        )
    pp.commit()
    return pp


def _aspects(pp: Perspective) -> list[Statement]:
    """A perspective's four aspect statements, the way a wheel chain uses them."""
    return [
        pp.t_plus.all()[0][0],
        pp.a_minus.all()[0][0],
        pp.a_plus.all()[0][0],
        pp.t_minus.all()[0][0],
    ]


def _wheel_over(cycle: Cycle, chain: list[Statement], tag: str) -> Wheel:
    """A wheel whose edges form a closed chain through `chain`.

    Every statement is therefore the source of one edge and the target of another,
    which is what makes the repeat-endpoint case in `_perspectives` reachable.
    """
    wheel = Wheel(intent=f"batched_{tag}")
    wheel.save()
    for i, source in enumerate(chain):
        target = chain[(i + 1) % len(chain)]
        edge = Transition(nonce=f"{tag}_{i}")
        edge.set_source(source).set_target(target)
        edge.commit()
        edge.cycle.connect(wheel)
    cycle.wheels.connect(wheel)
    wheel.commit()
    return wheel


def _perspectives_per_component(wheel: Wheel) -> list[Perspective]:
    """The implementation this change replaced, kept as the reference.

    Deliberately a copy rather than a call into the old code: the point is to compare
    against what the framework USED to return, so it has to survive the old code being
    deleted.
    """
    pp_repo = PerspectiveRepository()

    seen_hashes: set[str] = set()
    result: list[Perspective] = []

    cycle_result = wheel.cycle.get()
    allowed_hashes: set[str] | None = None
    if cycle_result:
        allowed_hashes = set(cycle_result[0].perspective_hashes)

    for edge in wheel.edges:
        source_result = edge.source.get()
        target_result = edge.target.get()

        components = []
        if source_result:
            components.append(source_result[0])
        if target_result:
            components.append(target_result[0])

        for component in components:
            for pp, _ in pp_repo.find_by_statement(component):
                if pp.hash in seen_hashes:
                    continue
                if allowed_hashes is not None and pp.hash not in allowed_hashes:
                    continue
                seen_hashes.add(pp.hash)
                result.append(pp)

    return result


def _assert_identical(wheel: Wheel, why: str) -> list[Perspective]:
    expected = _perspectives_per_component(wheel)
    actual = wheel._perspectives

    assert [pp.hash for pp in actual] == [pp.hash for pp in expected], (
        f"batched lookup changed the perspective list ({why}) — this order becomes"
        f" the wheel's polar_segments"
    )
    return actual


@pytest.fixture
def sid(di_container):
    case = Case()
    case.commit()
    with scope(case.sid):
        yield case.sid


class TestTheListIsUnchanged:
    def test_a_chain_over_aspect_positions(self, sid):
        """The real shape: a wheel's chain runs over T+/T-/A+/A-, i.e. the first leg."""
        pp1 = _perspective(_statement("T one"), _statement("A one"), "one")
        pp2 = _perspective(_statement("T two"), _statement("A two"), "two")

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp1, pp2])
        cycle.commit()

        wheel = _wheel_over(cycle, _aspects(pp1) + _aspects(pp2), "aspects")
        found = _assert_identical(wheel, "chain over aspect positions")

        assert {pp.hash for pp in found} == {pp1.hash, pp2.hash}
        assert wheel.polarity_count == 2

    def test_a_chain_over_t_and_a_with_repeating_endpoints(self, sid):
        """The second leg, via Polarity — and every endpoint visited twice."""
        t1, a1 = _statement("T pol one"), _statement("A pol one")
        t2, a2 = _statement("T pol two"), _statement("A pol two")
        pp1 = _perspective(t1, a1, "pol one")
        pp2 = _perspective(t2, a2, "pol two")

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp1, pp2])
        cycle.commit()

        wheel = _wheel_over(cycle, [t1, a1, t2, a2], "polarity")
        found = _assert_identical(wheel, "two perspectives, repeating endpoints")

        assert {pp.hash for pp in found} == {pp1.hash, pp2.hash}

    def test_the_chain_order_wins_over_the_databases_row_order(self, sid):
        """The test that actually pins ORDER, rather than merely returning a list.

        Every other shape here has the chain running in the same direction as the
        statements were created, so the rows come back in roughly chain order anyway and
        an implementation that iterated the RESULT MAP instead of the edges would still
        pass — verified by mutating it. Here the chain deliberately runs through the
        second perspective's aspects first, so the two orders disagree and only driving
        the loop from `edges` gives the right answer.
        """
        pp_first = _perspective(_statement("T early"), _statement("A early"), "early")
        pp_last = _perspective(_statement("T late"), _statement("A late"), "late")

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp_first, pp_last])
        cycle.commit()

        # Created first-then-last; chained last-then-first.
        wheel = _wheel_over(cycle, _aspects(pp_last) + _aspects(pp_first), "reversed")
        found = _assert_identical(wheel, "chain order opposite to creation order")

        # Self-validating: prove this shape can tell the two orders apart, so the
        # assertion above is not vacuous the way the others turned out to be.
        allowed = {pp.hash for pp in (pp_first, pp_last)}
        rows = PerspectiveRepository().find_by_statements(
            [s for edge in wheel.edges for s in (edge.source.get()[0],
                                                 edge.target.get()[0])]
        )
        map_order: list[str] = []
        for component_rows in rows.values():
            for pp, _ in component_rows:
                if pp.hash in allowed and pp.hash not in map_order:
                    map_order.append(pp.hash)

        assert map_order != [pp.hash for pp in found], (
            "this shape no longer distinguishes chain order from result-map order, so"
            " it cannot catch an implementation that iterates the map — pick endpoints"
            " whose ids run opposite to the chain"
        )

    def test_a_statement_shared_by_two_perspectives(self, sid):
        """One component, two rows — the only case where intra-component order shows.

        `find_by_statements` concatenates the two query legs explicitly instead of
        letting `UNION` decide, precisely so this stays fixed once more than one
        component is in flight.
        """
        shared = _statement("Shared thesis")
        a1, a2 = _statement("A alpha"), _statement("A beta")
        pp1 = _perspective(shared, a1, "alpha")
        pp2 = _perspective(shared, a2, "beta")

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp1, pp2])
        cycle.commit()

        wheel = _wheel_over(cycle, [shared, a1, a2], "shared")
        found = _assert_identical(wheel, "one statement in two perspectives")

        assert len(found) == 2, (
            "both perspectives sharing the component should surface"
        )

    def test_a_component_matching_both_query_legs(self, sid):
        """The case the explicit leg ordering exists for.

        `find_by_statements` runs the two legs as `UNION ALL` with a leg marker and
        concatenates them in Python, because `UNION`'s dedup gives no ordering guarantee
        once more than one component is in flight. That is only observable when a single
        component matches BOTH legs — here one statement is a polarity's T and another
        perspective's T+.

        This asserts the two forms AGREE on such a component. It does not prove the leg
        sort is what makes them agree: Memgraph emits the legs in order anyway, so
        removing the sort still passes (checked by mutation). The sort is insurance, and
        this test is the shape that would notice if the two forms ever diverged for a
        different reason.
        """
        both = _statement("Serves as T and as T+")
        pp_polarity = _perspective(both, _statement("A both"), "both pol")
        pp_aspect = _perspective(
            _statement("T other"), _statement("A other"), "both asp", t_plus=both
        )

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp_polarity, pp_aspect])
        cycle.commit()

        repo = PerspectiveRepository()
        single = repo.find_by_statement(both)
        batched = repo.find_by_statements([both])[both._id]

        assert {rel for _, rel in single} == {"T", "T_PLUS"}, (
            "the fixture no longer produces a both-legs component"
        )
        assert [(pp.hash, rel) for pp, rel in batched] == [
            (pp.hash, rel) for pp, rel in single
        ], "the batched form reordered or dropped a leg"

        wheel = _wheel_over(cycle, [both, _statement("A both")], "both")
        _assert_identical(wheel, "a component matching both legs")

    def test_a_perspective_outside_the_cycle_is_still_filtered_out(self, sid):
        """`allowed_hashes` must keep biting — batching must not widen the result."""
        t1, a1 = _statement("T inside"), _statement("A inside")
        pp_inside = _perspective(t1, a1, "inside")
        # Shares the endpoint, so the lookup returns it, but it is not in the cycle.
        pp_outside = _perspective(t1, _statement("A outside"), "outside")

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp_inside])
        cycle.commit()

        wheel = _wheel_over(cycle, [t1, a1], "filtered")
        found = _assert_identical(wheel, "a perspective outside the cycle")

        assert [pp.hash for pp in found] == [pp_inside.hash]
        assert pp_outside.hash not in {pp.hash for pp in found}


class TestItAsksOnce:
    def test_one_query_replaces_one_per_endpoint(self, di_container, sid, monkeypatch):
        """The saving, which is invisible in the results above."""
        pp1 = _perspective(_statement("T counted"), _statement("A counted"), "c1")
        pp2 = _perspective(_statement("T counted 2"), _statement("A counted 2"), "c2")
        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp1, pp2])
        cycle.commit()
        wheel = _wheel_over(cycle, _aspects(pp1) + _aspects(pp2), "counted")

        db = di_container.graph_db()
        sent: list[str] = []
        fetch = db.execute_and_fetch

        def wrapper(*args, **kwargs):
            sent.append(str(args[0] if args else kwargs.get("query", "")))
            return fetch(*args, **kwargs)

        monkeypatch.setattr(db, "execute_and_fetch", wrapper)
        wheel._perspectives

        lookups = [q for q in sent if "Aspect positions" in q]
        assert len(lookups) == 1, (
            f"expected a single batched perspective lookup, got {len(lookups)}"
            f" — one per endpoint is what this change removed"
        )
        assert "IN $component_ids" in lookups[0]


class TestTheBatchedRepositoryMethod:
    def test_it_returns_the_same_rows_as_the_single_form(self, sid):
        t1, a1 = _statement("T repo"), _statement("A repo")
        pp = _perspective(t1, a1, "repo")
        repo = PerspectiveRepository()

        # Both legs at once: T/A go through Polarity, aspects hang off the Perspective.
        components = [t1, a1] + _aspects(pp)
        batched = repo.find_by_statements(components)

        for component in components:
            single = repo.find_by_statement(component)
            assert [
                (pp.hash, rel) for pp, rel in batched.get(component._id, [])
            ] == [(pp.hash, rel) for pp, rel in single], (
                f"batched rows for {component.text} differ from the single form"
            )

    def test_an_unsaved_component_is_skipped_not_crashed(self, sid):
        """`find_by_statement` returns [] for `_id is None`; the batch must match."""
        unsaved = Statement(text="Never saved", meaning="test")
        assert unsaved._id is None

        assert PerspectiveRepository().find_by_statements([unsaved]) == {}
        assert PerspectiveRepository().find_by_statement(unsaved) == []

    def test_an_empty_batch_asks_nothing(self, di_container, sid, monkeypatch):
        db = di_container.graph_db()
        sent: list[str] = []
        fetch = db.execute_and_fetch
        monkeypatch.setattr(
            db, "execute_and_fetch",
            lambda *a, **k: (sent.append(1), fetch(*a, **k))[1],
        )

        assert PerspectiveRepository().find_by_statements([]) == {}
        assert sent == [], "an empty batch still hit the database"
