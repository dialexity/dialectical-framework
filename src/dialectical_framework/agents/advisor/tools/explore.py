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

from dialectical_framework.protocols.has_config import SettingsAware

# The Advisor's explore is LAZY and budgeted (settings.advisor_explore_*):
# every valid wheel is built and estimated (structural, cheap), but the
# expensive stages are capped — transformations + synthesis go only to the
# single top-plausibility wheel (advisor_explore_deepen, default on; off =
# fully reactive, pathways come only from the deepen tool), at most
# advisor_explore_perspectives (default 2) are woven per call (excess is
# reported as deferred, never dropped), and synthesis can be switched off
# (advisor_explore_synthesis). "Rich vs simple" exploration is this runtime
# budget, not a schema concept. The Explorer agent path is untouched — there
# the USER selects which wheels to deepen.


class _ExploreBudget(SettingsAware):
    """Accessor for the silent-explore depth budget (DI settings)."""

    @property
    def deep_wheels(self) -> int:
        # The pipeline seam stays an integer (generic); the Advisor's policy
        # is a flag: deepen the top arrangement eagerly, or none at all.
        return 1 if self.settings.advisor_explore_deepen else 0

    @property
    def max_perspectives(self) -> int:
        return self.settings.advisor_explore_perspectives

    @property
    def synthesis(self) -> bool:
        return self.settings.advisor_explore_synthesis


async def run_exploration(
    perspective_hashes: list[str],
    intent: str,
    nexus_hash: str | None,
) -> str:
    """
    Shared explore body: expand (or create) a nexus, build wheels, deepen
    the top-plausibility wheel(s) with transformations (+ synthesis), all
    within the silent-explore depth budget. Returns str(report).
    """
    from dialectical_framework.agents.explorer.explorer import \
        ExplorationPipeline
    from dialectical_framework.agents.explorer.skills.generate_synthesis import \
        GenerateSynthesis
    from dialectical_framework.concerns.create_nexus import CreateNexus
    from dialectical_framework.concerns.expand_nexus import ExpandNexus

    budget = _ExploreBudget()

    # Perspective cap: weave the first N now, report the rest as deferred so
    # the model weaves them in a follow-up call — never silently dropped.
    deferred_hashes: list[str] = []
    if (
        budget.max_perspectives > 0
        and len(perspective_hashes) > budget.max_perspectives
    ):
        deferred_hashes = perspective_hashes[budget.max_perspectives :]
        perspective_hashes = perspective_hashes[: budget.max_perspectives]

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
        max_deep_wheels=budget.deep_wheels,
    )
    exp_result = await exploration.resolve()

    # Synthesis only where transformations exist (the deepened wheels).
    synthesis_count = 0
    if budget.synthesis:
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
    if deferred_hashes:
        combined_report.artifacts["deferred_perspective_hashes"] = deferred_hashes
        combined_report.summary = (
            (combined_report.summary or "")
            + f" | {len(deferred_hashes)} perspective(s) deferred (budget: "
            f"{budget.max_perspectives} per call) — call explore again with "
            f"the deferred hashes to weave them in."
        ).strip(" |")

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
