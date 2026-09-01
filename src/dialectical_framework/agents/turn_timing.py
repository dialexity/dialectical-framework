"""Where a conversational turn's wall clock went, split on the line the person feels.

Deliberately NOT in `stream_events.py`: nothing here is a member of the
`StreamEvent` tagged union, and adding non-events to that module makes the union
ambiguous to read.

WHY THIS EXISTS
===============
`tests/e2e/probe_reply_path_latency.py` had to ESTIMATE the reply-path share by
regressing 187 archived runs' wall clock onto their tool-call histograms, because
no per-turn duration was recorded anywhere — `RunRecord.duration_s` covers a whole
cell of several sessions. That estimate came out at 81% (strong) / 88% (weak) of
run wall-clock spent between the person's message and their reply existing, with
`anchor` at ~229s and `explore` at ~140s per call. Useful, and not a measurement:
a regression cannot separate two tools that always co-occur, and the weak tier's
condition number (36.6) says it did not.

These types make the next run measure it. Populated by `ConversationFacilitator`
(per tool round) and assembled by `Advisor` (which alone knows where the reply was
handed over), then recorded onto `TurnRecord` by the e2e driver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True, slots=True)
class ToolRound:
    """One round of the agentic loop: which tools ran, and how long the round took.

    Wall clock per ROUND, not per tool, and the plural `names` is the warning:
    Mirascope's `execute_tools()` gathers a round's calls and runs them
    concurrently, so a round with three calls took as long as its SLOWEST call,
    never as long as their sum. A per-tool number is recoverable only from
    single-call rounds. Most rounds are single-call — but a reader should not have
    to assume that, so the shape of the data says it instead.
    """

    names: tuple[str, ...]
    seconds: float
    #: Of `seconds`, how many bought nothing: `use_brain` backoff sleep plus the
    #: attempts that raised before it. Recorded because r26 wrote up `anchor` at a
    #: 282.8s median as the tool's price when four of its ten rounds were ~40s of
    #: work plus a 750s ParseError ladder — a number nothing in the archive could
    #: have contradicted. `seconds` stays the person's real wait; this says how
    #: much of that wait was the framework failing and waiting.
    retry_seconds: float = 0.0
    #: How many attempts were retried inside this round (0 = clean).
    retry_count: int = 0

    @property
    def is_attributable(self) -> bool:
        """True when this round's seconds belong to exactly one tool."""
        return len(self.names) == 1

    @property
    def working_seconds(self) -> float:
        """`seconds` with retry waste removed — the tool's cost when it works.

        Clamped at zero for the same reason as `TurnTiming.generation_s`: the two
        quantities come from different clocks (one around the round, one summed
        from inside nested calls), and a negative duration in a record looks like
        data.
        """
        return max(0.0, self.seconds - self.retry_seconds)


@dataclass(frozen=True, slots=True)
class TurnTiming:
    """A turn's seconds, split into what the person waited for and what they did not.

    `reply_path_s` is the interval between their message arriving and their reply
    existing: the per-turn context re-render, PLUS model generation, PLUS every
    tool round the model elected — because `Advisor.chat` refreshes the prompt and
    then awaits `submit()` before it holds any text at all.

    `off_path_s` is work done after the reply was handed over — the decision
    repair and the pathway seam. `Advisor` already treats that boundary as load
    bearing ("so the person's reply is never delayed by the repair"), and this is
    that same boundary made observable rather than asserted in a comment.

    The invariant worth preserving when adding fields:
    `TurnRecord.duration_s == reply_path_s + off_path_s`, which held to 0%
    unexplained overhead across all 16 turns of `timing-check-building`. So a new
    reply-path cost belongs INSIDE `reply_path_s` as a component (like
    `tool_seconds`), never as a third addend — otherwise that check silently
    starts reporting the new field as harness overhead.
    """

    reply_path_s: float
    off_path_s: float
    tool_rounds: tuple[ToolRound, ...] = field(default_factory=tuple)
    #: Reply-path seconds that bought nothing: retry backoff plus the attempts
    #: that raised, anywhere under the submit — tool rounds AND the model's own
    #: generation. A COMPONENT of `reply_path_s`, never a third addend.
    #:
    #: Covers only the submit. The off-path repair runs outside it, so a retry
    #: there is in `off_path_s` and not here; and in the streaming path the chunk
    #: loop past its FIRST chunk is uncovered, which cannot retry once tokens flow.
    retry_seconds: float = 0.0
    #: Attempts retried under the submit (0 = the turn ran clean).
    retry_count: int = 0
    #: Reply-path seconds spent re-reading the graph into the system prompt. A
    #: COMPONENT of `reply_path_s`, not an addition to it. Recorded separately
    #: because it is the one reply-path cost the framework imposes on every turn
    #: whether the model asks for anything or not, which makes it the first thing
    #: to check if turns get slower for no visible reason.
    context_render_s: float = 0.0
    #: When the person first had something on screen, measured from their message
    #: arriving. A PREFIX of `reply_path_s`, not a component and certainly not an
    #: addend: the same clock, stopped earlier, so the `duration_s ==
    #: reply_path_s + off_path_s` check above is untouched.
    #:
    #: `None` on every non-streaming turn, where the question does not apply — the
    #: reply exists all at once, so `reply_path_s` already answers it.
    #:
    #: Read it as "when did the waiting stop looking like nothing happening", NOT
    #: as time-to-first-token. On a turn where the model calls a tool before
    #: narrating — the Advisor's contracted behaviour — this lands after the whole
    #: tool round. How often that happens is UNMEASURED: it needs a count of text
    #: deltas before the first `ToolStart`, which needs the streaming path, and no
    #: probe has taken it. The prefill-sensitive figure lives
    #: on `CallRecord.first_token_seconds`, per round.
    first_delta_s: Optional[float] = None

    @property
    def total_s(self) -> float:
        return self.reply_path_s + self.off_path_s

    @property
    def tool_seconds(self) -> float:
        """Reply-path seconds spent inside tool rounds."""
        return sum(r.seconds for r in self.tool_rounds)

    @property
    def tool_retry_seconds(self) -> float:
        """Of `tool_seconds`, how many bought nothing.

        A component of a component: `tool_seconds` ⊂ `reply_path_s`, and this ⊂
        `tool_seconds`. Nothing here is ever an addend of the turn total, so the
        `duration_s == reply_path_s + off_path_s` invariant is untouched.
        """
        return sum(r.retry_seconds for r in self.tool_rounds)

    @property
    def generation_retry_seconds(self) -> float:
        """Retry waste that happened outside any tool round.

        Backoff during the model's OWN generation is reply-path cost the same as
        backoff inside `anchor`, and it lands in `generation_s` where it looks
        like the model thinking. r26 had one turn shaped exactly like that —
        644.1s of residual with zero tool calls — which nothing at the time
        could have distinguished from a slow reply.

        Clamped: the two figures come from one shared accumulator and its nested
        children, so the subtraction cannot go negative unless a caller assembles
        rounds and totals from different turns.
        """
        return max(0.0, self.retry_seconds - self.tool_retry_seconds)

    @property
    def generation_s(self) -> float:
        """Reply-path seconds that were neither tool rounds nor the re-render.

        Clamped at zero: these intervals are measured by separate clocks around
        nested awaits, so a pathological scheduler could in principle make the
        subtraction negative, and a negative duration in a record is worse than a
        zero because it looks like data.
        """
        return max(0.0, self.reply_path_s - self.tool_seconds - self.context_render_s)

    def format_rounds(self) -> list[str]:
        """Rounds as `"anchor:229.4s"` / `"anchor+explore:301.2s"` strings.

        Matches how `TurnRecord.tool_outcomes` and `grounding_args` already record
        per-call facts, so the archive keeps one idiom. The `+` joins a
        concurrent round, which is exactly the case where the seconds must NOT be
        read as belonging to either name alone.
        """
        return [f"{'+'.join(r.names)}:{r.seconds:.1f}s" for r in self.tool_rounds]

    def format_retry_rounds(self) -> list[str]:
        """The same rounds, in the same order, carrying only their retry waste.

        A PARALLEL list rather than an annotation inside `format_rounds()`:
        readers already parse those strings by splitting on the last colon, and
        widening the format would break them silently. Index i here is the waste
        inside index i there, so `working = rounds[i] - retries[i]`.
        """
        return [f"{'+'.join(r.names)}:{r.retry_seconds:.1f}s" for r in self.tool_rounds]
