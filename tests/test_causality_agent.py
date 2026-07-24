"""
Tests for BuildWheels skill and estimator resolver.

Tests cover:
- BuildWheels: Creating Cycles + Wheels from Perspectives within a Nexus
- resolve_estimator: Mapping preset strings to CausalityEstimator instances
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.explorer.skills.build_wheels import (
    BuildWheels)
from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.concerns.causality.estimator_resolver import (
    resolve_estimator)
from dialectical_framework.concerns.causality.causality_estimator_balanced import (
    CausalityEstimatorBalanced)
from dialectical_framework.concerns.causality.causality_estimator_criteria import (
    CausalityEstimatorCriteria)
from dialectical_framework.concerns.causality.causality_estimator_desirable import (
    CausalityEstimatorDesirable)
from dialectical_framework.concerns.causality.causality_estimator_feasible import (
    CausalityEstimatorFeasible)
from dialectical_framework.concerns.causality.causality_estimator_realistic import (
    CausalityEstimatorRealistic)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture
def case_node():
    """Create a committed case for scoping."""
    bs = Case()
    bs.commit()
    return bs


def create_complete_perspective(index: int = 0) -> Perspective:
    """
    Create a complete Perspective with Polarity and all 6 positions filled.

    The modern Perspective structure requires a Polarity to hold T and A.
    """
    # Create T and A components
    t = Statement(
        text=f"Thesis {index}", meaning=f"thesis:test:{index}"
    )
    t.commit()
    a = Statement(
        text=f"Antithesis {index}", meaning=f"antithesis:test:{index}"
    )
    a.commit()

    # Create Polarity with T and A
    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    # Create PP and connect to Polarity
    pp = Perspective(intent="test")
    pp.save()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Create and connect aspects
    t_plus = Statement(
        text=f"T+ benefit {index}", meaning=f"thesis:positive:{index}"
    )
    t_plus.commit()
    t_minus = Statement(
        text=f"T- drawback {index}", meaning=f"thesis:negative:{index}"
    )
    t_minus.commit()
    a_plus = Statement(
        text=f"A+ benefit {index}", meaning=f"antithesis:positive:{index}"
    )
    a_plus.commit()
    a_minus = Statement(
        text=f"A- drawback {index}", meaning=f"antithesis:negative:{index}"
    )
    a_minus.commit()

    pp.t_plus.connect(
        t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9)
    )
    pp.t_minus.connect(
        t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9)
    )
    pp.a_plus.connect(
        a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9)
    )
    pp.a_minus.connect(
        a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9)
    )

    pp.commit()
    return pp


class TestResolveEstimator:
    """Tests for resolve_estimator — intent-to-estimator mapping."""

    def test_none_defaults_to_balanced(self):
        """None intent returns balanced estimator."""
        est = resolve_estimator(None)
        assert isinstance(est, CausalityEstimatorBalanced)

    def test_empty_string_defaults_to_balanced(self):
        """Empty string returns balanced estimator."""
        est = resolve_estimator("")
        assert isinstance(est, CausalityEstimatorBalanced)

    def test_preset_balanced(self):
        """preset:balanced returns balanced estimator."""
        est = resolve_estimator(CausalityPreset.BALANCED)
        assert isinstance(est, CausalityEstimatorBalanced)

    def test_preset_desirable(self):
        """preset:desirable returns desirable estimator."""
        est = resolve_estimator(CausalityPreset.DESIRABLE)
        assert isinstance(est, CausalityEstimatorDesirable)

    def test_preset_feasible(self):
        """preset:feasible returns feasible estimator."""
        est = resolve_estimator(CausalityPreset.FEASIBLE)
        assert isinstance(est, CausalityEstimatorFeasible)

    def test_preset_realistic(self):
        """preset:realistic returns realistic estimator."""
        est = resolve_estimator(CausalityPreset.REALISTIC)
        assert isinstance(est, CausalityEstimatorRealistic)

    def test_short_name_balanced(self):
        """Short name 'balanced' also works."""
        est = resolve_estimator("balanced")
        assert isinstance(est, CausalityEstimatorBalanced)

    def test_short_name_desirable(self):
        """Short name 'desirable' also works."""
        est = resolve_estimator("desirable")
        assert isinstance(est, CausalityEstimatorDesirable)

    def test_case_insensitive(self):
        """Preset matching is case-insensitive."""
        est = resolve_estimator("PRESET:REALISTIC")
        assert isinstance(est, CausalityEstimatorRealistic)

    def test_auto_preset_rejected(self):
        """preset:auto cannot be passed to resolve_estimator — caller must handle it."""
        with pytest.raises(ValueError, match="preset:auto must be resolved"):
            resolve_estimator(CausalityPreset.AUTO)

    def test_freeform_text_returns_criteria_estimator(self):
        """Non-preset text is treated as criteria — returns CausalityEstimatorCriteria."""
        est = resolve_estimator("depth and philosophical coherence")
        assert isinstance(est, CausalityEstimatorCriteria)
        assert est._criteria == "depth and philosophical coherence"

    def test_criteria_estimator_is_balanced_subclass(self):
        """CausalityEstimatorCriteria inherits from balanced estimator."""
        est = resolve_estimator("some custom criteria text")
        assert isinstance(est, CausalityEstimatorBalanced)
        assert isinstance(est, CausalityEstimatorCriteria)


class TestEstimatorPromptVariants:
    """The single-sequence prompt is one template; variants differ only in
    the lens phrase and probability instruction."""

    VARIANTS = [
        (
            CausalityEstimatorBalanced(),
            "considering realism, desirability, and feasibility",
            "weigh these together holistically into a single plausibility score",
        ),
        (
            CausalityEstimatorRealistic(),
            "for realism, i.e. what typically happens in natural systems",
            "regarding its realistic existence in natural/existing systems",
        ),
        (
            CausalityEstimatorDesirable(),
            "considering desirability, i.e. producing optimal outcomes and maximum results",
            "regarding how beneficial/optimal this sequence would be if implemented",
        ),
        (
            CausalityEstimatorFeasible(),
            "considering feasibility, i.e. best achievable with minimum resistance",
            "regarding how easily this sequence could be implemented given current constraints",
        ),
        (
            CausalityEstimatorCriteria(criteria="my custom criteria"),
            "with focus on the following assessment criteria: my custom criteria",
            "with emphasis on the assessment criteria above",
        ),
    ]

    @staticmethod
    def _render(estimator) -> str:
        messages = estimator.prompt_assess_single_sequence(sequence="X → Y → X...")
        assert len(messages) == 1
        return "".join(part.text for part in messages[0].content)

    def test_lens_and_probability_instruction_per_variant(self):
        for estimator, lens, instruction in self.VARIANTS:
            text = self._render(estimator)
            assert lens in text, f"{type(estimator).__name__} lens missing"
            assert instruction in text, f"{type(estimator).__name__} instruction missing"

    def test_shared_template_invariants(self):
        for estimator, _, _ in self.VARIANTS:
            text = self._render(estimator)
            assert text.count("X → Y → X...") == 1
            assert text.count("**exactly as provided**") == 1
            assert text.count("<instructions>") == 1
            assert text.count("<formatting>") == 1
            assert "explicit wording instead of technical aliases" in text


class TestAliasTranslation:
    """Technical aliases (batch-relative) must never survive into
    EstimationStructured text — they are translated to statement text."""

    def test_reasoning_aliases_become_statement_text(self):
        from types import SimpleNamespace

        from dialectical_framework.concerns.causality.causality_estimator_balanced import (
            CausalCycleDto, CausalCyclesDeckDto)

        s1 = Statement(text="Economic growth accelerates")
        s2 = Statement(text="Education access widens")
        structure = SimpleNamespace(hash="struct-hash-1")
        deck = CausalCyclesDeckDto(
            causal_cycles=[
                CausalCycleDto(
                    aliases=["C1_1", "C1_2"],
                    probability=0.7,
                    reasoning_explanation="C1_1 drives C1_2; C1_1-led systems persist.",
                    argumentation="Works when C1_2 is underfunded.",
                )
            ]
        )

        results = CausalityEstimatorBalanced._map_results_to_structures(
            [structure], deck, [[s1, s2]]
        )

        est = results["struct-hash-1"]
        assert "Economic growth accelerates" in est.reasoning
        assert "Education access widens" in est.reasoning
        assert "Education access widens" in est.argumentation
        for text in (est.reasoning, est.argumentation):
            assert "C1_1" not in text
            assert "C1_2" not in text


class TestStepCausationMapping:
    """Step DTOs (alias-identified) resolve to StepCausation (hash/text)."""

    @staticmethod
    def _fake_statements(n: int):
        from types import SimpleNamespace

        return [
            SimpleNamespace(hash=f"hash-{i}", text=f"Statement {i}") for i in range(n)
        ]

    def test_valid_aliases_resolve(self):
        from dialectical_framework.concerns.causality.causality_estimator_balanced import (
            StepCausationDto, _resolve_steps)

        seq = self._fake_statements(2)
        steps = _resolve_steps(
            [
                StepCausationDto(from_alias="C1_1", to_alias="C1_2", causation="a→b"),
                StepCausationDto(from_alias="C1_2", to_alias="C1_1", causation="b→a"),
            ],
            seq, 1, {},
        )
        assert [(s.source_hash, s.target_hash) for s in steps] == [
            ("hash-0", "hash-1"),
            ("hash-1", "hash-0"),
        ]
        assert steps[0].source_text == "Statement 0"

    def test_garbled_aliases_fall_back_positionally(self):
        from dialectical_framework.concerns.causality.causality_estimator_balanced import (
            StepCausationDto, _resolve_steps)

        seq = self._fake_statements(2)
        steps = _resolve_steps(
            [
                StepCausationDto(from_alias="??", to_alias="", causation="a→b"),
                StepCausationDto(from_alias="", to_alias="junk", causation="b→a"),
            ],
            seq, 1, {},
        )
        # count matches sequence length → positional wrap-around mapping
        assert [(s.source_hash, s.target_hash) for s in steps] == [
            ("hash-0", "hash-1"),
            ("hash-1", "hash-0"),
        ]

    def test_garbled_aliases_and_count_mismatch_drops_steps(self):
        from dialectical_framework.concerns.causality.causality_estimator_balanced import (
            StepCausationDto, _resolve_steps)

        seq = self._fake_statements(3)
        steps = _resolve_steps(
            [StepCausationDto(from_alias="??", to_alias="", causation="x")],
            seq, 1, {},
        )
        assert steps == []

    def test_empty_steps_noop(self):
        from dialectical_framework.concerns.causality.causality_estimator_balanced import \
            _resolve_steps

        assert _resolve_steps([], self._fake_statements(2), 1, {}) == []

    def test_causation_prose_aliases_translated(self):
        from dialectical_framework.concerns.causality.causality_estimator_balanced import (
            StepCausationDto, _resolve_steps)

        seq = self._fake_statements(2)
        steps = _resolve_steps(
            [
                StepCausationDto(
                    from_alias="C1_1", to_alias="C1_2", causation="C1_1 causes C1_2"
                ),
                StepCausationDto(from_alias="C1_2", to_alias="C1_1", causation="back"),
            ],
            seq, 1,
            {"C1_1": "Statement 0", "C1_2": "Statement 1"},
        )
        assert steps[0].causation == "Statement 0 causes Statement 1"


def _install_fake_estimator(monkeypatch, causation_fmt: str = "{src} enables {tgt}"):
    """Patch CausalityEstimatorBalanced.estimate to return per-step causations
    derived from each structure's statements (mock brain returns steps=[])."""
    from dialectical_framework.concerns.causality.causality_estimator import (
        EstimationStructured, StepCausation)

    async def fake_estimate(self, structures):
        structure_list = structures if isinstance(structures, list) else [structures]
        results = {}
        for s in structure_list:
            stmts = s.statements
            n = len(stmts)
            steps = [
                StepCausation(
                    source_hash=stmts[i].hash,
                    target_hash=stmts[(i + 1) % n].hash,
                    source_text=stmts[i].text,
                    target_text=stmts[(i + 1) % n].text,
                    causation=causation_fmt.format(
                        src=stmts[i].text, tgt=stmts[(i + 1) % n].text
                    ),
                )
                for i in range(n)
            ]
            results[s.hash] = EstimationStructured(
                probability=0.6,
                reasoning="test reasoning",
                argumentation="test contexts",
                steps=steps,
            )
        return results

    monkeypatch.setattr(CausalityEstimatorBalanced, "estimate", fake_estimate)


class TestPersistStepCausations:
    """Per-step causation rationales: wheel steps target edge Transitions,
    cycle steps target the Cycle with statement-text headers; re-estimation
    replaces prior rationales."""

    @staticmethod
    async def _build(case_node):
        """Build a 2-PP nexus; return (layer-2 cycle, one of its wheels)."""
        pp1 = create_complete_perspective(1)
        pp2 = create_complete_perspective(2)
        nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
        nexus.commit()
        agent = BuildWheels(
            nexus_hash=nexus.hash, perspective_hashes=[pp1.hash, pp2.hash]
        )
        result = await agent.resolve()
        cycle = next(c for c in result.new_cycles if c.perspective_count == 2)
        wheel = next(
            w
            for w in result.new_wheels
            if w.cycle.get() and w.cycle.get()[0].hash == cycle.hash
        )
        return cycle, wheel

    @pytest.mark.asyncio
    async def test_wheel_steps_attach_to_edges(self, case_node, monkeypatch):
        from dialectical_framework.concerns.causality_estimation import \
            CausalityEstimation

        with scope(case_node.sid):
            _, wheel = await self._build(case_node)
            _install_fake_estimator(monkeypatch)

            concern = CausalityEstimation()
            await concern.resolve([wheel])

            edges = wheel.edges
            assert len(edges) == 4  # 2-PP wheel: 4 edges
            for edge in edges:
                rationales = [r for r, _ in edge.rationales.all()]
                assert len(rationales) == 1
                src = edge.source.get()[0]
                tgt = edge.target.get()[0]
                assert rationales[0].text == f"{src.text} enables {tgt.text}"
                # verbose transition rendering surfaces the causation
                assert rationales[0].text in f"{edge:verbose}"

            # holistic rationale on the wheel itself (no step headers there)
            wheel_rationales = [r for r, _ in wheel.rationales.all()]
            assert len(wheel_rationales) == 1
            assert "test reasoning" in wheel_rationales[0].text
            assert "**Applicable contexts:** test contexts" in wheel_rationales[0].text

    @pytest.mark.asyncio
    async def test_cycle_steps_attach_to_cycle_with_headers(
        self, case_node, monkeypatch
    ):
        from dialectical_framework.concerns.causality_estimation import \
            CausalityEstimation

        with scope(case_node.sid):
            cycle, _ = await self._build(case_node)
            _install_fake_estimator(monkeypatch)

            concern = CausalityEstimation()
            await concern.resolve([cycle])

            rationales = [r for r, _ in cycle.rationales.all()]
            # 1 holistic + 2 per-step (2-PP cycle)
            assert len(rationales) == 3
            step_rationales = [r for r in rationales if r.text.startswith("**")]
            assert len(step_rationales) == 2
            stmts = cycle.statements
            for i, stmt in enumerate(stmts):
                nxt = stmts[(i + 1) % len(stmts)]
                expected = f"**{stmt.text} → {nxt.text}**\n{stmt.text} enables {nxt.text}"
                assert any(r.text == expected for r in step_rationales)
            # verbose cycle rendering surfaces them
            verbose = f"{cycle:verbose}"
            for r in step_rationales:
                assert r.text in verbose

    @pytest.mark.asyncio
    async def test_reestimation_replaces_rationales(self, case_node, monkeypatch):
        from dialectical_framework.concerns.causality_estimation import \
            CausalityEstimation

        with scope(case_node.sid):
            _, wheel = await self._build(case_node)

            _install_fake_estimator(monkeypatch, "{src} enables {tgt}")
            await CausalityEstimation().resolve([wheel])

            _install_fake_estimator(monkeypatch, "{src} reinforces {tgt}")
            concern = CausalityEstimation()
            await concern.resolve([wheel])

            for edge in wheel.edges:
                rationales = [r for r, _ in edge.rationales.all()]
                assert len(rationales) == 1  # replaced, not accumulated
                assert "reinforces" in rationales[0].text
            wheel_rationales = [r for r, _ in wheel.rationales.all()]
            assert len(wheel_rationales) == 1

            deleted = [
                e for e in concern.report.effects if e.effect_type == "node_deleted"
            ]
            created = [
                e for e in concern.report.effects if e.effect_type == "node_created"
            ]
            # round 1 left 1 holistic + 4 step rationales to delete
            assert len(deleted) == 5
            assert len(created) == 5


class TestNexusPresetIntentSeparation:
    """Tests for Nexus intent/preset separation."""

    def test_nexus_explicit_preset_and_intent(self):
        """Nexus with both preset and intent keeps them separate."""
        nexus = Nexus(
            sid="test-case-id",
            preset=CausalityPreset.REALISTIC,
            intent="deep meaning of love",
        )
        assert nexus.preset == CausalityPreset.REALISTIC
        assert nexus.intent == "deep meaning of love"

    def test_nexus_default_preset(self):
        """Nexus defaults to balanced preset."""
        nexus = Nexus(sid="test-case-id")
        assert nexus.preset == CausalityPreset.BALANCED
        assert nexus.intent is None

    def test_nexus_intent_is_freeform(self):
        """Intent is always free-form text, never migrated."""
        nexus = Nexus(sid="test-case-id", intent="deep meaning of love")
        assert nexus.preset == CausalityPreset.BALANCED
        assert nexus.intent == "deep meaning of love"


class TestBuildWheels:
    """Tests for BuildWheels.

    BuildWheels takes a Nexus and Perspective hashes, creates all
    Cycle/Wheel combinations, and optionally estimates them.
    """

    def test_build_wheels_has_correct_fields(self):
        """Test BuildWheels has expected fields."""
        agent = BuildWheels(
            nexus_hash="test-hash",
            perspective_hashes=["pp1", "pp2"],
        )

        assert agent.nexus_hash == "test-hash"
        assert agent.perspective_hashes == ["pp1", "pp2"]

    def test_build_wheels_default_values(self):
        """Test BuildWheels default field values."""
        agent = BuildWheels(nexus_hash="test-hash")

        assert agent.perspective_hashes == []

    @pytest.mark.asyncio
    async def test_build_wheels_invalid_nexus(self, case_node):
        """Test that invalid nexus hash returns error."""
        with scope(case_node.sid):
            agent = BuildWheels(
                nexus_hash="invalid-hash-that-does-not-exist",

            )

            result = await agent.resolve()
            assert result.new_cycles == []
            assert result.new_wheels == []
            assert agent.report.ok is False
            assert "Nexus not found" in agent.report.summary

    @pytest.mark.asyncio
    async def test_build_wheels_empty_nexus_no_pps(self, case_node):
        """Test BuildWheels with an empty Nexus and no PP hashes."""
        with scope(case_node.sid):
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,

            )

            result = await agent.resolve()
            assert result.new_cycles == []
            assert result.new_wheels == []
            assert "No Perspectives" in agent.report.summary

    @pytest.mark.asyncio
    async def test_build_wheels_single_pp(self, case_node):
        """Test BuildWheels with a single Perspective."""
        with scope(case_node.sid):
            pp = create_complete_perspective(0)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp.hash],

            )

            result = await agent.resolve()

            # Should create 1 cycle and 1 wheel
            assert len(result.new_cycles) >= 1
            assert len(result.new_wheels) >= 1

            # Layer-1 Cycle (single PP) should have no intent — causality requires 2+ PPs
            cycle = result.new_cycles[0]
            assert cycle.perspective_hashes == [pp.hash]
            assert cycle.intent is None

    @pytest.mark.asyncio
    async def test_build_wheels_multiple_pps(self, case_node):
        """Test BuildWheels with multiple Perspectives creates layers."""
        with scope(case_node.sid):
            pp1 = create_complete_perspective(1)
            pp2 = create_complete_perspective(2)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.REALISTIC)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp1.hash, pp2.hash],

            )

            result = await agent.resolve()

            # Should create cycles and wheels across layers
            assert len(result.new_cycles) >= 1
            assert len(result.new_wheels) >= 1

            # Layer-1 cycles (single PP) have no intent, layer 2+ have the preset
            for cycle in result.new_cycles:
                if cycle.perspective_count >= 2:
                    assert cycle.intent == CausalityPreset.REALISTIC
                else:
                    assert cycle.intent is None

    @pytest.mark.asyncio
    async def test_build_wheels_empty_hashes_uses_nexus_perspectives(self, case_node):
        """Test BuildWheels with empty PP hashes falls back to nexus members."""
        with scope(case_node.sid):
            pp = create_complete_perspective(0)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            # Add PP to Nexus manually
            pp.nexus.connect(nexus)

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[],  # Falls back to nexus perspectives
            )

            result = await agent.resolve()

            # With 1 PP in the nexus, should build a 1-PP wheel
            assert result.new_wheels != []
            assert result.new_cycles != []

    @pytest.mark.asyncio
    async def test_build_wheels_idempotent(self, case_node):
        """Test that BuildWheels is idempotent — no duplicates on re-run."""
        with scope(case_node.sid):
            pp = create_complete_perspective(0)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            # First call
            agent1 = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp.hash],

            )
            result1 = await agent1.resolve()
            assert len(result1.new_cycles) >= 1
            assert len(result1.new_wheels) >= 1

            # Second call with same inputs
            agent2 = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp.hash],

            )
            result2 = await agent2.resolve()

            # Nothing new created
            assert len(result2.new_cycles) == 0
            assert len(result2.new_wheels) == 0

    @pytest.mark.asyncio
    async def test_build_wheels_resolves_nexus_by_prefix(self, case_node):
        """Test that BuildWheels resolves Nexus by hash prefix."""
        with scope(case_node.sid):
            pp = create_complete_perspective(0)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            prefix = nexus.hash[:8]

            agent = BuildWheels(
                nexus_hash=prefix,
                perspective_hashes=[pp.hash],

            )

            result = await agent.resolve()
            assert result.nexus is not None
            assert result.nexus.hash == nexus.hash
            assert len(result.new_cycles) >= 1

    @pytest.mark.asyncio
    async def test_build_wheels_three_pp_layers(self, case_node):
        """Test BuildWheels with three PPs creates all layers."""
        with scope(case_node.sid):
            pp1 = create_complete_perspective(1)
            pp2 = create_complete_perspective(2)
            pp3 = create_complete_perspective(3)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp1.hash, pp2.hash, pp3.hash],

            )

            result = await agent.resolve()

            # 3 PPs should produce:
            # Layer 1: 3 cycles (one per PP), each with 1 wheel = 3 wheels
            # Layer 2: 3 cycles (C(3,2) pairs, (2-1)!=1 perm each), each with 2 wheels = 6 wheels
            # Layer 3: 2 cycles ((3-1)!=2 perms, no reversal skip), each with 4 wheels = 8 wheels
            assert len(result.new_cycles) == 8  # 3 + 3 + 2
            assert len(result.new_wheels) >= 8  # Multiple wheels per cycle

    @pytest.mark.asyncio
    async def test_build_wheels_graceful_when_all_combined(self, case_node):
        """Test BuildWheels is graceful when all structures already exist."""
        with scope(case_node.sid):
            pp = create_complete_perspective(0)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            # First call creates structures
            agent1 = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp.hash],

            )
            await agent1.resolve()

            # Second call with same PPs — everything exists
            agent2 = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp.hash],

            )
            result2 = await agent2.resolve()

            assert result2.new_cycles == []
            assert result2.new_wheels == []

            assert "already exist" in agent2.report.summary

    @pytest.mark.asyncio
    async def test_opposite_direction_cycles_three_pps(self, case_node):
        """Test that layer-3 cycles (3 PPs) are connected via OPPOSITE_DIRECTION."""
        with scope(case_node.sid):
            pp1 = create_complete_perspective(1)
            pp2 = create_complete_perspective(2)
            pp3 = create_complete_perspective(3)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp1.hash, pp2.hash, pp3.hash],
            )

            result = await agent.resolve()

            # Find layer-3 cycles (3 PPs)
            layer3_cycles = [
                c for c in result.new_cycles if c.perspective_count == 3
            ]
            assert len(layer3_cycles) == 2

            # They should be connected via opposite_direction
            cycle_a, cycle_b = layer3_cycles
            opposites = [c for c, _ in cycle_a.opposite_direction.all()]
            assert len(opposites) == 1
            assert opposites[0].hash == cycle_b.hash

    @pytest.mark.asyncio
    async def test_no_opposite_direction_for_single_pp(self, case_node):
        """Test that single-PP cycles have no OPPOSITE_DIRECTION."""
        with scope(case_node.sid):
            pp = create_complete_perspective(0)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp.hash],
            )

            result = await agent.resolve()

            cycle = result.new_cycles[0]
            opposites = list(cycle.opposite_direction.all())
            assert len(opposites) == 0

    @pytest.mark.asyncio
    async def test_no_opposite_direction_for_pair_cycles(self, case_node):
        """Test that pair cycles (2 PPs) have no OPPOSITE_DIRECTION (no distinct reversal)."""
        with scope(case_node.sid):
            pp1 = create_complete_perspective(1)
            pp2 = create_complete_perspective(2)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp1.hash, pp2.hash],
            )

            result = await agent.resolve()

            # Layer-2 cycles (2 PPs) — only 1 permutation, no reversal
            layer2_cycles = [
                c for c in result.new_cycles if c.perspective_count == 2
            ]
            for cycle in layer2_cycles:
                opposites = list(cycle.opposite_direction.all())
                assert len(opposites) == 0

    @pytest.mark.asyncio
    async def test_opposite_direction_wheels(self, case_node):
        """Test that opposite-direction wheels are detected and connected."""
        with scope(case_node.sid):
            pp1 = create_complete_perspective(1)
            pp2 = create_complete_perspective(2)
            nexus = Nexus(sid=case_node.sid, preset=CausalityPreset.BALANCED)
            nexus.commit()

            agent = BuildWheels(
                nexus_hash=nexus.hash,
                perspective_hashes=[pp1.hash, pp2.hash],
            )

            result = await agent.resolve()

            # Layer-2 wheels for 2 PPs: generate_compatible_sequences
            # produces 2 arrangements that are reverses of each other
            layer2_wheels = [
                w for w in result.new_wheels
                if w.polarity_count == 2
            ]

            # At least 2 wheels for the pair
            assert len(layer2_wheels) >= 2

            # Find a wheel with an opposite_direction connection
            has_opposite = False
            for wheel in layer2_wheels:
                opposites = list(wheel.opposite_direction.all())
                if opposites:
                    has_opposite = True
                    break
            assert has_opposite, "Expected at least one pair of opposite-direction wheels"
