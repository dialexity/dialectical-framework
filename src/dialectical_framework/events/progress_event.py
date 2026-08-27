"""A progress signal: work is happening that has produced no graph node yet.

WHY A SECOND EVENT TYPE AND A SECOND CHANNEL
============================================
`GraphEvent` carries an `Effect`, and `Effect` is documented as *a single atomic
graph mutation* — it names a node or an edge, carries the values that changed, and
keeps `previous` so the mutation can be undone. Every message on the `sid` channel
means "the graph is now different".

`probe_explore_progress.py` measured a stretch where that contract has nothing to
say: during `explore`'s transformation phase there were **45.6s and 33 provider
calls with no graph write at all**, because a Transformation is only written once
its whole four-call generation chain has finished. The honest signal in that window
is "4 of 6 transformations generated" — which is not a mutation, names no node, and
cannot be undone. Forcing it into an `Effect` (a `progress` member of `EffectType`,
`node=None`) would make `Effect` mean two different things and would hand every
existing subscriber a message whose `node` is `None`.

So progress rides a **separate channel**, `f"{sid}:progress"`. The consequence that
matters is the reason this shape was chosen: a host that knows nothing about
progress keeps working *exactly* as it does today, because nothing new appears on
the channel it subscribes to. Live progress is opt-in — one extra `subscribe_progress`
next to the existing `subscribe` — and the cost of not opting in is the status quo,
not a crash.

READING `done` / `total`
=======================
`total` GROWS as work is discovered. Transformation counts are not known up front:
`explore` learns how many tetrads an edge pair owes only after Phase 1 has extracted
its candidates, and it processes pairs concurrently. So a host must treat `total` as
the current best estimate and re-read it on every event, never cache the first one.
A denominator that rises is the truthful rendering of lazily-discovered work.

`done` counts steps that have FINISHED; `detail` describes the step that just
STARTED. So the pair reads as "3 of 24 done, now working on <detail>" — which is
why `done` never reaches `total` during the run. The `final=True` event published
when the scope closes carries the count that actually completed, which is lower
than `total` when steps failed. That is deliberate: 22 of 24 is a fact worth
seeing, and rounding it up to 24 would hide a partial build.

`key` distinguishes concurrent scopes for the same `stage` — two wheels deepened at
once each report `stage="transformation"`, and without `key` their counts would
interleave into one nonsensical bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Appended to the `sid` to form the progress channel. A constant because both the
#: publisher and every subscriber must agree on it, and a typo in either would look
#: exactly like "this stage reports no progress".
PROGRESS_CHANNEL_SUFFIX = ":progress"


def progress_channel(sid: str) -> str:
    """The channel progress for `sid` is published on. Never equal to `sid` itself."""
    return f"{sid}{PROGRESS_CHANNEL_SUFFIX}"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Work in flight that has not yet produced a graph mutation.

    Fields:
        sid: Scope, same meaning as on `GraphEvent`.
        stage: Which phase is running, e.g. "transformation". Stable enough for a
            host to switch on.
        key: Distinguishes concurrent scopes within one stage (e.g. the wheel's
            short hash). None when the stage cannot run twice at once.
        done: Steps finished so far.
        total: Steps expected so far — a moving target, see the module docstring.
        detail: Human-readable description of the step that just started.
        final: True on the single event published when the stage ends. A host can
            clear its spinner on this without waiting for `done == total`, which
            may never happen.
    """

    sid: str
    stage: str
    done: int
    total: int
    detail: str
    timestamp: float
    key: Optional[str] = None
    final: bool = False
