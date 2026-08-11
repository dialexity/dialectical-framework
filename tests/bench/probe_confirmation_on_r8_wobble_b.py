"""Why did the repair not fire on a decision the person stated outright?

`claim2-weak-r8-pathways` / wobble_b closed with the person saying "Go ahead and
write that down as the decision — buyout, this quarter" and the run recorded
ZERO decisions, which means `DecisionConfirmationCheck` either returned
not-recordable or fell through its fail-soft path. Those are different bugs (a
classifier false negative vs an infrastructure fault) and the bench log does not
capture the distinction, so this replays the exact saved turn against the weak
tier and prints the verdict.

Read-only with respect to the graph: the check "creates/mutates nothing".

    poetry run pytest tests/bench/probe_confirmation_on_r8_wobble_b.py \
        --real-llm -s
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dialectical_framework.concerns.decision_confirmation_check import \
    DecisionConfirmationCheck
from bench.config import BenchConfig
from bench.modelctx import using_model

_RECORD = (
    Path(__file__).parent / "results" / "claim2-weak-r8-pathways.json"
)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_replay_the_confirmation_check(di_container) -> None:
    if not _RECORD.exists():
        pytest.skip(f"no saved record at {_RECORD}")

    runs = json.loads(_RECORD.read_text())["runs"]
    run = next(r for r in runs if r["branch"] == "wobble_b")
    turn = run["sessions"][0]["turns"][-1]

    # On the WEAK tier, not the default model: the whole point is that this
    # classifier ran on haiku inside the failing cell.
    weak = BenchConfig.from_env(tiers=["weak"]).tiers["weak"]
    print("\n--- model:", weak)
    with using_model(di_container, weak):
        verdict = await DecisionConfirmationCheck().resolve(
            user_message=turn["user"],
            assistant_message=turn["assistant"] or "",
        )

    print("\n--- verdict:", verdict)
    if verdict is None:
        print("FELL THROUGH fail-soft: an infrastructure fault, not a judgement")
    else:
        print("confirmed   :", verdict.confirmed)
        print("recordable  :", verdict.is_recordable)
        print("question    :", repr(verdict.question))
        print("stance      :", repr(verdict.stance))
        print("polarity    :", repr(verdict.chosen_polarity_hash))
        print("side        :", repr(verdict.chosen_side))
    # Diagnostic only — the point is the printed verdict, not a pass/fail gate.
    # The saved turn is an unambiguous confirmation, so a not-recordable verdict
    # here IS the finding.
