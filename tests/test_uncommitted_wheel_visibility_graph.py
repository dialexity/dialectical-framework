"""An abandoned half-built Wheel must be invisible to every discovery read.

CLAUDE.md states the invariant flatly: "All listing/discovery queries MUST filter
`WHERE n.hash IS NOT NULL`." Two of the three wheel reads did not, and the build
order makes the gap reachable rather than theoretical —
`_build_wheels_for_cycle` commits the parent Cycle first, then `wheel.save()`s to
get an `_id`, attaches every Transition, connects the Cycle, and only then
`wheel.commit()`s. A conversation that stops anywhere in that window (a closed
stream, a killed process; there are no transactions to roll back, GQLAlchemy
hardcodes autocommit) leaves a Wheel with the FULL transition count, a matching
canonical signature and a perfectly good committed Cycle pointing at it.

Two consequences, both of which this file pins:

1. `find_by_component_sequence` is the DEDUP read. Handing back the ghost makes
   `_build_wheels_for_cycle` `continue` past building a real wheel, so the
   exploration ends one wheel short while believing it reused one.
2. `find_by_layer` feeds probability normalisation across competing alternatives
   (`causality_estimation`), the synthesis sub-wheel dump and the exploration
   presented to the person. A ghost there is not stale rows — it is a phantom
   alternative diluting the normalisation.

The last two tests are the other half: the filters must not hide REAL structure.
A committed-only predicate that also drops committed nodes would pass every
assertion above and break exploration completely.
"""

from __future__ import annotations

import uuid

import pytest
from test_dialectical_context import _create_perspective_with_aspects

from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.cycle_repository import \
    CycleRepository
from dialectical_framework.graph.repositories.wheel_repository import \
    WheelRepository
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    return f"uncommitted-wheel-{uuid.uuid4().hex[:8]}"


def _seed_perspective(nexus: Nexus, name: str) -> tuple[Perspective, Cycle,
                                                        list[Statement]]:
    """PP → committed Cycle, plus the two Statements a 1-PP wheel cycles over."""
    pp = _create_perspective_with_aspects(
        thesis_text=f"Control {name}", antithesis_text=f"Freedom {name}"
    )
    pp.nexus.connect(nexus)

    # Committed BEFORE any wheel exists, which is what makes the ghost
    # reachable: `find_by_layer` matches on the Cycle and walks HAS_WHEEL.
    cycle = Cycle(intent="preset:balanced")
    cycle.set_perspectives([pp])
    cycle.commit()

    polarity, _ = pp.polarity.get()
    t_stmt, _ = polarity.t.all()[0]
    a_stmt, _ = polarity.a.all()[0]
    return pp, cycle, [t_stmt, a_stmt]


def _seed_wheel(
    cycle: Cycle,
    components: list[Statement],
    name: str,
    *,
    commit: bool,
) -> Wheel:
    """A 1-PP wheel, stopped either at `commit()` or one step short of it.

    `commit=False` is not a contrived state: it is byte-for-byte what
    `_build_wheels_for_cycle` leaves behind when the run dies after the last
    `connect` and before the last write.
    """
    wheel = Wheel(intent=f"wheel {name}")
    wheel.save()
    t_stmt, a_stmt = components
    for i, (source, target) in enumerate(((t_stmt, a_stmt), (a_stmt, t_stmt))):
        edge = Transition(nonce=f"uncommitted_{name}_{i}")
        edge.set_source(source).set_target(target)
        edge.commit()
        edge.cycle.connect(wheel)
    cycle.wheels.connect(wheel)
    if commit:
        wheel.commit()
    return wheel


class TestAnAbandonedWheelIsNotADedupHit:
    @pytest.mark.asyncio
    async def test_find_by_component_sequence_ignores_the_uncommitted_wheel(self):
        """The whole bug in one assertion: a miss here is what lets a real one be built."""
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="abandoned exploration")
            nexus.save()
            nexus.commit()
            _, cycle, components = _seed_perspective(nexus, "a")
            ghost = _seed_wheel(cycle, components, "a", commit=False)

            found = WheelRepository().find_by_component_sequence(components)

        assert ghost.hash is None, "the fixture must leave the wheel uncommitted"
        assert found is None, (
            "an abandoned wheel was returned as a dedup hit; the caller would "
            "`continue` past building a real one"
        )

    @pytest.mark.asyncio
    async def test_the_committed_wheel_wins_when_both_exist(self):
        """Same components, one real and one abandoned: dedup must land on the real one."""
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="abandoned exploration")
            nexus.save()
            nexus.commit()
            _, cycle, components = _seed_perspective(nexus, "b")
            _seed_wheel(cycle, components, "b_ghost", commit=False)
            real = _seed_wheel(cycle, components, "b_real", commit=True)

            found = WheelRepository().find_by_component_sequence(components)

        assert found is not None
        assert found.hash == real.hash


class TestAnAbandonedWheelIsNotACompetingAlternative:
    @pytest.mark.asyncio
    async def test_find_by_layer_excludes_the_uncommitted_wheel(self):
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="abandoned exploration")
            nexus.save()
            nexus.commit()
            pp, cycle, components = _seed_perspective(nexus, "c")
            real = _seed_wheel(cycle, components, "c_real", commit=True)
            ghost = _seed_wheel(cycle, components, "c_ghost", commit=False)

            wheels = WheelRepository().find_by_layer([pp], nexus=nexus)

        assert ghost.hash is None
        hashes = [w.hash for w in wheels]
        assert hashes == [real.hash], (
            "a phantom alternative reached probability normalisation, the "
            f"synthesis dump and the presented exploration: {hashes}"
        )


class TestTheFiltersDoNotHideRealStructure:
    """The other half. A predicate that drops committed nodes breaks exploration."""

    @pytest.mark.asyncio
    async def test_committed_wheels_are_still_found_at_their_layer(self):
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="healthy exploration")
            nexus.save()
            nexus.commit()
            pp, cycle, components = _seed_perspective(nexus, "d")
            first = _seed_wheel(cycle, components, "d_one", commit=True)
            second = _seed_wheel(cycle, components, "d_two", commit=True)

            wheels = WheelRepository().find_by_layer([pp], nexus=nexus)
            found_seq = WheelRepository().find_by_component_sequence(components)

        assert {w.hash for w in wheels} == {first.hash, second.hash}
        assert found_seq is not None and found_seq.hash in {first.hash, second.hash}

    @pytest.mark.asyncio
    async def test_committed_cycles_are_still_found_at_their_layer(self):
        """The Cycle filter closes no live hole today; it must also cost nothing.

        Nothing currently `save()`s a Cycle before committing it, so an
        uncommitted Cycle carrying `perspective_hashes` cannot exist — which is a
        property of how callers happen to build them, not of the query. The
        filter is there so that stops mattering, and this asserts it did not
        change what the query returns meanwhile.
        """
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="healthy exploration")
            nexus.save()
            nexus.commit()
            pp, cycle, _ = _seed_perspective(nexus, "e")

            cycles = CycleRepository().find_by_layer([pp], nexus=nexus)

        assert [c.hash for c in cycles] == [cycle.hash]
