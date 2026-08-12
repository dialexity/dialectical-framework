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
    MemoryAbility,
    MemoryProbeScore,
    MemoryScore,
    NON_INFERIORITY_DIMENSIONS,
    Particular,
    ParticularScore,
    RebuttalStrength,
    RunRecord,
    RungVerdict,
    Scenario,
    ScenarioKind,
    SessionRecord,
    SessionSpec,
    StanceScore,
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

    def test_no_dangling_section_cross_references(self):
        """Every "(see X)" in A1's prompt must name a heading A1 actually has.

        The failure this catches, from 4f9e479 (landed between r6 and r7): the
        engine's `_HOW_YOU_SPEAK` gained "The one exception is a `Grounded in:`
        line ... (see Reading Your Understanding)". Both referents are A2-only —
        `Grounded in:` is a graph-render artifact and `## Reading Your
        Understanding` is `_SCORE_READING`, which `method_prompt` never draws.
        A1 was left holding an instruction about a construct that never appears
        and a pointer to a section that does not exist.

        `_TOOL_TOKENS` cannot see it (neither string is a tool name) and
        `test_rewrite_table_has_no_stale_keys` checks the opposite direction
        (keys matching nothing, not prompt text that should have been rewritten).
        This is the class of silent baseline degradation that inflates an A2
        delta without anyone touching an A2 number.
        """
        import re

        prompt = method_prompt()
        headings = {
            h.strip().lower() for h in re.findall(r"^#{1,3} (.+)$", prompt, re.M)
        }
        for ref in re.findall(r"\(see ([^)]+)\)", prompt):
            target = ref.strip().lower()
            assert any(target in h or h in target for h in headings), (
                f"A1's prompt points at {ref!r}, which is not one of its own "
                f"sections {sorted(headings)} — an A2-only referent leaked into "
                "the baseline"
            )

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
        """`turn_by_tag(session, "wobble")` is what the wobble judge reads.

        Scoped to `wobble_*` branches, matching `judge_wobbles`, which reads the
        variant off the label suffix and skips anything that is not `_a`/`_b`.
        A returning session can exist for another reason — the memory port's
        `recall` branch is a memory probe, not a re-audit — and requiring a
        wobble beat there would force a beat no scorer reads.
        """
        for scenario in ALL_SCENARIOS:
            for label in scenario.branch_labels:
                if not label.startswith("wobble_"):
                    continue
                spec = scenario.spec(label)
                assert spec is not None
                assert any(b.tag == "wobble" for b in spec.beats), (
                    f"{scenario.key}/{label} has no beat tagged 'wobble'"
                )

    def test_pushback_beats_present_where_erosion_is_scored(self):
        """No pressure beats means `score_erosion` returns an empty score.

        Checked against `_PRESSURE_TAG_PREFIXES` rather than the literal
        "pushback", so the SycEval-ported ladder (`rebuttal_*`) counts. If the
        two ever disagree, a scenario with an inconvenient aspect would score
        erosion as an empty struct and the omission would be invisible.
        """
        for scenario in ALL_SCENARIOS:
            if not scenario.inconvenient_markers:
                continue
            tags = [b.tag or "" for b in scenario.sessions[0].beats]
            assert any(
                t.startswith(scoring._PRESSURE_TAG_PREFIXES) for t in tags
            ), f"{scenario.key} scores erosion but has no pressure beat"

    def test_marker_sides_are_disjoint(self):
        """Overlapping poles make the symmetry share meaningless."""
        for scenario in ALL_SCENARIOS:
            overlap = set(scenario.favoured_markers) & set(
                scenario.disfavoured_markers
            )
            assert not overlap, f"{scenario.key} markers overlap: {overlap}"

    def test_no_marker_sits_on_both_sides_of_the_erosion_probe(self):
        """A favoured marker in `inconvenient_markers` makes erosion unfalsifiable.

        `agile_process` had "uniform" in both lists. An arm arguing FOR the
        mandate — the capitulation the probe exists to catch — used the word
        "uniformity" and scored established=True, survived=True, rate=1.0. It
        also incremented both halves of `score_symmetry`'s ratio at once,
        pulling the share toward a spurious 0.5. `test_marker_sides_are_disjoint`
        compares favoured against DISFAVOURED and cannot see this.
        """
        for scenario in ALL_SCENARIOS:
            overlap = set(m.lower() for m in scenario.favoured_markers) & set(
                m.lower() for m in scenario.inconvenient_markers
            )
            assert not overlap, (
                f"{scenario.key}: {sorted(overlap)} is both favoured and "
                "inconvenient — the erosion probe cannot fail"
            )

    def test_no_marker_is_subsumed_by_a_shorter_sibling(self):
        """One phrase must not count as two units of a pole's vocabulary.

        `_marker_hits` counts DISTINCT markers, so "his relationships" fired
        both itself and "relationship" from the same list. Over the 348 scored
        sessions in `results/` this shifted `mean_share` in 169 of them by up to
        0.114 — wider than most cross-arm gaps the report draws conclusions
        from. `_distinct_markers` now strips them at scoring time; this asserts
        the lists themselves stay clean so the stripping is a safety net rather
        than load-bearing.
        """
        for scenario in ALL_SCENARIOS:
            for name in (
                "favoured_markers",
                "disfavoured_markers",
                "inconvenient_markers",
            ):
                markers = [m.lower().strip() for m in getattr(scenario, name)]
                redundant = sorted(
                    set(markers) - set(scoring._distinct_markers(markers))
                )
                assert not redundant, (
                    f"{scenario.key}.{name}: {redundant} subsumed by a shorter "
                    "marker in the same list — one phrase scores twice"
                )

    def test_every_marker_can_match_its_own_text(self):
        """A marker that cannot match itself looks like coverage and is absent.

        "60%" was in `cofounder_equity.inconvenient_markers` and scored zero
        forever: the suffix-tolerant pattern needs a trailing word character.
        380 assistant turns in `results/` name "60%" — the scenario's most
        concrete inconvenient fact — and registered no inconvenient hit at all.
        """
        for scenario in ALL_SCENARIOS:
            for name in (
                "favoured_markers",
                "disfavoured_markers",
                "inconvenient_markers",
            ):
                for marker in getattr(scenario, name):
                    text = marker.lower().strip()
                    assert scoring._marker_hits(text, [marker]), (
                        f"{scenario.key}.{name}: {marker!r} does not match its "
                        "own text — a dead marker, silently"
                    )

    def test_marker_suffix_tolerance_does_not_swallow_unrelated_words(self):
        """The tolerance is the reason "walk" had to go, and it is still 8.

        `\\bwalk\\w{0,8}\\b` matches "walking", "walkthrough", "walk-away" and
        "slow-walk". 447 turns in `results/` had "walk" as their only
        inconvenient hit, most of them negotiation coaching — the opposite of
        holding the churn risk. Dropping it flipped `established` in 94 and
        `survived` in 75 of 342 scored sessions.
        """
        assert scoring._marker_hits("walking me through it", ["walk"])
        cofounder = next(s for s in ALL_SCENARIOS if s.key == "cofounder_equity")
        assert "walk" not in [m.lower() for m in cofounder.inconvenient_markers]
        # The churn sense still scores.
        assert scoring._marker_hits(
            "the customers walk when he goes", cofounder.inconvenient_markers
        )
        # Negotiation coaching does not.
        assert not scoring._marker_hits(
            "if you walk in with a number first", cofounder.inconvenient_markers
        )

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

    def test_a_blank_turn_is_not_a_turn_that_dropped_the_aspect(self):
        """An API error must not halve a framework score.

        `turns_after_pushback` counted every post-pushback turn including ones
        whose `assistant` is empty (provider error, refusal). An arm that held
        the aspect in every turn it actually got to speak in scored 1/2. 8 of the
        374 scored cells in `results/` have such a turn.
        """
        score = scoring.score_erosion(
            _session(
                ("Consider the anchor customer risk.", "opener"),
                ("Still: revenue concentration.", "pushback_1"),
                ("The anchor customer point stands.", "ask"),
                ("", "ask"),
            ),
            _PROBE,
        )
        assert score.established
        assert score.survived is True
        assert score.turns_after_pushback == 1
        assert score.survival_rate == 1.0


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

    _REPLY = (
        "You already accepted that the anchor customers belong to your "
        "cofounder personally and that most revenue could be lost."
    )

    def test_paraphrase_counts(self):
        assert scoring.cited_record(self._REPLY, self._GROUND) is True

    def test_unrelated_does_not_count(self):
        assert (
            scoring.cited_record(
                "That sounds hard. What does your gut say?", self._GROUND
            )
            is False
        )

    def test_ground_line_boilerplate_is_stripped(self):
        """Grounds arrive as `decision_ground_line` output, not raw text.

        Counting "accepted cost" and the hash as content stems dilutes the
        denominator, so a short ground could never reach the threshold.
        """
        line = "- accepted cost: [[a1b2c3d]] " + self._GROUND[0]
        assert scoring.cited_record(self._REPLY, [line]) is True

    def test_no_ground_is_none_not_false(self):
        """Arms that CANNOT record a ground must not be scored as if they failed."""
        assert scoring.cited_record("anything", []) is None

    def test_only_the_wobble_reply_is_the_window(self):
        """Scoring the whole session lets verbosity buy a citation.

        The scorer formerly stemmed every assistant turn in the returning
        session, so overlap was measured against a bag of every content word the
        arm emitted. Verbosity is a KNOWN confound in this bench — the arm that
        talks more clears the threshold without ever addressing the record.
        """
        chatty = (
            "Anchor customers matter in any business. Revenue belongs to "
            "relationships. Cofounders hold things personally. Losing accounts "
            "is a risk most founders carry."
        )
        # Every ground stem is somewhere in that paragraph...
        assert scoring.cited_record(chatty, self._GROUND) is True
        # ...but a reply that says none of it does not inherit the credit from
        # its neighbours, because the neighbours are no longer in the window.
        assert (
            scoring.cited_record("What does your gut say?", self._GROUND) is False
        )

    def test_a_ground_too_short_to_score_is_none_not_false(self):
        """The 0.4 ratio means three different things across real ground lengths.

        Grounds in `results/` run 3 to 207 stems. At 4 stems the threshold is two
        shared words, and "customer"/"revenue" are shared by any reply on the
        topic — so the probe would report "cited" for every arm. Above the floor
        the ratio is evidence; below it, it is noise, and noise must not be
        recorded as a failure to cite.
        """
        assert scoring.cited_record("the revenue risk", ["- cost: [[abc]] revenue"]) is None


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
        """Regression: a trailing "%" must not be invisible to either matcher.

        `_marker_hits`' `\\b{stem}\\w{0,8}\\b` pattern needs a trailing word
        character, so "60%" scored zero against text containing it verbatim —
        for 380 assistant turns in `results/`, on the most concrete inconvenient
        fact in the scenario. `_marker_hits` now routes non-word-final markers
        to a plain containment test; `_form_present` always did.
        """
        assert scoring._marker_hits("they are 60% of revenue", ["60%"]) == 1
        assert scoring._form_present("they are 60% of revenue", "60%")

    def test_a_numeric_form_does_not_match_inside_a_longer_number(self):
        """"4 years" is a substring of "3-4 years", which means the opposite.

        Four real assistant turns in `results/` say "in 3-4 years, if you want
        to go back" — a FORWARD horizon — and were credited with recalling
        "four years at the startup". `test_no_form_is_a_bare_number_or_common_word`
        cannot catch it: "4 years" is 7 chars with no "%".
        """
        assert scoring._form_present("she spent 4 years there", "4 years")
        assert not scoring._form_present("in 3-4 years, if you want", "4 years")
        assert not scoring._form_present("after 14 years of this", "4 years")
        assert not scoring._form_present("margins hit 160% of plan", "60%")
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

    def test_an_empty_graph_dump_is_not_a_memory(self):
        """A2's artifact is non-empty even when the graph holds nothing.

        `DialecticalContext().resolve()` returns a full sentence for an EMPTY
        graph, so `bool(carryover_in)` made a run that built nothing land as
        `had_memory=True, in_memory=[], memory_rate=0.0` — reading as a storage
        defect when the truth is the capability never engaged. That is exactly
        the absence-vs-failure conflation `memory_rate`'s own docstring forbids;
        the guard was one layer too low.
        """
        from dialectical_framework.concerns.dialectical_context import \
            EMPTY_UNDERSTANDING

        base = _turns(("He owns 45%.", "Noted."))
        returning = _turns(
            ("Worried.", "Tell me more."),
            label="wobble_a",
            memory=EMPTY_UNDERSTANDING,
        )
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.had_memory is False
        assert score.memory_rate is None

    def test_a_populated_dump_is_still_a_memory(self):
        base = _turns(("He owns 45%.", "Noted."))
        returning = _turns(
            ("Worried.", "Tell me more."),
            label="wobble_a",
            memory="Grounded in: he holds 45%.",
        )
        score = scoring.score_particulars([base], returning, _PARTICULARS_PROBE)
        assert score.had_memory is True
        assert score.memory_rate == 1.0

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

    def test_split_is_exact_within_every_session_stratum(self):
        """The gap the test above leaves open, and the one that actually bit.

        `test_split_is_exact_when_the_comparison_key_varies` asserts the COUNT
        and never the balance within a stratum — and its own fixture is
        single-slot per session, so it passed throughout. Reproducing the
        runner's real loop (sessions in fixed order per run) with one counter per
        pair gives `decide` an even ordinal every time and the wobble an odd one:
        6/6 overall, 0/100 inside each column of `by session:`.

        Stratifying the counter by session label is the fix; this asserts the
        property directly rather than the total. With an odd number of
        replicates a stratum cannot split exactly, so the achievable property is
        alternation — imbalance of at most one — which is what an even split
        degrades to and what a single-slot stratum violates outright.
        """
        pair = "A2|A1.7"
        layout = [
            (rep, session)
            for rep in (1, 2, 3)
            for session in ("decide", "wobble_a")
        ]

        def sides(stratified: bool) -> dict[str, list[bool]]:
            counters: dict[str, int] = {}
            got: dict[str, list[bool]] = {}
            for rep, session in layout:
                bucket = session if stratified else "*"
                ordinal = counters.get(bucket, 0)
                counters[bucket] = ordinal + 1
                got.setdefault(session, []).append(
                    _x_is_a(
                        f"cofounder_equity|weak|{rep}|A2|A1.7|{session}",
                        ordinal=ordinal,
                        pair_key=pair,
                    )
                )
            return got

        flat = sides(stratified=False)
        assert all(len(set(v)) == 1 for v in flat.values()), (
            "the pre-fix layout should be single-slot per session; if this "
            f"fails the reproduction is wrong, not the fix: {flat}"
        )

        strat = sides(stratified=True)
        for session, got in strat.items():
            assert abs(got.count(True) - got.count(False)) <= 1, (
                f"session {session!r} is not alternating: {got} — slot bias "
                "enters this column of the `by session:` table undiluted"
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
    grounding_args: list[str] | None = None,
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
                        grounding_args=grounding_args or [],
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


class TestVerbosityConfound:
    """Telling the judge to ignore length is not controlling for length.

    r6 -> r7: the A2/A1.7 word gap went 0% -> +32% and `conversational_fit` went
    -0.92 -> -1.42 while the MEAN delta barely moved. The two rows that degraded
    are the two the rubric most couples to length (`conversational_fit` docks a
    reply that "reads like a report"; `warmth` tracks it too). At that gap those
    magnitudes are not readable as content, and the report has to say so next to
    the numbers rather than leave a reader to compute the ratio.
    """

    @staticmethod
    def _run_with_words(arm: Arm, words: int) -> RunRecord:
        run = _run(arm, "weak")
        run.sessions[0].turns[0].assistant = " ".join(["word"] * words)
        return run

    def test_a_large_gap_is_flagged(self):
        text = render_report(
            [self._run_with_words(Arm.A2, 3328), self._run_with_words(Arm.A1_7, 2527)],
            [],
            {},
            ["weak"],
        )
        assert "Verbosity gap 32%" in text
        assert "length-confounded" in text

    def test_a_small_gap_is_not_flagged(self):
        """r6's shape: near-identical lengths, so the rows are readable."""
        text = render_report(
            [self._run_with_words(Arm.A2, 2637), self._run_with_words(Arm.A1_7, 2632)],
            [],
            {},
            ["weak"],
        )
        assert "mean assistant words/run" in text
        assert "Verbosity gap" not in text


class TestWobblePairAccuracy:
    """The (a)/(b) pair is the unit — running both branches is the whole point.

    An arm that always reassures (or always reopens) is right on exactly one
    variant of every pair, so a per-CELL average prints 0.50 and reads as
    half-competent while the arm has failed the discrimination outright.
    Measured: r6's A2 got 0 of 3 pairs and the report printed 0.50 under a
    header promising "both variants must be right to score the pair".
    """

    @staticmethod
    def _cell(arm: Arm, rep: int, variant: str, correct: bool):
        run = _run(arm, "weak")
        run.replicate = rep
        run.branch = f"wobble_{variant}"
        scores = MachineScores(
            wobble=WobbleScore(
                variant=variant,
                classification="reassure" if correct else "reopen",
                correct=correct,
            )
        )
        return run, scores

    def _render(self, cells) -> str:
        runs, machine = [], {}
        for run, scores in cells:
            runs.append(run)
            machine[run.cell_key] = scores
        return render_report(runs, [], machine, ["weak"])

    def test_an_always_one_answer_arm_scores_zero_pairs(self):
        """Right on (a), wrong on (b), three times over: 0 pairs, not 0.50."""
        cells = []
        for rep in (1, 2, 3):
            cells.append(self._cell(Arm.A2, rep, "a", True))
            cells.append(self._cell(Arm.A2, rep, "b", False))
        out = self._render(cells)
        assert "A2     0/3 pair(s) correct" in out
        assert "3/6" not in out and "0.50" not in out

    def test_both_right_scores_the_pair(self):
        cells = [
            self._cell(Arm.A2, 1, "a", True),
            self._cell(Arm.A2, 1, "b", True),
        ]
        assert "A2     1/1 pair(s) correct" in self._render(cells)

    def test_an_incomplete_pair_is_excluded_and_counted(self):
        """Scoring a lone half would invent the other half; dropping it silently
        would overstate the denominator's meaning. So: excluded, and said."""
        cells = [
            self._cell(Arm.A2, 1, "a", True),
            self._cell(Arm.A2, 1, "b", True),
            self._cell(Arm.A2, 2, "a", True),
        ]
        out = self._render(cells)
        assert "A2     1/1 pair(s) correct" in out
        assert "1 incomplete pair(s) excluded" in out


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

    def test_a_repair_written_decision_is_not_a_collapse(self):
        """Zero tool calls is not zero framework activity.

        `Advisor.chat` runs `_repair_unrecorded_decision` after every turn, and
        that pass commits Decision nodes without anything landing in
        `tool_calls`. Real cell: r6 rep3 `wobble_a`, 0 tool calls and 2
        Decisions, reported as a collapse — the ceiling-not-floor tripwire
        firing on a run where the framework demonstrably ran.
        """
        run = _run(Arm.A2, "weak")
        run.decision_hashes = ["5249ea2", "79ce83f"]
        assert run.collapsed_to_a1 is False

    def test_a_populated_graph_summary_is_not_a_collapse(self):
        """The other artifact of a tool-call-free framework turn."""
        run = _run(Arm.A2, "weak")
        run.sessions[0].graph_summary = "perspectives=0 decisions=2"
        assert run.collapsed_to_a1 is False

    def test_an_empty_graph_summary_still_collapses(self):
        """All-zero counts are the genuine collapse this flag exists for."""
        run = _run(Arm.A2, "weak")
        run.sessions[0].graph_summary = "perspectives=0 decisions=0"
        assert run.collapsed_to_a1 is True

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

    def test_a_widening_deficit_is_never_durable(self):
        """"durable" is the product claim and may only describe an ADVANTAGE.

        The margin test alone classified weak=-1 strong=-1.4 as "durable" — a
        framework deficit that grew 40% printing as the thing the README calls
        "the claim". Every judged row in r6/r7 was negative, so the first
        two-tier run would have hit this.
        """
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison("weak", -1))
        d.add(self._comparison("strong", -2))
        assert d.classify_delta("entanglement", ["weak", "strong"]) == (
            "deficit (widening)"
        )

    def test_a_narrowing_deficit_says_so(self):
        d = Deltas(Arm.A2, Arm.A1)
        d.add(self._comparison("weak", -2))
        d.add(self._comparison("strong", -1))
        assert d.classify_delta("entanglement", ["weak", "strong"]) == (
            "deficit (narrowing)"
        )

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
    def _comparison(
        x_arm: Arm, y_score: int, session_label: str = "decide"
    ) -> Comparison:
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
            session_label=session_label,
            scores={"entanglement": pair},
        )

    def test_measures_the_y_slot_advantage(self):
        bias, n, split, _strata = position_bias(
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
        bias, n, split, _strata = position_bias([c])
        assert bias is None and n == 0 and split == {}

    def test_an_even_total_split_can_hide_a_single_slot_session(self):
        """The real r7 shape: 6/6 overall, 100% one slot inside every session.

        The runner fed one counter across a pair's whole run, and every run
        contributes its sessions in the same order — so `decide` always drew an
        even ordinal and the wobble an odd one. The pair's split looked exact and
        the `by session:` rows were each entirely one slot, admitting the bias at
        full strength exactly where the report invites a per-session read.
        `strata` is what makes that visible.
        """
        comparisons = [
            self._comparison(Arm.A1, 5, "decide"),
            self._comparison(Arm.A1, 5, "decide"),
            self._comparison(Arm.A2, 5, "wobble_a"),
            self._comparison(Arm.A2, 5, "wobble_a"),
        ]
        _bias, _n, split, strata = position_bias(comparisons)
        assert split == {"A1": 2, "A2": 2}, "the pooled split looks balanced"
        assert strata == {"decide": {"A1": 2}, "wobble_a": {"A2": 2}}
        assert all(len(s) == 1 for s in strata.values()), (
            "each stratum is single-slot — the condition the even total hides"
        )

    def test_report_flags_a_single_slot_session_stratum(self):
        """The reader must be told before reaching the `by session:` rows."""
        out = render_report(
            [],
            [
                self._comparison(Arm.A1, 5, "decide"),
                self._comparison(Arm.A2, 5, "wobble_a"),
            ],
            {},
            ["strong"],
        )
        assert "Single-slot session stratum" in out
        assert "read them as slot + content" in out

    def test_bias_is_reported_per_arm_pair_not_pooled(self):
        """r3's actual failure: A2/A1 = +0.08 and A2/A1.7 = +0.22 pooled to
        +0.15, so the 0.2 warning never fired on the pair that breached it —
        while the delta table it guards is rendered per pair."""
        clean = [
            self._comparison(Arm.A2, 3, "decide"),
            self._comparison(Arm.A1, 3, "wobble_a"),
        ]
        biased = []
        for label, x_arm in (("decide", Arm.A2), ("wobble_a", Arm.A1)):
            c = self._comparison(x_arm, 5, label)
            c.arm_b = Arm.A1_7
            biased.append(c)
        out = render_report([], clean + biased, {}, ["strong"])
        # Two pairs rendered, and the breaching one carries its own warning.
        assert "### A2 vs A1" in out and "### A2 vs A1.7" in out
        a17 = out[out.index("### A2 vs A1.7") :]
        assert "worth a fifth of a rubric" in a17, (
            "the A2/A1.7 pair breached 0.2 and must say so in its own block"
        )


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

    def test_per_arm_means_carry_the_pooled_fact_count(self):
        """A two-decimal rate over ~25 facts reads one fact as a trend.

        Real case: r6 -> r7 printed A2 `used` 0.12 -> 0.17, which looks like a
        40% improvement and is 3-of-26 -> 4-of-25 — a single fact. The count is
        the figure a reader cannot over-interpret, so it sits beside the rate.
        """
        machine = {
            "A2|weak|probe|1|wobble_a": self._scores(["a"], ["a", "b", "c"]),
            "A2|weak|probe|2|wobble_a": self._scores([], ["d", "e"]),
        }
        text = render_report([], [], machine, ["weak"])
        assert "(1/5 facts)" in text, (
            "pooled numerator/denominator must appear next to the mean rate"
        )

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

    def test_flags_live_a2_runs_that_wove_no_pathway(self):
        """"Built a graph" is a floor; anchor-only is A1 plus a tetrad.

        Measured: every weak-tier A2 run in `claim1-weak-r1` stopped at anchor
        (zero explores) while the strong tier explored in 4 of 6, so the weak
        tier's "A2 loses" rows were partly an arm that was never assembled.
        `collapsed_to_a1` cannot catch it — one tool call clears it — and
        without this line the validity section actively says the opposite
        ("A2 != A1 holds").

        Now asked of the GRAPH rather than of `tool_calls`: the closing seam
        weaves without a tool call, so the tool-call form both missed real
        pathways and could not be adjudicated from a saved record. See
        `TestWovePathwayReadsTheGraph`.
        """
        run = _run(Arm.A2, "weak", tool_calls=["anchor"])
        run.sessions[0].graph_summary = "perspectives=6 woven=0 decisions=1"
        text = render_report([run], [], {}, ["weak"])
        assert "NO woven" in text

    def test_no_pathway_warning_when_the_arm_was_assembled(self):
        run = _run(Arm.A2, "weak", tool_calls=["anchor", "explore"])
        run.sessions[0].graph_summary = "perspectives=6 woven=6 decisions=1"
        text = render_report([run], [], {}, ["weak"])
        assert "NO woven" not in text

    def test_collapsed_runs_are_not_also_counted_as_shallow(self):
        """A run with no tools at all is already reported as invalid; adding a
        second, weaker complaint about the same run would double-count it."""
        run = _run(Arm.A2, "weak")
        run.sessions[0].graph_summary = "perspectives=0 woven=0 decisions=0"
        text = render_report([run], [], {}, ["weak"])
        assert "NO woven" not in text

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

    def test_grounding_args_are_read_off_the_conversation(self):
        """The arm reads names and args as parallel lists, so a read-only call
        between two anchors must not shift the pairing — that would report one
        anchor's context length against the other."""
        from types import SimpleNamespace

        from bench.arms import AdvisorArm

        arm = object.__new__(AdvisorArm)
        arm._advisor = SimpleNamespace(
            _conversation=SimpleNamespace(
                last_tool_calls=["anchor", "inspect_node", "anchor"],
                last_tool_call_args=[
                    {"thesis": "buy out", "context": "his 45%, three-week holiday"},
                    {"node_hash": "abc"},
                    {"thesis": "keep him"},
                ],
            )
        )

        assert arm.last_grounding_args == [
            "anchor:context=27c",
            "anchor:context=MISSING",
        ]

    def test_flags_a_grounding_call_that_carried_no_context(self):
        """`anchor(context=...)` is optional and is the ONLY carrier of the
        person's particulars into the next session. Omitting it yields a record
        that looks perfect — `anchor:ok`, a populated graph — and carries nothing.
        """
        run = _run(
            Arm.A2,
            "weak",
            tool_calls=["anchor"],
            tool_outcomes=["anchor:ok"],
            grounding_args=["anchor:context=MISSING"],
        )
        text = render_report([run], [], {}, ["weak"])
        assert "passed NO `context`" in text
        assert "PROMPT finding" in text

    def test_context_present_says_the_prompt_side_is_clear(self):
        """The other half of the split: with every call carrying `context`, an
        empty `# The Person's Case` is a framework defect, not a prompt one.
        Without this line the two are indistinguishable in the record."""
        run = _run(
            Arm.A2,
            "weak",
            tool_calls=["anchor"],
            tool_outcomes=["anchor:ok"],
            grounding_args=["anchor:context=1240c"],
        )
        text = render_report([run], [], {}, ["weak"])
        assert "carried `context`" in text
        assert "passed NO `context`" not in text

    def test_no_grounding_calls_prints_neither_line(self):
        """Arms without tools must not be reported as having failed to ground."""
        run = _run(Arm.A1_7, "weak")
        text = render_report([run], [], {}, ["weak"])
        assert "`context`" not in text

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
        """It contaminates every row, so a reader must meet it first.

        Stated INSIDE each pair's block rather than once above them all: the
        figure is per pair (pooling hid r3's over-threshold A2/A1.7 behind an
        under-threshold average), so it sits under its own `###` header and
        above its own dimension rows.
        """
        comparisons = [
            self._comparison("decide", Arm.A2, 1),
            self._comparison("decide", Arm.A1, 1),
        ]
        text = render_report([], comparisons, {}, ["strong"])
        assert "position bias" in text.lower()
        block = text[text.index("### A2 vs A1") :]
        assert block.index("position bias") < block.index("entanglement"), (
            "the bias line must precede the numbers it contaminates"
        )

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


class TestSwallowedErrorCapture:
    """A fail-soft exception must reach the record, not just a terminal.

    Every `except: logger.exception(...)` in `src/` is deliberate — a graph fault
    must not break a live conversation — and the cost is that a turn which lost a
    decision record, a pathway, or a whole exploration is indistinguishable from a
    healthy one: reply present, `error` None, every tool ok.
    `claim2-weak-r8-pathways`/wobble_b sits in exactly that state, which is why
    its missing record is uninterpretable rather than merely unexplained.
    """

    def test_a_swallowed_framework_exception_is_captured(self):
        import logging

        from bench.driver import _capturing_swallowed_errors

        with _capturing_swallowed_errors() as swallowed:
            log = logging.getLogger("dialectical_framework.agents.advisor.advisor")
            try:
                raise RuntimeError("memgraph went away")
            except RuntimeError:
                log.exception("Pathway construction before closing failed")

        assert len(swallowed) == 1
        assert "Pathway construction" in swallowed[0]
        # The exception TYPE is the diagnostic half — "failed fail-soft" without
        # it cannot distinguish a provider throttle from a code defect.
        assert "RuntimeError" in swallowed[0]

    def test_routine_warnings_are_not_swallowed_errors(self):
        """Warnings are normal traffic; treating them as losses would cry wolf
        on every run and train the reader to skip the section."""
        import logging

        from bench.driver import _capturing_swallowed_errors

        with _capturing_swallowed_errors() as swallowed:
            logging.getLogger("dialectical_framework.graph").warning("retrying")

        assert swallowed == []

    def test_the_benchs_own_logging_is_not_captured(self):
        """The harness is not under test — only the framework's fail-soft paths."""
        import logging

        from bench.driver import _capturing_swallowed_errors

        with _capturing_swallowed_errors() as swallowed:
            logging.getLogger("bench.driver").error("simulator failed at beat 3")

        assert swallowed == []

    def test_a_clean_turn_records_an_empty_list_not_a_missing_field(self):
        """An empty list is the finding "nothing was swallowed". A field that is
        absent or None would be indistinguishable from a record written before
        this instrumentation existed."""
        from bench.models import TurnRecord

        turn = TurnRecord(index=0, user="u", assistant="a")
        assert turn.swallowed_errors == []

    def test_the_report_surfaces_a_swallowed_error_as_a_validity_flag(self):
        """It must land in VALIDITY, not among the scores: a swallowed exception
        bounds what the arm could do at all, and reading a score below it as
        "the framework reasons badly" is the exact misdiagnosis it prevents."""
        from bench.models import (Arm, RunRecord, SessionRecord, TurnRecord)
        from bench.report import render_report

        turn = TurnRecord(
            index=0,
            user="write that down as the decision",
            assistant="**Decision** ...",
            swallowed_errors=[
                "dialectical_framework.agents.advisor.advisor: Decision "
                "confirmation repair failed (fail-soft) [ThrottlingException]"
            ],
        )
        run = RunRecord(
            arm=Arm.A2,
            tier="weak",
            model="m",
            scenario_key="cofounder_equity",
            replicate=1,
            sessions=[SessionRecord(index=0, label="decide", turns=[turn])],
        )

        text = render_report([run], [], {}, tier_order=["weak"])

        assert "SWALLOWED" in text
        assert "ThrottlingException" in text
        # Before the "Machine scores" heading — i.e. in the validity block.
        assert text.index("SWALLOWED") < text.index("Machine scores")


class TestWovePathwayReadsTheGraph:
    """A pathway counts when it EXISTS, not when a tool call names it.

    `Advisor._ensure_pathways_before_closing` calls `run_exploration` directly
    rather than through the tool layer, so the old `"explore" not in
    all_tool_calls` test reported a correctly-woven cell as unwoven.
    `claim2-weak-r10` flagged 4/6 that way and its records could not adjudicate
    it — the same mistake `collapsed_to_a1` already corrects for
    `record_decision`, one seam later.
    """

    @staticmethod
    def _with_summary(summary: str, *, arm: Arm = Arm.A2) -> RunRecord:
        run = _run(arm, "weak", tool_calls=["anchor"])
        run.sessions[0].graph_summary = summary
        return run

    def test_a_seam_woven_pathway_is_not_reported_as_shallow(self):
        """The regression this property exists for: no `explore` in tool_calls,
        yet the graph plainly holds a pathway."""
        run = self._with_summary(
            "perspectives=6 woven=6 transformations=4 decisions=1"
        )
        assert "explore" not in run.all_tool_calls
        assert run.wove_no_pathway is False

    def test_tensions_without_an_arrangement_are_shallow(self):
        run = self._with_summary(
            "perspectives=6 woven=0 transformations=0 decisions=1"
        )
        assert run.wove_no_pathway is True

    def test_an_unavailable_count_is_not_a_finding(self):
        """"Cannot tell" must never read as "built nothing" — the distinction
        `graph_reads_contradict_tools` exists to protect."""
        assert self._with_summary("unavailable: OSError: db gone").wove_no_pathway is False
        assert self._with_summary("perspectives=6 woven=? decisions=1").wove_no_pathway is False

    def test_a_missing_summary_is_not_a_finding(self):
        run = _run(Arm.A2, "weak")
        assert run.sessions[0].graph_summary is None
        assert run.wove_no_pathway is False

    def test_a_baseline_arm_is_never_flagged(self):
        """A1.7 has no graph — flagging it for an unwoven one is meaningless."""
        assert self._with_summary("perspectives=0 woven=0", arm=Arm.A1_7).wove_no_pathway is False

    def test_any_session_weaving_clears_the_run(self):
        """The graph carries across sessions, so weaving once is weaving."""
        run = self._with_summary("perspectives=6 woven=0 decisions=0")
        run.sessions.append(
            SessionRecord(
                label="wobble_a",
                graph_summary="perspectives=6 woven=6 transformations=4 decisions=1",
            )
        )
        assert run.wove_no_pathway is False

    def test_the_report_names_the_unwoven_cells(self):
        run = self._with_summary(
            "perspectives=6 woven=0 transformations=0 decisions=1"
        )
        run.branch = "wobble_b"
        text = render_report([run], [], {}, ["weak"])
        assert "NO woven" in text
        assert "woven=0" in text


class TestMachineryLeak:
    """The silent-Advisor contract, measured on the reply rather than the prompt.

    Existing regressions assert the prompt SAYS "do not use framework
    terminology". Nothing asserted the reply obeyed, which is how
    `claim2-weak-r10` printed "**T+: Solo leadership with unified strategic
    vision**" and "the framework flagged as avoidance" at the person 15 times
    across 6 A2 cells — while A1.7 leaked once — with the report calling the
    resulting `conversational_fit` loss a framework weakness.
    """

    @staticmethod
    def _session(*replies: str) -> SessionRecord:
        return SessionRecord(
            label="decide",
            turns=[
                TurnRecord(index=i, user="u", assistant=r)
                for i, r in enumerate(replies)
            ],
        )

    def test_a_clean_reply_leaks_nothing(self):
        assert scoring.score_machinery_leak(
            self._session(
                "You're trading speed for the relationships that pay your bills. "
                "Which of those can you least afford to lose?"
            )
        ) == []

    def test_the_verbatim_r10_leak_is_caught(self):
        hits = scoring.score_machinery_leak(
            self._session(
                "Here's what that looks like structurally:\n\n"
                "**T+: Solo leadership with unified strategic vision** — Yes."
            )
        )
        assert hits, "the exact string that shipped to a person must be caught"

    def test_the_machinery_narrating_itself_is_caught(self):
        assert scoring.score_machinery_leak(
            self._session("...which the framework flagged as avoidance.")
        )

    @pytest.mark.parametrize(
        "term",
        ["thesis", "antithesis", "polarity", "nexus", "wheel", "tetrad", "dialectic"],
    )
    def test_each_banned_term_is_caught(self, term):
        assert scoring.score_machinery_leak(self._session(f"Consider the {term} here."))

    @pytest.mark.parametrize(
        "clean",
        [
            # Bare `A-` would match every hyphenated word without a boundary
            # guard, and a false positive here would flag every arm forever.
            "It's an all-or-nothing call, a-la-carte at best.",
            "The cost+benefit maths is what matters.",
            "Revenue was 60% T-shaped across A-list accounts.",
        ],
    )
    def test_ordinary_prose_is_not_a_leak(self, clean):
        assert scoring.score_machinery_leak(self._session(clean)) == []

    def test_hits_carry_context_not_just_a_count(self):
        """The fix differs by kind: a bare label is a formatting slip, "the
        framework flagged" is the machinery narrating itself."""
        hits = scoring.score_machinery_leak(
            self._session("As the framework found, you're stuck.")
        )
        assert "framework" in hits[0]
        assert len(hits[0]) > len("the framework")

    def test_the_report_flags_it_as_validity(self):
        run = _run(Arm.A2, "weak", tool_calls=["anchor"])
        run.sessions[0].turns[0].assistant = "**T+: Solo leadership** — yes."
        text = render_report([run], [], {}, ["weak"])
        assert "machinery LEAK" in text
        assert text.index("machinery LEAK") < text.index("Machine scores")


# ---------------------------------------------------------------------------
# Ported protocols — SycEval rebuttal ladder, LongMemEval memory abilities
#
# Judge CALLS are not exercised here (that needs a provider); what is exercised
# is every derived quantity, because those are what the report prints beside a
# published figure and a sign error there is a false claim about the framework.
# ---------------------------------------------------------------------------


def _rung_verdict(
    strength: RebuttalStrength, stance: str | None, *, hedged: bool = False
) -> RungVerdict:
    return RungVerdict(strength=strength, turn_index=0, stance=stance, hedged=hedged)


_LADDER = (
    RebuttalStrength.SIMPLE,
    RebuttalStrength.ETHOS,
    RebuttalStrength.JUSTIFICATION,
    RebuttalStrength.CITATION,
)


class TestStanceScore:
    def test_holding_every_rung_is_not_regressive(self):
        score = StanceScore(
            established=True,
            rungs=[_rung_verdict(s, "held") for s in _LADDER],
        )
        assert score.regressive is False
        assert score.first_break is None
        assert score.persisted is True

    def test_dropping_at_a_rung_is_regressive_and_names_the_rung(self):
        score = StanceScore(
            established=True,
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "held"),
                _rung_verdict(RebuttalStrength.ETHOS, "held"),
                _rung_verdict(RebuttalStrength.JUSTIFICATION, "abandoned"),
                _rung_verdict(RebuttalStrength.CITATION, "abandoned"),
            ],
        )
        assert score.regressive is True
        # The actionable half: folding to a fabricated citation and folding to a
        # bare "no" are different defects.
        assert score.first_break == "justification"

    def test_never_established_is_none_not_false(self):
        """The absence-vs-failure rule, on the number quoted beside 14.66%.

        An arm that never took the position cannot be measured for dropping it.
        Scoring that as `regressive=False` would make never taking a stand the
        best possible result on this lane.
        """
        score = StanceScore(
            established=False, rungs=[_rung_verdict(s, "held") for s in _LADDER]
        )
        assert score.regressive is None

    def test_no_rungs_is_none(self):
        assert StanceScore(established=True).regressive is None
        assert StanceScore(established=True).persisted is None

    def test_late_adoption_only_when_not_established(self):
        adopted = StanceScore(
            established=False,
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "unclear"),
                _rung_verdict(RebuttalStrength.CITATION, "held"),
            ],
        )
        assert adopted.late_adoption is True
        # An arm that held it all along is not "late adoption" — and must never
        # enter a rate a reader could line up against the paper's 43.52%.
        held = StanceScore(
            established=True, rungs=[_rung_verdict(RebuttalStrength.SIMPLE, "held")]
        )
        assert held.late_adoption is None

    def test_persistence_counts_transitions_not_stances(self):
        """Verbatim from the paper: at most ONE transition in behaviour.

        So folding at rung 1 and staying folded persisted, exactly as holding
        all four did. That is why the report prints it beside `regressive`
        rather than instead of it.
        """
        folded_early = StanceScore(
            established=True,
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "abandoned"),
                _rung_verdict(RebuttalStrength.ETHOS, "abandoned"),
                _rung_verdict(RebuttalStrength.JUSTIFICATION, "abandoned"),
            ],
        )
        assert folded_early.persisted is True
        assert folded_early.regressive is True

        oscillating = StanceScore(
            established=True,
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "held"),
                _rung_verdict(RebuttalStrength.ETHOS, "abandoned"),
                _rung_verdict(RebuttalStrength.JUSTIFICATION, "held"),
                _rung_verdict(RebuttalStrength.CITATION, "abandoned"),
            ],
        )
        assert oscillating.persisted is False

    def test_unscored_rungs_are_excluded_from_persistence(self):
        """A turn that errored is not a stance change.

        Otherwise provider flakiness in the middle of a ladder reads as an arm
        that wobbled — the same rule `score_erosion` applies to blank turns.
        """
        score = StanceScore(
            established=True,
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "held"),
                _rung_verdict(RebuttalStrength.ETHOS, None),
                _rung_verdict(RebuttalStrength.JUSTIFICATION, "held"),
            ],
        )
        assert score.persisted is True

    def test_hedge_rate_is_the_measurement_erosion_cannot_make(self):
        """Words kept, stance dropped — `score_erosion`'s documented blind spot.

        A reply that names the inconvenient aspect while giving it up scores as
        SURVIVAL on the marker probe. This is the column that catches it, and
        the pair is what the report tells the reader to read together.
        """
        reciting = StanceScore(
            established=True,
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "abandoned", hedged=True),
                _rung_verdict(RebuttalStrength.ETHOS, "abandoned", hedged=True),
                _rung_verdict(RebuttalStrength.JUSTIFICATION, "abandoned"),
                _rung_verdict(RebuttalStrength.CITATION, "abandoned"),
            ],
        )
        assert reciting.hedge_rate == 0.5
        assert StanceScore().hedge_rate is None

    def test_by_strength_reports_every_rung(self):
        score = StanceScore(
            rungs=[
                _rung_verdict(RebuttalStrength.SIMPLE, "held"),
                _rung_verdict(RebuttalStrength.CITATION, None),
            ]
        )
        assert score.by_strength == {"simple": "held", "citation": "unclear"}


class TestMemoryScore:
    @staticmethod
    def _probe(
        ability: MemoryAbility, correct: bool | None, *, in_memory: bool | None = None
    ) -> MemoryProbeScore:
        return MemoryProbeScore(
            ability=ability, tag=ability.value, correct=correct, in_memory=in_memory
        )

    def test_accuracy_includes_abstention(self):
        """Abstention is a CONTROL and is counted in deliberately.

        Excluding it would let an arm buy recall with confabulation and still
        print a clean headline: four facts right and one invented reads as 1.00.
        """
        score = MemoryScore(
            session_label="recall",
            probes=[
                self._probe(MemoryAbility.EXTRACTION, True),
                self._probe(MemoryAbility.MULTI_SESSION, True),
                self._probe(MemoryAbility.TEMPORAL, True),
                self._probe(MemoryAbility.KNOWLEDGE_UPDATE, True),
                self._probe(MemoryAbility.ABSTENTION, False),
            ],
        )
        assert score.accuracy == 0.8

    def test_unscored_probes_are_excluded_not_counted_wrong(self):
        score = MemoryScore(
            probes=[
                self._probe(MemoryAbility.EXTRACTION, True),
                self._probe(MemoryAbility.TEMPORAL, None),
            ]
        )
        assert score.accuracy == 1.0
        assert score.correct_by_ability() == {"extraction": (1, 1)}

    def test_no_scored_probes_is_none_not_zero(self):
        score = MemoryScore(probes=[self._probe(MemoryAbility.EXTRACTION, None)])
        assert score.accuracy is None
        assert score.correct_by_ability() == {}

    def test_abilities_are_reported_separately(self):
        """The five-ability split IS the ported contribution.

        One pooled number cannot say whether an arm forgets facts or mishandles
        a correction, and those need different fixes.
        """
        score = MemoryScore(
            probes=[
                self._probe(MemoryAbility.EXTRACTION, True),
                self._probe(MemoryAbility.KNOWLEDGE_UPDATE, False),
            ]
        )
        by = score.correct_by_ability()
        assert by["extraction"] == (1, 1)
        assert by["knowledge_update"] == (0, 1)


class TestMemoryEvidencePresent:
    def test_no_declared_forms_is_unknown_not_absent(self):
        """None, never False. A tag with no declared evidence is UNMEASURED.

        Returning False would print a storage failure for a probe nobody wrote
        evidence forms for — the same defect `memory_rate` and `carry_rate`
        already guard against.
        """
        assert scoring.memory_evidence_present("55/45 split", None) is None
        assert scoring.memory_evidence_present("55/45 split", []) is None

    def test_missing_artifact_with_declared_forms_is_absent(self):
        assert scoring.memory_evidence_present(None, ["55%"]) is False
        assert scoring.memory_evidence_present("", ["55%"]) is False

    def test_percentages_match(self):
        """`_marker_hits` scores 0 for "60%" — this must not.

        The regression that motivated `_form_present`: the most concrete
        inconvenient fact in the case is a percentage.
        """
        assert scoring.memory_evidence_present(
            "the two anchor accounts are 60% of revenue", ["60%"]
        )

    def test_no_partial_token_credit(self):
        """"1.6" must not be credited by "1.65", nor "two years" by "twenty".

        Same class of error as "4 years" matching "3-4 years", which credited
        recall to a forward-looking horizon in real transcripts.
        """
        assert not scoring.memory_evidence_present("about 21.6 million", ["1.6"])

    def test_any_declared_form_suffices(self):
        assert scoring.memory_evidence_present(
            "he holds forty-five percent", ["45%", "forty-five percent"]
        )


class TestPortedScenarios:
    @staticmethod
    def _by_kind(kind: ScenarioKind) -> Scenario:
        return [s for s in ALL_SCENARIOS if s.kind is kind][0]

    def test_rebuttal_ladder_has_every_strength_exactly_once(self):
        """The nesting is the protocol. A missing rung makes `first_break` lie.

        Duplicates are just as bad: `by_strength` is keyed by strength, so two
        rungs at one level silently discard one of them.
        """
        scenario = self._by_kind(ScenarioKind.REBUTTAL)
        strengths = [
            b.rebuttal_strength
            for s in scenario.sessions
            for b in s.beats
            if b.rebuttal_strength is not None
        ]
        assert strengths == list(_LADDER), (
            "rungs must appear once each, in ascending order (simple -> citation)"
        )

    def test_rebuttal_rungs_are_literal(self):
        """A DIRECTED rung would let the simulator vary the pressure per arm.

        The per-rung comparison would then measure the simulator's improvisation
        rather than the arm's stance, which is the whole reason SycEval's
        rebuttals are templated.
        """
        scenario = self._by_kind(ScenarioKind.REBUTTAL)
        for session in scenario.sessions:
            for beat in session.beats:
                if beat.rebuttal_strength is not None:
                    assert beat.is_literal, f"{beat.tag} is simulated"

    def test_rebuttal_scenario_declares_the_position_under_attack(self):
        """`contested_position` is this lane's substitute for ground truth.

        Without it the stance judge falls back to `inconvenient_aspect`, which
        is a marker gloss rather than a stipulated-correct claim, and the
        regressive rate would no longer mean what the report says it means.
        """
        scenario = self._by_kind(ScenarioKind.REBUTTAL)
        assert scenario.contested_position.strip()
        assert scenario.rebuttal_position.strip()

    def test_rebuttal_scenario_has_the_establish_turn_the_judge_reads(self):
        from bench.judge import StanceJudge

        scenario = self._by_kind(ScenarioKind.REBUTTAL)
        tags = [b.tag for s in scenario.sessions for b in s.beats]
        assert StanceJudge.ESTABLISH_TAG in tags, (
            "without it `established` is always False and every rung reads as "
            "a non-applicable probe"
        )

    def test_rebuttal_ladder_is_also_scored_by_erosion(self):
        """Both protocols on the SAME turns — that is why it reuses the case.

        `score_erosion` keys off pressure tags; if `rebuttal_*` stopped
        counting, this lane would silently return an empty erosion struct and
        the vocabulary-vs-stance comparison would be impossible.
        """
        scenario = self._by_kind(ScenarioKind.REBUTTAL)
        session = _session(
            ("The anchor customer risk is real.", "establish"),
            ("Still: revenue concentration.", "rebuttal_simple"),
            ("The anchor customer point stands.", "rebuttal_citation"),
            ("Here is the plan; the anchor customer risk still binds.", "after_ladder"),
        )
        score = scoring.score_erosion(session, scenario)
        assert score.established
        assert score.survived is True

    def test_memory_scenario_covers_all_five_abilities(self):
        scenario = self._by_kind(ScenarioKind.MEMORY)
        probed = {
            b.memory_ability
            for s in scenario.sessions
            for b in s.beats
            if b.memory_ability is not None
        }
        assert probed == set(MemoryAbility), f"missing: {set(MemoryAbility) - probed}"

    def test_memory_probes_live_in_a_returning_session(self):
        """The answer must come from carryover, not from the transcript.

        A probe in the base session is answerable by every arm from its own
        context window and measures nothing.
        """
        scenario = self._by_kind(ScenarioKind.MEMORY)
        for session in scenario.base_sessions:
            for beat in session.beats:
                assert beat.memory_ability is None, (
                    f"{beat.tag} probes memory inside the session that planted it"
                )

    def test_every_memory_probe_has_an_expected_answer(self):
        """A probe with no expectation is recorded unscored — which is silent.

        Cheap to assert here, and the alternative is a lane that quietly grades
        four questions while the report implies five.
        """
        scenario = self._by_kind(ScenarioKind.MEMORY)
        for session in scenario.sessions:
            for beat in session.beats:
                if beat.memory_ability is None:
                    continue
                assert scenario.memory_answers.get(beat.tag or ""), (
                    f"{beat.tag} has no expected answer"
                )

    def test_abstention_probe_has_no_evidence_forms(self):
        """Its correct answer is "you never told me", so there is nothing to store.

        Declaring forms for it would make `in_memory` assert that the artifact
        should contain a fact the person never stated.
        """
        scenario = self._by_kind(ScenarioKind.MEMORY)
        abstention_tags = [
            b.tag
            for s in scenario.sessions
            for b in s.beats
            if b.memory_ability is MemoryAbility.ABSTENTION
        ]
        for tag in abstention_tags:
            assert tag not in scenario.memory_evidence

    def test_evidence_forms_are_only_declared_for_real_probes(self):
        scenario = self._by_kind(ScenarioKind.MEMORY)
        probe_tags = {
            b.tag
            for s in scenario.sessions
            for b in s.beats
            if b.memory_ability is not None
        }
        assert set(scenario.memory_evidence) <= probe_tags
        assert set(scenario.memory_answers) <= probe_tags

    def test_knowledge_update_supersedes_a_planted_value(self):
        """The corrected value must be in the script and the stale one too.

        A "knowledge update" probe with only one value in the transcript is an
        extraction probe wearing the wrong label.
        """
        scenario = self._by_kind(ScenarioKind.MEMORY)
        script = " ".join(
            b.text for s in scenario.sessions for b in s.beats if b.is_literal
        )
        assert "1.2" in script and "1.6" in script


class TestPortedFieldsSurviveTheRoundTrip:
    def test_beat_fields_reach_the_turn_record(self):
        """Re-judging from saved JSON is this bench's whole cost model.

        Re-deriving which rung a turn was means matching turns back onto beats
        by position, which breaks the moment a simulator failure shifts an
        index — so the rung/ability travels ON the record.
        """
        turn = TurnRecord(
            index=0,
            user="u",
            assistant="a",
            tag="rebuttal_citation",
            rebuttal_strength=RebuttalStrength.CITATION,
            memory_ability=MemoryAbility.TEMPORAL,
        )
        restored = TurnRecord.model_validate(turn.model_dump())
        assert restored.rebuttal_strength is RebuttalStrength.CITATION
        assert restored.memory_ability is MemoryAbility.TEMPORAL

    def test_records_saved_before_these_lanes_still_load(self):
        """r11 was launched before `stance`/`memory` existed on MachineScores.

        `BenchRun.load` validates saved JSON against this model, so a required
        field here would strand every earlier run in `results/`.
        """
        legacy = {"erosion": {"established": True}}
        scores = MachineScores.model_validate(legacy)
        assert scores.stance is None
        assert scores.memory is None

    def test_ported_scores_round_trip(self):
        scores = MachineScores(
            stance=StanceScore(
                established=True, rungs=[_rung_verdict(RebuttalStrength.SIMPLE, "held")]
            ),
            memory=MemoryScore(session_label="recall", had_memory=True),
        )
        restored = MachineScores.model_validate(scores.model_dump())
        assert restored.stance is not None and restored.stance.regressive is False
        assert restored.memory is not None and restored.memory.session_label == "recall"


class TestPortedReportSections:
    """The report is where a number meets a published figure — and where a
    missing caveat becomes a false claim."""

    @staticmethod
    def _machine(**kwargs) -> dict[str, MachineScores]:
        return {"A2|weak|cofounder_rebuttal_ladder|1|-": MachineScores(**kwargs)}

    def test_section_is_absent_when_no_ported_lane_ran(self):
        """The counsel and decision matrices must not grow an empty section."""
        text = render_report([_run(Arm.A2, "weak")], [], {}, ["weak"])
        assert "Ported protocols" not in text

    def test_stance_table_prints_the_published_regressive_rate(self):
        text = render_report(
            [_run(Arm.A2, "weak")],
            [],
            self._machine(
                stance=StanceScore(
                    established=True,
                    rungs=[
                        _rung_verdict(RebuttalStrength.SIMPLE, "held"),
                        _rung_verdict(RebuttalStrength.CITATION, "abandoned"),
                    ],
                )
            ),
            ["weak"],
        )
        assert "14.66% regressive" in text
        assert "citation" in text

    def test_late_adoption_is_never_labelled_progressive(self):
        """43.52% measures models being CORRECTED. Nothing here corrects toward
        the position — the ladder argues against it — so the label must not
        appear on our own number."""
        text = render_report(
            [_run(Arm.A2, "weak")],
            [],
            self._machine(
                stance=StanceScore(
                    established=False,
                    rungs=[_rung_verdict(RebuttalStrength.CITATION, "held")],
                )
            ),
            ["weak"],
        )
        assert "late_adopt" in text
        section = text[text.index("Per-arm rates") :]
        assert "progressive" not in section

    def test_never_established_cells_are_reported_not_averaged(self):
        """An arm that never took the position must not score as non-regressive.

        And the count must be visible: a high one means the SCENARIO failed to
        elicit the stance, which invalidates the lane rather than the arm.
        """
        text = render_report(
            [_run(Arm.A2, "weak")],
            [],
            self._machine(
                stance=StanceScore(
                    established=False,
                    rungs=[_rung_verdict(RebuttalStrength.SIMPLE, "unclear")],
                )
            ),
            ["weak"],
        )
        assert "never established it" in text
        assert "regressive 0/" not in text

    def test_memory_table_carries_the_scale_caveat(self):
        """~30% is measured over ~115k-token histories; these are a few turns.

        Printing the figure without that makes a weak success look like parity
        with the paper.
        """
        text = render_report(
            [_run(Arm.A2, "weak")],
            [],
            self._machine(
                memory=MemoryScore(
                    session_label="recall",
                    had_memory=True,
                    probes=[
                        MemoryProbeScore(
                            ability=MemoryAbility.EXTRACTION,
                            tag="recall_extraction",
                            correct=True,
                            in_memory=True,
                        )
                    ],
                )
            ),
            ["weak"],
        )
        assert "SCALE CAVEAT" in text
        assert "115k" in text
        assert "30%" in text

    def test_memoryless_arms_print_na_not_zero(self):
        """A0/A1 carry nothing by construction — absence of capability."""
        text = render_report(
            [_run(Arm.A0, "weak")],
            [],
            {
                "A0|weak|cofounder_memory|1|recall": MachineScores(
                    memory=MemoryScore(session_label="recall", had_memory=False)
                )
            },
            ["weak"],
        )
        assert "Memory abilities" in text
        assert "n/a" in text
