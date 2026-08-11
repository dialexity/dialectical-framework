"""Case particulars survive the tetrad's abstraction and reach the counsel dump.

The tetrad's text is universal by construction (~7-word poles, `commit()` dedup,
taxonomy anchoring). That is what makes it transferable and also what made the
live Advisor unable to say "you told me he's not a rainmaker": measured across
six counsel sessions, the graph carried 0 of 15 case particulars while a plain
LLM keeping its own session notes carried 11 of 15.

Grounding rides on `ExplainsRelationship.role == ROLE_GROUNDING`. These tests
pin the properties that make it useful rather than merely present:

  * it RENDERS unconditionally in the context dump — the moment it matters is a
    returning session's wobble, when the model does not know it needs to call
    `inspect_node`, so anything lazily loaded is anything unread;
  * machine assessment rationales (control-statement checks, causality
    reasoning) STAY OUT — they share the lane, and rendering them would bury
    each tetrad under CC/DV prose on every single turn;
  * a shared pole's note is not repeated per position.

Run: poetry run pytest tests/test_tetrad_grounding.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.explains_relationship import \
    ROLE_GROUNDING
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.rendering import (GROUNDING_PREFIX,
                                                   grounding_line)
from dialectical_framework.graph.scope_context import scope

PARTICULARS = (
    "Founder holds 55%. Cofounder closed both major customers and is on all "
    "their calls; founder joined three as a plus-one. Feedback given in March, "
    "acknowledged, no change since."
)


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _tetrad(t_minus_text: str = "Unchecked solo momentum") -> Perspective:
    """A fully-populated committed Perspective (cardinality requires all six)."""
    thesis = Statement(text="Hold the reins alone", meaning="test")
    thesis.commit()
    antithesis = Statement(text="Share the decisions", meaning="test")
    antithesis.commit()

    polarity = Polarity()
    polarity.set_t(thesis, heuristic_similarity=1.0)
    polarity.set_a(antithesis, heuristic_similarity=0.8)
    polarity.commit()

    aspects = {}
    for key, text in (
        ("t_plus", "Decisive autonomy with feedback"),
        ("t_minus", t_minus_text),
        ("a_plus", "Deliberation that still decides"),
        ("a_minus", "Consensus that blocks action"),
    ):
        stmt = Statement(text=text, meaning="test")
        stmt.commit()
        aspects[key] = stmt

    pp = Perspective()
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
    pp.t_plus.connect(
        aspects["t_plus"],
        relationship=TPlusRelationship(alias=POSITION_T_PLUS, heuristic_similarity=0.9),
    )
    pp.t_minus.connect(
        aspects["t_minus"],
        relationship=TMinusRelationship(alias=POSITION_T_MINUS, heuristic_similarity=0.85),
    )
    pp.a_plus.connect(
        aspects["a_plus"],
        relationship=APlusRelationship(alias=POSITION_A_PLUS, heuristic_similarity=0.88),
    )
    pp.a_minus.connect(
        aspects["a_minus"],
        relationship=AMinusRelationship(alias=POSITION_A_MINUS, heuristic_similarity=0.82),
    )
    pp.commit()
    return pp


def _ground(target, text: str = PARTICULARS) -> Rationale:
    rationale = Rationale(text=text)
    rationale.set_explanation_target(target, role=ROLE_GROUNDING)
    rationale.commit()
    return rationale


class TestGroundingLine:
    def test_grounding_renders(self):
        with scope(_new_sid()):
            pp = _tetrad()
            _ground(pp)

            line = grounding_line(pp)
            assert line is not None
            assert line.startswith(GROUNDING_PREFIX)
            assert "55%" in line
            assert "March" in line

    def test_machine_assessment_prose_is_not_grounding(self):
        """The lane is shared — an untagged rationale must stay invisible here.

        Without this filter every tetrad in the dump would carry its
        control-statement and DV reasoning, on every turn.
        """
        with scope(_new_sid()):
            pp = _tetrad()
            assessment = Rationale(
                text=(
                    "T+ without A+ yields T- (CC=0.82, DV=0.71): coherence "
                    "reasoning no reader wants inline."
                )
            )
            assessment.set_explanation_target(pp)  # no role
            assessment.commit()

            assert grounding_line(pp) is None

    def test_notes_accrete_in_disclosure_order(self):
        """A person reveals more later; the note reads as a chronology."""
        with scope(_new_sid()):
            pp = _tetrad()
            _ground(pp, "Founder holds 55%.")
            _ground(pp, "Two customers pay most of the bills.")

            line = grounding_line(pp)
            assert line is not None
            assert line.index("55%") < line.index("Two customers")

    def test_ungrounded_perspective_renders_nothing(self):
        with scope(_new_sid()):
            assert grounding_line(_tetrad()) is None


class TestContextDumpRendersGrounding:
    def test_dump_carries_the_particulars(self):
        """The dump is what the model sees at a returning session's wobble.

        Asserted on `_dump_one_perspective` rather than the whole `resolve()`
        because the full dump applies quality floors that would suppress an
        unscored perspective for unrelated reasons — this pins the grounding
        seam, not the pruning policy.
        """
        with scope(_new_sid()):
            pp = _tetrad()
            _ground(pp)

            block = DialecticalContext()._dump_one_perspective(pp)

            assert GROUNDING_PREFIX.strip() in block
            assert "55%" in block

    def test_assessment_prose_stays_out_of_the_dump(self):
        with scope(_new_sid()):
            pp = _tetrad()
            assessment = Rationale(text="CC=0.9 because the poles cohere.")
            assessment.set_explanation_target(pp)
            assessment.commit()

            block = DialecticalContext()._dump_one_perspective(pp)

            assert GROUNDING_PREFIX.strip() not in block

    def test_pole_grounding_renders_once_not_per_position(self):
        """A pole's note is deduplicated against the tetrad's own.

        `commit()` dedup makes one Statement the minus of several perspectives,
        so the same particulars attached at both levels would otherwise repeat
        down the block.
        """
        with scope(_new_sid()):
            pp = _tetrad()
            t_minus, _ = pp.t_minus.get()
            _ground(pp)
            _ground(t_minus)

            block = DialecticalContext()._dump_one_perspective(pp)

            assert block.count("55%") == 1

    def test_pole_only_grounding_still_surfaces(self):
        """Grounding a pole alone must reach the block — a Statement survives
        dedup reuse where a per-perspective note does not."""
        with scope(_new_sid()):
            pp = _tetrad()
            t_minus, _ = pp.t_minus.get()
            _ground(t_minus, "Cofounder is on every customer call.")

            block = DialecticalContext()._dump_one_perspective(pp)

            assert "every customer call" in block


class TestInspectNodeRendersGrounding:
    @pytest.mark.asyncio
    async def test_inspect_perspective_shows_grounding(self):
        """Same helper as the dump, so the two views cannot disagree."""
        from dialectical_framework.agents.orchestrator.tools.inspect_node import \
            InspectNode

        with scope(_new_sid()):
            pp = _tetrad()
            _ground(pp)

            out = await InspectNode().resolve(node_hash=pp.hash)

            assert "55%" in out


class TestPromptTeachesTheReadSide:
    """The dump renders grounding; the prompt must also say what to DO with it.

    Measured in `claim2-weak-r6-grounding`: with the lane live, A2's `memory`
    column (fact present in the handed-over artifact) rose to 0.62 while `used`
    (reply actually referenced it) stayed at 0.12 — statistically the same as
    the prose-journal arm's 0.11. The graph held "60% of revenue" and the reply
    spoke about "the tension between moving decisively and protecting
    relationships". Storage was never the whole fix: a line nobody is told to
    read is a line nobody reads.

    These pin the read side against the same failure mode that hit the write
    side, where `TetradGrounding` existed and one of `anchor`'s two branches
    never called it. Both halves of the lane now have a caller-seam test.
    """

    def _prompt(self) -> str:
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        return system_prompt()

    def test_prompt_names_the_grounding_line(self):
        from dialectical_framework.graph.rendering import GROUNDING_PREFIX

        prompt = self._prompt()
        # The literal marker, so the prompt and the renderer agree on the token
        # the model is told to look for. `GROUNDING_PREFIX` ends in a space.
        assert GROUNDING_PREFIX.strip() in prompt

    def test_prompt_exempts_grounding_from_the_rephrase_licence(self):
        """The two rules collide unless the exception is stated.

        "How You Speak" licenses free rephrasing of graph text, which is right
        for a ~7-word pole and wrong for "60% of revenue": a reworded number is
        a lost number. Whichever How-You-Speak variant renders (scoped or not),
        it must carry the carve-out — otherwise the strongest instruction in
        the prompt tells the model to paraphrase away the only case-specific
        text it has.
        """
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        for prompt in (system_prompt(), system_prompt(scoped_nexus_hash="abc1234")):
            speak = prompt.split("## How You Speak", 1)[1].split("\n## ", 1)[0]
            assert "Grounded in:" in speak

    def test_prompt_tells_it_to_lead_with_particulars(self):
        """Presence is not use — the instruction must be to SPEAK them."""
        prompt = self._prompt()
        section = prompt.split("`Grounded in:`", 1)[1]
        assert "Use them." in section
        # The failure it exists to prevent: restating the tension's shape in
        # place of the person's facts.
        assert "reads as having been forgotten" in section

    def test_scoped_prompt_teaches_it_too(self):
        """Counsel mode is where a returning session's wobble actually lands."""
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        assert "Grounded in:" in system_prompt(scoped_nexus_hash="abc1234")
