"""
`graph/views.py` — the graph as a picture a host can draw.

What these tests hold, and why each one is worth a test rather than a reading:

1. **Absence is `None`.** An unscored tetrad has no metrics, an unestimated
   wheel has no causality, an unconnected position is `None` — never `0.0`, and
   never the `-1.0` that `explorer._causality_probability` returns on purpose so
   an unestimated wheel loses a ranking. A widget draws whatever it is handed,
   so a sentinel reaching it is a lie on screen.
2. **`without_terminology()` really strips the machinery.** The framework
   already removes `[[hash]]` from person-facing TEXT (`reply_hygiene`); the
   picture is the second surface of the same policy. The test walks the
   serialized projection and fails on any position, alias, hash or number left
   in it — so a field added to a view without a line in `without_terminology`
   fails here rather than in a screenshot.
3. **The graph's fields, as they are.** `intent` is carried verbatim — the
   reading on a generated tetrad, free text where a person set it — and nothing
   is derived from it: the view invents no field the node does not have.
4. **Numbers are never re-derived.** The metrics view is asserted against the
   `Perspective` properties themselves, so the "do not fix this formula" notes
   on `area` / `rectangularity` keep exactly one owner. The one arithmetic
   assertion here is on the fixture, to prove the fixture is scored at all.
5. **A wheel keeps its own arrangement.** `polar_segments` order is load-bearing
   (it is the wheel), and spiral endpoints must be the poles the segments
   already built — a re-read endpoint would carry no position and a widget
   could not highlight both ends of a step.

Real Memgraph, no provider: every value in here is computed from stored data.
"""

from __future__ import annotations

import json
from typing import Any, Iterator, Optional

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.estimation import \
    CausalityProbabilityEstimation
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import (POSITION_A,
                                                           POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.graph.views import (PoleView, exploration_view,
                                               perspective_view, wheel_view)

from test_graph import create_cycle_wheel_setup

#: Complementarity per aspect, chosen so every metric is exact:
#: Ks = 0.7 / 0.2 / 0.75 / 0.25 → diff_t 0.5, diff_a 0.5, SP 1.0.
_COMPLEMENTARITY: dict[str, tuple[float, float]] = {
    "t_plus": (0.8, 0.6),
    "t_minus": (0.3, 0.1),
    "a_plus": (0.6, 0.9),
    "a_minus": (0.2, 0.3),
}
#: Aliases deliberately differ from the positions, so a test can tell the stored
#: label ("T1+") from the framework's terminology ("T+").
_ALIASES = {"t_plus": "T1+", "t_minus": "T1-", "a_plus": "A1+", "a_minus": "A1-"}
_ASPECT_RELATIONSHIPS = {
    "t_plus": TPlusRelationship,
    "t_minus": TMinusRelationship,
    "a_plus": APlusRelationship,
    "a_minus": AMinusRelationship,
}
_ALL_POSITIONS = (
    POSITION_T,
    POSITION_A,
    POSITION_T_PLUS,
    POSITION_T_MINUS,
    POSITION_A_PLUS,
    POSITION_A_MINUS,
)


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _stmt(text: str) -> Statement:
    stmt = Statement(text=text, meaning="test")
    stmt.commit()
    return stmt


def _tetrad(
    *,
    thesis: str = "Control",
    antithesis: str = "Freedom",
    prefix: str = "",
    intent: Optional[str] = None,
    scored: bool = True,
    omit: tuple[str, ...] = (),
) -> tuple[Perspective, dict[str, Statement]]:
    """A Perspective and its statements by view field name.

    `scored=False` leaves complementarity unset (HS stays, as it does in the
    graph — the two are scored by different calls). `omit` drops positions, which
    is what an interrupted build leaves behind — and such a tetrad is
    necessarily UNCOMMITTED, because `commit()` enforces the six-position
    cardinality. So it has no hash either, which is exactly the state a widget
    opened on a half-built tetrad reads.
    """
    t = _stmt(f"{prefix}{thesis}")
    a = _stmt(f"{prefix}{antithesis}")
    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    pp = Perspective(intent=intent) if intent else Perspective()
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

    statements: dict[str, Statement] = {"t": t, "a": a}
    for name, rel_class in _ASPECT_RELATIONSHIPS.items():
        if name in omit:
            continue
        stmt = _stmt(f"{prefix}{name} of {thesis}")
        k_t, k_a = _COMPLEMENTARITY[name]
        getattr(pp, name).connect(
            stmt,
            relationship=rel_class(
                alias=_ALIASES[name],
                heuristic_similarity=0.9,
                complementarity_t=k_t if scored else None,
                complementarity_a=k_a if scored else None,
            ),
        )
        statements[name] = stmt
    if not omit:
        pp.commit()
    return pp, statements


def _numbers(payload: Any) -> list[float]:
    """Every numeric leaf, bools excluded — `complete` is structure, not a score
    (and `bool` is an `int` in Python, which is how it sneaks into such a check).
    """
    return [
        leaf
        for leaf in _values(payload)
        if isinstance(leaf, (int, float)) and not isinstance(leaf, bool)
    ]


def _values(payload: Any) -> Iterator[Any]:
    """Every leaf value of a `to_dict()`, keys excluded.

    Keys are the renderer's own vocabulary (`t_plus`, `diagonals`) and are never
    shown to a person; values are.
    """
    if isinstance(payload, dict):
        for value in payload.values():
            yield from _values(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _values(item)
    else:
        yield payload


class TestATetradIsDrawable:
    def test_every_position_is_read_with_its_text_label_and_hash(self):
        with scope(_new_sid()):
            pp, statements = _tetrad()
            view = perspective_view(pp)

            assert view.complete is True
            assert set(view.poles) == {"t", "a", "t_plus", "t_minus", "a_plus", "a_minus"}
            assert view.t.text == "Control"
            assert view.t.position == POSITION_T
            assert view.t_plus.position == POSITION_T_PLUS
            assert view.t_plus.label == "T1+", "the stored alias, not the position"
            for name, stmt in statements.items():
                assert getattr(view, name).hash == stmt.hash, (
                    f"{name} must carry the FULL hash a host clicks through with"
                )
            assert view.hash == pp.hash

    def test_the_scores_are_read_off_the_edges(self):
        with scope(_new_sid()):
            pp, _ = _tetrad()
            view = perspective_view(pp)

            assert view.t_plus.hs == 0.9
            assert (view.t_plus.k_t, view.t_plus.k_a) == (0.8, 0.6)
            assert view.t_plus.ks == pytest.approx(0.7), "Ks survives to_dict as a field"
            assert view.t.hs == 1.0, "T defines the apex"
            assert view.t.ks is None, "T/A carry no complementarity — only aspects do"

    def test_a_display_override_carries_its_canonical_text(self):
        with scope(_new_sid()):
            pp, statements = _tetrad()
            statements["t_plus"].display_text = "Steadiness people can lean on"
            statements["t_plus"].save()

            view = perspective_view(pp)
            assert view.t_plus.text == "Steadiness people can lean on"
            assert view.t_plus.canonical_text == statements["t_plus"].text
            assert view.t.canonical_text is None, "filled only when the two differ"

    def test_the_metrics_come_from_the_perspective_properties(self):
        """Asserted against the properties themselves: `area` and
        `rectangularity` carry "do not fix this formula" notes and must keep
        exactly one owner."""
        with scope(_new_sid()):
            pp, _ = _tetrad()
            metrics = perspective_view(pp).metrics

            assert metrics is not None
            assert metrics.sp == pp.area
            assert metrics.sp_normalized == pp.area_normalized
            assert metrics.rectangularity == pp.rectangularity
            assert (metrics.diff_t, metrics.diff_a) == (pp.diff_t, pp.diff_a)
            # The fixture is really scored (otherwise the equalities above would
            # hold at None on both sides and prove nothing).
            assert metrics.sp == pytest.approx(1.0)
            assert metrics.sp_normalized == pytest.approx(0.5)

    def test_the_intent_is_the_nodes_own_verbatim(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(intent="Reading along: growth / security")
            assert perspective_view(pp).intent == "Reading along: growth / security"
            free, _ = _tetrad(prefix="f ", intent="the founders' own framing")
            assert perspective_view(free).intent == "the founders' own framing", (
                "free text is carried as free text, never parsed or dropped"
            )
            none, _ = _tetrad(prefix="n ")
            assert perspective_view(none).intent is None

    def test_to_dict_is_json_ready(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(intent="Reading along: growth / security")
            payload = perspective_view(pp).to_dict()

            reloaded = json.loads(json.dumps(payload))
            assert reloaded["t_plus"]["ks"] == pytest.approx(0.7)
            assert reloaded["metrics"]["sp"] == pytest.approx(1.0)
            assert reloaded["intent"] == "Reading along: growth / security"


class TestAbsenceIsNoneNotZero:
    def test_an_unscored_tetrad_has_no_metrics(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(scored=False)
            view = perspective_view(pp)

            assert view.metrics is None, "no metrics at all, not five zeros"
            assert view.t_plus.ks is None
            assert view.t_plus.hs == 0.9, "HS is scored by a different call and survives"
            assert view.complete is True, "unscored is not unfinished"

    def test_a_missing_position_is_none_and_the_tetrad_is_not_complete(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(omit=("a_minus",))
            view = perspective_view(pp)

            assert view.a_minus is None, "an empty-string pole would draw a blank corner"
            assert "a_minus" not in view.poles
            assert view.complete is False
            # Each metric is independently None: the two that need A- are gone,
            # the T-side gap is still real and still worth showing.
            metrics = view.metrics
            assert metrics is not None
            assert (metrics.sp, metrics.sp_normalized, metrics.diff_a) == (None, None, None)
            assert metrics.diff_t == pytest.approx(0.5)

    def test_a_perspective_without_a_polarity_draws_empty_rather_than_raising(self):
        """No Polarity means no position is readable — the lookup itself reaches
        through it — and the honest end of that for a host is an empty tetrad,
        never an exception in a render path."""
        with scope(_new_sid()):
            pp = Perspective()
            pp.save()
            pp.t_plus.connect(
                _stmt("Safety through structure"),
                relationship=TPlusRelationship(alias="T1+"),
            )
            view = perspective_view(pp)

            assert view.poles == {}
            assert view.complete is False

    def test_an_unvalidated_tetrad_says_none_rather_than_passed(self):
        with scope(_new_sid()):
            pp, _ = _tetrad()
            assert perspective_view(pp).validation is None

            pp.validation = "failed: T+ does not balance A-"
            pp.save()
            assert perspective_view(pp).validation == "failed: T+ does not balance A-"
            assert perspective_view(pp).complete is True, "validation is never a gate"


class TestWithoutTerminology:
    """The picture's half of the disclosure policy (`reply_hygiene` is the text's)."""

    def test_the_texts_and_the_reading_survive(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(intent="Reading along: growth / security")
            hidden = perspective_view(pp).without_terminology()

            assert hidden.t.text == "Control"
            assert len(hidden.poles) == 6, "a full tetrad is still a full tetrad"
            assert hidden.intent == "Reading along: growth / security", (
                "the reading names the axes in the person's terms; nothing to hide"
            )
            assert hidden.complete is True

    def test_nothing_the_text_filter_removes_is_left_in_the_picture(self):
        with scope(_new_sid()):
            pp, statements = _tetrad(intent="Reading along: growth / security")
            pp.validation = "passed"
            pp.save()
            hidden = perspective_view(pp).without_terminology()
            leaves = list(_values(hidden.to_dict()))

            for position in _ALL_POSITIONS:
                assert position not in leaves, f"{position} would be drawn on screen"
            for alias in _ALIASES.values():
                assert alias not in leaves
            hashes = {s.hash for s in statements.values()} | {pp.hash}
            assert not (hashes & {leaf for leaf in leaves if isinstance(leaf, str)})
            assert _numbers(hidden.to_dict()) == [], (
                "every number on a tetrad is machinery: scores, indices, metrics"
            )
            assert "passed" not in leaves, "a validation verdict is machinery too"

    def test_a_pole_keeps_only_what_a_person_reads(self):
        pole = PoleView(
            text="Steadiness",
            canonical_text="Control",
            position=POSITION_T_PLUS,
            label="T1+",
            hash="abc123",
            hs=0.9,
            k_t=0.8,
            k_a=0.6,
            ks=0.7,
        )
        hidden = pole.without_terminology()

        assert (hidden.text, hidden.canonical_text) == ("Steadiness", "Control")
        assert list(_values(hidden.__dict__)) == ["Steadiness", "Control"] + [None] * 7

    def test_an_unfinished_tetrad_projects_without_inventing_poles(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(omit=("a_minus",))
            hidden = perspective_view(pp).without_terminology()
            assert hidden.a_minus is None
            assert len(hidden.poles) == 5


@pytest.mark.usefixtures("di_container")
class TestAWheelIsDrawable:
    @staticmethod
    def _wheel(sid_scoped: bool = True):
        """Two tensions on one wheel, arranged so both orientations occur.

        The transition chain starts on pp1's T side and passes through pp2's A
        side, which is what makes `_derive_polar_segments_from_edges` read pp1 as
        "normal" and pp2 as "swapped".
        """
        pp1, one = _tetrad(thesis="Control", antithesis="Freedom", prefix="w1 ")
        pp2, two = _tetrad(thesis="Speed", antithesis="Care", prefix="w2 ")
        cycle, wheel, transitions = create_cycle_wheel_setup(
            pps=[pp1, pp2],
            components_for_transitions=[
                one["t_minus"], two["a_plus"], two["a_minus"], one["t_plus"],
            ],
        )
        wheel.commit()
        return wheel, (pp1, pp2), (one, two), transitions

    def test_the_segments_keep_the_wheels_own_arrangement(self):
        with scope(_new_sid()):
            wheel, (pp1, pp2), _, _ = self._wheel()
            view = wheel_view(wheel)

            pairs = wheel.polar_segments
            assert [(s.place, s.tetrad.hash) for s in view.segments] == [
                (place, pair.perspective.hash) for place, pair in enumerate(pairs)
            ], "polar_segments order IS the wheel — the view must not reorder it"
            assert [s.orientation for s in view.segments] == [
                pair.polarity for pair in pairs
            ]
            assert {s.orientation for s in view.segments} == {"normal", "swapped"}, (
                "the fixture must exercise the swapped branch to be worth anything"
            )
            assert view.layer == 2
            assert {s.tetrad.hash for s in view.segments} == {pp1.hash, pp2.hash}

    def test_the_segments_are_full_tetrads(self):
        with scope(_new_sid()):
            wheel, _, _, _ = self._wheel()
            view = wheel_view(wheel)

            first = view.segments[0].tetrad
            assert first.complete is True
            assert first.metrics is not None and first.metrics.sp == pytest.approx(1.0)

    def test_the_spiral_reuses_the_segment_poles(self):
        with scope(_new_sid()):
            wheel, _, (one, two), _ = self._wheel()
            view = wheel_view(wheel)

            assert len(view.spiral) == len(wheel.edges)
            endpoints = {
                (step.source.hash, step.target.hash) for step in view.spiral
            }
            assert (one["t_minus"].hash, two["a_plus"].hash) in endpoints
            for step in view.spiral:
                for pole in (step.source, step.target):
                    assert pole is not None
                    assert pole.position in _ALL_POSITIONS, (
                        "an endpoint re-read from the statement alone would carry "
                        "no position and a widget could not highlight both ends"
                    )
                    assert pole.label in _ALIASES.values()

    def test_causality_is_none_until_it_is_estimated(self):
        with scope(_new_sid()):
            wheel, _, _, _ = self._wheel()
            assert wheel_view(wheel).causality is None, (
                "never -1.0: a widget would draw the sentinel"
            )

            EstimationManager().upsert_estimation(
                wheel, CausalityProbabilityEstimation, 0.42
            )
            assert wheel_view(wheel).causality == pytest.approx(0.42)

    def test_completeness_counts_the_expected_transformations(self):
        with scope(_new_sid()):
            wheel, _, _, _ = self._wheel()
            view = wheel_view(wheel)

            # 4 edges × 3 insight categories = 6N at N=2, none built.
            assert view.completeness == "0/12"
            assert view.complete is False
            assert view.synthesis is None, "not generated is not an empty synthesis"

    def test_without_terminology_strips_the_whole_arrangement(self):
        with scope(_new_sid()):
            wheel, _, _, _ = self._wheel()
            EstimationManager().upsert_estimation(
                wheel, CausalityProbabilityEstimation, 0.42
            )
            hidden = wheel_view(wheel).without_terminology()
            leaves = list(_values(hidden.to_dict()))

            assert hidden.layer == 2, "how many tensions is structure, not machinery"
            assert len(hidden.segments) == 2 and len(hidden.spiral) == len(wheel.edges)
            assert hidden.causality is None and hidden.completeness is None
            for position in _ALL_POSITIONS:
                assert position not in leaves
            assert wheel.hash not in leaves
            assert set(_numbers(hidden.to_dict())) == {0, 1, 2}, (
                "the only numbers left are geometry: places 0 and 1 around the "
                "circle, and the layer (2 tensions)"
            )

    def test_to_dict_is_json_ready(self):
        with scope(_new_sid()):
            wheel, _, _, _ = self._wheel()
            reloaded = json.loads(json.dumps(wheel_view(wheel).to_dict()))
            assert reloaded["layer"] == 2
            assert reloaded["segments"][0]["tetrad"]["t"]["text"]


class TestTheExplorationView:
    def test_a_nexus_map_numbers_its_members_as_the_prompts_do(self):
        from dialectical_framework.graph.rendering import build_pp_index

        with scope(_new_sid()):
            pp1, _ = _tetrad(thesis="Control", antithesis="Freedom", prefix="n1 ")
            pp2, _ = _tetrad(thesis="Speed", antithesis="Care", prefix="n2 ")
            nexus = Nexus(intent="the map")
            nexus.save()
            nexus.commit()
            pp1.nexus.connect(nexus)
            pp2.nexus.connect(nexus)

            view = exploration_view(nexus)

            assert view.nexus_hash == nexus.hash
            assert {t.hash for t in view.perspectives} == {pp1.hash, pp2.hash}
            index = build_pp_index(nexus)
            assert [t.index for t in view.perspectives] == [
                index[pp._id] for pp in (pp1, pp2)
            ], "T1 must mean the same perspective in the picture and in the prompt"

    def test_a_standalone_tetrad_has_no_index(self):
        with scope(_new_sid()):
            pp, _ = _tetrad()
            assert perspective_view(pp).index is None, (
                "no exploration here — not an unknown index"
            )

    def test_without_a_nexus_every_active_tetrad_is_in_the_map(self):
        with scope(_new_sid()):
            kept, _ = _tetrad(thesis="Control", antithesis="Freedom", prefix="m1 ")
            dropped, _ = _tetrad(thesis="Speed", antithesis="Care", prefix="m2 ")
            dropped.discarded = "superseded by the reframing"
            dropped.save()

            view = exploration_view()

            assert view.nexus_hash is None
            assert [t.hash for t in view.perspectives] == [kept.hash]

    def test_a_discarded_member_is_not_drawn(self):
        with scope(_new_sid()):
            kept, _ = _tetrad(thesis="Control", antithesis="Freedom", prefix="d1 ")
            dropped, _ = _tetrad(thesis="Speed", antithesis="Care", prefix="d2 ")
            nexus = Nexus(intent="with a discard")
            nexus.save()
            nexus.commit()
            kept.nexus.connect(nexus)
            dropped.nexus.connect(nexus)
            dropped.discarded = "the person withdrew it"
            dropped.save()

            view = exploration_view(nexus)
            assert [t.hash for t in view.perspectives] == [kept.hash]

    def test_an_empty_scope_maps_to_an_empty_list(self):
        with scope(_new_sid()):
            assert exploration_view().perspectives == []


@pytest.mark.llm
class TestTheAdvisorDrawsWhatItSees:
    """`Advisor.exploration_view()` = the module function resolved through the
    seat: the pin picks the exploration, `hides_terminology` picks the
    projection. The host holds neither."""

    @pytest.mark.asyncio
    async def test_unpinned_and_hidden_is_the_whole_case_without_machinery(self):
        with scope(_new_sid()):
            pp, _ = _tetrad(intent="Reading along: growth / security")
            advisor = Advisor(app_preamble="You are a thinking partner.")

            view = await advisor.exploration_view()

            assert view.nexus_hash is None
            assert [p.t.text for p in view.perspectives] == ["Control"]
            assert view.perspectives[0].hash is None, "hidden: no hash on the picture"
            assert view.perspectives[0].t_plus.position is None
            assert view.perspectives[0].intent == "Reading along: growth / security"

    @pytest.mark.asyncio
    async def test_pinned_and_disclosed_is_that_exploration_with_everything(self):
        with scope(_new_sid()):
            member, _ = _tetrad(thesis="Control", antithesis="Freedom", prefix="m ")
            _tetrad(thesis="Speed", antithesis="Care", prefix="o ")  # outside the pin
            nexus = Nexus(intent="the pin")
            nexus.save()
            nexus.commit()
            member.nexus.connect(nexus)
            advisor = Advisor(
                nexus_hash=nexus.hash,
                app_preamble="## Terminology Disclosure\nHashes are the person's own.",
            )

            view = await advisor.exploration_view()

            assert view.nexus_hash == nexus.hash
            assert [p.hash for p in view.perspectives] == [member.hash], (
                "the pin protects other structure: only members are drawn"
            )
            assert view.perspectives[0].index == 1
            assert view.perspectives[0].t_plus.position == POSITION_T_PLUS

    @pytest.mark.asyncio
    async def test_a_pin_whose_nexus_is_gone_draws_nothing(self, monkeypatch):
        """The constructor validates the pin, so this is a nexus deleted AFTER
        construction (a stateless host resuming a stale pin). The guard must
        draw nothing rather than fall through to the whole case."""
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        with scope(_new_sid()):
            _tetrad()
            nexus = Nexus(intent="soon gone")
            nexus.save()
            nexus.commit()
            advisor = Advisor(nexus_hash=nexus.hash, app_preamble="x")
            monkeypatch.setattr(NexusRepository, "find_by_hash_prefix", lambda self, h: None)

            view = await advisor.exploration_view()

            assert view.perspectives == [], "never the whole case past a pin"


@pytest.mark.llm
class TestTheHostReadsOneDisclosureFlag:
    """One flag, two enforcement points: `reply_hygiene` filters the TEXT, the
    host filters the PICTURE. A host deciding this for itself would eventually
    disagree with the filter, and the disagreement shows as `T+` on screen in a
    conversation whose prose is scrubbed of it."""

    def test_a_silent_head_hides_its_terminology(self):
        with scope(_new_sid()):
            advisor = Advisor(app_preamble="You are a thinking partner.")
            assert advisor.hides_terminology is True
            assert advisor.hides_terminology is advisor._hides_hashes

    def test_a_head_granted_disclosure_does_not(self):
        with scope(_new_sid()):
            advisor = Advisor(
                app_preamble="## Terminology Disclosure\nHashes are the person's own addresses."
            )
            assert advisor.hides_terminology is False
            assert advisor.hides_terminology is advisor._hides_hashes
