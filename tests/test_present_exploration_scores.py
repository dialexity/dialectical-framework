"""
Tests for P/% rendering in present_exploration (task #3).

The Explorer's prompt tells the model to prioritize by causality P and
normalized % — the tool must actually show them. % is normalized within a
layer (same-layer wheels are the competing alternatives), matching the
dialectical_context dump convention.
"""

from __future__ import annotations

import random

import pytest

from dialectical_framework.agents.explorer.tools.present_exploration import \
    PresentExploration
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope


class _FakeEstimations:
    def __init__(self, probability):
        self._probability = probability

    def all(self):
        from dialectical_framework.graph.nodes.estimation import \
            CausalityProbabilityEstimation

        if self._probability is None:
            return []
        return [(CausalityProbabilityEstimation(value=self._probability), None)]


class _FakeCycleRel:
    def __init__(self, cycle_id):
        self._cycle_id = cycle_id

    def get(self):
        if self._cycle_id is None:
            return None

        class _C:
            pass

        c = _C()
        c._id = self._cycle_id
        return (c, None)


class _FakeWheel:
    def __init__(
        self,
        id: int,
        probability=None,
        polarity_count: int = 1,
        cycle_id: int = 100,
    ):
        self._id = id
        self.estimations = _FakeEstimations(probability)
        self.polarity_count = polarity_count
        self.cycle = _FakeCycleRel(cycle_id)


class TestCausalityLabel:
    def test_renders_p_and_percent(self):
        w1, w2 = _FakeWheel(1, 0.6), _FakeWheel(2, 0.2)
        probs = PresentExploration._collect_wheel_probabilities([w1, w2])
        totals = {100: 0.8}
        assert PresentExploration._causality_label(w1, probs, totals) == (
            "P=0.60, 75.0%"
        )
        assert PresentExploration._causality_label(w2, probs, totals) == (
            "P=0.20, 25.0%"
        )

    def test_unestimated_wheel_renders_nothing(self):
        w = _FakeWheel(1, None)
        probs = PresentExploration._collect_wheel_probabilities([w])
        assert PresentExploration._causality_label(w, probs, {}) == ""

    def test_percent_normalizes_within_parent_cycle_only(self):
        """Wheels of different cycles don't share the denominator — the %
        convention matches the dialectical_context dump (siblings within
        one Cycle are the competing arrangements)."""
        mine = _FakeWheel(1, 0.4, cycle_id=100)
        probs = PresentExploration._collect_wheel_probabilities([mine])
        totals = {100: 0.4, 200: 10.0}  # other cycle's total must not bleed in
        assert PresentExploration._causality_label(mine, probs, totals) == (
            "P=0.40, 100.0%"
        )

    def test_orphan_wheel_gets_p_but_no_percent(self):
        orphan = _FakeWheel(1, 0.5, cycle_id=None)
        probs = PresentExploration._collect_wheel_probabilities([orphan])
        assert PresentExploration._causality_label(orphan, probs, {}) == "P=0.50"


class TestFormatWheelsWithScores:
    def _seed_two_estimated_wheels(self):
        """Nexus + 1 PP + cycle + two committed wheels with P estimations."""
        from dialectical_framework.graph.estimation_manager import \
            EstimationManager
        from dialectical_framework.graph.nodes.cycle import Cycle
        from dialectical_framework.graph.nodes.estimation import \
            CausalityProbabilityEstimation
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.nodes.transition import Transition
        from dialectical_framework.graph.nodes.wheel import Wheel
        from test_dialectical_context import _create_perspective_with_aspects

        uid = f"{random.random():.8f}"
        pp = _create_perspective_with_aspects(
            thesis_text=f"Control {uid}", antithesis_text=f"Freedom {uid}"
        )
        nexus = Nexus(intent=f"score rendering {uid}")
        nexus.save()
        nexus.commit()
        pp.nexus.connect(nexus)

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp])
        cycle.commit()

        t_stmt, _ = pp.polarity.get()[0].t.all()[0]
        a_stmt, _ = pp.polarity.get()[0].a.all()[0]

        wheels = []
        for i, p in enumerate([0.6, 0.2]):
            wheel = Wheel(intent=f"wheel_{uid}_{i}")
            wheel.save()
            tr1 = Transition(nonce=f"{uid}_{i}_1")
            tr1.set_source(t_stmt).set_target(a_stmt)
            tr1.commit()
            tr1.cycle.connect(wheel)
            tr2 = Transition(nonce=f"{uid}_{i}_2")
            tr2.set_source(a_stmt).set_target(t_stmt)
            tr2.commit()
            tr2.cycle.connect(wheel)
            cycle.wheels.connect(wheel)
            wheel.commit()
            EstimationManager().upsert_estimation(
                wheel, CausalityProbabilityEstimation, p
            )
            wheels.append(wheel)

        return nexus, wheels

    @pytest.mark.asyncio
    async def test_output_carries_p_and_percent(self):
        case = Case()
        case.commit()
        with scope(case.sid):
            nexus, wheels = self._seed_two_estimated_wheels()

            concern = PresentExploration(nexus_hash=nexus.hash[:7])
            output = await concern.resolve()

            assert "P=0.60, 75.0%" in output
            assert "P=0.20, 25.0%" in output
            assert "causality" in output

    @pytest.mark.asyncio
    async def test_most_plausible_wheel_listed_first(self):
        case = Case()
        case.commit()
        with scope(case.sid):
            nexus, wheels = self._seed_two_estimated_wheels()

            concern = PresentExploration(nexus_hash=nexus.hash[:7])
            output = await concern.resolve()

            assert output.index("P=0.60") < output.index("P=0.20")
