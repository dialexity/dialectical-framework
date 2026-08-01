# Transformations & Synthesis — Theory → Implementation

### Insight (depth) scale — 11 levels
**Theory:** Reflex 0.0 → Transcendence 1.0, grouped Corrective (Reactive/Adjusted) /
Configurational / Generative (Strategic/Transformational). [P1 p.21]
**Implementation:** `concerns/ac_re_taxonomy.py:INSIGHT_SCALE` — all 11 labels/values match the
paper exactly (verified 2026-07-25).
**Status:** implemented

### Proactiveness scale — 11 levels
**Theory:** Observation → Stewardship ladder ("Reflections" low side, "Actions" high side); apex
Ac+/Re+ anchored low-proactiveness / high-depth. [P1 p.21]
**Implementation:** `ac_re_taxonomy.py:PROACTIVENESS_SCALE` (Observation 0.0 → Stewardship 1.0,
APEX Re at Interpretation 0.2, APEX Ac at Intervention 0.6); apex targets
`AC_PLUS_APEX_TARGET`/`RE_PLUS_APEX_TARGET`.
**Status:** implemented
**Notes:** Prose copies of both ladders are hand-typed in 3 concern prompts + Advisor
(df-review-reasoning-layer map §3.2 — drift sites; only Explorer derives via `_ladder()`).

### Forcefulness → polarity flip
**Theory:** "Proactiveness and Insight discourage forceful decisions — Ac+ and Re+ must remain
sufficiently subtle and flexible to balance each other. Becoming too forceful may reverse their
polarity from positive to negative." [P1 p.21]
**Implementation:** `transformation_generation.py` SYSTEM_PROMPT ("Forcefulness reverses polarity"
constraint: an Ac+/Re+ that imposes/coerces/overpowers becomes its "−" counterpart — soften or
reject) + `action_extraction.py` Requirements #5 (subtle-not-forceful, "reverses its polarity from
Ac+ to Ac-").
**Status:** implemented
**Notes:** Added 2026-08-01 as a prompt constraint at both Ac/Re generation sites. Locked by
`TestForcefulnessPolarityFlip` in `tests/test_prompt_review_regressions.py`.

### Greimas placement + 5 validity criteria
**Theory:** Ac operates in Not-A space, Re in Not-T (asymmetric, rotation δ); negation of A+ enables
Ac+. Five criteria — Ac+/Re+ must: (1) not restate A+/T+; (2) describe a generative operation, not a
result; (3) be valid before A+/T+ are affordable; (4) explain subtlety/indirectness/non-force;
(5) generalize beyond T/A. [P1 p.22]
**Implementation:** `concerns/positive_ac_re_apex_derivation.py` — Validation block encodes all
five criteria: "(1) not restate A+/T+, (2) be generative, (3) be valid BEFORE A+/T+ are
affordable…, (4) explain subtlety/non-force, (5) generalize beyond T/A"; Greimas Not-A/Not-T
mapping in CLAUDE.md + prompts.
**Status:** implemented
**Notes:** Criterion 3 (pre-affordability) added 2026-07-31. Locked by
`TestGreimasFiveCriteria` in `tests/test_prompt_review_regressions.py`.

### Transition tetrad coherence (Ac+⊥Re−, Ac−⊥Re+)
**Theory:** Transitions form a tetrad obeying rules 3.1–3.3: Ac+ directly contradicts Re−, Ac−
directly contradicts Re+; degeneration "Ac+ without Re+ → Ac−, Re+ without Ac+ → Re−". [P0 pp.16-17]
**Implementation:** `concerns/transformation_generation.py` (degeneration/CC rules in prompt; all
four positions generated).
**Status:** partial
**Notes:** Degeneration encoded; the transition-level *diagonal contradiction check* has no
equivalent of `DiagonalOppositionsCheck`. See generative-rules.md Rule 5.2.

### Full transitions matrix + principles/ontologies layer
**Theory:** Rule 8: all negative poles × all positive poles (4n² transitions), Ac+/Re+ special
cases; verbatim generation prompts; then compress each row → "how to overcome that downside" and
each column → "how to cultivate that upside" in child-clear language ("Life Principles"); the
principle set = an **ontology**; matrix extensible into R&D/business ideas. Cross-tetrad transitions
score highest in worked examples (A4−→T1+ 0.93). [P0 pp.18,22,24; P1 pp.42-48]
**Implementation:** Matrix: wheel-native decomposition — arrangement enumeration materializes every
cross-tetrad minus→plus pair as a wheel edge; matrix cell ≡ that edge's Transformation; higher
layers refine lower via `find_parent_transformations` → `parent_context`. Compression layer: —.
**Status:** matrix implemented (as wheel-native decomposition); principles/ontologies layer absent
**Notes:** Split verdict (2026-08-01, see generative-rules.md Rule 8 for the full argument):
eager-vs-lazy fill is application policy; a matrix *view* is an assembly query (group Transitions
by source/target Statement, dedupe by nonce) — build when a consumer needs it. Same-side cells
(T_i−→T_i+) deliberately unmediated (backfire constraint) — principled divergence from the naive
4n² count. The compression layer (row/column principles → ontology nodes) is the remaining true
absence; the paper's prompts [P1 p.42] are directly portable when/if built.

### Synthesis subtypes Sa/Sb/Sc (+ degradation modes)
**Theory:** S+ decomposes into Sa+ Self-Regulation (Process), Sb+ Bounded Coupling (Structure),
Sc+ Invariant Preservation (Normative); S− into Sa− distortion via dominant T, Sb− erosion via
dominant A, Sc− deregulation via T/A oscillation. Scored per sub-synthesis with HS; MHS aggregates.
Authors: "definitive classification left for future work". [P0 p.15; P1 p.18]
**Implementation:** — (`synthesis_generation.py` produces a single S+/S− pair per wheel; TODO stubs
reference apex coherence)
**Status:** absent
**Notes:** This is the missing substrate for Rule 7 (apex coherence): the "valid sub-syntheses"
whose convex hull S± must lie within are exactly these Sa/Sb/Sc instances (per-tetrad sub-syntheses
with exemplars appear in [P1 p.36]). If R7 ever gets wired, build Sa/Sb/Sc first.

### Apex coherence (Rule 7)
**Theory:** S± must lie within the convex hull / semantic centroid of its valid sub-syntheses
(which satisfy modality balance, Kc, control-statement coherence). [CLAUDE.md R7; sub-synthesis
data P1 p.18, p.36]
**Implementation:** — (TODO stubs in `concerns/synthesis_generation.py`)
**Status:** absent
**Notes:** Was "prompt-absent, no data to implement against". The supplement now provides the
sub-synthesis enumeration + MHS scoring — the data model exists in theory; still unwired in code.
Keep df-review-reasoning-layer's guard: reject prompt edits claiming apex validation until wired.
Also owns the "S+ without lower-layer support yields S−" control-statement extrapolation (TODO in
`synthesis_generation.py`) — control-statement *style* at synthesis level, no paper Rule 3.3
anchor; blocked on the same sub-synthesis substrate.

### "Wisdom unit"
**Theory:** Term of art: a tetrad + its complementary Ac/Re transitions as a self-regulating unit.
[P1 p.39]
**Implementation:** Conceptually = Perspective + its Transformations (no code term).
**Status:** implemented (structure) — vocabulary note only.

### Nested intensity cycles / bottom-up complementarity
**Theory:** Inner (intense) vs outer (less intense) conflict cycles on one wheel with micro-action
bundles per position; purpose: structure bottom-up complementarity. [P1 p.38]
**Implementation:** — (wheel layers = PP count, not conflict intensity)
**Status:** absent

### Hierarchical sub-aspects (T11+, T12+, …)
**Theory:** Each pole expands into open-ended numbered sub-aspect lists (two-digit indexing).
[P1 p.41]
**Implementation:** — (one aspect per position per Perspective; alternatives via separate
perspectives from `ExpandPolarity`)
**Status:** absent
**Notes:** ExpandPolarity's multiple-tetrads-per-polarity covers the *practical* need (alternative
framings); the hierarchical indexing scheme itself has no counterpart.

### Coupling dendrograms
**Theory:** Hierarchical clustering of T/A pairs at similarity thresholds reveals orthogonal
couplings/entanglement pairs between tetrads → deepest leverage mechanisms. [P1 pp.35,37]
**Implementation:** —
**Status:** absent
