"""The source listing: a stable order, and identifiers without the material.

Two defects in one query. `InputRepository.get_all()` had no `ORDER BY`, so the
list `input_context` walks came back in whatever order Memgraph chose — the same
graph rendering a different prompt run to run, which costs prompt-cache hits and
makes a bench arm irreproducible for nothing. And the `# Sources` line of the
context dump, which renders seven characters per source and no text at all, was
getting there through `get_all()` — shipping every source's full `content` to
print its hash: 34 ms for three 400 KB inputs, 113 ms for ten, against a flat
~2-3 ms for the projection (`tests/probe_source_listing_cost.py`), on a dump
that fires on most turns.

Order is rendering only: `_allocate` is order-independent by construction, so
nothing about how the budget is shared moves with it.
"""

from __future__ import annotations

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
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


class TestListingOrder:
    def test_oldest_first(self):
        case = _new_case()
        with scope(case.sid):
            first = _add_input(case, "Captured first.")
            second = _add_input(case, "Captured second.")
            third = _add_input(case, "Captured third.")

            assert [i.hash for i in InputRepository().get_all()] == [
                first.hash,
                second.hash,
                third.hash,
            ]

    def test_the_projection_agrees_with_the_full_read(self):
        """Two queries, one contract — they must not drift apart."""
        case = _new_case()
        with scope(case.sid):
            for text in ("First.", "Second.", "Third."):
                _add_input(case, text)

            repo = InputRepository()
            assert repo.all_hashes() == [i.hash for i in repo.get_all()]

    def test_repeated_reads_agree(self):
        """The property the prompt cache needs: same graph, same string."""
        case = _new_case()
        with scope(case.sid):
            for text in ("First.", "Second.", "Third.", "Fourth."):
                _add_input(case, text)

            repo = InputRepository()
            assert repo.all_hashes() == repo.all_hashes()
            assert DialecticalContext._dump_inputs() == (
                DialecticalContext._dump_inputs()
            )


class TestProjectionScoping:
    """`all_hashes` inherits `get_all`'s guards — it is the same query."""

    def test_is_scoped_to_the_current_case(self):
        mine = _new_case()
        theirs = _new_case()
        with scope(theirs.sid):
            _add_input(theirs, "Somebody else's material.")
        with scope(mine.sid):
            ours = _add_input(mine, "Our material.")

            assert InputRepository().all_hashes() == [ours.hash]

    def test_no_scope_returns_empty(self):
        assert InputRepository().all_hashes() == []

    def test_uncommitted_inputs_are_excluded(self):
        """The committed-only rule: `hash IS NOT NULL` on every listing query."""
        case = _new_case()
        with scope(case.sid):
            committed = _add_input(case, "Committed material.")
            draft = Input(content="Still being built.")
            draft.save()

            hashes = InputRepository().all_hashes()

            assert hashes == [committed.hash]
            assert draft.hash is None


class TestTheDumpShipsNoMaterial:
    def test_source_text_never_reaches_the_sources_line(self):
        """It renders identifiers; the text costs milliseconds and says nothing.

        Behavioural rather than a call-count assertion on purpose — what must
        stay true is that no source content is in the string, however the
        renderer gets its hashes.
        """
        case = _new_case()
        marker = "UNMISTAKABLE-SOURCE-BODY"
        with scope(case.sid):
            node = _add_input(case, f"{marker} and a good deal more besides.")

            rendered = DialecticalContext._dump_inputs()

        assert rendered is not None
        assert node.hash[:7] in rendered
        assert marker not in rendered

    def test_an_empty_scope_renders_nothing(self):
        case = _new_case()
        with scope(case.sid):
            assert DialecticalContext._dump_inputs() is None
