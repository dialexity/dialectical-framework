"""Probe: on a streamed turn, WHEN does the blank screen end — and on which channel?

WHY
===
`TurnTiming.first_delta_s` USED TO CARRY a warning that had stood unmeasured since it
was written (on the `first_delta_s` field itself, repeated in `CLAUDE.md`; the field's
comment was rewritten by the change that added this probe, so the text below no longer
appears there and is quoted from before it):

    Read it as "when did the waiting stop looking like nothing happening", NOT as
    time-to-first-token. On a turn where the model calls a tool before narrating —
    the Advisor's contracted behaviour — this lands after the whole tool round.
    How often that happens is UNMEASURED: it needs a count of text deltas before
    the first `ToolStart`, which needs the streaming path, and no probe has taken
    it.

This is that probe. The quantity is a RATE — of the turns that call tools, on what
fraction does model text arrive first? — because that rate decides how much of the
snappiness win streaming can actually deliver.

WHAT IS AND IS NOT ALREADY RECORDED
===================================
Three figures get quoted together to argue streaming is a large win. Only the third
is a measurement of what a person waits for, and the first two are NOT comparable
with each other. Stated precisely, because this probe exists to dispel exactly this
kind of conflation:

- `probe_stream_ttft.py` measured **1.46s / 1.34s** (`README.md`, probe table). That
  is `CallRecord.first_token_seconds` on the turn's FIRST streamed round, and it is
  time-to-first-**chunk**: `first_chunk_at` is stamped on the first chunk of ANY
  kind (`conversation_facilitator.py:600-601`), including a tool-call chunk nobody
  sees. It also runs from that round's `call_started`, so it excludes
  `context_render_s` and every earlier round.
- The bench's **~18s** median reply path (`rounds.md:4129`, 17.95/18.55s) is off the
  AWAITED path — the bench calls `chat()`, where `first_delta_s` is `None` by
  construction — and over turns whose median `tool_seconds` is **0.00s**
  (`rounds.md:4143`). So it is the wait on a TOOL-FREE turn, not on the
  tool-electing turns this probe's rate is about; those are the 34.5–42.0s `anchor`
  turns (`rounds.md:4126`).

Dividing the second by the first is arithmetic across two quantities on two paths,
and no such ratio is recorded anywhere in this repo. This probe measures the thing
neither of them measures: when a person first sees something on a tool-electing
streamed turn.

THE BLANK SCREEN IS NOT ACTUALLY BLANK, AND THAT IS THE POINT
=============================================================
An earlier draft of this probe asserted that on a tool-first turn "not a single
character appears" and "streaming buys the person nothing". That is FALSE, and the
framework's own code says so: `anchor` opens `progress_scope("anchor", ...)`
(`advisor/tools/anchor.py:81`) and the chain under it publishes person-facing
strings throughout the round — "Taking in both sides of what you described"
(`IntroducePolarity.resolve`, cited by symbol — the line moved within the commit
that added this probe), and more in `anchor_theses.py` and
`expand_polarities.py`. `utils/progress.py` exists precisely because `explore` was
"45.6s of total silence", and `probe_explore_progress.py` measured that channel
filling a 34s graph-silent stretch with ~28 events about 1.2s apart.

So this probe watches BOTH channels and reports time-to-first-visible-anything per
channel: model text, progress event, and `ToolStart` (itself a renderable event
hosts receive at `first_tool`). The rate is still the headline, but the class name
`silent-first` means **no model TEXT before the tool**, never "the person saw
nothing" — a host wired to `subscribe_progress` sees something much earlier, and
this probe now says when.

WHAT IT MEASURES
================
Every event from `Advisor.chat_stream` is timestamped as it is yielded, plus every
`ProgressEvent` on `f"{sid}:progress"`, and each turn is classified by comparing the
first `TextDelta` against the first `ToolStart`:

- **no-tool** — no `ToolStart` observed. First delta IS time-to-first-token here.
- **narrated-first** — a `TextDelta` preceded the first `ToolStart`. What the person
  reads first is the model saying what it is about to do (`stream_events.py:94` —
  that text is deliberately NOT part of `message`).
- **silent-first** — the first `ToolStart` preceded any `TextDelta`. This is the case
  the field's warning is about, and its `first_delta_s` is a tool-round wait.

`ThinkingDelta` is tracked and reported separately, because the framework's
`first_delta_s` is set on the first Text **or** Thinking chunk
(`conversation_facilitator.py:602-604` — `ThoughtChunk` or `TextChunk`; `:600-601` is
the different `first_chunk_at`) while `kind` above is classified on text alone. With `DIALEXITY_THINKING_LEVEL` unset (`settings.py:100` — `thinking_level`
defaults to `None`) thinking never fires and the two coincide; set it and they
diverge, so the field is validated against `min(first_text, first_thinking)` rather
than against text. **That setting is not cosmetic here — it decides the answer**, so
the RESULT below states which way it was set and what the other way would have read.

IT ALSO VALIDATES THE FIELD
===========================
`first_delta_s` is recorded inside the framework; this probe times the same event at
the consumer. Consumer-side is the looser of the two — inside is
`context_render_s + (first_delta_at - submit_stream_started)`, and every intervening
term (generator setup, the yield propagating up) is non-negative — so the outside
reading should be slightly LARGER, never smaller. A disagreement is worth more than
the rate: it would mean the field does not measure the moment it claims to.

WHAT IT DOES NOT DO
===================
- **One tier (weak), which is the tier documented to UNDER-elect tools.** CLAUDE.md
  records `explore` at 6/55 weak against 17/25 strong and `record_decision` at 0/6
  weak against 6/6 strong. The rate here is a weak-tier rate and is not the
  framework's rate.
- **Turns are not independent.** One conversation per rep, so the graph and the
  prompt grow turn over turn; per-turn prompt size is printed as a drift check,
  because `probe_reply_reuse_saving.py` found one shared `sid` growing later prompts
  62,794 → 74,808 chars.
- **The turns are hand-written**, in the persona of `scenarios.COFOUNDER`. Turn 1 is
  verbatim the bench's `_lit` opener; the rest are stand-ins, because the bench
  drives most of that scenario's beats through simulator `_dir(...)` directives. They
  are deliberately chosen to PROVOKE tools, so the election rate here should exceed
  the bench's ambient rate and is not an estimate of it.
- **`no-tool` means no `ToolStart` was observed**, not that no tool was requested: a
  `max_tool_rounds` overrun `break`s before the yields
  (`conversation_facilitator.py:648-682`). `last_tool_calls` is cross-checked and any
  disagreement printed.
- **Only the FIRST text and FIRST tool are classified.** A turn can narrate at 1.5s
  and then sit silent through a 40s third round; that reads as `narrated-first`. The
  streamed-round count is printed so multi-round turns are visible.

    poetry run pytest tests/e2e/probe_first_delta.py -s --real-llm

`DIALEXITY_PROBE_DELTA_REPS` sets how many conversations to run (default 2, ~5 turns
each). The denominator is what this probe is short of, not the turn count: a rate
over 1 or 2 tool-electing turns is not a rate, so raise reps rather than trusting a
small run — the report refuses to print a rate below `MIN_DENOMINATOR`.
`DIALEXITY_PROBE_DELTA_TURNS` caps turns within a rep (default: all).

RESULT (2026-09-02, weak tier, 2 reps x 5 turns, 5m09s)
=======================================================
**The rate is 0/3, and it does not matter, because the field's WARNING is false on
this build for a reason the warning never considered.** Both halves need saying, and
the second one is the finding.

The rate first, with its denominator: 3 of 10 turns elected a tool, and **0 of those
3 produced model text before the first `ToolStart`**. Turns chosen to provoke tools
on a tier documented to under-elect them still yield a denominator of exactly
`MIN_DENOMINATOR`, so 0/3 is a BOUND and a weak one — the ONE-SIDED 95%
Clopper-Pearson upper limit is **63%** (`1 - 0.05**(1/3)`; the two-sided 95% bound is
70.8%, and which one is meant is load-bearing at this denominator). It rules out
"narration first is the norm" and nothing narrower. Quote it as "text never came first
in 3 tool turns", never as "0%".

Now the field. On all three of those turns `first_delta_s` read **3.71 / 1.31 /
1.67s** (r1t1 / r2t1 / r2t5 — turn order, not sorted), matching `first_thinking` to
the millisecond — it did NOT land after the
tool round, which is exactly what `turn_timing.py` warned it would do. The reason is
that `first_delta_s` is stamped on Text **or** Thinking and `DIALEXITY_THINKING_LEVEL`
was **`medium`** for this run — read out of the environment, but read SEPARATELY: the
first run of this probe did not print the knob, so its own log can only show that
`ThinkingDelta`s arrived on 10/10 turns, i.e. that SOME level was set. The header now
prints it, so a re-run archives what this paragraph has to assert. Thinking
streams before the tool call is even assembled, so the field measures a ~2s wait on
every turn shape. **Flip that setting off and the warning becomes exactly right**:
the field would collapse onto `first_text`, which on those same three turns in the
same order was **55.65 / 45.69 / 66.79s**.  (Quote the two lists in turn order or as
ranges — sorting each independently, as an earlier draft did, silently pairs 1.67s with
55.7s and misattributes both.) So the warning is not wrong, it is CONDITIONAL, and the
condition is a setting nothing in the field's own docs mentions.

When the blank screen ended, by channel, medians over the turns having each:

| channel | n | median |
|---|---|---|
| model thinking | 10 | **2.39s** |
| ToolStart | 3 | 9.80s |
| progress event | 2 | 7.68s |
| model text | 10 | 12.20s |
| ANY of them | 10 | **2.39s** |

`no-tool` turns (n=7) reach text at a median 7.46s; the three tool turns at 55.65s.
**Thinking is where the snappiness actually comes from**, and the ratio must be taken
WITHIN a population or it is arithmetic across two: **~3x** on the tool-free majority
(text 7.46s against thinking 2.50s, both over those 7 turns) and **~33x** on the three
tool turns (text 55.65s against thinking 1.67s, both over those 3). Pooled over all 10
it is ~5x (12.20s / 2.39s). Any of the three is a bigger lever than anything the
prompt-size work moved, and it was already on. (An earlier draft wrote ~5x for the
tool-free subset and ~23x for the tool turns; the first is the pooled figure
mislabelled, and the second divides a subgroup numerator by the pooled denominator.)

The progress channel held on the turns it covers: 2 of 3 `silent-first` turns emitted
progress, a median **42.99s before any model text**, so a host wired to
`subscribe_progress` was not watching a blank screen. **The third turn (r2t5) is a
smaller hole than it first looks, and the difference matters.** `record_decision` has
no `progress_scope`, so nothing narrated its execution — but progress only exists WHILE
a tool runs (on r1t1 the first progress event lands 0.04s after `ToolStart`), and on
r2t5 `ToolStart` was at 61.21s against first text at 66.79s. So the missing scope
accounts for **~5.6s**, not the ~65s an earlier draft claimed. The larger stretch —
1.67s to 61.21s, round 1 generating the tool call — is not a progress gap at all and
no progress scope anywhere could fill it. Worth stating because the clause "while a
61s round ran" contains the refutation: that round ran BEFORE the tool. The ~5.6s is
still the same class of hole `utils/progress.py` closed in `explore`; the 59s is a
different problem this probe does not name a fix for, and cannot even size (see
below).

The field itself is sound: `first_delta_s` against the consumer-side reading of the
same event is **+0.001s median over 10 turns**, no turn negative.

WHAT THIS RESULT DOES NOT SUPPORT
=================================
- **A rate.** See the one-sided 63% bound above.
- **"The screen is never blank", and equally "it was blank for 59s".** This probe
  records FIRSTS only, so a turn whose thinking stopped early and whose text arrived a
  minute later is indistinguishable here from one that streamed thinking throughout.
  r2t5 (thinking from 1.67s, text at 66.79s) is a turn this probe cannot tell apart
  from either. Sizing that stretch needs last-delta-before-tool, which nothing takes.
- **A comparison with `probe_stream_ttft.py`'s 1.46s.** That is
  `CallRecord.first_token_seconds` — first chunk of ANY kind, from that ROUND's
  `call_started`. The 2.39s here is from the person's message. Different clocks.
- **Cross-turn comparison within a rep.** The prompt grew 62,794 -> 66,897 (rep 1)
  and -> 67,583 (rep 2) chars, and the per-class medians pool turns across that drift.
"""

from __future__ import annotations

import asyncio
import logging
import os
import statistics
import time
from contextlib import aclosing

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.driver import E2E_PERSONA, E2E_PRINCIPAL
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import (TextDelta, ThinkingDelta,
                                                        ToolStart)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.call_census import CallCensus, call_census

#: One conversation, in the persona of `scenarios.COFOUNDER` — the scenario every
#: `anchor` probe in this directory uses. Ordered as a real session: an opener that
#: states a tension (most likely to elect `anchor`), a detail that sharpens it,
#: pushback, a direct request for advice, and a commit.
#:
#: Turn 1 is VERBATIM the bench's `_lit` opener (`scenarios.py`); the others are
#: hand-written stand-ins for simulator-driven beats. All are chosen to provoke
#: tools, since a turn that elects nothing cannot contribute to the denominator.
TURNS = [
    # opener — states both poles outright, so `anchor` is the contracted response
    "I need to make a call about my cofounder. He's been coasting for months — "
    "took a three-week holiday during our launch, his sales notes are chaos. I'm "
    "at the point where I want to buy out his 45% and run this myself. I think "
    "it's the right move.",
    # deepen — the withheld fact, which should sharpen rather than restate
    "There's something I left out. He closed the two anchor customers who are 60% "
    "of our revenue, and both of those CEOs deal with him personally, not me.",
    # pushback — resists the obvious counsel, which is where the model tends to talk
    "Don't tell me to communicate more. I gave him direct feedback in March and "
    "nothing changed.",
    # ask advice — a direct question, the turn least likely to need a tool
    "So what would you actually do here? I'm leaning toward buying him out.",
    # commit — consent, which is what `record_decision` needs
    "Fine. I'm going to buy him out, and yes, write that down as my decision.",
]

TURN_LIMIT = max(
    1, min(len(TURNS), int(os.getenv("DIALEXITY_PROBE_DELTA_TURNS", str(len(TURNS)))))
)
REPS = max(1, int(os.getenv("DIALEXITY_PROBE_DELTA_REPS", "2")))

#: Below this many tool-electing turns the report prints no rate at all. Three is
#: not enough for a confident share either — it is the floor below which the number
#: is actively misleading, since `1/1` renders as 100% under a line captioned "THE
#: UNMEASURED RATE" and that sentence is what gets pasted into `rounds.md`.
MIN_DENOMINATOR = 3

NO_TOOL = "no-tool"
NARRATED = "narrated-first"
SILENT = "silent-first"


def _system_prompt_len(facilitator: ConversationFacilitator) -> int:
    """Rendered system prompt size, for the per-turn drift check.

    Same defensive read as `probe_reply_reuse_saving._system_prompt_text`: there is
    no reader for the system prompt (`set_system_prompt` only writes) and message 0's
    `content` is a `Text` part rather than a string.
    """
    messages = getattr(facilitator, "_messages", None) or []
    if not messages:
        return 0
    content = getattr(messages[0], "content", None)
    if isinstance(content, str):
        return len(content)
    for candidate in (content, *(content if isinstance(content, list) else ())):
        text = getattr(candidate, "text", None)
        if isinstance(text, str):
            return len(text)
    return 0


class _TurnRead:
    def __init__(self, rep: int, index: int):
        self.rep = rep
        self.index = index
        self.first_text: float | None = None
        self.first_thinking: float | None = None
        self.first_tool: float | None = None
        self.first_progress: float | None = None
        self.progress_count: int = 0
        self.tools: list[str] = []
        self.recorded_tool_calls: int = 0
        self.wall: float = 0.0
        self.reply_path_s: float | None = None
        self.off_path_s: float | None = None
        self.recorded_first_delta: float | None = None
        self.prompt_len: int = 0
        #: Streamed ROUNDS, not provider calls. `CLAUDE.md` is explicit that a turn
        #: must never be classified by its provider-call count — only
        #: `_call_with_tools` is `@use_brain`-decorated, so a five-round turn can
        #: record one call. One record per streamed round is the honest signal, and
        #: it is what makes a multi-round turn visible.
        self.rounds: int = 0
        #: Every provider call under the turn, INCLUDING the off-path repair that
        #: runs after the last yield. Kept for context, never for classification.
        self.calls: int = 0

    @property
    def first_model_delta(self) -> float | None:
        """First Text OR Thinking — the event the framework's field is stamped on."""
        candidates = [t for t in (self.first_text, self.first_thinking) if t is not None]
        return min(candidates) if candidates else None

    @property
    def first_visible(self) -> float | None:
        """When a host wired to everything first had something to show."""
        candidates = [
            t
            for t in (
                self.first_text,
                self.first_thinking,
                self.first_progress,
                self.first_tool,
            )
            if t is not None
        ]
        return min(candidates) if candidates else None

    @property
    def kind(self) -> str:
        if self.first_tool is None:
            return NO_TOOL
        if self.first_text is not None and self.first_text < self.first_tool:
            return NARRATED
        return SILENT

    def line(self) -> str:
        def fmt(value):
            return f"{value:6.2f}s" if value is not None else "   none"

        elected = ",".join(self.tools[:3]) if self.tools else "-"
        return (
            f"  r{self.rep}t{self.index} {self.kind:<14}"
            f" text {fmt(self.first_text)} think {fmt(self.first_thinking)}"
            f" tool {fmt(self.first_tool)} progress {fmt(self.first_progress)}"
            f" | visible {fmt(self.first_visible)}"
            f" | field {fmt(self.recorded_first_delta)}"
            f" | reply {fmt(self.reply_path_s)} wall {self.wall:6.2f}s"
            f" | rounds {self.rounds} calls {self.calls:3}"
            f" prog {self.progress_count:3} prompt {self.prompt_len:6}"
            f" | {elected}"
        )


async def _run_turn(advisor: Advisor, sid: str, rep: int, index: int, message: str):
    """One streamed turn, timestamping events at the CONSUMER."""
    read = _TurnRead(rep, index)
    census = CallCensus()
    bus = progress_module._event_bus
    progress_ready = asyncio.Event()

    started = time.monotonic()

    async def _collect_progress() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            progress_ready.set()
            async for _ in subscriber:
                read.progress_count += 1
                if read.first_progress is None:
                    read.first_progress = time.monotonic() - started

    collector = asyncio.create_task(_collect_progress())
    try:
        # Subscribe BEFORE the turn starts, or the early events — the ones that
        # decide whether the screen was ever blank — are missed.
        await progress_ready.wait()
        started = time.monotonic()
        # `aclosing` because `chat_stream` is an async generator wrapping another and
        # only the outermost consumer can close the chain. Iterating to EXHAUSTION is
        # the load-bearing part, and not for leak reasons: `_record_turn_timing` runs
        # after the `async with` inside `chat_stream`, so it executes only on the
        # `__anext__` following `ResponseComplete`. A `break` plus `aclose()` throws
        # `GeneratorExit` at the yield and leaves `last_turn_timing` at `None`, and
        # the field-validation section below would report "none" for every turn.
        with scope(sid), call_census(census):
            async with aclosing(advisor.chat_stream(message)) as events:
                async for event in events:
                    now = time.monotonic() - started
                    if isinstance(event, TextDelta) and read.first_text is None:
                        read.first_text = now
                    elif isinstance(event, ThinkingDelta) and read.first_thinking is None:
                        read.first_thinking = now
                    elif isinstance(event, ToolStart):
                        if read.first_tool is None:
                            read.first_tool = now
                        # `tool_name`, not `name` — `ToolStart` is a frozen slots
                        # dataclass, so reading a wrong attribute through `getattr`
                        # with a default would print a placeholder for every tool
                        # instead of failing, and this column would be quietly
                        # useless.
                        read.tools.append(event.tool_name)
    finally:
        collector.cancel()
        try:
            await collector
        except asyncio.CancelledError:
            pass

    read.wall = time.monotonic() - started
    read.calls = census.count
    read.rounds = sum(
        1
        for call in census.calls
        if call.caller == ConversationFacilitator._STREAM_ROUND_CALLER
    )
    timing = advisor.last_turn_timing
    # Direct attribute access, NOT `getattr(..., None)`: `TurnTiming` is a frozen
    # slots dataclass that declares these, so a rename must fail loudly here rather
    # than print "none" for every turn and report the field as unvalidated — which is
    # the same argument this file makes about `tool_name` above.
    if timing is not None:
        read.recorded_first_delta = timing.first_delta_s
        read.reply_path_s = timing.reply_path_s
        read.off_path_s = timing.off_path_s
    # The authoritative "did a tool fire" signal, per CLAUDE.md.
    read.recorded_tool_calls = len(advisor._conversation.last_tool_calls or [])
    read.prompt_len = _system_prompt_len(advisor._conversation)
    return read


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_first_delta(di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}  (weak tier UNDER-elects tools)")
    print(f"reps: {REPS} x {TURN_LIMIT} turns = {REPS * TURN_LIMIT} turns")
    # ARCHIVE THE SETTING THAT DECIDES THE ANSWER. `first_delta_s` is stamped on the
    # first Text OR Thinking chunk, so with thinking on it reads ~2s on every turn
    # shape and with thinking off it collapses onto first text — a 20x difference on a
    # tool-electing turn. The first run of this probe did not print it, which left the
    # log unable to support its own headline: `ThinkingDelta`s arriving proves SOME
    # level was set, not which, and the level had to be read out of the environment
    # separately and asserted in prose. A knob that changes the conclusion belongs in
    # the output, next to the model name.
    print(
        f"DIALEXITY_THINKING_LEVEL: {os.getenv('DIALEXITY_THINKING_LEVEL') or 'unset'}"
        "  (unset => `first_delta_s` IS first text)"
    )
    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    bus = di_container.event_bus()
    # Without this every `publish` is a silent no-op, and an empty progress stream
    # would read as "the emission points don't fire" — the most alarming possible
    # conclusion, from a probe defect.
    await bus.connect()
    assert progress_module._event_bus is bus, (
        "progress is not wired to this bus — see `utils/progress.set_event_bus`"
    )

    reads: list[_TurnRead] = []
    try:
        with using_model(di_container, DEFAULT_TIER_WEAK):
            for rep in range(1, REPS + 1):
                # A fresh Case AND a fresh Advisor per rep, but ONE Advisor across
                # the turns WITHIN a rep: the question is about a conversation, and a
                # fresh Advisor per turn would make every turn an opener — which are
                # exactly the turns most likely to elect a tool, biasing the rate
                # toward `silent-first`.
                case = Case()
                case.commit()
                advisor = Advisor(app_preamble=E2E_PERSONA, principal=E2E_PRINCIPAL)
                for index, message in enumerate(TURNS[:TURN_LIMIT], start=1):
                    read = await _run_turn(advisor, case.sid, rep, index, message)
                    reads.append(read)
                    print(read.line())
    finally:
        await bus.disconnect()

    print()
    by_kind = {k: [r for r in reads if r.kind == k] for k in (NO_TOOL, NARRATED, SILENT)}
    elected = [r for r in reads if r.first_tool is not None]

    # The denominator FIRST, so a rate can never be read off a sample that cannot
    # support one.
    print(f"  {len(elected)}/{len(reads)} turns elected a tool")
    disagree = [
        r for r in reads if bool(r.tools) != bool(r.recorded_tool_calls)
    ]
    if disagree:
        print(
            f"  WARNING: {len(disagree)} turn(s) where observed `ToolStart`s and"
            " `last_tool_calls` disagree — a tool was requested but never yielded"
            "\n  (a `max_tool_rounds` overrun breaks before the yields), so `no-tool`"
            " is undercounting."
        )

    for kind in (NO_TOOL, NARRATED, SILENT):
        group = by_kind[kind]
        if not group:
            print(f"  {kind:<14} n=0")
            continue
        firsts = [r.first_text for r in group if r.first_text is not None]
        median = f"{statistics.median(firsts):.2f}s" if firsts else "no text at all"
        print(f"  {kind:<14} n={len(group)}   median first text {median}")

    if len(elected) < MIN_DENOMINATOR:
        print(
            f"\n  NO RATE REPORTED: {len(elected)} tool-electing turn(s) is below the"
            f" {MIN_DENOMINATOR} this probe requires."
        )
        print(
            f"  A rate over 1-2 turns is not a rate. Re-run with"
            f" DIALEXITY_PROBE_DELTA_REPS={max(2, REPS * 2)} or higher."
        )
    else:
        narrated = len(by_kind[NARRATED])
        print(
            f"\n  THE UNMEASURED RATE: {narrated}/{len(elected)} tool-electing turns"
            f" produced model text BEFORE the first tool."
        )
        print(
            "  On the rest, `first_delta_s` is a tool-round wait — but see the"
            "\n  by-channel table below before concluding the screen was blank."
        )

    # When did the blank screen actually end, per channel? This is the section that
    # keeps `silent-first` from being read as "the person saw nothing".
    print("\n  WHEN THE BLANK SCREEN ENDED, by channel (median over turns having it):")
    for label, attr in (
        ("model text    ", "first_text"),
        ("model thinking", "first_thinking"),
        ("ToolStart     ", "first_tool"),
        ("progress event", "first_progress"),
        ("ANY of them   ", "first_visible"),
    ):
        values = [getattr(r, attr) for r in reads]
        values = [v for v in values if v is not None]
        if values:
            print(
                f"    {label}  n={len(values):3}  median {statistics.median(values):6.2f}s"
            )
        else:
            print(f"    {label}  n=  0  not recorded")

    silent = by_kind[SILENT]
    if silent:
        with_progress = [r for r in silent if r.first_progress is not None]
        print(
            f"\n  Of {len(silent)} `silent-first` turn(s), {len(with_progress)} had a"
            f" progress event."
        )
        if with_progress:
            saved = [
                (r.first_text or r.wall) - r.first_progress for r in with_progress
            ]
            print(
                f"  Progress arrived a median {statistics.median(saved):.2f}s before"
                " any model text on those turns, so a host wired to"
                "\n  `subscribe_progress` was NOT looking at a blank screen."
            )

    # Validate the framework's own field against this outside reading. Compared
    # against first Text OR Thinking, because that is what the field is stamped on.
    print()
    pairs = [
        (r.first_model_delta, r.recorded_first_delta)
        for r in reads
        if r.first_model_delta is not None and r.recorded_first_delta is not None
    ]
    if pairs:
        deltas = [outside - inside for outside, inside in pairs]
        print(
            f"  first_delta_s vs consumer-side, n={len(pairs)}:"
            f" median difference {statistics.median(deltas):+.3f}s"
            f"  (outside should be slightly larger, never smaller)"
        )
        negative = [d for d in deltas if d < -0.05]
        if negative:
            print(
                f"  WARNING: {len(negative)} turn(s) recorded a LATER first delta than"
                "\n  the consumer observed, which the field's definition does not allow."
            )
    else:
        print("  first_delta_s: no turn produced both readings; field NOT validated here")

    # Prompt drift, per rep — a growing prompt makes later turns incomparable with
    # earlier ones, and the per-class medians pool them.
    for rep in range(1, REPS + 1):
        sizes = [r.prompt_len for r in reads if r.rep == rep]
        if sizes:
            print(
                f"  rep {rep} prompt size {sizes[0]} -> {sizes[-1]} chars"
                f" ({sizes[-1] - sizes[0]:+d})"
            )

    # Coherence only — this probe measures, it does not gate.
    assert reads, "no turn ran"
    for r in reads:
        assert r.wall > 0
        for attr in ("first_text", "first_thinking", "first_tool"):
            value = getattr(r, attr)
            if value is not None:
                assert value <= r.wall + 0.05, (
                    f"r{r.rep}t{r.index}: {attr} at {value:.2f}s in a {r.wall:.2f}s turn"
                )
