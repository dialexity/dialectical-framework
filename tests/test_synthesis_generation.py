"""
Tests for wheel-level synthesis generation.
"""

from __future__ import annotations

import pytest
from conftest import traced

from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.explorer.explorer import ExplorationPipeline
from dialectical_framework.agents.explorer.skills.generate_synthesis import (
    GenerateSynthesis,
)
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.scope_context import scope


SITUATION_TEXT = """
A small startup is deciding whether to prioritize rapid product iteration
(move fast, break things, respond to market signals immediately) or build
robust engineering foundations (invest in testing, documentation, architecture
that scales). Both are valuable, both compete for the same limited time.
"""


@pytest.mark.real_llm
class TestSynthesisGenerationRealLLM:
    """Real LLM tests for synthesis generation."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    @traced
    async def test_synthesis_from_2pp_wheel(self):
        """Generate synthesis from a 2-PP wheel with real LLM."""
        case = Case()
        case.commit()

        with scope(case.sid):
            # Build perspectives via Analyst
            analyst = AnalysisPipeline(
                text=SITUATION_TEXT,
                intent="find 2 core tensions about startup priorities",
            )
            analysis = await analyst.resolve()

            if len(analysis.perspective_hashes) < 2:
                pytest.skip(
                    f"Analyst produced {len(analysis.perspective_hashes)} perspectives "
                    f"(need 2+) — LLM non-determinism"
                )

            # Create nexus
            create = CreateNexus()
            nexus_result = await create.resolve(
                intent="how speed and stability interact",
                perspective_hashes=analysis.perspective_hashes[:2],
            )

            # Run full exploration (builds wheels + transformations)
            explorer = ExplorationPipeline(
                nexus_hash=nexus_result.nexus.hash,
                perspective_hashes=analysis.perspective_hashes[:2],
            )
            result = await explorer.resolve()

            assert result.wheel_hashes, "Should have produced wheels"
            assert result.transformation_count > 0, "Should have transformations"

            # Now generate synthesis for each wheel
            for wheel_hash in result.wheel_hashes:
                wheel = NodeRepository().find_by_hash(wheel_hash, node_type=Wheel)
                assert wheel is not None

                # Only generate for wheels that have transformations
                if not wheel.transformations:
                    continue

                skill = GenerateSynthesis(wheel_hash=wheel_hash)
                synth_result = await skill.resolve()

                assert synth_result.is_new
                synthesis = synth_result.synthesis

                # Verify structure
                assert synthesis.is_committed
                sp_result = synthesis.s_plus.get()
                sm_result = synthesis.s_minus.get()
                assert sp_result is not None, "Should have S+"
                assert sm_result is not None, "Should have S-"

                s_plus_stmt, s_plus_rel = sp_result
                s_minus_stmt, s_minus_rel = sm_result

                # Print for manual inspection
                print(f"\n--- Wheel [{wheel.short_hash}] "
                      f"({len(wheel.edges)} edges) ---")
                print(f"  S+ = \"{s_plus_stmt.text}\"")
                print(f"  S- = \"{s_minus_stmt.text}\"")

                # Basic sanity: not empty, not identical
                assert s_plus_stmt.text.strip(), "S+ should not be empty"
                assert s_minus_stmt.text.strip(), "S- should not be empty"
                assert s_plus_stmt.text != s_minus_stmt.text, "S+ and S- should differ"

                # Verify idempotent
                skill2 = GenerateSynthesis(wheel_hash=wheel_hash)
                synth_result2 = await skill2.resolve()
                assert not synth_result2.is_new
                assert synth_result2.synthesis.hash == synthesis.hash
