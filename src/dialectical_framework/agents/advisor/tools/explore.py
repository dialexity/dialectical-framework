"""
explore tool: Group perspectives into nexus + build pathways + synthesis.

Handles the full exploration lifecycle: nexus creation/expansion,
wheel building, transformation generation, and synthesis.

The shared body lives in `run_exploration` so the nexus-scoped advisor
variant (tools/scoped.py) can pin the nexus hash in code and reuse the
exact same pipeline without drift.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

# The Advisor's explore is LAZY: every valid wheel is built and estimated
# (structural, cheap), but transformations + synthesis — the expensive LLM
# work — go only to the top-plausibility wheel(s). At 3-4 perspectives this
# is the difference between deepening 1 wheel and deepening 17-96. The
# Advisor leads with the most plausible arrangement anyway; the rest stay
# ranked-but-shallow, available for deepening on demand (arrangement
# contrast, task #3). The Explorer agent path is untouched — there the USER
# selects which wheels to deepen.
MAX_DEEP_WHEELS = 1


async def run_exploration(
    perspective_hashes: list[str],
    intent: str,
    nexus_hash: str | None,
) -> str:
    """
    Shared explore body: expand (or create) a nexus, build wheels, deepen
    the top-plausibility wheel(s) with transformations + synthesis.
    Returns str(report).
    """
    from dialectical_framework.agents.explorer.explorer import \
        ExplorationPipeline
    from dialectical_framework.agents.explorer.skills.generate_synthesis import \
        GenerateSynthesis
    from dialectical_framework.concerns.create_nexus import CreateNexus
    from dialectical_framework.concerns.expand_nexus import ExpandNexus

    if nexus_hash:
        expand = ExpandNexus()
        await expand.resolve(
            nexus_hash=nexus_hash,
            perspective_hashes=perspective_hashes,
        )
        nexus_report = expand.report
        effective_nexus_hash = nexus_hash
    else:
        create = CreateNexus()
        create_result = await create.resolve(
            intent=intent,
            perspective_hashes=perspective_hashes,
        )
        nexus_report = create.report
        effective_nexus_hash = create_result.nexus.short_hash

    exploration = ExplorationPipeline(
        nexus_hash=effective_nexus_hash,
        max_deep_wheels=MAX_DEEP_WHEELS,
    )
    exp_result = await exploration.resolve()

    # Synthesis only where transformations exist (the deepened wheels).
    synthesis_count = 0
    for wh in exp_result.deepened_wheel_hashes:
        try:
            synth = GenerateSynthesis(wheel_hash=wh)
            await synth.resolve()
            synthesis_count += 1
        except (ValueError, RuntimeError):
            pass

    combined_report = nexus_report.merge(exploration.report)
    combined_report.artifacts["nexus_hash"] = effective_nexus_hash
    combined_report.artifacts["synthesis_generated"] = synthesis_count
    shallow = [
        wh
        for wh in exp_result.wheel_hashes
        if wh not in exp_result.deepened_wheel_hashes
    ]
    if shallow:
        combined_report.artifacts["shallow_wheel_hashes"] = shallow

    return str(combined_report)


@llm.tool
async def explore(
    perspective_hashes: Annotated[
        list[str],
        Field(description="Hashes of perspectives to explore together"),
    ],
    intent: Annotated[
        str,
        Field(
            description="What this exploration is about — the theme connecting these tensions"
        ),
    ],
    nexus_hash: Annotated[
        str | None,
        Field(description="Existing nexus to enrich; omit to create a new one"),
    ] = None,
) -> str:
    """Group tensions and generate pathways. Creates or expands a nexus, builds causal arrangements, generates action-reflection pathways and synthesis. Call when you have perspective hashes ready for exploration."""
    return await run_exploration(perspective_hashes, intent, nexus_hash)
