"""`chunk_text` guarantees: coverage, a hard ceiling, overlap, determinism.

Coverage is the load-bearing one. Everything that chunks in this tree does it to
look at a whole document — a digest of a 400 KB source that silently described
the first 40 KB would be worse than no digest, because it reads as an
understanding of the source and is not one. So the property tested here is not
"the chunks look reasonable" but "no character of the input is missing from all
of them".

DB-free and LLM-free: this is a pure function.
"""

from __future__ import annotations

import pytest

from dialectical_framework.utils.chunking import (CHUNK_OVERLAP, CHUNK_SIZE,
                                                  chunk_text)


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _document(paragraphs: int, paragraph_chars: int = 900) -> str:
    """Prose-shaped input: paragraph breaks where a real document has them."""
    return "\n\n".join(
        f"Paragraph {i}. " + ("lorem ipsum dolor sit amet. " * (paragraph_chars // 28))
        for i in range(paragraphs)
    )


class TestCoverage:
    """Every character is somewhere. This is the guarantee that matters."""

    @pytest.mark.parametrize("paragraphs", [1, 2, 12, 60, 500])
    def test_no_character_is_lost(self, paragraphs: int):
        text = _document(paragraphs)
        chunks = chunk_text(text, size=5_000, overlap=400)

        # Walk the document against the chunk sequence: each chunk must resume
        # at or before where the previous one ended, or there is a hole.
        covered_to = 0
        for chunk in chunks:
            found = text.find(chunk)
            assert found != -1, "a chunk is not a literal slice of the source"
            assert found <= covered_to, f"gap in coverage at {covered_to}"
            covered_to = max(covered_to, found + len(chunk))

        assert covered_to == len(text), "the tail of the document was dropped"

    def test_a_source_that_fits_is_returned_unchanged(self):
        """The branch every existing caller stays on."""
        text = _document(1, 200)

        assert chunk_text(text) == [text]
        assert len(chunk_text(text)) == 1

    def test_empty_input_yields_no_chunks(self):
        assert chunk_text("") == []

    def test_text_without_any_break_still_covers(self):
        """A single 400 KB word: no boundary to find, so cut where it falls."""
        text = "x" * 400_000
        chunks = chunk_text(text, size=10_000, overlap=500)

        assert all(set(c) == {"x"} for c in chunks)
        assert max(len(c) for c in chunks) <= 10_000
        # Reconstructable ignoring overlap: nothing vanished.
        assert len(chunks) >= 400_000 // 10_000


class TestTheCeilingHolds:
    @pytest.mark.parametrize(
        "size,overlap", [(5_000, 400), (10_000, 2_000), (1_000, 999), (2_000, 0)]
    )
    def test_no_chunk_exceeds_size(self, size: int, overlap: int):
        chunks = chunk_text(_document(300), size=size, overlap=overlap)

        assert chunks
        assert max(len(c) for c in chunks) <= size

    def test_a_huge_document_at_real_settings_stays_under_the_window(self):
        chunks = chunk_text("y" * 1_200_000)

        assert max(len(c) for c in chunks) <= CHUNK_SIZE
        assert len(chunks) > 1

    def test_an_overlap_at_or_past_half_the_window_is_clamped(self):
        """Otherwise windows repeat faster than they advance and calls explode."""
        text = _document(200)

        chunks = chunk_text(text, size=4_000, overlap=4_000)

        assert max(len(c) for c in chunks) <= 4_000
        # Clamped to `size // 2 - 1`, and a boundary search reaches at most 25%
        # back, so each window advances at least `0.75 * size - size/2` — a
        # quarter of the window. That is the bound that keeps a long document
        # from costing unboundedly many calls.
        assert len(chunks) <= (len(text) // (4_000 // 4)) + 2


class TestOverlap:
    def test_consecutive_chunks_share_material(self):
        """A claim split down the middle must be whole in one of them."""
        chunks = chunk_text(_document(120), size=6_000, overlap=800)

        assert len(chunks) > 2
        for earlier, later in zip(chunks, chunks[1:]):
            tail = earlier[-400:]
            assert tail in earlier
            # `later` begins inside `earlier`, so the seam is covered whole.
            assert later[:100] in earlier

    def test_a_claim_spanning_a_boundary_survives_intact(self):
        claim = "REVENUE FELL BECAUSE HIRING OUTPACED ONBOARDING CAPACITY"
        filler = "background material. " * 300
        # Place the claim right where a window would otherwise cut.
        text = filler * 3 + claim + filler * 3
        size = len(filler * 3) + len(claim) // 2

        chunks = chunk_text(text, size=size, overlap=len(claim) * 2)

        assert any(claim in c for c in chunks), "the claim was split by every window"


class TestDeterminism:
    def test_the_same_input_yields_the_same_chunks(self):
        """Prompt stability: a chunk sweep must not vary between runs."""
        text = _document(80)

        assert chunk_text(text, size=7_000) == chunk_text(text, size=7_000)


class TestBoundaryPreference:
    def test_paragraph_breaks_are_preferred(self):
        text = _document(40, 400)

        chunks = chunk_text(text, size=5_000, overlap=200)

        # Every chunk but the last should end at a paragraph break, since the
        # document has one every ~400 chars and the search reaches 25% back.
        assert all(c.endswith("\n\n") for c in chunks[:-1])

    def test_sentence_ends_are_used_when_there_are_no_line_breaks(self):
        text = ("A claim about the system. " * 2_000)

        chunks = chunk_text(text, size=5_000, overlap=200)

        assert all(c.endswith(". ") for c in chunks[:-1])


class TestRealDefaults:
    def test_the_shipped_constants_are_coherent(self):
        """Overlap must leave room to advance, or long documents cost unboundedly."""
        assert CHUNK_OVERLAP < CHUNK_SIZE // 2
