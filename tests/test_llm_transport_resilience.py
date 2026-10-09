"""
Transport-level resilience of LLM calls: connect and read timeouts, the retry
curves, and the SDK's own retry being off.

Both guards here exist because of the same real failure, and because it is
mislabelled by default. The framework's parallel stages (ExplorationPipeline,
ExploreTransformations) open many connections at once, so a link whose cold TLS
handshake is slower than the SDK's 5s connect timeout fails EVERY call in a
gather at once. The turn then records no text, which reads as "the model
declined" rather than "the network was never crossed" — the exact same
misdiagnosis the extended-thinking bug produced (see test_thinking_compat).

The measured case: 7.7s cold handshake on a tethered link. A1 (sequential, one
reused socket) passed; A2 (parallel, cold sockets) failed all six turns.

The read timeout is the other half (2026-10-09): the client kept the SDK's 600s,
so a provider call that stopped sending held its caller for ten minutes with no
error — a 610s turn recorded as clean, and one hung draw holding a best-of-3
card for 300s where the same case took 20-31s. `Settings.llm_read_timeout_s`
bounds it, a stall is re-asked ONCE (`_STALL_RETRY_MAX`), and the SDK's own two
retries are off so that bound is the whole bound.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from dialectical_framework.utils import use_brain as use_brain_module
from dialectical_framework.utils.bedrock_provider import (
    _SDK_MAX_RETRIES,
    BedrockAnthropicProvider,
    _client_timeout,
)

pytestmark = []


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class TestClientTimeout:
    def test_connect_phase_is_widened(self):
        """The SDK's 5s default is the whole bug — it must not survive."""
        assert _client_timeout(30.0).connect == 30.0

    def test_read_phase_is_the_setting(self):
        """A stall is bounded by the read phase, which was the SDK's 600s."""
        from anthropic._constants import DEFAULT_TIMEOUT

        timeout = _client_timeout(30.0, 45.0)
        assert timeout.read == 45.0
        assert timeout.read != DEFAULT_TIMEOUT.read

    def test_write_and_pool_keep_sdk_defaults(self):
        """Only the connect and read phases are the framework's business.

        Nothing has stalled on a write or on the pool; widening or cutting
        them would be a guess with no failure behind it.
        """
        from anthropic._constants import DEFAULT_TIMEOUT

        timeout = _client_timeout(30.0, 45.0)
        assert timeout.write == DEFAULT_TIMEOUT.write
        assert timeout.pool == DEFAULT_TIMEOUT.pool

    def test_none_falls_back_to_generous_defaults(self):
        """Provider construction without DI (Mirascope's path) must still be safe
        — and still bounded: the fallback read phase is NOT the SDK's 600s."""
        timeout = _client_timeout(None)
        assert timeout.connect > 5.0
        assert timeout.read < 600.0

    def test_both_clients_get_the_timeouts(self):
        """The sync client is used by non-async callers — same link, same fix."""
        provider = BedrockAnthropicProvider(connect_timeout_s=17.0, read_timeout_s=23.0)
        for client in (provider.async_client, provider.client):
            assert client.timeout.connect == 17.0
            assert client.timeout.read == 23.0

    def test_the_sdk_does_not_retry_on_its_own(self):
        """Every retry is the framework's, so the account sees it and the
        read-timeout bound holds: with the SDK's default two retries one stall
        cost three read timeouts before the ladder saw a single failure."""
        assert _SDK_MAX_RETRIES == 0
        provider = BedrockAnthropicProvider(connect_timeout_s=17.0, read_timeout_s=23.0)
        assert provider.async_client.max_retries == 0
        assert provider.client.max_retries == 0

    def test_the_settings_carry_both_phases_from_the_env(self, monkeypatch):
        from dialectical_framework.settings import Settings

        monkeypatch.setenv("DIALEXITY_DEFAULT_MODEL", "anthropic/test-model")
        monkeypatch.setenv("DIALEXITY_LLM_CONNECT_TIMEOUT_S", "11")
        monkeypatch.setenv("DIALEXITY_LLM_READ_TIMEOUT_S", "31")
        settings = Settings.from_env()
        assert settings.llm_connect_timeout_s == 11.0
        assert settings.llm_read_timeout_s == 31.0

    def test_the_default_read_timeout_is_bounded_and_generous(self, monkeypatch):
        """Below the SDK's 600s stall, above every unstalled generation measured
        so far (the archive's longest conversational rounds sit under a minute)."""
        from dialectical_framework.settings import Settings

        monkeypatch.setenv("DIALEXITY_DEFAULT_MODEL", "anthropic/test-model")
        monkeypatch.delenv("DIALEXITY_LLM_READ_TIMEOUT_S", raising=False)
        assert 60.0 <= Settings.from_env().llm_read_timeout_s < 600.0


def _stalled(inner: Exception) -> Exception:
    """The shape a read timeout actually arrives in at the ladder: Mirascope's
    `TimeoutError` raised from the SDK's `APITimeoutError` raised from the httpx
    phase class — the phase is two links down the chain."""
    from anthropic import APITimeoutError
    from mirascope.llm.exceptions import TimeoutError as MirascopeTimeoutError

    request = httpx.Request("POST", "https://x")
    try:
        try:
            raise inner
        except Exception as phase:
            raise APITimeoutError(request=request) from phase
    except Exception as sdk:
        try:
            raise MirascopeTimeoutError("Request timed out.", "bedrock", original_exception=sdk) from sdk
        except Exception as wrapped:
            return wrapped
    raise AssertionError("unreachable")


class TestStallDetection:
    """A read timeout is a timeout by class and a stall by cost: every attempt
    has already waited the whole read timeout. It gets its own, shorter budget,
    and `_is_connection_error` must not ALSO claim it."""

    def test_a_read_timeout_is_a_stall_however_wrapped(self):
        for exc in (httpx.ReadTimeout("quiet"), _stalled(httpx.ReadTimeout("quiet"))):
            assert use_brain_module._is_stall_error(exc) is True
            assert use_brain_module._is_connection_error(exc) is False
            assert use_brain_module._transient_kind(exc) == "stall"

    def test_a_connect_timeout_stays_on_the_connection_curve(self):
        """Same SDK class, different phase: the link, not the generation."""
        for exc in (httpx.ConnectTimeout("cold"), _stalled(httpx.ConnectTimeout("cold"))):
            assert use_brain_module._is_stall_error(exc) is False
            assert use_brain_module._transient_kind(exc) == "connection"

    def test_a_bare_timeout_with_no_phase_is_read_as_a_stall(self):
        """The shorter budget is the safe guess when the chain says nothing."""
        from anthropic import APITimeoutError

        exc = APITimeoutError(request=httpx.Request("POST", "https://x"))
        assert use_brain_module._transient_kind(exc) == "stall"

    def test_the_other_kinds_are_untouched(self):
        from mirascope.llm.exceptions import ConnectionError as MirascopeConnectionError

        assert use_brain_module._transient_kind(httpx.ConnectError("refused")) == "connection"
        assert use_brain_module._transient_kind(MirascopeConnectionError("Connection error.", "bedrock")) == "connection"
        assert use_brain_module._transient_kind(ValueError("bug")) is None

    def test_the_budget_is_one_re_ask(self):
        """Bound on one call = `_STALL_RETRY_MAX` × read timeout + the flat delay;
        the view turn's card (and its host's deadline) are sized on it."""
        assert use_brain_module._STALL_RETRY_MAX == 2
        assert use_brain_module._STALL_RETRY_MAX < use_brain_module._CONNECT_RETRY_MAX


class TestConnectionErrorDetection:
    """`_is_connection_error` matches by class NAME, since Mirascope re-raises
    provider errors as its own ConnectionError/TimeoutError and importing those
    would shadow the builtins in use_brain."""

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.ConnectTimeout("timed out"),
            httpx.ConnectError("refused"),
        ],
    )
    def test_httpx_transport_failures_are_retryable(self, exc):
        """`ReadTimeout` is deliberately absent: it is a stall (`TestStallDetection`)."""
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


class TestStallRetryLoop(TestConnectionRetryLoop):
    """The stall curve through the decorator's own loop."""

    @pytest.mark.asyncio
    async def test_one_stall_is_re_asked(self, monkeypatch):
        """A stall is usually one bad backend instance; the fresh request lands."""
        method, calls = self._decorated(
            [_stalled(httpx.ReadTimeout("quiet")), "recovered"], monkeypatch
        )
        assert await method() == "recovered"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_a_second_stall_surfaces_as_the_provider_error(self, monkeypatch):
        """Not the connection curve's three: each attempt already cost a whole
        read timeout, and the gathered callers are waiting on it. The exception
        that surfaces is the wrapped one, so a failed draw can name its type."""
        from mirascope.llm.exceptions import TimeoutError as MirascopeTimeoutError

        method, calls = self._decorated(
            [
                _stalled(httpx.ReadTimeout("quiet")),
                _stalled(httpx.ReadTimeout("quiet")),
                "never reached",
            ],
            monkeypatch,
        )
        with pytest.raises(MirascopeTimeoutError):
            await method()
        assert len(calls) == use_brain_module._STALL_RETRY_MAX == 2

    @pytest.mark.asyncio
    async def test_the_stall_is_on_the_retry_account(self, monkeypatch):
        """The whole point of taking the SDK's retry away: the account sees it."""
        from dialectical_framework.utils.retry_accounting import retry_account

        method, _calls = self._decorated(
            [_stalled(httpx.ReadTimeout("quiet")), "recovered"], monkeypatch
        )
        with retry_account() as account:
            await method()
        assert account.kinds == {"stall": 1}


class TestTheAwaitedResumeIsRetriedToo:
    """`submit`'s continuation rounds are Mirascope's own requests, below
    `use_brain`. Until the SDK's retry went to 0 they had its two retries; now
    they have `retry_transient`, like the streamed resume — the same failure,
    treated the same way on both paths."""

    @pytest.fixture(autouse=True)
    def mock_llm(self):
        yield

    @pytest.fixture
    def no_backoff_sleep(self, monkeypatch):
        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(use_brain_module.asyncio, "sleep", _fake_sleep)

    @staticmethod
    def _submit_with_a_failing_resume(monkeypatch, failures: list[Exception]):
        from pydantic import BaseModel

        from dialectical_framework.agents.conversation_facilitator import (
            ConversationFacilitator,
        )

        class _Chat(BaseModel):
            message: str

        class _Final:
            tool_calls: list = []
            messages: list = []
            finish_reason = None

            def text(self):
                return "done"

        class _ToolRound:
            def __init__(self) -> None:
                self.tool_calls = [type("TC", (), {"name": "explore", "args": "{}", "id": "tc-1"})()]
                self.messages: list = []
                self.execute_calls = 0
                self.resume_calls = 0

            async def execute_tools(self):
                self.execute_calls += 1
                return []

            async def resume(self, _outputs):
                self.resume_calls += 1
                if failures:
                    raise failures.pop(0)
                return _Final()

        first = _ToolRound()

        async def _fake_call_with_tools(self):
            return first

        monkeypatch.setattr(ConversationFacilitator, "_call_with_tools", _fake_call_with_tools)
        monkeypatch.setattr(ConversationFacilitator, "_record_tool_results", lambda self, *a: [])
        monkeypatch.setattr(ConversationFacilitator, "_strip_caller_from_messages", lambda self, *a: None)
        monkeypatch.setattr(ConversationFacilitator, "_close_dangling_tool_calls", lambda self, *a: None)
        monkeypatch.setattr(ConversationFacilitator, "_strip_unsupported_input_fields", lambda self: None)
        monkeypatch.setattr(
            ConversationFacilitator, "_reuse_written_reply", lambda self, *a: _Chat(message="done")
        )
        return ConversationFacilitator(tools=[lambda: None]), first, _Chat

    @pytest.mark.asyncio
    async def test_a_stall_between_tool_rounds_is_re_asked_once(self, monkeypatch, no_backoff_sleep):
        facilitator, first, chat = self._submit_with_a_failing_resume(
            monkeypatch, [_stalled(httpx.ReadTimeout("quiet"))]
        )
        reply = await facilitator.submit(chat, "hello")
        assert reply.message == "done"
        assert first.resume_calls == 2, "the same round re-asked"
        assert first.execute_calls == 1, "the tools ran once — outputs are re-sent, never re-run"
        assert facilitator.last_submit_retries.kinds == {"stall": 1}

    @pytest.mark.asyncio
    async def test_a_persistent_stall_surfaces(self, monkeypatch, no_backoff_sleep):
        from mirascope.llm.exceptions import TimeoutError as MirascopeTimeoutError

        facilitator, first, chat = self._submit_with_a_failing_resume(
            monkeypatch, [_stalled(httpx.ReadTimeout("q")), _stalled(httpx.ReadTimeout("q"))]
        )
        with pytest.raises(MirascopeTimeoutError):
            await facilitator.submit(chat, "hello")
        assert first.resume_calls == 2

    @pytest.mark.asyncio
    async def test_a_defect_of_ours_is_not_retried(self, monkeypatch, no_backoff_sleep):
        facilitator, first, chat = self._submit_with_a_failing_resume(
            monkeypatch, [ValueError("our bug")]
        )
        with pytest.raises(ValueError):
            await facilitator.submit(chat, "hello")
        assert first.resume_calls == 1
