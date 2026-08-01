# Generative Rules — Theory → Implementation

The paper's constraint network (Table 3 [P0 pp.5-6], rule numbers theirs). CLAUDE.md's
"Theoretical Foundation" section is the promoted summary of this page.

### Rule 1-2: Thesis & antithesis selection
**Theory:** A is T's negation or *semantic/functional opposition* — "more than the mere absence of T";
if T implies a function, A functionally opposes it; multiple antitheses possible; A often a process
not an entity. [P0 p.5]
**Implementation:** `concerns/antithesis_extraction.py:AntithesisExtraction` (functional-opposition
framing in candidates prompt); `concerns/statement_classification.py:StatementClassification`
(SIMPLE→mechanical negation vs COMPLEX→taxonomy path).
**Status:** implemented
**Notes:** "Multiple antitheses per thesis" as a deliberate device (Conceptual Shifts Table
[P1 p.49] — Truth×Falsehood vs Truth×Imagination as distinct tetrads) is **absent**: the model
holds one A per Polarity; alternatives exist only as separate polarities, with no linkage that they
share a thesis by design.

### Rule 3.1: Tetradic structure + diagonal contradiction
**Theory:** Every T–A interaction yields (T+,A+) upsides and (T−,A−) exaggerations such that
T+ directly contradicts A− and T− directly contradicts A+. [P0 p.5] Strength-matching: all
components need equal argumentative/affective strength [P0 p.3].
**Implementation:** `concerns/scoring_scales.py:ASPECT_DEFINITIONS` (single source);
`concerns/aspect_generation.py` (generation constraints);
`concerns/diagonal_oppositions_check.py:DiagonalOppositionsCheck`;
`statement_classification.py:get_contradiction_pair`.
**Status:** implemented
**Notes:** Strength-matching ("equal argumentative AND affective strengths") is only implicitly
covered via modality/Ks balance — no explicit strength-parity check at generation time.

### Rule 3.2: Equal modalities (modality balance)
**Theory:** S+ occurs iff all components have equal absolute modalities. Eq (1):
`M(T+) = −M(T−) = M(A+) = −M(A−)` [P0 p.10]; linear approximation
`M(X) ≈ Ks(X) − (Ks)_Avg` [P0 p.11].
**Implementation:** —
**Status:** absent
**Notes:** No prompt or check enforces the zero-sum. The `M(X) ≈ Ks(X) − Ks_avg` approximation
means it COULD be computed from persisted K_T/K_A without new LLM calls — cheapest wiring path
if ever needed. Do not let prompts claim modality balance is enforced (see df-review-reasoning-layer).

### Rule 3.3: Control statements
**Theory:** "T+ without A+ yields T−; A+ without T+ yields A−" must make sense. [P0 p.5]
Variant at neutral-T level: "T without A+ yields T−"; truth criterion "T is true iff it fosters A+"
[P0 p.29]. Caution: strengthening T+ directly strengthens A−, flipping T+ into T− [P0 p.30].
**Implementation:** `concerns/control_statements_check.py:ControlStatementsCheck` (aspect level,
CC-scored); invoked live from `skills/edit_perspective.py:_validate_tetrad_coherence` (user edits,
blocking) AND from `skills/expand_polarities.py:_validate_and_flag` via `PerspectiveValidation`
(generation path, non-blocking flag on `Perspective.validation`). The neutral-T variant + truth
criterion are encoded in `ASPECT_DEFINITIONS` (`concerns/scoring_scales.py`) — "What T itself
degenerates into when A+ is absent" on the "−" definitions plus the explicit truth-criterion line
— reaching every aspect prompt via the shared constant. The backfire dynamic ("strengthening T+
directly strengthens A−, flipping T+ into T−") is a prompt constraint in
`concerns/transformation_generation.py` ("Never propose direct reinforcement of a '+' aspect").
**Status:** implemented
**Notes:** All three paper claims of this rule are encoded: aspect-level statements (CC-scored on
both live paths — edits gate; generation flags, deliberate since CC is the paper's less-reliable
coherence metric), neutral-T variant (2026-07-31, via `ASPECT_DEFINITIONS`, locked by
`TestSharedScoringConstants::test_aspect_definitions_carry_neutral_degeneration`), backfire
constraint (2026-07-31, locked by `TestBackfireConstraint`). The "S+ without lower-layer support
yields S−" TODO in `synthesis_generation.py` is Rule 7 material (control-statement *style* at
synthesis level, no paper 3.3 anchor), tracked there.

### Rule 3.4: Ontology profiling (MMI-driven tetrad selection)
**Theory:** S± outcomes depend on worldview assumptions estimable via empirical indices; the same
T/A pair yields Materialist/Unconstrained/Idealist tetrads, all passing SP/DV>0.5, distinguished
by MMI. [P0 pp.5,12-13]
**Implementation:** —
**Status:** absent
**Notes:** See scoring.md → MMI/PSI. Would be a tetrad-*selection* layer above ExpandPolarity.

### Rule 4.1-4.2: Equal-sign synthesis + different-sign isolation
**Theory:** S+ between T+/A+; S− between T−/A−. No direct interaction T+/A−, T−/A+ (contradictions),
nor T+/T−, A+/A− (levels of same phenomenon); positive–negative interactions are developmental
transitions, not synthesis. [P0 p.5]
**Implementation:** `concerns/synthesis_generation.py:SynthesisGeneration` — S+ derived from Ac+/Re+
spiral, S− from Ac−/Re−, AND the like-signed principle is stated as an explicit prompt constraint
("Like-signed inputs only… Never synthesize across opposite signs").
**Status:** implemented
**Notes:** Was correct-by-construction only (input routing); the explicit constraint was added
2026-07-31 so the rule holds even if synthesis inputs ever broaden. Locked by
`TestEqualSignSynthesisConstraint` in `tests/test_prompt_review_regressions.py`.

### Rule 4.3-4.4: S+ / S− definitions
**Theory:** S+ iff dimensionality increases while preserving stability, distinction, normative
coherence; S− iff existing dimensions are maximized through dominance or oscillation (faster
formation, finite lifespan). [P0 p.6] Operational wording: S+ = "1+1>2" synergy; S− = "1+1<2"
anti-synergy [P1 pp.40-41]; S− also triggered by executing transformations in reverse order [P1 p.41].
**Implementation:** `concerns/synthesis_generation.py:SYSTEM_PROMPT` (emergence-vs-trap framing).
**Status:** implemented (definitions) / absent (reverse-order S− trigger)
**Notes:** The reverse-order trigger relates to `OPPOSITE_DIRECTION` wheels (each opposite produces
its own synthesis) but is a sharper claim: *executing* a valid loop backwards yields S−. Nothing
encodes execution-order semantics.

### Rule 5.1: Circular causality
**Theory:** S+ requires simultaneous conversion T−→A+ and A−→T+ (closed reciprocal loop). [P0 p.6,16]
**Implementation:** `concerns/transformation_generation.py` (Ac+/Re+ definitions + coherence
constraint); `concerns/positive_ac_re_apex_derivation.py`; wheel spiral in
`skills/explore_transformations.py`.
**Status:** implemented
**Notes:** Directionality (Ac+=T−→A+, Re+=A−→T+) is restated in 4+ prompts with no single owner —
drift risk tracked in df-review-reasoning-layer's map.

### Rule 5.2: Transition tetrad (Ac±/Re± as a recursive tetrad)
**Theory:** Ac(T→A), Re(A→T), Ac+(T−→A+), Re+(A−→T+), Ac−(T+→A−), Re−(A+→T−); Ac±/Re± form "a new
tetrad obedient to rules 3.1–3.3": **Ac+ must directly contradict Re−, Ac− must directly contradict
Re+**; degeneration: "Ac+ without Re+ degenerates into Ac−; Re+ without Ac+ degenerates into Re−".
[P0 pp.6,16-17]
**Implementation:** `concerns/transformation_generation.py` (generates Ac+/Ac−/Re+/Re−; encodes the
degeneration rule and CC on transitions).
**Status:** partial
**Notes:** Generation produces all four positions and the degeneration coherence, but the diagonal
contradiction *within the transition tetrad* (Ac+⊥Re−, Ac−⊥Re+) is not checked the way
`DiagonalOppositionsCheck` checks aspect tetrads. See transformations-synthesis.md.

### Rules 6-7: Multi-thesis wheel geometry
**Theory:** In circular ordering of {T1..Tn, A1..An}, each Ti/Ai diametrically opposite. Valid
4-element sequences: T1→T2→A1→A2 and T1→A2→A1→T2; T1→A1→T2→A2 prohibited. Permutations reduce
(2n)! → 2ⁿ·n!/2n (≈3ⁿ-fold). [P0 p.6,17,19]
**Implementation:** `generate_compatible_sequences` (diagonal symmetry T_i opposite A_i);
`graph/repositories/` rotation-invariance; layer combinatorics in CLAUDE.md
(`C(N,k)·(k−1)!·W(k)`, W(1..4)=1,2,4,8).
**Status:** implemented
**Notes:** Paper's 2ⁿ·n!/2n and the repo's W(k) table should be formally reconciled once
(spot-check: n=2 → 2²·2!/4 = 2 sequences per starting point matches W(2)=2... verify for k=3,4).
The paper treats admissible sequences as scored *scenarios of one wheel*; the repo materializes
them as distinct Wheel nodes sharing rotation-invariant identity. Same math, different reification —
document, don't "fix".

### Rule 8: Transitions' Matrix (full negative×positive cross-product)
**Theory:** Optimization lives in the **4n² transitions** mapping every negative pole to every
positive pole; Ac+/Re+ are special cases. Verbatim generation prompts + row/column compression
into "child-clear principles" [P0 pp.6,18,24; P1 p.42].
**Implementation:** — (only the two diagonal transitions per edge pair exist)
**Status:** absent
**Notes:** The single biggest structural gap. The graph model (Transformation per edge pair) has no
cross-tetrad transition concept, and no principles/ontology compression layer. See
transformations-synthesis.md for the full sub-map. Worked examples in the paper score cross-tetrad
transitions HIGHER than within-tetrad ones (A4−→T1+ 0.93 [P0 p.22]) — theory considers them
first-class, not exotic.

### Operating-layer dynamics (pathological vs healthy)
**Theory:** Pathological systems operate in the minus layer (T1−→T2−→…), rigidly coupled to
diagonal pairs by symmetry; healthy systems operate in the plus layer with free transitions to any
positive pole; blocked systems may reorganize around another orthogonal pair. [P0 p.20]
**Implementation:** —
**Status:** absent
**Notes:** Diagnostic vocabulary (which layer is the system in?) rather than a generative rule;
natural fit for Advisor/Explorer score-reading guidance if ever surfaced.
