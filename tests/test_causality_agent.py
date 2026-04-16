"""
Tests for BuildWheels skill and sequencer resolver.

Tests cover:
- BuildWheels: Creating Cycles + Wheels from WisdomUnits within a Nexus
- resolve_sequencer: Mapping preset strings to CausalitySequencer instances
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.explorer.skills.build_wheels import (
    BuildWheels, BuildWheelsResult)
from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.features.causality.sequencer_resolver import (
    resolve_sequencer)
from dialectical_framework.features.causality.causality_sequencer_balanced import (
    CausalitySequencerBalanced)
from dialectical_framework.features.causality.causality_sequencer_criteria import (
    CausalitySequencerCriteria)
from dialectical_framework.features.causality.causality_sequencer_desirable import (
    CausalitySequencerDesirable)
from dialectical_framework.features.causality.causality_sequencer_feasible import (
    CausalitySequencerFeasible)
from dialectical_framework.features.causality.causality_sequencer_realistic import (
    CausalitySequencerRealistic)
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture
def brainstorm():
    """Create a committed brainstorm for scoping."""
    bs = Brainstorm()
    bs.commit()
    return bs


def create_complete_wisdom_unit(index: int = 0) -> WisdomUnit:
    """
    Create a complete WisdomUnit with Polarity and all 6 positions filled.

    The modern WisdomUnit structure requires a Polarity to hold T and A.
    """
    # Create T and A components
    t = DialecticalComponent(
        statement=f"Thesis {index}", meaning=f"thesis:test:{index}"
    )
    t.commit()
    a = DialecticalComponent(
        statement=f"Antithesis {index}", meaning=f"antithesis:test:{index}"
    )
    a.commit()

    # Create Polarity with T and A
    polarity = Polarity(intent="test")
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    # Create WU and connect to Polarity
    wu = WisdomUnit(intent="test")
    wu.save()
    wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Create and connect poles
    t_plus = DialecticalComponent(
        statement=f"T+ benefit {index}", meaning=f"thesis:positive:{index}"
    )
    t_plus.commit()
    t_minus = DialecticalComponent(
        statement=f"T- drawback {index}", meaning=f"thesis:negative:{index}"
    )
    t_minus.commit()
    a_plus = DialecticalComponent(
        statement=f"A+ benefit {index}", meaning=f"antithesis:positive:{index}"
    )
    a_plus.commit()
    a_minus = DialecticalComponent(
        statement=f"A- drawback {index}", meaning=f"antithesis:negative:{index}"
    )
    a_minus.commit()

    wu.t_plus.connect(
        t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9)
    )
    wu.t_minus.connect(
        t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9)
    )
    wu.a_plus.connect(
        a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9)
    )
    wu.a_minus.connect(
        a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9)
    )

    wu.commit()
    return wu


class TestResolveSequencer:
    """Tests for resolve_sequencer — intent-to-sequencer mapping."""

    def test_none_defaults_to_balanced(self):
        """None intent returns balanced sequencer."""
        seq = resolve_sequencer(None)
        assert isinstance(seq, CausalitySequencerBalanced)

    def test_empty_string_defaults_to_balanced(self):
        """Empty string returns balanced sequencer."""
        seq = resolve_sequencer("")
        assert isinstance(seq, CausalitySequencerBalanced)

    def test_preset_balanced(self):
        """preset:balanced returns balanced sequencer."""
        seq = resolve_sequencer(CausalityPreset.BALANCED)
        assert isinstance(seq, CausalitySequencerBalanced)

    def test_preset_desirable(self):
        """preset:desirable returns desirable sequencer."""
        seq = resolve_sequencer(CausalityPreset.DESIRABLE)
        assert isinstance(seq, CausalitySequencerDesirable)

    def test_preset_feasible(self):
        """preset:feasible returns feasible sequencer."""
        seq = resolve_sequencer(CausalityPreset.FEASIBLE)
        assert isinstance(seq, CausalitySequencerFeasible)

    def test_preset_realistic(self):
        """preset:realistic returns realistic sequencer."""
        seq = resolve_sequencer(CausalityPreset.REALISTIC)
        assert isinstance(seq, CausalitySequencerRealistic)

    def test_short_name_balanced(self):
        """Short name 'balanced' also works."""
        seq = resolve_sequencer("balanced")
        assert isinstance(seq, CausalitySequencerBalanced)

    def test_short_name_desirable(self):
        """Short name 'desirable' also works."""
        seq = resolve_sequencer("desirable")
        assert isinstance(seq, CausalitySequencerDesirable)

    def test_case_insensitive(self):
        """Preset matching is case-insensitive."""
        seq = resolve_sequencer("PRESET:REALISTIC")
        assert isinstance(seq, CausalitySequencerRealistic)

    def test_auto_preset_rejected(self):
        """preset:auto cannot be passed to resolve_sequencer — caller must handle it."""
        with pytest.raises(ValueError, match="preset:auto must be resolved"):
            resolve_sequencer(CausalityPreset.AUTO)

    def test_freeform_text_returns_criteria_sequencer(self):
        """Non-preset text is treated as criteria — returns CausalitySequencerCriteria."""
        seq = resolve_sequencer("depth and philosophical coherence")
        assert isinstance(seq, CausalitySequencerCriteria)
        assert seq._criteria == "depth and philosophical coherence"

    def test_criteria_sequencer_is_balanced_subclass(self):
        """CausalitySequencerCriteria inherits from balanced sequencer."""
        seq = resolve_sequencer("some custom criteria text")
        assert isinstance(seq, CausalitySequencerBalanced)
        assert isinstance(seq, CausalitySequencerCriteria)


class TestNexusPresetIntentSeparation:
    """Tests for Nexus intent/preset separation."""

    def test_nexus_explicit_preset_and_intent(self):
        """Nexus with both preset and intent keeps them separate."""
        nexus = Nexus(
            sid="test-sid",
            preset=CausalityPreset.REALISTIC,
            intent="deep meaning of love",
        )
        assert nexus.preset == CausalityPreset.REALISTIC
        assert nexus.intent == "deep meaning of love"

    def test_nexus_default_preset(self):
        """Nexus defaults to balanced preset."""
        nexus = Nexus(sid="test-sid")
        assert nexus.preset == CausalityPreset.BALANCED
        assert nexus.intent is None

    def test_nexus_intent_is_freeform(self):
        """Intent is always free-form text, never migrated."""
        nexus = Nexus(sid="test-sid", intent="deep meaning of love")
        assert nexus.preset == CausalityPreset.BALANCED
        assert nexus.intent == "deep meaning of love"


class TestBuildWheels:
    """Tests for BuildWheels.

    BuildWheels takes a Nexus and WisdomUnit hashes, creates all
    Cycle/Wheel combinations, and optionally estimates them.
    """

    def test_build_wheels_has_correct_fields(self):
        """Test BuildWheels has expected fields."""
        agent = BuildWheels(
            nexus_hash="test-hash",
            wisdom_unit_hashes=["wu1", "wu2"],
        )

        assert agent.nexus_hash == "test-hash"
        assert agent.wisdom_unit_hashes == ["wu1", "wu2"]
        assert agent.estimate is True

    def test_build_wheels_default_values(self):
        """Test BuildWheels default field values."""
        agent = BuildWheels(nexus_hash="test-hash")

        assert agent.wisdom_unit_hashes == []
        assert agent.estimate is True

    @pytest.mark.asyncio
    async def test_build_wheels_invalid_nexus(self, brainstorm):
        """Test that invalid nexus hash returns error."""
        with scope(brainstorm.sid):
            agent = BuildWheels(
                nexus_hash="invalid-hash-that-does-not-exist",

            )

            result = await agent.execute()
            assert result.new_cycles == []
            assert result.new_wheels == []
            assert agent.report.ok is False
            assert "Nexus not found" in agent.report.summary

    @pytest.mark.asyncio
    async def test_build_wheels_empty_nexus_no_wus(self, brainstorm):
        """Test BuildWheels with an empty Nexus and no WU hashes."""
        with scope(brainstorm.sid):
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,

            )

            result = await agent.execute()
            assert result.new_cycles == []
            assert result.new_wheels == []
            assert "No WisdomUnits" in agent.report.summary

    @pytest.mark.asyncio
    async def test_build_wheels_single_wu(self, brainstorm):
        """Test BuildWheels with a single WisdomUnit."""
        with scope(brainstorm.sid):
            wu = create_complete_wisdom_unit(0)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu.hash],

            )

            result = await agent.execute()

            # Should create 1 cycle and 1 wheel
            assert len(result.new_cycles) >= 1
            assert len(result.new_wheels) >= 1

            # Layer-1 Cycle (single WU) should have no intent — causality requires 2+ WUs
            cycle = result.new_cycles[0]
            assert cycle.wisdom_unit_hashes == [wu.hash]
            assert cycle.intent is None

    @pytest.mark.asyncio
    async def test_build_wheels_multiple_wus(self, brainstorm):
        """Test BuildWheels with multiple WisdomUnits creates layers."""
        with scope(brainstorm.sid):
            wu1 = create_complete_wisdom_unit(1)
            wu2 = create_complete_wisdom_unit(2)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.REALISTIC)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu1.hash, wu2.hash],

            )

            result = await agent.execute()

            # Should create cycles and wheels across layers
            assert len(result.new_cycles) >= 1
            assert len(result.new_wheels) >= 1

            # Layer-1 cycles (single WU) have no intent, layer 2+ have the preset
            for cycle in result.new_cycles:
                if cycle.wisdom_unit_count >= 2:
                    assert cycle.intent == CausalityPreset.REALISTIC
                else:
                    assert cycle.intent is None

    @pytest.mark.asyncio
    async def test_build_wheels_empty_hashes_does_nothing(self, brainstorm):
        """Test BuildWheels with empty WU hashes does nothing."""
        with scope(brainstorm.sid):
            wu = create_complete_wisdom_unit(0)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            # Add WU to Nexus manually
            wu.nexus.connect(nexus)

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[],  # Empty — does nothing

            )

            result = await agent.execute()

            assert result.new_cycles == []
            assert result.new_wheels == []
            assert "No WisdomUnits" in agent.report.summary

    @pytest.mark.asyncio
    async def test_build_wheels_idempotent(self, brainstorm):
        """Test that BuildWheels is idempotent — no duplicates on re-run."""
        with scope(brainstorm.sid):
            wu = create_complete_wisdom_unit(0)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            # First call
            agent1 = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu.hash],

            )
            result1 = await agent1.execute()
            assert len(result1.new_cycles) >= 1
            assert len(result1.new_wheels) >= 1

            # Second call with same inputs
            agent2 = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu.hash],

            )
            result2 = await agent2.execute()

            # Nothing new created
            assert len(result2.new_cycles) == 0
            assert len(result2.new_wheels) == 0

    @pytest.mark.asyncio
    async def test_build_wheels_resolves_nexus_by_prefix(self, brainstorm):
        """Test that BuildWheels resolves Nexus by hash prefix."""
        with scope(brainstorm.sid):
            wu = create_complete_wisdom_unit(0)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            prefix = nexus.hash[:8]

            agent = BuildWheels(
                nexus_hash=prefix,
                wisdom_unit_hashes=[wu.hash],

            )

            result = await agent.execute()
            assert result.nexus is not None
            assert result.nexus.hash == nexus.hash
            assert len(result.new_cycles) >= 1

    @pytest.mark.asyncio
    async def test_build_wheels_three_wu_layers(self, brainstorm):
        """Test BuildWheels with three WUs creates all layers."""
        with scope(brainstorm.sid):
            wu1 = create_complete_wisdom_unit(1)
            wu2 = create_complete_wisdom_unit(2)
            wu3 = create_complete_wisdom_unit(3)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu1.hash, wu2.hash, wu3.hash],

            )

            result = await agent.execute()

            # 3 WUs should produce:
            # Layer 1: 3 cycles (one per WU) + 3 wheels
            # Layer 2: 3 cycles (C(3,2) pairs) + 3 wheels
            # Layer 3: 1 cycle (all 3 WUs) + 1 wheel
            assert len(result.new_cycles) == 7  # 3 + 3 + 1
            assert len(result.new_wheels) >= 7  # At least one wheel per cycle

    @pytest.mark.asyncio
    async def test_build_wheels_graceful_when_all_combined(self, brainstorm):
        """Test BuildWheels is graceful when all structures already exist."""
        with scope(brainstorm.sid):
            wu = create_complete_wisdom_unit(0)
            nexus = Nexus(sid=brainstorm.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            # First call creates structures
            agent1 = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu.hash],

            )
            await agent1.execute()

            # Second call with same WUs — everything exists
            agent2 = BuildWheels(
                nexus_hash=nexus.hash,
                wisdom_unit_hashes=[wu.hash],

            )
            result2 = await agent2.execute()

            assert result2.new_cycles == []
            assert result2.new_wheels == []

            assert "already exist" in agent2.report.summary
