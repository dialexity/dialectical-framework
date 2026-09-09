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

`done` counts steps that have been ANNOUNCED; `detail` describes the step that just
started. So the pair reads as "3 announced, now working on <detail>" — **not** "3
finished". The publisher increments after publishing, so a step that fails after
announcing stays counted: a run whose last step dies still closes at 24/24. Read a
shortfall as informative (`22/24` means two declared steps were never reached) and a
full count as uninformative about success — failures arrive as errors in the report,
never as a short count. Rounding the closing count up to `total` would hide the
informative half, so it is deliberately not done.

**Do not render `done/total` as a completion bar.** Two separate reasons, both
measured on the real path rather than reasoned about. The denominator GROWS (above),
and because growth is additive the counter DOES reach it mid-run — whenever the last
declared step finishes before the next site declares one. A 120 KB ingest sat at 19/19
for 1.9s at 63% of the wall with 34 `note` events streaming against a full bar before
it dropped back to 19/20 (`probe_ingest_progress.py`). An earlier version of this
paragraph claimed `done` never reaches `total` during a run; that claim was false and a
host built on it would show a finished bar a third of the way through. Render this as
"step N, more coming" and clear on `final`.

`key` distinguishes concurrent scopes for the same `stage` — two wheels deepened at
once each report `stage="transformation"`, and without `key` their counts would
interleave into one nonsensical bar.

WHY THERE IS A THIRD KIND OF EVENT (`note`)
===========================================
A step event says "this is starting" and moves `done`. That is the whole vocabulary,
and it has one blind spot, measured on the real path: **N single provider calls that
are gathered, so they all start at the same instant.** `SourceDigest` reading a 120 KB
source in four parts announced all four inside the same 0.4s and then said nothing for
**25.4s** — the widest hole in that run, and the one place where no graph effect flows
either, because a part reading writes nothing (`probe_ingest_progress.py`). There is no
chain to subdivide: each part IS one call.

What is left to say is that a part came BACK, and the parts return at different times
(11.2s, 12.6s, 13.0s on that run). So `note=True` marks an event that carries no claim
about steps: same `done`, same `total`, a `detail` describing what has landed. A host
refreshes its label and leaves its bar alone.

Notes are deliberately not a general facility — see `note_progress` in
`utils/progress.py` for the one condition that earns one.
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
        done: Steps ANNOUNCED so far, which is not the same as finished — see the
            module docstring before rendering this as a completion count.
        total: Steps expected so far — a moving target, see the module docstring.
        detail: Human-readable description of the step that just started — or, when
            `note` is set, of something that just finished. **EMPTY on the `final`
            event**, always: see `final` below.
        final: True on the single event published when the stage ends. A host can
            clear its spinner on this without waiting for `done == total`, which
            may never happen. Its `detail` is the empty string, because the only
            thing this event knows that the fields do not already say would be a
            success claim, and `done` cannot back one (above). It carried
            `f"{stage} finished"` for a while, which was `stage` repeated as prose
            and leaked internal stage names — `"synthesis finished"` reached a
            person. The closing label belongs to the host, which has `stage`, `key`,
            `done` and `total` to write it from.
        note: True on an event that is NOT a step: `done` and `total` are the same
            values the previous event carried, so a host refreshes its label and
            leaves its bar where it is. Counting notes as steps would make `done`
            overshoot `total` — see the module docstring for what they are for.
    """

    sid: str
    stage: str
    done: int
    total: int
    detail: str
    timestamp: float
    key: Optional[str] = None
    final: bool = False
    note: bool = False
