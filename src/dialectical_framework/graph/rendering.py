"""
Shared rendering utilities for graph nodes.

Provides consistent alias computation and formatting used by both
dialectical_context (compact dump) and inspect_node (verbose detail).
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective

_REL_TYPE_TO_LABEL: dict[str, str] = {
    "T": "T",
    "A": "A",
    "T_PLUS": "T+",
    "T_MINUS": "T-",
    "A_PLUS": "A+",
    "A_MINUS": "A-",
}


def build_pp_index(nexus: Nexus) -> dict[int, int]:
    """
    Build the canonical perspective index map from a Nexus.

    Returns a dict mapping pp._id → 1-based index, using the same ordering
    that nexus.perspectives.all() returns (active perspectives only).
    """
    pp_index: dict[int, int] = {}
    for i, (pp, _) in enumerate(nexus.perspectives.all(), 1):
        if not pp.discarded:
            pp_index[pp._id] = i
    return pp_index


def find_nexus_for_cycle(cycle) -> Optional[Nexus]:
    """Find the Nexus that owns a Cycle's perspectives."""
    pps = cycle.perspectives
    if not pps:
        return None
    nexus_result = pps[0].nexus.get()
    if nexus_result:
        return nexus_result[0]
    return None


def find_nexus_for_wheel(wheel) -> Optional[Nexus]:
    """Find the Nexus that owns a Wheel (via its parent Cycle or perspectives)."""
    cycle_result = wheel.cycle.get()
    if cycle_result:
        return find_nexus_for_cycle(cycle_result[0])
    pps = wheel._perspectives
    if pps:
        nexus_result = pps[0].nexus.get()
        if nexus_result:
            return nexus_result[0]
    return None


def find_nexus_for_transformation(tr) -> Optional[Nexus]:
    """Find the Nexus for a Transformation (direct relationship)."""
    nexus_result = tr.nexus.get()
    if nexus_result:
        return nexus_result[0]
    return None


def component_alias(stmt, pp_index: Optional[dict[int, int]] = None) -> str:
    """
    Resolve a statement (component) to its display alias.

    If pp_index is provided, produces nexus-indexed labels like 'T1-', 'A2+'.
    If pp_index is None, produces perspective-local labels like 'T-', 'A+'.
    """
    from dialectical_framework.graph.repositories.perspective_repository import (
        PerspectiveRepository,
    )

    pp_repo = PerspectiveRepository()
    for pp, rel_type in pp_repo.find_by_statement(stmt):
        base = _REL_TYPE_TO_LABEL.get(rel_type, rel_type)
        if pp_index is not None:
            idx = pp_index.get(pp._id, 0)
            if idx:
                if len(base) == 2 and base[1] in "+-":
                    return f"{base[0]}{idx}{base[1]}"
                return f"{base}{idx}"
        return base
    return "?"


def format_edge_label(edge, pp_index: Optional[dict[int, int]] = None) -> str:
    """Format 'source → target' for a Transition (wheel edge or position)."""
    source_result = edge.source.get()
    target_result = edge.target.get()
    if not source_result or not target_result:
        return ""

    src = component_alias(source_result[0], pp_index)
    tgt = component_alias(target_result[0], pp_index)
    return f"{src} → {tgt}"


def format_spiral(wheel, pp_index: Optional[dict[int, int]] = None) -> str:
    """Format the wheel's discrete spiral pairs: T1- → A2+, A2+ → A1-, ..."""
    ordered_edges = wheel.edges
    if not ordered_edges:
        return ""

    pairs = []
    for edge in ordered_edges:
        label = format_edge_label(edge, pp_index)
        if label:
            pairs.append(label)

    return ", ".join(pairs)


# --- Decision grounds ---------------------------------------------------

# Ground-role vocabulary: role key → human-readable label. The single owning
# constant — GroundLink descriptions, GRAPH_SCHEMA prose, the coherence-check
# prompt, and both renderers (_dump_decisions, _inspect_decision) must all
# agree with THIS dict, never re-type it. A role exists iff a consumer
# branches on it; plain grounds carry role=None and render as "ground".
#: Stable lead-in for the condition clause appended to an `accepted_cost`
#: ground. Machine-strippable on purpose: consumers that compare a ledger
#: against a reply (the bench's citation scorer) must be able to isolate the
#: cost text itself, so the clause is a suffix behind one owning marker rather
#: than woven into the sentence.
ACCEPTED_COST_CONDITION_MARKER = " — arises when "

DECISION_GROUND_ROLES: dict[str, str] = {
    "accepted_cost": "accepted cost",
    "adopted_pathway": "adopted pathway",
}


def one_line(text: Optional[str]) -> str:
    """Collapse text to a single line for structured-dump fields.

    Dump sections have line-oriented structure the LLM is taught to parse
    (e.g. `Stance: ...` in # Decisions) — raw newlines in user-supplied text
    would let content fabricate sibling lines/entries (ledger injection).
    """
    return " ".join((text or "").split())


#: Lead-in for the case particulars a node was abstracted from.
#: Phrased as evidence ("came in as") rather than as a claim, so the model
#: treats it as facts to check against, not as another assertion to defend.
GROUNDING_PREFIX = "Grounded in: "


def grounding_line(node) -> Optional[str]:
    """The grounding note attached to `node`, or None.

    Reads `Rationale` nodes whose EXPLAINS edge carries
    `role == ROLE_GROUNDING`. Untagged rationales are machine assessment prose
    (control-statement checks, causality reasoning) and are deliberately NOT
    returned — rendering those in the counsel dump would bury the tetrad in
    CC/DV scoring text on every turn.

    Shared by `dialectical_context` and `inspect_node` for the same reason
    `build_pp_index` is shared: two renderers filtering on a role by hand drift
    apart, and a grounding that shows in one view but not the other reads as
    data loss.

    Multiple notes accrete (a person reveals more later) and are joined oldest
    first, so the note reads as a chronology of what was learned when. Fail-soft:
    an unreadable relationship yields None rather than breaking the dump.
    """
    from dialectical_framework.graph.relationships.explains_relationship import \
        ROLE_GROUNDING

    try:
        rationales = node.rationales.all()
    except Exception:  # noqa: BLE001
        return None

    notes: list[tuple[float, str]] = []
    for rationale, rel in rationales:
        if getattr(rel, "role", None) != ROLE_GROUNDING:
            continue
        text = one_line(getattr(rationale, "text", ""))
        if text:
            notes.append((getattr(rationale, "committed_at", 0.0) or 0.0, text))

    if not notes:
        return None

    notes.sort(key=lambda pair: pair[0])
    return GROUNDING_PREFIX + " ".join(text for _at, text in notes)


def decision_ground_line(
    node,
    role: Optional[str],
    show_type: bool = False,
    siblings: Optional[list] = None,
) -> str:
    """One-line rendering of a Decision ground for ledger/inspect output.

    Grounds are heavyweight nodes (a Perspective's __str__ is a multi-line
    block) — the ledger needs a compact single line per ground, so this
    selects a compact FORMAT per type (format selection, not truncation:
    full detail stays one inspect_node away via the hash).

    `siblings` are the OTHER nodes grounding the same decision. They exist only
    to disambiguate an `accepted_cost` condition: a shared minus sits in several
    perspectives, and if one of them is also a ground of this decision, that one
    is the tension the person actually decided on. Callers that render a
    decision's grounds should pass them; callers rendering a lone node can't and
    needn't.
    """
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.wheel import Wheel

    label = DECISION_GROUND_ROLES.get(role or "", "ground")
    flag = " — since discarded" if getattr(node, "discarded", None) else ""

    if isinstance(node, Perspective):
        text = f"{node:positions:0}"
    elif isinstance(node, Wheel):
        # Wheel.__str__ opens with a tabulate section header — the spiral
        # sequence is the one-line summary that actually names the
        # arrangement. Index the aliases (T1-/T2-) via the owning nexus so
        # sibling arrangements stay distinguishable; the hash disambiguates
        # when no nexus is found.
        nexus = find_nexus_for_wheel(node)
        pp_index = build_pp_index(nexus) if nexus else None
        text = format_spiral(node, pp_index) or f"{node!r}"
    else:
        # Statements are single-line already; Transformations/Syntheses
        # summarize as their first line (Ac/Re structure / S+ headline).
        text = str(node).strip().split("\n")[0]

    type_part = f" ({node.__class__.__name__})" if show_type else ""
    if role == "accepted_cost":
        text = f"{one_line(text)}{accepted_cost_condition(node, siblings=siblings)}"
    # one_line: embedded newlines in node text must not fabricate sibling
    # dump lines (see one_line docstring).
    return f"- {label}: [[{node.short_hash}]]{type_part} {one_line(text)}{flag}"


def accepted_cost_condition(node, siblings: Optional[list] = None) -> str:
    """The control statement's condition, appended to an accepted-cost ground.

    A bare minus is a named bad outcome; the control statement is the same
    fact with the condition that produces it, which is what makes it usable at
    re-audit time. Compare:

        "accounts may follow him out"
        "accounts may follow him out — arises when buying him out is pursued
         without diversifying the client relationships"

    Only the second lets the person tell "the risk I accepted, and I am not
    currently paying it" from "the thing now happening to me". Variant (a) of
    the wobble ("reassure me from the record") turns entirely on that
    distinction, and a ledger of bare minuses cannot make it.

    Derived, never generated: the condition is the chosen side's own pole
    ("without" the opposing plus), read structurally off the perspective the
    aspect already sits in. No LLM call, no new node — same reasoning as
    deriving the cost position from the chosen side.

    This renders the paper's NEUTRAL-T variant of the control statement — "T
    without A+ yields T-" [P0 p.29], with its truth criterion "T is true iff it
    fosters A+" — not the primary aspect-level form "T+ without A+ yields T-"
    [P0 p.5] that ConceptualCoherenceEstimation and DialecticalValidityEstimation
    score. Both are the theory's (docs/theory/generative-rules.md Rule 3.3); the
    neutral-T level is the right one for a ledger because what the person
    committed to is the SIDE, not its idealised plus, and the price arrives
    precisely when they hold the side and don't pay A+.

    Do not "fix" one form into the other. They sit at different developmental
    levels and have different jobs: CC/DV score whether the tetrad's aspects
    cohere, this states the condition under which a committed side extracts its
    price. The neutral-T variant's other encoding site is `ASPECT_DEFINITIONS`
    (concerns/scoring_scales.py, "What T itself degenerates into when A+ is
    absent") — keep the three in agreement.

    Returns "" for anything that is not a minus aspect of a locatable
    perspective — the ground is still worth rendering plain, and a half-derived
    condition would be worse than none.

    Ambiguity is the common case, not the exception. A minus aspect is shared
    across perspectives whenever `commit()` dedup finds the same wording, and a
    real session anchors several adjacent tensions on one theme: measured on the
    live anchor path, 3 well-separated tensions shared nothing (6/6 conditions
    rendered) but 5 adjacent ones shared 7 of 10 minus aspects (0 of those 7
    rendered) — which is why `claim2-weak-r5` recorded 5 risk-grounded costs and
    not one condition. So `siblings` (the decision's OTHER grounds) is consulted
    first: if exactly one of the candidate perspectives is itself a ground of
    this decision, that is the tension the person decided on, and no guessing is
    involved. Only when the siblings settle nothing does the single-candidate
    rule apply.
    """
    from dialectical_framework.graph.nodes.statement import Statement

    if not isinstance(node, Statement):
        return ""
    try:
        from dialectical_framework.graph.repositories.perspective_repository import (
            PerspectiveRepository,
        )

        # A shared Statement can sit at several positions across perspectives
        # (driver._ground_position records "A/A-" for exactly this). Render a
        # condition only when the reading is unambiguous: picking one of two
        # perspectives arbitrarily would attribute the person's accepted price
        # to a tension they never decided on.
        found = [
            (pp, rel_type)
            for pp, rel_type in PerspectiveRepository().find_by_statement(node)
            if rel_type in ("T_MINUS", "A_MINUS")
        ]
        if len(found) != 1:
            # Shared minus: let the decision's own other grounds pick the
            # perspective. A decision grounded on both a tension and its price
            # names them together, so the overlap is evidence, not a heuristic.
            sibling_ids = {
                s._id for s in (siblings or []) if getattr(s, "_id", None) is not None
            }
            found = [
                (pp, rel_type)
                for pp, rel_type in found
                if pp._id in sibling_ids
            ] or found
        if len(found) != 1:
            return ""
        pp, rel_type = found[0]
        if rel_type == "T_MINUS":
            held, remedy = pp.polarity.get(), pp.a_plus
            side = "t"
        else:
            held, remedy = pp.polarity.get(), pp.t_plus
            side = "a"
        if not held:
            return ""
        polarity, _ = held
        held_result = getattr(polarity, side).get()
        remedy_result = remedy.get()
        if not held_result or not remedy_result:
            return ""
        held_node, _ = held_result
        remedy_node, _ = remedy_result
        # `:short`, NOT str(): a Statement's default format is text PLUS its
        # rationale's explanation, and one_line() collapses that into the ledger
        # rather than dropping it. Measured — the first live run rendered a
        # 300-word COMPLEX-classification essay inside the condition clause.
        # The ground's own text uses the same short reading (first line only).
        return (
            f"{ACCEPTED_COST_CONDITION_MARKER}"
            f"{one_line(f'{held_node:short}')} is held without "
            f"{one_line(f'{remedy_node:short}')}"
        )
    except Exception:  # noqa: BLE001
        # Rendering a ledger must never fail on a decoration.
        return ""
