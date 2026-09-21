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

import os
from contextlib import contextmanager
from typing import Iterator


def bench_reasoning_model() -> str | None:
    """The bench's deliberate two-model split, or None for "the tier runs everything".

    Read from `DIALEXITY_E2E_REASONING_MODEL` and NOT from the framework's own
    `DIALEXITY_REASONING_MODEL`, so a local .env can never split a bench arm
    across two models without the run header and every cell saying so.
    """
    return os.getenv("DIALEXITY_E2E_REASONING_MODEL") or None


@contextmanager
def using_model(container, model: str) -> Iterator[None]:
    """Temporarily point DI settings at `model`.

    `settings` is a `Dependency` provider that must stay satisfied, so the
    restore path re-overrides with the previous instance instead of leaving it
    unset (a bare reset would break every later injection).
    """
    previous = container.settings()
    # Both models: a bench tier means "this model runs everything", so a
    # `DIALEXITY_REASONING_MODEL` in the local .env must not leak into a cell.
    # The bench's OWN knob, `DIALEXITY_E2E_REASONING_MODEL`, is the one way to
    # split them on purpose — explicit, printed in the run header and recorded
    # on every cell (`RunRecord.reasoning_model`), so an archive never holds a
    # two-model arm that reads as a one-model one.
    container.settings.override(
        previous.model_copy(
            update={"ai_model": model, "reasoning_model": bench_reasoning_model()}
        )
    )
    try:
        yield
    finally:
        container.settings.reset_override()
        container.settings.override(previous)
