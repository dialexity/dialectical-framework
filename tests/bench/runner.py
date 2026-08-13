"""
Matrix runner — sequences cells, scores them, judges pairs, writes the report.

Order of operations matters for cost
====================================
Cells run first and are saved to JSON before any judging happens. A run is the
expensive part; judging is cheap and re-runnable from the saved records
(`judge_records`). So a crashed judge never costs a re-run of the matrix.

Sequential by necessity
=======================
`modelctx.using_model` mutates a process-global DI container. Two concurrent
cells would answer on each other's model. This is the one place in the codebase
where sequential execution is a correctness property rather than a limitation,
and `--real-llm` runs are correspondingly slow: budget an hour-plus for the full
moderate matrix.

Selective invocation
====================
Everything is filterable — arms, tiers, scenarios, replicates, branches — so a
finding can be re-checked in isolation without re-spending the matrix. See
`tests/bench/README.md`.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .config import BenchConfig
from .driver import BenchDriver
from .judge import BenchJudge, MemoryJudge, StanceJudge, WobbleJudge
from .models import (
    Arm,
    Comparison,
    MachineScores,
    RunRecord,
    Scenario,
    ScenarioKind,
)
from .report import load_records, render_report, save_records
from .scenarios import scenarios_for
from .scoring import (
    cited_record,
    score_closure,
    score_erosion,
    score_particulars,
    score_phantom_record,
    score_symmetry,
    turn_by_tag,
)

logger = logging.getLogger(__name__)

#: Default ladder. A0 and A2 are the two ends of the claim; A1 is the honest
#: opponent for Claim 1; A1.7 is the honest opponent for Claim 2. A1.5 is the
#: most expensive arm per unit of information (it needs a real Advisor run just
#: to produce its context) so it is opt-in rather than default.
DEFAULT_ARMS: tuple[Arm, ...] = (Arm.A0, Arm.A1, Arm.A1_7, Arm.A2)

#: Pairs the report is built around. Each isolates ONE rung of the ladder:
#:   A1  vs A0   does the method text alone help?           (Claim 1 floor)
#:   A2  vs A1   does enforcement beat self-application?    (Claim 1)
#:   A2  vs A1_7 does a typed record beat a prose journal?  (Claim 2)
#:   A2  vs A0   the headline the product would claim.
JUDGED_PAIRS: tuple[tuple[Arm, Arm], ...] = (
    (Arm.A1, Arm.A0),
    (Arm.A2, Arm.A1),
    (Arm.A2, Arm.A1_7),
    (Arm.A2, Arm.A0),
)


class BenchRun:
    """One matrix execution. Holds records so judging can be re-done in place."""

    def __init__(self, container, config: BenchConfig) -> None:
        self._container = container
        self._config = config
        self._driver = BenchDriver(container, simulator_model=config.simulator_model)
        self.runs: list[RunRecord] = []
        self.comparisons: list[Comparison] = []
        self.machine: dict[str, MachineScores] = {}

    # -- the matrix --------------------------------------------------------

    async def run_matrix(
        self,
        *,
        arms: Iterable[Arm] = DEFAULT_ARMS,
        scenario_keys: Optional[list[str]] = None,
        replicates: int = 1,
        branches: Optional[list[str]] = None,
        progress=None,
    ) -> list[RunRecord]:
        """Run every cell sequentially. Returns the records (also on self.runs).

        `branches=None` runs every branch a scenario declares; pass a list to
        run only some (e.g. `["wobble_a"]` when only the reassure case is under
        investigation).
        """
        arms = list(arms)
        scenarios = scenarios_for(scenario_keys)
        say = progress or (lambda msg: logger.info("%s", msg))

        for tier, tier_model in self._config.tiers.items():
            for scenario in scenarios:
                cells = self._cells_for(scenario, branches)
                static_context: Optional[str] = None
                if Arm.A1_5 in arms:
                    say(f"[{tier}] building A1.5 static context for {scenario.key}")
                    static_context, provenance = await self._driver.build_static_context(
                        scenario, tier_model=tier_model
                    )
                    say(f"[{tier}]   static context: {provenance}")
                for replicate in range(1, replicates + 1):
                    for branch in cells:
                        for arm in arms:
                            label = (
                                f"[{tier}] {scenario.key} r{replicate} "
                                f"{branch or '-'} {arm.value}"
                            )
                            say(f"{label} ...")
                            record = await self._driver.run_cell(
                                arm=arm,
                                tier=tier,
                                tier_model=tier_model,
                                scenario=scenario,
                                replicate=replicate,
                                branch=branch,
                                static_context=static_context,
                            )
                            self.runs.append(record)
                            note = record.error or f"{record.duration_s}s"
                            # Turn errors first: they explain a collapse rather
                            # than accompanying it, and a run whose every turn
                            # 400'd is a broken harness, not a weak arm.
                            errors = record.turn_errors
                            if errors:
                                note += (
                                    f" !! {len(errors)} TURN ERROR(S)"
                                    f"{' — ALL TURNS FAILED' if record.all_turns_errored else ''}"
                                    f": {errors[0][:160]}"
                                )
                            if record.collapsed_to_a1:
                                note += " !! NO TOOL CALLS (A2 collapsed)"
                            say(f"{label} done: {note}")
        return self.runs

    @staticmethod
    def _cells_for(
        scenario: Scenario, branches: Optional[list[str]]
    ) -> list[Optional[str]]:
        """Which branch cells this scenario needs.

        A scenario with no branches runs one cell with `branch=None`. A scenario
        with branches runs one cell PER branch (each re-running the base
        sessions) — see the driver's docstring for why they cannot share state.
        """
        declared = scenario.branch_labels
        if not declared:
            return [None]
        if branches is None:
            return list(declared)
        wanted = [b for b in declared if b in branches]
        return wanted or [None]

    # -- scoring (no LLM) --------------------------------------------------

    def score_machine(self) -> dict[str, MachineScores]:
        """Marker-based scores for every run. Free, deterministic, re-runnable."""
        return score_machine_over(self.runs, self.machine)

    # -- judging (LLM, cheap, re-runnable from saved records) --------------

    async def judge_wobbles(self, *, progress=None) -> None:
        """Classify every branch session as reassure / reopen / neither.

        Runs on every arm, not just A2: "A0 always reassures" and "A1 always
        reopens" are both plausible failure modes, and the pair of variants is
        what distinguishes discrimination from a fixed habit.
        """
        say = progress or (lambda msg: logger.info("%s", msg))
        judge = WobbleJudge(self._container, self._config.judge_model)
        for record in self.runs:
            if not record.branch:
                continue
            session = record.session(record.branch)
            if session is None or not session.turns:
                continue
            variant = record.branch.rsplit("_", 1)[-1]
            if variant not in ("a", "b"):
                continue
            wobble_turn = turn_by_tag(session, "wobble")
            reply = wobble_turn.assistant if wobble_turn else ""
            say(f"wobble judge: {record.cell_key}")
            score = await judge.classify(
                variant=variant,
                decision_context=self._decision_context(record),
                wobble_text=wobble_turn.user if wobble_turn else "",
                reply_text=reply,
            )
            # Both halves of the record count as the record: reassuring from
            # the adopted pathway ("here is what you set up for exactly this")
            # is citing it just as much as naming the price again. Scoring only
            # costs understated A2 on precisely the reply the ceremony is FOR.
            score.cited_record = cited_record(
                reply,
                record.accepted_cost_grounds + record.adopted_pathway_grounds,
            )
            self.machine.setdefault(record.cell_key, MachineScores()).wobble = score

    async def judge_stance(self, *, progress=None) -> None:
        """Score the rebuttal ladder (SycEval port) on every REBUTTAL run.

        Every arm, for the same reason `judge_wobbles` runs on every arm: the
        published rates are model-level, so an arm axis is only informative if
        each arm gets its own rate. The scenario's ladder lives in the base
        session, so unlike the wobble pass this one does not need a branch.
        """
        say = progress or (lambda msg: logger.info("%s", msg))
        judge = StanceJudge(self._container, self._config.judge_model)
        for record in self.runs:
            scenario = _scenario(record.scenario_key)
            if scenario.kind is not ScenarioKind.REBUTTAL:
                continue
            session = record.sessions[0] if record.sessions else None
            if session is None or not session.turns:
                continue
            say(f"stance judge: {record.cell_key}")
            score = await judge.score(scenario=scenario, session=session)
            self.machine.setdefault(record.cell_key, MachineScores()).stance = score

    async def judge_memory(self, *, progress=None) -> None:
        """Grade the memory probes (LongMemEval port) on every MEMORY run.

        Probes live in the RETURNING session by construction — the point is that
        the answer has to come from carryover rather than from the transcript —
        so a record that errored before reaching its branch is skipped rather
        than graded as five wrong answers.
        """
        say = progress or (lambda msg: logger.info("%s", msg))
        judge = MemoryJudge(self._container, self._config.judge_model)
        for record in self.runs:
            scenario = _scenario(record.scenario_key)
            if scenario.kind is not ScenarioKind.MEMORY:
                continue
            if not record.branch or len(record.sessions) < 2:
                continue
            session = record.session(record.branch)
            if session is None or not session.turns:
                continue
            say(f"memory judge: {record.cell_key}")
            score = await judge.score(scenario=scenario, session=session)
            self.machine.setdefault(record.cell_key, MachineScores()).memory = score

    @staticmethod
    def _decision_context(record: RunRecord) -> str:
        """What the assistant had to go on when the person came back.

        Per arm, this is exactly the carryover it actually possessed — the
        typed record for A2, the model's own journal for A1.7, and nothing for
        A0/A1. The wobble judge is asked what the assistant DID, so giving it a
        context the assistant never had would let it mark an arm down for
        failing to use a record it never received.
        """
        # Both roles, because both are in the ledger the Advisor was handed.
        # Showing only costs would let the judge mark A2 down for "not using
        # the record" when the reply reassured from the adopted pathway — the
        # single most likely correct answer to variant (a).
        if record.accepted_cost_grounds or record.adopted_pathway_grounds:
            # No added "- ": `decision_ground_line` already emits it, and the
            # old code's double bullet ("- - accepted cost: ...") was text no
            # ledger ever renders that way.
            parts = ["The typed decision record the assistant was holding:"]
            parts.extend(record.accepted_cost_grounds)
            parts.extend(record.adopted_pathway_grounds)
            return "\n".join(parts)
        base = record.sessions[0] if record.sessions else None
        if base is not None and base.journal_after:
            return "The assistant's own notes from the earlier session:\n" + (
                base.journal_after
            )
        if base is not None:
            commit = turn_by_tag(base, "commit")
            if commit is not None:
                return (
                    "The person's own words when committing, in the earlier "
                    f"session:\n{commit.user}"
                )
        return ""

    async def judge_pairs(
        self,
        *,
        pairs: Iterable[tuple[Arm, Arm]] = JUDGED_PAIRS,
        progress=None,
    ) -> list[Comparison]:
        """Blind paired judging on every session of every matched cell."""
        say = progress or (lambda msg: logger.info("%s", msg))
        judge = BenchJudge(self._container, self._config.judge_model)
        index = {r.cell_key: r for r in self.runs}
        for arm_a, arm_b in pairs:
            # Counts comparisons within THIS pair AND session label so the judge
            # alternates X/Y exactly (see judge._x_is_a). Per-pair, not global:
            # each pair's own split is what enters its delta table.
            #
            # Stratified by session label, and that is load-bearing. A single
            # per-pair counter makes slot a deterministic function of session:
            # every run contributes its sessions in the same order (`decide`
            # then one wobble branch), so `decide` always landed on an even
            # ordinal and the wobble always on an odd one. The pair's split
            # stayed even — 6/6 — while every column of the `by session:` table
            # was 100% one slot, admitting slot bias at full strength there, and
            # `position_bias` degenerated into (gap_decide - gap_wobble)/2: a
            # session-heterogeneity statistic wearing a bias label. Verified as
            # an exact identity across all 9 saved multi-session runs.
            #
            # Alternation is exact only inside an EVEN stratum, so each odd one
            # leaves a 2/1 residual — and with one hashed starting side for all
            # of them those residuals ADD. `claim2-weak-r15-voice` (strata 6/3/3)
            # drew 7/5 under a +0.40 Y-slot bias, bigger than every delta it was
            # asked to support. `stratum_index` flips the start on alternate
            # strata so the residuals cancel; it is assigned in first-seen order
            # (deterministic given the run list, which is itself ordered) so
            # re-judging a saved matrix reproduces the same layout.
            ordinals: dict[str, int] = defaultdict(int)
            strata: dict[str, int] = {}
            for record in self.runs:
                if record.arm is not arm_a or record.error:
                    continue
                other_key = "|".join(
                    [
                        arm_b.value,
                        record.tier,
                        record.scenario_key,
                        str(record.replicate),
                        record.branch or "-",
                    ]
                )
                other = index.get(other_key)
                if other is None or other.error:
                    continue
                scenario = _scenario(record.scenario_key)
                for session in record.sessions:
                    if other.session(session.label) is None:
                        continue
                    say(
                        f"judge {arm_a.value} vs {arm_b.value}: "
                        f"{record.cell_key} / {session.label}"
                    )
                    if session.label not in strata:
                        strata[session.label] = len(strata)
                    comparison = await judge.compare(
                        scenario=scenario,
                        run_a=record,
                        run_b=other,
                        session_label=session.label,
                        ordinal=ordinals[session.label],
                        stratum_index=strata[session.label],
                    )
                    ordinals[session.label] += 1
                    self.comparisons.append(comparison)
        return self.comparisons

    # -- output ------------------------------------------------------------

    def report(self) -> str:
        return render_report(
            self.runs, self.comparisons, self.machine, self._config.tier_order
        )

    def load(self, path: Path, *, keep_comparisons: bool = False) -> None:
        """Rehydrate runs + machine scores from a saved records JSON.

        This is what makes "judging is cheap and re-runnable" true rather than
        merely intended: the matrix is hours of model time, the judge is minutes,
        and a judge-side defect must not cost the former. It cost exactly that
        once — `decision-strong-r4`'s X/Y split came out 10/2 because the
        starting side was hashed per comparison instead of per arm pair, and with
        no loader the only way to re-judge was to re-run 1h22m of conversation.

        Comparisons are DROPPED by default: the reason to reload is almost always
        that the previous verdicts are suspect, and silently keeping them would
        append new ones alongside, doubling every delta's n with two different
        judging regimes averaged together.
        """
        payload = load_records(path)
        self.runs = [RunRecord.model_validate(r) for r in payload["runs"]]
        self.machine = {
            k: MachineScores.model_validate(v)
            for k, v in payload.get("machine", {}).items()
        }
        self.comparisons = (
            [Comparison.model_validate(c) for c in payload.get("comparisons", [])]
            if keep_comparisons
            else []
        )

    def save(self, directory: Path, *, stem: str = "bench") -> tuple[Path, Path]:
        """Write records JSON + rendered report. Returns both paths."""
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / f"{stem}.json"
        report_path = directory / f"{stem}.txt"
        save_records(json_path, self.runs, self.comparisons, self.machine)
        report_path.write_text(self.report())
        return json_path, report_path


def _scenario(key: str) -> Scenario:
    return scenarios_for([key])[0]


def score_machine_over(
    runs: list[RunRecord], machine: dict[str, MachineScores]
) -> dict[str, MachineScores]:
    """Machine scores for `runs`, UPDATING `machine` in place.

    Module-level rather than only a `BenchRun` method so it can run over a loaded
    archive without a `BenchConfig` — re-scoring saved transcripts needs no models,
    no tiers and no API keys, and requiring a config to express that was the one
    thing standing between a new scorer and the whole back catalogue.

    Updates each entry instead of replacing it: `wobble`/`stance`/`memory` are
    judge-derived and cost money, so a fresh `MachineScores()` here would discard
    them the moment this ran on an already-judged record.
    """
    for record in runs:
        scenario = _scenario(record.scenario_key)
        scores = machine.setdefault(record.cell_key, MachineScores())
        first = record.sessions[0] if record.sessions else None
        if first is not None:
            scores.erosion = score_erosion(first, scenario)
            scores.symmetry = score_symmetry(first, scenario)
        # Every session, and no branch requirement: the obligation to honour an
        # explicit "write it down" is per-session and exists in the opening
        # conversation as much as after a wobble.
        if record.sessions:
            # `decision_hashes` (read back from the GRAPH by the driver), not the
            # turn's `tool_calls`: the repair seam writes records the model never
            # elected to write, and they appear in no turn. See
            # `score_phantom_record`.
            scores.phantom_record = score_phantom_record(
                record.sessions, record_exists=bool(record.decision_hashes)
            )
        # Carry-over is only measurable across a boundary, so this needs the
        # branch session AND the bases that preceded it. Scored off the record's
        # own sessions rather than the scenario's declared list: a cell that
        # errored before reaching the branch must produce no score rather than a
        # zero.
        if record.branch and len(record.sessions) > 1:
            returning = record.session(record.branch)
            if returning is not None and returning.turns:
                bases = [s for s in record.sessions if s.label != record.branch]
                scores.particulars = score_particulars(bases, returning, scenario)
                scores.closure = score_closure(bases, returning)
    return machine
