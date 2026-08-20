"""Does the minus-parentage defect concentrate in option-pairs rather than oppositions?

WHY THIS EXISTS
===============
`probe_tetrad_pole.py` chased a parentage defect across three runs and ended
UNPROVEN — and `power.py` later showed why it could not have ended otherwise: at
n=72 minus-slots per arm for an 18% -> 9% effect, that design had **power 0.28**.
The repair is not a bigger version of the same run. Power responds to the base rate
faster than to n (0.80 needs n=252/arm at 18%->9%, but n=96/arm at 40%->20%), so
the question worth asking next is where the defect is DENSE.

The archive points at one place. Its residual minus defects concentrated in the two
`cofounder_*` tensions — `cofounder_retention` was untouched by the parentage fix,
3 forward + 3 swapped in the baseline and 3 + 3 again in the replication — and 4 of
the 8 residual PLUS defects sat on `cofounder_sequencing`. Both are option-pairs:
two named, mutually exclusive courses of action rather than two opposed directions.

And there is a reason in the framework itself, which is what licenses this rather
than the counts. CLAUDE.md: "Named options / courses of action classify COMPLEX
... For option-pairs, Mode ... is the 'differ rather than oppose' tell, not HS:
mutually exclusive options sit in each other's negation space, so HS scores
moderate; Mode ~0.0-0.1 (distancing/privation) flags a fork that isn't the
tension." If the two poles are alternatives rather than ends of one dimension, then
"T+ develops T so it also takes up what A offers" has no clean referent — what A
offers is a different PLAN, so a plus drifts into the other plan and a minus has no
axis to overdevelop along. That predicts defects at every position, concentrated
here, for a structural reason that has nothing to do with the missing derivation
step the parentage fix addressed.

Honest provenance, because it matters for how much this run can claim: my attention
came from the archive's counts, which are outcome-selected. What licenses the test
is the structural claim above, which was in CLAUDE.md before any of these runs. The
population below is therefore ENTIRELY NEW text — no `cofounder_*`, nothing from
`probe_tetrad_pole._TENSIONS` (asserted in the free test). Selecting the enriched
population by which cells failed would bake the selection into the result; selecting
it by a property stated in advance does not.

THE OPERATIONAL DEFINITION (fixed before any text was written)
==============================================================
  OPTION_PAIR  Both poles name a specific course of action, and adopting one
               precludes adopting the other. They differ on SEVERAL dimensions at
               once, so no single axis runs between them.
               "Raise a priced round at the current valuation" /
               "Bootstrap to profitability on existing revenue"
  OPPOSITION   Both poles name opposite ends of ONE dimension. A single axis runs
               between them and either end is a direction, not a plan.
               "Standardise the deployment toolchain across every team" /
               "Let each team choose its own deployment toolchain"

The distinction is NOT abstract-vs-concrete and NOT short-vs-long. Both strata are
concrete, both are 6-8 words per pole, and the free test asserts their mean word
counts differ by less than 2 — because `probe_classifier_stability.py` has already
shown me how easily a form difference gets mistaken for a structural one. Form is
matched by construction so that a difference here cannot be read as a form effect.

PRE-REGISTRATION (written before any tetrad was generated, 2026-08-20)
=====================================================================
Population: 16 tensions (8 per stratum) x 2 orderings (T/A swapped) x 2 replicates
= 64 tetrads, on the WEAK tier — the tier every archive defect was produced on.
Each tetrad yields 2 minus slots and 2 plus slots, so 64 minus slots per stratum.

SINGLE ARM. The current (post-parentage-fix) prompt only. This run says NOTHING
about whether that fix works; it asks where the residual defect lives. Mixing both
questions into one run is what made the last one unreadable.

PRIMARY — minus-aspect misparentage (auditor `parent != own_pole`, i.e.
`other_pole` + `neither`, the same endpoint definition `probe_tetrad_pole` used, so
the rates are comparable), OPTION_PAIR stratum vs OPPOSITION stratum, 64 slots each:
  * CONCENTRATION REAL   rate(OPTION_PAIR) - rate(OPPOSITION) >= 0.15
                         AND Fisher two-sided p < 0.05.
  * NO CONCENTRATION     gap <= 0.05. The residual defect is not about option-pairs
                         and the archive's cofounder clustering was small-n noise.
  * INDETERMINATE        gap in 0.06..0.14.

POWER, computed with `power.py` BEFORE registering the bar rather than after:
  40% vs 15%  ->  0.86      (the effect the archive's clustering suggests)
  40% vs 20%  ->  0.63
  35% vs 15%  ->  0.69
  30% vs 15%  ->  0.45
So this run is well powered for a large concentration and UNDERPOWERED for a
moderate one. Registered consequence: a NULL result here bounds the effect, it does
not retire the hypothesis, and the write-up must say which of those it is. Reaching
0.80 for the 30%-vs-15% case would need n=132/stratum — roughly double — and that
is the number to spend if this run lands INDETERMINATE.

SECONDARY, pre-registered because each is a distinct predicted mechanism:
  * PLUS-aspect misparentage per stratum. The prediction is directional and
    specific: a plus on an option-pair drifts into the OTHER PLAN, so `other_pole`
    (not `neither`) should dominate at T+/A+ in the OPTION_PAIR stratum. Reported
    with the `other_pole`/`neither` split visible, not just the total.
  * Valence failures per stratum (`valence_matches_claim` false) — the "no axis to
    overdevelop along" prediction: a minus with no axis tends to name a neutral
    circumstance rather than a one-sided push.
  * ABSOLUTE rate per stratum with an interval. This is the number a future
    parentage A/B needs in order to size itself, and it is the main deliverable
    even if the primary lands INDETERMINATE.

MANIPULATION CHECK, and it can invalidate the primary. `AntithesisClassification`
returns `mode_value`; CLAUDE.md says a fork that is not the tension reads ~0.0-0.1
while a real opposition reads higher. Registered: mean mode_value(OPTION_PAIR) <
mean mode_value(OPPOSITION). If that fails, my two strata do not differ on the
property I claim to have manipulated, and the primary — whatever it says — is about
my labelling rather than about option-pairs. Reported before the primary, in the
`read_prereg` spirit of putting invalidating gates ahead of the endpoint.

Also recorded per pole, per the lesson from `probe_classifier_stability.py`: the
taxonomy branch AND domain each pole classified into. Only 38% of texts there were
stable on (family, domain, branch) over 6 readings, and the branch selects the apex
row interpolated into the generation prompt. It is part of the condition, not
fixture detail. One classification per distinct text, cached and reused across both
orderings and both replicates, so within this run the apex is pinned by
construction.

Pre-declared confounds:
  * Form is matched on word count and concreteness, not on specificity — an
    option-pair may still be more specific than a dimensional opposition. A
    positive result is about the option-pair PROPERTY as operationalised above, and
    the write-up must not upgrade that to a claim about any one ingredient.
  * The auditor is the archive's, verbatim and unchanged. That makes rates
    comparable and also inherits its limits.
  * Single tier (weak). A clean result on a stronger model would not retire this
    and is not measured.
  * 16 tensions is a small sample of the space of oppositions; a stratum effect
    could ride on 1-2 unusual tensions. Per-tension counts are printed so that is
    visible rather than absorbed into the stratum mean.

Run:
  poetry run pytest tests/e2e/probe_option_pair_tetrads.py -s --real-llm
  poetry run pytest tests/e2e/probe_option_pair_tetrads.py -s   (free: population,
      strata balance, form matching, archive-overlap check; no provider calls)
"""

from __future__ import annotations

import asyncio
import collections
import os
import statistics
import time

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.statement_classification import (
    ClassificationResult, parse_meaning_uri)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.power import fisher_exact_two_sided, fisher_power
# The instrument is imported, never re-typed: same auditor prompt, same verdict
# model, same generation path, so this run's rates are directly comparable to the
# archive's. A second copy would drift and quietly stop being comparable.
from e2e.probe_tetrad_pole import (_Cell, _PoleVerdict, _audit_prompt,  # noqa
                                   _branch_of, _generate)

pytestmark = [pytest.mark.llm]


OPTION_PAIR = "OPTION_PAIR"
OPPOSITION = "OPPOSITION"

#: (stratum, label, side_x, side_y). Every tension runs BOTH ways.
_TENSIONS: list[tuple[str, str, str, str]] = [
    # --- OPTION_PAIR: two mutually exclusive plans, no single axis between them --
    (OPTION_PAIR, "hiring_route",
     "Hire a senior engineer now at market rate",
     "Wait two quarters and train a junior internally"),
    (OPTION_PAIR, "platform_bet",
     "Rebuild the platform on the new framework",
     "Keep extending the platform that already ships"),
    (OPTION_PAIR, "funding_route",
     "Raise a priced round at the current valuation",
     "Bootstrap to profitability on existing revenue"),
    (OPTION_PAIR, "market_entry",
     "Launch in one country and go deep there",
     "Launch in five countries at the same time"),
    (OPTION_PAIR, "pricing_migration",
     "Move every customer onto the new pricing tier",
     "Grandfather existing customers on their current prices"),
    (OPTION_PAIR, "office_shape",
     "Consolidate the whole company into one office",
     "Close the office and commit to fully remote"),
    (OPTION_PAIR, "reserve_use",
     "Pay down the loan early from the reserve",
     "Keep the reserve and service the loan monthly"),
    (OPTION_PAIR, "acquisition_call",
     "Accept the acquisition offer on the table",
     "Stay independent and execute the current plan"),
    # --- OPPOSITION: opposite ends of ONE dimension, form-matched to the above ---
    (OPPOSITION, "tooling_control",
     "Standardise the deployment toolchain across every team",
     "Let each team choose its own deployment toolchain"),
    (OPPOSITION, "decision_formality",
     "Record every architectural decision in a written review",
     "Let engineers change architecture without written review"),
    (OPPOSITION, "roadmap_disclosure",
     "Publish detailed roadmap commitments to customers",
     "Keep roadmap plans internal until they ship"),
    (OPPOSITION, "budget_discretion",
     "Give managers full discretion over their team budgets",
     "Route every budget decision through central finance"),
    (OPPOSITION, "roadmap_weighting",
     "Weight the roadmap toward the largest existing accounts",
     "Weight the roadmap toward first-time users"),
    (OPPOSITION, "coverage_enforcement",
     "Enforce a coverage threshold on every merge",
     "Let developers judge when coverage is sufficient"),
    (OPPOSITION, "escalation_depth",
     "Escalate customer complaints to the founders immediately",
     "Resolve customer complaints entirely inside the support team"),
    (OPPOSITION, "process_density",
     "Document every internal process in careful detail",
     "Keep processes minimal and rely on judgement"),
]

_REPLICATES = 2

#: Registered bands. Named so the readout cannot quietly use a different number
#: from the docstring.
_PREREG_CONCENTRATION_GAP = 0.15
_PREREG_NULL_GAP = 0.05
_PREREG_ALPHA = 0.05
#: Form matching is a design claim, so it is enforced rather than asserted in prose.
_PREREG_MAX_WORD_COUNT_GAP = 2.0


def _words(text: str) -> int:
    return len(text.split())


def _plan() -> list[tuple[str, str, str, int, str, str]]:
    """(stratum, label, ordering, replicate, t_text, a_text) for every cell.

    Strata are INTERLEAVED rather than run in blocks: a provider that drifts over
    the run would otherwise load that drift onto whichever stratum ran second,
    which is precisely the confound that made two `probe_tetrad_pole` runs
    incomparable.
    """
    plan: list[tuple[str, str, str, int, str, str]] = []
    for rep in range(1, _REPLICATES + 1):
        for ordering in ("forward", "swapped"):
            for stratum, label, side_x, side_y in _TENSIONS:
                if ordering == "forward":
                    plan.append((stratum, label, ordering, rep, side_x, side_y))
                else:
                    plan.append((stratum, label, ordering, rep, side_y, side_x))
    return plan


def _domain_of(classification: ClassificationResult) -> str:
    """The taxonomy DOMAIN (General / Engineering / Institutions / ...).

    `parse_meaning_uri` returns (domain, category, branch, leaf) — index 1 is
    `category`, which is always "Viability" and therefore looks stable no matter how
    much the classifier drifts. Reading the wrong slot here would have manufactured
    exactly the reassurance `probe_classifier_stability.py` says not to trust.
    """
    if classification.is_simple:
        return "SIMPLE"
    domain, _, _, _ = parse_meaning_uri(classification.meaning)
    return domain or "?"


def _wilson(k: int, n: int) -> tuple[float, float]:
    """95% Wilson interval. Reported because a bare rate out of 64 invites being
    compared against another run's bare rate as though both were exact."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# --- free checks --------------------------------------------------------------


class TestThePopulationIsWhatTheDocstringClaims:
    """Runs without a provider AND without Memgraph. Every claim the
    pre-registration makes about the population is checked here, so a drifted
    population fails loudly instead of producing a number under a description that
    no longer fits it."""

    # Name-shadow conftest's autouse graph fixtures for this class only — the free
    # checks touch no graph, and the real run below still needs them.
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def test_strata_are_balanced(self):
        counts = collections.Counter(s for s, _l, _x, _y in _TENSIONS)
        assert counts[OPTION_PAIR] == counts[OPPOSITION] == 8, counts

    def test_labels_are_unique(self):
        labels = [l for _s, l, _x, _y in _TENSIONS]
        assert len(labels) == len(set(labels))

    def test_cell_count_matches_the_registration(self):
        plan = _plan()
        assert len(plan) == len(_TENSIONS) * 2 * _REPLICATES == 64
        per_stratum = collections.Counter(s for s, *_ in plan)
        assert per_stratum[OPTION_PAIR] == per_stratum[OPPOSITION] == 32
        # 2 minus slots per tetrad -> the 64/stratum the power calc was run on.
        assert per_stratum[OPTION_PAIR] * 2 == 64

    def test_form_is_matched_across_strata(self):
        """The design control. `probe_classifier_stability.py` killed a hypothesis
        that turned out to be about form, so form cannot be left to good intentions
        here: if the strata drift apart on length this fails."""
        by_stratum: dict[str, list[int]] = collections.defaultdict(list)
        for stratum, _label, side_x, side_y in _TENSIONS:
            by_stratum[stratum].extend((_words(side_x), _words(side_y)))
        mean_op = statistics.mean(by_stratum[OPTION_PAIR])
        mean_opp = statistics.mean(by_stratum[OPPOSITION])
        assert abs(mean_op - mean_opp) < _PREREG_MAX_WORD_COUNT_GAP, (
            f"strata differ on word count: OPTION_PAIR {mean_op:.1f} vs "
            f"OPPOSITION {mean_opp:.1f} — a result could be a form effect"
        )
        for stratum, counts in by_stratum.items():
            assert min(counts) >= 5, f"{stratum} has a pole under 5 words"
            assert max(counts) <= 14, f"{stratum} has a pole over 14 words"

    def test_no_pole_is_a_bare_abstract_noun(self):
        """Both strata must be concrete. A single-word pole would reintroduce the
        abstract/concrete axis this design is trying to hold constant."""
        for _stratum, label, side_x, side_y in _TENSIONS:
            for pole in (side_x, side_y):
                assert _words(pole) > 1, f"{label}: bare noun pole {pole!r}"

    def test_population_does_not_reuse_the_archive(self):
        """Enrichment must not select on the cells being compared against."""
        from e2e.probe_tetrad_pole import _TENSIONS as archive  # noqa: PLC0415

        archive_texts = {t.lower() for _l, x, y in archive for t in (x, y)}
        for _stratum, label, side_x, side_y in _TENSIONS:
            for pole in (side_x, side_y):
                assert pole.lower() not in archive_texts, (
                    f"{label} reuses archive text {pole!r} — the population must "
                    f"be new, or the enrichment is outcome-selected"
                )
        assert not any(
            "cofounder" in f"{x} {y}".lower() for _s, _l, x, y in _TENSIONS
        ), "the cofounder tensions are the outcome-selected ones; keep them out"

    def test_registered_bands_are_ordered(self):
        assert _PREREG_NULL_GAP < _PREREG_CONCENTRATION_GAP

    def test_the_power_claim_in_the_docstring_is_the_real_number(self):
        """The docstring's power table is load-bearing — it is what licenses calling
        a null 'a bound' rather than 'a refutation'. Pinned so an edit to the
        population size cannot silently invalidate it."""
        assert fisher_power(64, 0.40, 0.15) == pytest.approx(0.86, abs=0.03)
        assert fisher_power(64, 0.40, 0.20) == pytest.approx(0.63, abs=0.03)
        assert fisher_power(64, 0.30, 0.15) == pytest.approx(0.45, abs=0.03)


# --- the run ------------------------------------------------------------------


@pytest.mark.real_llm
@pytest.mark.asyncio
# NOT @traced — conftest's `traced` serialises the test's arguments as span input
# and `di_container` is cyclic; it hangs the process with no output. See the same
# comment in `probe_tetrad_pole.py`, which lost two full runs to it.
async def test_minus_parentage_concentrates_in_option_pairs(di_container) -> None:
    plan = _plan()
    limit = int(os.environ.get("PROBE_OPTION_PAIR_LIMIT", "0") or 0)
    if limit:
        # No silent caps: a truncated run must never read as full coverage.
        print(f"\n!! PROBE_OPTION_PAIR_LIMIT={limit} active — {limit} of "
              f"{len(plan)} pre-registered tetrads. PARTIAL RUN, and the "
              f"registered bands assume the full population.", flush=True)
        plan = plan[:limit]

    case_node = Case()
    case_node.commit()

    config = E2EConfig.from_env()
    gen_model = config.tiers["weak"]

    with scope(case_node.sid):
        print(f"\n=== generating {len(plan)} tetrads on the WEAK tier: "
              f"{gen_model} ===", flush=True)
        cells: list[tuple[str, _Cell]] = []
        class_cache: dict[str, ClassificationResult] = {}
        # Sequential: GQLAlchemy graph writes are not concurrency-safe and every
        # cell writes Perspective/Polarity/Statement before its LLM call.
        for index, (stratum, label, ordering, rep, t_text, a_text) in enumerate(
            plan, 1
        ):
            started = time.monotonic()
            with using_model(di_container, gen_model):
                cell = await _generate(label, ordering, rep, t_text, a_text,
                                       class_cache)
            if cell is not None:
                cells.append((stratum, cell))
            # flush=True is load-bearing: pytest buffers redirected stdout, and a
            # killed run would otherwise produce zero recoverable output.
            print(f"  [{index}/{len(plan)}] {stratum[:4]} {label}/{ordering}/"
                  f"rep{rep} {time.monotonic() - started:.1f}s"
                  f"{'' if cell is not None else '  FAILED'}", flush=True)

        print(f"generated {len(cells)} of {len(plan)}", flush=True)

        # --- manipulation check, BEFORE the endpoint ---------------------------
        # Registered as able to invalidate the primary, so it is computed and
        # printed first rather than appended as a footnote.
        print("\n=== MANIPULATION CHECK: Mode per stratum ===", flush=True)
        print("CLAUDE.md: a fork that is not the tension reads Mode ~0.0-0.1; a "
              "real opposition reads higher.", flush=True)
        modes: dict[str, list[float]] = collections.defaultdict(list)
        for stratum, label, side_x, side_y in _TENSIONS:
            t_class = class_cache.get(side_x)
            if t_class is None:
                continue
            try:
                thesis = Statement(text=side_x, meaning=t_class.meaning)
                with using_model(di_container, gen_model):
                    verdict = await AntithesisClassification().resolve(
                        thesis=thesis, antithesis_statement=side_y
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"  !! mode check failed {label}: "
                      f"{type(exc).__name__}: {exc}", flush=True)
                continue
            modes[stratum].append(verdict.mode_value)
            print(f"  {stratum[:4]} {label:24s} mode={verdict.mode_value:.2f} "
                  f"({verdict.mode_label})", flush=True)

    mode_op = statistics.mean(modes[OPTION_PAIR]) if modes[OPTION_PAIR] else None
    mode_opp = statistics.mean(modes[OPPOSITION]) if modes[OPPOSITION] else None
    if mode_op is not None and mode_opp is not None:
        print(f"\n  mean Mode  OPTION_PAIR {mode_op:.3f}  "
              f"OPPOSITION {mode_opp:.3f}", flush=True)
        if mode_op < mode_opp:
            print("  -> MANIPULATION HELD: the strata differ on the property "
                  "claimed. The primary below is about option-pairs.", flush=True)
        else:
            print("  -> !! MANIPULATION FAILED: option-pairs do NOT read lower on "
                  "Mode. Whatever the primary says, it is about my labelling of "
                  "these 16 tensions, not about the option-pair property. Report "
                  "it as such and do not size a future run on it.", flush=True)
    else:
        print("  -> !! Mode not measurable this run; manipulation UNCHECKED.",
              flush=True)

    # --- classification actually used ----------------------------------------
    print("\n=== how each pole classified (branch selects the apex in the prompt) "
          "===", flush=True)
    stratum_of: dict[str, str] = {}
    for stratum, _label, side_x, side_y in _TENSIONS:
        stratum_of[side_x] = stratum
        stratum_of[side_y] = stratum
    seen: dict[str, tuple[str, str]] = {}
    for text, classification in class_cache.items():
        seen[text] = (_branch_of(classification), _domain_of(classification))
    for text, (branch, domain) in sorted(seen.items()):
        print(f"  {stratum_of.get(text, '?')[:4]} {branch:12s} {domain:14s} {text}",
              flush=True)
    # Domain spread per stratum: if the two strata systematically classify into
    # different domains, that is a second difference riding alongside the one under
    # test, and the primary has to be read with it in view.
    for stratum in (OPTION_PAIR, OPPOSITION):
        domains = collections.Counter(
            d for t, (_b, d) in seen.items() if stratum_of.get(t) == stratum
        )
        print(f"  {stratum:12s} domains: {dict(domains)}", flush=True)
    simple = sorted(t for t, (b, _d) in seen.items() if b == "SIMPLE")
    if simple:
        print(f"  !! {len(simple)} pole(s) classified SIMPLE — those take the "
              f"'Simple' apex, not a taxonomy branch, and are NOT comparable to "
              f"the archive's COMPLEX tetrads:", flush=True)
        for text in simple:
            print(f"       {text}", flush=True)

    # --- audit ----------------------------------------------------------------
    judge_model = config.judge_model
    print(f"\n=== auditor model: {judge_model} ===", flush=True)

    units: list[tuple[str, _Cell, str, str, str, str]] = []
    for stratum, cell in cells:
        units.append((stratum, cell, "T-", cell.t_minus, cell.t_text, cell.a_text))
        units.append((stratum, cell, "A-", cell.a_minus, cell.a_text, cell.t_text))
        units.append((stratum, cell, "T+", cell.t_plus, cell.t_text, cell.a_text))
        units.append((stratum, cell, "A+", cell.a_plus, cell.a_text, cell.t_text))

    sem = asyncio.Semaphore(6)

    async def audit(unit):
        stratum, cell, position, aspect, own, other = unit
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
                print(f"  !! audit {cell.tension}/{position}: "
                      f"{type(exc).__name__}: {exc}", flush=True)
                return unit, None
        return unit, verdict

    results = await asyncio.gather(*(audit(u) for u in units))

    # (stratum, position) -> Counter of parent verdicts (+ valence_wrong)
    tally: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    per_tension: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    errors = 0
    findings: list[tuple[str, _Cell, str, str, _PoleVerdict]] = []
    for (stratum, cell, position, aspect, _own, _other), verdict in results:
        if verdict is None:
            errors += 1
            continue
        tally[(stratum, position)][verdict.parent] += 1
        if not verdict.valence_matches_claim:
            tally[(stratum, position)]["valence_wrong"] += 1
        if position in ("T-", "A-"):
            per_tension[cell.tension]["minus_scored"] += 1
            if verdict.parent != "own_pole":
                per_tension[cell.tension]["minus_misparented"] += 1
        if verdict.parent != "own_pole" or not verdict.valence_matches_claim:
            findings.append((stratum, cell, position, aspect, verdict))

    _PARENTS = ("own_pole", "other_pole", "neither", "unreadable")

    def scored(stratum: str, positions: tuple[str, ...]) -> int:
        return sum(tally[(stratum, p)][k] for p in positions for k in _PARENTS)

    def misparented(stratum: str, positions: tuple[str, ...]) -> int:
        """Registered endpoint definition, identical to `probe_tetrad_pole`."""
        return sum(
            tally[(stratum, p)][k] for p in positions for k in ("other_pole", "neither")
        )

    def valence_wrong(stratum: str, positions: tuple[str, ...]) -> int:
        return sum(tally[(stratum, p)]["valence_wrong"] for p in positions)

    if errors:
        print(f"\n!! {errors} audit(s) failed and are excluded from every "
              f"denominator below.", flush=True)

    minus = ("T-", "A-")
    plus = ("T+", "A+")

    print("\n=== per-stratum rates (denominators are audited slots) ===",
          flush=True)
    for label, positions in (("MINUS (primary)", minus), ("PLUS (secondary)", plus)):
        print(f"  {label}", flush=True)
        for stratum in (OPTION_PAIR, OPPOSITION):
            n = scored(stratum, positions)
            k = misparented(stratum, positions)
            vw = valence_wrong(stratum, positions)
            lo, hi = _wilson(k, n)
            other = sum(tally[(stratum, p)]["other_pole"] for p in positions)
            neither = sum(tally[(stratum, p)]["neither"] for p in positions)
            rate = k / n if n else 0.0
            print(f"    {stratum:12s} misparented {k:3d}/{n:3d} = {rate:5.1%} "
                  f"[95% {lo:.1%}-{hi:.1%}]   other_pole={other} neither={neither}"
                  f"   valence_wrong={vw}", flush=True)

    # --- the registered primary ----------------------------------------------
    n_op = scored(OPTION_PAIR, minus)
    k_op = misparented(OPTION_PAIR, minus)
    n_opp = scored(OPPOSITION, minus)
    k_opp = misparented(OPPOSITION, minus)
    rate_op = k_op / n_op if n_op else 0.0
    rate_opp = k_opp / n_opp if n_opp else 0.0
    gap = rate_op - rate_opp
    p_primary = fisher_exact_two_sided(k_op, n_op - k_op, k_opp, n_opp - k_opp)

    print("\n=== PRIMARY: minus misparentage, OPTION_PAIR vs OPPOSITION ===",
          flush=True)
    print(f"  OPTION_PAIR {k_op}/{n_op} = {rate_op:.1%}", flush=True)
    print(f"  OPPOSITION  {k_opp}/{n_opp} = {rate_opp:.1%}", flush=True)
    print(f"  gap = {gap:+.1%}   (registered: >= "
          f"{_PREREG_CONCENTRATION_GAP:.0%} concentrates, "
          f"<= {_PREREG_NULL_GAP:.0%} null)", flush=True)
    print(f"  Fisher two-sided p = {p_primary:.4f}", flush=True)

    if gap >= _PREREG_CONCENTRATION_GAP and p_primary < _PREREG_ALPHA:
        print("  -> CONCENTRATION REAL. The residual parentage defect is dense in "
              "option-pairs. A future parentage A/B should run on this stratum, "
              "where it is affordable.", flush=True)
    elif gap <= _PREREG_NULL_GAP:
        print("  -> NO CONCENTRATION at this power. NOTE THE BOUND, not a "
              "refutation: this design has 0.45 power for a 30%-vs-15% effect, so "
              "a moderate concentration would likely be missed. Settling it needs "
              "n=132/stratum.", flush=True)
    else:
        print(f"  -> INDETERMINATE (gap {gap:+.1%} sits between the bands). "
              f"Registered consequence: double the population "
              f"(n=132/stratum) rather than re-reading this one.", flush=True)

    # --- what a future parentage A/B should be sized on ----------------------
    print("\n=== sizing input for a future parentage A/B ===", flush=True)
    for stratum, n, k in ((OPTION_PAIR, n_op, k_op), (OPPOSITION, n_opp, k_opp)):
        if not n:
            continue
        base = k / n
        halved = base / 2
        if 0.02 < halved < base < 0.95:
            pw = fisher_power(64, base, halved)
            print(f"  {stratum:12s} base {base:.1%} -> halved {halved:.1%}: "
                  f"power at n=64/arm = {pw:.2f}", flush=True)

    print("\n=== per-tension minus misparentage (is a stratum riding on 1-2?) ===",
          flush=True)
    for stratum, label, _x, _y in _TENSIONS:
        c = per_tension[label]
        n = c["minus_scored"]
        k = c["minus_misparented"]
        if n:
            print(f"  {stratum[:4]} {label:24s} {k}/{n}", flush=True)

    if findings:
        print(f"\n=== every flagged aspect ({len(findings)}) ===", flush=True)
        for stratum, cell, position, aspect, verdict in findings:
            flags = []
            if verdict.parent != "own_pole":
                flags.append(f"parent={verdict.parent}")
            if not verdict.valence_matches_claim:
                flags.append("valence")
            print(f"  [{stratum[:4]}] {cell.tension}/{cell.ordering}/"
                  f"rep{cell.replicate} {position}: {aspect!r}", flush=True)
            print(f"       {' '.join(flags)} belongs_to="
                  f"{verdict.pole_it_belongs_to!r}", flush=True)
            print(f"       why: {verdict.why}", flush=True)

    # The probe reports; it does not fail on a finding. A pre-registered endpoint
    # that also gates CI would pressure the bands.
    assert cells, "no tetrads generated — nothing was measured"
