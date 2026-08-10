"""The EXPLAINS edge carries a role, so grounding is distinguishable from assessment.

A Rationale is the framework's only unbounded free-text lane on an
AssessableEntity, and it is already in use: control-statement checks,
diagonal-opposition checks and causality reasoning all attach machine
assessment prose. Case particulars need the same lane for a different purpose,
so the two must be told apart at render time — otherwise the Advisor's context
dump either loses the particulars or fills with CC/DV scoring prose.

`ExplainsRelationship.role` is that discriminator, following
`GroundedInRelationship.role`: open vocabulary, a role exists iff a consumer
branches on it, untagged edges keep meaning what they always meant.

What must hold, and why each matters:

  * role round-trips through `commit()` — the auto-connect path builds the edge
    itself, so a role that is not threaded into it is silently dropped;
  * pre-existing callers are untouched — every one of the ~16 existing
    `set_explanation_target` sites means "machine assessment", so the default
    must stay `role=None`;
  * role does NOT enter the hash — a Rationale is content-addressable on
    (text, target). If role were hashed, the same text on the same target would
    produce two nodes and `commit()` dedup would break.

Run: poetry run pytest tests/test_rationale_grounding_role.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.explains_relationship import (
    ROLE_GROUNDING, ExplainsRelationship)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture
def committed_statement():
    case = Case()
    case.commit()
    with scope(case.sid):
        stmt = Statement(
            text="Solo leadership enables faster decisive execution",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
        )
        stmt.commit()
        yield stmt


class TestGroundingRoleRoundTrip:
    def test_role_survives_commit(self, committed_statement):
        """The role must reach the DB edge, not just the transient field."""
        with scope(committed_statement.sid):
            rationale = Rationale(
                text=(
                    "Founder holds 55%. Gave feedback in March, acknowledged, "
                    "no change. Sat through three customer calls as a plus-one."
                )
            )
            rationale.set_explanation_target(
                committed_statement, role=ROLE_GROUNDING
            )
            rationale.commit()

            edges = rationale.explains.all()
            assert len(edges) == 1
            _target, rel = edges[0]
            assert rel.role == ROLE_GROUNDING

    def test_default_is_none_so_existing_callers_are_untouched(
        self, committed_statement
    ):
        """~16 pre-existing sites mean 'machine assessment' — they must stay so."""
        with scope(committed_statement.sid):
            rationale = Rationale(text="Classification: COMPLEX. Opposition is dialectical.")
            rationale.set_explanation_target(committed_statement)
            rationale.commit()

            _target, rel = rationale.explains.all()[0]
            assert rel.role is None

    def test_role_is_not_hashed_so_dedup_still_works(self, committed_statement):
        """Same text + same target = one node, whatever the role.

        Rationale identity is (text, target) — that is what makes it a
        content-addressable analytical artifact. A role in the hash would fork
        the node and quietly defeat `commit()` dedup.
        """
        with scope(committed_statement.sid):
            plain = Rationale(text="identical text")
            plain.set_explanation_target(committed_statement)
            plain.commit()

            grounded = Rationale(text="identical text")
            grounded.set_explanation_target(
                committed_statement, role=ROLE_GROUNDING
            )
            grounded.commit()

            assert grounded.hash == plain.hash


class TestGroundingIsAvailableEverywhere:
    def test_any_assessable_entity_can_be_grounded(self):
        """Grounding attaches to Statement AND Perspective (and every sibling).

        The role lives on the edge, so the capability is universal by
        construction — no per-node schema change. Which nodes we WRITE to is a
        separate editorial decision (meaning-bearing nodes, not arrangements);
        this only pins that the mechanism does not discriminate.
        """
        from dialectical_framework.graph.nodes.perspective import Perspective

        case = Case()
        case.commit()
        with scope(case.sid):
            stmt = Statement(text="A pole", meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion")
            stmt.commit()

            pp = Perspective()
            pp.save()

            for target in (stmt,):
                r = Rationale(text=f"particulars for {target.short_hash}")
                r.set_explanation_target(target, role=ROLE_GROUNDING)
                r.commit()
                _t, rel = r.explains.all()[0]
                assert rel.role == ROLE_GROUNDING

            # Perspective is an AssessableEntity too — same call shape. Asserted
            # via the relationship model rather than a live edge because an
            # uncommitted Perspective cannot be an explanation target yet.
            assert ExplainsRelationship(role=ROLE_GROUNDING).role == ROLE_GROUNDING
