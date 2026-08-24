"""
The status read against a real graph — the half `tests/test_build_status.py` fakes.

That file patches the repository reads to pin the state machine (shallow vs
interrupted vs blocked, the resume hint, fail-soft). Which leaves the new Cypher
untested: `WheelRepository.find_by_nexus` walks Cycle→Wheel across ALL layers
and scopes by the nexus's perspective hashes, and a typo or a wrong scoping
predicate there would surface only in a host app, as an empty status for a
graph full of work.

So: build a small exploration for real, and ask.
"""

from __future__ import annotations

import uuid

import pytest
from test_dialectical_context import _create_perspective_with_aspects

from dialectical_framework.concerns.ac_re_taxonomy import INSIGHT_CATEGORIES
from dialectical_framework.concerns.build_status import (WHEEL_SHALLOW,
                                                        BuildStatus)
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.wheel_repository import \
    WheelRepository
from dialectical_framework.graph.scope_context import scope

EXPECTED = 2 * len(INSIGHT_CATEGORIES)


def _new_sid() -> str:
    return f"build-status-{uuid.uuid4().hex[:8]}"


def _seed_wheel(nexus: Nexus, name: str) -> tuple[Cycle, Wheel]:
    """One 1-PP wheel under `nexus`: PP → Cycle → Wheel with its two edges."""
    pp = _create_perspective_with_aspects(
        thesis_text=f"Control {name}", antithesis_text=f"Freedom {name}"
    )
    pp.nexus.connect(nexus)

    cycle = Cycle(intent="preset:balanced")
    cycle.set_perspectives([pp])
    cycle.commit()

    polarity, _ = pp.polarity.get()
    t_stmt, _ = polarity.t.all()[0]
    a_stmt, _ = polarity.a.all()[0]

    wheel = Wheel(intent=f"wheel {name}")
    wheel.save()
    for i, (source, target) in enumerate(((t_stmt, a_stmt), (a_stmt, t_stmt))):
        edge = Transition(nonce=f"build_status_{name}_{i}")
        edge.set_source(source).set_target(target)
        edge.commit()
        edge.cycle.connect(wheel)
    cycle.wheels.connect(wheel)
    wheel.commit()
    return cycle, wheel


class TestBuildStatusOverARealGraph:
    @pytest.mark.asyncio
    async def test_find_by_nexus_returns_every_wheel_with_its_cycle(self):
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="status exploration")
            nexus.save()
            nexus.commit()
            cycle_a, wheel_a = _seed_wheel(nexus, "a")
            cycle_b, wheel_b = _seed_wheel(nexus, "b")

            pairs = WheelRepository().find_by_nexus(nexus)

        found = {w.hash: c.hash for c, w in pairs}
        assert found == {wheel_a.hash: cycle_a.hash, wheel_b.hash: cycle_b.hash}

    @pytest.mark.asyncio
    async def test_another_nexus_wheels_stay_out(self):
        """The scoping predicate, which is the easy one to get wrong: a Cycle is
        this Nexus's only when all of its perspectives are."""
        sid = _new_sid()
        with scope(sid):
            mine = Nexus(intent="mine")
            mine.save()
            mine.commit()
            theirs = Nexus(intent="theirs")
            theirs.save()
            theirs.commit()

            _, my_wheel = _seed_wheel(mine, "mine")
            _, their_wheel = _seed_wheel(theirs, "theirs")

            pairs = WheelRepository().find_by_nexus(mine)

        assert [w.hash for _, w in pairs] == [my_wheel.hash]
        assert their_wheel.hash not in [w.hash for _, w in pairs]

    @pytest.mark.asyncio
    async def test_status_reports_a_built_but_undeveloped_exploration(self):
        """A structure-only exploration: wheels exist, pathways do not.

        This is exactly what `explore` leaves behind for every arrangement it
        did not deepen, so it must read as shallow (0 of 6N, nothing owed) and
        not as an interrupted build the user should be nagged to finish.
        """
        sid = _new_sid()
        with scope(sid):
            nexus = Nexus(intent="status exploration")
            nexus.save()
            nexus.commit()
            _, wheel = _seed_wheel(nexus, "only")

            concern = BuildStatus()
            status = await concern.resolve()

        assert status.sid == sid
        assert status.nexus_hashes == (nexus.hash,)
        assert len(status.wheels) == 1

        only = status.wheels[0]
        assert only.hash == wheel.hash
        assert only.layer == 1
        assert only.fraction == f"0/{EXPECTED}"
        assert only.state == WHEEL_SHALLOW
        assert only.syntheses == ()
        assert status.resume_hint is None
        assert not status.unreadable_hashes

        # The tension itself is developed — the Perspective is complete — so the
        # only thing outstanding is a deepen the user has not asked for.
        assert status.is_complete
        assert concern.report.ok
