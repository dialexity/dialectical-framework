"""
Typed, JSON-ready views of graph structure — for a SCREEN, not for a prompt.

`rendering.py` next door renders for the LLM: prose that lands inside a prompt,
where a truncated text or an absent score is a reasoning defect. This module
renders for a host that draws pictures — a widget in a chat, a side pane, a
tension map. Different consumer, different rules, so a separate module:

- **Frozen dataclasses, JSON-ready.** `to_dict()` yields only str / float /
  bool / None / list / dict, so a host can serialize it and hand it to a
  visualiser in another process or another language.
- **Absence is explicit and it is `None`.** Every uncomputed quantity — an
  unscored aspect, an unaudited wheel, an unvalidated tetrad — is `None`, never
  a zero and never a sentinel. `explorer._causality_probability` returns `-1.0`
  for a missing estimation because it RANKS; a view must not, because a widget
  would draw the sentinel. The two contracts are deliberately different: do not
  unify them.
- **Structure is always present; TERMINOLOGY is optional.** See below.
- **Nothing is truncated.** Same rule as `__str__` on the nodes: the host
  decides what fits on screen, and it cannot decide that from a string somebody
  already cut.

WHAT THE KEYS MEAN AND WHY THEY ARE SAFE
========================================
The field names (`t_plus`, `a_minus`, `diagonals`) are the RENDERER's
vocabulary: they tell a visualiser which pole to draw where and which pairs to
join with a contradiction line. They are never printed to a person. What IS
printable lives in three fields per pole — `text` (the person's own words),
`position` (`"T+"`, framework terminology) and `label` (the stored alias,
`"T1+"` or a domain alias). So a picture can be drawn correctly without any
framework vocabulary appearing on it.

`without_terminology()` is that projection, and it exists because the framework
already strips the same class of thing from person-facing TEXT
(`agents/advisor/reply_hygiene.py` removes `[[hash]]` wherever the composed
preamble does not grant terminology disclosure). A widget that shipped `T+` and
a hash into a standalone-Advisor conversation would reinstate, in pixels,
exactly what that filter removes from prose. Two enforcement points, ONE policy:
the host reads `Advisor.hides_terminology` — the same flag the text filter reads
— and calls `without_terminology()` when it is true. What the projection drops:
positions, aliases, hashes and every number. What survives: the texts, the axis
names the tension is read along, and the full structure. The result is also the
shape a graphless surface can reach on its own (the `Consultant` has no scores
and no hashes to give), so one visualiser serves both.

COST
====
A tetrad view is ~20 relationship reads (six poles plus the five metric
properties, each of which re-reads its aspects — called rather than re-derived,
because `Perspective.area` / `rectangularity` are the single owners of formulas
that carry "do not fix this" notes). That is priced for a user-triggered widget,
not for a per-turn dump. A caller drawing many tetrads at once should
`RelationshipManager.prefetch` first.

NOT IN HERE, DELIBERATELY
=========================
Transformations (pathways). A wheel picture is its segments, its spiral and its
synthesis; the Ac+/Re+ recipes are a different widget with a different shape
(text and feasibility bands, no geometry), and `rendering.pathway_line` already
serves the prompt side. Add a `PathwayView` when a host actually draws one.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Optional

from dialectical_framework.graph.nodes.perspective import (POSITION_A,
                                                           POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.wheel import Wheel

logger = logging.getLogger(__name__)

#: Lead-in `expand_polarities._compose_reading` writes before the axes. Parsed
#: back out here so a widget can show the axes as axes (two labelled ends of a
#: line) rather than reprinting a sentence. Kept in sync by
#: `tests/test_views.py::TestTheReadingIsParsedBack`.
READING_PREFIX = "Reading along: "
#: Separator between the two axes inside a reading.
READING_SEPARATOR = " / "

#: View field name → canonical position, in the order a tetrad is drawn.
_TETRAD_POSITIONS: tuple[tuple[str, str], ...] = (
    ("t", POSITION_T),
    ("a", POSITION_A),
    ("t_plus", POSITION_T_PLUS),
    ("t_minus", POSITION_T_MINUS),
    ("a_plus", POSITION_A_PLUS),
    ("a_minus", POSITION_A_MINUS),
)


# --- Poles ---------------------------------------------------------------


@dataclass(frozen=True)
class PoleView:
    """One position of a tetrad: what it says, and what is known about it.

    `text` is what a person reads — the statement's `display_text` when a host
    set one, else its canonical text (the same precedence `Statement.prompt_text`
    uses). `canonical_text` is filled only when the two differ, so a host can
    show the override and still tell what it overrides.
    """

    #: What to render. Never truncated.
    text: str
    #: The canonical text, when `text` is a host-set display override.
    canonical_text: Optional[str] = None
    #: Framework terminology: "T", "A", "T+", "T-", "A+", "A-".
    position: Optional[str] = None
    #: The alias stored on the edge — "T1+", or a domain alias the app chose.
    label: Optional[str] = None
    #: Full node hash. The address for `inspect_node`, a click-through, a focus
    #: request. Full, not short: a host should not have to reassemble it.
    hash: Optional[str] = None
    #: Heuristic Similarity to the taxonomy apex. None = not scored.
    hs: Optional[float] = None
    #: Complementarity toward the thesis / the antithesis. None = not scored.
    k_t: Optional[float] = None
    k_a: Optional[float] = None
    #: Ks = (k_t + k_a) / 2, as the edge computes it. Carried as a field rather
    #: than a property so it survives `to_dict()`.
    ks: Optional[float] = None

    def without_terminology(self) -> PoleView:
        """The same pole with everything a hidden-machinery surface must not show."""
        return dataclasses.replace(
            self, position=None, label=None, hash=None, hs=None, k_t=None,
            k_a=None, ks=None,
        )


@dataclass(frozen=True)
class DiagonalView:
    """One of the two contradiction pairs, as field names plus its axis.

    The theory's diagonal constraint (T+ contradicts A-, T- contradicts A+) is
    what makes a tetrad a tetrad, and it is geometry a widget must draw — so it
    is stated here rather than left for the host to hardcode. `positive` and
    `negative` name FIELDS of `TetradView`, not text to print.
    """

    positive: str
    negative: str
    #: The single dimension the pair sits at opposite ends of, when the
    #: generation captured one (it travels in `Perspective.intent`).
    axis: Optional[str] = None


@dataclass(frozen=True)
class TetradMetricsView:
    """A tetrad's quality numbers, each independently None when it cannot be
    computed — an unfinished tetrad missing A- still has a real T-side gap
    (`diff_t`), and suppressing it would hide the half that IS known. The whole
    view is None only when nothing at all is scored.

    `sp` is the theory's Synthesis Potential and the code's `area` — one
    quantity, two names (docs/theory/scoring.md). Named `sp` here because a host
    drawing a chart should use the theory's name; `sp_normalized` is the ~0-1
    rescale `Perspective.area_normalized` exists for, which is UI-only and has
    no gate behind it anywhere.
    """

    sp: Optional[float] = None
    sp_normalized: Optional[float] = None
    rectangularity: Optional[float] = None
    diff_t: Optional[float] = None
    diff_a: Optional[float] = None


@dataclass(frozen=True)
class TetradView:
    """One Perspective as a drawable tetrad.

    A pole is `None` when the position is not connected — an interrupted build
    is a real and common state (`explore` takes minutes and people close tabs),
    and an empty-string pole would draw as a tetrad with a blank corner rather
    than as a tetrad that is not finished yet.
    """

    t: Optional[PoleView] = None
    a: Optional[PoleView] = None
    t_plus: Optional[PoleView] = None
    t_minus: Optional[PoleView] = None
    a_plus: Optional[PoleView] = None
    a_minus: Optional[PoleView] = None
    #: The two contradiction pairs. Always both, even on an unfinished tetrad:
    #: the geometry is structural, not a function of what got built.
    diagonals: list[DiagonalView] = field(default_factory=list)
    #: `Perspective.intent` verbatim — "Reading along: growth / security".
    reading: Optional[str] = None
    #: The axes parsed out of `reading`; empty when there is no reading or it
    #: does not use the framework's own phrasing.
    axes: list[str] = field(default_factory=list)
    #: Full Perspective hash.
    hash: Optional[str] = None
    #: The nexus-stable index — 1 where the prompts say T1. None outside a nexus.
    index: Optional[int] = None
    metrics: Optional[TetradMetricsView] = None
    #: "passed" / "failed: <reasons>" / None = not validated. Never a gate: a
    #: failed tetrad is still in the graph and still drawable.
    validation: Optional[str] = None
    #: The discard reason, when this tetrad was set aside.
    discarded: Optional[str] = None
    #: True when all six positions are connected.
    complete: bool = False

    @property
    def poles(self) -> dict[str, PoleView]:
        """The connected poles by field name — for a renderer that iterates."""
        return {
            name: pole
            for name, _position in _TETRAD_POSITIONS
            if (pole := getattr(self, name)) is not None
        }

    def without_terminology(self) -> TetradView:
        projected = {
            name: (pole.without_terminology() if pole is not None else None)
            for name, pole in (
                (field_name, getattr(self, field_name))
                for field_name, _position in _TETRAD_POSITIONS
            )
        }
        return dataclasses.replace(
            self,
            **projected,
            hash=None,
            index=None,
            metrics=None,
            validation=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# --- Wheels --------------------------------------------------------------


@dataclass(frozen=True)
class SegmentView:
    """One tetrad in its place on a wheel.

    `orientation` is the wheel's own reading of the tetrad: "swapped" means this
    arrangement puts the tetrad's A side where its T side would otherwise sit
    (`WheelSegmentPolarPair.polarity`). A widget that ignores it draws a wheel
    whose diagonal symmetry does not hold.
    """

    tetrad: TetradView
    #: 0-based place around the circle, in `Wheel.polar_segments` order — which
    #: is load-bearing, not cosmetic (see CLAUDE.md on `Wheel._perspectives`).
    place: int = 0
    orientation: Literal["normal", "swapped"] = "normal"

    def without_terminology(self) -> SegmentView:
        return dataclasses.replace(self, tetrad=self.tetrad.without_terminology())


@dataclass(frozen=True)
class SpiralStepView:
    """One edge of the discrete spiral: a minus of one segment becoming the plus
    of the next.

    Endpoints are resolved against the poles already built for the segments, so
    a step's `source`/`target` carry the same hashes and labels the tetrads do —
    a widget can highlight both ends of a step without a second lookup.
    """

    source: Optional[PoleView] = None
    target: Optional[PoleView] = None
    #: The Transition's own text, when it carries one.
    text: Optional[str] = None
    #: Full Transition hash.
    hash: Optional[str] = None

    def without_terminology(self) -> SpiralStepView:
        return dataclasses.replace(
            self,
            source=self.source.without_terminology() if self.source else None,
            target=self.target.without_terminology() if self.target else None,
            hash=None,
        )


@dataclass(frozen=True)
class SynthesisView:
    """The wheel's S+ / S-, each a pole or None when not generated."""

    s_plus: Optional[PoleView] = None
    s_minus: Optional[PoleView] = None
    #: The "4/6" stamp the synthesis was generated at, when it carries one.
    completeness: Optional[str] = None
    hash: Optional[str] = None

    def without_terminology(self) -> SynthesisView:
        return dataclasses.replace(
            self,
            s_plus=self.s_plus.without_terminology() if self.s_plus else None,
            s_minus=self.s_minus.without_terminology() if self.s_minus else None,
            completeness=None,
            hash=None,
        )


@dataclass(frozen=True)
class WheelView:
    """One Wheel as a drawable arrangement: segments, spiral, synthesis."""

    segments: list[SegmentView] = field(default_factory=list)
    #: Edges in wheel order. `Wheel.edges` is deliberately not memoised, so this
    #: is read fresh (CLAUDE.md, graph-performance).
    spiral: list[SpiralStepView] = field(default_factory=list)
    synthesis: Optional[SynthesisView] = None
    hash: Optional[str] = None
    #: How many tensions this arrangement holds — the wheel's layer.
    layer: int = 0
    #: Causality plausibility P. None = not estimated, never "low".
    causality: Optional[float] = None
    #: Transformations built vs expected, as "4/6". None when there are no
    #: edges to expect any from.
    completeness: Optional[str] = None
    #: True when every expected Transformation exists.
    complete: bool = False

    def without_terminology(self) -> WheelView:
        return dataclasses.replace(
            self,
            segments=[s.without_terminology() for s in self.segments],
            spiral=[s.without_terminology() for s in self.spiral],
            synthesis=(
                self.synthesis.without_terminology() if self.synthesis else None
            ),
            hash=None,
            causality=None,
            completeness=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class TensionMapView:
    """Several tetrads seen at once — an exploration's members, or everything
    active in the case.

    This is the "where does this sit" picture: the blindspot app's A+ is one
    pole of one tetrad in here, and what makes it legible is the others around
    it.
    """

    tetrads: list[TetradView] = field(default_factory=list)
    #: The exploration this map is of, when it is of one.
    nexus_hash: Optional[str] = None

    def without_terminology(self) -> TensionMapView:
        return dataclasses.replace(
            self,
            tetrads=[t.without_terminology() for t in self.tetrads],
            nexus_hash=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# --- Readers -------------------------------------------------------------


def _statement_texts(stmt: Statement) -> tuple[str, Optional[str]]:
    """(what to render, the canonical text when it differs)."""
    canonical = stmt.text or ""
    display = stmt.display_text or canonical
    return display, (canonical if display != canonical else None)


def _pole_from(stmt: Statement, rel: Any, position: Optional[str]) -> PoleView:
    text, canonical = _statement_texts(stmt)
    return PoleView(
        text=text,
        canonical_text=canonical,
        position=position,
        label=getattr(rel, "alias", None),
        hash=stmt.hash,
        hs=getattr(rel, "heuristic_similarity", None),
        k_t=getattr(rel, "complementarity_t", None),
        k_a=getattr(rel, "complementarity_a", None),
        ks=getattr(rel, "complementarity_s", None),
    )


def _pole(pp: Perspective, position: str) -> Optional[PoleView]:
    """One position of a perspective, or None when it is not connected.

    Fail-soft per position rather than per tetrad: a build interrupted before
    its aspects landed is a common state, and the four corners that exist are
    worth drawing — the alternative is a widget that shows nothing because one
    edge is missing.

    With no Polarity connected at all nothing is readable, not even an aspect:
    the position lookup itself reaches through the Polarity
    (`Perspective.get_relationship_manager_by_position` resolves every position
    eagerly, and `pp.t` raises). That yields an empty tetrad rather than an
    exception, which is the right end for a host — and it is not a state the
    build path produces, since the Polarity is created before the Perspective.
    """
    try:
        manager = pp.get_relationship_manager_by_position(position)
        result = manager.get()
    except ValueError:
        return None
    except Exception:  # noqa: BLE001
        logger.exception("Could not read %s of perspective %s", position, pp.hash)
        return None
    if not result:
        return None
    stmt, rel = result
    return _pole_from(stmt, rel, position)


def _metrics(pp: Perspective) -> Optional[TetradMetricsView]:
    """The tetrad's numbers, or None when nothing is scored at all.

    Each value comes from the Perspective property that owns its formula — `sp`
    from `area`, never re-derived here.
    """
    try:
        metrics = TetradMetricsView(
            sp=pp.area,
            sp_normalized=pp.area_normalized,
            rectangularity=pp.rectangularity,
            diff_t=pp.diff_t,
            diff_a=pp.diff_a,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not read metrics of perspective %s", pp.hash)
        return None
    if all(value is None for value in dataclasses.astuple(metrics)):
        return None
    return metrics


def parse_reading(reading: Optional[str]) -> list[str]:
    """The axes inside a `Perspective.intent`, or [] when it holds none.

    An intent is free text — a user-set reading, or an older perspective from
    before readings were composed — so anything that is not the framework's own
    phrasing yields no axes rather than a guess.
    """
    if not reading or not reading.startswith(READING_PREFIX):
        return []
    body = reading[len(READING_PREFIX):].strip()
    if not body:
        return []
    return [part.strip() for part in body.split(READING_SEPARATOR) if part.strip()]


def tetrad_view(
    perspective: Perspective, pp_index: Optional[dict[int, int]] = None
) -> TetradView:
    """One Perspective as a `TetradView`.

    `pp_index` is `rendering.build_pp_index(nexus)` — pass it so the picture's
    numbering matches the prompts' (T1 means the same perspective in both). Its
    absence means "no exploration here", not "index unknown".
    """
    poles = {name: _pole(perspective, position) for name, position in _TETRAD_POSITIONS}
    reading = getattr(perspective, "intent", None)
    axes = parse_reading(reading)
    # The axes are ordered as `_compose_reading` wrote them: the T+/A- pair
    # first, then A+/T-. One axis means the generation named a single dimension
    # for both diagonals.
    constructive = axes[0] if axes else None
    reflective = axes[1] if len(axes) > 1 else constructive
    return TetradView(
        **poles,
        diagonals=[
            DiagonalView(positive="t_plus", negative="a_minus", axis=constructive),
            DiagonalView(positive="a_plus", negative="t_minus", axis=reflective),
        ],
        reading=reading,
        axes=axes,
        hash=perspective.hash,
        index=(
            pp_index.get(perspective._id)
            if pp_index is not None and perspective._id is not None
            else None
        ),
        metrics=_metrics(perspective),
        validation=perspective.validation,
        discarded=perspective.discarded,
        complete=all(pole is not None for pole in poles.values()),
    )


def _causality(wheel: Wheel) -> Optional[float]:
    """The wheel's causality P, or None when it was never estimated.

    Deliberately NOT `explorer._causality_probability`, which answers the same
    question with `-1.0` so that an unestimated wheel loses a ranking. A widget
    would draw the sentinel.
    """
    from dialectical_framework.graph.nodes.estimation import \
        CausalityProbabilityEstimation

    try:
        for est, _ in wheel.estimations.all():
            if isinstance(est, CausalityProbabilityEstimation):
                return est.value
    except Exception:  # noqa: BLE001
        logger.exception("Could not read causality of wheel %s", wheel.hash)
    return None


def _synthesis_view(wheel: Wheel) -> Optional[SynthesisView]:
    """The wheel's synthesis, newest first when several exist.

    One wheel means one S+/S-, but a regenerated synthesis leaves the old node
    attached (analytical layer: add/replace, never edit), so the most recently
    committed one is the current reading.
    """
    try:
        found = [syn for syn, _ in wheel.synthesis.all()]
    except Exception:  # noqa: BLE001
        logger.exception("Could not read synthesis of wheel %s", wheel.hash)
        return None
    if not found:
        return None
    found.sort(key=lambda syn: getattr(syn, "committed_at", 0.0) or 0.0, reverse=True)
    synthesis = found[0]

    def _pole_of(manager, position: str) -> Optional[PoleView]:
        try:
            result = manager.get()
        except Exception:  # noqa: BLE001
            return None
        if not result:
            return None
        stmt, rel = result
        return _pole_from(stmt, rel, position)

    return SynthesisView(
        s_plus=_pole_of(synthesis.s_plus, "S+"),
        s_minus=_pole_of(synthesis.s_minus, "S-"),
        completeness=synthesis.completeness,
        hash=synthesis.hash,
    )


def wheel_view(wheel: Wheel, pp_index: Optional[dict[int, int]] = None) -> WheelView:
    """One Wheel as a `WheelView`: its segments in order, its spiral, its synthesis.

    `pp_index` defaults to the owning nexus's, so a wheel drawn on its own still
    numbers its tensions the way the rest of the system does.
    """
    from dialectical_framework.graph.rendering import (build_pp_index,
                                                       find_nexus_for_wheel,
                                                       wheel_completeness)

    if pp_index is None:
        nexus = find_nexus_for_wheel(wheel)
        if nexus is not None:
            pp_index = build_pp_index(nexus)

    segments: list[SegmentView] = []
    # hash → the pole already built for it, so spiral endpoints reuse the
    # segments' own poles instead of a repository lookup per edge.
    by_hash: dict[str, PoleView] = {}
    for place, pair in enumerate(wheel.polar_segments):
        view = tetrad_view(pair.perspective, pp_index)
        segments.append(
            SegmentView(tetrad=view, place=place, orientation=pair.polarity)
        )
        for pole in view.poles.values():
            if pole.hash:
                by_hash.setdefault(pole.hash, pole)

    spiral: list[SpiralStepView] = []
    edges = wheel.edges
    for edge in edges:
        spiral.append(
            SpiralStepView(
                source=_endpoint(edge.source, by_hash),
                target=_endpoint(edge.target, by_hash),
                text=edge.instruction or edge.summary,
                hash=edge.hash,
            )
        )

    completeness = wheel_completeness(wheel, pp_index)
    return WheelView(
        segments=segments,
        spiral=spiral,
        synthesis=_synthesis_view(wheel),
        hash=wheel.hash,
        layer=len(segments),
        causality=_causality(wheel),
        completeness=completeness.fraction if completeness.expected else None,
        complete=completeness.is_complete,
    )


def _endpoint(manager: Any, by_hash: dict[str, PoleView]) -> Optional[PoleView]:
    """A spiral endpoint, preferring the pole the segments already built.

    An endpoint that is not one of the wheel's own segment poles is still
    rendered — from the statement alone, so it carries text and a hash but no
    position. That is the honest reading: a wheel edge pointing outside its own
    segments is malformed, and drawing nothing would hide it.
    """
    try:
        result = manager.get()
    except Exception:  # noqa: BLE001
        return None
    if not result:
        return None
    stmt, _rel = result
    if stmt.hash and stmt.hash in by_hash:
        return by_hash[stmt.hash]
    text, canonical = _statement_texts(stmt)
    return PoleView(text=text, canonical_text=canonical, hash=stmt.hash)


def tension_map_view(nexus: Optional[Nexus] = None) -> TensionMapView:
    """Every active tetrad worth drawing — an exploration's, or the case's.

    With a `nexus`: its members, numbered as the prompts number them. Without:
    every active Perspective in the current scope, which is what a conversation
    that has anchored tensions but explored nothing yet has to show.
    """
    from dialectical_framework.graph.rendering import build_pp_index

    if nexus is not None:
        pp_index = build_pp_index(nexus)
        members = [pp for pp, _ in nexus.perspectives.all() if not pp.discarded]
        return TensionMapView(
            tetrads=[tetrad_view(pp, pp_index) for pp in members],
            nexus_hash=nexus.hash,
        )

    from dialectical_framework.graph.repositories.perspective_repository import \
        PerspectiveRepository

    return TensionMapView(
        tetrads=[tetrad_view(pp) for pp in PerspectiveRepository().find_all_active()]
    )
