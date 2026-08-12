"""
An exploration that transformed nothing must not report success.

The sibling of `test_pipeline_failure_visibility.py`, one layer down the
pathway chain. Same defect class, and here it lands squarely on the decision
ceremony: an `adopted_pathway` ground IS a Transformation, so a wheel that got
none can only ground a cost and never a recipe for living with it. A silent
"Exploration complete" therefore produces a half-record that reads as whole.

Three silent-success paths, all fixed:

1. `ExplorationPipeline.resolve` set `ok=True` unconditionally after the
   per-wheel gather and carried its `StepError`s home on `ExplorationResult`,
   which no tool renders.
2. `ExploreTransformations.resolve` only *logged* failed edge pairs, so a wheel
   whose every pair failed rendered as "0 new, 0 existing" with ok=True —
   indistinguishable from a wheel that was already fully transformed.
3. The same skill's no-edge-pairs early return left ok=True, telling the agent
   a structurally broken wheel had been deepened.

`ExecutionReport.ok` defaults to True, so in each case the failure had to be
asserted, not merely not-denied.

DB-free and LLM-free: the defect is in how the report is composed, so the
sub-skill and the graph steps are patched out.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.explorer.explorer import ExplorationPipeline


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _FakeReport:
    def __init__(self, ok: bool = True, summary: str = "") -> None:
        self.ok = ok
        self.summary = summary
        self.artifacts: dict = {}


class _FakeWheel:
    def __init__(self, hash_: str) -> None:
        self.hash = hash_
        self.short_hash = hash_[:7]


class _FakeBuildResult:
    def __init__(self, wheels: list[_FakeWheel]) -> None:
        self.new_cycles = [_FakeWheel("cyc1")]
        self.new_wheels = wheels


def _patch_build(monkeypatch, wheels: list[str]) -> None:
    class _FakeBuild:
        def __init__(self, **kwargs) -> None:
            self.report = _FakeReport(True, "built")

        async def resolve(self):
            return _FakeBuildResult([_FakeWheel(h) for h in wheels])

    monkeypatch.setattr(
        "dialectical_framework.agents.explorer.skills.build_wheels.BuildWheels",
        _FakeBuild,
    )


class _FakeTransition:
    def __init__(self, text: str) -> None:
        self.instruction = text
        self.summary = None


class _FakeManager:
    def __init__(self, transition=None) -> None:
        self._transition = transition

    def get(self):
        return (self._transition, None) if self._transition else None


class _FakeTransformation:
    """Only what `pathway_line` reads — a real one needs a committed wheel."""

    def __init__(self, hash_: str) -> None:
        self.hash = hash_
        self.short_hash = hash_
        self.edge = _FakeManager()
        self.ac_plus = _FakeManager(_FakeTransition(f"recipe for {hash_}"))
        self.re_plus = _FakeManager()


def _patch_transformations(monkeypatch, behaviour) -> None:
    """`behaviour(wheel_hash)` -> new-transformation count, or raises."""
    from dialectical_framework.agents.explorer.skills.explore_transformations \
        import ExploreTransformationsResult

    class _FakeExplore:
        def __init__(self, wheel_hash: str, **kwargs) -> None:
            self._wheel_hash = wheel_hash
            self.report = _FakeReport(True, "explored")

        async def resolve(self):
            count = behaviour(self._wheel_hash)
            # Hashes namespaced per wheel: the pipeline dedups across wheels, so
            # reusing "tr0" everywhere would make two wheels' pathways collapse
            # into one and hide a real double-count.
            return ExploreTransformationsResult(
                new=[
                    _FakeTransformation(f"{self._wheel_hash}-tr{i}")
                    for i in range(count)
                ]
            )

    monkeypatch.setattr(
        "dialectical_framework.agents.explorer.skills.explore_transformations."
        "ExploreTransformations",
        _FakeExplore,
    )


@pytest.mark.asyncio
async def test_pipeline_that_deepened_nothing_reports_failure(monkeypatch):
    """Every wheel's transformations raised -> the report must NOT say ok.

    Left ok=True, `explore` reports success over a graph with no pathway in
    it — and the decision ceremony that follows can only ground a cost.
    """
    _patch_build(monkeypatch, ["wh1", "wh2"])

    def boom(wheel_hash: str) -> int:
        raise RuntimeError("apex derivation timed out")

    _patch_transformations(monkeypatch, boom)

    pipeline = ExplorationPipeline(nexus_hash="nx1")
    await pipeline.resolve()

    assert pipeline.report.ok is False
    assert "FAILED to deepen" in pipeline.report.summary
    assert "apex derivation timed out" in str(pipeline.report)
    assert pipeline.report.artifacts["errors"]


@pytest.mark.asyncio
async def test_partial_deepening_reports_ok_but_names_the_loss(monkeypatch):
    """One wheel deepened, one failed: usable result, visible loss."""
    _patch_build(monkeypatch, ["wh1", "wh2"])

    def half(wheel_hash: str) -> int:
        if wheel_hash == "wh1":
            return 2
        raise RuntimeError("second wheel timed out")

    _patch_transformations(monkeypatch, half)

    pipeline = ExplorationPipeline(nexus_hash="nx1")
    await pipeline.resolve()

    assert pipeline.report.ok is True, "A partial result is still a result"
    assert "1 wheel(s) FAILED to deepen" in pipeline.report.summary
    assert "second wheel timed out" in str(pipeline.report)


@pytest.mark.asyncio
async def test_successful_exploration_still_reports_ok(monkeypatch):
    """The guard must not flip healthy runs."""
    _patch_build(monkeypatch, ["wh1"])
    _patch_transformations(monkeypatch, lambda wheel_hash: 4)

    pipeline = ExplorationPipeline(nexus_hash="nx1")
    await pipeline.resolve()

    assert pipeline.report.ok is True
    assert "FAILED" not in pipeline.report.summary
    assert "errors" not in pipeline.report.artifacts


@pytest.mark.asyncio
async def test_zero_transformations_without_errors_is_still_ok(monkeypatch):
    """"Nothing new to add" is a real success, not a failure.

    Every transformation already existing is the common re-run case; failing it
    would be the opposite error and would make `deepen` unusable as an idempotent
    call.
    """
    _patch_build(monkeypatch, ["wh1"])
    _patch_transformations(monkeypatch, lambda wheel_hash: 0)

    pipeline = ExplorationPipeline(nexus_hash="nx1")
    await pipeline.resolve()

    assert pipeline.report.ok is True
    assert "FAILED" not in pipeline.report.summary


class TestExploreTransformationsSkill:
    """The sub-skill's own two silent paths.

    Driven by calling the failure branches directly rather than through a real
    Wheel: the defect is entirely in report composition, and building a
    committed 2-PP wheel here would need the DB and the LLM.
    """

    @staticmethod
    def _skill():
        from dialectical_framework.agents.explorer.skills.explore_transformations \
            import ExploreTransformations

        return ExploreTransformations(wheel_hash="wh1")

    @pytest.mark.asyncio
    async def test_no_edge_pairs_is_not_ok(self, monkeypatch):
        """A wheel with no edge pairs is malformed, not already-complete."""
        skill = self._skill()
        monkeypatch.setattr(skill, "_resolve_wheel", lambda: _FakeWheel("wh1abcd"))
        monkeypatch.setattr(
            skill, "_resolve_nexus", lambda wheel: _FakeWheel("nx1abcd")
        )
        monkeypatch.setattr(skill, "_get_target_edge_pairs", lambda wheel: [])

        await skill.resolve()

        assert skill.report.ok is False
        assert "nothing could be transformed" in skill.report.summary

    @pytest.mark.asyncio
    async def test_all_edge_pairs_failing_is_not_ok(self, monkeypatch):
        """Failed pairs were only logged, so the report said "0 new, 0 existing".

        That is the same text a fully-transformed wheel produces — the agent
        could not tell "already done" from "everything broke".
        """
        skill = self._skill()
        monkeypatch.setattr(skill, "_resolve_wheel", lambda: _FakeWheel("wh1abcd"))
        monkeypatch.setattr(
            skill, "_resolve_nexus", lambda wheel: _FakeWheel("nx1abcd")
        )
        monkeypatch.setattr(
            skill, "_get_target_edge_pairs", lambda wheel: [("ea", "eb")]
        )

        async def _no_input():
            return "some input"

        monkeypatch.setattr(skill, "_get_input_text", _no_input)

        async def boom(*args, **kwargs):
            raise RuntimeError("aspect pair generation failed")

        monkeypatch.setattr(skill, "_process_edge_pair", boom)

        await skill.resolve()

        assert skill.report.ok is False
        assert "edge pair(s) FAILED" in skill.report.summary
        assert "aspect pair generation failed" in str(skill.report)

    @pytest.mark.asyncio
    async def test_partial_edge_pair_failure_stays_ok(self, monkeypatch):
        """Transformations that WERE built are real and the agent should use them."""
        skill = self._skill()
        monkeypatch.setattr(skill, "_resolve_wheel", lambda: _FakeWheel("wh1abcd"))
        monkeypatch.setattr(
            skill, "_resolve_nexus", lambda wheel: _FakeWheel("nx1abcd")
        )
        monkeypatch.setattr(
            skill,
            "_get_target_edge_pairs",
            lambda wheel: [("ea", "eb"), ("ec", "ed")],
        )

        async def _input():
            return "some input"

        monkeypatch.setattr(skill, "_get_input_text", _input)

        calls = {"n": 0}

        async def half(wheel, nexus, edge_a, edge_b, input_text):
            calls["n"] += 1
            if calls["n"] == 1:
                return ([], ["existing-transformation"], None)
            raise RuntimeError("second pair failed")

        monkeypatch.setattr(skill, "_process_edge_pair", half)

        await skill.resolve()

        assert skill.report.ok is True
        assert "1 edge pair(s) FAILED" in skill.report.summary


class TestPipelineNamesThePathwaysItBuilt:
    """A count is not a ground.

    `adopted_pathway` takes a Transformation hash, and the pipeline reported
    `transformation_count` and nothing else — so a model told "12
    transformations" had no hash to pass. Measured in `claim2-weak-r10`: 0/6
    decisions carried an adopted pathway, INCLUDING cells that called `explore`
    themselves. Unlike `explore` itself (an election failure fixed by a code
    seam), this one was never electable: the ground did not exist in the output.
    """

    @pytest.mark.asyncio
    async def test_pathways_carry_hash_and_recipe(self, monkeypatch):
        _patch_build(monkeypatch, ["wh1"])
        _patch_transformations(monkeypatch, lambda wheel_hash: 2)

        pipeline = ExplorationPipeline(nexus_hash="nx1")
        result = await pipeline.resolve()

        assert result.transformation_hashes == ["wh1-tr0", "wh1-tr1"]
        rendered = str(pipeline.report)
        assert "wh1-tr0" in rendered
        assert "recipe for wh1-tr0" in rendered, (
            "A hash with no recipe is not pickable — the model has to know "
            "WHICH pathway it is adopting."
        )

    @pytest.mark.asyncio
    async def test_reused_transformations_count_as_pathways(self, monkeypatch):
        """A wheel sharing edge pairs with an already-deepened one reuses every
        transformation. Reading `.new` reports zero pathways for a wheel that is
        fully developed — and then says so to the model at the closing turn."""
        from dialectical_framework.agents.explorer.skills.explore_transformations \
            import ExploreTransformationsResult

        _patch_build(monkeypatch, ["wh1"])

        class _AllExisting:
            def __init__(self, wheel_hash: str, **kwargs) -> None:
                self.report = _FakeReport(True, "explored")

            async def resolve(self):
                return ExploreTransformationsResult(
                    existing=[_FakeTransformation("shared-tr")]
                )

        monkeypatch.setattr(
            "dialectical_framework.agents.explorer.skills."
            "explore_transformations.ExploreTransformations",
            _AllExisting,
        )

        pipeline = ExplorationPipeline(nexus_hash="nx1")
        result = await pipeline.resolve()

        assert result.transformation_hashes == ["shared-tr"]
        assert result.transformation_count == 1
        assert "1 transformations" in pipeline.report.summary

    @pytest.mark.asyncio
    async def test_a_shared_pathway_is_listed_once(self, monkeypatch):
        """Opposite-edge transformations are shared across wheels with the same
        edge pairs; the same hash twice reads as two distinct recipes."""
        from dialectical_framework.agents.explorer.skills.explore_transformations \
            import ExploreTransformationsResult

        _patch_build(monkeypatch, ["wh1", "wh2"])

        class _Shared:
            def __init__(self, wheel_hash: str, **kwargs) -> None:
                self.report = _FakeReport(True, "explored")

            async def resolve(self):
                return ExploreTransformationsResult(
                    new=[_FakeTransformation("shared-tr")]
                )

        monkeypatch.setattr(
            "dialectical_framework.agents.explorer.skills."
            "explore_transformations.ExploreTransformations",
            _Shared,
        )

        pipeline = ExplorationPipeline(nexus_hash="nx1")
        result = await pipeline.resolve()

        assert result.transformation_hashes == ["shared-tr"]
        # The reference form, not the bare hash — the recipe text repeats it.
        assert str(pipeline.report).count("[[shared-tr]]") == 1
        assert len(pipeline.report.artifacts["pathways"]) == 1

    @pytest.mark.asyncio
    async def test_no_pathways_key_when_nothing_was_built(self, monkeypatch):
        """An empty list reads as an empty menu, not as "none exist yet"."""
        _patch_build(monkeypatch, ["wh1"])
        _patch_transformations(monkeypatch, lambda wheel_hash: 0)

        pipeline = ExplorationPipeline(nexus_hash="nx1")
        await pipeline.resolve()

        assert "pathways" not in pipeline.report.artifacts
