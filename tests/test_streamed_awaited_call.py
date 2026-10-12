"""
The awaited call sent as a stream (`Settings.llm_stream_awaited_calls`).

A non-streamed call's body arrives whole, so the read timeout is a ceiling on
the generation and one value had to serve a few-word DTO and a whole draw. The
first app measured stalls at ~6% per call whatever that value was (20s -> 10s),
so they are hangs, not long generations. Streamed, the call is policed by
silence: the read timeout up to the first content, `_STREAM_GAP_TIMEOUT_S`
after it, and above both the response must OPEN within
`_STREAM_HEADERS_TIMEOUT_S` — where every measured hang was (the promise run,
2026-10-12: 43 -> 51 cards, 9 -> 0 past the deadline). These tests pin the
policing and that the result is the same assembled `Message`.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dialectical_framework.utils import bedrock_provider
from dialectical_framework.utils.bedrock_provider import (
    StreamReadTimeout,
    _stream_to_message,
)
from dialectical_framework.utils.use_brain import _is_stall_error


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


FINAL = object()


def ev(kind: str, delta: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(type=kind, delta=SimpleNamespace(type=delta))


class FakeStream:
    def __init__(self, script: list[tuple[float, SimpleNamespace]]) -> None:
        self._script = script

    async def _gen(self):
        for pause, event in self._script:
            await asyncio.sleep(pause)
            yield event

    def __aiter__(self):
        return self._gen()

    async def get_final_message(self):
        return FINAL


class FakeManager:
    def __init__(self, script, opens_after: float = 0.0) -> None:
        self.stream = FakeStream(script)
        self.exited_with = "never"
        self._opens_after = opens_after

    async def __aenter__(self):
        await asyncio.sleep(self._opens_after)
        return self.stream

    async def __aexit__(self, exc_type, exc, tb):
        self.exited_with = exc_type


@pytest.fixture
def short_gap(monkeypatch):
    monkeypatch.setattr(bedrock_provider, "_STREAM_GAP_TIMEOUT_S", 0.05)
    monkeypatch.setattr(bedrock_provider, "_STREAM_HEADERS_TIMEOUT_S", 0.1)


TEXT = ev("content_block_delta", "text_delta")
THINKING = ev("content_block_delta", "thinking_delta")


class TestTheStreamIsPolicedBySilence:
    async def test_a_flowing_stream_returns_the_assembled_message(self, short_gap):
        manager = FakeManager([(0, ev("message_start")), (0.01, TEXT), (0.01, TEXT)])
        assert await _stream_to_message(manager, "m", 1.0) is FINAL
        assert manager.exited_with is None

    async def test_a_gap_after_content_is_a_stall(self, short_gap):
        manager = FakeManager([(0, TEXT), (0.5, TEXT)])
        with pytest.raises(StreamReadTimeout, match="mid-content") as caught:
            await _stream_to_message(manager, "m", 1.0)
        assert _is_stall_error(caught.value), "the ladder must re-ask it once"
        assert manager.exited_with is StreamReadTimeout

    async def test_before_content_the_wait_is_the_read_timeout_not_the_gap(
        self, short_gap
    ):
        """Prefill and thinking live here; a short call measured 10-14s of it."""
        manager = FakeManager([(0, ev("message_start")), (0.2, THINKING), (0.2, TEXT)])
        assert await _stream_to_message(manager, "m", 1.0) is FINAL

    async def test_pings_are_not_progress(self, short_gap):
        """A stream that only pings is a hang the socket's timeout never sees."""
        manager = FakeManager([(0.05, ev("ping"))] * 20)
        with pytest.raises(StreamReadTimeout, match="before first content"):
            await _stream_to_message(manager, "m", 0.3)

    async def test_a_response_that_never_opens_is_a_stall(self, short_gap):
        """Where every measured hang was: before the headers, 5.4% of calls."""
        manager = FakeManager([(0, TEXT)], opens_after=0.5)
        with pytest.raises(StreamReadTimeout, match="did not open") as caught:
            await _stream_to_message(manager, "m", 1.0)
        assert _is_stall_error(caught.value)
        assert manager.exited_with == "never", "nothing was opened to close"

    async def test_opening_within_the_budget_is_not_a_stall(self, short_gap):
        manager = FakeManager([(0, TEXT)], opens_after=0.05)
        assert await _stream_to_message(manager, "m", 1.0) is FINAL

    async def test_the_synthesized_text_event_counts_as_content(self, short_gap):
        manager = FakeManager([(0, ev("text")), (0.5, TEXT)])
        with pytest.raises(StreamReadTimeout, match="mid-content"):
            await _stream_to_message(manager, "m", 1.0)


class TestStreamingIsTheDefault:
    def test_default(self):
        from dialectical_framework.settings import Settings

        assert Settings.model_fields["llm_stream_awaited_calls"].default is True
