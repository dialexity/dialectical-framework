"""A digest failure must not cost the analysis, and must not be silent.

`ingest` writes a `SourceDigest` for the material it captures, then runs the
analysis. The digest is enrichment — the perspectives are built from full
content either way — so a failure there must be survivable. It was wrapped in

    except (ValueError, RuntimeError):
        pass

which was wrong twice over. Too narrow: those two cover only `SourceDigest`'s
own guards ("Input not found", "no resolvable content"), the least likely
failures at that point since the Input was created two lines earlier. A provider
error, a response-model validation error, or a URL fetch dying inside
`resolve_native` all escaped and aborted the whole tool. Too quiet: `pass` left
no trace, so a missing digest read as "not written yet" rather than "tried and
failed" — including to `input_context`, which then silently sends full content
where a digest was intended.

DB-free and LLM-free: the concerns and the pipeline are stubbed, because what is
under test is `ingest`'s composition of them.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.tools import ingest as ingest_mod
from dialectical_framework.agents.execution_report import ExecutionReport


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _FakeInput:
    hash = "a" * 64
    short_hash = "aaaaaaa"


class _FakeAddInput:
    def __init__(self) -> None:
        self.report = ExecutionReport(tool="add_input", summary="added")

    async def resolve(self, content: str):
        return _FakeInput()


class _FakePipeline:
    """Records that it ran; carries a real report so `str()` behaves."""

    instances: list["_FakePipeline"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.report = ExecutionReport(tool="ingest", summary="analysed")
        self.resolved = False
        _FakePipeline.instances.append(self)

    async def resolve(self):
        self.resolved = True
        return None


def _wire(monkeypatch, digest_resolve):
    _FakePipeline.instances = []

    class _FakeDigest:
        def __init__(self) -> None:
            self.report = ExecutionReport(tool="source_digest")

        async def resolve(self, input_hash: str, context: str = ""):
            return await digest_resolve(input_hash, context)

    monkeypatch.setattr(
        "dialectical_framework.concerns.add_input.AddInput", _FakeAddInput
    )
    monkeypatch.setattr(
        "dialectical_framework.concerns.source_digest.SourceDigest", _FakeDigest
    )
    monkeypatch.setattr(
        "dialectical_framework.agents.analyst.analyst.AnalysisPipeline", _FakePipeline
    )


class TestDigestFailureIsSurvivable:
    @pytest.mark.asyncio
    async def test_a_non_value_error_no_longer_aborts_the_tool(self, monkeypatch):
        """`TimeoutError` is neither ValueError nor RuntimeError.

        It stands in for the failures that actually happen here — provider
        errors, validation errors, a fetch timing out — none of which the old
        two-type except caught.
        """

        async def boom(input_hash, context):
            raise TimeoutError("provider timed out")

        _wire(monkeypatch, boom)

        out = await ingest_mod.ingest.fn(text="Some material to analyze.")

        assert _FakePipeline.instances, "the analysis never ran"
        assert _FakePipeline.instances[0].resolved is True
        assert "analysed" in out

    @pytest.mark.asyncio
    async def test_the_failure_is_reported_not_swallowed(self, monkeypatch):
        async def boom(input_hash, context):
            raise TimeoutError("provider timed out")

        _wire(monkeypatch, boom)

        await ingest_mod.ingest.fn(text="Some material to analyze.")
        note = _FakePipeline.instances[0].report.artifacts["digest"]

        assert note.startswith("failed softly")
        assert "TimeoutError" in note
        assert "provider timed out" in note

    @pytest.mark.asyncio
    async def test_the_note_names_no_tool_the_advisor_lacks(self, monkeypatch):
        """`ingest` is Advisor-only and the Advisor has no `digest_input`."""

        async def boom(input_hash, context):
            raise TimeoutError("provider timed out")

        _wire(monkeypatch, boom)

        await ingest_mod.ingest.fn(text="Some material to analyze.")
        note = _FakePipeline.instances[0].report.artifacts["digest"]

        assert "digest_input" not in note

    @pytest.mark.asyncio
    async def test_the_old_narrow_types_are_also_survivable(self, monkeypatch):
        """The two that WERE caught must keep being caught."""
        for error in (ValueError("Input not found"), RuntimeError("boom")):

            async def boom(input_hash, context, _e=error):
                raise _e

            _wire(monkeypatch, boom)
            await ingest_mod.ingest.fn(text="Some material to analyze.")

            assert _FakePipeline.instances[0].resolved is True
            note = _FakePipeline.instances[0].report.artifacts["digest"]
            assert note.startswith("failed softly")


class TestDigestSuccessIsReported:
    @pytest.mark.asyncio
    async def test_success_records_created(self, monkeypatch):
        async def fine(input_hash, context):
            return _FakeInput()

        _wire(monkeypatch, fine)

        await ingest_mod.ingest.fn(text="Some material to analyze.")

        assert _FakePipeline.instances[0].report.artifacts["digest"] == "created"

    @pytest.mark.asyncio
    async def test_no_text_means_no_digest_key(self, monkeypatch):
        """Nothing was captured, so there is nothing to say about a digest."""

        async def unreachable(input_hash, context):
            raise AssertionError("SourceDigest ran without new material")

        _wire(monkeypatch, unreachable)

        await ingest_mod.ingest.fn(input_hashes=["abc1234"])

        assert "digest" not in _FakePipeline.instances[0].report.artifacts
