# Dialectical Wheel Scoring

## Contextual Fidelity (CF)
Contextual fidelity (CF) measures how well an element of the dialectical framework is grounded in the initial context. It is not about likelihood (probability), but about the quality of contextual fit.

**Computation Principle:**
* **Everything is `Assessable`.**
* **Leaves are `Ratable`:** `DialecticalComponent`, `Transition`, `Rationale` (special; can later grow children).
* **Aggregation:** Non-leaves take the **geometric mean (GM)** of **immediate children** CFs.
* **Neutral fallback:** If nothing contributes → **CF = 1.0**.
* **Ratings apply exactly once at the source:**

  * Leaf’s **own CF** is multiplied by **its own `rating`**.
  * **Rationale CF** is multiplied by **`rationale.rating` by the parent** when aggregating rationales.
  * Parents never multiply their own rating onto children.
* **Zero handling:**

  * **Leaf own CF = 0** with rating>0 ⇒ **hard veto** (leaf CF = 0).
  * Zeros arising from weighting (e.g., rating=0) ⇒ **skip** (no contribution) to avoid brittle veto.
  * Drop `None`/`≤0` before GM (except the explicit leaf veto above).

**Why hierarchical?**

The framework explicitly structures assessable elements (e.g. `DialecticalComponent` -> `WheelSegment` -> `WisdomUnit` -> `Wheel`). Hierarchical aggregation respects this structure, treating each sub-entity as a coherent unit. Flattening all fidelities into one pool would erase dialectical organization and distort grounding.
