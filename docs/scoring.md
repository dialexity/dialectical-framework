# Dialectical Wheel Scoring

## Overview

The Dialectical Framework uses a hierarchical scoring system to rank any element ("assessable") in the dialectical structure. Each element receives a **Score (S)** that combines two fundamental dimensions:

* **Probability (P)** — structural feasibility. *Could this arrangement actually work?*
* **Contextual Fidelity (CF)** — contextual grounding. *Does this mak. e sense in this specific context?*

The final score formula is: **Score = P × CF^α**

Where **alpha (α ≥ 0)** is a global parameter controlling how much contextual fidelity influences the ranking.

## Scoring Architecture

The dialectical framework uses **dual aggregation paths** - one for contextual relevance, another for structural feasibility:

### Content Hierarchy (Contextual Fidelity flows upward)

**CF tracks "Does this make sense in context?"**

```
Level 4: Wheel
         ├─ Aggregates all WisdomUnit CFs
         ├─ Includes external Transition CFs (wheel-level connections)  
         └─ Includes wheel-level Rationale CFs

Level 3: WisdomUnit  
         ├─ Aggregates both WheelSegment CFs (T-side + A-side)
         ├─ Includes Transformation CF (internal spiral)
         ├─ Includes Synthesis CF
         └─ Includes unit-level Rationale CFs

Level 2: WheelSegment
         ├─ Aggregates DialecticalComponent CFs (T, T+, T-)
         └─ Includes segment-level Rationale CFs

Level 1: DialecticalComponent (leaf)
         ├─ Own CF × own rating
         └─ Includes component-level Rationale CFs

         Transition (leaf)
         ├─ Own CF × own rating  
         └─ Includes transition-level Rationale CFs

         Rationale (evidence, can attach to ANY assessable)
         ├─ Own CF (unweighted by rationale.rating)
         ├─ Child rationale CFs (critiques/counter-evidence)
         └─ Spawned wheel CFs (deeper dialectical analysis)
```

### Structure Hierarchy (Probability flows upward)

**P tracks "Could this structural arrangement work?"**

```
Level 3: Wheel
         ├─ GM of canonical cycle probabilities (T, TA, Spiral)
         ├─ Includes summary of WisdomUnit transformation probabilities
         └─ Wheel-level rationales can provide probability evidence

Level 2: Cycle  
         ├─ Product of member Transition probabilities (in sequence)
         └─ Cycle-level rationales can provide probability evidence

Level 1: Transition (leaf for probability)
         ├─ Manual probability × confidence
         └─ Transition-level rationale probabilities × confidence
         
         WisdomUnit (feeds into Wheel P)
         ├─ Transformation probability (internal spiral product)
         └─ Unit-level rationales can provide probability evidence

         Rationale (evidence, contributes to P when it has probability data)
         ├─ Own probability × confidence (if provided)
         └─ Child/spawned wheel probabilities
```

### Key Architectural Principles

1. **Dual-Signal Design**: CF tracks contextual relevance (content), P tracks structural feasibility (relationships)
2. **Single Rating Application**: Each rating is applied exactly once to prevent double-counting
3. **Hierarchical Evidence**: Information flows upward from specific elements to general containers
4. **Selective Veto Power**: Different element types have different veto behaviors for robustness
5. **Local Computation**: Scores are computed locally at each node, never averaged from children

## Complete Example: How Wheel Score is Calculated

```
Wheel: "Work Environment Optimization" (single WisdomUnit)
└── WisdomUnit: "Productivity vs Collaboration"
    ├── T-Segment (Thesis side):
    │   ├── T: "Remote work increases productivity" (CF=0.8, rating=0.9)
    │   ├── T+: "Eliminates commute time" (CF=0.9, rating=0.7)
    │   │   └── Rationale: "Average 54min daily savings" (CF=0.9, rating=0.8, P=0.95, confidence=0.95)
    │   └── T-: "Can cause isolation" (CF=0.6, rating=0.5)
    │       └── Rationale: "Mental health studies" (CF=0.8, rating=0.7, P=0.75, confidence=0.8)
    │           └── Critique: "Confounds with pandemic effects" (CF=0.5, rating=0.6)
    ├── A-Segment (Antithesis side):
    │   ├── A: "Office work enables collaboration" (CF=0.7, rating=0.8)
    │   ├── A+: "Face-to-face communication" (CF=0.8, rating=0.6)
    │   └── A-: "Requires physical presence" (CF=0.5, rating=0.4)
    ├── Synthesis:
    │   ├── S+: "Hybrid model optimizes both" (CF=0.85, rating=0.8)
    │   │   ├── Rationale: "Best of both worlds approach" (CF=0.9, rating=0.9, P=0.8, confidence=0.8)
    │   │   └── Rationale: "Microsoft hybrid work data" (CF=0.8, rating=0.7, P=0.85, confidence=0.9)
    │   │       └── Critique: "Corporate bias in reporting" (CF=0.6, rating=0.5)
    │   └── S-: "Context switching overhead" (CF=0.4, rating=0.3)
    └── Transformation (internal spiral: T- → A+ and A- → T+):
        ├── T-→A+: "Isolation → face-to-face need" (P=0.7, CF=0.8)
        └── A-→T+: "Physical limits → remote benefits" (P=0.6, CF=0.7)

External Transitions (wheel-level cycles):
├── T-Cycle: T → T (dummy cycle, single thesis)
│   └── Transition: T→T (trivial self-loop, P=1.0, CF=1.0)
├── TA-Cycle: T → A → T (full dialectical)  
│   ├── T→A: "Productivity needs → collaboration tools" (P=0.7, CF=0.6)
│   │   └── Rationale: "Digital transformation necessity" (CF=0.85, P=0.8, confidence=0.9)
│   └── A→T: "Collaboration insights → productivity" (P=0.6, CF=0.5)
└── Spiral: T- → A+ and A- → T+ (same as WisdomUnit transformation)
    ├── T-→A+: "Isolation → face-to-face need" (P=0.7, CF=0.8)
    └── A-→T+: "Physical limits → remote benefits" (P=0.6, CF=0.7)
```

**Complete Scoring Calculation:**

**Step 1: Calculate Component CFs (including rationales)**

**Components with rationales:**
- **T**: 0.8 × 0.9 = 0.72
- **T+**: GM(0.9×0.7, 0.9×0.8) = GM(0.63, 0.72) = 0.67
- **T-**: GM(0.6×0.5, GM(0.8,0.5×0.6)×0.7) = GM(0.30, 0.34) = 0.32
- **A**: 0.7 × 0.8 = 0.56
- **A+**: 0.8 × 0.6 = 0.48  
- **A-**: 0.5 × 0.4 = 0.20
- **S+**: GM(0.85×0.8, 0.9×0.9, GM(0.8,0.6×0.5)×0.7) = GM(0.68, 0.81, 0.34) = 0.58
- **S-**: 0.4 × 0.3 = 0.12

**Step 2: WisdomUnit CF** (all components + synthesis + transformation)
- All Components: GM(0.72, 0.67, 0.32, 0.56, 0.48, 0.20) = 0.49
- Synthesis: GM(0.58, 0.12) = 0.26
- Transformation CF: GM(0.8, 0.7) = 0.75
- **WisdomUnit CF** = GM(0.49, 0.26, 0.75) = 0.47

**Step 3: WisdomUnit P** (from Transformation)
- **Transformation P** = Product(0.7, 0.6) = 0.42
- **WisdomUnit P** = 0.42

**Step 4: External Transitions (Wheel Cycles)**
- **T-Cycle**: T→T transition P = 1.0, CF = 1.0 (trivial dummy cycle)
- **TA-Cycle**: 
  - T→A: CF = GM(0.6, 0.85) = 0.71, P = GM(0.7, 0.8×0.9) = 0.71
  - A→T: CF = 0.5, P = 0.6
  - **TA-Cycle P** = Product(0.71, 0.6) = 0.43
- **Spiral**: Same transitions as transformation = Product(0.7, 0.6) = 0.42

**Step 5: Wheel Aggregation**
- **Wheel CF** = GM(WisdomUnit_cf, TA_transition_cfs)
  = GM(0.47, 0.71, 0.5) = 0.55
- **Wheel P** = GM(T_cycle_p, TA_cycle_p, Spiral_p, unit_transformations)
  = GM(1.0, 0.43, 0.42, 0.42) = 0.55

**Step 6: Final Score**
- **Wheel Score** (α=1) = 0.55 × 0.55 = **0.30**

---

## Implementation Details

### Contextual Fidelity (CF) Implementation

**What CF measures**: How well an element is grounded in the initial context (sources, constraints, goals). It is **not** likelihood; it's about contextual fit and relevance.

#### Global CF Policies

* **Hierarchical aggregation:** Non-leaves take the **geometric mean** of their immediate children
* **Neutral fallback:** If nothing contributes at a node → CF = **1.0** (neutral)
* **Single rating application:** Ratings are applied exactly once at the source:
  * A leaf's **own CF** is multiplied by its **own rating**
  * A **rationale's CF** is multiplied by **rationale.rating** by the consuming parent
  * Parents never multiply their own rating onto children
* **Selective veto policy:**
  * **DialecticalComponent/Transition**: CF = 0 triggers **hard veto** (CF becomes 0)
  * **Rationale**: CF = 0 is treated as "no contribution" (ignored, not veto)
* **Zero handling:** Zeros from weighting (rating = 0) and `None` values are **ignored** in aggregation

#### CF Calculation by Element Type

**DialecticalComponent** *(leaf, `Ratable`)*

* Combine:

  * its **own CF × its rating** (if provided; 0 ⇒ hard veto), and
  * each **rationale CF × rationale.rating**.
* If nothing contributes → CF = 1.0.

**Transition** *(leaf, `Ratable`)*

* Same rule as components (combine own CF×rating with rated rationales).
* Do **not** inherit CF from source/target; CF(Transition) answers “is this step grounded here?”

**Rationale** *(special leaf-that-can-grow, `Ratable`)*

* **Combine**:

  * its **own CF** (unweighted here), and
  * CFs of its **children** (spawned wheels and critiques).
* The **parent** later multiplies by `rationale.rating`.
* If nothing contributes → CF = 1.0.

**WheelSegment** *(non-leaf)*

* CF = GM of its three DialecticalComponents (+ rated segment-level rationales).

**WisdomUnit** *(non-leaf; may be `Ratable`)*

* CF = GM of:

  * **both segments’ CFs**,
  * **one internal-relations CF** = GM of the unit’s **two internal transitions** (summarized once),
  * **rated unit-level rationales**,

**Cycle** *(T, TA, Spiral, Transformation — diagnostic)*

* CF = GM of member **Transition CFs** (+ rated cycle-level rationales).
* **Do not** feed cycle CFs into the Wheel CF (prevents double-counting transitions).

**Wheel**

* CF = GM of:

  * **all WisdomUnit CFs** (they already include internal relations),
  * **all external Transition CFs** (edges across units),
  * **rated wheel-level rationales**.

### Using alpha with CF

* **α = 0**: ignore CF in scoring (Score depends only on P).
* **α = 1**: CF influences score at a neutral strength.
* **α > 1**: emphasize CF more (good CF helps more; weak CF hurts more).
  Pick one **global** α and keep it fixed; with α fixed, increasing CF always increases the Score.

---

### Probability (P) Implementation

**What P measures**: Structural feasibility of **relations and arrangements**. P flows along the **structure hierarchy**: transitions → cycles → wheel. Content nodes (components, segments) don't directly affect P.

#### Global P Policies

* **Structure-only flow:** P aggregates only along transitions and cycles, not content elements
* **Confidence weighting:** Applied only when aggregating rationale probabilities at transitions
* **No ratings in P:** Unlike CF, probability calculations ignore rating values
* **Sequence veto behavior:** In cycles (sequences), any transition with P = 0 → entire cycle P = 0
* **Unknown propagation:** Any transition with P = None → cycle P = None
* **Aggregation handling:** At geometric mean points, skip `None` values but keep zeros

#### P Calculation by Element Type

**Transition** *(leaf for probability)*

* Combine as evidence:

  * **manual transition probability** (optional, can be weighted by the transition’s own `confidence`), and
  * each **rationale probability × rationale.confidence**.
* Aggregate with geometric mean over **positive** contributions; if nothing contributes → P = **unknown**.

**Cycle** *(T, TA, Spiral, Transformation)*

* P = **product** of member **Transition** probabilities (in order).
* Any edge 0 ⇒ cycle 0. Any edge unknown ⇒ cycle unknown.
* No cycle-level opinions in probability.

**WisdomUnit**

* P = probability of its **Transformation** cycle (the two internal transitions)
* Represents the structural feasibility of the thesis-antithesis dialectical relationship

**Wheel**

* P = **geometric mean** over canonical cycle probabilities (T, TA, Spiral cycles)  
* Include internal relations **once** via geometric mean of all WisdomUnit transformation probabilities
* Keep zeros (hard constraints); skip unknowns (insufficient data)
* If all canonical cycles are unknown → wheel P = unknown

### Alpha Parameter Usage

The **alpha (α)** parameter controls how much Contextual Fidelity influences the final score:

* **α = 0**: Score = P only (ignore contextual grounding, pure structural feasibility)
* **α = 1**: Score = P × CF (balanced weighting of structure and context)  
* **α > 1**: Score = P × CF^α (emphasize contextual grounding - good context helps more, poor context hurts more)

**Recommendation**: Use α = 1 as default. Increase α when contextual expertise is highly reliable; decrease toward 0 when focusing purely on structural relationships.

---

## Summary

The dialectical scoring system provides a robust, hierarchical approach to ranking dialectical elements by:

1. **Separating concerns**: CF measures contextual fit, P measures structural feasibility
2. **Respecting hierarchy**: Information flows upward through appropriate aggregation paths  
3. **Preventing double-counting**: Single application of ratings and confidence weights
4. **Handling uncertainty**: Neutral fallbacks and selective veto policies for robustness
5. **Local computation**: Each element computes its own score using the global α parameter

**Key Implementation Principle**: 
* **CF** flows up the **content hierarchy** (components → segments → units → wheel)
* **P** flows up the **structure hierarchy** (transitions → cycles → wheel)  
* **Score** is computed **locally** at each element using Score = P × CF^α
