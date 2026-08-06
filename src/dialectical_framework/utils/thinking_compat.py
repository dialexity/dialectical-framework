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
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

#: Thinking request shapes.
BUDGETED = "budgeted"
ADAPTIVE = "adaptive"

#: Framework thinking level -> ``output_config.effort``. The budgeted shape
#: expresses intensity as a fraction of max_tokens; the adaptive shape lets the
#: model decide and takes only a coarse effort label, so "minimal" and "low"
#: both land on "low". Keep in sync with ``Settings.thinking_level`` docs.
_LEVEL_TO_EFFORT = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}

#: Model name -> shape, learned from a 400. Overrides the name heuristic.
_LEARNED: dict[str, str] = {}

#: Claude 5+ naming puts the family before the version (``claude-sonnet-5``);
#: 3.x/4.x put it after or hyphenate the minor (``claude-3-5-sonnet``,
#: ``claude-haiku-4-5-...``). Matching ``claude-<family>-<major>`` therefore
#: reads 5 for ``claude-sonnet-5`` and 4 for ``claude-haiku-4-5``, and does not
#: match ``claude-3-5-sonnet`` at all.
_FAMILY_VERSION = re.compile(r"claude-([a-z]+)-(\d+)")


def thinking_shape(model_name: str) -> str:
    """Which thinking request shape this model accepts."""
    learned = _LEARNED.get(model_name)
    if learned:
        return learned
    match = _FAMILY_VERSION.search(model_name)
    if match and int(match.group(2)) >= 5:
        return ADAPTIVE
    return BUDGETED


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
    # "disabled" is accepted by both shapes, and a request without thinking has
    # nothing to translate.
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
    """Test seam — the learned map is process-global by design."""
    _LEARNED.clear()
