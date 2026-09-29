"""
`Consultant.exploration_view(focus=)` and `concerns/view_sketch.py` —
the view a graphless head draws of its own conversation.

What is pinned, and why each is worth a test:

1. **It is a turn on the consultant's OWN conversation.** Same history object,
   both sides in it, its own system prompt at the top — not a fresh
   conversation handed half the transcript. The view can therefore not
   disagree with the prose the person just read.
2. **What it draws, it remembers.** The turn stays in `messages` as the
   consultant's own words (`history_text`), never as a DTO repr, so the next
   turn can be asked about a corner it drew.
3. **It thinks.** The turn runs json-mode at the session's thinking level —
   the one structured shape that can think; `None` stays off.
4. **Same shape as the graph reader, terminology-free by construction.** Texts
   and the reading (`intent`, composed by `Perspective.compose_reading` after
   the graph path's own disclaimer filter); no position, alias, hash or number
   anywhere; `without_terminology()` is a no-op.
5. **Absence is `None` here too.** A corner the ask did not reach is a `None`
   pole and `complete` is False; a thesis with no antithesis yet is still
   drawn (a real state of a conversation); a "tension" with no thesis is not.

DB-free: nothing here touches the graph, which is itself the guarantee — the
view turn runs with no scope installed.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from mirascope import llm

from dialectical_framework.agents.advisor.migration import message_text
from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.view_sketch import (
    VIEW_SKETCH_MAX_PERSPECTIVES, ViewSketchDto, ViewSketchPerspectiveDto,
    history_text, perspective_from_sketch, view_sketch_prompt, exploration_view_from_sketch)
from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.views import ExplorationView


# DB-free: override the autouse graph fixtures (per CLAUDE.md DB-free convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


_HISTORY = [
    {"role": "user", "content": "I can't decide about the Berlin office."},
    {"role": "assistant", "content": "What would closing it cost you?"},
    {"role": "user", "content": "Twelve people, and the German clients."},
]


def _tension(**overrides: str) -> ViewSketchPerspectiveDto:
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
    return ViewSketchPerspectiveDto(**fields)


def _values(payload: Any) -> Iterator[Any]:
    if isinstance(payload, dict):
        for value in payload.values():
            yield from _values(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _values(item)
    else:
        yield payload


def _fake_submit(monkeypatch, dto: ViewSketchDto) -> list[dict]:
    """Stand in for the view turn's provider call, faithfully: the real
    `submit` appends the request and then the DTO's repr as the assistant
    message, which is exactly what `exploration_view` must then replace."""
    calls: list[dict] = []

    async def fake(self, response_model, user_content, max_tool_rounds=10):
        calls.append({"facilitator": self, "prompt": user_content, "model": response_model})
        self._messages.append(llm.messages.user(user_content))
        self._messages.append(llm.messages.assistant(str(dto), model_id=None, provider_id=None))
        return dto

    monkeypatch.setattr(ConversationFacilitator, "submit", fake)
    return calls


def _roles(messages: list) -> list[str]:
    return [getattr(m, "role", None) or m.get("role") for m in messages]


# --- the shaping (pure) ---------------------------------------------------


class TestTheSketchIsTheSamePicture:
    def test_a_tension_lands_in_the_view_shape(self):
        view = perspective_from_sketch(_tension())

        assert view.complete is True
        assert view.t.text == "Keep the Berlin office"
        assert view.a.text == "Consolidate everything in Zurich"
        assert view.t_plus.text == "Berlin stays close to the German clients"
        assert view.a_minus.text == "Zurich alone loses the German market"
        assert view.a_plus.text == "One team, one roadmap"
        assert view.t_minus.text == "Two half-teams that never align"
        assert view.intent == "Reading along: local presence / focus"

    def test_the_reading_is_composed_the_graphs_way(self):
        view = perspective_from_sketch(_tension())
        assert view.intent == Perspective.compose_reading(
            {"t_plus_vs_a_minus": "local presence", "a_plus_vs_t_minus": "focus"}
        )

    def test_one_dimension_named_twice_is_one_axis(self):
        view = perspective_from_sketch(
            _tension(t_plus_vs_a_minus_axis="Focus", a_plus_vs_t_minus_axis="focus")
        )
        assert view.intent == "Reading along: Focus"

    def test_a_disclaimer_is_not_an_axis(self):
        view = perspective_from_sketch(
            _tension(t_plus_vs_a_minus_axis="no genuine shared dimension exists")
        )
        assert view.intent == "Reading along: focus"

    def test_nothing_but_texts_and_the_reading_is_in_it(self):
        view = exploration_view_from_sketch(ViewSketchDto(tensions=[_tension()]))
        payload = view.to_dict()

        assert view.without_terminology() == view
        assert view.nexus_hash is None
        leaves = list(_values(payload))
        for banned in ("T", "A", "T+", "T-", "A+", "A-", "T1+"):
            assert banned not in leaves
        assert [
            v for v in leaves if isinstance(v, (int, float)) and not isinstance(v, bool)
        ] == [], "a number here would be an unchecked guess"
        json.dumps(payload)

    def test_a_tetrad_carries_no_score_fields_to_fill(self):
        for name, field in ViewSketchPerspectiveDto.model_fields.items():
            assert field.annotation is str, f"{name} is not a text"


class TestAbsenceIsNoneHereToo:
    def test_a_blank_position_is_a_none_pole(self):
        view = perspective_from_sketch(_tension(a_minus="   "))
        assert view.a_minus is None
        assert view.complete is False
        assert "a_minus" not in view.poles

    def test_the_two_poles_alone_are_an_unfinished_perspective(self):
        """"Show me the two sides": four blank corners, drawn as unfinished —
        never filled in to look complete."""
        view = perspective_from_sketch(
            _tension(t_plus="", t_minus="", a_plus="", a_minus="",
                     t_plus_vs_a_minus_axis="", a_plus_vs_t_minus_axis="")
        )
        assert set(view.poles) == {"t", "a"}
        assert view.complete is False
        assert view.intent is None

    def test_a_thesis_with_no_antithesis_yet_is_still_drawn(self):
        view = exploration_view_from_sketch(ViewSketchDto(tensions=[_tension(antithesis="")]))
        assert len(view.perspectives) == 1
        assert view.perspectives[0].a is None

    def test_a_tension_with_no_thesis_is_not_drawn(self):
        view = exploration_view_from_sketch(
            ViewSketchDto(tensions=[_tension(), _tension(thesis="  ")])
        )
        assert len(view.perspectives) == 1

    def test_a_blank_axis_leaves_a_one_axis_reading(self):
        view = perspective_from_sketch(_tension(a_plus_vs_t_minus_axis=""))
        assert view.intent == "Reading along: local presence"

    def test_the_picture_is_capped(self):
        many = ViewSketchDto(tensions=[_tension()] * (VIEW_SKETCH_MAX_PERSPECTIVES + 3))
        assert len(exploration_view_from_sketch(many).perspectives) == VIEW_SKETCH_MAX_PERSPECTIVES


class TestTheRequestAndTheRecord:
    def test_the_prompt_carries_the_focus_and_the_shared_definitions(self):
        prompt = view_sketch_prompt("the antitheses we discussed", 7)
        assert "What to show: the antitheses we discussed" in prompt
        assert ASPECT_DEFINITIONS in prompt, "never re-typed inline (CLAUDE.md)"
        assert "7 words or fewer" in prompt
        assert str(VIEW_SKETCH_MAX_PERSPECTIVES) in prompt
        assert "build it now" in prompt, "the ask may require reasoning, not just rendering"

    def test_no_focus_asks_for_what_is_established(self):
        assert "worked out so far" in view_sketch_prompt(None, 7)
        assert "worked out so far" in view_sketch_prompt("   ", 7)

    def test_the_history_record_is_words_with_the_corners_named(self):
        text = history_text(exploration_view_from_sketch(ViewSketchDto(tensions=[_tension()])))
        assert text.startswith("I drew the structure we have so far:")
        assert "T: Keep the Berlin office" in text
        assert "A-: Zurich alone loses the German market" in text
        assert "(Reading along: local presence / focus)" in text
        assert "ViewSketchPerspectiveDto(" not in text, "never a repr in the history"

    def test_an_empty_picture_is_recorded_as_such(self):
        assert history_text(ExplorationView()).startswith("I drew nothing")


# --- the head ---------------------------------------------------------------


@pytest.mark.llm
class TestThePictureIsATurnOnTheConsultantsOwnConversation:
    @pytest.mark.asyncio
    async def test_it_shares_the_history_and_sees_both_sides(self, monkeypatch):
        calls = _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        head = Consultant(app_preamble="You are a thinking partner.", messages=list(_HISTORY))

        view = await head.exploration_view(focus="a perspective for the office question")

        (call,) = calls
        sketch_turn = call["facilitator"]
        assert sketch_turn is not head._conversation, "a second facilitator..."
        assert sketch_turn._messages is head._conversation._messages, "...over the SAME history"
        assert sketch_turn._format_mode == "json"
        assert call["model"] is ViewSketchDto
        assert "What to show: a perspective for the office question" in call["prompt"]
        # Both sides were in front of the model, and its own system prompt led.
        texts = [message_text(m) for m in sketch_turn._messages]
        assert any("What would closing it cost you?" in t for t in texts), (
            "the counselor's own framing is material for the view"
        )
        assert _roles(sketch_turn._messages)[0] == "system"
        assert [p.t.text for p in view.perspectives] == ["Keep the Berlin office"]

    @pytest.mark.asyncio
    async def test_what_it_drew_stays_in_the_history_as_words(self, monkeypatch):
        _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        before = len(head.messages)

        await head.exploration_view()

        assert len(head.messages) == before + 2, "the request and the record: one turn"
        assert _roles(head.messages)[-2:] == ["user", "assistant"]
        last = message_text(head.messages[-1])
        assert last.startswith("I drew the structure we have so far:")
        assert "Keep the Berlin office" in last
        assert "ViewSketchPerspectiveDto(" not in last, "the DTO repr was replaced"

    @pytest.mark.asyncio
    async def test_it_thinks_at_the_sessions_level(self, monkeypatch):
        calls = _fake_submit(monkeypatch, ViewSketchDto(tensions=[]))
        await Consultant(app_preamble="x", thinking="medium").exploration_view()
        assert calls[-1]["facilitator"]._structured_thinking == "medium"

        await Consultant(app_preamble="x", thinking=None).exploration_view()
        assert calls[-1]["facilitator"]._structured_thinking is None, "off means off"

    @pytest.mark.asyncio
    async def test_it_runs_end_to_end_under_the_mock_brain_with_no_scope(self):
        """Through the real `submit`: the mocked DTO holds no tensions, so the
        view is empty and the record says so. What is pinned is that nothing
        on the path needs a Case or the graph, and the history is left well-formed."""
        head = Consultant(app_preamble="x", messages=list(_HISTORY))

        view = await head.exploration_view()

        assert isinstance(view, ExplorationView)
        assert view.perspectives == []
        assert _roles(head.messages)[-2:] == ["user", "assistant"]
        assert message_text(head.messages[-1]).startswith("I drew nothing")

    def test_the_head_still_holds_no_tools(self):
        """The view is a method the HOST calls; the prompt's "You have no
        tools" must stay true."""
        assert Consultant(app_preamble="x")._conversation._tools == []
