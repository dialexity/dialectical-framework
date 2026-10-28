"""Is the thesis-fit judge stable, and does it tell draws of one utterance apart?

The gate the 2026-10-20 handoff named for `concerns/thesis_fit_check.py`
(`docs/dev-notes/antithesis-selection.md`, "The hedge wins on coherence", proposal 3). The term ranks INSIDE
the pass rule (`tetrad_candidates.ranking`), so it only ever changes an outcome
when two draws of the SAME utterance disagree on it — which makes
discrimination, not accuracy, the question that decides whether the term is
inert. Both arms run on drafts already stored, so nothing is generated.

Two arms, over `results/tetrad_quality/view_turn_*.json` (utterance + the six
texts; the three `view_turn_pin_*` files also carry the runners-up):

- STABILITY: every item judged twice. Reads: agreement on `fits` at
  `THESIS_FIT_THRESHOLD`, the mean absolute shift in `fit`, and how often the
  two reads land on opposite sides of the line. The convention carried from the
  coherence judge (`probe_joint_judge_stability.py`): self-agreement below ~85%
  means the term is noise and must not rank.
- DISCRIMINATION: for each utterance with spares, the winner and every spare
  judged once. Reads: how often the field is NOT unanimous on `fits` (the only
  case where the term moves a choice), and how often a spare outranks the
  winner on fit — the handoff's own case, where the demand was drawn twice and
  the hedge won.

The model comes from the BENCH CONFIG, never from this file (`tests/e2e/config.py`:
"models come from the environment, never from code"): the arm runs under
`modelctx.using_model` on the tier `E2EConfig.from_env()` reports, which also
pins the reasoning model so a local `DIALEXITY_REASONING_MODEL` cannot split
the arm across two providers unnoticed. `FIT_TIER` picks which tier (default
the strong one); `DIALEXITY_E2E_TIER_*` in `.env` says what that tier is.

Provider note: a structured call is legal on the native `anthropic/` provider
(measured 2026-10-26: Sonnet 5.5 and Sonnet 5 both parse `ThesisFitDto`),
although the compat shims in `utils/bedrock_provider.py` are reached only for a
`bedrock/` model — so a tier on either provider runs this probe.

    poetry run pytest tests/e2e/probe_thesis_fit_judge.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import glob
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Optional

import pytest

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
#: Which configured tier answers. The model ITSELF is never written here.
_TIER = os.environ.get("FIT_TIER", "strong")
_CONCURRENCY = 6
#: Bounded so a re-run costs the same; the stability arm is 2 calls an item.
_MAX_STABILITY_ITEMS = int(os.environ.get("FIT_ITEMS", "40") or 40)


def _arm_model() -> str:
    """The tier's model id, from the bench config."""
    from config import E2EConfig

    return E2EConfig.from_env(tiers=[_TIER]).tiers[_TIER]


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def _fmt(k: int, n: int) -> str:
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}-{100*hi:.0f}%)"


def _complete(row: dict) -> bool:
    return bool(
        (row.get("utterance") or "").strip()
        and (row.get("thesis") or "").strip()
        and (row.get("antithesis") or "").strip()
        and (row.get("a_plus") or "").strip()
    )


def _items() -> list[dict]:
    """One item per (utterance, thesis), newest file wins, in a fixed order."""
    seen: dict[tuple[str, str], dict] = {}
    for path in sorted(glob.glob(str(_RESULTS / "view_turn_*.json"))):
        try:
            rows = json.loads(Path(path).read_text())
        except Exception:  # noqa: BLE001 — a probe skips an unreadable file
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or not _complete(row):
                continue
            key = (row["utterance"], row["thesis"])
            seen[key] = {
                "utterance": row["utterance"],
                "thesis": row["thesis"],
                "antithesis": row["antithesis"],
                "a_plus": row["a_plus"],
                "source": Path(path).name,
            }
    return list(seen.values())


def _fields() -> list[dict]:
    """One field per utterance: the winner plus its spares, where stored."""
    out: list[dict] = []
    for path in sorted(glob.glob(str(_RESULTS / "view_turn_*.json"))):
        try:
            rows = json.loads(Path(path).read_text())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or not _complete(row) or not row.get("spares"):
                continue
            draws = [
                {"slot": "winner", "thesis": row["thesis"],
                 "antithesis": row["antithesis"], "a_plus": row["a_plus"]}
            ]
            for i, spare in enumerate(row["spares"]):
                if isinstance(spare, dict) and all(
                    (spare.get(k) or "").strip() for k in ("thesis", "antithesis", "a_plus")
                ):
                    draws.append({
                        "slot": f"spare{i+1}", "thesis": spare["thesis"],
                        "antithesis": spare["antithesis"], "a_plus": spare["a_plus"],
                    })
            if len(draws) > 1:
                out.append({"utterance": row["utterance"], "source": Path(path).name,
                            "draws": draws})
    return out


async def _fit(gate: asyncio.Semaphore, item: dict) -> Optional[dict]:
    from dialectical_framework.concerns.thesis_fit_check import ThesisFitCheck

    async with gate:
        try:
            dto = await ThesisFitCheck().score_texts(
                thesis=item["thesis"],
                antithesis=item["antithesis"],
                a_plus=item["a_plus"],
                text=item["utterance"],
            )
        except Exception as exc:  # noqa: BLE001 — a probe records failure
            return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {
        "fit": round(dto.fit, 3),
        "claim": dto.thesis_is_the_claim,
        "a_granted": dto.antithesis_already_granted,
        "granted": dto.a_plus_already_granted,
        "reasoning": (dto.reasoning or "")[:300],
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_fit_judge_is_stable(di_container) -> None:
    from dialectical_framework.concerns.thesis_fit_check import \
        THESIS_FIT_THRESHOLD

    from modelctx import using_model

    items = _items()[:_MAX_STABILITY_ITEMS]
    assert items, "no stored view-turn draws with T/A/A+ and the person's words"
    model = _arm_model()
    print(f"\n  STABILITY on {len(items)} stored draws, tier={_TIER} model={model}", flush=True)
    gate = asyncio.Semaphore(_CONCURRENCY)
    started = time.perf_counter()
    with using_model(di_container, model):
        a, b = await asyncio.gather(
            asyncio.gather(*(_fit(gate, it) for it in items)),
            asyncio.gather(*(_fit(gate, it) for it in items)),
        )

    rows, agree, flips, shifts, passes = [], 0, 0, [], 0
    for item, ra, rb in zip(items, a, b):
        row = {**item, "a": ra, "b": rb}
        rows.append(row)
        if not ra or not rb or ra.get("error") or rb.get("error"):
            continue
        fa, fb = ra["fit"], rb["fit"]
        pa, pb = fa >= THESIS_FIT_THRESHOLD, fb >= THESIS_FIT_THRESHOLD
        agree += int(pa == pb)
        flips += int(pa != pb)
        shifts.append(abs(fa - fb))
        passes += int(pa)
    judged = len(shifts)

    out = _RESULTS / f"thesis_fit_stability-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(
        {"tier": _TIER, "model": model, "items": rows}, indent=2, ensure_ascii=False))
    print(f"    judged {judged}/{len(items)} twice in {time.perf_counter()-started:.0f}s "
          f"({sum(1 for r in rows if (r['a'] or {}).get('error') or (r['b'] or {}).get('error'))} errored)")
    print(f"    self-agreement on fits: {_fmt(agree, judged)}   (bar ~85%)")
    print(f"    opposite sides of the line: {flips}/{judged}")
    print(f"    mean |fit shift|: {sum(shifts)/max(judged,1):.3f}   max {max(shifts) if shifts else 0:.2f}")
    print(f"    pass rate on read A: {_fmt(passes, judged)}")
    print(f"    -> {out.name}", flush=True)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_fit_judge_tells_a_field_apart(di_container) -> None:
    from dialectical_framework.concerns.thesis_fit_check import \
        THESIS_FIT_THRESHOLD

    from modelctx import using_model

    fields = _fields()
    assert fields, "no stored utterance carries its runners-up"
    calls = sum(len(f["draws"]) for f in fields)
    model = _arm_model()
    print(f"\n  DISCRIMINATION on {len(fields)} fields / {calls} draws, "
          f"tier={_TIER} model={model}", flush=True)
    gate = asyncio.Semaphore(_CONCURRENCY)
    started = time.perf_counter()
    with using_model(di_container, model):
        scored = await asyncio.gather(
            *(_fit(gate, {**d, "utterance": f["utterance"]})
              for f in fields for d in f["draws"])
        )

    it = iter(scored)
    rows, split, spare_wins, unanimous_pass, unanimous_fail = [], 0, 0, 0, 0
    for f in fields:
        draws = []
        for d in f["draws"]:
            draws.append({**d, **(next(it) or {})})
        rows.append({"utterance": f["utterance"], "source": f["source"], "draws": draws})
        good = [d for d in draws if "fit" in d]
        if len(good) < 2:
            continue
        flags = [d["fit"] >= THESIS_FIT_THRESHOLD for d in good]
        if all(flags):
            unanimous_pass += 1
        elif not any(flags):
            unanimous_fail += 1
        else:
            split += 1
        winner = next((d for d in good if d["slot"] == "winner"), None)
        if winner and any(d["fit"] > winner["fit"] + 0.01 for d in good if d is not winner):
            spare_wins += 1
    fields_scored = sum(1 for r in rows if sum(1 for d in r["draws"] if "fit" in d) >= 2)

    out = _RESULTS / f"thesis_fit_discrimination-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(
        {"tier": _TIER, "model": model, "fields": rows}, indent=2, ensure_ascii=False))
    print(f"    scored {fields_scored} fields in {time.perf_counter()-started:.0f}s")
    print(f"    field SPLIT on fits (the term can move the choice): {_fmt(split, fields_scored)}")
    print(f"    unanimous pass {unanimous_pass}/{fields_scored}   unanimous fail {unanimous_fail}/{fields_scored}")
    print(f"    a spare scores higher than the winner: {_fmt(spare_wins, fields_scored)}")
    print(f"    -> {out.name}", flush=True)
