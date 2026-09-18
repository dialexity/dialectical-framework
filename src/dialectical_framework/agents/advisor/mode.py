"""
The Advisor's three surfaces, as one parameter.

The axis is BUILDS STRUCTURE versus DOES NOT, not read versus write. What costs
a person minutes on a turn is the four build tools (`ingest`, `anchor`,
`explore`, `deepen`), each a pipeline of provider calls; recording a confirmed
decision is one call of a few seconds, and discarding is free. So the fast
surface is not the one that cannot write — it is the one that cannot build, and
it still records what the person decides.

    FULL        the Advisor as shipped: builds silently, on and off the turn,
                and records decisions. The consulting chat, and the
                Explorer's advisory register when pinned to a nexus.
    CONSULTANT  a conversation over a graph that already exists: reads it,
                records decisions and grounds them on the pathways it finds,
                may retract and may score a pathway's feasibility on request,
                never builds — not on the turn and not off it. The closing seam
                still runs, so a person who says "write that down" is written
                down; the weave that would otherwise follow does not start.
    VIEW        reads and nothing else: `sync`, `inspect_node`, `read_digest`.
                For a seat that is not the one doing the work — a second reader
                on someone else's Case, a shared or public view, a support
                agent. The closing seam declines, so nothing said here is
                recorded, and the person must be told so by the host.

Enforced by the TOOLSET (what the head is never handed it cannot reach) and, for
the framework's own initiative, by the closing seam — never by prompt. The
prompt is told which surface it is on so it does not spend turns reaching for
what it does not have, but the prompt is not what stops it: measured across the
bench, tool-election instructions do not hold (`anchor` 6/6, `explore` 2/6,
`deepen` 0/6 under the full prompt), so a "prefer reading" register would make
the latency stochastic rather than bounded.

The prompt's render shape is DERIVED from the tool names, not from this enum
(`system_prompts.system_prompt`), so the two cannot disagree — this module is
the constructor's vocabulary, and `_BUILD_TOOL_NAMES` / `_WRITE_TOOL_NAMES` in
`system_prompts.py` are the prompt's. `tests/test_advisor_modes.py` holds them
together.
"""

from __future__ import annotations

from enum import Enum


class AdvisorMode(str, Enum):
    FULL = "full"
    CONSULTANT = "consultant"
    VIEW = "view"

    @property
    def builds(self) -> bool:
        """Whether this surface may add structure to the graph, on or off the turn."""
        return self is AdvisorMode.FULL

    @property
    def records(self) -> bool:
        """Whether this surface writes decisions — its own tool, or the closing seam."""
        return self is not AdvisorMode.VIEW
