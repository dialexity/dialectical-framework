"""
probe_extraction_thinking_ab — does thinking make extraction FAITHFUL?

The biggest measured reasoning defect in this tree is extraction: on the shipped
path, ~35-39% of the theses step 2 emits are not cleanly supported by their own
source and 13% are invented outright (`probe_support_validity.py`, instrument
validated at specificity 93% / sensitivity 100%). Every structured concern call
has run without extended thinking because its formatting mode forbids it;
`ConversationFacilitator(format_mode="json", thinking=...)` can put a concern
into JSON mode with thinking. This prices that switch on the defect it is aimed
at. (A setting for it existed for one day and was removed on this probe's
result; the arm is built by swapping the concern's constructor.)

DESIGN. Two arms, the shipped default and JSON mode with thinking at medium,
over the three documents `probe_step2_isolate_ab.py` already uses, REPS reps each,
arms interleaved per document. Each arm runs the whole of `extract_candidates`
(step 1 + the step-2 gate) — thinking applies to both — and every emitted thesis
is rated UNPAIRED against its source by the same `_support` judge the validation
round certified: no second set to be longer than, no position to prefer, no tie
to hide in. Endpoints, pre-registered here:

  PRIMARY    invented rate (the instrument's clean class: 0/39 false positives)
  SECONDARY  distorted rate (over-reads compression; read as a bound)
  ALSO       yield (candidates per run), seconds, output tokens

READ IT AS: a drop in `invented` at similar yield is the lever working; a drop
bought by yield falling is the gate getting stricter, which is a different thing
and may or may not be wanted. Per-item verdicts are printed so the rate can be
audited after the run.

NOT free: `--real-llm`. ~2 arms x 3 documents x REPS x (1 + ~10 gate calls),
the thinking arm at ~8s a call, plus one strong-tier judge call per set.

    DIALEXITY_PROBE_REPS=2 poetry run pytest \
        tests/e2e/probe_extraction_thinking_ab.py --real-llm -s

RESULT (2026-09-18, 3 documents x 2 reps, 136 rated claims) — DECLINED:

    arm               runs  yield/run  median s  out tok/run  supported distorted invented  invented%  not-supported%
    default              6      13.5       6.0          984         53        23        5      6.2%          34.6%
    thinking=medium      6       9.2      27.9         9221         39         9        7     12.7%          29.1%

The primary went the wrong way; the 5pp fall in not-supported was bought by a
third less yield (a stricter gate, not a more faithful one) at 4.6x the wall and
9x the output tokens. "Not shown, and not cheap enough to keep looking" — not
"thinking hurts extraction": n is small and this is one document set. The knob
stays opt-in and off (`rounds.md`, `probe-extraction-thinking-ab`).

ON SONNET 5 (2026-09-19, `DIALEXITY_PROBE_MODEL`, Fable as judge): default 3.5%
invented / 7.0% not-supported, thinking 0.0% / 9.1% — the defect is 5x smaller
from the MODEL alone and thinking moves nothing outside noise at no extra cost
(`rounds.md`, `sonnet-thinking`). The lever the defect responds to is which
model runs the extraction concern.
"""

from __future__ import annotations

import os
import statistics
import time
from collections import Counter
from contextlib import contextmanager
from typing import Iterator

import pytest

import probe_step2_isolate_ab as ps2
from dialectical_framework.concerns.thesis_extraction import ThesisExtraction
from dialectical_framework.utils.call_census import call_census
from e2e.config import DEFAULT_JUDGE, DEFAULT_TIER_STRONG, DEFAULT_TIER_WEAK
from e2e.modelctx import using_model
from probe_step2_isolate_ab import COUNT, DOCUMENTS, _support

REPS = int(os.getenv("DIALEXITY_PROBE_REPS", "2"))
ARMS = {"default": None, "thinking=medium": "medium"}
#: The model under test. Every figure is model-conditional (the 2026-09-18 run
#: was Haiku 4.5), so the same probe answers for Sonnet 5 by pointing this at it.
MODEL = os.getenv("DIALEXITY_PROBE_MODEL", DEFAULT_TIER_WEAK)
if MODEL == DEFAULT_TIER_STRONG:
    # The support judge is the strong tier by default; judging Sonnet's own
    # output with Sonnet would be self-preference, so the judge steps up.
    ps2.DEFAULT_TIER_STRONG = DEFAULT_JUDGE


@contextmanager
def _extraction_thinking(level: str | None) -> Iterator[None]:
    """Put the extraction concern's calls into JSON mode with thinking.

    There is no setting for this any more — the knob was removed after this
    probe showed thinking buys nothing on either tier — so the arm is built
    here, on the facilitator capability that remains, by swapping the
    concern's constructor for the probe's duration.
    """
    if not level:
        yield
        return
    from dialectical_framework.agents.conversation_facilitator import \
        ConversationFacilitator

    original = ThesisExtraction.__init__

    def thinking_init(self) -> None:
        self._conversation = ConversationFacilitator(format_mode="json", thinking=level)

    ThesisExtraction.__init__ = thinking_init  # type: ignore[method-assign]
    try:
        yield
    finally:
        ThesisExtraction.__init__ = original  # type: ignore[method-assign]


async def _extract(container, level: str | None, text: str) -> dict:
    with _extraction_thinking(level), using_model(container, MODEL):
        with call_census() as census:
            started = time.monotonic()
            candidates = await ThesisExtraction().extract_candidates(text, count=COUNT)
            seconds = time.monotonic() - started
    return {
        "candidates": candidates,
        "seconds": seconds,
        "calls": census.count,
        "output_tokens": sum((c.output_tokens or 0) for c in census.calls),
        "prefill_tokens": sum((c.prefill_tokens or 0) for c in census.calls),
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_extraction_thinking_ab(di_container):
    print(
        f"\nmodel: {MODEL}  judge: {ps2.DEFAULT_TIER_STRONG}\n"
        f"documents: {len(DOCUMENTS)}  reps: {REPS}  count: {COUNT}  arms: {list(ARMS)}"
    )
    verdicts: dict[str, Counter] = {arm: Counter() for arm in ARMS}
    runs: dict[str, list[dict]] = {arm: [] for arm in ARMS}
    misaligned: Counter = Counter()

    for name, document in DOCUMENTS.items():
        for rep in range(REPS):
            for arm, level in ARMS.items():
                run = await _extract(di_container, level, document)
                rated = await _support(di_container, document, run["candidates"])
                if rated is None:
                    misaligned[arm] += 1
                    rated = []
                run["verdicts"] = rated
                runs[arm].append(run)
                verdicts[arm].update(rated)
                print(
                    f"  {name:15s} rep {rep + 1} {arm:16s} {run['seconds']:6.1f}s "
                    f"calls={run['calls']:2d} out={run['output_tokens']:5d} "
                    f"yield={len(run['candidates']):2d} "
                    f"{dict(Counter(rated))}"
                )
                for thesis, verdict in zip(run["candidates"], rated):
                    if verdict != "supported":
                        print(f"      [{verdict}] {thesis[:110]}")

    print("\narm               runs  yield/run  median s  out tok/run  supported  distorted  invented   invented %  not-supported %")
    for arm in ARMS:
        rows = runs[arm]
        total = sum(verdicts[arm].values())
        inv = verdicts[arm]["invented"]
        dis = verdicts[arm]["distorted"]
        sup = verdicts[arm]["supported"]
        print(
            f"{arm:16s} {len(rows):5d}  {statistics.mean(len(r['candidates']) for r in rows):8.1f}  "
            f"{statistics.median(r['seconds'] for r in rows):8.1f}  "
            f"{statistics.mean(r['output_tokens'] for r in rows):11.0f}  "
            f"{sup:9d}  {dis:9d}  {inv:8d}   "
            f"{(100 * inv / total if total else 0):9.1f}%  "
            f"{(100 * (inv + dis) / total if total else 0):14.1f}%"
        )
    if misaligned:
        print(f"discarded (judge misaligned): {dict(misaligned)}")
    print(
        "\nread: PRIMARY is the invented rate at similar yield; a drop bought by "
        "yield falling is a stricter gate, not a more faithful one."
    )
