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


class _FakeCycle:
    def __init__(self, perspective_hashes: list[str]) -> None:
        self.perspective_hashes = perspective_hashes


def _nexus_of(pairs, monkeypatch):
    """Point both repositories at a hand-built nexus of (pp set, wheel) pairs.

    `_plan_rungs` reads exactly two things from the graph — that the nexus resolves,
    and every wheel under it WITH its perspective set — so those are the two seams
    stubbed here. The chain logic itself is set arithmetic and stays in the open.
    """
    from dialectical_framework.graph.repositories.nexus_repository import \
        NexusRepository
    from dialectical_framework.graph.repositories.wheel_repository import \
        WheelRepository

    sentinel = object()
    monkeypatch.setattr(
        NexusRepository, "find_by_hash_prefix", lambda self, h: sentinel
    )
    monkeypatch.setattr(
        WheelRepository,
        "find_by_nexus",
        lambda self, nexus: [
            (_FakeCycle(list(pps)), wheel) for pps, wheel in pairs
        ],
    )


class TestPlanRungs:
    """The climb: a deepened wheel needs its coarser ancestry deepened FIRST.

    Every Transformation is generated against the coarser Transformations its edge
    descends from. Those have to already be in the graph when the finer wheel's
    generation reads for them, so "which wheels" is not the whole policy — the ORDER
    is half of it, and a rung that runs alongside the wheel it should be refining is
    a rung that may as well not have run.
    """

    def _pipeline(self, climb: bool = True) -> ExplorationPipeline:
        return ExplorationPipeline(
            nexus_hash="deadbee", max_deep_wheels=1, refine_from_coarser=climb
        )

    def test_off_is_one_rung(self, monkeypatch):
        """The single gather the caller used to do, unchanged."""
        pairs = [(("a", "b"), _FakeWheel("top", 0.9))]
        _nexus_of(pairs, monkeypatch)
        assert self._pipeline(climb=False)._plan_rungs(["top"]) == [(0, ["top"])]

    def test_one_ancestor_per_layer_coarsest_first(self, monkeypatch):
        pairs = [
            (("a", "b", "c"), _FakeWheel("top", 0.5, polarity_count=3)),
            (("a", "b"), _FakeWheel("mid", 0.5, polarity_count=2)),
            (("a",), _FakeWheel("low", 0.5, polarity_count=1)),
        ]
        _nexus_of(pairs, monkeypatch)
        assert self._pipeline()._plan_rungs(["top"]) == [
            (1, ["low"]),
            (2, ["mid"]),
            (3, ["top"]),
        ]

    def test_the_chain_is_nested_not_best_per_layer(self, monkeypatch):
        """`ab` is the more plausible layer-2 wheel and is still the wrong rung.

        `find_parent_transformations` enumerates combinations of the ASKING wheel's
        perspectives and keeps coarser wheels whose set is a SUBSET, so the layer-1
        rung has to sit inside the layer-2 rung. Picking each layer's best
        independently would put `ab` (P 0.9) under the top wheel and `c` (the only
        layer-1 wheel) under nothing — a two-rung climb where the bottom rung
        refines neither wheel above it.
        """
        pairs = [
            (("a", "b", "c"), _FakeWheel("top", 0.5, polarity_count=3)),
            (("a", "b"), _FakeWheel("ab", 0.9, polarity_count=2)),
            (("b", "c"), _FakeWheel("bc", 0.1, polarity_count=2)),
            (("c",), _FakeWheel("c", 0.5, polarity_count=1)),
        ]
        _nexus_of(pairs, monkeypatch)
        plan = self._pipeline()._plan_rungs(["top"])
        assert plan == [(1, ["c"]), (2, ["bc"]), (3, ["top"])], (
            "the layer-1 wheel `c` is only inside `bc`, so choosing `ab` on"
            " plausibility strands it — the chain must stay nested"
        )

    def test_probability_breaks_the_tie_among_true_ancestors(self, monkeypatch):
        pairs = [
            (("a", "b", "c"), _FakeWheel("top", 0.5, polarity_count=3)),
            (("a", "b"), _FakeWheel("dull", 0.1, polarity_count=2)),
            (("a", "c"), _FakeWheel("likely", 0.8, polarity_count=2)),
        ]
        _nexus_of(pairs, monkeypatch)
        plan = self._pipeline()._plan_rungs(["top"])
        assert plan[0][1] == ["likely"]

    def test_a_gap_in_the_ancestry_stops_the_climb(self, monkeypatch):
        """No layer-2 wheel exists, so there is nothing to descend THROUGH.

        Reaching past the gap to a layer-1 wheel would deepen a rung the top wheel
        can reach (any subset of its own PPs) — but the point of stopping is that
        the walk is transitive: it is built by chaining parent to parent, and a
        missing middle is a chain that does not connect.
        """
        pairs = [
            (("a", "b", "c"), _FakeWheel("top", 0.5, polarity_count=3)),
            (("a",), _FakeWheel("low", 0.9, polarity_count=1)),
        ]
        _nexus_of(pairs, monkeypatch)
        assert self._pipeline()._plan_rungs(["top"]) == [(3, ["top"])]

    def test_a_shared_ancestor_is_deepened_once(self, monkeypatch):
        pairs = [
            (("a", "b"), _FakeWheel("t1", 0.5, polarity_count=2)),
            (("a", "c"), _FakeWheel("t2", 0.5, polarity_count=2)),
            (("a",), _FakeWheel("shared", 0.5, polarity_count=1)),
        ]
        _nexus_of(pairs, monkeypatch)
        plan = self._pipeline()._plan_rungs(["t1", "t2"])
        assert plan == [(1, ["shared"]), (2, ["t1", "t2"])]

    def test_a_target_that_is_another_targets_ancestor_runs_first(
        self, monkeypatch
    ):
        """Two targets at different layers cannot share a rung.

        Deepening them together is the same race the barrier exists to remove — the
        coarser target IS the finer one's ancestry.
        """
        pairs = [
            (("a", "b"), _FakeWheel("fine", 0.5, polarity_count=2)),
            (("a",), _FakeWheel("coarse", 0.5, polarity_count=1)),
        ]
        _nexus_of(pairs, monkeypatch)
        assert self._pipeline()._plan_rungs(["fine", "coarse"]) == [
            (1, ["coarse"]),
            (2, ["fine"]),
        ]

    def test_a_wheel_with_no_perspective_set_is_still_deepened(self, monkeypatch):
        """Soft, and LAST: it keeps its transformations, just not a claimed ancestry.

        A wheel the nexus read does not cover has no set to descend from, and
        dropping it would turn a missing edge into a silently unexplored wheel.
        """
        pairs = [(("a", "b"), _FakeWheel("known", 0.5))]
        _nexus_of(pairs, monkeypatch)
        plan = self._pipeline()._plan_rungs(["known", "stranger"])
        assert plan == [(2, ["known"]), (0, ["stranger"])]

    def test_an_unresolvable_nexus_degrades_to_no_climb(self, monkeypatch):
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        monkeypatch.setattr(
            NexusRepository, "find_by_hash_prefix", lambda self, h: None
        )
        assert self._pipeline()._plan_rungs(["top"]) == [(0, ["top"])]


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
    """run_exploration applies the depth budget and syntheses ONLY the
    deepened wheels."""

    def test_advisor_policy_deepens_one(self):
        """Explore's eager deepening is fixed policy (top-1), not a setting;
        the integer pipeline seam stays generic underneath."""
        from dialectical_framework.agents.advisor.tools.explore import (
            EXPLORE_DEEP_WHEELS, _ExploreBudget)

        assert EXPLORE_DEEP_WHEELS == 1
        assert _ExploreBudget().deep_wheels == 1

    def test_advisor_policy_climbs_from_the_coarser_wheels(self):
        """The one deepened wheel is deepened ON TOP of its ancestry.

        Also fixed policy, and not a cheaper/richer dial: off, the refinement
        recursion has no parent Transformations to find, so the deepest arrangement
        is the one generated with no coarser context at all (measured at k=4 as 0 of
        8 parent lookups finding anything, against 18 of 20 with it on).
        """
        from dialectical_framework.agents.advisor.tools.explore import (
            EXPLORE_REFINE_FROM_COARSER, _ExploreBudget)

        assert EXPLORE_REFINE_FROM_COARSER is True
        assert _ExploreBudget().refine_from_coarser is True

    async def test_synthesis_follows_deepened_only(self, monkeypatch):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration
        from dialectical_framework.agents.explorer import explorer as exp_mod
        from dialectical_framework.agents.explorer.skills import \
            generate_synthesis as gs_mod
        from dialectical_framework.concerns import expand_nexus as en_mod

        captured_cap: list = []
        # The constant test above proves the policy's VALUE; this proves it reaches
        # the pipeline. A budget property nothing passes on is a policy that is off.
        captured_climb: list = []

        async def stub_pipeline_resolve(self):
            captured_cap.append(self.max_deep_wheels)
            captured_climb.append(self.refine_from_coarser)
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
        assert captured_climb == [True]
        assert synthesized == ["top4444"]
        assert "shallow_wheel_hashes" in report_str
