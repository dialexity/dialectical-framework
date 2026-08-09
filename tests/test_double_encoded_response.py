"""Recovery of structured results the model returned double-encoded.

The real failure: sonnet-5 on Bedrock answered `StatementDeduplication`'s
`SemanticDedupDto` call by serializing the whole object a second time and
putting that string in the first field —

    {"matches": "{\\"matches\\": [{...}]}"}

— so pydantic rejected `matches` (`Input should be a valid array`,
`input_type=str`) although the entire answer was present and correct.

What made it expensive was the retry, not the parse. A re-ask is a fresh sample
of the same model tendency, so it fails again, and `parse_delay` (10s doubling
to a 120s cap across `retry_max`=10) spends 10+ minutes per call before raising.
Nested in `AnalysisPipeline` that compounded: one `anchor` took 857s and failed
on sonnet-5 against ~33s succeeding on haiku, and the bench's A2 arm read as
2.6h of framework slowness when the model had in fact answered correctly on the
first attempt.

Hence `_salvage_double_encoded` unwraps exactly one encoding layer — and only
when the decoded value validates against the same model, so a truncated or
genuinely malformed response still raises and still retries.
"""

from __future__ import annotations

import json

import pytest
from mirascope.llm.exceptions import ParseError
from pydantic import BaseModel, Field

from dialectical_framework.utils import use_brain as use_brain_module

pytestmark = []


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _Match(BaseModel):
    extraction_hash: str = ""
    db_hash: str | None = None
    confidence: float = 0.0


class _DedupLike(BaseModel):
    """Same shape as the DTO that actually failed: one list-of-model field,
    defaulted. The default matters — it means ANY JSON object validates, which
    is exactly why the salvage cannot rely on validation alone to tell a
    double-encoded answer from unrelated JSON."""

    matches: list[_Match] = Field(default_factory=list)


class _FakeResponse:
    """Minimal stand-in for AsyncResponse: `parse()` + `text()` are all the
    salvage path touches.

    `parse()` wraps validation failures in `ParseError` as Mirascope's real
    `RootResponse.parse` does — the retry loop keys off that type, so a fake
    that leaked the raw pydantic error would test a path that cannot happen.
    """

    def __init__(self, payload: str, format: type[BaseModel] = _DedupLike):
        self._payload = payload
        self._format = format

    def text(self, sep: str = "\n") -> str:
        return self._payload

    def parse(self):
        try:
            return self._format.model_validate_json(self._payload)
        except Exception as e:
            raise ParseError(
                f"Failed to parse response: {e}", original_exception=e
            ) from e


def _double_encoded(inner: dict) -> str:
    """The observed wire shape: the whole object, stringified, as field one."""
    return json.dumps({"matches": json.dumps(inner)})


def _parse_error(response: _FakeResponse, format: type[BaseModel]) -> ParseError:
    """The ParseError Mirascope would raise, with its real `original_exception`."""
    try:
        response.parse()
    except ParseError as e:
        return e
    raise AssertionError("payload was expected to fail parsing")


class TestSalvage:
    def test_double_encoded_payload_is_recovered(self):
        inner = {"matches": [{"extraction_hash": "abc", "db_hash": "def", "confidence": 0.9}]}
        response = _FakeResponse(_double_encoded(inner))
        error = _parse_error(response, _DedupLike)

        salvaged = use_brain_module._salvage_double_encoded(response, _DedupLike, error)

        assert salvaged is not None
        assert len(salvaged.matches) == 1
        assert salvaged.matches[0].extraction_hash == "abc"
        assert salvaged.matches[0].confidence == 0.9

    def test_salvage_warns_so_the_model_tendency_stays_visible(self, caplog):
        """Silent recovery would hide a prompt/DTO problem worth fixing upstream."""
        response = _FakeResponse(_double_encoded({"matches": []}))
        error = _parse_error(response, _DedupLike)

        with caplog.at_level("WARNING"):
            use_brain_module._salvage_double_encoded(response, _DedupLike, error)

        assert "double-encoded" in caplog.text
        assert "_DedupLike" in caplog.text


class TestSalvageStaysNarrow:
    """Every case here must return None so the caller re-raises and retries.

    Over-broad salvage is worse than none: it would convert genuinely bad
    responses into plausible-looking half-answers that flow into the graph.
    """

    def test_truncated_json_is_not_salvaged(self):
        response = _FakeResponse('{"matches": "{\\"matches\\": [{\\"extra')
        error = _parse_error(response, _DedupLike)
        assert use_brain_module._salvage_double_encoded(response, _DedupLike, error) is None

    def test_string_field_that_is_not_the_model_is_not_salvaged(self):
        """A field holding unrelated JSON must not be mistaken for the answer."""
        response = _FakeResponse(json.dumps({"matches": json.dumps({"unrelated": 1})}))
        error = _parse_error(response, _DedupLike)
        assert use_brain_module._salvage_double_encoded(response, _DedupLike, error) is None

    def test_plain_prose_is_not_salvaged(self):
        response = _FakeResponse("I could not determine any matches.")
        error = _parse_error(response, _DedupLike)
        assert use_brain_module._salvage_double_encoded(response, _DedupLike, error) is None

    def test_non_validation_parse_error_is_not_salvaged(self):
        """A JSONDecodeError means the bytes are broken, not the encoding depth."""
        response = _FakeResponse(_double_encoded({"matches": []}))
        error = ParseError(
            "Failed to parse response",
            original_exception=json.JSONDecodeError("bad", "", 0),
        )
        assert use_brain_module._salvage_double_encoded(response, _DedupLike, error) is None


class TestRetryLoopIntegration:
    """The salvage must fire inside `use_brain`'s loop and cost ZERO retries —
    the retry budget was the whole expense (10+ min per failing call)."""

    @pytest.fixture(autouse=True)
    def mock_llm(self):
        """Opt out of the autouse mock brain: it replaces the decorator under test."""
        yield

    @pytest.mark.asyncio
    async def test_double_encoded_response_parses_without_a_retry(self, monkeypatch):
        calls: list[int] = []
        payload = _double_encoded(
            {"matches": [{"extraction_hash": "abc", "db_hash": None, "confidence": 0.0}]}
        )

        slept: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(use_brain_module.asyncio, "sleep", _fake_sleep)
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)

        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    calls.append(1)
                    return _FakeResponse(payload)

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)

        @use_brain_module.use_brain(ai_model="anthropic/claude-x", format=_DedupLike)
        async def _method():
            return None

        result = await _method()

        assert isinstance(result, _DedupLike)
        assert result.matches[0].extraction_hash == "abc"
        assert len(calls) == 1, "salvage must not cost a re-ask"
        assert slept == [], "salvage must not pay the parse backoff"

    @pytest.mark.asyncio
    async def test_unsalvageable_response_still_retries(self, monkeypatch):
        """The existing guarantee must survive: real parse failures get retried."""
        calls: list[int] = []

        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(use_brain_module.asyncio, "sleep", _fake_sleep)
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)

        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    calls.append(1)
                    return _FakeResponse("no json here at all")

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)

        @use_brain_module.use_brain(
            ai_model="anthropic/claude-x", format=_DedupLike, retry_max=3
        )
        async def _method():
            return None

        with pytest.raises(ParseError):
            await _method()
        assert len(calls) == 3
