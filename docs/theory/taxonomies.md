# Taxonomies — Theory → Implementation

### Antithesis "thesis-lessness" ladder (11 modes, 0.0–1.0)
**Theory:** Every functional antithesis arises from absence or violation of T. Single graded scale:
Negation 1.0, Inversion 0.9 (Negation branch); Devaluation 0.8, Hollowing 0.7 (Violations);
Corruption 0.6, Distortion 0.5 (Corruption); Skew 0.4, Blocking 0.3 (Deformation); Suppression 0.2,
Distancing 0.1 (Inhibition); Privation 0.0 (Absence). Ask "what functionally opposes the role played
by T?", not "what negates T?". [P0 p.7, Fig 3A]
**Implementation:** `concerns/antithesis_classification.py:MODE_FIELDS` — all 11 labels and values
match the paper exactly (verified 2026-07-25).
**Status:** implemented
**Notes:** The repo calls this the Mode scale / "universal taxonomy"; the paper's name is
"thesis-lessness". Same object. The markdown restatement inside the same file's SYSTEM_PROMPT is a
known drift site (df-review-reasoning-layer map §3.4).

### Mode × Arousal plane + corner semantics
**Theory:** Mode = interaction mechanism, Arousal = activation level. Hypothesis: Arousal separates
true antitheses (S+ potential) from void antitheses (S− traps). Top-right (→1,1) = active negation;
bottom-left (→0,0) = passive privation, which "attracts latent pathologies (S−) that occupy the void
while imitating progression toward S+". Table 5 adds an "Optimum A" column — AI-selected antithesis
maximizing tetrad coherence + S+ likelihood. [P0 pp.7-8]
**Implementation:** `antithesis_classification.py:MODE_FIELDS`, `AROUSAL_VALUES` (both axes scored);
`concerns/antithesis_extraction.py` generates candidates across mode branches and picks by HS.
**Status:** partial
**Notes:** Both coordinates are computed and persisted (Estimations), but the corner/void semantics
(bottom-left = pathology attractor) and the explicit "Optimum A" selection rationale are not used —
selection goes by HS, not by the Arousal-separates-true-from-void hypothesis.

### Systemic taxonomy (5 branches, apex = Viability)
**Theory:** Apex "system viability" from 5 capacities: Integrity, Fidelity, Exchange, Flexibility,
Resilience — "heuristic organizing framework, not definitive ontology". Full Table S1.11-1 provides
General T/A/T±/A± apex concepts per branch **with (K_T; K_A; HS) numeric triples** and two worked
tetrads (Love/Hate, Hate/Benevolence). Authors' caveat: the triples "did not identify any useful
dependences". [P1 pp.18-19]
**Implementation:** `concerns/statement_classification.py:SYSTEMIC_TAXONOMY` (names match); rendered
as a hand-typed table in the same file's SYSTEM_PROMPT (drift hotspot).
**Status:** implemented (names) / absent (numeric triples)
**Notes:** The numeric (K_T;K_A;HS) triples are potential calibration/few-shot data for
`aspect_classification` — but the authors themselves found no useful dependences, so treat as
optional seed data, not a to-do.

### Elemental taxonomy (Fire/Earth/Air/Water)
**Theory:** Co-equal heuristic peer ("heuristic illustration, not a revival of classical doctrine");
full table with domain rows and worked Love/Hate instance. [P1 pp.20-21]
**Implementation:** `statement_classification.py:ELEMENTAL_TAXONOMY`.
**Status:** implemented
**Notes:** Confirms the memory note: peer taxonomy, NOT a validation lens; meaning URIs dispatch on
family token.

### "Abstraction" scalar per T/A pair
**Theory:** Per-tetrad scalar on HS-vs-|ΔK| plots (~0.9 for generic Integration/Disintegration,
~0.4-0.5 for concrete pairs) gauging how abstract the T–A pair is. [P1 p.20]
**Status:** absent
**Notes:** Presented as descriptive plot annotation, not a gating metric — low priority.

### Thesis reformulation ladder
**Theory:** Successive reformulations of one observation shift the whole tetrad; S1+ ≈ T2,
S2+ ≈ T3+ ("each synthesis suggests a deeper thesis"); repeated reformulation impractical —
poor initial T may "optimize the pathology". [P0 p.7, Table 4]
**Implementation:** — (no reformulation-depth concept; closest: Advisor `anchor` re-framing flow)
**Status:** absent
**Notes:** Conceptual guidance for Analyst/Advisor thesis intake more than a computable structure.
