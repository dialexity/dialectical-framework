"""
Tests for the silent-explore depth budget (task #8).

"Rich vs simple" exploration is a runtime budget, not a schema concept:
explore always deepens exactly the top-plausibility wheel (fixed policy,
EXPLORE_DEEP_WHEELS = 1; the deepen tool develops any other on demand) and
always finishes it with synthesis; advisor_max_perspectives_per_exploration
caps perspectives woven per call (excess is deferred, reported, never
dropped). The Explorer agent path is user-driven and ignores all of these.
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

        with _settings(di_container, advisor_max_perspectives_per_exploration=2):
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

        with _settings(di_container, advisor_max_perspectives_per_exploration=2):
            report = await run_exploration(
                ["pp1", "pp2"], intent="", nexus_hash="deadbee"
            )

        assert stubs["expand"] == [["pp1", "pp2"]]
        assert "deferred_perspective_hashes" not in report

    async def test_zero_cap_unlimited(self, di_container, stubs):
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        with _settings(di_container, advisor_max_perspectives_per_exploration=0):
            report = await run_exploration(
                ["pp1", "pp2", "pp3"], intent="", nexus_hash="deadbee"
            )

        assert stubs["expand"] == [["pp1", "pp2", "pp3"]]
        assert "deferred_perspective_hashes" not in report

    async def test_explore_always_deepens_exactly_one(self, stubs):
        """Fixed policy, not a setting: the pipeline gets max_deep_wheels=1
        on every silent explore call."""
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        await run_exploration(["pp1"], intent="", nexus_hash="deadbee")

        assert stubs["pipeline"] == [1]

    async def test_synthesis_always_follows_deepened_only(self, stubs):
        """Synthesis is unconditional for deepened wheels (a deepened wheel
        without S+/S- is structurally unfinished) — and only for them."""
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration

        await run_exploration(["pp1"], intent="", nexus_hash="deadbee")

        assert stubs["synthesis"] == ["top4444"]


class TestExplorerPathUnaffected:
    """The Explorer is lazy by TOOLSET, and that is what has to be pinned.

    This class used to read the source of an `explore` tool in `explorer.py` and
    assert it set no cap — treating "uncapped" as the Explorer's correct policy
    because the user picks wheels there. The tool was in no toolset, so the
    assertion described a path no agent could take, and the belief it encoded was
    the dangerous one: uncapped means deepen EVERY wheel, and the wheel count is
    combinatorial. Measured with the LLM mocked, k=4's 96 wheels had not finished
    after 41 minutes (`tests/probe_explore_deep_wheels.py`). The tool is gone.

    What makes the Explorer lazy is that it never reaches `ExplorationPipeline`
    at all: it builds structure with `build_wheels` and deepens the wheel the user
    named with `explore_transformations`. Pin THAT, so wiring a whole-pipeline
    tool into this toolset has to argue with a test.
    """

    def test_explorer_deepens_per_wheel_and_not_by_pipeline(self):
        from dialectical_framework.agents.explorer.explorer import _build_tools

        names = {getattr(t, "__name__", None) for t in _build_tools()}
        assert {"build_wheels", "explore_transformations"} <= names, (
            "the Explorer's lazy depth IS these two tools — structure for all"
            " wheels, transformations for the one the user picked"
        )

    def test_no_explorer_tool_runs_the_whole_pipeline(self):
        """No Explorer tool may construct `ExplorationPipeline`.

        Source-level on purpose: the cost is in what the tool CALLS, and calling
        it here would need a committed Nexus plus a full transformation run per
        wheel — which is the very thing that does not return.
        """
        import inspect

        from dialectical_framework.agents.explorer.explorer import _build_tools

        for tool in _build_tools():
            try:
                src = inspect.getsource(tool)
            except (OSError, TypeError):  # closures over C-level wrappers
                continue
            assert "ExplorationPipeline" not in src, (
                f"{getattr(tool, '__name__', tool)} runs the whole exploration"
                " pipeline. Uncapped that deepens every wheel built"
                " (96 at k=4, measured as not returning in 41 minutes with the"
                " LLM mocked); the Explorer's contract is per-wheel deepening"
                " on the user's pick. If an agent really needs the pipeline in"
                " one call, give the tool a cap in its own signature."
            )
