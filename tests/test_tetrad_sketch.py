"""The one-shot build: one reasoning call writes the tetrad, the graph persists it.

`concerns/tetrad_sketch.py` (the call), `AspectGeneration.score_given` (scores
for texts someone else wrote), `ExpandPolarity(given_tetrad=)` (the seam), and
`agents/analyst/skills/sketch_tetrad.py` (the composition). The mock brain fills
every DTO, so these pin the WIRING: what the call is given, what is written,
that nothing is rewritten, and that the result is a normal tetrad.

Run: poetry run pytest tests/test_tetrad_sketch.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              GivenTetrad,
                                                              TetradScoresDto)
from dialectical_framework.concerns.tetrad_sketch import (TetradSketch,
                                                          TetradSketchDto,
                                                          tetrad_sketch_prompt)
from dialectical_framework.concerns.view_sketch import (
    TETRAD_BUILD_PROCEDURE, ViewSketchPerspectiveDto, view_sketch_prompt)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)
from dialectical_framework.graph.scope_context import scope

UTTERANCE = "I should quit my job and start my own company."

SKETCH = ViewSketchPerspectiveDto(
    thesis="Quit and start my own company",
    antithesis="Keep the craft and security of employment",
    t_plus_vs_a_minus_axis="ownership of outcomes",
    t_plus="Build something I own, using what the job taught me",
    a_minus="Clinging to a salary that stops me growing",
    a_plus_vs_t_minus_axis="footing",
    a_plus="Deepen my craft on the job, then leap with footing",
    t_minus="Jumping with no footing and nothing to sell",
)


def fake_tetrad_sketch(monkeypatch, tension: ViewSketchPerspectiveDto = SKETCH) -> list[dict]:
    """Replace the one reasoning call with a fixed tetrad; returns the calls seen.

    Shared by every test that drives the thesis-only `anchor` (which is the
    one-shot build since 2026-10-01): the mock brain would fill the sketch DTO
    with placeholder strings, and the graph then needs real-looking poles.
    """
    seen: list[dict] = []

    async def fake(self, material, context="", thesis=None):
        seen.append({"material": material, "context": context, "thesis": thesis})
        self._report.ok = True
        return tension

    monkeypatch.setattr(TetradSketch, "resolve", fake)
    return seen


class TestThePrompt:
    def test_a_given_thesis_is_pinned_not_replaced(self):
        """`anchor` names the position to plant; the call words it, it does not
        pick another."""
        pinned = tetrad_sketch_prompt(UTTERANCE, "", 7, thesis="Quit and found a company")
        assert 'The thesis (T) is GIVEN: "Quit and found a company"' in pinned
        assert "Keep its meaning as the position" in pinned
        free = tetrad_sketch_prompt(UTTERANCE, "", 7)
        assert "is GIVEN" not in free
        assert "the position the person holds or is weighing in this material" in free

    def test_the_antithesis_cannot_be_pinned(self):
        """Measured and removed (2026-10-02): with both poles given the writer
        drifted off the pair in 17–22 of 40. The given-pair writer is
        `AspectGeneration._generate_tetrad`; this one chooses its opposition."""
        import inspect

        assert "antithesis" not in inspect.signature(tetrad_sketch_prompt).parameters
        assert "antithesis" not in inspect.signature(TetradSketch.resolve).parameters

    def test_material_is_optional_when_the_thesis_is_pinned(self):
        """Off the turn the Advisor's `anchor` has no Input: the pinned thesis
        plus `context` is what the call reads, and no empty tag is sent."""
        prompt = tetrad_sketch_prompt("", "", 7, thesis="Keep the Berlin office")
        assert "<material>" not in prompt
        assert 'is GIVEN: "Keep the Berlin office"' in prompt

    def test_the_system_prompt_is_the_method(self):
        """Read, not copied: the bench's A1 baseline and this builder cannot
        drift apart, because they are one function."""
        from dialectical_framework.agents.consultant.consultant import method_prompt

        assert TetradSketch.system_prompt() == method_prompt(include_decision=False)
        assert TetradSketch.system_prompt("## Persona\nwarm").startswith("## Persona\nwarm\n\n")

    def test_the_request_carries_the_words_the_procedure_and_the_asks(self):
        from dialectical_framework.concerns.antithesis_extraction import \
            _OPPOSING_POSITION_ASK

        prompt = tetrad_sketch_prompt(UTTERANCE, "He holds 45%.", 7)
        assert "<material>\n" + UTTERANCE in prompt
        assert "<context>\nHe holds 45%." in prompt
        assert TETRAD_BUILD_PROCEDURE in prompt
        assert _OPPOSING_POSITION_ASK in prompt
        assert "ONE tension" in prompt
        assert "7 words or fewer" in prompt
        assert "<context>" not in tetrad_sketch_prompt(UTTERANCE, "", 7)

    def test_the_build_procedure_is_shared_with_the_view_turn_byte_for_byte(self):
        """Two one-shot builders, one procedure. The view turn's prompt is the
        measured one, so the constant must land in it unchanged."""
        assert TETRAD_BUILD_PROCEDURE in view_sketch_prompt(None, 7)
        assert TETRAD_BUILD_PROCEDURE.startswith("Building a tetrad, when you build one")
        assert "(b) Restated parent:" in TETRAD_BUILD_PROCEDURE

    def test_the_dto_is_one_flat_tension_with_no_numbers(self):
        fields = TetradSketchDto.model_fields
        assert list(fields) == ["tension"]
        for name, field in ViewSketchPerspectiveDto.model_fields.items():
            assert field.annotation is str, name


@pytest.mark.llm
class TestTheSketchCall:
    @pytest.mark.asyncio
    async def test_no_material_and_no_thesis_is_refused(self):
        with pytest.raises(ValueError, match="material or a thesis"):
            await TetradSketch().resolve("   ")

    @pytest.mark.asyncio
    async def test_a_sketch_with_an_empty_corner_is_refused(self, monkeypatch):
        """A complete tetrad or nothing: the graph cannot hold a blank
        position, and an invented one is worse."""
        from dialectical_framework.agents.conversation_facilitator import \
            ConversationFacilitator

        async def fake_submit(self, model, content):
            return TetradSketchDto(tension=SKETCH.model_copy(update={"a_plus": ""}))

        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        with pytest.raises(ValueError, match="a_plus"):
            await TetradSketch().resolve(UTTERANCE)

    @pytest.mark.asyncio
    async def test_the_call_is_json_mode_with_the_method_as_system_prompt(self, monkeypatch):
        from dialectical_framework.agents.conversation_facilitator import \
            ConversationFacilitator

        seen: dict = {}
        original_set = ConversationFacilitator.set_system_prompt

        def spy_set(self, system_prompt):
            seen["system"] = system_prompt
            original_set(self, system_prompt)

        async def fake_submit(self, model, content):
            seen["format_mode"] = self._format_mode
            seen["content"] = content
            return TetradSketchDto(tension=SKETCH)

        monkeypatch.setattr(ConversationFacilitator, "set_system_prompt", spy_set)
        monkeypatch.setattr(ConversationFacilitator, "submit", fake_submit)
        tension = await TetradSketch().resolve(UTTERANCE, "He holds 45%.")
        assert tension == SKETCH
        assert seen["format_mode"] == "json"
        assert seen["system"] == TetradSketch.system_prompt()
        assert UTTERANCE in seen["content"] and "He holds 45%." in seen["content"]


def _given() -> GivenTetrad:
    return GivenTetrad(
        texts={
            POSITION_T_PLUS: SKETCH.t_plus,
            POSITION_T_MINUS: SKETCH.t_minus,
            POSITION_A_PLUS: SKETCH.a_plus,
            POSITION_A_MINUS: SKETCH.a_minus,
        },
        axes={
            "t_plus_vs_a_minus": SKETCH.t_plus_vs_a_minus_axis,
            "a_plus_vs_t_minus": SKETCH.a_plus_vs_t_minus_axis,
        },
    )


@pytest.mark.llm
class TestScoringAGivenTetrad:
    @pytest.mark.asyncio
    async def test_the_texts_are_persisted_verbatim_and_only_scored(self, monkeypatch):
        from test_expand_polarities_grounding import _make_polarity

        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity

        case = Case()
        case.commit()
        seen: dict = {}
        original = AspectGeneration._scores_prompt

        def spy(self, given):
            prompt = original(self, given)
            seen["prompt"] = prompt
            return prompt

        async def never(self, *a, **k):
            raise AssertionError("the generator must not write when a tetrad is given")

        monkeypatch.setattr(AspectGeneration, "_scores_prompt", spy)
        monkeypatch.setattr(AspectGeneration, "_generate_tetrad", never)

        with scope(case.sid):
            polarity = _make_polarity(case.sid)
            pps = await ExpandPolarity(
                polarity_hash=polarity.hash, given_tetrad=_given(), count=3
            ).resolve()
            assert len(pps) == 1, "a given tetrad is one tetrad, whatever count says"
            pp = pps[0]
            texts = {
                POSITION_T_PLUS: pp.t_plus.get()[0].text,
                POSITION_T_MINUS: pp.t_minus.get()[0].text,
                POSITION_A_PLUS: pp.a_plus.get()[0].text,
                POSITION_A_MINUS: pp.a_minus.get()[0].text,
            }
            assert texts == _given().texts
            # scored: the mock brain fills the floats, and they land on the edges
            for manager in (pp.t_plus, pp.t_minus, pp.a_plus, pp.a_minus):
                _node, rel = manager.get()
                assert rel.heuristic_similarity is not None
                assert rel.complementarity_t is not None and rel.complementarity_a is not None
            assert pp.intent == "Reading along: ownership of outcomes / footing"

        assert "do not rewrite" in seen["prompt"]
        for text in _given().texts.values():
            assert text in seen["prompt"]

    def test_the_scores_dto_echoes_no_text(self):
        """A scorer that could rewrite is a second generator."""
        for position_field in TetradScoresDto.model_fields.values():
            inner = position_field.annotation.model_fields
            assert set(inner) == {"heuristic_similarity", "complementarity_t", "complementarity_a"}


@pytest.mark.llm
class TestTheSkill:
    @pytest.mark.asyncio
    async def test_one_utterance_becomes_one_persisted_tetrad_with_its_source(self, monkeypatch):
        from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
            SketchTetrad
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.repositories.input_repository import \
            InputRepository
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        async def fake_sketch(self, material, context="", thesis=None):
            # the material is what the Input renders, not a text the host repeats
            assert UTTERANCE in material and "<Input id=" in material
            assert thesis is None, "a host's paste pins nothing; the call finds the position"
            self._report.ok = True
            return SKETCH

        monkeypatch.setattr(TetradSketch, "resolve", fake_sketch)
        case = Case()
        case.commit()
        with scope(case.sid):
            source = Input(content=UTTERANCE)
            source.commit()
            skill = SketchTetrad(input_hashes=[source.hash])
            pps = await skill.resolve()
            assert len(pps) == 1
            pp = pps[0]
            assert pp.t.get()[0].text == SKETCH.thesis
            assert pp.a.get()[0].text == SKETCH.antithesis
            assert pp.t_plus.get()[0].text == SKETCH.t_plus
            report = skill.report.artifacts
            assert report["perspective_hashes"] == [pp.hash]
            assert report["polarity_quality"][0]["status"] == "expanded"
            assert report["polarity_quality"][0]["tetrad_potential"] is None
            # both poles trace to the Input that keeps the person's words
            sources = InputRepository().find_by_statement_hashes(
                [pp.t.get()[0].hash, pp.a.get()[0].hash]
            )
            assert {i.hash for v in sources.values() for i in v} == {source.hash}
            assert PerspectiveRepository().find_by_polarity(pp.polarity.get()[0])

    @pytest.mark.asyncio
    async def test_no_input_and_no_thesis_builds_nothing(self):
        from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
            SketchTetrad

        case = Case()
        case.commit()
        with scope(case.sid):
            skill = SketchTetrad()
            assert await skill.resolve() == []
            assert skill.report.ok is False

    @pytest.mark.asyncio
    async def test_a_pinned_thesis_with_no_input_builds_from_the_thesis(self, monkeypatch):
        """The Advisor's `anchor` off the turn: no Input, the thesis pinned."""
        from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
            SketchTetrad

        seen = fake_tetrad_sketch(monkeypatch)
        case = Case()
        case.commit()
        with scope(case.sid):
            pps = await SketchTetrad(thesis="Quit and start my own company", context="He holds 45%.").resolve()
        assert len(pps) == 1
        assert seen == [{"material": "", "context": "He holds 45%.", "thesis": "Quit and start my own company"}]


@pytest.mark.llm
class TestTheOppositionIsEvaluatedWhileTheTetradIsScored:
    @pytest.mark.asyncio
    async def test_classify_opposition_overlaps_expand(self, monkeypatch):
        """The ~12 s antithesis evaluation used to stand in the chain ahead of
        scoring, grounding and validation, none of which read its result. The
        skill now gathers it with `ExpandPolarity`; the write of its result
        (`record_opposition`) follows on the parent task."""
        import asyncio

        from dialectical_framework.agents.analyst.skills import sketch_tetrad as mod
        from dialectical_framework.agents.analyst.skills.introduce_polarity import \
            IntroducePolarity
        from dialectical_framework.agents.analyst.skills.sketch_tetrad import \
            SketchTetrad

        fake_tetrad_sketch(monkeypatch)
        events: list[str] = []
        original_classify = IntroducePolarity.classify_opposition
        original_record = IntroducePolarity.record_opposition
        expand_gate = asyncio.Event()

        async def slow_classify(self):
            events.append("classify:start")
            await expand_gate.wait()  # cannot finish until expand has started
            result = await original_classify(self)
            events.append("classify:end")
            return result

        def record(self, classification):
            events.append("record")
            return original_record(self, classification)

        original_expand = mod.ExpandPolarity.resolve

        async def expand(self):
            events.append("expand:start")
            expand_gate.set()
            out = await original_expand(self)
            events.append("expand:end")
            return out

        monkeypatch.setattr(IntroducePolarity, "classify_opposition", slow_classify)
        monkeypatch.setattr(IntroducePolarity, "record_opposition", record)
        monkeypatch.setattr(mod.ExpandPolarity, "resolve", expand)

        case = Case()
        case.commit()
        with scope(case.sid):
            pps = await SketchTetrad(thesis="Quit and start my own company").resolve()
            assert len(pps) == 1
            # the opposition's HS landed on the edge after the overlap
            _a, rel = pps[0].polarity.get()[0].a.get()
            assert rel.heuristic_similarity is not None

        assert events.index("classify:start") < events.index("expand:end")
        assert events.index("expand:start") < events.index("classify:end"), "no overlap"
        assert events[-1] == "record", "the write comes last, on the parent task"
