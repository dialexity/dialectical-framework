"""
Tests for the DialecticalContext concern.

Verifies:
1. Empty graph returns "No prior understanding" message
2. Graph with perspectives includes structured dump
3. Scores are included in output
4. Hash links are present
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.dialectical_context import DialecticalContext
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
from dialectical_framework.graph.relationships.polarity_relationship import (
    APlusRelationship,
    AMinusRelationship,
    HasPolarityRelationship,
    TPlusRelationship,
    TMinusRelationship,
)
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    """Create a Case and return its sid."""
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _create_perspective_with_aspects(
    thesis_text: str = "Control",
    antithesis_text: str = "Freedom",
    t_plus_text: str = "Safety through structure",
    t_minus_text: str = "Rigidity and micromanagement",
    a_plus_text: str = "Autonomy builds responsibility",
    a_minus_text: str = "Chaos without boundaries",
) -> Perspective:
    """Create a fully-populated Perspective for testing."""
    thesis = Statement(text=thesis_text, meaning="test")
    thesis.commit()
    antithesis = Statement(text=antithesis_text, meaning="test")
    antithesis.commit()

    polarity = Polarity()
    polarity.set_t(thesis, heuristic_similarity=1.0)
    polarity.set_a(antithesis, heuristic_similarity=0.8)
    polarity.commit()

    t_plus = Statement(text=t_plus_text, meaning="test")
    t_plus.commit()
    t_minus = Statement(text=t_minus_text, meaning="test")
    t_minus.commit()
    a_plus = Statement(text=a_plus_text, meaning="test")
    a_plus.commit()
    a_minus = Statement(text=a_minus_text, meaning="test")
    a_minus.commit()

    pp = Perspective()
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
    pp.t_plus.connect(
        t_plus,
        relationship=TPlusRelationship(alias=POSITION_T_PLUS, heuristic_similarity=0.9),
    )
    pp.t_minus.connect(
        t_minus,
        relationship=TMinusRelationship(alias=POSITION_T_MINUS, heuristic_similarity=0.85),
    )
    pp.a_plus.connect(
        a_plus,
        relationship=APlusRelationship(alias=POSITION_A_PLUS, heuristic_similarity=0.88),
    )
    pp.a_minus.connect(
        a_minus,
        relationship=AMinusRelationship(alias=POSITION_A_MINUS, heuristic_similarity=0.82),
    )
    pp.commit()

    return pp


class TestDialecticalContextEmpty:
    """Tests for empty graph state."""

    @pytest.mark.asyncio
    async def test_empty_graph_returns_no_understanding(self):
        """Empty graph produces the 'no prior understanding' message."""
        sid = _new_sid()
        with scope(sid):
            concern = DialecticalContext()
            result = await concern.resolve()

            assert "No prior understanding" in result
            assert concern.report.ok is True

    @pytest.mark.asyncio
    async def test_empty_graph_report_summary(self):
        """Empty graph report summary says 'Empty graph'."""
        sid = _new_sid()
        with scope(sid):
            concern = DialecticalContext()
            await concern.resolve()

            assert concern.report.summary == "Empty graph"


class TestDialecticalContextWithPerspectives:
    """Tests for graph with perspectives."""

    @pytest.mark.asyncio
    async def test_includes_thesis_antithesis_text(self):
        """Output contains the thesis and antithesis text."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            concern = DialecticalContext()
            result = await concern.resolve()

            assert "Control" in result
            assert "Freedom" in result

    @pytest.mark.asyncio
    async def test_includes_aspect_texts(self):
        """Output contains T+, T-, A+, A- texts."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            concern = DialecticalContext()
            result = await concern.resolve()

            assert "Safety through structure" in result
            assert "Rigidity and micromanagement" in result
            assert "Autonomy builds responsibility" in result
            assert "Chaos without boundaries" in result

    @pytest.mark.asyncio
    async def test_includes_hash_links(self):
        """Output contains [[hash]] style links."""
        sid = _new_sid()
        with scope(sid):
            pp = _create_perspective_with_aspects()

            concern = DialecticalContext()
            result = await concern.resolve()

            assert f"[[{pp.short_hash}]]" in result

    @pytest.mark.asyncio
    async def test_includes_scores(self):
        """Output contains HS scores inline."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            concern = DialecticalContext()
            result = await concern.resolve()

            assert "HS=" in result

    @pytest.mark.asyncio
    async def test_includes_position_labels(self):
        """Output uses framework position labels (T+, A-, etc)."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            concern = DialecticalContext()
            result = await concern.resolve()

            assert "T+:" in result
            assert "T-:" in result
            assert "A+:" in result
            assert "A-:" in result

    @pytest.mark.asyncio
    async def test_unexplored_header_present(self):
        """Perspectives not in a nexus appear under 'Unexplored Tensions'."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            concern = DialecticalContext()
            result = await concern.resolve()

            assert "# Unexplored Tensions" in result

    @pytest.mark.asyncio
    async def test_report_summary_with_perspectives(self):
        """Report summary includes perspective count."""
        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            concern = DialecticalContext()
            await concern.resolve()

            assert "1 perspectives" in concern.report.summary
