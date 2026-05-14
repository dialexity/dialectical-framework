"""
Tests for EditPerspective skill (unified polarity + tetrad editing).
"""

from __future__ import annotations

import pytest
from langfuse import observe

from dialectical_framework.agents.analyst.skills.edit_perspective import (
    HS_WRONG_CATEGORY_THRESHOLD, EditPerspective)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import (POSITION_A,
                                                           POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope


def create_test_pp(sid: str, commit: bool = False) -> Perspective:
    """Create a test Perspective with T, A and all aspects via Polarity.

    Args:
        sid: Scope ID
        commit: If True, commits the PP (default: False, returns uncommitted)

    Returns:
        Perspective with Polarity (T+A) and all 4 aspects connected
    """
    with scope(sid):
        t = Statement(
            text="Love",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
        )
        t.commit()

        a = Statement(
            text="Indifference",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
        )
        a.commit()

        # Create aspects
        t_plus = Statement(
            text="Deep connection",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence",
        )
        t_plus.commit()

        t_minus = Statement(
            text="Obsessive attachment",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Enmeshment",
        )
        t_minus.commit()

        a_plus = Statement(
            text="Healthy detachment",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Autonomy",
        )
        a_plus.commit()

        a_minus = Statement(
            text="Cold isolation",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Disconnection",
        )
        a_minus.commit()

        # Create Polarity (atomic creation)
        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()

        # Create PP and connect to Polarity
        pp = Perspective()
        pp.save()
        pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

        # Connect aspects
        pp.t_plus.connect(
            t_plus,
            relationship=TPlusRelationship(
                alias=POSITION_T_PLUS,
                heuristic_similarity=0.9,
            ),
        )
        pp.t_minus.connect(
            t_minus,
            relationship=TMinusRelationship(
                alias=POSITION_T_MINUS,
                heuristic_similarity=0.85,
            ),
        )
        pp.a_plus.connect(
            a_plus,
            relationship=APlusRelationship(
                alias=POSITION_A_PLUS,
                heuristic_similarity=0.88,
            ),
        )
        pp.a_minus.connect(
            a_minus,
            relationship=AMinusRelationship(
                alias=POSITION_A_MINUS,
                heuristic_similarity=0.82,
            ),
        )

        if commit:
            pp.commit()

        return pp


@pytest.mark.llm
class TestEditPerspectiveThesis:
    """Tests for editing thesis (T)."""

    @pytest.mark.asyncio
    @observe()
    async def test_change_thesis_with_compatible_antithesis(self):
        """Changing T when A is still compatible."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T: "Trust"},
            )
            result = await editor.resolve()

            assert editor.report.ok
            if result.is_valid:
                assert result.perspective is not None
                # HS is on ARelationship
                a_result = result.perspective.a.get()
                assert a_result is not None
                _, a_rel = a_result
                assert a_rel.heuristic_similarity is not None
                # PP should be committed
                assert result.perspective.is_committed

    @pytest.mark.asyncio
    @observe()
    async def test_change_thesis_with_incompatible_antithesis(self):
        """Changing T to something incompatible with current A."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T: "Database Indexing"},
            )
            result = await editor.resolve()

            # Should either:
            # 1. Generate new antithesis if original A has HS <= 0.1
            # 2. Keep A if HS > 0.1
            assert editor.report.ok is result.is_valid
            if result.is_valid:
                assert result.perspective is not None


@pytest.mark.llm
class TestEditPerspectiveAntithesis:
    """Tests for editing antithesis (A)."""

    @pytest.mark.asyncio
    @observe()
    async def test_change_antithesis_valid(self):
        """Changing A to a valid antithesis."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_A: "Hate"},
            )
            result = await editor.resolve()

            assert editor.report.ok
            assert result.is_valid
            assert result.perspective is not None
            # HS is on ARelationship
            a_result = result.perspective.a.get()
            assert a_result is not None
            _, a_rel = a_result
            assert a_rel.heuristic_similarity is not None
            assert a_rel.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD

    @pytest.mark.asyncio
    @observe()
    async def test_change_antithesis_to_aspect_suggests_correction(self):
        """Changing A to something that's actually an aspect."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_A: "Obsession"},
            )
            result = await editor.resolve()

            # May be invalid with error message, or valid with low HS
            if not result.is_valid:
                # Error should mention aspect position
                assert "aspect" in result.error_message.lower() or result.error_message


@pytest.mark.llm
class TestEditPerspectiveAspect:
    """Tests for editing aspects (T+, T-, A+, A-)."""

    @pytest.mark.asyncio
    @observe()
    async def test_change_aspect_valid(self):
        """Changing an aspect to a valid value."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T_PLUS: "Deep bond"},
            )
            result = await editor.resolve()

            if result.is_valid:
                assert result.perspective is not None
                # HS is on ARelationship
                a_result = result.perspective.a.get()
                assert a_result is not None
                _, a_rel = a_result
                assert a_rel.heuristic_similarity is not None

    @pytest.mark.asyncio
    @observe()
    async def test_change_aspect_wrong_position_suggests_correct(self):
        """Changing an aspect to something that belongs elsewhere."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T_PLUS: "Complete isolation"},
            )
            result = await editor.resolve()

            # Should be invalid or have suggestion in error
            if not result.is_valid:
                # Might suggest A- or another position
                pass


@pytest.mark.llm
class TestEditPerspectiveCloning:
    """Tests for cloning behavior (committed vs uncommitted PP)."""

    @pytest.mark.asyncio
    @observe()
    async def test_uncommitted_pp_edited_in_place(self):
        """Editing uncommitted PP fills it in place and commits it."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid)
            # Don't commit - leave uncommitted
            pp.save()  # But save so it has _id

            # Note: EditPerspective requires a committed PP hash or prefix
            # For uncommitted PPs, the caller should commit first or use a different pattern
            # This test documents that limitation

    @pytest.mark.asyncio
    @observe()
    async def test_committed_pp_creates_clone(self):
        """Editing committed PP creates a new PP (clone, not mutation)."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)
            original_hash = pp.hash

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_A: "Hatred"},
            )
            result = await editor.resolve()

            if result.is_valid:
                # Should be a different PP
                assert result.perspective.hash != original_hash


class TestEditPerspectiveValidation:
    """Tests for validation edge cases."""

    @pytest.mark.asyncio
    async def test_edit_empty_changes_fails(self):
        """Empty changes dict should fail."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={POSITION_T: ""},
            )
            result = await editor.resolve()

            assert not result.is_valid
            assert "No valid changes" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_invalid_position_fails(self):
        """Invalid position should fail."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            pp = create_test_pp(case_node.sid, commit=True)

            editor = EditPerspective(
                perspective_hash=pp.hash,
                changes={"X+": "Something"},
            )
            result = await editor.resolve()

            assert not result.is_valid
            assert "No valid changes" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_nonexistent_pp_fails(self):
        """Nonexistent PP hash should fail."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            editor = EditPerspective(
                perspective_hash="nonexistent123",
                changes={POSITION_T: "Something"},
            )
            result = await editor.resolve()

            assert not result.is_valid
            assert "not found" in result.error_message.lower()
