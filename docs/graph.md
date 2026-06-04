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
- **Cycle**: T-cycle — ordered sequence of Perspectives defining abstract thesis causality
- **Wheel**: TA-cycle — concrete arrangement with edges between statements
- **Transformation**: Action-Reflection structure per edge (Ac, Re, Ac+, Ac-, Re+, Re-)

**Layered combination model:**
- A Nexus groups Perspectives for exploration
- Cycles and Wheels are built in layers (1-PP, 2-PP, 3-PP combinations)
- Wheels with the same component set are reused across Cycles

## Base Classes

| Class | Purpose | Used By |
|-------|---------|---------|
| **BaseNode** | Hash identity, save/commit lifecycle, `sid` auto-population | All nodes |
| **AssessableEntity** | Adds `rationales`/`estimations` relationships, `best_rationale` property | Statement, Polarity, Perspective, Cycle, Wheel |
| **IntentMixin** | Adds `intent: Optional[str]` field (included in hash if set) | Ideas, Cycle, Perspective, Transformation, Wheel, Nexus |
| **IncrementalBuildMixin** | Staged build: `save()` → add children → `commit()` | Perspective, Ideas, Wheel, Transformation, Synthesis |

**BaseNode interface:**
- `hash`, `committed_at`, `sid` — identity fields
- `is_committed` — True when hash is set
- `short_hash` — first 7 chars of hash
- `save()` — persist to DB (dedup for content-addressable nodes)
- `commit()` — set `committed_at`, compute hash, persist (raises if already committed)
- `clone(destination_sid)` — creates uncommitted copy of a committed node

## Core Nodes

| Node | Purpose | Key Relationships |
|------|---------|-------------------|
| **Statement** | Atomic statement | `oppositions`, `positive_side_of`, `negative_side_of`, `source_of`, `target_of` |
| **Polarity** | T-A tension (thesis-antithesis pair) | `t`, `a`, `perspectives` |
| **Perspective** | Full polar interpretation | `polarity`, `t_plus`, `t_minus`, `a_plus`, `a_minus`, `nexus`, `changed_to` |
| **Nexus** | Exploration container for Perspectives | `perspectives`, `intent`, `preset` |
| **Cycle** | T-cycle (ordered Perspective sequence) | `perspective_hashes`, `wheels`, `opposite_direction` |
| **Wheel** | TA-cycle implementation | `cycle`, `_edges`, `opposite_direction`, `synthesis` |
| **Transition** | Edge between statements | `source`, `target`, `cycle` (→Cycle or Wheel) |
| **Transformation** | Action-Reflection per edge | `edge` (→Transition via ACTION_REFLECTION), `nexus`, positions (ac, re, ac+, etc.) |
| **Synthesis** | Emergent S+/S- pair from Wheel's circular causality | `s_plus`, `s_minus`, `target` (→Wheel) |
| **Rationale** | Evidence/explanation | `explains`, `critiques`, `provided_estimations` |
| **Estimation** | P/R values | `target` (→AssessableEntity via ESTIMATES), `provider` (←Rationale via PROVIDES) |
| **Input** | Content source | `has_statements`, `ideas` |
| **Ideas** | Distilled concepts from Input | `inputs` (→Input), `statements` |
| **Case** | Multi-input exploration | `inputs` (→Input) |

**Removed:**
- **Spiral**: Replaced by Transformations on edges (fully removed from codebase)

## Intent Levels

All reasoning nodes inherit from `IntentMixin`, providing a unified `intent: Optional[str]` field. Intent maps to the reflective practice framework:

| Level | Reflection | Question | Lives On | Example Intent |
|-------|------------|----------|----------|----------------|
| **Discovery** | (Gathering) | What sources to explore? | Ideas | "economic_articles", "ethical_perspectives" |
| **Focus** | What? | What tensions exist? | Cycle | "economic_vs_social", "sustainability" |
| **Dynamics** | So What? | Why do they matter? | Cycle (intent field) | "preset:balanced", "preset:realistic" |
| **Path** | Now What? | How to navigate? | Perspective, Transformation, Wheel | "preset:general_concepts", "growth_based" |
| **Synthesis** | (Outcome) | What emerges? | Synthesis (via Wheel's intent) | "practical_compromise" |

**Nodes with IntentMixin:** Ideas, Cycle, Perspective, Transformation, Wheel, Nexus (not Synthesis)

**Intent inheritance:** Wheels inherit intent from their parent Cycle. Use `get_effective_intent()` to resolve (checks wheel's own intent first, then cycle's).

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

## Layered Combination Model

Cycles and Wheels are generated combinatorially from a Nexus's Perspectives:

```
Given Nexus with [PP1, PP2, PP3]:

Layer 1:  Cycle(PP1)    Cycle(PP2)    Cycle(PP3)
Layer 2:  Cycle(PP1,PP2)  Cycle(PP1,PP3)  Cycle(PP2,PP3)
Layer 3:  Cycle(PP1,PP2,PP3)

Each Cycle can have multiple Wheels (different TA arrangements).
```

**Wheel reuse:** Wheels with the same component set (rotation-invariant hash) are reused across Cycles.

**Opposite direction:** Cycles/Wheels that are circular reverses of each other are linked via `OPPOSITE_DIRECTION`.

## Case Layer

The Case layer provides multi-input exploration before Perspective construction:

```
Case (multi-input exploration)
├── HAS_INPUT → Input₁
│              ◄── DISTILLED_FROM ── Ideas₁ (intent: "thesis_extraction")
│                                      └── HAS_STATEMENT → Statements...
├── HAS_INPUT → Input₂
│              ◄── DISTILLED_FROM ── Ideas₂ (intent: "antithesis_extraction")
└── get_vocabulary() → All statements in scope (uses DI scope)
```

### Key Concepts

| Node | Purpose | Cardinality |
|------|---------|-------------|
| **Case** | Multi-input exploration with shared vocabulary | HAS_INPUT (1, ∞) to Input |
| **Ideas** | Distilled concepts from a single Input | DISTILLED_FROM (0, ∞) to Input |

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

## Nexus → Cycle → Wheel Generation

The `PerspectiveCombination` concern (`concerns/perspective_combination.py`) orchestrates combinatorial generation:

1. Input: committed Nexus + committed Perspectives
2. Connect PPs to Nexus (idempotent)
3. Generate layers combinatorially:
   - **Layer 1:** Single-PP Cycles/Wheels (self-reference)
   - **Layer 2:** Pair combinations → permutation-based T-cycles → diagonal-symmetric Wheel arrangements
   - **Layer 3+:** Triplets, quadruplets, etc.
4. Dedup: reuse existing Cycles/Wheels by hash
5. Link opposite-direction pairs via `OPPOSITE_DIRECTION`

**Diagonal symmetry constraint:** In a 2n-component Wheel, each thesis T_i sits diametrically opposite its antithesis A_i. This is enforced by `generate_compatible_sequences` (`utils/sequence_generation.py`).

## Branching and Cardinality Rationale

### Cycle as Snapshot

**Critical:** A Cycle contains specific PP hashes (ordered), not "latest" PPs. It is a snapshot.

When a PP pool needs to grow:
- The original Cycle remains (immutable once committed)
- Create a new Cycle within the same Nexus with additional Perspectives

### Where Branching Happens

To explore different dialectical paths, branch at the appropriate upstream level:

```
Different polar interpretations         → Create different Perspectives
Different PP pools                      → Create different Nexuses (or add to existing)
Different PP orderings/causality types  → Create different Cycles
Different TA arrangements               → Create different Wheels for same Cycle
Different transformation interpretations → Create different Transformations on same edge
```

**Example:** Exploring different transformation paths:

```
Nexus [PP1, PP2, PP3]
     │
     ├── Cycle(PP1,PP2) → Wheel → Transformation A (fear-based)
     │                         └── Transformation B (growth-based)
     │
     └── Cycle(PP1,PP2,PP3) → Wheel → Transformation (uses A/B as context)
```

### Multiple Synthesis Interpretations

Synthesis is a wheel-level phenomenon — it emerges from the complete circular causality system:

```
Wheel (2-PP)
├── Edge pair: T1→A2 / A2→T1 (two opposite Transformations)
└── Synthesis (0, ∞)  ← Multiple interpretations of what emerges

Wheel (3-PP)
├── Edges: T1→A2, T2→A3, T3→A1 (each with Transformation)
└── Synthesis (0, ∞)  ← System-level emergence (uses layer-2 syntheses as context)
```

Higher-layer wheel synthesis uses lower-layer (sub-wheel) syntheses as input context.

## Structural vs Analytical Layers

The graph architecture separates into two distinct layers.

### Structural Layer: The Immutable Backbone

Think of the structural layer as a **tree growing downward**:

- **Vertical dimension**: Containment hierarchy (Nexus → Cycle → Wheel → Transition → Statement)
- **Horizontal dimension**: Sibling relationships (multiple Perspectives in a Nexus, multiple Wheels per Cycle)

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
| Synthesis | Wheel (emergent S+/S- from circular causality) |

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
    """Defines container composition (belongs_to_*)
    Blocked if TARGET (container) is committed"""

class OutgoingContainerMembership(ImmutableStructure):
    """For HAS_* relationships where containers point TO children
    Blocked if SOURCE (container) is committed"""

# Analytical layer - freely attachable
class AnalyticalStructure(Relationship):
    """Can connect/disconnect anytime, even to committed nodes"""
```

### Relationship Classification

| Relationship | Layer | Base Class |
|--------------|-------|------------|
| Polarity (T, A) and Aspects (T+, T-, A+, A-) | Structural | IdentityRelationship |
| `IS_SOURCE_OF`, `IS_TARGET_OF` | Structural | IdentityRelationship |
| `HAS_POLARITY` | Structural | IdentityRelationship |
| `BELONGS_TO_CYCLE` | Structural | ContainerMembership |
| `HAS_STATEMENT` | Structural | OutgoingContainerMembership |
| `BELONGS_TO_NEXUS` | Analytical | AnalyticalStructure |
| `HAS_WHEEL` | Analytical | AnalyticalStructure |
| `EXPLAINS`, `CRITIQUES` | Analytical | AnalyticalStructure |
| `SYNTHESIS_OF`, `ACTION_REFLECTION` | Analytical | AnalyticalStructure |
| `ESTIMATES`, `PROVIDES` | Analytical | AnalyticalStructure |
| `CHANGED_TO` | Analytical | AnalyticalStructure |
| `OPPOSITE_DIRECTION` | Unclassified | Relationship (bare) |

### Practical Effect

```python
# Structural: must follow save → add members → commit
transformation.save()
transition.cycle.connect(transformation)  # OK - container uncommitted
transformation.commit()
transition.cycle.connect(transformation)  # BLOCKED - container committed

# Analytical: attach/detach anytime
pp.nexus.connect(nexus)  # OK even after PP is committed
wheel.synthesis.connect(synth)  # OK - analytical annotation
rationale.set_explanation_target(any_node)  # OK - pointing into structure
```

## Relationship Patterns

**The simplified hierarchy:**
```
Nexus → Cycle → Wheel → Transformation
  ↓        ↓       ↓          ↓
(PPs)  (T-cycle) (edges)  (per-edge)
```

**Perspective lineage:**
```
Perspective ──CHANGED_TO──► Perspective' (edited version)
```

**Structural containment hierarchy:**
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
# Parent defines outgoing edge
class Cycle:
    wheels = RelationshipTo("Wheel", model=HasWheelRelationship)

# Child sees incoming edge (same physical edge)
class Wheel:
    cycle = RelationshipFrom("Cycle", model=HasWheelRelationship)
```

**Convention:** Child → Parent edges use `RelationshipTo` on child. Parent → Child (HAS_*) edges use `RelationshipTo` on parent.

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

## Polarity → Perspective Creation

Polarity is a shared structural atom (same T+A pair = same node). Perspective builds on top of it:

```python
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import Perspective

# 1. Create and commit statements
thesis = Statement(text="Democracy"); thesis.commit()
antithesis = Statement(text="Autocracy"); antithesis.commit()

# 2. Create Polarity (reusable, order-independent hash)
pol = Polarity()
pol.set_t(thesis)
pol.set_a(antithesis, heuristic_similarity=0.72)
pol.commit()

# 3. Create Perspective with aspects
pp = Perspective()
pp.save()
pp.polarity.connect(pol)
pp.t_plus.connect(t_plus_stmt)   # T+ aspect
pp.t_minus.connect(t_minus_stmt) # T- aspect
pp.a_plus.connect(a_plus_stmt)   # A+ aspect
pp.a_minus.connect(a_minus_stmt) # A- aspect
pp.commit()

# Access T/A through Perspective (delegates to Polarity)
pp.t  # → thesis Statement
pp.a  # → antithesis Statement
```

**Key design:** Multiple Perspectives can share the same Polarity (different tetrad interpretations of the same T-A tension).

## Semantic Relationships

Statements have semantic relationships that capture dialectical structure:

| Relationship | Direction | Purpose |
|--------------|-----------|---------|
| `OPPOSITE_OF` | Symmetric | T ↔ A (dialectical opposition) |
| `CONTRADICTION_OF` | Symmetric | T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity) |
| `POSITIVE_SIDE_OF` | T+ → T, A+ → A | Positive aspect of neutral |
| `NEGATIVE_SIDE_OF` | T- → T, A- → A | Negative aspect of neutral |

**Auto-creation:** When connecting statements to positions, semantic relationships are automatically created.
Note: T and A live on the Polarity node. `pp.t` and `pp.a` are convenience properties that delegate to `pp.polarity → Polarity.t / Polarity.a`.

```python
pp = Perspective()
pp.save()

t = Statement(text="Democracy")
t.save()
pp.t.connect(t)  # Actually connects to pp's Polarity

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

## Quality Signals

Quality is measured by structural edge properties, not a separate scoring system:

- **heuristic_similarity** (0.0-1.0) on T/A/aspect edges — similarity to taxonomy apex
- **complementarity_t**, **complementarity_a** (0.0-1.0) on aspect edges — how well aspect complements T/A
- **insight**, **proactiveness** (0.0-1.0) on transformation aspect edges
- **Perspective computed properties:** `diff_t`, `diff_a`, `area_normalized`, `rectangularity`

## Scope Context

All graph operations happen within a scope (identified by `sid`). The `scope()` context manager sets the active sid via `contextvars`:

```python
from dialectical_framework.graph.scope_context import scope

with scope(case.sid):
    # All nodes created here auto-inherit this sid
    stmt = Statement(text="...")
    stmt.commit()  # stmt.sid == case.sid

    # Repository queries are scoped to this sid
    vocab = repo.get_vocabulary()
```

**Rules:**
- The **application layer** calls `scope()` — the framework layer never does
- `BaseNode.__init__` auto-reads `sid` from the active scope if not passed explicitly
- Repositories read `sid` via DI (`Provide[DI.sid]` → `get_current_sid()`)
- Scopes nest: exiting restores the previous scope

## Key Conventions

- **Cardinality (1,1):** Exactly one statement per polarity position
- **TYPE_CHECKING:** Always use `from __future__ import annotations` + TYPE_CHECKING guard
- **ClassVar:** Required for RelationshipManager descriptors on GQLAlchemy nodes

## Node Lifecycle Patterns

### Simple Nodes

Nodes without children (Statement, Rationale) can use `commit()` directly:

```python
stmt = Statement(text="Remote work improves focus")
stmt.commit()  # save + compute hash in one step
```

### Container Nodes (IncrementalBuildMixin)

Container nodes (Perspective, Transformation, Wheel, Ideas, Synthesis) whose hash depends on children use `IncrementalBuildMixin`:

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

# Create Cycle with ordered PPs (not IncrementalBuildMixin — uses set_perspectives())
cycle = Cycle(intent="preset:balanced")
cycle.set_perspectives([pp1, pp2])  # stores ordered hashes as a field
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
```

## Critique Architecture

Critique is NOT a separate node — it's a **Rationale→Rationale relationship** (`CRITIQUES`):

```
Rationale₂ ─[CRITIQUES]─► Rationale₁ ─[EXPLAINS]─► (any AssessableEntity)
```

- A Rationale can critique at most one other Rationale (`cardinality=(0,1)`)
- Temporal cycle prevention: can only critique a Rationale committed earlier
- Access: `rationale.critiques` (incoming), `rationale._critiques_target` (outgoing)

## Repositories

All queries go through `graph/repositories/` classes, always sid-scoped:

| Repository | Key Methods |
|---|---|
| **NodeRepository** | `find_by_hash(hash, node_type)` — handles both full and prefix (7+ chars) lookup |
| **PerspectiveRepository** | `find_all_active()`, `find_by_polarity(pol)`, `find_by_statement(stmt)`, `is_in_use_by_cycle(pp)`, `discard_uncommitted(pp)` |
| **PolarityRepository** | `find_by_tension(t, a)`, `find_by_component(stmt, position)`, `find_unconnected()` |
| **CycleRepository** | `find_by_perspectives(pps, exact_order)` (rotation-invariant), `find_by_layer(pps, nexus)` |
| **WheelRepository** | `find_by_component_sequence(components)` (rotation-invariant), `get_transformations(wheel)` |
| **StatementRepository** | `get_vocabulary()`, `find_by_perspective(pp)`, `safe_delete(stmt)`, `find_unconnected(limit)` |
| **TransformationRepository** | `find_by_edge(edge)`, `find_by_nexus(nexus)`, `find_parent_transformations(edge)` |

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
| `CausalityProbabilityEstimation` | Causality ordering likelihood (raw on Cycles/Wheels, normalized on Transitions) |
| `FeasibilityEstimation` | Practical achievability |
| `ModeEstimation` | T-A opposition characterization |
| `ArousalEstimation` | T-A opposition intensity |
| `ConceptualCoherenceEstimation` | Tetrad validation (control statements) |
| `DiagonalContradictionEstimation` | Tetrad validation (diagonal pairs) |

**Content-addressed identity:** Estimations are identified by `(type, value, target)`. Same tuple = same hash = reused node.

## Events

Graph mutations are broadcast via `GraphEventBus` (in-process async, channel = sid):

**Effect types:** `node_created`, `node_updated`, `node_deleted`, `relationship_created`, `relationship_updated`, `relationship_deleted`

**Emitting (tools/concerns):** Call methods on `ExecutionReport` — e.g., `self._report.node_created(node)`. The report auto-publishes to the bus. Fire-and-forget.

**Subscribing (app/UI layer):**
```python
async with bus.subscribe(sid) as subscriber:
    async for event in subscriber:
        process(event.effect)
```

## Discarded Nodes

The `discarded: Optional[str]` field exists on **Statement** and **Perspective** only:
- Soft-marks a committed node as excluded from active queries (node stays in graph)
- Value is a reason string (e.g., "not relevant") or just "discarded"
- Repositories filter by `discarded IS NULL` for active queries (`find_all_active()`, etc.)
- Uncommitted nodes are physically deleted instead (`discard_uncommitted()`)

## Further Reading

- **Portability & identifiers:** `docs/graph-portability.md` (uid, sid, nid, scopes, cloning, realms)
- **Project conventions:** `CLAUDE.md`
