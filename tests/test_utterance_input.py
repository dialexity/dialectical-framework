"""The person's own words come in as an Input, and a tension reads its own.

Before 2026-10-01 the original wording behind an anchored tension was stored
nowhere: `anchor` kept a ≤7-word headline as the Statement and the model's
paraphrase as `context`. Now the turn the tool fired on is kept VERBATIM as an
`Input` (content-addressed, so one turn is one Input however many anchors it
fires), linked to the poles as their source, and `inputs_for_statements` makes
it — not every digest in the case — the material the tension is developed
against. A note carries the turn it was kept on to the plant that runs later.

Run: poetry run pytest tests/test_utterance_input.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.tools import anchor as anchor_mod
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.input_context import inputs_for_statements
from dialectical_framework.utils.utterance import current_utterance, speaking

A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"
UTTERANCE = (
    "I'm thinking of buying out my cofounder. He holds 45%, he closed both of "
    "our big accounts, and I've been a plus-one on every call with them."
)


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid
    return case.sid


@pytest.fixture
def one_antithesis(monkeypatch):
    """The thesis-only branch is the one-shot build: its reasoning call is
    replaced with a fixed tetrad so the graph gets real-looking poles."""
    from test_tetrad_sketch import fake_tetrad_sketch

    return fake_tetrad_sketch(monkeypatch)


def _report(json_text: str) -> dict:
    import json

    return json.loads(json_text)


def _sources_of(statement_hashes: list[str]) -> dict[str, list[Input]]:
    return InputRepository().find_by_statement_hashes(statement_hashes)


class TestTheScope:
    def test_blank_is_none_and_nesting_restores(self):
        assert current_utterance() is None
        with speaking("  "):
            assert current_utterance() is None
        with speaking("outer"):
            assert current_utterance() == "outer"
            with speaking(" inner "):
                assert current_utterance() == "inner"
            assert current_utterance() == "outer"
        assert current_utterance() is None


@pytest.mark.llm
class TestAnchorKeepsThePersonsWords:
    @pytest.mark.asyncio
    async def test_thesis_only_anchor_keeps_the_turn_as_an_input_the_thesis_traces_to(
        self, one_antithesis
    ):
        sid = _new_sid()
        with scope(sid), speaking(UTTERANCE):
            report = _report(
                await anchor_mod.anchor.fn(thesis="Buy out the cofounder", context="")
            )
        with scope(sid):
            inputs = InputRepository().get_all()
            assert [i.content for i in inputs] == [UTTERANCE]
            assert report["artifacts"]["input_hash"] == inputs[0].hash
            theses = [report["artifacts"]["thesis_hash"]]
            sources = _sources_of(theses)
            assert {i.hash for i in sources[theses[0]]} == {inputs[0].hash}

    @pytest.mark.asyncio
    async def test_two_pole_anchor_links_both_poles_to_the_turn(self):
        sid = _new_sid()
        with scope(sid), speaking(UTTERANCE):
            report = _report(
                await anchor_mod.anchor.fn(
                    thesis="Buy out the cofounder",
                    antithesis="Keep the partnership",
                    context="",
                )
            )
        with scope(sid):
            inputs = InputRepository().get_all()
            assert len(inputs) == 1 and inputs[0].content == UTTERANCE
            assert report["artifacts"]["input_hash"] == inputs[0].hash
            from dialectical_framework.graph.nodes.polarity import Polarity
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            found = NodeRepository().find_by_hashes(
                [report["artifacts"]["primary_polarity_hash"]], node_type=Polarity
            )
            assert len(found) == 1
            polarity = found[0]
            poles = [node for manager in (polarity.t, polarity.a) for node, _rel in manager.all()]
            assert sorted(s.text for s in poles) == ["Buy out the cofounder", "Keep the partnership"]
            sources = _sources_of([s.hash for s in poles])
            for s in poles:
                assert {i.hash for i in sources[s.hash]} == {inputs[0].hash}, s.text

    @pytest.mark.asyncio
    async def test_one_turn_is_one_input_however_many_anchors_fire_on_it(self):
        sid = _new_sid()
        with scope(sid), speaking(UTTERANCE):
            await anchor_mod.anchor.fn(
                thesis="Buy out the cofounder", antithesis="Keep the partnership"
            )
            await anchor_mod.anchor.fn(
                thesis="Transfer the accounts first", antithesis="Leave the accounts with him"
            )
        with scope(sid):
            assert len(InputRepository().get_all()) == 1

    @pytest.mark.asyncio
    async def test_no_turn_means_no_input_and_no_artifact(self):
        """Off the turn (`_anchor(utterance=None)`), and the headless caller:
        the path is as it was."""
        sid = _new_sid()
        with scope(sid):
            assert current_utterance() is None
            report = _report(
                await anchor_mod._anchor(
                    thesis="Buy out the cofounder",
                    antithesis="Keep the partnership",
                    context="",
                    utterance=None,
                )
            )
            assert InputRepository().get_all() == []
            assert "input_hash" not in report["artifacts"]


@pytest.mark.llm
class TestATensionReadsItsOwnSources:
    """`inputs_for_statements`: own sources when there are any, else all."""

    def test_own_inputs_only_when_a_statement_has_a_source(self):
        sid = _new_sid()
        with scope(sid):
            mine = Input(content="the turn this thesis came from")
            mine.commit()
            other = Input(content="an unrelated document ingested earlier")
            other.commit()
            thesis = Statement(text="Buy out the cofounder", meaning=A_MEANING)
            thesis.commit()
            mine.statements.connect(thesis)
            orphan = Statement(text="Something with no source", meaning=A_MEANING)
            orphan.commit()

            assert [i.hash for i in inputs_for_statements([thesis.hash])] == [mine.hash]
            # a pair where one pole has a source: the source, not everything
            assert [i.hash for i in inputs_for_statements([thesis.hash, orphan.hash])] == [
                mine.hash
            ]
            # no provenance at all: every Input, as before
            assert {i.hash for i in inputs_for_statements([orphan.hash])} == {
                mine.hash,
                other.hash,
            }
            assert {i.hash for i in inputs_for_statements([])} == {mine.hash, other.hash}

    @pytest.mark.asyncio
    async def test_thesis_only_anchor_develops_against_its_turn_not_the_cases_documents(
        self, monkeypatch, one_antithesis
    ):
        """END TO END through `anchor.fn`, because the unit test below could not
        see what review found: `FindPolarities._create_ideas` linked EVERY Input
        to its Ideas container, so both poles traced to every document and the
        own-sources rule collapsed back to "all" on exactly this path."""
        from dialectical_framework.concerns.aspect_generation import AspectGeneration

        sid = _new_sid()
        seen: list[str] = []
        original = AspectGeneration.score_given

        async def _recording(self, perspective, given, text=""):
            seen.append(text)
            return await original(self, perspective, given, text)

        with scope(sid):
            other = Input(content="OTHER DOCUMENT: an unrelated quarterly report")
            other.commit()
            monkeypatch.setattr(AspectGeneration, "score_given", _recording)
            with speaking("MY TURN: " + UTTERANCE):
                report = _report(
                    await anchor_mod.anchor.fn(thesis="Buy out the cofounder", context="")
                )
            theses = [report["artifacts"]["thesis_hash"]]
            sources = _sources_of(theses)
            assert {i.content for i in sources[theses[0]]} == {"MY TURN: " + UTTERANCE}

        assert seen, "no tetrad was generated"
        assert all("MY TURN" in text for text in seen)
        assert not any("OTHER DOCUMENT" in text for text in seen)

    @pytest.mark.asyncio
    async def test_off_turn_anchor_links_no_source_rather_than_all(self):
        """`_anchor(utterance=None)` → `AnchorTheses(input_hashes=[])`: a stance
        anchored off the turn traces to nothing, not to every document."""
        from dialectical_framework.agents.analyst.skills.anchor_theses import \
            AnchorTheses

        sid = _new_sid()
        with scope(sid):
            doc = Input(content="a document already in the case")
            doc.commit()
            skill = AnchorTheses(statements=["Close the Berlin office"], input_hashes=[])
            await skill.resolve()
            theses = skill.report.artifacts["thesis_hashes"]
            assert theses
            assert _sources_of(theses) == {}
            # and the Analyst's contract — None — still means every Input
            legacy = AnchorTheses(statements=["Keep the Berlin office"], input_hashes=None)
            await legacy.resolve()
            legacy_theses = legacy.report.artifacts["thesis_hashes"]
            assert {i.hash for i in _sources_of(legacy_theses)[legacy_theses[0]]} == {doc.hash}

    @pytest.mark.asyncio
    async def test_the_aspect_call_reads_the_tensions_own_turn_not_the_other_documents(
        self, monkeypatch
    ):
        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity
        from dialectical_framework.concerns.aspect_generation import AspectGeneration
        from test_expand_polarities_grounding import (_distinct_aspect_stub,
                                                      _make_polarity)

        sid = _new_sid()
        seen: dict = {}
        with scope(sid):
            own = Input(content="OWN TURN: he closed both accounts")
            own.commit()
            other = Input(content="OTHER DOCUMENT: quarterly revenue table")
            other.commit()
            polarity = _make_polarity(sid)
            thesis_node = next(node for node, _rel in polarity.t.all())
            own.statements.connect(thesis_node)

            stub, _ = _distinct_aspect_stub(sid)

            async def _recording(self, perspective, positions=None, text="", not_like_these=None):
                seen["text"] = text
                return await stub(self, perspective, positions, text, not_like_these)

            monkeypatch.setattr(AspectGeneration, "resolve", _recording)
            await ExpandPolarity(polarity_hash=polarity.hash).resolve()

        assert "OWN TURN" in seen["text"]
        assert "OTHER DOCUMENT" not in seen["text"]


class TestTheAdvisorSpeaksForTheTurn:
    """DB-free: the ContextVar is set around the provider round and only there."""

    @pytest.mark.asyncio
    async def test_chat_sets_the_utterance_during_submit_and_clears_it_after(self, monkeypatch):
        from dialectical_framework.agents.advisor.advisor import Advisor
        from dialectical_framework.agents.advisor.build_policy import BuildPolicy

        case = Case()
        case.commit()
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.NEVER)
            seen: dict = {}

            async def fake_submit(model, message):
                seen["during"] = current_utterance()
                return model(message="ok")

            async def fake_repair(user_message, reply):
                seen["after"] = current_utterance()

            monkeypatch.setattr(advisor._conversation, "submit", fake_submit)
            monkeypatch.setattr(advisor, "_repair_unrecorded_decision", fake_repair)
            await advisor.chat("  My cofounder never listens to me.  ")

        assert seen["during"] == "My cofounder never listens to me."
        assert seen["after"] is None, "the closing seam runs outside the scope"
        assert current_utterance() is None

    @pytest.mark.asyncio
    async def test_a_note_keeps_the_turn_and_hands_it_to_the_plant(self, monkeypatch):
        from dialectical_framework.agents.advisor.advisor import Advisor
        from dialectical_framework.agents.advisor.build_policy import BuildPolicy

        case = Case()
        case.commit()
        planted: list[dict] = []

        async def fake_anchor(*, thesis, antithesis, context, utterance=None):
            planted.append({"thesis": thesis, "utterance": utterance})
            return '{"artifacts": {"perspective_hashes": ["pp0001"]}}'

        monkeypatch.setattr(anchor_mod, "_anchor", fake_anchor)
        with scope(case.sid):
            advisor = Advisor(build=BuildPolicy.ON_CONSENT)
            with speaking("Please write down that I want to keep the Berlin office."):
                await advisor._queue_note("Keep the Berlin office", None, "12 people there")
            from dialectical_framework.graph.repositories.note_repository import \
                NoteRepository

            notes = NoteRepository().find_unplanted()
            assert [n.utterance for n in notes] == [
                "Please write down that I want to keep the Berlin office."
            ]
            # planted later, with no turn in progress: the note's own turn travels
            assert current_utterance() is None
            await advisor._plant_noted_tensions([], notes)

        assert planted == [
            {
                "thesis": "Keep the Berlin office",
                "utterance": "Please write down that I want to keep the Berlin office.",
            }
        ]
