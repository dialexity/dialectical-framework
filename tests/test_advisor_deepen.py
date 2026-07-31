"""
Tests for the Advisor's deepen tool (on-demand wheel development).

`explore` deepens only the top-plausibility wheel (budget); `deepen` is the
follow-up when the person's lived reality picks a reading whose pathways
don't exist yet. One composed call: transformations then synthesis (always —
a deepened wheel without S+/S- is structurally unfinished), sequencing
absorbed in code.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.llm


@pytest.fixture
def stubs(monkeypatch):
    from dialectical_framework.agents.explorer.skills import \
        explore_transformations as et_mod
    from dialectical_framework.agents.explorer.skills import \
        generate_synthesis as gs_mod

    calls: dict = {"transformations": [], "synthesis": []}

    async def stub_transformations(self):
        calls["transformations"].append(self.wheel_hash)

        class _R:
            new: list = []

        return _R()

    async def stub_synthesis(self):
        calls["synthesis"].append(self.wheel_hash)
        return None

    monkeypatch.setattr(
        et_mod.ExploreTransformations, "resolve", stub_transformations
    )
    monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)
    return calls


class TestRunDeepen:
    async def test_generates_transformations_then_synthesis(self, stubs):
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen

        report = await run_deepen("wheel444")

        assert stubs["transformations"] == ["wheel444"]
        assert stubs["synthesis"] == ["wheel444"]
        assert "wheel444" in report

    async def test_synthesis_failure_is_soft_and_reported(
        self, monkeypatch, stubs
    ):
        """A wheel that can't synthesize (e.g. no transformations produced)
        still returns the transformation report, with the skip noted."""
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen
        from dialectical_framework.agents.explorer.skills import \
            generate_synthesis as gs_mod

        async def broken_synthesis(self):
            raise ValueError("no transformations yet")

        monkeypatch.setattr(
            gs_mod.GenerateSynthesis, "resolve", broken_synthesis
        )

        report = await run_deepen("wheel444")

        assert stubs["transformations"] == ["wheel444"]
        assert "synthesis_skipped" in report

    async def test_transformation_failure_propagates(self, monkeypatch):
        """Unlike synthesis, a transformations failure is the whole call
        failing — surface it to the tool layer (Mirascope turns raised
        exceptions into error tool-outputs)."""
        from dialectical_framework.agents.advisor.tools.deepen import \
            run_deepen
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod

        async def broken(self):
            raise ValueError("Wheel not found: wheel444")

        monkeypatch.setattr(et_mod.ExploreTransformations, "resolve", broken)

        with pytest.raises(ValueError, match="Wheel not found"):
            await run_deepen("wheel444")


class TestDeepenPromptWiring:
    def test_default_render_documents_deepen(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        p = " ".join(SYSTEM_PROMPT.split())
        assert "`deepen`" in p
        # the decision point: lived reality over plausibility score
        assert "lived reality outranks the plausibility score" in p or (
            "reality outranks the plausibility score" in p
        )

    def test_scoped_render_documents_deepen_without_consent_ceremony(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        p = " ".join(
            system_prompt(
                tool_names=[
                    "anchor", "sync", "inspect_node", "read_digest",
                    "discard", "explore", "deepen",
                ],
                scoped_nexus_hash="abc1234",
            ).split()
        )
        assert "`deepen`" in p
        # deepening adds depth, doesn't change contents — no consent needed
        assert "never changes what the exploration contains" in p
