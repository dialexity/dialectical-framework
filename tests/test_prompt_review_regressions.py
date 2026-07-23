"""
Mechanical regression tests for the prompt-review pass.

Each test locks in one fix from the prompt-consistency review so it cannot
silently regress. These are pure string/logic assertions over prompt constants
and scoring helpers — no LLM, no graph DB — so they run in the default suite.

Grouped by the review theme they guard:
- S1: single aspect ontology (cross-enhancement + diagonal contradiction)
- S2: single HS scale, single complementarity scale (shared constants)
- S3: complementarity 0.0 anchor is not "contradicts"
- H1: transformation worked example matches the formal spec
- H4: control-statements coherence status uses both-scores rule
- H5: apex sweet-spot numbers match the computed constants
- S4: transition length is settings-driven, no hardcoded "1-15 words"
- Agent-prompt correctness (H2/H3/H6/S5) and Task 6/7 polish

Run: poetry run pytest tests/test_prompt_review_regressions.py -v
"""

from __future__ import annotations

import inspect

import pytest


# DB-free: override the autouse graph fixtures (per CLAUDE.md DB-free convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


# --- S1 / S2 / S3: shared scoring vocabulary ---------------------------------


class TestSharedScoringConstants:
    def test_aspect_definitions_carry_cross_enhancement_and_diagonal(self):
        """S1: the canonical aspect defs name both distinguishing properties."""
        from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS

        # cross-enhancement: a "+" aspect strengthens the OTHER side
        assert "also strengthens what A offers" in ASPECT_DEFINITIONS
        assert "also strengthens what T offers" in ASPECT_DEFINITIONS
        # diagonal contradiction for all four aspects
        for diag in ("Contradicts A-.", "Contradicts T-.", "Contradicts A+.", "Contradicts T+."):
            assert diag in ASPECT_DEFINITIONS, f"missing diagonal: {diag}"
        # the drift phrasing must not creep back
        assert "benefits, strengths" not in ASPECT_DEFINITIONS
        assert "risks, downsides, shadow" not in ASPECT_DEFINITIONS

    def test_hs_scale_is_descending_six_band_with_gate(self):
        """S2: one HS scale — descending 6-band, valid-above-0.1 gate."""
        from dialectical_framework.concerns.scoring_scales import HS_SCALE

        for band in ("0.9-1.0", "0.7-0.9", "0.5-0.7", "0.3-0.5", "0.1-0.3", "0.0-0.1"):
            assert band in HS_SCALE, f"missing band: {band}"
        # descending: top band appears before bottom band
        assert HS_SCALE.index("0.9-1.0") < HS_SCALE.index("0.0-0.1")
        assert "above 0.1 is valid" in HS_SCALE

    def test_complementarity_zero_anchor_is_not_contradiction(self):
        """S3: 0.0 = contributes nothing, NOT "undermines or contradicts"."""
        from dialectical_framework.concerns.scoring_scales import COMPLEMENTARITY_SCALE

        assert "Actively undermines or contradicts" not in COMPLEMENTARITY_SCALE
        assert "contributes nothing to its constructive development" in COMPLEMENTARITY_SCALE
        # the explicit trap-avoidance line
        assert "not a complementarity defect" in COMPLEMENTARITY_SCALE

    @pytest.mark.parametrize(
        "module_name",
        [
            "dialectical_framework.concerns.aspect_generation",
            "dialectical_framework.concerns.aspect_classification",
        ],
    )
    def test_generator_and_classifier_share_the_constants(self, module_name):
        """S1/S2/S3: both files import the shared constants, none re-type a scale."""
        import importlib

        mod = importlib.import_module(module_name)
        src = inspect.getsource(mod)
        assert "from dialectical_framework.concerns.scoring_scales import" in src
        # no locally re-typed HS bands (the old ascending-collapsed generator scale)
        assert "0.0-0.3: Unrelated or tangentially" not in src
        # no locally re-typed drift ontology
        assert "benefits, strengths" not in src


# --- H1: transformation worked example ---------------------------------------


class TestTransformationExample:
    def test_example_directions_match_formal_spec(self):
        """H1: the four example directions match docs/graph.md + the prompt's own defs."""
        from dialectical_framework.concerns.transformation_generation import SYSTEM_PROMPT as P

        assert "Ac+ (T- → A+, Enmeshment → Autonomy)" in P
        assert "Re+ (A- → T+, Alienation → Bonding)" in P
        assert "Ac- (T+ → A-, Bonding → Alienation)" in P
        assert "Re- (A+ → T-, Autonomy → Enmeshment)" in P

    def test_ac_plus_and_re_plus_do_not_both_target_autonomy(self):
        """H1: the mirror collision (both ending at Autonomy) must not return."""
        from dialectical_framework.concerns.transformation_generation import SYSTEM_PROMPT as P

        assert "Alienation → Autonomy" not in P


# --- H4: control-statements coherence ----------------------------------------


class TestControlStatementsCoherence:
    def test_status_uses_both_scores_not_average(self):
        """H4: a split verdict (0.9/0.6) is NOT coherent; rationale status agrees."""
        from dialectical_framework.graph.nodes.estimation import (
            ConceptualCoherenceEstimation,
        )

        split = ConceptualCoherenceEstimation(
            value=0.75,
            t_plus_without_a_plus_yields_t_minus=0.9,
            a_plus_without_t_plus_yields_a_minus=0.6,
        )
        assert split.is_coherent is False  # 0.6 < 0.7 fails despite avg 0.75

        both_pass = ConceptualCoherenceEstimation(
            value=0.85,
            t_plus_without_a_plus_yields_t_minus=0.8,
            a_plus_without_t_plus_yields_a_minus=0.9,
        )
        assert both_pass.is_coherent is True

    def test_no_average_based_gate_in_resolve(self):
        """H4: resolve() derives status from the estimation, not the average."""
        from dialectical_framework.concerns import control_statements_check as m

        src = inspect.getsource(m.ControlStatementsCheck.resolve)
        assert "is_coherent = avg_score >=" not in src
        assert "estimation.is_coherent" in src


# --- H5: apex sweet-spot numbers ---------------------------------------------


class TestApexSweetSpots:
    def test_field_descriptions_match_computed_bounds(self):
        """H5: Field descriptions render the computed sweet spots, not stale numbers."""
        from dialectical_framework.concerns.positive_ac_re_apex_derivation import (
            ApexPairDto,
        )

        re_desc = ApexPairDto.model_fields["re_plus_apex"].description
        ac_desc = ApexPairDto.model_fields["ac_plus_apex"].description
        assert "proactiveness 0.15-0.35" in re_desc
        assert "proactiveness 0.55-0.75" in ac_desc

    def test_no_stale_numbers_in_module(self):
        """H5: the stale 0.2-0.3 / 0.5-0.7 proactiveness ranges are gone."""
        from dialectical_framework.concerns import positive_ac_re_apex_derivation as m

        src = inspect.getsource(m)
        assert "0.2-0.3" not in src
        assert "(proactiveness 0.5-0.7" not in src


# --- S4: transition length is settings-driven --------------------------------


class TestTransitionLength:
    def test_setting_exists_with_env_override(self, monkeypatch):
        from dialectical_framework.settings import Settings

        monkeypatch.setenv("DIALEXITY_DEFAULT_MODEL", "bedrock/x")
        monkeypatch.delenv("DIALEXITY_DEFAULT_TRANSITION_LENGTH", raising=False)
        assert Settings.from_env().transition_length == 15
        monkeypatch.setenv("DIALEXITY_DEFAULT_TRANSITION_LENGTH", "12")
        assert Settings.from_env().transition_length == 12

    @pytest.mark.parametrize(
        "module_name",
        [
            "dialectical_framework.concerns.transformation_generation",
            "dialectical_framework.concerns.action_extraction",
            "dialectical_framework.concerns.positive_ac_re_apex_derivation",
        ],
    )
    def test_no_hardcoded_word_limit(self, module_name):
        import importlib

        mod = importlib.import_module(module_name)
        assert "1-15 words" not in inspect.getsource(mod)


# --- Agent-prompt correctness (H2 / H3 / H6 / S5) and polish ------------------


class TestAgentPrompts:
    def test_explorer_no_dead_tool_and_true_1pp_claim(self):
        """H2 + H3: no present_analysis ref; 1-PP claim matches the code."""
        from dialectical_framework.agents.explorer.system_prompts import system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="t")
        assert "present_analysis" not in p  # H3
        assert "only one position" not in p  # H2 false claim gone
        assert "single perspective builds one self-referential wheel" in p

    def test_apps_wheel_definition_uses_spiral_not_blindspot(self):
        """H6: Wheel def routes exaggeration -> constructive strength, no blindspot."""
        from dialectical_framework.agents.apps import DEFAULT_APP

        idx = DEFAULT_APP.find("Within a Nexus, Wheels")
        snippet = DEFAULT_APP[idx : idx + 260]
        assert "blindspot" not in snippet
        assert "constructive strength" in snippet

    def test_advanced_app_override_resolves_translation_table_conflict(self):
        """S5: override names both sections and supersedes the CRITICAL directive."""
        from dialectical_framework.agents.apps import ADVANCED_APP

        assert "overrides Contextual Vocabulary and Presentation Defaults" in ADVANCED_APP
        assert "does not apply here" in ADVANCED_APP

    def test_no_tetrades_misspelling(self):
        from dialectical_framework.agents.apps import DEFAULT_APP
        from dialectical_framework.agents.analyst.system_prompts import SYSTEM_PROMPT

        assert "tetrades" not in DEFAULT_APP
        assert "tetrades" not in SYSTEM_PROMPT

    def test_causality_alias_example_matches_real_format(self):
        """Task 6: the alias example teaches C{seq}_{comp}, not C1,C2,C3."""
        from dialectical_framework.concerns.causality import (
            causality_estimator_balanced as m,
        )

        src = inspect.getsource(m)
        assert "C1_1, C1_2, C1_3" in src
        assert "e.g. C1, C2, C3" not in src

    def test_advisor_has_discard_and_prompt_documents_it(self):
        """9a/9b: discard is wired into the Advisor and its prompt documents it,
        with the single consolidated tool section (no leftover duplicate)."""
        from dialectical_framework.agents.advisor.advisor import _build_tools
        from dialectical_framework.agents.advisor.system_prompts import SYSTEM_PROMPT

        names = {getattr(t, "__name__", None) for t in _build_tools()}
        assert "discard" in names
        assert "## When to Use Tools" not in SYSTEM_PROMPT  # sections consolidated
        assert SYSTEM_PROMPT.count("## Internal Tools") == 1
        # every wired tool is documented in the single section
        for name in names:
            assert f"`{name}`" in SYSTEM_PROMPT
        # reject-framing now discards rather than merely "stops drawing on"
        assert "silently `discard` it" in SYSTEM_PROMPT


# --- Empty-ingest fallback: extraction miss must route to anchor -------------


class TestEmptyIngestFallback:
    """When ingest surfaces no tensions, the advisor must fall back to anchor
    rather than reverting to unstructured discussion, and the pipeline must
    say so actionably instead of reporting a bare success."""

    def test_advisor_prompt_documents_empty_ingest_fallback(self):
        """The Sequence has an explicit branch for a tool that surfaces no
        tensions, pointing at `anchor` (not discussion)."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "surfaces no tensions" in SYSTEM_PROMPT
        # the fallback names anchor as the recovery move
        idx = SYSTEM_PROMPT.find("surfaces no tensions")
        window = SYSTEM_PROMPT[idx : idx + 400]
        assert "`anchor`" in window

    def test_advisor_prompt_disambiguates_ingest_vs_anchor(self):
        """ingest/anchor selection is no longer an ambiguous overlap: an
        explicit position/either-or routes to anchor."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        idx = SYSTEM_PROMPT.find("- `ingest`")
        ingest_section = SYSTEM_PROMPT[idx : idx + 700]
        assert "prefer `anchor`" in ingest_section

    def test_pipeline_empty_summary_is_actionable(self):
        """AnalysisPipeline's no-thesis path suggests anchoring instead of the
        old bare 'No theses found'."""
        from dialectical_framework.agents.analyst import analyst as m

        src = inspect.getsource(m.AnalysisPipeline.resolve)
        assert "No theses found" not in src
        assert "No tensions extracted" in src
        assert "Anchor an" in src

    def test_thesis_extraction_has_gate_rejection_safety_net(self):
        """A step-2 gate that rejects every item falls back to raw content
        items rather than returning zero candidates."""
        from dialectical_framework.concerns import thesis_extraction as m

        src = inspect.getsource(m.ThesisExtraction.resolve)
        # fallback keys off content_items surviving when candidates are empty
        assert "not all_candidates and content_items" in src


# --- Task 10: Elemental as a full peer taxonomy ------------------------------


class _FakeStatement:
    """Minimal stand-in for the static lookups (touch only .meaning/.is_simple)."""

    def __init__(self, meaning: str) -> None:
        self.meaning = meaning
        self.is_simple = False


class TestElementalTaxonomy:
    _URI = "dx://taxonomy/Elements(General.v1)/Viability/Fire/Activation"

    def test_dict_matches_table_s2(self):
        """The ELEMENTAL_TAXONOMY dict transcribes Table S-2 (Fire row + Apex)."""
        from dialectical_framework.concerns.statement_classification import (
            ELEMENTAL_TAXONOMY,
        )
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A, POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T,
            POSITION_T_MINUS, POSITION_T_PLUS,
        )

        for element in ("Apex", "Fire", "Earth", "Air", "Water"):
            assert element in ELEMENTAL_TAXONOMY
        fire = ELEMENTAL_TAXONOMY["Fire"]
        assert fire[POSITION_T] == "Activation"
        assert fire[POSITION_A] == "Inhibition"
        assert fire[POSITION_T_PLUS] == "Motivation"
        assert fire[POSITION_T_MINUS] == "Impulsivity"
        assert fire[POSITION_A_PLUS] == "Regulation"
        assert fire[POSITION_A_MINUS] == "Repression"

    def test_parse_extracts_elemental_branch_not_none(self):
        """The old trap: an elemental URI parsed to branch=None. Now it doesn't."""
        from dialectical_framework.concerns.statement_classification import (
            parse_meaning_uri,
        )

        domain, category, branch, leaf = parse_meaning_uri(self._URI)
        assert (domain, category, branch, leaf) == (
            "General",
            "Viability",
            "Fire",
            "Activation",
        )

    def test_family_and_taxonomy_dispatch(self):
        from dialectical_framework.concerns.statement_classification import (
            ELEMENTAL_TAXONOMY, SYSTEMIC_TAXONOMY, _family_for_meaning,
            _taxonomy_for_meaning,
        )

        assert _family_for_meaning(self._URI) == "Elements"
        assert _taxonomy_for_meaning(self._URI) is ELEMENTAL_TAXONOMY
        # default / systemic
        assert _family_for_meaning(None) == "System"
        assert _taxonomy_for_meaning("dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling") is SYSTEMIC_TAXONOMY

    def test_antithesis_stays_elemental(self):
        """Regression: elemental thesis must NOT fall back to systemic Fidelity."""
        from dialectical_framework.concerns.statement_classification import (
            StatementClassification as SC,
        )

        result = SC.lookup_antithesis_meaning(_FakeStatement(self._URI))
        assert result == "dx://taxonomy/Elements(General.v1)/Viability/Fire/Inhibition"
        assert "System(" not in result  # the corruption we fixed
        assert "Fidelity" not in result

    def test_all_aspects_stay_elemental(self):
        """Regression: aspects must NOT collapse to the systemic Apex column."""
        from dialectical_framework.concerns.statement_classification import (
            StatementClassification as SC,
        )

        parent = _FakeStatement(self._URI)
        expected = {"T+": "Motivation", "T-": "Impulsivity", "A+": "Regulation", "A-": "Repression"}
        for pos, apex in expected.items():
            meaning = SC.lookup_aspect_meaning(parent, pos)
            assert meaning == f"dx://taxonomy/Elements(General.v1)/Viability/Fire/{apex}"
            # apex concept name drives HS scoring — must be the elemental one,
            # not the systemic Apex fallback (Coherence/Rigid fusion/...)
            assert SC.lookup_aspect_apex(parent, pos) == apex

    def test_dedup_prefix_preserves_family(self):
        from dialectical_framework.concerns.statement_deduplication import (
            _extract_meaning_prefix,
        )

        assert (
            _extract_meaning_prefix(self._URI)
            == "dx://taxonomy/Elements(General.v1)/Viability/Fire"
        )

    def test_systemic_path_unchanged(self):
        """Systemic lookups must be untouched by the elemental dispatch."""
        from dialectical_framework.concerns.statement_classification import (
            StatementClassification as SC,
        )
        from dialectical_framework.concerns.statement_deduplication import (
            _extract_meaning_prefix,
        )

        uri = "dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Simulation"
        assert SC.lookup_aspect_apex(_FakeStatement(uri), "T+") == "Accuracy"
        assert (
            _extract_meaning_prefix(uri)
            == "dx://taxonomy/System(Engineering.v1)/Viability/Fidelity"
        )

    def test_build_meaning_uri_emits_uniform_elemental_form(self):
        """_build_meaning_uri emits the family-uniform Elements(General.v1) form."""
        from dialectical_framework.concerns.statement_classification import (
            StatementClassification, TaxonomyLocationDto,
        )

        loc = TaxonomyLocationDto(
            taxonomy_type="elemental", domain="General", branch="Fire",
            leaf="Activation", reasoning="drive",
        )
        uri = StatementClassification()._build_meaning_uri(False, loc)
        assert uri == "dx://taxonomy/Elements(General.v1)/Viability/Fire/Activation"
        # the old bespoke domain-free form must be gone
        assert "Elemental/Viability" not in uri

    def test_selection_criterion_in_prompt(self):
        """The classifier prompt now gives a real systemic-vs-elemental rule."""
        from dialectical_framework.concerns.statement_classification import (
            SYSTEM_PROMPT,
        )

        assert "peer taxonomies" in SYSTEM_PROMPT
        assert "drive, energy, motivation" in SYSTEM_PROMPT
        # polysemy fix: the is_simple=false label is no longer "COMPLEX/SYSTEMIC"
        assert "COMPLEX/SYSTEMIC" not in SYSTEM_PROMPT
