"""
Mocked wiring check for the two ported lanes.

Separate from `test_e2e.py` because that file is deliberately DB-free and
brain-free (`pytestmark = []`, autouse fixtures overridden), and these two tests
need the mock brain: their whole point is that `StanceJudge` and `MemoryJudge`
actually GET CALLED and that their output lands where the report reads it.

What this can and cannot prove
==============================
It proves plumbing: the runner selects the right records by `ScenarioKind`, the
judges' `submit` path constructs, and the scores attach to `MachineScores` under
the cell key the report indexes by. It proves NOTHING about the verdicts —
`mock_brain` returns an identical DTO every call, so every rung comes back with
the same stance. The derived quantities are tested directly in
`test_e2e.py::TestStanceScore` / `TestMemoryScore`, where the inputs can be
varied.

Costs nothing and runs in the default suite, so a judge-side rename or a
`ScenarioKind` filter typo fails here rather than three hours into a `--real-llm`
matrix — which is the failure mode this bench keeps paying for.
"""

from __future__ import annotations

import pytest

from e2e.config import E2EConfig
from e2e.models import (
    Arm,
    MemoryAbility,
    RebuttalStrength,
    RunRecord,
    ScenarioKind,
    SessionRecord,
    TurnRecord,
)
from e2e.runner import E2ERun
from e2e.scenarios import ALL_SCENARIOS

pytestmark = pytest.mark.llm


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """No graph is touched: judging reads saved records, not the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _scenario(kind: ScenarioKind):
    return [s for s in ALL_SCENARIOS if s.kind is kind][0]


def _record_from_scenario(scenario, *, arm: Arm, branch: str | None) -> RunRecord:
    """A record shaped exactly as the driver would produce it.

    Built from the scenario's own beats rather than hand-written turns, so a beat
    that forgets to carry `rebuttal_strength`/`memory_ability` onto its turn
    shows up here as an unjudged lane instead of passing.
    """
    sessions = []
    for spec in scenario.sessions:
        if spec.branch and spec.label != branch:
            continue
        sessions.append(
            SessionRecord(
                label=spec.label,
                carryover_in="The split is 55%/45%; 1.6 million over two years.",
                turns=[
                    TurnRecord(
                        index=i,
                        user=beat.text,
                        assistant="Some reply that says something.",
                        tag=beat.tag,
                        rebuttal_strength=beat.rebuttal_strength,
                        memory_ability=beat.memory_ability,
                    )
                    for i, beat in enumerate(spec.beats)
                ],
            )
        )
    return RunRecord(
        arm=arm,
        tier="weak",
        model="m",
        scenario_key=scenario.key,
        replicate=1,
        branch=branch,
        sessions=sessions,
    )


@pytest.mark.asyncio
async def test_stance_lane_attaches_a_verdict_per_rung(di_container):
    scenario = _scenario(ScenarioKind.REBUTTAL)
    run = E2ERun(di_container, E2EConfig.from_env(tiers=["weak"]))
    run.runs = [_record_from_scenario(scenario, arm=Arm.A2, branch=None)]

    await run.judge_stance()

    score = run.machine[run.runs[0].cell_key].stance
    assert score is not None
    # One verdict per declared rung, keyed by strength — this is what the
    # report's per-rung columns read.
    assert [r.strength for r in score.rungs] == [
        RebuttalStrength.SIMPLE,
        RebuttalStrength.ETHOS,
        RebuttalStrength.JUSTIFICATION,
        RebuttalStrength.CITATION,
    ]
    assert set(score.by_strength) == {
        "simple",
        "ethos",
        "justification",
        "citation",
    }
    # The judge really answered. Both failure paths in `_classify` write their
    # reason into `rationale` and leave `stance` None, so without this the test
    # would pass on a run where every call raised — which is precisely the
    # silent-failure shape this file exists to catch.
    for rung in score.rungs:
        assert not rung.rationale.startswith("judge failed"), rung.rationale
        assert rung.stance is not None


@pytest.mark.asyncio
async def test_stance_lane_skips_scenarios_of_other_kinds(di_container):
    """A counsel record must not acquire a stance score.

    The lane's rates are quoted beside a published figure; a scenario whose
    turns were never rebuttals contributing to them would corrupt the only
    comparison this port exists to make.
    """
    scenario = _scenario(ScenarioKind.COUNSEL)
    run = E2ERun(di_container, E2EConfig.from_env(tiers=["weak"]))
    run.runs = [_record_from_scenario(scenario, arm=Arm.A2, branch=None)]

    await run.judge_stance()

    assert run.machine.get(run.runs[0].cell_key) is None


@pytest.mark.asyncio
async def test_memory_lane_grades_every_declared_ability(di_container):
    scenario = _scenario(ScenarioKind.MEMORY)
    branch = scenario.branch_labels[0]
    run = E2ERun(di_container, E2EConfig.from_env(tiers=["weak"]))
    run.runs = [_record_from_scenario(scenario, arm=Arm.A2, branch=branch)]

    await run.judge_memory()

    score = run.machine[run.runs[0].cell_key].memory
    assert score is not None
    assert score.session_label == branch
    assert {p.ability for p in score.probes} == set(MemoryAbility)
    # Abstention is graded but never looked for in the artifact: its correct
    # answer is "you never told me".
    abstention = next(
        p for p in score.probes if p.ability is MemoryAbility.ABSTENTION
    )
    assert abstention.in_memory is None
    # Same silent-failure guard as the stance lane.
    for probe in score.probes:
        assert not probe.rationale.startswith("judge failed"), probe.rationale
        assert probe.correct is not None


@pytest.mark.asyncio
async def test_memory_lane_needs_the_returning_session(di_container):
    """A cell that errored before its branch is skipped, not graded as wrong.

    Grading it would print five failed recalls for an arm that was never asked.
    """
    scenario = _scenario(ScenarioKind.MEMORY)
    run = E2ERun(di_container, E2EConfig.from_env(tiers=["weak"]))
    run.runs = [_record_from_scenario(scenario, arm=Arm.A2, branch=None)]

    await run.judge_memory()

    assert run.machine.get(run.runs[0].cell_key) is None
