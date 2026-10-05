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
