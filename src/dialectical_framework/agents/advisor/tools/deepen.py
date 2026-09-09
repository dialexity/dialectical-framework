"""
deepen tool: Develop a shallow wheel on demand (transformations + synthesis).

The Advisor's `explore` deep-generates only the single top-plausibility
arrangement (fixed policy) and leaves the rest shallow
(built + ranked, listed as `shallow_wheel_hashes`). `deepen` is the follow-up
move: when the person's lived reality points at an ALTERNATIVE arrangement —
the 20% reading over the 80% one — this generates its action-reflection
pathways and synthesis so counsel can follow the person off the argmax path.

One composed tool, not two: transformations and synthesis are generated
together (the Advisor reveals them progressively per its conversation arc);
the sequencing constraint (synthesis requires transformations) is absorbed
here instead of being a prompt rule. Synthesis is always generated — a
deepened wheel without S+/S- is structurally unfinished (synthesis is the
wheel-level phenomenon the circular causality exists to produce, and the
S- trap-naming is the Advisor's most distinctive counsel move). Pure glue
over the Explorer's existing skills — no new pipeline capability.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field


async def run_deepen(wheel_hash: str) -> str:
    """
    Shared deepen body: generate transformations for the wheel, then
    synthesis. Idempotent — both skills reuse existing nodes.
    Returns str(report).

    The scope goes HERE and not in the `@llm.tool` wrapper because every other
    entry to a deepen comes through this function — the wrapper below, `scoped.py`,
    the resume tests, and the resume-hint pattern `concerns/build_status.py`'s
    docstring hands to host apps — and each of them is one action to a person.
    (`build_status` itself calls nothing; it only recommends this shape. Named here
    because a host that follows its advice becomes a caller.)

    One stream for the whole call, which the two skills below could not give on
    their own: `ExploreTransformations` and `GenerateSynthesis` each open a scope
    (both are reachable directly), so this call used to publish TWO `final`
    events and a host cleared its indicator halfway through. A nested
    `progress_scope` now defers to this one instead of installing — see
    `utils/progress.py`.

    The key is the wheel's short hash rather than a digest of it: unlike
    `ingest`, nothing here is the person's own text, so there is nothing to hide
    from a host that renders the key. Truncated to 7 so it matches the
    `key=wheel.short_hash` the skills used to publish under.

    BUT `wheel_hash` IS RAW MODEL OUTPUT AT THIS POINT, and the scope opens above
    any attempt to resolve it, so the key must be sanitised the same way
    `audit_feasibility` sanitises the hashes it is handed. The framework renders
    pathway hashes to the model as `[[abc1234]]`, and a model that echoes the
    brackets back — which is the single most common malformed-hash shape in this
    tree — keyed the stream `"[[a1b2"` and put punctuation from a prompt template
    into whatever a host shows beside its spinner. Sanitising only the KEY, not the
    argument passed on: what a bad hash should do to the reasoning path is
    `ExploreTransformations`' decision, not this line's.
    """
    from dialectical_framework.utils.progress import progress_scope

    # `.strip("[]")` after `.strip()`, matching `audit_feasibility`: whitespace can
    # sit outside the brackets.
    key = (wheel_hash or "").strip().strip("[]")[:7]
    with progress_scope("deepen", key=key):
        return await _deepen(wheel_hash)


async def _deepen(wheel_hash: str) -> str:
    """The body, under `run_deepen`'s progress scope."""
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations
    from dialectical_framework.agents.explorer.skills.generate_synthesis import \
        GenerateSynthesis

    from dialectical_framework.graph.rendering import pathway_line

    explore_tr = ExploreTransformations(wheel_hash=wheel_hash)
    tr_result = await explore_tr.resolve()
    combined_report = explore_tr.report

    # Same reason as `explore`: the whole point of deepening is that the person's
    # lived reality picked THIS arrangement, so the pathway they can adopt has to
    # be nameable from the tool's own output. Idempotent re-runs return every
    # transformation as `existing`, so `.all` is the only correct source — a
    # second deepen on the same wheel would otherwise report no pathways at all.
    pathways = [
        line
        for line in (
            pathway_line(t)
            for t in sorted(tr_result.all, key=lambda t: t.hash or "")
            if t.hash
        )
        if line
    ]
    if pathways:
        combined_report.artifacts["pathways"] = pathways

    # Whether the deepening actually finished. `pathways` has no denominator, so
    # a run that lost half its edges to a mid-flight failure or an interrupted
    # session reported a shorter list and nothing else — the tool looked like it
    # succeeded. The fraction is what tells the Advisor a second `deepen` would
    # add something, and what tells it not to present a fragment as the whole.
    try:
        from dialectical_framework.graph.nodes.wheel import Wheel
        from dialectical_framework.graph.rendering import wheel_completeness
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        wheel = NodeRepository().find_by_hash(wheel_hash, node_type=Wheel)
        completeness = wheel_completeness(wheel) if wheel else None
        if completeness and completeness.expected:
            combined_report.artifacts["pathway_completeness"] = completeness.fraction
            if completeness.incomplete_edges:
                combined_report.artifacts["pathways_incomplete_on"] = (
                    completeness.incomplete_edges
                )
            if completeness.blocked_edges:
                combined_report.artifacts["pathways_blocked_on"] = (
                    completeness.blocked_edges
                )
    except Exception:  # noqa: BLE001 - decoration, never the payload
        # Status decoration must never be the thing that fails a deepen that
        # otherwise produced real pathways. Broad on purpose: the read goes to
        # the DB, so the failure modes include driver errors that are neither
        # ValueError nor RuntimeError.
        pass

    try:
        synth = GenerateSynthesis(wheel_hash=wheel_hash)
        await synth.resolve()
        combined_report = combined_report.merge(synth.report)
    except Exception as e:  # noqa: BLE001 - pathways stand without a synthesis
        # A failed synthesis is reported, not raised: the Transformations this
        # call built are real and adoptable, and losing them to a synthesis
        # fault would throw away the expensive half of the work.
        combined_report.artifacts["synthesis_skipped"] = f"{type(e).__name__}: {e}"

    combined_report.artifacts["wheel_hash"] = wheel_hash
    return str(combined_report)


@llm.tool
async def deepen(
    wheel_hash: Annotated[
        str,
        Field(
            description="Hash of the shallow wheel (causal arrangement) to develop — from shallow_wheel_hashes or the Current Understanding dump"
        ),
    ],
) -> str:
    """Develop an alternative causal arrangement: generates its action-reflection pathways and synthesis. Use when the person's lived reality points at an arrangement whose pathways don't exist yet (a shallow wheel) — e.g. they resonate with the less-plausible reading during arrangement contrast. Idempotent on already-deepened wheels."""
    return await run_deepen(wheel_hash)
