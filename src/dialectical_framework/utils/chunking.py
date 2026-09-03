"""Split a long source into windows that fit in one prompt.

The shared substrate under every "the document is too big for this call" problem
in the tree, and there were three of them: `SourceDigest` interpolates the whole
resolved source inline, `SurfaceTheses` concatenates every Input's full content
and hands it to a 3-hop extraction that retries up to three times, and
`input_context` used to render everything (bounded since `INPUT_CONTEXT_BUDGET`).

The three want the chunks for different reasons, which is why this module knows
about none of them:

- **Digestion and extraction want COVERAGE.** Every part must be looked at, or
  the understanding is of the first N pages and says otherwise. That is a sweep
  over all chunks plus a merge, not a selection.
- **Grounding wants RELEVANCE** — the passages bearing on one pole. That is a
  selection, and a retrieval index is the right instrument for it — but that index belongs to the APPLICATION,
  served through `InputResolver` (whose docstring already names `Ideas.intent` as the relevance hint). The
  framework grows no embeddings: grounding reads `Input.digest`, which is already a semantic compression built by
  sweeping for coverage.

Retrieval cannot do coverage: extraction has no query to retrieve against, since
the theses are the thing being looked for, so top-k against the intent string
would systematically return what the intent already anticipated and miss the
tensions nobody thought to ask about. Which is the whole job.

Boundaries are sought backwards from the window edge, preferring a paragraph
break, then a line break, then a sentence end. A chunk that starts mid-sentence
costs the model the beginning of a claim; the cost of the search is nothing.

Windows OVERLAP because the interesting material sits at boundaries as often as
anywhere else: a tension stated across two paragraphs, split down the middle, is
invisible to both halves. Overlap makes it whole in at least one chunk. It also
means the chunks are not a partition — `"".join(chunks) != text`, deliberately —
so nothing downstream may reassemble them and call the result the source.
"""

from __future__ import annotations

#: Characters per window (~10k tokens). Big enough that a chunk is a few pages
#: and a claim's context travels with it; small enough that a chunk plus its
#: instructions plus the model's own reasoning fit any provider the tree
#: supports, with room for the 3-hop extraction conversation to replay it.
#: A module constant rather than a setting, per "Policy is not config": no
#: deployment has a reason to pick a different number, and the cost of getting
#: it wrong is paid in reasoning quality, not in configuration.
CHUNK_SIZE = 40_000

#: Characters each window shares with the previous one (~500 tokens): a
#: paragraph or two, enough that a claim spanning the seam is whole somewhere.
CHUNK_OVERLAP = 2_000

#: Boundaries to prefer, best first. Searched backwards from the window edge.
_BREAKS = ("\n\n", "\n", ". ")

#: How far back a boundary search may reach, as a fraction of the window. Past
#: this a "nice" break is not worth the shrunken chunk it buys, so the window
#: is cut where it falls.
_MAX_BREAK_SEARCH = 0.25


def _best_break(text: str, start: int, end: int) -> int:
    """Index to cut at, at or before `end`, preferring a natural boundary."""
    floor = end - int((end - start) * _MAX_BREAK_SEARCH)
    for token in _BREAKS:
        found = text.rfind(token, floor, end)
        if found != -1:
            return found + len(token)
    return end


def chunk_text(
    text: str,
    *,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split `text` into overlapping windows of at most `size` characters.

    A source that already fits comes back as a single chunk holding the text
    unchanged, so callers can branch on `len(chunks) == 1` to keep their
    existing single-pass path byte-for-byte identical.

    Guarantees, all pinned in `tests/test_chunking.py`:
      - every character of `text` appears in at least one chunk (coverage)
      - no chunk exceeds `size`
      - consecutive chunks overlap while text remains
      - the same input yields the same chunks (prompt stability)

    Args:
        text: The resolved source. Not media — chunking text is meaningless for
            an image or a PDF part, and `SourceDigest` keeps those on the single
            native-content pass.
        size: Window size in characters.
        overlap: Characters shared with the previous window. Clamped below half
            of `size`, because at or past half the windows stop advancing faster
            than they repeat and a long document costs unboundedly more calls.

    Returns:
        The windows, in document order. `[]` only for empty input.
    """
    if not text:
        return []
    if len(text) <= size:
        return [text]

    overlap = max(0, min(overlap, size // 2 - 1))

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))

        if end < len(text):
            end = _best_break(text, start, end)
            # A tail shorter than the overlap would be a chunk made almost
            # entirely of material the previous one already carried, so absorb
            # it — but only while the ceiling holds. Absorbing unconditionally
            # is how the first draft of this produced chunks 40% over `size`,
            # which is the one thing the whole module exists to prevent.
            if 0 < len(text) - end <= overlap and len(text) - start <= size:
                end = len(text)

        chunks.append(text[start:end])

        if end >= len(text):
            break

        # `max(..., start + 1)` is a liveness guard, not decoration: a
        # pathological `_best_break` result at or before `start + overlap`
        # would otherwise leave `start` where it was and loop forever.
        start = max(end - overlap, start + 1)

    return chunks
