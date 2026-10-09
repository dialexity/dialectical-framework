"""
Per-model compatibility for how a STRUCTURED call asks for its DTO.

Mirascope's default formatting mode is forced tool use (``tool_choice`` of type
``tool``, or ``any`` with several tools), and every concern has always used it.
Claude 5.5 models refuse it on Bedrock — reported 2026-10-08 on Sonnet 5.5 and
Opus 5.5, and probed the same day on Fable 5.1 (Fable 5 still accepts it): ``tool_choice: type "tool" and "any" are not supported for this
model`` — so with a 5.5 model configured every structured call 400s: the
coherence judge, the tetrad writers, every concern. JSON mode works on both
(it asks for the JSON in the reply instead), and it is the shape the framework
already uses where a structured call must think (`format_mode="json"`).

The mode is therefore chosen by MODEL at the provider, the way
`thinking_compat` chooses the thinking shape: a request that asked for forced
tool use, explicitly or by default, is sent in JSON mode to a model that cannot
take it. A request that asked for another mode (json, strict, parser) is left
alone. Selection is by model name with a learned fallback — if the heuristic
misses a future model, its first 400 teaches the process and the call is
re-encoded once.

What this does NOT decide: whether JSON mode is the better default for models
that accept both. It parses as reliably on a DTO-shaped call and costs less
prefill (`probe_format_mode_thinking.py`), but the framework's measured figures
were taken on forced tool use, so switching every model is a measurement, not
a compatibility fix.

**A JSON-mode call to such a model is also sent as a structured output**
(`output_config.format`, a JSON-schema constraint on the reply; since
2026-10-09). JSON mode alone asks for JSON and gets prose-shaped JSON back
often enough to cost whole calls: a host measured 32 parse re-asks in 80 cards
on Sonnet 5.5 (25 on `TransformationSketchDto`, 7 on `ViewSketchDto` —
trailing commas, invalid JSON), each a full extra generation on the
framework's parse ladder. The constraint removes the class; Bedrock takes it
through the client the framework uses on Sonnet 5, Sonnet 5.5 and Opus 5.5,
with every thinking shape the framework sends and with the real DTO schemas
(`tests/e2e/probe_structured_outputs.py`). Applied to the SAME models that
refuse forced tool use — the ones whose structured calls go in JSON mode in
the first place, explicitly (`format_mode="json"`) or by substitution — and
to no other: Sonnet 5 / Opus 5 took it too in the probe, but every judged
figure there was taken without it, so widening it is a measurement.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, get_origin

from anthropic.lib._parse._transform import transform_schema
from mirascope import llm
from mirascope.llm.formatting.format import Format
from pydantic import BaseModel

logger = logging.getLogger(__name__)

#: The mode substituted for forced tool use on a model that refuses it.
JSON = "json"

#: Model name -> True when it was LEARNED (from a 400) to refuse forced tool use.
_LEARNED: dict[str, bool] = {}

#: ``claude-<family>-<major>[-<minor>]``. The minor is one or two digits NOT
#: followed by another digit, so a date suffix is never read as a minor:
#: ``claude-haiku-4-5-20251001`` is 4.5, ``claude-sonnet-5`` is 5.0,
#: ``claude-sonnet-5-5`` is 5.5, and ``claude-3-5-sonnet`` does not match.
_FAMILY_VERSION = re.compile(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2})(?!\d))?")


def claude_version(model_name: str) -> Optional[tuple[int, int]]:
    """(major, minor) of a Claude 4+-style model name; None when unreadable."""
    match = _FAMILY_VERSION.search(model_name)
    if not match:
        return None
    return int(match.group(2)), int(match.group(3) or 0)


def claude_family(model_name: str) -> Optional[str]:
    """``sonnet`` / ``opus`` / ... of a Claude 4+-style model name."""
    match = _FAMILY_VERSION.search(model_name)
    return match.group(1) if match else None


def refuses_forced_tool_use(model_name: str) -> bool:
    """True when this model rejects ``tool_choice`` of type ``tool``/``any``."""
    if model_name in _LEARNED:
        return _LEARNED[model_name]
    version = claude_version(model_name)
    if version is None:
        return False
    # Probed 2026-10-08: Sonnet/Opus 5.5 and Fable 5.1 refuse; Fable 5 accepts.
    if claude_family(model_name) in ("fable", "mythos"):
        return version >= (5, 1)
    return version >= (5, 5)


def _forced_tool(format: Any) -> Any:
    """The formattable when `format` asks for forced tool use, else None.

    A bare DTO class resolves to Mirascope's default mode, which is ``tool``; a
    `Format` says its own mode. An `OutputParser` is never forced tool use.
    """
    if isinstance(format, Format):
        return format.formattable if format.mode == "tool" else None
    # A class, or a parameterised generic (`list[str]`), which is not a `type`
    # but resolves to the default mode exactly as one does.
    if isinstance(format, type) or get_origin(format) is not None:
        return format
    return None


def with_format_compat(model_name: str, format: Any) -> Any:
    """`format` as this model can take it. Pure; None passes through."""
    if format is None or not refuses_forced_tool_use(model_name):
        return format
    formattable = _forced_tool(format)
    if formattable is None:
        return format
    return llm.format(formattable, mode=JSON)


def learn_format_mode_from_error(
    model_name: str, format: Any, error: BaseException
) -> bool:
    """Record that this model refuses forced tool use. True if worth retrying once.

    Only when the failed request asked for forced tool use and the error says
    so; every other error returns False and surfaces unchanged.
    """
    if format is None or _forced_tool(format) is None:
        return False
    message = str(error)
    # The provider's text: 'tool_choice: type "tool" and "any" are not
    # supported for this model.' Matched on the forced types, so a 400 about
    # some other tool_choice field cannot move a capable model to JSON.
    if "tool_choice" not in message or "not supported" not in message:
        return False
    if '"tool"' not in message and '"any"' not in message:
        return False
    if refuses_forced_tool_use(model_name):
        # Already sent as JSON and it still failed — the mode is not the problem.
        return False
    _LEARNED[model_name] = True
    logger.warning(
        "Model %s rejected forced tool use; structured calls go in JSON mode for "
        "the rest of this process. Adjust format_compat if this is a naming gap.",
        model_name,
    )
    return True


def structured_output_format(model_name: str, format: Any) -> Optional[dict[str, Any]]:
    """The ``output_config.format`` for this request, or None when it gets none.

    Given the format AS RESOLVED for the model (after `with_format_compat`):
    a `Format` in JSON mode on a model whose structured calls go in JSON mode
    (`refuses_forced_tool_use`) gets a ``json_schema`` constraint on the reply;
    everything else — forced tool use, parser mode, a primitive or an output
    parser, a model that keeps forced tool use — gets None and goes as it
    always did. The schema is the SDK's own strict transform of the DTO
    (``additionalProperties: false`` on every object, the constraints the
    grammar cannot hold moved into descriptions), the same one
    ``messages.parse`` would send.
    """
    if format is None or not refuses_forced_tool_use(model_name):
        return None
    if not isinstance(format, Format) or format.mode != JSON:
        return None
    formattable = format.formattable
    if not (isinstance(formattable, type) and issubclass(formattable, BaseModel)):
        return None
    return {"type": "json_schema", "schema": transform_schema(formattable)}


def reset_learned_format_modes() -> None:
    """Test seam — the learned map is process-global by design."""
    _LEARNED.clear()
