"""`audit_feasibility` against a real graph: the answer must survive the round trip.

WHY A GRAPH TEST AND NOT JUST FAKES
===================================
`test_audit_feasibility_tool.py` pins the tool's decisions (what to audit, what
to skip, what to name) with fakes. It cannot pin the part that actually breaks:
the tool never reads the concern's RETURN value. It writes through
`TransformationAudit` and reads back out of the graph — score from the
`FeasibilityEstimation`, reasoning from that estimation's `provider` Rationale.
Two live queries, one of them across a relationship the framework had no reader
for before this tool existed, and both invisible to a fake.

So this builds a real Transformation, runs the real concern (mock brain, no
provider calls), and asserts the answer comes back out. Then asks twice, which
is the case that pays double if the idempotency check reads the graph wrong.
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.relationships.polarity_relationship import (
    AcPlusRelationship, RePlusRelationship)
from dialectical_framework.graph.scope_context import scope

pytestmark = pytest.mark.llm


def _built_transformation():
    """A committed Transformation with Ac+/Re+ transitions the audit can read.

    Each transition carries an explanation Rationale, because that is what the
    audit critiques — a transition without one is silently skipped, which would
    make this test pass by auditing nothing.
    """
    labels = ["T", "T+", "T-", "A", "A+", "A-"]
    components = []
    for label in labels:
        stmt = Statement(
            text=f"{label} of the buyout question", meaning=f"verbatim:{label}"
        )
        stmt.commit()
        components.append(stmt)

    import test_graph as tg

    pp, _ = tg.create_pp_from_components(
        t=components[0],
        a=components[3],
        t_plus=components[1],
        t_minus=components[2],
        a_plus=components[4],
        a_minus=components[5],
        intent="buyout",
    )
    pp.commit()

    nexus = Nexus(intent="whether to buy out the cofounder")
    nexus.commit()
    pp.nexus.connect(nexus)

    cycle = Cycle(intent="preset:balanced")
    cycle.set_perspectives([pp])
    cycle.commit()

    wheel = Wheel(intent="wheel")
    wheel.save()
    edge = Transition()
    edge.set_source(components[0]).set_target(components[3])
    edge.commit()
    edge.cycle.connect(wheel)
    back_edge = Transition()
    back_edge.set_source(components[3]).set_target(components[0])
    back_edge.commit()
    back_edge.cycle.connect(wheel)
    cycle.wheels.connect(wheel)
    wheel.commit()

    transformation = Transformation(intent="tr")
    transformation.set_nexus(nexus)
    transformation.set_on_edge(edge)
    transformation.save()

    for source, target, alias, manager_name, text in (
        (components[2], components[4], "Ac+", "ac_plus", "Hand the accounts over deliberately"),
        (components[5], components[1], "Re+", "re_plus", "Notice what the handover costs"),
    ):
        transition = Transition()
        transition.set_source(source).set_target(target)
        transition.instruction = text
        transition.commit()
        rationale = Rationale(text=f"Why {alias} works: {text.lower()}")
        rationale.set_explanation_target(transition)
        rationale.commit()
        rel = AcPlusRelationship if alias == "Ac+" else RePlusRelationship
        getattr(transformation, manager_name).connect(
            transition, relationship=rel(alias=alias)
        )
    transformation.commit()

    return nexus, transformation


async def test_the_answer_comes_back_out_of_the_graph():
    """The full round trip: audit writes, the tool reads it back and renders it.

    The mock brain builds `TransitionAuditDto` from field metadata — feasibility
    lands at the 0.0-1.0 midpoint and the prose fields carry their own names, so
    0.50 and "key_factors" here are the mock's fingerprints, not magic numbers.
    """
    from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
        run_audit_feasibility

    case = Case()
    case.commit()

    with scope(case.sid):
        _, transformation = _built_transformation()
        report = await run_audit_feasibility([transformation.short_hash])

        assert transformation.short_hash in report
        assert "feasibility=0.50" in report, (
            "the score has to survive the estimation write and the read back"
        )
        assert "key_factors" in report, (
            "the reasoning comes through the estimation's provider Rationale — "
            "a link nothing else in the framework traverses"
        )
        assert "Ac+" in report and "Re+" in report
        assert '"audited": 1' in report


async def test_the_audit_does_not_cry_corruption(caplog):
    """The critique write must not log "a committed node that is not stored".

    It did — 2 per audited Transformation, 12 in the 1-PP cost census, and the
    message names corruption, which is the loudest thing the graph layer says.
    Cause: `commit()` assigns `self.hash`, then `save()` re-computes it as an
    immutability check, so `_collect_structure_hash_parts` read EXPLAINS while
    `hash` was set, `_id` was None and the row did not exist yet. Benign, but a
    warning that cries corruption on a routine write teaches everyone to ignore
    the one signal that would catch the real thing.
    """
    import logging

    from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
        run_audit_feasibility

    case = Case()
    case.commit()

    with scope(case.sid):
        transformation = _built_transformation()[1]
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            report = await run_audit_feasibility([transformation.short_hash])

        offenders = [
            r.getMessage()
            for r in caplog.records
            if "no row in the database" in r.getMessage()
        ]
        assert offenders == [], f"spurious corruption warnings: {offenders}"
        # ...and the audit still did its job, so the silence is not achieved by
        # skipping the write.
        assert "feasibility=0.50" in report


def test_a_critique_hashes_on_its_target(caplog):
    """Hash-neutrality of the fix above, pinned independently of the code path.

    The short-circuit must return the SAME hash the DB-reading fall-through
    returned — a Rationale is content-addressable, so a change here would
    silently fork every existing critique into a duplicate node.
    """
    import hashlib
    import logging

    from dialectical_framework.graph.nodes.rationale import Rationale

    case = Case()
    case.commit()

    with scope(case.sid):
        explained = Rationale(text="the pathway as offered")
        stmt = Statement(text="somewhere to point at", meaning="verbatim:target")
        stmt.commit()
        explained.set_explanation_target(stmt)
        explained.commit()

        critique = Rationale(text="**Key Factors:** goodwill, timing")
        critique.set_critiques_target(explained)
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            critique.commit()

        expected = hashlib.sha256(
            f"{critique.text}\n{explained.hash}".encode("utf-8")
        ).hexdigest()
        assert critique.hash == expected, (
            "a critique hashes on text + target hash; changing that forks "
            "every critique already in the graph"
        )
        assert not [
            r for r in caplog.records if "no row in the database" in r.getMessage()
        ]


async def test_the_two_positions_are_audited_at_once(monkeypatch):
    """Ac+ and Re+ must be in flight together, not one after the other.

    Sequential cost nothing anyone could feel while the audit lived inside a
    `gather` over 6 Transformations. On the `audit_feasibility` path it IS the
    wait — someone asked "is this doable?" and gets 2 × ~12.3s of silence.

    The barrier below is the assertion: the first auditor blocks until the second
    arrives. Under `gather` both are in flight, the second releases the first,
    and the concern returns. Restore the `for` loop and the second call never
    happens — the first waits out the timeout and this fails with TimeoutError
    rather than passing slowly.
    """
    from dialectical_framework.concerns import transformation_audit as ta_mod

    arrived = asyncio.Event()
    entered: list[str] = []
    real_run = ta_mod.TransformationAudit._run_audit

    async def barrier(self, prompt: str):
        entered.append(prompt)
        if len(entered) == 1:
            await asyncio.wait_for(arrived.wait(), timeout=10)
        else:
            arrived.set()
        return await real_run(self, prompt)

    monkeypatch.setattr(ta_mod.TransformationAudit, "_run_audit", barrier)

    case = Case()
    case.commit()

    with scope(case.sid):
        _, transformation = _built_transformation()
        results = await ta_mod.TransformationAudit().resolve(transformation)

    assert len(entered) == 2, "both positions must reach the provider"
    assert {r.position for r in results} == {"Ac+", "Re+"}


async def test_asking_again_costs_nothing(monkeypatch):
    """The second ask is the likely one (someone re-raises the same doubt) and
    the one that pays double: `upsert_estimation` would replace the score, but
    the critique Rationales accumulate with no way to tell which produced it."""
    from dialectical_framework.concerns import transformation_audit as ta_mod
    from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
        run_audit_feasibility

    case = Case()
    case.commit()

    with scope(case.sid):
        _, transformation = _built_transformation()
        await run_audit_feasibility([transformation.short_hash])

        calls: list = []
        real_resolve = ta_mod.TransformationAudit.resolve

        async def counted(self, *args, **kwargs):
            calls.append(args[0])
            return await real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(ta_mod.TransformationAudit, "resolve", counted)
        again = await run_audit_feasibility([transformation.short_hash])

        assert calls == [], "an already-assessed pathway must not be re-audited"
        assert "already_estimated" in again
        assert "feasibility=0.50" in again, (
            "free does not mean empty — the stored answer is the answer"
        )
        assert "key_factors" in again
