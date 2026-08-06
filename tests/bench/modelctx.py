"""
Model switching for the bench.

Three models coexist in a run — the ARM's tier model, the USER SIMULATOR's
fixed model, and the JUDGE's model — and all three reach the provider through
the same DI singleton (`settings.ai_model`), which `use_brain` reads at call
time. So the only honest way to keep them apart is to flip the setting around
each call.

Consequence, and it is a correctness requirement rather than a performance
note: **bench work must not run concurrently.** The container is
process-global; two interleaved cells would silently answer on each other's
model.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def using_model(container, model: str) -> Iterator[None]:
    """Temporarily point DI settings at `model`.

    `settings` is a `Dependency` provider that must stay satisfied, so the
    restore path re-overrides with the previous instance instead of leaving it
    unset (a bare reset would break every later injection).
    """
    previous = container.settings()
    container.settings.override(previous.model_copy(update={"ai_model": model}))
    try:
        yield
    finally:
        container.settings.reset_override()
        container.settings.override(previous)
