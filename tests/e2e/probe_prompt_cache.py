"""Probe: does moving the cache breakpoint off the graph dump actually cache?

WHY
===
Mirascope stamps `cache_control` at the END of the system prompt, and the
Advisor's system prompt ENDS with the mutable Current Understanding dump. So the
cached prefix missed on every turn that followed a graph write, and the whole
~15.6k-token engine was re-prefilled at full rate to deliver a few hundred changed
tokens. `split_system_for_cache` breaks the block at the seam and leaves the
breakpoint on the stable half.

That reasoning is sound and still needs checking, because the failure mode is
SILENT in both directions. A request with the breakpoint in the wrong place is
perfectly valid and merely caches nothing; and a prefix under the model's minimum
cacheable length (4,096 tokens on haiku-4.5) is also not an error — the provider
just declines and bills at full rate. Nothing raises either way.

THE DISCRIMINATING CONDITION
============================
Not "does a repeated turn hit the cache" — it would with or without the fix, since
an unchanged prompt matches at any breakpoint. The fix only pays on a turn whose
**dump has changed**. So each arm runs:

    turn 1 → mutate the graph (no provider call) → turn 2, measured

and the number that matters is turn 2's `cache_read_tokens`. With the split, the
engine should come back as a read; without it, the changed dump should invalidate
the single entry and force a fresh write of everything.

WHAT MAKES THE ARMS INDEPENDENT
===============================
Each arm-run gets a unique marker in its persona, so its cached prefix cannot be
served from another arm's writes. Without that the arms alias: both send the same
engine text, and a read for a prefix one arm wrote could be served to the other,
flattering whichever ran second. The marker is one line of persona in a ~15.6k
engine, so it changes cache identity without changing what is being measured.

    poetry run pytest tests/e2e/probe_prompt_cache.py -s --real-llm

Assertions gate the measurement's coherence, never the cache numbers — a null is a
real possible answer and a probe that cannot report one is worthless.
"""

from __future__ import annotations

import os

#: Makes every RUN a fresh cache lineage, not just every arm. Without it a re-run
#: within the 5-minute TTL serves its own previous writes: the first run of this
#: probe had a warm turn read 18,070 tokens it was supposed to have written,
#: because an earlier smoke had already cached the identical `rep 0, arm on`
#: prefix. `os.getpid()` rather than a clock because it is stable within the run
#: and different between runs, which is exactly the property needed.
_RUN_MARKER = os.getpid()

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.driver import E2E_PERSONA, E2E_PRINCIPAL
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import bedrock_provider
from dialectical_framework.utils.call_census import (CallCensus, CallRecord,
                                                     call_census)

REPS = max(1, int(os.getenv("DIALEXITY_PROBE_CACHE_REPS", "3")))

MESSAGE_1 = "Give me your read on where I stand."
MESSAGE_2 = "And now? Anything changed in how you see it?"

#: Only the Advisor's engine clears the provider's 4,096-token minimum, so a call
#: this large is the turn's own generation rather than a concern the tools ran or
#: the decision repair's classifier — every one of those is under ~3.5k tokens and
#: can never be cached as the prompts stand.
_ENGINE_PREFILL_FLOOR = 10_000

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
    def __init__(self, *, split: bool, label: str, census: CallCensus, tool_calls):
        self.split = split
        self.label = label
        self.tool_calls = list(tool_calls)
        self.calls = list(census.calls)

    @property
    def engine_call(self) -> CallRecord | None:
        """The turn's OWN first generation, and nothing else.

        Three filters, each removing a different impostor:

        `prefill >= _ENGINE_PREFILL_FLOOR` drops the concern calls — including the
        decision repair's classifier, which runs off-path on every turn.

        `format_name is None` drops `_call_with_response_model`. That matters more
        than it looks: the structured fallback re-sends the same system prompt PLUS
        the accumulated messages, so its prefill is strictly larger, and it would
        read the first call's own cache write — a forged hit that would flatter the
        reuse-off arm and understate the effect. `max(prefill)` selected exactly
        that call, while the docstring claimed the first one was being measured.

        `min(started)` makes the claim true rather than incidental.
        """
        candidates = [
            c for c in self.calls
            if (c.prefill_tokens or 0) >= _ENGINE_PREFILL_FLOOR
            and c.format_name is None
        ]
        return min(candidates, key=lambda c: c.started) if candidates else None

    @property
    def fallback_calls(self) -> int:
        """Structured calls this turn made — printed so a reader can see there were
        none, rather than inferring it from the total call count."""
        return sum(1 for c in self.calls if c.format_name is not None)

    @property
    def clean(self) -> bool:
        """The engine call reported usage. Tool election is NOT disqualifying.

        Unlike the leak probe — where a tool changes how much machinery there is
        to narrate and must be discarded — a tool here cannot touch the number
        being read. The measured record is the turn's first `_call_with_tools`,
        whose prompt was rendered before the tool could run, and the loop's
        continuation rounds bypass `use_brain` so they never reach the census at
        all. A tool's write moves the NEXT turn's dump, which is the condition
        under test anyway.
        """
        return self.engine_call is not None

    def line(self) -> str:
        call = self.engine_call
        elected = (f"   elected {','.join(sorted(set(self.tool_calls)))}"
                   if self.tool_calls else "")
        if call is None:
            return (f"  split={'on ' if self.split else 'off'} {self.label:<9}"
                    f" SKIPPED: no call reported usage{elected}")
        return (
            f"  split={'on ' if self.split else 'off'} {self.label:<9}"
            f" prefill {call.prefill_tokens:>7,}"
            f"  = uncached {call.uncached_input_tokens:>6,}"
            f" + read {call.cache_read_tokens:>7,}"
            f" + write {call.cache_write_tokens:>7,}"
            f"  {call.seconds:5.1f}s"
            + (f"   [{len(self.calls)} calls]" if len(self.calls) > 1 else "")
            + (f"   [{self.fallback_calls} structured]" if self.fallback_calls else "")
            + elected
        )


async def _one_turn(sid: str, message: str, *, split: bool, label: str,
                    marker: str) -> _Turn:
    advisor = Advisor(
        app_preamble=E2E_PERSONA + marker, principal=E2E_PRINCIPAL
    )
    census = CallCensus()
    with scope(sid), call_census(census):
        await advisor.chat(message)
    return _Turn(
        split=split,
        label=label,
        census=census,
        tool_calls=advisor._conversation.last_tool_calls,
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_prompt_cache(monkeypatch, di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(f"reps: {REPS}  (each rep runs both arms; 2 turns per arm)\n")

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
        "no measured turn reported an engine call — every turn either elected a"
        " tool or reported no usage, so this probe measured nothing"
    )


def _report(pairs: list[tuple[_Turn, _Turn]]) -> None:
    by_arm: dict[bool, list[_Turn]] = {True: [], False: []}
    for _, measured in pairs:
        if measured.clean:
            by_arm[measured.split].append(measured)

    print("TURN AFTER THE DUMP CHANGED — the only condition the fix pays on")
    for split in (True, False):
        turns = by_arm[split]
        arm = "split ON (breakpoint before the dump)" if split else "split OFF (as shipped by Mirascope)"
        if not turns:
            print(f"  {arm}: no usable turn")
            continue
        reads = [t.engine_call.cache_read_tokens for t in turns]
        writes = [t.engine_call.cache_write_tokens for t in turns]
        uncached = [t.engine_call.uncached_input_tokens for t in turns]
        seconds = [t.engine_call.seconds for t in turns]
        n = len(turns)
        print(f"  {arm}  n={n}")
        print(f"    cache READ  {sum(reads) / n:>9,.0f} tokens (mean)")
        print(f"    cache WRITE {sum(writes) / n:>9,.0f}")
        print(f"    uncached    {sum(uncached) / n:>9,.0f}")
        # Reads bill at ~0.1x and writes at ~1.25x, so this converts the token
        # split into the one number that is comparable between the arms.
        billed = (sum(reads) * 0.1 + sum(writes) * 1.25 + sum(uncached)) / n
        print(f"    billed-equivalent prefill {billed:>9,.0f} tokens")
        # Printed, not analysed. This is WHOLE-CALL wall time, so output length —
        # uncontrolled between arms — dominates it, and the only quantity prefill
        # caching should move is time-to-first-token, which `CallRecord.seconds`
        # cannot see. `probe_stream_ttft.py` measured that quantity directly and
        # came back with a null (1.46s vs 1.34s, 4/4, mechanism confirmed), so the
        # latency claim is not merely unsupported here — it is settled elsewhere,
        # against. Do not build one from these seconds; see the round write-up.
        print(f"    whole-call seconds {sum(seconds) / n:>6.1f}s mean"
              f"   ({', '.join(f'{s:.1f}' for s in seconds)})"
              "   <- NOT a latency measurement, see docstring")

    on, off = by_arm[True], by_arm[False]
    if on and off:
        read_on = sum(t.engine_call.cache_read_tokens for t in on) / len(on)
        read_off = sum(t.engine_call.cache_read_tokens for t in off) / len(off)
        print(f"\n  engine tokens served from cache after a dump change:"
              f" {read_on:,.0f} with the split vs {read_off:,.0f} without")
        if read_on > read_off * 2 and read_on > _ENGINE_PREFILL_FLOOR:
            # Reads bill at ~0.1x and writes at ~1.25x, so this is the figure that
            # turns into money and latency.
            print("  The fix works: the stable engine survives a dump change.")
        elif read_on <= read_off:
            print("  NO EFFECT. Do not claim the fix works — check whether the"
                  "\n  prefix cleared the model's 4,096-token minimum and whether"
                  "\n  anything before `system` in the request is varying per turn.")
        else:
            print("  PARTIAL. Report the numbers, not a verdict.")

    # Warm turns are printed rather than analysed: each is a cold prefix by
    # construction (unique persona marker), so a write there is expected and a read
    # would mean the markers are not doing their job.
    warm_reads = [
        w.engine_call.cache_read_tokens for w, _ in pairs
        if w.clean and w.engine_call.cache_read_tokens
    ]
    if warm_reads:
        print(f"\n  WARNING: {len(warm_reads)} warm turn(s) read from cache."
              " The per-arm persona markers are supposed to make every arm-run a"
              " cold prefix — if they are not, the arms can serve each other's"
              " entries and the comparison above is contaminated.")
