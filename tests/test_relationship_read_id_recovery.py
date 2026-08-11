"""A relationship READ must not answer "no edges" for a node it failed to locate.

`all()` and `count()` bail when the source node has no `_id`. They used to bail
by returning `[]`/`0` — a value indistinguishable from "this node genuinely has
no such edges". The lie is load-bearing rather than cosmetic, because
`Perspective.is_complete()` is `self.polarity.count() >= 1 and ...`:

  * a committed Perspective whose Python object lost its `_id` counts 0
    HAS_POLARITY edges, so `is_complete()` reports PARTIAL;
  * `ExpandPolarity` sends partials back through `AspectGeneration`;
  * that reads `perspective.t`, which raises "Perspective has no Polarity
    connected" — about a perspective whose HAS_POLARITY edge is in the database.

Measured in `claim2-weak-r6-grounding` (A2 / cofounder_equity / rep 1 /
wobble_a): one `anchor` call reported all five of its tensions failing with that
message, `0 perspectives`, and a cause that was not true. The identical shape
reproduces cleanly under the mock brain, which is why the reproduction hunt
found nothing — the trigger is a lost `_id`, not the pipeline's shape.

The asymmetry that allowed it: the WRITE path already recovered a missing `_id`
from `hash` (`_connect_internal.get_node_id`), and the read path did not. So a
write would repair the very state a read had just mis-reported. Reads now use
the same fallback.

`hash` is the right recovery key because it IS the node's identity — but only
after commit. Pre-commit (`save()` → attach children → `commit()`) there is no
hash and `_id` is the only handle a node has, which is why an unsaved node's
empty read stays legitimate and silent.

Run: poetry run pytest tests/test_relationship_read_id_recovery.py
"""

from __future__ import annotations

import logging

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope

BRANCH = "dx://taxonomy/System(General.v1)/Viability/Integrity"


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _polarity(t_text: str = "Buy out the cofounder now") -> Polarity:
    t = Statement(text=t_text, meaning=f"{BRANCH}/Cohesion")
    t.commit()
    a = Statement(text="Keep him and reset the terms", meaning=f"{BRANCH}/Separation")
    a.commit()
    pol = Polarity()
    pol.set_t(t, heuristic_similarity=1.0)
    pol.set_a(a, heuristic_similarity=0.85)
    pol.commit()
    return pol


def _committed_pp(pol: Polarity) -> Perspective:
    """A fully-populated committed Perspective — a hash is what makes it recoverable.

    All four aspects are attached because cardinality requires them and because
    `is_complete()` (the predicate the bug corrupted) reads all five edges.
    """
    aspects = {}
    for key, text in (
        ("t_plus", "Clean ownership with a stated exit"),
        ("t_minus", "Control that stops listening"),
        ("a_plus", "Terms that keep him accountable"),
        ("a_minus", "Endless renegotiation"),
    ):
        stmt = Statement(text=text, meaning=f"{BRANCH}/Cohesion")
        stmt.commit()
        aspects[key] = stmt

    pp = Perspective()
    pp.save()
    pp.polarity.connect(pol, relationship=HasPolarityRelationship())
    pp.t_plus.connect(
        aspects["t_plus"],
        relationship=TPlusRelationship(alias=POSITION_T_PLUS, heuristic_similarity=0.9),
    )
    pp.t_minus.connect(
        aspects["t_minus"],
        relationship=TMinusRelationship(
            alias=POSITION_T_MINUS, heuristic_similarity=0.85
        ),
    )
    pp.a_plus.connect(
        aspects["a_plus"],
        relationship=APlusRelationship(alias=POSITION_A_PLUS, heuristic_similarity=0.88),
    )
    pp.a_minus.connect(
        aspects["a_minus"],
        relationship=AMinusRelationship(
            alias=POSITION_A_MINUS, heuristic_similarity=0.8
        ),
    )
    pp.commit()
    assert pp.hash is not None
    return pp


class TestReadRecoversLostId:
    def test_count_does_not_report_zero_for_a_live_edge(self):
        """The exact defect: 0 edges reported while the edge is in the DB."""
        with scope(_new_sid()):
            pp = _committed_pp(_polarity())
            assert pp.polarity.count() == 1

            pp._id = None
            assert pp.polarity.count() == 1

    def test_all_does_not_report_empty_for_a_live_edge(self):
        with scope(_new_sid()):
            pp = _committed_pp(_polarity())
            pp._id = None

            assert len(pp.polarity.all()) == 1

    def test_is_complete_no_longer_calls_a_full_tetrad_partial(self):
        """The misclassification itself: PARTIAL sends it back to generation.

        `ExpandPolarity` splits on this predicate, and a false PARTIAL is what
        put a fully-built tetrad in front of `AspectGeneration` again.
        """
        with scope(_new_sid()):
            pp = _committed_pp(_polarity())
            assert pp.is_complete() is True

            pp._id = None
            assert pp.is_complete() is True

    def test_t_and_a_stay_reachable(self):
        """`Perspective.t` is where the bench-visible ValueError came from."""
        with scope(_new_sid()):
            pp = _committed_pp(_polarity())
            pp._id = None

            t_result = pp.t.get()
            assert t_result is not None
            assert t_result[0].text == "Buy out the cofounder now"

            pp._id = None
            assert pp.a.get() is not None

    def test_the_id_is_cached_so_recovery_costs_one_query(self):
        with scope(_new_sid()):
            pp = _committed_pp(_polarity())
            original = pp._id

            pp._id = None
            pp.polarity.count()

            assert pp._id == original

    def test_recovery_is_logged_not_silent(self, caplog):
        """A recovered read means something upstream lost the id — say so."""
        with scope(_new_sid()):
            pp = _committed_pp(_polarity())
            pp._id = None

            with caplog.at_level(logging.WARNING):
                pp.polarity.count()

            assert any(
                "recovered it by hash" in r.getMessage() for r in caplog.records
            )


class TestUnsavedNodesStayQuiet:
    """A node that was never persisted genuinely has no edges.

    This is the one empty read that is TRUE, so it must stay empty and must not
    warn — otherwise every `is_complete()` call on a fresh Perspective logs.
    """

    def test_unsaved_node_reads_empty(self):
        with scope(_new_sid()):
            pp = Perspective()
            assert pp.polarity.count() == 0
            assert pp.polarity.all() == []

    def test_unsaved_node_does_not_warn(self, caplog):
        with scope(_new_sid()):
            pp = Perspective()
            with caplog.at_level(logging.WARNING):
                pp.polarity.count()
            assert not [
                r for r in caplog.records if "recovered it by hash" in str(r.msg)
            ]

    def test_saved_but_uncommitted_pp_still_reads_its_edges(self):
        """The build path: `save()` → connect → `commit()`, no hash yet.

        `_id` is the only identity here, which is why it is threaded around at
        all — the recovery path must not have disturbed this.
        """
        with scope(_new_sid()):
            pol = _polarity("Transfer the accounts before deciding")
            pp = Perspective()
            pp.save()
            pp.polarity.connect(pol, relationship=HasPolarityRelationship())

            assert pp.hash is None
            assert pp.polarity.count() == 1
            assert pp.t.get() is not None


class TestErrorNamesTheNode:
    """The bench log could not be traced to a Perspective, only to a Polarity.

    `AnalysisPipeline` labels each expansion error with the POLARITY hash it was
    expanding, so five identical "Perspective has no Polarity connected" lines
    named no perspective and did not say whether one was even saved.
    """

    def test_message_carries_id_hash_and_sid(self):
        with scope(_new_sid()):
            pp = Perspective()  # never saved: no _id, no hash, truly unconnected

            with pytest.raises(ValueError) as exc:
                pp.t.get()

            message = str(exc.value)
            assert "cannot access T" in message
            assert "_id=None" in message
            assert "hash=None" in message

    def test_a_side_is_named_too(self):
        with scope(_new_sid()):
            pp = Perspective()
            with pytest.raises(ValueError) as exc:
                pp.a.get()
            assert "cannot access A" in str(exc.value)
            assert "_id=None" in str(exc.value)
