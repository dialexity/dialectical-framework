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
        from dialectical_framework.concerns.scoring_scales import \
            ASPECT_DEFINITIONS

        # cross-enhancement: a "+" aspect strengthens the OTHER side
        assert "also strengthens what A offers" in ASPECT_DEFINITIONS
        assert "also strengthens what T offers" in ASPECT_DEFINITIONS
        # diagonal contradiction for all four aspects
        for diag in (
            "Contradicts A-.",
            "Contradicts T-.",
            "Contradicts A+.",
            "Contradicts T+.",
        ):
            assert diag in ASPECT_DEFINITIONS, f"missing diagonal: {diag}"
        # the drift phrasing must not creep back
        assert "benefits, strengths" not in ASPECT_DEFINITIONS
        assert "risks, downsides, shadow" not in ASPECT_DEFINITIONS

    def test_aspect_definitions_carry_neutral_degeneration(self):
        """R3.3 neutral-T variant: 'T without A+ yields T-' + truth criterion
        (P0 p.29) live in the shared constant, reaching every aspect prompt."""
        from dialectical_framework.concerns.scoring_scales import \
            ASPECT_DEFINITIONS

        # neutral-level degeneration on both "-" definitions
        assert "What T itself degenerates into when A+ is absent" in ASPECT_DEFINITIONS
        assert "What A itself degenerates into when T+ is absent" in ASPECT_DEFINITIONS
        # truth criterion
        assert "only insofar as it fosters A+" in ASPECT_DEFINITIONS

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
        from dialectical_framework.concerns.scoring_scales import \
            COMPLEMENTARITY_SCALE

        assert "Actively undermines or contradicts" not in COMPLEMENTARITY_SCALE
        assert (
            "contributes nothing to its constructive development"
            in COMPLEMENTARITY_SCALE
        )
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


class TestTetradDiagonalStructure:
    """S1: diagonal contradiction is enforced by the output structure, not a
    trailing 'Ensure T+ contradicts A-' sentence.

    Guards the fix for closed issue #25 (Tree/Mother produced non-opposed
    aspects): the generator must (a) nest the tetrad into its two diagonal
    contradiction pairs and (b) make each pair name the axis of opposition.
    """

    def test_tetrad_dto_groups_four_aspects_by_two_axes(self):
        from dialectical_framework.concerns.aspect_generation import (
            AspectDto, TetradDto)

        fields = TetradDto.model_fields
        # four top-level aspects (deep nesting made the model drop a branch) ...
        for aspect in ("t_plus", "t_minus", "a_plus", "a_minus"):
            assert fields[aspect].annotation is AspectDto
        # ... plus one explicit axis field per diagonal pair
        assert fields["t_plus_vs_a_minus_axis"].annotation is str
        assert fields["a_plus_vs_t_minus_axis"].annotation is str

    def test_tetrad_axis_carries_no_opposition_escape(self):
        from dialectical_framework.concerns.aspect_generation import TetradDto

        # the axis field must let the model say "no genuine opposition exists"
        desc = TetradDto.model_fields["t_plus_vs_a_minus_axis"].description
        assert "not a genuine contradiction" in desc

    def test_contradiction_pair_requires_an_axis(self):
        from dialectical_framework.concerns.aspect_generation import \
            ContradictionPairDto

        fields = ContradictionPairDto.model_fields
        assert "axis" in fields
        assert fields["axis"].annotation is str
        # the axis field must carry the "no genuine opposition → say so" escape
        assert "no such shared dimension" in fields["axis"].description

    def test_tetrad_prompt_leads_with_axis_procedure_not_trailing_ensure(self):
        import inspect

        from dialectical_framework.concerns import aspect_generation

        src = inspect.getsource(aspect_generation.AspectGeneration._tetrad_prompt)
        # positive procedure: name the axis first
        assert "name the **axis**" in src
        # the old weak trailing constraint must not creep back
        assert "Ensure T+ contradicts A-" not in src


# --- H1: transformation worked example ---------------------------------------


class TestTransformationExample:
    def test_example_directions_match_formal_spec(self):
        """H1: the four example directions match docs/graph.md + the prompt's own defs."""
        from dialectical_framework.concerns.transformation_generation import \
            SYSTEM_PROMPT as P

        assert "Ac+ (T- → A+, Enmeshment → Autonomy)" in P
        assert "Re+ (A- → T+, Alienation → Bonding)" in P
        assert "Ac- (T+ → A-, Bonding → Alienation)" in P
        assert "Re- (A+ → T-, Autonomy → Enmeshment)" in P

    def test_ac_plus_and_re_plus_do_not_both_target_autonomy(self):
        """H1: the mirror collision (both ending at Autonomy) must not return."""
        from dialectical_framework.concerns.transformation_generation import \
            SYSTEM_PROMPT as P

        assert "Alienation → Autonomy" not in P


# --- H4: control-statements coherence ----------------------------------------


class TestControlStatementsCoherence:
    def test_status_uses_both_scores_not_average(self):
        """H4: a split verdict (0.9/0.6) is NOT coherent; rationale status agrees."""
        from dialectical_framework.graph.nodes.estimation import \
            ConceptualCoherenceEstimation

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
        from dialectical_framework.concerns import \
            control_statements_check as m

        src = inspect.getsource(m.ControlStatementsCheck.resolve)
        assert "is_coherent = avg_score >=" not in src
        assert "estimation.is_coherent" in src


# --- H5: apex sweet-spot numbers ---------------------------------------------


class TestApexSweetSpots:
    def test_field_descriptions_match_computed_bounds(self):
        """H5: Field descriptions render the computed sweet spots, not stale numbers."""
        from dialectical_framework.concerns.positive_ac_re_apex_derivation import \
            ApexPairDto

        re_desc = ApexPairDto.model_fields["re_plus_apex"].description
        ac_desc = ApexPairDto.model_fields["ac_plus_apex"].description
        assert "proactiveness 0.15-0.35" in re_desc
        assert "proactiveness 0.55-0.75" in ac_desc

    def test_no_stale_numbers_in_module(self):
        """H5: the stale 0.2-0.3 / 0.5-0.7 proactiveness ranges are gone."""
        from dialectical_framework.concerns import \
            positive_ac_re_apex_derivation as m

        src = inspect.getsource(m)
        assert "0.2-0.3" not in src
        assert "(proactiveness 0.5-0.7" not in src


class TestGreimasFiveCriteria:
    """Theory Greimas criteria (P1 p.22): all FIVE must be in the apex-derivation
    Validation block. Criterion 3 (pre-affordability — valid BEFORE A+/T+ are
    affordable) was the missing one (docs/theory/transformations-synthesis.md)."""

    def test_validation_block_carries_all_five(self):
        from dialectical_framework.concerns import \
            positive_ac_re_apex_derivation as m

        p = m.SYSTEM_PROMPT
        assert "not restate A+/T+" in p
        assert "be generative" in p
        # criterion 3: pre-affordability
        assert "valid BEFORE A+/T+ are affordable" in p
        assert "subtlety/non-force" in p
        assert "generalize beyond T/A" in p
        # five numbered items, not four
        assert "(5)" in p


class TestEqualSignSynthesisConstraint:
    """R5 (equal-sign synthesis): the like-signed rule must be an EXPLICIT prompt
    constraint, not only correct-by-construction input routing
    (docs/theory/generative-rules.md Rule 4.1-4.2)."""

    def test_like_signed_constraint_is_explicit(self):
        from dialectical_framework.concerns import synthesis_generation as m

        p = m.SYSTEM_PROMPT
        assert "Like-signed inputs only" in p
        assert "Never synthesize across opposite signs" in p


class TestBackfireConstraint:
    """R6 backfire corollary (P0 p.30): strengthening T+ head-on strengthens A-
    and flips T+ into T-. Transformation generation must forbid direct
    '+'-reinforcement (docs/theory/generative-rules.md Rule 3.3)."""

    def test_no_direct_reinforcement_rule_present(self):
        from dialectical_framework.concerns import transformation_generation as m

        p = m.SYSTEM_PROMPT
        assert "Never propose direct reinforcement" in p
        # the mechanism, so the constraint explains itself
        assert "flips T+ into T-" in p


class TestForcefulnessPolarityFlip:
    """Forcefulness -> polarity flip (P1 p.21): Ac+/Re+ must stay subtle and
    flexible; becoming too forceful reverses their polarity to '-'. Both Ac/Re
    generation prompts must carry the constraint
    (docs/theory/transformations-synthesis.md)."""

    def test_transformation_generation_carries_the_flip_rule(self):
        from dialectical_framework.concerns import transformation_generation as m

        p = m.SYSTEM_PROMPT
        assert "Forcefulness reverses polarity" in p
        assert "subtle and flexible" in p

    def test_action_extraction_carries_the_flip_rule(self):
        from dialectical_framework.concerns import action_extraction as m

        p = m.SYSTEM_PROMPT
        assert "reverses its polarity from Ac+ to Ac-" in p


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
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="t")
        assert "present_analysis" not in p  # H3
        assert "only one position" not in p  # H2 false claim gone
        assert "single perspective builds one self-referential wheel" in p

    def test_apps_wheel_definition_uses_spiral_not_blindspot(self):
        """H6: Wheel def routes exaggeration -> constructive strength, no blindspot."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        idx = NAVIGATOR_APP.find("Within a Nexus, Wheels")
        snippet = NAVIGATOR_APP[idx : idx + 260]
        assert "blindspot" not in snippet
        assert "constructive strength" in snippet

    def test_advanced_app_override_resolves_translation_table_conflict(self):
        """S5: override names both sections and supersedes the CRITICAL directive."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_ADVANCED_TOGGLE

        assert (
            "overrides Contextual Vocabulary and Presentation Defaults" in NAVIGATOR_APP_ADVANCED_TOGGLE
        )
        assert "does not apply here" in NAVIGATOR_APP_ADVANCED_TOGGLE

    def test_no_tetrades_misspelling(self):
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        assert "tetrades" not in NAVIGATOR_APP
        assert "tetrades" not in SYSTEM_PROMPT

    def test_causality_alias_example_matches_real_format(self):
        """Task 6: technical aliases follow C{seq}_{comp}; no stale C1,C2,C3
        examples survive in any estimator prompt."""
        from dialectical_framework.concerns.causality import (
            causality_estimator_balanced,
            causality_estimator_criteria,
            causality_estimator_desirable,
            causality_estimator_feasible,
            causality_estimator_realistic,
        )

        src = inspect.getsource(causality_estimator_balanced)
        assert 'f"C{seq_idx}_{comp_idx}"' in src
        for m in (
            causality_estimator_balanced,
            causality_estimator_criteria,
            causality_estimator_desirable,
            causality_estimator_feasible,
            causality_estimator_realistic,
        ):
            assert "e.g. C1, C2, C3" not in inspect.getsource(m)

    def test_advisor_has_discard_and_prompt_documents_it(self):
        """9a/9b: discard is wired into the Advisor and its prompt documents it,
        with the single consolidated tool section (no leftover duplicate)."""
        from dialectical_framework.agents.advisor.advisor import _build_tools
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

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
    """When ingest surfaces no tensions, the advisor should look for a genuine
    opposition itself and anchor it if present — while treating 'not
    tension-shaped' as a valid finding (never fabricating a tension). The
    pipeline must say so actionably instead of reporting a bare success."""

    def test_advisor_prompt_documents_empty_ingest_fallback(self):
        """The arc has an explicit branch for a tool that surfaces no
        tensions, pointing at `anchor` when opposition is genuinely there."""
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


# --- Floor guarantee: framework must never lower the model's floor -----------


class TestAdvisorFloorGuarantee:
    """The Advisor prompt must steer eagerly toward analysis without ever
    gating speech on tool calls or forcing fabricated tensions. Principle:
    prompts are for judgment, code is for invariants — the framework raises
    the ceiling, never lowers the floor."""

    def test_floor_guarantee_present(self):
        """Full native capability is guaranteed explicitly; analysis deepens
        counsel but never gates speech."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "full native capability" in SYSTEM_PROMPT
        assert "never gates your speech" in SYSTEM_PROMPT

    def test_eager_thinking_ungated_speech_section(self):
        """Tool use is framed as default identity for counsel-shaped turns,
        with named opt-outs — and speech never waits on the machinery."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "## Thinking Eagerly, Speaking Freely" in SYSTEM_PROMPT
        assert "never waits on the machinery" in SYSTEM_PROMPT

    def test_no_speech_gating_language(self):
        """The coercive anchor-before-responding override is gone, along with
        the grudging own-judgment escape."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "anchor that tension before responding" not in SYSTEM_PROMPT
        assert (
            "Only proceed on your own judgement if you genuinely"
            not in SYSTEM_PROMPT
        )

    def test_anchor_override_inverted(self):
        """'Not tension-shaped' is documented as a valid finding near the
        empty-ingest branch — fabricating a tension is not an option."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        idx = SYSTEM_PROMPT.find("surfaces no tensions")
        window = SYSTEM_PROMPT[idx : idx + 700]
        assert "valid finding" in window
        assert "tension-shaped" in window

    def test_sequence_is_default_arc_not_script(self):
        """The rigid Sequence is reframed as a default arc with explicit
        permission to depart."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "## Sequence" not in SYSTEM_PROMPT
        assert "## Default Arc" in SYSTEM_PROMPT
        assert "not a script" in SYSTEM_PROMPT

    def test_no_structural_guarantee_claim(self):
        """Verification (PerspectiveValidation) is unwired — the prompt must
        not claim a structural guarantee the system doesn't perform. Control
        statements are the model's own internal test instead."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "structural guarantee" not in SYSTEM_PROMPT
        assert "internal test" in SYSTEM_PROMPT

    def test_terminology_ban_has_preamble_escape_hatch(self):
        """Terminology hiding is preamble-overridable (vocabulary dial),
        following the NAVIGATOR_APP_ADVANCED_TOGGLE override precedent."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        idx = SYSTEM_PROMPT.find("framework terminology")
        window = " ".join(SYSTEM_PROMPT[idx : idx + 500].split())
        assert "unless the app preamble" in window

    def test_prohibition_wall_replaced_with_positive_rules(self):
        """'What You Must Never Do' is gone; 'How You Speak' carries the same
        constraints as positive rules."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "## What You Must Never Do" not in SYSTEM_PROMPT
        assert "## How You Speak" in SYSTEM_PROMPT
        # counsel-specificity survives as a positive rule
        assert "as specific as your understanding" in SYSTEM_PROMPT

    def test_statement_text_rephrasable_in_counsel(self):
        """Graph statement text is raw material for counsel prose — the
        Advisor rephrases freely (unlike Analyst/Explorer node referencing)."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "rephrase it freely" in SYSTEM_PROMPT

    def test_analyst_no_tension_is_valid_conclusion(self):
        """Analyst: reporting no genuine tension is a valid conclusion, not a
        failure to force a weak opposition."""
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT as ANALYST_PROMPT

        assert "valid analytical conclusion" in ANALYST_PROMPT

    def test_explorer_build_wheels_intent_driven(self):
        """Explorer: build_wheels is driven by user intent, not a reflex on
        every first message."""
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        rendered = system_prompt(nexus_hash="abc1234", nexus_intent="test")
        assert "not a reflex" in rendered

    def test_thesis_extraction_has_gate_rejection_safety_net(self):
        """A step-2 gate that rejects every item falls back to raw content
        items rather than returning zero candidates."""
        from dialectical_framework.concerns import thesis_extraction as m

        src = inspect.getsource(m.ThesisExtraction.resolve)
        # fallback keys off content_items surviving when candidates are empty
        assert "not all_candidates and content_items" in src


# --- Anchor path: component_length now clamps verbatim T/A statements --------


class TestAnchorHeadlineClamp:
    """The anchor path had no generation step, so agent prose was stored
    verbatim — bypassing component_length. StatementHeadline closes that gap."""

    def test_prompt_body_is_settings_driven_not_field_description(self):
        """Per CLAUDE.md: numeric limit goes in the prompt body, never in a
        Pydantic Field description (which can't interpolate self.settings)."""
        from dialectical_framework.concerns import statement_headline as m

        # No hardcoded number in the module source (prompt interpolates settings).
        src = inspect.getsource(m)
        assert "7 words" not in src
        assert "15 words" not in src
        # The word limit must NOT live on the DTO field description.
        desc = m.HeadlineDto.model_fields["headline"].description
        assert "word" not in desc.lower()
        # The prompt builder interpolates the runtime budget.
        assert "{max_words}" in inspect.getsource(m.StatementHeadline._prompt)

    @pytest.mark.asyncio
    async def test_short_statement_short_circuits_without_llm(self, monkeypatch):
        """A statement already within component_length is returned unchanged and
        never touches the LLM (keeps anchor_theses(['Trust']) free)."""
        from dialectical_framework.concerns.statement_headline import \
            StatementHeadline

        headliner = StatementHeadline()

        async def _boom(*args, **kwargs):
            raise AssertionError("LLM must not be called for a short statement")

        monkeypatch.setattr(headliner._conversation, "submit", _boom)

        result = await headliner.resolve(statement="Trust matters")
        assert result == "Trust matters"
        assert "within word budget" in headliner.report.summary

    @pytest.mark.asyncio
    async def test_long_statement_is_condensed(self, monkeypatch):
        """A verbose statement is routed through the LLM and replaced by its
        headline."""
        from dialectical_framework.concerns import statement_headline as m
        from dialectical_framework.concerns.statement_headline import \
            StatementHeadline

        headliner = StatementHeadline()

        async def _fake_submit(response_model, user_content, **kwargs):
            # the runtime word budget must reach the prompt
            assert "approximately" in user_content
            return m.HeadlineDto(
                headline="Preplanning should be the primary sales mode"
            )

        monkeypatch.setattr(headliner._conversation, "submit", _fake_submit)

        long = (
            "Preplanning creates structural stability — denser groups, less "
            "teacher search stress, packaged courses with committed slots — and "
            "deserves to be the primary sales mode"
        )
        result = await headliner.resolve(statement=long)
        assert result == "Preplanning should be the primary sales mode"

    def test_both_anchor_legs_condense_the_stored_text(self):
        """IntroducePolarity (T+A leg) and AnchorTheses (thesis-only leg) both
        store the headline, not the raw statement."""
        from dialectical_framework.agents.analyst.skills import \
            anchor_theses as at
        from dialectical_framework.agents.analyst.skills import \
            introduce_polarity as ip

        ip_src = inspect.getsource(ip.IntroducePolarity._resolve_statement)
        assert "StatementHeadline()" in ip_src
        assert "Statement(text=headline" in ip_src

        at_src = inspect.getsource(at.AnchorTheses)
        assert "StatementHeadline()" in at_src
        assert "Statement(text=headline" in at_src


# --- Orchestrator intelligence: Explorer depth + Analyst grouping -----------


class TestExplorerExplorationDepth:
    """The Explorer is a sandboxed mini-advisor. Its prompt must carry
    exploration-phase reasoning (score interpretation, S+/S-) and interpolate
    the shared taxonomy ladders rather than re-typing them."""

    def _render(self) -> str:
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        return system_prompt(nexus_hash="abc1234", nexus_intent="test intent")

    def test_has_causality_and_score_section(self):
        p = self._render()
        assert "## Reading Causality & Transformation Scores" in p
        # P vs normalized % causality reasoning
        assert "normalized" in p and "%" in p
        # feasibility bands
        assert "feasibility" in p

    def test_interpolates_shared_taxonomy_ladders_not_retyped(self):
        """The insight/proactiveness ladders come from ac_re_taxonomy.py, so
        both ends of each scale must render from the constants."""
        from dialectical_framework.agents.explorer import system_prompts as m

        p = self._render()
        # insight ladder ends
        assert "0.0 reflex" in p and "1.0 transcendence" in p
        # proactiveness ladder ends + zone anchors
        assert "0.0 observation" in p and "1.0 stewardship" in p
        assert "0.5-1.0" in p and "0.0-0.4" in p
        # built from the constants, not hand-typed
        src = inspect.getsource(m)
        assert "from dialectical_framework.concerns.ac_re_taxonomy import" in src
        assert "INSIGHT_SCALE" in src and "PROACTIVENESS_SCALE" in src

    def test_synthesis_emergence_vs_trap(self):
        p = self._render()
        assert "S+" in p and "S-" in p
        # emergence framing and the S- trap
        assert "1+1>2" in p or "emergence" in p
        assert "trap" in p

    def test_hs_on_transition_disambiguated(self):
        """HS on Ac+/Re+ (apex fit) is clarified so the Explorer doesn't confuse
        it with HS-on-antithesis, without renaming the Advisor-only dump."""
        p = self._render()
        assert "HS" in p and "apex" in p

    def test_no_leaked_brace_tokens(self):
        """The f-string must fully interpolate — no stray {CONST} tokens."""
        p = self._render().replace("T+/T-/A+/A-", "")
        assert "{" not in p and "}" not in p


class TestExplorerIsBoundedConsumer:
    """The Explorer is a pure consumer within one nexus: no material-capture
    and no perspective-building tools. New analysis routes to the Analyst."""

    def test_no_capture_or_perspective_building_tools(self):
        from dialectical_framework.agents.explorer.explorer import _build_tools

        names = {getattr(t, "__name__", None) for t in _build_tools()}
        for forbidden in (
            "add_input",
            "surface_theses",
            "find_polarities",
            "expand_polarities",
            "anchor_theses",
            "introduce_polarity",
            "ingest",
            "anchor",
        ):
            assert forbidden not in names, f"Explorer must not expose {forbidden}"

    def test_prompt_routes_new_material_to_analysis_thread(self):
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="test intent")
        assert "analysis view" in p


class TestNavigatorRoundTrip:
    """The round-trip (exploration insight -> dx:// input -> Analyst -> new
    perspectives -> expand_nexus) must be narrated on BOTH sides, and the
    Explorer must carry the capture tool so the loop starts where the insight
    appears — no courier job, no dead off-ramp."""

    def test_explorer_carries_create_dx_input(self):
        from dialectical_framework.agents.explorer.explorer import _build_tools

        names = {getattr(t, "__name__", None) for t in _build_tools()}
        assert "create_dx_input" in names

    def test_explorer_prompt_narrates_the_round_trip(self):
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="test intent")
        assert "create_dx_input" in p
        # the loop closes back into the exploration, not just exits
        assert "expand_nexus" in p
        # offered at resonance moments, not as a reflex
        assert "not\n  as a reflex" in p or "not as a reflex" in " ".join(p.split())
        # the capture is the Explorer's ONLY analysis-side move — the
        # boundary (no thesis extraction / perspective building) survives
        assert "cannot extract" in p

    def test_explorer_narrates_analyst_as_weave_owner(self):
        """Weave-step ownership: the Analyst weaves back after developing;
        the Explorer's expand_nexus is the FALLBACK for perspectives that
        weren't woven in there — not the primary path (previously both
        prompts claimed the step)."""
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="test intent")
        joined = " ".join(p.split())
        assert "weaving it back into this exploration) happens in the " \
            "analysis view" in joined
        assert "attach them yourself via `expand_nexus`" in joined
        # the old double-claim is gone
        assert "return here afterwards to weave the result in" not in joined

    def test_explorer_prompt_frames_analyst_trip_as_growth_not_exit(self):
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="test intent")
        joined = " ".join(p.split())
        # the old dead off-ramp ("suggest they return...") must be gone
        assert "suggest the user returns to the analysis thread" not in joined
        assert "suggest they return to the analysis thread" not in joined
        assert "not as an exit" in joined

    def test_analyst_prompt_recognizes_dx_inputs_and_closes_loop(self):
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT

        joined = " ".join(SYSTEM_PROMPT.split())
        assert "dx://" in joined
        # dx inputs are exploration feedback, developed then offered back
        assert "expand_nexus` to weave them back" in joined
        # the "weave back to the SOURCE" instruction must be executable —
        # the prompt points at the origin channels (digest / inspect_node
        # on the URI's transition hash — dx-specific, not the generic
        # inspect_node mentions elsewhere in the prompt)
        assert "Origin: insight from" in joined
        assert "the last segment of the dx:// URI" in joined


class TestValidationVerdictNarration:
    """PerspectiveValidation now runs live (task #4) — the prompts may
    reference the machine-run verdict, and must frame it as a flag to
    prioritize by, not a structural guarantee (which stays banned)."""

    def test_advisor_reads_the_validation_line(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        p = " ".join(SYSTEM_PROMPT.split())
        assert "machine-run verdict" in p
        # score-reading section explains the three states
        assert '"passed"' in p and '"failed' in p
        # the floor-guarantee ban stays: no unwired-guarantee claim
        assert "structural guarantee" not in p

    def test_advisor_names_mechanical_opposition(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "mechanical opposition" in SYSTEM_PROMPT

    def test_analyst_narrates_the_verdict_as_meaning(self):
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT

        p = " ".join(SYSTEM_PROMPT.split())
        assert "`validation` verdict" in p
        # failed = provisional + offer a fix path, not silent drop
        assert "provisional" in p
        assert "edit_perspective" in p


class TestContextDumpPrePruned:
    """The dump is pre-pruned (task #5): code suppresses below-floor tensions
    and low-% wheels, so the Advisor prompt must say 'rank within what you
    see' rather than carry re-filtering instructions the dump already
    enforces."""

    def _advisor(self) -> str:
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        return " ".join(SYSTEM_PROMPT.split())

    def test_prompt_declares_the_dump_pre_pruned(self):
        p = self._advisor()
        assert "pre-pruned" in p
        assert "you rank within them, you don't re-filter" in p
        # the DV floor joined the pruning (SP+DV pair) — the prompt's floor
        # description must name the distorted-framing suppression
        assert "unnatural/distorted framing" in p

    def test_old_poor_scores_rule_reconciled(self):
        """Rule 4 ('if a perspective has poor scores...') described material
        the pruning now removes — the surviving wording must speak of the
        softer-but-above-floor band, not of ignoring poor scores."""
        p = self._advisor()
        assert "If a perspective has poor scores" not in p
        assert "Softer" in p and "still visible by design" in p

    def test_unexplored_tensions_notes_the_filter(self):
        p = self._advisor()
        assert "quality-filtered" in p


class TestCrossAgentHsBandParity:
    """Analyst and Advisor hand-type HS-on-A reading bands. They must carry
    the SAME band boundaries (0.7 / 0.5 / 0.3) so a borderline tension gets
    consistent treatment across the toggle — a user shouldn't see a 0.42
    tension demoted in the analysis view and promoted in counsel. Boundaries
    come from the shared HS_SCALE constant (0.9/0.7/0.5/0.3/0.1)."""

    def _bands(self, text: str) -> list[str]:
        import re

        # normalize unicode dash and whitespace, then extract band tokens
        t = " ".join(text.replace("–", "-").split())
        return re.findall(r"(?:≥|>=|<)?0\.\d(?:-0\.\d)?", t)

    def test_analyst_and_advisor_share_band_boundaries(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT as ADVISOR
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT as ANALYST

        # Analyst: locate its HS reading section
        a_idx = ANALYST.find("Reading Polarity Quality")
        analyst_section = " ".join(
            ANALYST[a_idx : a_idx + 900].replace("–", "-").split()
        )
        # Advisor: locate the HS-on-A entry in score reading
        d_idx = ADVISOR.find("`HS` on A (antithesis)")
        advisor_section = " ".join(
            ADVISOR[d_idx : d_idx + 500].replace("–", "-").split()
        )

        for band in ("0.7", "0.5-0.7", "0.3-0.5", "<0.3"):
            assert band in analyst_section, f"Analyst missing band {band}"
            assert band in advisor_section, f"Advisor missing band {band}"
        # the old coarse Analyst floor must not return
        assert "<0.5 — weak or tangential; the two sides barely oppose" not in (
            analyst_section
        )

    def test_analyst_and_advisor_agree_on_dv_semantics(self):
        """DV parity across the toggle: both agents must describe DV as
        naturalness-of-framing (not quality/coherence), both must route low
        DV to RE-FRAMING (not aspect polishing), and the Analyst must know
        counsel mode prunes very-low-DV tensions — otherwise a perspective
        visible in analysis silently vanishes in counsel and the Analyst
        can't explain why."""
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT as ADVISOR
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT as ANALYST

        for prompt, agent in ((ANALYST, "Analyst"), (ADVISOR, "Advisor")):
            text = " ".join(prompt.split())
            # DV = naturalness, both agents
            assert "DV" in text, f"{agent} never mentions DV"
            assert "natural" in text.lower(), f"{agent} DV not framed as naturalness"
            # low DV → the FRAMING is at fault → re-frame/re-anchor
            assert "re-anchor" in text.lower() or "re-fram" in text.lower(), (
                f"{agent} lacks the low-DV re-framing route"
            )
        # the Analyst-specific toggle warning
        analyst_text = " ".join(ANALYST.split())
        assert "counsel mode prunes very-low-DV" in analyst_text


class TestArrangementContrast:
    """The wheel enumeration's payoff (task #3): when top arrangements are
    close AND encode different causal readings, both prompts must instruct
    contrast-and-ask ("which matches your lived reality?") instead of pure
    argmax — this is the reasoning move a bare model can't cheaply
    self-generate. Argmax stays the rule when one arrangement dominates."""

    def _explorer(self) -> str:
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        return " ".join(
            system_prompt(nexus_hash="abc1234", nexus_intent="test").split()
        )

    def _advisor(self) -> str:
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        return " ".join(SYSTEM_PROMPT.split())

    def test_explorer_carries_contrast_guidance(self):
        p = self._explorer()
        assert "competing readings" in p
        assert "lived reality" in p
        # argmax preserved for the dominant case
        assert "clearly dominates" in p
        # the old unconditional argmax phrasing must be gone
        assert "Lead with the highest-`%` arrangement" not in p

    def test_advisor_carries_contrast_guidance(self):
        p = self._advisor()
        assert "lived reality" in p
        assert "clearly dominates" in p
        # diagnostic framing: the user's answer selects the reading
        assert "diagnostic" in p

    def test_advisor_contrast_acknowledges_selective_depth(self):
        """Lazy explore (task #2) means pathways may exist for one wheel only —
        the contrast rule must say the causal contrast needs no pathways."""
        p = self._advisor()
        assert "depth is selective" in p.lower()

    def test_both_share_the_closeness_heuristic(self):
        """The ~15-point closeness band must not drift apart between agents."""
        assert "~15 percentage points" in self._explorer()
        assert "~15 percentage points" in self._advisor()


class TestExplorerAdvisorToggleNarration:
    """The Explorer<->Advisor toggle is host-driven; each head must surface the
    handover signal for its opposite register without auto-switching."""

    def test_explorer_signals_counsel_mode(self):
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="test intent")
        joined = " ".join(p.split())
        assert "counsel" in joined
        # host drives the switch, never the agent
        assert "never switch modes yourself" in joined
        # graceful floor: absent a counsel mode, keep counseling
        assert "keep counseling" in joined

    def test_explorer_routes_decision_moments_to_counsel(self):
        """A decision declaration is a handover signal (immediate, not after
        a sustained pull) — the Explorer cannot record decisions and must
        never fake an acknowledgment."""
        from dialectical_framework.agents.explorer.system_prompts import \
            system_prompt

        p = system_prompt(nexus_hash="abc1234", nexus_intent="test intent")
        joined = " ".join(p.split())
        assert "when the user tries to DECIDE" in joined
        assert "NEVER claim to have noted a decision yourself" in joined
        assert "Recording and retiring decisions happens in counsel mode" in joined

    def test_analyst_never_fakes_or_anchors_decisions(self):
        """Cross-agent parity (review finding): the Analyst serves the same
        Case but had no decision seam — leaving it a plausible wrong move
        (anchor the declared choice as a thesis, misfiling a decision as
        analytical structure) and no bar on faking an acknowledgment."""
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT

        joined = " ".join(SYSTEM_PROMPT.split())
        assert "you cannot record decisions" in joined
        assert "NEVER claim to have noted a decision yourself" in joined
        assert "NEVER anchor the declared choice as a thesis" in joined

    def test_scoped_advisor_signals_exploration_view(self):
        """The counsel-mode preamble already narrates switching back to the
        technical exploration view — lock that phrase."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        joined = " ".join(NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER.split())
        assert "they can switch anytime" in joined
        assert "exploration view" in joined


class TestScopedAdvisorConsentContract:
    """The scoped (counsel-mode) render must not contradict the preamble's
    transparency contract: no silent mutation instructions may survive into
    the assembled scoped prompt. The unscoped render keeps silent-discard
    (that's its design)."""

    def _scoped(self) -> str:
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        # The FULL production scoped toolset (build_scoped_tools) — the sweep
        # must see every section that actually renders in counsel mode; a
        # reduced list leaves conditionally-rendered sections unswept.
        return system_prompt(
            tool_names=[
                "anchor", "sync", "inspect_node", "read_digest",
                "discard", "explore", "deepen", "record_decision",
            ],
            scoped_nexus_hash="abc1234",
        )

    def test_scoped_render_has_no_silent_discard(self):
        p = self._scoped()
        joined = " ".join(p.split())
        assert "silently `discard` it" not in joined
        assert "Don't announce it" not in joined
        # consented retraction instead
        assert "retractions are consented, not silent" in joined
        assert "nothing appears or disappears from it without them knowing" \
            in joined

    def test_scoped_render_whole_prompt_silence_sweep(self):
        """Sweep the ENTIRE assembled scoped prompt for silent-mutation and
        machinery-hiding phrasing — not just the rejection section. Catches
        remnants in shared sections (_ROLE, _TOOLS_INTRO, tool docs) that
        section-specific asserts miss (found by review: the discard tool doc
        still said 'Silently retracts')."""
        p = self._scoped()
        joined = " ".join(p.split())
        for phrase in (
            "Silently retracts",
            "silently `discard`",
            "never see the machinery",
            "never mention them",
            "Don't announce",
        ):
            assert phrase not in joined, f"silent-mutation remnant: {phrase!r}"
        # effects are announced, tool names still hidden
        assert "announce additions and removals" in joined
        assert "Never name the tools themselves" in joined \
            or "never name the tools" in joined.lower()

    def test_scoped_rejection_covers_woven_in_dead_end(self):
        """A woven-in perspective can't be discarded (Discard refuses cycle
        members) — the consent script must not promise a removal the tool
        will refuse. The prompt must carry the re-anchor fallback."""
        p = self._scoped()
        joined = " ".join(p.split())
        assert "cannot be removed" in joined
        assert "don't offer a removal you can't deliver" in joined.lower() \
            or "don't offer a removal" in joined.lower()
        assert "the old one stays visible" in joined

    def test_unscoped_render_keeps_silent_discard(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "silently `discard` it" in SYSTEM_PROMPT

    def test_scope_section_defers_consent_to_preamble(self):
        """The scope section describes routing (where things land), not an
        unconditional command to mutate — consent belongs to the preamble."""
        p = self._scoped()
        joined = " ".join(p.split())
        assert "the person agrees to add it" in joined
        assert "app preamble above governs how that consent works" in joined

    def test_scoped_render_does_not_reference_ingest(self):
        """ingest is not wired in scoped mode — the prompt must not mention
        it at all (bare-word sweep; review found 'More precise than ingest'
        and 'anchor/ingest result' surviving a backtick-only check)."""
        p = self._scoped()
        assert "ingest" not in p.lower()
        # anchor guidance survives the rewrite
        assert "**After anchor (tensions identified):**" in p

    def test_own_rejected_anchor_is_retractable_in_prompt(self):
        """The scoped rejection section covers the fresh-anchor case (no
        ceremony) separately from exploration members (confirm first)."""
        p = self._scoped()
        joined = " ".join(p.split())
        assert "anchored during THIS conversation" in joined

    def test_scoped_speech_rule_quotes_exact_text_when_citing_hashes(self):
        """The scoped render sits in Navigator territory with hash disclosure:
        it must NOT carry the unscoped 'machinery stays invisible / rephrase
        freely' rules — a paraphrase next to a hash citation is exactly the
        ambiguity the Navigator's never-rephrase rule prevents."""
        p = self._scoped()
        joined = " ".join(p.split())
        assert "The machinery stays invisible" not in joined
        assert "rephrase it freely" not in joined
        assert "quote its exact statement text" in joined
        # the unscoped render keeps its rules
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "The machinery stays invisible" in SYSTEM_PROMPT
        assert "rephrase it freely" in SYSTEM_PROMPT


class TestAdvisorScoreLaddersDerived:
    """The Advisor's insight/proactiveness ladders must be derived from
    ac_re_taxonomy.py (like the Explorer's), not hand-typed — hand-typed
    copies drift when the taxonomy changes."""

    def test_ladders_interpolated_from_constants(self):
        """The rendered helper output must appear verbatim in the prompt —
        proves the ladders come THROUGH _ladder_lines, not a hand-typed copy
        that happens to match (a copy passes the value test until the
        taxonomy changes)."""
        from dialectical_framework.agents.advisor.system_prompts import (
            SYSTEM_PROMPT, _ladder_lines)
        from dialectical_framework.concerns.ac_re_taxonomy import (
            INSIGHT_SCALE, PROACTIVENESS_SCALE)

        insight_render = _ladder_lines(
            INSIGHT_SCALE,
            {0.0: "automatic response", 1.0: "paradigm shift"},
        )
        proactiveness_render = _ladder_lines(
            PROACTIVENESS_SCALE,
            {0.2: "Re apex zone", 0.4: "midpoint", 0.6: "Ac apex zone"},
        )
        assert insight_render in SYSTEM_PROMPT
        assert proactiveness_render in SYSTEM_PROMPT

    def test_rendered_values_match_taxonomy(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT
        from dialectical_framework.concerns.ac_re_taxonomy import (
            INSIGHT_SCALE, PROACTIVENESS_SCALE)

        for label, value in {**INSIGHT_SCALE, **PROACTIVENESS_SCALE}.items():
            assert f"{value:.1f} = {label.lower()}" in SYSTEM_PROMPT


class TestUnscopedAdvisorNexusDedup:
    """The unscoped Advisor's explore doc must carry reuse-before-create
    guidance — without it the model silently spawns sibling nexuses for the
    same theme (the Analyst has the equivalent rule; parity)."""

    def test_explore_doc_carries_dedup_guidance(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        joined = " ".join(SYSTEM_PROMPT.split())
        assert "Reuse before creating" in joined
        assert "sibling nexuses" in joined


class TestAdvisorNexusSizeCapDerived:
    """The explore doc's nexus-size ladder ('How a nexus evolves', '>N:
    combinatorial explosion') must derive from settings.max_wheel_layer —
    the cap PerspectiveCombination actually enforces — not restate the
    default as a hand-typed '4'. Otherwise DIALEXITY_MAX_WHEEL_LAYER=3
    leaves the Advisor advising sizes the pipeline silently won't build."""

    def test_default_render_matches_settings_default(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT
        from dialectical_framework.settings import Settings

        cap = Settings.model_fields["max_wheel_layer"].default
        joined = " ".join(SYSTEM_PROMPT.split())
        assert f">{cap}: combinatorial explosion" in joined
        assert f"aren't built beyond {cap} perspectives" in joined
        # the unfilled placeholder must never leak into a render
        assert "{nexus_evolution}" not in SYSTEM_PROMPT

    def test_render_follows_settings_override(self, di_container):
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        current = di_container.settings()
        di_container.settings.override(current.model_copy(update={"max_wheel_layer": 3}))
        try:
            joined = " ".join(system_prompt().split())
        finally:
            di_container.settings.reset_override()
            di_container.settings.override(current)

        assert ">3: combinatorial explosion" in joined
        assert ">4:" not in joined
        # ladder collapses gracefully: "3" alone, not "3-3"
        assert "- 3 perspectives:" in joined
        assert "3-3" not in joined

    def test_ladder_handles_tiny_caps(self):
        """No '3-2 perspectives' nonsense or stale rungs below the cap."""
        from dialectical_framework.agents.advisor.system_prompts import \
            _nexus_evolution

        two = " ".join(_nexus_evolution(2).split())
        assert ">2: combinatorial explosion" in two
        assert "3" not in two.replace(">2", "")

        one = " ".join(_nexus_evolution(1).split())
        assert ">1: combinatorial explosion" in one
        assert "2 perspectives" not in one


class TestExplorationAdvisorColdStart:
    """NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER must not presuppose shared history or that the
    user built the exploration — the constructor explicitly supports
    messages=None on an existing (possibly ingest-built or shared) nexus."""

    def test_history_is_ground_truth_not_assumed(self):
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        joined = " ".join(NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER.split())
        assert "take the history you actually see as the ground truth" in joined
        assert "never assume shared memories" in joined
        # authorship is not presupposed either
        assert "built this exploration themselves — they worked through" \
            not in joined
        assert "don't address them as its author" in joined

    def test_switch_back_hedged_on_host_affordance(self):
        """Mirror of the Explorer's 'if the application offers' hedge — the
        counsel head must not promise a UI affordance the host may not have."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        joined = " ".join(NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER.split())
        assert "if the application offers a way back" in joined


class TestAnalystNexusGrouping:
    """The Analyst owns the grouping judgment at handoff: prefer different
    polarities, but allow same-polarity when it fits or the user asks."""

    def test_prompt_carries_grouping_principle_with_fallback(self):
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT

        assert "different polarities" in SYSTEM_PROMPT
        assert "angle shifts" in SYSTEM_PROMPT
        # the fallback must not be an absolute prohibition
        assert "Same-polarity grouping is still valid" in SYSTEM_PROMPT

    def test_prompt_does_not_mandate_confirming_exploration_direction(self):
        """Intent is an internal quality gate (do not surface). Nexus creation
        must NOT block on asking the user to state an exploration intent when the
        perspectives to group are already clear — that contradicts the
        infer-silently design and produced a generic "what is your intent?"
        stall. See eo-debug conv 140."""
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT

        # the old unconditional gate must be gone
        assert "Confirm the exploration direction with the user before creating" \
            not in SYSTEM_PROMPT
        # intent stays internal, and creation happens when perspectives are clear
        assert "do not surface to user" in SYSTEM_PROMPT
        assert "Create immediately when the perspectives to group are clear" \
            in SYSTEM_PROMPT


class TestNexusExplorationVocabulary:
    """"Nexus" is internal-only; the user-facing term is "Exploration". The app
    preamble must not whitelist "Nexus" as user-facing, and both the preamble
    and the Analyst prompt must carry the internal<->user mapping. Polarity
    stays user-facing (it is Thesis-Antithesis, used throughout the UI)."""

    def test_default_app_does_not_whitelist_nexus_as_user_facing(self):
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        idx = NAVIGATOR_APP.find("are fine to use")
        assert idx != -1, "user-facing structural-terms whitelist moved"
        whitelist = NAVIGATOR_APP[idx - 160 : idx]
        assert "Nexus" not in whitelist
        # Polarity is still user-facing.
        assert "Polarity" in whitelist

    def test_default_app_carries_nexus_to_exploration_mapping(self):
        from dialectical_framework.agents.apps import NAVIGATOR_APP

        assert "Exploration" in NAVIGATOR_APP
        # agents still know they are the same thing
        assert 'never surface\n  the word "Nexus"' in NAVIGATOR_APP

    def test_analyst_prompt_keeps_internal_mapping_but_not_user_leak(self):
        from dialectical_framework.agents.analyst.system_prompts import \
            SYSTEM_PROMPT

        # agent still knows Nexus == Exploration and keeps the tool names
        assert "internal name for what the user calls an **Exploration**" in \
            SYSTEM_PROMPT
        # the one user-facing dedup line no longer says "existing nexus"
        assert "name the existing exploration" in SYSTEM_PROMPT
        assert "name the existing nexus" not in SYSTEM_PROMPT

    def test_advanced_app_still_permits_nexus_for_experts(self):
        """NAVIGATOR_APP_ADVANCED_TOGGLE explicitly overrides the vocabulary rules for experts."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_ADVANCED_TOGGLE

        assert "Nexus" in NAVIGATOR_APP_ADVANCED_TOGGLE


class TestExplorationAdvisorApp:
    """NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER is the counsel-mode preamble of the
    Explorer<->Advisor toggle. It MUST be composed on NAVIGATOR_APP (Navigator
    territory: same vocabulary contract, perspective detection, score
    presentation) — not written from scratch — and it must mandate
    transparent, consented mutation of the user-built exploration."""

    def test_composed_on_default_app(self):
        from dialectical_framework.agents.apps import (NAVIGATOR_APP,
                                                       NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER)

        assert NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER.startswith(NAVIGATOR_APP)
        assert "## Advisory Register" in NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

    def test_grants_terminology_disclosure_for_engine_hatch(self):
        """The engine's terminology escape hatch keys on the preamble
        granting disclosure — the section must exist."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        assert "## Terminology Disclosure" in NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

    def test_disclosure_defers_to_default_app_nexus_rule(self):
        """Disclosure does NOT unlock 'Nexus' — NAVIGATOR_APP's exploration
        vocabulary still governs (unlike NAVIGATOR_APP_ADVANCED_TOGGLE, which unlocks it)."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        idx = NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER.find("## Terminology Disclosure")
        disclosure = NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER[idx:]
        assert '"Nexus" stays internal' in disclosure

    def test_mandates_transparent_mutation(self):
        """Counsel mode must never grow or prune the user-built exploration
        silently — ask first, announce after."""
        from dialectical_framework.agents.apps import NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER

        assert "Never grow or prune their exploration silently" in (
            NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER
        )


class TestDedupReportsAreMerged:
    """surface_theses and find_polarities must merge the deduplicator's report
    so dedup deletions surface as node_deleted effects (not just a count)."""

    def test_surface_theses_merges_dedup_report(self):
        from dialectical_framework.agents.analyst.skills import \
            surface_theses as m

        src = inspect.getsource(m.SurfaceTheses.resolve)
        assert "self._report.merge(deduplicator.report)" in src

    def test_find_polarities_merges_dedup_report(self):
        from dialectical_framework.agents.analyst.skills import \
            find_polarities as m

        # _process_thesis is where the dedup runs
        src = inspect.getsource(m)
        assert "self._report.merge(deduplicator.report)" in src


# --- Task 10: Elemental as a full peer taxonomy ------------------------------


class _FakeStatement:
    """Minimal stand-in for the static lookups (.meaning/.is_simple/.text)."""

    def __init__(self, meaning: str) -> None:
        self.meaning = meaning
        self.is_simple = False
        self.text = "fake statement"


class TestElementalTaxonomy:
    _URI = "dx://taxonomy/Elements(General.v1)/Viability/Fire/Activation"

    def test_dict_matches_table_s2(self):
        """The ELEMENTAL_TAXONOMY dict transcribes Table S-2 (Fire row + Apex)."""
        from dialectical_framework.concerns.statement_classification import \
            ELEMENTAL_TAXONOMY
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A, POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T,
            POSITION_T_MINUS, POSITION_T_PLUS)

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
        from dialectical_framework.concerns.statement_classification import \
            parse_meaning_uri

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
            _taxonomy_for_meaning)

        assert _family_for_meaning(self._URI) == "Elements"
        assert _taxonomy_for_meaning(self._URI) is ELEMENTAL_TAXONOMY
        # default / systemic
        assert _family_for_meaning(None) == "System"
        assert (
            _taxonomy_for_meaning(
                "dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling"
            )
            is SYSTEMIC_TAXONOMY
        )

    def test_antithesis_stays_elemental(self):
        """Regression: elemental thesis must NOT fall back to systemic Fidelity."""
        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC

        result = SC.lookup_antithesis_meaning(_FakeStatement(self._URI))
        assert result == "dx://taxonomy/Elements(General.v1)/Viability/Fire/Inhibition"
        assert "System(" not in result  # the corruption we fixed
        assert "Fidelity" not in result

    def test_all_aspects_stay_elemental(self):
        """Regression: aspects must NOT collapse to the systemic Apex column."""
        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC

        parent = _FakeStatement(self._URI)
        expected = {
            "T+": "Motivation",
            "T-": "Impulsivity",
            "A+": "Regulation",
            "A-": "Repression",
        }
        for pos, apex in expected.items():
            meaning = SC.lookup_aspect_meaning(parent, pos)
            assert (
                meaning == f"dx://taxonomy/Elements(General.v1)/Viability/Fire/{apex}"
            )
            # apex concept name drives HS scoring — must be the elemental one,
            # not the systemic Apex fallback (Coherence/Rigid fusion/...)
            assert SC.lookup_aspect_apex(parent, pos) == apex

    def test_dedup_prefix_preserves_family(self):
        from dialectical_framework.concerns.statement_deduplication import \
            _extract_meaning_prefix

        assert (
            _extract_meaning_prefix(self._URI)
            == "dx://taxonomy/Elements(General.v1)/Viability/Fire"
        )

    def test_systemic_path_unchanged(self):
        """Systemic lookups must be untouched by the elemental dispatch."""
        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC
        from dialectical_framework.concerns.statement_deduplication import \
            _extract_meaning_prefix

        uri = "dx://taxonomy/System(Engineering.v1)/Viability/Fidelity/Simulation"
        assert SC.lookup_aspect_apex(_FakeStatement(uri), "T+") == "Accuracy"
        assert (
            _extract_meaning_prefix(uri)
            == "dx://taxonomy/System(Engineering.v1)/Viability/Fidelity"
        )

    def test_build_meaning_uri_emits_uniform_elemental_form(self):
        """_build_meaning_uri emits the family-uniform Elements(General.v1) form."""
        from dialectical_framework.concerns.statement_classification import (
            StatementClassification, TaxonomyLocationDto)

        loc = TaxonomyLocationDto(
            taxonomy_type="elemental",
            domain="General",
            branch="Fire",
            leaf="Activation",
            reasoning="drive",
        )
        uri = StatementClassification()._build_meaning_uri(False, loc)
        assert uri == "dx://taxonomy/Elements(General.v1)/Viability/Fire/Activation"
        # the old bespoke domain-free form must be gone
        assert "Elemental/Viability" not in uri

    def test_selection_criterion_in_prompt(self):
        """The classifier prompt now gives a real systemic-vs-elemental rule."""
        from dialectical_framework.concerns.statement_classification import \
            SYSTEM_PROMPT

        assert "peer taxonomies" in SYSTEM_PROMPT
        assert "drive, energy, motivation" in SYSTEM_PROMPT
        # polysemy fix: the is_simple=false label is no longer "COMPLEX/SYSTEMIC"
        assert "COMPLEX/SYSTEMIC" not in SYSTEM_PROMPT


# --- Cross-exploration correspondences guidance -------------------------------


class TestCrossExplorationGuidance:
    """The engine prompt must teach the Advisor what the correspondence lines
    in the dump are FOR (parallels across the person's situations), that
    family-level matches are coarse and need substance-checking, and that the
    family names stay behind the vocabulary rules."""

    def test_score_reading_explains_correspondence_lines(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        assert "Cross-exploration correspondences" in SYSTEM_PROMPT
        # Both line formats the dump emits are named
        assert "Also woven into Nexus" in SYSTEM_PROMPT
        assert "Same opposition family" in SYSTEM_PROMPT
        # Coarseness warning: verify substance before drawing the parallel
        assert "collisions are common" in SYSTEM_PROMPT
        # Family names follow the speech rules, not raw disclosure
        assert "How You Speak rules above govern" in SYSTEM_PROMPT

    def test_scoped_render_keeps_guidance(self):
        """Counsel-mode dumps are single-nexus, but the person can toggle
        heads — the score-reading section is shared, so the guidance must
        survive the scoped render too."""
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        scoped = system_prompt(
            ["anchor", "explore", "sync", "inspect_node", "read_digest", "discard"],
            scoped_nexus_hash="abc1234",
        )
        assert "Cross-exploration correspondences" in scoped


# --- Fail loudly on taxonomy coercion ----------------------------------------


class TestTaxonomyFailsLoudly:
    """Unknown/missing taxonomy anchorings must raise, never silently coerce.

    The old fallbacks (unknown branch → Fidelity/Earth, missing meaning →
    Fidelity leaves, unparseable branch → Apex row) mis-anchored statements
    invisibly. Since the cross-nexus dump states "Same opposition family
    (Branch)" facts derived from these URIs, a coerced anchor now produces
    confident false correspondences — hence loud failure.
    """

    def test_location_dto_rejects_unknown_branch(self):
        import pytest
        from pydantic import ValidationError

        from dialectical_framework.concerns.statement_classification import \
            TaxonomyLocationDto

        with pytest.raises(ValidationError):
            TaxonomyLocationDto(
                taxonomy_type="systemic",
                domain="General",
                branch="Strengths",  # SWOT vocabulary, not in the taxonomy
                leaf="Strengths",
                reasoning="r",
            )

    def test_location_dto_rejects_unknown_domain_and_type(self):
        import pytest
        from pydantic import ValidationError

        from dialectical_framework.concerns.statement_classification import \
            TaxonomyLocationDto

        with pytest.raises(ValidationError):
            TaxonomyLocationDto(
                taxonomy_type="systemic",
                domain="Astrology",
                branch="Integrity",
                leaf="Cohesion",
                reasoning="r",
            )
        with pytest.raises(ValidationError):
            TaxonomyLocationDto(
                taxonomy_type="zodiac",
                domain="General",
                branch="Integrity",
                leaf="Cohesion",
                reasoning="r",
            )

    def test_location_dto_rejects_family_branch_mismatch(self):
        import pytest
        from pydantic import ValidationError

        from dialectical_framework.concerns.statement_classification import \
            TaxonomyLocationDto

        with pytest.raises(ValidationError):
            TaxonomyLocationDto(
                taxonomy_type="elemental",
                domain="General",
                branch="Integrity",  # systemic branch under elemental type
                leaf="Cohesion",
                reasoning="r",
            )
        with pytest.raises(ValidationError):
            TaxonomyLocationDto(
                taxonomy_type="systemic",
                domain="General",
                branch="Fire",  # element under systemic type
                leaf="Activation",
                reasoning="r",
            )

    def test_lookup_antithesis_raises_on_missing_or_junk_meaning(self):
        import pytest

        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC

        with pytest.raises(ValueError, match="no meaning URI"):
            SC.lookup_antithesis_meaning(_FakeStatement(""))
        with pytest.raises(ValueError, match="no known taxonomy branch"):
            SC.lookup_antithesis_meaning(_FakeStatement("dx://garbage/uri"))

    def test_lookup_aspect_raises_instead_of_apex_fallback(self):
        import pytest

        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC

        junk = _FakeStatement("dx://taxonomy/System(General.v1)/Viability/Nope/X")
        with pytest.raises(ValueError, match="no known taxonomy branch"):
            SC.lookup_aspect_meaning(junk, "T+")
        with pytest.raises(ValueError, match="no known taxonomy branch"):
            SC.lookup_aspect_apex(junk, "T+")

    def test_lookup_thesis_meaning_raises_on_unknown_vocab(self):
        import pytest

        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC

        with pytest.raises(ValueError, match="Unknown taxonomy branch"):
            SC.lookup_thesis_meaning(branch="Strengths")
        with pytest.raises(ValueError, match="Unknown taxonomy domain"):
            SC.lookup_thesis_meaning(branch="Integrity", domain="Astrology")

    def test_build_meaning_uri_raises_without_location(self):
        import pytest

        from dialectical_framework.concerns.statement_classification import \
            StatementClassification

        classifier = StatementClassification()
        classifier._statement = "Trust"
        with pytest.raises(ValueError, match="no taxonomy location"):
            classifier._build_meaning_uri(False, None)

    def test_simple_paths_still_short_circuit(self):
        """Simple statements never touch the taxonomy — no new raises there."""
        from dialectical_framework.concerns.statement_classification import \
            StatementClassification as SC

        simple = _FakeStatement("dx://taxonomy/Simple")
        simple.is_simple = True
        assert SC.lookup_antithesis_meaning(simple) == "dx://taxonomy/Simple"
        assert SC.lookup_aspect_meaning(simple, "T+") == "dx://taxonomy/Simple"
        assert SC.lookup_aspect_apex(simple, "T+") == "Simple"


class TestDecisionReadiness:
    """Decision lifecycle prompt contract: the recording ceremony is
    consented in BOTH modes, the section renders only when the tool is
    wired, and the prompt's reading guidance stays in lockstep with what
    _dump_decisions actually renders."""

    def _unscoped(self) -> str:
        from dialectical_framework.agents.advisor.system_prompts import \
            SYSTEM_PROMPT

        return " ".join(SYSTEM_PROMPT.split())

    def _scoped(self) -> str:
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        rendered = system_prompt(
            tool_names=[
                "anchor", "sync", "inspect_node", "read_digest", "discard",
                "explore", "deepen", "record_decision",
            ],
            scoped_nexus_hash="abc1234",
        )
        return " ".join(rendered.split())

    def test_never_silent_recording_in_both_modes(self):
        """Decisions are a consented artifact even for the silent Advisor —
        the explicit-confirmation contract must survive both renders."""
        for prompt in (self._unscoped(), self._scoped()):
            assert "Record ONLY on their explicit confirmation" in prompt
            assert "NEVER recorded silently" in prompt

    def test_section_renders_only_when_tool_wired(self):
        from dialectical_framework.agents.advisor.system_prompts import \
            system_prompt

        without_tool = system_prompt(
            tool_names=["anchor", "sync", "inspect_node", "read_digest", "discard"]
        )
        assert "Decision Readiness" not in without_tool
        assert "record_decision" not in without_tool
        assert "{decision" not in without_tool  # no leaked placeholders

    def test_cross_references_render_when_wired(self):
        """The conditional cross-references (eager filter note, arc step 6,
        speech exception) must actually appear in the wired unscoped render —
        the unwired absence alone doesn't prove the wiring works."""
        prompt = self._unscoped()
        assert (
            "a candidate tension that could not change the choice is "
            "acknowledged, not mapped" in prompt
        )
        assert "6. When the conversation is decision-shaped" in prompt
        assert "One exception: the decision record" in prompt
        assert "{decision" not in prompt  # all placeholders consumed

    def test_discard_docs_mention_decisions_in_both_modes(self):
        """record_decision's doc routes retraction through discard — the
        discard docs must agree it accepts decisions (in-prompt consistency),
        and must carry the consent rule for them."""
        from dialectical_framework.agents.advisor.system_prompts import \
            _TOOL_DOCS

        for key in ("discard", "discard_scoped"):
            doc = " ".join(_TOOL_DOCS[key].split())
            assert "decision" in doc.lower(), key
            assert "confirm" in doc.lower(), key

    def test_convergence_mechanics_present(self):
        prompt = self._unscoped()
        # Discrimination test
        assert "would the person lean differently" in prompt
        # Saturation: honest claim + the exhaustiveness distinction
        assert "collapsing into tensions already mapped" in prompt
        assert 'Never claim "we found all tensions"' in prompt
        # Pre-commit ritual is soft: the person's wish outranks it
        assert "their wish outranks the ritual" in prompt
        # Re-audit
        assert "does this discriminate against what was decided?" in prompt

    def test_score_reading_lockstep_with_dump_wording(self):
        """The prompt's reading guidance must name what _dump_decisions
        actually renders (role labels, ground-status flag, Validation line)."""
        import dialectical_framework.agents.advisor.system_prompts as sp

        reading = " ".join(sp._SCORE_READING.split())
        # Role labels as rendered by _dump_decisions
        assert "accepted cost" in reading
        assert "adopted pathway" in reading
        # Ground-status flag wording
        assert "since discarded" in reading
        # Validation line semantics
        assert "Validation" in reading

    def test_dump_wording_matches_prompt_expectations(self):
        """Inverse lock: the shared role vocabulary and renderer emit the
        labels the prompt teaches. DECISION_GROUND_ROLES is the single owner
        (graph/rendering.py) consumed by _dump_decisions, _inspect_decision,
        and the coherence-check prompt — locking it locks all three."""
        import inspect as _inspect

        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.rendering import (
            DECISION_GROUND_ROLES, decision_ground_line)

        assert DECISION_GROUND_ROLES == {
            "accepted_cost": "accepted cost",
            "adopted_pathway": "adopted pathway",
        }
        ground_src = _inspect.getsource(decision_ground_line)
        assert "since discarded" in ground_src

        # Both renderers consume the shared helper (no local label dicts).
        dump_src = _inspect.getsource(DialecticalContext._dump_decisions)
        assert "decision_ground_line" in dump_src
        assert "# Decisions" in dump_src
        from dialectical_framework.agents.orchestrator.tools import inspect_node
        inspect_src = _inspect.getsource(inspect_node._inspect_decision)
        assert "decision_ground_line" in inspect_src

    def test_tool_doc_defers_replacement_to_discard(self):
        """record_decision's doc must route retraction through the standard
        discard tool, not promise its own supersede machinery."""
        from dialectical_framework.agents.advisor.system_prompts import \
            _TOOL_DOCS

        doc = " ".join(_TOOL_DOCS["record_decision"].split())
        assert "use `discard`" in doc
        assert "EXPLICITLY confirmed" in doc

    def test_accepted_cost_asks_for_the_chosen_side_minus(self):
        """A cost is a RISK, so the ground is the chosen side's minus.

        Read the tetrad plainly: T is what is said, T+ its implied goal, T- its
        risk; A is the opponent's say, A+ the obligation falling on the T-sayer,
        A- the risk that follows. The role previously asked for the unchosen
        side's A+ — a correctly-selected A+, being an obligation, reads as a
        task. The bench duly recorded remedies as costs ("Diversify client
        relationships before any separation") in 4 of 6 A+ -grounded runs, the
        re-audit had no risk to reassure from, and the judge marked the
        commitment turn down on `earned_confidence` against a prose-journal
        baseline in all six cells.

        Asserted on both renders and on the tool schema, because the LLM sees
        the two independently and one drifting from the other reintroduces the
        bug in exactly the way that is hardest to spot.
        """
        from dialectical_framework.agents.advisor.system_prompts import \
            _TOOL_DOCS

        doc = " ".join(_TOOL_DOCS["record_decision"].split())
        assert "CHOSEN side's `-` aspect" in doc
        # The mis-selection must be named, not merely the right answer stated.
        assert "never a cost" in doc
        assert "unchosen side's `+`" not in doc

        for prompt in (self._unscoped(), self._scoped()):
            assert "CHOSEN side's `-` aspect" in prompt
            # The ritual must elicit a price, not a to-do, or the right hash is
            # never in hand to pass.
            assert "chosen side's own `-` aspect" in prompt
            assert "is a remedy" in prompt

    def test_materialised_risk_is_not_the_risk_resurfacing(self):
        """The re-audit must not file an EVENT as the cost it already priced.

        Measured, and it is the failure mode a sharper record invites: once
        `accepted_cost` named a real risk ("the accounts may follow him"),
        `decision-strong-r4` had 2 of 3 A2 runs answer "the customer called
        yesterday, 40% of revenue on a six-week clock" by reassuring from the
        record — one of them verbatim that this changed "the shape of the risk,
        not the decision itself". A2's wobble accuracy fell to 4/6 against
        A1.7's 6/6. A probability that became a dated fact with a named
        counterparty is new information however familiar its topic, and the
        decision was priced on the probability.
        """
        for prompt in (self._unscoped(), self._scoped()):
            assert "has MATERIALISED is not that risk resurfacing" in prompt
            # The observed rationalisation, named so the model can catch itself.
            assert 'the shape of the risk, not the decision' in prompt
            # Reassurance is bounded, not merely discouraged.
            assert "no more than what was priced" in prompt

    def test_naming_the_record_openly_does_not_expose_its_schema(self):
        """The record's CONTENT is theirs; its storage is not.

        The machinery ban has one carve-out — the decision record is named
        openly — and it bounded only the naming, not what about the record may
        be said. Measured at weak tier (`claim1-weak-r2`): one A2 wobble turn
        told the person "the validation on your decision already failed… it
        said the stance 'directly contradicts the adopted pathway ground'" and
        later "the T pathway holds". The judge marked it down on
        `conversational_fit` ("references to 'recorded stance', 'validation…
        failed', 'T pathway' break the conversational frame") — a
        non-inferiority dimension the framework must not lose. Grounds, roles
        and the coherence verdict are internals; what they IMPLY is counsel.

        Unscoped only: the scoped render's preamble governs vocabulary
        (the person knows the structural terms there), and prompt-only arms
        have no record schema to leak.
        """
        prompt = " ".join(self._unscoped().split())
        assert "how it is stored is not" in prompt
        # The specific internals observed leaking, named so the ban is checkable.
        assert "never of its grounds, roles, pathways or validation verdict" in prompt
        # Paired example — the same content spoken two ways, since "don't say
        # it" without "say this instead" suppresses the counsel too.
        assert "machinery wearing plain words" in prompt

    def test_decision_mode_closes_on_pathways_not_tensions_alone(self):
        """Pruning tensions must not read as permission to stop building.

        Measured at weak tier (`claim1-weak-r1`): all 6 A2 runs stopped at
        `anchor` — 1-2 perspectives, zero explores — where the strong tier
        explored in 4 of 6. Decision mode's discrimination test tells the model
        what NOT to map, and nothing told it to develop what it kept, so the
        closing turn counselled from a single tension. The record then asks for
        an "adopted_pathway" ground that no explore had produced, and the trap
        version of the choice has no arrangement to be read from.

        The rule is method, not machinery: a prompt-only arm owes the same
        reasoning, so `bench/arms.py` rewrites the tool verb rather than
        dropping the paragraph (asserted there).
        """
        for prompt in (self._unscoped(), self._scoped()):
            prompt = " ".join(prompt.split())
            assert "closes on pathways, not on tensions alone" in prompt
            # Names the mistake, not just the instruction.
            assert "permission to stop building" in prompt
            # The threshold, because "enough structure" is what stalls it.
            assert "Two mapped tensions are enough to explore" in prompt

    def test_ritual_asks_once_and_never_gates_the_record(self):
        """A soft ritual pressed twice is a hard gate on the person's own call.

        Measured at weak tier (`claim1-weak-r1`): handed "That's the decision,
        final… I'm not reopening this one. Go ahead and write this down as my
        decision", one A2 run answered with "I need you to answer the question
        directly… Can you name that cost and own it?" and recorded nothing.
        The section already said the person's wish outranks the ritual, but it
        illustrated declining only with the polite "just record it" — a firm
        refusal to be tested did not pattern-match, so the model read its own
        unanswered question as an outstanding precondition.

        Both renders, because a prompt-only arm can withhold a written record
        for the same reason.
        """
        for prompt in (self._unscoped(), self._scoped()):
            prompt = " ".join(prompt.split())
            assert "Ask once." in prompt
            # Declining is illustrated by the refusals actually observed, not
            # by the one polite phrasing.
            assert "that's the decision, not a maybe" in prompt
            assert "I'm not reopening this one" in prompt
            assert "does not have to be polite" in prompt
            # The stakes of pressing again, named as the failure it is.
            assert "gate you are holding" in prompt

    def test_reading_the_record_back_is_not_speaking_as_them(self):
        """"In their own words" invited the model to take the person's voice.

        Measured at weak tier: one A2 commit turn replied entirely in the
        user's first person — "I'm paying the premium now to get him out
        cleanly… Record it: Buy out cofounder now" — handing the person a
        script of their own decision. An A1 run drifted the same way, so the
        correction belongs in the shared section, not in tool prose.
        """
        for prompt in (self._unscoped(), self._scoped()):
            prompt = " ".join(prompt.split())
            assert "Their words, YOUR voice" in prompt
            assert "not speaking as them" in prompt
            # The observed surface form, so the model can catch itself.
            assert '"I\'m buying him out"' in prompt

    def test_prose_summary_is_not_a_substitute_for_recording(self):
        """A formatted "Decision:" reply is a message, not a record.

        Measured at weak tier: 4 of 6 A2 runs never called `record_decision`,
        and 2 of those had already written the full record out in prose under
        headings — question, stance, accepted cost, pathway. The ceremony
        promises the person an artifact they can be held to later; prose alone
        leaves them believing in a record that does not exist and the re-audit
        with nothing to reassure from.

        Unscoped/scoped only: the paragraph names the tool, so the bench's
        `_strip_tool_prose` drops it for prompt-only arms — which record in
        prose legitimately, and must not be told that is a failure.
        """
        for prompt in (self._unscoped(), self._scoped()):
            prompt = " ".join(prompt.split())
            assert "Writing the record out is not recording it" in prompt
            assert "is a MESSAGE" in prompt
            # Not an either/or — the reply AND the call.
            assert "not alternatives" in prompt

    def test_the_obligation_reaches_the_text_nearest_the_call(self):
        """The prose rule alone lost to the tool doc at call time.

        `test_prose_summary_is_not_a_substitute_for_recording` above locks the
        Decision Readiness paragraph, and it WAS rendering — yet the failure
        recurred at weak tier (`claim2-weak-r2`, 4 of 6 A2 runs closed in prose
        with `tool_calls == []`). The paragraph sits ~100 lines below the tool
        list, while the text the model actually reads when deciding whether to
        call — the docstring and `_TOOL_DOCS` entry — carried only the
        PROHIBITION ("never call this silently") with no counterpart obligation.
        On a weak model that asymmetry reads as "when in doubt, don't call".

        So: when a prompt rule governs whether to CALL something, the tool doc
        has to carry it too. Both surfaces are asserted because they drift
        independently.
        """
        from dialectical_framework.agents.advisor.tools.record_decision import (
            build_record_decision,
        )

        docstring = " ".join((build_record_decision().__doc__ or "").split())
        # The prohibition must survive — the ceremony is still consent-first.
        assert "Never call this silently or speculatively" in docstring
        # ...but no longer alone.
        assert "OBLIGES the call" in docstring
        assert "SAME turn" in docstring

        from dialectical_framework.agents.advisor import system_prompts as sp

        tool_doc = " ".join(sp._TOOL_DOCS["record_decision"].split())
        assert "OBLIGES this call" in tool_doc
        assert "same turn" in tool_doc

    def test_the_explore_threshold_reaches_its_tool_doc_too(self):
        """The same lesson, applied to the other half of the closing.

        `claim2-weak-r2`: 5 of 6 live A2 runs never called `explore`, so the
        closing turn had no pathway to adopt and no trap version of the choice
        to name — measured as 0/6 records carrying an `adopted_pathway` ground.
        "Two mapped tensions are enough to explore" was stated only in Decision
        Readiness; the explore tool doc said "use once tensions exist" without
        naming the threshold, leaving "enough structure" to the model's
        judgement at exactly the point where it stalls.

        Unscoped only: the scoped variant is already inside an exploration.
        """
        from dialectical_framework.agents.advisor import system_prompts as sp

        tool_doc = " ".join(sp._TOOL_DOCS["explore"].split())
        assert "Two mapped tensions are already enough" in tool_doc
        # Names the consequence, so the threshold is not read as arbitrary.
        assert "closes with no pathway" in tool_doc

    def test_coherence_auditor_reads_accepted_cost_as_a_risk(self):
        """The re-audit's own auditor is a third surface teaching the role.

        It is the one that can catch the failure after the fact: a rationale
        resting on "we will diversify the accounts first" has scheduled the
        cost's avoidance rather than accepted it, and an auditor told the cost
        is "what the unchosen side offered" has no basis to say so.
        """
        from dialectical_framework.concerns import decision_coherence_check

        prompt = " ".join(decision_coherence_check.SYSTEM_PROMPT.split())
        assert "the risk the chosen side carries" in prompt
        assert "is a remedy" in prompt
        assert "unchosen side offered" not in prompt

    def test_accepted_cost_tool_schema_matches_the_prompt(self):
        """The Field description is a second, independent prompt surface."""
        from dialectical_framework.concerns.record_decision import GroundLink

        description = GroundLink.model_fields["role"].description
        assert "CHOSEN side's overdevelopment aspect" in description
        assert "never a plus" in description

    def test_named_options_paragraph_in_both_modes(self):
        """Named-options guidance lives in _DECISION_READINESS, so it must
        survive both renders: options anchored in the person's own words,
        alternatives lazy (demand-driven), weak/distancing opposition read
        as 'the fork is not where the tension is'."""
        for prompt in (self._unscoped(), self._scoped()):
            assert "Named options" in prompt
            assert "Anchor the pair as it comes" in prompt
            # Lazy, demand-driven alternatives — never eager enumeration
            assert "ask which pull matters most" in prompt
            assert "only when their reactions show" in prompt
            # Weak-opposition branch keeps BOTH options in the graph
            assert "the fork is not where the tension is" in prompt
            assert "anchor each option alone" in prompt

    def test_named_options_reconciled_with_discrimination_test(self):
        """Alternative tetrads must be exempted from the discrimination test
        explicitly — competing map-more/map-less signals in one section is
        the failure mode this clause exists to prevent."""
        prompt = self._unscoped()
        assert (
            "readings of the choice itself, not new candidate tensions"
            in prompt
        )

    def test_anchor_doc_alternative_tetrad_line_in_both_modes(self):
        """The repeat-call mechanism the named-options paragraph relies on
        must stay documented in both anchor variants, WITH the
        identical-wording caveat (a rephrase creates a new polarity, not a
        sibling tetrad — statement hashing is content-addressed)."""
        from dialectical_framework.agents.advisor.system_prompts import \
            _TOOL_DOCS

        for key in ("anchor", "anchor_scoped"):
            doc = " ".join(_TOOL_DOCS[key].split())
            assert "Call again with the same T-A" in doc, key
            assert "identical wording" in doc, key
            assert "a rephrase plants a new tension" in doc, key

    def test_classifier_treats_options_as_complex(self):
        """Keystone for the decision use case: named options / courses of
        action must classify COMPLEX (both prompt sites), or the whole
        option-pair tetrad loses taxonomy anchoring. Behavioral coverage:
        tests/test_options_classification_real_llm.py (--real-llm)."""
        import dialectical_framework.concerns.statement_classification as sc

        # System prompt: criterion + a course-of-action example
        assert "courses of action" in sc.SYSTEM_PROMPT
        assert "Take the startup offer" in sc.SYSTEM_PROMPT
        # Per-call classification prompt carries the same rule
        concern = sc.StatementClassification()
        concern._statement = "Take the startup offer"
        concern._text = ""
        prompt = concern._classification_prompt()
        assert "course of action" in prompt

    def test_named_options_reading_promotion(self):
        """A resonant reading (Perspective.intent, the persisted axis) is an
        anchor candidate — the lazy materialization path from reading-string
        to first-class Polarity. Must survive both renders."""
        for prompt in (self._unscoped(), self._scoped()):
            assert "Each perspective names its reading" in prompt
            assert "it is itself an anchor candidate" in prompt

    def test_anchor_report_carries_mode(self):
        """The named-options paragraph tells the Advisor to read 'a low mode
        (drifting/absence rather than negation)' from the anchor result at
        call time — IntroducePolarity must actually put mode in the polarity
        artifacts and summary, or the instruction points at nothing."""
        import inspect as _inspect

        from dialectical_framework.agents.analyst.skills import \
            introduce_polarity as ip

        src = _inspect.getsource(ip.IntroducePolarity)
        assert '"mode": classification.mode_value' in src
        assert "Mode: {classification.mode_value" in src


class TestAdvisoryPersonaBoundary:
    """App/engine boundary for advisory personas (systemic-map gap: personas
    were entirely untested). Advisory personas carry ONLY voice — the engine
    owns framework terminology and the decision-convergence mechanics, and a
    persona that re-states either would fuse into a contradicting or
    double-specified system prompt."""

    ADVISORY_PERSONAS = [
        "COUNSELOR_PERSONA",
        "STRATEGIC_ADVISOR_PERSONA",
        "COACH_PERSONA",
        "MEDIATOR_PERSONA",
        "SPARRING_PARTNER_PERSONA",
        "DECISION_PARTNER_PERSONA",
    ]

    @pytest.mark.parametrize("name", ADVISORY_PERSONAS)
    def test_no_framework_terminology(self, name):
        """The engine's How You Speak bans framework terms unless the preamble
        grants disclosure — an advisory persona must not smuggle them in."""
        import re

        from dialectical_framework.agents import apps

        persona = getattr(apps, name)
        # Unambiguous framework-only vocabulary. Everyday polysemous words
        # ("perspective", "transformation", "synthesis") are deliberately not
        # banned — COUNSELOR_PERSONA legitimately "offers perspectives".
        banned = [
            "thesis", "antithesis", "polarity", "tetrad", "nexus",
            "dialectic", "wheel",
        ]
        for term in banned:
            assert not re.search(rf"(?<![\w+]){term}", persona, re.I), (
                f"{name} carries framework term '{term}' — personas are "
                "voice-only; terminology disclosure belongs to Navigator-side "
                "preambles."
            )

    @pytest.mark.parametrize("name", ADVISORY_PERSONAS)
    def test_no_engine_mechanics_respecification(self, name):
        """Convergence mechanics (discrimination test, saturation, the
        recording ceremony, re-audit) are engine behavior — a persona tunes
        how convergence FEELS, never re-specifies the mechanics."""
        from dialectical_framework.agents import apps

        persona = getattr(apps, name).lower()
        for term in ["discrimination", "saturation", "re-audit",
                     "record_decision", "ceremony"]:
            assert term not in persona, (
                f"{name} re-specifies engine mechanics ('{term}') — "
                "the Decision Readiness section owns these."
            )

    def test_decision_partner_is_convergence_forward(self):
        """The decision-partner persona's contract: the decision (not the
        exploration) is the deliverable, a formed leaning flips the persona's
        phase from opening to testing (NOT a register in the Explorer↔Advisor
        toggle sense — no head swap, just the persona's own arc), and settled
        choices are defended against wobble but reopened on real news."""
        from dialectical_framework.agents.apps import DECISION_PARTNER_PERSONA

        text = " ".join(DECISION_PARTNER_PERSONA.split())
        assert "decision partner" in text.lower()
        # The frame: establish and hold the decision.
        assert "what exactly is being decided" in text
        # Phase shift on a forming leaning (within one persona).
        assert "stop opening the space and start testing the choice" in text
        # Vocabulary guard: "register" is the Explorer↔Advisor toggle's term.
        assert "register" not in text.lower()
        # Post-decision stance: keeper, not prosecutor; wobble vs news.
        assert "keeper of their decisions" in text
        assert "genuinely new information" in text
        # The product is the person's own confidence, not obedience.
        assert "not because you told them what to do" in text
