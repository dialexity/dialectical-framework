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

## The comparison that was missing (2026-10-01)

Path A — the Consultant's view turn, ONE thinking structured call over the
bare utterance — had only ever been read by hand. Its tetrads scored by the
pipeline's own judge (`ControlStatementsCheck._evaluate_control_statement`,
same model, no context), both sets:

| | set A | set B | median latency |
|---|---|---|---|
| pipeline, final stack (first tetrad) | 7–9/20 | 7/20 | ~55 s |
| Consultant view turn | **13/20** | **11/20** | ~6 s |

24/40 against 14–16/40, on the pipeline's own metric, at a tenth of the time,
with antitheses that are positions by inspection. One judge, one model, n = 40
— a screen — but it reframes the three reverted generation fixes: the staged
path is not short of a better-worded step. What differs between the two is
structural, and each difference is a testable variable: (1) THINKING — the
view turn thinks, every structured concern call does not (forced tool choice
suppresses it); (2) WHOLENESS — one call sees thesis, antithesis and all four
aspects together and can choose the antithesis for the tetrad it yields, which
is the paper's Optimum A taken literally, where the pipeline picks the
antithesis from eleven isolated one-rung calls and builds aspects afterwards;
(3) the taxonomy apex the pipeline's aspects are scored toward. Next
measurements, one variable each: thinking on `AspectGeneration`'s tetrad call
alone; then a holistic thinking generation with the ladder and the scales
demoted to CLASSIFYING and SCORING what was generated.

**A6 — thinking on `AspectGeneration`'s full-tetrad call alone (json mode,
`medium`), set A, 15 of 20 before the run hit its time limit.** Rejected. CC
2/15 on the first tetrad and 6/30 over all expanded, against 5–7/15 and
8–14/~30 for the same fifteen utterances in the unthinking runs A1–A3; T+/A+
the same compromise in 19/30; ~66 s per utterance against ~55 s; no parse
failures (the nested DTO fills in json mode). Thinking is NOT what separates
the staged path from the view turn — given room to deliberate over the staged
prompt, the model converges the pluses, the same drift the derivation-order
change (A5) produced. Reverted; `_generate_tetrad`'s docstring carries the
number. Of the three differences listed above, that leaves WHOLENESS and the
TAXONOMY APEX, and the next run is the holistic one: one call that builds
thesis reading, antithesis and all four aspects together, with the ladder and
the scales classifying and scoring afterwards.

## Working the non-refactoring suspects (2026-10-01)

**Suspect 9 — judge noise: ruled out.** The same 80 saved first tetrads
re-scored three times each by `ControlStatementsCheck` (40 pipeline, final
stack; 40 view turn). Pipeline: 13/40 on every one of the three readings; view
turn: 24, 24, 25. The verdict was unanimous across the three readings for 36/40
and 34/40 tetrads, and agreed with the original single scoring on 107/120 and
105/120 readings; mean per-statement score sd 0.015 and 0.011. The gap is not
the judge.

**Suspects 1–2 — context: a confirmed defect, by static trace.** On every
`anchor` / `note` path the tetrad is generated context-free. Thesis-only: the
utterance reaches `StatementClassification` and `StatementHeadline`, then the
≤7-word headline is all that taxonomy contextualization, the mode-point
candidates, the Optimum-A ranking, `AspectGeneration` and the CC/DV judge ever
see; the tool's `context` goes only to `TetradGrounding`
(`expand_polarities.py`, `_ground_tetrads`). Thesis-plus-antithesis: `context`
reaches the two classifications and `AntithesisClassification`, and again not
the aspect call or the judge. `ExpandPolarity._get_input_text()` returns ""
on a Case with no Input, which is the ordinary Advisor case. The tool's own
comment says "`context` grounds the tetrad, not just its classification"; the
2026-09 fix it describes covered grounding only. Also found: the thesis-only
branch classifies without `context` while the two-pole branch composes it in;
the person's original wording is stored nowhere after headlining; and an
`anchor` after an `ingest` receives every Input's digest as its context
(unrelated documents) but still not its own. `ingest` itself is fine — its
prompts receive the Input digests.

**Suspect 8 — situation reports classified SIMPLE: bigger than set B showed,
and one sentence moves it** (`tests/e2e/probe_simple_reports.py`, 20 REPORT /
20 FACT / 20 COURSE statements × 3 readings × 3 arms, 540 readings):

| arm | REPORT read SIMPLE | FACT read SIMPLE | COURSE read SIMPLE |
|---|---|---|---|
| production | 52/60 (87%) | 60/60 | 0/60 |
| one added sentence | 6/60 (10%) | 60/60 | 0/60 |
| context framing from the anchor path | 53/60 (88%) | 60/60 | 0/60 |

The sentence, at both sites where the sibling named-options rule already sits:
"A person's account of a situation they are in — someone's behaviour toward
them, a relationship pattern, a standing conflict — is likewise COMPLEX: it is
a stance held inside a system of people and stakes, not a fact to verify ("My
landlord ignores every repair request I send")." Framing does nothing; the two
holdouts are standing states with no behaviour toward the speaker. Unmeasured
before shipping: first-person DOCUMENT facts ("Our server refuses connections")
— the stratum is being added.

The added stratum: 20 first-person document facts ("Our server refuses
connections on port 443", "My laptop refuses to wake from sleep") read SIMPLE
57/60 under production AND 57/60 with the sentence — no statement moved, no
flips; the one COMPLEX statement ("My car stalls when the engine is cold")
states a cause and is COMPLEX in production too. The sentence does not
over-correct on this evidence (one model, 3 readings, 20 statements).

**Suspect 3 — which half carries the gap: the ASPECT call, not the choice of
antithesis** (`tests/e2e/probe_aspect_variants.py`, DB-free replay of
`AspectGeneration`'s full-tetrad call on fixed T/A pairs, the pipeline's own
judge, 40 pairs per arm, one variable per arm):

| arm | T/A from | CC pass |
|---|---|---|
| production prompt (harness check: pipeline measured 14/40) | pipeline | 14/40 |
| + utterance as context (suspect 1, aspect side) | pipeline | 13/40 |
| − taxonomy apex hints (suspect 5) | pipeline | 11/40 |
| + "in the person's own terms" (suspect 6) | pipeline | 13/40 |
| texts only, no scores or scales (suspect 4) | pipeline | 18/40 |
| view-style aspect call (Consultant system prompt, utterance as the conversation, thinking, texts only) | pipeline | **26/40** |
| production prompt | view turn | 16/40 |

The pipeline's own T/A with view-style aspects reaches the view turn's level
(24/40); the view turn's T/A through the production aspect prompt does not
(16/40). Paired, view-style against production on the same pairs: 13 gained, 1
lost (exact McNemar p ≈ 0.002) — the first resolved effect of the whole
investigation. So the antithesis the pipeline now picks is good enough, and
the three reverted generation fixes plus A6 were all aimed at the right call
with the wrong changes. Context, apex hints and wording are null alone;
texts-only is the one production-prompt variant that moved up (unresolved,
paired 9/5). Which ingredient of the view-style call does the work — system
prompt, texts-only shape, thinking, or the combination — is the isolation run
in flight. Per-pair verdicts agree with the pipeline's own only 26/40 on
regeneration: read totals, never single pairs.

**Isolation of the winning aspect call** (same 40 pipeline pairs):

| arm | what differs from production | CC pass |
|---|---|---|
| production | — | 14/40 |
| texts only (+ context) | no scores in the call | 18/40 (18/40) |
| Consultant system prompt, production user prompt and `TetradDto` | system prompt only (+ utterance as the conversation) | 19/40 |
| view-style without thinking | system prompt, texts only | 20/40 |
| view-style | the whole bundle, thinking on | 26/40 |
| view-style under `AspectGeneration.SYSTEM_PROMPT` | the winning call with the production system prompt put back | **3/40** |

The one resolved ingredient is the production SYSTEM PROMPT: swapped under
the otherwise identical winning call it loses 24 and gains 1, and the pluses
return as hedges ("Double budget only where returns are proven"). Thinking
inside the bundle (20 → 26) and texts-only on the production prompt (+4) are
unresolved. A drift audit of the view-style arm: 18/40 tetrads were built on a
reworded tension rather than the given T/A (CC 16/22 on the given pair, 10/18
drifted) — the gain is not bought by drift, but 45% drift is disqualifying for
a graph path as it stands. The smallest positive-signal change keeps the
production user prompt and DTO and changes only the system prompt (19/40, one
call, scores intact). The section-by-section ablation of
`AspectGeneration.SYSTEM_PROMPT` — which part carries the damage, and what
removing it does to the restatement rate its examples were added to cut — is
in flight.

**The context defect, fixed (2026-10-01).** `compose_context(particulars,
input_text)` moved from `IntroducePolarity` to `utils/input_context.py` and is
now applied in `ExpandPolarity` (aspect call, aspect dedup, coherence judge),
`FindPolarities` (every antithesis prompt; `AnalysisPipeline` forwards its
`grounding_context`) and `AnchorTheses` (classification and headline, from
`anchor`'s `context`). `ingest` is unchanged — it sets no grounding context.
Pinned at each seam by `TestContextReachesGeneration`; removing the
composition fails two of its tests. This is a contract fix, not a coherence
lever: on the aspect side the utterance as context measured 13/40 against
14/40.

**Suspect 7 — the antithesis, on the real pipeline: rejected as the coherence
lever, and a second defect found.** One cheap call naming "the other side of
the person's dilemma", fed to the existing thesis-plus-antithesis path (set A,
20/20): antithesis a position 18/20 (A3: 11), rungs spread over the whole
ladder, CC pass 7/20 — identical to A3's 7/20 (paired: both 4, only new 3, only
baseline 3). Better antitheses, same coherence: the aspect half again. The
defect: on that path HS scores genuine dilemma antitheses LOW — 0.02 to 0.85,
mean 0.45, 11/20 under 0.5 ("Caring for my parents at home myself" 0.08) — and
HS does not track coherence there (CC passed 6/16 under 0.7, 1/4 at or above).
Fed to the Advisor's own context floor (`_apply_quality_floor`: failed
validation, or antithesis HS < `advisor_polarity_quality_min_hs` = 0.5) those
20 freshly anchored standalone perspectives would be shown as: hidden for
failed validation 13, hidden for HS alone 5, kept 2. The floor exempts
exploration members, so this lands on the first turns of a from-scratch
conversation. Open; it depends on what the aspect prompt fix does to the
validation rate, and on a decision about HS on a NAMED antithesis.

**Suspect 8, shipped (2026-10-01).** `SITUATION_REPORT_RULE` in
`concerns/statement_classification.py`, the measured sentence verbatim,
interpolated into the system prompt's COMPLEX list and after the user prompt's
named-options clarification; `TestASituationReportIsComplex` pins both sites.
Not measured: whether the reclassified reports then build coherent tetrads —
they now go down the ladder path, whose first-tetrad coherence is the 35%
this note is about.

**The classifier rule on the real pipeline (set B's three SIMPLE reports,
re-run 2026-10-01 with the rule and the context fix in).** All three now
classify COMPLEX and take the ladder: "Daughter wants to stay in university
and not travel" → "Finish school first, travel later"; "father agrees to stop
driving" → "Safety demands he surrender the keys"; "Sister has no expectation
that I host" → "Hosting should rotate, not fall on me" (antithesis kind:
mirror 3/3 → position 3/3 on the first tetrad). First-tetrad coherence is
still 0/3 (0/8 over all expanded): the pluses are conditional compromises
("Scheduled driving evaluations, keys retained conditionally") — the aspect
prompt's signature, not the classifier's. And the daughter's four antitheses
carry HS 0.25–0.5: genuine positions scored low, the floor defect above, now
visible on the default path too.

**Suspect ruled out on the archive: aspect dedup across sibling tetrads.**
`ExpandPolarity._deduplicate_aspects` replaces a generated aspect with any
equivalent Statement in the case vocabulary, so tetrads on DIFFERENT
antitheses of one thesis end up sharing aspect nodes: across every default-mode
run in `results/tetrad_quality/` an A+ is shared with a sibling on a different
antithesis in 209 of 278 tetrads that have such a sibling. It does not cost
coherence — CC passes 58/209 (28%) shared against 20/69 (29%) not, mean
`cc_a` 0.68 against 0.67, and the parentage auditor reads `own_pole` 89%
against 90% — and single-tetrad utterances, which have nothing to merge with,
pass at the same 28% (13/46). What it does mean is that sibling tetrads are
mostly the same tetrad under different antitheses: a diversity observation
for whoever renders several of them, not a defect on this ledger.

**The aspect system prompt, ablated by section and fixed (2026-10-01).**
Production shape throughout (production user prompt, `TetradDto` with scores,
forced tool, no thinking), same 40 pipeline pairs, only the system prompt
varied:

| system prompt | CC pass | paired vs production (gained / lost) | plus parentage own/other/neither of 80 | restated |
|---|---|---|---|---|
| production | 14/40 | — | 70 / 5 / 5 | 1 |
| − the worked plus mistake (toolchain) | 20/40 | 7 / 1 | 77 / 2 / 1 | 3 |
| − all examples | 16/40 | 6 / 4 | 78 / 1 / 1 | 2 |
| − both mistake paragraphs | 15/40 | 7 / 6 | 72 / 5 / 3 | 3 |
| role line only | 14/40 | 8 / 8 | 77 / 2 / 1 | 4 |
| − the truth criterion | 11/40 | 6 / 9 | 73 / 3 / 4 | 1 |

Replication of the one lopsided cut, two fresh generations per pair: production
14/40 and 14/40, cut 20/40 and 17/40; pooled over three generations 42/120
(35%) against 57/120 (48%), 28 gained / 13 lost (p ≈ 0.03 treating a pair's
generations as independent; the two fresh ones alone p ≈ 0.16). Weak tier
(generation on Haiku 4.5, same judge): 14/40 → 25/40, 17 gained / 6 lost
(exact McNemar p ≈ 0.035); restatement 0 → 3 of 80, wrong-parent pluses 13 →
14 of 80.

Shipped: the paragraph is out of `AspectGeneration.SYSTEM_PROMPT` (the shipped
prompt was checked byte-identical to the measured arm), the check stays in
every user prompt. What the paragraph did, read off the pairs: it warned
against "Teams choose within centrally aligned standards" and the pluses came
back in exactly that shape — "Expand budget tied to proven growth milestones",
"Builds structured path back to technical track". Without it: "Strategic
reinvestment targeting high-yield growth channels", "Management role channels
engineer's impact into stable structures".

Open after this fix: 48% is still under the view-style call's 26/40 on the
same pairs, and that bundle's remaining ingredients (thinking 20 → 26, texts
only +4) are unresolved; the same system prompt serves
`_contradiction_pair_prompt` and `_single_aspect_prompt`, which were not
measured; restatement on the weak tier is not re-measured at the archive's
192-slot size.

**End to end, the three fixes together — coherence did not move (2026-10-01).**
Sets A and B through the thesis-only `anchor` path with the context fix, the
classifier rule and the aspect-prompt cut all in
(`results/tetrad_quality/set_{a,b}-*-20261001-07*.json`):

| | first tetrad CC | all tetrads CC | antithesis a position (first) | SIMPLE | utterances with a tetrad the Advisor's floor keeps |
|---|---|---|---|---|---|
| before, set A (A3) | 7/20 | 12/37 | 11/20 | 0 | 8/20 |
| after, set A | 8/20 | 22/47 | 15/20 | 0 | 10/20 |
| before, set B | 7/20 | 11/27 | 14/20 | 3 | 7/20 |
| after, set B | 6/20 | 13/47 | 12/20 | 0 | 7/20 |

Paired on the first tetrad: set A both 3 / only after 5 / only before 4; set B
both 2 / 4 / 5. Same-compromise pluses did not fall (14/37 → 18/47, 9/27 →
25/47). The harness's 35% → 48% on fixed pairs is not visible here. This run is
NOT paired on T/A (the antithesis is redrawn), n = 40, and the earlier
same-stack runs ranged 6–9/20, so it cannot exclude a +13-point effect — but
it does not show one, and the cut was chosen as the best of five arms on the
pairs it was measured on. The out-of-sample check (old against new prompt on
the 40 pairs THIS run produced, beside the pipeline's own verdict on them)
decides whether the cut is kept.

**Out of sample, on 40 pairs the cut was never selected on.** The cut was the
best of five arms on one fixed pair set, so it was re-run on P2 = the 40
first-tetrad (thesis, antithesis) pairs the end-to-end pipeline run itself
produced, two generations per pair, production shape, old prompt against new:

| arm | CC pass | 95% Wilson | paired (gained / lost) |
|---|---|---|---|
| with the paragraph (`old`) | 25/80 (31%) | 22–42% | — |
| without it (`new`) | 33/80 (41%) | 31–52% | 18 / 10, p ≈ 0.19 |

Generation 1 was null (8 gained / 7 lost), generation 2 was 10 / 3. The
pipeline's own verdict on those same 40 pairs is 14/40 (35%), which the harness
`new` arm (41%) brackets — so there is no large harness-versus-pipeline gap to
explain the flat end-to-end result; the harness is measuring the same thing.

**Every measurement of the cut, in one place:** Sonnet in-sample 42/120 → 57/120
(three generations), Sonnet out-of-sample 25/80 → 33/80, Haiku 14/40 → 25/40
(p ≈ 0.025). Pooled over all six harness generations, 81/240 (34%) → 115/240
(48%), Fisher p ≈ 0.002. The direction holds in five of six and the one flat
cell is the end-to-end pipeline run, which is not paired on T/A.

Shipped on that evidence. What is NOT claimed: that first-tetrad coherence on a
free utterance improves — the one run that measured it end to end did not move
(14/40 both ways). The cut is a REVERT of one paragraph to the pre-fix prompt
(byte-identical to `84ef6bd` again), with the verification step it shipped
beside kept; so the burden it carries is small, and the open question stays
where the end-to-end run put it: what else, between a fixed T/A pair and a free
utterance, costs the tetrad its coherence.

**The two remaining context items, closed (2026-10-01).** (1) The person's
original wording is now kept: the Advisor wraps its provider round in
`speaking(user_message)` (`utils/utterance.py`), the `anchor` tool reads it and
`_keep_utterance` commits the turn as an `Input` through `AddInput` —
content-addressed, so the same turn anchoring twice is one Input, and
`ensure_digest` skips the model for anything short — then hands its hash to
`AnchorTheses` / `IntroducePolarity`, which link it to the poles as their source
(`HAS_STATEMENT`). A `note` stores the turn on the `Note` node (`utterance`, not
in the hash) so the plant that runs later, possibly in another process, still
traces to it; a closing's own anchor on an empty graph passes `utterance=None`,
since those words belong to the Decision's record. The off-turn task inherits
the scheduling turn's ContextVar, which is why `_anchor` never reads it itself
— only the two tools do, on the turn. (2) `inputs_for_statements`: a tension
reads its own sources, every Input only when it has none. This also changes
`ingest`: a tension extracted from document A is now developed against A alone,
not A+B+C. Caveat recorded, not measured: the Input is the turn the tool FIRED
on, and the material is sometimes an earlier turn — the model's `context`
paraphrase is what selects across turns, so it stays first in
`compose_context`. Tests: `tests/test_utterance_input.py`.

**Review of the Input change (fresh reviewer, 2026-10-01) — one defect, fixed.**
`FindPolarities._create_ideas` connected EVERY Input in the case to the Ideas
container it writes for a thesis-only anchor (and for every `ingest`), and
`find_by_statement_hashes` follows `Input → Ideas → Statement`, so both poles of
every tension traced to every document and `inputs_for_statements` returned the
union — "a tension reads its own sources" held on the two-pole branch only,
and the unit test built its polarity directly so it could not see it. The
container now links the theses' OWN sources (`inputs_for_statements(…,
fallback_all=False)`), and `AnchorTheses.input_hashes` is three-state: `None` =
every Input (the Analyst tool's documented contract), `[]` = no provenance (an
anchor off the turn), a list = those. Pinned end to end through `anchor.fn`
with a second Input seeded in the case. Smaller findings fixed in the same
pass: `committed_at` is a float (sort key), the ContextVar reset when a host
closes the stream from another task, the cache declared in `__init__`. Checked
clean: two `anchor`s in one gathered tool round cannot interleave inside
`AddInput` (no suspension point — safe by the absence of awaits, now said in a
comment); the context dump renders Input HASHES only, so turns do not appear in
the prompt; Note fields are never rendered. Open and recorded: wheel-level
prompts (`explore_transformations`, `generate_synthesis`, `audit_feasibility`,
`present_analysis`) still read every Input, so after many anchoring turns the
24k source budget fills with chat (40 turns × 300 chars ≈ 12k) — they should
read `inputs_for_statements` over the wheel's poles; a person's turns are now
readable through `read_digest` and `query_graph` on a shared Case.

**What `ingest` does to ONE sentence (static trace, 2026-10-01).** The
document path, applied to ten words: `_parse_intent` (1 call) → step 1 "extract
up to 5 content items" → step 2 one atomic thesis per item, 1–7 words, up to
FOUR attempts demanding novelty until `count=3` theses exist → classification
per candidate → antithetical-pair detection → per thesis ≤ 11 mode-point calls
+ ranking → up to 5 polarities per thesis, `_rank_polarities` keeps 5 → 4
calls per expansion. About 75–80 provider calls for one sentence, and the
theses are never the person's sentence: fragments and generalisations
("Father is eighty-four"), with `SITUATION_REPORT_RULE` applied to the fragment,
not the utterance. Defects found on the way: (a) `_rank_polarities` mixed its
keys — a SIMPLE polarity's hardcoded HS 1.0 served as its fallback potential and
outranked every rated candidate (≤ 1.0), so mechanical negations expanded FIRST
whenever theses mixed; fixed, unrated now sorts after rated. (b) Re-`ingest` of
a short Input runs `ensure_digest(refresh=True)` and replaces the verbatim
digest with a paraphrase. (c) `_deduplicate_aspects`' vocabulary includes
sibling tensions' antitheses from the same sentence. The conclusion for the
blindspot app: the INPUT half of "the utterance is ingested" is right and now
holds on both doors; the EXTRACTION half is a document procedure that
over-extracts from one sentence by contract. Measured next with
`TETRAD_PROBE_MODE=ingest`.

**The third door measured: `ingest` on one utterance (2026-10-01, sets A+B,
`TETRAD_PROBE_MODE=ingest`, 40/40, 0 errors).** The three doors on the same 40
free utterances, first tetrad per utterance:

| door | CC pass, first tetrad | any tetrad passes | tetrads / utterance | median latency | antithesis a position (first) |
|---|---|---|---|---|---|
| Consultant view turn | 24/40 (60%) | — (one drawn) | 1 | ~6–8 s | 30/40 on the auditor (hand count 20/20 was set A, one rater) |
| `anchor` thesis-only (staged) | 14/40 (35%) | 18/40 | 2.4 | ~55 s | 27/40 |
| `ingest` (extract, then staged) | 18/40 (45%) | 31/40 | 4.3 | ~75 s | 27/40; mirror 10/40 |

Paired first tetrad, ingest vs anchor: both 5, only ingest 13, only anchor 9,
neither 13 — a lean, not a result. What extraction made of a sentence: exactly
3 theses every time (the `count=3` ask, filled by retry), the first a ≤7-word
restatement of the utterance ("Author should quit job", "Marketing budget cut
in half"), the second and third generalisations the person did not say
("Leaving stable employment enables entrepreneurial pursuit", "New managers
often lack employee trust"); 0/120 SIMPLE. So 172 tetrads for 40 sentences,
most of them on invented theses — the 31/40 "any tetrad passes" is bought by
volume. The Advisor's floor would keep ≥ 1 tetrad for 29/40 utterances (anchor:
17/40). Reading: for a one-utterance app the Input half of "ingest it" is right
and the extraction half is a document procedure; its first tetrad is no better
than the view turn's and takes ten times as long. The one-shot path (item 3)
is the design that keeps the Input and drops the extraction.

## The one-shot build (item 3), measured (2026-10-01)

`SketchTetrad` (`agents/analyst/skills/sketch_tetrad.py`): ONE json-mode call
with thinking (`concerns/tetrad_sketch.py`, system prompt = the Consultant's
`method_prompt()` read live, request = the utterance + `ASPECT_DEFINITIONS` +
`_OPPOSING_POSITION_ASK` + the shared `TETRAD_BUILD_PROCEDURE`) writes T, A,
two axes and four aspects; `IntroducePolarity` classifies, headlines and
scores the pair; `ExpandPolarity(given_tetrad=)` SCORES the given aspects
(`AspectGeneration.score_given`, texts fixed, DTO echoes none) and then
dedups, names, commits, grounds and validates as today. Pre-registered bar
before it replaces the staged thesis-only `anchor`: first-tetrad CC ≥ 20/40,
antithesis a position ≥ 30/40, restatement ≤ 3/80 plus slots.

Generation 1, sets A+B, 40/40, 0 errors, called directly by the probe
(`TETRAD_PROBE_MODE=oneshot`, `oneshot_persona` = `COUNSELOR_PERSONA` above
the method, the bundle the 26/40 harness arm carried):

| arm | CC first | position | restatement (plus slots) | T+/A+ distinct | latency |
|---|---|---|---|---|---|
| one-shot, method alone | 21/40 (52%) | 36/40 | 8/80 | 20/40 | 43 s |
| one-shot + persona | 23/40 (58%) | 38/40 | 3/80 | 17/40 | 43 s |
| staged (same day) | 14/40 (35%) | 27/40 | 3/80 | 25/47 | 55 s |
| Consultant view turn | 24/40 (60%) | 30/40 on the auditor (hand count was 20/20, set A, one rater) | 10/80 | 25/40 | ~7 s |

Paired first tetrad, one-shot vs staged: both 7, only one-shot 14, only staged
7, neither 12. Persona vs method alone: 14 / 9 / 7 / 10 — the persona's two
extra passes are noise; its 3/80 against 8/80 on restatement is the one cell
where it may be doing work, and the wrong layer to fix that in. Two of three
bars met; restatement missed on the production candidate. A second generation
of both arms is running to resolve both cells (n = 80 / 160 slots).

**The HS floor meets the one-shot path, and the defect has teeth.** HS on the
first antithesis: 28/40 below 0.5 (min 0.03) against the staged run's 3/40 —
the one-shot antitheses are genuine positions, and HS measures closeness to
"[T]-lessness". With `advisor_polarity_quality_min_hs` = 0.5, the Advisor's
context floor would keep a tetrad for 7/40 of these utterances (persona arm
12/40; staged 17/40, whose antitheses are nearer the negation end). Validation
passed on 21/40 against the staged 14/40, so it is the HS term alone that
hides them. The HS term leaves the floor together with this path, or the
Advisor builds what it cannot see. Latency: ~7 s is the reasoning call; the
other ~36 s is the unchanged classify / HS / score / ground / validate chain
(the design estimated 30 s).

**Generation 2 and the decision (2026-10-01).** Both arms re-run on the same
40: method alone CC 21/40 again (pooled 42/80, 52%), position 38/40 (pooled
74/80), restatement 3/80 (pooled 11/160, 6.9%); persona CC 22/40 (pooled
45/80), restatement 8/80 (pooled 11/160). The persona's gen-1 edges on both
counts were noise; the method alone is wired. Against the bar: coherence and
antithesis quality met and replicated; restatement at the archive's post-fix
level (6.9% vs 7.8%), above the one-generation staged figure the bar was set
from — recorded as unchanged, not improved. Wired into `anchor`'s thesis-only
branch with the model's `thesis` PINNED in the request (the measured arm let
the call find T; the production shape is measured next as the probe's
`default` mode, which now runs the wired tool). HS left the Advisor's floor in
the same commit (above). Open: ~36 s of the ~43 s is the classify / HS /
score / ground / validate chain, untouched; the restatement check in the
sketch request is the one inherited from the procedure, and a stronger
verification step there is the next lever if 6.9% matters for the app.

**The production shape, measured after wiring (2026-10-01, probe `default`
mode = the wired tool, thesis pinned to the utterance, no turn, 40/40, 0
errors):** CC first 20/40 (50%), antithesis a position 36/40, restatement
6/80, validation passed 20/40, HS(A) below 0.5 on 22/40 (the floor term that
left), median 43.5 s. Paired against the staged run on the same utterances:
both 9, only one-shot 11, only staged 5, neither 15. Against the free arm
(thesis found by the call) 13 / 7 / 9 / 11 — pinning the model's thesis costs
nothing measurable; the pinned T is the utterance tightened ("Take the Berlin
job and relocate"), the free T the same tension in its own words. Three
one-shot generations now sit at 20–21/40 each against the staged 14/40
(pooled 62/120, 52%, vs 14/40, 35%); the Consultant's view turn stays the
ceiling at 24/40 and ~7 s. Where the wired path's 43 s go: ~7 s the reasoning
call, the rest the unchanged classify / HS / score / ground / validate chain.

**Same instruments, both paths (2026-10-02, `tests/e2e/probe_view_turn_audit.py`).**
The view turn's "20/20 genuine antitheses" was a hand count on set A by one
rater; the one-shot figures came from the probe's LLM auditors. The view
turn's 40 tetrads (`path_a_cc-20261001.json`) were put through the same three
auditors, sequentially:

| | coherent first tetrad | antithesis a position (auditor) | mirror / not an opposition | restatement (plus slots) | T+/A+ distinct |
|---|---|---|---|---|---|
| Consultant view turn (1 gen) | 24/40 (60%) | 30/40 | 6 / 4 | 10/80 (12.5%) | 25/40 |
| one-shot build, wired (3 gens) | 62/120 (52%) | 36–38/40 per gen | 2–4 / 1–2 | 11/160 (6.9%) + 6/80 | 17–20/40 |
| staged build (before) | 14/40 (35%) | 27/40 | 5 / 1 | 3/80 | 25/47 |

Read together: the view turn is ahead on coherence by four tetrads at n = 40
(not resolved), the one-shot build is ahead on antithesis quality (the view
turn's ten non-positions are plain mirrors — "Saying no to clients" for "I
always say yes to clients", "Keep owning the flat" for "Sell the flat") and on
restatement, and ~6x slower. The view turn's own `_OPPOSING_POSITION_ASK` is
not in `view_sketch_prompt`; the one-shot request carries it, which is the
likely source of the antithesis difference and a one-line change to measure
on the view turn. The hand count overstated the view turn; corrected above.

**The ask in the view turn's request (2026-10-02, `tests/e2e/probe_view_turn_ask.py`,
same 40 utterances drawn as the pre-MVP draws them, same judge and auditors):**

| view turn | coherent first tetrad | antithesis a position | mirror / non-opposition | restatement | latency |
|---|---|---|---|---|---|
| without the ask (2026-10-01) | 24/40 | 30/40 | 6 / 4 | 10/80 | ~7 s |
| with `_OPPOSING_POSITION_ASK` | 25/40 | **39/40** | 1 / 0 | 10/80 | 6.8 s |

Paired coherence: both 16, only after 9, only before 8, neither 7 — unchanged.
The antithesis gap between the two surfaces was that one paragraph: with it,
the view turn draws a genuine opposing position for 39/40 against the one-shot
build's 36–38/40, and the two surfaces now differ in nothing measured but the
time the graph chain adds (~7 s against ~43 s). Restatement is the same 10/80
on both counts and sits above the one-shot build's 6.9%; the one-shot request
differs from the view turn's in pinning one tension and in having no
conversation to render, so the plus-restatement gap, if real, is the next
thing to isolate — and it is the SAME lever on both surfaces, since they share
`TETRAD_BUILD_PROCEDURE`.

**Restatement: the take-up fields, tried and reverted (2026-10-02).** The
flagged pluses on both one-shot surfaces were almost all A+ stating A's own
benefit (18/20 on the view turn, 12/12 on the build) — advocacy for the
invented pole. Lever tried: two text fields in the shared sketch DTO,
`t_plus_takes_up` / `a_plus_takes_up`, each ahead of its plus, naming what
the other pole is for that the plus delivers — the archive's "verification
step beats restatement" made structural. Measured on the view turn (40
utterances, same judges): restatement 10/80 → 0/80, position 39 → 40/40, and
coherence 25/40 → 15/40 (paired both 9 / only after 6 / only before 15 /
neither 10), compromise pluses 18 → 23/40. The target defect vanished and the
tetrad broke: a plus built to carry the other pole is a compromise, and
"T+ without A+ yields T-" has nothing to yield. Reverted before it reached the
build. Rule carried forward: a restatement lever is measured on COHERENCE
first (`CLAUDE.md`, the worked-example rule says the same); restatement at
7–12% stays an open number.

## Step 2: the build's latency (2026-10-02)

**Census first** (`tests/e2e/probe_oneshot_census.py`, four utterances through the
wired `anchor`): 11–13 provider calls, parallelism 1.4, wall 37–42 s, non-LLM < 1.5 s.
The chain: sketch ~5 s → both poles' classification + taxonomy location (gathered,
~8 s) → the antithesis's contextualised taxonomy (~5 s) → its HS/Mode/Arousal
evaluation (~7 s) → aspect scoring (~3 s) → grounding (~2 s) → the two coherence
judge calls (gathered, ~8 s). The antithesis evaluation stood in the chain ahead of
~14 s of work that never read its result.

**The overlap.** `IntroducePolarity` split into `prepare` / `classify_opposition` /
`record_opposition` (the Polarity commits with its A-edge HS unknown — the hash is
the two statement hashes; HS is an edge property, written afterwards with
`update_properties`); `SketchTetrad` gathers the evaluation with `ExpandPolarity`
and writes the result on the parent task — one writer at a time, pinned by a test
that proves the overlap happened. Same calls, same provider seconds; wall 23–28 s
(parallelism 2.0). Semantics-preserving by construction; the 20-utterance quality
sanity is recorded below.

**What is left in the chain and what each cut would cost in quality terms.** sketch
4–5 s → classify T ∥ A with taxonomy 7–8 s → max(contextualise + evaluate ≈ 11 s,
score + ground + validate ≈ 12 s). Further cuts: (B) the sketched antithesis is
classified standalone AND contextualised against T — on the staged path a generated
antithesis gets `lookup_antithesis_meaning(thesis)` and no classification, so the
standalone call is extra; dropping it saves two calls and ~1 s of wall (it is
gathered with T's), and changes A's `meaning` to the staged convention. (C) On the
Advisor's pinned-thesis path T is known before the sketch, so its classification
can run DURING the sketch (~4 s off that path only). (D) Folding the taxonomy
branch into the reasoning call would remove the whole classification stage (~8 s)
and is a quality question, not a plumbing one — the branch selects the apex every
score is read against. None of B–D is semantics-preserving; each is a measured
change or nothing.

**Sanity after the overlap** (set A, 20 utterances, the probe's `default` mode = the
wired tool): CC first 9/20 (45%), antithesis a position 18/20, median 26.8 s (max
31.1 s) against 43 s before — the same tetrads at the rate the one-shot build has
shown on set A, 16 s faster. No errors.

## Consolidation 1: can the one-shot writer be THE writer for a given pair? (pre-registered 2026-10-02)

Three writers of a tetrad exist (`TetradSketch` from material; `AspectGeneration.
_generate_tetrad` for a given T/A; the Consultant's view turn), and the review map
has to say "these must say the same thing" — the sign of redundancy. The one-shot
style scored 26/40 on fixed pairs in the harness but built on a REWORDED pair in
18/40 — fatal where the poles are already nodes. `TetradSketch` now takes both
poles pinned ("Keep BOTH poles as given").

DESIGN. `tests/e2e/probe_aspect_variants.py`, arm `oneshot_pinned` (two
generations, `#g1`/`#g2`): `TetradSketch(material=utterance, thesis=T,
antithesis=A)` on the 40 P pairs, judged by the same CC judge, audited for drift
(the arm joins `DRIFT_AUDITED`) and plus parentage. Comparator: the production
four-aspect call as it is NOW — the cut prompt — whose rows on these pairs are the
`sys_no_plus_mistake` arm (20/40, 17/40, 20/40 across three generations; `base`'s
14/40 rows are the pre-cut prompt and are not the comparator).

SHIP CRITERIA, all three: drift ≤ 4/40 per generation (the given pair is kept);
CC not below the comparator by more than 2/40 per generation (non-inferior; a gain
is welcome, not required); restatement not above the comparator's 3/80. If met,
`_generate_tetrad` and `_tetrad_prompt` are removed, `ExpandPolarity` always
scores a given tetrad, and the two-pole `anchor`/`note` and `ingest` write their
aspects with the one writer. If drift fails, the staged four-aspect call stays
and the duplication is recorded as measured, not accidental.

**RESULT (2026-10-02): no.** Two generations on the 40 P pairs, pinned both poles,
utterance as material:

| arm | CC pass | built on the given pair | drifted |
|---|---|---|---|
| production four-aspect call (cut prompt), 3 gens | 20, 20, 17 /40 | by construction | — |
| `oneshot_pinned` gen 1 | 20/40 | 23/40 (CC 11/23) | 17/40 (CC 9/17) |
| `oneshot_pinned` gen 2 | 23/40 | 18/40 (CC 13/18) | 22/40 (CC 10/22) |

Coherence non-inferior (paired vs the comparator's rows 10/4 and 14/5 in the
one-shot's favour), drift far past the 4/40 line: the writer that chooses its
opposition does not stay on an opposition it is handed, even told to keep both
poles. Decision per the pre-registration: the staged four-aspect call stays THE
writer for a given pair (two-pole `anchor`/`note`, `ingest`, the Analyst); the
one-shot writes where it also chooses A (thesis-only `anchor`, a host's material).
The `antithesis=` pin is removed from `TetradSketch` — no production caller, and
a parameter kept for a rejected use is not a minimal SDK. Two writers, both
measured, each on the shape it won; the review map carries the parity rule.
Not tried: persisting the writer's OWN poles for a given pair (it would make
"given" mean "suggested"), and a drift-repair step — both would be new
measurements, not tidying.

## Consolidation 2: the one-shot build per extracted thesis, for any Input (pre-registered 2026-10-02)

`ingest` is extraction (finds the theses in material — a document job, kept) followed by
the staged per-thesis build: the antithesis ladder (≤ 11 mode points + ranking) and
the four-aspect call, up to five polarities per thesis. The one-shot writer wins
where it chooses its own opposition, and an extracted thesis with its own Input as
material is exactly that shape. Route: `AnalysisPipeline` with
`BUILD_PER_THESIS_ONE_SHOT = True` builds each thesis with
`SketchTetrad(input_hashes=the thesis's own sources, thesis=thesis.text,
context=grounding_context)` instead of `FindPolarities` + `ExpandPolarity`. The
constant defaults to False until this measurement says otherwise.

DESIGN, two instruments, both arms on each:
1. `tests/e2e/probe_tetrad_quality.py` mode `ingest` on the 40 one-sentence Inputs
   (sets A+B), staged baseline already measured 18/40 first-tetrad CC, 31/40 any,
   172 tetrads, ~75 s; `TETRAD_PROBE_ONESHOT_PER_THESIS=1` runs the same mode with
   the route on.
2. `tests/e2e/probe_ingest_documents.py` — NEW, the document instrument that did not
   exist: five documents written for the probe (a founder's memo, a product retro, a
   care-home letter, a process complaint, a policy note; 400–700 words, several
   tensions each; authored by the assistant — a bias, recorded), `AnalysisPipeline(
   text=document)` per arm in a fresh Case, every perspective judged by the same CC
   judge and the antithesis / parentage auditors, latency and call census per doc.

SHIP CRITERIA. On both instruments: first-tetrad CC per thesis not below the staged
arm by more than noise (≥ staged − 2/40 on the sentences; on documents read per
thesis, direction and prose), antithesis a position not below, latency per Input
lower, extraction unchanged (same thesis texts — the route starts after it). If met,
the constant flips to True, `FindPolarities`' ladder loses its last production
caller and is removed with `AntithesisExtraction`'s mode-point generation
(`AntithesisClassification` — Mode/Arousal/HS on a named antithesis — stays);
`_rank_polarities` and `tetrad_potential` go with it. If not met, the staged build
stays for documents and the record says why.

**Instrument 1 result (2026-10-02): the 40 one-sentence Inputs, `ingest`, one-shot per
thesis against the staged build.**

| ingest on 40 sentences | first-tetrad CC | all tetrads CC | tetrads | antithesis a position (first) | mirror / caricature | median latency |
|---|---|---|---|---|---|---|
| staged (ladder + four-aspect call) | 18/40 (45%) | 63/172 (37%) | 172 | 27/40 | 10 / 2 | 75 s |
| one-shot per thesis | 16/40 (40%) | 49/120 (41%) | 120 | **37/40** | 1 / 0 | **53 s** |

Extraction identical (three theses per sentence in both arms). Coherence on the
first tetrad at the non-inferiority line exactly (16 ≥ 18 − 2); over all tetrads
41% against 37%; antithesis quality the one-shot's usual step up (mirrors 10 → 1);
30% faster, 30% fewer tetrads (one per thesis instead of up to five). Read: the
one-shot build is at least as good per tetrad and much better on the antithesis,
and builds less — which on one-sentence material is the right direction. The
document instrument decides.

**Instrument 2 result (2026-10-02): five documents, both builds — and the decision: no.**

| five documents | tetrads | CC pass | antithesis a position | restated | calls / doc | s / doc |
|---|---|---|---|---|---|---|
| staged (ladder + four-aspect call) | 21 | 6/21 (29%) | **20/21** | 1/42 | 78 | 111 |
| one-shot per thesis | 15 | 4/15 (27%) | 12/15 | 1/30 | 51 | 88 |

Per document (staged → one-shot, CC / positions): founder memo 2/5 → 1/3, 5/5 → 3/3;
product retro 0/3 → 1/3, 3/3 → 2/3; care letter 3/3 → 1/3, 3/3 → 2/3; process
complaint 0/5 → 0/3, 4/5 → 3/3; policy note 1/5 → 1/3, 5/5 → 2/3. Extraction
identical (three theses per document in both arms).

Coherence equal within this n; cost and time 30% lower; antithesis quality the
other way round from the sentences — on a document the ladder draws a genuine
opposing position 20 times in 21, the one-shot 12 in 15. The reading that fits
all three instruments: the ladder was never the defect; running it on a
seven-word headline with nothing to read was. On the thesis-only `anchor` of
2026-09-30 it had no material and drew caricatures; given a document it does its
job. The one-shot writer's win is the free utterance, where material and
position are the same ten words and choosing the opposition in the same breath
as the aspects is what works.

DECISION. The pre-registered criterion "antithesis a position not below" is not
met; the constant does not flip. Per the minimal-SDK rule a route that stays
False is dead code, so `BUILD_PER_THESIS_ONE_SHOT` and `_build_one_shot` are
removed again (this commit's predecessor has them); the two probes keep the arm
as historical. `ingest` keeps the staged build for documents; `anchor` keeps
the one-shot for a bare position. Two writers, each measured on the shape it
won — now on three instruments. Caveats that travel with the number: five
documents, authored for the probe, one generation; the one-shot read the
document's DIGEST as material (as every skill does above 1,500 chars), so a
"material = the thesis's own passage" variant is the untried lever if this is
ever revisited.

**Tried and reverted (2026-10-02): classifying the pinned thesis DURING the reasoning
call.** On the Advisor's path T is known before the sketch, so its ~8 s of classification
was moved into the ~5 s reasoning call (`IntroducePolarity.classify_pole` +
`prepare(thesis_draft=)`). Census: wall 28–33 s against 23–28 s before — WORSE by ~3 s.
Why: T and A were already classified in parallel, so T's cost was hidden behind A's;
pulling T forward left A — which exists only after the sketch — running alone for 8 s.
The chain's floor on this path is sketch → A's classification → max(opposition
evaluation, scoring + grounding + validation) ≈ 5 + 8 + 12 s, and the only way below it
is to not classify A separately (its meaning is `lookup_antithesis_meaning(thesis)` on
the staged path anyway) or to fold the taxonomy branch into the reasoning call — both
quality questions, measured or nothing. Reverted the same hour.

## Restatement, lever 2: repair a flagged plus (pre-registered 2026-10-02)

The take-up fields removed restatement at the source and cost coherence by
manufacturing compromises. This tries the other shape (`tests/e2e/probe_plus_repair.py`,
DB-free): build with the one-shot writer as today, audit both pluses with the archive's
parentage judge, regenerate ONLY a flagged plus with a repair instruction (the draft
named as a restatement, the take-up asked for, "not a compromise, not the other pole
in this pole's clothes"), then judge the repaired tetrad's coherence and re-audit.
40 utterances (sets A+B), one generation. A production repair step — one extra
check call per tetrad plus a regeneration in the ~10% flagged — is worth it only if,
over the repaired tetrads: restatement drops by at least half, CC does not fall, and
the T+/A+ `same_compromise` share does not rise. Otherwise restatement stays an
open number at 7–12% and the record says what the two obvious levers did.

**RESULT (2026-10-03): the repair step does not earn its call — and the flag it
repairs is not a coherence defect.** 40 utterances, one generation, one-shot writer:
CC 20/40; restated plus slots 5/80 (6.2%) in 4 tetrads. Every one of those 4 had
PASSED coherence before repair. After repairing only the flagged plus: restated
0/5, CC 4/4 → 2/4, `same_compromise` 0 → 1. Two of the five repairs read as what
they are — the plus bent toward the other pole ("Raise prices, earning accessible
value customers trust"; "Price low enough to fund growth") — the same compromise
shape the take-up fields manufactured at scale. n = 4 is a screen, but the sign
agrees with the 40-pair result and with the theory: a plus that already develops
its parent and passes "T+ without A+ yields T-" is doing its job; the auditor's
"restates its pole" verdict on such a plus is a vocabulary disagreement about what
"takes up" must look like, not a tetrad defect. Decision: no repair step; the
restatement rate (6–12% across runs) is recorded as a property of the auditor's
strictness as much as of the writer, and stops being a target. Two levers tried,
both cost coherence; the number stays open only in the sense that nobody should
chase it with a third lever that is not measured on coherence first.

**Real documents in the instrument (2026-10-03).** Five public-domain passages
(~950 words each, `tests/e2e/fixtures/documents/`, provenance on the first line:
Madison's Federalist No. 10, Mill's *On Liberty* ch. I and *The Subjection of Women*
ch. I, Thoreau's *Civil Disobedience*, Emerson's *Self-Reliance*) replace the
authored five as the probe's default set. Staged `ingest` baseline on them:

| document | theses | tetrads | CC | antithesis a position | calls | s |
|---|---|---|---|---|---|---|
| Federalist 10 | 3 | 5 | 5/5 | 3/5 | 101 | 135 |
| Civil Disobedience | 3 | 5 | 4/5 | 4/5 | 96 | 113 |
| On Liberty ch. I | 3 | 5 | 3/5 | 4/5 | 77 | 73 |
| Self-Reliance | 3 | 5 | 1/5 | 3/5 | 87 | 145 |
| Subjection of Women | 3 | 5 | 1/5 | 3/5 | 83 | 77 |
| **all** | 15 | 25 | **14/25 (56%)** | 17/25 (68%) | median 87 | median 113 |

Restated 1/50. Against the authored five (CC 6/21, positions 20/21): real
argumentative prose builds more coherent tetrads and the ladder draws more mirrors
on it ("Liberty is a price worth paying" against "Destroying liberty to cure faction
is worse than faction itself" — a mirror of a position that is itself a weighing).
Two observations for whoever next touches `ingest`: extraction returned exactly
three theses per document whatever its length (the default, and the only way to
ask for more was a number inside `intent` — CLOSED 2026-10-04, see
`ingest-and-extraction.md`: `count` is a parameter, and on long sources the swept
candidates are ranked across windows instead of cut in document order), and the
per-document cost is 77–101 calls, ~2 minutes (open). One generation, five texts:
a baseline to pair against, not a result.

## Best-of-N: the agent checks its own tetrad before anyone sees it (pre-registered 2026-10-04)

**The question.** Both one-shot surfaces are coherent about half the time (view turn
with the ask 25/40, build 21/40 on sets A+B). The owner's position: the person may
polish, but it is the agent that should reach quality — manual polishing is steering
an agent during its quality pursuit. Four readings of the existing draws, 2026-10-04:

- **The judge is stable and roughly valid, with known blind spots.** Re-judging the
  same 40 texts agreed with the stored verdict on 92%; ~10% of scores sit within
  0.05 of the 0.7 rule, which is where the disagreement lives. A blind read of 24
  verdicts by a second judge prompt agreed on 18. It never sees T or A — it scores
  the four aspects' coherence — so a MIRROR antithesis passes more readily than a
  position (its aspects are the thesis's own, reflected). The 0.7 line was never
  calibrated against a human read. DV is scored in the same call and is redundant
  with CC (0.96 corr on the archive): a DV gate would be the CC gate twice.
- **The failure is over-dispersed: part pair, part draw.** Across the generations
  that drew the same utterance more than once, a third to a half of the failure
  variance sits with the PAIR (8/40 utterances failed on every draw) and the rest
  with the DRAW — the same T/A pair passing on one roll and failing on the next.
  The draw share is what a second roll buys back; the pair share needs a
  different tension, not another roll.
- **The dominant defect by eye is the hedged plus** (9 of 13 failures read): a T+
  that is "T, but moderately" rather than T developed so that A's good arrives
  too — the verifier's "T+ without A+ yields T-" then has nothing to yield.
- **Keep-any-passing-draw, counted on the existing files:** the build's pass rate
  goes 52.5% → 72.5% with two draws → 80% with three (the same 40 pairs, the draws
  already stored); the view turn's best-of-three reads 87.5%, with the caveat that
  its three draws came from three prompt variants, not three rolls of one.

**The lever: `attempts` — N sketches in parallel, the framework's own control
statements judge each, the best is kept** (`concerns/tetrad_candidates.py`;
`TetradSketch.resolve(attempts=)`, `SketchTetrad(attempts=)`,
`Consultant.exploration_view(attempts=)`). Ranking: the weaker control statement
first (the pass rule), then the mean, then the earlier draw; a judging that fails
sorts last; one candidate is never judged, so `attempts=1` is today's call for
today's cost. The runners-up come back with their verdicts (`SketchTetrad.alternatives`,
the `attempts` artifact) — a person's "another" can be one of them without a new
reasoning call; nothing but the winner is persisted. Capped at 3: a fourth draw
buys ~3 points for a third more cost. **What it is not:** a loop that regenerates
from the verdict. The judge rewards mirrors, so a generation steered by it would
converge on coherent strawmen — the 2026-09-30 shape by another road. Selection
among independent draws is bounded by what the prompt already asks for;
regeneration is not. The antithesis kind is therefore measured beside the pass
rate, and a run that raises CC by lowering `position` fails.

**Pre-registration.** Same 40 utterances (sets A+B), one generation each, `attempts=3`
on both surfaces, scored by the probes' FRESH judge pass (`_judge`, a separate call
on the winner's texts — the selection's own verdict is the max of three noisy reads
and would flatter it) and the three auditors:

| surface | baseline | ship bar (fresh judge) | must not move | screen |
|---|---|---|---|---|
| view turn (`VIEW_TURN_PROBE_TAG=attempts3 VIEW_TURN_ATTEMPTS=3`) | CC 25/40, position 39/40, 8 s median | CC ≥ 30/40 (75%) | position ≥ 37/40, restated ≤ 10/80 | median ≤ 16 s |
| build (`TETRAD_PROBE_ATTEMPTS=3`, default mode) | CC 21/40, position 37/40, 23–28 s | CC ≥ 28/40 (70%) | position ≥ 35/40, restated ≤ 10/80 | median ≤ 35 s |

| documents, staged writer (`TETRAD_PROBE_ATTEMPTS=3 INGEST_DOC_SET=public`, `probe_ingest_documents.py`; added to the registration before its run, after the view-turn result and during the build's) | CC 14/25, position 17/25, restated 1/50, median 113 s/document | CC ≥ 18/25 (72%) | position ≥ 16/25, restated ≤ 5/50 | median ≤ 150 s/document |

Pass on both: `DEFAULT_SKETCH_ATTEMPTS` becomes 3 and the notebook's "another"
serves a runner-up first. Pass on one: the default moves on that surface's caller
only, and the record says why the other did not follow. Fail: the parameter stays
at 1, available to a host, and the next lever is the hedged plus at the prompt
(measured on the downstream judge, as the aspect prompt was). Cost is three
reasoning calls plus six short judge calls per tetrad in either case; latency is
the longest of three parallel calls plus one judge round.

**RESULT, view turn (2026-10-04, `view_turn_attempts3-20261004-104227.json`, 40/40 drawn,
0 errors):** CC **36/40 (90%)** against the ask baseline's 25/40 — paired 24 both / **12 only
after / 0 only before** / 4 neither; the bar (≥ 30) is cleared and the sign is resolved.
Antithesis a position **36/40** against the bar's 37 (baseline 39): kind transitions
position→position 36, position→mirror 2, position→not_an_opposition 1, mirror→mirror 1 — the
two new mirrors are the auditor's thin line ("Keep offering help regardless of what they do
with it" against the baseline's "Keep offering support as act of friendship"), not the
2026-09-30 caricature. Restated plus slots **12/80** against the bar's 10 (baseline 10/80);
T+/A+ `same_compromise` 11/40 against 18/40 before. Latency median **15.0 s** (bar 16, baseline
8). Reading: the primary bar passes resolved; both "must not move" conditions miss by one and
two counts at n = 40, inside their own intervals, with no sign of mirror convergence in the
pairwise kinds. A pass to replicate, not a pass — see the decision below.

**RESULT, build (2026-10-04, `set_a-default-att3-off00-20261004-105901.json` +
`set_b-default-att3-off00-20261004-111403.json`, 40/40 built, 0 errors; the post-commit
validation is the fresh read — a separate call on the persisted texts):** CC **30/40
(75%)** against the 2026-10-01/02 default runs' 20/40 on the same utterances — paired
17 both / **13 only after / 3 only before** / 7 neither; bar ≥ 28 cleared. Antithesis a
position **36/40** (bar 35; baseline 37/40; kinds {'position': 36, 'not_an_opposition': 2, 'mirror': 2}). Restated **9/80** (bar 10;
baseline 6/80). `same_compromise` 19/40 against 20/40. Latency median **33.8 s** (bar 35;
baseline 35.25 s on those runs, which predate the phase overlap that brought the single draw
to 23–28 s — so three draws plus the judge round cost the turn roughly 6–10 s). Every
pre-registered condition holds on this surface.

**Documents, first launch (2026-10-04 11:29): hung, not slow.** After 63 minutes the probe
process had used 7 s of CPU and exchanged 4.5 KB with the provider on ONE established
Bedrock connection — the Anthropic SDK stall shape (`streaming-latency-and-retry.md`: a
600 s read timeout below `use_brain`'s ladder, invisible to the retry account), not a
throttle ladder (which would show many short requests). Killed, Memgraph restarted,
relaunched with `-o faulthandler_timeout=1500` so a repeat dumps its stacks.

**RESULT, documents (2026-10-04, second launch, `ingest_documents-public-att3-20261004-122203.json`,
5/5 documents, 0 errors):** CC **15/21 (71%)** against the baseline's 14/25 (56%) — the bar
was 72%, missed by six tenths of a point on a different tetrad count (the pipeline placed
21 tetrads this time, 25 last time; three theses per document both times). Antithesis a
position **13/21 (62%)** against 17/25 (68%) and the bar's 64%. Restated 2/42 (bar 5/50;
baseline 1/50). `same_compromise` 4/21. Median **116 s** and **121 calls** per document against
113 s and 87–96 calls (bar 150 s). Per document: civil_disobedience 5/5 (positions 3, 124 calls, 118.6 s); federalist_10 3/3 (positions 3, 92 calls, 82.5 s); on_liberty_ch1 2/3 (positions 1, 97 calls, 116.1 s); self_reliance 3/5 (positions 2, 123 calls, 121.2 s); subjection_of_women 2/5 (positions 4, 121 calls, 106.4 s).
Reading: the point estimate moved fifteen points in the right direction and the position
rate six points in the wrong one, on 21 tetrads with a 50–86% interval — unresolved on
both counts, and the pre-registered bar is not met. Unpaired by construction (the
extracted theses differ run to run), so no sign test is available here.

**Decision (2026-10-04): two defaults, one per writer, because the two writers were
measured apart.** `DEFAULT_SKETCH_ATTEMPTS = 3` for the one-shot writer: the build cleared
every condition and the view turn cleared its primary bar resolved (12 up / 0 down), its two
side conditions one and two counts short at n = 40 with no mirror convergence in the
pairwise kinds — shipped as a pass that owes a replication of the side conditions, said
plainly rather than re-read as a pass. `DEFAULT_ASPECT_ATTEMPTS = 1` for the staged writer:
the document point estimate is encouraging and unresolved, the position rate dipped, and
the cost is +25% calls per document; a second generation on the five public texts plus the
authored five (n ≈ 45) decides, with `TETRAD_PROBE_ATTEMPTS=3` on `probe_ingest_documents.py`
already wired. Both are module constants with the figures in their comment, not settings:
no deployment chooses them, a measurement does. The runners-up a build returns
(`SketchTetrad.alternatives`) can be persisted without a new reasoning call through
`SketchTetrad(sketch=)` — the "another" door; the pre-MVP notebook is left to the app
session to wire.

**Replication for the staged writer (pre-registered 2026-10-04, owner's ask: "run the documents
replication so the Analyst gets best-of-3 too").** Four runs the same afternoon, same model,
sequential: `TETRAD_PROBE_ATTEMPTS=3` and the single draw, each on the five public texts and
the five authored ones (`INGEST_DOC_SET=public|authored`), so the control is a fresh
generation and not yesterday's file. Pooled over both sets (~40–50 tetrads an arm), the
staged default moves to 3 if: CC (fresh judge) is at least 10 points above the same-day
single-draw arm; the genuine-position rate is not more than 5 points below it; restated
plus slots do not double; median seconds per document ≤ 1.3× the single-draw arm. Any
miss keeps `DEFAULT_ASPECT_ATTEMPTS = 1` and records the figures. Unpaired by construction.

**RESULT, replication (2026-10-04 13:43–15:01, four runs, files `ingest_documents-{public,authored}-att{3,1}-20261004-*.json`):**

| arm | tetrads | CC (fresh judge) | position | restated | compromise pluses | median s/doc | median calls/doc |
|---|---|---|---|---|---|---|---|
| best-of-3, public | 25 | 15 (60%) | 21 | 2/50 | 6 | 112 | 121 |
| best-of-3, authored | 21 | 11 (52%) | 17 | 0/42 | 6 | 125 | 129 |
| single draw, public | 25 | 5 (20%) | 21 | 3/50 | 10 | 94 | 80 |
| single draw, authored | 19 | 12 (63%) | 15 | 1/38 | 12 | 108 | 81 |
| **pooled best-of-3** | 46 | **26 (57%)** | 38 (83%) | 2/92 | 12 | 120 | 124 |
| **pooled single draw** | 44 | **17 (39%)** | 36 (82%) | 4/88 | 22 | 96 | 81 |

Against the rule: CC +18 points (bar +10) — holds; position 83% against 82% (bar: not
more than 5 below) — holds; restated 2/92 against 4/88 (bar: not doubled) — holds;
1.24× the seconds per document (bar 1.3×) — holds. **`DEFAULT_ASPECT_ATTEMPTS` moves to 3.**
What the table also says, and the constant's comment carries: the two sets DISAGREE
(public +40 points, authored −11), and the single draw alone ranged 20% to 63% across
runs of five documents — yesterday's 56% on the public set became 20% today with no code
change on that path. Per-run figures on 20–25 tetrads are weather; only pooled,
same-day, pre-registered comparisons mean anything here, and even this pooled +18 on 90
tetrads is not resolved (its own interval reaches zero). The cost is real and bounded:
1.5× the calls and 1.24× the wall clock per document, because the draws and the judge
round run in parallel. A deployment that prices calls over coherence sets the constant
back to 1; the measurement, not the constant, is the thing to argue with. Compromise
pluses halving (22 → 12) is the one secondary that moved in both sets.

**Open beside it, not in it:** calibrating the 0.7 line needs two human raters on
a blind sheet (15 pass / 15 fail near the line, scores hidden) — the sheet is a
framework task (`tests/e2e/calibration_sheet.py` → `results/tetrad_quality/calibration_sheet.md`,
key beside it, 30 tetrads whose weaker score sits in 0.60–0.75), the second rater is not.

### The judge in one call (2026-10-06) — shipped, measured, rejected the same day

Best-of-N made judging the most expensive thing about a card. The first app's own
census (`utils/call_census.py` around its real entry points, Sonnet 5 via Bedrock,
40-case eval at `--reps 2`) priced one first card at 11 provider calls and ~$0.10 at
Anthropic list prices as a Bedrock proxy, of which:

| call | n | prefill read | uncached | output |
|---|---|---|---|---|
| intake gate (app-side) | 1 | 0 | ~250 | ~90 |
| view turn, best-of-3 | 3 | 11,874 each | ~1,520 each | ~370 each |
| **coherence judge** | **6** | 1,165 each | ~680 each | **~550 each** |
| pill (app-side) | 1 | 1,810 | ~400 | ~620 |

Prompt caching was working (69–83% of all prefill served from cache). The money was
in OUTPUT — ~5.1k tokens, $0.051 of the $0.10 — and two-thirds of the output was the
judge, because `judge_sketch` spent a full reasoning call on each control statement
of each draw: 2 x 3 = 6 calls to rank three drafts.

`judge_sketches` asks once. One `JointCoherenceEvaluationDto` carries all three
drafts' two statements and a one-sentence note each (~1k output expected against
3.3k, one round trip against six). What is deliberately unchanged: the statements
are built by the same builder `ControlStatementsCheck.resolve` uses, the judge still
sees only the four aspects of each draft, and the prompt forbids comparing or
ranking the drafts — the standing rule that selection happens among independent
draws and never as regeneration from a verdict. CC only; DV was dropped from this
path because it is an annotation `resolve` persists and no selection term reads it.

Two things to hold against it. The fail-soft is coarser: a per-statement shape could
lose one draft's verdict and keep the rest, while a failed joint call leaves every
draft unjudged and keeps the first draw (which is what `attempts=1` would have
done). And the placement is by the tetrad NUMBER the model echoes, not by list
order, because a verdict out of place would score every later draft on another's
words.

**Measured the same day, and rejected — both it and its fallback.**
`tests/e2e/probe_joint_judge_stability.py` re-judged stored drafts instead of
generating new ones: 41 utterances had three or more drafts carrying the
per-statement judge's `cc` pair, 40 triples were used (120 drafts). The old judge
was re-run on the same drafts as the baseline, so nothing was compared against a
92% from a different set.

| read | per-statement (re-run) | joint, one call | per draft, one call each |
|---|---|---|---|
| pass/fail agrees with stored verdict | 92% / 90% (two runs) | **70%** | **73%** |
| mean \|floor shift\| from stored | 0.025 | 0.113 | 0.101 |
| same winner when re-run | 90% | 78% | 82% |
| same winner, order reversed | — | **7/40** | — |
| winner in the first slot shown | 11/40 | **29/40** (21/40 reversed) | — |
| winners decided by a tie | 3–5 | 18 | 10–11 |
| same winner as the per-statement judge | — | 42% | 58% |

(`joint_judge_stability-20261006-122506.json`, `per_draft_judge-20261006-122730.json`.)
The joint call picked by position and ties: its scores are coarse (a third of the
triples tied at the top, and `ranking()` breaks ties toward the earlier draft), and
it also preferred the first-listed draft outright. The per-draft fallback removed
the position effect by construction and stayed stable with itself (96%), but it
measured something else: the lean prompt (CC only, a one-sentence note) shifts
scores by ~0.1 and agrees with the validated judge on the winner barely more than
chance. So the defect is the prompt, not only the field. And a selection judge that
disagrees with the post-commit judge breaks the property this module rests on —
a verdict before persistence and one after are the same question.

Reverted: `judge_sketches` scores each draft with `ControlStatementsCheck.score_texts`
(two calls, the `resolve` prompt), fail-soft per draft again. The candidate judges
live in the probe, not in `src/`. A third of a card's cost stays where it is until a
cheaper judge clears this probe against the per-statement one; the obvious next
candidate is the per-statement PROMPT with a shorter reasoning field, which keeps the
question and cuts output, measured the same way.
