"""
An interrupted build must be finishable, and must say that it is unfinished.

`explore`/`deepen` take minutes on their heavy turns, so a user closing the tab
mid-build is the common path. Three defects made that path lossy, and each one
is pinned here:

1. **A half-finished edge could never be finished.** `_process_edge_pair` treated
   any non-empty `find_by_edge` as done, but an edge owes one Transformation per
   insight category. Kill the sequential write loop part-way and the edge counted
   as complete forever. Worse, the *fix* had its own dead spot: a tetrad pairs an
   edge's Ac+ with its partner's Ac+ in the same band, so an edge whose partner
   was already complete had nobody to pair with — and the write loop finishes one
   edge before the other, which makes exactly that the commonest interrupted
   state.
2. **Nothing knew the denominator.** A 4-of-6 wheel rendered identically to a
   6-of-6 one: the dump listed whatever existed. Derived on read
   (`wheel_completeness`), never stored.
3. **Partial synthesis was silently whole.** S+ emerges from ALL Transformations
   simultaneously, so a synthesis built mid-interruption came from a fragment
   with nothing recording that. Stamped (`Synthesis.completeness`), not blocked —
   and the stamp must stay out of the hash, or every existing node's identity
   would change.

Plus the register split: the standalone Advisor speaks completeness in plain
words with no counts; counsel mode (nexus-pinned) gets the numbers.

DB-free and LLM-free — all three defects live in counting and composition, so
the repository reads and the generation calls are patched out.
"""

from __future__ import annotations

from typing import Optional

import pytest

from dialectical_framework.concerns.ac_re_taxonomy import (
    INSIGHT_CATEGORIES,
    INSIGHT_SCALE,
    insight_category_of_label,
    insight_category_of_value,
)
from dialectical_framework.concerns.action_extraction import ActionCandidateResultDto
from dialectical_framework.graph import rendering
from dialectical_framework.graph.rendering import (
    completeness_line,
    wheel_completeness,
)


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


PER_EDGE = len(INSIGHT_CATEGORIES)


# --- Fakes ---------------------------------------------------------------


class _FakeSegment:
    def __init__(self, complete: bool = True) -> None:
        self._complete = complete

    def is_complete(self) -> bool:
        return self._complete


class _FakeManager:
    """Stands in for a bound RelationshipManager on read-only paths."""

    def __init__(self, items: Optional[list] = None) -> None:
        self._items = items or []

    def all(self) -> list:
        return [(item, None) for item in self._items]

    def get(self):
        return (self._items[0], None) if self._items else None


class _FakeEdge:
    _next_id = 100

    def __init__(
        self,
        label: str,
        source: Optional[_FakeSegment] = None,
        target: Optional[_FakeSegment] = None,
    ) -> None:
        self.label = label
        self.hash = f"hash-{label}"
        self.short_hash = f"h-{label}"
        # `wheel_completeness` batches its count by internal edge id, so a fake
        # edge needs a distinct one or every edge reads the same tally.
        _FakeEdge._next_id += 1
        self._id = _FakeEdge._next_id
        self._source = source if source is not None else _FakeSegment()
        self._target = target if target is not None else _FakeSegment()
        self.rationales = _FakeManager()

    def get_source_wheel_segment(self):
        return self._source

    def get_target_wheel_segment(self):
        return self._target


class _FakeTransformation:
    def __init__(self, category: Optional[str] = "Generative") -> None:
        self.insight_category = category
        self.short_hash = "tr00000"
        self.edge = _FakeManager()


class _FakeWheel:
    def __init__(self, edges: list[_FakeEdge], transformations: Optional[list] = None) -> None:
        self.edges = edges
        self.transformations = transformations if transformations is not None else []
        self.hash = "wheelhash"
        self.short_hash = "wheelha"
        self._id = 1
        self._perspectives: list = []
        self.cycle = _FakeManager()
        self.estimations = _FakeManager()
        self.synthesis = _FakeManager()
        self.rationales = _FakeManager()
        self.segments: list = []

    def _format_edges(self, _mode: str) -> str:
        return ""


def _patch_edges(monkeypatch, counts: dict[str, int]) -> None:
    """Give each edge label a number of existing Transformations.

    Patches BOTH repository reads: `_process_edge_pair` reads the rows it needs
    to categorise (`find_by_edge`), while `wheel_completeness` only needs a
    tally and batches it for the whole wheel (`count_by_edges`) — one query per
    wheel on a path that renders every wheel of a nexus. Also patches the edge
    labeller, which would otherwise resolve component aliases through the DB.
    """
    from dialectical_framework.graph.repositories.transformation_repository import \
        TransformationRepository

    def _find_by_edge(self, edge, **_kwargs):
        return [_FakeTransformation() for _ in range(counts.get(edge.label, 0))]

    def _count_by_edges(self, edges, **_kwargs):
        return {edge._id: counts.get(edge.label, 0) for edge in edges}

    monkeypatch.setattr(TransformationRepository, "find_by_edge", _find_by_edge)
    monkeypatch.setattr(TransformationRepository, "count_by_edges", _count_by_edges)
    monkeypatch.setattr(
        rendering, "format_edge_label", lambda edge, pp_index=None: edge.label
    )


# --- Taxonomy helpers ---------------------------------------------------


def test_insight_category_helpers_agree_with_the_scale():
    """Every scale level maps to the category that claims it, by label and by value.

    Resume asks "which bands does this edge already carry?", so a level that
    categorises differently by label than by stored value would make an edge
    look like it owes a band it already has — a duplicate, or a permanent gap.
    """
    declared = {
        level.capitalize(): category
        for category, info in INSIGHT_CATEGORIES.items()
        for level in info["levels"]
    }
    assert set(declared) == set(INSIGHT_SCALE)

    for label, value in INSIGHT_SCALE.items():
        assert insight_category_of_label(label) == declared[label]
        assert insight_category_of_value(value) == declared[label]


def test_insight_category_of_value_snaps_and_never_overclaims():
    # A float that survived a DB round-trip is still read as its own level.
    assert insight_category_of_value(0.5999999) == insight_category_of_label("Leverage")
    # Exactly between two levels resolves DOWN — depth is not claimed beyond
    # what was measured. 0.55 is the load-bearing case: it sits between
    # Composition (0.5, Configurational) and Leverage (0.6, Generative), and
    # under a raw float comparison it promoted itself into the stronger band.
    assert insight_category_of_value(0.55) == insight_category_of_label("Composition")
    assert insight_category_of_value(0.45) == insight_category_of_label("Reformulation")
    assert insight_category_of_value(0.35) == insight_category_of_label("Variation")


def test_insight_category_of_label_rejects_unknown():
    with pytest.raises(ValueError):
        insight_category_of_label("Telepathy")


# --- Denominator ---------------------------------------------------------


def test_wheel_completeness_counts_against_6n(monkeypatch):
    edges = [_FakeEdge("A"), _FakeEdge("B")]
    _patch_edges(monkeypatch, {"A": PER_EDGE, "B": 1})

    c = wheel_completeness(_FakeWheel(edges), pp_index={})

    assert c.expected == 2 * PER_EDGE
    assert c.done == PER_EDGE + 1
    assert c.fraction == f"{PER_EDGE + 1}/{2 * PER_EDGE}"
    assert not c.is_complete
    assert c.incomplete_edges == ["B"]
    assert c.blocked_edges == []


def test_complete_wheel_says_nothing(monkeypatch):
    edges = [_FakeEdge("A"), _FakeEdge("B")]
    _patch_edges(monkeypatch, {"A": PER_EDGE, "B": PER_EDGE})
    wheel = _FakeWheel(edges)

    c = wheel_completeness(wheel, pp_index={})
    assert c.is_complete
    assert c.done == c.expected == 2 * PER_EDGE
    # Status is only worth saying when something is outstanding.
    assert completeness_line(wheel, {}, numeric=True) is None
    assert completeness_line(wheel, {}, numeric=False) is None


def test_blocked_edge_is_named_not_silently_absent(monkeypatch):
    """An edge that CANNOT be developed is a different problem from one that wasn't."""
    edges = [
        _FakeEdge("A"),
        _FakeEdge("B", target=_FakeSegment(complete=False)),
    ]
    _patch_edges(monkeypatch, {"A": PER_EDGE, "B": 0})
    wheel = _FakeWheel(edges)

    c = wheel_completeness(wheel, pp_index={})
    assert c.blocked_edges == ["B"]
    assert c.incomplete_edges == []

    line = completeness_line(wheel, {}, numeric=True)
    assert "blocked" in line
    assert "B" in line


def test_blocked_is_a_property_of_the_pair(monkeypatch):
    """A workable edge opposite an unfinished one is just as stuck.

    A tetrad pairs an edge's Ac+ with its partner's Ac+ in the same band, so a
    part-built edge whose partner has no segments to build from cannot be topped
    up either. Listing it as `incomplete` invited a `deepen` that could only
    burn LLM calls and write nothing.
    """
    edges = [
        _FakeEdge("A"),
        _FakeEdge("B", source=_FakeSegment(complete=False)),
    ]
    _patch_edges(monkeypatch, {"A": 1, "B": 0})

    c = wheel_completeness(_FakeWheel(edges), pp_index={})

    assert sorted(c.blocked_edges) == ["A", "B"]
    assert c.incomplete_edges == []


def test_edge_cannot_count_past_its_share(monkeypatch):
    """A category-skewed edge must not inflate the wheel past its own denominator."""
    edges = [_FakeEdge("A"), _FakeEdge("B")]
    _patch_edges(monkeypatch, {"A": PER_EDGE + 2, "B": 1})

    c = wheel_completeness(_FakeWheel(edges), pp_index={})

    assert c.done == PER_EDGE + 1
    assert c.done < c.expected


def test_wheel_with_no_edges_is_not_called_complete(monkeypatch):
    _patch_edges(monkeypatch, {})
    wheel = _FakeWheel([])

    c = wheel_completeness(wheel, pp_index={})
    assert c.expected == 0
    assert not c.is_complete  # malformed, and calling it complete would hide that
    assert completeness_line(wheel, {}, numeric=True) is None


# --- Register: numbers in counsel mode, plain words otherwise -----------


def test_completeness_line_registers_differ(monkeypatch):
    edges = [_FakeEdge("T1- → A2+"), _FakeEdge("A1- → T2+")]
    _patch_edges(monkeypatch, {"T1- → A2+": PER_EDGE, "A1- → T2+": 1})
    wheel = _FakeWheel(edges)

    numeric = completeness_line(wheel, {}, numeric=True)
    assert f"Pathways: {PER_EDGE + 1}/{2 * PER_EDGE}" in numeric
    assert "A1- → T2+" in numeric

    plain = completeness_line(wheel, {}, numeric=False)
    # No digits, no framework nouns: unscoped, the machinery is invisible.
    assert not any(ch.isdigit() for ch in plain)
    lowered = plain.lower()
    for noun in ("pathway", "wheel", "transformation", "edge"):
        assert noun not in lowered
    assert "partly" in lowered


def test_numeric_register_names_an_undeveloped_wheel_as_such(monkeypatch):
    """`0/6` alone reads as a broken build; by design most wheels sit there.

    `explore` deep-generates exactly one wheel (EXPLORE_DEEP_WHEELS), so every
    other wheel of a counsel-mode dump is at 0/N on purpose.
    """
    edges = [_FakeEdge("A"), _FakeEdge("B")]
    _patch_edges(monkeypatch, {"A": 0, "B": 0})
    line = completeness_line(_FakeWheel(edges), {}, numeric=True)
    assert f"Pathways: 0/{2 * PER_EDGE}" in line
    assert "not yet developed" in line
    # Workable, so nothing suggests it is stuck.
    assert "cannot" not in line

    blocked_edges = [_FakeEdge("C"), _FakeEdge("D", target=_FakeSegment(complete=False))]
    _patch_edges(monkeypatch, {"C": 0, "D": 0})
    blocked_line = completeness_line(_FakeWheel(blocked_edges), {}, numeric=True)
    assert "cannot be until its segments are finished" in blocked_line


def test_plain_register_still_distinguishes_nothing_from_something(monkeypatch):
    edges = [_FakeEdge("A"), _FakeEdge("B")]
    _patch_edges(monkeypatch, {"A": 0, "B": 0})
    untouched = completeness_line(_FakeWheel(edges), {}, numeric=False)
    assert "not yet" in untouched.lower()
    assert not any(ch.isdigit() for ch in untouched)


# --- Per-category resume ------------------------------------------------


def _skill():
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations

    return ExploreTransformations(wheel_hash="wheelhash")


def test_missing_categories_is_bounded_by_band_and_by_count():
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations

    missing = ExploreTransformations._missing_categories

    assert missing([]) == set(INSIGHT_CATEGORIES)
    assert missing([_FakeTransformation("Generative")]) == set(INSIGHT_CATEGORIES) - {
        "Generative"
    }
    # Skewed edge: three Generative Transformations spend the whole budget, so
    # nothing is owed — growing the edge would break the 6N cardinality.
    assert missing([_FakeTransformation("Generative")] * PER_EDGE) == set()
    # Uncategorisable Transformations consume budget without covering a band:
    # something is there, but resume cannot tell what.
    assert missing([_FakeTransformation(None)] * PER_EDGE) == set()
    partial_unknown = missing([_FakeTransformation(None)])
    assert len(partial_unknown) == PER_EDGE - 1


def test_only_missing_filters_by_band_and_keeps_unknown_labels():
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations

    def candidate(label: str) -> ActionCandidateResultDto:
        return ActionCandidateResultDto(
            headline="h",
            statement="s",
            insight=0.5,
            proactiveness=0.6,
            insight_label=label,
            proactiveness_label="Intervention",
            explanation="e",
            haiku="k",
        )

    kept = ExploreTransformations._only_missing(
        [candidate("Leverage"), candidate("Tuning"), candidate("Telepathy")],
        {"Corrective"},
    )
    labels = [c.insight_label for c in kept]
    assert "Leverage" not in labels  # Generative band already covered
    assert "Tuning" in labels  # Corrective band is owed
    assert "Telepathy" in labels  # taxonomy gap must not lose generation work

    assert ExploreTransformations._only_missing([candidate("Tuning")], set()) == []


def test_only_missing_keeps_one_candidate_per_band():
    """Two answers in one band cannot both be written.

    `ActionExtraction` is asked per band, but the LLM picks the level inside it
    and can answer two prompts with the same band. Unfiltered, an edge could end
    up with three Configurational Transformations and none Generative — and read
    as 3/3 done, because the derived count is per row, so two of its three
    documented depth alternatives would be permanently absent AND invisible.
    """
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations

    def candidate(label: str) -> ActionCandidateResultDto:
        return ActionCandidateResultDto(
            headline=label,
            statement="s",
            insight=0.5,
            proactiveness=0.6,
            insight_label=label,
            proactiveness_label="Intervention",
            explanation="e",
            haiku="k",
        )

    # Composition and Reformulation are both Configurational.
    kept = ExploreTransformations._only_missing(
        [candidate("Composition"), candidate("Reformulation"), candidate("Tuning")],
        {"Configurational", "Corrective"},
    )
    assert [c.insight_label for c in kept] == ["Composition", "Tuning"]

    # Off-scale labels share a single slot for the same reason: they cannot be
    # told apart as bands, so keeping all of them would skew the edge just as far.
    unmapped = ExploreTransformations._only_missing(
        [candidate("Telepathy"), candidate("Telekinesis")],
        {"Generative"},
    )
    assert len(unmapped) == 1


async def _run_edge_pair(
    monkeypatch,
    counts: dict[str, int],
    *,
    edges: Optional[tuple[_FakeEdge, _FakeEdge]] = None,
    answers_with: Optional[str] = None,
):
    """Drive `_process_edge_pair` over a fake pair, recording what it asked for.

    Phase 1 and tetrad generation are patched: the defect is in which bands get
    requested and which get written, not in the LLM calls. `answers_with` forces
    every extracted candidate into one insight level, standing in for an LLM that
    drifts out of the band it was asked for.
    """
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        ExploreTransformations

    edge_a, edge_b = edges if edges is not None else (_FakeEdge("A"), _FakeEdge("B"))
    _patch_edges(monkeypatch, counts)

    requested: dict[str, set[str]] = {}
    first_level = {
        category: info["levels"][0] for category, info in INSIGHT_CATEGORIES.items()
    }

    async def fake_phase1(self, edge, wheel, input_text, only_categories=None):
        from dialectical_framework.agents.execution_report import ExecutionReport

        requested[edge.label] = set(only_categories or INSIGHT_CATEGORIES)
        candidates = [
            ActionCandidateResultDto(
                headline=f"{edge.label}:{category}",
                statement="s",
                insight=INSIGHT_SCALE[answers_with or first_level[category]],
                proactiveness=0.6,
                insight_label=answers_with or first_level[category],
                proactiveness_label="Intervention",
                explanation="e",
                haiku="k",
            )
            for category in (only_categories or INSIGHT_CATEGORIES)
        ]
        return object(), candidates, ExecutionReport(tool="fake")

    async def fake_generate(self, edge, ac_plus, opposite_ac, apexes, input_text):
        from dialectical_framework.agents.execution_report import ExecutionReport

        return (edge.label, ac_plus, opposite_ac), ExecutionReport(tool="fake")

    written: list[tuple] = []

    def fake_create(self, nexus, edge, source, target, tetrad):
        written.append(tetrad)
        return _FakeTransformation()

    monkeypatch.setattr(ExploreTransformations, "_phase1_for_edge", fake_phase1)
    monkeypatch.setattr(ExploreTransformations, "_generate_tetrad", fake_generate)
    monkeypatch.setattr(ExploreTransformations, "_create_transformation", fake_create)

    skill = _skill()
    wheel = _FakeWheel([edge_a, edge_b])
    existing, new, _ = await skill._process_edge_pair(
        wheel, object(), edge_a, edge_b, "input"
    )
    return skill, requested, written, existing, new


async def test_fresh_pair_builds_every_band_on_both_edges(monkeypatch):
    skill, requested, written, existing, new = await _run_edge_pair(
        monkeypatch, {"A": 0, "B": 0}
    )

    assert requested == {"A": set(INSIGHT_CATEGORIES), "B": set(INSIGHT_CATEGORIES)}
    assert len(new) == 2 * PER_EDGE  # the 6N cardinality, per pair
    assert existing == []
    assert skill._resumed_edges == {}  # nothing was resumed


async def test_resume_tops_up_exactly_the_gap(monkeypatch):
    """The interrupted state: one edge finished, its partner part-way through."""
    skill, requested, written, existing, new = await _run_edge_pair(
        monkeypatch, {"A": PER_EDGE, "B": 1}
    )

    # B carries one Transformation of unknown-but-Generative band, so it owes the
    # other two — and only those.
    owed = set(INSIGHT_CATEGORIES) - {"Generative"}
    assert requested["B"] == owed
    # A is complete: it extracts as SUPPORT for B's bands, and earns nothing.
    # Without this pass the top-up had nobody to pair with and produced nothing.
    assert requested["A"] == owed

    assert len(new) == len(owed)
    assert all(edge_label == "B" for edge_label, _, _ in written)
    written_bands = {
        insight_category_of_label(ac_plus.insight_label) for _, ac_plus, _ in written
    }
    assert written_bands == owed
    # Each new Transformation pairs with the opposite edge's Ac+ in the same band.
    for _, ac_plus, opposite_ac in written:
        assert insight_category_of_label(
            opposite_ac.insight_label
        ) == insight_category_of_label(ac_plus.insight_label)
        assert opposite_ac.headline.startswith("A:")

    assert len(existing) == PER_EDGE + 1
    assert skill._resumed_edges == {"h-B": sorted(owed)}


async def test_complete_pair_is_left_alone(monkeypatch):
    skill, requested, written, existing, new = await _run_edge_pair(
        monkeypatch, {"A": PER_EDGE, "B": PER_EDGE}
    )

    assert requested == {}  # no LLM work at all
    assert new == []
    assert len(existing) == 2 * PER_EDGE
    assert skill._resumed_edges == {}


async def test_blocked_pair_spends_nothing_and_invites_nothing(monkeypatch):
    """An unfinished partner makes the whole pair unbuildable — say so, cheaply.

    Neither edge can earn a Transformation, because the side whose segments are
    unfinished has no Ac+ to lend. Extracting anyway burned an ApexDerivation
    plus one ActionExtraction per band and wrote nothing — and derived status
    then invited another `deepen`, repeating the cost for as long as the user
    kept trying.
    """
    pair = (_FakeEdge("A"), _FakeEdge("B", target=_FakeSegment(complete=False)))
    skill, requested, written, existing, new = await _run_edge_pair(
        monkeypatch, {"A": 1, "B": 0}, edges=pair
    )

    assert requested == {}  # not one LLM call
    assert written == []
    assert new == []
    # The part-built edge is named as blocked, not left to read as a top-up that
    # produced nothing, and not as a resume.
    assert skill._blocked_edges == {"h-A", "h-B"}
    assert skill._resumed_edges == {}

    skill._report.summary = "Processed 1 edge pair(s)"
    skill._report_resume_state()
    assert skill._report.artifacts["blocked_edges"] == ["h-A", "h-B"]
    assert "blocked, segments unfinished" in skill._report.summary
    assert "resumed_categories" not in skill._report.artifacts


async def test_short_top_up_reports_what_it_still_owes(monkeypatch):
    """A resume that came back short must not read like a finished one.

    The LLM picks the level inside a band and can land outside the one it was
    asked for, so a top-up can write nothing while still counting as a run.
    Silence there left the wheel partial with nobody saying why, across
    unlimited retries.
    """
    skill, requested, written, _, new = await _run_edge_pair(
        monkeypatch, {"A": PER_EDGE, "B": 1}, answers_with="Leverage"
    )

    owed = set(INSIGHT_CATEGORIES) - {"Generative"}
    assert requested["B"] == owed  # it did ask for the right bands
    assert written == []  # and got answers in a band it already had
    assert new == []
    assert skill._resumed_edges == {}  # nothing was topped up
    assert skill._resume_shortfall == {"h-B": sorted(owed)}

    skill._report.summary = "Processed 1 edge pair(s)"
    skill._report_resume_state()
    assert skill._report.artifacts["still_missing"] == {"h-B": sorted(owed)}
    assert "still short" in skill._report.summary


async def test_resumed_edges_reach_the_report(monkeypatch):
    """A top-up must read as a top-up, not as a fresh build."""
    skill, _, _, _, _ = await _run_edge_pair(monkeypatch, {"A": PER_EDGE, "B": 1})

    skill._report.summary = "Processed 1 edge pair(s)"
    # The real report tail — `resolve()` needs a live wheel, this does not.
    skill._report_resume_state()

    assert skill._report.artifacts["resumed_categories"] == {
        "h-B": sorted(set(INSIGHT_CATEGORIES) - {"Generative"})
    }
    assert "resumed 1 partly-built edge(s)" in skill._report.summary
    # It finished the gap, so there is nothing outstanding to report.
    assert "still_missing" not in skill._report.artifacts


# --- Synthesis stamp ----------------------------------------------------


class _CommittedStub:
    def __init__(self, hash_: str) -> None:
        self.hash = hash_
        self.short_hash = hash_[:7]

    @property
    def is_committed(self) -> bool:
        return True


def test_completeness_never_enters_the_synthesis_hash(monkeypatch):
    """The stamp is metadata: adding it must not re-identify existing nodes.

    `Synthesis._collect_structure_hash_parts` is an allowlist (S+ hash, S- hash),
    and `compute_hash` adds only intent and committed_at — so the field is
    excluded by construction. Verified rather than assumed, because a later edit
    to that allowlist would silently change every Synthesis hash in every graph.
    """
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.relationship_manager import RelationshipManager

    stubs = {
        "target": _CommittedStub("wheelhash"),
        "s_plus": _CommittedStub("splushash"),
        "s_minus": _CommittedStub("sminushash"),
    }

    def fake_get(self, instance, owner):
        if instance is None:
            return self
        return _FakeManager([stubs[self.name]])

    monkeypatch.setattr(RelationshipManager, "__get__", fake_get)

    plain = Synthesis(sid="test-sid", committed_at=1700000000)
    stamped = Synthesis(
        sid="test-sid", committed_at=1700000000, completeness=f"{PER_EDGE + 1}/{2 * PER_EDGE}"
    )

    assert stamped.completeness == f"{PER_EDGE + 1}/{2 * PER_EDGE}"
    assert plain.completeness is None
    assert stamped.compute_hash() == plain.compute_hash()


def test_synthesis_stamp_renders_only_when_partial():
    """`_synthesis_stamp` warns about a fragment, and stays quiet otherwise."""
    from dialectical_framework.concerns.dialectical_context import DialecticalContext

    class _Synth:
        def __init__(self, completeness):
            self.completeness = completeness

    scoped = DialecticalContext(nexus_hash="nexushash")
    unscoped = DialecticalContext()

    assert scoped._numeric_status is True
    assert unscoped._numeric_status is False

    partial = scoped._synthesis_stamp(_Synth("4/6"))
    assert "4 of 6" in partial

    plain = unscoped._synthesis_stamp(_Synth("4/6"))
    assert not any(ch.isdigit() for ch in plain)
    assert "pathway" not in plain.lower()

    # Complete, unrecorded, or unparseable: nothing to warn about.
    assert scoped._synthesis_stamp(_Synth("6/6")) is None
    assert scoped._synthesis_stamp(_Synth(None)) is None
    assert scoped._synthesis_stamp(_Synth("all of it")) is None
    assert scoped._synthesis_stamp(_Synth("x/y")) is None


# --- Wiring: the denominator reaches both renderers --------------------


def test_context_wheel_dump_carries_the_status_line(monkeypatch):
    from dialectical_framework.concerns.dialectical_context import DialecticalContext

    edges = [_FakeEdge("T1- → A2+"), _FakeEdge("A1- → T2+")]
    _patch_edges(monkeypatch, {"T1- → A2+": PER_EDGE, "A1- → T2+": 1})
    monkeypatch.setattr(
        DialecticalContext, "_format_ta_sequence", lambda self, w, i: ""
    )
    monkeypatch.setattr(DialecticalContext, "_dump_synthesis", lambda self, w, i: None)
    wheel = _FakeWheel(edges)

    scoped = DialecticalContext(nexus_hash="nexushash")._dump_wheel(wheel, {}, 0.0, {})
    assert f"Pathways: {PER_EDGE + 1}/{2 * PER_EDGE}" in scoped

    unscoped = DialecticalContext()._dump_wheel(wheel, {}, 0.0, {})
    assert "Pathways" not in unscoped
    assert "Partly worked through" in unscoped


def test_inspect_wheel_shows_the_expected_total(monkeypatch):
    from dialectical_framework.agents.orchestrator.tools import inspect_node as mod

    edges = [
        _FakeEdge("T1- → A2+"),
        _FakeEdge("A1- → T2+", source=_FakeSegment(complete=False)),
    ]
    _patch_edges(monkeypatch, {"T1- → A2+": 1, "A1- → T2+": 0})
    monkeypatch.setattr(mod, "format_edge_label", lambda edge, pp_index=None: edge.label)
    monkeypatch.setattr(mod, "_node_id", lambda node: "wheelha")
    monkeypatch.setattr(mod, "_status_tag", lambda node: "")

    wheel = _FakeWheel(edges, transformations=[_FakeTransformation()])
    out = mod._inspect_wheel(wheel)

    assert f"Transformations (1 of {2 * PER_EDGE} expected):" in out
    # Both edges are blocked: the pair needs an Ac+ from each side, so the
    # part-built one is as stuck as the one with the unfinished segment. Nothing
    # is offered as top-up-able, because nothing here is.
    assert "Blocked (segments unfinished): T1- → A2+, A1- → T2+" in out
    assert "Incomplete (deepen can top these up)" not in out


def test_incomplete_and_blocked_are_told_apart(monkeypatch):
    """A workable pair reads as top-up-able; only a stuck one reads as blocked."""
    from dialectical_framework.agents.orchestrator.tools import inspect_node as mod

    edges = [_FakeEdge("T1- → A2+"), _FakeEdge("A1- → T2+")]
    _patch_edges(monkeypatch, {"T1- → A2+": 1, "A1- → T2+": PER_EDGE})
    monkeypatch.setattr(mod, "format_edge_label", lambda edge, pp_index=None: edge.label)
    monkeypatch.setattr(mod, "_node_id", lambda node: "wheelha")
    monkeypatch.setattr(mod, "_status_tag", lambda node: "")

    out = mod._inspect_wheel(_FakeWheel(edges, transformations=[_FakeTransformation()]))

    assert "Incomplete (deepen can top these up): T1- → A2+" in out
    assert "Blocked" not in out


def test_exploration_view_shows_the_denominator():
    """The Navigator's own view must not read a fragment as a finished wheel.

    `present_exploration` already groups Transformations per edge while
    rendering, so the fraction costs it no extra queries — and it uses
    `WheelCompleteness.from_edge_counts` rather than its own arithmetic, so a
    second surface cannot compute completeness differently.
    """
    from dialectical_framework.agents.explorer.tools.present_exploration import \
        PresentExploration

    edge_a, edge_b = _FakeEdge("A"), _FakeEdge("B")
    wheel = _FakeWheel([edge_a, edge_b])
    wheel.polarity_count = 1
    for edge in (edge_a, edge_b):
        edge.cycle = _FakeManager([wheel])
        edge.source = _FakeManager()
        edge.target = _FakeManager()

    def _tr(edge) -> _FakeTransformation:
        tr = _FakeTransformation()
        tr.edge = _FakeManager([edge])
        tr.is_committed = True
        tr.ac_plus = _FakeManager()
        tr.re_plus = _FakeManager()
        return tr

    partial = [_tr(edge_a)] * PER_EDGE + [_tr(edge_b)]
    out = PresentExploration._format_wheels([wheel], partial)
    assert f"Pathways: {PER_EDGE + 1}/{2 * PER_EDGE}" in out

    # Finished: no line at all, same convention as `completeness_line`.
    whole = [_tr(edge_a)] * PER_EDGE + [_tr(edge_b)] * PER_EDGE
    assert "Pathways:" not in PresentExploration._format_wheels([wheel], whole)


def test_completeness_counts_only_committed_transformations(monkeypatch):
    """Uncommitted rows are invisible to the count, by repository rule.

    `count_by_edges` filters `hash IS NOT NULL`: a Transformation abandoned
    mid-commit must not make an edge look finished, or the gap it left could
    never be topped up.
    """
    from dialectical_framework.graph.repositories.transformation_repository import \
        TransformationRepository
    import inspect

    source = inspect.getsource(TransformationRepository.count_by_edges)
    assert "tr.hash IS NOT NULL" in source
    assert "tr.sid = $sid" in source
