"""
`concerns/consultation_sketch.py` and `Consultant.sketch()` — the picture a
graphless head can draw.

What is pinned, and why each is worth a test:

1. **Same shape as the graph reader, by construction terminology-free.** The
   sketch must land in `TensionMapView` with the texts where the widget expects
   them, the two diagonals labelled with the person's own axis words — and
   NOTHING else: no position, alias, hash or number anywhere in the serialized
   result, because there is none to give and a future "improvement" that adds
   a guessed score would be an unchecked number dressed as a measurement.
2. **Absence is `None` here too.** A position the model leaves blank is a
   `None` pole and `complete` is False; a "tension" with no thesis or no
   antithesis is not drawn at all.
3. **No material, no call.** An empty conversation is an empty map and the
   provider is never asked.
4. **The speaker rule holds at the head.** `Consultant.sketch()` passes the
   person's turns only; the replies are counsel, never material — the same
   rule the migration runs on, for the same reason.
5. **The geometry has one owner.** The sketch's diagonals are
   `views.diagonals_for`'s, so the graph reader and the sketch cannot disagree
   about which field faces which.

DB-free: nothing here touches the graph, and that is itself the guarantee —
the sketch runs with no scope installed.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.concerns import consultation_sketch as sketch_mod
from dialectical_framework.concerns.consultation_sketch import (
    SKETCH_MAX_TENSIONS, ConsultationSketch, ConsultationSketchDto,
    SketchedTensionDto, sketch_view, tetrad_from_sketch)
from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS
from dialectical_framework.graph.views import TensionMapView, diagonals_for


# DB-free: override the autouse graph fixtures (per CLAUDE.md DB-free convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _tension(**overrides: str) -> SketchedTensionDto:
    fields = dict(
        thesis="Keep the Berlin office",
        antithesis="Consolidate everything in Zurich",
        t_plus_vs_a_minus_axis="local presence",
        t_plus="Berlin stays close to the German clients",
        a_minus="Zurich alone loses the German market",
        a_plus_vs_t_minus_axis="focus",
        a_plus="One team, one roadmap",
        t_minus="Two half-teams that never align",
    )
    fields.update(overrides)
    return SketchedTensionDto(**fields)


def _values(payload: Any) -> Iterator[Any]:
    if isinstance(payload, dict):
        for value in payload.values():
            yield from _values(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _values(item)
    else:
        yield payload


def _fake_ask(monkeypatch, dto: ConsultationSketchDto) -> list[str]:
    """Stand in for the one provider call; records the prompts it was given."""
    prompts: list[str] = []

    async def fake(self, prompt: str) -> ConsultationSketchDto:
        prompts.append(prompt)
        return dto

    monkeypatch.setattr(ConsultationSketch, "_ask", fake)
    return prompts


class TestTheSketchIsTheSamePicture:
    def test_a_tension_lands_in_the_view_shape(self):
        view = tetrad_from_sketch(_tension())

        assert view.complete is True
        assert view.t.text == "Keep the Berlin office"
        assert view.a.text == "Consolidate everything in Zurich"
        assert view.t_plus.text == "Berlin stays close to the German clients"
        assert view.a_minus.text == "Zurich alone loses the German market"
        assert view.a_plus.text == "One team, one roadmap"
        assert view.t_minus.text == "Two half-teams that never align"
        assert view.axes == ["local presence", "focus"]
        assert [(d.positive, d.negative, d.axis) for d in view.diagonals] == [
            ("t_plus", "a_minus", "local presence"),
            ("a_plus", "t_minus", "focus"),
        ]
        assert view.reading is None, "there is no Perspective.intent to quote"

    def test_the_geometry_is_the_readers_own(self):
        view = tetrad_from_sketch(_tension())
        assert view.diagonals == diagonals_for(view.axes)

    def test_one_dimension_named_twice_is_one_axis(self):
        view = tetrad_from_sketch(
            _tension(t_plus_vs_a_minus_axis="Focus", a_plus_vs_t_minus_axis="focus")
        )
        assert view.axes == ["Focus"]
        assert [d.axis for d in view.diagonals] == ["Focus", "Focus"]

    def test_nothing_but_texts_and_geometry_is_in_it(self):
        """Terminology-free by construction: `without_terminology()` must be a
        no-op, and no position, alias, hash or number may appear anywhere."""
        view = sketch_view(ConsultationSketchDto(tensions=[_tension()]))
        payload = view.to_dict()

        assert view.without_terminology() == view
        assert view.nexus_hash is None
        leaves = list(_values(payload))
        for banned in ("T", "A", "T+", "T-", "A+", "A-", "T1+"):
            assert banned not in leaves
        numbers = [
            v for v in leaves if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        assert numbers == [], "a number here would be an unchecked guess"
        json.dumps(payload)  # JSON-ready, like the graph reader's

    def test_a_tetrad_carries_no_score_fields_to_fill(self):
        """The DTO has no numeric field at all — the guard against the next
        session adding `heuristic_similarity: float` "for completeness"."""
        for name, field in SketchedTensionDto.model_fields.items():
            assert field.annotation is str, f"{name} is not a text"


class TestAbsenceIsNoneHereToo:
    def test_a_blank_position_is_a_none_pole(self):
        view = tetrad_from_sketch(_tension(a_minus="   "))
        assert view.a_minus is None
        assert view.complete is False
        assert "a_minus" not in view.poles

    def test_a_tension_without_both_ends_is_not_drawn(self):
        view = sketch_view(
            ConsultationSketchDto(tensions=[_tension(), _tension(antithesis="")])
        )
        assert len(view.tetrads) == 1

    def test_a_blank_axis_leaves_the_diagonal_unlabelled(self):
        view = tetrad_from_sketch(_tension(a_plus_vs_t_minus_axis=""))
        assert view.axes == ["local presence"]
        # One named axis is read as the dimension of both diagonals — the same
        # convention the reading parser applies.
        assert [d.axis for d in view.diagonals] == ["local presence"] * 2

    def test_the_map_is_capped(self):
        many = ConsultationSketchDto(tensions=[_tension()] * (SKETCH_MAX_TENSIONS + 3))
        assert len(sketch_view(many).tetrads) == SKETCH_MAX_TENSIONS


@pytest.mark.llm
class TestTheConcern:
    @pytest.mark.asyncio
    async def test_nothing_said_means_no_call_and_an_empty_map(self, monkeypatch):
        prompts = _fake_ask(monkeypatch, ConsultationSketchDto(tensions=[_tension()]))
        concern = ConsultationSketch()

        view = await concern.resolve(turns=["", "   "])

        assert view == TensionMapView()
        assert prompts == [], "the provider must not be asked about nothing"
        assert concern.report.ok is True

    @pytest.mark.asyncio
    async def test_the_turns_reach_the_prompt_and_the_map_comes_back(self, monkeypatch):
        prompts = _fake_ask(monkeypatch, ConsultationSketchDto(tensions=[_tension()]))
        concern = ConsultationSketch()

        view = await concern.resolve(
            turns=["I can't decide about the Berlin office.", "Twelve people work there."]
        )

        assert len(view.tetrads) == 1
        assert len(prompts) == 1
        assert "I can't decide about the Berlin office." in prompts[0]
        assert "Twelve people work there." in prompts[0]
        assert str(SKETCH_MAX_TENSIONS) in prompts[0]
        assert "Sketched 1 tension(s)" in concern.report.summary

    @pytest.mark.asyncio
    async def test_it_runs_with_no_scope_under_the_mock_brain(self):
        """End to end through the facilitator, no `scope()` installed: the
        mocked DTO carries no tensions, so the map is empty — what is pinned is
        that nothing on the path needs a Case or the graph."""
        view = await ConsultationSketch().resolve(turns=["I have a problem with my wife."])
        assert isinstance(view, TensionMapView)
        assert view.tetrads == []

    def test_the_prompt_reads_the_shared_aspect_definitions(self):
        """Never re-typed inline: the definitions drift otherwise (CLAUDE.md)."""
        assert ASPECT_DEFINITIONS in sketch_mod.SYSTEM_PROMPT


@pytest.mark.llm
class TestTheHeadAppliesTheSpeakerRule:
    @pytest.mark.asyncio
    async def test_sketch_passes_the_persons_turns_only(self, monkeypatch):
        seen: list[list[str]] = []

        async def fake_resolve(self, turns):
            seen.append(list(turns))
            return TensionMapView()

        monkeypatch.setattr(ConsultationSketch, "resolve", fake_resolve)
        head = Consultant(
            app_preamble="You are a thinking partner.",
            messages=[
                {"role": "user", "content": "I can't decide about the Berlin office."},
                {"role": "assistant", "content": "What would closing it cost you?"},
                {"role": "user", "content": "Twelve people, and the German clients."},
            ],
        )

        view = await head.sketch()

        assert isinstance(view, TensionMapView)
        assert seen == [
            ["I can't decide about the Berlin office.", "Twelve people, and the German clients."]
        ], "the reply is counsel, not material"

    @pytest.mark.asyncio
    async def test_a_sketch_is_not_a_turn(self, monkeypatch):
        async def fake_resolve(self, turns):
            return TensionMapView()

        monkeypatch.setattr(ConsultationSketch, "resolve", fake_resolve)
        head = Consultant(
            app_preamble="x", messages=[{"role": "user", "content": "Hello there."}]
        )
        # The head prepends its system message at construction; what must not
        # move is the history AS THE HEAD HOLDS IT once constructed.
        before = list(head.messages)

        await head.sketch()

        assert head.messages == before, "a read over the conversation writes nothing into it"
