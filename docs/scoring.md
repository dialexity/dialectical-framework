# Scoring & Visualization Guide

Reference for UI implementors: how to score dialectical entities, what "good" and "bad" look like, and how to lay out the molecular visualization.

---

## Metrics by Entity

### Thesis (T)

The thesis defines the polarity axis. It IS the reference point.

| Metric | Value | Notes |
|--------|-------|-------|
| HS | Always 1.0 | Tautological — T defines its own apex |

No quality metrics — a thesis is the starting axiom.

---

### Antithesis (A)

The antithesis opposes the thesis. Its quality determines polarity strength.

| Metric | Range | What it measures |
|--------|-------|------------------|
| **HS** | 0.0–1.0 | How well A captures the antithesis apex concept |
| **Mode** | 0.0–1.0 | Type of opposition (privation → negation) |
| **Arousal** | 0.1–0.9 | Tension visibility/intensity |

**HS Scale:**

| Range | Quality |
|-------|---------|
| 0.9–1.0 | Perfect antithesis — exemplary |
| 0.7–0.9 | Strong — captures most of the apex |
| 0.5–0.7 | Moderate — some aspects, acceptable |
| 0.3–0.5 | Weak — still valid, poor quality |
| 0.1–0.3 | Very weak — barely an antithesis |
| 0.0–0.1 | Invalid — wrong category entirely |

**Mode Scale (opposition mechanism):**

| Value | Type | Description |
|-------|------|-------------|
| 1.0 | Negation | Direct, active opposition |
| 0.9 | Inversion | Reversal of T's meaning |
| 0.8 | Devaluation | Diminishing T's worth |
| 0.7 | Hollowing | Emptying T of substance |
| 0.6 | Corruption | Degrading/perverting T |
| 0.5 | Distortion | Twisting T's form |
| 0.4 | Skew | Imbalancing T |
| 0.3 | Blocking | Obstructing T |
| 0.2 | Suppression | Holding T down |
| 0.1 | Distancing | Drifting from T |
| 0.0 | Privation | Complete absence of T |

**Arousal Scale (tension activation):**

| Value | Label | Description |
|-------|-------|-------------|
| 0.9 | Active | Fully manifest, immediate |
| 0.8 | Intense | Very active, urgent |
| 0.7 | High | Strong, clearly visible |
| 0.6 | Elevated | Becoming prominent |
| 0.5 | Moderate | Balanced, present tension |
| 0.4 | Mild | Noticeable but subdued |
| 0.3 | Low | Background tension |
| 0.2 | Latent | Barely perceptible |
| 0.1 | Dormant | Completely invisible |

---

### Polarity (T + A container)

The polarity is a container. Its quality is determined by the antithesis:

| Indicator | Source | Good | Bad |
|-----------|--------|------|-----|
| Tightness of opposition | HS_A | High (0.7+) | Low (<0.5) |
| Directness | Mode | Context-dependent | Context-dependent |
| Aliveness | Arousal | Context-dependent | Context-dependent |

Mode and Arousal are characterization, not quality — a "dormant" polarity isn't necessarily bad, it's just latent.

---

### Aspects (T+, T-, A+, A-)

Each aspect has three complementarity scores plus HS:

| Metric | Range | What it measures |
|--------|-------|------------------|
| **HS** | 0.0–1.0 | Similarity to taxonomy apex for that position |
| **K_T** | 0.0–1.0 | How well the aspect complements the thesis |
| **K_A** | 0.0–1.0 | How well the aspect complements the antithesis |
| **Ks** | 0.0–1.0 | Combined: (K_T + K_A) / 2 — complementarity toward synthesis |

**Ks interpretation:**
- 0.0 = Actively undermines the system
- 0.5 = Neutral
- 1.0 = Strongly enhances the whole

**Expected pattern for a balanced tetrad:**

| Position | K_T | K_A | Ks | Pattern |
|----------|-----|-----|-----|---------|
| T+ | High | Low-ish | Mid-high | Favors T but complements A somewhat |
| A+ | Low-ish | High | Mid-high | Favors A but complements T somewhat |
| T- | Low | Mid | Low | Undermines T, doesn't help A |
| A- | Mid | Low | Low | Undermines A, doesn't help T |

(A theory heuristic sometimes cited is K_T + K_A ≈ 1.0 per aspect in ideal systems, but
nothing in code computes or enforces this — K_T and K_A are scored independently.)

---

### Perspective (full tetrad)

Computed from the four aspects' Ks values:

| Metric | Formula | Range | Good | Bad |
|--------|---------|-------|------|-----|
| **diff_t** | Ks(T+) − Ks(T−) | −1 to 1 | ≥ 0.1 | < 0.1 |
| **diff_a** | Ks(A+) − Ks(A−) | −1 to 1 | ≥ 0.1 | < 0.1 |
| **area** | diff_t + diff_a | −2 to 2 (well-formed tetrads ~0 to 2) | ≥ 0.7 | < 0.3 |
| **area_normalized** | area / 2 | −1 to 1 (well-formed tetrads ~0 to 1) | ~0.5 | ~0.15 |
| **rectangularity** | [Ks(T+)−Ks(A+)]² + [Ks(T−)−Ks(A−)]² | 0+ | < 0.01 | > 0.09 |

**Empirical inequalities (pass/fail):**

1. `diff_t ≥ 0.1` AND `diff_a ≥ 0.1`
2. `|diff_t − diff_a| ≤ 0.15`
3. `Ks(T+) > 0.4` AND `Ks(A+) > 0.4`
4. `Ks(T−) < 0.6` AND `Ks(A−) < 0.6`

**Structural validity checks (pass/fail):**

| Check | Threshold | What it tests |
|-------|-----------|---------------|
| Conceptual Coherence (CC) | **both** control scores ≥ 0.7 | "T+ without A+ yields T−" and "A+ without T+ yields A−" |
| Diagonal Contradiction | both ≥ 0.7 | T+ vs A− and A+ vs T− are genuine contradictions |

CC stores the *average* of the two control scores as its `value`, but the pass/fail
criterion is that **each** score clears 0.7 (`ConceptualCoherenceEstimation.is_coherent`)
— 0.5 + 0.9 does not pass. Diagonal Contradiction is **not** part of the standard
`PerspectiveValidation` run; it is an extra LLM call that only fires on user-edited
tetrads (`edit_perspective`). Generated tetrads are never gated on it.

**Quality tiers** (suggested UI grouping — not a built-in framework ranking; see note below):

| Tier | Criteria |
|------|----------|
| **Invalid** | Fails CC (Diagonal Contradiction, too, but only on user-edited tetrads) |
| **Bad** | Fails any empirical inequality |
| **Good** | Passes all checks |
| **Best** | Passes all + highest area_normalized + lowest rectangularity |

**Ranking, in practice:** these tiers and an `area_normalized` ordering are guidance for
a UI — the framework does **not** implement them. The only ranking in code is
`AnalysisPipeline._rank_polarities`, which orders polarities by their antithesis
`heuristic_similarity` against a soft `HS_THRESHOLD = 0.7` (if nothing clears it, the top
few are expanded anyway). If a UI wants to order valid tetrads, `area_normalized` (0–1,
higher = better) gated by the validity checks is a reasonable choice, with rectangularity
as a tiebreaker.

---

### Transitions (Ac+, Ac−, Re+, Re−)

| Metric | Range | What it measures |
|--------|-------|------------------|
| **Insight** | 0.0–1.0 | Depth of understanding in the transition |
| **Proactiveness** | 0.0–1.0 | How actionable/practical the transition is |
| **Feasibility** | 0.0–1.0 | Practical achievability |
| **HS** | 0.0–1.0 | Similarity of Ac+/Re+ to their derived apex |

**Insight scale (Y-axis — depth of transformation):**

| Value | Level | Character |
|-------|-------|-----------|
| 1.0 | Transcendence | Paradigm shift |
| 0.9 | Redirection | Fundamental change |
| 0.8 | Inversion | Flipping perspective |
| 0.7 | Anticipation | Acting ahead |
| 0.6 | Leverage | Using leverage points |
| 0.5 | Composition | Combining elements |
| 0.4 | Reformulation | Restructuring approach |
| 0.3 | Variation | Deliberate small changes |
| 0.2 | Tuning | Fine-tuning |
| 0.1 | Procedure | Following protocol |
| 0.0 | Reflex | Automatic response |

**Proactiveness scale (X-axis — action vs reflection):**

| Value | Level | Zone |
|-------|-------|------|
| 0.0 | Observation | Re (reflection) |
| 0.1 | Detection | Re |
| 0.2 | Interpretation | Re (apex zone) |
| 0.3 | Framing | Re |
| 0.4 | Evaluation | Midpoint |
| 0.5 | Coordination | Ac (action) |
| 0.6 | Intervention | Ac (apex zone) |
| 0.7 | Implementation | Ac |
| 0.8 | Configuration | Ac |
| 0.9 | Governance | Ac |
| 1.0 | Stewardship | Ac |

**Feasibility scale:**

| Range | Meaning |
|-------|---------|
| 0.9–1.0 | Highly achievable |
| 0.7–0.8 | Moderately feasible |
| 0.5–0.6 | Challenging but achievable |
| 0.3–0.4 | Extremely difficult |
| 0.0–0.2 | Practically impossible |

---

### Cycles & Wheels

| Metric | Range | What it measures |
|--------|-------|------------------|
| **Causality Probability** | 0.0–1.0 | Plausibility of this causal ordering vs alternatives |

The value **stored on a Cycle or Wheel is the raw LLM plausibility score** (0.0–1.0), not
a normalized one. Normalization to a layer-relative share (siblings sum to 1.0) is applied
only to Wheel **Transitions** (nth-root decomposed) and is otherwise computed on the fly
for display (raw `P` vs normalized `%`). A UI reading the estimation directly off a
Cycle/Wheel gets the raw score.

---

## Molecular Visualization

The perspective is displayed as a molecule with T and A as the nucleus and aspects as bonded satellites.

### Coordinate System

**No formal X-axis.** This is a spatial/relational layout, not a chart. Only vertical position (Ks) is a true metric axis.

### Layout Rules

| Element | Position/Distance | Encoded metric |
|---------|-------------------|----------------|
| T ↔ A distance | `1 − HS_A` | Polarity quality (tight = good) |
| Aspect vertical position | Ks value | Complementarity toward synthesis |
| Aspect bond length to parent | `1 − K_parent` | Affinity to parent concept |
| Trapezoid shape | Connect T+→A+→A−→T− | Area + rectangularity visible |

**"K_parent" means:**
- For T+ and T−: bond length = `1 − K_T`
- For A+ and A−: bond length = `1 − K_A`

### What "Good" Looks Like

```
                Ks
                 ↑
                 │
         T+ ○━━━━━━━━○ A+        ← Both high Ks (~0.6–0.7)
            ╲       ╱              ← Short bonds (high K)
             T●━━━●A               ← Close together (HS_A = 0.85)
            ╱       ╲              ← Short bonds
         T- ○━━━━━━━━○ A-        ← Both low Ks (~0.2–0.3)
                 │
                 └──────

   ✓ Compact nucleus (high HS_A → strong opposition)
   ✓ Tall vertical gap (high area → clear differentiation)
   ✓ Flat top/bottom edges (low rectangularity → balanced)
   ✓ Short bonds (high K → tight complementarity)
   ✓ Symmetric left/right
```

### What "Bad" Looks Like

```
                Ks
                 ↑
                 │
         T+ ○                       ← High Ks (0.7)
              ╲
               ╲ (long bond)
                T●                          ●A    ← Far apart (HS_A = 0.4)
                                           ╱ ╲
                                     ○ A+     ╲   ← Mid Ks (0.45)
                                               ╲
         T- ○                            ○ A-  ← A- very low (0.15)
                 │
                 └──────

   ✗ Sprawling nucleus (low HS_A → weak opposition)
   ✗ Tilted shape (high rectangularity → imbalanced sides)
   ✗ Long bonds (low K → aspects loosely related)
   ✗ Small vertical gap on one side (low area)
   ✗ Asymmetric — T-side taller than A-side
```

### What "Mediocre" Looks Like

```
                Ks
                 ↑
                 │
         T+ ○━━━━━━○ A+          ← Mid Ks (~0.50, 0.55)
            ╲     ╱
             T●━●A                ← Moderate closeness (HS_A = 0.7)
            ╱     ╲
         T- ○━━━━━━○ A-          ← Mid Ks (~0.35, 0.40)
                 │
                 └──────

   ~ Decent nucleus (acceptable HS_A)
   ~ Small vertical gap (low area = 0.30 → weak differentiation)
   ~ Shape is rectangular but flat (aspects mushed together)
   ~ Bonds mid-length
```

### Visual Cue Summary

| Visual property | Metric | Good | Bad |
|-----------------|--------|------|-----|
| T-A closeness | HS_A | Close (< 0.3 gap) | Far (> 0.5 gap) |
| Vertical gap (+ row vs − row) | area | Tall (> 0.7) | Squished (< 0.3) |
| Top/bottom edge horizontality | rectangularity | Flat (< 0.01) | Tilted (> 0.09) |
| Bond lengths to parent | K_T / K_A | Short (K > 0.6) | Long (K < 0.3) |
| Overall compactness | Combined | Dense molecule | Straggling/diffuse |

### Secondary Annotations (not spatial)

| Property | Encoding suggestion |
|----------|---------------------|
| Mode | Color/icon on T-A bond (e.g., negation=red, privation=grey) |
| Arousal | Bond thickness or pulse animation |
| HS of aspects | Node size or opacity |
| CC validity | Green/red border on the tetrad quadrilateral |
| Diagonal contradiction | Diagonal dashed lines with check/cross |

---

## Geometric Interpretation (from theory)

The paper (Generative Rules for Dialectical Synthesis) establishes:

1. The tetrad forms a **trapezoid** when plotted with Ks on the vertical axis and T-side / A-side on the horizontal.

2. In practice, no tetrad is a perfect rectangle. The goal is a trapezoid **approaching rectangular shape** with **maximum surface area**.

3. Balanced tetrads (A and D in Fig. 4) produce **near-rectangular trapezoids** where like-signed components occupy comparable Ks levels.

4. Distorted tetrads produce **skewed, twisted, or compressed trapezoids** — the shape visually communicates what's wrong:
   - **Compressed** = low area, aspects not well-differentiated
   - **Tilted** = high rectangularity, one side overdeveloped
   - **Narrow** = low HS_A, weak polarity foundation

5. Selection criterion: **"the best one typically shows trapezoid that is most similar to rectangular with the largest surface area"** (paper, p. 10).

---

## Quality Summary Table

| Entity | Primary quality metric | Threshold | Secondary |
|--------|----------------------|-----------|-----------|
| Thesis | — | — | Defines the axis |
| Antithesis | HS_A | > 0.7 good, > 0.1 valid | Mode, Arousal |
| Aspect | Ks | T+/A+ > 0.4, T−/A− < 0.6 | HS, K_T, K_A |
| Perspective | area_normalized | ~0.5 excellent, ~0.35 good | rectangularity, CC, diagonals |
| Transition | Feasibility | > 0.7 feasible | Insight, Proactiveness, HS |
| Cycle/Wheel | Causality Probability | Raw on the node; layer-relative `%` (sum = 1.0) computed for display | — |
