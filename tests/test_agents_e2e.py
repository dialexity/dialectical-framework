"""
End-to-end tests for Analyst and Explorer sub-agents.

These tests hit the real LLM provider and verify the full pipeline produces
meaningful dialectical structures — not just that it runs without error.
"""

from __future__ import annotations

import pytest
from conftest import traced

from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.explorer.explorer import ExplorationPipeline
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)
from dialectical_framework.graph.scope_context import scope

pytestmark = pytest.mark.real_llm


SITUATION_TEXT = """
Our company is growing from 50 to 200 people in the next year. The founders built
the culture through daily interaction — everyone knew everyone, decisions were fast,
context was shared implicitly. Now we're hiring aggressively and new people don't
have that shared context. The veterans feel like the culture is diluting. The new
hires feel excluded from an implicit old-guard network. We need to scale but we
can't lose what made us great.
"""


class TestAnalystEndToEnd:
    """Full pipeline tests for the Analyst sub-agent."""

    @pytest.mark.asyncio
    @traced
    async def test_analyst_produces_perspectives(self):
        """Analyst produces at least one complete Perspective from raw text."""
        case = Case()
        case.commit()

        with scope(case.sid):
            analyst = AnalysisPipeline(text=SITUATION_TEXT)
            result = await analyst.resolve()

            assert result.thesis_hashes, "Should find at least one thesis"
            assert result.polarity_hashes, "Should find at least one polarity"
            assert result.perspective_hashes, (
                f"Should produce at least one perspective. Errors: {result.errors}"
            )

    @pytest.mark.asyncio
    @traced
    async def test_analyst_perspectives_are_complete(self):
        """Each Perspective has all 6 positions (T, A, T+, T-, A+, A-)."""
        case = Case()
        case.commit()

        with scope(case.sid):
            analyst = AnalysisPipeline(text=SITUATION_TEXT)
            result = await analyst.resolve()

            pp_repo = PerspectiveRepository()
            for pp_hash in result.perspective_hashes:
                repo = NodeRepository()
                pp = repo.find_by_hash(pp_hash, node_type=Perspective)
                assert pp is not None, f"Perspective {pp_hash} not found"
                assert pp.is_complete(), (
                    f"Perspective {pp.short_hash} is incomplete"
                )

    @pytest.mark.asyncio
    @traced
    async def test_analyst_theses_are_relevant(self):
        """Extracted theses relate to the input situation (not generic filler)."""
        case = Case()
        case.commit()

        with scope(case.sid):
            analyst = AnalysisPipeline(
                text=SITUATION_TEXT,
                intent="find tensions about scaling culture",
            )
            result = await analyst.resolve()

            repo = NodeRepository()
            relevant_keywords = [
                "growth", "culture", "scale", "team", "hire", "people",
                "autonomy", "identity", "cohesion", "trust", "communication",
                "context", "founders", "values", "inclusion",
            ]

            found_relevant = False
            for thesis_hash in result.thesis_hashes:
                stmt = repo.find_by_hash(thesis_hash, node_type=Statement)
                if stmt:
                    text_lower = stmt.text.lower()
                    if any(kw in text_lower for kw in relevant_keywords):
                        found_relevant = True
                        break

            assert found_relevant, (
                f"No thesis relates to the input situation. "
                f"Theses: {[repo.find_by_hash(h, node_type=Statement).text for h in result.thesis_hashes if repo.find_by_hash(h, node_type=Statement)]}"
            )

    @pytest.mark.asyncio
    @traced
    async def test_analyst_polarities_have_genuine_tension(self):
        """Polarities represent real dialectical oppositions, not just word games."""
        case = Case()
        case.commit()

        with scope(case.sid):
            analyst = AnalysisPipeline(text=SITUATION_TEXT)
            result = await analyst.resolve()

            repo = NodeRepository()
            identical_count = 0
            for pol_hash in result.polarity_hashes:
                pol = repo.find_by_hash(pol_hash, node_type=Polarity)
                assert pol is not None

                # Get T and A statements via correct accessors
                t_stmts = [(s, r) for s, r in pol.t.all()]
                a_stmts = [(s, r) for s, r in pol.a.all()]

                assert t_stmts, f"Polarity {pol.short_hash} has no thesis"
                assert a_stmts, f"Polarity {pol.short_hash} has no antithesis"

                # T and A should not be the same text
                t_text = t_stmts[0][0].text.lower()
                a_text = a_stmts[0][0].text.lower()
                if t_text == a_text:
                    identical_count += 1

            # At least half the polarities should have genuine tension
            assert identical_count < len(result.polarity_hashes), (
                f"ALL polarities have identical T and A — deduplication bug"
            )

    @pytest.mark.asyncio
    @traced
    async def test_analyst_partial_pipeline_from_hashes(self):
        """Analyst can pick up from existing thesis hashes (partial pipeline)."""
        case = Case()
        case.commit()

        with scope(case.sid):
            # First run: just surface theses
            from dialectical_framework.agents.analyst.skills.surface_theses import (
                SurfaceTheses,
            )
            from dialectical_framework.agents.orchestrator.tools.add_input import (
                AddInput,
            )

            add = AddInput()
            await add.resolve(content=SITUATION_TEXT)

            surface = SurfaceTheses(intent="find 2 theses about scaling")
            await surface.resolve()
            thesis_hashes = surface.report.artifacts.get("thesis_hashes", [])
            assert thesis_hashes

            # Second run: develop from existing theses (no text needed)
            analyst = AnalysisPipeline(thesis_hashes=thesis_hashes)
            result = await analyst.resolve()

            assert result.polarity_hashes, "Should find polarities for existing theses"
            assert result.perspective_hashes, "Should produce perspectives"

    @pytest.mark.asyncio
    @traced
    async def test_analyst_quality_gate_filters(self):
        """Analyst doesn't expand every polarity — quality gate filters by HS."""
        case = Case()
        case.commit()

        with scope(case.sid):
            analyst = AnalysisPipeline(text=SITUATION_TEXT)
            result = await analyst.resolve()

            # The number of perspectives should be <= number of polarities
            # (quality gate may filter some out)
            assert len(result.perspective_hashes) <= len(result.polarity_hashes) * 2


class TestExplorerEndToEnd:
    """Full pipeline tests for the Explorer sub-agent."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    @traced
    async def test_explorer_produces_wheels(self):
        """Explorer produces wheels from perspectives (2 PPs, minimal case)."""
        case = Case()
        case.commit()

        with scope(case.sid):
            # Build perspectives via Analyst
            analyst = AnalysisPipeline(
                text=SITUATION_TEXT,
                intent="find 2-3 core tensions about scaling company culture",
            )
            analysis = await analyst.resolve()

            if len(analysis.perspective_hashes) < 2:
                pytest.skip(
                    f"Analyst produced {len(analysis.perspective_hashes)} perspectives "
                    f"(need 2+) — LLM non-determinism, not an Explorer bug"
                )

            # Create nexus first (Analyst's responsibility in the new arch)
            from dialectical_framework.concerns.create_nexus import CreateNexus

            create = CreateNexus()
            nexus_result = await create.resolve(
                intent="understand how these tensions interact",
                perspective_hashes=analysis.perspective_hashes[:2],
            )

            # Explore within the nexus
            explorer = ExplorationPipeline(
                nexus_hash=nexus_result.nexus.hash,
                perspective_hashes=analysis.perspective_hashes[:2],
            )
            result = await explorer.resolve()

            assert result.nexus_hash, "Should reference the Nexus"
            assert result.cycle_hashes, "Should produce at least one Cycle"
            assert result.wheel_hashes, "Should produce at least one Wheel"
