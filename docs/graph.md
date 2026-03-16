# Graph Data Model

Graph-native dialectical framework using Memgraph/Neo4j.

## Node Hierarchy

```
Wheel (top-level)
├─ Cycle ────────────────────────────────┐
│  ├─ Nexus (pool of WisdomUnits) ───────┤ WU → Nexus → Cycle → Wheel
│  │  └─ WisdomUnits (1+) ───────────────┤
│  │     ├─ T, A, T+, T-, A+, A- components (1:1 each)
│  │     └─ Transformation (0-1) internal spiral
│  │        └─ Synthesis (0-N) with S+, S-
│  └─ Transitions (2+)                   │
├─ Wheel-level Transitions (detailed)    │
└─ Spiral (0-1) ─────────────────────────┘
   └─ Transitions (2+)
```

**Key insight:** Nexus serves as a "pool" of WisdomUnits that can be shared
across different analytical perspectives. Cycles arrange WUs in causal sequences,
while Wheels provide detailed transition-level analysis.

## Core Nodes

| Node | Purpose | Key Relationships |
|------|---------|-------------------|
| **DialecticalComponent** | Atomic statement | `oppositions`, `positive_side_of`, `negative_side_of`, `similar_to`, `source_of`, `target_of` |
| **WisdomUnit** | Thesis-antithesis pair | `t`, `a`, `t_plus`, `t_minus`, `a_plus`, `a_minus`, `nexus` |
| **Nexus** | Pool of WisdomUnits | `wisdom_units`, `cycles` |
| **Synthesis** | Emergent S+/S- pair | `s_plus`, `s_minus`, `target` (→Transformation or Spiral) |
| **Transition** | Component relationship | `source`, `target`, `cycle` |
| **Cycle** | Causal loop | `nexus`, `wheels` |
| **Spiral** | Transformational sequence | `wheel`, `synthesis` (0-N) |
| **Transformation** | Internal WU spiral | `wisdom_unit`, `ac_re`, `synthesis` (0-N) |
| **Wheel** | Top container | `cycle`, `spiral` |
| **Rationale** | Evidence/explanation | `explanation`, `critiques`, `provided_estimations` |
| **Estimation** | P/R values | `target` (→AssessableEntity via ESTIMATES), `_provider` (←Rationale via PROVIDES) |
| **Input** | Content source | `statements`, `ideas` |
| **Ideas** | Distilled concepts from Input | `input` (→Input), `statements` |
| **Brainstorm** | Multi-input exploration | `inputs` (→Input), `get_vocabulary()` |

## Intent Levels

All reasoning nodes inherit from `IntentMixin`, providing a unified `intent: Optional[str]` field. Intent maps to the reflective practice framework:

| Level | Reflection | Question | Lives On | Example Intent |
|-------|------------|----------|----------|----------------|
| **Discovery** | (Gathering) | What sources to explore? | Brainstorm, Ideas | "economic_articles", "ethical_perspectives" |
| **Focus** | What? | What tensions exist? | Nexus | "economic_vs_social", "sustainability" |
| **Dynamics** | So What? | Why do they matter? | Cycle | "preset:balanced", "preset:realistic" |
| **Path** | Now What? | How to navigate? | WisdomUnit, Transformation | "preset:general_concepts", "growth_based" |
| **Synthesis** | (Outcome) | What emerges? | Synthesis, Spiral | "practical_compromise" |

**Nodes with IntentMixin:** Brainstorm, Ideas, Nexus, Cycle, WisdomUnit, Transformation, Synthesis, Spiral, Wheel

**Intent enables grouping:** Explicit intent on the graph allows finding explorations with similar focus, grouping by dynamics, and making the graph a readable analysis artifact. Presets like "preset:balanced" or "preset:realistic" serve as defaults but can be replaced with natural language.

## Transformation and Spiral: Local vs Global

**WU Transformation** (local, abstract):
- Internal spiral within ONE WisdomUnit (2 transitions)
- Resolves the internal dialectic of a single tension
- Produces local Synthesis (S+/S-)
- Has its own Path intent

**Wheel Spiral** (global, concrete):
- Weaves together all WU Transformations in the Nexus
- Blends Path intents from all WUs into coherent navigation
- Adds inter-WU transitions and ordering
- Produces meta-Synthesis (what emerges from the whole journey)
- **Spirals are the ultimate artifacts** - preserved synthesis decisions

### Calculation Order

**Bottom-up: WU Transformations first, then Wheel Spiral**

1. Each WU calculates its Transformation (local path with local intent)
2. Wheel Spiral weaves those Transformations together with Wheel-level (blended) intent
3. Wheel doesn't recalculate WU paths - it sequences and blends them

```
WU₁.Transformation ──┐
WU₂.Transformation ──┼──► Wheel.Spiral (blended navigation)
WU₃.Transformation ──┘
```

**What Wheel Spiral adds:**
- Ordering between WU transitions (WU₁'s T-→A+ before WU₂'s A-→T+)
- Inter-WU transitions (moving from one tension to another)
- Meta-synthesis (emergent insight from the whole journey)

## Brainstorm Layer

The Brainstorm layer provides multi-input exploration before WisdomUnit construction:

```
Brainstorm (multi-input exploration)
├── HAS_INPUT → Input₁
│              └── DISTILLED_TO → Ideas₁ (intent: "thesis_extraction")
│                                └── HAS_STATEMENT → Components...
├── HAS_INPUT → Input₂
│              └── DISTILLED_TO → Ideas₂ (intent: "antithesis_extraction")
└── get_vocabulary() → All components in scope (uses DI scope)
```

### Key Concepts

| Node | Purpose | Cardinality |
|------|---------|-------------|
| **Brainstorm** | Multi-input exploration with shared vocabulary | HAS_INPUT (1, ∞) to Input |
| **Ideas** | Distilled concepts from a single Input | DISTILLED_TO (1, 1) from Input |

**Ideas as filtered lens:** Each Ideas node represents a specific distillation of an Input (e.g., "thesis concepts", "ethical implications"). Multiple Ideas nodes can point to the same Input with different intents.

**Vocabulary:** `repo.get_vocabulary()` returns all DialecticalComponents in the current scope. This enables cross-input WisdomUnit construction.

### Usage

```python
from dialectical_framework.graph.nodes.brainstorm import Brainstorm
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)
from dialectical_framework.graph.scope_context import scope

# Create brainstorm (scope root)
brainstorm = Brainstorm()
brainstorm.commit()

with scope(brainstorm.sid):
    # Create inputs (inherit sid from scope)
    input_a = Input(content="https://article.com/pro")
    input_b = Input(content="https://article.com/con")
    input_a.commit()
    input_b.commit()
    brainstorm.inputs.connect(input_a)
    brainstorm.inputs.connect(input_b)

    # Create ideas
    ideas_thesis = Ideas(intent="thesis_extraction")
    ideas_thesis.save()
    input_a.ideas.connect(ideas_thesis)

    # Get vocabulary (inside scope context)
    repo = DialecticalComponentRepository()
    vocab = repo.get_vocabulary()
```

## Branching and Cardinality Rationale

The framework uses (0, 1) cardinality for both `WisdomUnit.transformation` and `Wheel.spiral`. This is intentional - different exploration paths require branching **upstream**, not at these nodes.

### Why (0, 1) for Transformation and Spiral?

Both Transformation and Spiral are **derived structures**, fully determined by their inputs:

| Node | Determined By | Cardinality |
|------|---------------|-------------|
| **Transformation** | WU's polar structure + Path intent | (0, 1) per WU |
| **Spiral** | Wheel's segment ordering + all WU Transformations | (0, 1) per Wheel |

**Key insight:** The Spiral doesn't have independent "intentions" - it inherits and blends them from the WU Transformations within the Nexus. Given a fixed Wheel arrangement and fixed WU Transformations, there is exactly one Spiral structure.

### Nexus as Snapshot

**Critical:** A Nexus contains specific WU versions, not "latest" WUs. It is a snapshot, not a living container.

When a WU needs to evolve:
- The original WU remains in its Nexus (immutable once committed)
- Create a new WU with the evolved structure
- Create a new Nexus containing the evolved WU

```
WU₁ (original)           WU₁' (evolved version - new node)
 │                         │
 └── Nexus₁ (snapshot)     └── Nexus₂ (new snapshot with evolved WU)
       │                         │
    Wheel₁ → Spiral₁          Wheel₂ → Spiral₂
    (preserved)               (new synthesis)
```

**Why this matters:** Spirals are ultimate artifacts. Spiral₁ remains as historical synthesis - "given these WUs with these intents, here's what emerged." It's a committed insight, not a cache to be invalidated.

### Where Branching Happens

To explore different dialectical paths, branch at the appropriate upstream level:

```
Different polar interpretations     → Create different WisdomUnits
Different WU combinations           → Create different Nexuses
Different orderings/causality types → Create different Cycles
Different detailed implementations  → Create different Wheels
```

**The duplication is the feature:** WUs appearing in multiple Nexuses isn't waste - it's provenance. You can trace "Spiral₂ emerged because WU₁ evolved, while keeping WU₂, WU₃."

**Example:** To explore Love↔Hate through different transformation paths:

```
WU1: Love↔Hate (Transformation: fear-based)
WU2: Love↔Hate (Transformation: growth-based)  ← Different WU, not multiple Transformations
     │
     ▼
Nexus A {WU1, WU3}          Nexus B {WU2, WU3}
     │                           │
     ▼                           ▼
Cycle → Wheel → Spiral A    Cycle → Wheel → Spiral B
```

### Multiple Synthesis Interpretations

While Transformation and Spiral have (0, 1) cardinality, **Synthesis has (0, ∞)**:

```
Transformation (0, 1)
└── Synthesis (0, ∞)  ← Multiple interpretations of the same transformation

Spiral (0, 1)
└── Synthesis (0, ∞)  ← Multiple interpretations of the same spiral path
```

This allows exploring different synthesis outcomes (S+/S-) without duplicating the structural path.

## Structural vs Analytical Layers

The graph architecture separates into two distinct layers.

### Structural Layer: The Immutable Backbone

Think of the structural layer as a **3D tree growing downward**:

- **Vertical dimension**: Containment hierarchy (Wheel → Cycle → Nexus → WU → Components)
- **Horizontal dimension**: Sibling relationships (multiple WUs in a Nexus, multiple Wheels in a Cycle)
- **Depth dimension**: Branching via clones (Nexus₁ → Nexus₂ with evolved WUs)

**Properties:**
- **Hash-linked**: Each node's hash includes its children's hashes (Merkle tree)
- **Immutable after commit**: Structure frozen for integrity
- **Content-addressed**: Same structure = same hash = same identity

| Node | Role in Structure |
|------|-------------------|
| DialecticalComponent | Atomic leaves (statements) |
| WisdomUnit | Polar pairs (T/A with +/-) |
| Transition | Edges between components |
| Nexus | Snapshot of WU versions |
| Cycle | Causal ordering |
| Wheel | Complete detailed view |

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
| Synthesis | Transformation or Spiral (emergent S+/S-) |
| ac_re WU | Transformation (action-reflection context) |

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
| Polarity (T, A, T+, etc.) | Structural | IdentityRelationship |
| `IS_SOURCE_OF`, `IS_TARGET_OF` | Structural | IdentityRelationship |
| `BELONGS_TO_CYCLE`, `BELONGS_TO_NEXUS` | Structural | ContainerMembership |
| `HAS_CYCLE`, `HAS_WHEEL` | Structural | ContainerMembership |
| `EXPLAINS`, `CRITIQUES` | Analytical | AnalyticalStructure |
| `SYNTHESIS_OF`, `IS_SPIRAL_OF` | Analytical | AnalyticalStructure |
| `ACTION_REFLECTION` | Analytical | AnalyticalStructure |
| `ESTIMATES`, `PROVIDES` | Analytical | AnalyticalStructure |

### Practical Effect

```python
# Structural: must follow save → add members → commit
transformation.save()
transition.cycle.connect(transformation)  # OK - container uncommitted
transformation.commit()
transition.cycle.connect(transformation)  # BLOCKED - container committed

# Analytical: attach/detach anytime
transformation.ac_re.connect(new_wu)  # OK even after commit
transformation.ac_re.disconnect(old_wu)  # OK - just removes annotation
rationale.set_explanation_target(any_node)  # OK - pointing into structure
```

## Relationship Patterns

**The Nexus-based hierarchy:**
```
WisdomUnit → Nexus → Cycle → Wheel
     ↓          ↓       ↓        ↓
  (content)  (pool)  (order)  (detail)
```

**Complete scoring hierarchy (child → parent edges):**
```
DialecticalComponent ──► WisdomUnit ──► Nexus ──► Cycle ──► Wheel
       │                     ▲                               ▲
       │                     │                               │
       │              Transformation ◄── Synthesis           │
       │                                    │                │
       └──► Synthesis ──────────────────────┴──► Spiral ─────┘

Transition ──► Cycle/Wheel/Spiral/Transformation
Rationale ──► (any AssessableEntity)
```

**Same edge, different views:**
```python
# Child defines outgoing edge
class WisdomUnit:
    nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")  # WU → Nexus

# Parent sees incoming edge (same physical edge)
class Nexus:
    wisdom_units = RelationshipFrom("WisdomUnit", "BELONGS_TO_NEXUS")
```

**Convention:** Child → Parent edges use `RelationshipTo` on child.

## Vocabulary

**Vocabulary** is simply all DialecticalComponents within a scope (by `sid`). Components can be combined freely within the same scope.

### Querying Vocabulary

```python
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)
from dialectical_framework.graph.scope_context import scope

repo = DialecticalComponentRepository()

# Get vocabulary (always uses current DI scope)
with scope(brainstorm.sid):
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

Components have semantic relationships that capture dialectical structure:

| Relationship | Direction | Purpose |
|--------------|-----------|---------|
| `OPPOSITE_OF` | Symmetric | T ↔ A (dialectical opposition) |
| `CONTRADICTION_OF` | Symmetric | T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity) |
| `POSITIVE_SIDE_OF` | T+ → T, A+ → A | Positive aspect of neutral |
| `NEGATIVE_SIDE_OF` | T- → T, A- → A | Negative aspect of neutral |
| `SIMILAR_TO` | Directed | Semantic similarity between components |

**Auto-creation:** When connecting components to WisdomUnit positions, semantic relationships are automatically created:

```python
wu = WisdomUnit()
wu.save()

t = DialecticalComponent(statement="Democracy")
t.save()
wu.t.connect(t)

a = DialecticalComponent(statement="Autocracy")
a.save()
wu.a.connect(a)  # Auto-creates: t.oppositions ↔ a

t_plus = DialecticalComponent(statement="Citizen empowerment")
t_plus.save()
wu.t_plus.connect(t_plus)  # Auto-creates: t_plus.positive_side_of → t
                           # Auto-creates: t_plus.oppositions ↔ a_minus (if exists)
```

**Access patterns:**
```python
# Get all opposites
for opp, _ in component.oppositions.all():
    print(f"Opposite: {opp.statement}")

# Get what this component is a positive side of
for neutral, _ in component.positive_side_of.all():
    print(f"Positive side of: {neutral.statement}")

# Get all positive sides of this component
for pos, _ in component.positive_sides.all():
    print(f"Has positive side: {pos.statement}")
```

## Scoring (TaroRank)

**Formula:** `Score = P × R^α`

- **P (Probability):** Structural feasibility (0.0-1.0)
- **R (Relevance):** Dialectical quality (0.0-1.0)
- **α (Alpha):** Relevance exponent (default 1.0)

| Method | Use Case |
|--------|----------|
| **GM** | Independent evidence (component + rationales, Nexus aggregation) |
| **PM (p=4)** | Symmetric pairs (T↔A) |
| **Product** | Sequential probability (cycle transitions) |

**Score flow:** Component → WU → Nexus → Cycle → Wheel (child to parent)

**Nexus aggregation:** Nexus.R = GM(WU relevances), Nexus.P = GM(WU transformation Ps)

**Hard veto:** Element's own P=0 or R=0 → returns 0
**Soft exclusion:** Rationale P=0 or R=0 → filtered out

## Key Conventions

- **Cardinality (1,1):** Exactly one component per polarity position
- **TYPE_CHECKING:** Always use `from __future__ import annotations` + TYPE_CHECKING guard
- **ClassVar:** Required for RelationshipManager descriptors on GQLAlchemy nodes
- **Manual vs Calculated:** Separate estimation types prevent circular dependencies

## Node Lifecycle Patterns

### Simple Nodes

Nodes without children (DialecticalComponent, Rationale) can use `commit()` directly:

```python
component = DialecticalComponent(statement="Remote work improves focus")
component.commit()  # save + compute hash in one step
```

### Container Nodes (IncrementalBuildMixin)

Container nodes (Transformation, Spiral, Nexus, Cycle, Wheel) whose hash depends on children use `IncrementalBuildMixin`:

```python
# Pattern: save() → add members → commit()
transformation = Transformation()
transformation.set_wisdom_unit(wu)  # Set parent reference for hash
transformation.save()               # HEAD state - allows adding members

# Add children while uncommitted
transition1.cycle.connect(transformation)
transition2.cycle.connect(transformation)

# Commit after all members added
transformation.commit()  # Computes hash from children, makes immutable
```

**Why this pattern?**
- Container hash = f(children hashes) - children must exist first
- `ContainerMembership` validation blocks adding to committed containers
- Supports atomic construction: either fully built or not at all

**Note:** The first `connect()` auto-saves if needed, so explicit `save()` is optional but recommended for clarity.

## Common Operations

```python
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
from dialectical_framework.graph.scoring.tarorank import TaroRank

# Create WisdomUnit with components
wu = WisdomUnit()
wu.save()
component = DialecticalComponent(statement="Remote work improves focus")
component.commit()
wu.t.connect(component, relationship=TRelationship(alias='T1'))

# Create Nexus and pool WisdomUnits
nexus = Nexus()
nexus.save()
wu.nexus.connect(nexus)

# Create Cycle from Nexus
cycle = Cycle()
cycle.save()
nexus.cycles.connect(cycle)

# Create Wheel from Cycle
wheel = Wheel()
wheel.save()
cycle.wheels.connect(wheel)

# Access WisdomUnits from Wheel (via Cycle→Nexus)
for wu, _ in wheel.wisdom_units:
    print(f"WU: {wu.uid}")

# Score the hierarchy
scorer = TaroRank(alpha=1.0)
scorer.calculate_score(wheel)  # Recursively scores: WU → Nexus → Cycle → Wheel
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
