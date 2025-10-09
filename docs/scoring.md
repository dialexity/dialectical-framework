# Dialectical Wheel Scoring

## Overview

The Dialectical Framework uses a hierarchical scoring system to rank any element ("assessable") in the dialectical structure. Each element receives a **Score (S)** that combines two fundamental dimensions:

* **Probability (P)** — structural feasibility. *Could this arrangement actually work?*
* **Relevance (R)** — contextual and factual alignment. *Does this make sense in this specific context or reality?*

The final score formula is: **Score = P × R^α**

Where **alpha (α ≥ 0)** is a global parameter controlling how much relevance influences the ranking.

## Scoring Architecture

The dialectical framework uses **dual aggregation paths** - one for relevance to context/reality, another for structural feasibility:

### Assessable Class Hierarchy

The scoring system is built on the `Assessable` protocol with the following inheritance structure:

**Abstract Protocols:**
- `Assessable` - Base protocol with score calculation (`Score = P × R^α`)
  - `Ratable` - Extends Assessable for leaf nodes with rating field

**Concrete Implementations:**
- **Leaf Assessables (Ratable):**
  - `DialecticalComponent` - Basic statements/concepts (T, A, T+, T-, A+, A-, S+, S-)
  - `Transition` - Relationships between components with predicates
  - `Rationale` - Evidence/commentary (special: soft exclusion instead of hard veto, evidence vs self-scoring views)

- **Composite Assessables:**
  - `AssessableCycle` - Abstract base for cycles (inherits from Assessable)
    - `Cycle` - Sequences of transitions between components
    - `Spiral` - Transformational cycles between segments
  - `WisdomUnit` - Thesis-antithesis pairs with synthesis and transformation
  - `Wheel` - Complete dialectical systems containing multiple WisdomUnits

**Key Behavioral Differences:**
- **Hard Veto Policy**: Components and transitions with zero values (R=0 or P=0) indicate structural impossibility and return 0
- **Soft Exclusion Policy**: Rationales with zero values are excluded from aggregation without vetoing parent elements
- **Single Rating Application**: Each element's rating is applied exactly once to prevent double-counting

### Content Hierarchy (Relevance flows upward)

**R tracks "Does this make sense in context or reality?"**

```
Level 4: Wheel
         ├─ Aggregates all WisdomUnit Rs
         ├─ Includes external Transition Rs (wheel-level connections)
         └─ Includes wheel-level Rationale Rs

Level 3: WisdomUnit
         ├─ Aggregates both WheelSegment Rs (T-side + A-side)
         ├─ Includes Transformation R (internal spiral)
         ├─ Includes Synthesis R
         └─ Includes unit-level Rationale Rs

Level 2: WheelSegment
         ├─ Aggregates DialecticalComponent Rs (T, T+, T-)
         └─ Includes segment-level Rationale Rs

Level 1: DialecticalComponent (leaf)
         ├─ Own R × own rating
         └─ Includes component-level Rationale Rs

         Transition (leaf)
         ├─ Own R × own rating
         └─ Includes transition-level Rationale Rs

         Rationale (evidence, can attach to ANY assessable)
         ├─ Own R (unweighted by rationale.rating)
         ├─ Child rationale Rs (critiques/counter-evidence)
         ├─ Spawned wheel Rs (deeper dialectical analysis)
         └─ Returns None if no real evidence (never invents neutral values)
```

### Structure Hierarchy (Probability flows upward)

**P tracks "Could this structural arrangement work?"**

```
Level 3: Wheel
         ├─ GM of canonical cycle probabilities (T, TA, Spiral)
         └─ Includes summary of WisdomUnit transformation probabilities

Level 2: Cycle
         └─ Product of member Transition probabilities (in sequence)

Level 1: Transition (leaf for probability)
         ├─ Manual probability × confidence
         └─ Transition-level rationale probabilities × confidence
         
         WisdomUnit (feeds into Wheel P)
         └─ Transformation probability (internal spiral product)

         Rationale (evidence, contributes to P when it has probability data)
         ├─ Own probability × confidence (if provided)
         ├─ Child/spawned wheel probabilities  
         └─ Returns None if no probability evidence (prevents empty rationale inflation)
```

### Key Architectural Principles

1. **Dual-Signal Design**: R tracks contextual and factual relevance (content), P tracks structural feasibility (relationships)
2. **Single Rating Application**: Each rating is applied exactly once to prevent double-counting
3. **Hierarchical Evidence**: P and R flow upward from specific elements to general containers
4. **Selective Veto Power**: Different element types have different veto behaviors for robustness
5. **Local Score Computation**: P and R aggregate hierarchically; the final Score is computed locally from that node's own P and R

## Complete Example: How Wheel Score is Calculated

```
Wheel: "Work Environment Optimization" (single WisdomUnit)
└── WisdomUnit: "Productivity vs Collaboration"
    ├── T-Segment (Thesis side):
    │   ├── T: "Remote work increases productivity" (R=0.8, rating=0.9)
    │   ├── T+: "Eliminates commute time" (R=0.9, rating=0.7)
    │   │   └── Rationale: "Average 54min daily savings" (R=0.9, rating=0.8, P=0.95, confidence=0.95)
    │   └── T-: "Can cause isolation" (R=0.6, rating=0.5)
    │       └── Rationale: "Mental health studies" (R=0.8, rating=0.7, P=0.75, confidence=0.8)
    │           └── Critique: "Confounds with pandemic effects" (R=0.5, rating=0.6)
    ├── A-Segment (Antithesis side):
    │   ├── A: "Office work enables collaboration" (R=0.7, rating=0.8)
    │   ├── A+: "Face-to-face communication" (R=0.8, rating=0.6)
    │   └── A-: "Requires physical presence" (R=0.5, rating=0.4)
    ├── Synthesis:
    │   ├── S+: "Hybrid model optimizes both" (R=0.85, rating=0.8)
    │   │   ├── Rationale: "Best of both worlds approach" (R=0.9, rating=0.9, P=0.8, confidence=0.8)
    │   │   └── Rationale: "Microsoft hybrid work data" (R=0.8, rating=0.7, P=0.85, confidence=0.9)
    │   │       └── Critique: "Corporate bias in reporting" (R=0.6, rating=0.5)
    │   └── S-: "Context switching overhead" (R=0.4, rating=0.3)
    └── Transformation (internal spiral: T- → A+ and A- → T+):
        ├── T-→A+: "Isolation → face-to-face need" (P=0.7, R=0.8)
        └── A-→T+: "Physical limits → remote benefits" (P=0.6, R=0.7)

External Transitions (wheel-level cycles):
├── T-Cycle: T → T (dummy cycle, single thesis)
│   └── Transition: T→T (trivial self-loop, P=1.0, R=1.0)
├── TA-Cycle: T → A → T (full dialectical)
│   ├── T→A: "Productivity needs → collaboration tools" (P=0.7, R=0.6)
│   │   └── Rationale: "Digital transformation necessity" (R=0.85, P=0.8, confidence=0.9)
│   └── A→T: "Collaboration insights → productivity" (P=0.6, R=0.5)
└── Spiral: T- → A+ and A- → T+ (same as WisdomUnit transformation)
    ├── T-→A+: "Isolation → face-to-face need" (P=0.7, R=0.8)
    └── A-→T+: "Physical limits → remote benefits" (P=0.6, R=0.7)
```

**Complete Scoring Calculation:**

**Step 1: Calculate Component Rs (including rationales)**

**Components with rationales:**
- **T**: 0.8 × 0.9 = 0.72
- **T+**: GM(0.9×0.7, 0.9×0.8) = GM(0.63, 0.72) = 0.67
- **T-**: Component has rationale with critique (auditor-wins):
  - Critique overrides rationale R → rationale returns R=0.5
  - Element applies rationale.rating → 0.5 × 0.7 = 0.35
  - Element aggregates: GM(0.6×0.5, 0.35) = GM(0.30, 0.35) = 0.32
- **A**: 0.7 × 0.8 = 0.56
- **A+**: 0.8 × 0.6 = 0.48
- **A-**: 0.5 × 0.4 = 0.20
- **S+**: Component has 2 rationales, one with critique (auditor-wins):
  - Rationale 1: R=0.9, rating=0.9 → contributes 0.9×0.9 = 0.81
  - Rationale 2: Has critique R=0.6 (overrides R=0.8), rating=0.7 → contributes 0.6×0.7 = 0.42
  - Element: GM(0.85×0.8, 0.81, 0.42) = GM(0.68, 0.81, 0.42) = 0.61
- **S-**: 0.4 × 0.3 = 0.12

**Step 2: WisdomUnit R** (symmetric pairs + synthesis + transformation)
- **T ↔ A pair**: PowerMean(0.72, 0.56, p=4) = 0.66
- **T+ ↔ A- pair**: PowerMean(0.67, 0.20, p=4) = 0.57
- **T- ↔ A+ pair**: PowerMean(0.32, 0.48, p=4) = 0.43
- **S+ ↔ S- pair**: PowerMean(0.61, 0.12, p=4) = 0.51
- Transformation R: GM(0.8, 0.7) = 0.75
- **WisdomUnit R** = GM(0.66, 0.57, 0.43, 0.51, 0.75) = 0.57

**Step 3: WisdomUnit P** (from Transformation)
- **Transformation P** = Product(0.7, 0.6) = 0.42
- **WisdomUnit P** = 0.42

**Step 4: External Transitions (Wheel Cycles)**
- **T-Cycle**: T→T transition P = 1.0, R = 1.0 (trivial dummy cycle)
- **TA-Cycle**:
  - T→A: R = GM(0.6, 0.85) = 0.71, P = GM(0.7, 0.8×0.9) = 0.71
  - A→T: R = 0.5, P = 0.6
  - **TA-Cycle P** = Product(0.71, 0.6) = 0.43
- **Spiral**: Same transitions as transformation = Product(0.7, 0.6) = 0.42

**Step 5: Wheel Aggregation**
- **Wheel R** = GM(WisdomUnit_r, TA_transition_rs)
  = GM(0.57, 0.71, 0.5) = 0.59
- **Wheel P** = GM(T_cycle_p, TA_cycle_p, Spiral_p, unit_transformations)
  = GM(1.0, 0.43, 0.42, 0.42) = 0.55

**Step 6: Final Score**
- **Wheel Score** (α=1) = 0.55 × 0.59 = **0.32**

**Note on Implementation Reality**: The actual implementation may produce values that vary from this worked example due to several factors:

1. Leaves (DialecticalComponent, Transition, Rationale) never invent neutral values - they return None when there's no evidence.
2. Empty rationales return None for both R and P calculations.
3. **Auditor-wins semantics**: When rationales have child rationales (critiques), the critiques override the parent rationale's values at the deepest level. Multiple critiques aggregate via weighted average (if rated) or GM (if unrated).
4. WisdomUnit axis R aggregation using power mean (p≈4) may produce slightly different values based on specific implementation details.
5. The final wheel score in actual implementation may be lower (around 0.15) due to differences in cycle probability calculations and transition probability contributions.

These implementation differences are expected and the key behaviors (leaves not inventing values, auditor-wins for critiques, power mean usage, axis veto) are correctly modeled in the system.

---

## Implementation Details

### Rationale Semantics: Evidence vs Audits

**Core Principle: Rationale P/R values assess the parent element, not the rationale itself.**

A `Rationale` object has three key fields: `relevance`, `probability`, and `rating`. Critically:
- **Rationale.relevance** = *"How relevant is THE PARENT ELEMENT (Component/Transition) to context?"*
- **Rationale.probability** = *"How feasible is THE PARENT ELEMENT's structural arrangement?"*
- **Rationale.rating** = *"How much weight/authority does this assessment carry?"*

These are **not** assessments of the rationale itself - they are assessments of the parent element, with the rationale providing the explanatory text/reasoning.

The framework uses rationales (the `rationales[]` array) with different semantics depending on the parent:

**Element → rationales[] (Evidence Aggregation)**

When an element (Component, Transition, etc.) has rationales, they are **independent evidence sources** that aggregate:

- **Element's own R/P**: Direct assessment of itself without explanation
- **Rationale R/P**: Assessment of the parent element with explanation text
- **Both assess the same target** (the parent element) - just with/without justification text
- All evidence aggregates via **Geometric Mean**: `GM(element_own × element_rating, rationale1 × rating1, rationale2 × rating2, ...)`
- Example:
  ```
  Component(R=0.8, rating=0.9)
  ├─ Rationale1(R=0.7, rating=0.8, text="Expert A: this component is 70% relevant because...")
  └─ Rationale2(R=0.6, rating=0.7, text="Expert B: this component is 60% relevant because...")

  All three assess THE COMPONENT's relevance:
  - Direct: Component says "I'm 80% relevant" (no justification)
  - Expert A: "Component is 70% relevant because..." (with justification)
  - Expert B: "Component is 60% relevant because..." (with justification)

  Final R = GM(0.8×0.9, 0.7×0.8, 0.6×0.7) ≈ 0.52
  # Geometric mean of all independent assessments OF THE COMPONENT
  ```

**Rationale → rationales[] (Audit Override)**

When a rationale has child rationales, they are **critiques/audits** with more context that override:

- Critiques **override** the parent rationale's values (auditor-wins semantics)
- The deepest level critique(s) win, recursively
- Multiple critiques at same level aggregate via:
  - Weighted average (if ratings exist): `Σ(critique_i × rating_i) / Σ(rating_i)`
  - Geometric mean (if no ratings): `GM(critique_1, critique_2, ...)`
- rating=0 means "ignore this critique"
- Example:
  ```
  Component(R=?, P=?) ← "What are this component's R and P?"
  └─ Rationale(R=0.9, P=0.8, text="Initial assessment: R=0.9, P=0.8 because...")
      └─ Critique(R=0.5, P=0.6, rating=0.9, text="Auditor: Actually R=0.5, P=0.6 because...")

  Both Rationale and Critique assess THE COMPONENT's R and P:
  - Rationale: "Component has R=0.9, P=0.8"
  - Critique: "No, component has R=0.5, P=0.6" (auditor correction)

  Final R = 0.5, P = 0.6
  # Auditor's assessment wins (more context/authority)
  ```

**Key Distinction:**

| Parent → Child | Semantic Relationship | Aggregation Method | Rating Applied By |
|---|---|---|---|
| **Element → Rationale** | Independent evidence sources | Geometric Mean | Parent (element) |
| **Rationale → Rationale** | Audit/critique override | Weighted avg or GM (deepest wins) | N/A (deepest critique wins) |

**Why This Makes Sense:**

When assessing a DialecticalComponent or Transition, you have multiple ways to provide evidence:

1. **Direct assessment** (Element's own R/P):
   - `Component(relevance=0.8, probability=0.9)`
   - Meaning: *"I assess this component's relevance as 0.8 and probability as 0.9"*
   - No explanation provided - just the numbers

2. **Rationalized assessment** (Element's rationales):
   - `Rationale(relevance=0.7, probability=0.85, text="Because of X, Y, Z...")`
   - Meaning: *"I assess THE COMPONENT's relevance as 0.7 and probability as 0.85, here's why..."*
   - Explanation provided - justified assessment

Both assess **the same target** (the parent element), so they aggregate as **independent evidence sources** via GM.

3. **Audit/critique** (Rationale's child rationales):
   - `Rationale(relevance=0.9) → Critique(relevance=0.5, rating=0.9)`
   - Meaning: *"Original assessment was 0.9, but auditor says actually it's 0.5"*
   - Critiques **override** the original assessment (auditor-wins), they don't aggregate with it

### Relevance (R) Implementation

**What R measures**: How well an element is grounded in the initial context (sources, constraints, goals) or aligned with reality. It is **not** likelihood; it's about contextual/factual fit and relevance.

#### Global R Policies

* **Hierarchical aggregation:** Non-leaves take the **geometric mean** of their immediate children
* **Neutral fallback:** Only non-leaf nodes apply neutral R=1.0 when their entire child set contributes nothing; leaves never invent R values
* **Single rating application:** Ratings are applied exactly once at the source:
  * A leaf's **own R** is multiplied by its **own rating** (only applies to DialecticalComponent and Transition)
  * A **rationale's R** is multiplied by **rationale.rating** by the consuming parent
  * Parents never multiply their own rating onto children
* **Selective veto policy:**
  * **DialecticalComponent/Transition**: Zero values (R=0 or P=0) trigger **hard veto** (return 0)
  * **Rationale**: Zero values (R=0 or P=0) are treated as "no contribution" (excluded, not veto)
* **Zero handling:** Zeros from weighting (rating = 0) and `None` values are **ignored** in aggregation

#### R Calculation by Element Type

**DialecticalComponent** *(leaf, `Ratable`)*

* Combine multiple **independent evidence sources** via Geometric Mean:
  * Component's **own R × its rating** (direct evidence without explanation)
  * Each **rationale R × rationale.rating** (evidence with explanation/reasoning)
* All evidence sources have **equal semantic role** - just with/without justification text
* If own R = 0 → hard veto (zero values ⇒ structural impossibility)
* If nothing contributes → returns None (default policy: DC.P defaults to 1.0 unless manually set)
* Example: `GM(component_R × component_rating, rationale1_R × rationale1_rating, ...)`

**Transition** *(leaf, `Ratable`)*

* Same rule as components: combine multiple **independent evidence sources** via Geometric Mean
  * Transition's **own R × its rating** (direct evidence)
  * Each **rationale R × rationale.rating** (evidence with explanation)
* Do **not** inherit R from source/target; R(Transition) answers "is this step grounded here?"
* If nothing contributes → returns None
* Example: `GM(transition_R × transition_rating, rationale1_R × rationale1_rating, ...)`

**Rationale** *(special leaf-that-can-grow)*

* **Auditor-wins semantics**: Rationale child rationales are **critiques/audits** that override:
  * If rationale has child rationales (critiques), the deepest critiques override the parent's values
  * Multiple critiques at same level aggregate via weighted average (if rated) or GM (if unrated)
  * rating=0 means "ignore this critique"
  * Recursive audits supported (deepest level wins)
* **Spawned wheels**: Wheels attached to rationale augment (GM) with critiques or original values
* **Evidence contribution**: When consumed by parent elements, returns critique consensus (if critiques exist) or own R/P with spawned wheels
* **No free lunch**: Returns nothing if no real evidence exists (prevents "empty rationale" inflation)
* **Rating application**: Parent applies the rationale's rating when consuming its evidence
* **Self-scoring**: When calculating its own score for ranking, uses same evidence without external rating
* **Soft exclusion**: Zero-value rationales (R=0 or P=0) are excluded from aggregation (no hard veto like components/transitions)

**WheelSegment** *(non-leaf)*

* R = GM of its three DialecticalComponents (+ rated segment-level rationales).

**WisdomUnit** *(non-leaf)*

* R = GM of:

  * **Dialectically symmetric component pairs** using power mean (p=4, soft max):
    * **T ↔ A**: Power mean of thesis and antithesis Rs
    * **T+ ↔ A-**: Power mean of positive thesis and negative antithesis Rs
    * **T- ↔ A+**: Power mean of negative thesis and positive antithesis Rs
    * **S+ ↔ S-**: Power mean of synthesis components (if present)
  * **Transformation R** (internal spiral transitions between segments),
  * **rated unit-level rationales**,

*Note: WisdomUnit R calculation treats thesis-antithesis pairs as dialectical axes, using symmetrized aggregation with power mean (p≈4). Power mean balances opposing poles while allowing dominance of stronger arguments. Any explicit hard veto (zero values) on a pole collapses that axis R to 0.0.*

**Cycle** *(T, TA, Spiral, Transformation — diagnostic)*

* R = GM of member **Transition Rs** (+ rated cycle-level rationales).
* **Do not** feed cycle Rs into the Wheel R (prevents double-counting transitions).

**Wheel**

* R = GM of:

  * **all WisdomUnit Rs** (they already include internal relations),
  * **all external Transition Rs** (edges across units),
  * **rated wheel-level rationales**.

### Using alpha with R

* **α = 0**: ignore R in scoring (Score depends only on P).
* **α = 1**: R influences score at a neutral strength.
* **α > 1**: emphasize R more (good R helps more; weak R hurts more).
  Pick one **global** α and keep it fixed; with α fixed, increasing either P or R strictly increases the Score.

---

### Probability (P) Implementation

**What P measures**: Structural feasibility of **relations and arrangements**. P flows along the **structure hierarchy**: transitions → cycles → wheel. Content nodes (components, segments) don't directly affect P.

#### Global P Policies

* **Structure-only flow:** P aggregates only along transitions and cycles, not content elements
* **Component default:** DialecticalComponent.P defaults to 1.0 (fact) unless manually set
* **Confidence weighting:** Applied only when aggregating rationale probabilities at transitions
* **No ratings in P:** Unlike R, probability calculations ignore rating values
* **Sequence veto behavior:** In cycles (sequences), any transition with P = 0 → entire cycle P = 0
* **Unknown propagation:** Any transition with P = None → cycle P = None
* **Aggregation handling:** At geometric mean points, skip `None` values but keep zeros

#### P Calculation by Element Type

**Transition** *(leaf for probability)*

* Combine as evidence:
  * **manual transition probability** (if provided), and
  * each **rationale probability** (from rationales attached to this transition)
* **Rationale evidence**: Rationale probability values are used when present
* **No "free lunch"**: Empty rationales (text-only, no probability) contribute nothing to probability
* Aggregate with geometric mean over **positive** contributions; if nothing contributes → P = unknown

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

The **alpha (α)** parameter controls how much Relevance influences the final score:

* **α = 0**: Score = P only (ignore relevance, pure structural feasibility)
* **α = 1**: Score = P × R (balanced weighting of structure and relevance)
* **α > 1**: Score = P × R^α (emphasize relevance - high relevance helps more, low relevance hurts more)

**Recommendation**: Use α = 1 as default. Increase α when contextual/factual expertise is highly reliable; decrease toward 0 when focusing purely on structural relationships.

---

## Summary

The dialectical scoring system provides a robust, hierarchical approach to ranking dialectical elements by:

1. **Separating concerns**: R measures contextual/factual relevance, P measures structural feasibility
2. **Respecting hierarchy**: Information flows upward through appropriate aggregation paths
3. **Preventing double-counting**: Single application of ratings and confidence weights
4. **Handling uncertainty**: Selective veto policies for robustness and proper fallbacks
5. **Local score computation**: Each element computes its own score using its aggregated P and R with the global α parameter

**Key Implementation Principle**:
* **R** flows up the **content hierarchy** (components → segments → units → wheel)
* **P** flows up the **structure hierarchy** (transitions → cycles → wheel)
* **Score** is computed **locally** at each element using Score = P × R^α

---

## Relevance (R) by Assessable Type

**DialecticalComponent**: *"How well does this statement/concept fit the specific situation or reality?"*
- Domain expertise, situational relevance, stakeholder alignment, factual accuracy

**Transition**: *"How contextually appropriate or realistic is this relationship/step?"*
- Cultural fit, timing appropriateness, stakeholder readiness for this change, logical connection

**Cycle**: *"How relevant is this pattern/sequence to the current context or reality?"*
- Historical precedent, organizational maturity, environmental conditions, natural occurrence

**Rationale**: *"How relevant is this evidence/reasoning to the context or facts?"*
- Source credibility, recency, applicability to situation, factual alignment

**Wheel**: *"How well does this entire dialectical framework fit the problem space or reality?"*
- Comprehensive alignment across all dimensions, both contextual and factual

## Probability (P) by Assessable Type

**DialecticalComponent**: *"How likely is this statement to be valid/true?"*
- Empirical support, logical consistency, expert consensus

**Transition**: *"How likely is this relationship/change to actually occur?"*
- Causal strength, prerequisite conditions, historical success rates

**Cycle**: *"How likely is this cyclical pattern to complete/sustain?"*
- Structural integrity, feedback loop strength, systemic stability

**Rationale**: *"How credible/reliable is this evidence?"*
- Source reliability, methodological rigor, reproducibility

**Wheel**: *"How feasible is this entire system of relationships?"*
- Structural coherence, resource requirements, implementation complexity

## Practical Implications

This means scoring interpretation should be context-sensitive:

```
Transition Score: 0.75 | R=0.90 | P=0.83
↓
"This change step is highly appropriate for your culture/context (R=0.90)
and very likely to succeed structurally (P=0.83)"

vs.

Component Score: 0.75 | R=0.90 | P=0.83
↓
"This concept fits your situation or reality perfectly (R=0.90)
and has strong empirical support (P=0.83)"
```

---

## Score Discrimination and Decision Making

### Challenge: Similar Composite Scores

When comparing assessables with similar composite scores (difference <0.05), the standard **Score = P × R^α** formula may compress different risk/reward profiles into nearly identical values, making decisions difficult:

```
Option A: S=0.36 | R=0.90 | P=0.40  (High-relevance, high-risk)
Option B: S=0.35 | R=0.50 | P=0.70  (Moderate-relevance, lower-risk)
```

### Decision Framework by Score Difference

**Clear Winner** (difference >0.1): Trust the composite score
```
Wheel A: S=0.65 → Choose A (substantially better)
Wheel B: S=0.32
```

**Probable Winner** (difference 0.05-0.1): Consider composite score + profile fit
```
Wheel A: S=0.45 → Likely choose A, but verify P/R profile matches needs
Wheel B: S=0.38
```

**Strategic Choice** (difference <0.05): Ignore composite score, analyze P/R profiles
```
Wheel A: S=0.36 | R=0.90 | P=0.40 → Choose based on risk tolerance and strategic context
Wheel B: S=0.35 | R=0.50 | P=0.70
```

### Alternative Scoring Approaches for Better Discrimination

When standard scoring yields insufficient discrimination, consider:

**1. Adjusted Alpha Values**
- **α = 1.5-2.0**: Emphasizes relevance more heavily
- **α = 0.5**: Emphasizes structural feasibility more heavily
- Creates clearer numerical separation between options

**2. Risk-Adjusted Scoring**
```
balance_penalty = 1 - abs(P - R)
adjusted_score = P × R × balance_penalty
```
Penalizes highly imbalanced P/R profiles, favoring more balanced approaches.

**3. Geometric Mean Approach**
```
geometric_score = √(P × R)
```
Treats P and R equally, naturally penalizes extreme values in either dimension.

**4. Confidence-Weighted Scoring**
```
uncertainty = abs(P - R)
confidence = 1 / (1 + uncertainty)
confidence_score = (P × R) × confidence
```
Reduces scores when P and R diverge significantly, indicating higher uncertainty.

### Recommendation

For most applications, **adjusting α** provides the best balance of interpretability and discrimination:
- **α = 1.0**: Balanced weighting (default)
- **α = 1.5-2.0**: When contextual/factual expertise is highly reliable
- **α = 0.5**: When focusing on structural relationships over relevance