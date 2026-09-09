"""`edit_perspective` must speak while it works — and it had nothing to say at all.

WHY THIS TEST EXISTS
====================
Every other multi-call skill in this tree was at least CONDITIONALLY instrumented:
the reporting calls were written, and the only question was whether some caller had
installed a scope for them to publish into. `edit_perspective` was the one genuinely
silent skill. Not a missing `with` — nothing to light up. Six to eight sequential
provider calls, awaited one after another, with no `expect_progress`, no
`report_progress`, and no node written until the very end, so not even the graph
event stream covered the wait.

It is a bad path to leave silent for a reason that has nothing to do with its
length: **it is the path a person reaches by disagreeing.** They corrected something
the framework generated, and the two branches that take the longest are the two that
end in "no, that does not fit" — the refusal probes, which spend three to four
provider calls deciding what the person's wording looks like instead, and write
nothing to the graph on the way. A wait that ends in a refusal is indistinguishable,
while you are sitting in it, from a wait that is going to succeed.

WHAT IS PINNED, AND AT WHICH LEVEL
==================================
Two levels, because neither can see the other's failure — the same split the
extraction-label fix needed.

`TestEachEditPathSaysWhatItIsDoing` stubs all six concerns and drives
`EditPerspective.resolve()` directly. That is the only way to pin the ORDER and the
COUNT per branch: which branch runs is decided by heuristic-similarity values that
come back from the provider, so under mock brain the path is whatever the mock
happens to produce. Stubs make the branch an argument.

`TestOneEditIsOneKeyedStream` goes through the `@llm.tool` against mock brain and
pins what only the assembled stream shows: that a scope is installed at all, that it
closes exactly once, that the arithmetic closes, and that the key is sanitised. A
unit test cannot see any of that — `report_progress` is a no-op with no scope, so
every assertion in the first class passes just as happily when the tool forgets its
`with`.

Run: poetry run pytest tests/test_edit_progress.py
"""

from __future__ import annotations

import asyncio

import pytest
from test_analyst_polarity_editing import create_test_pp

from dialectical_framework.agents.analyst.skills import edit_perspective as ep
from dialectical_framework.agents.analyst.skills.edit_perspective import (
    EditPerspective, edit_perspective)
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.concerns.aspect_classification import \
    AspectClassification
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              AspectResult)
from dialectical_framework.concerns.control_statements_check import \
    ControlStatementsCheck
from dialectical_framework.concerns.diagonal_oppositions_check import \
    DiagonalOppositionsCheck
from dialectical_framework.concerns.statement_classification import (
    ClassificationResult, StatementClassification)
from dialectical_framework.events.graph_event_bus import GraphEventBus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)
from dialectical_framework.graph.nodes.polarity import POSITION_A, POSITION_T
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.progress import progress_scope

MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"

#: The person's own correction. Long and distinctive so any substring of it turning
#: up in a label or a key is a leak and not a coincidence of ordinary English.
CORRECTION = (
    "What actually helps here is that the dispatchers can reach a supervisor "
    "within the same shift, not that the rota looks balanced on paper"
)

#: Terms a host may not render to a person. Kept in step with
#: `tests/test_ingest_progress.py` and `tests/test_analyze_progress.py` — one
#: contract, three entry points.
BANNED = (
    "thesis",
    "antithesis",
    "polarity",
    "tetrad",
    "perspective",
    "nexus",
    "wheel",
    "dialectical",
    "framework",
    "synthesis",
    "digest",
)

_LEAK_RUN = 40


# ─── Stubs. Each replaces exactly one concern's `resolve`, so the branch under
# ─── test is an argument rather than whatever mock brain happens to score.


class _Diag:
    """Stands in for `DiagonalOppositionsCheckResult`.

    Not the real dataclass: it requires an estimation node and a rationale node,
    and the code under test reads only `is_valid` and the two scores. Building the
    real thing would test GQLAlchemy, not the label ordering.
    """

    is_valid = True
    t_plus_vs_a_minus_score = 0.9
    t_plus_vs_a_minus_reasoning = ""
    a_plus_vs_t_minus_score = 0.9
    a_plus_vs_t_minus_reasoning = ""


class _Ctrl:
    """Stands in for `ControlStatementsCheckResult`, same reasoning as `_Diag`."""

    is_coherent = True


def _aspect_result(statement: str, position: str, hs: float):
    from dialectical_framework.concerns.aspect_classification import \
        AspectClassificationResult

    return AspectClassificationResult(
        statement=statement,
        position=position,
        meaning=MEANING,
        heuristic_similarity=hs,
        complementarity_t=0.8,
        complementarity_a=0.8,
        apex_concept="Cohesion",
        reasoning="",
    )


def _antithesis_result(statement: str, hs: float):
    from dialectical_framework.concerns.antithesis_classification import \
        AntithesisClassificationResult

    return AntithesisClassificationResult(
        statement=statement,
        meaning=MEANING,
        mode_value=1.0,
        mode_label="negation",
        arousal_value=0.5,
        heuristic_similarity=hs,
        reasoning="",
    )


@pytest.fixture
def stub_concerns(monkeypatch):
    """Stub every provider-backed concern this skill awaits, with knobs per branch.

    Returns a dict the test mutates BEFORE calling `resolve()`:
      `aspect_hs`      — what `AspectClassification` scores every candidate
      `antithesis_hs`  — what `AntithesisClassification` scores the pair
      `antitheses`     — what `AntithesisExtraction` hands back
    """
    knobs = {"aspect_hs": 0.8, "antithesis_hs": 0.8, "antitheses": []}

    async def fake_statement(self, statement="", text="", **kwargs):
        return ClassificationResult(
            statement=statement,
            is_simple=True,
            meaning=MEANING,
            classification_reasoning="",
        )

    async def fake_antithesis(self, thesis, antithesis_statement="", text="", **kwargs):
        return _antithesis_result(antithesis_statement, knobs["antithesis_hs"])

    async def fake_aspect(
        self, thesis, antithesis, aspect_statement="", position="", text="", **kwargs
    ):
        return _aspect_result(aspect_statement, position, knobs["aspect_hs"])

    async def fake_generation(self, perspective, positions=None, text="", **kwargs):
        results = []
        for pos in positions or []:
            stmt = Statement(text=f"generated {pos}", meaning=MEANING)
            stmt.commit()
            results.append(
                AspectResult(
                    component=stmt,
                    position=pos,
                    apex_concept="Cohesion",
                    heuristic_similarity=0.8,
                    complementarity_t=0.8,
                    complementarity_a=0.8,
                )
            )
        return results

    async def fake_extraction(self, thesis, text="", **kwargs):
        return knobs["antitheses"]

    async def fake_diag(self, perspective, text="", **kwargs):
        return _Diag()

    async def fake_ctrl(self, perspective, text="", **kwargs):
        return _Ctrl()

    monkeypatch.setattr(StatementClassification, "resolve", fake_statement)
    monkeypatch.setattr(AntithesisClassification, "resolve", fake_antithesis)
    monkeypatch.setattr(AspectClassification, "resolve", fake_aspect)
    monkeypatch.setattr(AspectGeneration, "resolve", fake_generation)
    monkeypatch.setattr(AntithesisExtraction, "resolve", fake_extraction)
    monkeypatch.setattr(DiagonalOppositionsCheck, "resolve", fake_diag)
    monkeypatch.setattr(ControlStatementsCheck, "resolve", fake_ctrl)
    return knobs


@pytest.fixture
def timeline(monkeypatch) -> list[str]:
    """Record every label this module publishes, in order.

    Wraps the real function rather than replacing it, so the scope's counters still
    move — `report_progress` publishes AND increments `done`, and a bare
    `seen.append` would leave every `done == total` assertion below comparing 0 to a
    denominator that `expect_progress` had grown on its own.
    """
    real = ep.report_progress
    seen: list[str] = []

    def record(detail: str) -> None:
        seen.append(detail)
        real(detail)

    monkeypatch.setattr(ep, "report_progress", record)
    return seen


@pytest.mark.llm
class TestEachEditPathSaysWhatItIsDoing:
    """Order and count per branch, with the branch chosen by the stubs.

    Every assertion here would also pass if the tool dropped its `progress_scope`,
    because `report_progress` is a no-op with no scope installed. That is what the
    second class is for.
    """

    @pytest.mark.asyncio
    async def test_the_aspect_only_edit_names_each_part_then_the_two_checks(
        self, stub_concerns, timeline
    ):
        """Two changed parts, two named waits, then the two coherence checks.

        The fraction is the point of the first two: `len(changes)` is the whole of
        that phase and this loop runs every iteration, so a number is a promise the
        window can keep. The two checks are separate lines because they are separate
        awaits — one label over both would cover a stretch in which the first starts,
        finishes and is replaced.
        """
        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T_PLUS: "Reachable supervisor", POSITION_A_PLUS: "Clear rota"},
            )
            with progress_scope("edit"):
                result = await editor.resolve()

        assert result.is_valid, f"the stubs were supposed to pass: {result.error_message}"
        assert timeline == [
            "Checking your wording fits where you put it (1 of 2)",
            "Checking your wording fits where you put it (2 of 2)",
            "Checking that opposing sides really do pull apart",
            "Checking that each side's strength needs the other",
        ], f"got {timeline}"

    @pytest.mark.asyncio
    async def test_a_single_part_edit_carries_no_fraction(self, stub_concerns, timeline):
        """"(1 of 1)" beside a spinner is noise, and one part is the common edit."""
        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T_MINUS: "Supervisors stop checking anything"},
            )
            with progress_scope("edit"):
                await editor.resolve()

        assert timeline[0] == "Checking your wording fits where you put it", (
            f"a lone changed part should not be counted: {timeline}"
        )

    @pytest.mark.asyncio
    async def test_a_rejected_part_announces_the_search_and_never_the_checks(
        self, stub_concerns, timeline
    ):
        """The refusal path, which is the longest silence this skill had.

        Three extra provider calls looking for somewhere the wording fits better,
        and then the edit bails — so the two coherence labels must NOT appear. They
        are declared at their own sites for exactly this reason: declared at the top
        of the path they would be phantoms here, announced and never reported, which
        a host cannot tell apart from a step that failed.
        """
        stub_concerns["aspect_hs"] = 0.05  # below HS_WRONG_CATEGORY_THRESHOLD

        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_A_MINUS: CORRECTION},
            )
            with progress_scope("edit") as progress:
                result = await editor.resolve()

        assert not result.is_valid, "the stub scored below the threshold; this must refuse"
        assert timeline == [
            "Checking your wording fits where you put it",
            "Checking where what you wrote fits better",
            "Checking where what you wrote fits better",
            "Checking where what you wrote fits better",
        ], f"got {timeline}"
        assert progress.done == progress.total == 4, (
            f"closed at {progress.done}/{progress.total} — a refusal must still add"
            f" up, and the three-call search is what the person is actually waiting"
            f" through"
        )

    @pytest.mark.asyncio
    async def test_both_poles_retyped_speaks_three_times(self, stub_concerns, timeline):
        """T and A both changed: take both in, weigh them, work out the four parts.

        The first two lines are `introduce_polarity`'s, verbatim. Same work, same
        words — a person should not be able to tell from the vocabulary whether they
        are introducing a tension or correcting one.
        """
        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T: "Reachable supervisors", POSITION_A: "Balanced rota"},
            )
            with progress_scope("edit"):
                result = await editor.resolve()

        assert result.is_valid, result.error_message
        assert timeline == [
            "Taking in both sides of what you described",
            "Weighing how strongly the two pull against each other",
            "Working out how each side helps and how each overreaches",
        ], f"got {timeline}"

    @pytest.mark.asyncio
    async def test_one_pole_retyped_says_so_in_the_singular(
        self, stub_concerns, timeline
    ):
        """Only T changed, so the label is `anchor_theses`' singular one."""
        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T: "Reachable supervisors"},
            )
            with progress_scope("edit"):
                result = await editor.resolve()

        assert result.is_valid, result.error_message
        assert timeline == [
            "Taking in the position you named",
            "Weighing how strongly the two pull against each other",
            "Working out how each side helps and how each overreaches",
        ], f"got {timeline}"

    @pytest.mark.asyncio
    async def test_the_regeneration_branch_leaves_the_talking_to_extraction(
        self, stub_concerns, timeline
    ):
        """The longest branch on the pole path declares NOTHING of its own.

        When the existing opposition no longer holds against the retyped position,
        `AntithesisExtraction` runs — and it reports its own steps and notes each
        angle as it comes back. A step declared here would publish in the same
        instant as extraction's first one and be superseded before a person could
        read it: the 0.0s flash that moved the extraction label out of
        `AnalysisPipeline` in the first place.

        `AntithesisExtraction.resolve` is stubbed here, so its own labels are absent
        by construction; what this pins is that no THIRD label appears from this
        module in between.
        """
        stub_concerns["antithesis_hs"] = 0.05  # forces the regeneration branch
        stub_concerns["antitheses"] = []  # ...which then finds nothing, and bails

        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T: "Reachable supervisors"},
            )
            with progress_scope("edit") as progress:
                result = await editor.resolve()

        assert not result.is_valid, "extraction returned nothing; this must refuse"
        assert timeline == [
            "Taking in the position you named",
            "Weighing how strongly the two pull against each other",
        ], f"a label was added over `AntithesisExtraction`'s own: {timeline}"
        assert progress.done == progress.total == 2, (
            f"closed at {progress.done}/{progress.total} — the regeneration branch"
            f" must not leave a step declared for work it delegated"
        )

    @pytest.mark.asyncio
    async def test_a_guard_that_returns_without_a_provider_call_says_nothing(
        self, stub_concerns, timeline
    ):
        """Both top-of-`resolve` refusals, which cost nothing and must announce nothing.

        A step declared at the top of `resolve()` would be reported on every path and
        would be a phantom on these two, closing the stream short. `record_decision`
        set the precedent that 0/0 is a legitimate close for an in-band refusal.
        """
        case = Case()
        case.commit()

        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)

            with progress_scope("edit") as progress:
                nothing_valid = await EditPerspective(
                    perspective_hash=pp.hash, changes={"X+": "not a position"}
                ).resolve()
                missing = await EditPerspective(
                    perspective_hash="deadbeefcafe", changes={POSITION_T: "Anything"}
                ).resolve()

        assert not nothing_valid.is_valid and not missing.is_valid
        assert timeline == [], f"a cost-free refusal published a step: {timeline}"
        assert progress.done == progress.total == 0


# ─── Level two: the assembled stream, through the tool, against mock brain.


@pytest.fixture
async def collected_progress():
    """Subscribe to `sid:progress` and hand back the bus for one run."""
    bus = GraphEventBus()
    await bus.connect()
    # RESTORE, never clear: the module-level bus is wired once by the
    # session-scoped `di_container` fixture, so `None` here would silently disable
    # progress for every test that ran afterwards.
    previous = progress_module._event_bus
    progress_module.set_event_bus(bus)
    try:
        yield bus
    finally:
        progress_module.set_event_bus(previous)
        await bus.disconnect()


async def _drain(received: list, *, timeout: float = 5.0) -> None:
    """Wait until `received` stops growing, rather than sleeping a fixed interval."""
    previous = -1
    waited = 0.0
    while previous != len(received) and waited < timeout:
        previous = len(received)
        await asyncio.sleep(0.05)
        waited += 0.05


async def _run_edit_collecting(bus, sid: str, **kwargs) -> list:
    """Run the `edit_perspective` TOOL under `sid` while draining its channel.

    The `scope` is entered around the AWAIT, not around building the coroutine:
    `_publish` drops every event when no sid is in scope, so a factory that left the
    `with` before anything ran would report "the person saw silence" about the
    harness rather than about the tool.
    """
    received: list = []
    ready = asyncio.Event()

    async def _listen() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            ready.set()
            async for event in subscriber:
                received.append(event.message)

    listener = asyncio.create_task(_listen())
    await ready.wait()
    try:
        with scope(sid):
            await edit_perspective.fn(**kwargs)
        await _drain(received)
    finally:
        listener.cancel()
    return received


@pytest.mark.llm
class TestOneEditIsOneKeyedStream:
    """What only the assembled stream can show: that the scope exists and closes."""

    @pytest.mark.asyncio
    async def test_the_tool_installs_a_scope_and_closes_it_once(
        self, collected_progress
    ):
        """The whole defect: this tool published nothing at all before.

        Deliberately NOT asserting which labels arrive — which branch mock brain
        drives depends on the similarity scores it returns, and pinning that here
        would be pinning the mock. The branch-by-branch labels are the first class's
        job; this one pins that they reach a host.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            pp_hash = pp.hash

        events = await _run_edit_collecting(
            collected_progress,
            case.sid,
            perspective_hash=pp_hash,
            changes={POSITION_T_PLUS: "Reachable supervisor"},
        )

        assert events, (
            "not one progress event — this is the silence the whole change exists to"
            " end, and the assertion that fails if the tool's `with` is removed"
        )
        finals = [e for e in events if e.final]
        steps = [e for e in events if not e.final and not e.note]
        assert len(finals) == 1, (
            f"expected exactly one closing event, got {len(finals)} — a host clears"
            f" its indicator on `final`, so two means it cleared mid-run"
        )
        assert steps, (
            "a `final` arrived with no steps before it, which is the mis-placed-scope"
            " signature: the scope is installed but nothing under it reported"
        )
        assert finals[0].done == finals[0].total, (
            f"closed at {finals[0].done}/{finals[0].total} — every step on this path"
            f" is declared immediately before its own await, so a shortfall means one"
            f" was declared over a guard that skipped the work (a phantom step)"
        )
        assert {e.stage for e in events} == {"edit"}, (
            f"more than one stage on this channel: {sorted({e.stage for e in events})}"
            f" — an inner stage name here means a nested scope installed instead of"
            f" deferring"
        )

    @pytest.mark.asyncio
    async def test_the_key_survives_a_model_echoing_the_brackets_back(
        self, collected_progress
    ):
        """`perspective_hash` is raw model output, and the key is a rendered surface.

        The framework shows hashes to the model as `[[abc1234]]`, and echoing the
        brackets back is the single most common malformed-hash shape in this tree.
        Unsanitised it keyed the stream `"[[a1b2"` and put prompt-template punctuation
        beside a host's spinner. Same fix, and same reason, as `deepen`'s.

        The edit itself REFUSES here — a bracketed hash resolves to no node — and that
        is the design being pinned as much as the key is: only the key is sanitised,
        because what a malformed hash should do to the reasoning path is
        `_resolve_perspective`'s decision, not the progress channel's.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            pp_hash = pp.hash

        events = await _run_edit_collecting(
            collected_progress,
            case.sid,
            perspective_hash=f"  [[{pp_hash[:7]}]]  ",
            changes={POSITION_T_PLUS: "Reachable supervisor"},
        )

        assert events
        assert {e.key for e in events} == {pp_hash[:7]}, (
            f"key was not sanitised: {sorted({e.key for e in events})}"
        )

    @pytest.mark.asyncio
    async def test_nothing_a_host_renders_carries_the_correction_or_the_machinery(
        self, collected_progress
    ):
        """Labels AND the key are host-rendered, and here the input is a correction.

        `changes` is the person's own retyped wording by definition — this is the one
        tool whose entire purpose is that they typed it themselves — so the leak check
        matters more here than on paths where the text is merely quoted.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            pp_hash = pp.hash

        events = await _run_edit_collecting(
            collected_progress,
            case.sid,
            perspective_hash=pp_hash,
            changes={POSITION_T_PLUS: CORRECTION},
        )

        assert events
        for event in events:
            lowered = event.detail.lower()
            for term in BANNED:
                assert term not in lowered, (
                    f"label {event.detail!r} names the machinery ({term!r}) — a host"
                    f" may render these to a person verbatim, which is why the"
                    f" per-part label says 'where you put it' and not 'T+'"
                )
            assert len(event.detail) < 200, (
                f"label is {len(event.detail)} chars: too long to be a label and long"
                f" enough to be carrying content"
            )
            if event.final:
                assert event.detail == "", (
                    f"the closing event labelled itself {event.detail!r}; the label"
                    f" beside a host's spinner is the host's to write, from `stage`,"
                    f" `key`, `done` and `total`"
                )
            for start in range(0, len(CORRECTION) - _LEAK_RUN):
                run = CORRECTION[start : start + _LEAK_RUN]
                assert run not in event.detail, f"correction leaked into {event.detail!r}"
                assert run not in (event.key or ""), "correction leaked into the key"

    @pytest.mark.asyncio
    async def test_a_refused_edit_still_closes_its_stream(self, collected_progress):
        """The cost-free refusal, through the tool.

        No steps at all on this path, which is legitimate — `record_decision`'s
        in-band refusals set that precedent. What is not legitimate is leaving the
        stream open, or closing it short because something was declared above the
        guard.
        """
        case = Case()
        case.commit()
        with scope(case.sid):
            pp = create_test_pp(case.sid, commit=True)
            pp_hash = pp.hash

        events = await _run_edit_collecting(
            collected_progress,
            case.sid,
            perspective_hash=pp_hash,
            changes={"X+": "not a position"},
        )

        finals = [e for e in events if e.final]
        assert len(finals) == 1, (
            f"expected exactly one closing event on the refusal branch, got"
            f" {len(finals)} — a tool that returns early must still close its stream"
        )
        assert finals[0].done == finals[0].total == 0, (
            f"closed at {finals[0].done}/{finals[0].total} on a branch that made no"
            f" provider call: a step was declared above a guard it does not reach"
        )
