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
        from dialectical_framework.agents.apps import NAVIGATOR_ADVANCED_MODE_APP

        assert (
            "overrides Contextual Vocabulary and Presentation Defaults" in NAVIGATOR_ADVANCED_MODE_APP
        )
        assert "does not apply here" in NAVIGATOR_ADVANCED_MODE_APP

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
        following the NAVIGATOR_ADVANCED_MODE_APP override precedent."""
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
        assert "analysis thread" in p


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
            "analysis thread" in joined
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

    def test_scoped_advisor_signals_exploration_view(self):
        """The counsel-mode preamble already narrates switching back to the
        technical exploration view — lock that phrase."""
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        joined = " ".join(EXPLORATION_ADVISOR_APP.split())
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

        return system_prompt(
            tool_names=[
                "anchor", "sync", "inspect_node",
                "read_digest", "discard", "explore",
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


class TestExplorationAdvisorColdStart:
    """EXPLORATION_ADVISOR_APP must not presuppose shared history or that the
    user built the exploration — the constructor explicitly supports
    messages=None on an existing (possibly ingest-built or shared) nexus."""

    def test_history_is_ground_truth_not_assumed(self):
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        joined = " ".join(EXPLORATION_ADVISOR_APP.split())
        assert "take the history you actually see as the ground truth" in joined
        assert "never assume shared memories" in joined
        # authorship is not presupposed either
        assert "built this exploration themselves — they worked through" \
            not in joined
        assert "don't address them as its author" in joined

    def test_switch_back_hedged_on_host_affordance(self):
        """Mirror of the Explorer's 'if the application offers' hedge — the
        counsel head must not promise a UI affordance the host may not have."""
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        joined = " ".join(EXPLORATION_ADVISOR_APP.split())
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
        """NAVIGATOR_ADVANCED_MODE_APP explicitly overrides the vocabulary rules for experts."""
        from dialectical_framework.agents.apps import NAVIGATOR_ADVANCED_MODE_APP

        assert "Nexus" in NAVIGATOR_ADVANCED_MODE_APP


class TestExplorationAdvisorApp:
    """EXPLORATION_ADVISOR_APP is the counsel-mode preamble of the
    Explorer<->Advisor toggle. It MUST be composed on NAVIGATOR_APP (Navigator
    territory: same vocabulary contract, perspective detection, score
    presentation) — not written from scratch — and it must mandate
    transparent, consented mutation of the user-built exploration."""

    def test_composed_on_default_app(self):
        from dialectical_framework.agents.apps import (NAVIGATOR_APP,
                                                       EXPLORATION_ADVISOR_APP)

        assert EXPLORATION_ADVISOR_APP.startswith(NAVIGATOR_APP)
        assert "## Advisory Register" in EXPLORATION_ADVISOR_APP

    def test_grants_terminology_disclosure_for_engine_hatch(self):
        """The engine's terminology escape hatch keys on the preamble
        granting disclosure — the section must exist."""
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        assert "## Terminology Disclosure" in EXPLORATION_ADVISOR_APP

    def test_disclosure_defers_to_default_app_nexus_rule(self):
        """Disclosure does NOT unlock 'Nexus' — NAVIGATOR_APP's exploration
        vocabulary still governs (unlike NAVIGATOR_ADVANCED_MODE_APP, which unlocks it)."""
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        idx = EXPLORATION_ADVISOR_APP.find("## Terminology Disclosure")
        disclosure = EXPLORATION_ADVISOR_APP[idx:]
        assert '"Nexus" stays internal' in disclosure

    def test_mandates_transparent_mutation(self):
        """Counsel mode must never grow or prune the user-built exploration
        silently — ask first, announce after."""
        from dialectical_framework.agents.apps import EXPLORATION_ADVISOR_APP

        assert "Never grow or prune their exploration silently" in (
            EXPLORATION_ADVISOR_APP
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
    """Minimal stand-in for the static lookups (touch only .meaning/.is_simple)."""

    def __init__(self, meaning: str) -> None:
        self.meaning = meaning
        self.is_simple = False


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
