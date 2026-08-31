"""Probe: did removing the extraction round make the Advisor leak its machinery?

WHY
===
`read_reply_hygiene.py` re-scored the archive across the reply-reuse boundary and
found turns leaking framework vocabulary went **1/16 → 4/16** — hits like "the
framework flagged three distinct readings", the machinery narrating itself inside
A2's counsel. That is the silent-Advisor product claim, not a style nit.

But the two stems were not a controlled pair. The later one elected **13 tool
calls against 3**, so its sessions had far more machinery in front of them and far
more to narrate. Two explanations fit the same numbers:

1. **The confound.** More tool activity → more machinery mentioned. Nothing to do
   with the change.
2. **The mechanism.** The removed extraction round re-rendered the reply through
   `ChatResponse`, and that second pass was an accidental hygiene filter — a
   chance to drop a stray "the framework found". Removing it removed the filter.

This probe separates them by holding constant everything the bench could not.

HOW IT CONTROLS WHAT THE BENCH COULD NOT
========================================
- **ONE pre-built graph, built WITHOUT the provider.** Five hand-authored
  perspectives (`_create_perspective_with_aspects`), committed once. Both arms
  therefore narrate byte-identical machinery, which is the whole confound
  neutralised: "how much is there to mention" is no longer a variable.
- **Fixed messages, chosen to INVITE narration.** The archive's leaks landed on
  turns asking the advisor to lay out how it sees things. A message that cannot
  provoke a leak measures nothing, so these deliberately can.
- **`_reuse_written_reply` toggled as the only variable**, with a fresh `Advisor`
  per turn and adjacent alternating-order pairs — the design
  `probe_reply_reuse_saving.py` arrived at, for the same reasons.
- **Pairs are matched on prompt size.** A turn that elects a tool can WRITE to the
  shared graph, and every later prompt would then differ. A pair counts only when
  both its turns rendered the same number of characters, so it stays an internally
  matched comparison even if the graph moved between pairs.

WHAT IT MEASURES
================
`score_machinery_leak` over each reply — the same scorer, unchanged, so the number
is comparable to the archive's. Reported as **turns leaking**, not hits: hits are
±40-char windows and both a machinery term and a position label can match inside
one sentence, so one leaking sentence can report as three.

Scored TWICE: once on the scorer's full term list, and once on HARD machinery only
(see `_SOFT_TERMS`). Two of the banned terms are also ordinary advisory English,
and if one of them fires in both arms of every pair the discordant count goes to
zero and this probe prints a null it manufactured itself — indistinguishable from
a real one. The hard-only cut is the discriminating instrument; the full cut is the
one that stays comparable to the archive.

The paired statistic is **McNemar's** — only the DISCORDANT pairs carry
information. A pair where both arms leak, or neither does, says nothing about the
toggle however many of them there are; counting them dilutes a real effect toward
nothing. It is reported per MESSAGE as well as pooled, because leak propensity
clusters by question and the pooled exact test assumes pairs are independent when
16 pairs come from only 4 distinct prompts.

    poetry run pytest tests/e2e/probe_leak_reply_reuse.py -s --real-llm

`DIALEXITY_PROBE_LEAK_REPS=1` for one pass over the messages (4 pairs) as a smoke.
Assertions gate the MEASUREMENT's coherence — extraction counts, never leak counts.
A probe that fails on a leak count cannot report a null, and the null is a real
possible answer here.

WHAT A NULL HERE WOULD AND WOULD NOT MEAN
=========================================
Three things are deliberately smaller than the archive's conditions, and all three
cut AGAINST the mechanism under test: each turn is a fresh Advisor with **no
history**, where the archive's leaks landed mid-session behind seven prior
exchanges; the graph is five 7-word tetrads, about 3% of the prompt, against real
grown graphs; and only the non-streaming path is exercised, so a leak in
`chat_stream`'s pre-`ToolStart` preamble is invisible here exactly as it is to the
bench. A null is therefore a null AT THIS DOSE, not an all-clear for the change.
"""

from __future__ import annotations

import collections
import os
from math import comb

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.driver import E2E_PERSONA, E2E_PRINCIPAL
from e2e.models import SessionRecord, TurnRecord
from e2e.modelctx import using_model
from e2e.scoring import _MACHINERY_TERMS, _POSITION_LABEL, score_machinery_leak

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import CallCensus, call_census

#: Cofounder-equity readings, matching the scenario whose replies leaked. Written
#: short on purpose: `component_length` is ~7 words, and a dump of essay-length
#: components would be a different prompt shape than the framework ever produces.
_READINGS: list[tuple[str, str, str, str, str, str]] = [
    (
        "Sole founder buyout is right",
        "Board oversight serves all stakeholders",
        "Decisive ownership ends the deadlock",
        "Unilateral control without any check",
        "Shared scrutiny catches blind spots",
        "Endless consultation stalls every call",
    ),
    (
        "He earned his stake through risk",
        "Equity should track future contribution",
        "Honouring early risk keeps trust",
        "Paying forever for past courage",
        "Aligning reward with work ahead",
        "Erasing what the beginning cost",
    ),
    (
        "Preserve the friendship above all",
        "The company's survival comes first",
        "Loyalty holds the partnership together",
        "Avoiding the conversation indefinitely",
        "Clear-eyed choices protect everyone",
        "Treating a friend as a line item",
    ),
    (
        "Clear hierarchy prevents deadlock",
        "Equal partnership keeps both invested",
        "One accountable owner moves fast",
        "Authority drifting into isolation",
        "Mutual stake sustains commitment",
        "Two vetoes and no decision",
    ),
    (
        "Move now on the equity split",
        "Align on values before structure",
        "Settling terms while goodwill lasts",
        "Rushing a deal he resents",
        "Shared purpose survives hard terms",
        "Talking values to postpone deciding",
    ),
]

#: Turns that ASK the advisor to lay out how it sees things — where the archive's
#: leaks landed. A message that cannot provoke a leak measures nothing.
MESSAGES: list[str] = [
    "So what have you got so far? Lay out how you're seeing my situation.",
    "I don't follow why keeping him as a partner has any upside. Walk me through it.",
    "Of all the ways of looking at this, which is closest to the truth, and why?",
    "Before I decide anything: what am I not seeing here?",
]

#: One rep is one pass over MESSAGES, so 4 reps is 16 pairs / 32 turns. Leaks are
#: a BINARY outcome and only discordant pairs inform McNemar, so n buys much less
#: here than it did for the seconds — this needs to be run wide, not deep.
REPS = max(1, int(os.getenv("DIALEXITY_PROBE_LEAK_REPS", "4")))

#: Banned terms that are ALSO ordinary English an advisor says with no framework
#: behind them. A hit on one of these is ambiguous evidence, and — being
#: high-base-rate — it can fire in both arms of every pair, drive the discordant
#: count to zero, and turn this probe into a null-generator. So the pairs are also
#: scored with these two removed. This is NOT a softening of the contract: the
#: prompt bans them outright and `score_machinery_leak` still counts them. It is
#: this probe buying back the discrimination the base rate would eat.
_SOFT_TERMS = ("perspective", "transformation")
#: Derived from the scorer's own list so the two cannot drift apart.
_HARD_TERMS = tuple(t for t in _MACHINERY_TERMS if t not in _SOFT_TERMS)

_REUSE_OFF = lambda self, response, response_model, *, text=None: None  # noqa: E731


def _build_graph() -> str:
    """Five committed perspectives, no provider call. Returns the sid.

    Hand-built rather than grown with `anchor`, and that is the point: a graph
    built by the model would differ between arms and reintroduce exactly the
    confound this probe exists to remove. Unscored perspectives are never
    suppressed from the dump: `_apply_quality_floor` skips each check whose score
    is `None`, and hand-built aspect relationships set only `heuristic_similarity`,
    so SP/DV/validation are all `None` and the sole live check is antithesis
    HS (0.9 against a 0.5 floor). All five render.

    These perspectives are standalone by construction — no nexus is created. That
    is what keeps the helper's default `thesis_meaning="test"` safe: the only
    `parse_meaning_uri` caller is reached from `_build_cross_nexus_refs`, which is
    gated on there being more than one nexus. Add a nexus here and the placeholder
    meaning starts raising.
    """
    from test_dialectical_context import _create_perspective_with_aspects

    case = Case()
    case.commit()
    with scope(case.sid):
        for t, a, t_plus, t_minus, a_plus, a_minus in _READINGS:
            _create_perspective_with_aspects(
                thesis_text=t,
                antithesis_text=a,
                t_plus_text=t_plus,
                t_minus_text=t_minus,
                a_plus_text=a_plus,
                a_minus_text=a_minus,
            )
    return case.sid


def _system_prompt_text(facilitator: ConversationFacilitator) -> str:
    """The rendered system prompt. `content` is a `Text` part, not a string, and
    there is no reader — `set_system_prompt` only writes."""
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


def _system_prompt_chars(facilitator: ConversationFacilitator) -> int:
    return len(_system_prompt_text(facilitator))


def _leak_hits(reply: str) -> list[str]:
    """`score_machinery_leak` over a one-turn session — the scorer UNCHANGED, so
    the count is comparable to the archive's."""
    session = SessionRecord(
        label="probe", turns=[TurnRecord(index=0, user="probe", assistant=reply)]
    )
    return score_machinery_leak(session)


def _hard_terms(reply: str) -> list[str]:
    """Unambiguous machinery in the reply: the scorer's terms minus `_SOFT_TERMS`,
    plus its position labels.

    Presence is tested against the TEXT rather than filtered out of the scorer's
    snippets, because a snippet is a ±40-char window and can carry a soft term
    that sits next to a hard one — filtering on the window would drop real hits.
    Returns the terms themselves, since which kind leaked is what decides the fix.
    """
    lowered = reply.lower()
    found = [term for term in _HARD_TERMS if term in lowered]
    found.extend(sorted({m.group(0) for m in _POSITION_LABEL.finditer(reply)}))
    return found


class _Turn:
    def __init__(
        self,
        *,
        reuse: bool,
        message_index: int,
        first: bool,
        reply: str,
        submit_s: float,
        prompt_chars: int,
        tool_calls: list[str],
        census: CallCensus,
    ):
        self.reuse = reuse
        self.message_index = message_index
        self.first = first
        self.reply = reply
        self.submit_s = submit_s
        self.prompt_chars = prompt_chars
        self.tool_calls = list(tool_calls)
        self.extractions = sum(
            1 for c in census.calls if c.format_name == "ChatResponse"
        )
        self.off_path = census.count - self.extractions - sum(
            1 for c in census.calls if c.format_name is None
        )
        self.hits = _leak_hits(reply)
        self.hard = _hard_terms(reply)

    @property
    def leaked(self) -> bool:
        return bool(self.hits)

    @property
    def leaked_hard(self) -> bool:
        return bool(self.hard)

    @property
    def clean(self) -> bool:
        """No tool elected. Classified from `last_tool_calls`, NEVER from the
        census count: only `_call_with_tools` is `@use_brain`-decorated, so the
        loop's `response.resume()` continuations are invisible to it and a
        five-round turn records the same single raw call as a tool-free one."""
        return not self.tool_calls

    def line(self) -> str:
        why = ""
        if self.tool_calls:
            why = f"  DISCARDED: elected {','.join(sorted(set(self.tool_calls)))}"
        elif self.off_path != 1:
            # One off-path call is the baseline: the decision repair's classifier
            # runs on every turn. More than that means the repair went on to
            # RECORD a decision, which writes to the shared graph and moves every
            # later dump. The `prompt_chars` guard drops the affected pair, but
            # silently — this is the line that explains why one went missing.
            why = f"  off-path {self.off_path} (repair wrote to the graph?)"
        return (
            f"  m{self.message_index} reuse={'on ' if self.reuse else 'off'}"
            f" {'1st' if self.first else '2nd'}"
            f"  {self.submit_s:5.1f}s  extractions {self.extractions}"
            f"  prompt {self.prompt_chars:,}"
            f"  leak {'YES' if self.leaked else ' no'}"
            f" ({len(self.hits)} hits, hard {'YES' if self.leaked_hard else 'no'})"
            f"{why}"
        )


async def _one_turn(
    monkeypatch, sid: str, *, reuse: bool, message_index: int, first: bool
) -> _Turn:
    """A fresh Advisor on the SHARED pre-built graph: same dump, no history."""
    with monkeypatch.context() as patch:
        if not reuse:
            patch.setattr(ConversationFacilitator, "_reuse_written_reply", _REUSE_OFF)
        advisor = Advisor(app_preamble=E2E_PERSONA, principal=E2E_PRINCIPAL)
        census = CallCensus()
        with scope(sid), call_census(census):
            reply = await advisor.chat(MESSAGES[message_index])
        return _Turn(
            reuse=reuse,
            message_index=message_index,
            first=first,
            reply=reply or "",
            submit_s=advisor._conversation.last_submit_seconds,
            prompt_chars=_system_prompt_chars(advisor._conversation),
            tool_calls=list(advisor._conversation.last_tool_calls),
            census=census,
        )


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_leak_reply_reuse(monkeypatch, di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    sid = _build_graph()
    print(f"graph: {len(_READINGS)} hand-built perspectives, no provider call")

    pairs: list[tuple[_Turn, _Turn]] = []
    with using_model(di_container, DEFAULT_TIER_WEAK):
        probe = Advisor(app_preamble=E2E_PERSONA, principal=E2E_PRINCIPAL)
        with scope(sid):
            await probe._refresh_context()
        rendered = _system_prompt_text(probe._conversation)
        print(f"system prompt with that graph: {len(rendered):,} chars")

        # `_refresh_context` is fail-soft: any exception leaves the prompt at
        # EMPTY_UNDERSTANDING. An empty prompt is ~62,800 chars and five 7-word
        # tetrads add only ~2k, so a failed render prints an entirely plausible
        # number and all 32 turns then measure an empty graph while the header
        # claims five perspectives. The fixed graph is this probe's whole control,
        # so it is checked rather than hoped for — and checked here, before any
        # provider time is spent.
        assert "# Unexplored Tensions" in rendered, (
            "the perspectives did not render — `_refresh_context` fail-softed to"
            " EMPTY_UNDERSTANDING, so there is no graph to hold constant"
        )
        for reading in _READINGS:
            assert reading[0] in rendered, f"missing from the dump: {reading[0]!r}"
        print(f"reps: {REPS}  messages: {len(MESSAGES)}"
              f"  pairs: {REPS * len(MESSAGES)}\n")

        for rep in range(REPS):
            for mi in range(len(MESSAGES)):
                # Alternate which arm goes first so a warming provider — or a
                # graph a previous turn wrote to — cannot systematically favour
                # one arm.
                order = (True, False) if (rep + mi) % 2 == 0 else (False, True)
                run: list[_Turn] = []
                for position, reuse in enumerate(order):
                    turn = await _one_turn(
                        monkeypatch, sid,
                        reuse=reuse, message_index=mi, first=position == 0,
                    )
                    run.append(turn)
                    print(turn.line())
                on = next(t for t in run if t.reuse)
                off = next(t for t in run if not t.reuse)
                pairs.append((on, off))

    print()
    _report(pairs)

    turns = [t for pair in pairs for t in pair]
    clean = [t for t in turns if t.clean]
    assert clean, (
        "every turn elected a tool, so nothing here measures the reply-generation"
        " step — rerun, or reword MESSAGES"
    )
    # The measurement's coherence, and the only thing asserted. Leak counts are
    # the finding and must be free to come out either way.
    #
    # `>=` rather than `==` on the reuse-off arm: `use_brain` records a call
    # BEFORE parsing it, and a ParseError retries the round — so a single bad
    # parse legitimately shows 2 extractions. Failing the whole run for that
    # would throw away 32 real turns over a retry, so the extra is printed as a
    # note above and only ZERO is an error, because zero means the toggle did
    # nothing and the two arms were never different.
    for turn in clean:
        if turn.reuse:
            assert turn.extractions == 0, (
                f"reuse-on clean turn made {turn.extractions} extraction calls,"
                " expected 0 — the reply is not being reused, so both arms ran"
                " the same code and the comparison is meaningless"
            )
        else:
            assert turn.extractions >= 1, (
                "reuse-off clean turn made no extraction call, so the monkeypatch"
                " did not take effect and both arms ran the same code"
            )


def _exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar. Only the discordant pairs are data."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / 2**n
    return min(1.0, 2 * tail)


def _report(pairs: list[tuple[_Turn, _Turn]]) -> None:
    turns = [t for pair in pairs for t in pair]
    clean = [t for t in turns if t.clean]
    discarded = len(turns) - len(clean)
    print(f"  clean turns: {len(clean)}/{len(turns)}"
          + (f"   DISCARDED {discarded} (a tool fired)" if discarded else ""))

    # Both clean AND rendered the same prompt: a tool-electing turn can write to
    # the shared graph, and a pair whose two turns saw different dumps is not a
    # matched pair however clean each turn was on its own.
    usable = [
        (a, b) for a, b in pairs
        if a.clean and b.clean and a.prompt_chars == b.prompt_chars
    ]
    # Over the CLEAN turns only: a discarded turn's own prompt is irrelevant, and
    # counting it here would blame a graph write on a turn that was dropped anyway.
    sizes = sorted({t.prompt_chars for t in clean})
    print(f"  prompt sizes seen: {[f'{s:,}' for s in sizes]}"
          + ("" if len(sizes) == 1 else "   (a tool wrote to the graph mid-run)"))
    print(f"  usable pairs (both clean, prompts matched): {len(usable)}/{len(pairs)}")
    if not usable:
        print("\n  NOTHING COMPARABLE. Report that, not a rate off one arm.")
        return

    retried = [t for t in clean if not t.reuse and t.extractions > 1]
    if retried:
        print(f"  note: {len(retried)} reuse-off turn(s) made >1 extraction call"
              " — a ParseError retry, not a second round in the design")

    for label, leaked in (
        ("ALL terms (comparable to the archive)", lambda t: t.leaked),
        ("HARD machinery only (the discriminating cut)", lambda t: t.leaked_hard),
    ):
        print(f"\n  === {label} ===")
        on_leaks = sum(1 for a, _ in usable if leaked(a))
        off_leaks = sum(1 for _, b in usable if leaked(b))
        print(
            f"  turns leaking — reuse ON (current build): {on_leaks}/{len(usable)}"
            f"   reuse OFF (pre-change): {off_leaks}/{len(usable)}"
        )
        _mcnemar(usable, leaked, indent="  ")

        # Blocked by message, because the pooled exact test assumes independent
        # pairs and these come from only a handful of distinct prompts. If the
        # discordance lives in one message, that is a prompt finding, not a
        # plumbing one — and the pooled p was flattering it.
        print("  by message:")
        for mi in sorted({a.message_index for a, _ in usable}):
            block = [(a, b) for a, b in usable if a.message_index == mi]
            on_b = sum(1 for a, _ in block if leaked(a))
            off_b = sum(1 for _, b in block if leaked(b))
            d_on = sum(1 for a, b in block if leaked(a) and not leaked(b))
            d_off = sum(1 for a, b in block if not leaked(a) and leaked(b))
            print(f"    m{mi} n={len(block)}  on {on_b} / off {off_b}"
                  f"   discordant: on-only {d_on}, off-only {d_off}"
                  f"   | {MESSAGES[mi][:52]}")

    for label, side in (("reuse ON (current)", 0), ("reuse OFF (pre-change)", 1)):
        hits = [h for pair in usable for h in pair[side].hits]
        hard = collections.Counter(h for pair in usable for h in pair[side].hard)
        print(f"\n  {label} — hard terms said: "
              + (", ".join(f"{t}×{n}" for t, n in hard.most_common()) or "none"))
        if hits:
            print(f"  {label} — leak snippets ({len(hits)}):")
            for hit in hits:
                print(f"    · {hit!r}")


def _mcnemar(usable, leaked, *, indent: str) -> None:
    """Print the paired test. Concordant pairs carry no information about the
    toggle, so they are shown but excluded from the statistic."""
    both = sum(1 for a, b in usable if leaked(a) and leaked(b))
    neither = sum(1 for a, b in usable if not leaked(a) and not leaked(b))
    only_on = sum(1 for a, b in usable if leaked(a) and not leaked(b))
    only_off = sum(1 for a, b in usable if not leaked(a) and leaked(b))
    print(f"{indent}pairs: both leaked {both}, neither {neither},"
          f" ONLY reuse-on {only_on}, ONLY reuse-off {only_off}")
    p = _exact_mcnemar_p(only_on, only_off)
    print(f"{indent}exact McNemar on the {only_on + only_off} discordant pairs:"
          f" p={p:.3f}")
    if only_on + only_off == 0:
        if both == len(usable):
            print(f"{indent}Both arms leaked on EVERY pair. That is not a null for"
                  f"\n{indent}the toggle — it is a saturated scorer, and this cut"
                  f"\n{indent}cannot answer the question. Read the hard-only cut.")
        else:
            print(f"{indent}Every pair agreed. At this n that is a NULL for the"
                  f"\n{indent}toggle: so the archive's 1/16 → 4/16 is better"
                  f"\n{indent}explained by tool election than by the extraction"
                  f"\n{indent}round — at this dose (see the docstring).")
    elif p >= 0.05:
        print(f"{indent}Not separable at this n. Report the direction and the"
              f"\n{indent}count; do NOT convert it into a rate difference.")
