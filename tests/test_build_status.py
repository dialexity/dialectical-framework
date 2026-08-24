"""
A host app must be able to ask "how far did this case get?" and get data back.

`DialecticalContext` already walks the same graph, but it returns prose for an
LLM — a UI cannot render it and a caller cannot branch on it. `BuildStatus`
returns dataclasses over the same derived reads (`wheel_completeness`,
`polarity_completeness`), and the pieces that carry real judgement are pinned
here:

1. **Shallow is not interrupted.** Both are short of 6N. A shallow wheel was
   never developed BY DESIGN (`explore` deepens one arrangement per call), an
   interrupted one is work the user lost. Only the second is a resume, and
   conflating them would either hide lost work or nag the user to "finish"
   arrangements they deliberately did not pick.
2. **Blocked is never offered.** A wheel whose edge pairs have unfinished
   segments cannot take a Transformation, so it must not become a resume hint —
   the deepen would spend nothing and add nothing.
3. **Nothing vanishes.** A node whose status read fails is named in
   `unreadable_hashes`, not dropped: dropping it would report a broken graph as
   a finished one, which is the exact defect the whole status pass exists to
   remove.

DB-free and LLM-free — the aggregation is counting and classification, so the
repository reads are patched out.
"""

from __future__ import annotations

from typing import Optional

import pytest

from dialectical_framework.concerns.ac_re_taxonomy import INSIGHT_CATEGORIES
from dialectical_framework.concerns.build_status import (WHEEL_BLOCKED,
                                                        WHEEL_COMPLETE,
                                                        WHEEL_INTERRUPTED,
                                                        WHEEL_SHALLOW,
                                                        BuildStatus)
from dialectical_framework.graph import rendering
from dialectical_framework.graph.rendering import (POLARITY_DEVELOPED,
                                                   POLARITY_NOT_DEVELOPED,
                                                   POLARITY_PARTIAL,
                                                   POLARITY_SET_ASIDE)


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


PER_EDGE = len(INSIGHT_CATEGORIES)
FULL = 2 * PER_EDGE


# --- Fakes ---------------------------------------------------------------


class _FakeSegment:
    def __init__(self, complete: bool = True) -> None:
        self._complete = complete

    def is_complete(self) -> bool:
        return self._complete


class _FakeManager:
    def __init__(self, items: Optional[list] = None) -> None:
        self._items = items or []

    def all(self) -> list:
        return [(item, None) for item in self._items]


class _FakeEdge:
    _next_id = 500

    def __init__(self, label: str, buildable: bool = True) -> None:
        self.label = label
        self.hash = f"hash-{label}"
        self.short_hash = f"h-{label}"
        # `wheel_completeness` tallies by internal edge id — distinct ids or
        # every edge reads the same count.
        _FakeEdge._next_id += 1
        self._id = _FakeEdge._next_id
        self._segment = _FakeSegment(buildable)

    def get_source_wheel_segment(self):
        return self._segment

    def get_target_wheel_segment(self):
        return self._segment


class _FakeSynthesis:
    def __init__(self, completeness: Optional[str]) -> None:
        self.completeness = completeness
        self.hash = f"synth-{completeness}"
        self.short_hash = "synth00"


class _FakeWheel:
    def __init__(
        self,
        name: str,
        *,
        done_per_edge: tuple[int, int] = (0, 0),
        buildable: bool = True,
        syntheses: Optional[list[_FakeSynthesis]] = None,
    ) -> None:
        self.hash = f"wheelhash-{name}"
        self.short_hash = f"wheel-{name}"
        self.edges = [
            _FakeEdge(f"{name}-A", buildable),
            _FakeEdge(f"{name}-B", buildable),
        ]
        self._counts = {
            edge._id: count for edge, count in zip(self.edges, done_per_edge)
        }
        self.synthesis = _FakeManager(syntheses or [])


class _FakeCycle:
    def __init__(self, name: str, layer: int = 1) -> None:
        self.hash = f"cyclehash-{name}"
        self.short_hash = f"cycle-{name}"
        self.perspective_hashes = [f"pp{i}" for i in range(layer)]


class _FakeNexus:
    def __init__(self, name: str = "n1") -> None:
        self.hash = f"nexushash-{name}"
        self.short_hash = f"nexus-{name}"
        self.perspectives = _FakeManager()


class _FakeStatement:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakePolarity:
    def __init__(
        self,
        name: str,
        *,
        hs: Optional[float] = 0.9,
        perspectives: Optional[list] = None,
    ) -> None:
        self.hash = f"polhash-{name}"
        self.short_hash = f"pol-{name}"
        self.heuristic_similarity = hs
        self.perspectives = perspectives or []

    def get_t_component(self):
        return _FakeStatement(f"T of {self.short_hash}")

    def get_a_component(self):
        return _FakeStatement(f"A of {self.short_hash}")


class _FakePerspective:
    def __init__(self, complete: bool = True, discarded: Optional[str] = None) -> None:
        self._complete = complete
        self.discarded = discarded

    def is_complete(self) -> bool:
        return self._complete


def _patch_graph(
    monkeypatch,
    *,
    wheels: Optional[list[tuple[_FakeCycle, _FakeWheel]]] = None,
    polarities: Optional[list[_FakePolarity]] = None,
    nexuses: Optional[list[_FakeNexus]] = None,
) -> _FakeNexus:
    """Wire the four repository reads `BuildStatus` performs.

    `wheel_completeness` itself runs for real — the state machine on top of it
    is what these tests are about, so faking the counts and letting the real
    clamp/pair logic decide `incomplete` vs `blocked` is the point.
    """
    from dialectical_framework.graph.repositories.nexus_repository import \
        NexusRepository
    from dialectical_framework.graph.repositories.perspective_repository import \
        PerspectiveRepository
    from dialectical_framework.graph.repositories.polarity_repository import \
        PolarityRepository
    from dialectical_framework.graph.repositories.transformation_repository import \
        TransformationRepository
    from dialectical_framework.graph.repositories.wheel_repository import \
        WheelRepository

    all_nexuses = nexuses or [_FakeNexus()]
    nexus = all_nexuses[0]
    pairs = wheels or []

    monkeypatch.setattr(
        NexusRepository, "find_all", lambda self, **_kw: list(all_nexuses)
    )
    monkeypatch.setattr(
        PolarityRepository, "find_all", lambda self, **_kw: list(polarities or [])
    )
    monkeypatch.setattr(
        WheelRepository, "find_by_nexus", lambda self, n, **_kw: list(pairs)
    )
    monkeypatch.setattr(
        PerspectiveRepository,
        "find_by_polarity",
        lambda self, polarity, **_kw: list(polarity.perspectives),
    )

    counts: dict[int, int] = {}
    for _cycle, wheel in pairs:
        counts.update(wheel._counts)

    monkeypatch.setattr(
        TransformationRepository,
        "count_by_edges",
        lambda self, edges, **_kw: {e._id: counts.get(e._id, 0) for e in edges},
    )
    # Would otherwise resolve component aliases through the DB.
    monkeypatch.setattr(
        rendering, "format_edge_label", lambda edge, pp_index=None: edge.label
    )
    monkeypatch.setattr(rendering, "build_pp_index", lambda _nexus: {})
    return nexus


async def _status(monkeypatch, **kwargs):
    _patch_graph(monkeypatch, **kwargs)
    return await BuildStatus().resolve(sid="test-sid")


# --- Wheel states --------------------------------------------------------


@pytest.mark.asyncio
async def test_the_four_wheel_states_are_told_apart(monkeypatch):
    complete = _FakeWheel("complete", done_per_edge=(PER_EDGE, PER_EDGE))
    interrupted = _FakeWheel("interrupted", done_per_edge=(PER_EDGE, 1))
    shallow = _FakeWheel("shallow", done_per_edge=(0, 0))
    blocked = _FakeWheel("blocked", done_per_edge=(0, 0), buildable=False)

    status = await _status(
        monkeypatch,
        wheels=[
            (_FakeCycle("c", layer=2), w)
            for w in (complete, interrupted, shallow, blocked)
        ],
    )

    by_hash = {w.short_hash: w for w in status.wheels}
    assert by_hash["wheel-complete"].state == WHEEL_COMPLETE
    assert by_hash["wheel-interrupted"].state == WHEEL_INTERRUPTED
    assert by_hash["wheel-shallow"].state == WHEEL_SHALLOW
    assert by_hash["wheel-blocked"].state == WHEEL_BLOCKED

    assert by_hash["wheel-interrupted"].fraction == f"{PER_EDGE + 1}/{FULL}"
    assert by_hash["wheel-interrupted"].incomplete_edges == ("interrupted-B",)
    # Blocked is a property of the pair, so BOTH edges of the stuck pair are
    # named — and none of them is offered as topping-up work.
    assert set(by_hash["wheel-blocked"].blocked_edges) == {"blocked-A", "blocked-B"}
    assert by_hash["wheel-blocked"].incomplete_edges == ()
    assert not by_hash["wheel-blocked"].is_resumable

    assert status.wheels_by_state()[WHEEL_SHALLOW] == [shallow.hash]
    assert status.shallow_wheel_hashes == (shallow.hash,)


@pytest.mark.asyncio
async def test_layer_and_parentage_come_from_the_cycle(monkeypatch):
    wheel = _FakeWheel("w", done_per_edge=(PER_EDGE, PER_EDGE))
    cycle = _FakeCycle("c", layer=3)

    status = await _status(monkeypatch, wheels=[(cycle, wheel)])

    only = status.wheels[0]
    assert only.layer == 3
    assert only.cycle_hash == cycle.hash
    assert only.nexus_hash == status.nexus_hashes[0]


@pytest.mark.asyncio
async def test_a_wheel_shared_by_two_explorations_is_counted_once(monkeypatch):
    """A cycle qualifies for every nexus whose perspective set contains it.

    So an overlapping pair of explorations returns the same wheel twice, and a
    host counting arrangements (or listing shallow ones to offer) would see two
    where there is one.
    """
    shared = _FakeWheel("shared", done_per_edge=(0, 0))

    status = await _status(
        monkeypatch,
        wheels=[(_FakeCycle("c"), shared)],
        nexuses=[_FakeNexus("first"), _FakeNexus("second")],
    )

    assert len(status.nexus_hashes) == 2
    assert [w.hash for w in status.wheels] == [shared.hash]
    assert status.shallow_wheel_hashes == (shared.hash,)


@pytest.mark.asyncio
async def test_a_nexus_with_no_wheels_still_reports(monkeypatch):
    """Structure never built is status, not absence — the app should say so."""
    status = await _status(monkeypatch, wheels=[])

    assert status.nexus_hashes and not status.wheels
    assert status.resume_hint is None


# --- Resume hint ---------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_hint_names_the_interrupted_wheel_not_the_shallow_one(monkeypatch):
    """The distinction the hint exists for.

    A shallow wheel is short of 6N too, but deepening it is a choice the user
    makes from their own reality (lived reality outranks the plausibility
    score). Offering it as "unfinished business" would quietly push the argmax
    path back onto them.
    """
    interrupted = _FakeWheel("interrupted", done_per_edge=(1, 0))
    shallow = _FakeWheel("shallow", done_per_edge=(0, 0))

    status = await _status(
        monkeypatch,
        wheels=[(_FakeCycle("c"), shallow), (_FakeCycle("c"), interrupted)],
    )

    assert status.resume_hint == interrupted.hash
    assert status.resume_hint not in status.shallow_wheel_hashes


@pytest.mark.asyncio
async def test_resume_hint_takes_the_wheel_closest_to_finishing(monkeypatch):
    barely = _FakeWheel("barely", done_per_edge=(1, 0))
    nearly = _FakeWheel("nearly", done_per_edge=(PER_EDGE, PER_EDGE - 1))

    status = await _status(
        monkeypatch,
        wheels=[(_FakeCycle("c"), barely), (_FakeCycle("c"), nearly)],
    )

    assert status.resume_hint == nearly.hash
    assert {w.hash for w in status.interrupted_wheels} == {barely.hash, nearly.hash}


@pytest.mark.asyncio
async def test_tied_wheels_resolve_the_same_way_every_read(monkeypatch):
    """Two reads of one graph must not disagree about what to resume.

    Cypher leaves the order of equally-scored rows unspecified, so with a
    done-count-only key the hint could flip between reads and a host would
    deepen a different wheel each time it asked.
    """
    first = _FakeWheel("aaa", done_per_edge=(1, 0))
    second = _FakeWheel("bbb", done_per_edge=(1, 0))

    forward = await _status(
        monkeypatch, wheels=[(_FakeCycle("c"), first), (_FakeCycle("c"), second)]
    )
    reversed_ = await _status(
        monkeypatch, wheels=[(_FakeCycle("c"), second), (_FakeCycle("c"), first)]
    )

    assert forward.resume_hint == reversed_.resume_hint


@pytest.mark.asyncio
async def test_blocked_wheel_is_never_a_resume_hint(monkeypatch):
    """Half-built AND stuck: real lost work, but a deepen cannot recover it."""
    stuck = _FakeWheel("stuck", done_per_edge=(1, 0), buildable=False)

    status = await _status(monkeypatch, wheels=[(_FakeCycle("c"), stuck)])

    assert status.wheels[0].state == WHEEL_BLOCKED
    assert status.wheels[0].done == 1
    assert status.resume_hint is None


@pytest.mark.asyncio
async def test_nothing_outstanding_reads_as_complete(monkeypatch):
    """A finished wheel plus an undeveloped alternative plus a set-aside tension.

    None of those is unfinished business: the shallow wheel is the explore
    budget working, the set-aside polarity is the HS gate working.
    """
    status = await _status(
        monkeypatch,
        wheels=[
            (_FakeCycle("c"), _FakeWheel("done", done_per_edge=(PER_EDGE, PER_EDGE))),
            (_FakeCycle("c"), _FakeWheel("alt", done_per_edge=(0, 0))),
        ],
        polarities=[_FakePolarity("weak", hs=0.3)],
    )

    assert status.resume_hint is None
    assert status.is_complete
    assert status.polarities_by_state() == {POLARITY_SET_ASIDE: ["polhash-weak"]}


@pytest.mark.asyncio
async def test_a_half_built_tension_keeps_the_case_incomplete(monkeypatch):
    """The analysis-path half of resume: an interrupted expansion counts too."""
    status = await _status(
        monkeypatch,
        wheels=[
            (_FakeCycle("c"), _FakeWheel("done", done_per_edge=(PER_EDGE, PER_EDGE)))
        ],
        polarities=[_FakePolarity("partial", perspectives=[_FakePerspective(False)])],
    )

    assert status.polarities[0].state == POLARITY_PARTIAL
    assert not status.is_complete


# --- Polarities ----------------------------------------------------------


@pytest.mark.asyncio
async def test_polarity_states_and_texts_reach_the_caller(monkeypatch):
    developed = _FakePolarity("dev", hs=0.9, perspectives=[_FakePerspective(True)])
    lost = _FakePolarity("lost", hs=0.9)
    aside = _FakePolarity("aside", hs=0.2)

    status = await _status(monkeypatch, polarities=[developed, lost, aside])

    states = {p.short_hash: p.state for p in status.polarities}
    assert states == {
        "pol-dev": POLARITY_DEVELOPED,
        "pol-lost": POLARITY_NOT_DEVELOPED,
        "pol-aside": POLARITY_SET_ASIDE,
    }
    first = status.polarities[0]
    assert first.thesis == "T of pol-dev" and first.antithesis == "A of pol-dev"
    assert first.heuristic_similarity == 0.9


# --- Synthesis stamps ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_stamp_from_a_fragment_reads_as_stale(monkeypatch):
    """S+ emerges from ALL transformations at once.

    A synthesis stamped 4/6 on a wheel that is now whole was drawn from a
    fragment, and regenerating it is real work — so the flag has to survive the
    trip to the app, not just the LLM dump.
    """
    stale = _FakeSynthesis(f"{PER_EDGE}/{FULL}")
    wheel = _FakeWheel(
        "w", done_per_edge=(PER_EDGE, PER_EDGE), syntheses=[stale]
    )

    status = await _status(monkeypatch, wheels=[(_FakeCycle("c"), wheel)])

    only = status.wheels[0]
    assert only.is_complete
    assert only.syntheses[0].completeness == f"{PER_EDGE}/{FULL}"
    assert only.syntheses[0].is_stale
    assert only.has_stale_synthesis
    assert status.stale_synthesis_wheel_hashes == (wheel.hash,)


@pytest.mark.asyncio
async def test_matching_and_missing_stamps_are_not_stale(monkeypatch):
    """An unstamped synthesis predates the stamp — flagging it would flag every
    pre-existing graph as needing regeneration."""
    current = _FakeWheel(
        "current",
        done_per_edge=(PER_EDGE, PER_EDGE),
        syntheses=[_FakeSynthesis(f"{FULL}/{FULL}")],
    )
    unstamped = _FakeWheel(
        "unstamped",
        done_per_edge=(PER_EDGE, PER_EDGE),
        syntheses=[_FakeSynthesis(None)],
    )

    status = await _status(
        monkeypatch,
        wheels=[(_FakeCycle("c"), current), (_FakeCycle("c"), unstamped)],
    )

    assert status.stale_synthesis_wheel_hashes == ()


# --- Fail-soft -----------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreadable_wheel_is_named_not_dropped(monkeypatch):
    good = _FakeWheel("good", done_per_edge=(PER_EDGE, PER_EDGE))
    bad = _FakeWheel("bad", done_per_edge=(1, 0))

    _patch_graph(
        monkeypatch,
        wheels=[(_FakeCycle("c"), good), (_FakeCycle("c"), bad)],
    )

    real_completeness = rendering.wheel_completeness

    def exploding(wheel, pp_index=None):
        if wheel.hash == bad.hash:
            raise KeyError("driver went away")
        return real_completeness(wheel, pp_index)

    monkeypatch.setattr(rendering, "wheel_completeness", exploding)

    status = await BuildStatus().resolve(sid="test-sid")

    assert [w.hash for w in status.wheels] == [good.hash]
    assert status.unreadable_hashes == (bad.hash,)
    # And the failure is not laundered into "nothing outstanding": there is no
    # hint to give, but the case must not claim to be finished either.
    assert status.resume_hint is None
    assert not status.is_complete


@pytest.mark.asyncio
async def test_an_unreadable_polarity_does_not_sink_the_read(monkeypatch):
    ok = _FakePolarity("ok", hs=0.2)
    broken = _FakePolarity("broken", hs=0.9)

    _patch_graph(monkeypatch, polarities=[ok, broken])

    real_polarity = rendering.polarity_completeness

    def exploding(polarity, **kwargs):
        if polarity.hash == broken.hash:
            raise KeyError("driver went away")
        return real_polarity(polarity, **kwargs)

    monkeypatch.setattr(rendering, "polarity_completeness", exploding)

    status = await BuildStatus().resolve(sid="test-sid")

    assert [p.hash for p in status.polarities] == [ok.hash]
    assert status.unreadable_hashes == (broken.hash,)


@pytest.mark.asyncio
async def test_report_summary_names_the_resume(monkeypatch):
    """The concern is also reachable as a report — keep the two in agreement."""
    interrupted = _FakeWheel("interrupted", done_per_edge=(1, 0))
    _patch_graph(monkeypatch, wheels=[(_FakeCycle("c"), interrupted)])

    concern = BuildStatus()
    status = await concern.resolve(sid="test-sid")

    assert status.resume_hint
    assert "resume" in concern.report.summary
    assert status.resume_hint[:7] in concern.report.summary
