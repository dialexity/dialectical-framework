"""Best-of-N sketch selection (`concerns/tetrad_candidates.py`) and its two
callers: `TetradSketch.resolve(attempts=)` and
`Consultant.exploration_view(attempts=)`.

What is pinned: the ranking (weaker control statement, then mean, then the
earlier draw), fail-soft judging, that ONE candidate is never judged (so
`attempts=1` costs no extra call), that N draws run on fresh facilitators and
the view turn's draws on COPIES of the history with the record appended once,
and the cap. DB-free.
"""

from __future__ import annotations

import pytest
from mirascope import llm

from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import tetrad_candidates as candidates
from dialectical_framework.concerns.tetrad_candidates import (
    MAX_SKETCH_ATTEMPTS, SketchVerdict, clamp_attempts, select_sketch)
from dialectical_framework.concerns.tetrad_sketch import (TetradSketch,
                                                          TetradSketchDto)
from dialectical_framework.concerns.view_sketch import (
    ViewSketchDto, ViewSketchPerspectiveDto)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _tension(**overrides) -> ViewSketchPerspectiveDto:
    base = dict(
        thesis="Keep the Berlin office",
        antithesis="Go fully remote",
        t_plus_vs_a_minus_axis="presence",
        t_plus="A place people choose to meet",
        a_minus="Everyone alone behind a screen",
        a_plus_vs_t_minus_axis="reach",
        a_plus="Hire wherever the talent is",
        t_minus="Only who can commute counts",
    )
    base.update(overrides)
    return ViewSketchPerspectiveDto(**base)


def _verdicts_by_thesis(table: dict[str, tuple[float, float] | Exception]):
    """Monkeypatch-able judge keyed on the sketch's thesis text."""

    async def fake(tension, context=""):
        value = table[tension.thesis]
        if isinstance(value, Exception):
            raise value
        return SketchVerdict(*value)

    return fake


class TestTheKnob:
    def test_none_is_the_default_and_the_cap_holds(self, monkeypatch):
        monkeypatch.setattr(candidates, "DEFAULT_SKETCH_ATTEMPTS", 2)
        assert clamp_attempts(None) == 2
        assert clamp_attempts(None, default=1) == 1, "the staged writer's own default"
        assert clamp_attempts(0) == 1
        assert clamp_attempts(-4) == 1
        assert clamp_attempts(MAX_SKETCH_ATTEMPTS + 5) == MAX_SKETCH_ATTEMPTS

    def test_the_verdict_reads_the_weaker_statement(self):
        assert SketchVerdict(0.9, 0.6).floor == 0.6
        assert not SketchVerdict(0.9, 0.6).passes
        assert SketchVerdict(0.7, 0.8).passes


class TestTheSelection:
    @pytest.mark.asyncio
    async def test_the_weaker_statement_ranks_first_then_the_mean(self, monkeypatch):
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({
            "a": (0.95, 0.60),   # floor 0.60 — the best mean, but it fails
            "b": (0.75, 0.75),   # floor 0.75
            "c": (0.90, 0.75),   # floor 0.75, higher mean → wins
        }))
        best, verdicts = await select_sketch(
            [_tension(thesis="a"), _tension(thesis="b"), _tension(thesis="c")]
        )
        assert best == 2
        assert [v.floor for v in verdicts] == [0.60, 0.75, 0.75]

    @pytest.mark.asyncio
    async def test_a_tie_keeps_the_earlier_draw(self, monkeypatch):
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({
            "a": (0.8, 0.8), "b": (0.8, 0.8)
        }))
        best, _ = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 0

    @pytest.mark.asyncio
    async def test_a_failed_judging_sorts_last_and_is_none(self, monkeypatch):
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({
            "a": RuntimeError("provider down"), "b": (0.5, 0.5)
        }))
        best, verdicts = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 1
        assert verdicts[0] is None and verdicts[1].floor == 0.5

    @pytest.mark.asyncio
    async def test_when_every_judging_fails_the_first_draw_is_kept(self, monkeypatch):
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({
            "a": RuntimeError("x"), "b": RuntimeError("y")
        }))
        best, verdicts = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 0 and verdicts == [None, None]

    @pytest.mark.asyncio
    async def test_one_candidate_is_never_judged(self, monkeypatch):
        async def boom(tension, context=""):
            raise AssertionError("judged a lone candidate")

        monkeypatch.setattr(candidates, "judge_sketch", boom)
        assert await select_sketch([_tension()]) == (0, [None])


@pytest.mark.llm
class TestTheBuildDrawsNAndKeepsTheBest:
    @pytest.mark.asyncio
    async def test_three_draws_three_facilitators_one_winner(self, monkeypatch):
        drawn: list[ConversationFacilitator] = []
        names = iter(["a", "b", "c"])

        async def fake_submit(self, model, content):
            drawn.append(self)
            return TetradSketchDto(tension=_tension(thesis=next(names)))

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({
            "a": (0.6, 0.9), "b": (0.8, 0.85), "c": (0.75, 0.75)
        }))
        sketch = TetradSketch()
        tension = await sketch.resolve("I should keep the office.", attempts=3)

        assert tension.thesis == "b"
        assert len(drawn) == 3 and len({id(f) for f in drawn}) == 3, "fresh facilitator per draw"
        assert sketch.verdict.floor == 0.8
        assert [t.thesis for t, _v in sketch.alternatives] == ["a", "c"]
        assert sketch.report.artifacts["attempts"]["selected"] == 1
        assert sketch.report.artifacts["attempts"]["floors"] == [0.6, 0.8, 0.75]
        assert [alt["thesis"] for alt in sketch.report.artifacts["attempts"]["alternatives"]] == ["a", "c"]

    @pytest.mark.asyncio
    async def test_one_attempt_makes_no_judge_call_and_no_alternatives(self, monkeypatch):
        async def fake_submit(self, model, content):
            return TetradSketchDto(tension=_tension())

        async def boom(tension, context=""):
            raise AssertionError("attempts=1 must not judge")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", boom)
        sketch = TetradSketch()
        await sketch.resolve("I should keep the office.", attempts=1)
        assert sketch.verdict is None and sketch.alternatives == []
        assert "attempts" not in sketch.report.artifacts

    @pytest.mark.asyncio
    async def test_a_draw_with_an_empty_corner_is_dropped_not_fatal(self, monkeypatch):
        names = iter(["a", "b"])

        async def fake_submit(self, model, content):
            name = next(names)
            return TetradSketchDto(tension=_tension(thesis=name, a_plus="" if name == "a" else "x"))

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({"b": (0.9, 0.9)}))
        sketch = TetradSketch()
        tension = await sketch.resolve("material", attempts=2)
        assert tension.thesis == "b"
        assert sketch.verdict is None, "a lone survivor is not judged"

    @pytest.mark.asyncio
    async def test_when_every_draw_fails_the_first_error_is_raised(self, monkeypatch):
        async def fake_submit(self, model, content):
            return TetradSketchDto(tension=_tension(a_plus=""))

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        with pytest.raises(ValueError, match="a_plus"):
            await TetradSketch().resolve("material", attempts=2)


_HISTORY = [
    llm.messages.user("Should we close the Berlin office?"),
    llm.messages.assistant("What would closing it cost you?", model_id=None, provider_id=None),
]


@pytest.mark.llm
class TestTheViewTurnDrawsOnCopies:
    @pytest.mark.asyncio
    async def test_each_draw_has_its_own_history_and_the_record_lands_once(self, monkeypatch):
        seen: list[list] = []
        names = iter(["a", "b", "c"])

        async def fake_submit(self, model, content):
            seen.append(self._messages)
            self._messages.append(llm.messages.user(content))
            dto = ViewSketchDto(tensions=[_tension(thesis=next(names))])
            self._messages.append(llm.messages.assistant(str(dto), model_id=None, provider_id=None))
            return dto

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", _verdicts_by_thesis({
            "a": (0.5, 0.9), "b": (0.7, 0.7), "c": (0.9, 0.9)
        }))
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        before = len(head.messages)

        view = await head.exploration_view(focus="the office", attempts=3)

        assert [p.t.text for p in view.perspectives] == ["c"]
        assert len(seen) == 3 and len({id(m) for m in seen}) == 3
        assert all(m is not head._conversation._messages for m in seen)
        assert len(head.messages) == before + 2, "the ask and the record, once"
        last = head.messages[-1]
        text = last.content if isinstance(last.content, str) else "".join(
            getattr(p, "text", "") for p in last.content)
        assert "c" in text and "ViewSketchPerspectiveDto(" not in text

    @pytest.mark.asyncio
    async def test_a_draw_with_no_complete_first_tension_is_not_chosen(self, monkeypatch):
        names = iter(["a", "b"])

        async def fake_submit(self, model, content):
            name = next(names)
            tensions = [] if name == "a" else [_tension(thesis=name)]
            return ViewSketchDto(tensions=tensions)

        async def boom(tension, context=""):
            raise AssertionError("one judgeable draw needs no judging")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", boom)
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        view = await head.exploration_view(focus="the office", attempts=2)
        assert [p.t.text for p in view.perspectives] == ["b"]


@pytest.mark.llm
class TestTheStagedWriterSelectsToo:
    """`AspectGeneration._generate_tetrad` — documents, the pipeline, the
    two-pole anchor — runs the same selection; `_create_aspect_result` is
    stubbed so no Statement is committed here."""

    def _generator(self, monkeypatch):
        from dialectical_framework.concerns.aspect_generation import AspectGeneration

        gen = AspectGeneration()
        monkeypatch.setattr(gen, "_build_existing_aspects_context", lambda positions: "")
        monkeypatch.setattr(gen, "_tetrad_prompt", lambda existing: "the request")
        monkeypatch.setattr(
            gen, "_create_aspect_result",
            lambda position, statement, dto: (position, statement),
        )
        gen._text = ""
        return gen

    @staticmethod
    def _dto(tag: str):
        from dialectical_framework.concerns.aspect_generation import AspectDto, TetradDto

        def aspect(text):
            return AspectDto(statement=text, explanation="why", heuristic_similarity=0.5,
                             complementarity_t=0.5, complementarity_a=0.5)

        return TetradDto(
            t_plus_vs_a_minus_axis="x", a_plus_vs_t_minus_axis="y",
            t_plus=aspect(f"{tag}-t_plus"), a_minus=aspect(f"{tag}-a_minus"),
            a_plus=aspect(f"{tag}-a_plus"), t_minus=aspect(f"{tag}-t_minus"),
        )

    @pytest.mark.asyncio
    async def test_three_draws_fresh_facilitators_best_kept(self, monkeypatch):
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS, POSITION_T_PLUS)

        gen = self._generator(monkeypatch)
        gen._attempts = 3
        seen: list = []
        names = iter(["a", "b", "c"])

        async def fake_submit(self, response_model, user_content):
            seen.append(self)
            return TestTheStagedWriterSelectsToo._dto(next(names))

        async def judge(tension, context=""):
            return SketchVerdict(*{"a": (0.9, 0.5), "b": (0.8, 0.8), "c": (0.7, 0.7)}[
                tension.t_plus.statement.split("-")[0]])

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", judge)
        results = await gen._generate_tetrad(
            [POSITION_T_PLUS, POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS]
        )
        assert [r[1] for r in results] == ["b-t_plus", "b-a_minus", "b-a_plus", "b-t_minus"]
        assert len(seen) == 3 and gen._conversation not in seen, "fresh facilitators, not the shared one"
        assert gen.verdict.floor == 0.8
        assert gen.report.artifacts["attempts"] == {"drawn": 3, "selected": 1, "floors": [0.5, 0.8, 0.7]}

    @pytest.mark.asyncio
    async def test_one_attempt_is_the_shared_conversation_and_no_judge(self, monkeypatch):
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS, POSITION_T_PLUS)

        gen = self._generator(monkeypatch)
        gen._attempts = 1  # one draw asked for: the call as it always was
        seen: list = []

        async def fake_submit(self, response_model, user_content):
            seen.append(self)
            return TestTheStagedWriterSelectsToo._dto("a")

        async def boom(tension, context=""):
            raise AssertionError("one draw is never judged")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketch", boom)
        await gen._generate_tetrad([POSITION_T_PLUS, POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS])
        assert seen == [gen._conversation]
        assert gen.verdict is None and "attempts" not in gen.report.artifacts


def test_ranking_orders_by_the_floor_then_the_mean_with_unjudged_last():
    from dialectical_framework.concerns.tetrad_candidates import SketchVerdict, ranking

    verdicts = [
        SketchVerdict(0.5, 0.9),  # floor .5
        None,  # unjudged: last
        SketchVerdict(0.8, 0.8),  # floor .8, mean .8
        SketchVerdict(0.8, 0.9),  # floor .8, mean .85: wins
    ]
    assert ranking(verdicts) == [3, 2, 0, 1]
