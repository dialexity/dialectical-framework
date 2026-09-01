from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from functools import wraps
from typing import (TYPE_CHECKING, Any, Awaitable, Callable, Iterator, Literal,
                    Optional, TypeVar, overload)

from dependency_injector.wiring import Provide, inject
from langfuse import get_client, observe
from mirascope import llm
from mirascope.llm.exceptions import ParseError
from mirascope.llm.responses import _utils
from pydantic import ValidationError as PydanticValidationError

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.utils.bedrock_provider import ensure_bedrock_provider
from dialectical_framework.utils.call_census import record_call
from dialectical_framework.utils.concurrency import llm_concurrency_slot
from dialectical_framework.utils.retry_accounting import record_retry

if TYPE_CHECKING:
    from mirascope.llm.calls import AsyncCall
    from mirascope.llm.responses import AsyncResponse

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


@overload
def use_brain(
    *,
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    format: type[T],
    tools: Optional[list[Any]] = ...,
    thinking: Optional[str | dict[str, Any]] = ...,
    raw_call: bool = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[T]]]: ...


@overload
def use_brain(
    *,
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    raw_call: Literal[True],
    format: Optional[type] = ...,
    tools: Optional[list[Any]] = ...,
    thinking: Optional[str | dict[str, Any]] = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[AsyncCall]]]: ...


@overload
def use_brain(
    *,
    ai_model: Optional[str] = ...,
    retry_max: int = ...,
    tools: Optional[list[Any]] = ...,
    thinking: Optional[str | dict[str, Any]] = ...,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Awaitable[AsyncResponse]]]: ...


def use_brain(
    *,
    ai_model: Optional[str] = None,
    retry_max: int = 10,
    format: Optional[type] = None,
    tools: Optional[list[Any]] = None,
    thinking: Optional[str | dict[str, Any]] = None,
    raw_call: bool = False,
    **llm_call_kwargs: Any,
) -> Callable[[F], Callable[..., Any]]:
    """
    Decorator factory for Mirascope v2 LLM calls.

    Retries on ParseError (validation failures) with a FLAT delay — waiting does
    not fix a wrong shape, see `_PARSE_RETRY_DELAY_S` — and on rate limits /
    throttling, transient connection failures and transient 5xx with exponential
    backoff (each with its own curve — see `_is_connection_error`).
    Automatically traces all LLM calls via Langfuse when configured.

    When ``format`` is provided, returns the parsed model instance.
    Otherwise returns the raw AsyncResponse (useful for tool calls).

    Args:
        ai_model: Model ID (e.g., 'bedrock/anthropic/claude-...'). Reads from DI if not provided.
        retry_max: Maximum attempts (default: 10). Set to 1 to disable retries.
            Ten is a DELIBERATE hold, revisited and kept 2026-08-27. Now that the
            parse curve is flat the residual exposure is ten generations rather
            than ten naps (~400s for `anchor`), so cutting it is tempting — but
            that trades latency for failure rate on stochastic derailments, and
            there is no distribution data on how many resamples one needs (n=1
            says one; r26 had a call succeed on attempt 10, since salvaged).
            Get the attempt-count distribution off a bench run before changing it.
        format: Pydantic model class for structured output.
        tools: List of tool functions/classes to make available.
        thinking: Extended thinking level string ("medium", "high", etc.)
            or a dict ({"level": "high", ...}). include_thoughts=True is added automatically.
        raw_call: If True, returns AsyncCall for caller to .stream() or await.
        **llm_call_kwargs: Additional kwargs for @llm.call (temperature, max_tokens, etc.)
    """

    def decorator(method: F) -> Callable[..., Any]:
        @wraps(method)
        @observe(as_type="generation", name=method.__qualname__, capture_input=False)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            resolved = ai_model
            if resolved is None:
                resolved = _get_ai_model()

            if resolved.startswith("bedrock/"):
                ensure_bedrock_provider()

            call_params: dict[str, Any] = {}
            if format is not None:
                call_params["format"] = format
            if tools is not None:
                call_params["tools"] = tools

            if thinking is not None:
                if isinstance(thinking, str):
                    call_params["thinking"] = {"level": thinking, "include_thoughts": True}
                else:
                    thinking.setdefault("include_thoughts", True)
                    call_params["thinking"] = thinking

            for key in ("temperature", "max_tokens", "top_p", "top_k", "seed", "stop_sequences"):
                if key in llm_call_kwargs:
                    call_params[key] = llm_call_kwargs[key]

            has_format = "format" in call_params
            format_name = call_params["format"].__name__ if has_format else None

            @llm.call(resolved, **call_params)
            async def _llm_call() -> Any:
                return await method(*args, **kwargs)

            # raw_call mode: return the AsyncCall for caller to .stream() or await.
            # Everything below this line belongs to the awaited path, and the
            # streaming caller has to provide its own equivalent — which it now
            # partly does. What that leaves, stated so nobody has to infer it:
            # - Retry: NOT here, and not on the same terms. The caller owns the
            #   stream lifecycle, so it retries with `retry_transient` around the
            #   open PLUS the first chunk — the largest unit that can still be
            #   re-asked. Once a chunk has been handed to the host, nothing can be
            #   retried, so a failure mid-stream still surfaces to the caller.
            # - Concurrency slot: NOT taken. A streamed round is unthrottled by
            #   `DIALEXITY_MAX_CONCURRENT_LLM_CALLS`.
            # - Census: the CALLER records it. `submit_stream` reports one record
            #   per round with first-chunk latency and post-consumption usage,
            #   because usage does not exist until the stream is drained.
            # - Langfuse: still nothing per round. `@observe()` on `submit_stream`
            #   creates the span, but there is no per-generation child, so token
            #   usage for streamed turns is absent from the trace.
            if raw_call:
                return _llm_call

            attempts = max(1, retry_max)
            parse_delay = _PARSE_RETRY_DELAY_S
            rate_delay = _RATE_LIMIT_BASE_S
            connect_delay = _CONNECT_RETRY_BASE_S
            connect_attempts = 0
            server_delay = _SERVER_RETRY_BASE_S
            server_attempts = 0
            last_error: Exception | None = None
            #: Cumulative backoff for THIS call, so a log line can say what the
            #: retry has cost so far rather than only what the next nap costs.
            #: Reading nine separate "backing off" lines and summing them by hand
            #: is how the old 750s parse ladder went unnoticed for a whole bench
            #: round. Still worth carrying now that the parse curve is flat: the
            #: throttle and 5xx curves still double, and they will exhaust the
            #: same budget the same way.
            slept_s = 0.0

            for attempt in range(attempts):
                attempt_started = time.monotonic()
                try:
                    async with llm_concurrency_slot():
                        # Timed INSIDE the slot: waiting for a semaphore is
                        # queueing, not provider time, and counting it here would
                        # make a throttled fan-out read as slow calls rather than
                        # as a queue. `CallCensus` documents where that wait
                        # surfaces instead.
                        call_started = time.monotonic()
                        response = await _llm_call()
                        record_call(
                            method.__qualname__,
                            seconds=time.monotonic() - call_started,
                            started=call_started,
                            # Without this the census cannot tell 33 DTOs apart:
                            # they all come through one `@use_brain` site in
                            # `ConversationFacilitator`, so the qualname is a
                            # constant.
                            format_name=format_name,
                            # This path is Mirascope's non-streaming decoder, which
                            # pre-adds the cache tokens into `input_tokens`. Said
                            # explicitly rather than left to the arithmetic, since
                            # the arithmetic can only DISPROVE pre-adding.
                            **prefill_token_kwargs(response, pre_added=True),
                        )
                    _trace_generation(
                        response=response,
                        model=resolved,
                        format_name=format_name,
                        caller=method.__qualname__,
                        attempt=attempt + 1,
                    )
                    if has_format:
                        try:
                            return response.parse()
                        except ParseError as e:
                            salvaged = _salvage_envelope(
                                response, call_params["format"], e
                            )
                            if salvaged is not None:
                                return salvaged
                            # Nothing fit, so this is about to cost a re-ask and
                            # a nap. Say what the model actually sent, ONCE per
                            # call: the pydantic error names the field and
                            # truncates the payload mid-value, which is enough to
                            # know something is wrong and not enough to write the
                            # unwrapper that would fix it. Diagnosing the
                            # `GroundingDto` envelope took a dedicated probe run
                            # for want of exactly this line.
                            if attempt == 0:
                                _log_unsalvageable(response, format_name)
                            raise
                    return response
                except ParseError as e:
                    last_error = e
                    if attempt < attempts - 1:
                        # LOGGED, unlike before 2026-08-26. This was the only
                        # retry branch that logged nothing, and it used to be the
                        # most expensive one: r26 spent 12.5 minutes here on four
                        # separate `anchor` calls, all of which then reported
                        # `ok`, and the whole 2.5-hour run produced zero warnings
                        # — so the archive recorded 810s as the cost of the tool.
                        # A silent retry is a cost with no owner.
                        #
                        # FLAT since 2026-08-27, deliberately unlike the three
                        # curves below — see `_PARSE_RETRY_DELAY_S`. The re-ask
                        # still happens; only the waiting between re-asks is gone.
                        slept_s += parse_delay
                        logging.getLogger(__name__).warning(
                            "Parse failure on %s (attempt %d/%d), backing off "
                            "%.0fs — this call has now slept %.0fs: %s",
                            format_name or method.__qualname__,
                            attempt + 1, attempts, parse_delay, slept_s, e,
                        )
                        record_retry(
                            "parse",
                            sleep_s=parse_delay,
                            attempt_s=time.monotonic() - attempt_started,
                        )
                        await asyncio.sleep(parse_delay)
                except Exception as e:
                    if _is_rate_limit_error(e):
                        last_error = e
                        logging.getLogger(__name__).warning(
                            "Rate limit hit (attempt %d/%d), backing off %.0fs: %s",
                            attempt + 1, attempts, rate_delay, e,
                        )
                        if attempt < attempts - 1:
                            slept_s += rate_delay
                            record_retry(
                                "rate_limit",
                                sleep_s=rate_delay,
                                attempt_s=time.monotonic() - attempt_started,
                            )
                            await asyncio.sleep(rate_delay)
                            rate_delay = min(rate_delay * 2.0, _RATE_LIMIT_CAP_S)
                    elif _is_connection_error(e):
                        # Bounded separately from `attempts`: a down endpoint must
                        # surface as an error, not consume the whole retry budget.
                        connect_attempts += 1
                        if connect_attempts >= _CONNECT_RETRY_MAX:
                            raise
                        last_error = e
                        logging.getLogger(__name__).warning(
                            "Connection error (attempt %d/%d), retrying in %.0fs: %s",
                            connect_attempts, _CONNECT_RETRY_MAX, connect_delay, e,
                        )
                        if attempt < attempts - 1:
                            slept_s += connect_delay
                            record_retry(
                                "connection",
                                sleep_s=connect_delay,
                                attempt_s=time.monotonic() - attempt_started,
                            )
                            await asyncio.sleep(connect_delay)
                            connect_delay *= 2.0
                    elif _is_transient_server_error(e):
                        # Bounded separately, same reasoning as connection
                        # errors: a persistent 5xx is an outage and must surface.
                        server_attempts += 1
                        if server_attempts >= _SERVER_RETRY_MAX:
                            raise
                        last_error = e
                        logging.getLogger(__name__).warning(
                            "Provider %d/%d unavailable, retrying in %.0fs: %s",
                            server_attempts, _SERVER_RETRY_MAX, server_delay, e,
                        )
                        if attempt < attempts - 1:
                            slept_s += server_delay
                            record_retry(
                                "server",
                                sleep_s=server_delay,
                                attempt_s=time.monotonic() - attempt_started,
                            )
                            await asyncio.sleep(server_delay)
                            server_delay *= 2.0
                    else:
                        raise

            raise last_error  # type: ignore[misc]

        return wrapper

    return decorator


#: Generic container keys a model may nest the real object under. An allowlist,
#: not a heuristic: `raw["error"]` or `raw["refusal"]` must NEVER be unwrapped as
#: if it were the answer, so only names that mean "here is the payload" qualify.
_CONTAINER_KEYS = (
    "properties",  # the model echoed the JSON Schema instead of instantiating it
    "result",
    "output",
    "response",
    "data",
    "arguments",  # tool-call framing leaking into a structured-output response
    "parameters",
    "input",
    "json",
)


#: How much of an unsalvageable payload to log. Enough to see the envelope's
#: shape — its keys and how the first value starts — without dumping a whole
#: tetrad into the log on every parse failure.
_RAW_PAYLOAD_LOG_CHARS = 600


#: Anthropic tool-call parameter framing, as it appears when it leaks into a
#: structured-output payload. Observed inside a string slot that expected an
#: object (`TetradDto.t_plus`, `probe_anchor_retry_cost.py`).
#:
#: Stops at the `=` on purpose. The leak lands INSIDE a JSON string value, so the
#: attribute quote arrives escaped — the observed text reads
#: `"t_plus": "\n<parameter name=\"statement\">…"`, and a marker that included
#: the bare `"` would have matched nothing it was written for.
_TOOL_CALL_XML_MARKER = "<parameter name="


def _framing_leak_note(text: str) -> str:
    """Name the tool-call-framing leak, and say whether it EARNS a salvage rule.

    Two dialects of one tendency — tool-call parameter framing bleeding into
    structured output. The JSON descriptor dialect has a rule
    (`_envelope_candidates` #2) because the model emitted it 3/3 times: a
    deterministic envelope cannot be re-sampled away. The XML dialect
    deliberately has none, and the archive states the condition under which it
    would earn one: the single observation was ALSO truncated, so unwrapping
    would have failed validation anyway — it needed the re-ask it got.

    That condition is a judgement someone had to make by eye on a clipped
    payload. This makes it mechanical: if the container parses, the XML is riding
    inside an otherwise complete answer and a rule is now justified; if it does
    not, this is the derailment already known to recover on the next sample.
    Detection only — no field name is inferred here, and nothing is salvaged.
    """
    if _TOOL_CALL_XML_MARKER not in text:
        return ""
    try:
        json.loads(_utils.extract_serialized_json(text))
    except Exception:  # noqa: BLE001
        return (
            " DIAGNOSIS: tool-call XML framing leaked into the payload AND the "
            "container does not parse — the known stochastic derailment, which "
            "the next sample fixes. Not salvageable; the re-ask is correct."
        )
    return (
        " DIAGNOSIS: tool-call XML framing leaked into an OTHERWISE COMPLETE "
        "payload. This is the documented trigger for adding an XML salvage rule "
        "to _envelope_candidates — see probe_anchor_retry_cost.py."
    )


def _log_unsalvageable(response: Any, format_name: Optional[str]) -> None:
    """Log what the model actually sent, so the next envelope is a one-line fix.

    Truncated and never raising: this runs on the failure path, and a logging
    helper that throws would replace a recoverable parse error with an unhandled
    one. Payload text only — no prompt, no system prompt, so this cannot leak the
    person's material any more widely than the parse error already does.
    """
    try:
        text = response.text("") or ""
    except Exception:  # noqa: BLE001
        return
    if not text.strip():
        logging.getLogger(__name__).warning(
            "Unsalvageable %s response: the model returned NO text at all.",
            format_name,
        )
        return
    clipped = text[:_RAW_PAYLOAD_LOG_CHARS]
    logging.getLogger(__name__).warning(
        "Unsalvageable %s envelope, retrying blind. Raw payload (%d chars%s): %s%s",
        format_name,
        len(text),
        ", truncated" if len(text) > _RAW_PAYLOAD_LOG_CHARS else "",
        clipped,
        # Appended AFTER the payload on purpose: the clip is what someone reads
        # first, and the note is only present when there is something to say.
        _framing_leak_note(text),
    )


def _envelope_candidates(raw: Any, format: type) -> Iterator[tuple[str, Any]]:
    """Every way this payload might be the right answer in the wrong wrapper.

    Yields `(what_went_wrong, candidate_payload)`. Ordered cheapest-and-most-
    observed first, but order only decides which explanation gets logged when two
    would both validate — `_salvage_envelope` gates every candidate identically.

    Each rule is deliberately small, and adding one when a NEW envelope is
    observed is the intended way to extend this: a rule, a line in the log, and a
    case in `tests/test_envelope_salvage.py`. What must not be added is a rule
    that guesses — see the invariant on `_salvage_envelope`.
    """
    fields = set(format.model_fields)

    # `raw` is always a dict: Mirascope's `RootResponse.parse` runs
    # `extract_serialized_json` before validating, which strips prose preambles,
    # ```json fences and any list wrapper down to the first balanced `{...}`. So
    # those three envelope families are already handled upstream and need no rule
    # here — what reaches this function is the object Mirascope itself tried and
    # failed to validate.
    if not isinstance(raw, dict):
        return

    # 1. The whole object serialized a second time into one field's string.
    #    Observed: sonnet-5 on Bedrock, `SemanticDedupDto`.
    #       {"matches": "{\"matches\": [{...}]}"}
    for value in raw.values():
        if not isinstance(value, str):
            continue
        try:
            yield "double-encoded (the whole object stringified inside a field)", json.loads(value)
        except Exception:
            continue

    # 2. A PARAMETER DESCRIPTOR instead of the object. Observed: haiku-4.5 on
    #    Bedrock, `TetradGrounding`'s single-field `GroundingDto` —
    #       {"parameter_name": "particulars", "parameter_value": "..."}
    #    i.e. the model described the field it was asked to fill instead of
    #    filling it. Recognised by SHAPE rather than by key name, because the
    #    provider's wording for "parameter_name" is not a contract: exactly two
    #    keys, one holding a string that IS one of this model's field names. Two
    #    keys keeps it unambiguous; more, and which key held the value would be
    #    a guess.
    if len(raw) == 2:
        for key, value in raw.items():
            if isinstance(value, str) and value in fields:
                other = next(k for k in raw if k != key)
                yield (
                    f"a parameter descriptor naming {value!r} instead of filling it",
                    {value: raw[other]},
                )

    # 3. The object nested one level under a generic container key, including the
    #    DTO's own name (`{"GroundingDto": {...}}`) — a model that treats the
    #    schema title as a wrapper.
    for key in (*_CONTAINER_KEYS, format.__name__):
        inner = raw.get(key)
        if isinstance(inner, dict):
            yield f"nested under a {key!r} wrapper", inner


def _salvage_envelope(response: Any, format: type, error: ParseError) -> Any:
    """Recover a structured result the model returned in the wrong envelope.

    Models answer with the right content in the wrong wrapper, and each provider
    and model has its own way of doing it. Two are confirmed here, both on
    Bedrock, both on SINGLE-FIELD DTOs: sonnet-5 re-serialized the whole object
    into the one field (`SemanticDedupDto`), and haiku-4.5 answered with a
    parameter descriptor naming the field instead of filling it (`GroundingDto`).
    Pydantic rejects both although every byte of the answer is present.

    Salvaged here rather than left to the retry loop because the retry CANNOT
    work: a re-ask is a fresh sample of the same model tendency, so it draws the
    same envelope again. Measured — an `anchor` on sonnet-5 re-asked itself for
    857s and then FAILED; on haiku-4.5 three of three `anchor` calls emitted the
    same descriptor 3/3 times. Nested in a pipeline that fans out, one such
    tendency multiplies across every gathered child.

    This used to be expensive as well as futile: the old parse curve doubled from
    10s to a 120s cap, so those haiku calls slept 70 / 270 / 750s around ~41s of
    real work and then succeeded, which is worse than failing, because succeeding
    is silent. The curve is flat now (`_PARSE_RETRY_DELAY_S`), so an unsalvaged
    envelope costs re-asks rather than naps — but a re-ask that will never succeed
    is still `retry_max` generations of someone's turn, which is why unwrapping
    beats retrying even at 2s a rung.

    THE INVARIANT, and the reason this can be generic without being dangerous:
    **every candidate's field names come from the model's own bytes, never from
    the schema.** No rule may invent a field name. `{"value": "I cannot answer"}`
    is therefore not salvageable into a single-field DTO even though it would
    validate — inventing the key would turn a refusal into content, and putting
    junk in the graph is worse than the parse error it replaces. A candidate must
    additionally validate AND name at least one real field, because DTOs whose
    fields all have defaults (`SemanticDedupDto.matches` among them) accept ANY
    JSON object.

    Returns None when nothing fits, leaving the caller's `raise` intact so a
    genuinely malformed or truncated response still retries.
    """
    if not isinstance(error.original_exception, PydanticValidationError):
        return None

    try:
        raw = json.loads(_utils.extract_serialized_json(response.text("")))
    except Exception:
        return None

    fields = set(format.model_fields)
    for what_went_wrong, candidate in _envelope_candidates(raw, format):
        if not isinstance(candidate, dict) or not fields & set(candidate):
            continue
        try:
            salvaged = format.model_validate(candidate)
        except Exception:
            continue
        # WARNING, not debug: a silent recovery hides a prompt/DTO problem worth
        # fixing upstream, and the whole reason this defect cost a bench round is
        # that the framework recovered from it without saying so.
        logging.getLogger(__name__).warning(
            "Model returned %s as %s; unwrapped it instead of spending the "
            "call's whole retry budget re-asking for the same envelope.",
            format.__name__, what_went_wrong,
        )
        return salvaged
    return None


def prefill_token_kwargs(
    response: Any, *, pre_added: Optional[bool] = None
) -> dict[str, Optional[int]]:
    """Cache-aware prefill breakdown for the census, as `record_call` kwargs.

    All three are `None` when the response carries no usable prefill, so the census
    can tell "not reported" from "reported as zero" — see `record_call`.

    THE SUBTRACTION IS THE WHOLE POINT. Mirascope's non-streaming decoder defines
    `input_tokens = raw_input + cache_read + cache_write` (`anthropic/_utils/
    decode.py:99`) while its streaming decoder does not (`:286`), so the raw field
    means two different things depending on the path. Recording the difference
    once, here, is what stops every downstream ratio from inheriting the ambiguity.

    `pre_added` says which convention this response follows, and a caller that
    KNOWS must say so. `None` falls back to arithmetic, which is sound only in one
    direction: `input_tokens >= cache_read + cache_write` always holds under the
    pre-adding convention, so a negative difference proves the field is already the
    uncached count — but a POSITIVE difference proves nothing. A streamed turn with
    an 18k cache read and a 25k uncached dump satisfies the pre-adding inequality
    comfortably and would be reported as 6,925 uncached out of 25,000 (a 0.72 cache
    share) when the truth is 25,000 out of 43,075 (0.42). That is the failure mode
    that matters: not a missing number, a confident wrong one. Hence the parameter.

    Clamping a negative difference to zero — the obvious defensive move — would be
    wrong in the worst available direction: it reports 0 uncached against a large
    cache_read, i.e. `cache_read_share` of 1.0, announcing perfect caching exactly
    when the instrument has lost track.

    ALL-ZERO PREFILL IS TREATED AS UNMEASURED, not as zero. A real round-trip
    cannot prefill nothing — there is always a system prompt — so zeros mean the
    provider did not tell us. That case is reachable: Mirascope's Anthropic stream
    decoder has no `message_start` handler at all and reads usage only from
    `message_delta` (`decode.py:277-291`), whose fields are optional on the SDK
    type. The `Usage` object still comes back truthy because `output_tokens` is
    populated, so without this guard a streamed round would be counted in
    `calls_with_usage` and drag `cache_read_share` toward zero — publishing "the
    cache fix does nothing" from an instrument that never saw a prefill token.
    """
    usage = getattr(response, "usage", None)
    unmeasured: dict[str, Optional[int]] = {
        "uncached_input_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
    }
    if not usage:
        return unmeasured
    cache_read = usage.cache_read_tokens or 0
    cache_write = usage.cache_write_tokens or 0
    reported_input = usage.input_tokens or 0
    if not (cache_read or cache_write or reported_input):
        return unmeasured
    if pre_added is False:
        uncached = reported_input
    else:
        difference = reported_input - cache_read - cache_write
        uncached = difference if difference >= 0 else reported_input
    return {
        "uncached_input_tokens": uncached,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }


def _trace_generation(
    response: Any,
    model: str,
    format_name: Optional[str],
    caller: str,
    attempt: int,
) -> None:
    """Report a completed LLM generation to Langfuse (if active)."""
    try:
        lf = get_client()

        usage_details: Optional[dict[str, int]] = None
        if response.usage:
            prefill = prefill_token_kwargs(response, pre_added=True)
            # Reported unconditionally, and `input` is the UNCACHED count. Both
            # halves were wrong before: the cache keys were behind falsy guards,
            # so a zero read as "not measured" exactly when a cache miss is the
            # thing worth seeing; and `input` was `usage.input_tokens`, which on
            # this path already contains the cache tokens, so every cached call
            # double-counted its prefill.
            usage_details = {
                "input": prefill["uncached_input_tokens"] or 0,
                "output": response.usage.output_tokens,
                "cache_read": prefill["cache_read_tokens"] or 0,
                "cache_write": prefill["cache_write_tokens"] or 0,
            }

        input_messages = [_serialize_message(m) for m in response.messages[:-1]]
        # `text` is a METHOD; the missing call recorded a bound-method repr as
        # every traced generation's output. Default `sep="\n"` here rather than
        # the `""` used at the parse sites above — those rebuild a JSON payload
        # that a separator would corrupt, this one is read by a person.
        output_text = response.text() if response.texts else str(response.tool_calls)

        metadata: dict[str, Any] = {"caller": caller, "attempt": attempt}
        if format_name:
            metadata["format"] = format_name

        lf.update_current_generation(
            model=model,
            input=input_messages,
            output=output_text,
            usage_details=usage_details,
            metadata=metadata,
        )
    except Exception as e:
        logging.getLogger(__name__).debug("Langfuse trace failed: %s", e)


def _serialize_message(msg: Any) -> dict[str, Any]:
    """Best-effort serialization of a Mirascope message for Langfuse."""
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "role") and hasattr(msg, "content"):
        content = msg.content
        if isinstance(content, list):
            parts = []
            for part in content:
                if hasattr(part, "text"):
                    parts.append(part.text)
                else:
                    parts.append(str(part))
            content = "\n".join(parts)
        return {"role": msg.role, "content": str(content)}
    return {"content": str(msg)}


#: The parse retry curve, and the only FLAT one in this file.
#:
#: Exponential backoff is a congestion-control curve. It works because waiting
#: makes the next attempt MORE LIKELY to succeed — the throttle window rolls over,
#: the link comes back, the overloaded service drains. A parse failure has no such
#: property: the model returned the wrong SHAPE, and nothing about that shape
#: heals over 120 seconds. So the doubling curve (10s → 120s cap, 750s over ten
#: attempts) was spending the person's turn buying nothing at all.
#:
#: Measured on both outcomes a parse failure actually has, and neither wanted the
#: wait. A DETERMINISTIC envelope defect (haiku-4.5's `GroundingDto` parameter
#: descriptor, 3/3 calls) cannot be re-sampled away — 9 retries and 750s of sleep
#: never fixed it and `_salvage_envelope` now does, at attempt 1. A STOCHASTIC
#: derailment (`TetradDto` truncated mid-field) recovers on the very next sample —
#: it did, having first slept 10s for no reason. Retrying is worth keeping;
#: waiting between retries never was.
#:
#: Not zero, though, and this is the whole reason the value is 2 rather than 0:
#: `ExplorationPipeline` and `ExploreTransformations` fan out, so a systematic
#: shape defect fails many gathered children at once, and a zero-delay loop would
#: turn one bad DTO into a burst of `retry_max` × N requests and earn a real
#: throttle — trading a curve that does nothing for a curve that does harm.
_PARSE_RETRY_DELAY_S = 2.0


#: Retry curve for transient connection failures. Shorter and shallower than the
#: throttle curve on purpose: throttling means "the service told us to wait", so
#: waiting long is the correct response, while a connect failure is usually a
#: momentary link glitch that either clears in seconds or is a real outage no
#: amount of waiting fixes. Capped attempts so a genuinely-down endpoint still
#: surfaces as an error instead of hanging a pipeline for minutes.
_CONNECT_RETRY_MAX = 3
_CONNECT_RETRY_BASE_S = 2.0


def _is_connection_error(e: Exception) -> bool:
    """Detect transient network failures worth retrying.

    Real failure this catches: the framework's parallel stages
    (ExplorationPipeline, ExploreTransformations) open many connections at once,
    so a single cold-connect blip took down an entire agent turn — every call in
    the gather died together and the turn recorded as "the model produced
    nothing", which reads as a weak model rather than a network fault.

    Matched by class name, not by import: Mirascope re-raises provider
    exceptions as its own `mirascope.llm.exceptions.ConnectionError`/`TimeoutError`,
    and importing those shadows the builtins in this module.
    """
    name = type(e).__name__
    if name in ("ConnectionError", "TimeoutError", "APIConnectionError", "APITimeoutError"):
        return True
    # httpx raises distinct classes per phase (ConnectTimeout, ReadTimeout,
    # ConnectError, RemoteProtocolError); the shared suffix is the reliable tell.
    return name.endswith(("ConnectError", "ConnectTimeout", "ReadTimeout"))


#: Provider-side transient failures: the request was well-formed and the service
#: simply could not take it right now. Bounded like connection errors rather than
#: like throttles — a 500/503 that persists is an outage, and burning the full
#: `retry_max` budget on one would hang a pipeline for minutes.
_SERVER_RETRY_MAX = 3
_SERVER_RETRY_BASE_S = 5.0


def _is_transient_server_error(e: Exception) -> bool:
    """Detect a provider saying "not now" — 500/502/503/504.

    Real failure this catches: a single Bedrock 503 ("Bedrock is unable to
    process your request") killed three turns of a bench baseline arm, which
    records as an arm that produced nothing and reads as a weak model rather than
    a provider blip — the identical misdiagnosis `_is_connection_error` exists to
    prevent, arriving one layer higher. Silently degrading the BASELINE is worse
    than degrading the framework arm: it inflates every framework-vs-baseline
    delta with nobody touching a framework number.

    Deliberately NOT matching 4xx: those are our bug (bad request, auth, too
    large) and retrying them wastes the budget and hides the cause. 429 is
    excluded here too — it has its own, longer backoff curve.
    """
    status = getattr(e, "status_code", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    # Bedrock/Mirascope frequently surface the status only in the message
    # ("Error code: 503 - {'message': 'Bedrock is unable to process...'}"), so
    # the class name and attribute are not enough on their own.
    msg = str(e)
    if any(f"code: {code}" in msg for code in (500, 502, 503, 504)):
        return True
    return (
        "ServiceUnavailable" in msg
        or "InternalServerException" in msg
        or "ModelNotReadyException" in msg
    )


#: Throttle curve. Long and doubling, unlike the connect and 5xx curves above:
#: throttling is the service explicitly telling us to wait, so waiting is the
#: correct response rather than a hope that something clears.
_RATE_LIMIT_BASE_S = 10.0
_RATE_LIMIT_CAP_S = 60.0

#: How many attempts a throttle gets in `retry_transient` — i.e. on the STREAMING
#: path. Deliberately NOT the ladder's budget, which is `retry_max` (default 10)
#: and therefore ~430s of sleep at the cap. That number was never chosen for
#: throttles; it is the shared attempt budget sized for parse re-asks, and the
#: throttle branch merely inherits it, the same accident `_CONNECT_RETRY_MAX` and
#: `_SERVER_RETRY_MAX` exist to correct.
#:
#: Three (30s) because of who is waiting. A ladder call is one concern inside a
#: pipeline nobody is watching, so seven more minutes is cheaper than a failed
#: run. A streamed round is a person who has just hit send and is looking at a
#: blank screen; seven minutes there is not patience, it is an abandoned session,
#: and a surfaced error at least lets the host say what happened. The honest
#: consequence: a sustained throttle still fails a streamed turn earlier than an
#: awaited one. That is the trade, not an oversight.
_RATE_LIMIT_RETRY_MAX = 3


def _is_rate_limit_error(e: Exception) -> bool:
    """Detect rate-limit / throttling errors from various providers."""
    if hasattr(e, "status_code") and getattr(e, "status_code", None) == 429:
        return True
    msg = str(e)
    if "ThrottlingException" in msg or "TooManyRequests" in msg:
        return True
    if "rate" in msg.lower() and ("limit" in msg.lower() or "exceeded" in msg.lower()):
        return True
    return False


def _transient_kind(e: Exception) -> Optional[str]:
    """Which retry curve this failure belongs on, or None if it belongs on none.

    The three predicates above in one place, in the same order the ladder above
    tests them, so a second caller cannot drift from the first.

    The order is load-bearing and it costs something. `_is_rate_limit_error`'s last
    branch is a loose text match ("rate" plus "limit"/"exceeded"), so a 5xx whose
    message happens to mention a rate limit is classified as a throttle and gets
    the 10s curve instead of the 5s one. Asking either predicate first trades one
    misfiling for the other; this order is the ladder's, and matching the ladder is
    worth more than winning that coin flip, because the whole point of this function
    is that the two paths cannot disagree about what a failure IS.
    """
    if _is_rate_limit_error(e):
        return "rate_limit"
    if _is_connection_error(e):
        return "connection"
    if _is_transient_server_error(e):
        return "server"
    return None


async def retry_transient(
    operation: Callable[[], Awaitable[T]], *, what: str
) -> T:
    """Run `operation`, retrying the transient failures `@use_brain` retries.

    Exists because the streaming path cannot use the ladder above. `use_brain`
    returns the raw callable before its own retry loop (`raw_call=True`), and the
    failure does not surface where the call is made anyway: `await call.stream()`
    issues no HTTP request, so a throttle or a 503 arrives on the stream's first
    `__anext__`, several frames away in the caller's chunk loop. Until this
    existed, a streamed round that hit a 429 took the whole turn down while the
    awaited path retried the same 429 up to ten times — the SAME failure, treated
    two ways depending on which path the person's turn happened to take.

    Same classification and the same three curves as the ladder, by construction:
    `_transient_kind` IS the ladder's branch order, and the delays are its
    constants. The budgets match for `connection` and `server`; the throttle budget
    does NOT, on purpose, and `_RATE_LIMIT_RETRY_MAX` is where that choice and its
    consequence are written down. Deliberately does NOT retry anything else: the
    ladder it replaces caught bare `Exception` and would sleep 15s over three
    attempts on a malformed request or a local encoding bug — buying nothing, for the
    same reason `_PARSE_RETRY_DELAY_S` is flat: waiting does not change a
    deterministic answer.

    Bounded per kind, with no overall ceiling, so the worst case is not any single
    curve: a failure sequence that keeps CHANGING kind gets each budget in full, 7
    attempts and ~51s of sleep before it surfaces. Bounded is what matters here, but
    "30s" is the throttle-only figure and not the promise.

    `operation` must be safe to call again. That is a real precondition and not a
    formality: the caller re-sends a whole prompt, so it must have no side effects
    of its own before the provider answers. On the streaming path's resume leg that
    means the tool outputs are already in hand — `execute_tools()` stays OUTSIDE, or
    a network blip re-runs a turn's worth of concern calls.

    Nothing is retried once content has arrived. The caller decides how much of
    itself to put inside `operation` — for a stream that is the open plus the
    first chunk, which is the largest unit that can still be re-asked safely.
    """
    delay = {
        "rate_limit": _RATE_LIMIT_BASE_S,
        "connection": _CONNECT_RETRY_BASE_S,
        "server": _SERVER_RETRY_BASE_S,
    }
    #: Only the throttle curve is capped, matching the ladder: a connect or 5xx
    #: curve is bounded by its attempt budget long before the delay matters. With
    #: `_RATE_LIMIT_RETRY_MAX` at 3 the throttle curve is too (10s then 20s), so this
    #: cap cannot currently bind HERE — it is carried so that raising the budget
    #: stays a one-line change that inherits the ladder's ceiling rather than
    #: doubling past it.
    cap = {"rate_limit": _RATE_LIMIT_CAP_S}
    #: Per KIND, not shared, and for the ladder's reason: a down endpoint must
    #: surface as an error instead of spending a throttle-sized budget on it.
    budget = {
        "rate_limit": _RATE_LIMIT_RETRY_MAX,
        "connection": _CONNECT_RETRY_MAX,
        "server": _SERVER_RETRY_MAX,
    }
    used: Counter = Counter()
    while True:
        attempt_started = time.monotonic()
        try:
            return await operation()
        except Exception as e:
            kind = _transient_kind(e)
            if kind is None:
                raise
            used[kind] += 1
            if used[kind] >= budget[kind]:
                raise
            sleep_s = delay[kind]
            logging.getLogger(__name__).warning(
                "%s failed (%s %d/%d), retrying in %.0fs: %s",
                what, kind, used[kind], budget[kind], sleep_s, e,
            )
            # The SAME kind the awaited path records, so `RetryAccount.kinds`
            # answers "which curve spent the seconds" across both paths. Where it
            # happened is in the log line above and in which account holds it — a
            # stream open is not inside any tool round, so it lands in
            # `TurnTiming.generation_retry_seconds`.
            record_retry(
                kind, sleep_s=sleep_s, attempt_s=time.monotonic() - attempt_started
            )
            await asyncio.sleep(sleep_s)
            delay[kind] = min(sleep_s * 2.0, cap.get(kind, float("inf")))


@inject
def _get_ai_model(settings: Settings = Provide[DI.settings]) -> str:
    return settings.ai_model
