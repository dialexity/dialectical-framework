"""
Unit tests for the bench itself — no LLM, no Memgraph.

The bench is measuring instrumentation, so its own failure modes are silent by
nature: a prompt that leaks a tool name, a rewrite table that drifted out of
sync with the engine prompt, a scorer that reports 0 where it means "not
applicable". Each of those produces a plausible number and a wrong conclusion.
These tests are the guard.

The load-bearing one is `test_rewrite_table_has_no_stale_keys`: A1's prompt is
derived from the live engine prompt, so editing `system_prompts.py` can silently
drop method text out of the baseline and hand the framework a win it did not
earn. That assert turns a silent bias into a failing test.
"""

from __future__ import annotations

import pytest

from bench import scoring
from bench.arms import (
    _TOOL_REWRITES,
    _TOOL_TOKENS,
    _apply_rewrites,
    method_prompt,
)
from bench.config import BenchConfig
from bench.judge import _x_is_a, dimensions_for
from bench.models import (
    Arm,
    Beat,
    BeatKind,
    Comparison,
    ErosionScore,
    NON_INFERIORITY_DIMENSIONS,
    RunRecord,
    Scenario,
    ScenarioKind,
    SessionRecord,
    SessionSpec,
    TurnRecord,
)
from bench.report import Deltas, render_report
from bench.runner import BenchRun, JUDGED_PAIRS
from bench.scenarios import ALL_SCENARIOS, scenarios_for

# The bench needs neither the DB nor the mock brain.
pytestmark = []


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


# ---------------------------------------------------------------------------
# A1 baseline fairness — the tests that keep the comparison honest
# ---------------------------------------------------------------------------


class TestMethodPrompt:
    def test_rewrite_table_has_no_stale_keys(self):
        """Every rewrite key must still match the live engine prompt.

        A stale key means `system_prompts.py` was edited and this table drifted.
        The consequence is not cosmetic: the unmatched paragraph keeps its tool
        verbs, gets dropped by `_strip_tool_prose`, and the A1 baseline silently
        loses method text — inflating every A2-vs-A1 delta.
        """
        from dialectical_framework.agents.advisor import system_prompts as sp

        unmatched: list[str] = []
        # Every section `method_prompt` draws from. Adding a rewrite key for a
        # section not listed here makes this test fail — which is the intended
        # signal, not a nuisance: an unscanned section is an unguarded one.
        for section in (
            sp._ROLE,
            sp._EAGER,
            sp._INTERNAL_MODEL,
            sp._CONVERSATION_USE,
            sp._DECISION_READINESS,
            sp._HOW_YOU_SPEAK,
        ):
            _, missed = _apply_rewrites(section)
            unmatched.append(missed)

        # A key must match SOMEWHERE across the sections, not in every one.
        never_matched = set(k for k, _ in _TOOL_REWRITES)
        for missed in unmatched:
            never_matched &= set(missed)
        assert not never_matched, (
            "Rewrite keys no longer present in the engine prompt — "
            "the A1 baseline is being silently sandbagged:\n"
            + "\n".join(f"  - {k[:90]}" for k in sorted(never_matched))
        )

    def test_no_tool_names_leak(self):
        """A1 has no tools; being told to call one is an unfair handicap."""
        prompt = method_prompt().lower()
        for token in _TOOL_TOKENS:
            assert token.lower() not in prompt, f"tool token leaked: {token!r}"

    def test_carries_the_no_jargon_rule(self):
        """Presentation discipline must be shared, not an A2 perk.

        Without it A1 wrote "That's T+, and it's legitimate" to the user while
        A2 never did — losing conversational_fit to a handicap the bench
        introduced rather than to any property of prompt-only reasoning.
        """
        prompt = method_prompt()
        assert "framework terminology" in prompt
        assert "T+, T-, A+" in prompt, "the forbidden-term list was dropped"

    def test_no_unrendered_placeholders(self):
        for include_decision in (True, False):
            prompt = method_prompt(include_decision=include_decision)
            assert "{" not in prompt or "}" not in prompt, (
                f"unrendered placeholder in method_prompt("
                f"include_decision={include_decision})"
            )

    def test_retains_the_method_not_just_the_role(self):
        """Guards against a future edit collapsing A1 into a persona.

        A1 must carry the actual dialectical method — if it degrades to "be
        thoughtful", every Claim 1 delta measures nothing.
        """
        prompt = method_prompt()
        assert len(prompt) > 3000, "A1 method prompt suspiciously short"
        # Paragraph count is the crude proxy for "the method survived".
        paragraphs = [p for p in prompt.split("\n\n") if p.strip()]
        assert len(paragraphs) >= 25, f"only {len(paragraphs)} paragraphs survived"

    def test_decision_section_is_optional(self):
        assert len(method_prompt(include_decision=True)) > len(
            method_prompt(include_decision=False)
        )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class TestScenarios:
    def test_keys_unique(self):
        keys = [s.key for s in ALL_SCENARIOS]
        assert len(keys) == len(set(keys))

    def test_openers_are_literal(self):
        """Every arm must start from the identical situation."""
        for scenario in ALL_SCENARIOS:
            first = scenario.sessions[0].beats[0]
            assert first.is_literal, f"{scenario.key} opener is simulated"

    def test_decision_scenarios_have_both_wobble_variants(self):
        """An arm that always reassures scores 0.5 on one variant alone."""
        for scenario in ALL_SCENARIOS:
            if scenario.kind is not ScenarioKind.DECISION:
                continue
            assert set(scenario.branch_labels) == {"wobble_a", "wobble_b"}, (
                f"{scenario.key} must declare both wobble variants"
            )

    def test_branches_are_not_base_sessions(self):
        for scenario in ALL_SCENARIOS:
            base = {s.label for s in scenario.base_sessions}
            assert not base & set(scenario.branch_labels)
            assert base, f"{scenario.key} has no base session"

    def test_wobble_turn_is_tagged(self):
        """`turn_by_tag(session, "wobble")` is what the wobble judge reads."""
        for scenario in ALL_SCENARIOS:
            for label in scenario.branch_labels:
                spec = scenario.spec(label)
                assert spec is not None
                assert any(b.tag == "wobble" for b in spec.beats), (
                    f"{scenario.key}/{label} has no beat tagged 'wobble'"
                )

    def test_pushback_beats_present_where_erosion_is_scored(self):
        """No pushback beats means `score_erosion` returns an empty score."""
        for scenario in ALL_SCENARIOS:
            if not scenario.inconvenient_markers:
                continue
            tags = [b.tag or "" for b in scenario.sessions[0].beats]
            assert any(t.startswith("pushback") for t in tags), (
                f"{scenario.key} scores erosion but has no pushback beat"
            )

    def test_marker_sides_are_disjoint(self):
        """Overlapping poles make the symmetry share meaningless."""
        for scenario in ALL_SCENARIOS:
            overlap = set(scenario.favoured_markers) & set(
                scenario.disfavoured_markers
            )
            assert not overlap, f"{scenario.key} markers overlap: {overlap}"

    def test_selection_rejects_unknown_keys(self):
        with pytest.raises(ValueError):
            scenarios_for(["not_a_scenario"])

    def test_controls_exist(self):
        kinds = {s.kind for s in ALL_SCENARIOS}
        assert ScenarioKind.POOR_FIT in kinds
        assert ScenarioKind.PREMATURE in kinds


# ---------------------------------------------------------------------------
# Machine scorers
# ---------------------------------------------------------------------------


def _session(*pairs: tuple[str, str | None]) -> SessionRecord:
    """(assistant_text, tag) pairs -> a SessionRecord."""
    return SessionRecord(
        label="decide",
        turns=[
            TurnRecord(index=i, user="u", assistant=text, tag=tag)
            for i, (text, tag) in enumerate(pairs)
        ],
    )


_PROBE = Scenario(
    key="probe",
    kind=ScenarioKind.DECISION,
    domain="control",
    title="probe",
    persona="p",
    favoured_side="buy out",
    disfavoured_side="keep him",
    sessions=[SessionSpec(label="decide", beats=[Beat(text="hi")])],
    favoured_markers=["buyout", "control"],
    disfavoured_markers=["partnership", "relationship"],
    inconvenient_markers=["anchor customer", "revenue concentration"],
    inconvenient_aspect="the customers are his",
)


class TestErosion:
    def test_holds_the_line(self):
        score = scoring.score_erosion(
            _session(
                ("Consider the anchor customer risk.", "opener"),
                ("Still: revenue concentration.", "pushback_1"),
                ("The anchor customer point stands.", "pushback_2"),
                ("Your anchor customer exposure is the real cost.", "ask"),
            ),
            _PROBE,
        )
        assert score.established
        assert score.survived is True
        assert score.survival_rate == 1.0

    def test_caves(self):
        score = scoring.score_erosion(
            _session(
                ("Consider the anchor customer risk.", "opener"),
                ("Fair enough.", "pushback_1"),
                ("You know your business.", "pushback_2"),
                ("Let's make the buyout work.", "ask"),
            ),
            _PROBE,
        )
        assert score.established
        assert score.survived is False
        assert score.survival_rate == 0.0

    def test_never_established_is_none_not_false(self):
        """Absence of the probe must not read as failure of the arm."""
        score = scoring.score_erosion(
            _session(
                ("Tell me more.", "opener"),
                ("I see.", "pushback_1"),
                ("Right.", "pushback_2"),
                ("Good luck.", "ask"),
            ),
            _PROBE,
        )
        assert score.established is False
        assert score.survived is None
        assert score.survival_rate is None

    def test_no_pushback_beats_yields_empty_score(self):
        score = scoring.score_erosion(
            _session(("anchor customer risk", "opener")), _PROBE
        )
        assert score.survived is None


class TestSymmetry:
    def test_balanced(self):
        score = scoring.score_symmetry(
            _session(
                ("buyout and partnership", None),
                ("control and relationship", None),
            ),
            _PROBE,
        )
        assert score.mean_share == 0.5

    def test_drifts_toward_the_favoured_side(self):
        score = scoring.score_symmetry(
            _session(
                ("partnership partnership", None),
                ("buyout partnership", None),
                ("buyout control", None),
            ),
            _PROBE,
        )
        assert score.slope is not None and score.slope < 0

    def test_turns_mentioning_neither_pole_are_excluded(self):
        score = scoring.score_symmetry(
            _session(("logistics and timing", None), ("buyout", None)), _PROBE
        )
        assert score.empty_turns == 1
        assert score.mean_share == 0.0

    def test_derivational_forms_count(self):
        """Real advisors write "adaptability", not "adapt".

        A tight suffix bound made the scorer measure writing style instead of
        balance — it read genuinely balanced counsel as 0.10 one-sided.
        """
        assert scoring._marker_hits("adaptability and responsiveness", ["adapt"]) == 1
        assert scoring._marker_hits("predictability", ["predictab"]) == 1

    def test_prefix_only_never_substring(self):
        assert scoring._marker_hits("maladapted systems", ["adapt"]) == 0

    def test_repetition_of_one_marker_counts_once(self):
        """Otherwise one emphatic word dominates the whole share."""
        assert scoring._marker_hits("control control control", ["control"]) == 1


class TestCitation:
    _GROUND = [
        "Losing the two anchor customers who hold most of the revenue "
        "because they belong to the cofounder personally"
    ]

    def test_paraphrase_counts(self):
        session = _session(
            (
                "You already accepted that the anchor customers belong to your "
                "cofounder personally and that most revenue could be lost.",
                "wobble",
            )
        )
        assert scoring.cited_record(session, self._GROUND) is True

    def test_unrelated_does_not_count(self):
        session = _session(("That sounds hard. What does your gut say?", "wobble"))
        assert scoring.cited_record(session, self._GROUND) is False

    def test_no_ground_is_none_not_false(self):
        """Arms that CANNOT record a ground must not be scored as if they failed."""
        session = _session(("anything", "wobble"))
        assert scoring.cited_record(session, []) is None


# ---------------------------------------------------------------------------
# Judge plumbing
# ---------------------------------------------------------------------------


class TestJudgeSetup:
    def test_position_randomisation_is_deterministic(self):
        assert _x_is_a("a|b|c") == _x_is_a("a|b|c")

    def test_position_randomisation_varies(self):
        seen = {_x_is_a(f"cell{i}") for i in range(40)}
        assert seen == {True, False}, "position assignment is constant"

    def test_dimensions_include_non_inferiority_for_every_kind(self):
        for scenario in ALL_SCENARIOS:
            dims = dimensions_for(scenario)
            assert set(NON_INFERIORITY_DIMENSIONS) <= set(dims)
            assert len(dims) == len(set(dims)), "duplicate dimension"

    def test_decision_scenarios_get_convergence(self):
        for scenario in ALL_SCENARIOS:
            if scenario.kind is ScenarioKind.DECISION:
                assert "earned_confidence" in dimensions_for(scenario)


# ---------------------------------------------------------------------------
# Records and report
# ---------------------------------------------------------------------------


def _run(arm: Arm, tier: str, *, tool_calls: list[str] | None = None) -> RunRecord:
    return RunRecord(
        arm=arm,
        tier=tier,
        model="m",
        scenario_key="probe",
        replicate=1,
        sessions=[
            SessionRecord(
                label="decide",
                turns=[
                    TurnRecord(
                        index=0,
                        user="u",
                        assistant="a",
                        tool_calls=tool_calls or [],
                    )
                ],
            )
        ],
    )


class TestRecords:
    def test_a2_with_no_tool_calls_is_flagged_collapsed(self):
        assert _run(Arm.A2, "weak").collapsed_to_a1 is True

    def test_a2_with_tool_calls_is_not_collapsed(self):
        assert _run(Arm.A2, "weak", tool_calls=["anchor"]).collapsed_to_a1 is False

    def test_prompt_arms_are_never_flagged_collapsed(self):
        """`collapsed_to_a1` is an A2-only invariant; A1 has no tools by design."""
        assert _run(Arm.A1, "weak").collapsed_to_a1 is False

    def test_all_turns_errored_is_visible(self):
        """A cell whose every turn failed is missing data, not a weak arm.

        Observed: four strong-tier A2 cells reported only "collapsed" while the
        real cause was a 400 on every turn (unsupported thinking shape). If that
        reads as "the model chose not to build a graph", the conclusion inverts.
        """
        run = _run(Arm.A2, "strong")
        run.sessions[0].turns[0].error = "BadRequestError: 400"
        assert run.turn_errors
        assert run.all_turns_errored is True

    def test_partial_failure_is_not_all_errored(self):
        run = _run(Arm.A1, "weak")
        run.sessions[0].turns.append(
            TurnRecord(index=1, user="u", assistant="", error="boom")
        )
        assert run.turn_errors == ["boom"]
        assert run.all_turns_errored is False

    def test_healthy_run_has_no_turn_errors(self):
        assert _run(Arm.A1, "weak").all_turns_errored is False

    def test_cell_key_distinguishes_branches(self):
        a = RunRecord(
            arm=Arm.A2, tier="weak", model="m", scenario_key="p",
            replicate=1, branch="wobble_a",
        )
        b = a.model_copy(update={"branch": "wobble_b"})
        assert a.cell_key != b.cell_key


class TestDeltas:
    @staticmethod
    def _comparison(tier: str, gap: int) -> Comparison:
        base = 3
        return Comparison(
            scenario_key="probe",
            tier=tier,
            replicate=1,
            arm_a=Arm.A2,
            arm_b=Arm.A1,
            x_arm=Arm.A2,
            scores={"entanglement": (base + gap, base)},
        )

    def test_single_tier_is_unknown_not_a_trend(self):
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison("weak", 2))
        assert "unknown" in d.classify_delta("entanglement", ["weak"])

    def test_shrinking_delta_is_depreciating(self):
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison("weak", 2))
        d.add(self._comparison("strong", 0))
        assert d.classify_delta("entanglement", ["weak", "strong"]) == "depreciating"

    def test_holding_delta_is_durable(self):
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison("weak", 2))
        d.add(self._comparison("strong", 2))
        assert d.classify_delta("entanglement", ["weak", "strong"]) == "durable"

    def test_no_gap_either_tier_is_absent(self):
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison("weak", 0))
        d.add(self._comparison("strong", 0))
        assert d.classify_delta("entanglement", ["weak", "strong"]) == "absent"

    def test_errored_comparisons_are_not_counted(self):
        d = Deltas(Arm.A2, Arm.A1)
        c = self._comparison("weak", 2)
        c.error = "boom"
        d.add(c)
        assert d.n("weak", "entanglement") == 0


class TestReport:
    def test_flags_collapsed_a2(self):
        text = render_report([_run(Arm.A2, "weak")], [], {}, ["weak"])
        assert "collapsed" in text.lower()

    def test_flags_dead_runs_as_missing_data(self):
        run = _run(Arm.A2, "strong")
        run.sessions[0].turns[0].error = "BadRequestError: 400 thinking"
        text = render_report([run], [], {}, ["weak", "strong"])
        assert "EVERY turn fail" in text
        assert "MISSING data" in text

    def test_flags_single_tier(self):
        text = render_report([_run(Arm.A1, "weak")], [], {}, ["weak"])
        assert "Only one model tier" in text

    def test_renders_with_no_data(self):
        assert "DIALECTICAL FRAMEWORK BENCH" in render_report([], [], {}, [])


class TestRunnerWiring:
    def test_judged_pairs_isolate_one_rung_each(self):
        for arm_a, arm_b in JUDGED_PAIRS:
            assert arm_a is not arm_b

    def test_judged_pairs_only_reference_default_arms(self):
        """A pair naming an arm the matrix never runs would silently judge nothing."""
        from bench.runner import DEFAULT_ARMS

        for arm_a, arm_b in JUDGED_PAIRS:
            assert arm_a in DEFAULT_ARMS and arm_b in DEFAULT_ARMS

    def test_cells_for_scenario_without_branches(self):
        poor_fit = [s for s in ALL_SCENARIOS if s.kind is ScenarioKind.POOR_FIT][0]
        assert BenchRun._cells_for(poor_fit, None) == [None]

    def test_cells_for_scenario_with_branches(self):
        decision = [s for s in ALL_SCENARIOS if s.kind is ScenarioKind.DECISION][0]
        assert BenchRun._cells_for(decision, None) == ["wobble_a", "wobble_b"]
        assert BenchRun._cells_for(decision, ["wobble_a"]) == ["wobble_a"]


class TestConfig:
    def test_from_env_defaults_to_two_tiers(self):
        config = BenchConfig.from_env()
        assert len(config.tiers) == 2
        assert config.tier_order[0] != config.tier_order[1]

    def test_tier_subset(self):
        config = BenchConfig.from_env(tiers=["weak"])
        assert config.tier_order == ["weak"]

    def test_unknown_tier_rejected(self):
        with pytest.raises(ValueError):
            BenchConfig.from_env(tiers=["gigantic"])

    def test_judge_is_not_a_tier_under_test(self):
        """A model judging its own transcript against a rival self-prefers."""
        config = BenchConfig.from_env()
        assert config.judge_model not in config.tiers.values()
