"""
Tests for the silent-explore depth budget (task #8).

"Rich vs simple" exploration is a runtime budget, not a schema concept:
settings.advisor_explore_deepen flags eager top-1 deepening (delivered by
task #2; off = fully reactive via the deepen tool),
advisor_explore_perspectives caps perspectives woven per call (excess is
deferred, reported, never dropped), advisor_explore_synthesis toggles S+/S-.
The Explorer agent path is user-driven and ignores all of these.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from dialectical_framework.agents.explorer.explorer import ExplorationResult

pytestmark = pytest.mark.llm


@contextmanager
def _settings(di_container, **overrides):
    current = di_container.settings()
    di_container.settings.override(current.model_copy(update=overrides))
    try:
        yield
    finally:
        di_container.settings.reset_override()
        di_container.settings.override(current)


@pytest.fixture
def stubs(monkeypatch):
    """Stub the pipeline stages; record what each receives."""
    from dialectical_framework.agents.explorer import explorer as exp_mod
    from dialectical_framework.agents.explorer.skills import \
        generate_synthesis as gs_mod
    from dialectical_framework.concerns import expand_nexus as en_mod

    calls: dict = {"expand": [], "pipeline": [], "synthesis": []}

    async def stub_expand(self, nexus_hash, perspective_hashes):
        calls["expand"].append(list(perspective_hashes))
        return None

    async def stub_pipeline_resolve(self):
        calls["pipeline"].append(self.max_deep_wheels)
        return ExplorationResult(
            nexus_hash=self.nexus_hash,
            wheel_hashes=["top4444", "low4444"],
            deepened_wheel_hashes=["top4444"],
        )

    async def stub_synthesis(self):
        calls["synthesis"].append(self.wheel_hash)
        return None

    monkeypatch.setattr(en_mod.ExpandNexus, "resolve", stub_expand)
    monkeypatch.setattr(
        exp_mod.ExplorationPipeline, "resolve", stub_pipeline_resolve
    )
    monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)
    return calls


class TestExploreBudget:
    async def test_perspective_cap_defers_excess(self, di_container, stubs):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_perspectives=2):
            report = await run_exploration(
                ["pp1", "pp2", "pp3", "pp4"], intent="", nexus_hash="deadbee"
            )

        # only the first two woven this call
        assert stubs["expand"] == [["pp1", "pp2"]]
        # the rest deferred and reported, never dropped
        assert "deferred_perspective_hashes" in report
        assert "pp3" in report and "pp4" in report
        assert "call explore again" in report

    async def test_under_cap_weaves_all_no_deferral(self, di_container, stubs):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_perspectives=2):
            report = await run_exploration(
                ["pp1", "pp2"], intent="", nexus_hash="deadbee"
            )

        assert stubs["expand"] == [["pp1", "pp2"]]
        assert "deferred_perspective_hashes" not in report

    async def test_zero_cap_unlimited(self, di_container, stubs):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_perspectives=0):
            report = await run_exploration(
                ["pp1", "pp2", "pp3"], intent="", nexus_hash="deadbee"
            )

        assert stubs["expand"] == [["pp1", "pp2", "pp3"]]
        assert "deferred_perspective_hashes" not in report

    async def test_deepen_flag_on_reaches_pipeline_as_one(
        self, di_container, stubs
    ):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_deepen=True):
            await run_exploration(["pp1"], intent="", nexus_hash="deadbee")

        assert stubs["pipeline"] == [1]

    async def test_deepen_flag_off_reaches_pipeline_as_zero(
        self, di_container, stubs
    ):
        """False = fully reactive: build + rank only; the deepen tool is the
        sole pathway generator."""
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_deepen=False):
            await run_exploration(["pp1"], intent="", nexus_hash="deadbee")

        assert stubs["pipeline"] == [0]

    async def test_synthesis_toggle_off(self, di_container, stubs):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_synthesis=False):
            report = await run_exploration(
                ["pp1"], intent="", nexus_hash="deadbee"
            )

        assert stubs["synthesis"] == []
        assert '"synthesis_generated": 0' in report

    async def test_synthesis_on_follows_deepened_only(
        self, di_container, stubs
    ):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_explore_synthesis=True):
            await run_exploration(["pp1"], intent="", nexus_hash="deadbee")

        assert stubs["synthesis"] == ["top4444"]


class TestExplorerPathUnaffected:
    def test_explorer_agent_pipeline_has_no_budget(self):
        """The Explorer's LLM-facing explore tool constructs the pipeline
        without a deep-wheel cap — the user selects wheels there."""
        import inspect

        from dialectical_framework.agents.explorer import explorer as exp_mod

        src = inspect.getsource(exp_mod.explore)
        assert "max_deep_wheels" not in src
        assert "advisor_" not in src
