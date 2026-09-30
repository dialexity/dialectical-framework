# Antithesis selection: HS ranked the strawman end of the ladder

Lab notes for the 2026-09-30 change to `concerns/antithesis_extraction.py` and
`AnalysisPipeline._rank_polarities`. Rule in CLAUDE.md ("HS gates;
`tetrad_potential` ORDERS"); theory entry in `docs/theory/taxonomies.md` (Mode ×
Arousal plane, "Optimum A").

## How it was found

The blindspot app's probe (`tests/probe_blindspot_paths.py`, `views.md`) ran 20
free utterances through the headless thesis-only `anchor` path. Every expanded
antithesis was a caricature: "Never quit, stay employed forever", "I hate my new
manager", "Strip every feature; ship nothing", "Abandon parents to fend alone".
HS(A) was 0.95 on every row; 17 of 19 tetrads carried `failed: Conceptual
coherence`. The notebook's Case (one utterance, three perspectives) showed the
selection directly, off the antitheses' own Rationales:

| antithesis | branch | HS |
|---|---|---|
| Never quit, stay employed forever | Negation (1.0) | 0.95 |
| Quitting your job is reckless self-sabotage | Inversion (0.9) | 0.85 |
| Starting a company is just gambling | Devaluation (0.8) | 0.75 |

## The mechanism

1. `AntithesisExtraction` generates one candidate per rung of the
   "thesis-lessness" ladder, each asked to be "{branch} of the thesis".
2. Each rates HS against the apex — defined in the shared prompt as
   "[T]-lessness (complete absence/negation)".
3. `_truncate_candidates` keeps the top `count` **by HS**; `_rank_polarities`
   gates at HS ≥ 0.7 and expands the top `MAX_POLARITIES_TO_EXPAND` **by HS**.

Similarity to complete absence of T is maximised by the most total negation, so
the selector structurally prefers the top of the ladder. The theory's own
canonical pair is Love / Indifference — a Privation-rung (0.0) antithesis, an
independent value. Under this selector "Hate" wins. With A already an extreme,
A- has nowhere to go, A+ becomes "the moderate version of the caricature", and
CC fails — which is the 17/19.

Not new: the selector predates the finding by months. Not universal: the
Advisor's `anchor` with BOTH T and A supplied never runs it (the ladder only
classifies a given A). Affected: every build from a bare thesis — `ingest`
(headless builder, `migrate_consultation`), `AnchorTheses`, the Analyst's
`find_polarities`, `note`/`anchor` without an antithesis. The bench's sealed
Advisor result (+0.50 over a builder-made graph) was measured over graphs with
exactly these antitheses: counsel quality survived it, tetrad quality did not.

The theory ledger had it as a known gap: "selection goes by HS, not by [the
paper's] Optimum A" (`taxonomies.md`, status partial), and the paper's
instruction is "ask what functionally opposes the role played by T, not what
negates T".

## The fix

- `ModePointResultDto.tetrad_potential` (0–1): can this opposition be developed
  so it strengthens what T is for (an A+ exists) and does it have its own
  one-sided failure (an A-); low for T's absence or degradation dressed as a
  stance, or a caricature nobody holds. Rated by the same call — a proxy for the
  tetrad's later CC/DV, not a measurement of them.
- `_OPPOSING_POSITION_ASK` in both mode-point prompts: the paper's ask stated
  as a step, with the measured caricature as the concrete failure (the review
  skill's rule: a rule the procedure omits is not a rule; a check stated where a
  recipe belongs becomes the recipe).
- `AntithesisExtraction.selection_key` and `AnalysisPipeline._selection_key`:
  potential, HS as fallback where nothing rated it (SIMPLE path, consolidated
  pairs, pre-existing oppositions). HS keeps the validity gate.
- `TetradPotentialEstimation` persisted next to Mode/Arousal; `polarity_quality`
  and the Analyst's "Reading Polarity Quality" section carry it.

## Before / after (20 utterances, Path B of the probe, Sonnet 5)

Before (2026-09-29): drawn 19/20; antithesis a caricature on 19/19; HS(A) 0.95
uniform; CC passed 2/19; median 49 s.

After (2026-09-30, same 20 utterances, same model; per-item JSON kept in the
session scratchpad): drawn 20/20, errors 0; **CC passed 7/20** (was 2/19);
HS(A) now spread 0.75–1.0 (was 0.95 uniform); median 59 s (was 49 s — the
extra rating costs tokens, and one run's variance is within that).

The antitheses, read by hand and sorted into two piles:

- **A position with its own value — 12/20.** "Build mastery and security within
  employment", "Decline the offer, stay rooted here", "Keep parents at home,
  care for them ourselves", "Strip features down to the essential core", "Trust
  public school to educate my kids", "Confront it now, fully, unfiltered",
  "Chaos itself drives real innovation", "Strict rules prove how much I care",
  "Discipline just kills spontaneity and joy", "Refusing clients protects my
  energy", "Remote work builds a stronger culture", "Promoting your best
  engineer is the right call".
- **A mirror-image stance — 8/20.** "My co-founder always listens to me" (HS
  1.0: the SIMPLE path's mechanical negation, not this selector at all), "I
  fully trust my new manager", "Hire only juniors; seniors slow the team",
  "Keep funding brother, no matter what", "Double the marketing budget to grow",
  "Prices too high, must be lowered", "Every meeting must end with a firm
  decision", "Always be reachable for work". These are the opposite STANCE
  rather than the absent-T caricature ("never risk anything") the old selector
  chose, and several still yield a usable A+ ("Help with clear, sustainable
  limits attached"), but they are not the functional opposition the paper asks
  for.

So: the selector no longer picks the strawman end of the ladder (19/19 → 0/20
of the "never/forever/nothing" shape), the coherence pass rate more than
tripled, and roughly a third of the antitheses are still mirror stances. One
sample each side, one rater. Two threads remain open, both upstream of the
selector:

1. **The candidates themselves.** The ladder's high rungs are asked for
   Negation/Inversion of T; with the ask fixed the model now offers a stance
   rather than a caricature there, but a stance is what those rungs produce.
   The genuine-position candidates come from the middle and low rungs. Whether
   the selector should weight rungs, or the rung prompts should change, is a
   prompt-review question with a measurement behind it — not this change.
2. **The SIMPLE/COMPLEX boundary.** "My co-founder never listens to me" was
   classified SIMPLE and mechanically negated (HS hardcoded 1.0, no ladder, no
   potential). CLAUDE.md already calls that boundary the most leverage-dense
   prompt in the pipeline; this run is one more row for it.

What this does NOT settle: whether CC at 7/20 is the ceiling of this path or
the selector's floor. The tetrads behind the 13 failures were built from
positions, so the next look is at `AspectGeneration` on these pairs, not here.

## Working through the four open items (2026-09-30, `tests/e2e/probe_tetrad_quality.py`)

The instrument: per expanded perspective on the thesis-only `anchor` path,
everything the pipeline persisted (thesis classification, antithesis rung /
HS / potential, four aspects, SP, CC per control statement, DV, verdict) plus
three auditors on the bench's judge model — antithesis KIND (position /
mirror / caricature / not an opposition, operational definitions in the file),
T+/A+ relation (distinct / same compromise), and the archive's parentage
auditor from `probe_tetrad_pole`. Incremental JSON under
`tests/e2e/results/tetrad_quality/`. Set A = the 20 utterances the finding was
made on; set B = 20 fresh ones for confirmation.

**Replication (set A, code as committed in 8ad6b5e).** CC pass 9/20 on the
first tetrad, 14/40 over all expanded. Every expanded antithesis on the top
three rungs (negation 20, inversion 13, devaluation 7 of 40); the HS gate set
aside 59 of 99 candidates, and the set-aside pile holds the best positions
("Build a side hustle, keep the job" HS 0.45; "He listens, but only to what
confirms his views" 0.45). `tetrad_potential` rated in isolation is flat: 0.75
on 68 of 99, mean 0.78 on CC-pass vs 0.77 on CC-fail — the selection fix
worked through the ASK (top-rung candidates became positions), not through the
ranking. Mirrors pass CC more than positions (6/8 vs 2/9): a one-axis reversal
makes coherent control statements; "mirror = bad" was a prior the data refused.

**Item 2 — SIMPLE/COMPLEX.** 5 readings × 20 utterances on Sonnet 5: 0 flips,
never SIMPLE. Yesterday's SIMPLE reading of "My co-founder never listens to me"
was a rare event, consistent with the Aug-20 result (0 of 47 on Haiku). What
that thread did find and fix: the classifier's answer arriving as
`{"$PARAMETER_NAME": {...}}` / `{"parameter name": {...}}`, an envelope the
salvage did not unwrap — ten blind re-asks per occurrence, one anchor in twenty
lost. Rule 4 in `use_brain._envelope_candidates` (a single key of the model's
own, inner object still gated on naming a real field) + `TestASingleKeyOfTheModelsOwn`.
Closed.

**Item 3 — the CC failures.** A hand audit of the 20 after-run tetrads
suggested plus CONVERGENCE (T+ and A+ the same compromise: 8/20, CC 25% there
vs 42% distinct). Tried: a `PLUS_HEDGE_CHECK` as failure (c) of step 3 and the
two control statements as a construction step 4. The instrument said no: CC
9/20 → 9/20 first-tetrad, 35% → 41% over all (noise), same-compromise 40% →
36%, and CC did not differ by relation (44% vs 39%); parentage already clean
(own pole 41/44 and 43/44). Reverted the same day; the null is recorded next to
`PLUS_RESTATEMENT_CHECK`. What the two runs DO show about the metric itself:
CC scores cluster at 0.55 and 0.75/0.85 with a hard line at 0.7 — a third of
the failures sit at 0.55–0.65; SP is ≈1.0 on nearly every tetrad here and
separates nothing; DV separates pass from fail (mean 0.70 vs 0.45, 0.69 vs
0.42) and is scored in the SAME call as CC (the DESIGN FORK the DTO warns
about — anchoring is likely); the paper's own SP > 0.5 ∧ DV > 0.5 passes
21/40 and 24/44 where CC passes 14 and 18, with 7 CC-failures per run passing
it. Whether a CC-failed tetrad is a BAD tetrad has not been shown — nobody has
read them against the score. The lever for item 3 is therefore the acceptance
metric and its validation, not the generation prompt; open. One more
measurement on the same 44 tetrads (`scratchpad/cc_dv_separate.py`, generator
model): CC and DV re-scored in SEPARATE calls. Same-call corr(CC, DV) = 0.96;
separate calls 0.69 — the DTO's DESIGN FORK is real, DV scored beside CC is
mostly CC again. Separate-call CC passed 15/44 against the pipeline's 18, with
37/44 verdicts agreeing; separate CC scores are as bimodal (0.35 / 0.55 / 0.75).
Separate DV mean 0.50; the paper's SP ∧ DV with separate DV passes 18/44. So
splitting the call changes DV's meaning but not the pass count, and nothing yet
says which of these is the tetrads' truth: the next instrument is a blind hand
read of CC-pass vs CC-fail tetrads against the score.

Done, same day: 24 tetrads of the A2 run I had not seen (ranks 2–3), shuffled,
scores hidden, each pair of control statements judged by hand as holding or
not. Agreement with CC **18/24**; CC is strict rather than lax (4 tetrads I
pass it fails, 2 it passes I fail); DV mean 0.65 where I pass, 0.43 where I
fail. So the metric is usable and the reframing above is retracted: the lever
IS generation. And the blind read names the failing shape, which none of the
three auditors measured: in most failures the minus is the plus's OPPOSITE,
not the plus's own slide when the other plus is absent — "naming the issue"
(A+) without preparing (T+) "yields silence forever" (A-) is false by
construction, however clean A-'s parentage. The procedure derives each minus
from its PARENT, anywhere in that parent's degradation space; the control
statement needs it derived from its PLUS ("what T+ becomes when A+ is
absent", which is what `ASPECT_DEFINITIONS` already says and step 1 does not
do). That is a derivation-order change — pluses first, each minus as its
plus's degeneration — and it is queued as A5, one variable, after the gate.

**Item 1 — selection.** Two steps, one variable each: (A3) the comparative
Optimum-A ranking (`OptimumARankingDto`, one call per thesis over all
candidates, shuffled, rank → potential, the flat self-rating as fallback);
(A4) the expansion gate lowered from HS ≥ 0.7 to a validity floor so the lower
rungs can reach expansion at all. Results appended below as they land.

**A3 — comparative ranking (gate still 0.7), set A.** CC 7/20 on the first
tetrad, 12/37 over all expanded — no gain against A1/A2's 9/20 (noise). What
moved is antithesis KIND: non-oppositions 8 → 5 → 1 across A1/A2/A3 (all
expanded), positions 11/20 on the first tetrad against 9/20. The ranker's own
preference does not predict CC (potential mean 0.85 on CC-pass, 0.91 on
CC-fail), and rungs are unchanged because the gate is — negation 17, inversion
15, devaluation 5. Read: selection among top-rung candidates is now better at
picking an opposition and irrelevant to coherence; CC is decided downstream, in
the aspects (A5).

**A4 — gate lowered to the HS scale's 0.3 floor (+ ranking), set A, 13 of 20
before the machine stopped the run (memory).** Rejected. CC pass 9/51 (18%)
over all expanded and 2/13 on the first tetrad, against 32–45% in A1–A3; the
newly admitted HS < 0.7 antitheses passed CC at 3/25 against 6/26 for the old
pool; non-oppositions 15/51 (were 8/40, 5/44, 1/37); the floor also admits
~4 polarities per thesis instead of ~2. The rungs did open up (blocking 7,
skew 6, distortion 5, corruption 3, suppression 1) and the tetrads built on
them were worse. So the set-aside examples that motivated the floor were the
exceptions: HS measured against "[T]-lessness" is a quality gate after all,
and 0.7 stays. Reverted the same day; the constant carries the numbers.

**A5 — derivation order (pluses first, each minus as its plus's slide), set
A, gate 0.7 + ranking.** Rejected, and worse than the null: CC 5/20 on the
first tetrad, 6/38 over all expanded (A1–A3: 7–9/20, 12–18/40); T+/A+ the same
compromise in 19/38 (was 14–16 of ~40). Deriving the minus from the plus
pulled the pluses toward one middle — the minus became "the plus without the
other", which reads as a hedge of the plus, and both pluses drifted to meet
it. The blind read's diagnosis (the minus is the plus's opposite) was right
about the failing tetrads and wrong about the remedy. Reverted the same day;
the procedure's docstring carries both null results.

**Set B (20 fresh utterances) ran once with A5 in the tree**: CC 6/20 first,
15/49 all; positions 38/49. Not a confirmation of anything, since A5 is out;
rerun on the final stack below.

**What the day settles about the CC lever.** Three generation-side changes
(two prompt checks, one derivation order) and two selection-side changes
(comparative ranking, gate floor) moved CC by nothing or downward; the only
thing that moved it upward was yesterday's selection fix (caricatures out:
2/19 → 7/20). The tetrads that fail CC do so from real positions with clean
parentage, and the blind read agrees with CC on 3 of 4. Whatever raises it
next is not a re-wording of the procedure. Candidates worth a measured run,
none tried: the SIMPLE/COMPLEX-independent taxonomy apex fed to
`AspectGeneration` (every aspect is scored against an apex the classifier
chose — `probe_classifier_stability` found that branch wobbles); the CC judge
given the case CONTEXT (the anchor path passes none); and a model-tier check,
since every number here is Sonnet 5 on utterances with no context at all.

**Set B on the final stack** (selection fix + comparative ranking + salvage
rule 4, gate 0.7; 20 fresh utterances): CC 7/20 on the first tetrad, 11/27
over all expanded; antithesis a position 14/20 (mirror 5, not an opposition
1), caricatures 0; rungs negation 16 / inversion 3 / devaluation 1;
parentage clean. Consistent with set A (7–9/20). The per-kind CC split
inverted between sets (positions 6/14 here, 2/9 on set A; mirrors 1/5 vs
6/8) — at n = 20 those splits are noise and should not be read.

**Item 2, reopened by set B.** 3 of 20 fresh utterances classified SIMPLE —
all three the person REPORTING a situation ("My daughter wants to drop out of
university to travel", "My father refuses to stop driving and he's
eighty-four", "My sister expects me to host every family holiday") — and each
became a mechanical negation ("Daughter wants to stay in university and not
travel", HS 1.0, no ladder, no potential) whose tetrad failed CC. Set A had
none, so the 0/100 flip count stands; this is not instability but the RULE:
an observable report is SIMPLE by definition, and on the anchor path the
person's report IS their position. Open, and it is a prompt question with a
measured population now (`SET_B`): either the classifier learns "a person's
account of a situation they are in is COMPLEX", or the anchor path passes
context that says so. Untried.

## Where the day ends

Kept: yesterday's selection fix, the comparative Optimum-A ranking, salvage
rule 4, the instrument. Tried and reverted with the numbers on them: two
prompt checks (null), the gate floor (worse), the derivation order (worse).
CC on the first tetrad of a free utterance sits at 35–45% on both sets, up
from 10% before the selection fix; the antithesis is a genuine position in
about 70% of first tetrads, a caricature in none. Every number is Sonnet 5,
n = 20 per set, one auditor model — screens, not results, and recorded as
such.
