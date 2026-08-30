"""Probe: what did removing the second provider round actually buy per turn?

WHY
===
With tools wired, every conversation turn used to end with an EXTRA structured
`_call_with_response_model` round that re-rendered prose the tool-round call had
already written — even when the model requested no tools, because the loop breaks
and falls through. `_reuse_written_reply` (2026-08-30) removed it from the common
turn. The saving was never measured; `rounds.md` recorded it as arithmetic and
said so.

`timing-after-one-round` then tried to measure it on the bench and **could not**:
the model elected 13 tool calls against the baseline's 3, and tool election
decides how big the graph — and so the system prompt — is on every later turn.
Pairing turns by position gave a median delta of +2.2s spread from −9.5s to
+13.7s, an order of magnitude wider than the effect. One run per build cannot see
a per-turn saving through that.

So this probe controls what the bench cannot. ONE fixed prompt, ONE fixed user
message, a FRESH `Advisor` per measurement so no history accumulates, and
`_reuse_written_reply` toggled as the only variable. Arms run as ADJACENT PAIRS
and are reported as paired deltas: provider latency drifts over minutes, and two
pooled samples would book that drift as the effect.

WHAT IT MEASURES, AND WHICH HALF TO TRUST
=========================================
Two quantities, and they are not equally reliable — the lesson
`probe_explore_cost.py` learned the hard way ("the call count is the
deterministic half; the wall clock is one sample of a noisy quantity"):

- **EXTRACTION calls per turn, from `utils/call_census.py` — deterministic.** A
  clean reuse turn asks for 0 structured extractions; the same turn with reuse
  off asks for exactly 1. This cannot come out any other way, and if it does the
  change is not doing what it claims. `format_name` is the discriminator: the
  extraction call carries `ChatResponse`, a tool round carries `None`, and
  anything else is off-path machinery. Note the census only sees the
  NON-streaming path (`use_brain` returns before `record_call` when
  `raw_call=True`), which is exactly why this probe drives `chat()` and not
  `chat_stream()` — on the streaming path the first call would be invisible.
  Count extractions, NOT total calls: `chat()` also runs the decision repair
  after handing the reply over, and that repair's own provider call belongs to
  neither arm. This probe's first run asserted on the total and failed at 2-vs-3
  with both shapes perfectly correct.
- **Seconds, paired — noisy, and the actual question.** Measured as
  `last_submit_seconds`, the reply path, so the off-path repair is outside the
  number. Report the paired distribution, not a median of medians. Deltas are
  ALSO split by which arm ran first: provider latency can carry a within-pair
  position component, and the effect here is small enough that a position effect
  would be mistaken for it. Alternating order makes that recoverable rather than
  fatal — with the strata balanced the mean delta stays unbiased for the arm, and
  `_report_order` separates the two. Read that split before quoting a median.

Turns are CLASSIFIED, not assumed: a turn whose model elected a tool spent its
seconds on the tool rather than on this question, so it is discarded and counted
as discarded. Never silently. Classified from `last_tool_calls` — **the census
cannot answer this**, because only `_call_with_tools` is `@use_brain`-decorated
and the loop's `response.resume()` continuations therefore never reach
`record_call`. A turn that ran five tool rounds records exactly ONE
`format_name=None` call, the same as a turn that ran none. This probe's 12-pair
run classified on that count and admitted five tool-electing turns as clean
single generations — one of them 92.8s with 70 recorded concern calls — putting
−48s and +77s deltas into a comparison of a sub-second effect.

An empty graph is deliberate. It renders `EMPTY_UNDERSTANDING`, so the prompt is
the ~15.6k-token engine and nothing else — the FLOOR of the saving, since the
skipped round re-sends the whole prompt and a real conversation's dump only makes
it bigger. The rendered size is printed so the number stays interpretable, and
`timing-after-one-round` measured dumps big enough to cost 5.9s just to render.

    poetry run pytest tests/e2e/probe_reply_reuse_saving.py -s --real-llm

`DIALEXITY_PROBE_REUSE_PAIRS=1` for a single pair when the question is only
"is the call count right". A retry account runs alongside, so a laddering call
cannot masquerade as work — the failure mode that made r26's `anchor` median
meaningless.
"""

from __future__ import annotations

import os
import statistics
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.driver import E2E_PERSONA, E2E_PRINCIPAL
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import CallCensus, call_census
from dialectical_framework.utils.retry_accounting import retry_account

#: Conversational on purpose. The saving lives on the turn that calls no tool —
#: `timing-after-audit-gather` and `timing-check-building` both put
#: `tool_seconds` at a median of 0.00s, so the tool-free turn IS the median turn
#: and it is the one a person feels. A message inviting `anchor` would measure
#: `anchor`, which two other probes already do.
USER_MESSAGE = (
    "I keep going back and forth on whether to have a hard conversation with my "
    "business partner or just let it ride for another quarter. What should I be "
    "asking myself?"
)

#: Each pair is one reuse-on turn and one reuse-off turn, adjacent. 4 pairs is 8
#: turns; at a ~20s tool-free turn that is a few minutes, and pairing means the
#: count buys precision on the delta rather than on either arm's absolute level.
PAIRS = max(1, int(os.getenv("DIALEXITY_PROBE_REUSE_PAIRS", "4")))

#: `_reuse_written_reply` returns None for every documented refusal reason, so
#: this is the pre-change path exactly: the structured call runs and answers.
_REUSE_OFF = lambda self, response, response_model, *, text=None: None  # noqa: E731


def _system_prompt_text(facilitator: ConversationFacilitator) -> str:
    """The rendered system prompt, read off message 0.

    There is no reader for this — `set_system_prompt` only writes — and the
    message's `content` is a `Text` part rather than a string, so pull the text
    out defensively rather than assuming either shape.
    """
    messages = getattr(facilitator, "_messages", None) or []
    if not messages:
        return ""
    content = getattr(messages[0], "content", None)
    if isinstance(content, str):
        return content
    for candidate in (content, *(content if isinstance(content, list) else ())):
        text = getattr(candidate, "text", None)
        if isinstance(text, str):
            return text
    return ""


class _Turn:
    """One measured turn, classified by what the census saw.

    `submit_s` is the number, not `waited`. `Advisor.chat` runs the decision
    repair AFTER handing the reply over, and that repair makes a provider call of
    its own — so `chat()`'s wall clock contains a whole extra round-trip that
    belongs to neither arm. The first run of this probe asserted on total calls
    and failed at 2-vs-3 for exactly that reason: the shapes were right and the
    arithmetic was counting off-path machinery. `reply_path_s` in the bench is
    defined the same way this is (`context_render_s + last_submit_seconds`).
    """

    #: Structured calls that are neither the reply nor a tool round: the decision
    #: repair's classifier, which runs off-path in BOTH arms.
    def __init__(
        self,
        reuse: bool,
        waited: float,
        submit_s: float,
        census: CallCensus,
        account,
        *,
        first: bool,
        prompt_chars: int,
        tool_calls: list[str],
    ):
        self.reuse = reuse
        self.waited = waited
        self.submit_s = submit_s
        self.census = census
        self.account = account
        #: Ran first within its pair. Recorded because the first six pairs showed
        #: the SECOND turn slower in 5 of 6, by about the size of the effect —
        #: order has to be visible in the report or it gets read as the arm.
        self.first = first
        #: Rendered system prompt for THIS turn. Turns get their own Case now, so
        #: this SHOULD be constant; it is measured rather than assumed because a
        #: shared `sid` once let a tool-electing turn grow every later prompt from
        #: 62,794 to 74,808 chars, and the deltas silently stopped being paired.
        self.prompt_chars = prompt_chars
        #: Tools the model actually elected, from `last_tool_calls`.
        #: THE classifier — and the census cannot do this job. Only
        #: `_call_with_tools` is `@use_brain`-decorated, so the tool loop's
        #: `response.resume()` continuations never reach `record_call`: a turn
        #: that ran five tool rounds still records exactly ONE `format_name=None`
        #: call. Classifying on that count read 5 tool-electing turns (one of
        #: them 92.8s, with 70 recorded concern calls) as clean single
        #: generations, which is how −48s and +77s deltas got into a comparison
        #: of an 0.9s effect.
        self.tool_calls = list(tool_calls)
        self.tool_rounds = sum(1 for c in census.calls if c.format_name is None)
        self.extractions = sum(
            1 for c in census.calls if c.format_name == "ChatResponse"
        )
        self.off_path = census.count - self.tool_rounds - self.extractions

    @property
    def clean(self) -> bool:
        """No tool elected, so the submit path is one generation and this turn
        answers the question. `off_path` is checked too as a cross-check on a
        DIFFERENT instrument: the ordinary turn runs exactly one off-path call
        (the decision repair's classifier), and a tool's concern pipeline shows
        up there in the dozens even though the loop's own rounds do not."""
        return not self.tool_calls and self.off_path == 1

    @property
    def calls(self) -> int:
        return self.census.count

    def line(self) -> str:
        why = ""
        if self.tool_calls:
            why = f"   DISCARDED: elected {','.join(sorted(set(self.tool_calls)))}"
        elif self.off_path != 1:
            why = f"   DISCARDED: {self.off_path} off-path calls, expected 1"
        return (
            f"  reuse={'on ' if self.reuse else 'off'}"
            f" {'1st' if self.first else '2nd'}  "
            f"submit {self.submit_s:6.1f}s  (chat {self.waited:6.1f}s)  "
            f"calls {self.calls} = {self.tool_rounds} recorded raw"
            f" + {self.extractions} extraction + {self.off_path} off-path  "
            f"prompt {self.prompt_chars:,}  retries {self.account.count}"
            + why
        )


async def _one_turn(monkeypatch, di_container, *, reuse: bool, first: bool) -> _Turn:
    """A FRESH Advisor AND a fresh Case every time: identical prompt, one user
    message, no history, and an empty graph.

    History is what made the bench uninterpretable. A second turn carries the
    first turn's reply in its prompt, so its generation is a different size of
    work; starting clean makes every measurement the same measurement.

    The Case is per-turn for the same reason one level down. Sharing one `sid`
    across the run means a turn that elects `anchor` writes perspectives, and
    every LATER turn then renders a bigger dump — measured at 62,794 → 74,808
    chars mid-run, at which point the arms are no longer being compared on equal
    work. Now a tool-electing turn can only spoil ITSELF, and it is discarded.
    """
    with monkeypatch.context() as patch:
        if not reuse:
            patch.setattr(
                ConversationFacilitator, "_reuse_written_reply", _REUSE_OFF
            )
        case = Case()
        case.commit()
        advisor = Advisor(app_preamble=E2E_PERSONA, principal=E2E_PRINCIPAL)
        census = CallCensus()
        with scope(case.sid), call_census(census), retry_account() as account:
            started = time.monotonic()
            await advisor.chat(USER_MESSAGE)
            waited = time.monotonic() - started
        submit_s = advisor._conversation.last_submit_seconds
        # Read AFTER the turn: `set_system_prompt` runs at submit time, so before
        # the call there is nothing to read.
        prompt_chars = len(_system_prompt_text(advisor._conversation))
        tool_calls = list(advisor._conversation.last_tool_calls)
    return _Turn(
        reuse, waited, submit_s, census, account,
        first=first, prompt_chars=prompt_chars, tool_calls=tool_calls,
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_reply_reuse_saving(monkeypatch, di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")

    # Pairs kept as pairs from the start. Reconstructing them afterwards by
    # position is how a discarded turn silently re-pairs its neighbour with the
    # wrong partner.
    pairs: list[tuple[_Turn, _Turn]] = []
    with using_model(di_container, DEFAULT_TIER_WEAK):
        # Printed so the seconds below are interpretable: the skipped round
        # re-sends this whole thing, so its size IS the saving's scale.
        probe = Advisor(app_preamble=E2E_PERSONA, principal=E2E_PRINCIPAL)
        rendered = _system_prompt_text(probe._conversation)
        print(
            f"system prompt: {len(rendered):,} chars ≈ {len(rendered)//4:,} tokens"
            "  (empty graph — EMPTY_UNDERSTANDING, so this is the FLOOR)"
        )
        print(f"pairs: {PAIRS}  message: {USER_MESSAGE[:56]}...\n")

        for i in range(PAIRS):
            # Order alternates so a warming provider cannot systematically
            # favour whichever arm happens to run first.
            order = (True, False) if i % 2 == 0 else (False, True)
            run: list[_Turn] = []
            for position, reuse in enumerate(order):
                turn = await _one_turn(
                    monkeypatch, di_container,
                    reuse=reuse, first=position == 0,
                )
                run.append(turn)
                print(turn.line())
            on = next(t for t in run if t.reuse)
            off = next(t for t in run if not t.reuse)
            pairs.append((on, off))

    turns = [t for pair in pairs for t in pair]
    print()
    _report(pairs)

    # Assertions gate the MEASUREMENT's coherence, never a duration — the same
    # discipline as `probe_anchor_retry_cost.py`. A probe that gates on seconds
    # fails on a provider's bad afternoon and teaches nothing.
    for turn in turns:
        assert turn.account.wasted_s <= turn.waited + 1.0, (
            "recorded retry waste exceeds the turn's own wall clock"
        )
    clean = [t for t in turns if t.clean]
    assert clean, (
        "every turn elected a tool, so this run measured tools and not the"
        " reply path — rerun, or reword USER_MESSAGE"
    )
    # The deterministic half, and the whole claim: reuse answers from the text
    # already written, so a clean reuse turn asks for NO structured extraction
    # and the same turn without it asks for exactly one. Asserted on the
    # EXTRACTION count, not on total calls — `chat()`'s total also contains the
    # off-path decision repair, which belongs to neither arm. The first run of
    # this probe failed at 2-vs-3 for precisely that reason: the shapes were
    # right and the arithmetic was counting machinery.
    for turn in clean:
        expected = 0 if turn.reuse else 1
        assert turn.extractions == expected, (
            f"reuse={turn.reuse} clean turn made {turn.extractions} extraction"
            f" calls, expected {expected} — the call SHAPE is the claim being"
            " tested, and it did not hold"
        )


def _report(pairs: list[tuple[_Turn, _Turn]]) -> None:
    turns = [t for pair in pairs for t in pair]
    clean = [t for t in turns if t.clean]
    print(f"  clean turns: {len(clean)}/{len(turns)}", end="")
    if len(clean) != len(turns):
        print(f"   DISCARDED {len(turns)-len(clean)} (a tool fired — not this question)")
    else:
        print()

    on = [t for t in clean if t.reuse]
    off = [t for t in clean if not t.reuse]
    if not on or not off:
        print(
            "  NOT COMPARABLE: one arm has no clean turn. Report that and do not"
            " read a delta off the arm that survived."
        )
        return

    print(
        f"\n  extractions per turn — reuse on:"
        f" {sorted(t.extractions for t in on)}"
        f"   off: {sorted(t.extractions for t in off)}   (deterministic)"
    )
    print(f"  reuse ON   n={len(on):2d}  median submit"
          f" {statistics.median([t.submit_s for t in on]):6.1f}s"
          f"   {sorted(round(t.submit_s,1) for t in on)}")
    print(f"  reuse OFF  n={len(off):2d}  median submit"
          f" {statistics.median([t.submit_s for t in off]):6.1f}s"
          f"   {sorted(round(t.submit_s,1) for t in off)}")

    # A pair counts only when BOTH its turns are clean: each delta is then a
    # difference measured seconds apart, which is the one comparison provider
    # drift cannot forge. A half-clean pair has no partner and is not a delta.
    usable = [(a, b) for a, b in pairs if a.clean and b.clean]
    deltas = [off_t.submit_s - on_t.submit_s for on_t, off_t in usable]
    if deltas:
        print(
            f"\n  PAIRED saving (off − on), n={len(deltas)}:"
            f" median {statistics.median(deltas):+.1f}s"
            f"  mean {statistics.fmean(deltas):+.1f}s"
            f"   {[round(d, 1) for d in deltas]}"
        )
        _report_order(usable, deltas)
        if len(deltas) > 1 and min(deltas) * max(deltas) < 0:
            print(
                "  Deltas STRADDLE ZERO. Read the order split above before"
                " quoting\n  anything: if the split is wide, the spread is"
                " position and not noise."
            )
    else:
        print("\n  No pair had both turns clean, so there is no paired delta.")
    print(
        f"  provider seconds, whole chat() — on median"
        f" {statistics.median([t.census.provider_s for t in on]):.1f}s,"
        f" off median {statistics.median([t.census.provider_s for t in off]):.1f}s"
    )
    print(
        "\n  Read the extractions column first. If it is 0 vs 1 the round is gone,"
        "\n  whatever the clock says; the seconds are one sample of a noisy"
        "\n  quantity and the paired median is the only one worth quoting."
    )
    # A drift check, not a comparison: every turn shares one `sid`, so a turn
    # that wrote to the graph would make every LATER prompt bigger work and the
    # run would not be measuring one thing twelve times. Constant = it didn't.
    sizes = {t.prompt_chars for t in turns}
    if len(sizes) == 1:
        print(f"  prompt was identical on all {len(turns)} turns"
              f" ({next(iter(sizes)):,} chars) — no graph drift")
    else:
        print(
            f"  PROMPT DRIFTED across turns: {sorted(sizes)} chars. Something"
            "\n  wrote to the shared graph, so the later turns are a different"
            "\n  size of work and the deltas are not paired on equal prompts."
        )


def _report_order(usable: list[tuple[_Turn, _Turn]], deltas: list[float]) -> None:
    """Split the deltas by WHICH ARM RAN FIRST, and separate the two effects.

    Provider latency has a within-pair position component — the first six pairs
    put the second turn slower in 5 of 6, by about the size of the effect being
    measured. Alternating the order makes that recoverable instead of fatal.
    Writing `submit = μ + a·(reuse off) + p·(ran second)`:

        on-first  pair delta = off(2nd) − on(1st) =  a + p
        off-first pair delta = off(1st) − on(2nd) =  a − p

    so `a = (mean_on_first + mean_off_first) / 2` and `p` is their half-difference.
    With the strata BALANCED the plain mean of all deltas already equals `a`; when
    they are not, it is biased by `p` and only the stratified figure is honest.
    """
    on_first = [d for d, (a, _) in zip(deltas, usable) if a.first]
    off_first = [d for d, (_, b) in zip(deltas, usable) if b.first]
    if not on_first or not off_first:
        print(
            "  ORDER NOT BALANCED: every usable pair ran the same arm first, so"
            "\n  the arm effect and the position effect are the same number here."
        )
        return
    print(
        f"    by order — reuse-on first (n={len(on_first)}):"
        f" mean {statistics.fmean(on_first):+.1f}s"
        f"   {[round(d, 1) for d in on_first]}"
    )
    print(
        f"              reuse-off first (n={len(off_first)}):"
        f" mean {statistics.fmean(off_first):+.1f}s"
        f"   {[round(d, 1) for d in off_first]}"
    )
    arm = (statistics.fmean(on_first) + statistics.fmean(off_first)) / 2
    position = (statistics.fmean(on_first) - statistics.fmean(off_first)) / 2
    print(
        f"    ORDER-ADJUSTED: extra round costs {arm:+.1f}s,"
        f" running second costs {position:+.1f}s"
    )
    if len(on_first) != len(off_first):
        print(
            f"    (strata uneven, {len(on_first)}/{len(off_first)} — the plain"
            " mean above is biased by position; use this line)"
        )
    if abs(position) >= abs(arm) / 2:
        print(
            "    Position is not small next to the arm. Any single unpaired"
            "\n    comparison of these two builds would be mostly measuring it."
        )
