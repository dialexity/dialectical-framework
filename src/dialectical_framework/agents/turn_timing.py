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
from enum import Enum
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


class ClosingOutcome(str, Enum):
    """What the decision seam concluded about a turn, off the reply path.

    Recorded because the seam's own firing was INVISIBLE and a round was decided
    without it. `feasibility-offturn` measured one turn where the person waited
    284.5s, 95% of the reply path, on `deferred_wait_s` — the previous turn's
    off-path work not being finished yet. The leading explanation was that the
    repair seam had written a decision the model never recorded and scheduled the
    weave itself, and that explanation could not be checked: nothing archived
    whether the seam fired, and the log line it writes was not captured
    (`grep -c "left unrecorded"` over the run's output returned 0).

    The prior round made the more expensive version of the same mistake. It ruled
    the ~300s tail out of being the deferral by ORDERING — the run's only
    `record_decision` fired at t5, so no decision existed when the turn began —
    and that argument read `tool_calls`, which cannot see the framework's own
    writes. This seam records a decision the model did not, so an absence in
    `tool_calls` is evidence about the MODEL's elections and never about what the
    framework did on its own. Hence a field rather than an inference.

    `None` on `TurnTiming.closing` is a fifth state and the one to keep separate:
    the seam did not run, or the turn predates this field. Every member here is a
    positive claim about a seam that ran to a conclusion.

    `Advisor(read_only=True)` is a third way into that `None`, and the reason it
    gets no member of its own: the seam declines before the classifier looks, so
    nothing was concluded about whether anyone was closing. Reading such a turn as
    `NO_CLOSING` would turn "nobody asked" into "the answer was no".
    """

    #: The classifier read the exchange and found no decision being closed. The
    #: ordinary outcome, and the reason this is not a boolean: "the seam did not
    #: fire" and "the seam ran and there was nothing to do" are different facts.
    NO_CLOSING = "no_closing"
    #: The model called `record_decision` itself. The seam then only grounded the
    #: record on a pathway and scheduled the weave — it repaired nothing. Measured
    #: across the archive, this is the LARGER population (50 A2 cells recorded
    #: without `explore` against 48 with both), so reading it as a repair would
    #: overstate the seam's reach several times over.
    MODEL_RECORDED = "model_recorded"
    #: The person confirmed a decision, the model did not write it, and the seam
    #: wrote it. The case the seam exists for, and the one whose rate no prompt
    #: change ever moved.
    REPAIRED = "repaired"
    #: The seam ran and did not deliver what it set out to. Five ways in: it
    #: raised; the classifier returned nothing; the classifier said the person
    #: confirmed but gave no question or stance to write; the record write handed
    #: back no hash; or the model had recorded and the pathway read raised.
    #:
    #: Fail-soft, so the person's reply was unaffected — and a turn that failed
    #: here is NOT a turn with no closing. Pooling the two would report the seam
    #: as finding nothing to do when it in fact broke, which is the shape of the
    #: one unexplained case in the archive: `claim2-weak-r8-pathways`/wobble_b
    #: closed on an unambiguous confirmation and recorded nothing, and the cause
    #: is STILL unknown because nothing captured what its `except` blocks saw.
    #:
    #: It WINS over the branch label deliberately. What the field answers is what
    #: `off_path_s` bought, and on all five paths it bought nothing.
    FAILED = "failed"


class DeferralOutcome(str, Enum):
    """Whether a turn left off-path work in flight, which is what the NEXT turn pays.

    `deferred_wait_s` is charged to the turn that WAITS, so a large one is a fact
    about some earlier turn and the archive could not say which. This names it at
    the source.

    Distinguishing `STARTED` from `JOINED` is the whole point rather than
    bookkeeping: the seam is single-flight, so a closing that arrives while the
    weave is running queues onto the task instead of starting one. If turn 3
    JOINED, the work turn 4 waits on may have been started by turn 2, and an
    instrument that recorded only "work is in flight" would attribute it to the
    wrong turn — the same class of error as the ordering argument above.
    """

    #: No decision was waiting on a pathway, so nothing was scheduled. Weaving
    #: anyway would leave a better graph behind that no record points at.
    NOTHING_TO_DEFER = "nothing_to_defer"
    #: This turn created the task. The seconds a later turn waits start here.
    STARTED = "started"
    #: A task was already running; this closing was queued onto it, and the work
    #: in flight is NOT this turn's alone. Should be UNREACHABLE from a turn:
    #: both turn loops settle deferred work before submitting, so the task is
    #: done by the time the seam runs. Seeing it in an archive is therefore
    #: evidence about the host — two turns overlapping on one sid, which the
    #: one-writer-per-sid contract forbids — and not about the weave.
    JOINED = "joined"
    #: There was work to defer and no running loop to defer onto, so the closing
    #: kept its pre-deferral behaviour. Recorded rather than collapsed into
    #: `NOTHING_TO_DEFER`, which would claim there was nothing to do.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TurnTiming:
    """A turn's seconds, split into what the person waited for and what they did not.

    `reply_path_s` is the interval between their message arriving and their reply
    existing: the per-turn context re-render, PLUS model generation, PLUS every
    tool round the model elected — because `Advisor.chat` refreshes the prompt and
    then awaits `submit()` before it holds any text at all.

    `off_path_s` is work done after the reply EXISTS — the decision repair and
    the pathway seam. `Advisor` already treats that boundary as load bearing
    ("so the person's reply is never delayed by the repair"), and this is that
    same boundary made observable rather than asserted in a comment.

    Read "off path" as off the GENERATION path, not necessarily off the person's
    clock, and which one you get depends on the entry point:

    - `chat_stream()` really does hand the reply over first: the chunks are
      already on screen, so these seconds are genuinely free.
    - `chat()` does NOT. It cannot return until the repair finishes, so its
      `off_path_s` is time the caller spends blocked with the reply in hand but
      undelivered. The measured worst case is a 387.7s repair on a turn whose
      reply took 14.3s (see the comment above the repair in `Advisor.chat_stream`).

    Both entry points populate this field identically, so an archive mixing them
    cannot be read as "seconds the person did not wait" without first checking
    which call produced each turn. `tests/e2e` benches all use `chat()`.

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
    #: Reply-path seconds spent waiting for the PREVIOUS turn's off-path work to
    #: finish before this turn could start. A COMPONENT of `reply_path_s`, not an
    #: addend.
    #:
    #: Usually 0.0, and that is the design rather than luck: the Advisor defers
    #: pathway construction off the turn and the person's own think-time absorbs
    #: it. This field is what the deferral costs when it does NOT — the person
    #: replied before the weave finished, and the one-writer-per-sid contract
    #: makes waiting the only correct answer (two concurrent writers on one sid
    #: produce duplicate nodes and half-built containers).
    #:
    #: Read it as the honest price of the deferral. A run where this is large on
    #: many turns means the weave is not fitting in the gaps and belongs behind a
    #: setting, not that the timing is wrong.
    deferred_wait_s: float = 0.0
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
    #: as time-to-first-token.
    #:
    #: This used to warn that on a turn where the model calls a tool before
    #: narrating — the Advisor's contracted behaviour — the figure lands after the
    #: whole tool round, and that how often that happens was UNMEASURED. Measured
    #: now, and the warning is CONDITIONAL on a setting it never named
    #: (`probe_first_delta.py`, 2026-09-02). Model text did indeed never precede the
    #: first `ToolStart` (0 of 3 tool-electing turns, so the premise holds — though
    #: 0/3 only bounds narration-first below ~63% one-sided, it does not measure it). But this
    #: field is stamped on the first Text **or** Thinking chunk, and with
    #: `DIALEXITY_THINKING_LEVEL` set it read 1.3–3.7s on those very turns, tracking
    #: `ThinkingDelta`, while their first TEXT was 45.7–66.8s. So:
    #:
    #: - thinking ON — this is a genuine ~2s "something is happening", every turn
    #:   shape, and the old warning does not apply;
    #: - thinking OFF (`thinking_level` defaults to `None`) — it collapses onto first
    #:   text and the old warning is exactly right, tool round included.
    #:
    #: Never quote it without saying which. The prefill-sensitive figure lives on
    #: `CallRecord.first_token_seconds`, per round.
    first_delta_s: Optional[float] = None
    #: What the decision seam concluded, off the reply path. See `ClosingOutcome`.
    #: `None` = the seam did not run to a conclusion, or the turn predates this
    #: field — never "nothing happened", which is `NO_CLOSING`.
    #:
    #: This is not seconds, and it belongs here anyway: it says what `off_path_s`
    #: was SPENT ON, and this class already documents that boundary as "the
    #: decision repair and the pathway seam". A reader holding the seconds without
    #: it can see that a turn spent 300s after the reply and not which of four
    #: things it was doing.
    closing: Optional[ClosingOutcome] = None
    #: Whether this turn left off-path work in flight, and whether it started it.
    #: See `DeferralOutcome`. `None` = the seam did not reach the scheduler.
    #:
    #: Read together with the NEXT turn's `deferred_wait_s`: that field says a
    #: person waited, this one says which turn's closing they were waiting for.
    deferral: Optional[DeferralOutcome] = None

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
        """Reply-path seconds that were none of the accounted-for components.

        Subtracts the tool rounds, the re-render and the deferred-work wait, so
        this stays "the model thinking" rather than quietly absorbing whatever
        component was added last.

        Clamped at zero: these intervals are measured by separate clocks around
        nested awaits, so a pathological scheduler could in principle make the
        subtraction negative, and a negative duration in a record is worse than a
        zero because it looks like data.
        """
        return max(
            0.0,
            self.reply_path_s
            - self.tool_seconds
            - self.context_render_s
            - self.deferred_wait_s,
        )

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
