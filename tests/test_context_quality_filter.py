"""
Tests for the context-dump quality filter (task #5).

DialecticalContext pre-prunes instead of instructing: standalone perspectives
below the quality floor (HS < advisor_polarity_quality_min_hs, area < advisor_perspective_quality_min_area, or
failed validation) are suppressed with a count line; wheels are capped to the
top-% advisor_wheel_quality_top_plausible per cycle with a count line. Nexus members are
load-bearing and never suppressed. Missing scores never suppress.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS, POSITION_T_PLUS,
    Perspective)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope
from test_dialectical_context import _create_perspective_with_aspects


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


@contextmanager
def _settings(di_container, **overrides):
    """Temporarily override settings fields on the DI container."""
    current = di_container.settings()
    di_container.settings.override(current.model_copy(update=overrides))
    try:
        yield
    finally:
        di_container.settings.reset_override()
        di_container.settings.override(current)


def _perspective_with_hs(a_hs: float, tag: str) -> Perspective:
    """Committed perspective whose antithesis HS is controllable."""
    t = Statement(text=f"Thesis {tag}", meaning="test")
    t.commit()
    a = Statement(text=f"Antithesis {tag}", meaning="test")
    a.commit()
    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=a_hs)
    polarity.commit()

    pp = Perspective()
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
    for text, rel_cls, alias, attr in [
        (f"T+ {tag}", TPlusRelationship, POSITION_T_PLUS, "t_plus"),
        (f"T- {tag}", TMinusRelationship, POSITION_T_MINUS, "t_minus"),
        (f"A+ {tag}", APlusRelationship, POSITION_A_PLUS, "a_plus"),
        (f"A- {tag}", AMinusRelationship, POSITION_A_MINUS, "a_minus"),
    ]:
        s = Statement(text=text, meaning="test")
        s.commit()
        getattr(pp, attr).connect(
            s, relationship=rel_cls(alias=alias, heuristic_similarity=0.8)
        )
    pp.commit()
    return pp


class TestPerspectiveQualityFloor:
    @pytest.mark.asyncio
    async def test_weak_hs_suppressed_with_count_line(self):
        sid = _new_sid()
        with scope(sid):
            _perspective_with_hs(0.9, "strong")
            _perspective_with_hs(0.2, "weak")

            dump = await DialecticalContext().resolve()

            assert "Thesis strong" in dump
            assert "Thesis weak" not in dump
            assert "1 unexplored tension(s) suppressed" in dump

    @pytest.mark.asyncio
    async def test_failed_validation_suppressed(self):
        sid = _new_sid()
        with scope(sid):
            bad = _create_perspective_with_aspects(thesis_text="Flawed")
            bad.validation = "failed: Differential minimum: ..."
            bad.save()
            _create_perspective_with_aspects(thesis_text="Sound")

            dump = await DialecticalContext().resolve()

            assert "Sound" in dump
            assert "Flawed" not in dump
            assert "suppressed" in dump

    @pytest.mark.asyncio
    async def test_missing_scores_never_suppress(self):
        """The reference helper sets no complementarities (area=None) and
        HS=0.8 — such a perspective must stay visible."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects(thesis_text="Unscored")
            dump = await DialecticalContext().resolve()
            assert "Unscored" in dump
            assert "suppressed" not in dump

    @pytest.mark.asyncio
    async def test_zero_floor_disables_hs_check(self, di_container):
        sid = _new_sid()
        with scope(sid):
            _perspective_with_hs(0.2, "weak")
            with _settings(di_container, advisor_polarity_quality_min_hs=0.0):
                dump = await DialecticalContext().resolve()
            assert "Thesis weak" in dump

    @pytest.mark.asyncio
    async def test_all_suppressed_still_reports_count(self):
        """Even when every standalone tension is below the floor the dump
        must say so — never a silent 'fresh conversation'."""
        sid = _new_sid()
        with scope(sid):
            _perspective_with_hs(0.2, "weak")
            dump = await DialecticalContext().resolve()
            assert "1 unexplored tension(s) suppressed" in dump

    @pytest.mark.asyncio
    async def test_nexus_members_never_suppressed(self):
        """Nexus members are load-bearing (wheel indices reference them) —
        the floor applies to standalone perspectives only."""
        from dialectical_framework.graph.nodes.nexus import Nexus

        sid = _new_sid()
        with scope(sid):
            weak_member = _perspective_with_hs(0.2, "member")
            nexus = Nexus(intent="floor test")
            nexus.save()
            nexus.commit()
            weak_member.nexus.connect(nexus)

            dump = await DialecticalContext().resolve()
            assert "Thesis member" in dump
            assert "suppressed" not in dump


class TestWheelCap:
    def _seed_cycle_with_wheels(self, probabilities: list[float]):
        from dialectical_framework.graph.estimation_manager import \
            EstimationManager
        from dialectical_framework.graph.nodes.cycle import Cycle
        from dialectical_framework.graph.nodes.estimation import \
            CausalityProbabilityEstimation
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.transition import Transition
        from dialectical_framework.graph.nodes.wheel import Wheel

        pp = _create_perspective_with_aspects(thesis_text="Capped")
        nexus = Nexus(intent="wheel cap test")
        nexus.save()
        nexus.commit()
        pp.nexus.connect(nexus)

        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp])
        cycle.commit()

        polarity, _ = pp.polarity.get()
        t_stmt, _ = polarity.t.all()[0]
        a_stmt, _ = polarity.a.all()[0]

        wheels = []
        for i, p in enumerate(probabilities):
            wheel = Wheel(intent=f"cap_wheel_{i}")
            wheel.save()
            tr1 = Transition(nonce=f"cap_{i}_1")
            tr1.set_source(t_stmt).set_target(a_stmt)
            tr1.commit()
            tr1.cycle.connect(wheel)
            tr2 = Transition(nonce=f"cap_{i}_2")
            tr2.set_source(a_stmt).set_target(t_stmt)
            tr2.commit()
            tr2.cycle.connect(wheel)
            cycle.wheels.connect(wheel)
            wheel.commit()
            EstimationManager().upsert_estimation(
                wheel, CausalityProbabilityEstimation, p
            )
            wheels.append(wheel)
        return wheels

    @pytest.mark.asyncio
    async def test_cap_renders_top_percent_with_count(self, di_container):
        sid = _new_sid()
        with scope(sid):
            wheels = self._seed_cycle_with_wheels([0.6, 0.3, 0.1])
            with _settings(di_container, advisor_wheel_quality_top_plausible=1):
                dump = await DialecticalContext().resolve()

            top, mid, low = wheels
            assert top.short_hash in dump
            assert mid.short_hash not in dump
            assert low.short_hash not in dump
            assert "2 lower-probability wheel(s) not shown" in dump

    @pytest.mark.asyncio
    async def test_percent_denominator_stays_full_sibling_set(
        self, di_container
    ):
        """Hidden wheels still count in the % denominator — the shown wheel
        must NOT display 100%."""
        sid = _new_sid()
        with scope(sid):
            self._seed_cycle_with_wheels([0.6, 0.3, 0.1])
            with _settings(di_container, advisor_wheel_quality_top_plausible=1):
                dump = await DialecticalContext().resolve()
            assert "P=0.60, 60.0%" in dump

    @pytest.mark.asyncio
    async def test_under_cap_renders_all_without_note(self, di_container):
        sid = _new_sid()
        with scope(sid):
            wheels = self._seed_cycle_with_wheels([0.6, 0.3])
            with _settings(di_container, advisor_wheel_quality_top_plausible=3):
                dump = await DialecticalContext().resolve()
            for w in wheels:
                assert w.short_hash in dump
            assert "not shown" not in dump

    @pytest.mark.asyncio
    async def test_zero_cap_disables_limit(self, di_container):
        sid = _new_sid()
        with scope(sid):
            wheels = self._seed_cycle_with_wheels([0.5, 0.3, 0.2])
            with _settings(di_container, advisor_wheel_quality_top_plausible=0):
                dump = await DialecticalContext().resolve()
            for w in wheels:
                assert w.short_hash in dump

    @pytest.mark.asyncio
    async def test_scoped_dump_exempt_from_wheel_cap(self, di_container):
        """The counsel-mode (nexus-pinned) render shows the user-built
        exploration in FULL — the wheel cap is unscoped-dump policy only
        (same load-bearing exemption as nexus members in the quality floor)."""
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        sid = _new_sid()
        with scope(sid):
            wheels = self._seed_cycle_with_wheels([0.6, 0.3, 0.1])
            nexus = NexusRepository().find_all()[0]

            with _settings(di_container, advisor_wheel_quality_top_plausible=1):
                dump = await DialecticalContext(
                    nexus_hash=nexus.hash[:7]
                ).resolve()

            for w in wheels:
                assert w.short_hash in dump
            assert "not shown" not in dump
