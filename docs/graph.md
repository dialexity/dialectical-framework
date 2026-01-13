# Graph Data Model

Graph-native dialectical framework using Memgraph/Neo4j.

## Node Hierarchy

```
Wheel (top-level)
├─ WisdomUnit (1+) ─────────────────────┐
│  ├─ T, A, T+, T-, A+, A- components   │ 6 core positions (1:1 each)
│  ├─ Synthesis (0-N) ──┐               │
│  │  └─ S+, S- components (1:1 each)   │
│  └─ Transformation (0-1) ─────────────┤ internal spiral
│     ├─ Transitions (exactly 2)        │
│     └─ ac_re → WisdomUnit             │
├─ Cycles (T-cycle, TA-cycle) ──────────┤
│  └─ Transitions (2+)                  │
└─ Spiral (0-1) ────────────────────────┘
   └─ Transitions (2+)
```

## Core Nodes

| Node | Purpose | Key Relationships |
|------|---------|-------------------|
| **DialecticalComponent** | Atomic statement | `oppositions`, `source_of`, `target_of` |
| **WisdomUnit** | Thesis-antithesis pair | `t`, `a`, `t_plus`, `t_minus`, `a_plus`, `a_minus`, `wheel` |
| **Synthesis** | Emergent S+/S- pair | `s_plus`, `s_minus`, `wisdom_unit` |
| **Transition** | Component relationship | `source`, `target`, `cycle` |
| **Cycle** | Causal loop | `transitions`, `_wheel_as_t`, `_wheel_as_ta` |
| **Spiral** | Transformational sequence | `transitions`, `_wheel_as_spiral` |
| **Transformation** | Internal WU spiral | `transitions`, `wisdom_unit`, `ac_re` |
| **Wheel** | Top container | `wisdom_units`, `t_cycle`, `ta_cycle`, `spiral` |
| **Rationale** | Evidence/explanation | `explanation`, `critiques` |
| **Estimation** | P/R values | `assessed_entity` |

## Relationship Patterns

**Same edge, different views:**
```python
# Child defines outgoing edge
class WisdomUnit:
    wheel = RelationshipTo("Wheel", "BELONGS_TO_WHEEL")  # WU → Wheel

# Parent sees incoming edge (same physical edge)
class Wheel:
    wisdom_units = RelationshipFrom("WisdomUnit", "BELONGS_TO_WHEEL")
```

**Convention:** Child → Parent edges use `RelationshipTo` on child.

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

## Scoring (TaroRank)

**Formula:** `Score = P × R^α`

- **P (Probability):** Structural feasibility (0.0-1.0)
- **R (Relevance):** Dialectical quality (0.0-1.0)
- **α (Alpha):** Relevance exponent (default 1.0)

| Method | Use Case |
|--------|----------|
| **GM** | Independent evidence (component + rationales) |
| **PM (p=4)** | Symmetric pairs (T↔A) |
| **Product** | Sequential probability (cycle transitions) |

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
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
from dialectical_framework.graph.scoring.tarorank import TaroRank

# Create and connect component to WisdomUnit
component = DialecticalComponent(statement="Remote work improves focus")
component.save()
wu.t.connect(component, relationship=TRelationship(alias='T1'))

# Get all connected nodes with relationships
for comp, rel in wu.t.all():
    print(f"{rel.alias}: {comp.statement}")

# Get single connection
result = wu.t.get()  # Returns (component, relationship) or None

# Score a wheel
scorer = TaroRank(alpha=1.0)
scorer.calculate_score(wheel)
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

- **Detailed architecture:** `src/dialectical_framework/graph/CLAUDE.md`
- **Scoring specification:** `docs/scoring.md`
