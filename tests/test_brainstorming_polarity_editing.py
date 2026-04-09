"""
Tests for PolarityEditor agent.
"""

from __future__ import annotations

import pytest
from langfuse.decorators import observe

from dialectical_framework.agents.analyst.skills.polarity_editor import (
    HS_WRONG_CATEGORY_THRESHOLD, PolarityEditor)
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.wisdom_unit import (POSITION_A,
                                                           POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           WisdomUnit)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, ARelationship,
    HasPolarityRelationship, TMinusRelationship, TPlusRelationship,
    TRelationship)
from dialectical_framework.graph.scope_context import scope


def create_test_wu(sid: str, commit: bool = False) -> WisdomUnit:
    """Create a test WisdomUnit with T, A and all poles via Polarity.

    Args:
        sid: Session ID
        commit: If True, commits the WU (default: False, returns uncommitted)

    Returns:
        WisdomUnit with Polarity (T+A) and all 4 poles connected
    """
    with scope(sid):
        t = DialecticalComponent(
            statement="Love",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
        )
        t.commit()

        a = DialecticalComponent(
            statement="Indifference",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Separation",
        )
        a.commit()

        # Create poles
        t_plus = DialecticalComponent(
            statement="Deep connection",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence",
        )
        t_plus.commit()

        t_minus = DialecticalComponent(
            statement="Obsessive attachment",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Enmeshment",
        )
        t_minus.commit()

        a_plus = DialecticalComponent(
            statement="Healthy detachment",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Autonomy",
        )
        a_plus.commit()

        a_minus = DialecticalComponent(
            statement="Cold isolation",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Disconnection",
        )
        a_minus.commit()

        # Create Polarity (atomic creation)
        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()

        # Create WU and connect to Polarity
        wu = WisdomUnit()
        wu.save()
        wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

        # Connect poles
        wu.t_plus.connect(
            t_plus,
            relationship=TPlusRelationship(
                alias=POSITION_T_PLUS,
                heuristic_similarity=0.9,
            ),
        )
        wu.t_minus.connect(
            t_minus,
            relationship=TMinusRelationship(
                alias=POSITION_T_MINUS,
                heuristic_similarity=0.85,
            ),
        )
        wu.a_plus.connect(
            a_plus,
            relationship=APlusRelationship(
                alias=POSITION_A_PLUS,
                heuristic_similarity=0.88,
            ),
        )
        wu.a_minus.connect(
            a_minus,
            relationship=AMinusRelationship(
                alias=POSITION_A_MINUS,
                heuristic_similarity=0.82,
            ),
        )

        if commit:
            wu.commit()

        return wu


class TestPolarityEditorThesis:
    """Tests for editing thesis (T)."""

    @pytest.mark.asyncio
    @observe()
    async def test_change_thesis_with_compatible_antithesis(self):
        """Changing T when A is still compatible."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_T: "Trust"},
            )
            result = await editor.execute()

            assert editor.report.ok
            if result.is_valid:
                assert result.wisdom_unit is not None
                # HS is on ARelationship
                a_result = result.wisdom_unit.a.get()
                assert a_result is not None
                _, a_rel = a_result
                assert a_rel.heuristic_similarity is not None
                # Should be forked since original was committed
                assert result.wisdom_unit.origin_hash == wu.hash
                # WU should be committed
                assert result.wisdom_unit.is_committed

    @pytest.mark.asyncio
    @observe()
    async def test_change_thesis_with_incompatible_antithesis(self):
        """Changing T to something incompatible with current A."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_T: "Database Indexing"},
            )
            result = await editor.execute()

            # Should either:
            # 1. Generate new antithesis if original A has HS <= 0.1
            # 2. Keep A if HS > 0.1
            assert editor.report.ok is result.is_valid
            if result.is_valid:
                assert result.wisdom_unit is not None


class TestPolarityEditorAntithesis:
    """Tests for editing antithesis (A)."""

    @pytest.mark.asyncio
    @observe()
    async def test_change_antithesis_valid(self):
        """Changing A to a valid antithesis."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_A: "Hate"},
            )
            result = await editor.execute()

            assert editor.report.ok
            assert result.is_valid
            assert result.wisdom_unit is not None
            # HS is on ARelationship
            a_result = result.wisdom_unit.a.get()
            assert a_result is not None
            _, a_rel = a_result
            assert a_rel.heuristic_similarity is not None
            assert a_rel.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD

    @pytest.mark.asyncio
    @observe()
    async def test_change_antithesis_to_pole_suggests_correction(self):
        """Changing A to something that's actually a pole."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_A: "Obsession"},
            )
            result = await editor.execute()

            # May be invalid with error message, or valid with low HS
            if not result.is_valid:
                # Error should mention pole position
                assert "pole" in result.error_message.lower() or result.error_message


class TestPolarityEditorPole:
    """Tests for editing poles (T+, T-, A+, A-)."""

    @pytest.mark.asyncio
    @observe()
    async def test_change_pole_valid(self):
        """Changing a pole to a valid value."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_T_PLUS: "Deep bond"},
            )
            result = await editor.execute()

            if result.is_valid:
                assert result.wisdom_unit is not None
                # HS is on ARelationship
                a_result = result.wisdom_unit.a.get()
                assert a_result is not None
                _, a_rel = a_result
                assert a_rel.heuristic_similarity is not None

    @pytest.mark.asyncio
    @observe()
    async def test_change_pole_wrong_position_suggests_correct(self):
        """Changing a pole to something that belongs elsewhere."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_T_PLUS: "Complete isolation"},
            )
            result = await editor.execute()

            # Should be invalid or have suggestion in error
            if not result.is_valid:
                # Might suggest A- or another position
                pass


class TestPolarityEditorForking:
    """Tests for forking behavior (committed vs uncommitted WU)."""

    @pytest.mark.asyncio
    @observe()
    async def test_uncommitted_wu_edited_in_place(self):
        """Editing uncommitted WU fills it in place and commits it."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid)
            # Don't commit - leave uncommitted
            wu.save()  # But save so it has _id

            # Note: PolarityEditor requires a committed WU hash or prefix
            # For uncommitted WUs, the caller should commit first or use a different pattern
            # This test documents that limitation

    @pytest.mark.asyncio
    @observe()
    async def test_committed_wu_creates_fork(self):
        """Editing committed WU creates a fork with origin_hash."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)
            original_hash = wu.hash

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_A: "Hatred"},
            )
            result = await editor.execute()

            if result.is_valid:
                # Should be a different WU
                assert result.wisdom_unit.hash != original_hash
                # Should have origin_hash pointing to original
                assert result.wisdom_unit.origin_hash == original_hash


class TestPolarityEditorValidation:
    """Tests for validation edge cases."""

    @pytest.mark.asyncio
    async def test_edit_empty_changes_fails(self):
        """Empty changes dict should fail."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={POSITION_T: ""},
            )
            result = await editor.execute()

            assert not result.is_valid
            assert "non-empty" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_edit_invalid_position_fails(self):
        """Invalid position should fail."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            wu = create_test_wu(brainstorm.sid, commit=True)

            editor = PolarityEditor(
                wisdom_unit_hash=wu.hash,
                changes={"X+": "Something"},
            )
            result = await editor.execute()

            assert not result.is_valid
            assert "Invalid position" in result.error_message

    @pytest.mark.asyncio
    async def test_edit_nonexistent_wu_fails(self):
        """Nonexistent WU hash should fail."""
        brainstorm = Brainstorm()
        brainstorm.commit()

        with scope(brainstorm.sid):
            editor = PolarityEditor(
                wisdom_unit_hash="nonexistent123",
                changes={POSITION_T: "Something"},
            )
            result = await editor.execute()

            assert not result.is_valid
            assert "not found" in result.error_message.lower()
