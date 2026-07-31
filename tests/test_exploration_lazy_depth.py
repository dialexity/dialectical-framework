"""
Tests for the lazy-depth exploration seam (task #2).

ExplorationPipeline.max_deep_wheels caps the expensive stage: ALL wheels are
built + estimated (structural), but only the top-plausibility wheels (deepest
layer first, then highest causality P) get transformations. The Advisor's
explore path pins the cap at MAX_DEEP_WHEELS = 1 and generates synthesis only
for the deepened wheels; the Explorer agent path never sets the cap.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.explorer.explorer import (
    ExplorationPipeline, ExplorationResult)


class _FakeEstimations:
    def __init__(self, probability):
        self._probability = probability

    def all(self):
        from dialectical_framework.graph.nodes.estimation import \
            CausalityProbabilityEstimation

        if self._probability is None:
            return []
        est = CausalityProbabilityEstimation(value=self._probability)
        return [(est, None)]


class _FakeWheel:
    """Duck-typed wheel: exactly what _select_deep_wheels touches."""

    def __init__(self, hash: str, probability=None, polarity_count: int = 2):
        self.hash = hash
        self.estimations = _FakeEstimations(probability)
        self._polarity_count = polarity_count

    @property
    def polarity_count(self) -> int:
        if self._polarity_count < 0:
            raise ValueError("incomplete wheel")
        return self._polarity_count


class TestSelectDeepWheels:
    def _pipeline(self, cap) -> ExplorationPipeline:
        return ExplorationPipeline(nexus_hash="deadbee", max_deep_wheels=cap)

    def test_no_cap_deepens_all(self):
        wheels = [_FakeWheel("w1", 0.2), _FakeWheel("w2", 0.9)]
        assert self._pipeline(None)._select_deep_wheels(wheels) == ["w1", "w2"]

    def test_cap_larger_than_set_deepens_all(self):
        wheels = [_FakeWheel("w1", 0.2), _FakeWheel("w2", 0.9)]
        assert self._pipeline(5)._select_deep_wheels(wheels) == ["w1", "w2"]

    def test_top_probability_wins_within_layer(self):
        wheels = [
            _FakeWheel("low", 0.2),
            _FakeWheel("top", 0.9),
            _FakeWheel("mid", 0.5),
        ]
        assert self._pipeline(1)._select_deep_wheels(wheels) == ["top"]
        assert self._pipeline(2)._select_deep_wheels(wheels) == ["top", "mid"]

    def test_deeper_layer_beats_probability(self):
        """A 2-PP wheel outranks a more-probable 1-PP wheel — layers don't
        compete on P (different denominators); depth wins."""
        wheels = [
            _FakeWheel("single", 0.95, polarity_count=1),
            _FakeWheel("double", 0.3, polarity_count=2),
        ]
        assert self._pipeline(1)._select_deep_wheels(wheels) == ["double"]

    def test_unestimated_ranks_last_within_layer(self):
        wheels = [
            _FakeWheel("unscored", None),
            _FakeWheel("scored", 0.1),
        ]
        assert self._pipeline(1)._select_deep_wheels(wheels) == ["scored"]

    def test_zero_cap_deepens_nothing(self):
        wheels = [_FakeWheel("w1", 0.9)]
        assert self._pipeline(0)._select_deep_wheels(wheels) == []

    def test_broken_polarity_count_is_soft(self):
        wheels = [
            _FakeWheel("broken", 0.9, polarity_count=-1),
            _FakeWheel("fine", 0.1, polarity_count=2),
        ]
        assert self._pipeline(1)._select_deep_wheels(wheels) == ["fine"]


@pytest.mark.llm
class TestPipelineHonorsCap:
    """Pipeline-level: only selected wheels reach ExploreTransformations."""

    async def _run(self, monkeypatch, cap):
        from dialectical_framework.agents.explorer.skills import build_wheels
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        wheels = [
            _FakeWheel("top4444", 0.9),
            _FakeWheel("mid4444", 0.5),
            _FakeWheel("low4444", 0.2),
        ]

        async def stub_build(self):
            return build_wheels.BuildWheelsResult(
                nexus=None, new_cycles=[], new_wheels=wheels
            )

        monkeypatch.setattr(build_wheels.BuildWheels, "resolve", stub_build)

        explored: list[str] = []

        class _StubResult:
            new: list = []

        async def stub_explore(self):
            explored.append(self.wheel_hash)
            return _StubResult()

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", stub_explore
        )

        pipeline = ExplorationPipeline(
            nexus_hash="deadbee", max_deep_wheels=cap
        )
        result = await pipeline.resolve()
        return explored, result

    async def test_cap_one_explores_only_top(self, monkeypatch):
        explored, result = await self._run(monkeypatch, cap=1)
        assert explored == ["top4444"]
        assert result.deepened_wheel_hashes == ["top4444"]
        # ALL wheels are still reported as built.
        assert set(result.wheel_hashes) == {"top4444", "mid4444", "low4444"}

    async def test_no_cap_explores_all(self, monkeypatch):
        explored, result = await self._run(monkeypatch, cap=None)
        assert set(explored) == {"top4444", "mid4444", "low4444"}
        assert set(result.deepened_wheel_hashes) == set(result.wheel_hashes)

    async def test_summary_mentions_lazy_split(self, monkeypatch):
        from dialectical_framework.agents.explorer.skills import build_wheels
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        wheels = [_FakeWheel("top4444", 0.9), _FakeWheel("low4444", 0.2)]

        async def stub_build(self):
            return build_wheels.BuildWheelsResult(
                nexus=None, new_cycles=[], new_wheels=wheels
            )

        class _StubResult:
            new: list = []

        async def stub_explore(self):
            return _StubResult()

        monkeypatch.setattr(build_wheels.BuildWheels, "resolve", stub_build)
        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", stub_explore
        )

        pipeline = ExplorationPipeline(nexus_hash="deadbee", max_deep_wheels=1)
        await pipeline.resolve()
        assert "not deepened" in pipeline.report.summary
        assert pipeline.report.artifacts["deepened_wheel_hashes"] == ["top4444"]


@pytest.mark.llm
class TestAdvisorExploreIsLazy:
    """run_exploration pins the cap and syntheses ONLY the deepened wheels."""

    def test_advisor_cap_is_one(self):
        from dialectical_framework.agents.advisor.tools.explore import \
            MAX_DEEP_WHEELS

        assert MAX_DEEP_WHEELS == 1

    async def test_synthesis_follows_deepened_only(self, monkeypatch):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration
        from dialectical_framework.agents.explorer import explorer as exp_mod
        from dialectical_framework.agents.explorer.skills import \
            generate_synthesis as gs_mod
        from dialectical_framework.concerns import expand_nexus as en_mod

        captured_cap: list = []

        async def stub_pipeline_resolve(self):
            captured_cap.append(self.max_deep_wheels)
            return ExplorationResult(
                nexus_hash=self.nexus_hash,
                wheel_hashes=["top4444", "mid4444", "low4444"],
                deepened_wheel_hashes=["top4444"],
            )

        monkeypatch.setattr(
            exp_mod.ExplorationPipeline, "resolve", stub_pipeline_resolve
        )

        async def stub_expand(self, nexus_hash, perspective_hashes):
            return None

        monkeypatch.setattr(en_mod.ExpandNexus, "resolve", stub_expand)

        synthesized: list[str] = []

        async def stub_synthesis(self):
            synthesized.append(self.wheel_hash)
            return None

        monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)

        report_str = await run_exploration(
            ["pp1"], intent="", nexus_hash="deadbee"
        )

        assert captured_cap == [1]
        assert synthesized == ["top4444"]
        assert "shallow_wheel_hashes" in report_str
