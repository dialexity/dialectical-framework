"""
Settings per request: a ContextVar over a process base, the way `sid` works.

WHY
===
The container's `settings` used to be ONE slot (`providers.Dependency`, filled by
`DialecticalReasoning.setup`). A host serving many people from one process could
only change a person's settings with `container.settings.override(...)`, which
swaps the slot for EVERY call in flight: two concurrent requests answered on each
other's model, thinking level, word limits. The first app met it with a
process-wide lock around every framework call, one card at a time (handoff from
alsotrue-app, 2026-10-06).

Now `settings` resolves through `get_current_settings()` on every read: the
innermost `using_settings(...)` of the current asyncio context, else the base
`setup()` installed. Every `Provide[DI.settings]` and every `SettingsAware.settings`
read goes through it unchanged.

    from dialectical_framework.settings_context import using_settings

    with using_settings(base.model_copy(update={"ai_model": person_model})):
        reply = await consultant.chat(text)      # this request, this model

`create_task` / `gather` copy the context, so the framework's own fan-out (best-of-N
draws, the coherence judge, the off-turn weave) runs on the settings of the turn
that started it. Composes with `scope(sid)`; the two stay separate on purpose
(`scope` is whose data, this is how to reason).

TWO TIERS, as the code already treats them (see `Settings`):
- read at call time, per request: `ai_model`, `reasoning_model`, everything read
  through `SettingsAware.settings` (word limits, thinking level, the Advisor's
  floors and caps, the audit switches);
- read ONCE per process, from the base only: `graph_db_*` (the connection is a
  Singleton), `llm_connect_timeout_s` and `llm_read_timeout_s` (the provider is
  registered once), `effect_log_dir` (installed in `setup`). A value for these inside
  `using_settings` has no effect, by construction, not by accident.

`container.settings.override(...)` RAISES: it would replace this provider with one
fixed object and silently put the whole process back on a single settings slot.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dialectical_framework.settings import Settings

_base: Optional["Settings"] = None
_current: contextvars.ContextVar[Optional["Settings"]] = contextvars.ContextVar(
    "current_settings", default=None
)


def set_base_settings(settings: Settings) -> None:
    """The process default, installed by `DialecticalReasoning.setup()`. A later
    `setup()` replaces it, as a second container always replaced the first."""
    global _base
    _base = settings


def get_base_settings() -> Settings:
    """The process base. Raises when nothing called `setup()` — an unconfigured
    process must fail loudly, not run on a default nobody chose."""
    if _base is None:
        raise RuntimeError(
            "No settings installed: call DialecticalReasoning.setup(settings) "
            "once per process before using the framework."
        )
    return _base


def get_current_settings() -> Settings:
    """The innermost `using_settings` of this context, else the base. The DI
    container's `settings` provider calls this on every resolution."""
    return _current.get() or get_base_settings()


class _SettingsContextManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> Settings:
        self._token = _current.set(self._settings)
        return self._settings

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token is not None:
            _current.reset(self._token)


def using_settings(settings: Settings) -> _SettingsContextManager:
    """Run framework calls inside this context on `settings` (HOST LAYER).

    Async-safe: each asyncio task sees only what was set in its own context;
    tasks created inside inherit it; code outside sees the base. Nesting: the
    innermost wins and the outer is restored on exit. An explicit
    `use_brain(ai_model=...)` still wins over both. Build the value from the base
    (`get_base_settings().model_copy(update=...)`) so per-request choices do not
    drop the deployment's own values.
    """
    return _SettingsContextManager(settings)
