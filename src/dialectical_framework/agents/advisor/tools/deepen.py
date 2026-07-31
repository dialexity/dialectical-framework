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
    """
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations
    from dialectical_framework.agents.explorer.skills.generate_synthesis import \
        GenerateSynthesis

    explore_tr = ExploreTransformations(wheel_hash=wheel_hash)
    await explore_tr.resolve()
    combined_report = explore_tr.report

    try:
        synth = GenerateSynthesis(wheel_hash=wheel_hash)
        await synth.resolve()
        combined_report = combined_report.merge(synth.report)
    except (ValueError, RuntimeError) as e:
        combined_report.artifacts["synthesis_skipped"] = str(e)

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
