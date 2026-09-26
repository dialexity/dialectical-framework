"""
WHEN the Advisor builds structure, as one parameter — and WHETHER it writes at
all, as another.

The axis that costs a person minutes on a turn is building: the four build tools
(`ingest`, `anchor`, `explore`, `deepen`) are each a pipeline of provider calls.
Recording a confirmed decision is one call of a few seconds, discarding is free,
and reading costs nothing. So the question a host answers with this parameter is
not "may it write" but "when may it build":

    ON_ELECTION  the Advisor as shipped: the build tools are wired, the model
                 builds mid-conversation whenever it elects to, and the closing
                 seam weaves what it left unwoven off the turn. The Navigator's
                 advisory register and the Advisor from scratch.
    ON_CONSENT   no build tool on the turn, so a reply is one graph read plus
                 the model. The understanding still grows — on the person's
                 word, between turns: what they ask to have written down
                 (`note`) is planted as a tension after the reply, and a
                 decision they confirm starts the same off-turn weave the
                 election policy gets. The graph never changes while they wait,
                 and never without their say-so.
    NEVER        nothing is built, on the turn or off it. A conversation over a
                 graph something else finished, or a graph nobody may grow.

`records` is the other parameter, and it is a PERMISSION rather than a policy:
whether this seat may write decisions and retractions at all (`record_decision`,
`discard`, `audit_feasibility`, and the closing seam that records a decision the
model did not). A seat without it reads and nothing else — a second reader on
someone else's Case, a shared or public view, a support agent — and the person
must be told by the host that nothing said there is written down. It is
independent of the policy on one side only: a building head without it is
coherent (it builds what the model elects and keeps no ledger), but ON_CONSENT
without it has no consent to act on — both triggers are writes — so that
combination raises rather than silently meaning NEVER.

Enforced by the TOOLSET (what the head is never handed it cannot reach) and, for
the framework's own initiative, by the closing seam — never by prompt. The prompt
is told which surface it is on so it does not spend turns reaching for what it
does not have, but the prompt is not what stops it: measured across the bench,
tool-election instructions do not hold (`anchor` 6/6, `explore` 2/6, `deepen`
0/6 under the full prompt), so a "prefer reading" register would make the
latency stochastic rather than bounded.

The prompt's render shape is DERIVED from the tool names, not from this enum
(`system_prompts.system_prompt`), so the two cannot disagree — this module is
the constructor's vocabulary, and `_BUILD_TOOL_NAMES` / `_CONSENT_TOOL_NAMES` /
`_WRITE_TOOL_NAMES` in `system_prompts.py` are the prompt's.
`tests/test_advisor_build_policy.py` holds them together.
"""

from __future__ import annotations

from enum import Enum


class BuildPolicy(str, Enum):
    ON_ELECTION = "on_election"
    ON_CONSENT = "on_consent"
    NEVER = "never"

    @property
    def on_turn(self) -> bool:
        """Whether the build tools are wired, so the model may build mid-turn."""
        return self is BuildPolicy.ON_ELECTION

    @property
    def off_turn(self) -> bool:
        """Whether the closing seam may plant and weave after the reply."""
        return self is not BuildPolicy.NEVER
