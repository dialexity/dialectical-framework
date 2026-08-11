"""
Transport-level resilience of LLM calls: connect timeout and connection retry.

Both guards here exist because of the same real failure, and because it is
mislabelled by default. The framework's parallel stages (ExplorationPipeline,
ExploreTransformations) open many connections at once, so a link whose cold TLS
handshake is slower than the SDK's 5s connect timeout fails EVERY call in a
gather at once. The turn then records no text, which reads as "the model
declined" rather than "the network was never crossed" — the exact same
misdiagnosis the extended-thinking bug produced (see test_thinking_compat).

The measured case: 7.7s cold handshake on a tethered link. A1 (sequential, one
reused socket) passed; A2 (parallel, cold sockets) failed all six turns.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from dialectical_framework.utils import use_brain as use_brain_module
from dialectical_framework.utils.bedrock_provider import (
    BedrockAnthropicProvider,
    _connect_timeout,
)

pytestmark = []


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class TestConnectTimeout:
    def test_connect_phase_is_widened(self):
        """The SDK's 5s default is the whole bug — it must not survive."""
        assert _connect_timeout(30.0).connect == 30.0

    def test_read_and_write_keep_sdk_defaults(self):
        """Only the connect phase is the framework's business.

        Widening read/write too would mask genuine hangs: a slow generation and
        an unreachable endpoint are different faults and must stay
        distinguishable.
        """
        from anthropic._constants import DEFAULT_TIMEOUT

        timeout = _connect_timeout(30.0)
        assert timeout.read == DEFAULT_TIMEOUT.read
        assert timeout.write == DEFAULT_TIMEOUT.write

    def test_none_falls_back_to_a_generous_default(self):
        """Provider construction without DI (Mirascope's path) must still be safe."""
        assert _connect_timeout(None).connect > 5.0

    def test_both_clients_get_the_timeout(self):
        """The sync client is used by non-async callers — same link, same fix."""
        provider = BedrockAnthropicProvider(connect_timeout_s=17.0)
        assert provider.async_client.timeout.connect == 17.0
        assert provider.client.timeout.connect == 17.0


class TestConnectionErrorDetection:
    """`_is_connection_error` matches by class NAME, since Mirascope re-raises
    provider errors as its own ConnectionError/TimeoutError and importing those
    would shadow the builtins in use_brain."""

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.ConnectTimeout("timed out"),
            httpx.ConnectError("refused"),
            httpx.ReadTimeout("slow"),
        ],
    )
    def test_httpx_transport_failures_are_retryable(self, exc):
        assert use_brain_module._is_connection_error(exc) is True

    def test_mirascope_wrapped_connection_error_is_retryable(self):
        """The shape actually observed in the bench: the provider error arrives
        already translated by Mirascope, message "Connection error."."""
        from mirascope.llm.exceptions import ConnectionError as MirascopeConnectionError

        exc = MirascopeConnectionError("Connection error.", "bedrock")
        assert use_brain_module._is_connection_error(exc) is True

    def test_anthropic_connection_error_is_retryable(self):
        from anthropic import APIConnectionError

        exc = APIConnectionError(request=httpx.Request("POST", "https://x"))
        assert use_brain_module._is_connection_error(exc) is True

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad argument"),
            KeyError("missing"),
            RuntimeError("logic error"),
        ],
    )
    def test_logic_errors_are_not_retryable(self, exc):
        """Retrying a bug wastes the budget and hides the stack trace."""
        assert use_brain_module._is_connection_error(exc) is False

    def test_bad_request_is_not_a_connection_error(self):
        """A 400 is deterministic — retrying it can only burn the budget.

        Specifically important because the thinking-shape 400 has its OWN
        one-shot self-correcting retry in the provider; treating it as transient
        here would retry the same malformed request three more times.
        """
        from anthropic import BadRequestError

        exc = BadRequestError(
            "thinking.type.enabled not supported",
            response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
            body=None,
        )
        assert use_brain_module._is_connection_error(exc) is False


class TestConnectionRetryLoop:
    """The retry itself, exercised through the decorator's own loop.

    `_llm_call` is monkeypatched at the `llm.call` seam so no provider, no
    credentials and no network are involved.
    """

    @pytest.fixture(autouse=True)
    def mock_llm(self):
        """Opt out of the autouse mock brain.

        `install_mock_brain` replaces the `use_brain` decorator itself, so with it
        installed the retry loop under test is not the code that runs. No network
        is reached regardless: `llm.call` is monkeypatched below.
        """
        yield

    @staticmethod
    def _decorated(side_effects: list, monkeypatch) -> tuple:
        """Build a use_brain-decorated coroutine whose LLM call yields
        `side_effects` in order (exceptions raised, values returned).

        Returns (callable, calls list). Sleeps are stubbed out: the point under
        test is the retry decision, not wall-clock backoff.
        """
        calls: list[int] = []
        remaining = list(side_effects)

        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(use_brain_module.asyncio, "sleep", _fake_sleep)

        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    calls.append(1)
                    outcome = remaining.pop(0)
                    if isinstance(outcome, Exception):
                        raise outcome
                    return outcome

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)

        @use_brain_module.use_brain(ai_model="anthropic/claude-x")
        async def _method():
            return None

        return _method, calls

    @pytest.mark.asyncio
    async def test_transient_connection_error_recovers(self, monkeypatch):
        """The failure mode this whole file exists for: one blip must not kill
        the turn."""
        method, calls = self._decorated(
            [httpx.ConnectTimeout("cold handshake"), "recovered"], monkeypatch
        )
        assert await method() == "recovered"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_persistent_connection_error_surfaces(self, monkeypatch):
        """A real outage must raise, not retry the full budget.

        Bounded separately from `retry_max` (10) precisely so an unreachable
        endpoint fails in seconds instead of stalling a pipeline for minutes.
        """
        method, calls = self._decorated(
            [httpx.ConnectError("down")] * 10, monkeypatch
        )
        with pytest.raises(httpx.ConnectError):
            await method()
        assert len(calls) == use_brain_module._CONNECT_RETRY_MAX

    @pytest.mark.asyncio
    async def test_logic_error_is_not_retried(self, monkeypatch):
        method, calls = self._decorated([ValueError("bug"), "unreachable"], monkeypatch)
        with pytest.raises(ValueError):
            await method()
        assert len(calls) == 1


class _FakeProviderError(Exception):
    """A provider error shaped like the ones that actually arrive.

    Two shapes exist and both must be caught: some SDKs attach `status_code`,
    while Bedrock through Mirascope often carries the code only in the message
    (`Error code: 503 - {'message': 'Bedrock is unable to process your
    request.'}`). A predicate that reads only the attribute passes a unit test
    and misses the real thing.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class TestTransientServerErrorDetection:
    """A 5xx is the provider saying "not now" — the request was fine.

    Measured: one Bedrock 503 cost `claim2-weak-r9-pathways-judged` three turns
    of its A1.7 BASELINE arm on the first cell. That direction matters — a
    degraded baseline inflates every framework-vs-baseline delta with nobody
    touching a framework number, so it manufactures a win rather than hiding one.
    """

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_server_errors_are_retryable_by_attribute(self, status):
        exc = _FakeProviderError("upstream sad", status_code=status)
        assert use_brain_module._is_transient_server_error(exc)

    def test_the_real_bedrock_503_shape_is_retryable(self):
        """Verbatim from the bench log — the message-only shape."""
        exc = _FakeProviderError(
            "Error code: 503 - {'message': 'Bedrock is unable to process "
            "your request.'}"
        )
        assert use_brain_module._is_transient_server_error(exc)

    @pytest.mark.parametrize(
        "msg",
        [
            "ServiceUnavailableException: try later",
            "InternalServerException: something broke",
            "ModelNotReadyException: warming up",
        ],
    )
    def test_named_aws_transients_are_retryable(self, msg):
        assert use_brain_module._is_transient_server_error(_FakeProviderError(msg))

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
    def test_client_errors_are_not_retried(self, status):
        """4xx is OUR bug — a malformed request, bad auth, too much context.
        Retrying wastes the budget and buries the cause."""
        exc = _FakeProviderError("that's on us", status_code=status)
        assert not use_brain_module._is_transient_server_error(exc)

    def test_a_throttle_is_not_a_server_error(self):
        """429 has its own, much longer backoff curve; classifying it here would
        retry it 3 times fast and then give up, instead of 10 times patiently."""
        exc = _FakeProviderError("ThrottlingException", status_code=429)
        assert not use_brain_module._is_transient_server_error(exc)
        assert use_brain_module._is_rate_limit_error(exc)

    def test_a_plain_bug_is_not_a_server_error(self):
        assert not use_brain_module._is_transient_server_error(ValueError("bug"))


class TestServerErrorRetryLoop(TestConnectionRetryLoop):
    """Same seam, same stubbed sleeps — inherits the `_decorated` harness."""

    @pytest.mark.asyncio
    async def test_a_transient_503_does_not_kill_the_turn(self, monkeypatch):
        method, calls = self._decorated(
            [
                _FakeProviderError(
                    "Error code: 503 - {'message': 'Bedrock is unable to "
                    "process your request.'}"
                ),
                "recovered",
            ],
            monkeypatch,
        )
        assert await method() == "recovered"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_a_persistent_outage_still_surfaces(self, monkeypatch):
        """Bounded separately from `retry_max` (10): a provider that is genuinely
        down must fail in seconds, not stall a pipeline for minutes."""
        method, calls = self._decorated(
            [_FakeProviderError("down", status_code=503)] * 10, monkeypatch
        )
        with pytest.raises(_FakeProviderError):
            await method()
        assert len(calls) == use_brain_module._SERVER_RETRY_MAX

    @pytest.mark.asyncio
    async def test_a_client_error_is_not_retried(self, monkeypatch):
        method, calls = self._decorated(
            [_FakeProviderError("bad request", status_code=400), "unreachable"],
            monkeypatch,
        )
        with pytest.raises(_FakeProviderError):
            await method()
        assert len(calls) == 1
