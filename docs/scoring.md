# Dialectical Wheel Scoring

This framework ranks any element (“assessable”) by combining two ideas:

* **Probability (P)** — structural feasibility. *Could this structure happen?*
* **Contextual Fidelity (CF)** — contextual grounding. *Does this make sense **here**?*

A global knob **alpha (α ≥ 0)** controls how strongly CF influences the ranking.
**Score (S)** is computed **locally** for each element (we never average child scores). Higher P or CF (with α fixed) produces a higher score.

**Why hierarchical?**
The wheel is a structured object (components → segments → units → cycles → wheel). We respect that shape by aggregating **evidence upward**:

* **CF** aggregates along the **content branch** (what the thing is).
* **P** aggregates along the **structure branch** (how things connect).
  This keeps each signal interpretable and avoids double-counting.

---

## Contextual Fidelity (CF)

### What CF means

CF measures how well an element is grounded in the initial context (sources, constraints, goals). It is **not** likelihood; it’s about fit and relevance.

### Global CF policies

* **Hierarchical aggregation:** non-leaves take the **geometric mean** of their **immediate children**.
* **Neutral fallback:** if nothing contributes at a node → CF = **1.0** (neutral).
* **Ratings apply exactly once, at the source:**

  * A leaf’s **own CF** is multiplied by its **own `rating`**.
  * A **rationale’s CF** is multiplied by **`rationale.rating` by the parent** that consumes it.
  * Parents never multiply their own rating onto children.
* **Zeros & unknowns:**

  * **Leaf own CF = 0** (DialecticalComponent or Transition) is a **hard veto** at that leaf.
  * Zeros created by weighting (e.g., rating = 0) and `None` values are **ignored** in aggregation.

### CF by element

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

## Probability (P)

### What P means

P measures structural feasibility of **relations/arrangements**. It flows along **transitions → cycles → wheel**. Content nodes don’t affect P.

### Global P policies

* **Confidence applies only when a parent Transition aggregates rationale probabilities.**
* **No ratings** in probability.
* **Zeros & unknowns:**

  * In a **sequence** (cycle), any edge with P = 0 ⇒ cycle P = 0; any edge with P unknown ⇒ cycle P unknown.
  * At aggregation points that average multiple items, skip `None`, keep zeros.

### P by element

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

* P = probability of its **Transformation** cycle (the two internal transitions).

**Wheel**

* P = **geometric mean** over a **fixed canonical set** of cycle probabilities (for example: T, TA, Spiral).
* Include internal relations **once** by appending **one** extra term: the geometric mean of all unit Transformation probabilities. Don’t add one term per unit.
* Keep zeros; skip unknowns. If all canonical cycles are unknown → wheel P = unknown.

---

**In practice:**

* **CF** climbs the **content** hierarchy (components → segments → units → wheel).
* **P** climbs the **structure** hierarchy (transitions → cycles → wheel).
* **Score** is computed **locally** everywhere using fixed α.
* **Ratings** affect **CF** only; **confidence** affects **P** only (at transitions).
  This keeps the system transparent, modular, and resistant to double-counting.
