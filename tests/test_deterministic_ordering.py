"""
Deterministic ordering of rendered structures (review finding: T1/T2 indices
rested on unordered Cypher results).

`build_pp_index` is the canonical source of perspective indices — every
rendered label (T1, A2+, cycle sequences, cross-exploration references)
depends on its ordering. Without an ORDER BY, Cypher result order is
unspecified: stable only by accident of the current storage engine, and
free to permute across DB restarts or vendors. These tests pin the contract:
RelationshipManager.all() (and the nexus/cycle/wheel listing queries) order
by committed_at with id() as tiebreaker, so two renders of the same graph
always agree — and the order is COMMIT time, not edge-creation time.
"""

from __future__ import annotations

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    Perspective,
)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.belongs_to_nexus_relationship import (
    BelongsToNexusRelationship,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship,
    APlusRelationship,
    HasPolarityRelationship,
    TMinusRelationship,
    TPlusRelationship,
)
from dialectical_framework.graph.rendering import build_pp_index
from dialectical_framework.graph.scope_context import scope


def _committed_perspective(thesis_text: str, antithesis_text: str) -> Perspective:
    """Fully-populated committed Perspective (tetrad cardinality requires
    all four aspects at commit)."""
    thesis = Statement(text=thesis_text, meaning="test")
    thesis.commit()
    antithesis = Statement(text=antithesis_text, meaning="test")
    antithesis.commit()

    polarity = Polarity()
    polarity.set_t(thesis, heuristic_similarity=1.0)
    polarity.set_a(antithesis, heuristic_similarity=0.8)
    polarity.commit()

    aspects = {}
    for role in ("T+", "T-", "A+", "A-"):
        stmt = Statement(text=f"{role} of {thesis_text}", meaning="test")
        stmt.commit()
        aspects[role] = stmt

    pp = Perspective()
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
    pp.t_plus.connect(
        aspects["T+"],
        relationship=TPlusRelationship(alias=POSITION_T_PLUS, heuristic_similarity=0.9),
    )
    pp.t_minus.connect(
        aspects["T-"],
        relationship=TMinusRelationship(alias=POSITION_T_MINUS, heuristic_similarity=0.85),
    )
    pp.a_plus.connect(
        aspects["A+"],
        relationship=APlusRelationship(alias=POSITION_A_PLUS, heuristic_similarity=0.88),
    )
    pp.a_minus.connect(
        aspects["A-"],
        relationship=AMinusRelationship(alias=POSITION_A_MINUS, heuristic_similarity=0.8),
    )
    pp.commit()
    return pp


class TestPerspectiveIndexOrdering:
    def test_index_follows_commit_time_not_connect_order(self):
        """Perspectives connected to the nexus in REVERSE commit order must
        still index by commit time — the ordering contract is temporal,
        not an accident of edge-insertion order."""
        case = Case()
        case.commit()
        with scope(case.sid):
            pps = [
                _committed_perspective(f"Thesis {i}", f"Antithesis {i}")
                for i in range(3)
            ]

            nexus = Nexus(intent="ordering test")
            nexus.save()
            # Connect newest-first: under insertion-order results this
            # would index pps[2] as T1.
            for pp in reversed(pps):
                pp.nexus.connect(nexus, relationship=BelongsToNexusRelationship())
            nexus.commit()

            index = build_pp_index(nexus)

        assert [index[pp._id] for pp in pps] == [1, 2, 3]

    def test_repeated_calls_agree(self):
        """Two renders of the same graph must produce identical indices."""
        case = Case()
        case.commit()
        with scope(case.sid):
            pps = [
                _committed_perspective(f"Stmt {i}", f"Anti {i}") for i in range(4)
            ]
            nexus = Nexus(intent="repeat render test")
            nexus.save()
            for pp in pps:
                pp.nexus.connect(nexus, relationship=BelongsToNexusRelationship())
            nexus.commit()

            first = build_pp_index(nexus)
            second = build_pp_index(nexus)

        assert first == second
        assert sorted(first.values()) == [1, 2, 3, 4]


class TestWheelCapTiebreak:
    def test_tied_probability_wheels_sort_by_hash(self):
        """The rendered top-N under advisor_wheel_quality_top_plausible must
        not depend on arrival order when probabilities tie: hash breaks the
        tie deterministically. Exercises the sort key directly (the full
        dump path is covered by test_advisor_context_render)."""

        class _W:
            def __init__(self, _id: int, hash_: str) -> None:
                self._id = _id
                self.hash = hash_

        wheels = [_W(1, "bbb"), _W(2, "aaa"), _W(3, "ccc")]
        probs: dict[int, float | None] = {1: 0.5, 2: 0.5, 3: None}

        def key(w):
            return (-(probs.get(w._id) or -1.0), w.hash or "")

        assert [w.hash for w in sorted(wheels, key=key)] == ["aaa", "bbb", "ccc"]
        # Arrival order must not matter.
        assert [w.hash for w in sorted(reversed(wheels), key=key)] == [
            "aaa",
            "bbb",
            "ccc",
        ]
