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
# synthesis — goes only to the single top-plausibility wheel and the coarser
# ancestry it refines from, one wheel per layer below it (fixed policy: lead with
# the best, built up from the smaller arrangements inside it; the `deepen` tool
# develops any other arrangement on demand). At most
# advisor_max_perspectives_per_exploration (default 2) are
# woven per call (excess is reported as deferred, never dropped — bounds
# turn latency, not total work). "Rich vs simple" exploration is this
# runtime budget, not a schema concept. The Explorer agent path is untouched
# — there the USER selects which wheels to deepen.

# One wheel deepened eagerly per explore call. Not a setting: 0 would strand
# the conversation arc ("after explore, offer pathways") behind an extra
# deepen round-trip, and N>1 pre-pays for arrangements the user may never
# pick — contrast works at causality level, deepen covers the picked one.
EXPLORE_DEEP_WHEELS = 1

# ...but that one wheel is deepened WITH its coarser ancestry underneath it, one
# wheel per layer below, coarsest first. Also not a setting, because off is not a
# cheaper version of the same answer — it is the refinement recursion not running.
# Every Transformation is generated against the coarser Transformations its edge
# descends from ("be more concrete than this broader path"), and with the top wheel
# deepened alone there are none: measured at k=4 as 0 of 8 parent lookups finding
# anything, so the deepest arrangement — the one the theory says carries the most —
# was the one produced with no refinement context. Deepening the ancestry first
# turns that into 18 of 20, chained transitively.
#
# It costs less than the 2.5x edge count suggests (20 edges against 8): building and
# estimating all 96 wheels is paid either way, so at k=4 the whole call goes from 177
# provider calls to 273 — 1.5x — and off-provider wall clock moves ~5%. What buys
# that back for the person is the ORDER: the coarsest wheel has the fewest edges, so
# it finishes first and is a complete, usable answer while the deeper rungs are still
# running. Deepening the top wheel alone is not faster to something readable, it is
# slower — one long silence instead of an answer that keeps getting sharper.
EXPLORE_REFINE_FROM_COARSER = True


class _ExploreBudget(SettingsAware):
    """Accessor for the silent-explore depth budget (DI settings)."""

    @property
    def deep_wheels(self) -> int:
        return EXPLORE_DEEP_WHEELS

    @property
    def refine_from_coarser(self) -> bool:
        return EXPLORE_REFINE_FROM_COARSER

    @property
    def max_perspectives(self) -> int:
        return self.settings.advisor_max_perspectives_per_exploration


async def run_exploration(
    perspective_hashes: list[str],
    intent: str,
    nexus_hash: str | None,
) -> str:
    """
    Shared explore body: expand (or create) a nexus, build wheels, deepen the
    top-plausibility wheel and its coarser ancestry with transformations +
    synthesis, all within the silent-explore depth budget. Returns str(report).

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

    ONE PROGRESS STREAM for the whole call, opened here rather than in the
    `@llm.tool` wrapper because the wrapper is not the only door — the
    nexus-scoped variant and the Advisor's closing seam come straight in here,
    and a stream that only exists for one of three callers is worse than none.
    Everything below defers into it: `ExplorationPipeline` opens the same stage,
    and the two skills it drives (`ExploreTransformations`, `GenerateSynthesis`)
    each own a stage of their own when called directly. Before this, one explore
    call published `2 x deepened wheels` `final` events — the same defect
    `deepen` had, where a host cleared its indicator halfway through the work
    and started over.

    The cap is applied ABOVE the scope so the key describes the perspectives
    actually woven, not the ones handed in: the deferred ones are reported and
    left for a follow-up call, and that call is a different stream.
    """
    from dialectical_framework.utils.progress import (progress_hash_key,
                                                      progress_scope)

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

    # The hashes themselves, joined and sorted — NOT digested, for
    # `audit_feasibility`'s reason: these are already opaque short hashes the model
    # read off its own prompt, so a digest would hide nothing and cost a host the
    # one thing a key is good for, lining a bar up with the tensions the person just
    # named. Sanitised one by one because they are raw model output and this
    # framework renders hashes into prompts as `[[abc1234]]`; unstripped, a model
    # echoing the brackets keys a second stream for the same call. `intent` is
    # deliberately NOT in here: it is free-form text in the person's own words, and
    # including it would force a digest over the whole key to keep it off a host's
    # surface.
    key = ",".join(
        sorted(k for k in (progress_hash_key(h) for h in perspective_hashes) if k)
    )
    if nexus_hash:
        key = f"{progress_hash_key(nexus_hash)}:{key}"
    with progress_scope("exploration", key=key):
        return await _run_exploration(
            perspective_hashes=perspective_hashes,
            intent=intent,
            nexus_hash=nexus_hash,
            deferred_hashes=deferred_hashes,
            budget=budget,
        )


async def _run_exploration(
    perspective_hashes: list[str],
    intent: str,
    nexus_hash: str | None,
    deferred_hashes: list[str],
    budget: _ExploreBudget,
) -> tuple[str, list[str]]:
    """The body, split out so `run_exploration_detailed` can own the progress stream.

    Split rather than indented for the reason the seam requires: a task created
    before the scope is installed captures the context without it, so the `with`
    has to sit above every await here — which is the whole body.
    """
    from dialectical_framework.agents.explorer.explorer import \
        ExplorationPipeline
    from dialectical_framework.agents.explorer.skills.generate_synthesis import \
        GenerateSynthesis
    from dialectical_framework.concerns.create_nexus import CreateNexus
    from dialectical_framework.concerns.expand_nexus import ExpandNexus

    # No progress step for the nexus phase, deliberately: it is graph work with no
    # provider call in it, and every node and edge it writes is already announced
    # on the `sid` channel as an effect. A step here would report the one phase
    # that needs no reporting.
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
        refine_from_coarser=budget.refine_from_coarser,
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
    # Whether the wheels explore DID deepen came out whole. A deepened wheel
    # that lost edges to a failure or an interrupted session still lands in
    # `deepened_wheel_hashes`, so without a fraction the caller cannot tell a
    # finished arrangement from a fragment — and would present the fragment as
    # the answer. Only partial wheels are listed; a clean run says nothing.
    partial: dict[str, str] = {}
    for wh in exp_result.deepened_wheel_hashes:
        try:
            from dialectical_framework.graph.nodes.wheel import Wheel
            from dialectical_framework.graph.rendering import wheel_completeness
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            wheel_node = NodeRepository().find_by_hash(wh, node_type=Wheel)
            if not wheel_node:
                continue
            completeness = wheel_completeness(wheel_node)
            if completeness.expected and not completeness.is_complete:
                partial[wh] = completeness.fraction
        except Exception:  # noqa: BLE001 - decoration, never the payload
            # Broad on purpose: this is a derived-status read decorating an
            # exploration that already succeeded, and a DB-level failure here
            # is neither ValueError nor RuntimeError.
            continue
    if partial:
        combined_report.artifacts["partial_wheels"] = partial
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
