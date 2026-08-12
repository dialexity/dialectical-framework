"""Re-estimating a value the entity used to hold must not raise.

An `Estimation` is content-identified by `(type, value, target)` — `provider` is
deliberately excluded from the hash (`set_provider`: "the same (type, value,
target) estimation is the same regardless of provider"). That exclusion is what
made value ping-pong fatal:

  1. `upsert_estimation(node, Mode, 0.4, provider=r1)` creates Mode(0.4) with
     ESTIMATES + PROVIDES.
  2. `upsert_estimation(node, Mode, 0.1, ...)` sees the value change and used to
     merely `disconnect` the ESTIMATES edge. Mode(0.4) survived as an orphan,
     still carrying r1's PROVIDES.
  3. A later `upsert_estimation(node, Mode, 0.4, provider=r2)` looks up by
     `{value: 0.4}` ALONG the ESTIMATES edge, which is gone — so it missed and
     built a fresh node.
  4. `commit()` hashes the same three parts, so hash-dedup adopted the orphan's
     `_id`, then connected r2 as provider. The orphan already had r1 and
     `provider` cardinality is `(0,1)` -> ValueError.

That ValueError is what killed two whole `anchor` calls in the `claim2-weak-r14`
bench run, reported as "Perspective has no Polarity connected" — a false cause
(cardinality is validated BEFORE hashing, so a committed Perspective provably
had its edge). Antithesis re-extraction ping-pongs Mode/Arousal on every repeat
anchor of the same tension, so this was reachable by ordinary conversation.

Two fixes, both pinned here:
  * `EstimationManager.upsert_estimation` DELETES the superseded node instead of
    detaching it — an estimation has no meaning apart from what it estimates, so
    a detached one is garbage, invisible to lookup but visible to hash-dedup.
  * `Estimation.commit` skips the provider connect when an edge already exists —
    defence in depth, since content-addressing means resolving onto another
    rationale's node is by design. First attribution stands.

Run: poetry run pytest tests/test_estimation_upsert_lifecycle.py
"""

from __future__ import annotations

from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.estimation import (ArousalEstimation,
                                                          ModeEstimation)
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity"


def _mode_nodes(db, target_id: int) -> list[dict]:
    """Every Mode node in the test scope, with its edge types."""
    rows = list(
        db.execute_and_fetch(
            "MATCH (e:Mode:___DIALEXITY_TEST___) "
            "RETURN id(e) AS i, e.value AS v"
        )
    )
    out = []
    for r in rows:
        edges = list(
            db.execute_and_fetch(
                "MATCH (e)-[rel]-(m) WHERE id(e) = $i "
                "RETURN type(rel) AS t, id(m) AS mi",
                {"i": r["i"]},
            )
        )
        out.append(
            {
                "id": r["i"],
                "value": r["v"],
                "types": sorted(e["t"] for e in edges),
                "estimates_target": any(
                    e["t"] == "ESTIMATES" and e["mi"] == target_id for e in edges
                ),
            }
        )
    return out


def _fixture(text: str = "Transfer the accounts first"):
    """A committed target plus a manager, inside a fresh case scope."""
    case = Case()
    case.commit()
    return case, text


def test_value_change_leaves_no_orphan(di_container):
    """The superseded estimation is deleted, not merely detached."""
    db = di_container.graph_db()
    case, text = _fixture()
    with scope(case.sid):
        target = Statement(text=text, meaning=MEANING)
        target.commit()
        manager = EstimationManager()

        why = Rationale(text="first explanation")
        why.set_explanation_target(target)
        why.commit()

        manager.upsert_estimation(target, ModeEstimation, 0.4, provider=why)
        manager.upsert_estimation(target, ModeEstimation, 0.1, provider=why)

        nodes = _mode_nodes(db, target._id)
        assert len(nodes) == 1, f"superseded Mode(0.4) survived: {nodes}"
        assert nodes[0]["value"] == 0.1
        assert nodes[0]["estimates_target"]


def test_reestimating_an_old_value_with_a_new_provider(di_container):
    """The exact r14 sequence: 0.4 -> 0.1 -> 0.4 under a different rationale."""
    db = di_container.graph_db()
    case, text = _fixture()
    with scope(case.sid):
        target = Statement(text=text, meaning=MEANING)
        target.commit()
        manager = EstimationManager()

        first = Rationale(text="first explanation")
        first.set_explanation_target(target)
        first.commit()

        second = Rationale(text="second, different explanation")
        second.set_explanation_target(target)
        second.commit()

        manager.upsert_estimation(target, ModeEstimation, 0.4, provider=first)
        manager.upsert_estimation(target, ModeEstimation, 0.1, provider=first)

        # Used to raise: "ModeEstimation already has 1 'provider' relationship(s)"
        result = manager.upsert_estimation(
            target, ModeEstimation, 0.4, provider=second
        )

        assert result is not None
        assert result.value == 0.4
        nodes = _mode_nodes(db, target._id)
        assert len(nodes) == 1, f"expected one live Mode node, got {nodes}"
        assert nodes[0]["value"] == 0.4
        assert nodes[0]["types"] == ["ESTIMATES", "PROVIDES"]


def test_repeated_ping_pong_stays_stable(di_container):
    """Many alternations, two estimation types, two providers — still one each.

    Antithesis re-extraction writes Mode AND Arousal on every repeat anchor, so
    the realistic failure mode is a long alternation, not a single switch.
    """
    db = di_container.graph_db()
    case, text = _fixture()
    with scope(case.sid):
        target = Statement(text=text, meaning=MEANING)
        target.commit()
        manager = EstimationManager()

        providers = []
        for i in range(2):
            why = Rationale(text=f"explanation {i}")
            why.set_explanation_target(target)
            why.commit()
            providers.append(why)

        for round_index in range(6):
            provider = providers[round_index % 2]
            mode = 0.4 if round_index % 2 == 0 else 0.1
            manager.upsert_estimation(
                target, ModeEstimation, mode, provider=provider
            )
            manager.upsert_estimation(
                target, ArousalEstimation, 1.0 - mode, provider=provider
            )

        nodes = _mode_nodes(db, target._id)
        assert len(nodes) == 1, f"Mode nodes accumulated: {nodes}"
        arousal = [
            est
            for est, _ in target.estimations.all()
            if isinstance(est, ArousalEstimation)
        ]
        assert len(arousal) == 1, f"Arousal nodes accumulated: {arousal}"


def test_same_value_reupsert_is_idempotent(di_container):
    """Baseline: no value change means the existing node is reused as-is."""
    db = di_container.graph_db()
    case, text = _fixture()
    with scope(case.sid):
        target = Statement(text=text, meaning=MEANING)
        target.commit()
        manager = EstimationManager()

        why = Rationale(text="one explanation")
        why.set_explanation_target(target)
        why.commit()

        ids = set()
        for _ in range(3):
            est = manager.upsert_estimation(
                target, ModeEstimation, 0.8, provider=why
            )
            ids.add(est._id)

        assert len(ids) == 1, f"same value produced different nodes: {ids}"
        assert len(_mode_nodes(db, target._id)) == 1
