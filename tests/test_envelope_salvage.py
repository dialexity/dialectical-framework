"""Recovery of structured results the model returned in the wrong envelope.

Two confirmed failures, both on Bedrock, both on SINGLE-FIELD DTOs:

* sonnet-5 answered `StatementDeduplication`'s `SemanticDedupDto` by serializing
  the whole object a second time into the one field —
  `{"matches": "{\\"matches\\": [{...}]}"}`
* haiku-4.5 answered `TetradGrounding`'s `GroundingDto` with a **parameter
  descriptor** naming the field instead of filling it —
  `{"parameter_name": "particulars", "parameter_value": "..."}`

Pydantic rejects both although every byte of the answer is present.

What makes it expensive is the retry, not the parse — and the retry cannot work.
A re-ask is a fresh sample of the same model tendency, so it draws the same
envelope again, while `parse_delay` (10s doubling to a 120s cap across
`retry_max`=10) sleeps up to 750s per call. Measured both ways: an `anchor` on
sonnet-5 took 857s and then FAILED, and on haiku-4.5 three of three `anchor`
calls slept 70 / 270 / 750s around ~41s of real work and then SUCCEEDED — which
is worse, because succeeding is silent. Two write-ups then quoted the blend as
the tool's cost.

So `_salvage_envelope` is a chain of small rules rather than one special case,
and every rule obeys one invariant: **field names come from the model's own
bytes, never from the schema.** `TestTheSalvageNeverInventsAField` is that
invariant, and it is the reason a generic salvage is safe — inventing a key would
turn a refusal into content, and junk in the graph is worse than the parse error
it replaces.

Adding a rule when a new envelope shows up is the intended way to extend this.
`_log_unsalvageable` exists so that the next one costs a log line to diagnose
rather than a dedicated `--real-llm` probe run, which is what the `GroundingDto`
envelope cost.
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


class _GroundingLike(BaseModel):
    """Same shape as the second DTO that failed: one REQUIRED string field.

    Required, unlike `_DedupLike`, so the two together cover both halves of the
    validation gate — a model that accepts anything and a model that accepts
    almost nothing.
    """

    particulars: str


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


def _salvage(payload: str, format: type[BaseModel]):
    """Drive the whole path exactly as `use_brain` does, from raw bytes."""
    response = _FakeResponse(payload, format)
    error = _parse_error(response, format)
    return use_brain_module._salvage_envelope(response, format, error)


class TestTheTwoObservedEnvelopes:
    """Both confirmed in production, on real providers, on real DTOs."""

    def test_double_encoded_payload_is_recovered(self):
        inner = {"matches": [{"extraction_hash": "abc", "db_hash": "def", "confidence": 0.9}]}

        salvaged = _salvage(_double_encoded(inner), _DedupLike)

        assert salvaged is not None
        assert len(salvaged.matches) == 1
        assert salvaged.matches[0].extraction_hash == "abc"
        assert salvaged.matches[0].confidence == 0.9

    def test_parameter_descriptor_is_recovered(self):
        """The `GroundingDto` failure, verbatim: the model described the field.

        The 750s ladder this replaces bought a `None`, because grounding is
        fail-soft — 12.5 minutes of someone's turn for nothing they could see.
        """
        payload = json.dumps(
            {
                "parameter_name": "particulars",
                "parameter_value": "Cofounder holds 45%; two anchor accounts are 60% of revenue.",
            }
        )

        salvaged = _salvage(payload, _GroundingLike)

        assert salvaged is not None
        assert salvaged.particulars.startswith("Cofounder holds 45%")

    def test_the_descriptor_rule_does_not_depend_on_the_providers_wording(self):
        """Recognised by shape, not by the literal key `parameter_name`.

        "parameter_name" is one provider's phrasing of a tool-argument
        descriptor, not a contract. What identifies the envelope is that a value
        IS one of this model's field names.
        """
        payload = json.dumps({"field": "particulars", "content": "Feedback given in March."})

        salvaged = _salvage(payload, _GroundingLike)

        assert salvaged is not None
        assert salvaged.particulars == "Feedback given in March."


class TestTheOtherRules:
    """Not yet observed here, but each is one line and strictly gated.

    Three envelope families deliberately have NO rule, because Mirascope's
    `RootResponse.parse` already runs `extract_serialized_json` before validating:
    a prose preamble, a ```json fence and a list wrapper are all stripped down to
    the first balanced `{...}` upstream. What reaches the salvage is the object
    Mirascope itself tried and failed to validate, so a rule for any of those
    three would be unreachable code pretending to be a safety net.
    """

    @pytest.mark.parametrize("key", ["result", "output", "properties", "arguments"])
    def test_generic_container_key(self, key):
        payload = json.dumps({key: {"particulars": "Decision due before the raise."}})

        salvaged = _salvage(payload, _GroundingLike)

        assert salvaged is not None
        assert salvaged.particulars == "Decision due before the raise."

    def test_the_dtos_own_name_as_a_wrapper(self):
        payload = json.dumps({"_GroundingLike": {"particulars": "45% equity."}})

        salvaged = _salvage(payload, _GroundingLike)

        assert salvaged is not None
        assert salvaged.particulars == "45% equity."


class TestTheSalvageNeverInventsAField:
    """The invariant that makes a GENERIC salvage safe.

    Every candidate's field names must come from the model's own bytes. Without
    this rule the chain would happily coerce any one-key object into a
    single-field DTO — and single-field DTOs are exactly where both real failures
    happened, so the temptation is real and so is the damage: a refusal or an
    error message would be validated into the graph as content, and the fail-soft
    contract that makes a parse error harmless would be what let it in.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            '{"value": "I cannot determine any particulars."}',
            '{"answer": "No relevant facts."}',
            '{"error": "context too short"}',
            '{"refusal": "I will not answer that."}',
            '{"text": "45% equity, feedback in March."}',
        ],
    )
    def test_a_wrongly_named_single_key_is_not_coerced(self, payload):
        """Every one of these WOULD validate if the key were renamed.

        That is the whole point: validation cannot distinguish them, so the
        salvage must not be the thing that renames.
        """
        assert _salvage(payload, _GroundingLike) is None

    def test_a_bare_string_is_not_coerced_into_the_only_field(self):
        assert _salvage('"45% equity, feedback in March."', _GroundingLike) is None

    def test_a_container_key_holding_a_non_object_is_not_unwrapped(self):
        """`{"result": "text"}` still needs the field named — see above."""
        assert _salvage('{"result": "45% equity."}', _GroundingLike) is None


class TestSalvageStaysNarrow:
    """Every case here must return None so the caller re-raises and retries.

    Over-broad salvage is worse than none: it would convert genuinely bad
    responses into plausible-looking half-answers that flow into the graph.
    """

    def test_truncated_json_is_not_salvaged(self):
        assert _salvage('{"matches": "{\\"matches\\": [{\\"extra', _DedupLike) is None

    def test_string_field_that_is_not_the_model_is_not_salvaged(self):
        """A field holding unrelated JSON must not be mistaken for the answer."""
        payload = json.dumps({"matches": json.dumps({"unrelated": 1})})
        assert _salvage(payload, _DedupLike) is None

    def test_plain_prose_is_not_salvaged(self):
        assert _salvage("I could not determine any matches.", _DedupLike) is None

    def test_non_validation_parse_error_is_not_salvaged(self):
        """A JSONDecodeError means the bytes are broken, not the encoding depth."""
        response = _FakeResponse(_double_encoded({"matches": []}))
        error = ParseError(
            "Failed to parse response",
            original_exception=json.JSONDecodeError("bad", "", 0),
        )
        assert use_brain_module._salvage_envelope(response, _DedupLike, error) is None


class TestTheRecoveryIsAudible:
    """A silent recovery hides a prompt/DTO problem worth fixing upstream — and
    silence is precisely what made this defect cost a bench round."""

    def test_salvage_warns_and_names_the_envelope(self, caplog):
        with caplog.at_level("WARNING"):
            _salvage(_double_encoded({"matches": []}), _DedupLike)

        assert "double-encoded" in caplog.text
        assert "_DedupLike" in caplog.text

    def test_the_descriptor_warning_says_which_field_was_described(self, caplog):
        payload = json.dumps({"parameter_name": "particulars", "parameter_value": "x"})

        with caplog.at_level("WARNING"):
            _salvage(payload, _GroundingLike)

        assert "particulars" in caplog.text
        assert "descriptor" in caplog.text

    def test_an_unsalvageable_payload_is_logged_verbatim(self, caplog):
        """The line that turns the NEXT envelope into a one-line diagnosis.

        Pydantic's own message truncates the payload mid-value
        (`input_value={'parameter_name': 'parti...`), which is enough to know
        something is wrong and not enough to write the rule that fixes it.
        """
        response = _FakeResponse('{"mystery_wrapper": {"nested": {"particulars": "x"}}}')

        with caplog.at_level("WARNING"):
            use_brain_module._log_unsalvageable(response, "_GroundingLike")

        assert "mystery_wrapper" in caplog.text
        assert "_GroundingLike" in caplog.text

    def test_an_empty_response_says_so_rather_than_logging_nothing(self, caplog):
        with caplog.at_level("WARNING"):
            use_brain_module._log_unsalvageable(_FakeResponse("   "), "_GroundingLike")

        assert "NO text" in caplog.text

    def test_a_long_payload_is_truncated(self, caplog):
        response = _FakeResponse(json.dumps({"junk": "x" * 5000}))

        with caplog.at_level("WARNING"):
            use_brain_module._log_unsalvageable(response, "_GroundingLike")

        assert "truncated" in caplog.text
        assert len(caplog.text) < 2000

    def test_the_logger_never_raises_on_the_failure_path(self):
        """It runs while a parse error is in flight; throwing there would
        replace a recoverable error with an unhandled one."""

        class _Hostile:
            def text(self, sep: str = "\n") -> str:
                raise RuntimeError("no text for you")

        use_brain_module._log_unsalvageable(_Hostile(), "_GroundingLike")


class TestRetryLoopIntegration:
    """The salvage must fire inside `use_brain`'s loop and cost ZERO retries —
    the retry budget was the whole expense (up to 750s of sleep per call)."""

    @pytest.fixture(autouse=True)
    def mock_llm(self):
        """Opt out of the autouse mock brain: it replaces the decorator under test."""
        yield

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload,format,check",
        [
            (
                _double_encoded(
                    {"matches": [{"extraction_hash": "abc", "db_hash": None, "confidence": 0.0}]}
                ),
                _DedupLike,
                lambda r: r.matches[0].extraction_hash == "abc",
            ),
            (
                json.dumps({"parameter_name": "particulars", "parameter_value": "45% equity."}),
                _GroundingLike,
                lambda r: r.particulars == "45% equity.",
            ),
        ],
        ids=["double-encoded", "parameter-descriptor"],
    )
    async def test_a_salvageable_response_parses_without_a_retry(
        self, monkeypatch, payload, format, check
    ):
        calls: list[int] = []
        slept: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(use_brain_module.asyncio, "sleep", _fake_sleep)
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)

        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    calls.append(1)
                    return _FakeResponse(payload, format)

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)

        @use_brain_module.use_brain(ai_model="anthropic/claude-x", format=format)
        async def _method():
            return None

        result = await _method()

        assert isinstance(result, format)
        assert check(result)
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

    @pytest.mark.asyncio
    async def test_the_raw_payload_is_logged_once_not_once_per_attempt(
        self, monkeypatch, caplog
    ):
        """Three attempts, one dump: the point is a readable log, and ten copies
        of the same envelope is how the useful line gets skipped."""

        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(use_brain_module.asyncio, "sleep", _fake_sleep)
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)

        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    # `_GroundingLike` explicitly: `_DedupLike` defaults every
                    # field, so it would VALIDATE this payload and never reach
                    # the failure path — the same trap the salvage's
                    # names-a-real-field gate exists for.
                    return _FakeResponse(
                        '{"mystery_wrapper": {"particulars": "x"}}', _GroundingLike
                    )

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)

        @use_brain_module.use_brain(
            ai_model="anthropic/claude-x", format=_GroundingLike, retry_max=3
        )
        async def _method():
            return None

        with caplog.at_level("WARNING"), pytest.raises(ParseError):
            await _method()

        # Counting the dump line, not the envelope's text: pydantic's own message
        # quotes the payload as `input_value=` on EVERY attempt, so a naive
        # occurrence count would be 3 here and would pass for the wrong reason.
        assert caplog.text.count("Raw payload") == 1
        assert caplog.text.count("backing off") == 2, "the retries themselves still log"
