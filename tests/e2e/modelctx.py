"""
Model switching for the bench.

Three models coexist in a run — the ARM's tier model, the USER SIMULATOR's
fixed model, and the JUDGE's model — and all three reach the provider through
`settings.ai_model`, which `use_brain` reads at call time. `using_model` scopes
the choice with `using_settings` (`dialectical_framework.settings_context`), so
it holds for the calls inside the `with` and the tasks they start, and for
nothing else.

Until 2026-10-07 it overrode the container's one global settings slot, which
made "bench work must not run concurrently" a correctness rule: two interleaved
cells answered on each other's model. Settings are per-context now, so that
rule is gone; the bench still runs its cells sequentially for its own reasons
(Memgraph, provider throttling), not for this one.
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
    """Run the calls inside on `model` (and the tasks they start).

    Built from the CURRENT settings, so an enclosing `using_settings` (or
    another `using_model`) keeps its other values; the outer choice is
    restored on exit.
    """
    from dialectical_framework.settings_context import using_settings

    # Both models: a bench tier means "this model runs everything", so a
    # `DIALEXITY_REASONING_MODEL` in the local .env must not leak into a cell.
    # The bench's OWN knob, `DIALEXITY_E2E_REASONING_MODEL`, is the one way to
    # split them on purpose — explicit, printed in the run header and recorded
    # on every cell (`RunRecord.reasoning_model`), so an archive never holds a
    # two-model arm that reads as a one-model one.
    with using_settings(
        container.settings().model_copy(
            update={"ai_model": model, "reasoning_model": bench_reasoning_model()}
        )
    ):
        yield
