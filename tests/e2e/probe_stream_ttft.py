"""Probe: does the relocated cache breakpoint make the reply START sooner?

ANSWERED: NO — 1.46s with the split against 1.34s without, 4/4 pairs, weak tier,
nominally slower and far inside the noise, while cache read was 18,075 against 0 and
every warm turn wrote 18,075. Mechanism confirmed and setup verified, so that null is
an effect size rather than a condition that never ran. **The caching change is a cost
win only.** The reason transfers: TTFT was ~1.4s in BOTH arms, which send the same
~19,100 prefill and differ only in how it is billed, so ~19k of prefix is not what
that 1.4s is made of — the floor is the fixed cost of getting a request out and a
first byte back. A prompt-size lever aimed at snappiness has nothing to bite on here.
Re-run it after any change that could plausibly move prefill cost; see `rounds.md`.

WHY
===
`probe_prompt_cache.py` settled the COST question — moving the breakpoint off the
mutable graph dump makes a post-write turn's prefill ~6.8x cheaper in
billed-equivalent tokens. It could not settle the SPEED question, and said so:
`CallRecord.seconds` is whole-call wall time, which output length dominates. That
probe read 7.5s vs 9.2s at four reps and then INVERTED to 8.9s vs 7.2s at two, on
the same configuration. Not an underpowered measurement — the wrong instrument.

A prefill cache moves exactly one interval: the wait before the first token. That
interval is only observable on the streaming path, and the streaming path recorded
nothing at all until `ConversationFacilitator._record_stream_round` — `use_brain`
hands the caller a raw callable and returns before its own recording. So this probe
is the first thing in the tree to read a streamed turn's numbers, and it is the
only way to answer the question the whole caching change was made for.

WHAT IT COMPARES
================
The same discriminating condition as the cost probe, because the fix only pays on a
turn whose dump has changed:

    turn 1 -> mutate the graph (no provider call) -> turn 2, measured

and the number is turn 2's `first_token_seconds` on the turn's FIRST streamed
round. First round specifically: round 1 prefills the cacheable system prompt,
while round N prefills that plus every accumulated tool result at a different size
and a different breakpoint, so a mean over rounds blurs the comparison.

WHAT THE NUMBER IS NOT
======================
Not a provider RTT. `await call.stream()` issues no HTTP request — Anthropic's
stream manager sends on `__aenter__`, which Mirascope's decoder defers to the first
`__anext__` — so this interval also contains the framework's own request
construction: the `use_brain` wrapper, `encode_request`, and the cache-breakpoint
scan over a ~60k-char prompt. Those sit on the person's critical path too, which is
why they are included, but "TTFT" here means "from asking to the first byte back",
not "how fast the model is".

Also not the person's whole wait. `TurnTiming.first_delta_s` is that, and on a
tool-electing turn it lands after the tool round — see its docstring.

THE TOKENS MAY COME BACK UNMEASURED, AND THAT IS NOT A FAILURE
==============================================================
In the event they did not: prefill came back MEASURED on 16/16 turns, so Bedrock does
populate `message_delta.usage` and the branch below never ran. Keep it anyway — it is
insurance against a provider or decoder that stops populating those optional fields,
and the difference between insurance and description is worth stating rather than
quietly deleting.

Mirascope iterates the raw event stream and DISCARDS the `message_start` usage that
Anthropic's own SDK accumulator would have folded in, reading prefill only from
`message_delta` — whose token fields the API declares optional. So if Bedrock reports
prefill only at `message_start`, the token columns come back UNMEASURED, by design,
rather than as zeros that would read as "caching does nothing".

When that happens the SECONDS are still reported — an unconfirmed mechanism does not
make the clock unreadable, it makes the cause unattributable — but the verdict
sentence is then barred from naming caching. `_mechanism_verdict` enforces that, and
it is also what stops the opposite failure: it compares the arms against EACH OTHER,
so a run where `split_system_for_cache` had silently become a no-op cannot print
provider noise as the fix working. `_report_setup` closes the third hole, by checking
that the warm turn wrote the entry the measured turn is supposed to read — otherwise
a setup that never ran reports as a null.

    poetry run pytest tests/e2e/probe_stream_ttft.py -s --real-llm

Assertions gate coherence only, never the direction of the result. A null was always a
real possible answer here — the ~19k prefix is small next to 7-11s of generation — and
it is the answer that came back.
"""

from __future__ import annotations

import os

#: Same reasoning as `probe_prompt_cache._RUN_MARKER`: makes every RUN a fresh
#: cache lineage, so a re-run inside the 5-minute TTL cannot serve its own previous
#: writes back to itself and report them as the fix working.
_RUN_MARKER = os.getpid()

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.driver import E2E_PERSONA, E2E_PRINCIPAL
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import bedrock_provider
from dialectical_framework.utils.call_census import (CallCensus, CallRecord,
                                                    call_census)

#: Default 4 rather than 3, and EVEN on purpose: the arm order alternates on
#: `rep % 2`, so an odd count runs one arm first more often than the other and the
#: warming-neutralisation the docstring claims is not actually delivered. An odd
#: override still runs — it prints a warning instead of refusing, since a 1-rep
#: smoke run is the cheapest way to check the instrument fires at all.
REPS = max(1, int(os.getenv("DIALEXITY_PROBE_TTFT_REPS", "4")))

#: Same floor and same reason as `probe_prompt_cache._ENGINE_PREFILL_FLOOR`: the
#: Advisor engine is the only prompt in the tree over the model's 4,096-token
#: minimum, so a cache read below this is not the engine and cannot be the effect.
_ENGINE_PREFILL_FLOOR = 10_000

MESSAGE_1 = "Give me your read on where I stand."
MESSAGE_2 = "And now? Anything changed in how you see it?"

_READINGS = [
    ("Sole founder buyout is right", "Board oversight serves all stakeholders"),
    ("He earned his stake through risk", "Equity should track future contribution"),
    ("Preserve the friendship above all", "The company's survival comes first"),
    ("Clear hierarchy prevents deadlock", "Equal partnership keeps both invested"),
    ("Move now on the equity split", "Align on values before structure"),
]


def _add_perspective(index: int) -> None:
    """One more reading in the current scope. No provider call."""
    from test_dialectical_context import _create_perspective_with_aspects

    thesis, antithesis = _READINGS[index % len(_READINGS)]
    _create_perspective_with_aspects(
        thesis_text=f"{thesis} ({index})",
        antithesis_text=f"{antithesis} ({index})",
        t_plus_text="What this way of seeing buys",
        t_minus_text="What it quietly costs",
        a_plus_text="What the other way buys",
        a_minus_text="What that costs in turn",
    )


def _build_graph(count: int) -> str:
    case = Case()
    case.commit()
    with scope(case.sid):
        for i in range(count):
            _add_perspective(i)
    return case.sid


def _identity(system):
    return system


class _Turn:
    def __init__(self, *, split: bool, label: str, census: CallCensus, timing, tools):
        self.split = split
        self.label = label
        self.calls = list(census.calls)
        self.timing = timing
        self.tool_calls = list(tools)

    @property
    def rounds(self) -> list[CallRecord]:
        """Every streamed round of this turn, in the order they ran."""
        return sorted(
            (c for c in self.calls
             if c.caller == ConversationFacilitator._STREAM_ROUND_CALLER),
            key=lambda c: c.started,
        )

    @property
    def first_round(self) -> CallRecord | None:
        """The turn's first streamed round, or `None` if it took no reading.

        Selected by caller and then by `min(started)` — round 1 specifically, the
        one whose prefill is the cacheable system prompt on its own. Round 2+
        prefills that plus the accumulated tool results, at a different size and a
        different breakpoint, which is a different measurement wearing the same
        units.

        **Filtering on `first_token_seconds is not None` before taking the minimum
        would be the bug this is written to avoid**: a round 1 that took no reading
        would silently promote round 2 into the comparison, and the report would
        look identical. So the selection happens first and the reading is checked
        second — a turn whose round 1 is unmeasured is DROPPED, not substituted.
        """
        rounds = self.rounds
        if not rounds or rounds[0].first_token_seconds is None:
            return None
        return rounds[0]

    @property
    def clean(self) -> bool:
        return self.first_round is not None

    def line(self) -> str:
        call = self.first_round
        elected = (f"   elected {','.join(sorted(set(self.tool_calls)))}"
                   if self.tool_calls else "")
        if call is None:
            why = ("round 1 took no first-token reading"
                   if self.rounds else "no streamed round recorded")
            return (f"  split={'on ' if self.split else 'off'} {self.label:<9}"
                    f" SKIPPED: {why}{elected}")
        if call.prefill_tokens is None:
            tokens = "  prefill UNMEASURED (provider sent none in message_delta)"
        else:
            tokens = (f"  prefill {call.prefill_tokens:>7,}"
                      f" = uncached {call.uncached_input_tokens:>6,}"
                      f" + read {call.cache_read_tokens:>7,}"
                      f" + write {call.cache_write_tokens:>7,}")
        return (
            f"  split={'on ' if self.split else 'off'} {self.label:<9}"
            f" FIRST TOKEN {call.first_token_seconds:6.2f}s"
            + tokens
            # Round count printed, because "which round did this come from" is the
            # one question the seconds cannot answer for the reader.
            + f"   [{len(self.calls)} calls, {len(self.rounds)} streamed rounds]"
            + elected
        )


async def _one_turn(sid: str, message: str, *, split: bool, label: str,
                    marker: str) -> _Turn:
    advisor = Advisor(
        app_preamble=E2E_PERSONA + marker, principal=E2E_PRINCIPAL
    )
    census = CallCensus()
    # The census must be installed around the ITERATION, not just around the
    # generator's creation: an async generator runs in its consumer's context at
    # each resumption, so `record_call` inside it reads the stack installed here.
    with scope(sid), call_census(census):
        async for _event in advisor.chat_stream(message):
            pass
    return _Turn(
        split=split,
        label=label,
        census=census,
        timing=advisor.last_turn_timing,
        tools=advisor._conversation.last_tool_calls,
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_stream_ttft(monkeypatch, di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(f"reps: {REPS}  (each rep runs both arms; 2 turns per arm)")
    if REPS % 2:
        print(f"  WARNING: {REPS} is odd, so the arm order does not balance — one"
              " arm runs first\n  more often than the other and provider-side"
              " warming is NOT neutralised.\n  Fine for a smoke run; do not quote"
              " the comparison off it.")
    print()

    pairs: list[tuple[_Turn, _Turn]] = []
    with using_model(di_container, DEFAULT_TIER_WEAK):
        for rep in range(REPS):
            # Alternate which arm runs first, so provider-side warming cannot be
            # booked as the effect.
            order = (True, False) if rep % 2 == 0 else (False, True)
            for split in order:
                sid = _build_graph(3)
                marker = (
                    f"\n\nSession marker: run {_RUN_MARKER}, rep {rep},"
                    f" arm {'on' if split else 'off'}."
                )
                with monkeypatch.context() as patch:
                    if not split:
                        patch.setattr(
                            bedrock_provider, "split_system_for_cache", _identity
                        )
                    warm = await _one_turn(
                        sid, MESSAGE_1, split=split, label="warm", marker=marker
                    )
                    print(warm.line())
                    # The whole point: change the dump between the two turns, with
                    # no provider call, so the only thing that moved is the tail.
                    with scope(sid):
                        _add_perspective(90 + rep)
                    measured = await _one_turn(
                        sid, MESSAGE_2, split=split, label="after mut",
                        marker=marker,
                    )
                    print(measured.line())
                pairs.append((warm, measured))
            print()

    _report(pairs)

    measured = [m for _, m in pairs if m.clean]
    assert measured, (
        "no measured turn recorded a streamed round — either nothing streamed or"
        " the census never saw it, so this probe measured nothing"
    )
    # BOTH arms, not just one: a run where the whole OFF arm produced nothing would
    # otherwise print a one-armed report and pass green, which reads as a completed
    # comparison. Coherence only — this says nothing about the direction.
    assert any(m.split for m in measured) and any(not m.split for m in measured), (
        "only one arm produced a usable turn, so there is no comparison here:"
        f" {sum(m.split for m in measured)} with the split,"
        f" {sum(not m.split for m in measured)} without"
    )


def _report(pairs: list[tuple[_Turn, _Turn]]) -> None:
    by_arm: dict[bool, list[_Turn]] = {True: [], False: []}
    for _, measured in pairs:
        if measured.clean:
            by_arm[measured.split].append(measured)

    print("TURN AFTER THE DUMP CHANGED — the only condition the fix pays on")
    for split in (True, False):
        turns = by_arm[split]
        arm = ("split ON (breakpoint before the dump)" if split
               else "split OFF (as shipped by Mirascope)")
        if not turns:
            print(f"  {arm}: no usable turn")
            continue
        ttfts = [t.first_round.first_token_seconds for t in turns]
        n = len(turns)
        print(f"  {arm}  n={n}")
        print(f"    first token {sum(ttfts) / n:>6.2f}s mean"
              f"   ({', '.join(f'{s:.2f}' for s in ttfts)})")
        reads = [t.first_round.cache_read_tokens for t in turns
                 if t.first_round.cache_read_tokens is not None]
        if reads:
            print(f"    cache read  {sum(reads) / len(reads):>9,.0f} tokens (mean)")
        else:
            print("    cache read  UNMEASURED — the provider reported no prefill on"
                  " the streaming path,\n                so the tokens cannot"
                  " confirm the arms differed at all")
        deltas = [t.timing.first_delta_s for t in turns
                  if t.timing and t.timing.first_delta_s is not None]
        if deltas:
            # Printed for contrast, not compared: on a tool-electing turn this
            # includes the whole tool round, which is not a prefill effect.
            print(f"    (whole-turn first delta {sum(deltas) / len(deltas):>6.1f}s"
                  " — includes tool rounds, NOT a prefill measurement)")

    _report_setup(pairs)

    on, off = by_arm[True], by_arm[False]
    if not (on and off):
        return
    ttft_on = sum(t.first_round.first_token_seconds for t in on) / len(on)
    ttft_off = sum(t.first_round.first_token_seconds for t in off) / len(off)
    print(f"\n  time to first token after a dump change:"
          f" {ttft_on:.2f}s with the split vs {ttft_off:.2f}s without")

    mechanism = _mechanism_verdict(on, off)
    print(mechanism.text)

    # The seconds are reported either way — an unconfirmed mechanism does not make
    # the clock unreadable, it makes the CAUSE unattributable. What changes with
    # `mechanism.confirmed` is whether the sentence may name caching.
    #
    # A difference smaller than this is inside the noise a single-digit n can
    # resolve, and the cost probe's own seconds inverted between runs at n=4 and
    # n=2. Stated as a threshold rather than left to the reader's eye.
    floor = max(0.3, 0.15 * ttft_off)
    if ttft_off - ttft_on > floor:
        print("  The split arm starts SOONER." + (
            " The cache read says why." if mechanism.confirmed
            else " Attribute it to nothing: the mechanism is"
                 "\n  unconfirmed above, so this is an observation and not a finding."
        ))
    elif ttft_on - ttft_off > floor:
        print("  The split arm starts LATER." + (
            " Report it — the uncached tail is now"
            "\n  full-rate input, and on a small dump that can cost more than the"
            " read saves." if mechanism.confirmed
            else " With the mechanism unconfirmed this is not"
                 "\n  evidence against the split either."
        ))
    else:
        print("  NO RESOLVABLE DIFFERENCE at this n. The cost win stands on its own"
              "\n  numbers; do not convert it into a latency claim.")


class _Mechanism:
    def __init__(self, *, confirmed: bool, text: str):
        self.confirmed = confirmed
        self.text = text


def _mechanism_verdict(on: list[_Turn], off: list[_Turn]) -> _Mechanism:
    """Did the arms actually differ in the way the probe assumes?

    **This is the gate the first draft did not have, and its absence was the worst
    defect in the instrument.** The old check asked only whether the ON arm read
    from cache at all — which passes when the two arms are the SAME arm. If
    `CACHE_SPLIT_SENTINEL` stops matching (a `system_prompts.py` edit moves
    `_CONTEXT_SLOT` off the tail, or the header text changes), `split_system_for_cache`
    returns its input unchanged, both arms read the warm prefix, and provider noise
    across two means of n=4 would have printed as "the split arm starts sooner, and
    the cache read says why".

    So the comparison is between arms, on the same criterion the cost probe uses:
    the ON arm must read multiples of the OFF arm AND clear the engine floor.
    """
    reads_on = [t.first_round.cache_read_tokens for t in on
                if t.first_round.cache_read_tokens is not None]
    reads_off = [t.first_round.cache_read_tokens for t in off
                 if t.first_round.cache_read_tokens is not None]
    if not reads_on or not reads_off:
        return _Mechanism(
            confirmed=False,
            text=("  MECHANISM UNMEASURED: the streaming path reported no prefill"
                  " tokens, so the\n  arms cannot be shown to have differed at all."
                  " Expected on some providers —\n  Mirascope discards the"
                  " `message_start` counts and depends on optional\n "
                  " `message_delta` fields. See the module docstring."),
        )
    read_on = sum(reads_on) / len(reads_on)
    read_off = sum(reads_off) / len(reads_off)
    print(f"  engine tokens served from cache: {read_on:,.0f} with the split"
          f" vs {read_off:,.0f} without")
    if read_on > read_off * 2 and read_on > _ENGINE_PREFILL_FLOOR:
        return _Mechanism(confirmed=True, text="  MECHANISM CONFIRMED: the arms"
                                              " differ, and in the intended way.")
    if read_on <= read_off:
        return _Mechanism(
            confirmed=False,
            text=("  MECHANISM ABSENT: the split arm read no more than the control."
                  " Check that\n  `CACHE_SPLIT_SENTINEL` still matches"
                  " `system_prompt()`'s tail and that the head\n  clears the model's"
                  " 4,096-token minimum. The seconds below compare nothing."),
        )
    return _Mechanism(
        confirmed=False,
        text=("  MECHANISM PARTIAL: the arms differ but not decisively"
              f" ({read_on:,.0f} vs {read_off:,.0f},\n  floor"
              f" {_ENGINE_PREFILL_FLOOR:,}). Report the numbers, not a verdict."),
    )


def _report_setup(pairs: list[tuple[_Turn, _Turn]]) -> None:
    """Did the warm turn actually do its job — write a cache entry to be read?

    The warm turns were printed and never analysed in the first draft, which is how
    a FAILED SETUP would have read as a null result: if the prefix falls under the
    model's minimum, or a warm turn retries, or the graph renders smaller than
    expected, then both arms measure a cold miss, the seconds come out equal, and
    the report says "NO RESOLVABLE DIFFERENCE at this n" — charging to effect size
    what belongs to a condition that never ran.
    """
    warm = [w for w, _ in pairs if w.clean and w.split]
    writes = [w.first_round.cache_write_tokens for w in warm
              if w.first_round.cache_write_tokens is not None]
    if not writes:
        print("\n  SETUP UNVERIFIED: no warm turn in the split arm reported a cache"
              " write, so\n  nothing confirms there was an entry for the measured"
              " turn to read.")
        return
    below = [w for w in writes if w <= _ENGINE_PREFILL_FLOOR]
    print(f"\n  warm turns wrote {sum(writes) / len(writes):,.0f} tokens (mean of"
          f" {len(writes)}) — the entry the measured turn reads")
    if below:
        print(f"  SETUP SUSPECT: {len(below)} of {len(writes)} warm turns wrote at"
              f" or under the {_ENGINE_PREFILL_FLOOR:,}-token\n  floor, which is not"
              " the engine. A null below may be a setup that never ran.")

    # Reads on a warm turn mean the opposite problem: each arm-run is supposed to be
    # a cold prefix (unique persona marker), so a read there means the arms can serve
    # each other's entries — exactly the contamination the cost probe once caught.
    contaminated = [
        w for w, _ in pairs
        if w.clean and w.first_round.cache_read_tokens
    ]
    if contaminated:
        print(f"  WARNING: {len(contaminated)} warm turn(s) READ from cache. The"
              " per-arm persona markers\n  are supposed to make every arm-run cold —"
              " if they are not, the arms can\n  serve each other's entries and the"
              " comparison is contaminated.")
