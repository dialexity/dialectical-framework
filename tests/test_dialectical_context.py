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
    thesis_meaning: str = "test",
) -> Perspective:
    """Create a fully-populated Perspective for testing."""
    thesis = Statement(text=thesis_text, meaning=thesis_meaning)
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

            for position in ("T+", "T-", "A+", "A-"):
                assert f"{position} [[" in result, f"{position} line missing"

    @pytest.mark.asyncio
    async def test_aspect_lines_are_addressable(self):
        """Each T/A/aspect line carries its Statement hash.

        Load-bearing, not cosmetic: `record_decision` asks for the unchosen
        side's `+` aspect as the "accepted_cost" ground, and the later wobble
        re-audit reassures FROM that ground. With no aspect hash in the dump the
        only address in view is the Perspective's, so the model grounds on the
        tension instead of the cost and the re-audit has nothing specific to
        point back to — observed in tests/bench before this was rendered.
        """
        import re

        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()

            result = await DialecticalContext().resolve()

        hashes = {
            position: re.search(
                rf"^{re.escape(position)} \[\[([0-9a-f]+)\]\]:", result, re.M
            )
            for position in ("T", "A", "T+", "T-", "A+", "A-")
        }
        missing = [p for p, m in hashes.items() if m is None]
        assert not missing, f"positions rendered without a hash: {missing}"
        found = [m.group(1) for m in hashes.values() if m]
        assert len(set(found)) == len(found), (
            "two positions rendered the same hash — grounding one would be "
            f"ambiguous: {found}"
        )

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


class TestDialecticalContextScoped:
    """Nexus-scoped rendering: one nexus + outside-count line only."""

    @staticmethod
    def _seed_nexus_and_outside(sid: str) -> str:
        """One perspective in a nexus, one standalone. Returns nexus hash."""
        in_nexus = _create_perspective_with_aspects(
            thesis_text="Control", antithesis_text="Freedom"
        )
        _create_perspective_with_aspects(
            thesis_text="Speed", antithesis_text="Thoroughness"
        )
        nexus = Nexus(intent="scoped test exploration")
        nexus.save()
        nexus.commit()
        in_nexus.nexus.connect(nexus)
        return nexus.hash

    async def test_scoped_dump_contains_only_nexus_perspectives(self):
        sid = _new_sid()
        with scope(sid):
            nexus_hash = self._seed_nexus_and_outside(sid)

            dump = await DialecticalContext(nexus_hash=nexus_hash[:7]).resolve()

            assert "Control" in dump
            assert "Freedom" in dump
            # the standalone perspective must NOT be rendered
            assert "Speed" not in dump
            assert "Thoroughness" not in dump

    async def test_scoped_dump_has_outside_count_line(self):
        sid = _new_sid()
        with scope(sid):
            nexus_hash = self._seed_nexus_and_outside(sid)

            dump = await DialecticalContext(nexus_hash=nexus_hash[:7]).resolve()

            assert "1 other tension(s) exist outside this exploration" in dump

    async def test_scoped_dump_no_unexplored_section(self):
        sid = _new_sid()
        with scope(sid):
            nexus_hash = self._seed_nexus_and_outside(sid)

            dump = await DialecticalContext(nexus_hash=nexus_hash[:7]).resolve()

            assert "# Unexplored Tensions" not in dump

    async def test_scoped_raises_on_missing_nexus(self):
        sid = _new_sid()
        with scope(sid):
            with pytest.raises(ValueError, match="Nexus not found"):
                await DialecticalContext(nexus_hash="deadbeef").resolve()

    async def test_unscoped_unchanged(self):
        """Default construction still renders everything."""
        sid = _new_sid()
        with scope(sid):
            self._seed_nexus_and_outside(sid)

            dump = await DialecticalContext().resolve()

            assert "Control" in dump
            assert "Speed" in dump
            assert "# Unexplored Tensions" in dump


class TestDialecticalContextMultiNexus:
    """Multi-exploration dumps: per-nexus index disambiguation + machine-stated
    cross-nexus references (shared perspectives, shared taxonomy branch).
    The parallels themselves stay LLM interpretation — the dump only surfaces
    raw correspondences already persisted in the graph."""

    @staticmethod
    def _make_nexus(intent: str, *pps) -> Nexus:
        nexus = Nexus(intent=intent)
        nexus.save()
        nexus.commit()
        for pp in pps:
            pp.nexus.connect(nexus)
        return nexus

    async def test_single_nexus_has_no_multi_header(self):
        sid = _new_sid()
        with scope(sid):
            pp = _create_perspective_with_aspects()
            self._make_nexus("solo", pp)

            dump = await DialecticalContext().resolve()

            assert "Multiple explorations below" not in dump
            assert "Also woven into" not in dump

    async def test_multi_nexus_index_disambiguation_note(self):
        sid = _new_sid()
        with scope(sid):
            pp1 = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            pp2 = _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )
            self._make_nexus("first", pp1)
            self._make_nexus("second", pp2)

            dump = await DialecticalContext().resolve()

            assert "Multiple explorations below" in dump
            assert "per-exploration" in dump

    async def test_shared_perspective_annotated_in_both_nexuses(self):
        sid = _new_sid()
        with scope(sid):
            shared = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            other = _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )
            nx1 = self._make_nexus("first", shared)
            nx2 = self._make_nexus("second", shared, other)

            dump = await DialecticalContext().resolve()

            assert f"Also woven into Nexus [[{nx2.short_hash}]]" in dump
            assert f"Also woven into Nexus [[{nx1.short_hash}]]" in dump

    async def test_same_branch_across_nexuses_annotated(self):
        sid = _new_sid()
        with scope(sid):
            uri = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
            pp1 = _create_perspective_with_aspects(
                thesis_text="Control",
                antithesis_text="Freedom",
                thesis_meaning=uri,
            )
            pp2 = _create_perspective_with_aspects(
                thesis_text="Bonding",
                antithesis_text="Detachment",
                thesis_meaning=uri,
            )
            self._make_nexus("first", pp1)
            self._make_nexus("second", pp2)

            dump = await DialecticalContext().resolve()

            assert "Same opposition family (Integrity)" in dump

    async def test_different_branches_not_annotated(self):
        sid = _new_sid()
        with scope(sid):
            pp1 = _create_perspective_with_aspects(
                thesis_text="Control",
                antithesis_text="Freedom",
                thesis_meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            pp2 = _create_perspective_with_aspects(
                thesis_text="Speed",
                antithesis_text="Thoroughness",
                thesis_meaning="dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling",
            )
            self._make_nexus("first", pp1)
            self._make_nexus("second", pp2)

            dump = await DialecticalContext().resolve()

            assert "Same opposition family" not in dump

    async def test_standalone_echoing_explored_tension_annotated(self):
        """A fresh unexplored anchor sharing a branch with an explored tension
        gets a correspondence line in BOTH directions — this is exactly the
        counseling moment the cross-refs exist for (single nexus suffices)."""
        sid = _new_sid()
        with scope(sid):
            uri = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
            explored = _create_perspective_with_aspects(
                thesis_text="Control",
                antithesis_text="Freedom",
                thesis_meaning=uri,
            )
            nx = self._make_nexus("explored", explored)
            fresh = _create_perspective_with_aspects(
                thesis_text="Bonding",
                antithesis_text="Detachment",
                thesis_meaning=uri,
            )

            dump = await DialecticalContext().resolve()

            # No multi-exploration header for a single nexus
            assert "Multiple explorations below" not in dump
            # Standalone side points at the nexus member by index
            assert f"1 in [[{nx.short_hash}]]" in dump
            # Nexus side points back at the unexplored anchor by hash
            assert f"[[{fresh.short_hash}]] (unexplored)" in dump

    async def test_standalone_never_marked_also_woven(self):
        """Standalone perspectives are by definition not in any nexus — the
        'Also woven into' fact can only relate two nexus memberships."""
        sid = _new_sid()
        with scope(sid):
            pp = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            self._make_nexus("solo", pp)
            # No standalone perspectives at all: no cross-refs computed
            dump = await DialecticalContext().resolve()
            assert "Also woven into" not in dump

    async def test_standalone_different_branch_not_annotated(self):
        sid = _new_sid()
        with scope(sid):
            explored = _create_perspective_with_aspects(
                thesis_text="Control",
                antithesis_text="Freedom",
                thesis_meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion",
            )
            self._make_nexus("explored", explored)
            _create_perspective_with_aspects(
                thesis_text="Speed",
                antithesis_text="Thoroughness",
                thesis_meaning="dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling",
            )

            dump = await DialecticalContext().resolve()

            assert "Same opposition family" not in dump
