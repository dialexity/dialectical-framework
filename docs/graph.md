# Graph Data Model

Graph-native dialectical framework using Memgraph/Neo4j.

## Node Hierarchy

```
Wheel (top-level)
├─ Cycle ────────────────────────────────┐
│  ├─ Nexus (pool of WisdomUnits) ───────┤ WU → Nexus → Cycle → Wheel
│  │  └─ WisdomUnits (1+) ───────────────┤
│  │     ├─ T, A, T+, T-, A+, A- components (1:1 each)
│  │     ├─ Synthesis (0-N) with S+, S-
│  │     └─ Transformation (0-1) internal spiral
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
| **WisdomUnit** | Thesis-antithesis pair | `t`, `a`, `t_plus`, `t_minus`, `a_plus`, `a_minus`, `nexus`, `changed_to` |
| **Nexus** | Pool of WisdomUnits | `wisdom_units`, `cycles`, `shrunk_to`, `expanded_to` |
| **Synthesis** | Emergent S+/S- pair | `s_plus`, `s_minus`, `wisdom_unit` |
| **Transition** | Component relationship | `source`, `target`, `cycle`, `derived_statements` |
| **Cycle** | Causal loop | `nexus`, `wheels` |
| **Spiral** | Transformational sequence | `wheel` |
| **Transformation** | Internal WU spiral | `wisdom_unit`, `ac_re` |
| **Wheel** | Top container | `cycle`, `spiral` |
| **Rationale** | Evidence/explanation | `explanation`, `critiques`, `derived_statements` |
| **Estimation** | P/R values | `assessed_entity` |
| **Input** | Content source | `statements` (optional, for extraction provenance) |

## Provenance Tracing

Wheels trace back to their source Inputs via the Nexus hierarchy:

```python
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)

repo = DialecticalComponentRepository()

# Trace all root Inputs that contributed to a Wheel
roots = repo.get_root_inputs(wheel)
for input_node in roots:
    print(f"Source: {input_node.content_uri}")
```

**Key concepts:**
- Gen-0 WUs trace to a single Input
- Gen-1+ WUs trace to multiple Inputs (multi-root provenance via Nexus synthesis)
- `get_root_inputs()` recursively collects all contributing sources

## Relationship Patterns

**The Nexus-based hierarchy:**
```
WisdomUnit → Nexus → Cycle → Wheel
     ↓          ↓       ↓        ↓
  (content)  (pool)  (order)  (detail)
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

**Nexus evolution relationships:**
```python
# Direct evolution (no intermediate nodes)
nexus1.shrunk_to.connect(nexus2)    # Reduction: fewer WUs
nexus1.expanded_to.connect(nexus3)  # Growth: more WUs
```

## Vocabulary and WisdomUnit Purity

Components are born via `HAS_STATEMENT` relationships from different sources. The **vocabulary** determines which components can be combined in a WisdomUnit.

### Component Birth Sources

| Source | Relationship | Generation |
|--------|--------------|------------|
| **Input** | `Input -[HAS_STATEMENT]-> Component` | Gen-0 (primary) |
| **Synthesis** | `Synthesis.s_plus/s_minus -> Component` | Gen-1+ (synthesis) |
| **Transition** | `Transition -[HAS_STATEMENT]-> Component` | Gen-1+ (synthesis) |
| **Rationale** | `Rationale -[HAS_STATEMENT]-> Component` | Gen-1+ (synthesis) |

### Vocabulary Boundaries

```
Gen-0 Vocabulary: Input
────────────────────────
Input_A ──HAS_STATEMENT──> [Component_1, Component_2, ...]
                                    │
                                    ▼
                            WisdomUnit (Gen-0)
                            All components from same Input

Gen-1+ Vocabulary: Nexus
────────────────────────
Nexus_1
├── WU position components (Input-born, pulled into vocabulary)
├── Synthesis S+/S- components
├── Transition-derived components
└── Rationale-derived components
                                    │
                                    ▼
                            WisdomUnit (Gen-1)
                            All components from same Nexus vocabulary
```

### WisdomUnit Purity Rule

**All components in a WisdomUnit must belong to the same vocabulary:**
- **Gen-0 WU**: All 6 components from the same Input
- **Gen-1+ WU**: All 6 components from the same Nexus's vocabulary

This is **enforced at connect time**. Attempting to connect a component from a different vocabulary raises `ValueError`.

```python
# Gen-0: Components from same Input
input_a = Input(content_uri="https://article.com/x")
input_a.save()
comp1 = DialecticalComponent(statement="Thesis from A")
comp1.save()
input_a.statements.connect(comp1)

# This works - same Input vocabulary
wu.t.connect(comp1)
wu.a.connect(comp2_from_input_a)  # OK

# This fails - different Input vocabulary
wu.t_plus.connect(comp_from_input_b)  # ValueError!
```

### Querying Vocabulary

```python
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)

repo = DialecticalComponentRepository()

# Get vocabulary for a context
input_vocab = repo.get_vocabulary(input_node)   # Gen-0 components
nexus_vocab = repo.get_vocabulary(nexus)        # Gen-1+ components

# Find context for any node
context = repo.get_vocabulary_context(component)  # Returns Input or Nexus

# Trace all root Inputs
roots = repo.get_root_inputs(wheel)  # All Inputs that contributed
```

### Multi-Root Provenance

Gen-1+ components have **multi-root provenance** - they trace back to multiple original Inputs via the Nexus that produced them. This is by design: synthesis combines perspectives from different sources.

```
Wheel_2
  └── Cycle_2
        └── Nexus_2 (Gen-1 WUs)
              │
              └── birth_nexus = Nexus_1
                    ├── WU_A (from Input_A)
                    └── WU_B (from Input_B)

get_root_inputs(Wheel_2) → [Input_A, Input_B]
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
| `OPPOSITE_OF` | Symmetric | T ↔ A, T+ ↔ A-, A+ ↔ T- (opposites) |
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
component.save()
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

## Estimation Types

| Type | Purpose |
|------|---------|
| `ProbabilityEstimation` | Manual P value |
| `RelevanceEstimation` | Manual R value |
| `FeasibilityEstimation` | Fallback R value |
| `CalculatedProbabilityEstimation` | TaroRank-computed P |
| `CalculatedRelevanceEstimation` | TaroRank-computed R |

Access via properties:
```python
node.probability  # Returns calculated or manual P
node.relevance    # Returns calculated or manual R or feasibility
```

## Further Reading

- **Scoring specification:** `docs/scoring.md`
- **Project conventions:** `CLAUDE.md`
