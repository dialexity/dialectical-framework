"""
audit_feasibility tool: ask whether named pathways are practically doable.

WHY A TOOL RATHER THAN A PIPELINE STAGE
=======================================
`TransformationAudit` used to run on every Transformation `explore` built — two
provider calls each, 40% of the tool's entire provider spend, for an annotation
no code read. It is now off by default (`settings.audit_transformations`), and
this is how a conversation gets it back.

The two mechanisms answer genuinely different questions, which is why both exist:

    settings.audit_transformations   "audit everything as it is built" — for
                                     programmatic pipelines with no agent in the
                                     loop, where nobody will ever ask.
    audit_feasibility (this tool)    "audit THIS, because someone just asked" —
                                     after the pathway was offered, about the
                                     pathway they asked about.

The asymmetry is the whole argument: eager auditing pays for all 6N
Transformations of an exploration, while "can I actually do that?" is a question
a person asks about the one or two they were shown. Same concern, same prose,
the cost lands where the interest is.

IDEMPOTENT, AND THAT IS LOAD-BEARING
====================================
A Transformation whose covered positions already carry a `FeasibilityEstimation`
is reported straight from the graph, with no provider call. Without that skip,
asking twice costs twice AND leaves two critique Rationales whose prose
disagrees: `upsert_estimation` replaces the number, but critiques accumulate, and
a later reader cannot tell which one produced the surviving score.

The skip is all-or-nothing per Transformation, because the concern has no
per-position entry point: if Ac+ carries a band and Re+ does not (a provider
failure on the first pass), a re-audit re-scores both. That costs one extra call
and can leave the superseded critique behind, unreferenced by any live
estimation — accepted, because the missing half is exactly what the person is
asking about and a permanently unanswerable position is worse.

WHAT THIS READS THAT NOTHING ELSE DOES
======================================
The critique Rationale the audit writes had no reader anywhere in the framework
(`.critiques` was traversed only by its own declaration and a cascade-delete) —
one of the reasons the eager audit was such a bad deal. This renders it: the
score comes from the `FeasibilityEstimation`, the reasoning from its `provider`
Rationale. Both paths render the same way, from the graph, so the reuse path is
exercised by every second call and cannot silently rot.
"""

from __future__ import annotations

from typing import Annotated, Optional, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver

#: How many Transformations one call may audit. Policy, not config: two provider
#: calls apiece, so an unbounded list lets a model re-spend the entire eager
#: audit budget (a 1-PP wheel is 6 Transformations = 12 calls) on a question
#: about one pathway. Four covers "the one or two under discussion" with slack.
#: Anything beyond is DEFERRED AND NAMED, never silently dropped — the model can
#: ask again if the person really wants the rest.
MAX_TRANSFORMATIONS_PER_CALL = 4

#: The positions this reports, matching what `TransformationAudit` audits (it
#: takes `audit_all` but nothing passes it, and rightly: Ac-/Re- are failure-mode
#: descriptions, not action prescriptions, so feasibility does not apply to them
#: the same way). Not exposed as a parameter for that reason.
_COVERED_POSITIONS = ("Ac+", "Re+")


@inject
async def _get_input_text(
    input_resolver: InputResolver = Provide[DI.input_resolver],
) -> str:
    """Input context from digests (falls back to full content if no digest).

    Same body as every skill's `_get_input_text`. The audit is a judgement about
    the person's actual circumstances — resources, resistance, timelines — so
    running it without the situation in front of it produces generic scoring.
    """
    from dialectical_framework.graph.repositories.input_repository import \
        InputRepository
    from dialectical_framework.utils.input_context import input_context

    return await input_context(InputRepository().get_all(), input_resolver)


def _feasibility_of(transition) -> tuple[Optional[float], Optional[str]]:
    """(score, reasoning) for a transition, from the graph. (None, None) if unaudited."""
    from dialectical_framework.graph.nodes.estimation import \
        FeasibilityEstimation

    for est, _ in transition.estimations.all():
        if isinstance(est, FeasibilityEstimation):
            provider = est.provider.get()
            return est.value, (provider[0].text if provider else None)
    return None, None


def _covered_transitions(tr) -> list[tuple[str, object]]:
    """(label, transition) for the positions the audit covers, where they exist."""
    pairs = []
    for label, manager in (("Ac+", tr.ac_plus), ("Re+", tr.re_plus)):
        result = manager.get()
        if result:
            pairs.append((label, result[0]))
    return pairs


def _needs_audit(tr) -> bool:
    """True when any covered position lacks a stored feasibility band."""
    covered = _covered_transitions(tr)
    if not covered:
        return False
    return any(_feasibility_of(t)[0] is None for _, t in covered)


def _render(tr, pp_index: Optional[dict[int, int]] = None) -> str:
    """Render one Transformation's feasibility, reading only from the graph."""
    from dialectical_framework.graph.rendering import format_edge_label, one_line

    edge_result = tr.edge.get()
    edge_label = format_edge_label(edge_result[0], pp_index) if edge_result else ""
    head = f"[[{tr.short_hash}]]"
    if edge_label:
        head += f" ({edge_label})"

    lines = [head]
    for label, transition in _covered_transitions(tr):
        text = one_line(transition.instruction or transition.summary or "")
        value, reasoning = _feasibility_of(transition)
        if value is None:
            lines.append(f"  {label} (not estimated): {text}")
            continue
        lines.append(f"  {label} feasibility={value:.2f}: {text}")
        if reasoning:
            for reason_line in reasoning.splitlines():
                if reason_line.strip():
                    lines.append(f"    {reason_line.strip()}")
    return "\n".join(lines)


async def run_audit_feasibility(transformation_hashes: list[str]) -> str:
    """
    Shared audit body: score the named Transformations' Ac+/Re+ transitions for
    practical achievability, skipping any already scored. Returns str(report).
    """
    from dialectical_framework.agents.execution_report import ExecutionReport
    from dialectical_framework.concerns.transformation_audit import \
        TransformationAudit
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.repositories.node_repository import \
        NodeRepository
    from dialectical_framework.utils.progress import (progress_scope,
                                                      report_progress)

    report = ExecutionReport(tool="audit_feasibility")

    if not transformation_hashes:
        report.ok = False
        report.summary = (
            "No pathway named. Pass the [[hash]] of the pathway(s) in question."
        )
        return str(report)

    # Resolve first, audit second: a bad hash should cost nothing, and the model
    # needs to know WHICH of its hashes was bad rather than that "the tool
    # failed" — it usually has a longer prefix available.
    repo = NodeRepository()
    targets: list[Transformation] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for raw in transformation_hashes:
        h = (raw or "").strip().strip("[]")
        if not h or h in seen:
            continue
        seen.add(h)
        try:
            node = repo.find_by_hash(h)
        except ValueError as e:  # ambiguous prefix — recoverable, so say so
            unresolved.append(f"{h} ({e})")
            continue
        if not isinstance(node, Transformation):
            found = type(node).__name__ if node is not None else "nothing"
            unresolved.append(f"{h} (is {found}, not a pathway)")
            continue
        targets.append(node)

    if unresolved:
        report.artifacts["unresolved"] = unresolved

    if not targets:
        report.ok = False
        report.summary = (
            "None of the given hashes is a pathway (Transformation) in this case."
        )
        return str(report)

    deferred = [t.short_hash for t in targets[MAX_TRANSFORMATIONS_PER_CALL:]]
    targets = targets[:MAX_TRANSFORMATIONS_PER_CALL]
    if deferred:
        report.artifacts["deferred"] = deferred

    to_audit = [t for t in targets if _needs_audit(t)]
    _to_audit_ids = {id(t) for t in to_audit}
    reused = [t.short_hash for t in targets if id(t) not in _to_audit_ids]
    if reused:
        report.artifacts["already_estimated"] = reused

    failed: list[str] = []
    if to_audit:
        input_text = await _get_input_text()
        with progress_scope("feasibility", total=len(to_audit)):
            for tr in to_audit:
                report_progress("Checking whether the move is actually doable")
                auditor = TransformationAudit()
                try:
                    await auditor.resolve(tr, input_text)
                except Exception as e:  # noqa: BLE001 - one bad audit, not all
                    # Sequential and individually caught: the whole point is
                    # answering about a specific pathway, so a failure on one
                    # must not take the answers about the others with it.
                    failed.append(f"{tr.short_hash} ({type(e).__name__}: {e})")
                    continue
                report = report.merge(auditor.report)
        # The concern's own artifacts are per-Transformation and last-write-wins
        # under merge, so across several targets `avg_feasibility` would name one
        # pathway's average while appearing to describe the call. The rendered
        # lines below carry the per-pathway numbers properly.
        report.artifacts.pop("positions_audited", None)
        report.artifacts.pop("avg_feasibility", None)
    if failed:
        report.artifacts["audit_failed"] = failed

    # Render every target from the graph, freshly audited or not — one renderer,
    # so the reuse path is exercised on every second call.
    report.artifacts["feasibility"] = [_render(tr) for tr in targets]
    report.artifacts["audited"] = len(to_audit) - len(failed)
    report.summary = (
        f"Feasibility for {len(targets)} pathway(s): "
        f"{len(to_audit) - len(failed)} newly estimated, {len(reused)} already on record"
        + (f", {len(deferred)} deferred" if deferred else "")
    )
    return str(report)


@llm.tool
async def audit_feasibility(
    transformation_hashes: Annotated[
        list[str],
        Field(
            description="Hashes of the pathway(s) to assess — the [[hash]] shown with each action-reflection pathway. Name only the ones actually in question."
        ),
    ],
) -> str:
    """Assess whether specific action-reflection pathways are practically achievable: a 0.0-1.0 feasibility band per Ac+/Re+ step, with the resource, resistance, timeline and precedent factors behind it, and what would have to be true for it to work. Use when the person asks whether something is realistic or doable, or when choosing between pathways turns on achievability rather than insight. Costs two model calls per pathway, so name the one or two under discussion, not everything; already-assessed pathways are returned free."""
    return await run_audit_feasibility(transformation_hashes)
