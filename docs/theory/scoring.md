# Scoring & Metrics — Theory → Implementation

Companion to `docs/scoring.md` (implementation-side reference). This page maps the *paper's* metric
set onto the code and names every divergence.

### K / Ks — complementarity
**Theory:** K_T, K_A ∈ [0,1] complementarity toward T/A; Eq (2): `Ks = (K_T + K_A)/2`. 11-band
scoring prompt. [P0 p.10]
**Implementation:** `concerns/scoring_scales.py:COMPLEMENTARITY_SCALE`; K_T/K_A persisted on
`AspectRelationship` edges; Ks computed (`graph/nodes/perspective.py`).
**Status:** implemented

### SP — Synthesis Potential (= code `area`)
**Theory:** Eq (3): `SP = Ks(T+) + Ks(A+) − Ks(T−) − Ks(A−)` — "dialectical work", hysteresis-loop
area analogy. [P0 p.11]
**Implementation:** `graph/nodes/perspective.py:area` — formula identical.
**Status:** diverges (naming only)
**Notes:** The paper's canonical name is SP; the repo says `area` everywhere. Same quantity. When
communicating with theory-literate users or reading the papers, SP ≡ area. A rename is churn for
zero behavior — record the synonym instead.

### Rectangularity
**Theory:** Paper form is LINEAR: `Rectangularity = 1 − [|Ks(T+)−Ks(A+)| + |Ks(T−)−Ks(A−)|]`
(higher = more balanced) — and the paper reports it was NOT a successful discriminator. [P1 S1.5-1.6]
**Implementation:** `graph/nodes/perspective.py:rectangularity` =
`(Ks(T+)−Ks(A+))² + (Ks(T−)−Ks(A−))²` (lower = better).
**Status:** diverges (formula form AND polarity of "good")
**Notes:** Deliberate-looking divergence: squared penalty, no 1− inversion. Since the paper itself
rejected its linear version, the code's variant is a local empirical choice, not an implementation
bug. Documented so nobody "fixes" either direction blindly. Theory connection (2026-08-01): under
the paper's linear approximation `M(X) ≈ Ks(X) − Ks_avg` [P0 p.11], rectangularity = 0 is exactly
Rule 3.2's modality-balance chain Eq (1) — the squared and linear forms have identical zero-sets,
so this holds despite the formula divergence. See generative-rules.md Rule 3.2 for why balance is
measured but deliberately not enforced.

### HS — Heuristic Similarity (+ MHS)
**Theory:** Similarity to taxonomy apex; appears in taxonomy triples [P1 p.19] and sub-synthesis
scoring as **MHS = Mean Heuristic Similarity** aggregating aspect-level HS (e.g. S1+ "Mature Love"
MHS 0.84±0.03). Within a taxonomy row K varies modestly while HS varies widely. [P1 pp.18-20]
**Implementation:** `concerns/scoring_scales.py:HS_SCALE`; assignment rules per position (T=1.0,
A/aspects/Ac+/Re+ LLM-scored) — see CLAUDE.md and `docs/scoring.md`.
**Status:** implemented (HS) / absent (MHS aggregation)
**Notes:** MHS becomes relevant only with Sa/Sb/Sc sub-syntheses (transformations-synthesis.md).

### CC — Conceptual Coherence
**Theory:** 0–1 heuristic AI estimate to reject inconsistent suggestions; empirically LESS reliable
than DV. [P0 pp.10-12]
**Implementation:** `concerns/control_statements_check.py` (CC on control statements);
`CONCEPTUAL_COHERENCE_THRESHOLD` in `graph/nodes/estimation.py`.
**Status:** implemented (narrow scope)
**Notes:** Code uses CC only for control-statement/transition coherence, not as a general
per-statement acceptance score. Given the paper's own reliability caveat, the narrow use is sound.

### DV — Dialectical Validity
**Theory:** 0–1, "naturalness and dialectical balance", complements CC; paper's acceptance gate is
**SP > 0.5 AND DV > 0.5**; DV tracks SP better than CC ("Generally, DV parameter performed better
than CC" [P1 S1.7]) and is more model-stable (Orwellian: CC 0.85 Gemini vs 0.15 GPT; DV 0.00 vs
0.05 [P1 S1.7-2]). Verbatim prompt anchors in S1.7 [P1 p.11]. [P0 p.12]
**Implementation:** `concerns/control_statements_check.py` — each control-statement evaluation
scores CC and DV together (paper's verbatim 1.0/0.0 anchors in the DTO field description +
prompt); persisted as `DialecticalValidityEstimation` (`graph/nodes/estimation.py`) on the
Perspective. Surfaced next to `area` in `dialectical_context` (`DV=`), `inspect_node`, and the
Advisor's score-reading section.
**Status:** implemented (annotation only — deliberately no DV > 0.5 gate)
**Notes:** Added 2026-08-01. The paper's DV > 0.5 gate is NOT adopted (per-LLM calibration, same
stance as every other threshold — see "Gates"). DESIGN FORK, recorded in
`CoherenceEvaluationDto`'s docstring: CC and DV are scored in the SAME LLM call (zero extra cost)
while the paper used separate prompts; if real-LLM checks against the S1.7 reference values show
the two scores anchoring on each other (the paper's own data separates them sharply on
Orwellian-style cases), split DV into its own call (+2 calls per perspective). Reference-value
spot-check lives in `tests/test_dialectical_validity_real_llm.py` (`--real-llm`).

### MMI — Mind-Matter Index
**Theory:** 0 = matter ontologically primary, 1 = mind primary; low → optimize within ontology,
high → revise ontology; drives tetrad selection among same-pair alternatives (Rule 3.4); quadrant
model S±×MMI (Innovative Construction / Integral Synergy / Technocracy / Dogmatic Ideology). 21
worldview archetypes with (MMI;PSI) coordinates as calibration set. [P0 pp.12-14; P1 S1.6-1.8]
**Implementation:** —
**Status:** absent

### PSI — (S+/S− index)
**Theory:** 11-point anchored scale with 5-question rubric, scored per statement/worldview; pairs
with MMI in the quadrant model. [P1 S1.8]
**Implementation:** —
**Status:** absent
**Notes:** PSI+MMI+archetype set is the "ontology profiling" machinery (generative-rules.md Rule 3.4).

### PC — Perceived Complementarity
**Theory:** [0,1], verbatim prompt: "Estimate the extent to which the commonly perceived meaning of
T fosters A+." Multi-model average (±0.1). Low PC across a culture's core concepts ⇒ S−-biased
conceptualization. Vocabulary: A+ labeled "Obligation" relative to T. [P0 pp.29-30; P1 pp.49-50]
**Implementation:** —
**Status:** absent
**Notes:** Distinct from K: scores *common perception* of T, not in-context complementarity.

### Div — semantic divergence
**Theory:** 0–1 divergence between Materialist and Idealist formulations. [P0 p.13]
**Status:** absent

### Feasibility (P) / sequences / Self-Reg
**Theory:** Each admissible causal sequence scored P ∈ (0,1); threshold **P ≥ 0.5 = feasible**
(per-LLM calibration: GPT 0.5 ≈ Gemini 0.2); `No≥0.5` (count of feasible sequences) proxies
self-regulatory capability, inversely correlated with log(people involved); conditional prompt
"estimate practical feasibility of step x in the presence of steps y1, y2, …"; transition
feasibility rises with wheel size (mutual reinforcement). [P0 pp.19-22; P1 pp.23-24,35-39]
**Implementation:** `concerns/causality/*` (CausalityEstimation scores cycle plausibility);
`concerns/transformation_audit.py` (per-transformation feasibility annotation).
**Status:** partial
**Notes:** Both scoring sites exist but: (a) causality scoring is not the paper's conditional
in-presence-of prompt; (b) no 0.5 feasibility threshold/`No≥0.5` aggregate anywhere; (c) neither
gates — both annotate. The mutual-reinforcement hypothesis (feasibility ↑ with thesis count) is
untested in code.

### Mode / Arousal values
**Theory:** Mode = thesis-lessness ladder value; Arousal ∈ [0,1] activation. [P0 pp.7-8]
**Implementation:** `antithesis_classification.py:MODE_FIELDS`, `AROUSAL_VALUES`; persisted via
`EstimationManager.upsert_estimation` (caller's duty — see CLAUDE.md checklist).
**Status:** implemented

## Gates — paper vs live pipeline

| Gate | Paper | Code | Status |
|------|-------|------|--------|
| Tetrad acceptance | SP > 0.5 AND DV > 0.5 [P0 p.12] — soft ("Biased < 0.5, balanced > 0.2 is only a heuristic"; no universal cutoff exists) | HS ≥ 0.7 (`_rank_polarities`, `HS_THRESHOLD`) + empirical bands diff ≥ 0.1, Ks(+) > 0.4, Ks(−) < 0.6 (`perspective_validation.py`, wired live 2026-07 as a non-blocking flag in `ExpandPolarity._validate_and_flag` → `Perspective.validation`; prompts deprioritize "failed", nothing is dropped). ALSO: the Advisor context dump soft-prunes standalone perspectives on **SP < 0.3 OR DV < 0.3** (`dialectical_context._apply_quality_floor`, `advisor_perspective_quality_min_sp`/`_dv`, since 2026-08-01) — the paper's SP∧DV pair as render-time pruning with deliberately conservative floors (not 0.5), graph untouched, `inspect_node` reaches everything | **partial convergence** (generation still flags on CC+empirical bands; the Advisor render path now prunes on the paper's SP+DV pair at conservative floors) |
| Sequence viability | P ≥ 0.5 [P1 p.35] | CausalityEstimation scores, no threshold gate | partial |
| Consolidation | — | HS ≥ 0.7 merge / 0.1 suggest (`antithetical_thesis_detection.py`) | code-only |

**Notes:** The gate divergence is the most consequential scoring finding. The live pipeline gates on
HS (opposition quality), the paper gates on SP+DV (tetrad quality). These measure different things
at different pipeline stages; the paper's own caveat (no universal SP cutoff, all LLM-dependent)
means adopting SP/DV>0.5 verbatim would be naive. Recorded as `diverges`, resolution is a product
decision, not a bug fix.
