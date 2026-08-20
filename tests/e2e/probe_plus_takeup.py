"""Does the plus-restatement CHECK reduce plus-restatement? A/B, pre-registered.

THE DEFECT
==========
Rule 1's take-up half: T+/A+ are constructive developments that actively balance
the other side, so a plus must develop its own parent in a way whose RESULT also
supplies what the other pole is for. A plus that only names its own pole's native
benefit satisfies parentage and fails take-up.

`probe_option_pair_tetrads.py` audited 128 plus slots on the weak tier and found
**17 of them (13.3%)** doing exactly that — the auditor's own words, "merely
restates its pole without taking up what the other pole offers". In the same audit
output, minus-parentage — the defect the archive had been chasing for weeks — ran
at **3.1%**. The take-up defect is 4x the one being hunted, and it was found as a
side-observation of a run designed for something else.

WHY THE FIX IS A CHECK AND NOT A FIFTH RESTATEMENT
==================================================
The take-up clause was already stated four times in the generation stack:
`ASPECT_DEFINITIONS`, the `TetradDto` plus-field descriptions, `_tetrad_prompt`
step 1, and both sibling prompts. Four assertions, 13.3%. Minus-parentage was
stated fewer times but had a RE-READ STEP in the numbered procedure, and ran at
3.1%. The difference between the two rules was not how forcefully each was stated;
it was that only one of them was verified. So the change under test is a
verification step — `PLUS_RESTATEMENT_CHECK`, stated once and interpolated into
every generation path — plus one worked example of the plus failure and of its
over-correction. Restating the rule a fifth time is the intervention already
measured to not work.

The over-correction is in the example on purpose. The obvious repair to "A+ only
restates A" is to bolt T onto A+ as a constraint, which hands the generative act
to T and produces T+ in A's clothes — the option-pair auditor scored a real
instance of that as `other_pole`. So the two defects trade off, and both arms are
audited for both.

PRE-REGISTRATION
================
Population: the same 16 tensions as `probe_option_pair_tetrads` (8 OPTION_PAIR +
8 OPPOSITION), 2 orderings x 3 replicates x 2 arms = **192 tetrads, 96 per arm**.
No outcome selection: 13.3% was measured over all 16 tensions, not over the
subset that failed, which is what keeps the power calculation below unconditional.
(The 2026-08-20 lesson: an enrichment hypothesis is itself a hypothesis, and a
power number inherits the uncertainty of the base rate fed into it. Here the base
rate is measured, on this population, with this instrument.)

Each tetrad yields 2 plus slots and 2 minus slots -> **192 plus slots per arm**.

PRIMARY endpoint: plus valence failure — `valence_matches_claim == false` on T+ or
A+, the identical field and auditor that produced the 13.3%.
  CONFIRMED  iff fixed rate <= 4.4% AND Fisher two-sided p < 0.05
  NOT CONFIRMED iff fixed rate >= 9.0%
  INDETERMINATE in between, and the registered consequence is to say so rather
  than to re-read the run.

Power at n=192/arm, computed before the run and pinned in the free tests:
  13.3% -> 4.4%  (a two-thirds cut)   0.85
  13.3% -> 6.7%  (a halving)          0.52
  13.3% -> 9.0%  (a third off)        0.22
**Stated up front: this run is powered for a LARGE fix only.** A real halving
would be missed about half the time, so a null bounds the effect at roughly "not
a two-thirds cut" and does not refute the fix. Reporting a null as "the check
does nothing" would be the `probe_tetrad_pole` mistake again.

CO-PRIMARY GUARD (registered WEAK): minus misparentage must not worsen — same
`other_pole` + `neither` endpoint as the archive, 192 minus slots per arm. At the
3.1% base rate this has **0.22 power to detect a doubling** and 0.66 to detect a
tripling. So a clean guard CANNOT be reported as "no harm done"; it rules out a
tripling and nothing smaller. It is registered anyway because the over-correction
failure mode predicts harm in exactly this direction, and an unmeasured
prediction is worse than a weakly measured one.

SECONDARIES (descriptive, registered so they cannot be invented afterwards):
  * T+ vs A+ split of the plus defect within each arm.
  * Parent shape of flagged pluses (`other_pole` = drifted into the other pole,
    the over-correction; `own_pole` + valence false = plain restatement).
  * Per-tension counts, to see whether either arm's rate rides on 1-2 tensions.

Pairing was considered and rejected as the analysis unit: the arms are interleaved
cell by cell, so pairs exist, but exact McNemar on 96 pairs reaches only 0.38 power
under plausible discordance (0.10/0.03) — weaker than Fisher on the 192 slots.
The interleaving is therefore a DRIFT CONTROL, not a pairing; arms alternate every
single cell, which is stronger than the block-of-8 alternation the option-pair run
had to admit to.

HOW THE BASELINE ARM IS RECONSTRUCTED
=====================================
The fix is committed, so "baseline" is the fixed code with the fix subtracted at
render time:
  1. `SYSTEM_PROMPT` — the plus worked example paragraph is sliced out.
  2. `_tetrad_prompt` — the rendered step 3 line is replaced with the pre-fix
     literal (`_PREFIX_STEP3`, taken verbatim from the commit before the fix).
Both operations RAISE if they do not change the string, and the fixed arm renders
through the same wrapper purely to assert the check IS present. Per-arm counts are
printed. Without those assertions a silent no-op patch runs the fixed prompt in
both arms and produces a null that looks like evidence — the failure mode that a
direction-only manipulation check hid in the previous run.

Only the full-tetrad path is exercised (that is what production generation uses).
The check reaching the other two generation paths is a structural claim, tested
free in `tests/test_prompt_review_regressions.py::TestPlusTakeUpIsChecked`.

COST
====
192 sequential tetrad generations on the weak tier plus 768 audit calls. The
64-tetrad option-pair run took ~30 minutes of generation; expect ~90 minutes here
before audits. `PROBE_PLUS_TAKEUP_LIMIT=n` truncates and says so loudly; a
truncated run does not carry the registered bands.

RESULT (2026-08-20, 192/192 tetrads generated, 0 failures, 768 audits, weak tier
        generation / fable-5 auditor — the same auditor as the 13.3% measurement)
====================================================================
Manipulation check, exact: **96/96 baseline renders downgraded, 96/96 fixed
renders verified.** No cell in either arm ran the other arm's prompt.

PRIMARY — plus valence failure:
    baseline  31/192 = 16.1%  [95% Wilson 11.6-22.0]
    fixed     15/192 =  7.8%  [95% Wilson  4.8-12.5]
    Fisher two-sided p = 0.0176
**Registered verdict: INDETERMINATE.** The reduction is significant at the
registered alpha on the registered endpoint — a 52% relative cut — and 7.8% sits
between the 4.4% CONFIRMED ceiling and the 9.0% NOT-CONFIRMED floor. So the
registered word is INDETERMINATE and the finding is "the check roughly halves
plus-restatement", stated together and not traded for each other.

And the band was not missed for lack of power: at the baseline rate this run
actually observed (16.1%), the design had **0.97** power to detect a drop to the
4.4% ceiling and 0.63 for a halving. The two-thirds cut is therefore ruled out
about as firmly as this lane rules anything out. The effect is real and smaller
than the ceiling I registered.

Which exposes a design error worth more than the result: **I picked the ceiling
off the power table, not off what would matter.** 4.4% was "the effect 192 slots
can see at 0.85", not "the smallest improvement worth shipping". A band chosen for
detectability answers a question about the instrument; a band chosen for
consequence answers a question about the fix. When those two differ — and they
did — the honest move is to register the consequential band and say up front that
the run is a screen for anything smaller.

GUARD (registered WEAK) — minus misparentage:
    baseline  18/192 = 9.4%   fixed 14/192 = 7.3%   p = 0.5803
No harm detected, and the guard turned out STRONGER than registered because its
base rate came in high: at the observed 9.4% it had 0.71 power for a doubling
(registered 0.22, computed at the 3.1% base rate the archive had). It still has
only 0.25 for a +50% drift, so "no harm" reaches a doubling and stops there.

THE FINDING THAT OUTRANKS THE PRIMARY: THE BASE RATES DID NOT REPRODUCE
======================================================================
Same 16 tensions, same generation tier, same auditor model, same endpoint code,
baseline prompt verified byte-identical to the pre-fix commit, four hours apart:
    minus misparentage   3.1% (4/128, option-pair run)  ->  9.4% (18/192)
                         Fisher two-sided p = 0.0406
    plus valence failure 13.3% (17/128)                 ->  16.1% (31/192)
                         p = 0.5257  (this one reproduced)
So the endpoint the archive spent three runs and a replication chasing moved 3x
between two runs of the same instrument, at conventional significance, with no
intervention between them. Consequences, in order of importance:
  1. **Cross-run rate comparisons in this archive are not safe.** Any verdict
     resting on "this run's rate vs that run's rate" — including this probe's own
     sizing input — inherits a variance nobody has bounded. Only within-run arms
     are comparable. Registering the baseline arm rather than borrowing 13.3%
     turned out to be the load-bearing decision of the design.
  2. It adds a second explanation for `probe_tetrad_pole`'s two irreconcilable
     runs (4/72 then 9/72). `power.py` attributed them to 0.28 power, which was
     true; this says the base rate itself may also have moved.
  3. A mechanism is available and was NOT measured here: `StatementClassification`
     runs fresh each run, and the branch it lands on selects the apex row
     interpolated into the tetrad prompt (`probe_classifier_stability.py` exists
     because that classifier drifts). A pole classifying differently is a
     different prompt, not noise. **This run did not print the per-pole
     classification, so drift cannot be told apart from sampling variance.** The
     readout is now in the run (added after the fact, so it is empty for this
     result) — the next run can check it, and no future probe in this lane should
     omit it.

LIMITATIONS OF THIS RUN, STATED RATHER THAN IMPLIED
==================================================
  * Arms alternate every cell, but the ORDER WITHIN a pair is always
    baseline-then-fixed. Strict alternation controls slow drift; it does not
    control a position-within-pair effect, which would align with the arm. Not
    reordered mid-flight (that would have invalidated the run) and not corrected
    afterwards, so it stands as a limitation. Counter-balancing the within-pair
    order is the first change any replication should make.
  * The fix is TWO changes measured as one: the interpolated check and the worked
    example both landed. Which one carries the effect is unseparated.
  * Weak tier only. Nothing here says a stronger model needs the check.
  * The secondaries are descriptive and unpowered. For the record: the plus defect
    fell at both positions (T+ 14->5, A+ 17->10); the over-correction the worked
    example warns about did not appear as a net drift into the other pole
    (baseline other_pole+neither 17, fixed 13); and no arm's rate rides on one or
    two tensions, though `roadmap_weighting` is the one tension that went the
    wrong way (3/12 -> 5/12).

Run:
  poetry run pytest tests/e2e/probe_plus_takeup.py -s --real-llm
  poetry run pytest tests/e2e/probe_plus_takeup.py -s   (free: population, power
      pins, and the baseline-reconstruction manipulation check; no provider calls)
"""

from __future__ import annotations

import collections
import contextlib
import inspect
import os
import time
from typing import Iterator

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import aspect_generation
from dialectical_framework.concerns.statement_classification import \
    ClassificationResult
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.power import fisher_exact_two_sided, fisher_power, mcnemar_power
# The instrument and the population are imported, never re-typed: same auditor
# prompt, same verdict model, same generation path, same 16 tensions. A copy would
# drift and the 13.3% this run is sized against would stop being comparable.
from e2e.probe_option_pair_tetrads import (OPPOSITION,  # noqa: F401
                                           OPTION_PAIR, _TENSIONS, _wilson)
from e2e.probe_tetrad_pole import (_Cell, _PoleVerdict,  # noqa: F401
                                   _audit_prompt, _branch_of, _generate)

pytestmark = [pytest.mark.llm]


BASELINE = "baseline"
FIXED = "fixed"

_REPLICATES = 3

#: Registered bands on the PRIMARY (plus valence failure rate in the fixed arm).
_PREREG_BASELINE_RATE = 0.133
_PREREG_FIXED_CEILING = 0.044
_PREREG_NULL_FLOOR = 0.090
_PREREG_ALPHA = 0.05

#: Registered power at n=192 plus slots per arm. Pinned in the free tests so an
#: edit to the population cannot silently invalidate the interpretation rules.
_PREREG_POWER_TWO_THIRDS_CUT = 0.85
_PREREG_POWER_HALVING = 0.52
_PREREG_POWER_GUARD_DOUBLING = 0.22

#: `_tetrad_prompt` step 3 as it stood in the commit BEFORE the fix
#: (`git show 84ef6bd:src/dialectical_framework/concerns/aspect_generation.py`).
_PREFIX_STEP3 = (
    "3. Re-read both aspects against step 1. If one of them is really the OTHER "
    "parent developed, rewrite it from its own parent; opposing the facing aspect "
    "well is not a reason to keep the wrong parentage."
)
_STEP3_PREFIX_MARKER = "3. Re-read both aspects"
#: The commit the baseline arm reconstructs — the one before the fix landed.
_PREFIX_COMMIT = "84ef6bd"
_PLUS_EXAMPLE_MARKER = "The mistake to avoid on a plus."


# --- baseline reconstruction ---------------------------------------------------


def _strip_plus_example(prompt: str) -> str:
    """Remove the plus worked example paragraph, restoring the pre-fix prompt."""
    start = prompt.find(_PLUS_EXAMPLE_MARKER)
    if start < 0:
        raise AssertionError(
            f"{_PLUS_EXAMPLE_MARKER!r} not in SYSTEM_PROMPT — the baseline arm "
            f"would silently run the same prompt as the fixed arm"
        )
    end = prompt.find("\n\n", start)
    if end < 0:
        raise AssertionError("plus example is not paragraph-terminated")
    stripped = prompt[:start] + prompt[end + 2 :]
    if _PLUS_EXAMPLE_MARKER in stripped or len(stripped) >= len(prompt):
        raise AssertionError("plus example removal was a no-op")
    return stripped


def _downgrade_step3(rendered: str) -> str:
    """Replace the rendered step 3 with the pre-fix literal.

    Matched on the line prefix rather than the full current wording: a later edit
    to step 3 should still produce a valid baseline, and if the step disappears
    entirely this raises instead of quietly comparing a prompt to itself.
    """
    lines = rendered.split("\n")
    for index, line in enumerate(lines):
        if line.startswith(_STEP3_PREFIX_MARKER):
            if line == _PREFIX_STEP3:
                raise AssertionError(
                    "step 3 already IS the pre-fix literal — nothing to subtract"
                )
            lines[index] = _PREFIX_STEP3
            break
    else:
        raise AssertionError(
            f"no line starting {_STEP3_PREFIX_MARKER!r} in the rendered tetrad "
            f"prompt — the baseline reconstruction is stale"
        )
    out = "\n".join(lines)
    if aspect_generation.PLUS_RESTATEMENT_CHECK in out:
        raise AssertionError(
            "the check survived the downgrade — it reaches the tetrad prompt from "
            "somewhere other than step 3, so the baseline arm is not a baseline"
        )
    return out


@contextlib.contextmanager
def _arm(arm: str, counts: collections.Counter) -> Iterator[None]:
    """Render the tetrad prompt as `arm` requires, counting every render.

    The FIXED arm goes through the same wrapper and asserts the check is present.
    That is not ceremony: it is the only thing standing between a leaked patch and
    a null that reads as evidence.
    """
    original_prompt = aspect_generation.SYSTEM_PROMPT
    original_tetrad = aspect_generation.AspectGeneration._tetrad_prompt

    def wrapper(self, existing_context: str) -> str:
        rendered = original_tetrad(self, existing_context)
        if arm == FIXED:
            if aspect_generation.PLUS_RESTATEMENT_CHECK not in rendered:
                raise AssertionError(
                    "fixed arm rendered WITHOUT the check — a leaked baseline "
                    "patch, or the fix is no longer in the tetrad path"
                )
            counts["fixed_verified"] += 1
            return rendered
        out = _downgrade_step3(rendered)
        counts["baseline_downgraded"] += 1
        return out

    aspect_generation.AspectGeneration._tetrad_prompt = wrapper  # type: ignore[method-assign]
    if arm == BASELINE:
        aspect_generation.SYSTEM_PROMPT = _strip_plus_example(original_prompt)
    try:
        yield
    finally:
        aspect_generation.AspectGeneration._tetrad_prompt = original_tetrad  # type: ignore[method-assign]
        aspect_generation.SYSTEM_PROMPT = original_prompt


def _plan() -> list[tuple[str, str, str, str, int, str, str]]:
    """(arm, stratum, label, ordering, replicate, t_text, a_text) for every cell.

    Arms alternate on EVERY cell. Provider drift over a ~2 hour run cannot land on
    one arm, which is the confound that made two `probe_tetrad_pole` runs
    incomparable and that the option-pair run could only partly control.
    """
    plan: list[tuple[str, str, str, str, int, str, str]] = []
    for rep in range(1, _REPLICATES + 1):
        for ordering in ("forward", "swapped"):
            for stratum, label, side_x, side_y in _TENSIONS:
                t_text, a_text = (
                    (side_x, side_y) if ordering == "forward" else (side_y, side_x)
                )
                for arm in (BASELINE, FIXED):
                    plan.append((arm, stratum, label, ordering, rep, t_text, a_text))
    return plan


# --- free checks --------------------------------------------------------------


class TestThePreRegistrationIsAuditable:
    """No provider, no Memgraph. The population, the power table, and — most
    importantly — the baseline reconstruction are all checkable for free, so the
    manipulation check does not have to wait for the run that depends on it."""

    # Name-shadow conftest's autouse graph fixtures for this class only.
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def test_cell_count_and_arm_balance(self):
        plan = _plan()
        assert len(plan) == 16 * 2 * _REPLICATES * 2 == 192
        per_arm = collections.Counter(a for a, *_ in plan)
        assert per_arm[BASELINE] == per_arm[FIXED] == 96
        # 2 plus slots per tetrad -> the 192/arm the power calc was run on
        assert per_arm[FIXED] * 2 == 192

    def test_arms_alternate_every_cell(self):
        """The drift control, enforced rather than described."""
        arms = [a for a, *_ in _plan()]
        assert all(arms[i] != arms[i + 1] for i in range(len(arms) - 1))

    def test_every_tension_appears_equally_in_both_arms(self):
        seen: dict[tuple[str, str], int] = collections.Counter()
        for arm, _stratum, label, _ordering, _rep, _t, _a in _plan():
            seen[(arm, label)] += 1
        for _stratum, label, _x, _y in _TENSIONS:
            assert seen[(BASELINE, label)] == seen[(FIXED, label)] == 2 * _REPLICATES

    def test_population_is_the_option_pair_population_unchanged(self):
        """Not outcome-selected, and not re-typed. 13.3% was measured over all 16
        tensions; if this list drifts, the sizing stops applying."""
        assert len(_TENSIONS) == 16
        strata = collections.Counter(s for s, _l, _x, _y in _TENSIONS)
        assert strata[OPTION_PAIR] == strata[OPPOSITION] == 8

    def test_the_baseline_arm_actually_subtracts_the_fix(self):
        """The manipulation check, free and exact.

        A patch that fails to change the prompt produces a null indistinguishable
        from a fix that does not work. The previous run shipped a manipulation
        check that could only report a direction and printed HELD on a 0.026
        separation; this one is binary and deterministic, so it is checked here
        rather than inferred from the result.
        """
        gen = aspect_generation.AspectGeneration.__new__(
            aspect_generation.AspectGeneration
        )
        gen._thesis = Statement(
            text="Standardise the deployment toolchain",
            meaning="dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence",
        )
        gen._antithesis = Statement(
            text="Let each team choose its own toolchain",
            meaning="dx://taxonomy/System(General.v1)/Viability/Flexibility/Adaptation",
        )
        gen._text = ""
        gen._not_like_these = []
        gen._existing_aspects = {}

        counts: collections.Counter = collections.Counter()

        with _arm(FIXED, counts):
            fixed = aspect_generation.AspectGeneration._tetrad_prompt(gen, "")
        with _arm(BASELINE, counts):
            baseline = aspect_generation.AspectGeneration._tetrad_prompt(gen, "")
            baseline_system = aspect_generation.SYSTEM_PROMPT

        assert counts["fixed_verified"] == 1
        assert counts["baseline_downgraded"] == 1
        assert aspect_generation.PLUS_RESTATEMENT_CHECK in fixed
        assert aspect_generation.PLUS_RESTATEMENT_CHECK not in baseline
        assert _PREFIX_STEP3 in baseline
        assert "two distinct failures" not in baseline
        # the worked example goes too, and only in the baseline arm
        assert _PLUS_EXAMPLE_MARKER not in baseline_system
        assert _PLUS_EXAMPLE_MARKER in aspect_generation.SYSTEM_PROMPT
        # and EXACTLY ONE line differs: the arms must not diverge on anything
        # except step 3, or the primary is comparing two unrelated prompts
        differing = [
            (b, f)
            for b, f in zip(baseline.split("\n"), fixed.split("\n"))
            if b != f
        ]
        assert len(differing) == 1, differing
        assert differing[0][0] == _PREFIX_STEP3
        assert len(baseline.split("\n")) == len(fixed.split("\n"))

    def test_the_patch_restores_state_even_when_the_body_raises(self):
        """A leaked patch would contaminate every later cell in the run, and the
        contamination would be invisible in the output."""
        original = aspect_generation.SYSTEM_PROMPT
        counts: collections.Counter = collections.Counter()
        with pytest.raises(RuntimeError):
            with _arm(BASELINE, counts):
                assert aspect_generation.SYSTEM_PROMPT != original
                raise RuntimeError("boom")
        assert aspect_generation.SYSTEM_PROMPT == original

    def test_the_registered_power_table_is_the_real_number(self):
        """What licenses calling a null a BOUND rather than a refutation."""
        assert fisher_power(192, _PREREG_BASELINE_RATE, _PREREG_FIXED_CEILING) == (
            pytest.approx(_PREREG_POWER_TWO_THIRDS_CUT, abs=0.03)
        )
        assert fisher_power(
            192, _PREREG_BASELINE_RATE, _PREREG_BASELINE_RATE / 2
        ) == pytest.approx(_PREREG_POWER_HALVING, abs=0.03)
        assert fisher_power(192, _PREREG_BASELINE_RATE, _PREREG_NULL_FLOOR) == (
            pytest.approx(0.22, abs=0.03)
        )

    def test_the_guard_is_registered_as_weak_with_the_real_number(self):
        """0.22 for a doubling. Pinned so 'the guard came back clean' can never be
        written up as 'the fix did no harm'."""
        assert fisher_power(192, 0.031, 0.062) == pytest.approx(
            _PREREG_POWER_GUARD_DOUBLING, abs=0.03
        )
        assert fisher_power(192, 0.031, 0.093) == pytest.approx(0.66, abs=0.03)

    def test_pairing_was_rejected_on_a_number_not_a_preference(self):
        assert mcnemar_power(96, 0.10, 0.03) == pytest.approx(0.38, abs=0.03)
        assert mcnemar_power(96, 0.10, 0.03) < _PREREG_POWER_TWO_THIRDS_CUT

    def test_the_sizing_base_rate_is_the_measured_one(self):
        """13.3% = 17/128 pooled plus valence failures in the option-pair run
        (OPTION_PAIR 12/64 + OPPOSITION 5/64), over the whole population."""
        assert (12 + 5) / 128 == pytest.approx(_PREREG_BASELINE_RATE, abs=0.001)
        # and the two strata were not distinguishable on it, which is why this run
        # pools them instead of stratifying
        assert fisher_exact_two_sided(12, 52, 5, 59) == pytest.approx(
            0.1162, abs=0.001
        )

    def test_registered_bands_are_ordered(self):
        assert (
            _PREREG_FIXED_CEILING
            < _PREREG_NULL_FLOOR
            < _PREREG_BASELINE_RATE
        )

    def test_the_baseline_arm_is_byte_identical_to_the_pre_fix_commit(self):
        """Stronger than "the marker is gone": the reconstructed baseline prompt
        must be the prompt that actually produced the archive's numbers.

        Checked because the RESULT leans on it — the base rates not reproducing is
        only a statement about run-to-run variance if the two runs really ran the
        same prompt. Compares the SYSTEM_PROMPT source literal rather than exec'ing
        the old module: the interpolated constants are unchanged, and importing a
        detached copy of the module breaks dataclass resolution.
        """
        import subprocess  # noqa: PLC0415

        path = "src/dialectical_framework/concerns/aspect_generation.py"
        try:
            old_source = subprocess.run(
                ["git", "show", f"{_PREFIX_COMMIT}:{path}"],
                capture_output=True, text=True, check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            pytest.skip(f"pre-fix commit not reachable: {exc}")

        def literal(source: str) -> str:
            opener = 'SYSTEM_PROMPT = f"""'
            start = source.index(opener)
            return source[start : source.index('"""', start + len(opener))]

        assert _strip_plus_example(literal(inspect.getsource(aspect_generation))) == (
            literal(old_source)
        ), "the baseline arm is NOT the pre-fix prompt"

    def test_the_recorded_primary_is_the_number_the_docstring_states(self):
        """The RESULT's arithmetic. Its whole value is that "significant" and
        "INDETERMINATE" are both true of the same table, so neither can be dropped
        in a later retelling."""
        assert fisher_exact_two_sided(31, 161, 15, 177) == pytest.approx(
            0.0176, abs=0.001
        )
        assert 31 / 192 == pytest.approx(0.161, abs=0.001)
        assert 15 / 192 == pytest.approx(0.078, abs=0.001)
        # significant, and still above the CONFIRMED ceiling: hence INDETERMINATE
        assert _PREREG_FIXED_CEILING < 15 / 192 < _PREREG_NULL_FLOOR

    def test_the_registered_band_was_not_missed_for_lack_of_power(self):
        """What licenses "the effect is real and smaller than the ceiling" instead
        of "the run could not see the ceiling"."""
        assert fisher_power(192, 0.161, _PREREG_FIXED_CEILING) == pytest.approx(
            0.97, abs=0.03
        )
        assert fisher_power(192, 0.161, 0.0805) == pytest.approx(0.63, abs=0.03)

    def test_the_recorded_guard_and_its_real_sensitivity(self):
        """The guard came back clean AND stronger than registered, because its base
        rate came in high. Both halves pinned: 0.71 for a doubling, 0.25 for +50%,
        so "no harm" reaches a doubling and stops."""
        assert fisher_exact_two_sided(18, 174, 14, 178) == pytest.approx(
            0.5803, abs=0.001
        )
        assert fisher_power(192, 0.094, 0.188) == pytest.approx(0.71, abs=0.03)
        assert fisher_power(192, 0.094, 0.141) == pytest.approx(0.25, abs=0.03)

    def test_the_base_rates_did_not_reproduce_across_runs(self):
        """The finding that outranks the primary, pinned because every future
        cross-run comparison in this lane is constrained by it: the minus endpoint
        moved 3x between two runs of one instrument at p=0.04, while the plus
        endpoint reproduced."""
        assert fisher_exact_two_sided(4, 124, 18, 174) == pytest.approx(
            0.0406, abs=0.001
        ), "minus misparentage 3.1% (option-pair) vs 9.4% (this baseline)"
        assert fisher_exact_two_sided(17, 111, 31, 161) == pytest.approx(
            0.5257, abs=0.001
        ), "plus valence 13.3% (option-pair) vs 16.1% (this baseline)"


# --- the run ------------------------------------------------------------------


@pytest.mark.real_llm
@pytest.mark.asyncio
# NOT @traced — conftest's `traced` serialises the test's arguments as span input
# and `di_container` is cyclic; it pins the process at 100% CPU with no output.
# `probe_tetrad_pole.py` lost two full runs to that trap.
async def test_the_check_reduces_plus_restatement(di_container) -> None:
    plan = _plan()
    limit = int(os.environ.get("PROBE_PLUS_TAKEUP_LIMIT", "0") or 0)
    if limit:
        # No silent caps. Truncating also breaks arm balance unless it is even.
        print(f"\n!! PROBE_PLUS_TAKEUP_LIMIT={limit} active — {limit} of "
              f"{len(plan)} pre-registered tetrads. PARTIAL RUN: the registered "
              f"bands assume the full population and do NOT apply.", flush=True)
        plan = plan[:limit]

    case_node = Case()
    case_node.commit()

    config = E2EConfig.from_env()
    gen_model = config.tiers["weak"]

    render_counts: collections.Counter = collections.Counter()
    cells: list[tuple[str, str, _Cell]] = []  # (arm, stratum, cell)

    with scope(case_node.sid):
        print(f"\n=== generating {len(plan)} tetrads on the WEAK tier: "
              f"{gen_model} ===", flush=True)
        class_cache: dict[str, ClassificationResult] = {}
        # Sequential: GQLAlchemy graph writes are not concurrency-safe and every
        # cell writes Perspective/Polarity/Statement before its LLM call.
        for index, (arm, stratum, label, ordering, rep, t_text, a_text) in enumerate(
            plan, 1
        ):
            started = time.monotonic()
            with _arm(arm, render_counts):
                with using_model(di_container, gen_model):
                    cell = await _generate(label, ordering, rep, t_text, a_text,
                                           class_cache)
            if cell is not None:
                cells.append((arm, stratum, cell))
            # flush=True is load-bearing: pytest buffers redirected stdout, and a
            # killed run would otherwise produce zero recoverable output.
            print(f"  [{index}/{len(plan)}] {arm:8s} {stratum[:4]} {label}/"
                  f"{ordering}/rep{rep} {time.monotonic() - started:.1f}s"
                  f"{'' if cell is not None else '  FAILED'}", flush=True)

    # --- the manipulation check, on the run that actually happened ------------
    n_baseline = sum(1 for a, _s, _c in cells if a == BASELINE)
    n_fixed = sum(1 for a, _s, _c in cells if a == FIXED)
    print("\n=== manipulation check (how many renders were actually patched) ===",
          flush=True)
    print(f"  baseline cells {n_baseline}, renders downgraded "
          f"{render_counts['baseline_downgraded']}", flush=True)
    print(f"  fixed cells    {n_fixed}, renders verified "
          f"{render_counts['fixed_verified']}", flush=True)
    assert render_counts["baseline_downgraded"] >= n_baseline, (
        "fewer downgrades than baseline cells — some baseline cell ran the fixed "
        "prompt and the comparison is contaminated"
    )
    assert render_counts["fixed_verified"] >= n_fixed

    # --- what the classifier did this run ------------------------------------
    #
    # ADDED AFTER the 2026-08-20 run, so it is empty for that result. Its absence
    # is why that run cannot tell classifier drift apart from sampling variance
    # after its minus base rate came in 3x the archive's (p=0.0406) on a prompt
    # verified byte-identical to the pre-fix commit. The branch selects the apex
    # row interpolated into the tetrad prompt, so a pole classifying differently
    # is a DIFFERENT PROMPT, not noise — and both arms share these meanings within
    # a run, so this readout is about run-to-run comparability, not about the A/B.
    print("\n=== how each pole classified (branch selects the apex in the prompt) "
          "===", flush=True)
    for text, classification in sorted(class_cache.items()):
        print(f"  {_branch_of(classification):12s} {text}", flush=True)

    # --- audit ---------------------------------------------------------------
    judge_model = config.judge_model
    print(f"\n=== auditor model: {judge_model} ===", flush=True)

    units: list[tuple[str, str, _Cell, str, str, str, str]] = []
    for arm, stratum, cell in cells:
        units.append((arm, stratum, cell, "T+", cell.t_plus, cell.t_text, cell.a_text))
        units.append((arm, stratum, cell, "A+", cell.a_plus, cell.a_text, cell.t_text))
        units.append((arm, stratum, cell, "T-", cell.t_minus, cell.t_text, cell.a_text))
        units.append((arm, stratum, cell, "A-", cell.a_minus, cell.a_text, cell.t_text))

    import asyncio  # local: the module is import-light for the free lane

    sem = asyncio.Semaphore(6)

    async def audit(unit):
        arm, _stratum, cell, position, aspect, own, other = unit
        if not aspect.strip():
            return unit, None
        async with sem:
            try:
                conversation = ConversationFacilitator()
                conversation.set_system_prompt(
                    _audit_prompt(own, other, position, aspect)
                )
                with using_model(di_container, judge_model):
                    verdict = await conversation.submit(
                        _PoleVerdict,
                        "Audit the aspect against the structural rule.",
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"  !! audit {arm}/{cell.tension}/{position}: "
                      f"{type(exc).__name__}: {exc}", flush=True)
                return unit, None
        return unit, verdict

    results = await asyncio.gather(*(audit(u) for u in units))

    tally: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    per_tension: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    findings: list[tuple[str, _Cell, str, str, _PoleVerdict]] = []
    errors = 0
    for (arm, _stratum, cell, position, aspect, _own, _other), verdict in results:
        if verdict is None:
            errors += 1
            continue
        tally[(arm, position)][verdict.parent] += 1
        tally[(arm, position)]["scored"] += 1
        if not verdict.valence_matches_claim:
            tally[(arm, position)]["valence_wrong"] += 1
        if position in ("T+", "A+"):
            per_tension[(arm, cell.tension)]["plus_scored"] += 1
            if not verdict.valence_matches_claim:
                per_tension[(arm, cell.tension)]["plus_valence_wrong"] += 1
        if verdict.parent != "own_pole" or not verdict.valence_matches_claim:
            findings.append((arm, cell, position, aspect, verdict))

    if errors:
        print(f"\n!! {errors} audit(s) failed and are excluded from every "
              f"denominator below.", flush=True)

    plus = ("T+", "A+")
    minus = ("T-", "A-")

    def total(arm: str, positions: tuple[str, ...], key: str) -> int:
        return sum(tally[(arm, p)][key] for p in positions)

    def misparented(arm: str, positions: tuple[str, ...]) -> int:
        return sum(
            tally[(arm, p)][k] for p in positions for k in ("other_pole", "neither")
        )

    # --- the registered primary ----------------------------------------------
    n_b = total(BASELINE, plus, "scored")
    k_b = total(BASELINE, plus, "valence_wrong")
    n_f = total(FIXED, plus, "scored")
    k_f = total(FIXED, plus, "valence_wrong")
    rate_b = k_b / n_b if n_b else 0.0
    rate_f = k_f / n_f if n_f else 0.0
    p_primary = fisher_exact_two_sided(k_b, n_b - k_b, k_f, n_f - k_f)

    print("\n=== PRIMARY: plus valence failure, baseline vs fixed ===", flush=True)
    for arm, n, k in ((BASELINE, n_b, k_b), (FIXED, n_f, k_f)):
        lo, hi = _wilson(k, n)
        print(f"  {arm:8s} {k:3d}/{n:3d} = {(k / n if n else 0):5.1%} "
              f"[95% {lo:.1%}-{hi:.1%}]", flush=True)
    print(f"  Fisher two-sided p = {p_primary:.4f}", flush=True)
    print(f"  registered: CONFIRMED iff fixed <= {_PREREG_FIXED_CEILING:.1%} and "
          f"p < {_PREREG_ALPHA}; NOT CONFIRMED iff fixed >= "
          f"{_PREREG_NULL_FLOOR:.1%}", flush=True)

    if rate_f <= _PREREG_FIXED_CEILING and p_primary < _PREREG_ALPHA:
        print("  -> CONFIRMED. The check reduces plus-restatement on the weak "
              "tier. Note what this does NOT show: the mechanism (verification "
              "step vs. worked example) is not separated — both landed together.",
              flush=True)
    elif rate_f >= _PREREG_NULL_FLOOR:
        print("  -> NOT CONFIRMED, as a BOUND not a refutation: this design has "
              f"{_PREREG_POWER_HALVING:.2f} power for a halving, so a real but "
              "moderate improvement would be missed about half the time. What is "
              "ruled out is a two-thirds cut.", flush=True)
    else:
        print(f"  -> INDETERMINATE (fixed {rate_f:.1%} sits between the bands). "
              f"Registered consequence: say so. Settling it needs a larger "
              f"population, not a re-reading of this one.", flush=True)

    # --- the registered WEAK guard -------------------------------------------
    gn_b = total(BASELINE, minus, "scored")
    gk_b = misparented(BASELINE, minus)
    gn_f = total(FIXED, minus, "scored")
    gk_f = misparented(FIXED, minus)
    p_guard = fisher_exact_two_sided(gk_b, gn_b - gk_b, gk_f, gn_f - gk_f)

    print("\n=== GUARD (registered WEAK): minus misparentage must not worsen ===",
          flush=True)
    for arm, n, k in ((BASELINE, gn_b, gk_b), (FIXED, gn_f, gk_f)):
        lo, hi = _wilson(k, n)
        print(f"  {arm:8s} {k:3d}/{n:3d} = {(k / n if n else 0):5.1%} "
              f"[95% {lo:.1%}-{hi:.1%}]", flush=True)
    print(f"  Fisher two-sided p = {p_guard:.4f}", flush=True)
    print(f"  POWER {_PREREG_POWER_GUARD_DOUBLING:.2f} for a DOUBLING. A clean "
          f"guard here rules out a tripling (0.66) and nothing smaller — it is "
          f"NOT 'the fix did no harm'.", flush=True)

    # --- registered secondaries ----------------------------------------------
    print("\n=== SECONDARY: T+ vs A+ split of the plus defect ===", flush=True)
    for arm in (BASELINE, FIXED):
        for position in plus:
            c = tally[(arm, position)]
            print(f"  {arm:8s} {position} valence_wrong "
                  f"{c['valence_wrong']}/{c['scored']}", flush=True)

    print("\n=== SECONDARY: shape of the plus defect (restatement vs drift) ===",
          flush=True)
    for arm in (BASELINE, FIXED):
        drifted = misparented(arm, plus)
        print(f"  {arm:8s} own_pole={total(arm, plus, 'own_pole')} "
              f"other_pole={total(arm, plus, 'other_pole')} "
              f"neither={total(arm, plus, 'neither')}   (drifted={drifted} — the "
              f"over-correction the worked example warns about)", flush=True)

    print("\n=== SECONDARY: per-tension plus defects (is an arm riding on 1-2?) ===",
          flush=True)
    for _stratum, label, _x, _y in _TENSIONS:
        cb = per_tension[(BASELINE, label)]
        cf = per_tension[(FIXED, label)]
        print(f"  {label:24s} baseline {cb['plus_valence_wrong']}/"
              f"{cb['plus_scored']}   fixed {cf['plus_valence_wrong']}/"
              f"{cf['plus_scored']}", flush=True)

    if findings:
        print(f"\n=== every flagged aspect ({len(findings)}) ===", flush=True)
        for arm, cell, position, aspect, verdict in findings:
            flags = []
            if verdict.parent != "own_pole":
                flags.append(f"parent={verdict.parent}")
            if not verdict.valence_matches_claim:
                flags.append("valence")
            print(f"  [{arm}] {cell.tension}/{cell.ordering}/rep{cell.replicate} "
                  f"{position}: {aspect!r}", flush=True)
            print(f"       {' '.join(flags)} belongs_to="
                  f"{verdict.pole_it_belongs_to!r}", flush=True)
            print(f"       why: {verdict.why}", flush=True)

    # The probe reports; it does not gate CI on a finding. A pre-registered
    # endpoint that also fails the build pressures the bands.
    assert cells, "no tetrads generated — nothing was measured"
