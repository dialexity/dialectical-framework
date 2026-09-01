"""Does a generated minus overdevelop its OWN parent pole?

Generative Rule 1 says T- "exaggerates the parent AND underdevelops the
opposition" — and `ASPECT_DEFINITIONS` states it correctly and symmetrically for
both sides ("overdevelops T's own side while underdeveloping A. A one-sided
overextension, not merely 'a downside of T'"). So this is not a prompt-absent
question. It is a compliance question.

WHY THIS PROBE EXISTS
=====================
`probe_cost_side.py` set out to test whether the Advisor's T-side-only internal
model mis-prices decisions, and its endpoint relocated the defect entirely.
`rendering._accepted_cost_condition` builds the "— arises when X is held without
Y" clause from `getattr(polarity, side).get()` — the NEUTRAL pole statement in the
graph — and pairs it with the minus attached to that same pole. Neither half comes
from `record_decision` or from the Advisor prompt. So the 4 mispriced and 6
non-degenerative accepted costs that probe found (of 88) are tetrad-internal: the
minus hanging off pole X was an exaggeration of ¬X, or of nothing at all.

Examples it produced, both A2 weak tier, `cofounder_equity`:
  * held "Secure anchor accounts BEFORE removing cofounder"
    minus "Immediate buyout WITHOUT anchor accounts triggers revenue cliff"
    -> exaggerates the RUSH, which is the pole `held` refuses.
  * held "Buy out the cofounder now to secure anchor accounts"
    minus "Buy out cofounder, run company solo"
    -> names no exaggeration at all; it restates the pole.

The archive cannot measure this at useful n: `results/*.json` stores decision
grounds only, no tetrads. So this probe GENERATES tetrads and audits them
directly, which also removes the archive's confound (a decision transcript in the
loop) and its ceiling (only costs that reached a `record_decision`).

MECHANISM UNDER TEST
====================
`TetradDto` is organised by DIAGONAL PAIR, not by parent pole: field descriptions
read "T+ - constructive thesis (positive end of the axis)" and "A- - exaggerated
antithesis (negative end of the axis)", under a required `axis` field naming the
shared dimension. The axis framing is what the model is steered by at the point of
generation; the parent-pole rule lives in the shared preamble and in one
adjectival word ("exaggerated antithesis").

**An axis is symmetric.** "The negative end of the caution axis" is satisfiable by
exaggerating EITHER pole — recklessness overdevelops courage, paralysis
overdevelops fear, and both sit at a negative end of something. So the axis
constraint under-determines which parent the minus belongs to, and the per-field
instruction that would determine it is a single adjective. That is a
competing-signals / under-determination defect, not a missing-information one, so
the fix is not more emphasis (`POSITION_TO_PARENT` already exists in code — the
mapping is known; the prompt never makes the model use it).

THE LABEL-VS-CONTENT DESIGN
===========================
This also answers the question `probe_cost_side` could NOT: is there a real T-/A-
asymmetry, or does an apparent one just track the naming? T/A is a relabelling
convention — read the antithesis as thesis and its minus IS the T- of that reading
— so any count over the position label in an archive measures the naming. Here
that confound is removable, because the probe SUPPLIES the labels: every tension
is generated twice, once as (T=X, A=Y) and once swapped as (T=Y, A=X).

  * If the defect rate follows the POSITION (T- clean, A- broken, in both
    orderings) the asymmetry is real and lives in generation.
  * If it follows the CONTENT (the same statement degrades whichever label it
    wears) there is no label asymmetry, and the archive's 14-vs-2 mention count in
    `advisor/system_prompts.py::_INTERNAL_MODEL` is text, not behaviour.

Pluses are audited too, on the same rubric. Auditing only where a defect is
expected cannot distinguish "minuses are broken" from "the auditor is strict".

PRE-REGISTRATION (written before any tetrad was generated, 2026-08-20)
======================================================================
Population: 6 tensions x 2 orderings (swapped) x 3 replicates = 36 tetrads,
generated on the WEAK tier (every archive defect was weak-tier; a clean result on
a stronger model would not transfer),
yielding 72 minuses (36 at T-, 36 at A-) and 72 pluses. Tensions include the two
`cofounder_equity` framings the archive actually failed on, so a null result
cannot be explained by never presenting the failing input.

Primary endpoint: MISPARENTED = a minus whose exaggeration belongs to the
opposite pole. Secondary defect: NO_EXAGGERATION = a minus that names no
overdevelopment at all (the archive's six restatements). Both are Rule 1
violations and are reported separately, because they have different fixes.
[Kept verbatim as registered. The second one is called `valence_wrong` in the
code and the readout: the auditor's verdict was later split into parentage +
valence to repair the control arm (see RESULT, instrument defect 1). The
definitions and the thresholds below did not change.]

Decision rule, fixed in advance, on the 72 minuses:
  * DEFECT CONFIRMED   MISPARENTED + NO_EXAGGERATION >= 11 (>= ~15%). A
                       generator this far off Rule 1 warrants a prompt change.
  * CLEAN              MISPARENTED + NO_EXAGGERATION <= 4 (<= ~5%). At that rate
                       the archive's 10-of-88 is better explained by the
                       decision path than by generation.
  * INDETERMINATE      between 5 and 10. More n, not a re-read.

Asymmetry endpoint, on the same 72: |defects at T- - defects at A-|, pooled
across BOTH orderings so content is balanced across labels by construction.
  * ASYMMETRY REAL     gap >= 10 (a >= 28pp difference at 36 per position) AND
                       Fisher's exact p < 0.05. Both, because at this n a gap
                       that size is roughly the sensitivity limit and a bare
                       count would over-read it.
  * NO ASYMMETRY       gap <= 4 with total defects >= 8.
  * UNTESTED           total minus defects < 8. A rate comparison whose numerator
                       is near zero cannot separate "symmetric" from "no signal",
                       and reporting it as symmetric would repeat exactly the
                       error `probe_cost_side` made with `opened_against`.

Pre-declared confound: the auditor is an LLM reading a statement pair with no
transcript, and "which pole does this exaggerate" is the same judgement the
generator just made. An auditor sharing the generator's blind spot biases toward
CLEAN. Mitigated by running the audit on the JUDGE model
(`DIALEXITY_E2E_JUDGE`), never on the generator's model, and by requiring the
auditor to quote which pole it read the exaggeration as belonging to — a verdict
with no named pole is not usable evidence.

POST-FIX PRE-REGISTRATION (written before the post-fix run, 2026-08-20)
======================================================================
The baseline below is now the control arm for a prompt change, so the bar for
"the fix worked" is registered here, in the same commit as the fix, before the
re-run.

What changed, in `aspect_generation.py`: the numbered procedure. The root cause
was not weak compliance with a stated rule — `ASPECT_DEFINITIONS` states
parentage correctly and symmetrically — but a procedure that OMITTED it.
`_tetrad_prompt` told the model, in two numbered steps, to (1) name the axis and
(2) place each aspect at an opposite end of it. Neither step mentions the parent,
and the model complied. The fix orders derivation-from-parent as step 1, demotes
the axis to a test applied to the finished pair, annotates parentage on all eight
worked-example aspects (Courage/Fear were bare nouns teaching only the axis), and
names the parent in each of the four aspect field descriptions.

Held fixed: population (same 6 tensions, both orderings, 3 replicates), generator
tier, auditor model, and the audit prompt — verbatim. Only the generation prompt
moves, so a change in the endpoint is attributable to it.

Baseline to beat, from the run in RESULT below:
  raw misparented minuses   13/72   (adjudicated 11/72)
  A- 12/36 raw vs T- 1/36   gap 11

Primary endpoint, unchanged: raw MISPARENTED out of 72, same auditor, tested
against 13/72 by Fisher's exact two-sided test.
  * FIX WORKED   p < 0.05, which at this n requires <= 4/72 — the same count as
                 the CLEAN band already registered above, so the two thresholds
                 agree rather than one being tuned to the other.
  * NO EFFECT    >= 13/72.
  * PARTIAL      5..12/72. Reported as partial, with the count, NOT rounded up to
                 a win: 13/72 vs 5/72 is p ~ 0.08, and a halving that misses the
                 registered bar is a halving that misses the bar.
Secondary: the A-/T- gap, expected to narrow to <= 3 if the mechanism really was
the axis-first procedure (A- sits furthest from its own parent in field order).

Pre-declared risk of a FALSE win, and what was done about it: a worked
counter-example teaches by being concrete, and the first draft of it used the
`freedom_security` A- from THIS population (3 of the 13 baseline defects). That
makes a clean post-fix run unattributable — recitation and rule-learning look
identical at the endpoint. It was rewritten onto Courage/Fear, a pair already in
the prompt and in none of the six probed tensions
(`TestTetradParentage::test_system_prompt_carries_a_counter_example_from_outside_the_probe_set`
pins that). The per-tension breakdown stays in the readout regardless, because
`freedom_security`'s defect content was still diagnostic input.

Run:
  poetry run pytest tests/e2e/probe_tetrad_pole.py -s --real-llm    (needs Memgraph)
  poetry run pytest tests/e2e/probe_tetrad_pole.py -s              (free: prints
      the pre-registration, the population, and one rendered audit prompt)

Cap with PROBE_TETRAD_POLE_LIMIT=<n> to shorten a run; the cap PRINTS when
active, so a truncated run can never read as full coverage.


RESULT (generator haiku-4.5 weak tier, auditor fable-5, n = 36 tetrads, 2026-08-20)
===================================================================================
Full pre-registered population, 36 of 36 generated, 144 aspects audited, 0 audit
errors.

                  parent own   other   neither  | valence_wrong
    T-                    35       1         0  |            0
    A-                    24      12         0  |            0
    T+                    35       1         0  |            3
    A+                    31       4         1  |            2

Endpoint, raw:      13 of 72 minuses misparented        -> floor was 11, CONFIRMED
Auditor control:     6 of 72 pluses  misparented        -> not an over-flagger
Asymmetry, raw:     T- 1/36 vs A- 12/36, gap 11, Fisher p = 0.0013 -> both bars met

ADJUDICATED, by reading all 13 rather than taking the branch. 11 of 13 survive.
The two I reject are the same finding twice — `cofounder_retention` forward rep1
and rep3, both "cofounder exits abruptly, severing all customer relationships"
attached to A = "Take full ownership and run the company solo". The auditor read
these as retention's dependency collapsing. But an abrupt exit that strands the
relationships is what solo-ownership pushed one-sidedly PRODUCES; the aspect names
an event (the exit) whose cause is the A-side push. Coherent either way, so they
do not count. The other 11 are unambiguous, and 8 are textbook: "Total collapse
and loss of all binding coherence" as A- of A = Security (x3 wordings), "Complete
absorption into collective identity" as A- of A = Individual, "unchecked local
autonomy" as A- of A = Mandate uniform process discipline (x2).

So, stated honestly:
  * Rule 1 misparentage at generation is REAL. 11 of 72 confirmed, which lands
    EXACTLY on the pre-registered floor of 11 — a confirmed defect sitting on the
    line, not comfortably past it. Report it that way.
  * The A- concentration is the substantive finding: 10 of the 11 confirmed
    defects are at A-. Per-position that is A- 10/36 (28%) vs T- 1/36 (3%).
  * The pre-registered asymmetry bar is NOT met after adjudication. Removing two
    A- findings drops the gap to 9, one unit under the bar of 10, while the RATE
    ratio is still ~10x and Fisher stays well under 0.05. The gap bar was
    registered as an absolute count and that was the wrong shape for the question
    — but it was registered, so the result is "direction large and consistent,
    pre-registered bar missed by one unit", NOT "asymmetry confirmed". Moving the
    bar now would be moving the goalposts, so it stays where it was written.

Independent corroboration, unprompted: fixing `tests/test_aspect_axis_real_llm.py`
(broken fixture, see `_classify`) made it run for the first time, and its
Freedom/Security tetrad produced `A- = "Reckless collapse: freedom abandoned into
chaos and helplessness"` on A = Security — Freedom's exaggeration on the wrong
parent, the same defect, from a different fixture that was not built to look for
it. Its Individual/Collective tetrad got BOTH minuses right, matching this
probe's cross-tab (freedom_security 3 defects, individual_collective 1).

What the swap bought, and what it did not:
  * It bought the position/content separation the archive could not give: the
    defect stays at A- in BOTH orderings, so it follows the POSITION, not the
    statement. `freedom_security` is the cleanest case — 3 defects in forward
    (A = Security) and 0 in swapped (A = Freedom), i.e. the A- SLOT received the
    "dissolution of bonds" content either way, which is correct when Freedom sits
    at A and wrong when Security does.
  * It did not buy a reading of the CLEAN cells: this probe prints only defects,
    so the above is inferred from where defects fall, not from having read the 59
    compliant minuses. A probe that printed every aspect could confirm the
    slot-filling mechanism directly. Worth doing before writing a prompt fix that
    assumes it.

Two instrument defects were found and fixed BEFORE this run, both worth carrying:
  1. The plus control was uninterpretable by construction. One verdict field in
     minus-only vocabulary scored the pluses 4 defects of 4, because
     "no_exaggeration" is the CORRECT answer for a constructive aspect. Split into
     parentage (shared by both arms, so comparable) + valence (position-specific).
     A control that cannot come out clean measures nothing.
  2. `meaning=<text>.lower()` cannot reach the generator at all — `_tetrad_prompt`
     resolves `lookup_aspect_apex` for all four positions and raises on an
     unparseable meaning, before the provider call. Both poles now go through the
     real `StatementClassification`. See `_classify` for why a hand-PICKED branch
     would be worse than a wrong one.

POST-FIX RESULT, run 1 (prompt at ae10a32, same population/tier/auditor, 2026-08-20)
====================================================================================
                        baseline   post-fix   Fisher two-sided
  misparented minuses     13/72      4/72     p = 0.036   <- REGISTERED PRIMARY
  total minus defects     13/72      5/72     p = 0.076
  adjudicated             11/72      4/72     p = 0.099
  A- misparented          12/36      4/36     p = 0.045
  T- misparented           1/36      0/36
  plus arm (control)       6/72      6/72     p = 1.0

The registered primary endpoint is MET, and by exactly zero margin: the bar was
<= 4/72 and it came in at 4/72. One cell adjudicated the other way is 5/72 and
p = 0.076, which the registration already named PARTIAL. So:

  THE HONEST HEADLINE. The fix cleared its pre-registered bar on the endpoint as
  registered (raw, 13 -> 4). The same comparison on ADJUDICATED counts (11 -> 4)
  does NOT clear, p = 0.099. Both comparisons are defensible and they disagree,
  so this is "probably real, not established" — a 3x reduction whose n is too
  small to pin at this defect rate. Not a win to bank yet.

I adjudicated all 4 residual cases and upheld all 4, holding the baseline's own
standard. Worth recording because one of them LOOKS like a case I rejected there:
baseline rejected "cofounder exits abruptly" as A- when A was "run the company
solo" (an abrupt exit IS going-solo pushed one-sidedly, so the auditor was being
over-clever). Post-fix has the mirror — "Sudden cofounder exit" as A- when A is
"RETAIN the cofounder" — where an exit is retention's opposite, not its
overdevelopment. Same rule, opposite verdict, and applying it asymmetrically
would have manufactured a cleaner number.

What survived the fix, unchanged in shape: all 4 residual misparented minuses sit
at A-, none at T-, and all 4 are still the minus that negates its facing plus.
The mechanism is 3x rarer, not gone. The gap (4 vs 0) is no longer demonstrable
at this n and the probe says UNTESTED rather than claiming symmetry.

The plus arm did not move at all: 6/72 both runs, p = 1.0, despite the plus
fields getting the same parentage clause. Two readings, both worth keeping:
  * As an auditor-stability check it is the strongest single number here — the
    auditor flagged exactly as many pluses before and after, so the 13 -> 4 drop
    on the minuses is not the auditor going soft between runs.
  * As a control it is now IMPURE, and by my own edit: I changed `t_plus`/`a_plus`
    descriptions too, so "untouched arm" no longer describes it. Registering an
    arm as a control and then editing it is exactly the mistake instrument defect
    1 was about, committed in the other direction.
  * 4 of the 8 residual plus defects are `cofounder_sequencing`, the option-pair
    tension. For mutually exclusive courses of action a plus that "also takes up
    what the other pole offers" reads as the other pole's plan — CLAUDE.md already
    flags named options as a fork that is not the tension. That is the next target,
    and it is not a parentage bug.

CONFOUND I registered as absent and was wrong about. I wrote "held fixed:
population, tier, auditor, audit prompt — only the generation prompt moves." The
classification drifted between the two runs, and it is upstream of the prompt:
  "Secure the anchor accounts"  Integrity   -> Resilience
  Freedom                       Water       -> Air
  "Decide now and commit"       Flexibility -> Fire
  "Wait until unknowns resolve" Fidelity    -> Integrity
`StatementClassification` is itself a non-deterministic LLM call, and the branch
it returns SELECTS THE APEX ROW interpolated into the generation prompt. So the
two runs are not a matched pair: 4 of 12 poles taught from a different apex. No
reason a Resilience apex fixes parentage where an Integrity one does not, so this
probably does not explain the direction — but "probably" is the whole point, and I
cannot claim my edit was the only difference. It also means run-to-run variance in
this pipeline is larger than the comparison assumed, which is the second reason to
replicate rather than bank 4/72.

REPLICATION PRE-REGISTRATION (written before run 2, after seeing run 1)
=======================================================================
Replicating the POST-FIX arm only, n = 36, identical config and prompt. Pooling is
declared HERE, before run 2, so it is not a post-hoc choice:
  * Primary: baseline raw 13/72 vs pooled post-fix raw (run1 + run2) / 144.
  * CONFIRMED     pooled p < 0.05 AND run-2 raw <= 8/72 (run 2 independently in
                  the same neighbourhood, so the pooled p is not carried by run 1).
  * NOT CONFIRMED run-2 raw >= 13/72. Run 1 was noise; the fix is unproven and
                  says so, prompt edit notwithstanding.
  * Between 9 and 12: reported as such, pooled p reported either way.
Adjudicated pooled vs adjudicated baseline 11/72 is reported alongside, never
instead of.
Secondary, free and independent of my edit: run 2 gives a second reading of the
12 pole classifications, so branch stability becomes a measured quantity (how
many of 12 agree across runs) rather than an anecdote about 4 that moved.

REPLICATION RESULT, run 2 — NOT CONFIRMED (2026-08-20)
======================================================
  misparented minuses   baseline 13/72 | run 1 4/72 | run 2 9/72 | pooled 13/144
  total minus defects   baseline 13/72 | run 1 5/72 | run 2 13/72 | pooled 18/144

  POOLED misparented 13/144 vs 13/72 : p = 0.075   <- registered primary
  POOLED total       18/144 vs 13/72 : p = 0.306
  run 2 alone         9/72  vs 13/72 : p = 0.488
  run 1 vs run 2      4/72  vs  9/72 : p = 0.244

BOTH prongs of CONFIRMED fail. The registration required run-2 <= 8/72 (it is 9,
missing by one cell) AND pooled p < 0.05 (it is 0.075). The bar stays where it was
written; run 1's 4/72 was the favourable tail of a noisy distribution, and the
9-to-12 band I registered for exactly this case is where it landed.

  THE FIX IS UNPROVEN. Point estimate: 18.1% -> 9.0% misparented, a halving that
  does not reach significance at n = 144. Direction is consistent across both runs
  (4 and 9, each below 13) and no comparison suggests harm, but consistency of
  direction across two runs I chose to pool is not the endpoint I registered.

Kept anyway, and the reason is not statistical: the procedure at `_tetrad_prompt`
omitted the parentage rule outright — two numbered steps, "name the axis" and
"place each aspect at an opposite end", neither mentioning the parent. That is a
defect in the instruction as written, readable in the source without any run, and
worth repairing whether or not this population can resolve the effect size. What
is NOT established is that repairing it fixes the behaviour.

One nominally-clearing secondary, reported and deliberately NOT promoted:
POOLED A- misparented 11/72 vs baseline 12/36, p = 0.045. The primary failed, and
this is one of seven tests run on the same data. Reading it as the result would be
picking the test that agrees with me after the registered one did not.

Where the residual defect lives, consistent across all three runs:
  * A- carries it: pooled 11 of 13 misparented minuses are at A-, T- has 2.
  * `cofounder_retention` is untouched by the fix — 3 forward + 3 swapped in the
    BASELINE and 3 + 3 again in run 2. Six of run 2's nine sit there. Whatever
    breaks that pair is not the missing derivation step.
  * `process_autonomy` and `decide_wait` went to 0 minus defects in run 2 and
    0/1 in run 1, from 2 and 0 in the baseline.

UPSTREAM INSTABILITY, measured across the three runs and independent of my edit
==============================================================================
The 12 pole classifications, read three times (baseline | run 1 | run 2). The
branch SELECTS the apex row interpolated into the generation prompt, so this is
prompt content, not metadata:

  Buy the cofounder out now       Integrity   Integrity   Integrity    stable
  Retain the cofounder            Integrity   Integrity   Integrity    stable
  Take full ownership solo        Integrity   Integrity   Integrity    stable
  Collective                      Integrity   Integrity   Integrity    stable
  Mandate uniform process         Integrity   Integrity   Integrity    stable
  Let teams own their process     Flexibility Flexibility Flexibility  stable
  Individual                      SIMPLE      SIMPLE      SIMPLE       stable
  Secure the anchor accounts      Integrity   Resilience  Integrity    wobbles
  Security                        Integrity   Integrity   Resilience   wobbles
  Wait until unknowns resolve     Fidelity    Integrity   Fidelity     wobbles
  Decide now and commit           Flexibility Fire        Fire         CROSSES
  Freedom                         Water       Air         Fire         3 for 3

7 of 12 stable, 5 wobble. Two cases are worse than a wobble — "Decide now and
commit" crossed from SYSTEMIC (Flexibility) to ELEMENTAL (Fire), changing the apex
vocabulary wholesale, and "Freedom" returned a different element on all three
readings. Per CLAUDE.md the same branch also feeds HS, so this reaches
`_rank_polarities` (HS_THRESHOLD = 0.7), not just this probe.

This is very likely part of why the same prompt gave 4/72 and 9/72: for 4-5 of 12
poles the generation prompt was not the same prompt. It is a separate defect from
the one this probe was built for, it is upstream of it, and it should be measured
on its own (n readings of one pole set, no generation) before anything downstream
of the classifier is measured again.

  RETRACTED from this section: I originally wrote that the split is "by FORM not
  domain — every long concrete course-of-action stable, every short abstract noun
  not." That was read off these same 12 rows and it is false.
  `probe_classifier_stability.py` tested it on 36 statements written for the
  purpose (bare noun / short action / long course of action, domains matched
  across arms): 6/12, 5/12, 7/12 unanimous, gap 1, p = 1.0 — inside the
  pre-registered no-effect band. The instability is real and worse than this table
  shows (only 38% of 47 texts are stable on family+domain+branch over 6 readings);
  its CAUSE is unidentified.

RETROSPECTIVE POWER — why the verdict above carries less than it looks like
==========================================================================
Computed after the fact with `tests/e2e/power.py`, which did not exist when this
probe was designed. It should have.

  this design, aspect-level, n = 72/arm, 18% -> 9%   POWER = 0.28
  0.80 would have needed n = 252/arm (126 tetrads/arm, 3.5x what was run)

So the design had roughly a 1-in-4 chance of detecting exactly the effect its
point estimate suggests. Three consequences, and they revise the reading above
rather than the numbers:

  1. NOT CONFIRMED was close to preordained. A 72%-likely outcome under a REAL
     effect cannot be evidence against it. The verdict stands as written — the fix
     is unproven — but "unproven" here means the instrument was too small to look,
     not that the fix was weighed and found wanting.
  2. The replication did not overturn run 1. I framed 4/72 as "the favourable tail
     of a noisy distribution", which is right, and 9/72 as the correction. Both are
     draws from a distribution this design cannot resolve; the honest statement is
     that the two runs are mutually consistent AND consistent with no effect.
  3. Enlarging THIS population is the wrong repair. Reaching 0.80 by brute n costs
     3.5x; reaching it by enrichment costs less than the original run, because
     power responds to the base rate faster than to n (`power.py::enrichment`).
     The enrichment must select on a property known in advance — e.g. "the two
     poles are mutually exclusive named options rather than opposites", which
     CLAUDE.md already flags structurally and which the residual-defect
     concentration in `cofounder_*` is consistent with — and NOT on which cells
     failed in the runs being compared against, which would bake the selection
     into the baseline arm's rate.

General lesson, now in `power.py`'s module docstring and the review skill: an
endpoint and a pre-registered bar with no power calculation is a coin-flip dressed
as a hypothesis test. Pre-registration prevents moving the goalposts; it does
nothing about goalposts too small to hit.
"""

from __future__ import annotations

import asyncio
import collections
import os
import time
from typing import Literal, Optional

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                             TetradDto)
from dialectical_framework.concerns.statement_classification import (
    ClassificationResult, StatementClassification, parse_meaning_uri)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import \
    HasPolarityRelationship
from dialectical_framework.graph.scope_context import scope
from e2e.config import E2EConfig
from e2e.modelctx import using_model

pytestmark = [pytest.mark.llm]


#: (label, side_x, side_y). Each is generated BOTH ways: (T=x, A=y) and (T=y, A=x).
#: The first two are the framings the archive actually produced broken minuses on
#: — a clean result on general tensions while the failing input is absent would
#: not be evidence about the failing input.
_TENSIONS: list[tuple[str, str, str]] = [
    (
        "cofounder_sequencing",
        "Secure the anchor accounts before removing the cofounder",
        "Buy the cofounder out now and consolidate ownership",
    ),
    (
        "cofounder_retention",
        "Retain the cofounder in the key customer relationships",
        "Take full ownership and run the company solo",
    ),
    ("freedom_security", "Freedom", "Security"),
    ("individual_collective", "Individual", "Collective"),
    (
        "process_autonomy",
        "Mandate uniform process discipline across all teams",
        "Let teams own their process where they demonstrably deliver",
    ),
    (
        "decide_wait",
        "Decide now and commit",
        "Wait until the load-bearing unknowns resolve",
    ),
]

_REPLICATES = 3

_PREREG_DEFECT_FLOOR = 11
_PREREG_CLEAN_CEILING = 4
_PREREG_ASYMMETRY_GAP = 10
_PREREG_ASYMMETRY_MIN_DEFECTS = 8


# --- What the auditor returns -------------------------------------------------


class _PoleVerdict(BaseModel):
    """Two ORTHOGONAL questions, deliberately not one verdict field.

    The first version asked a single question in minus-only vocabulary
    ("overdevelops_own_pole" / "misparented" / "no_exaggeration"). Run on the plus
    positions as a control, that instrument returned 4 defects of 4 — because
    "no_exaggeration" is the CORRECT answer for a constructive aspect, and the
    control counted it as a failure. The auditor said so in its own rationale: "as
    an exaggeration audit it registers none". A control that cannot come out clean
    measures nothing, so parentage and valence are now separate.

    `parent` is asked in identical words of all four positions, which is what makes
    the plus arm a real control: misparentage is the Rule 1 property under test and
    it means the same thing for T+ as for T-. `valence_matches_claim` is
    position-specific and reported on its own.

    Literal order matters: the mock brain fills the FIRST allowed value, so the
    compliant verdict leads — a mocked run must not manufacture a finding."""

    parent: Literal["own_pole", "other_pole", "neither", "unreadable"] = Field(
        description="Which of the two poles this aspect is a development or "
        "degeneration OF, regardless of whether it is positive or negative."
    )
    pole_it_belongs_to: str = Field(
        description="Quote the pole statement this aspect actually hangs off. "
        "Required: a verdict that names no pole is not usable evidence."
    )
    valence_matches_claim: bool = Field(
        description="True if the aspect has the direction its position claims — "
        "a one-sided overdevelopment where an exaggeration is claimed, a "
        "constructive development where one is claimed. False if it merely "
        "restates its pole or names a neutral circumstance."
    )
    why: str = Field(
        description="One sentence. Name the structure, not the sentiment."
    )


_AUDIT_SYSTEM_PROMPT = """You are auditing one aspect of a dialectical tetrad for
two structural properties. Ignore whether the aspect is well written, whether it
is desirable, and whether you agree with it.

The tetrad sits on an opposition between two poles:

    POLE ONE: {pole_one}
    POLE TWO: {pole_two}

The aspect under audit is claimed to hang off POLE ONE. It is claimed to be:

    {claim}

The aspect is:

    {aspect}

Answer two SEPARATE questions about it.

QUESTION 1 — PARENTAGE. Which pole is this aspect a development or degeneration
OF? Ask which pole, taken further, PRODUCES this aspect. This question is about
origin only; a positive and a negative aspect are placed the same way.
- "own_pole": it grows out of POLE ONE. Correct.
- "other_pole": it grows out of POLE TWO, so the tetrad has hung it on the wrong
  parent.
- "neither": it grows out of some third thing — an outside circumstance, or the
  two poles combined into one course of action.
- "unreadable": too vague to place. Use sparingly.

QUESTION 2 — VALENCE. Does the aspect have the direction claimed above?
- A claimed EXAGGERATION must be its pole pushed one-sidedly with the other pole
  absent — not "a bad thing that happens", not "a risk in the vicinity".
- A claimed CONSTRUCTIVE DEVELOPMENT must develop its pole in a way that also
  strengthens what the other pole offers.
- Answer false if the aspect merely restates its pole, or names a neutral
  circumstance with no direction.

Worked contrast on POLE ONE = "Courage", POLE TWO = "Fear".
Claimed as an exaggeration of POLE ONE:
- "Foolhardiness": courage pushed with caution absent.
  -> parent = own_pole, valence_matches_claim = true.
- "Paranoia": fear pushed with courage absent. Wrong parent.
  -> parent = other_pole ("Fear"), valence_matches_claim = true.
- "Being brave in difficult moments": grows out of Courage but pushes nothing.
  -> parent = own_pole, valence_matches_claim = false.
Claimed as a constructive development of POLE ONE:
- "Acting decisively while naming the real risk": develops Courage and takes up
  what Fear is for.
  -> parent = own_pole, valence_matches_claim = true.
- "Careful risk assessment before acting": this is what Fear is for, developed.
  -> parent = other_pole ("Fear"), valence_matches_claim = true.

Note that both "Foolhardiness" and "Paranoia" sit at a negative end of the same
caution axis, and both "acting decisively" and "assessing risk" sit at a positive
end of it. Sitting opposite an aspect of the other sign is NOT evidence of correct
parentage; an axis is symmetric, and either pole can supply either of its ends.

Judge the structure, not the wording."""


def _audit_prompt(pole_one: str, pole_two: str, position: str, aspect: str) -> str:
    claim = {
        "T+": "a constructive development of POLE ONE",
        "A+": "a constructive development of POLE ONE",
        "T-": "a one-sided exaggeration of POLE ONE",
        "A-": "a one-sided exaggeration of POLE ONE",
    }[position]
    return _AUDIT_SYSTEM_PROMPT.format(
        pole_one=pole_one, pole_two=pole_two, claim=claim, aspect=aspect
    )


# --- Generation ---------------------------------------------------------------


def _branch_of(classification: ClassificationResult) -> str:
    """The taxonomy branch a classification landed in, for the readout."""
    if classification.is_simple:
        return "SIMPLE"
    _, _, branch, _ = parse_meaning_uri(classification.meaning)
    return branch or "?"


class _Cell(BaseModel):
    """One generated tetrad, with the labelling that produced it."""

    tension: str
    #: "forward" = (T=side_x, A=side_y); "swapped" = (T=side_y, A=side_x).
    ordering: str
    replicate: int
    t_text: str
    a_text: str
    #: Taxonomy branch each pole classified into. Recorded because the branch
    #: selects the apex row interpolated into the tetrad prompt, so it is part of
    #: the condition under test, not incidental fixture detail.
    t_branch: str = ""
    a_branch: str = ""
    t_plus: str = ""
    t_minus: str = ""
    a_plus: str = ""
    a_minus: str = ""
    t_plus_vs_a_minus_axis: str = ""
    a_plus_vs_t_minus_axis: str = ""


async def _classify(text: str, cache: dict[str, ClassificationResult]) -> ClassificationResult:
    """Assign a statement its taxonomy meaning the way production does.

    This is not fixture ceremony — it is load-bearing. `AspectGeneration`'s
    `_tetrad_prompt` interpolates `lookup_aspect_apex(parent, position)` for all
    four positions, and that lookup raises on any meaning that does not parse to a
    known branch. A hand-written `meaning=text.lower()` therefore cannot reach the
    LLM at all (it raises in the prompt builder, before the call), and a
    hand-PICKED branch would be worse than useless: the branch chooses the apex
    row the prompt teaches from, so choosing it myself would change the prompt
    under test. The archive's meanings came from this classifier, so the probe
    uses this classifier.

    `anchor`'s `IntroducePolarity._classify_statement` classifies each pole
    independently of its role, so a text's meaning does not depend on whether it
    is sitting at T or at A. That is what makes the label-vs-content swap sound:
    the only thing the swap changes is the POSITION, and one classification per
    distinct text is reused across both orderings and all replicates.
    """
    if text not in cache:
        cache[text] = await StatementClassification().resolve(statement=text)
    return cache[text]


async def _generate(tension: str, ordering: str, replicate: int,
                    t_text: str, a_text: str,
                    cache: dict[str, ClassificationResult]) -> Optional[_Cell]:
    """Run the real full-tetrad path and capture the raw DTO.

    Graph writes are NOT concurrency-safe (GQLAlchemy), so callers must keep this
    sequential-per-task and only the LLM call inside it overlaps.
    """
    try:
        t_class = await _classify(t_text, cache)
        a_class = await _classify(a_text, cache)
    except Exception as exc:  # noqa: BLE001
        print(f"  !! classification failed {tension}/{ordering}/rep{replicate}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return None

    pp = Perspective()
    pp.save()

    t = Statement(text=t_text, meaning=t_class.meaning)
    t.commit()
    a = Statement(text=a_text, meaning=a_class.meaning)
    a.commit()

    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()
    pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

    gen = AspectGeneration()
    captured: list[TetradDto] = []
    original_submit = gen._conversation.submit

    async def _capturing_submit(**kwargs):
        result = await original_submit(**kwargs)
        if isinstance(result, TetradDto):
            captured.append(result)
        return result

    gen._conversation.submit = _capturing_submit  # type: ignore[method-assign]

    try:
        await gen.resolve(perspective=pp, text="")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! generation failed {tension}/{ordering}/rep{replicate}: "
              f"{type(exc).__name__}: {exc}")
        return None
    if not captured:
        print(f"  !! no TetradDto {tension}/{ordering}/rep{replicate}")
        return None

    dto = captured[0]
    return _Cell(
        tension=tension,
        ordering=ordering,
        replicate=replicate,
        t_text=t_text,
        a_text=a_text,
        t_branch=_branch_of(t_class),
        a_branch=_branch_of(a_class),
        t_plus=dto.t_plus.statement,
        t_minus=dto.t_minus.statement,
        a_plus=dto.a_plus.statement,
        a_minus=dto.a_minus.statement,
        t_plus_vs_a_minus_axis=dto.t_plus_vs_a_minus_axis,
        a_plus_vs_t_minus_axis=dto.a_plus_vs_t_minus_axis,
    )


def _plan() -> list[tuple[str, str, int, str, str]]:
    """The full pre-registered cell list, before any capping."""
    plan: list[tuple[str, str, int, str, str]] = []
    for label, side_x, side_y in _TENSIONS:
        for rep in range(1, _REPLICATES + 1):
            plan.append((label, "forward", rep, side_x, side_y))
            plan.append((label, "swapped", rep, side_y, side_x))
    return plan


# --- Free test: the pre-registration is auditable without spending ------------


def test_the_population_matches_the_preregistration() -> None:
    """No LLM. Prints the plan and one rendered audit prompt."""
    plan = _plan()
    tetrads = len(plan)
    print(f"\n=== pre-registered population ===")
    print(f"tensions   : {len(_TENSIONS)}")
    print(f"orderings  : 2 (forward + swapped)")
    print(f"replicates : {_REPLICATES}")
    print(f"tetrads    : {tetrads}")
    print(f"minuses    : {tetrads * 2}  ({tetrads} at T-, {tetrads} at A-)")
    print(f"pluses     : {tetrads * 2}")
    print(f"\ndefect floor {_PREREG_DEFECT_FLOOR}, clean ceiling "
          f"{_PREREG_CLEAN_CEILING}, asymmetry gap {_PREREG_ASYMMETRY_GAP} "
          f"(min {_PREREG_ASYMMETRY_MIN_DEFECTS} defects to compare)")

    print("\n=== one rendered audit prompt (T- on the first tension) ===")
    print(_audit_prompt(
        _TENSIONS[0][1], _TENSIONS[0][2], "T-",
        "Immediate buyout without anchor accounts triggers a revenue cliff",
    ))

    # Every tension must appear in both orderings, or the label-vs-content
    # comparison silently becomes a label-only comparison.
    for label, _x, _y in _TENSIONS:
        orderings = {o for lbl, o, _r, _t, _a in plan if lbl == label}
        assert orderings == {"forward", "swapped"}, label
    assert tetrads == len(_TENSIONS) * 2 * _REPLICATES


# --- The measurement ----------------------------------------------------------


def _fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """p-value for the 2x2 table [[a,b],[c,d]], no SciPy dependency.

    Sums the hypergeometric probability of every table with the same margins
    whose probability is <= the observed table's, which is the two-sided
    convention `judge.py` and the other probes report.
    """
    from math import comb

    n = a + b + c + d
    row1, col1 = a + b, a + c

    def prob(x: int) -> float:
        return (
            comb(row1, x)
            * comb(n - row1, col1 - x)
            / comb(n, col1)
        )

    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    observed = prob(a)
    # 1e-9 absorbs float error on tables that are equiprobable by symmetry.
    return min(1.0, sum(p for x in range(lo, hi + 1)
                        if (p := prob(x)) <= observed + 1e-9))


@pytest.mark.real_llm
@pytest.mark.asyncio
# NOT @traced. conftest's `traced` serialises the test's arguments as the span
# input, and `di_container` is cyclic — the serialiser recurses until the process
# is pinned at 100% CPU with no output and no test ever running. CLAUDE.md names
# this exact trap; two full runs (46 min and 17 min) were lost to it before the
# cause was found, and both looked like a slow provider. `probe_cost_side.py`
# takes the same fixture without `@traced` and completes in ~73s.
async def test_a_generated_minus_overdevelops_its_own_pole(di_container) -> None:
    plan = _plan()
    limit = int(os.environ.get("PROBE_TETRAD_POLE_LIMIT", "0") or 0)
    if limit:
        # Printed, per the no-silent-caps rule: a truncated run must never read
        # as full coverage of the pre-registered population.
        print(f"\n!! PROBE_TETRAD_POLE_LIMIT={limit} active — "
              f"{limit} of {len(plan)} pre-registered tetrads. Partial run.")
        plan = plan[:limit]

    case_node = Case()
    case_node.commit()

    # Generate on the WEAK tier, not the ambient default. Every archive defect
    # this probe is chasing was produced at weak tier; measuring a stronger model
    # would answer a different question and a clean result would not transfer.
    config = E2EConfig.from_env()
    gen_model = config.tiers["weak"]

    with scope(case_node.sid):
        print(f"\n=== generating {len(plan)} tetrads on the WEAK tier: "
              f"{gen_model} ===")
        cells: list[_Cell] = []
        # One classification per distinct text, reused across both orderings and
        # all replicates — see `_classify`. Also keeps the swap honest: forward and
        # swapped cells of one tension share identical meanings by construction, so
        # any difference between them is the POSITION and nothing else.
        class_cache: dict[str, ClassificationResult] = {}
        # Sequential: GQLAlchemy graph writes are not concurrency-safe, and every
        # cell writes a Perspective/Polarity/Statement set before its LLM call.
        for index, (label, ordering, rep, t_text, a_text) in enumerate(plan, 1):
            started = time.monotonic()
            with using_model(di_container, gen_model):
                cell = await _generate(label, ordering, rep, t_text, a_text,
                                       class_cache)
            if cell is not None:
                cells.append(cell)
            # flush=True is load-bearing, not decoration. Generation is
            # sequential and slow, and the first version of this probe printed
            # nothing for 46 minutes because stdout buffers when pytest's output
            # is redirected to a file — so a run that had to be killed produced
            # zero recoverable output and the whole spend was lost.
            print(
                f"  [{index}/{len(plan)}] {label}/{ordering}/rep{rep} "
                f"{time.monotonic() - started:.1f}s"
                f"{'' if cell is not None else '  FAILED'}",
                flush=True,
            )

    print(f"generated {len(cells)} of {len(plan)}")

    # The branch selects the apex row the tetrad prompt teaches from, and SIMPLE
    # takes a different apex path entirely ("Simple", no taxonomy anchoring). A run
    # where poles landed SIMPLE is measuring a different regime than the archive's
    # COMPLEX tetrads, so the classification is reported, never assumed.
    print("\n=== how each pole classified (selects the apex in the prompt) ===")
    seen_branch: dict[str, str] = {}
    for cell in cells:
        seen_branch[cell.t_text] = cell.t_branch
        seen_branch[cell.a_text] = cell.a_branch
    for text, branch in seen_branch.items():
        print(f"  {branch:16s} {text}")
    simple = sorted(t for t, b in seen_branch.items() if b == "SIMPLE")
    if simple:
        print(f"  !! {len(simple)} pole(s) classified SIMPLE — those tetrads take "
              f"the 'Simple' apex, not a taxonomy branch, and are NOT comparable "
              f"to the archive's COMPLEX tetrads.")

    judge_model = config.judge_model
    print(f"\n=== auditor model: {judge_model} ===")

    # (cell, position, aspect_text, own_pole, other_pole)
    units: list[tuple[_Cell, str, str, str, str]] = []
    for cell in cells:
        units.append((cell, "T-", cell.t_minus, cell.t_text, cell.a_text))
        units.append((cell, "A-", cell.a_minus, cell.a_text, cell.t_text))
        units.append((cell, "T+", cell.t_plus, cell.t_text, cell.a_text))
        units.append((cell, "A+", cell.a_plus, cell.a_text, cell.t_text))

    sem = asyncio.Semaphore(6)

    async def audit(unit):
        cell, position, aspect, own, other = unit
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
                      f"{type(exc).__name__}: {exc}")
                return unit, None
        return unit, verdict

    results = await asyncio.gather(*(audit(u) for u in units))

    tally: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    errors = 0
    findings: list[tuple[_Cell, str, str, _PoleVerdict]] = []
    for (cell, position, aspect, _own, _other), verdict in results:
        if verdict is None:
            errors += 1
            continue
        tally[position][verdict.parent] += 1
        if not verdict.valence_matches_claim:
            tally[position]["valence_wrong"] += 1
        if verdict.parent != "own_pole" or not verdict.valence_matches_claim:
            findings.append((cell, position, aspect, verdict))

    def scored(position: str) -> int:
        """Audited units at this position. Sums the four PARENT buckets only —
        `valence_wrong` is a second, overlapping axis and would double-count."""
        return sum(tally[position][p] for p in
                   ("own_pole", "other_pole", "neither", "unreadable"))

    def misparented(position: str) -> int:
        """The Rule 1 endpoint: the aspect belongs to a pole other than its own."""
        return tally[position]["other_pole"] + tally[position]["neither"]

    def defects(position: str) -> int:
        """Either failure. Kept as the total the floor of 11 was registered on, so
        the endpoint definition is unchanged by the control repair."""
        return misparented(position) + tally[position]["valence_wrong"]

    print("\n=== per position ===")
    for position in ("T-", "A-", "T+", "A+"):
        c = tally[position]
        print(f"  {position}: parent own={c['own_pole']} other={c['other_pole']} "
              f"neither={c['neither']} unreadable={c['unreadable']} | "
              f"valence_wrong={c['valence_wrong']}  (n={scored(position)})")
    print(f"  audit errors: {errors}")

    minus_defects = defects("T-") + defects("A-")
    minus_n = scored("T-") + scored("A-")
    minus_misparented = misparented("T-") + misparented("A-")
    plus_misparented = misparented("T+") + misparented("A+")
    plus_n = scored("T+") + scored("A+")

    print("\n=== endpoint (minuses) ===")
    print(f"misparented     : {minus_misparented}/{minus_n}")
    print(f"valence wrong   : "
          f"{tally['T-']['valence_wrong'] + tally['A-']['valence_wrong']}")
    print(f"TOTAL defects   : {minus_defects}/{minus_n}")
    # The auditor's control, on PARENTAGE only — the one question asked in identical
    # words of a plus and a minus, so the two rates are comparable. A minus
    # misparentage rate that merely matches the plus rate is an auditor that cannot
    # place aspects at all, not a Rule 1 violation concentrated in the negatives.
    # (Valence is deliberately excluded here: "is this an exaggeration" and "is this
    # a constructive development" are different questions, and the first version of
    # this probe scored 4 defects of 4 on the pluses precisely by conflating them.)
    print(f"plus misparented (auditor control): {plus_misparented}/{plus_n}")

    if findings:
        print("\n=== every defect, with the pole the auditor read it as ===")
        for cell, position, aspect, verdict in findings:
            flag = ("misparented" if verdict.parent != "own_pole"
                    else "valence_wrong")
            print(f"\n  [{flag}] {cell.tension} / {cell.ordering} / "
                  f"rep{cell.replicate} / {position}")
            print(f"    T (own pole of T-/T+) : {cell.t_text}")
            print(f"    A (own pole of A-/A+) : {cell.a_text}")
            print(f"    aspect                : {aspect}")
            print(f"    parent                : {verdict.parent} "
                  f"({verdict.pole_it_belongs_to})")
            print(f"    valence matches claim : {verdict.valence_matches_claim}")
            print(f"    why                   : {verdict.why}")

    print("\n=== verdict: Rule 1 compliance ===")
    if minus_defects >= _PREREG_DEFECT_FLOOR:
        print(f"DEFECT CONFIRMED: {minus_defects}/{minus_n} minuses violate "
              f"Rule 1 (floor was {_PREREG_DEFECT_FLOOR}).")
    elif minus_defects <= _PREREG_CLEAN_CEILING:
        print(f"CLEAN: {minus_defects}/{minus_n} (ceiling was "
              f"{_PREREG_CLEAN_CEILING}). The archive's 10-of-88 is then better "
              f"explained by the decision path than by generation.")
    else:
        print(f"INDETERMINATE: {minus_defects}/{minus_n} sits between "
              f"{_PREREG_CLEAN_CEILING} and {_PREREG_DEFECT_FLOOR}. More n.")

    print("\n=== verdict: is the T-/A- asymmetry real or just the naming? ===")
    gap = abs(defects("T-") - defects("A-"))
    print(f"defects at T-: {defects('T-')}/{scored('T-')}   "
          f"defects at A-: {defects('A-')}/{scored('A-')}   gap={gap}")
    if minus_defects < _PREREG_ASYMMETRY_MIN_DEFECTS:
        print(f"UNTESTED: only {minus_defects} minus defects total (needed "
              f"{_PREREG_ASYMMETRY_MIN_DEFECTS}). A rate comparison with a "
              f"near-zero numerator cannot separate 'symmetric' from 'no "
              f"signal'. Not reportable as symmetric.")
    else:
        p = _fisher_exact_two_sided(
            defects("T-"), scored("T-") - defects("T-"),
            defects("A-"), scored("A-") - defects("A-"),
        )
        print(f"Fisher exact two-sided p = {p:.4f}")
        if gap >= _PREREG_ASYMMETRY_GAP and p < 0.05:
            print("ASYMMETRY REAL: the defect rate follows the POSITION LABEL "
                  "across both orderings, so it is not a relabelling artefact.")
        elif gap <= _PREREG_CLEAN_CEILING:
            print("NO ASYMMETRY: the defect rate does not follow the label. An "
                  "apparent T-/A- imbalance in prompt text is text, not "
                  "behaviour.")
        else:
            print(f"INDETERMINATE: gap {gap} with p={p:.4f} meets neither "
                  f"pre-registered bar.")

    # Content-vs-label cross-tab: the same statement wears both labels across the
    # two orderings, so a defect that follows the tension rather than the position
    # is a content effect. Printed rather than gated — with 6 tensions no single
    # cell has the n to carry a threshold.
    print("\n=== defects by tension (content) x ordering ===")
    by_tension: dict[tuple[str, str], int] = collections.Counter()
    for cell, position, _aspect, _verdict in findings:
        if position in ("T-", "A-"):
            by_tension[(cell.tension, cell.ordering)] += 1
    for label, _x, _y in _TENSIONS:
        f = by_tension.get((label, "forward"), 0)
        s = by_tension.get((label, "swapped"), 0)
        print(f"  {label:24s} forward={f} swapped={s}")

    # No assertion on the endpoint: this is a MEASUREMENT, and a probe that fails
    # when the generator misbehaves would be un-runnable exactly when it is most
    # interesting. It fails only if it could not measure at all.
    assert minus_n, "no minus was audited — every generation or audit errored"
