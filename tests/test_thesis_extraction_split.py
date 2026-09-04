"""`ThesisExtraction`'s two halves are separately callable.

Steps 1-2 (`extract_candidates`) return candidate STRINGS and write nothing;
steps 3-4 (`classify_candidates`) write the graph. The split exists so a caller
sweeping a source too long for one prompt can gather candidates from every window
before deciding which deserve a `Statement` — sweeping with the whole `resolve()`
would commit a Statement plus a Rationale per candidate per window and lean on
deduplication to delete most of them again.

`resolve()` is the two in sequence and must behave exactly as it did when both
halves were inline, so these tests pin the seam from both sides.
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns import thesis_extraction as module
from dialectical_framework.concerns.thesis_extraction import (ContentItemDto,
                                                              ThesisExtraction)


@pytest.fixture
def cleanup_graph_db():
    """DB-free: the writing half is stubbed out."""
    yield


@pytest.fixture
def cleanup_test_graph_data():
    yield


class _FakeStatement:
    def __init__(self, text: str) -> None:
        self.text = text
        self.hash = f"h-{abs(hash(text)) % 10**7:07d}"


def _items(*texts: str) -> list[ContentItemDto]:
    return [ContentItemDto(content=t, content_type="claim") for t in texts]


def _stub_steps(
    monkeypatch,
    concern: ThesisExtraction,
    *,
    items: list[ContentItemDto],
    candidates: list[str],
) -> None:
    """Replace the two provider steps, leaving the plumbing under test."""

    async def fake_step1():
        return items

    async def fake_step2(content_items):
        return list(candidates)

    monkeypatch.setattr(concern, "_step1_extract_content", fake_step1)
    monkeypatch.setattr(concern, "_step2_identify_candidates", fake_step2)
    monkeypatch.setattr(concern, "_conversation", _NullConversation())


class _NullConversation:
    def set_system_prompt(self, prompt: str) -> None:
        pass


class TestExtractCandidatesWritesNothing:
    @pytest.mark.asyncio
    async def test_it_returns_strings_and_never_classifies(self, monkeypatch):
        concern = ThesisExtraction()
        _stub_steps(
            monkeypatch,
            concern,
            items=_items("centralization erodes trust"),
            candidates=["centralization erodes trust"],
        )

        classified: list[object] = []

        async def fail_classify(*args, **kwargs):  # pragma: no cover
            classified.append(args)
            raise AssertionError("extract_candidates must not classify")

        monkeypatch.setattr(concern, "classify_candidates", fail_classify)

        found = await concern.extract_candidates(text="a source", count=3)

        assert found == ["centralization erodes trust"]
        assert classified == []
        assert concern.report.artifacts["candidate_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_text_reaches_no_provider_at_all(self, monkeypatch):
        concern = ThesisExtraction()

        async def fail_step1():  # pragma: no cover
            raise AssertionError("no LLM call for empty text")

        monkeypatch.setattr(concern, "_step1_extract_content", fail_step1)

        assert await concern.extract_candidates(text="   ", count=3) == []
        assert concern.report.artifacts["thesis_hashes"] == []
        assert concern.report.ok is True

    @pytest.mark.asyncio
    async def test_zero_count_reaches_no_provider_either(self, monkeypatch):
        concern = ThesisExtraction()

        async def fail_step1():  # pragma: no cover
            raise AssertionError("no LLM call for count <= 0")

        monkeypatch.setattr(concern, "_step1_extract_content", fail_step1)

        assert await concern.extract_candidates(text="a source", count=0) == []

    @pytest.mark.asyncio
    async def test_the_gate_rejection_safety_net_moved_with_the_steps(
        self, monkeypatch
    ):
        """Step 1 found assertable content but the step-2 gate rejected all of
        it — a gate over-rejection, not genuinely thesis-free material. The
        fallback protects the sweep path too, since the sweep only ever calls
        this half."""
        concern = ThesisExtraction()
        _stub_steps(
            monkeypatch,
            concern,
            items=_items("openness invites drift", "openness invites drift", "x"),
            candidates=[],
        )

        found = await concern.extract_candidates(text="a source", count=3)

        # Deduplicated, order preserved, blanks dropped.
        assert found == ["openness invites drift", "x"]
        assert "gate rejected all items" in concern.report.summary

    @pytest.mark.asyncio
    async def test_nothing_found_at_all_is_reported_as_such(self, monkeypatch):
        concern = ThesisExtraction()
        _stub_steps(monkeypatch, concern, items=[], candidates=[])

        assert await concern.extract_candidates(text="a source", count=3) == []
        assert concern.report.artifacts["thesis_hashes"] == []
        assert "No thesis candidates found" in concern.report.summary


class TestResolveIsStillTheTwoInSequence:
    @pytest.mark.asyncio
    async def test_each_candidate_is_paired_with_the_source_it_came_from(
        self, monkeypatch
    ):
        concern = ThesisExtraction()
        _stub_steps(
            monkeypatch,
            concern,
            items=_items("a", "b"),
            candidates=["claim one", "claim two"],
        )
        seen: list[tuple] = []

        async def fake_classify(candidates, domain_hint=""):
            seen.append((list(candidates), domain_hint))
            return [_FakeStatement(text) for text, _ in candidates]

        monkeypatch.setattr(concern, "classify_candidates", fake_classify)

        components = await concern.resolve(
            text="the whole source", count=4, domain_hint="governance"
        )

        assert seen == [
            (
                [("claim one", "the whole source"), ("claim two", "the whole source")],
                "governance",
            )
        ]
        assert [c.text for c in components] == ["claim one", "claim two"]
        assert concern.report.artifacts["thesis_hashes"] == [
            c.hash for c in components
        ]
        assert "Extracted 2 thesis(es)" in concern.report.summary

    @pytest.mark.asyncio
    async def test_the_count_ceiling_of_four_still_holds(self, monkeypatch):
        concern = ThesisExtraction()
        _stub_steps(
            monkeypatch,
            concern,
            items=_items("a"),
            candidates=["c1", "c2", "c3", "c4", "c5", "c6"],
        )
        seen: list[list] = []

        async def fake_classify(candidates, domain_hint=""):
            seen.append(list(candidates))
            return [_FakeStatement(text) for text, _ in candidates]

        monkeypatch.setattr(concern, "classify_candidates", fake_classify)

        await concern.resolve(text="a source", count=10)

        assert [text for text, _ in seen[0]] == ["c1", "c2", "c3", "c4"]

    @pytest.mark.asyncio
    async def test_no_candidates_means_no_classification_call(self, monkeypatch):
        concern = ThesisExtraction()
        _stub_steps(monkeypatch, concern, items=[], candidates=[])

        async def fail_classify(*args, **kwargs):  # pragma: no cover
            raise AssertionError("nothing to classify")

        monkeypatch.setattr(concern, "classify_candidates", fail_classify)

        assert await concern.resolve(text="a source", count=3) == []


class TestClassifyCandidatesUsesEachPairsOwnContext:
    """`StatementClassification` truncates its source context to 2000 chars and
    uses it to pick the taxonomy domain, so one shared context string means a
    claim from page 300 is placed using page 1."""

    @pytest.mark.asyncio
    async def test_the_per_candidate_context_reaches_classification(
        self, monkeypatch
    ):
        calls: list[dict] = []

        class _FakeClassification:
            def __init__(self) -> None:
                from dialectical_framework.agents.execution_report import \
                    ExecutionReport

                self.report = ExecutionReport(tool="StatementClassification")

            async def resolve(self, statement, text, domain_hint=""):
                calls.append(
                    {
                        "statement": statement,
                        "text": text,
                        "domain_hint": domain_hint,
                    }
                )
                return object()

        monkeypatch.setattr(module, "StatementClassification", _FakeClassification)

        concern = ThesisExtraction()
        monkeypatch.setattr(
            concern,
            "_create_component",
            lambda result: _FakeStatement(f"stmt-{len(calls)}"),
        )

        await concern.classify_candidates(
            [("claim one", "window A"), ("claim two", "window B")],
            domain_hint="governance",
        )

        assert calls == [
            {
                "statement": "claim one",
                "text": "window A",
                "domain_hint": "governance",
            },
            {
                "statement": "claim two",
                "text": "window B",
                "domain_hint": "governance",
            },
        ]
