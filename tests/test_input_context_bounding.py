"""`input_context` is bounded, shares its budget fairly, and says when it cut.

It used to render every Input in scope at full length, falling back to entire
raw content for any Input whose digest was not written. Three pasted ~400 KB
files rendered 1.22 MB — ~300k tokens (`tests/probe_input_text_cost.py`) —
into concern prompts of which five never truncate what they are handed. That
is a context-limit failure or a ruinous bill, once per polarity.

Bounding alone is not enough, twice over: a per-Input cap still grows with the
number of Inputs, and a silent cut reads as a document that simply ended, so
the model reasons confidently from a fragment. Hence water-filling plus
`shown`/`of` signalling.

The coverage half is here too — "whoever adds the input, digests it" was a
convention that only `ingest` kept.
"""

from __future__ import annotations

import re

import pytest

from dialectical_framework.concerns.source_digest import ensure_digest
from dialectical_framework.utils.input_context import (
    INPUT_CONTEXT_BUDGET,
    _allocate,
    input_context,
)


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _FakeInput:
    def __init__(self, hash_: str, content: str = "", digest: str | None = None):
        self.hash = hash_
        self.content = content
        self.digest = digest


class _FakeResolver:
    """Records what it was asked to resolve, so digest-preference is checkable."""

    def __init__(self) -> None:
        self.resolved: list[str] = []

    async def resolve(self, input_node) -> str:
        self.resolved.append(input_node.hash)
        return input_node.content


def _shown(rendered: str) -> list[int]:
    """The `shown` figures the rendering advertises, in order."""
    return [int(n) for n in re.findall(r'shown="(\d+)"', rendered)]


def _bodies(rendered: str) -> list[str]:
    return re.findall(r">\n(.*?)\n</Input>", rendered, flags=re.DOTALL)


class TestAllocation:
    """Water-filling: promise everyone a share, re-share what is handed back."""

    def test_everything_fits(self):
        assert _allocate([100, 200, 300], budget=10_000) == [100, 200, 300]

    def test_a_small_source_is_not_crowded_out_by_a_huge_one(self):
        """The whole reason the budget is shared rather than capped per input."""
        small, huge = _allocate([500, 1_000_000], budget=10_000)

        assert small == 500, "the small source was cut to make room for the huge one"
        assert huge == 9_500, "the huge source did not take the released remainder"

    def test_sources_that_all_want_more_split_evenly(self):
        assert _allocate([50_000, 50_000, 50_000], budget=9_000) == [3_000] * 3

    def test_release_cascades(self):
        """Releasing raises the share, which can satisfy the next source up.

        1000/4 = 250 satisfies only the 100. Re-sharing 900 over 3 gives 300,
        which then satisfies the 300 as well — a single pass would have cut it.
        """
        assert _allocate([100, 300, 5_000, 5_000], budget=1_000) == [100, 300, 300, 300]

    def test_never_exceeds_the_budget(self):
        for lengths in ([1], [10_000] * 7, [1, 2, 999_999], [500] * 40):
            assert sum(_allocate(lengths, budget=10_000)) <= 10_000

    def test_a_share_too_small_to_be_worth_showing_is_zero(self):
        """Two sentences of a 400 KB document is a misleading fragment."""
        allocations = _allocate([100_000] * 100, budget=10_000)

        assert allocations == [0] * 100


class TestRenderingIsBounded:
    @pytest.mark.asyncio
    async def test_a_huge_undigested_source_no_longer_renders_whole(self):
        resolver = _FakeResolver()
        inputs = [_FakeInput("a" * 64, content="x" * 400_000)]

        rendered = await input_context(inputs, resolver)

        assert len(rendered) < INPUT_CONTEXT_BUDGET + 500, "tag overhead only"
        assert "x" * 400_000 not in rendered

    @pytest.mark.asyncio
    async def test_the_budget_holds_across_many_sources(self):
        """The failure a per-input cap would not have caught."""
        resolver = _FakeResolver()
        inputs = [_FakeInput(f"{i:064d}", content="y" * 100_000) for i in range(30)]

        rendered = await input_context(inputs, resolver)

        assert sum(_shown(rendered)) <= INPUT_CONTEXT_BUDGET


class TestTheCutAnnouncesItself:
    @pytest.mark.asyncio
    async def test_a_cut_source_carries_shown_of_and_a_marker(self):
        resolver = _FakeResolver()
        inputs = [_FakeInput("a" * 64, content="x" * 400_000)]

        rendered = await input_context(inputs, resolver, budget=1_000)

        assert 'shown="1000"' in rendered
        assert 'of="400000"' in rendered
        assert 'truncated="true"' in rendered
        assert _bodies(rendered) == ["x" * 1_000 + "..."], "the cut is unannounced"

    @pytest.mark.asyncio
    async def test_an_uncut_source_is_rendered_exactly_as_before(self):
        """Backward compatibility: no attributes appear when nothing was cut."""
        resolver = _FakeResolver()
        inputs = [_FakeInput("a" * 64, content="short material")]

        rendered = await input_context(inputs, resolver)

        assert rendered == f'<Input id="{"a" * 64}">\nshort material\n</Input>'

    @pytest.mark.asyncio
    async def test_a_source_squeezed_to_nothing_is_still_named(self):
        """"There is a third source you saw none of" is its own fact."""
        resolver = _FakeResolver()
        inputs = [_FakeInput(f"{i:064d}", content="z" * 100_000) for i in range(100)]

        rendered = await input_context(inputs, resolver, budget=1_000)

        assert rendered.count("<Input ") == 100
        assert set(_shown(rendered)) == {0}
        assert _bodies(rendered) == []

    @pytest.mark.asyncio
    async def test_no_tool_is_offered_as_an_off_ramp(self):
        """This string goes to concern prompts, whose model has no tools."""
        resolver = _FakeResolver()
        inputs = [_FakeInput("a" * 64, content="x" * 400_000)]

        rendered = await input_context(inputs, resolver, budget=1_000)

        for tool in ("read_input", "read_digest", "digest_input", "inspect_node"):
            assert tool not in rendered


class TestUnchangedBehaviour:
    """Bounding must not have moved anything else."""

    @pytest.mark.asyncio
    async def test_digest_is_preferred_and_content_is_not_resolved(self):
        resolver = _FakeResolver()
        inputs = [_FakeInput("a" * 64, content="the full source", digest="a digest")]

        rendered = await input_context(inputs, resolver)

        assert "a digest" in rendered
        assert "the full source" not in rendered
        assert resolver.resolved == [], "resolved content despite having a digest"

    @pytest.mark.asyncio
    async def test_no_inputs_renders_empty(self):
        assert await input_context([], _FakeResolver()) == ""

    @pytest.mark.asyncio
    async def test_contentless_inputs_are_skipped_not_named(self):
        resolver = _FakeResolver()
        inputs = [_FakeInput("a" * 64, content=""), _FakeInput("b" * 64, content="kept")]

        rendered = await input_context(inputs, resolver)

        assert rendered == f'<Input id="{"b" * 64}">\nkept\n</Input>'


def _wire_digest(monkeypatch, stored_digest, resolve=None):
    """Stub the STORED node and the concern.

    `ensure_digest` reads the digest off the stored node rather than off the
    object it was handed, so the lookup is what these tests have to control.
    """
    calls: list[str] = []

    class _Repo:
        def find_by_hash(self, hash_, node_type=None):
            return _FakeInput(hash_, digest=stored_digest)

    class _Digest:
        async def resolve(self, input_hash, context=""):
            calls.append(context)
            if resolve is not None:
                return resolve()
            return None

    monkeypatch.setattr(
        "dialectical_framework.concerns.source_digest.NodeRepository", _Repo
    )
    monkeypatch.setattr(
        "dialectical_framework.concerns.source_digest.SourceDigest", _Digest
    )
    return calls


class TestEnsureDigestGapFilling:
    """The coverage half: never pay twice, always fill a gap, never raise."""

    @pytest.mark.asyncio
    async def test_an_existing_digest_costs_no_call(self, monkeypatch):
        calls = _wire_digest(monkeypatch, stored_digest="already understood")

        note = await ensure_digest("a" * 64)

        assert note == "already present"
        assert calls == [], "spent a provider call on work already done"

    @pytest.mark.asyncio
    async def test_the_stored_digest_decides_not_the_callers_object(
        self, monkeypatch
    ):
        """The trap this signature exists for.

        `AddInput` builds a fresh `Input(content=...)` every time, and on a
        dedup hit `commit()` copies only `_id` off the stored node — so the
        object it returns reports `digest=None` for material digested an hour
        ago. Deciding from it re-digested on every capture.
        """
        calls = _wire_digest(monkeypatch, stored_digest="written an hour ago")

        assert await ensure_digest("a" * 64) == "already present"
        assert calls == []

    @pytest.mark.asyncio
    async def test_refresh_spends_the_call_on_purpose(self, monkeypatch):
        """`ingest` has the user's intent, which is what refining is for."""
        calls = _wire_digest(monkeypatch, stored_digest="old")

        note = await ensure_digest(
            "a" * 64, context="focus on runway", refresh=True
        )

        assert note == "refreshed"
        assert calls == ["focus on runway"]

    @pytest.mark.asyncio
    async def test_a_missing_digest_is_filled(self, monkeypatch):
        calls = _wire_digest(monkeypatch, stored_digest=None)

        assert await ensure_digest("a" * 64) == "created"
        assert calls == [""]

    @pytest.mark.asyncio
    async def test_failure_is_survivable_and_named(self, monkeypatch):
        def boom():
            raise TimeoutError("provider timed out")

        _wire_digest(monkeypatch, stored_digest=None, resolve=boom)

        note = await ensure_digest("a" * 64)

        assert note.startswith("failed softly")
        assert "TimeoutError" in note and "provider timed out" in note

    @pytest.mark.asyncio
    async def test_an_unknown_hash_does_not_raise(self, monkeypatch):
        """A lookup miss is a gap to fill, not a crash on the capture path."""

        class _Repo:
            def find_by_hash(self, hash_, node_type=None):
                return None

        class _Digest:
            async def resolve(self, input_hash, context=""):
                raise ValueError(f"Input not found: {input_hash}")

        monkeypatch.setattr(
            "dialectical_framework.concerns.source_digest.NodeRepository", _Repo
        )
        monkeypatch.setattr(
            "dialectical_framework.concerns.source_digest.SourceDigest", _Digest
        )

        assert (await ensure_digest("f" * 64)).startswith("failed softly")
