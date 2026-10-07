# Whole vs chopped at the transformation layer

Lab notes, 2026-10-04/05. The rule this produced is in CLAUDE.md under
"Synthesis Architecture"; the numbers are in the files named, never in this
prose. Framework-only: what a host does with Ac±/Re±/S± on a screen is the
host's record, not this one.

## The question

Does the transformation layer — `ExploreTransformations` (one Ac+ candidate per
insight band, then one position per call) and `GenerateSynthesis` (S± from the
transition texts) — produce Ac+/Re+/S+/S- better than ONE call handed the
theory and the six corners of the tetrad? The project's ceiling-not-floor rule
demands the comparison, and the one-shot tetrad (`SketchTetrad`, 25/40 against
the staged build's 14/40) made it a live question one layer up. The trigger was
a host rendering those positions for a person and finding the corners flat;
the question is the framework's.

## Instruments (all `tests/e2e/`, results under `results/tetrad_quality/`, gitignored)

Same 17 tetrads throughout (12 statements, 5 questions, drawn by the view turn
best-of-3; `wisdom_line-20261004-153912.json` carries their six texts).

- `probe_synthesis_arms_corners.py` — the six corners → one rendering call, told "do not
  reason the structure". 5 s. Its prose improvised the move (Ac+-shaped) with
  no structure behind it — the baseline that raised the question.
- `probe_synthesis_arms_machinery.py` — each tetrad persisted through
  `SketchTetrad(sketch=)` (no re-reasoning), `run_exploration_detailed` on the
  1-PP wheel (2 edges × 3 insight bands = 6 Transformations) + synthesis, then
  the same writer handed Ac±/Re±/S±. `wisdom_machinery-20261005-082435.json`:
  17/17 built, persist 22 s, explore 56–75 s (median 61), **~88 s a tetrad**.
- `probe_synthesis_arms_theory1.py` (arm 1) — one call, the six corners + the
  theory stated loosely ("Ac- carries T+ into A-"). 9.4 s.
- `probe_synthesis_arms_theory2.py` (arm 2) — one call, the Transformation AS A
  TETRAD: Ac and Re first, then each one's ± development, then S± from the
  pairs; S- told to be one named state. 9.5 s. Adds a **third-trap auditor**
  (is S- a failure distinct from T- and A-, or the traps restated / one trap)
  and a blind pairwise "sharper S-" judge, order randomised and persisted.
- `probe_synthesis_rerun.py` — `GenerateSynthesis` re-run on the 17 existing
  wheels after the prompt fix below; 5.5 s a call.
- `probe_synthesis_arms_rejudge.py` — every S- pair judged in BOTH slot orders,
  a win counted only when the orders agree (the bench's exact-split rule, which
  the two probes above did not follow).

One judge (Fable 5), one rater, n = 17; the third-trap auditor is new and
unvalidated against a hand count.

## What was measured, in order

**Arm 1 collapsed the Transformation onto the Perspective.** Its Ac- came back
as T- restated, Re- as A- restated, and S- as "Either X or Y" in 14/17 — the
two traps as a fork. Third-trap auditor: 0/17. It had no action to degrade
(it never derived Ac/Re), so it mapped Ac- onto the nearest thing it had.

**Arm 2 did not.** Third-trap 11/17; blind pairwise against the machinery's
S- **12–5**. The difference between the two prompts was the framework's node
model stated exactly (Ac/Re are poles, Ac±/Re± their aspects, S± from the
pairs). Its Ac/Re were concrete and Corrective-rung by nature ("Tell one client
'not this time' and watch what happens").

**The machinery's S- read as the traps restated in 10/17** (third-trap 4/17) —
"Negotiated freedom decays into either lockdown or neglect", "X while Y" with
X, Y the traps. A first reading of this session claimed 0/17 had the fork
shape; the auditor's count corrected that. The machinery's synthesis prompt
had never been told S- is one state; arm 2 had. That was the confound.

**With the confound removed, the gap closed.** `synthesis_generation.SYSTEM_PROMPT`
gained "The shape of the inputs, exactly" — the Transformation as a tetrad,
Ac-/Re- as the action/reflection gone wrong and not the segments' traps, S- as
ONE named state ("either X or Y" lists the inputs), S+ as a gain in dimension
and not "both" — with the same rule on `s_minus_statement` and the user
prompt's closing line. Re-run on the same wheels
(`synthesis_rerun-20261005-103628.json`): third-trap **12/17** (from 4),
blind pairwise new-vs-old 10–7, new-vs-arm 2 7–10 — neither resolved.

## Reading

1. **The S- defect was the reassembly prompt, not the chop.** Given the exact
   theory, the chopped pipeline names the third trap as often as the whole
   call. The earlier claim in this session — "at N = 1 the whole call beats
   the chopped machinery on the transformation layer, as it did on the
   tetrad" — is withdrawn on S- quality. What a whole call still wins on is
   **cost** (9.5 s against 88 s) and **register**: the machinery's S- is
   abstract-nouny ("Belonging ossifies into surveilled, mandatory theater
   nobody actually inhabits"), arm 2's is plain ("Performing generosity while
   quietly keeping score"). The register difference is unmeasured as a
   number; it is the owner's read of the two lists.
2. **The architecture question stands on cost and register.** The owner's
   proposal — at N ≥ 2, one whole call per EDGE PAIR (the unit a Transformation
   spans; the Re side is another tetrad's statements, which is where the 1-PP
   collapse stops holding) in parallel, then one reassembly call for S± that
   sees every transformation tetrad, the perspectives and the person's words
   — would cut a deep wheel at N = 4 from ~105 calls to ~13 and wall clock
   from ~60 s to ~20 s. Endpoint drift, the defect that disqualified the
   one-shot tetrad writer on a GIVEN pair (17–22/40), is structurally smaller
   here: a Transition's endpoints are nodes and the call writes only the
   instruction between them. Not one call per wheel: flat schemas survive
   the real provider, a 4-tension wheel in one DTO is 50+ fields. **Unmeasured
   at N ≥ 2**; the project's rule is that consolidation is a measurement, not
   a cleanup. Pre-registered shape of that measurement: ten N = 2 wheels
   (pairs of the 40 statements a nexus would group — different polarities)
   built both ways; S± read with the third-trap auditor, each Transformation
   with the control statements (Ac+ without Re+ yields Ac-), endpoint
   fidelity, cost, the owner's eye.
3. **What the framework was for at N = 1** — the honest answer to "why the
   whole framework if a prompt does it": the theory as a data model (arm 1
   had it loosely and scored 0/17; arm 2 had it exactly and scored 11/17 —
   the prompt that works IS the framework's node model); selection and
   checks (best-of-3 raised first tetrads 25 → 36/40 and a prompt cannot do
   that to itself; the third-trap auditor exists because a derived S- gave it
   something to compare); addressability and memory (a pathway node grounds
   a decision, a second utterance lands next to the first); N ≥ 2
   (enumeration, not a thought); measurability. Not generation at a single
   node — the bench never resolved that in either direction and this did not
   either.

## Review (2026-10-05, four reviewers on the proposal; the owner's prompt: "transformations are recursive for N ≥ 2")

**Retractions.** The 12–5 pairwise was slot bias: the RNG put arm 2 in slot A in
12/17 pairs and slot A won 13/17. Re-judged with exact crossed order
(`synthesis_arms_rejudge-20261005-112123.json`, order-bound pairs excluded):
arm 2 over the old machinery **9–4** (4 order-bound), new machinery vs old
**6–7** (4), new machinery vs arm 2 **5–9** (3). Arm 2 keeps an edge on S-
sharpness; nothing resolves at this n, and the prompt-fix did not move the
pairwise. The third-trap auditor is saturated by the instruction it tests for
(arm 2 and the fixed synthesis were both told "never either/or"; the auditor
defines `traps_restated` as either/or) — its 4 → 12 reads as instruction
compliance, not insight. The 88 s vs 9.5 s cost compares different products:
six scored, persisted Transformations with bands, apexes and HS plus a synthesis
against eight unscored one-line strings; the real one-shot DTO is ~50 fields
(headline/statement/explanation/haiku/insight/proactiveness per position), the
shape the provider has been recorded dropping. Register is an instruction
difference (the generation prompts ask for labels at `component_length`; arm 2
asked for second person). Nothing instrumented Ac-/Re-; "arm 1 collapsed Ac-
onto T-" is a reading.

**What "recursive" means at N ≥ 2, from the code** (theory reviewer):
(A) layer recursion — a layer-k Transformation is generated against the
committed Transformations of the edge it subdivides at k−1…1
(`TransformationRepository.find_parent_transformations`, `[]` at
`polarity_count <= 1`; rendered coarsest-first by `build_coarser_context`;
rung barrier in `explorer.py`, one layer at a time; synthesis recurses the
same way over sub-wheel S±); (B) antipode recursion — Re+ is written FRESH
"responding to" the antipode's same-band Ac+ (`_generate_re_side`), never
copied, so CLAUDE.md's "E1's Ac+ = E3's Re+" is not what the code does;
(C) the Transition-as-tetrad rule (5.2), partial, checked by nobody. **No
cross-pair dependence within a wheel**: pairs already run in parallel at a
rung. **Every wheel measured here was 1-PP, where `parent_context == ""`:
recursion was structurally absent from all 17**, and an N = 2 gate built
directly from statement pairs would repeat that — it must be a two-rung climb.

**What the proposal got wrong about the code** (code reviewer):
`_create_transformation` is per EDGE, not per pair; the existing DTO carries
scores, so "reuse unchanged" puts scoring in the writer, and kept separate
it is writer + scorer + HS (which needs the apex the proposal deleted) ≈ 3
calls per edge-band; refinement is per edge (two ancestries per pair) and
collapsing the three `REFINE_*` instructions into one prompt is the
"an instruction that names neither is an instruction to both" trap; writing
S± in the writer breaks R5's belt-and-suspenders; "cannot drift because
endpoints are nodes" is unsupported — fixed endpoints make drift invisible.
Two bugs found on the way, independent of the proposal:
`ActionExtraction._build_exclusion_list` compares Ac+ candidate text against
the Ac+ transition's TARGET (A+) text, so the dedup never matches (dead
code); `positive_ac_re_apex_derivation.py` still carries `ApexDerivation` /
`ApexDerivationResultDto` aliases, against the no-alias rule.

**What the product contract pins** (consumer reviewer): "one band by default"
falsifies every derived-status read on day one — `len(INSIGHT_CATEGORIES)` is
the `expected` of completeness lines, synthesis stamps ("built from 2 of 6"),
`build_status` (`WHEEL_COMPLETE` never fires), views, `partial_wheels`; the
depth ladder is a claim in both system prompts and the docs, with `deepen`
elected 0/6 by the Advisor. Either three bands ship in the one call or the
ladder is retired as a product decision. Maintenance that would shrink: about
a third of the transformation layer (four prompts, extraction, apex, band
pairing, the which-position-reads-which-line argument); what stays is the
larger half — completeness, resume, blocked edges, parent lookup,
persistence, grounds — which exists because of layers, pairs and interrupted
builds, not the chop. Failure granularity coarsens: one ParseError on a
~50-field DTO empties a pair.

**The proposal as written is not earned.** The honest revised shape: a
one-shot per EDGE writing the full DTO minus scores; apex and HS kept; scorer
separate and not elective; all three bands in the call (measure the drop
rate); refinement lines per position inside the one prompt (Ac+ ← the
`Action:` line, Re+ ← the `Reflection:` line, negatives refine nothing); S±
left to the synthesis. Expected ~14 → ~5 calls per edge — a 3× figure, not
10×. **The decisive experiment, corrected:** ten N = 2 wheels as a two-rung
climb (both layer-1 wheels first), both arms, two generations, exact crossed
judge order, three binary reads per Transition — endpoint fidelity (does the
Ac+ text carry THIS source minus to THIS target tetrad's plus), antipode
consistency, and whether the layer-2 Ac+ is more concrete than its layer-1
parent (`probe_transformation_recursion.py`'s exposure table is the starting
instrument). Reject if the sketch's fidelity trails by > 2/20 in either
generation or any N = 2 Ac+ stays inside its source tetrad in > 2/20 — the
1-PP collapse surfacing at the seam the owner named.

## Open

- The two-rung N = 2 measurement above (never the direct-build form).
- (The two bugs named in the review were fixed the same day: the exclusion list
  now collects Ac+ instruction text; the apex aliases are deleted and swept.)
- Register: the synthesis statements are written to `component_length` as
  "declarative labels naming the emergent state"; arm 2's were written for a
  person. Whether a person-facing register belongs on the Statement or only
  on a renderer is a product question the app repo owns.
- The third-trap auditor against a hand count.

## Ac-/Re- with both halves, and the one statement of the Transformation (2026-10-06)

**What was wrong.** The paper gives each minus transition twice [P0 pp.6,16-17]: by its ENDS
(Ac- = T+ → A-, Re- = A+ → T-, which is how `_create_transformation` wires them) and by what it is
MADE of ("Ac+ without Re+ degenerates into Ac-"). The staged generator says both. Two prompts said
half: the synthesis prompt ("acting without reflecting yields Ac-", and the "shape of the inputs"
paragraph of 10-05 with no endpoints) and the first app's pill, which carried arm 2 verbatim. A host
noticed: in the app, Ac- read as "the action done badly" with no say on where it goes.

**Arm 1 is not evidence against the endpoints.** The host's note read the 0/17 above as "stating
the endpoints collapsed it". Arm 1 differed from arm 2 in three ways at once (no Ac/Re poles, the
endpoints, no either/or rule), and its Ac- came back as T- — which violates the endpoint reading too
(Ac- ends in A-). What arm 1 shows is that a degradation needs a pole to degrade.

**What changed.** `concerns/transformation_sketch.py` holds the one statement:
`TRANSFORMATION_POSITIONS` (poles; developments; both halves of Ac-/Re-; the diagonal
contradictions), `SYNTHESIS_SHAPE` (the 10-05 S- rule verbatim) and `TRANSFORMATION_BUILD_PROCEDURE`
(poles first). The synthesis prompt's "shape of the inputs" IS those two constants now; the app's pill
embeds the procedure and subclasses `TransformationSketchDto`; `TransformationSketch` is the graph-free
one-shot for a host with a drawn tetrad and no wheel (one tension only). `attempts=` reuses the tetrad
judge on the transition tetrad through `as_control_tetrad` — Rule 5.2's control statements in the
tetrad's corners — default ONE, because nothing about this call is measured and the judge cannot see
the two defects this layer has shown (S- shape, endpoint fidelity).

**Measured on the synthesis prompt only** (the pill's change is the app's first-card eval). The 17
wheels of 10-05 were gone from the DB, so they were rebuilt with the PRE-change prompt
(`wisdom_machinery-20261006-105337.json`, 17/17, ~95 s each), synthesis re-run on the same wheels with
the new one (`synthesis_rerun-20261006-112425.json`), and both sides read by
`probe_synthesis_rescore.py` (written for this: `probe_synthesis_rerun.py` audits only the new side and
prints 10-05 constants for the old, and its pairwise is single-order):
`synthesis_rescore-20261006-113009.json` — third-trap old **11/17**, new **12/17**; crossed-order
pairwise new 7, old 4, same 1, order-bound 5. **No regression, no resolved gain**: a correctness fix
that held the measured S- rule, not an S- improvement. Note the before is the 10-05 prompt WITH its
shape rule (it already scored 12/17 on the old wheels), so the 4 → 12 of 10-05 is not re-earned here.
Same caveats as above: one judge, n = 17, the auditor saturated by the either/or rule both sides carry.

### The ends did not land in text; they land through the DTO (2026-10-06, same day)

**The host caught it.** The first app measured the pill on 25 frozen tetrads (its 8 plus the 17
above), old arm-2 text against the both-halves text, Sonnet 5 writing, Opus 5 judging, 2 reps,
paired: the endpoint half did not land in either arm (Ac- on T+ → A- 30% → 14%, the drop clearing
noise; Re- 20% → 12%), with the card text, S- and the makeup reads unchanged within noise. The writer
put Ac- on T's OWN trap — "T overdone into T-" — instead of carrying T's strength into A's trap. The
mechanism is in the wording: "Ac+ without Re+" reads like the aspect tetrad's "T+ without A+ yields
T-", so the makeup half pulls the line onto T-. Shipping the both-halves text into the framework as
"Ac-/Re- carry both halves" claimed an instruction works because it was stated. It was not measured.

**The framework now owns the instrument.** `tests/e2e/probe_transformation_sketch.py` ports the app's
eval onto `TransformationSketch`: the same 25 tetrads (`fixtures/transformation_tetrads.jsonl`), the
same two auditors verbatim (third-trap; endpoints + makeup, four booleans), crossed-order S-
pairwise, every read a paired delta against the shipped arm with a 95% CI, the bench judge (Fable 5)
on a Sonnet 5 writer. Run it before any edit to `TRANSFORMATION_POSITIONS`, `SYNTHESIS_SHAPE` or the
DTO. `transformation_sketch-20261006-130616.json`, n = 50 per arm:

| arm | Ac- ends | Re- ends | Ac- is the action | Re- is the reflection | S- third |
|---|---|---|---|---|---|
| both-halves text (dd2be18) | 22% | 18% | 88% | 94% | 72% |
| makeup only (arm 2) | 16% | 4% | 92% | 96% | 78% |
| ends first, wrong pattern named | 40% (+18, clears) | 28% | 82% | 82% | 70% |
| **text + `from`/`into` fields before each line** | **60% (+38, clears)** | **58% (+40, clears)** | 82% (−6) | 88% (−6) | 82% (+10) |

S- pairwise, fields vs text, crossed: 17–23 with 10 order-bound — unresolved, a lean against.
Read before trusting (the app's caution): the text-only failures are what the app described ("a
clean break, dropped from the rolls" for T+ "stay engaged" — T's own cut-off, T-); the fields'
passes are the theory's non-obvious failures ("keep visiting him so often the conversation drifts
into just accepting his checks again"); the fields' failures are a line drifting back to T- past a
correct scaffold, and twice a wrong target named in the scaffold itself.

**Shipped:** the four scaffold fields in `TransformationSketchDto`, before their lines; the text is
unchanged. The app's own "both-halves did worse than none" did not replicate on this judge and
without the app's voice (22% vs 16% the other way, within noise); its "the ends do not land in text"
did. A host subclassing the DTO inherits the fields.

**Open:** whether the staged generator lands the ends at all — never instrumented; its stored
pathways carry no edge orientation, so judging them needs the wheel read back from the graph. That is
also the first number the N = 2 one-shot-per-edge measurement needs.

### The staged generator's ends: Ac- lands, Re- does not, and the one-shot's fix does not carry (2026-10-06)

`tests/e2e/probe_staged_endpoints.py` answers the open question above. It reads the 17 one-tension
wheels back from the graph (rebuilt with cleanup off), orients every Transformation by its Ac-
transition's SOURCE statement (T+ means the edge runs T -> A; A+ means A -> T and the corners are
swapped), and puts the same endpoint auditor to all 102 of them. Wiring 102/102 — the structure is
right; the question is the text.

| staged, 102 Transformations | Ac- ends | Re- ends | Ac- is the action | Re- is the reflection |
|---|---|---|---|---|
| all | **74%** | **34%** | 75% | 88% |
| T -> A edges | 67% | 18% | 73% | 86% |
| A -> T edges | 80% | 51% | 78% | 90% |

So the production Ac- is fine — better than the one-shot even with its scaffold (60%), probably
because its own call says "the path from T+ (strength) toward A- (problem)" concretely. Re- is
the weak position: its failures LAND right (T-) and START wrong — from the reflection's own noticing
or from T+, not from A+. A plausible cause in the prompt: `build_edge_context` renders the
reflection block RELATIVE to the opposite edge (its T+ is the other side's strength, its A- your own
trap), and the Re- instruction "the Reflection Perspective's positive regresses you toward your
negative" names neither of the block's two positives.

**The one-shot's fix did not carry.** `re_minus_from` / `re_minus_into` before the Re- lines, by the
block's own labels: Re- 34% -> 40%, paired by (tetrad, edge, band) +6 (-6..+18), within noise; the
unchanged Ac- (the control) -2. Reverted — a claimed fix with extra output tokens and no measured
effect is not shipped. Not seen: whether the writer filled the two fields correctly (they were not
persisted), which is the first thing to capture if this is picked up again.

**Read the judge before acting on this.** It requires Re- to visibly START from A+. The staged
prompt defines Re- by makeup ("what Re+ itself degenerates into when Ac+ is absent"), and Re+ starts
from the block's T- side, so a line that starts from "the reflection" is following its own
instruction. Whether "taking in their strength without acting, landing in your trap" must NAME the
other side's strength to count is a reading of the theory, not a measurement. Open:
- capture the Re- DTO (both scaffold fields) on a few wheels to see whether the scaffold was ignored
  or wrong;
- the prose fix: name the block's T+ as the start in the Re- instruction itself;
- hand-read 10 Re- failures with the owner against the paper's Re- definition before either.

### The auditor was too strict, and the staged Re- fails on its landing (2026-10-06, the same day)

The last bullet above was done by three theory reviewers instead of the owner, who asked for it:
three independent agents, each told to settle from the papers what Re- must express and then judge
15 staged Re- lines BLIND — 10 the auditor had failed, 5 it had passed, shuffled, no verdicts shown
(`tests/e2e/fixtures/re_minus_theory_cases.jsonl` holds the cases and their verdicts). They agreed
with each other on every clear case and cited the same passages: Re- "transforms A+ into T-"
[P0 pp.6, 16-17], so it must END in T- — the definition, not optional; "Re+ without Ac+ degenerates
into Re-" is a coherence test it passes, not its definition; it need NOT name A+ (the paper's only
named Re- is the one word "Dogmatize", Fig. 1B, p.3); and it should not start from T+ (T+ decaying
into T- is the base tetrad's control statement, not a transition).

**Against the auditor:** its 5 passes were all valid; of its 10 failures, 5 were genuinely invalid —
every one LANDING in A-, not T- — and 5 were valid or borderline, failed only for not naming A+. So
the reading recorded above, "Re- lands right and starts wrong", was the strict auditor talking, and
it is withdrawn: the real defect is the landing. The writer reads "the reflection without the
action" as "keep watching, do nothing", and wherever A is the passive pole (postponing, paying on,
keeping one's distance) doing nothing IS A's trap.

**The auditor that replaced it.** `TransitionVerdict` (`tests/e2e/probe_transformation_sketch.py`):
lands in the right trap (asked first), is the operation degenerated, does not start from the wrong
side's plus; valid = all three. Validated before use (`probe_transition_rescore.py`, two runs of
two passes on the 15 cases): 51/52 agreement with the reviewers' consensus on clear cases against
the old auditor's 10/13; landing 15/15; self-agreement 29/30; both borderline cases called invalid.
Validated on Re- only — Ac- rests on the mirror rule.

**Everything re-read, nothing regenerated** (`transition_rescore-20261006-175449.json`):

| | Ac- valid (lands) | Re- valid (lands) | strict auditor read |
|---|---|---|---|
| staged generator, 102 | 70% (91%) | **49% (59%)** | 74% / 34% |
| — T -> A edges | 53% | 27% | |
| — A -> T edges | 86% | 71% | |
| one-shot, text only | 30% (30%) | 26% (30%) | 22% / 18% |
| one-shot, from/into fields (shipped) | **56% (64%)** | **62% (64%)** | 60% / 58% |
| one-shot, makeup only (arm 2) | 16% | 10% | 16% / 4% |

The shipped fields' gain survives the honest test (paired +26 / +36, both clearing noise), so they
stay. The staged Re- is the open defect, and it is a landing problem worst on T -> A edges; the
from/into fields did not move it (strict read, within noise). The staged Ac- is fine.

**Open:** the staged Re- landing (try naming the landing — the reflection block's A- — in the
instruction, measured on `probe_staged_endpoints.py` by `TransitionVerdict`); and the first app's
endpoint judge is the same strict auditor, so its endpoint figures read low by the same margin.

### The staged Re- names its landing (2026-10-06, same day)

The Re- instruction in `_generate_re_side` said "the Reflection Perspective's positive regresses you
toward your negative" — no landing in the block's own labels, and a definition ("reflection without
the action") the writer read as "keep watching, do nothing". It now says where Re- LANDS (the A-
line of `<reflection_perspective>`, your own trap), that the start (its T+ line) need not be named,
and names the miss: doing nothing leaves the OTHER side's trap in place (the block's T- line), which
is not Re-. Rebuilt the 17 wheels and judged with `TransitionVerdict`, paired by (tetrad, edge,
band) against the re-scored baseline (`staged_endpoints-20261006-185109.json`):

| staged, 102 | before | after | paired |
|---|---|---|---|
| Re- lands in T- | 59% | **76%** | +18 (+7..+29), clears |
| Re- is the reflection degenerated | 88% | 97% | +9 (+2..+16), clears |
| Re- valid | 49% | 61% | +12 (-0..+24), at the edge of noise |
| — T -> A edges | 27% | 57% | |
| — A -> T edges | 71% | 65% | |
| Ac- valid (unchanged, the control) | 70% | 70% | +0 |

Shipped: the targeted defect moved and cleared, the makeup read moved WITH it rather than trading
against it, and the control held. Not resolved: validity overall (the CI touches zero), and the A->T
dip, unpaired. What is left (40 failures): 22 still do not land (the "keep watching" shape, less of
it), 14 land but start from T+ — the shape two of the three theory reviewers called borderline.

## The N = 2 measurement, run (2026-10-06)

The pre-registered experiment above, as `tests/e2e/probe_n2_one_shot_edge.py`.

**Setup.** Ten two-tension wheels, each two genuinely different tensions from ONE situation
(`fixtures/n2_tetrad_pairs.jsonl`: a frozen tetrad plus a second tension the Consultant's view
turn drew over the same conversation, best-of-3, kept only when thesis and antithesis both differ —
stored drafts of the same utterance were mostly the same tension reworded). A two-rung climb:
`ExplorationPipeline(max_deep_wheels=None, refine_from_coarser=True)` deepens both one-tension
wheels, then the two-tension wheels with them as parents. On the top two-tension wheel, `staged` =
what the build wrote; `one_shot` = one call per edge with what the staged generator is handed (both
perspectives' blocks, the coarser hierarchy with a refinement line per position), all three insight
bands and the start/landing fields in the one call. Two generations, each a fresh build. Reads on
the bench judge (Fable 5), paired by (edge, band): fidelity (Ac+ turns THIS source trap into THIS
target's strength), inside (it heads for its own tension's other strength — the N = 1 collapse),
refines (a more concrete sub-step of a parent Action line), antipode (Re+ and the opposite edge's
same-band Ac+ describe one move).

**Results** (`n2_one_shot_edge-gen1-20261006-211407.json`, `-gen2-20261006-223221.json`; edges whose
target strength is the SAME statement as the source tension's own — two tetrads sharing an aspect
text, deduplicated by the graph — excluded, 7 / 6 of 40 edges, decided after seeing gen 1):

| | gen 1 staged / one-shot | gen 2 staged / one-shot |
|---|---|---|
| fidelity | 67% / 79% (+12, -0..+24) | 59% / 57% (-2, -15..+11) |
| inside | 28% / 4% (-24, clears) | 35% / 18% (-18, clears) |
| refines the parent | 85% / 73% (-12, clears) | 93% / 70% (-24, clears) |
| antipode | 96% / 89% (noise) | 97% / 94% (noise) |
| cost | ~200 calls a pair (all four wheels + synthesis), ~165 s | 1 call an edge, ~12 s |

**Verdict by the pre-registered rule: REJECTED** — generation 2 has 18% of the one-shot's Ac+
inside their source tension, over the 10% bar. The staged generator stays.

**What the rule did not foresee.** It treated the collapse as a one-shot risk; the staged generator
collapses MORE, in both generations (28%, 35% — read by hand on samples: "insisting on solo
control" → "book a call with an outside expert" heads for the source tension's own "partners add
skills", not the target's "employment funds and de-risks"). Fidelity is a tie. The one-shot's
consistent cost is the RECURSION: it refines the coarser layer worse (-12, -24), which is what the
staged path's per-position refinement exists for.

**A cheap lead for the staged collapse.** The one-shot prompt says the two perspectives "come from
TWO DIFFERENT tensions — do not read A as the other side of T's own tension". The staged generator's
`build_edge_context` labels the target segment "A" with no such warning, which reads, at N >= 2, as
T's own antithesis. Untested.

**Measurement notes.** The first fidelity judge returned an EMPTY response on every row from Fable 5
in both tool and JSON mode, while the model answered other schemas and Opus 5 answered this one; a
schema with different field names and descriptions parses (`FidelityVerdict`'s docstring). Gen 1 was
re-judged from its stored outputs (`test_rejudge_fidelity`), nothing rebuilt.

### The staged collapse: a cross-tension note in the edge context (2026-10-07)

The lead above, tested. `build_edge_context` renders an edge's two segments with RELATIVE labels (the
target is "A"); at N >= 2 the target belongs to ANOTHER tension, and the staged writer read that "A"
as T's own antithesis. It now appends `CROSS_TENSION_NOTE` — "T and A above come from TWO DIFFERENT
tensions: do not read A as the other side of T's own tension" — whenever the target is not the
source's own opposite (by statement hash; a one-tension edge, and two readings of one polarity, get
nothing). It reaches every consumer of the block: Ac+ extraction, the tetrad calls, the apex.

Measured with `probe_n2_one_shot_edge.py`'s staged arm, two fresh generations with the note against
the two without (`-gen3-crossnote-20261007-064707`, `-gen4-crossnote-20261007-073017`; unpaired,
different builds of the same 10 pairs; shared-statement edges excluded as before):

| staged, two-tension wheels | without (gen 1+2, n=201) | with (gen 3+4, n=207) | difference |
|---|---|---|---|
| fidelity | 63% | **72%** | **+10 (+1..+19), clears** |
| stays inside its own tension | 32% | 24% | -8 (-17..+0), edge of noise |
| refines its parent | 89% | 85% | -4, within noise |
| antipode | 97% | 97% | flat |

Shipped: fidelity cleared, the collapse fell in both note generations (25%, 23% against 28%, 35%),
nothing got worse beyond noise. Still OPEN: a quarter of staged Ac+ at N = 2 heading for their own
tension, and the one-shot's refinement gap, which this does not touch.
