"""
Per-model compatibility for Anthropic extended thinking.

Two incompatible request shapes exist and neither works everywhere:

* **budgeted** — ``thinking={"type": "enabled", "budget_tokens": N}``.
  Claude 3.x/4.x. Claude 5 models reject it outright:
  ``'"thinking.type.enabled" is not supported for this model'``.
* **adaptive** — ``thinking={"type": "adaptive"}`` plus
  ``output_config={"effort": ...}``. Claude 5 models. Claude 4.5 rejects both
  halves: ``'adaptive thinking is not supported on this model'`` and
  ``'output_config.effort: Extra inputs are not permitted'``.

Mirascope emits only the budgeted shape (it converts the level into a token
budget), so pointing ``DIALEXITY_DEFAULT_MODEL`` at a Claude 5 model with a
thinking level set makes every call 400. On the Advisor's conversational path
thinking kwargs go out on every turn, so the symptom is an agent that returns
empty text and calls no tools — which reads as a weak model rather than as a
malformed request. Hence this translation, and hence a shape mismatch must
never be silent.

Mode selection is by model name, with a learned fallback: if the heuristic is
wrong for some future model, the first 400 teaches us and every later call in
the process uses the other shape.

**"Off" is a third per-model shape** (probed 2026-10-08,
`tests/e2e/probe_claude_5_5_compat.py`). Claude 5 takes
``{"type": "disabled"}``. Sonnet 5.5 rejects it and names its own off,
``{"type": "between_tools"}`` ("The model does not think before responding. The
short updates it writes between tool calls come back as thinking blocks"),
which Sonnet 5 and Opus 5.5 reject in turn. Opus 5.5 — and Fable 5 / 5.1 — cannot turn thinking off
at all ("Use thinking.type.adaptive and output_config.effort"), so its off is
the least thinking it takes: adaptive at effort ``low``. Hence `off_shape`,
chosen by name with the same learned fallback.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping, Optional

from dialectical_framework.utils.format_compat import claude_family, claude_version

logger = logging.getLogger(__name__)

#: Thinking request shapes.
BUDGETED = "budgeted"
ADAPTIVE = "adaptive"

#: Framework thinking level -> ``output_config.effort``. The budgeted shape
#: expresses intensity as a fraction of max_tokens; the adaptive shape lets the
#: model decide and takes only a coarse effort label, so "minimal" and "low"
#: both land on "low". Keep in sync with ``Settings.conversation_thinking_level`` docs.
_LEVEL_TO_EFFORT = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}

#: How "thinking off" is said, per model (adaptive-shape models only; a
#: budgeted model is off when nothing is sent).
OFF_DISABLED = "disabled"
OFF_BETWEEN_TOOLS = "between_tools"
OFF_LOW_EFFORT = "low_effort"

#: Model name -> shape, learned from a 400. Overrides the name heuristic.
_LEARNED: dict[str, str] = {}
#: Model name -> off shape, learned from a 400. Overrides the name heuristic.
_LEARNED_OFF: dict[str, str] = {}

#: True while a CONVERSATIONAL provider round is being opened — the facilitator's
#: tool-path call and its resumes — and nowhere else. Read by
#: `with_thinking_compat` to send "disabled" where an unset level would otherwise
#: fall to the provider's default (thinking ON for Claude 5). A ContextVar rather
#: than an argument because the request is encoded three layers below the caller
#: that knows which kind of call it is; a task inherits the value, and the
#: structured concern calls a TOOL makes run outside the `with`, so they keep
#: the default.
_CONVERSATIONAL_ROUND: ContextVar[bool] = ContextVar(
    "dialexity_conversational_round", default=False
)


@contextmanager
def conversational_round() -> Iterator[None]:
    """Mark the provider call(s) inside as a conversational round.

    Entered by `ConversationFacilitator` around `_call_with_tools`, each
    `response.resume(...)` and each streamed round start — the calls a person
    is waiting on and whose thinking, with no level set, is double work over a
    graph that already holds the reasoning. NOT entered around tool execution:
    the concerns a tool runs are the framework's own reasoning steps and keep
    the provider default.
    """
    token = _CONVERSATIONAL_ROUND.set(True)
    try:
        yield
    finally:
        _CONVERSATIONAL_ROUND.reset(token)

def thinking_shape(model_name: str) -> str:
    """Which thinking request shape this model accepts."""
    learned = _LEARNED.get(model_name)
    if learned:
        return learned
    version = claude_version(model_name)
    if version and version[0] >= 5:
        return ADAPTIVE
    return BUDGETED


def off_shape(model_name: str) -> str:
    """How to send "thinking off" to an adaptive-shape model.

    By name: Fable/Mythos (any version), adaptive at low effort; otherwise
    below 5.5, ``disabled``; Sonnet 5.5+, ``between_tools``; any other 5.5+
    family, adaptive at low effort — the one off every adaptive model
    measured accepts, so an unknown family degrades to a little thinking rather
    than to a 400.
    """
    learned = _LEARNED_OFF.get(model_name)
    if learned:
        return learned
    if claude_family(model_name) in ("fable", "mythos"):
        # Thinking is always on in the Fable line (5 and 5.1 both refuse
        # "disabled" and "between_tools", probed 2026-10-08).
        return OFF_LOW_EFFORT
    version = claude_version(model_name)
    if version is None or version < (5, 5):
        return OFF_DISABLED
    if claude_family(model_name) == "sonnet":
        return OFF_BETWEEN_TOOLS
    return OFF_LOW_EFFORT


def binds_thinking_to_prefix(model_name: str) -> bool:
    """True when this model's thinking blocks are bound to the prefix that
    produced them (preserved thinking: Opus/Sonnet 5.5+, Fable/Mythos 5.1+).

    Such a block replayed under a different ``system`` prompt, tool set or
    earlier message fails the provider's prefix check — a 400 for accounts
    created on or after 2026-08-31, on every platform.
    """
    version = claude_version(model_name)
    if version is None:
        return False
    if claude_family(model_name) in ("fable", "mythos"):
        return version >= (5, 1)
    return version >= (5, 5)


_THINKING_BLOCK_TYPES = ("thinking", "redacted_thinking")


def _is_person_turn(message: Mapping[str, Any]) -> bool:
    """A user message that is not only tool results — a turn's opening."""
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return True
    return not content or any(
        not (isinstance(b, Mapping) and b.get("type") == "tool_result") for b in content
    )


def without_earlier_turn_thinking(
    model_name: str, messages: list[Any], *, every_turn: bool = False
) -> list[Any]:
    """Encoded messages with every thinking block before the current turn removed.

    Why (probed 2026-10-08, `probe_claude_5_5_compat.py`): the Advisor rebuilds
    its ``system`` prompt every turn — the graph dump lives there, after
    ``CACHE_SPLIT_SENTINEL`` — so on a binding model the previous turn's
    replayed blocks fail the prefix check on the next turn: "Invalid signature
    in thinking block. The block is bound to a different conversation … The
    system prompt differs" (Opus 5.5, enforcement on). Removing a LEADING run of
    thinking blocks is the one history change the check allows, and every block
    before the last person turn is exactly such a run. The current turn's tool
    loop keeps its blocks: they were produced under this turn's prefix, which
    this function leaves the same on every round of the turn.

    ``every_turn`` drops the current turn's blocks too — for a request whose
    prefix is NOT the tool loop's: the structured fallback after a tool loop
    sends no tools and, in JSON mode, extra system instructions, so the turn's
    own blocks are bound to a prefix it no longer has (and when the budget ran
    out the history ends on a tool result, so no new person turn marks the
    boundary). All of them is the longest leading run there is.

    An assistant message that would be left with nothing — thinking only, e.g.
    cut off at max_tokens — is dropped whole: keeping its block would leave a
    block behind a removed run, which the check does not allow, and an empty
    message is refused by the encoder. Consecutive user messages it leaves
    behind are joined by the API into one turn.

    Pure: returns a new list, never mutates the history it was given (the
    facilitator's `raw_message` dicts are the conversation of record). A model
    that does not bind is returned unchanged — the earlier-turn blocks are what
    every pre-5.5 measurement was taken with.
    """
    if not binds_thinking_to_prefix(model_name):
        return messages
    if every_turn:
        boundary = len(messages)
    else:
        boundary = max(
            (
                i
                for i, m in enumerate(messages)
                if isinstance(m, Mapping) and _is_person_turn(m)
            ),
            default=-1,
        )
    if boundary <= 0:
        return messages
    out: list[Any] = []
    for i, message in enumerate(messages):
        if (
            i >= boundary
            or not isinstance(message, Mapping)
            or message.get("role") != "assistant"
            or not isinstance(message.get("content"), list)
        ):
            out.append(message)
            continue
        content = message["content"]
        kept = [
            b
            for b in content
            if not (isinstance(b, Mapping) and b.get("type") in _THINKING_BLOCK_TYPES)
        ]
        if not kept:
            continue
        out.append(message if len(kept) == len(content) else {**message, "content": kept})
    return out


def _apply_off(model_name: str, out: dict[str, Any]) -> dict[str, Any]:
    off = off_shape(model_name)
    if off == OFF_BETWEEN_TOOLS:
        out["thinking"] = {"type": "between_tools"}
    elif off == OFF_LOW_EFFORT:
        out["thinking"] = {"type": "adaptive"}
        output_config = dict(out.get("output_config") or {})
        output_config["effort"] = "low"
        out["output_config"] = output_config
    else:
        out["thinking"] = {"type": "disabled"}
    return out


def with_thinking_compat(
    model_name: str,
    kwargs: Mapping[str, Any],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    """Return request kwargs adjusted to the model's thinking shape.

    Pure — the input is not mutated, so a caller can retry from the same base
    kwargs after :func:`learn_thinking_shape_from_error` flips the shape.

    ``params`` is Mirascope's own params dict, which still carries the original
    ``{"level": ...}``; the encoded kwargs have already lost it to a token
    budget. Reading the level here avoids inverting the budget arithmetic.
    """
    out = dict(kwargs)
    thinking = out.get("thinking")
    # A request WITHOUT thinking is not a request without thinking on a Claude 5
    # model: Bedrock's default for the adaptive shape is thinking ON. Measured
    # 2026-09-24 (`probe_tool_path_hidden_output`, Sonnet 5, level unset): every
    # call came back with a `thinking` block and `thinking_tokens` in usage —
    # ~500 on a plain reply, ~2,500 on a tool-wired turn over a real graph,
    # which is the whole of the sealed Advisor's 42s turn against the dump's 13s
    # (`probe_consultant_42s`).
    #
    # WHERE "unset" is sent as "disabled" is a policy, and it is scoped on
    # purpose: only inside a CONVERSATIONAL round (`conversational_round()`,
    # entered by the facilitator around the tool loop's own provider calls and
    # nothing else). There the hidden tokens are double work — the model
    # deliberating over tools about structure the graph already holds. The
    # structured calls that BUILD that structure (tetrads, extraction,
    # transformations, the checks) are not touched HERE — but they do not think
    # either: forced tool choice suppresses the provider default (0 thinking
    # tokens, 2026-09-24), and a call moved to JSON on 5.5 is sent the model's
    # off by `BedrockAnthropicProvider._encode`. Only the callers that ask for a
    # level (`TetradSketch`, the Consultant's view turn) think. That concerns do
    # not is what every measured figure was taken under, not a tested principle
    # (thinking was A/B'd on the extraction concern only, and bought nothing).
    # Budgeted-shape models do not think unless asked and are left alone either
    # way.
    #
    # "Off" itself is per model (`off_shape`): Claude 5 takes "disabled",
    # Sonnet 5.5 only "between_tools", Opus 5.5 no off at all (low effort).
    if thinking is None:
        if _CONVERSATIONAL_ROUND.get() and thinking_shape(model_name) == ADAPTIVE:
            return _apply_off(model_name, out)
        return out
    if isinstance(thinking, dict) and thinking.get("type") == "disabled":
        # Budgeted models accept "disabled" as sent; an adaptive model gets its
        # own way of saying it.
        if thinking_shape(model_name) == ADAPTIVE:
            return _apply_off(model_name, out)
        return out
    if not isinstance(thinking, dict) or thinking.get("type") != "enabled":
        return out
    if thinking_shape(model_name) != ADAPTIVE:
        return out

    out["thinking"] = {"type": "adaptive"}
    effort = _effort_from_params(params)
    if effort:
        output_config = dict(out.get("output_config") or {})
        output_config["effort"] = effort
        out["output_config"] = output_config
    return out


def learn_thinking_shape_from_error(model_name: str, error: BaseException) -> bool:
    """Record the shape this model really wants. True if worth retrying once.

    Returns False for every other error, so an unrelated 400 still surfaces.
    """
    message = str(error)
    off = _off_from_error(message)
    if off is not None:
        if _LEARNED_OFF.get(model_name) == off and _LEARNED.get(model_name) == ADAPTIVE:
            return False
        _LEARNED_OFF[model_name] = off
        # Only an adaptive-shape model has an "off" to get wrong, so this also
        # settles the shape — a name the heuristic cannot read (an inference
        # profile ARN) is BUDGETED by default, and `_apply_off` would never run.
        _LEARNED[model_name] = ADAPTIVE
        logger.warning(
            "Model %s rejected the way thinking was turned off; using %s for the "
            "rest of this process. Adjust thinking_compat if this is a naming gap.",
            model_name,
            off,
        )
        return True
    if "thinking.type.enabled" in message and "not supported" in message:
        wanted = ADAPTIVE
    elif "adaptive thinking is not supported" in message or (
        "output_config" in message and "not permitted" in message
    ):
        wanted = BUDGETED
    else:
        return False
    if _LEARNED.get(model_name) == wanted:
        # Already learned and it still failed — the shape is not the problem.
        return False
    _LEARNED[model_name] = wanted
    logger.warning(
        "Model %s rejected the %s thinking shape; using %s for the rest of "
        "this process. Adjust thinking_compat if this is a naming gap.",
        model_name,
        ADAPTIVE if wanted == BUDGETED else BUDGETED,
        wanted,
    )
    return True


def _off_from_error(message: str) -> Optional[str]:
    """The off shape a 400 asks for, or None when it is not about "off".

    The texts are the provider's own (`probe_claude_5_5_compat.py`):
    Sonnet 5.5 names ``between_tools`` as the replacement for ``disabled``;
    Opus 5.5 says ``thinking.type.disabled`` is not supported; a model that
    refuses ``between_tools`` says so the same way. Low effort is the off
    every adaptive model takes, so it is the landing for both refusals.
    """
    if '"between_tools"' in message and "instead of" in message:
        return OFF_BETWEEN_TOOLS
    if (
        "thinking.type.disabled" in message or "thinking.type.between_tools" in message
    ) and "not supported" in message:
        return OFF_LOW_EFFORT
    return None


def _effort_from_params(params: Mapping[str, Any]) -> Optional[str]:
    thinking = params.get("thinking")
    if isinstance(thinking, str):
        level = thinking
    elif isinstance(thinking, Mapping):
        level = thinking.get("level")
    else:
        level = None
    if not isinstance(level, str):
        return None
    return _LEVEL_TO_EFFORT.get(level.lower())


def reset_learned_thinking_shapes() -> None:
    """Test seam — the learned maps are process-global by design."""
    _LEARNED.clear()
    _LEARNED_OFF.clear()
