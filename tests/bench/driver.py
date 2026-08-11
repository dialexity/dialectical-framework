"""
Driver — runs one cell of the design and records it.

A cell is (arm, tier, scenario, replicate, branch). It runs the scenario's BASE
sessions in order, then at most one BRANCH session.

Why branches get their own cell
===============================
`wobble_a` and `wobble_b` are alternative continuations of the same session 1:
each asks "given this person's committed decision, what happens when they come
back with X". They must not see each other. For A0/A1 that is free (nothing
carries). For A1.7 it is a copy of a string. But for A2 the carryover is a
*graph*, and a graph cannot be rolled back — running both branches against one
Case would let variant (a)'s conversation contaminate variant (b)'s ledger, and
the arm whose whole claim is "the record is authoritative" would be measured
against a polluted record.

So each branch is a separate cell that re-runs session 1 from scratch. That
costs a duplicate session-1 per branch and buys the only clean comparison
available. Session 1 is re-run, not re-used, for every arm equally.

Model switching
===============
See `modelctx.using_model`. The arm answers on the tier model; the simulator
always answers on its own fixed model so the opponent's quality never co-varies
with the tier. Cells MUST run sequentially — the DI container is process-global.

Why there is no separate "framework model" knob
===============================================
"Sonnet talking to a framework running on Opus" is not currently expressible.
The Advisor's inner analysis calls (extraction, scoring, synthesis) happen
*inside* `arm.reply()` and read the same `settings.ai_model` as the
conversational call, so no wrapper around `reply()` can separate them. Faking it
would mislabel which model produced what. Splitting them for real needs a seam
in `src/` (a distinct analysis-model setting the concerns read); until then the
whole A2 arm runs on one tier model per row — which is what the
depreciating/durable classification actually needs.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from dialectical_framework.concerns.dialectical_context import DialecticalContext
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.decision_repository import (
    DecisionRepository,
)
from dialectical_framework.graph.rendering import decision_ground_line
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.perspective_repository import (
    PerspectiveRepository,
)
from dialectical_framework.graph.scope_context import scope

from .arms import AdvisorArm, PromptArm, method_prompt
from .models import (
    Arm,
    Beat,
    RunRecord,
    Scenario,
    SessionRecord,
    SessionSpec,
    TurnRecord,
)
from .modelctx import using_model
from .simulator import UserSimulator

logger = logging.getLogger(__name__)


class _SwallowedErrorCapture(logging.Handler):
    """Collect framework exceptions that a fail-soft block logged and moved past.

    Every `except: logger.exception(...)` in `src/` is deliberate — a graph fault
    must not break a live conversation — but it makes a turn that lost a decision
    record, a pathway, or an entire exploration indistinguishable from a healthy
    one: reply present, `error` None, every tool ok. That is exactly the state
    `claim2-weak-r8-pathways`/wobble_b is in, and why its missing record is
    uninterpretable rather than merely unexplained.

    Attached to the `dialectical_framework` logger for the duration of one turn,
    so a swallowed exception lands in the RECORD instead of only in a terminal
    nobody kept. ERROR and above only: warnings are routine.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            exc = record.exc_info[0].__name__ if record.exc_info else None
        except Exception:  # noqa: BLE001
            exc = None
        text = f"{record.name}: {record.getMessage()}"
        if exc:
            text = f"{text} [{exc}]"
        self.messages.append(text)


@contextmanager
def _capturing_swallowed_errors() -> Iterator[list[str]]:
    """Framework-only: the bench's own loggers are not under test."""
    handler = _SwallowedErrorCapture()
    target = logging.getLogger("dialectical_framework")
    target.addHandler(handler)
    try:
        yield handler.messages
    finally:
        target.removeHandler(handler)

#: The persona every arm wears, held constant across the ladder so persona
#: quality is never the variable — only structure and state are.
BENCH_PERSONA = """## Persona

You are a thoughtful advisor helping someone navigate a difficult situation.
You are warm but direct. You take their intelligence seriously — no
hand-holding, no platitudes. You help them see their situation more clearly
rather than telling them what to do, but when they ask for a view you give one.

Match their register. Be concise enough to be read: a few paragraphs, not an
essay."""

#: Provenance for decisions recorded during a bench run. NEVER "human" — no
#: person confirmed anything here, and the framework's own attestation contract
#: says a simulated confirmation must not claim otherwise.
BENCH_PRINCIPAL = "agent:bench-simulator"


class BenchDriver:
    """Runs scenarios against arms. One instance per matrix run."""

    def __init__(self, container, *, simulator_model: str) -> None:
        self._container = container
        self._simulator_model = simulator_model

    # -- turn loop ---------------------------------------------------------

    async def _run_beats(
        self,
        arm,
        simulator: UserSimulator,
        beats: list[Beat],
        *,
        tier_model: str,
        start_index: int = 0,
    ) -> list[TurnRecord]:
        turns: list[TurnRecord] = []
        for offset, beat in enumerate(beats):
            index = start_index + offset
            if beat.is_literal:
                user_text = beat.text
            else:
                with using_model(self._container, self._simulator_model):
                    try:
                        user_text = await simulator.next_turn(beat.text)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Simulator failed at beat %s", index)
                        turns.append(
                            TurnRecord(
                                index=index,
                                user="",
                                assistant="",
                                tag=beat.tag,
                                error=f"simulator: {type(exc).__name__}: {exc}",
                            )
                        )
                        continue

            simulator.observe("user", user_text)

            # The capture spans the arm's whole turn, which for A2 includes the
            # post-reply repair and pathway seams — the fail-soft blocks most
            # able to lose an artifact without anyone noticing.
            with _capturing_swallowed_errors() as swallowed:
                try:
                    with using_model(self._container, tier_model):
                        assistant_text = await arm.reply(user_text)
                    tool_calls = list(arm.last_tool_calls)
                    tool_outcomes = list(arm.last_tool_outcomes)
                    error = None
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Arm failed at beat %s", index)
                    assistant_text = ""
                    tool_calls = []
                    tool_outcomes = []
                    error = f"arm: {type(exc).__name__}: {exc}"

            simulator.observe("assistant", assistant_text)
            turns.append(
                TurnRecord(
                    index=index,
                    user=user_text,
                    assistant=assistant_text,
                    tag=beat.tag,
                    tool_calls=tool_calls,
                    tool_outcomes=tool_outcomes,
                    error=error,
                    swallowed_errors=list(swallowed),
                )
            )
        return turns

    # -- graph reads -------------------------------------------------------

    #: Graph relationship type -> the position label a reader would recognise.
    _POSITION_OF_REL = {
        "T_PLUS": "T+",
        "T_MINUS": "T-",
        "A_PLUS": "A+",
        "A_MINUS": "A-",
        "T": "T",
        "A": "A",
    }

    @classmethod
    def _ground_position(cls, node) -> str:
        """Which dialectical position an accepted_cost ground occupies.

        Non-Statement grounds report their node type: a Perspective ground is
        the whole TENSION, which is precisely the miss this distinguishes.
        A Statement can sit at several positions across perspectives, so all
        distinct ones are joined rather than one being picked arbitrarily.
        """
        if not isinstance(node, Statement):
            return type(node).__name__
        try:
            rels = PerspectiveRepository().find_by_statement(node)
        except Exception:  # noqa: BLE001
            logger.exception("Position lookup failed for %s", node.hash)
            return "Statement"
        positions = sorted({cls._POSITION_OF_REL.get(r, r) for _, r in rels})
        return "/".join(positions) if positions else "Statement"

    @classmethod
    def _read_decisions(cls) -> tuple[list[str], list[str], list[str], list[str]]:
        """Committed decisions + their accepted-cost and adopted-pathway grounds.

        Requires an active scope. The typed ground is what the wobble scorer
        compares against — and the thing no prose journal has.

        `adopted_pathway` is tracked alongside the cost because the two are the
        record's two halves: the cost is the price confronted, the pathway is
        the recipe for living with it, and the re-audit's reassurance ("here is
        what you adopted for this") needs BOTH. Untracked, a record with a cost
        and no recipe scored identically to a complete one — which is exactly
        what a decision closed without `explore` produces, since a recipe IS a
        pathway and unexplored tensions have none.

        Rendered with the framework's own `decision_ground_line`, not `str(node)`.
        A Statement's `__str__` appends "\\nExplanation: ..." and an aspect's can
        trail a whole COMPLEX-classification rationale; the ledger the model
        actually reads at wobble time takes the first line only. Comparing the
        model's citation against text it was never shown would understate
        citation and read as the record going unused.
        """
        hashes: list[str] = []
        costs: list[str] = []
        positions: list[str] = []
        pathways: list[str] = []
        try:
            for decision in DecisionRepository().find_all_active():
                hashes.append(decision.short_hash)
                try:
                    all_grounds = decision.grounds.all()
                    # Siblings disambiguate a shared minus's condition clause —
                    # pass them exactly as the live renderers do, or the bench
                    # measures a ledger the model never sees.
                    ground_nodes = [n for n, _ in all_grounds]
                    for node, rel in all_grounds:
                        role = getattr(rel, "role", None)
                        if role == "accepted_cost":
                            costs.append(
                                decision_ground_line(
                                    node, "accepted_cost", siblings=ground_nodes
                                )
                            )
                            positions.append(cls._ground_position(node))
                        elif role == "adopted_pathway":
                            pathways.append(
                                decision_ground_line(node, "adopted_pathway")
                            )
                except Exception:  # noqa: BLE001
                    logger.exception("Reading grounds failed for %s", decision.hash)
        except Exception:  # noqa: BLE001
            logger.exception("Reading decisions failed")
        return hashes, costs, positions, pathways

    @staticmethod
    def _graph_summary() -> str:
        """What the graph holds at the end of a session.

        Cross-checked against the cell's own tool outcomes rather than trusted:
        the repositories are fail-soft, so a read fault returns [] and would
        report an empty graph over a populated one. Observed in
        `claim2-weak-r1` — two cells logged `anchor:ok` repeatedly and then
        summarised `perspectives=0`, which reads as "the model built nothing"
        when the truth was "the count could not be taken".
        """
        try:
            return (
                f"perspectives={len(PerspectiveRepository().find_all_active())} "
                f"decisions={len(DecisionRepository().find_all_active())}"
            )
        except Exception as exc:  # noqa: BLE001
            return f"unavailable: {type(exc).__name__}: {exc}"

    # -- A1.5 support ------------------------------------------------------

    async def build_static_context(
        self, scenario: Scenario, *, tier_model: str
    ) -> tuple[str, str]:
        """Build a graph with the REAL Advisor, then dump it as static text.

        This is the A1.5 arm's context: structure produced by the actual
        pipeline (quality-gated, scored, ranked), handed to a plain model as
        text. It isolates "structure as context" from "the live process", which
        is the only way A1.5 -> A2 means anything.

        Built once per (scenario, tier) and reused across replicates and
        branches: it is a static artifact by definition, and rebuilding it per
        replicate would change the arm's input between replicates.

        Returns (dump, provenance). An empty graph makes A1.5 a duplicate of A1
        and the report must be able to say so, so what was actually built is
        recorded rather than assumed.
        """
        case = Case()
        case.commit()
        simulator = UserSimulator(scenario)
        with scope(case.sid):
            advisor_arm = AdvisorArm(BENCH_PERSONA, principal=BENCH_PRINCIPAL)
            index = 0
            for spec in scenario.base_sessions:
                turns = await self._run_beats(
                    advisor_arm,
                    simulator,
                    spec.beats,
                    tier_model=tier_model,
                    start_index=index,
                )
                index += len(turns)
            summary = self._graph_summary()
            try:
                with using_model(self._container, tier_model):
                    dump = await DialecticalContext().resolve()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Static dump failed")
                return "", f"failed: {type(exc).__name__}: {exc}"
        return dump, summary

    # -- the cell ----------------------------------------------------------

    async def run_cell(
        self,
        *,
        arm: Arm,
        tier: str,
        tier_model: str,
        scenario: Scenario,
        replicate: int,
        branch: Optional[str] = None,
        static_context: Optional[str] = None,
    ) -> RunRecord:
        """Run the base sessions, then at most one branch session."""
        started = time.monotonic()
        record = RunRecord(
            arm=arm,
            tier=tier,
            model=tier_model,
            scenario_key=scenario.key,
            replicate=replicate,
            branch=branch,
        )
        specs = list(scenario.base_sessions)
        if branch:
            spec = scenario.spec(branch)
            if spec is None:
                record.error = f"unknown branch {branch!r}"
                return record
            specs.append(spec)

        # A2 keeps ONE case across this cell's sessions: the graph is the
        # carryover. A separate cell (different branch) gets a separate Case.
        case: Optional[Case] = None
        if arm is Arm.A2:
            case = Case()
            case.commit()

        journal: Optional[str] = None
        try:
            for position, spec in enumerate(specs):
                session, journal = await self._run_session(
                    arm=arm,
                    tier_model=tier_model,
                    scenario=scenario,
                    spec=spec,
                    case=case,
                    journal=journal,
                    static_context=static_context,
                    is_first=position == 0,
                    is_last=position == len(specs) - 1,
                    record=record,
                )
                record.sessions.append(session)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cell failed: %s/%s/%s", arm, tier, scenario.key)
            record.error = f"{type(exc).__name__}: {exc}"

        record.duration_s = round(time.monotonic() - started, 1)
        return record

    async def _run_session(
        self,
        *,
        arm: Arm,
        tier_model: str,
        scenario: Scenario,
        spec: SessionSpec,
        case: Optional[Case],
        journal: Optional[str],
        static_context: Optional[str],
        is_first: bool,
        is_last: bool,
        record: RunRecord,
    ) -> tuple[SessionRecord, Optional[str]]:
        """Run one session; return it plus any carry-forward state produced.

        A fresh `UserSimulator` per session is deliberate: the person does not
        remember the exact words of a conversation weeks ago either, and giving
        the simulator a transcript the ASSISTANT no longer has would leak
        session-1 content into every arm's session 2 — handing A0/A1 a memory
        they are supposed to lack.
        """
        simulator = UserSimulator(scenario)
        session = SessionRecord(label=spec.label)

        if arm is Arm.A2:
            assert case is not None
            with scope(case.sid):
                # On a returning session the Advisor is handed the freshly
                # rendered dump (decision ledger included) — the live-graph
                # equivalent of "remembering", and the thing under test.
                live_context = None
                if not is_first:
                    try:
                        with using_model(self._container, tier_model):
                            live_context = await DialecticalContext().resolve()
                    except Exception:  # noqa: BLE001
                        logger.exception("Live context render failed")
                session.carryover_in = live_context
                advisor_arm = AdvisorArm(
                    BENCH_PERSONA,
                    principal=BENCH_PRINCIPAL,
                    dialectical_context=live_context,
                )
                session.turns = await self._run_beats(
                    advisor_arm, simulator, spec.beats, tier_model=tier_model
                )
                hashes, costs, positions, pathways = self._read_decisions()
                record.decision_hashes = sorted(
                    set(record.decision_hashes) | set(hashes)
                )
                record.accepted_cost_grounds = sorted(
                    set(record.accepted_cost_grounds) | set(costs)
                )
                record.accepted_cost_positions = sorted(
                    set(record.accepted_cost_positions) | set(positions)
                )
                record.adopted_pathway_grounds = sorted(
                    set(record.adopted_pathway_grounds) | set(pathways)
                )
                session.graph_summary = self._graph_summary()
            return session, journal

        # What this arm was handed, recorded on the same field for every arm so
        # the two carryovers can be compared as the same kind of object.
        if arm is Arm.A1_7:
            session.carryover_in = journal
        elif arm is Arm.A1_5:
            session.carryover_in = static_context
        prompt_arm = PromptArm(
            arm,
            BENCH_PERSONA,
            engine_prompt=None if arm is Arm.A0 else method_prompt(),
            static_context=static_context if arm is Arm.A1_5 else None,
            journal=journal if arm is Arm.A1_7 else None,
        )
        session.turns = await self._run_beats(
            prompt_arm, simulator, spec.beats, tier_model=tier_model
        )
        # A1.7 writes its own carry-forward notes at the end of every session
        # that is followed by another one. Skipped on the last session: an
        # unused journal call would only spend tokens and pad the arm's word
        # count in the verbosity table.
        if arm is Arm.A1_7 and not is_last:
            try:
                with using_model(self._container, tier_model):
                    journal = await prompt_arm.write_journal()
                session.journal_after = journal
            except Exception:  # noqa: BLE001
                logger.exception("Journal write failed")
        return session, journal
