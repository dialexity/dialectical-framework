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
| **DialecticalComponent** | Atomic statement | `oppositions`, `source_of`, `target_of` |
| **WisdomUnit** | Thesis-antithesis pair | `t`, `a`, `t_plus`, `t_minus`, `a_plus`, `a_minus`, `nexus` |
| **Nexus** | Pool of WisdomUnits | `wisdom_units`, `cycles`, `shrinks_to`, `expands_to` |
| **Synthesis** | Emergent S+/S- pair | `s_plus`, `s_minus`, `wisdom_unit` |
| **Transition** | Component relationship | `source`, `target`, `cycle` |
| **Cycle** | Causal loop | `transitions`, `nexus`, `wheels` |
| **Spiral** | Transformational sequence | `transitions`, `wheel` |
| **Transformation** | Internal WU spiral | `transitions`, `wisdom_unit`, `ac_re` |
| **Wheel** | Top container | `cycle`, `transitions`, `spiral`, `input_uri` |
| **Rationale** | Evidence/explanation | `explanation`, `critiques` |
| **Estimation** | P/R values | `assessed_entity` |
| **Input** | Content source | `statements` (optional, for extraction provenance) |

## Wheel as Self-Contained Artifact

A Wheel carries its source reference directly via `input_uri`, making it a portable, self-contained analytical artifact:

```python
wheel = Wheel(input_uri="https://example.com/article")
wheel.save()

# Later: reconstruct analysis context
print(f"This wheel analyzes: {wheel.input_uri}")
```

**Design rationale:**
- Wheels can be shared/exported independently
- No dependency on external Input nodes for provenance
- All WisdomUnits in a Wheel share the same source (the Wheel's `input_uri`)
- Components are vocabulary—their extraction origin is an app-level concern

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
nexus1.shrinks_to.connect(nexus2)   # Reduction: fewer WUs
nexus1.expands_to.connect(nexus3)   # Growth: more WUs
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

- **Detailed architecture:** `src/dialectical_framework/graph/CLAUDE.md`
- **Scoring specification:** `docs/scoring.md`
