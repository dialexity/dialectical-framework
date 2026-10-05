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

## Open

- The N ≥ 2 measurement above.
- Register: the synthesis statements are written to `component_length` as
  "declarative labels naming the emergent state"; arm 2's were written for a
  person. Whether a person-facing register belongs on the Statement or only
  on a renderer is a product question the app repo owns.
- The third-trap auditor against a hand count.
