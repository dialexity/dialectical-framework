"""
Shared rendering utilities for graph nodes.

Provides consistent alias computation and formatting used by both
dialectical_context (compact dump) and inspect_node (verbose detail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel

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


def pathway_line(tr, pp_index: Optional[dict[int, int]] = None) -> Optional[str]:
    """One pickable line for a Transformation: hash, edge, and its Ac+/Re+ text.

    A bare hash list is not a menu. `adopted_pathway` asks the model to name ONE
    Transformation as the person's ongoing recipe, and it can only do that if it
    can tell the pathways apart — so the identifier travels WITH the recipe.
    Ac+/Re+ only: those two ARE the circular causality (Rule 5.1, T-→A+ and
    A-→T+ simultaneously), so they are what gets adopted; Ac-/Re- are the
    degradation modes and belong to the trap-naming, not to a menu of recipes.
    """
    edge_result = tr.edge.get()
    edge_label = format_edge_label(edge_result[0], pp_index) if edge_result else ""

    recipe = []
    for position, manager in (("Ac+", tr.ac_plus), ("Re+", tr.re_plus)):
        result = manager.get()
        if not result:
            continue
        transition, _ = result
        text = one_line(transition.instruction or transition.summary or "")
        if text:
            recipe.append(f"{position}: {text}")
    if not recipe:
        return None

    head = f"[[{tr.short_hash}]]"
    if edge_label:
        head += f" ({edge_label})"
    return f"{head} — " + " | ".join(recipe)


# --- Completeness (derived status, never stored) -------------------------
#
# `explore`/`deepen` take minutes on their heavy turns, so users close the tab
# mid-build and an interrupted build is a common state, not an edge case.
# Everything below DERIVES how far a build got, on read, from the graph itself —
# no progress counter, no new node field, nothing to keep in sync. Reopening a
# session therefore reports honest status for free.


@dataclass(frozen=True)
class WheelCompleteness:
    """How many of a wheel's expected Transformations exist, and what's missing.

    `expected` is `len(edges) × len(INSIGHT_CATEGORIES)` — the 6N cardinality
    (see `docs/graph.md`), because `ActionExtraction` yields one Ac+ candidate
    per insight category and Phase 2 builds a tetrad per candidate.

    `done` counts ROWS per edge (clamped to the per-edge share), not distinct
    insight bands. Reading bands here would cost one relationship read per
    Transformation on a path that renders every wheel of a nexus, and it is
    unnecessary because band uniqueness is enforced where the write happens:
    `ExploreTransformations._only_missing` keeps at most one candidate per band,
    so an edge cannot accumulate two Transformations in the same band.
    """

    done: int = 0
    expected: int = 0
    #: Edge labels that carry fewer than `len(INSIGHT_CATEGORIES)` Transformations
    #: but could still be developed — what a `deepen` call would top up.
    incomplete_edges: list[str] = field(default_factory=list)
    #: Edge labels where no Transformation can be built yet — either this edge's
    #: own source/target segment is unfinished, or its PAIR PARTNER's is. The
    #: partner half matters because a tetrad needs an Ac+ from both edges of the
    #: pair, so a workable edge opposite an unfinished one is just as stuck.
    #: Named rather than silently absent, and kept out of `incomplete_edges` so
    #: nothing invites a `deepen` that cannot possibly help.
    blocked_edges: list[str] = field(default_factory=list)

    @classmethod
    def from_edge_counts(cls, counts: list[int]) -> WheelCompleteness:
        """Build from per-edge Transformation counts alone, no labels.

        For callers that already hold the counts (`present_exploration` groups
        them while rendering) — the clamp and the denominator live in one place
        so a second surface cannot compute the fraction differently.
        """
        from dialectical_framework.concerns.ac_re_taxonomy import \
            INSIGHT_CATEGORIES

        per_edge = len(INSIGHT_CATEGORIES)
        return cls(
            done=sum(min(c, per_edge) for c in counts),
            expected=len(counts) * per_edge,
        )

    @property
    def is_complete(self) -> bool:
        """True when every expected Transformation exists.

        A wheel with no edges is not "complete" — it is malformed, and calling
        it complete would hide that.
        """
        return self.expected > 0 and self.done >= self.expected

    @property
    def fraction(self) -> str:
        """`"4/6"` — the stamp form, also what `Synthesis.completeness` stores."""
        return f"{self.done}/{self.expected}"


def wheel_completeness(
    wheel: Wheel, pp_index: Optional[dict[int, int]] = None
) -> WheelCompleteness:
    """Count a wheel's Transformations per edge against the expected 6N.

    `pp_index` only labels the missing edges (T1- → A2+ rather than a hash); it
    is derived from the wheel's nexus when not supplied.

    Fail-soft like the repository reads: an edge whose segments can't be
    resolved counts as blocked rather than raising, so status rendering never
    takes down the dump it decorates.
    """
    from dialectical_framework.concerns.ac_re_taxonomy import INSIGHT_CATEGORIES
    from dialectical_framework.graph.repositories.transformation_repository import \
        TransformationRepository
    from dialectical_framework.utils.order_transitions import \
        pair_opposite_edges

    edges = wheel.edges
    if not edges:
        return WheelCompleteness()

    per_edge = len(INSIGHT_CATEGORIES)
    # One query for the whole wheel, not one per edge: this runs on every wheel
    # of a counsel-mode dump, which is exempt from the wheel cap.
    counts = TransformationRepository().count_by_edges(edges)
    if pp_index is None:
        nexus = find_nexus_for_wheel(wheel)
        if nexus:
            pp_index = build_pp_index(nexus)

    def _buildable(edge: Transition) -> bool:
        source = edge.get_source_wheel_segment()
        target = edge.get_target_wheel_segment()
        return bool(
            source and target and source.is_complete() and target.is_complete()
        )

    # Buildability is a property of the PAIR, matching the builder: an edge is
    # stuck if its own segments are unfinished OR its partner's are, because a
    # tetrad pairs the two edges' Ac+ candidates.
    stuck: set[int] = set()
    paired: set[int] = set()
    for edge_a, edge_b in pair_opposite_edges(edges):
        paired.update(e._id for e in (edge_a, edge_b) if e._id is not None)
        if not _buildable(edge_a) or not _buildable(edge_b):
            stuck.update(
                e._id for e in (edge_a, edge_b) if e._id is not None
            )
    # An edge in no pair (a malformed wheel with an odd edge count) is stuck by
    # construction — the builder only ever iterates pairs.
    stuck.update(
        e._id for e in edges if e._id is not None and e._id not in paired
    )

    done = 0
    incomplete: list[str] = []
    blocked: list[str] = []
    for edge in edges:
        found = counts.get(edge._id, 0) if edge._id is not None else 0
        # An edge cannot count more than its share, or a category-skewed edge
        # would inflate the wheel's progress past its own denominator.
        done += min(found, per_edge)
        if found >= per_edge:
            continue

        label = format_edge_label(edge, pp_index) or edge.short_hash
        if edge._id is None or edge._id in stuck:
            blocked.append(label)
        else:
            incomplete.append(label)

    return WheelCompleteness(
        done=done,
        expected=len(edges) * per_edge,
        incomplete_edges=incomplete,
        blocked_edges=blocked,
    )


def completeness_line(
    wheel: Wheel,
    pp_index: Optional[dict[int, int]] = None,
    *,
    numeric: bool = True,
) -> Optional[str]:
    """One status line for a partly-built wheel, or None when it is finished.

    `numeric` sets the register, in code rather than by prompt discipline:
    the Navigator and counsel mode get counts and edge labels because the
    exploration is on screen and is the person's own deliverable; the
    standalone Advisor gets plain words with no digits and no framework nouns,
    because there the machinery is invisible by design.

    Returns None on a complete wheel — status is only worth saying when there
    is something outstanding.
    """
    completeness = wheel_completeness(wheel, pp_index)
    if completeness.expected == 0 or completeness.is_complete:
        return None

    if not numeric:
        if completeness.done == 0:
            if completeness.blocked_edges:
                return "Not yet worked through — parts of this are still unformed."
            return "Not yet worked through."
        if completeness.blocked_edges:
            return (
                "Partly worked through — some of it is still unformed, "
                "so a few angles are missing."
            )
        return "Partly worked through — a few angles are still missing."

    line = f"Pathways: {completeness.fraction}"
    if completeness.done == 0:
        # Never deepened is not the same as interrupted, and the numeric line is
        # where that distinction is most load-bearing: `explore` deepens exactly
        # one wheel by design (EXPLORE_DEEP_WHEELS), so counsel mode dumps every
        # other wheel at 0/N. Left as a bare shortfall the model reads a working
        # budget as a broken build and offers to repair it.
        line += " (not yet developed"
        if completeness.blocked_edges and not completeness.incomplete_edges:
            line += ", and cannot be until its segments are finished"
        line += ")"
        return line
    if completeness.incomplete_edges:
        line += f" (incomplete: {', '.join(completeness.incomplete_edges)})"
    if completeness.blocked_edges:
        line += f" (blocked, segments unfinished: {', '.join(completeness.blocked_edges)})"
    return line


#: Derived polarity states. `not_developed` vs `set_aside` is the distinction
#: that was invisible: both look like "a polarity with no perspectives", but one
#: is work the user lost and the other is a deliberate gate outcome.
POLARITY_NOT_DEVELOPED = "not_developed"
POLARITY_SET_ASIDE = "set_aside"
POLARITY_PARTIAL = "partial"
POLARITY_DEVELOPED = "developed"


def polarity_completeness(
    polarity: Polarity,
    *,
    hs_threshold: float = 0.7,
) -> str:
    """Classify how far a polarity got, without storing anything.

    `AnalysisPipeline._rank_polarities` expands only polarities at or above
    `HS_THRESHOLD`, so an empty polarity means two different things: below the
    threshold it was deliberately set aside; at or above it, the expansion was
    supposed to happen and didn't — a crash, not a judgement. Callers pass
    `analyst.HS_THRESHOLD`; the default repeats it only so this module stays
    importable without pulling in the analyst.

    An unscored polarity (HS None) reads as `set_aside` rather than lost work:
    claiming interrupted work on no evidence would send the user chasing a
    build that was never started.
    """
    from dialectical_framework.graph.repositories.perspective_repository import \
        PerspectiveRepository

    perspectives = [
        pp
        for pp in PerspectiveRepository().find_by_polarity(polarity)
        if not pp.discarded
    ]
    complete = [pp for pp in perspectives if pp.is_complete()]
    if complete:
        return POLARITY_DEVELOPED if len(complete) == len(perspectives) else POLARITY_PARTIAL
    if perspectives:
        # Something was started and never finished — unambiguously interrupted,
        # whatever the HS says.
        return POLARITY_PARTIAL

    hs = polarity.heuristic_similarity
    if hs is not None and hs >= hs_threshold:
        return POLARITY_NOT_DEVELOPED
    return POLARITY_SET_ASIDE


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
    not one condition. So `siblings` (the decision's OTHER grounds) decides:
    when the record grounds a Perspective, THAT is the tension the person
    decided on and the condition comes from it or from nowhere. The
    single-candidate rule applies only to records that name no perspective at
    all.
    """
    from dialectical_framework.graph.nodes.perspective import Perspective
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
        # A decision grounded on both a tension and its price names them
        # together, so a cited Perspective is EVIDENCE, not a heuristic — and it
        # is authoritative, not a tie-breaker. Consulting siblings only when the
        # minus was ambiguous meant a unique minus rendered its own tetrad's
        # condition even when the record cited a different one: with P1's `T-`
        # as the price and P2 as the tension, the ledger read out P1's poles
        # under P2's name. `RecordDecision._ground_set_inconsistency` refuses to
        # WRITE that now; archived records still exist, and a condition drawn
        # from a tetrad the record does not name is worse than none.
        sibling_pp_ids = {
            s._id
            for s in (siblings or [])
            if isinstance(s, Perspective) and getattr(s, "_id", None) is not None
        }
        if sibling_pp_ids:
            found = [(pp, rel_type) for pp, rel_type in found if pp._id in sibling_pp_ids]
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
