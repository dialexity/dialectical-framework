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


def _verdicts_by_thesis(table: dict[str, tuple[float, float] | None]):
    """Monkeypatch-able judge keyed on the sketch's thesis text.

    Stands in for `judge_sketches`: a thesis the table maps to `None`, or
    omits, is a candidate whose judging failed.
    """

    async def fake(candidates, context=""):
        return [
            None if table.get(c.thesis) is None else SketchVerdict(*table[c.thesis])
            for c in candidates
        ]

    return fake


def _judging_fails():
    """Every candidate's judging failing: all come back unjudged."""

    async def fake(candidates, context=""):
        return [None] * len(candidates)

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
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({
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
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({
            "a": (0.8, 0.8), "b": (0.8, 0.8)
        }))
        best, _ = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 0

    @pytest.mark.asyncio
    async def test_a_failed_judging_sorts_last_and_is_none(self, monkeypatch):
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({
            "a": None, "b": (0.5, 0.5)
        }))
        best, verdicts = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 1
        assert verdicts[0] is None and verdicts[1].floor == 0.5

    @pytest.mark.asyncio
    async def test_when_every_judging_fails_the_first_draw_is_kept(self, monkeypatch):
        monkeypatch.setattr(candidates, "judge_sketches", _judging_fails())
        best, verdicts = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 0 and verdicts == [None, None]

    @pytest.mark.asyncio
    async def test_each_draft_is_judged_by_the_per_statement_judge(self, monkeypatch):
        """The validated judge, one draft at a time: the same question
        `ControlStatementsCheck.resolve` asks after persistence. Two cheaper
        shapes (the whole field in one call; one call per draft) were measured
        against it and rejected (`tests/e2e/probe_joint_judge_stability.py`)."""
        from dialectical_framework.concerns import control_statements_check as csc

        calls: list[dict] = []

        async def fake_score_texts(self, *, t_plus, t_minus, a_plus, a_minus, text=""):
            calls.append({"t_plus": t_plus, "text": text})
            score = {"a": 0.6, "b": 0.7, "c": 0.8}[t_plus]
            dto = csc.CoherenceEvaluationDto(
                coherence_score=score, reasoning="why",
                dialectical_validity=0.5, dv_reasoning="why",
            )
            return dto, csc.CoherenceEvaluationDto(
                coherence_score=0.9, reasoning="why",
                dialectical_validity=0.5, dv_reasoning="why",
            )

        monkeypatch.setattr(csc.ControlStatementsCheck, "score_texts", fake_score_texts)
        best, verdicts = await select_sketch(
            [_tension(t_plus="a"), _tension(t_plus="b"), _tension(t_plus="c")],
            context="the situation",
        )
        assert len(calls) == 3, "one judging per draft, each on its own"
        assert all(c["text"] == "the situation" for c in calls)
        assert best == 2 and [v.floor for v in verdicts] == [0.6, 0.7, 0.8]

    @pytest.mark.asyncio
    async def test_one_draft_failing_to_judge_leaves_the_others_judged(self, monkeypatch):
        from dialectical_framework.concerns import control_statements_check as csc

        async def flaky(self, *, t_plus, t_minus, a_plus, a_minus, text=""):
            if t_plus == "a":
                raise RuntimeError("provider down")
            dto = csc.CoherenceEvaluationDto(
                coherence_score=0.8, reasoning="", dialectical_validity=0.5, dv_reasoning="",
            )
            return dto, dto

        monkeypatch.setattr(csc.ControlStatementsCheck, "score_texts", flaky)
        best, verdicts = await select_sketch([_tension(t_plus="a"), _tension(t_plus="b")])
        assert verdicts[0] is None and verdicts[1].floor == 0.8 and best == 1

    @pytest.mark.asyncio
    async def test_a_malformed_verdict_is_a_failed_judging_not_a_crash(self, monkeypatch):
        """Reading the scores off the response is inside the fail-soft too."""
        from dialectical_framework.concerns import control_statements_check as csc

        async def wrong_shape(self, **kwargs):
            return object(), object()

        monkeypatch.setattr(csc.ControlStatementsCheck, "score_texts", wrong_shape)
        best, verdicts = await select_sketch([_tension(thesis="a"), _tension(thesis="b")])
        assert best == 0 and verdicts == [None, None]

    @pytest.mark.asyncio
    async def test_the_judge_never_sees_the_thesis_or_the_antithesis(self, monkeypatch):
        """The module's standing rule: the judge scores the four aspects, and a
        verdict steered by the poles passes mirrors more readily than positions."""
        from dialectical_framework.concerns import control_statements_check as csc

        seen: list[str] = []

        async def fake_score_texts(self, *, t_plus, t_minus, a_plus, a_minus, text=""):
            seen.extend([t_plus, t_minus, a_plus, a_minus])
            raise RuntimeError("only recording what was sent")

        monkeypatch.setattr(csc.ControlStatementsCheck, "score_texts", fake_score_texts)
        await select_sketch([_tension(), _tension(thesis="other")])
        sent = " ".join(seen)
        assert seen, "the judge was asked"
        assert "Keep the Berlin office" not in sent and "Go fully remote" not in sent

    @pytest.mark.asyncio
    async def test_one_candidate_is_never_judged(self, monkeypatch):
        async def boom(candidates, context=""):
            raise AssertionError("judged a lone candidate")

        monkeypatch.setattr(candidates, "judge_sketches", boom)
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
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({
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

        async def boom(candidates, context=""):
            raise AssertionError("attempts=1 must not judge")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", boom)
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
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({"b": (0.9, 0.9)}))
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
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({
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

        async def boom(candidates, context=""):
            raise AssertionError("one judgeable draw needs no judging")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", boom)
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

        async def judge(candidates, context=""):
            table = {"a": (0.9, 0.5), "b": (0.8, 0.8), "c": (0.7, 0.7)}
            return [
                SketchVerdict(*table[c.t_plus.statement.split("-")[0]])
                for c in candidates
            ]

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", judge)
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

        async def boom(candidates, context=""):
            raise AssertionError("one draw is never judged")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", boom)
        await gen._generate_tetrad([POSITION_T_PLUS, POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS])
        assert seen == [gen._conversation]
        assert gen.verdict is None and "attempts" not in gen.report.artifacts


class TestTheRejectedJudgesStayOutOfTheLibrary:
    """Two cheaper judges were measured against the per-statement one and
    rejected (2026-10-06, `tests/e2e/probe_joint_judge_stability.py`): the whole
    field in one call picked by position and ties, one call per draft measured
    something else. They live in that probe, not in `src/`, so nobody wires a
    measured-bad judge back in by finding it there."""

    def test_no_joint_judge_in_the_concern(self):
        from dialectical_framework.concerns import control_statements_check as csc

        assert not hasattr(csc.ControlStatementsCheck, "score_texts_many")
        assert not hasattr(csc, "JointCoherenceEvaluationDto")


def test_ranking_orders_by_the_floor_then_the_mean_with_unjudged_last():
    from dialectical_framework.concerns.tetrad_candidates import SketchVerdict, ranking

    verdicts = [
        SketchVerdict(0.5, 0.9),  # floor .5
        None,  # unjudged: last
        SketchVerdict(0.8, 0.8),  # floor .8, mean .8
        SketchVerdict(0.8, 0.9),  # floor .8, mean .85: wins
    ]
    assert ranking(verdicts) == [3, 2, 0, 1]


class TestDialecticalValidityRanksAfterTheFloor:
    """The handoff of 2026-10-13, §2: DV was scored on every draft in the same
    call as CC and dropped at the moment of choosing. It now ranks AFTER the
    pass floor and BEFORE the mean — the floor keeps every keep-any-passing
    figure on record, DV is the paper's acceptance term and the one that tells
    two holding draws apart, the mean is the other statement's score."""

    def test_the_floor_still_decides_first(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.6, 0.9, "", 1.0, 1.0),  # fails the rule, perfect DV
            SketchVerdict(0.8, 0.8, "", 0.3, 0.3),  # holds, poor DV: still wins
        ]
        assert ranking(verdicts) == [1, 0]

    def test_among_draws_that_hold_equally_the_live_one_wins_over_the_mean(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.8, 0.95, "", 0.5, 0.5),  # floor .8, mean .875, DV .5
            SketchVerdict(0.8, 0.80, "", 0.9, 0.9),  # floor .8, mean .80, DV .9: wins
        ]
        assert ranking(verdicts) == [1, 0]
        assert verdicts[1].dialectical_validity == 0.9

    def test_the_mean_then_the_earlier_draw_break_a_dv_tie(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.8, 0.8, "", 0.7, 0.7),
            SketchVerdict(0.8, 0.9, "", 0.7, 0.7),  # same DV, higher mean: wins
            SketchVerdict(0.8, 0.9, "", 0.7, 0.7),  # the same again: the earlier draw
        ]
        assert ranking(verdicts) == [1, 2, 0]

    def test_a_verdict_without_dv_ranks_below_one_with_it_never_as_a_zero(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        assert SketchVerdict(0.8, 0.8).dialectical_validity is None
        assert SketchVerdict(0.8, 0.8, "", 0.1, None).dialectical_validity is None
        verdicts = [
            SketchVerdict(0.8, 0.9),              # no DV: below any judged DV...
            SketchVerdict(0.8, 0.8, "", 0.0, 0.0),  # ...even a DV of zero
        ]
        assert ranking(verdicts) == [1, 0]
        # The old pins still hold where no DV is on the verdicts at all.
        assert ranking([SketchVerdict(0.8, 0.8), SketchVerdict(0.8, 0.9)]) == [1, 0]

    @pytest.mark.asyncio
    async def test_the_judge_fills_dv_from_the_same_call_as_cc(self, monkeypatch):
        """No extra call: `CoherenceEvaluationDto` carries both scores."""
        from dialectical_framework.concerns import control_statements_check as csc
        from dialectical_framework.concerns.tetrad_candidates import judge_sketches

        async def fake_score_texts(self, *, t_plus, t_minus, a_plus, a_minus, text=""):
            dv = {"a": 0.2, "b": 0.9}[t_plus]
            first = csc.CoherenceEvaluationDto(
                coherence_score=0.8, reasoning="", dialectical_validity=dv, dv_reasoning="",
            )
            second = csc.CoherenceEvaluationDto(
                coherence_score=0.8, reasoning="", dialectical_validity=dv + 0.05, dv_reasoning="",
            )
            return first, second

        monkeypatch.setattr(csc.ControlStatementsCheck, "score_texts", fake_score_texts)
        verdicts = await judge_sketches([_tension(t_plus="a"), _tension(t_plus="b")])
        assert [round(v.dialectical_validity, 3) for v in verdicts] == [0.225, 0.925]
        best, _ = await select_sketch([_tension(t_plus="a"), _tension(t_plus="b")])
        assert best == 1, "equal coherence: the live tension wins"


class TestEveryDrawIsTheSameRequest:
    """The handoff of 2026-10-13, §1, measured and REJECTED the same day:
    asking draw 2..N for a different opposition made the spares differ (75/80
    positions) and the winner worse (CC 19/40 against 27/40 with identical
    draws, positions 34 against 37, 1.26x the seconds;
    `tests/e2e/probe_view_turn_ask.py`, pinned, two arms). So best-of-N is a
    coherence re-roll of ONE request on both one-shot writers, and the
    builders take no per-draw argument."""

    def test_the_builders_take_no_per_draw_argument(self):
        import inspect

        from dialectical_framework.concerns.tetrad_sketch import tetrad_sketch_prompt
        from dialectical_framework.concerns.view_sketch import view_sketch_prompt

        for builder in (tetrad_sketch_prompt, view_sketch_prompt):
            assert not {"draw", "drawn", "variation"} & set(inspect.signature(builder).parameters)

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_build_sends_one_request_n_times_and_records_the_oppositions(self, monkeypatch):
        sent: list[str] = []
        names = iter(["a", "b", "c"])

        async def fake_submit(self, model, content):
            sent.append(content)
            return TetradSketchDto(tension=_tension(thesis=next(names), antithesis=f"against {len(sent)}"))

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({
            "a": (0.8, 0.8), "b": (0.8, 0.8), "c": (0.8, 0.8)
        }))
        sketch = TetradSketch()
        await sketch.resolve("I should keep the office.", attempts=3)

        assert len(sent) == 3 and len(set(sent)) == 1, "one request, three draws"
        # The oppositions drawn and each draw's DV are on the artifact, so a
        # host can see for itself whether its spares differ.
        assert sketch.report.artifacts["attempts"]["oppositions"] == ["against 1", "against 2", "against 3"]
        assert sketch.report.artifacts["attempts"]["validity"] == [None, None, None]

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_view_turn_sends_one_request_n_times(self, monkeypatch):
        sent: list[str] = []
        names = iter(["a", "b", "c"])

        async def fake_submit(self, model, content):
            sent.append(content)
            return ViewSketchDto(tensions=[_tension(thesis=next(names))])

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({"Keep": (0.8, 0.8)}))
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        await head.exploration_view(focus="the office", attempts=3, thesis="Keep")
        assert len(sent) == 3 and len(set(sent)) == 1


class TestTheViewTurnsJudgeReadsThePersonsWords:
    """The handoff of 2026-10-13, §3: `select_sketch` was called with no
    context on the view turn while the build, the staged writer and the
    persisted check all pass their material — the judge, which never sees T
    or A, scored the four aspects against nothing."""

    def test_judge_context_keeps_the_newest_turns_whole_within_the_budget(self):
        from dialectical_framework.concerns.view_sketch import judge_context

        assert judge_context([]) == ""
        assert judge_context(["", "  "]) == ""
        assert judge_context(["first", "second"]) == "first\n\nsecond"
        # Older turns go first; the newest is always kept, even alone and over budget.
        assert judge_context(["a" * 10, "b" * 10, "c" * 10], budget=25) == "b" * 10 + "\n\n" + "c" * 10
        assert judge_context(["a" * 10, "c" * 40], budget=25) == "c" * 40

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_judge_is_handed_the_persons_turns(self, monkeypatch):
        seen: list[str] = []
        names = iter(["a", "b"])

        async def fake_submit(self, model, content):
            return ViewSketchDto(tensions=[_tension(thesis=next(names))])

        async def fake_judge(candidates, context=""):
            seen.append(context)
            return [SketchVerdict(0.8, 0.8) for _ in candidates]

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", fake_judge)
        history = list(_HISTORY) + [llm.messages.user("Mostly the people who would not move.")]
        head = Consultant(app_preamble="x", messages=history)
        await head.exploration_view(focus="the office", attempts=2)

        assert seen == [
            "Should we close the Berlin office?\n\nMostly the people who would not move."
        ], "the person's turns, in order, and nothing of the counselor's"


class TestTheFitTermRanksInsideThePassRule:
    """The first app's handoff of 2026-10-20 (`docs/handoff-2026-10-20-thesis-choice.md`):
    on a multi-claim input the writer drew the claim the person would sign
    twice in three draws and the coherence-only ranking kept the hedge. A
    second judge (`concerns/thesis_fit_check.py`) reads T, A and A+ against
    the person's words; its yes/no ranks AFTER the pass rule and BEFORE the
    floor's value, so every keep-any-passing figure stands and a hedge no
    longer wins on coherence alone. Not judged counts as fitting."""

    def test_the_verdict_reads_the_threshold_and_treats_unjudged_as_fitting(self):
        from dialectical_framework.concerns.thesis_fit_check import THESIS_FIT_THRESHOLD

        assert SketchVerdict(0.8, 0.8).thesis_fit is None
        assert SketchVerdict(0.8, 0.8).fits, "no fit judging: ranks as before the term"
        assert SketchVerdict(0.8, 0.8, thesis_fit=THESIS_FIT_THRESHOLD).fits
        assert not SketchVerdict(0.8, 0.8, thesis_fit=THESIS_FIT_THRESHOLD - 0.01).fits

    def test_the_fit_is_the_weaker_of_the_two_reads(self):
        from dialectical_framework.concerns.thesis_fit_check import ThesisFitDto

        on_the_claim_but_granted = ThesisFitDto(
            thesis_is_the_claim=1.0, a_plus_already_granted=0.9, reasoning="")
        assert on_the_claim_but_granted.fit == pytest.approx(0.1)
        a_hedge_with_a_real_opposition = ThesisFitDto(
            thesis_is_the_claim=0.2, a_plus_already_granted=0.0, reasoning="")
        assert a_hedge_with_a_real_opposition.fit == pytest.approx(0.2)

    def test_among_passing_draws_the_one_on_the_persons_claim_beats_the_more_coherent_hedge(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.9, 0.95, "", 0.9, 0.9, thesis_fit=0.2),  # the hedge: holds best
            SketchVerdict(0.75, 0.8, "", 0.7, 0.7, thesis_fit=0.9),  # the demand: holds, fits
        ]
        assert ranking(verdicts) == [1, 0]

    def test_the_pass_rule_still_decides_first(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.6, 0.9, thesis_fit=1.0),  # fits, fails the rule
            SketchVerdict(0.8, 0.8, thesis_fit=0.1),  # does not fit, holds: still wins
        ]
        assert ranking(verdicts) == [1, 0], "a term ahead of the floor would trade every keep-any-passing figure"

    def test_among_fitting_draws_the_floor_decides_as_before(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.8, 0.8, thesis_fit=0.95),  # fits better, holds less
            SketchVerdict(0.9, 0.9, thesis_fit=0.6),   # fits, holds better: wins
        ]
        assert ranking(verdicts) == [1, 0], "a yes/no, not a score: the fit never outranks the floor's value among fitting draws"

    def test_among_failing_draws_the_fit_decides_the_same_way(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.6, 0.6, thesis_fit=0.1),
            SketchVerdict(0.5, 0.5, thesis_fit=0.9),  # no draw holds: the one on their claim
        ]
        assert ranking(verdicts) == [1, 0]

    def test_an_unjudged_fit_never_demotes_a_draw(self):
        from dialectical_framework.concerns.tetrad_candidates import ranking

        verdicts = [
            SketchVerdict(0.8, 0.8, thesis_fit=None),  # the fit call failed on this one
            SketchVerdict(0.8, 0.8, thesis_fit=0.9),
        ]
        assert ranking(verdicts) == [0, 1], "a provider error on one draw is not a verdict against it"
        # And every pin from before the term holds with no fit on any verdict.
        assert ranking([SketchVerdict(0.5, 0.9), None, SketchVerdict(0.8, 0.8), SketchVerdict(0.8, 0.9)]) == [3, 2, 0, 1]


class TestTheFitJudgeIsGatheredBesideTheControlStatements:
    @pytest.mark.asyncio
    async def test_fit_against_runs_both_judges_and_the_verdicts_carry_the_fit(self, monkeypatch):
        seen: dict = {}

        async def fake_judge(cands, context=""):
            seen["cc"] = context
            return [SketchVerdict(0.9, 0.9), SketchVerdict(0.8, 0.8)]

        async def fake_fit(cands, context):
            seen["fit"] = context
            return [0.1, 0.9]

        monkeypatch.setattr(candidates, "judge_sketches", fake_judge)
        monkeypatch.setattr(candidates, "judge_fit", fake_fit)
        best, verdicts = await select_sketch(
            [_tension(thesis="hedge"), _tension(thesis="demand")],
            context="a paraphrase", fit_against="what the person said",
        )
        assert seen == {"cc": "a paraphrase", "fit": "what the person said"}, (
            "two judges, two inputs: the control statements take the caller's context, "
            "the fit judge the person's own words"
        )
        assert best == 1
        assert [v.thesis_fit for v in verdicts] == [0.1, 0.9]

    @pytest.mark.asyncio
    async def test_without_words_to_read_against_the_fit_judge_is_not_asked(self, monkeypatch):
        async def boom(cands, context):
            raise AssertionError("asked blind")

        monkeypatch.setattr(candidates, "judge_sketches", _verdicts_by_thesis({"a": (0.8, 0.8), "b": (0.9, 0.9)}))
        monkeypatch.setattr(candidates, "judge_fit", boom)
        for words in (None, "", "   "):
            best, verdicts = await select_sketch(
                [_tension(thesis="a"), _tension(thesis="b")], fit_against=words)
            assert best == 1 and all(v.thesis_fit is None for v in verdicts)

    @pytest.mark.asyncio
    async def test_a_failed_fit_judging_is_none_for_that_draw_alone(self, monkeypatch):
        from dialectical_framework.concerns import thesis_fit_check as tfc
        from dialectical_framework.concerns.tetrad_candidates import judge_fit

        calls = iter([RuntimeError("provider"), tfc.ThesisFitDto(
            thesis_is_the_claim=0.9, a_plus_already_granted=0.1, reasoning="")])

        async def fake_score(self, *, thesis, antithesis, a_plus, text):
            outcome = next(calls)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(tfc.ThesisFitCheck, "score_texts", fake_score)
        fits = await judge_fit([_tension(thesis="a"), _tension(thesis="b")], "words")
        assert fits[0] is None and fits[1] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_the_fit_judge_reads_t_a_and_a_plus_against_the_words(self, monkeypatch):
        from dialectical_framework.concerns import thesis_fit_check as tfc
        from dialectical_framework.concerns.tetrad_candidates import judge_fit

        seen: list[dict] = []

        async def fake_score(self, *, thesis, antithesis, a_plus, text):
            seen.append(dict(thesis=thesis, antithesis=antithesis, a_plus=a_plus, text=text))
            return tfc.ThesisFitDto(thesis_is_the_claim=1.0, a_plus_already_granted=0.0, reasoning="")

        monkeypatch.setattr(tfc.ThesisFitCheck, "score_texts", fake_score)
        await judge_fit([_tension()], "Should we close it?")
        assert seen == [dict(
            thesis="Keep the Berlin office", antithesis="Go fully remote",
            a_plus="Hire wherever the talent is", text="Should we close it?",
        )]

    @pytest.mark.asyncio
    async def test_a_transition_tetrad_has_no_thesis_and_is_not_fit_judged(self, monkeypatch):
        from types import SimpleNamespace

        from dialectical_framework.concerns import thesis_fit_check as tfc
        from dialectical_framework.concerns.tetrad_candidates import judge_fit

        async def boom(self, **kwargs):
            raise AssertionError("a transition tetrad has no claim to fit")

        monkeypatch.setattr(tfc.ThesisFitCheck, "score_texts", boom)
        corners = SimpleNamespace(t_plus="a", t_minus="b", a_plus="c", a_minus="d")
        assert await judge_fit([corners, corners], "words") == [None, None]

    def test_the_prompt_asks_the_two_questions_over_the_words(self):
        from dialectical_framework.concerns.thesis_fit_check import ThesisFitDto

        fields = ThesisFitDto.model_fields
        assert list(fields) == ["thesis_is_the_claim", "a_plus_already_granted", "reasoning"], (
            "scores before the reasoning; a reasoning written first anchors the score"
        )
        assert "would SIGN" in fields["thesis_is_the_claim"].description
        assert "ALREADY name and concede" in fields["a_plus_already_granted"].description
        # The idiom reads the SAME way at the field and in the prompt: "not only
        # X but also Y" concedes X (the field said Y until 2026-10-20, and the
        # judge was handed both readings in one call).
        assert "concedes X" in fields["a_plus_already_granted"].description
        assert "concedes Y" not in fields["a_plus_already_granted"].description

    @pytest.mark.asyncio
    async def test_the_field_and_the_prompt_read_the_idiom_the_same_way(self, monkeypatch):
        """The judge is handed the schema and the prompt in ONE call; two
        readings of "not only X but also Y" in that call is a judge told to
        contradict itself."""
        from dialectical_framework.agents.conversation_facilitator import \
            ConversationFacilitator
        from dialectical_framework.concerns.thesis_fit_check import (
            ThesisFitCheck, ThesisFitDto)

        seen = {}

        async def fake_submit(self, *, response_model, user_content):
            seen["prompt"] = user_content
            return ThesisFitDto(
                thesis_is_the_claim=1.0, a_plus_already_granted=0.0, reasoning="r"
            )

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        await ThesisFitCheck().score_texts(
            thesis="t", antithesis="a", a_plus="a+", text="words"
        )
        prompt = seen["prompt"]
        assert "concedes X" in prompt and "concedes Y" not in prompt
        assert "<context>\nwords\n</context>" in prompt


class TestWhoAsksForTheFit:
    """The writers that CHOOSE the thesis ask; the writers on a given pair do
    not, because every draw has the same T and A there and N calls would say
    nothing."""

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_the_view_turn_hands_the_persons_turns_to_both_judges(self, monkeypatch):
        seen: dict = {}
        names = iter(["a", "b"])

        async def fake_submit(self, model, content):
            return ViewSketchDto(tensions=[_tension(thesis=next(names))])

        async def fake_judge(cands, context=""):
            seen["cc"] = context
            return [SketchVerdict(0.8, 0.8) for _ in cands]

        async def fake_fit(cands, context):
            seen["fit"] = context
            return [0.9 for _ in cands]

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", fake_judge)
        monkeypatch.setattr(candidates, "judge_fit", fake_fit)
        head = Consultant(app_preamble="x", messages=list(_HISTORY))
        await head.exploration_view(focus="the office", attempts=2)
        assert seen == {"cc": "Should we close the Berlin office?", "fit": "Should we close the Berlin office?"}

    @pytest.mark.asyncio
    async def test_the_one_shot_build_hands_the_material_to_the_fit_judge(self, monkeypatch):
        seen: dict = {}
        names = iter(["a", "b"])

        async def fake_submit(self, model, content):
            return TetradSketchDto(tension=_tension(thesis=next(names)))

        async def fake_judge(cands, context=""):
            seen["cc"] = context
            return [SketchVerdict(0.8, 0.8) for _ in cands]

        async def fake_fit(cands, context):
            seen["fit"] = context
            return [0.9 for _ in cands]

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", fake_judge)
        monkeypatch.setattr(candidates, "judge_fit", fake_fit)
        await TetradSketch().resolve("I should keep the office.", context="He holds 45%.", attempts=2)
        assert seen == {"cc": "He holds 45%.", "fit": "I should keep the office."}, (
            "the control statements keep the caller's context; the fit judge reads the person's words"
        )

    @pytest.mark.asyncio
    async def test_the_staged_writer_on_a_given_pair_does_not_ask(self, monkeypatch):
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS, POSITION_T_PLUS)

        gen = TestTheStagedWriterSelectsToo()._generator(monkeypatch)
        gen._text = "the material"
        names = iter(["a", "b", "c"])

        async def fake_submit(self, response_model, user_content):
            return TestTheStagedWriterSelectsToo._dto(next(names))

        async def boom(cands, context):
            raise AssertionError("a given pair has one T and one A on every draw")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(candidates, "judge_sketches", lambda cands, context="": _same(cands))
        monkeypatch.setattr(candidates, "judge_fit", boom)
        await gen._generate_tetrad([POSITION_T_PLUS, POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS])

    def test_the_transformation_sketch_does_not_ask_either(self):
        import inspect

        from dialectical_framework.concerns import transformation_sketch

        assert "fit_against" not in inspect.getsource(transformation_sketch), (
            "a transition tetrad has no thesis to fit"
        )


async def _same(cands):
    return [SketchVerdict(0.8, 0.8) for _ in cands]
