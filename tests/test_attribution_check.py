"""The attribution check: a holder the words do not bear is dropped in code
(`concerns/attribution_check.py`, 2026-10-27)."""

from __future__ import annotations

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import attribution_check as ac
from dialectical_framework.concerns.view_sketch import ViewSketchPerspectiveDto


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _tension(**overrides: str) -> ViewSketchPerspectiveDto:
    fields = dict(
        thesis="Rein in the courts; Parliament sets the rules",
        thesis_held_by="Ben Goldsborough",
        antithesis="Courts must protect rights even for the dangerous",
        antithesis_held_by="Anna Turley",
        t_plus_vs_a_minus_axis="authority",
        t_plus="Parliament answerable for the rules it sets",
        a_minus="Courts ruling by their own lights",
        a_plus_vs_t_minus_axis="protection",
        a_plus="Rights that bind the state when it is hardest",
        t_minus="Rules that bend to the mood of the day",
    )
    fields.update(overrides)
    return ViewSketchPerspectiveDto(**fields)


def _verdicts(monkeypatch, by_holder: dict[str, str], seen: list | None = None):
    async def fake(self, *, position, held_by, text):
        if seen is not None:
            seen.append(dict(position=position, held_by=held_by, text=text))
        return ac.AttributionDto(verdict=by_holder[held_by], reasoning="")

    monkeypatch.setattr(ac.AttributionCheck, "score_texts", fake)


class TestTheVerdict:
    def test_the_safe_value_is_first_so_the_mocked_suite_keeps_holders(self):
        from typing import get_args

        first = get_args(ac.AttributionDto.model_fields["verdict"].annotation)[0]
        assert first == "attributed"

    @pytest.mark.asyncio
    async def test_the_prompt_names_the_party_and_carries_the_words(self, monkeypatch):
        seen = {}

        async def fake_submit(self, *, response_model, user_content):
            seen["prompt"] = user_content
            seen["model"] = response_model
            return ac.AttributionDto(verdict="attributed", reasoning="r")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        await ac.AttributionCheck().score_texts(
            position="Courts must protect rights", held_by=" Anna Turley ", text="the window"
        )
        assert seen["model"] is ac.AttributionDto
        assert "<text>\nthe window\n</text>" in seen["prompt"]
        assert "attribute the following position to Anna Turley" in seen["prompt"]
        assert '"Courts must protect rights"' in seen["prompt"]


class TestDroppingUnborneHolders:
    @pytest.mark.asyncio
    async def test_an_unborne_holder_is_blanked_and_a_borne_one_kept(self, monkeypatch):
        _verdicts(monkeypatch, {"Ben Goldsborough": "attributed", "Anna Turley": "not_attributed"})
        tension = _tension()
        dropped = await ac.drop_unborne_holders([tension], "the window")
        assert tension.thesis_held_by == "Ben Goldsborough"
        assert tension.antithesis_held_by == ""
        assert dropped == ["antithesis held_by 'Anna Turley': the words do not bear it"]

    @pytest.mark.asyncio
    async def test_no_holder_named_means_no_call(self, monkeypatch):
        seen: list = []
        _verdicts(monkeypatch, {}, seen)
        tension = _tension(thesis_held_by="", antithesis_held_by="  ")
        assert await ac.drop_unborne_holders([tension], "their own words") == []
        assert seen == []

    @pytest.mark.asyncio
    async def test_no_words_means_no_call_and_nothing_dropped(self, monkeypatch):
        seen: list = []
        _verdicts(monkeypatch, {}, seen)
        tension = _tension()
        assert await ac.drop_unborne_holders([tension], "   ") == []
        assert seen == [] and tension.antithesis_held_by == "Anna Turley"

    @pytest.mark.asyncio
    async def test_every_tension_given_is_checked(self, monkeypatch):
        """The spares too: a host serving a runner-up must not get the
        misquotation back."""
        seen: list = []
        _verdicts(monkeypatch, {"Ben Goldsborough": "attributed", "Anna Turley": "not_attributed", "X": "not_attributed"}, seen)
        first, spare = _tension(), _tension(thesis_held_by="X", antithesis_held_by="")
        dropped = await ac.drop_unborne_holders([first, spare], "the window")
        assert len(seen) == 3 and all(s["text"] == "the window" for s in seen)
        assert spare.thesis_held_by == "" and first.antithesis_held_by == ""
        assert len(dropped) == 2

    @pytest.mark.asyncio
    async def test_a_failed_judging_keeps_the_holder(self, monkeypatch):
        """Dropping on error would turn "the Minister's position" into "your
        position" on a provider hiccup — the 2026-10-26 defect back."""
        async def boom(self, *, position, held_by, text):
            raise RuntimeError("provider")

        monkeypatch.setattr(ac.AttributionCheck, "score_texts", boom)
        tension = _tension()
        assert await ac.drop_unborne_holders([tension], "the window") == []
        assert tension.antithesis_held_by == "Anna Turley"

    @pytest.mark.asyncio
    async def test_a_wrong_shaped_answer_keeps_the_holder(self, monkeypatch):
        async def odd(self, *, position, held_by, text):
            return object()

        monkeypatch.setattr(ac.AttributionCheck, "score_texts", odd)
        tension = _tension()
        await ac.drop_unborne_holders([tension], "the window")
        assert tension.antithesis_held_by == "Anna Turley"


class TestTheViewTurnRunsIt:
    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_a_drawn_holder_the_words_do_not_bear_reaches_no_view(self, monkeypatch):
        from test_view_sketch import _fake_submit

        from dialectical_framework.agents.consultant.consultant import Consultant
        from dialectical_framework.concerns.view_sketch import ViewSketchDto

        _fake_submit(monkeypatch, ViewSketchDto(tensions=[_tension()]))
        checked: list = []
        _verdicts(monkeypatch, {"Ben Goldsborough": "attributed", "Anna Turley": "not_attributed"}, checked)
        head = Consultant(
            app_preamble="You are a thinking partner.",
            messages=[{"role": "user", "content": "Ben Goldsborough: rein in the courts. Anna Turley: my hon. Friend is right."}],
        )
        view = await head.exploration_view(attempts=1)
        first = view.perspectives[0]
        assert first.t.held_by == "Ben Goldsborough"
        assert first.a.held_by is None
        # Checked against the PERSON's words, the judges' own context.
        assert checked and all("Ben Goldsborough: rein in the courts" in c["text"] for c in checked)

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_persons_own_words_cost_no_check(self, monkeypatch):
        from test_view_sketch import _fake_submit, _tension as own_tension

        from dialectical_framework.agents.consultant.consultant import Consultant
        from dialectical_framework.concerns.view_sketch import ViewSketchDto

        _fake_submit(monkeypatch, ViewSketchDto(tensions=[own_tension()]))
        checked: list = []
        _verdicts(monkeypatch, {}, checked)
        head = Consultant(app_preamble="You are a thinking partner.", messages=[{"role": "user", "content": "I should keep the Berlin office."}])
        await head.exploration_view(attempts=1)
        assert checked == []

    def test_the_check_runs_before_selection_and_on_every_draw(self):
        import inspect

        from dialectical_framework.agents.consultant.consultant import Consultant

        source = inspect.getsource(Consultant.exploration_view)
        assert source.index("drop_unborne_holders(") < source.index("select_sketch(")
        assert "for s in sketches if s.tensions" in source
