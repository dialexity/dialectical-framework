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

import httpx
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
        from dialectical_framework.concerns.antithesis_extraction import \
            _OPPOSING_POSITION_ASK

        assert _OPPOSING_POSITION_ASK in prompt, (
            "the antithesis is asked for as a position, as on the ladder and the "
            "one-shot build — without it the view turn drew mirrors for 6/40"
        )

    def test_no_focus_asks_for_what_is_established(self):
        assert "worked out so far" in view_sketch_prompt(None, 7)
        assert "worked out so far" in view_sketch_prompt("   ", 7)

    def test_the_history_record_is_words_in_the_persons_terms(self):
        text = history_text(exploration_view_from_sketch(ViewSketchDto(tensions=[_tension()])))
        assert text.startswith("I drew the structure we have so far:")
        assert 'Tension: "Keep the Berlin office" against "Consolidate everything in Zurich"' in text
        assert '"Consolidate everything in Zurich" overdone: Zurich alone loses the German market' in text
        assert "(Reading along: local presence / focus)" in text
        assert "ViewSketchPerspectiveDto(" not in text, "never a repr in the history"

    def test_the_history_record_carries_no_position_label(self):
        """Measured: with "T-:" in the record, the next reply said "the one I'd
        flag is T-" to the person (`test_view_sketch_real_llm.py`)."""
        import re
        text = history_text(exploration_view_from_sketch(ViewSketchDto(tensions=[_tension()])))
        assert not re.search(r"\b[TA][+-]?:", text), text

    def test_the_two_sides_alone_are_recorded_as_such(self):
        bare = _tension(t_plus="", t_minus="", a_plus="", a_minus="",
                        t_plus_vs_a_minus_axis="", a_plus_vs_t_minus_axis="")
        text = history_text(exploration_view_from_sketch(ViewSketchDto(tensions=[bare])))
        assert "the two sides only, not yet developed" in text
        lone = _tension(antithesis="")
        assert "its opposition not yet found" in history_text(
            exploration_view_from_sketch(ViewSketchDto(tensions=[lone]))
        )

    def test_an_empty_picture_is_recorded_as_such(self):
        assert history_text(ExplorationView()).startswith("I drew nothing")


# --- the head ---------------------------------------------------------------


@pytest.mark.llm
class TestThePictureIsATurnOnTheConsultantsOwnConversation:
    @pytest.mark.asyncio
    async def test_it_shares_the_history_and_sees_both_sides(self, monkeypatch):
        calls = _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        head = Consultant(app_preamble="You are a thinking partner.", messages=list(_HISTORY))

        # One draw here: this test is about WHOSE history the turn runs on; the
        # best-of-N selection is pinned in `tests/test_tetrad_candidates.py`.
        view = await head.exploration_view(focus="a perspective for the office question", attempts=1)

        (call,) = calls
        sketch_turn = call["facilitator"]
        assert sketch_turn is not head._conversation, "a second facilitator..."
        # ...over a COPY of the same history: the draws of a best-of-N run in
        # parallel and none may write into the record the others read; what
        # the view leaves behind is appended to the head's history once.
        assert sketch_turn._messages is not head._conversation._messages
        assert sketch_turn._messages[: len(_HISTORY) + 1] == head._conversation._messages[: len(_HISTORY) + 1]
        assert sketch_turn._format_mode == "json"
        assert call["model"] is ViewSketchDto
        assert "What to show: a perspective for the office question" in call["prompt"]
        # The WHOLE request is the turn, never split onto the system prompt:
        # for one day it was (a cache lever), and a retry card — whose history
        # already holds a drawing in prose — answered in prose too, 4.75
        # view-turn calls instead of 3 (`tests/e2e/probe_view_turn_retry_calls.py`).
        assert "Answer with ONE JSON object" in call["prompt"]
        assert ASPECT_DEFINITIONS in call["prompt"]
        assert sketch_turn._messages[0] == head._conversation._messages[0], (
            "the view turn's system prompt is the head's own, unchanged"
        )
        assert message_text(head.messages[-2]) == "Show me: a perspective for the office question"
        # Both sides were in front of the model, and its own system prompt led.
        texts = [message_text(m) for m in sketch_turn._messages]
        assert any("What would closing it cost you?" in t for t in texts), (
            "the counselor's own framing is material for the view"
        )
        assert _roles(sketch_turn._messages)[0] == "system"
        assert [p.t.text for p in view.perspectives] == ["Keep the Berlin office"]

    @pytest.mark.asyncio
    async def test_the_draws_that_lost_come_back_as_runners_up_best_first(self, monkeypatch):
        """Best-of-3: the judge's winner is the view; the other two judged draws
        are `runners_up` in the judge's order, so a host's "again"/"another"
        can show one without a new call. The history records the winner only."""
        from dialectical_framework.concerns import tetrad_candidates

        drafts = iter([
            ViewSketchDto(tensions=[_tension(thesis="Draw one")]),
            ViewSketchDto(tensions=[_tension(thesis="Draw two")]),
            ViewSketchDto(tensions=[_tension(thesis="Draw three")]),
        ])

        async def fake_submit(self, response_model, user_content, max_tool_rounds=10):
            dto = next(drafts)
            self._messages.append(llm.messages.user(user_content))
            self._messages.append(llm.messages.assistant(str(dto), model_id=None, provider_id=None))
            return dto

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)

        async def fake_select(candidates, context=""):
            verdicts = [
                tetrad_candidates.SketchVerdict(0.5, 0.6),  # draw one: weakest
                tetrad_candidates.SketchVerdict(0.9, 0.8),  # draw two: the winner
                tetrad_candidates.SketchVerdict(0.7, 0.9),  # draw three: second
            ]
            return tetrad_candidates.ranking(verdicts)[0], verdicts

        monkeypatch.setattr(tetrad_candidates, "select_sketch", fake_select)
        head = Consultant(app_preamble="x", messages=list(_HISTORY))

        view = await head.exploration_view(focus="a perspective", attempts=3)

        assert [p.t.text for p in view.perspectives] == ["Draw two"]
        assert [p.t.text for p in view.runners_up] == ["Draw three", "Draw one"]
        assert all(p.complete for p in view.runners_up)
        assert "Draw two" in message_text(head.messages[-1])
        assert "Draw three" not in message_text(head.messages[-1]), "the record is what was shown"
        assert view.without_terminology().runners_up[0].t.text == "Draw three"

    @pytest.mark.asyncio
    async def test_one_draw_has_no_runners_up(self, monkeypatch):
        _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        view = await head.exploration_view(attempts=1)
        assert view.runners_up == []

    @pytest.mark.asyncio
    async def test_what_it_drew_stays_in_the_history_as_words(self, monkeypatch):
        _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        before = len(head.messages)

        await head.exploration_view()

        assert len(head.messages) == before + 2, "the ask and the record: one turn"
        assert _roles(head.messages)[-2:] == ["user", "assistant"]
        ask = message_text(head.messages[-2])
        assert ask == "Show me the structure of what we've worked out so far."
        assert "Aspect Definitions" not in ask, (
            "the long request is not kept: as a Q→A exemplar it taught the next "
            "view turn to answer in prose"
        )
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


class TestAFailedDrawIsOnRecord:
    """Best-of-N: a draw that raises used to vanish — dropped by the gather,
    unlogged, uncounted (8 of 240 draws on Opus 5.5, no cause on record). Now
    it is logged by type and carried on the view as `failed_draws`."""

    def _submits(self, monkeypatch, outcomes):
        from dialectical_framework.concerns import tetrad_candidates

        queue = iter(outcomes)

        async def fake_submit(self, response_model, user_content, max_tool_rounds=10):
            outcome = next(queue)
            if isinstance(outcome, BaseException):
                raise outcome
            self._messages.append(llm.messages.user(user_content))
            self._messages.append(llm.messages.assistant(str(outcome), model_id=None, provider_id=None))
            return outcome

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)

        async def fake_select(candidates, context=""):
            verdicts = [tetrad_candidates.SketchVerdict(0.9, 0.9) for _ in candidates]
            return 0, verdicts

        monkeypatch.setattr(tetrad_candidates, "select_sketch", fake_select)

    @pytest.mark.asyncio
    async def test_a_refusal_is_recorded_with_its_category_and_logged(self, monkeypatch, caplog):
        import logging

        from dialectical_framework.exceptions.provider_errors import ModelRefusal

        self._submits(monkeypatch, [
            ViewSketchDto(tensions=[_tension(thesis="Draw one")]),
            ModelRefusal("opus", category="general_harms", explanation="declined"),
            ViewSketchDto(tensions=[_tension(thesis="Draw three")]),
        ])
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        with caplog.at_level(logging.WARNING, logger="dialectical_framework.agents.consultant.consultant"):
            view = await head.exploration_view(focus="a perspective", attempts=3)

        assert len(view.perspectives) == 1 and len(view.runners_up) == 1
        assert [(f.kind, f.category) for f in view.failed_draws] == [("ModelRefusal", "general_harms")]
        assert "declined" in view.failed_draws[0].message
        assert any("ModelRefusal (general_harms)" in r.getMessage() for r in caplog.records)
        # The record is JSON-ready and the screen projection drops the text.
        assert view.to_dict()["failed_draws"][0]["kind"] == "ModelRefusal"
        scrubbed = view.without_terminology().failed_draws[0]
        assert scrubbed.message is None and scrubbed.kind == "ModelRefusal"

    @pytest.mark.asyncio
    async def test_two_failures_leave_one_draw_and_no_comparison(self, monkeypatch):
        """The shape the host saw once: a single survivor is served as drawn,
        with no judge call, and the view says why there was no choice."""
        from mirascope.llm.exceptions import ParseError

        self._submits(monkeypatch, [
            ParseError("Failed to parse response: trailing comma", original_exception=ValueError("x")),
            ViewSketchDto(tensions=[_tension(thesis="The survivor")]),
            RuntimeError("provider went away"),
        ])
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        view = await head.exploration_view(focus="a perspective", attempts=3)
        assert [p.t.text for p in view.perspectives] == ["The survivor"]
        assert view.runners_up == []
        assert sorted(f.kind for f in view.failed_draws) == ["ParseError", "RuntimeError"]
        assert all(f.category is None for f in view.failed_draws)

    @pytest.mark.asyncio
    async def test_a_stalled_draw_is_named_by_the_provider_error(self, monkeypatch):
        """The read timeout's whole purpose on this surface: a hung draw raises
        after its one re-ask instead of holding the two that finished, and the
        host counts it as `APITimeoutError` — the SDK's class, not Mirascope's
        `TimeoutError` wrapper (the builtin's name, which says nothing)."""
        from anthropic import APITimeoutError
        from mirascope.llm.exceptions import TimeoutError as MirascopeTimeoutError

        sdk = APITimeoutError(request=httpx.Request("POST", "https://x"))
        stalled = MirascopeTimeoutError("Request timed out.", "bedrock", original_exception=sdk)
        self._submits(monkeypatch, [
            ViewSketchDto(tensions=[_tension(thesis="Draw one")]),
            stalled,
            ViewSketchDto(tensions=[_tension(thesis="Draw three")]),
        ])
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        view = await head.exploration_view(focus="a perspective", attempts=3)
        assert len(view.perspectives) == 1 and len(view.runners_up) == 1
        assert [f.kind for f in view.failed_draws] == ["APITimeoutError"]
        assert view.failed_draws[0].category is None

    @pytest.mark.asyncio
    async def test_every_draw_failing_still_raises_the_first(self, monkeypatch):
        self._submits(monkeypatch, [RuntimeError("one"), RuntimeError("two"), RuntimeError("three")])
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        with pytest.raises(RuntimeError, match="one"):
            await head.exploration_view(focus="a perspective", attempts=3)

    @pytest.mark.asyncio
    async def test_a_clean_card_has_no_failed_draws(self, monkeypatch):
        _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        view = await head.exploration_view(attempts=1)
        assert view.failed_draws == []
        assert "failed_draws" in view.to_dict()
