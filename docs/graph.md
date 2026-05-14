# Graph Data Model

Graph-native dialectical framework using Memgraph/Neo4j.

## Node Hierarchy

```
Perspective → Cycle → Wheel (edges) → Transformation
     │          │        │               │
   (tetrad)  (T-cycle) (TA-cycle)    (per-edge)
                         │
                    Synthesis (0-N)
```

**Simplified model:**
- **Perspective**: Tetrad (T, A, T+, T-, A+, A-) — atomic polar structure
- **Cycle**: T-cycle — ordered sequence of PPs defining abstract thesis causality
- **Wheel**: TA-cycle — concrete arrangement with edges between statements
- **Transformation**: Action-Reflection structure per edge (Ac, Re, Ac+, Ac-, Re+, Re-)

**Evolution model:**
- Cycles evolve by adding PPs to the pool (Cycle → `evolutions` → child Cycle)
- Wheels grow in layers within a Cycle's pool (Wheel → `evolutions` → child Wheel)
- All wheels in an evolution chain point to the same parent Cycle

## Core Nodes

| Node | Purpose | Key Relationships |
|------|---------|-------------------|
| **Statement** | Atomic statement | `oppositions`, `positive_side_of`, `negative_side_of`, `source_of`, `target_of` |
| **Perspective** | Thesis-antithesis tetrad | `t`, `a`, `t_plus`, `t_minus`, `a_plus`, `a_minus` |
| **Cycle** | T-cycle (ordered PP pool) | `perspective_hashes`, `wheels`, `evolutions`, `evolved_from` |
| **Wheel** | TA-cycle implementation | `cycle`, `_edges`, `evolutions`, `evolved_from` |
| **Transition** | Edge between statements | `source`, `target`, `cycle` (→Wheel) |
| **Transformation** | Action-Reflection per edge | `edge` (→Transition), `ac_re`, `synthesis` (0-N) |
| **Synthesis** | Emergent S+/S- pair | `s_plus`, `s_minus`, `target` (→Transformation) |
| **Rationale** | Evidence/explanation | `explanation`, `critiques`, `provided_estimations` |
| **Estimation** | P/R values | `target` (→AssessableEntity via ESTIMATES), `_provider` (←Rationale via PROVIDES) |
| **Input** | Content source | `has_statements`, `ideas` |
| **Ideas** | Distilled concepts from Input | `input` (→Input), `has_statements` |
| **Case** | Multi-input exploration | `inputs` (→Input), `get_vocabulary()` |

**DEPRECATED** (kept for backwards compatibility):
- **Nexus**: Replaced by Cycle storing PP hashes directly
- **Spiral**: Replaced by Transformations on edges

## Intent Levels

All reasoning nodes inherit from `IntentMixin`, providing a unified `intent: Optional[str]` field. Intent maps to the reflective practice framework:

| Level | Reflection | Question | Lives On | Example Intent |
|-------|------------|----------|----------|----------------|
| **Discovery** | (Gathering) | What sources to explore? | Ideas | "economic_articles", "ethical_perspectives" |
| **Focus** | What? | What tensions exist? | Cycle | "economic_vs_social", "sustainability" |
| **Dynamics** | So What? | Why do they matter? | Cycle (intent field) | "preset:balanced", "preset:realistic" |
| **Path** | Now What? | How to navigate? | Perspective, Transformation, Wheel | "preset:general_concepts", "growth_based" |
| **Synthesis** | (Outcome) | What emerges? | Synthesis | "practical_compromise" |

**Nodes with IntentMixin:** Ideas, Cycle, Perspective, Transformation, Synthesis, Wheel

**Intent inheritance:** Wheels inherit intent from parent Wheel (via `evolved_from`) or from Cycle. Use `get_effective_intent()` to resolve.

**Intent enables grouping:** Explicit intent on the graph allows finding explorations with similar focus, grouping by dynamics, and making the graph a readable analysis artifact. Presets like "preset:balanced" or "preset:realistic" serve as defaults but can be replaced with natural language.

## Transformation Model

**Transformations belong to edges (Transitions)**, not Perspectives:

```
Wheel
├── Edge 1 (T1- → A2+) ── Transformation (Ac+, Re+, ...)
├── Edge 2 (A2- → T1+) ── Transformation (Ac+, Re+, ...)
├── Edge 3 (T2- → A1+) ── Transformation (Ac+, Re+, ...)
└── Edge 4 (A1- → T2+) ── Transformation (Ac+, Re+, ...)
```

**Action-Reflection structure** (6 positions per Transformation):
- **Ac** (Action): T → A
- **Ac+** (Positive Action): T- → A+ (REQUIRED)
- **Ac-** (Negative Action): T+ → A-
- **Re** (Reflection): A → T
- **Re+** (Positive Reflection): A- → T+ (REQUIRED)
- **Re-** (Negative Reflection): A+ → T-

**Each edge can have multiple Transformation alternatives** at different insight/proactiveness levels.

### Layered Transformation Computation

Transformations use parent wheel's Transformations as computation context (coarse → fine refinement):

```
Layer 1:  Wheel(PP1) ── Transformation (coarse)
              │
Layer 2:  Wheel(PP1,PP2) ── Transformation (refines Layer 1)
              │
Layer 3:  Wheel(PP1,PP2,PP3) ── Transformation (refines Layer 2)
```

**Context is snapshot-based:** The parent's Transformations are input to computing child Transformations. No bidirectional feedback.

## Evolution Model (Layered Growth)

### Cycle Evolution

Cycles evolve by adding Perspectives to the pool:

```
Cycle [PP1] ──evolutions──► Cycle [PP1, PP2] ──evolutions──► Cycle [PP1, PP2, PP3]
```

**Note:** Adding a PP can create multiple child Cycles with different orderings:
- Cycle [PP1, PP2] + PP3 → Cycle [PP1, PP2, PP3] (different causalities possible)

### Wheel Evolution (Layered Growth)

Wheels grow in layers within a Cycle's PP pool:

```
Given Cycle [PP1, PP2, PP3]:

Layer 1:  Wheel(PP1)    Wheel(PP2)    Wheel(PP3)
              │             │             │
Layer 2:  Wheel(PP1,PP2)  ...          ...
              │
Layer 3:  Wheel(PP1,PP2,PP3)
```

**All wheels in an evolution chain point to the same parent Cycle.**

### Wheel Reuse

Wheels with the same PP set (rotation-invariant hash) are reused across branches:

```
             Cycle A                    Cycle B
                │                          │
    Wheel(PP1,PP2) ◄─────────────────► Wheel(PP1,PP2)  [SAME wheel reused]
```

**Rotation-invariant:** `Wheel(PP1→PP2)` and `Wheel(PP2→PP1)` hash to the same canonical form.

### Intent Inheritance

Resolve intent via `get_effective_intent()`:
1. This wheel's intent (if set)
2. Parent wheel's effective intent (via `evolved_from`)
3. Parent Cycle's effective intent
4. Default ("preset:balanced")

## Case Layer

The Case layer provides multi-input exploration before Perspective construction:

```
Case (multi-input exploration)
├── HAS_INPUT → Input₁
│              └── DISTILLED_TO → Ideas₁ (intent: "thesis_extraction")
│                                └── HAS_STATEMENT → Statements...
├── HAS_INPUT → Input₂
│              └── DISTILLED_TO → Ideas₂ (intent: "antithesis_extraction")
└── get_vocabulary() → All statements in scope (uses DI scope)
```

### Key Concepts

| Node | Purpose | Cardinality |
|------|---------|-------------|
| **Case** | Multi-input exploration with shared vocabulary | HAS_INPUT (1, ∞) to Input |
| **Ideas** | Distilled concepts from a single Input | DISTILLED_TO (1, 1) from Input |

**Ideas as filtered lens:** Each Ideas node represents a specific distillation of an Input (e.g., "thesis concepts", "ethical implications"). Multiple Ideas nodes can point to the same Input with different intents.

**Vocabulary:** `repo.get_vocabulary()` returns all Statements in the current scope. This enables cross-input Perspective construction.

### Usage

```python
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.statement_repository import (
    StatementRepository
)
from dialectical_framework.graph.scope_context import scope

# Create case (scope root)
case = Case()
case.commit()

with scope(case.sid):
    # Create inputs (inherit sid from scope)
    input_a = Input(content="https://article.com/pro")
    input_b = Input(content="https://article.com/con")
    input_a.commit()
    input_b.commit()
    case.inputs.connect(input_a)
    case.inputs.connect(input_b)

    # Create ideas
    ideas_thesis = Ideas(intent="thesis_extraction")
    ideas_thesis.save()
    input_a.ideas.connect(ideas_thesis)

    # Get vocabulary (inside scope context)
    repo = StatementRepository()
    vocab = repo.get_vocabulary()
```

## Branching and Cardinality Rationale

### Cycle as Snapshot

**Critical:** A Cycle contains specific PP hashes (ordered), not "latest" PPs. It is a snapshot.

When a PP pool needs to grow:
- The original Cycle remains (immutable once committed)
- Create a new Cycle with the additional PP via `evolutions` relationship

```
Cycle₁ [PP1, PP2] ──evolutions──► Cycle₂ [PP1, PP2, PP3]
```

### Where Branching Happens

To explore different dialectical paths, branch at the appropriate upstream level:

```
Different polar interpretations         → Create different Perspectives
Different PP pools                      → Create different Cycles (via evolutions)
Different PP orderings/causality types  → Create different Cycles
Different layer subsets                 → Create different Wheels (via evolutions)
Different transformation interpretations → Create different Transformations on same edge
```

**Example:** Exploring different transformation paths:

```
Cycle [PP1, PP2, PP3]
     │
     ├── Wheel(PP1) ── Transformation A (fear-based)
     │       │
     │       └── Wheel(PP1,PP2) ── Transformation (refines A)
     │
     └── Wheel(PP1) ── Transformation B (growth-based)  [different Transformation on same edge]
             │
             └── Wheel(PP1,PP2) ── Transformation (refines B)
```

### Multiple Synthesis Interpretations

Each edge can have multiple Transformations, and each Transformation can have multiple Syntheses:

```
Edge (T1- → A2+)
├── Transformation A (insight level 1)
│   └── Synthesis (0, ∞)  ← Multiple interpretations
└── Transformation B (insight level 2)
    └── Synthesis (0, ∞)  ← Multiple interpretations
```

This allows exploring different synthesis outcomes without duplicating structural paths.

## Structural vs Analytical Layers

The graph architecture separates into two distinct layers.

### Structural Layer: The Immutable Backbone

Think of the structural layer as a **3D tree growing downward**:

- **Vertical dimension**: Containment hierarchy (Wheel → Cycle → PP → Statements)
- **Horizontal dimension**: Sibling relationships (multiple PPs in a Cycle, multiple Wheels per Cycle)
- **Depth dimension**: Branching via evolution (Cycle₁ → Cycle₂ with added PP)

**Properties:**
- **Hash-linked**: Each node's hash includes its children's hashes (Merkle tree)
- **Immutable after commit**: Structure frozen for integrity
- **Content-addressed**: Same structure = same hash = same identity

| Node | Role in Structure |
|------|-------------------|
| Statement | Atomic leaves (statements) |
| Perspective | Polar tetrads (T/A with +/-) |
| Transition | Edges between statements |
| Cycle | T-cycle (ordered PP pool + intent) |
| Wheel | TA-cycle (edges implementing Cycle's pool) |
| Transformation | Action-Reflection per edge |

### Analytical Layer: Floating Annotations

Think of the analytical layer as **pins and sticky notes** attached to the structural tree:

- They **point into** the structure at various depths
- They can be **attached, detached, replaced** without affecting the tree
- They **don't contribute** to structural hashes
- Multiple annotations can point to the **same structural node**

**Properties:**
- **Evolvable**: Can be refined, replaced, or removed
- **Non-structural**: Don't affect parent hashes
- **Multi-attach**: Same insight can reference multiple structural points

| Node | What It Annotates |
|------|-------------------|
| Rationale | Any AssessableEntity (explains why) |
| Estimation | Any AssessableEntity (P/R values) |
| Critique | Rationales (audit/challenge) |
| Synthesis | Transformation (emergent S+/S-) |
| ac_re PP | Transformation (action-reflection context) |

### Why This Separation?

```
STRUCTURAL                           ANALYTICAL
────────────────────────────────────────────────────────────
"What IS the dialectical structure"  "How we UNDERSTAND it"
────────────────────────────────────────────────────────────
Immutable after commit               Evolvable anytime
Hash = identity                      Hash = provenance (optional)
Parent contains child hashes         Points TO structure
Branching creates new trees          Reattaches to existing trees
────────────────────────────────────────────────────────────
```

**The elegance**: You can have multiple analytical perspectives on the SAME structural tree. Different rationales, different estimations, different synthesis interpretations - all pointing to one immutable structure. When structure evolves, you branch the tree; when understanding evolves, you update the annotations.

### Implementation

**Base classes** in `relationships/immutable_structure.py`:

```python
# Structural layer - validated for immutability
class ImmutableStructure(Relationship):
    """Marker for structural layer"""

class IdentityRelationship(ImmutableStructure):
    """Defines what a node IS (polarity, source/target)
    Blocked if SOURCE is committed"""

class ContainerMembership(ImmutableStructure):
    """Defines container composition (belongs_to_*, has_*)
    Blocked if TARGET (container) is committed"""

# Analytical layer - freely attachable
class AnalyticalStructure(Relationship):
    """Can connect/disconnect anytime, even to committed nodes"""
```

### Relationship Classification

| Relationship | Layer | Base Class |
|--------------|-------|------------|
| Polarity (T, A) and Aspects (T+, T-, A+, A-) | Structural | IdentityRelationship |
| `IS_SOURCE_OF`, `IS_TARGET_OF` | Structural | IdentityRelationship |
| `BELONGS_TO_CYCLE` | Structural | ContainerMembership |
| `HAS_WHEEL`, `EVOLVED_TO` | Structural | IdentityRelationship |
| `EXPLAINS`, `CRITIQUES` | Analytical | AnalyticalStructure |
| `SYNTHESIS_OF`, `ACTION_REFLECTION` | Analytical | AnalyticalStructure |
| `ESTIMATES`, `PROVIDES` | Analytical | AnalyticalStructure |

### Practical Effect

```python
# Structural: must follow save → add members → commit
transformation.save()
transition.cycle.connect(transformation)  # OK - container uncommitted
transformation.commit()
transition.cycle.connect(transformation)  # BLOCKED - container committed

# Analytical: attach/detach anytime
transformation.ac_re.connect(new_pp)  # OK even after commit
transformation.ac_re.disconnect(old_pp)  # OK - just removes annotation
rationale.set_explanation_target(any_node)  # OK - pointing into structure
```

## Relationship Patterns

**The simplified hierarchy:**
```
Perspective → Cycle → Wheel → Transformation
     ↓          ↓       ↓          ↓
  (tetrad)  (T-cycle) (edges)  (per-edge)
```

**Evolution hierarchy:**
```
Cycle ──evolutions──► Cycle' (PP added)
Wheel ──evolutions──► Wheel' (layer added)
```

**Complete scoring hierarchy (child → parent edges):**
```
Statement ──► Perspective
                              │
Transition ──► Wheel ◄────────┘ (via edges)
                │
         Transformation ◄── Synthesis

Rationale ──► (any AssessableEntity)
```

**Same edge, different views:**
```python
# Child defines outgoing edge
class Wheel:
    cycle = RelationshipFrom("Cycle", model=HasWheelRelationship)

# Parent sees incoming edge (same physical edge)
class Cycle:
    wheels = RelationshipTo("Wheel", model=HasWheelRelationship)
```

**Convention:** Child → Parent edges use `RelationshipFrom` on child when parent "has" children.

## Vocabulary

**Vocabulary** is simply all Statements within a scope (by `sid`). Statements can be combined freely within the same scope.

### Querying Vocabulary

```python
from dialectical_framework.graph.repositories.statement_repository import (
    StatementRepository
)
from dialectical_framework.graph.scope_context import scope

repo = StatementRepository()

# Get vocabulary (always uses current DI scope)
with scope(case.sid):
    vocab = repo.get_vocabulary()
```

## Polarity Relationships

Each position has a typed relationship model:

```python
from dialectical_framework.graph.relationships.polarity_relationship import (
    TRelationship, ARelationship,
    TPlusRelationship, TMinusRelationship,
    APlusRelationship, AMinusRelationship,
    SPlusRelationship, SMinusRelationship,
)
```

The `alias` property on relationships stores contextual names (e.g., "T1", "A2+").

## Semantic Relationships

Statements have semantic relationships that capture dialectical structure:

| Relationship | Direction | Purpose |
|--------------|-----------|---------|
| `OPPOSITE_OF` | Symmetric | T ↔ A (dialectical opposition) |
| `CONTRADICTION_OF` | Symmetric | T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity) |
| `POSITIVE_SIDE_OF` | T+ → T, A+ → A | Positive aspect of neutral |
| `NEGATIVE_SIDE_OF` | T- → T, A- → A | Negative aspect of neutral |

**Auto-creation:** When connecting statements to Perspective positions, semantic relationships are automatically created:

```python
pp = Perspective()
pp.save()

t = Statement(text="Democracy")
t.save()
pp.t.connect(t)

a = Statement(text="Autocracy")
a.save()
pp.a.connect(a)  # Auto-creates: t.oppositions ↔ a

t_plus = Statement(text="Citizen empowerment")
t_plus.save()
pp.t_plus.connect(t_plus)  # Auto-creates: t_plus.positive_side_of → t
                           # Auto-creates: t_plus.oppositions ↔ a_minus (if exists)
```

**Access patterns:**
```python
# Get all opposites
for opp, _ in stmt.oppositions.all():
    print(f"Opposite: {opp.text}")

# Get what this statement is a positive side of
for neutral, _ in stmt.positive_side_of.all():
    print(f"Positive side of: {neutral.text}")

# Get all positive sides of this statement
for pos, _ in stmt.positive_sides.all():
    print(f"Has positive side: {pos.text}")
```

## Scoring (TaroRank)

**Formula:** `Score = P × R^α`

- **P (Probability):** Structural feasibility (0.0-1.0)
- **R (Relevance):** Dialectical quality (0.0-1.0)
- **α (Alpha):** Relevance exponent (default 1.0)

| Method | Use Case |
|--------|----------|
| **GM** | Independent evidence (statement + rationales) |
| **PM (p=4)** | Symmetric pairs (T↔A) |
| **Product** | Sequential probability (cycle transitions) |

**Score flow:** Statement → PP → Cycle → Wheel (child to parent)

**Wheel aggregation:** Wheel scores derive from edges and their Transformations.

**Hard veto:** Element's own P=0 or R=0 → returns 0
**Soft exclusion:** Rationale P=0 or R=0 → filtered out

## Key Conventions

- **Cardinality (1,1):** Exactly one statement per polarity position
- **TYPE_CHECKING:** Always use `from __future__ import annotations` + TYPE_CHECKING guard
- **ClassVar:** Required for RelationshipManager descriptors on GQLAlchemy nodes
- **Manual vs Calculated:** Separate estimation types prevent circular dependencies

## Node Lifecycle Patterns

### Simple Nodes

Nodes without children (Statement, Rationale) can use `commit()` directly:

```python
stmt = Statement(text="Remote work improves focus")
stmt.commit()  # save + compute hash in one step
```

### Container Nodes (IncrementalBuildMixin)

Container nodes (Transformation, Cycle, Wheel, Ideas) whose hash depends on children use `IncrementalBuildMixin`:

```python
# Pattern: save() → add members → commit()
wheel = Wheel()
wheel.save()               # HEAD state - allows adding members
cycle.wheels.connect(wheel)  # Connect to parent Cycle

# Add edges while uncommitted
edge1.cycle.connect(wheel)
edge2.cycle.connect(wheel)

# Commit after all members added
wheel.commit()  # Computes hash from edges, makes immutable
```

**Why this pattern?**
- Container hash = f(children hashes) - children must exist first
- `ContainerMembership` validation blocks adding to committed containers
- Supports atomic construction: either fully built or not at all

**Note:** The first `connect()` auto-saves if needed, so explicit `save()` is optional but recommended for clarity.

## Common Operations

```python
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
from dialectical_framework.graph.scoring.tarorank import TaroRank

# Create Perspectives with statements
pp1 = Perspective()
pp1.save()
t1 = Statement(text="Remote work improves focus")
t1.commit()
pp1.t.connect(t1, relationship=TRelationship(alias='T1'))
# ... add other statements (t_plus, t_minus, a, a_plus, a_minus)
pp1.commit()

pp2 = Perspective()
# ... similar setup
pp2.commit()

# Create Cycle with ordered PPs
cycle = Cycle(intent="preset:balanced")
cycle.set_perspectives([pp1, pp2])
cycle.commit()

# Create Wheel with edges
wheel = Wheel()
wheel.save()
cycle.wheels.connect(wheel)

# Add edges (transitions) that define the T-A arrangement
edge1 = Transition()
edge1.set_source(t1_minus).set_target(a2_plus)
edge1.commit()
edge1.cycle.connect(wheel)
# ... add more edges to complete the cycle

wheel.commit()

# Create Transformation for an edge
transformation = Transformation()
transformation.set_on_edge(edge1)
transformation.save()
# ... add ac_plus, re_plus transitions
transformation.commit()

# Access Perspectives from Wheel (derived from edges)
for pp in wheel._perspectives:
    print(f"PP: {pp.short_hash}")

# Access Transformations
for tr in wheel.transformations:
    print(f"Transformation: {tr.short_hash}")

# Score the hierarchy
scorer = TaroRank(alpha=1.0)
scorer.calculate_score(wheel)
print(f"Wheel score: {wheel.score}")
```

## Estimation Architecture

Estimations are separate nodes that point TO their target entity:

```
Rationale ─[PROVIDES]─► Estimation ─[ESTIMATES]─► AssessableEntity
```

**Relationships:**
| Relationship | Direction | Purpose |
|--------------|-----------|---------|
| `ESTIMATES` | Estimation → AssessableEntity | What this estimation measures |
| `PROVIDES` | Rationale → Estimation | Provenance (optional) |

**Estimation Types:**

| Type | Purpose |
|------|---------|
| `ProbabilityEstimation` | Manual P value (user/agent input) |
| `RelevanceEstimation` | Manual R value (user/agent input) |
| `FeasibilityEstimation` | Fallback R value (user/agent input) |
| `CalculatedProbabilityEstimation` | TaroRank-computed P (algorithm output) |
| `CalculatedRelevanceEstimation` | TaroRank-computed R (algorithm output) |
| `CalculatedScoreEstimation` | TaroRank-computed Score = P × R^α |

**Content-addressed identity:** Estimations are identified by `(type, value, target)`. Same tuple = same hash = reused node.

**Access via properties:**
```python
node.probability  # Returns calculated or manual P
node.relevance    # Returns calculated or manual R or feasibility
node.score        # Returns calculated score (via CalculatedScoreEstimation)
node.is_score_valid()  # True if score hasn't been invalidated
```

## Further Reading

- **Scoring specification:** `docs/scoring.md`
- **Portability & identifiers:** `docs/graph-portability.md` (uid, sid, nid, scopes, cloning, realms)
- **Project conventions:** `CLAUDE.md`
