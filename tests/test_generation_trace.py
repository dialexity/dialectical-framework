"""What Langfuse records about a generation, and why it went unnoticed.

`_trace_generation` recorded `response.text` — the bound METHOD, not the
prose — as every traced generation's output. It survived because the whole
body sits inside `except Exception: logging.debug(...)`, so nothing raised, and
because no test had ever read the recorded output. Traces looked populated: the
field was there, it just said `<bound method RootResponse.text of ...>`.

That is the general hazard, not a one-off: on mirascope `text` is a method
(`RootResponse.text(sep="\\n")`), so forgetting the parentheses is always
truthy and never an error. These tests read what actually reaches the client.
"""

from __future__ import annotations

from typing import Any

import pytest

from dialectical_framework.utils import use_brain


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _Text:
    def __init__(self, text: str):
        self.text = text


class _ToolCall:
    def __repr__(self) -> str:
        return "ToolCall(anchor)"


class _Response:
    """The parts of a mirascope response `_trace_generation` reads."""

    def __init__(self, texts: list[str], tool_calls: list | None = None):
        self.texts = [_Text(t) for t in texts]
        self.tool_calls = list(tool_calls or [])
        self.usage = None
        # `[:-1]` drops the assistant turn, so one entry means "no input".
        self.messages: list = [object()]

    def text(self, sep: str = "\n") -> str:
        return sep.join(part.text for part in self.texts)


@pytest.fixture
def recorded(monkeypatch) -> dict[str, Any]:
    """Capture the one `update_current_generation` call, if it happens."""
    seen: dict[str, Any] = {}

    class _Client:
        def update_current_generation(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(use_brain, "get_client", lambda: _Client())
    monkeypatch.setattr(use_brain, "_serialize_message", lambda m: "msg")
    return seen


def _trace(response, **overrides) -> None:
    use_brain._trace_generation(
        response,
        overrides.get("model", "bedrock/some-model"),
        overrides.get("format_name", None),
        overrides.get("caller", "SomeConcern.resolve"),
        overrides.get("attempt", 1),
    )


class TestTheRecordedOutput:
    def test_the_prose_is_recorded_not_the_method(self, recorded):
        _trace(_Response(["Buy him out."]))
        assert recorded["output"] == "Buy him out."

    def test_a_bound_method_never_reaches_the_client(self, recorded):
        """The exact regression. Asserting the positive above is not enough: a
        future refactor that drops the call again produces a truthy string, so
        pin the shape that string must never have."""
        _trace(_Response(["Buy him out."]))
        assert "bound method" not in str(recorded["output"])

    def test_multiple_text_parts_are_joined_readably(self, recorded):
        """Default `sep="\\n"`, unlike the `""` at the parse sites — this value
        is read by a person, not re-parsed as JSON."""
        _trace(_Response(["First thought.", "Second thought."]))
        assert recorded["output"] == "First thought.\nSecond thought."

    def test_a_tool_only_response_records_its_tool_calls(self, recorded):
        """No text parts at all: the turn's output IS the tool request."""
        _trace(_Response([], tool_calls=[_ToolCall()]))
        assert recorded["output"] == "[ToolCall(anchor)]"

    def test_failure_stays_silent(self, monkeypatch, recorded):
        """Deliberate: a broken trace must not break the generation it traces.
        This is also why the defect above lasted — so any NEW claim about
        recorded content needs a test that reads it, not an absent error."""
        class _Exploding:
            texts = [_Text("hi")]

            def text(self, sep: str = "\n"):
                raise RuntimeError("no")

        _trace(_Exploding())  # must not raise
        assert recorded == {}
