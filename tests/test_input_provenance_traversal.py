"""
Tests for reading the Input↔Statement provenance link.

An Input reaches its Statements two ways (see the diagram in `nodes/case.py`):

    Input -[:HAS_STATEMENT]-> Statement                          (direct shortcut)
    Input -[:DISTILLED_TO]-> Ideas -[:HAS_STATEMENT]-> Statement  (what extraction writes)

Readers that followed only the direct edge saw every analyzed Input as
"pending, not yet analyzed" forever, and the causality estimator grounded
itself in empty source text. These tests pin the union.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.orchestrator.tools.present_analysis import \
    PresentAnalysis
from dialectical_framework.concerns.causality.causality_estimator_balanced import \
    CausalityEstimatorBalanced
from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.scope_context import scope


def _new_case() -> Case:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case


def _add_input(case: Case, content: str) -> Input:
    input_node = Input(content=content)
    input_node.commit()
    case.inputs.connect(input_node)
    return input_node


def _distill(input_node: Input, *texts: str) -> Ideas:
    """Write the 2-hop path exactly as `AnchorTheses._create_ideas` does."""
    ideas = Ideas(intent="Extract theses")
    ideas.save()
    ideas.inputs.connect(input_node)
    for text in texts:
        statement = Statement(text=text, meaning="test")
        statement.commit()
        ideas.statements.connect(statement)
    ideas.commit()
    return ideas


class TestAnalyzedHashes:
    """InputRepository.analyzed_hashes follows both provenance paths."""

    def test_input_distilled_into_ideas_counts_as_analyzed(self):
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(case, "Remote work reshapes focus.")
            _distill(input_node, "Remote work improves focus")

            assert InputRepository().analyzed_hashes() == {input_node.hash}

    def test_direct_has_statement_edge_counts_as_analyzed(self):
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(case, "Direct extraction shortcut.")
            statement = Statement(text="A direct thesis", meaning="test")
            statement.commit()
            input_node.statements.connect(statement)

            assert InputRepository().analyzed_hashes() == {input_node.hash}

    def test_input_without_statements_is_absent(self):
        case = _new_case()
        with scope(case.sid):
            _add_input(case, "Captured but never processed.")

            assert InputRepository().analyzed_hashes() == set()

    def test_ideas_with_no_statements_does_not_count(self):
        """A HEAD Ideas container with nothing in it is not an analysis."""
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(case, "Distillation started, produced nothing.")
            ideas = Ideas(intent="Extract theses")
            ideas.save()
            ideas.inputs.connect(input_node)

            assert InputRepository().analyzed_hashes() == set()

    def test_is_scoped_to_the_current_case(self):
        other = _new_case()
        with scope(other.sid):
            other_input = _add_input(other, "Another case's material.")
            _distill(other_input, "Another case's thesis")

        case = _new_case()
        with scope(case.sid):
            mine = _add_input(case, "My material.")
            _distill(mine, "My thesis")

            assert InputRepository().analyzed_hashes() == {mine.hash}

    def test_no_scope_returns_empty(self):
        assert InputRepository().analyzed_hashes() == set()


class TestFindByStatementHashes:
    """InputRepository.find_by_statement_hashes is the reverse traversal."""

    def test_resolves_source_through_ideas(self):
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(case, "Material behind the thesis.")
            ideas = _distill(input_node, "A distilled thesis")
            statement = next(s for s, _ in ideas.statements.all())

            found = InputRepository().find_by_statement_hashes([statement.hash])

            assert [i.hash for i in found[statement.hash]] == [input_node.hash]

    def test_resolves_source_through_direct_edge(self):
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(case, "Material with a direct edge.")
            statement = Statement(text="A direct thesis", meaning="test")
            statement.commit()
            input_node.statements.connect(statement)

            found = InputRepository().find_by_statement_hashes([statement.hash])

            assert [i.hash for i in found[statement.hash]] == [input_node.hash]

    def test_input_reachable_both_ways_is_returned_once(self):
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(case, "Material linked twice.")
            statement = Statement(text="A doubly-linked thesis", meaning="test")
            statement.commit()
            input_node.statements.connect(statement)

            ideas = Ideas(intent="Extract theses")
            ideas.save()
            ideas.inputs.connect(input_node)
            ideas.statements.connect(statement)
            ideas.commit()

            found = InputRepository().find_by_statement_hashes([statement.hash])

            assert [i.hash for i in found[statement.hash]] == [input_node.hash]

    def test_statement_without_a_source_is_absent(self):
        case = _new_case()
        with scope(case.sid):
            statement = Statement(text="An ungrounded thesis", meaning="test")
            statement.commit()

            assert InputRepository().find_by_statement_hashes([statement.hash]) == {}

    def test_does_not_cross_scopes(self):
        other = _new_case()
        with scope(other.sid):
            other_input = _add_input(other, "Another case's material.")
            other_ideas = _distill(other_input, "Another case's thesis")
            foreign = next(s for s, _ in other_ideas.statements.all())

        case = _new_case()
        with scope(case.sid):
            assert InputRepository().find_by_statement_hashes([foreign.hash]) == {}

    def test_empty_arguments_short_circuit(self):
        case = _new_case()
        with scope(case.sid):
            assert InputRepository().find_by_statement_hashes([]) == {}


class TestPendingRendering:
    """The two context renderers stop calling analyzed inputs pending."""

    def test_dump_inputs_lists_a_distilled_input_as_used(self):
        case = _new_case()
        with scope(case.sid):
            analyzed = _add_input(case, "Material that was analyzed.")
            _distill(analyzed, "An extracted thesis")
            untouched = _add_input(case, "Material still waiting.")

            rendered = DialecticalContext._dump_inputs()

        assert rendered is not None
        used_line = next(l for l in rendered.split("\n") if l.startswith("Inputs:"))
        pending_line = next(l for l in rendered.split("\n") if l.startswith("Pending"))
        assert analyzed.short_hash in used_line
        assert analyzed.short_hash not in pending_line
        assert untouched.short_hash in pending_line

    def test_present_analysis_counts_only_unanalyzed_as_pending(self):
        case = _new_case()
        with scope(case.sid):
            analyzed = _add_input(case, "Material that was analyzed.")
            _distill(analyzed, "An extracted thesis")
            untouched = _add_input(case, "Material still waiting.")

            repo = InputRepository()
            rendered = PresentAnalysis._format_inputs(
                repo.get_all(), repo.analyzed_hashes()
            )

        assert "2 total, 1 pending" in rendered
        assert untouched.short_hash in rendered
        assert analyzed.short_hash not in rendered


class TestCausalitySourceText:
    """The balanced estimator grounds causality in the material it came from."""

    @pytest.mark.asyncio
    async def test_source_text_resolves_through_ideas(self):
        case = _new_case()
        with scope(case.sid):
            input_node = _add_input(
                case, "Deadlines compress attention, which compounds fatigue."
            )
            ideas = _distill(input_node, "Deadlines compress attention")
            statement = next(s for s, _ in ideas.statements.all())

            text = await CausalityEstimatorBalanced()._get_source_text([[statement]])

        assert "Deadlines compress attention, which compounds fatigue." in text

    @pytest.mark.asyncio
    async def test_source_text_is_empty_without_a_source(self):
        case = _new_case()
        with scope(case.sid):
            statement = Statement(text="An ungrounded thesis", meaning="test")
            statement.commit()

            text = await CausalityEstimatorBalanced()._get_source_text([[statement]])

        assert text == ""
