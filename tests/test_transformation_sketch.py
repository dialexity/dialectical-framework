"""The graph-free one-shot Transformation (`concerns/transformation_sketch.py`).

What is pinned: that the ONE statement of the Transformation carries both
halves of the paper's minus transitions (their makeup and their ends), that the
synthesis prompt reads the same text rather than its own copy, the build order
of the DTO, and the concern's refusal of an incomplete tetrad. DB-free.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import transformation_sketch as ts
from dialectical_framework.graph.views import PerspectiveView, PoleView


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _tetrad(**blank) -> PerspectiveView:
    texts = dict(
        t="Keep the Berlin office",
        a="Go fully remote",
        t_plus="A place people choose to meet",
        t_minus="Only who can commute counts",
        a_plus="Hire wherever the talent is",
        a_minus="Everyone alone behind a screen",
    )
    poles = {k: (None if k in blank else PoleView(text=v)) for k, v in texts.items()}
    return PerspectiveView(**poles, intent=None, complete=not blank)


class TestTheTheoryIsStatedOnce:
    def test_the_minus_transitions_carry_both_halves(self):
        """[P0 pp.6,16-17]: what Ac-/Re- are MADE of and where they GO. The
        first app's copy kept only the first half (2026-10-06)."""
        text = ts.TRANSFORMATION_POSITIONS
        assert "Ac+ without Re+" in text and "Re+ without Ac+" in text
        assert "carries T's strength (T+) into A's trap (A-)" in text
        assert "carries A's strength (A+) into T's trap (T-)" in text
        assert "Ac+ contradicts Re-, and Re+ contradicts Ac-" in text
        assert "a path is not its destination" in text

    def test_the_pluses_are_the_circular_causality(self):
        text = ts.TRANSFORMATION_POSITIONS
        assert "Ac+ turns T's trap (T-) into A's strength (A+)" in text
        assert "Re+ turns A's trap (A-) into T's strength (T+)" in text

    def test_the_synthesis_prompt_reads_the_same_text(self):
        """One statement for the graph path's synthesis and the one-shot: a
        copy in either is the drift this module exists to end."""
        from dialectical_framework.concerns import synthesis_generation

        assert ts.TRANSFORMATION_POSITIONS in synthesis_generation.SYSTEM_PROMPT
        assert ts.SYNTHESIS_SHAPE in synthesis_generation.SYSTEM_PROMPT

    def test_the_measured_s_minus_rule_is_kept(self):
        assert "S- is the ONE named state" in ts.SYNTHESIS_SHAPE
        assert '"Either X or Y"' in ts.SYNTHESIS_SHAPE

    def test_the_procedure_puts_the_poles_first(self):
        """The measured order: a degraded action needs an action to degrade."""
        proc = ts.TRANSFORMATION_BUILD_PROCEDURE
        assert proc.index("The action (Ac)") < proc.index("Each developed well")
        assert proc.index("Each developed well") < proc.index("Each overdeveloped")
        assert proc.index("Each overdeveloped") < proc.index("S+ is what emerges")


class TestTheShape:
    def test_the_fields_are_in_build_order_and_text_only(self):
        fields = ts.TransformationSketchDto.model_fields
        assert list(fields) == [
            "action", "reflection", "ac_plus",
            "ac_minus_from", "ac_minus_into", "ac_minus",
            "re_plus",
            "re_minus_from", "re_minus_into", "re_minus",
            "s_plus", "s_minus",
        ]
        assert all(f.annotation is str for f in fields.values()), "no scores"

    def test_each_minus_line_is_preceded_by_its_ends(self):
        """The measured fix (2026-10-06, `probe_transformation_sketch.py`): the
        definition in text gave a valid Ac- / Re- in 30% / 26%; naming the start
        and the landing BEFORE the line moved them to 56% / 62%. The order is the
        mechanism — the model writes fields in order."""
        order = list(ts.TransformationSketchDto.model_fields)
        assert order.index("ac_minus_from") < order.index("ac_minus_into") < order.index("ac_minus")
        assert order.index("re_minus_from") < order.index("re_minus_into") < order.index("re_minus")
        fields = ts.TransformationSketchDto.model_fields
        assert "T's strengths (T+)" in fields["ac_minus_from"].description
        assert "A's trap (A-)" in fields["ac_minus_into"].description
        assert "A's strengths (A+)" in fields["re_minus_from"].description
        assert "T's trap (T-)" in fields["re_minus_into"].description

    def test_a_host_extends_it_after_the_derivation(self):
        """The first app's card writes its sentences in the same call; a
        subclass keeps the derivation's fields first."""
        from pydantic import Field

        class Card(ts.TransformationSketchDto):
            paragraph: str = Field(description="for the person")

        assert list(Card.model_fields)[:2] == ["action", "reflection"]
        assert list(Card.model_fields)[-1] == "paragraph"

    def test_the_request_carries_the_corners_and_the_lengths(self):
        request = ts.transformation_sketch_prompt(_tetrad(), "Should we keep Berlin?", 15, 7)
        assert 'They said: "Should we keep Berlin?"' in request
        assert "A's trap (A-): Everyone alone behind a screen" in request
        assert "at most 15 words" in request and "at most 7 words" in request
        assert "They said" not in ts.transformation_sketch_prompt(_tetrad(), "  ", 15, 7)


@pytest.mark.llm
class TestTheConcern:
    @pytest.mark.asyncio
    async def test_it_builds_from_a_complete_tetrad(self, monkeypatch):
        calls: list = []

        async def fake_submit(self, response_model, user_content):
            calls.append((self, response_model, user_content))
            return _dto("x", ac_plus="a+", s_minus="s-")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        concern = ts.TransformationSketch()
        sketch = await concern.resolve(_tetrad(), material="Should we keep Berlin?")

        (facilitator, model, request), = calls
        assert model is ts.TransformationSketchDto
        assert "Position (T): Keep the Berlin office" in request
        assert ts.TRANSFORMATION_BUILD_PROCEDURE in facilitator._messages[0].content.text
        assert sketch.s_minus == "s-"
        assert concern.report.ok and concern.report.artifacts["transformation"]["ac_plus"] == "a+"

    @pytest.mark.asyncio
    async def test_an_incomplete_tetrad_is_refused_without_a_call(self, monkeypatch):
        async def boom(self, response_model, user_content):
            raise AssertionError("an empty corner would be invented, not read")

        monkeypatch.setattr(ConversationFacilitator, "submit", boom)
        with pytest.raises(ValueError, match="a_minus"):
            await ts.TransformationSketch().resolve(_tetrad(a_minus=True))


@pytest.mark.llm
class TestSelectionIsAvailableAndOffByDefault:
    """Best-of-N with the tetrad writers' judge, through the paper's transition
    control statements; ONE draw by default until a measurement says otherwise."""

    def test_the_judge_reads_the_transition_tetrad_in_the_tetrads_corners(self):
        """Rule 5.2: "Ac+ without Re+ yields Ac-" is "T+ without A+ yields T-"
        with the transition positions in the corners."""
        from dialectical_framework.concerns.control_statements_check import \
            control_statements

        sketch = _dto("x", ac_plus="AC+", ac_minus="AC-", re_plus="RE+", re_minus="RE-")
        c = ts.as_control_tetrad(sketch)
        first, second = control_statements(
            t_plus=c.t_plus, t_minus=c.t_minus, a_plus=c.a_plus, a_minus=c.a_minus
        )
        assert first == '"AC+" without "RE+" yields "AC-"'
        assert second == '"RE+" without "AC+" yields "RE-"'

    def test_the_default_is_one(self):
        assert ts.DEFAULT_TRANSFORMATION_ATTEMPTS == 1

    @pytest.mark.asyncio
    async def test_one_draw_by_default_and_no_judge(self, monkeypatch):
        from dialectical_framework.concerns import tetrad_candidates

        calls: list = []

        async def fake_submit(self, response_model, user_content):
            calls.append(self)
            return _dto("a")

        async def boom(candidates, context=""):
            raise AssertionError("one draw is never judged")

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(tetrad_candidates, "judge_sketches", boom)
        concern = ts.TransformationSketch()
        await concern.resolve(_tetrad())
        assert len(calls) == 1 and concern.verdict is None and concern.alternatives == []
        assert "attempts" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_three_draws_keep_the_most_coherent(self, monkeypatch):
        from dialectical_framework.concerns import tetrad_candidates
        from dialectical_framework.concerns.tetrad_candidates import SketchVerdict

        names = iter(["a", "b", "c"])
        drawn: list = []

        async def fake_submit(self, response_model, user_content):
            drawn.append(self)
            return _dto(next(names))

        async def judge(candidates, context=""):
            table = {"a": (0.9, 0.5), "b": (0.8, 0.8), "c": (0.7, 0.7)}
            return [SketchVerdict(*table[c.t_plus.split("-")[0]]) for c in candidates]

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        monkeypatch.setattr(tetrad_candidates, "judge_sketches", judge)
        concern = ts.TransformationSketch()
        sketch = await concern.resolve(_tetrad(), attempts=3)

        assert sketch.ac_plus == "b-ac+"
        assert len({id(f) for f in drawn}) == 3, "fresh facilitator per draw"
        assert concern.verdict.floor == 0.8
        assert [alt.ac_plus for alt, _v in concern.alternatives] == ["a-ac+", "c-ac+"]
        assert concern.report.artifacts["attempts"] == {
            "drawn": 3, "selected": 1, "floors": [0.5, 0.8, 0.7]
        }


def _dto(tag: str, **overrides: str) -> ts.TransformationSketchDto:
    fields = dict(
        action=f"{tag}-ac", reflection=f"{tag}-re", ac_plus=f"{tag}-ac+",
        ac_minus_from=f"{tag}-from", ac_minus_into=f"{tag}-into", ac_minus=f"{tag}-ac-",
        re_plus=f"{tag}-re+",
        re_minus_from=f"{tag}-rfrom", re_minus_into=f"{tag}-rinto", re_minus=f"{tag}-re-",
        s_plus=f"{tag}-s+", s_minus=f"{tag}-s-",
    )
    fields.update(overrides)
    return ts.TransformationSketchDto(**fields)
