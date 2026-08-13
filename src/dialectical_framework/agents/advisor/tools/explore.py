"""
explore tool: Group perspectives into nexus + build pathways + synthesis.

Handles the full exploration lifecycle: nexus creation/expansion,
wheel building, transformation generation, and synthesis.

The shared body lives in `run_exploration_detailed` so the nexus-scoped advisor
variant (tools/scoped.py) can pin the nexus hash in code and reuse the
exact same pipeline without drift. `run_exploration` is the prose-only face of
it for the two `@llm.tool` wrappers; programmatic callers that need to USE what
was built (the Advisor's closing seam, grounding a decision on a pathway) take
the detailed one.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.protocols.has_config import SettingsAware

# The Advisor's explore is LAZY and budgeted: every valid wheel is built and
# estimated (structural, cheap), but the expensive stage — transformations +
# synthesis — goes only to the single top-plausibility wheel (fixed policy:
# lead with the best; the `deepen` tool develops any other arrangement on
# demand). At most advisor_max_perspectives_per_exploration (default 2) are
# woven per call (excess is reported as deferred, never dropped — bounds
# turn latency, not total work). "Rich vs simple" exploration is this
# runtime budget, not a schema concept. The Explorer agent path is untouched
# — there the USER selects which wheels to deepen.

# One wheel deepened eagerly per explore call. Not a setting: 0 would strand
# the conversation arc ("after explore, offer pathways") behind an extra
# deepen round-trip, and N>1 pre-pays for arrangements the user may never
# pick — contrast works at causality level, deepen covers the picked one.
EXPLORE_DEEP_WHEELS = 1


class _ExploreBudget(SettingsAware):
    """Accessor for the silent-explore depth budget (DI settings)."""

    @property
    def deep_wheels(self) -> int:
        return EXPLORE_DEEP_WHEELS

    @property
    def max_perspectives(self) -> int:
        return self.settings.advisor_max_perspectives_per_exploration


async def run_exploration(
    perspective_hashes: list[str],
    intent: str,
    nexus_hash: str | None,
) -> str:
    """
    Shared explore body: expand (or create) a nexus, build wheels, deepen
    the top-plausibility wheel with transformations + synthesis, all within
    the silent-explore depth budget. Returns str(report).

    The transformation hashes this built are ALSO published on the report's
    `transformation_hashes` artifact, so a programmatic caller (the Advisor's
    closing seam) can ground a decision on a pathway it just built instead of
    having to re-query for it. See `run_exploration_detailed`.
    """
    report, _ = await run_exploration_detailed(
        perspective_hashes=perspective_hashes,
        intent=intent,
        nexus_hash=nexus_hash,
    )
    return report


async def run_exploration_detailed(
    perspective_hashes: list[str],
    intent: str,
    nexus_hash: str | None,
) -> tuple[str, list[str]]:
    """Same body, returning `(str(report), transformation_hashes)`.

    The hashes exist so a caller that builds pathways on the person's behalf
    can then USE one. `run_exploration` returns only prose because that is all
    an LLM tool call can consume; the seam is not an LLM and re-deriving the
    hashes from the graph would be a second query for something already in
    hand — and one that cannot tell "the pathway I just built for this
    closing" from "some pathway on some wheel".
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

    # Synthesis only where transformations exist (the deepened wheels) —
    # always generated: a deepened wheel without S+/S- is structurally
    # unfinished.
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
    # Full hashes, not the short ones on the `pathways` lines: a ground is
    # resolved by hash and `RecordDecision` fails closed on anything it cannot
    # resolve, so the caller needs the identifier the repository will match.
    transformation_hashes = list(exp_result.transformation_hashes)
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

    return str(combined_report), transformation_hashes


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
