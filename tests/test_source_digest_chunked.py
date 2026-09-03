"""A source too big for one prompt is READ IN PARTS, and every part is read.

The digest is what every downstream concern reasons from, so the failure mode
these tests exist to prevent is not an error — it is a digest that describes the
first few pages of a 400 KB document while presenting itself as the
understanding of the source. Nothing downstream can detect that, which is why
prompt-level coverage is asserted here and not merely inside `chunk_text`: a
rewiring that drops the last window would still pass the chunker's own tests.

Every LLM call is intercepted, so nothing here reaches a provider. The fake
facilitator records what each call SAW, which is the only way to ask the
questions that matter — did the whole document ever go out in one prompt, did
the reduce see the readings or the source, did each part know it was a part.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import pytest

from dialectical_framework.concerns import source_digest as source_digest_module
from dialectical_framework.concerns.source_digest import (COMBINE_SYSTEM_PROMPT,
                                                          PART_SYSTEM_PROMPT,
                                                          SYSTEM_PROMPT,
                                                          DigestDto,
                                                          SourceDigest)
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.chunking import CHUNK_SIZE


def _new_sid() -> str:
    import uuid

    return f"test-{uuid.uuid4().hex[:8]}"


def _document(chars: int) -> str:
    """Prose-shaped material with paragraph breaks, and a findable marker per page."""
    paragraphs = []
    i = 0
    while sum(len(p) for p in paragraphs) < chars:
        paragraphs.append(
            f"MARKER-{i}. "
            + ("The system exhibits a tension between speed and care. " * 16)
        )
        i += 1
    return "\n\n".join(paragraphs)


class _FakeFacilitator:
    """Stands in for `ConversationFacilitator`, recording what each call saw.

    Class-level `instances` is what lets a test count facilitators, which is the
    only observable difference between "a fresh conversation per part" and "one
    conversation accumulating every part" — the bug that would silently undo the
    whole point of chunking, since the last call would carry the document again.
    """

    instances: list[_FakeFacilitator] = []

    def __init__(self) -> None:
        self.system_prompt: str | None = None
        self.prompts: list = []
        _FakeFacilitator.instances.append(self)

    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt

    async def submit(self, *, response_model, user_content):
        self.prompts.append(user_content)
        # A reading derived from the part's own index, so the reduce prompt can be
        # checked for BOTH content and document order — `asyncio.gather` preserves
        # argument order regardless of completion order, and that is load-bearing
        # here: readings shuffled into completion order would hand the model a
        # document whose argument develops backwards.
        if isinstance(user_content, str):
            match = re.search(r'<source_part index="(\d+)"', user_content)
            if match:
                return DigestDto(
                    digest=f"READING-OF-PART-{match.group(1)}", reasoning="r"
                )
        return DigestDto(digest="THE-COMBINED-DIGEST", reasoning="r")


@pytest.fixture
def facilitators(monkeypatch):
    """Every facilitator the concern builds, in construction order."""
    _FakeFacilitator.instances = []
    monkeypatch.setattr(
        source_digest_module, "ConversationFacilitator", _FakeFacilitator
    )
    yield _FakeFacilitator.instances
    _FakeFacilitator.instances = []


def _part_prompts(facilitators) -> list[str]:
    return [
        p
        for f in facilitators
        for p in f.prompts
        if isinstance(p, str) and "<source_part" in p
    ]


def _windows(part_prompts: list[str]) -> list[str]:
    """The source material each part prompt carried, in document order."""
    windows = []
    for prompt in part_prompts:
        match = re.search(
            r'<source_part index="(\d+)" of="\d+">\n(.*)\n</source_part>',
            prompt,
            re.DOTALL,
        )
        assert match, "a part prompt did not carry a recognisable source window"
        windows.append((int(match.group(1)), match.group(2)))
    return [w for _, w in sorted(windows)]


class TestASourceThatFitsIsUnchanged:
    """The branch every existing caller stays on, and it must not move."""

    @pytest.mark.asyncio
    async def test_one_call_with_the_original_single_pass_prompt(self, facilitators):
        concern = SourceDigest()
        text = _document(5_000)

        digest = await concern._generate_digest(content=text)

        assert digest == "THE-COMBINED-DIGEST"
        assert len(facilitators) == 1, "a fitting source must not fan out"
        assert facilitators[0].system_prompt == SYSTEM_PROMPT
        prompt = facilitators[0].prompts[0]
        assert f"<source>\n{text}\n</source>" in prompt
        assert "<source_part" not in prompt

    @pytest.mark.asyncio
    async def test_no_chunk_count_is_reported(self, facilitators):
        """`chunks` in the report means "this was read in parts". Absent otherwise."""
        concern = SourceDigest()

        await concern._generate_digest(content=_document(5_000))

        assert "chunks" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_media_is_never_chunked(self, facilitators):
        """Chunking an image part is meaningless — media keeps the native pass."""
        from mirascope.llm import Image
        from mirascope.llm.content.image import Base64ImageSource

        concern = SourceDigest()
        # Larger than the window, to prove the branch is on TYPE and not on size.
        parts = [
            Image(
                source=Base64ImageSource(
                    type="base64_image_source",
                    data="x" * (CHUNK_SIZE * 2),
                    mime_type="image/png",
                )
            )
        ]

        await concern._generate_digest(content=parts)

        assert len(facilitators) == 1
        assert facilitators[0].system_prompt == SYSTEM_PROMPT
        user_content = facilitators[0].prompts[0]
        assert isinstance(user_content, list)
        assert any(isinstance(p, Image) for p in user_content)


class TestEveryPartIsRead:
    """Coverage at the prompt level: what actually went out to the model."""

    @pytest.mark.asyncio
    async def test_no_character_of_the_source_goes_unread(self, facilitators):
        text = _document(CHUNK_SIZE * 5)
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        windows = _windows(_part_prompts(facilitators))
        assert len(windows) > 1

        covered_to = 0
        for window in windows:
            found = text.find(window)
            assert found != -1, "a part prompt carried material not in the source"
            assert found <= covered_to, "a stretch of the source was never read"
            covered_to = max(covered_to, found + len(window))

        assert covered_to == len(text), "the tail of the source was never read"

    @pytest.mark.asyncio
    async def test_the_whole_document_never_goes_out_in_one_prompt(self, facilitators):
        text = _document(CHUNK_SIZE * 5)
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        every_prompt = [p for f in facilitators for p in f.prompts]
        assert all(isinstance(p, str) for p in every_prompt)
        for prompt in every_prompt:
            assert text not in prompt
        # Each part prompt is a window plus framing, not a fraction of a monolith.
        for window in _windows(_part_prompts(facilitators)):
            assert len(window) <= CHUNK_SIZE

    @pytest.mark.asyncio
    async def test_one_call_per_part_plus_one_to_combine(self, facilitators):
        from dialectical_framework.utils.chunking import chunk_text

        text = _document(CHUNK_SIZE * 3)
        expected_parts = len(chunk_text(text))
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        assert len(_part_prompts(facilitators)) == expected_parts
        total_calls = sum(len(f.prompts) for f in facilitators)
        assert total_calls == expected_parts + 1
        assert concern.report.artifacts["chunks"] == expected_parts


class TestPartsAreFreshConversations:
    @pytest.mark.asyncio
    async def test_each_part_gets_its_own_facilitator(self, facilitators):
        """One shared conversation would re-accumulate the document it just split."""
        text = _document(CHUNK_SIZE * 3)
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        part_facilitators = [f for f in facilitators if f is not concern._conversation]
        assert len(part_facilitators) == len(_part_prompts(facilitators))
        assert all(len(f.prompts) == 1 for f in part_facilitators)
        assert all(f.system_prompt == PART_SYSTEM_PROMPT for f in part_facilitators)

    @pytest.mark.asyncio
    async def test_the_concerns_own_conversation_only_reduces(self, facilitators):
        text = _document(CHUNK_SIZE * 3)
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        assert len(concern._conversation.prompts) == 1
        assert concern._conversation.system_prompt == COMBINE_SYSTEM_PROMPT
        assert "<source_part" not in concern._conversation.prompts[0]


class TestAPartKnowsItIsAPart:
    @pytest.mark.asyncio
    async def test_position_is_stated_in_the_instruction_and_on_the_tag(
        self, facilitators
    ):
        text = _document(CHUNK_SIZE * 3)
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        prompts = _part_prompts(facilitators)
        total = len(prompts)
        for prompt in prompts:
            match = re.search(r'<source_part index="(\d+)" of="(\d+)">', prompt)
            assert match
            index, stated_total = match.group(1), int(match.group(2))
            assert stated_total == total
            assert f"part {index} of {total}" in prompt
            assert "not the whole source" in prompt

    @pytest.mark.asyncio
    async def test_the_part_prompt_forbids_summarising_the_whole(self, facilitators):
        """A part with no frame writes "this document argues X" — and it survives."""
        concern = SourceDigest()

        await concern._generate_digest(content=_document(CHUNK_SIZE * 3))

        for prompt in _part_prompts(facilitators):
            assert "you have not seen it" in prompt


class TestTheReduceSeesReadingsNotTheSource:
    @pytest.mark.asyncio
    async def test_every_reading_reaches_the_combine_prompt_in_document_order(
        self, facilitators
    ):
        text = _document(CHUNK_SIZE * 4)
        concern = SourceDigest()

        digest = await concern._generate_digest(content=text)

        assert digest == "THE-COMBINED-DIGEST"
        combine_prompt = concern._conversation.prompts[0]
        total = len(_part_prompts(facilitators))
        positions = [
            combine_prompt.index(f"READING-OF-PART-{i}") for i in range(1, total + 1)
        ]
        assert positions == sorted(positions), "readings are out of document order"

    @pytest.mark.asyncio
    async def test_the_source_material_does_not_reach_the_combine_prompt(
        self, facilitators
    ):
        """Otherwise the reduce is the unbounded call, one step further along."""
        text = _document(CHUNK_SIZE * 4)
        concern = SourceDigest()

        await concern._generate_digest(content=text)

        combine_prompt = concern._conversation.prompts[0]
        # A marker from deep in the document: present in some part prompt, absent here.
        marker = "MARKER-" + str(text.count("MARKER-") - 2) + "."
        assert any(marker in p for p in _part_prompts(facilitators))
        assert marker not in combine_prompt
        assert len(combine_prompt) < CHUNK_SIZE


class TestTheFanOutIsBounded:
    """Width comes from a pasted file's size, so it cannot be left unbounded."""

    @pytest.mark.asyncio
    async def test_no_more_than_the_cap_are_in_flight_at_once(self, monkeypatch):
        import asyncio

        from dialectical_framework.concerns.source_digest import \
            MAX_CONCURRENT_PART_READINGS

        in_flight = 0
        peak = 0

        class _CountingFacilitator(_FakeFacilitator):
            async def submit(self, *, response_model, user_content):
                nonlocal in_flight, peak
                in_flight += 1
                peak = max(peak, in_flight)
                try:
                    # Yield control, so a genuinely unbounded gather would show it.
                    await asyncio.sleep(0.01)
                    return await super().submit(
                        response_model=response_model, user_content=user_content
                    )
                finally:
                    in_flight -= 1

        _FakeFacilitator.instances = []
        monkeypatch.setattr(
            source_digest_module, "ConversationFacilitator", _CountingFacilitator
        )
        try:
            concern = SourceDigest()
            # Comfortably more windows than the cap, or the assertion is vacuous.
            await concern._generate_digest(content=_document(CHUNK_SIZE * 10))

            assert (
                len(_part_prompts(_FakeFacilitator.instances))
                > MAX_CONCURRENT_PART_READINGS
            )
            assert peak <= MAX_CONCURRENT_PART_READINGS
            assert peak > 1, "the readings did not overlap at all"
        finally:
            _FakeFacilitator.instances = []


class TestRefinement:
    @pytest.mark.asyncio
    async def test_the_existing_digest_goes_to_the_reduce_not_to_the_parts(
        self, facilitators
    ):
        """Parts report what they contain; only the reduce owns the whole digest."""
        concern = SourceDigest()

        await concern._generate_digest(
            content=_document(CHUNK_SIZE * 3),
            existing_digest="THE-PRIOR-UNDERSTANDING",
            context="focus on regulatory tension",
        )

        combine_prompt = concern._conversation.prompts[0]
        assert "THE-PRIOR-UNDERSTANDING" in combine_prompt
        assert "Refine the existing digest" in combine_prompt
        assert all(
            "THE-PRIOR-UNDERSTANDING" not in p for p in _part_prompts(facilitators)
        )

    @pytest.mark.asyncio
    async def test_the_context_reaches_both_stages(self, facilitators):
        """A part that does not know the focus cannot preserve what matters for it."""
        concern = SourceDigest()

        await concern._generate_digest(
            content=_document(CHUNK_SIZE * 3),
            context="focus on regulatory tension",
        )

        assert all(
            "focus on regulatory tension" in p for p in _part_prompts(facilitators)
        )
        assert "focus on regulatory tension" in concern._conversation.prompts[0]


class TestThroughResolve:
    """One pass through the real entry point, so the wiring is not assumed."""

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_a_large_input_is_digested_in_parts_and_persisted(
        self, facilitators
    ):
        sid = _new_sid()
        with scope(sid):
            input_node = Input(content=_document(CHUNK_SIZE * 3))
            input_node.commit()

            concern = SourceDigest()
            result = await concern.resolve(input_hash=input_node.hash)

            assert result.digest == "THE-COMBINED-DIGEST"
            assert concern.report.ok is True
            assert "created" in concern.report.summary.lower()
            assert concern.report.artifacts["chunks"] > 1
            assert len(_part_prompts(facilitators)) > 1
