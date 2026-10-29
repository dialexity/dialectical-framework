"""
Does a call KILLED mid-stream leave its bill in the census? (`CallRecord.partial`)

The first app's cancel endpoint kills a draw's task; the provider billed the
request and, until 2026-10-29, nothing recorded it. The mocked suite proves the
plumbing with fake events; this is the gate on the REAL stream: that Anthropic's
`message_start` lands the prefill in the holder, that a cancel mid-content
records a `partial` record under `use_brain`, and that the same call finishing
records a normal one. Run on the configured model (`DIALEXITY_DEFAULT_MODEL`).

    poetry run pytest tests/e2e/probe_cancelled_call_usage.py --real-llm -s
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.utils import bedrock_provider
from dialectical_framework.utils.call_census import call_census


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class Essay(BaseModel):
    """Long enough to be cancelled mid-generation."""

    title: str = Field(description="A title")
    body: str = Field(description="About four hundred words on the subject")


ASK = "Write about why cities grow along rivers."


def _watch_content(monkeypatch) -> asyncio.Event:
    """Set once the live stream has delivered content, so the cancel lands
    mid-generation rather than before the request opened."""
    seen = asyncio.Event()
    original = bedrock_provider._note_stream_usage

    def noting(event):
        original(event)
        if getattr(event, "type", None) == "content_block_delta":
            seen.set()

    monkeypatch.setattr(bedrock_provider, "_note_stream_usage", noting)
    return seen


@pytest.mark.real_llm
async def test_a_cancel_mid_stream_records_a_partial_bill(di_container, monkeypatch):
    seen = _watch_content(monkeypatch)
    with call_census() as census:
        task = asyncio.create_task(ConversationFacilitator().submit(Essay, ASK))
        await asyncio.wait_for(seen.wait(), timeout=120)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert census.count == 1, [c.label for c in census.calls]
    record = census.calls[0]
    print(
        f"\npartial={record.partial} uncached={record.uncached_input_tokens} "
        f"cache_read={record.cache_read_tokens} cache_write={record.cache_write_tokens} "
        f"output_tokens={record.output_tokens} output_chars={record.output_chars} "
        f"seconds={record.seconds:.1f} format={record.format_name}"
    )
    assert record.partial is True
    assert record.prefill_tokens is not None and record.prefill_tokens > 0, (
        "message_start's usage did not reach the holder"
    )
    assert record.output_chars is not None and record.output_chars > 0


@pytest.mark.real_llm
async def test_the_same_call_finishing_is_not_partial(di_container):
    with call_census() as census:
        essay = await ConversationFacilitator().submit(Essay, ASK)
    assert essay.body
    (record,) = census.calls
    print(
        f"\npartial={record.partial} prefill={record.prefill_tokens} "
        f"output_tokens={record.output_tokens} output_chars={record.output_chars}"
    )
    assert record.partial is False
    assert record.output_chars is None
    assert record.output_tokens is not None and record.output_tokens > 0
