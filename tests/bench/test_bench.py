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
from bench.driver import BenchDriver
from bench.judge import _x_is_a, dimensions_for
from bench.models import (
    Arm,
    Beat,
    BeatKind,
    Comparison,
    ErosionScore,
    MachineScores,
    NON_INFERIORITY_DIMENSIONS,
    Particular,
    ParticularScore,
    RunRecord,
    Scenario,
    ScenarioKind,
    SessionRecord,
    SessionSpec,
    TurnRecord,
    WobbleScore,
)
from bench.report import Deltas, position_bias, render_report
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

    def test_ground_line_boilerplate_is_stripped(self):
        """Grounds arrive as `decision_ground_line` output, not raw text.

        Counting "accepted cost" and the hash as content stems dilutes the
        denominator, so a short ground could never reach the threshold.
        """
        session = _session(
            (
                "You already accepted that the anchor customers belong to your "
                "cofounder personally and that most revenue could be lost.",
                "wobble",
            )
        )
        line = "- accepted cost: [[a1b2c3d]] " + self._GROUND[0]
        assert scoring.cited_record(session, [line]) is True

    def test_no_ground_is_none_not_false(self):
        """Arms that CANNOT record a ground must not be scored as if they failed."""
        session = _session(("anything", "wobble"))
        assert scoring.cited_record(session, []) is None


def _turns(
    *pairs: tuple[str, str], label: str = "decide", memory: str | None = None
) -> SessionRecord:
    """(user_text, assistant_text) pairs -> a SessionRecord.

    Separate from `_session` because the particulars scorer reads BOTH sides:
    who said a fact is the whole discriminator, and a helper that stubs the
    user turn as "u" cannot express the test.
    """
    return SessionRecord(
        label=label,
        carryover_in=memory,
        turns=[
            TurnRecord(index=i, user=user, assistant=assistant)
            for i, (user, assistant) in enumerate(pairs)
        ],
    )


_PARTICULARS_PROBE = Scenario(
    key="probe_particulars",
    kind=ScenarioKind.DECISION,
    domain="control",
    title="probe",
    persona="p",
    favoured_side="buy out",
    disfavoured_side="keep him",
    sessions=[SessionSpec(label="decide", beats=[Beat(text="hi")])],
    particulars=[
        Particular(label="his 45%", forms=["45%", "forty-five percent"]),
        Particular(label="60% of revenue", forms=["60%", "sixty percent"]),
        Particular(label="three-week holiday", forms=["three-week holiday"]),
    ],
)


class TestCarriedParticulars:
    """The probe the grounding lane exists for.

    Measured by hand before this existed (`claim2-weak-r5`: the graph ledger
    carried 0 of 15 case particulars at 28 mean words against A1.7's prose
    journal at 11 of 15) — which is exactly the kind of number that cannot be
    re-checked after a fix. Hence a scorer.
    """

    def test_a_fact_only_memory_could_supply_counts(self):
        base = _turns(("He owns 45% and took a three-week holiday.", "Noted."))
        returning = _turns(
            ("I'm second-guessing myself.", "You told me he holds 45%."),
            label="wobble_a",
        )
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.stated == ["his 45%", "three-week holiday"]
        assert score.eligible == ["his 45%", "three-week holiday"]
        assert score.carried == ["his 45%"]
        assert score.carry_rate == 0.5

    def test_restated_facts_leave_the_denominator(self):
        """Echoing back what the person just said is not memory.

        The wobble openers re-state some facts verbatim. Counting those would
        hand every arm — including the ones that carry nothing at all — a score
        for reading the transcript in front of it.
        """
        base = _turns(("He owns 45%.", "Noted."))
        returning = _turns(
            ("What about his 45%?", "Yes — his 45% is the crux."),
            label="wobble_a",
        )
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.stated == ["his 45%"]
        assert score.restated == ["his 45%"]
        assert score.eligible == []
        # Nothing was left to remember, so the probe does not apply: None, never
        # 0.0, which would read as total forgetting.
        assert score.carry_rate is None

    def test_a_fact_the_person_never_stated_is_not_scored(self):
        """The simulator improvises DIRECTED beats and may never elicit a fact.

        Fixing the denominator to the scenario's full list would score an arm
        down for forgetting something nobody told it.
        """
        base = _turns(("He owns 45%.", "Noted."))
        returning = _turns(("Worried.", "His 45%."), label="wobble_a")
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert "60% of revenue" not in score.stated
        assert "60% of revenue" not in score.eligible

    def test_an_assistant_invention_is_not_the_persons_particular(self):
        """Only USER turns establish a fact.

        An arm that introduces "60% of revenue" itself and then repeats it next
        session has remembered its own inference, which says nothing about
        whether the person's case survived.
        """
        base = _turns(("He's been coasting.", "Perhaps 60% of revenue is his?"))
        returning = _turns(("Worried.", "That 60% is the risk."), label="wobble_a")
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.stated == []
        assert score.carry_rate is None

    def test_a_paraphrased_form_still_counts(self):
        """"sixty percent" and "60%" are one fact; paraphrase is not forgetting."""
        base = _turns(("They're 60% of revenue.", "Noted."))
        returning = _turns(
            ("Worried.", "Those accounts are sixty percent of your revenue."),
            label="wobble_a",
        )
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.carried == ["60% of revenue"]

    def test_percent_forms_match_at_all(self):
        """Regression: the erosion matcher cannot see a trailing "%".

        `_marker_hits` anchors on `\\b{stem}\\w{0,8}\\b`, which scores zero
        against text containing "60%" verbatim. Percentages and equity splits
        are precisely the particulars this probe is about, so reusing that
        helper would have produced a permanent, silent 0/N for every arm.
        """
        assert scoring._marker_hits("they are 60% of revenue", ["60%"]) == 0
        assert scoring._form_present("they are 60% of revenue", "60%")

    def test_line_wrapped_multiword_form_still_matches(self):
        assert scoring._form_present("a three-week\n  holiday", "three-week holiday")

    def test_memory_and_use_are_scored_separately(self):
        """The pair is the diagnosis; one number would hide which fix applies.

        Here the artifact HELD the fact and the reply ignored it — a prompt
        defect. A grounding lane cannot fix that, and a single combined score
        would send the fix to the wrong layer.
        """
        base = _turns(("He owns 45% and they're 60% of revenue.", "Noted."))
        returning = _turns(
            ("Worried.", "Let's think about the relationship risk."),
            label="wobble_a",
            memory="Grounded in: he holds 45%; two accounts are 60% of revenue.",
        )
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert sorted(score.in_memory) == ["60% of revenue", "his 45%"]
        assert score.carried == []
        assert score.memory_rate == 1.0
        assert score.carry_rate == 0.0

    def test_an_arm_with_no_artifact_scores_memory_as_none(self):
        """A0/A1 carry nothing by construction — absence, not failure.

        The same trap `cited_record` avoids: reporting 0.00 for an arm that has
        no memory reads as a memory that forgot everything.
        """
        base = _turns(("He owns 45%.", "Noted."))
        returning = _turns(("Worried.", "Tell me more."), label="wobble_a")
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.had_memory is False
        assert score.memory_rate is None
        assert score.carry_rate == 0.0

    def test_scenario_without_particulars_scores_nothing(self):
        bare = _PARTICULARS_PROBE.model_copy(update={"particulars": []})
        score = scoring.score_particulars(
            [_turns(("45%", "a"))], _turns(("b", "45%")), bare
        )
        assert score.eligible == [] and score.carry_rate is None


class TestParticularsAreWellFormed:
    def test_only_multi_session_scenarios_declare_particulars(self):
        """Carry-over needs a boundary to cross.

        Inside one session every arm holds the transcript, so a number scored
        there measures nothing and would dilute the per-arm mean.
        """
        for scenario in ALL_SCENARIOS:
            if scenario.particulars:
                assert scenario.branch_labels, (
                    f"{scenario.key} declares particulars but has no returning "
                    "session to carry them into"
                )

    def test_every_decision_scenario_declares_particulars(self):
        """The claim-2 arm is where the grounding lane is measured."""
        for scenario in ALL_SCENARIOS:
            if scenario.kind is ScenarioKind.DECISION:
                assert scenario.particulars, f"{scenario.key} has no particulars"

    def test_declared_particulars_actually_appear_in_the_script(self):
        """A form no literal beat contains can only be elicited by improvisation.

        Not fatal — the persona holds facts the simulator reveals under
        pressure — but a particular absent from BOTH the literal beats and the
        persona is a typo that would silently sit at 0/N forever.
        """
        for scenario in ALL_SCENARIOS:
            script = " ".join(
                [scenario.persona]
                + [b.text for s in scenario.sessions for b in s.beats]
            ).lower()
            for particular in scenario.particulars:
                assert any(
                    " ".join(f.lower().split()) in " ".join(script.split())
                    for f in particular.forms
                ), f"{scenario.key}: {particular.label!r} appears nowhere in the script"

    def test_no_form_is_a_bare_number_or_common_word(self):
        """Forms are matched as substrings, so an ambiguous one is a false positive.

        "34" matches "340" and every date; "double" is ordinary advisor
        vocabulary ("double down") and also sits in `favoured_markers`. A loose
        form inflates every arm equally, which does not look like a bug — it
        looks like all the arms remembering, and it destroys the metric's whole
        job of separating them.
        """
        for scenario in ALL_SCENARIOS:
            for particular in scenario.particulars:
                for form in particular.forms:
                    # A percentage or split ("45%") is short but unambiguous —
                    # the unit is what disambiguates it, and those are the
                    # particulars this probe is most about.
                    if "%" in form:
                        continue
                    assert len(form) >= 4, f"{scenario.key}: {form!r} is too short"
                    assert not form.replace(".", "").replace(
                        ",", ""
                    ).isdigit(), f"{scenario.key}: {form!r} is a bare number"

    def test_particular_forms_do_not_collide_with_pole_markers(self):
        """A form that is also pole vocabulary measures development, not memory.

        The two probes must be able to disagree: erosion/symmetry are about
        which SIDE got airtime, this is about whether the person's specifics
        survived. Sharing a term makes them agree by construction.
        """
        for scenario in ALL_SCENARIOS:
            poles = {
                m.lower()
                for m in scenario.favoured_markers + scenario.disfavoured_markers
            }
            for particular in scenario.particulars:
                collisions = {f.lower() for f in particular.forms} & poles
                assert not collisions, f"{scenario.key}: {collisions}"

    def test_labels_are_unique_per_scenario(self):
        """Labels are the report's keys; a duplicate silently merges two facts."""
        for scenario in ALL_SCENARIOS:
            labels = [p.label for p in scenario.particulars]
            assert len(labels) == len(set(labels)), scenario.key


# ---------------------------------------------------------------------------
# Judge plumbing
# ---------------------------------------------------------------------------


class TestJudgeSetup:
    def test_position_randomisation_is_deterministic(self):
        assert _x_is_a("a|b|c") == _x_is_a("a|b|c")

    def test_position_randomisation_varies(self):
        seen = {_x_is_a(f"cell{i}") for i in range(40)}
        assert seen == {True, False}, "position assignment is constant"

    def test_ordinal_makes_the_split_exact(self):
        """Hashing alone balances only in EXPECTATION, which is not enough.

        Measured: whichever arm sat in the Y slot scored +0.35 of a 5-point step
        higher (288 scores, decision-strong-r3). The same run drew an 8/4 X/Y
        split per pair, so that bias did not cancel — it entered the deltas as a
        per-arm effect. Alternating by ordinal makes the split exact, which is
        what actually cancels it.
        """
        key = "probe|strong|1|A2|A1|decide"
        sides = [_x_is_a(key, ordinal=i) for i in range(12)]
        assert sides.count(True) == sides.count(False) == 6

    def test_split_is_exact_when_the_comparison_key_varies(self):
        """The runner's ACTUAL call pattern: a different key every comparison.

        This is the test that was missing. The first `ordinal` version hashed
        the starting side from the per-comparison key, so each call re-rolled
        its own start and parity-flipping it balanced nothing:
        `decision-strong-r4` drew 10/2 and reported an 8-of-12-dimension A2 win
        with a +0.48 Y-slot bias sitting on A2's side of 10 comparisons. Holding
        the key fixed (the test above) cannot see that, because the bug is
        precisely that the key moves.
        """
        pair = "A2|A1.7"
        sides = [
            _x_is_a(
                f"cofounder_equity|strong|{rep}|A2|A1.7|{session}",
                ordinal=i,
                pair_key=pair,
            )
            for i, (rep, session) in enumerate(
                (rep, session)
                for rep in (1, 2, 3)
                for session in ("decide", "wobble_a", "decide", "wobble_b")
            )
        ]
        assert sides.count(True) == sides.count(False) == 6, (
            "X/Y split is uneven under varying comparison keys — the starting "
            f"side is not pair-stable: {sides}"
        )

    def test_ordinal_layout_is_still_scenario_dependent(self):
        """The hash must still choose the STARTING side, or every pair would be
        laid out identically ("A always first at ordinal 0") and position bias
        would align with arm order across the whole matrix."""
        starts = {_x_is_a(f"cell{i}", ordinal=0) for i in range(40)}
        assert starts == {True, False}

    def test_pair_key_alone_decides_the_starting_side(self):
        """Two comparisons of the same pair at the same ordinal must agree even
        when their comparison keys differ — that is what makes the alternation
        an alternation rather than twelve independent coin flips."""
        pair = "A2|A1.7"
        assert _x_is_a("a|1|decide", ordinal=0, pair_key=pair) == _x_is_a(
            "b|3|wobble_b", ordinal=0, pair_key=pair
        )

    def test_ordinal_assignment_stays_deterministic(self):
        key = "probe|strong|1|A2|A1|decide"
        assert _x_is_a(key, ordinal=3) == _x_is_a(key, ordinal=3)

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


def _run(
    arm: Arm,
    tier: str,
    *,
    tool_calls: list[str] | None = None,
    tool_outcomes: list[str] | None = None,
) -> RunRecord:
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
                        tool_outcomes=tool_outcomes or [],
                    )
                ],
            )
        ],
    )


class TestCostGroundPosition:
    """A cost is a MINUS. The scorer must not credit anything else.

    This inverted: it used to accept T+/A+, which scored the framework's own
    defect as a success — `decision-strong-r3` reported 4/6 grounded "on a
    +aspect" while the recorded texts were remedies ("Diversify client
    relationships before any separation"). A plus is a goal (T+) or an
    obligation (A+); neither is a price paid.
    """

    def test_minus_aspect_counts_as_confronting_the_cost(self):
        for position in ("A-", "T-"):
            run = _run(Arm.A2, "weak")
            run.accepted_cost_positions = [position]
            assert run.costs_grounded_on_risk is True, position

    def test_plus_aspects_do_not_count(self):
        """The regression this class now guards: a prescription is not a cost."""
        for position in ("A+", "T+"):
            run = _run(Arm.A2, "weak")
            run.accepted_cost_positions = [position]
            assert run.costs_grounded_on_risk is False, position

    def test_tension_and_neutral_grounds_do_not_count(self):
        for position in ("Perspective", "Polarity", "Wheel", "T", "A", "Statement"):
            run = _run(Arm.A2, "weak")
            run.accepted_cost_positions = [position]
            assert run.costs_grounded_on_risk is False, position

    def test_no_ground_at_all_is_not_grounded(self):
        assert _run(Arm.A2, "weak").costs_grounded_on_risk is False

    def test_one_good_ground_among_several_counts(self):
        run = _run(Arm.A2, "weak")
        run.accepted_cost_positions = ["Perspective", "A-"]
        assert run.costs_grounded_on_risk is True

    def test_a_multi_position_statement_counts_if_any_is_a_minus(self):
        """`_ground_position` joins positions with "/" when one Statement sits
        at several across perspectives (e.g. "A/A-"), so the check must see
        through that rather than string-comparing the whole label."""
        run = _run(Arm.A2, "weak")
        run.accepted_cost_positions = ["A/A-"]
        assert run.costs_grounded_on_risk is True


class TestDecisionRecordCompleteness:
    """A cost is half a record. The pathway is the other half.

    The cost is the price confronted; the adopted pathway is the recipe for
    living with it. The wobble re-audit's reassurance ("here is what you
    adopted for this") needs both, so a record carrying only one must not score
    as a complete one. It used to: `adopted_pathway` was never read at all,
    which made a decision closed without `explore` — a decision that cannot
    have a pathway, since a recipe IS a pathway — indistinguishable from a
    complete record.
    """

    def test_cost_without_pathway_is_incomplete(self):
        run = _run(Arm.A2, "weak")
        run.accepted_cost_positions = ["A-"]
        run.accepted_cost_grounds = ["- accepted cost: [[beef1]] Accounts may follow"]
        assert run.costs_grounded_on_risk is True
        assert run.decision_record_complete is False

    def test_pathway_without_a_risk_grounded_cost_is_incomplete(self):
        """A recipe for a price that was never named is not a record either."""
        run = _run(Arm.A2, "weak")
        run.accepted_cost_positions = ["Perspective"]
        run.accepted_cost_grounds = ["- accepted cost: [[dead1]] Control"]
        run.adopted_pathway_grounds = ["- adopted pathway: [[cafe1]] T1- -> A2+"]
        assert run.decision_record_complete is False

    def test_both_halves_present_is_complete(self):
        run = _run(Arm.A2, "weak")
        run.accepted_cost_positions = ["T-"]
        run.accepted_cost_grounds = ["- accepted cost: [[beef1]] Accounts may follow"]
        run.adopted_pathway_grounds = ["- adopted pathway: [[cafe1]] T1- -> A2+"]
        assert run.decision_record_complete is True

    def test_report_separates_the_two_halves(self):
        """The counts must be readable apart, so a reader can see WHICH half is
        going missing rather than only that completeness is low."""
        cost_only = _run(Arm.A2, "weak", tool_calls=["anchor"])
        cost_only.decision_hashes = ["beef1"]
        cost_only.accepted_cost_grounds = ["- accepted cost: [[beef1]] Accounts go"]
        cost_only.accepted_cost_positions = ["A-"]

        text = render_report([cost_only], [], {}, ["weak", "strong"])
        assert "runs with adopted_pathway ground: 0/1" in text
        assert "COMPLETE records (risk-grounded cost + pathway): 0/1" in text

        full = _run(Arm.A2, "weak", tool_calls=["anchor", "explore"])
        full.decision_hashes = ["beef1"]
        full.accepted_cost_grounds = ["- accepted cost: [[beef1]] Accounts go"]
        full.accepted_cost_positions = ["A-"]
        full.adopted_pathway_grounds = ["- adopted pathway: [[cafe1]] T1- -> A2+"]

        text = render_report([full], [], {}, ["weak", "strong"])
        assert "runs with adopted_pathway ground: 1/1" in text
        assert "COMPLETE records (risk-grounded cost + pathway): 1/1" in text


class TestRecordlessWobbleA:
    """Variant (a) without a record measures the CEREMONY, not the re-audit.

    Measured in `claim2-weak-r2`: all three A2 `wobble_a` cells recorded zero
    decisions and all three called "reopen" — 3/6 paired accuracy, -2.67 on both
    convergence and decision_closure. Read at face value that is the framework
    losing the exact job it exists for; the truth was that the closing ceremony
    never fired, so there was nothing to reassure from and "reopen" was the only
    honest answer available.
    """

    @staticmethod
    def _a_variant(**kwargs) -> RunRecord:
        run = _run(Arm.A2, "weak", tool_calls=["anchor"])
        run.branch = "wobble_a"
        for k, v in kwargs.items():
            setattr(run, k, v)
        return run

    def test_a_variant_without_a_decision_is_flagged(self):
        assert self._a_variant().wobble_a_without_a_record is True

    def test_a_variant_with_a_decision_is_not_flagged(self):
        run = self._a_variant(decision_hashes=["beef1"])
        assert run.wobble_a_without_a_record is False

    def test_b_variant_is_never_flagged(self):
        """(b) asks the assistant to REOPEN — no record is needed to be right."""
        run = _run(Arm.A2, "weak", tool_calls=["anchor"])
        run.branch = "wobble_b"
        assert run.wobble_a_without_a_record is False

    def test_prompt_arms_are_never_flagged(self):
        """A1.7 cannot record by design; flagging it would invent a defect."""
        run = _run(Arm.A1_7, "weak")
        run.branch = "wobble_a"
        assert run.wobble_a_without_a_record is False

    def test_report_names_the_cause_and_keeps_the_score(self):
        run = self._a_variant()
        scores = MachineScores(
            wobble=WobbleScore(variant="a", classification="reopen", correct=False)
        )
        text = render_report([run], [], {run.cell_key: scores}, ["weak", "strong"])
        assert "NO recorded" in text
        assert "no record to reassure from" in text
        # The wrong call must still be visible: hiding it would blind the
        # collapse tripwire.
        assert " X " in text


class TestProseOnlyDecision:
    """"Write it down" answered with headings and no tool call.

    The framework's own rule ("writing the record out is not recording it")
    failing to bind, and the direct cause of a missing-record row. Measured in
    `claim2-weak-r2`: the person said "Go ahead and write that down as the
    decision" and the reply produced a bolded "Your Decision:" block, an
    itemised list of accepted prices, and a sequence — with `tool_calls == []`.
    """

    @staticmethod
    def _commit_run(arm: Arm, assistant: str, tool_calls: list[str]) -> RunRecord:
        return RunRecord(
            arm=arm,
            tier="weak",
            model="m",
            scenario_key="cofounder_equity",
            replicate=1,
            sessions=[
                SessionRecord(
                    label="decide",
                    turns=[
                        TurnRecord(
                            index=0,
                            user="Go ahead and write that down as the decision.",
                            assistant=assistant,
                            tag="commit",
                            tool_calls=tool_calls,
                        )
                    ],
                )
            ],
        )

    def test_decision_in_prose_with_no_call_is_flagged(self):
        run = self._commit_run(
            Arm.A2,
            "**Your Decision: Buy out your cofounder.** You're paying these prices:",
            [],
        )
        assert run.prose_only_decision is True

    def test_recording_on_the_commit_turn_is_not_flagged(self):
        run = self._commit_run(
            Arm.A2, "**Your Decision: Buy out your cofounder.**", ["record_decision"]
        )
        assert run.prose_only_decision is False

    def test_a_reply_that_does_not_close_is_not_flagged(self):
        """Not closing at all is a different defect with a different fix."""
        run = self._commit_run(Arm.A2, "What would change your mind here?", [])
        assert run.prose_only_decision is False

    def test_prompt_arms_are_never_flagged(self):
        run = self._commit_run(Arm.A1_7, "**Your Decision: Buy him out.**", [])
        assert run.prose_only_decision is False

    def test_report_names_it_as_the_cause(self):
        run = self._commit_run(
            Arm.A2, "**Your Decision: Buy out your cofounder.**", []
        )
        text = render_report([run], [], {}, ["weak", "strong"])
        assert "closed a decision in PROSE" in text


class TestReadDecisions:
    """`_read_decisions` must split grounds by ROLE, not lump them together.

    Both roles render through the same `decision_ground_line`, so a reader
    cannot tell them apart downstream — the split has to happen here.
    """

    class _Ground:
        def __init__(self, text: str) -> None:
            self._text = text
            self.short_hash = "cafe123"
            self.discarded = None

        def __str__(self) -> str:  # what decision_ground_line renders
            return self._text

    class _Rel:
        def __init__(self, role: str) -> None:
            self.role = role

    class _Grounds:
        def __init__(self, pairs) -> None:
            self._pairs = pairs

        def all(self):
            return self._pairs

    def _fake_repo(self, pairs):
        outer = self

        class _Decision:
            short_hash = "dec1234"
            hash = "dec1234full"
            grounds = outer._Grounds(pairs)

        class _Repo:
            def find_all_active(self):
                return [_Decision()]

        return _Repo

    def test_roles_land_in_separate_lists(self, monkeypatch):
        pairs = [
            (self._Ground("Accounts may follow him out"), self._Rel("accepted_cost")),
            (self._Ground("T1- -> A2+ rebalancing"), self._Rel("adopted_pathway")),
        ]
        monkeypatch.setattr(
            "bench.driver.DecisionRepository", self._fake_repo(pairs)
        )
        hashes, costs, positions, pathways = BenchDriver._read_decisions()

        assert hashes == ["dec1234"]
        assert len(costs) == 1 and "Accounts may follow" in costs[0]
        assert len(pathways) == 1 and "rebalancing" in pathways[0]
        # The cost's position is still tracked; a pathway has no position slot
        # because a pathway is never a cost — it is what you do about one.
        assert len(positions) == 1

    def test_a_cost_with_no_pathway_yields_an_empty_pathway_list(self, monkeypatch):
        """The shape a decision closed without `explore` produces."""
        pairs = [
            (self._Ground("Accounts may follow him out"), self._Rel("accepted_cost")),
        ]
        monkeypatch.setattr(
            "bench.driver.DecisionRepository", self._fake_repo(pairs)
        )
        _hashes, costs, _positions, pathways = BenchDriver._read_decisions()
        assert costs and pathways == []

    def test_unknown_roles_are_ignored(self, monkeypatch):
        """A new ground role must not silently count as either half."""
        pairs = [(self._Ground("something else"), self._Rel("supporting_evidence"))]
        monkeypatch.setattr(
            "bench.driver.DecisionRepository", self._fake_repo(pairs)
        )
        _hashes, costs, _positions, pathways = BenchDriver._read_decisions()
        assert costs == [] and pathways == []


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

    def test_gaps_are_attributable_to_a_session(self):
        """A pooled delta cannot say WHERE it comes from.

        Concentrated in one session it is a targeted defect; spread evenly it is
        a property of the arm — opposite fixes. In decision-strong-r3 A2's
        earned_confidence gap was three times larger in `decide` than in the
        wobble follow-up, and recovering that required re-deriving judging order
        by hand because the label was never recorded.
        """
        d = Deltas(Arm.A2, Arm.A1)
        decide = self._comparison("strong", -3)
        decide.session_label = "decide"
        wobble = self._comparison("strong", 1)
        wobble.session_label = "wobble_a"
        d.add(decide)
        d.add(wobble)

        assert d.sessions() == ["decide", "wobble_a"]
        assert d.session_gap("decide", "entanglement") == -3
        assert d.session_gap("wobble_a", "entanglement") == 1
        # The pooled figure still averages both, and on its own would read as a
        # mild deficit rather than one localised to the commitment turn.
        assert d.gap("strong", "entanglement") == -1


class TestPositionBias:
    """The judge scores the Y slot higher regardless of content.

    Measured at +0.35 of a 5-point step over 288 scores in decision-strong-r3,
    with Y winning 16 of 24 comparisons. This is bias, not variance: replicates
    do not remove it, so it has to be measured and the split kept even.
    """

    @staticmethod
    def _comparison(x_arm: Arm, y_score: int) -> Comparison:
        """A comparison where the Y slot always scores `y_score` and X scores 3,
        whichever arm happens to be in Y."""
        a_is_x = x_arm is Arm.A2
        pair = (3, y_score) if a_is_x else (y_score, 3)
        return Comparison(
            scenario_key="probe",
            tier="strong",
            replicate=1,
            arm_a=Arm.A2,
            arm_b=Arm.A1,
            x_arm=x_arm,
            scores={"entanglement": pair},
        )

    def test_measures_the_y_slot_advantage(self):
        bias, n, split = position_bias(
            [self._comparison(Arm.A2, 5), self._comparison(Arm.A1, 5)]
        )
        assert bias == 2.0
        assert n == 2
        assert split == {"A2": 1, "A1": 1}

    def test_an_even_split_cancels_the_bias_in_the_delta(self):
        """Why the `ordinal` fix works: with the split exact, a pure position
        effect contributes nothing to the per-arm gap."""
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison(Arm.A2, 5))
        d.add(self._comparison(Arm.A1, 5))
        assert d.gap("strong", "entanglement") == 0

    def test_an_uneven_split_leaks_bias_into_the_delta(self):
        """The r3 situation: 2:1 in favour of one arm sitting in Y, so the
        judge's slot preference shows up as an arm advantage."""
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison(Arm.A1, 5))
        d.add(self._comparison(Arm.A1, 5))
        d.add(self._comparison(Arm.A2, 5))
        assert d.gap("strong", "entanglement") > 0

    def test_errored_comparisons_are_ignored(self):
        c = self._comparison(Arm.A2, 5)
        c.error = "judge failed"
        bias, n, split = position_bias([c])
        assert bias is None and n == 0 and split == {}


class TestCarryoverIsRecorded:
    """The artifact each arm was HANDED must land on the record.

    Without it the two carryovers cannot be compared: A1.7's journal is text
    while A2's `graph_summary` is `perspectives=N`, and a count says nothing
    about whether the person's case is inside. That mismatch is how a hand-read
    came to compare one arm's artifact against the other arm's replies.
    """

    @staticmethod
    async def _session(monkeypatch, arm: Arm, **kwargs):
        """Run `_run_session` for a prompt arm with the LLM plumbing stubbed."""
        driver = BenchDriver(None, simulator_model="sim")

        async def _beats(self, arm_obj, simulator, beats, **_kw):
            return [TurnRecord(index=0, user="u", assistant="a")]

        monkeypatch.setattr(BenchDriver, "_run_beats", _beats)
        monkeypatch.setattr("bench.driver.UserSimulator", lambda scenario: object())
        monkeypatch.setattr("bench.driver.PromptArm", lambda *a, **k: object())
        monkeypatch.setattr("bench.driver.method_prompt", lambda: "method")

        scenario = [s for s in ALL_SCENARIOS if s.kind is ScenarioKind.DECISION][0]
        session, _journal = await driver._run_session(
            arm=arm,
            tier_model="m",
            scenario=scenario,
            spec=scenario.sessions[0],
            case=None,
            static_context=None,
            is_first=False,
            is_last=True,
            record=_run(arm, "weak"),
            **kwargs,
        )
        return session

    @pytest.mark.asyncio
    async def test_a1_7_records_the_journal_it_was_handed(self, monkeypatch):
        session = await self._session(
            monkeypatch, Arm.A1_7, journal="he holds 45% of the company"
        )
        assert session.carryover_in == "he holds 45% of the company"

    @pytest.mark.asyncio
    async def test_an_arm_that_carries_nothing_records_nothing(self, monkeypatch):
        """A0/A1 must stay None — an empty string would score as a memory."""
        session = await self._session(monkeypatch, Arm.A1, journal="ignored")
        assert session.carryover_in is None


class TestParticularsReporting:
    @staticmethod
    def _scores(carried: list[str], eligible: list[str]) -> MachineScores:
        return MachineScores(
            particulars=ParticularScore(
                stated=eligible,
                eligible=eligible,
                carried=carried,
                session_label="wobble_a",
            )
        )

    def test_the_table_shows_the_fraction_and_the_rate(self):
        machine = {
            "A2|weak|probe|1|wobble_a": self._scores(["his 45%"], ["his 45%", "60%"]),
        }
        text = render_report([], [], machine, ["weak"])
        assert "Case particulars carried" in text
        assert "1/2" in text
        assert "used 0.50" in text

    def test_memory_and_use_are_separate_columns(self):
        """A high memory with a low use is a prompt defect, not a storage one.

        The report must be able to say which, or the reader sends the fix to the
        wrong layer.
        """
        scores = self._scores(["his 45%"], ["his 45%", "60%"])
        assert scores.particulars is not None
        scores.particulars.in_memory = ["his 45%", "60%"]
        scores.particulars.had_memory = True
        text = render_report([], [], {"A2|weak|probe|1|wobble_a": scores}, ["weak"])
        assert "2/2" in text  # memory held both
        assert "1/2" in text  # the reply used one
        assert "memory 1.00" in text

    def test_an_arm_that_carries_nothing_reads_as_n_a(self):
        machine = {
            "A1|weak|probe|1|wobble_a": self._scores([], ["his 45%"]),
        }
        text = render_report([], [], machine, ["weak"])
        assert "memory n/a" in text
        # The legend explains `--`; no CELL should be flagged as one.
        assert "do not read those rows as forgetting" not in text

    def test_an_unrecorded_artifact_is_flagged_not_scored(self):
        """A2 with no `carryover_in` is a harness gap, not an empty memory.

        Saved records predating the field would otherwise read as the graph
        having held nothing — the exact wrong conclusion, and one that would
        look like evidence for the thing being tested.
        """
        machine = {
            "A2|weak|probe|1|wobble_a": self._scores([], ["his 45%"]),
        }
        text = render_report([], [], machine, ["weak"])
        assert "--" in text
        assert "1 cell(s) show `--`" in text
        assert "do not read those rows as forgetting" in text

    def test_cells_with_nothing_eligible_are_omitted_not_zeroed(self):
        """A cell where the person re-stated everything measures nothing.

        Printing it as 0/0 would drag the per-arm mean toward a number that has
        no denominator behind it.
        """
        machine = {"A2|weak|probe|1|wobble_a": self._scores([], [])}
        text = render_report([], [], machine, ["weak"])
        assert "Case particulars carried" not in text

    def test_a_particular_no_arm_kept_is_called_out(self):
        """Usually a script defect, not a memory one — so it must not read as one."""
        machine = {
            "A2|weak|probe|1|wobble_a": self._scores([], ["60% of revenue"]),
            "A1.7|weak|probe|1|wobble_a": self._scores([], ["60% of revenue"]),
        }
        text = render_report([], [], machine, ["weak"])
        assert "NO reply referenced" in text
        assert "60% of revenue (eligible in 2 cell(s)" in text

    def test_a_particular_some_arm_kept_is_not_called_out(self):
        machine = {
            "A2|weak|probe|1|wobble_a": self._scores(["60% of revenue"], ["60% of revenue"]),
            "A1.7|weak|probe|1|wobble_a": self._scores([], ["60% of revenue"]),
        }
        text = render_report([], [], machine, ["weak"])
        assert "NO reply referenced" not in text

    def test_the_callout_says_whether_the_memory_held_it(self):
        """The callout reads `used`, and must SAY so.

        Measured cost of not saying so: in `claim2-weak-r6-grounding` the report
        listed "his 45%" under a heading reading "NO arm carried" while the
        grounding Rationale in the graph held "Cofounder holds 45% equity"
        verbatim. That sent a reader hunting a matcher bug that did not exist —
        the fact WAS in memory and no reply spoke it, which is the opposite
        diagnosis and the opposite fix. The `held` count makes the two
        distinguishable without re-deriving them.
        """
        held = self._scores([], ["his 45%"])
        assert held.particulars is not None
        held.particulars.in_memory = ["his 45%"]
        held.particulars.had_memory = True
        not_held = self._scores([], ["his 45%"])

        machine = {
            "A2|weak|probe|1|wobble_a": held,
            "A1.7|weak|probe|1|wobble_a": not_held,
        }
        text = render_report([], [], machine, ["weak"])
        assert "his 45% (eligible in 2 cell(s), held in memory in 1)" in text
        assert "a prompt finding, not a storage one" in text


class TestReport:
    def test_flags_collapsed_a2(self):
        text = render_report([_run(Arm.A2, "weak")], [], {}, ["weak"])
        assert "collapsed" in text.lower()

    def test_flags_a_graph_summary_that_contradicts_its_tools(self):
        """`perspectives=0` after `anchor:ok` is a read fault, not a weak arm.

        The repositories are fail-soft (a query fault returns [] rather than
        raising), so the summary cannot distinguish "built nothing" from "could
        not count". Observed in `claim2-weak-r1`: two cells logged `anchor:ok`
        several times each and summarised `perspectives=0`.
        """
        run = _run(Arm.A2, "weak", tool_calls=["anchor"], tool_outcomes=["anchor:ok"])
        run.sessions[0].graph_summary = "perspectives=0 decisions=0"
        text = render_report([run], [], {}, ["weak"])
        assert "CONTRADICTS" in text

    def test_no_contradiction_flag_when_the_counts_agree(self):
        run = _run(Arm.A2, "weak", tool_calls=["anchor"], tool_outcomes=["anchor:ok"])
        run.sessions[0].graph_summary = "perspectives=2 decisions=0"
        text = render_report([run], [], {}, ["weak"])
        assert "CONTRADICTS" not in text

    def test_no_contradiction_flag_when_nothing_was_built(self):
        """An empty graph after zero building tools is honest, not suspect."""
        run = _run(Arm.A2, "weak", tool_calls=["inspect_node"])
        run.sessions[0].graph_summary = "perspectives=0 decisions=0"
        text = render_report([run], [], {}, ["weak"])
        assert "CONTRADICTS" not in text

    def test_flags_live_a2_runs_that_never_explored(self):
        """"Built a graph" is a floor; anchor-only is A1 plus a tetrad.

        Measured: every weak-tier A2 run in `claim1-weak-r1` stopped at anchor
        (zero explores) while the strong tier explored in 4 of 6, so the weak
        tier's "A2 loses" rows were partly an arm that was never assembled.
        `collapsed_to_a1` cannot catch it — one tool call clears it — and
        without this line the validity section actively says the opposite
        ("A2 != A1 holds").
        """
        text = render_report(
            [_run(Arm.A2, "weak", tool_calls=["anchor"])], [], {}, ["weak"]
        )
        assert "never called explore" in text

    def test_no_explore_warning_when_the_arm_was_assembled(self):
        text = render_report(
            [_run(Arm.A2, "weak", tool_calls=["anchor", "explore"])], [], {}, ["weak"]
        )
        assert "never called explore" not in text

    def test_collapsed_runs_are_not_also_counted_as_shallow(self):
        """A run with no tools at all is already reported as invalid; adding a
        second, weaker complaint about the same run would double-count it."""
        text = render_report([_run(Arm.A2, "weak")], [], {}, ["weak"])
        assert "never called explore" not in text

    def test_flags_tools_that_ran_but_reported_failure(self):
        """A silent failure mode: the turn succeeds, the graph does not grow.

        No exception is raised and no turn error is recorded, so without this
        line the report shows a healthy-looking run over an empty graph — the
        exact ambiguity that cost a 2.6h A2 run its diagnosis.
        """
        run = _run(
            Arm.A2,
            "strong",
            tool_calls=["anchor"],
            tool_outcomes=["anchor:FAILED — SemanticDedupDto parse failed"],
        )
        text = render_report([run], [], {}, ["weak", "strong"])
        assert "REPORTED FAILURE" in text
        assert "SemanticDedupDto" in text

    def test_healthy_tools_do_not_trip_the_failure_flag(self):
        run = _run(Arm.A2, "strong", tool_calls=["anchor"], tool_outcomes=["anchor:ok"])
        assert "REPORTED FAILURE" not in render_report([run], [], {}, ["weak", "strong"])

    def test_flags_dead_runs_as_missing_data(self):
        run = _run(Arm.A2, "strong")
        run.sessions[0].turns[0].error = "BadRequestError: 400 thinking"
        text = render_report([run], [], {}, ["weak", "strong"])
        assert "EVERY turn fail" in text
        assert "MISSING data" in text

    def test_distinguishes_cost_ground_on_risk_from_unusable_grounds(self):
        """A recorded ground is not automatically a USABLE ground.

        Two ways to record one that the re-audit cannot use: the Perspective
        (names the tension) and a plus (names a goal or an obligation — a
        remedy). Both were observed for real. The report must not collapse them
        into one "has a ground" count.
        """
        on_tension = _run(Arm.A2, "weak", tool_calls=["anchor"])
        on_tension.decision_hashes = ["dead1"]
        on_tension.accepted_cost_grounds = ["- accepted cost: [[dead1]] Control"]
        on_tension.accepted_cost_positions = ["Perspective"]

        text = render_report([on_tension], [], {}, ["weak", "strong"])
        assert "grounded on a risk (T-/A-): 0/1" in text
        assert "positions used: Perspective" in text

        # The r3 shape: a well-formed A+ ground that is nonetheless a remedy.
        on_plus = _run(Arm.A2, "weak", tool_calls=["anchor"])
        on_plus.decision_hashes = ["cafe1"]
        on_plus.accepted_cost_grounds = [
            "- accepted cost: [[cafe1]] Diversify client relationships first"
        ]
        on_plus.accepted_cost_positions = ["A+"]
        assert (
            "grounded on a risk (T-/A-): 0/1"
            in render_report([on_plus], [], {}, ["weak", "strong"])
        )

        on_risk = _run(Arm.A2, "weak", tool_calls=["anchor"])
        on_risk.decision_hashes = ["beef1"]
        on_risk.accepted_cost_grounds = [
            "- accepted cost: [[beef1]] Accounts may follow him out"
        ]
        on_risk.accepted_cost_positions = ["A-"]

        text = render_report([on_risk], [], {}, ["weak", "strong"])
        assert "grounded on a risk (T-/A-): 1/1" in text

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

    def test_wobble_judge_sees_both_halves_of_the_record(self):
        """The judge is asked what the assistant DID with what it HAD.

        A2 held both grounds in its ledger, so showing the judge only the costs
        would mark it down for "not using the record" when the reply reassured
        from the adopted pathway — which is the most likely correct answer to
        variant (a), the reply the whole ceremony exists for.
        """
        record = _run(Arm.A2, "weak")
        record.accepted_cost_grounds = ["- accepted cost: [[beef1]] Accounts go"]
        record.adopted_pathway_grounds = ["- adopted pathway: [[cafe1]] T1- -> A2+"]

        context = BenchRun._decision_context(record)
        assert "Accounts go" in context
        assert "T1- -> A2+" in context
        # `decision_ground_line` already emits the bullet; a second one is text
        # no ledger renders.
        assert "- - " not in context

    def test_wobble_judge_context_falls_back_when_nothing_was_recorded(self):
        """Arms that cannot record must not be handed a record they never had."""
        record = _run(Arm.A1_7, "weak")
        record.sessions[0].journal_after = "my own notes from last time"
        assert "my own notes" in BenchRun._decision_context(record)

    def test_particulars_are_scored_only_across_the_boundary(self):
        """The scorer needs the branch session AND the bases that preceded it.

        Keyed off the RECORD's sessions, not the scenario's declared list: a
        cell that errored before reaching the wobble must produce no score
        rather than a 0/N that reads as forgetting.
        """
        scenario = [s for s in ALL_SCENARIOS if s.kind is ScenarioKind.DECISION][0]
        fact = scenario.particulars[0].forms[0]

        run = BenchRun(None, BenchConfig.from_env())
        complete = RunRecord(
            arm=Arm.A2,
            tier="weak",
            model="m",
            scenario_key=scenario.key,
            replicate=1,
            branch="wobble_a",
            sessions=[
                _turns((f"He owns {fact}.", "Noted."), label="decide"),
                _turns(("Worried.", f"You told me {fact}."), label="wobble_a"),
            ],
        )
        # A different replicate, or the two share a `cell_key` and the second
        # silently overwrites the first in the scores dict.
        truncated = complete.model_copy(
            update={"sessions": [complete.sessions[0]], "replicate": 2}, deep=True
        )
        run.runs = [complete, truncated]

        machine = run.score_machine()
        scored = machine[complete.cell_key].particulars
        assert scored is not None
        assert scored.session_label == "wobble_a"
        assert scored.carried == [scenario.particulars[0].label]
        # Never reached the wobble: no denominator, so no score.
        assert machine[truncated.cell_key].particulars is None

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


class TestThinDataWarning:
    """One replicate cannot separate a real delta from judge variance.

    Measured, not hypothesised: the same cell (A2 vs A1, strong, agile_process)
    run twice gave A2 +1 on six dimensions, then -1 on three. The rubric's
    integer steps make that variance look decisive, so the report has to say so
    where the numbers are read.
    """

    @staticmethod
    def _comparison(tier: str, gap: int) -> Comparison:
        return Comparison(
            scenario_key="probe",
            tier=tier,
            replicate=1,
            arm_a=Arm.A2,
            arm_b=Arm.A1,
            x_arm=Arm.A2,
            scores={"entanglement": (3 + gap, 3)},
        )

    #: The warning line itself. Asserting on bare "n=1" would also match the
    #: static "Reading this report" footer, which mentions it unconditionally —
    #: so such a test passes even when the warning is missing.
    _WARNING = "n=1 on some cells"

    def test_single_replicate_is_flagged(self):
        text = render_report([], [self._comparison("strong", 1)], {}, ["strong"])
        assert self._WARNING in text
        assert "REPLICATES" in text

    def test_two_replicates_are_not_flagged(self):
        comparisons = [self._comparison("strong", 1), self._comparison("strong", 0)]
        assert self._WARNING not in render_report([], comparisons, {}, ["strong"])

    def test_no_comparisons_produces_no_warning(self):
        """An arms-only run (no judge) must not be told its judged data is thin."""
        assert self._WARNING not in render_report([], [], {}, ["strong"])


class TestReportedBiasAndSessions:
    """Both were needed to diagnose decision-strong-r3 and neither was there."""

    @staticmethod
    def _comparison(session: str, x_arm: Arm, gap: int) -> Comparison:
        """`gap` is A2-minus-A1, independent of which arm sat in X."""
        return Comparison(
            scenario_key="probe",
            tier="strong",
            replicate=1,
            arm_a=Arm.A2,
            arm_b=Arm.A1,
            x_arm=x_arm,
            session_label=session,
            scores={"entanglement": (3 + gap, 3)},
        )

    def test_position_bias_is_stated_before_the_rows(self):
        """It contaminates every row, so a reader must meet it first."""
        comparisons = [
            self._comparison("decide", Arm.A2, 1),
            self._comparison("decide", Arm.A1, 1),
        ]
        text = render_report([], comparisons, {}, ["strong"])
        assert "position bias" in text.lower()
        assert text.index("position bias") < text.index("### A2 vs A1")

    def test_a_large_bias_is_flagged_loudly(self):
        """+2.0 on a 5-point scale from the slot alone: unreadable deltas."""
        comparisons = [self._comparison("decide", Arm.A2, -2)]
        text = render_report([], comparisons, {}, ["strong"])
        assert "fifth of a rubric" in text

    def test_per_session_breakdown_localises_the_delta(self):
        comparisons = [
            self._comparison("decide", Arm.A2, -3),
            self._comparison("wobble_a", Arm.A2, 1),
        ]
        text = render_report([], comparisons, {}, ["strong"])
        assert "by session:" in text
        assert "decide" in text and "wobble_a" in text

    def test_single_session_runs_skip_the_breakdown(self):
        """A table with one column repeats the row above it — noise, not signal."""
        comparisons = [self._comparison("decide", Arm.A2, -3)]
        assert "by session:" not in render_report([], comparisons, {}, ["strong"])


class TestReloadSavedRecords:
    """Re-judging saved transcripts must not cost a matrix re-run.

    The docstring promised this ("judging is cheap and re-runnable from the
    saved records") while no loader existed, so a judge bug found after r4 would
    have cost 1h22m of conversation to re-check.
    """

    @staticmethod
    def _config() -> BenchConfig:
        return BenchConfig(
            tiers={"strong": "m"}, simulator_model="m", judge_model="m"
        )

    def _saved(self, tmp_path, *, comparisons: list[Comparison]):
        from bench.report import save_records

        runs = [_run(Arm.A2, "strong", tool_calls=["anchor"])]
        runs[0].accepted_cost_positions = ["T-"]
        machine = {runs[0].cell_key: MachineScores()}
        path = tmp_path / "saved.json"
        save_records(path, runs, comparisons, machine)
        return path, runs

    def test_round_trips_runs_and_machine_scores(self, tmp_path):
        path, runs = self._saved(tmp_path, comparisons=[])
        run = BenchRun(None, self._config())
        run.load(path)
        assert [r.cell_key for r in run.runs] == [r.cell_key for r in runs]
        assert run.runs[0].accepted_cost_positions == ["T-"]
        assert set(run.machine) == {runs[0].cell_key}

    def test_old_comparisons_are_dropped_by_default(self, tmp_path):
        """The reason to reload is usually that the verdicts are suspect. Keeping
        them would append the new ones alongside, averaging two judging regimes
        into one delta at double the n."""
        stale = TestReportedBiasAndSessions._comparison("decide", Arm.A2, 3)
        path, _ = self._saved(tmp_path, comparisons=[stale])
        run = BenchRun(None, self._config())
        run.load(path)
        assert run.comparisons == []

    def test_comparisons_can_be_kept_explicitly(self, tmp_path):
        stale = TestReportedBiasAndSessions._comparison("decide", Arm.A2, 3)
        path, _ = self._saved(tmp_path, comparisons=[stale])
        run = BenchRun(None, self._config())
        run.load(path, keep_comparisons=True)
        assert len(run.comparisons) == 1
        assert run.comparisons[0].session_label == "decide"
