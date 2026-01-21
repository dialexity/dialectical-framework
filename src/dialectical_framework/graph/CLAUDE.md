# Graph Module - AI Co-Developer Guide

This is the core graph-native data model for the Dialectical Framework. Everything here uses Memgraph/Neo4j via GQLAlchemy.

**Quick reference**: See `docs/graph.md` in the project root.
**Scoring details**: See `docs/scoring.md` for complete TaroRank specification.

---

## Quick Start: Common Operations

### Create a WisdomUnit with Components

```python
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.relationships.polarity_relationship import TRelationship, ARelationship

# Create and save nodes
wu = WisdomUnit()
wu.save()

t = DialecticalComponent(statement="Remote work increases productivity")
t.save()

a = DialecticalComponent(statement="Office work enables collaboration")
a.save()

# Connect with polarity relationships
wu.t.connect(t, relationship=TRelationship(alias="T"))
wu.a.connect(a, relationship=ARelationship(alias="A"))

# Access connected nodes
t_result = wu.t.get()  # Returns (node, relationship) or None
if t_result:
    component, rel = t_result
    print(f"{rel.alias}: {component.statement}")
```

### Score a Node

```python
from dependency_injector.wiring import inject, Provide
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.scoring.tarorank import TaroRank

@inject
def score_it(wheel, tarorank: TaroRank = Provide[DI.tarorank]):
    tarorank.score_node(wheel)
    print(f"Score: {wheel.score}, P: {wheel.probability}, R: {wheel.relevance}")
```

### Add a Rationale

```python
from dialectical_framework.graph.nodes.rationale import Rationale

rationale = Rationale(
    text="Studies show 54min average commute savings",
    headline="Commute savings",
)
rationale.save()

# Set estimation values
from dialectical_framework.graph.estimation_manager import upsert_estimation
from dialectical_framework.graph.nodes.estimation import RelevanceEstimation

upsert_estimation(rationale, RelevanceEstimation, 0.85)

# Connect to component (Rationale explains Component)
rationale.explanation.connect(component)
```

### Create Input Source

```python
from dialectical_framework.graph.nodes.input import Input

input_node = Input(
    content_uri="https://example.com/article",
    handle="article-2024-01"
)
input_node.save()

# Link extracted statements
input_node.statements.connect(component1)
input_node.statements.connect(component2)
```

---

## File Map

```
graph/
├── nodes/                          # All node types
│   ├── base_node.py               # BaseNode (uid, handle, uri, save())
│   ├── assessable_entity.py       # AssessableEntity (score, P, R, rationales)
│   ├── dialectical_component.py   # DialecticalComponent (statement)
│   ├── wisdom_unit.py             # WisdomUnit (t, a, t_plus, t_minus, nexus)
│   ├── nexus.py                   # Nexus (pool of WisdomUnits, cycles)
│   ├── wheel.py                   # Wheel (cycle, transitions, spiral)
│   ├── cycle.py                   # Cycle (transitions, nexus, wheels)
│   ├── spiral.py                  # Spiral (transitions)
│   ├── transformation.py          # Transformation (internal WU spiral)
│   ├── transition.py              # Transition (source, target)
│   ├── synthesis.py               # Synthesis (s_plus, s_minus)
│   ├── rationale.py               # Rationale (text, headline, critiques)
│   ├── estimation.py              # P/R estimation nodes
│   └── input.py                   # Input (content sources)
│
├── relationships/                  # Relationship models
│   ├── polarity_relationship.py   # T/A/T+/T-/A+/A-/S+/S- relationships
│   └── opposition_relationship.py # Opposition edges
│
├── scoring/                        # TaroRank implementation
│   ├── tarorank.py                # Main scorer (Score = P × R^α)
│   ├── gm.py                      # Geometric mean
│   ├── pm.py                      # Power mean
│   └── tarorank_calculators/      # Per-node-type calculators
│       ├── base_calculator.py
│       ├── dialectical_component_calculator.py
│       ├── wisdom_unit_calculator.py
│       ├── nexus_calculator.py    # Nexus: GM of WisdomUnit scores
│       ├── wheel_calculator.py
│       ├── cycle_calculator.py
│       ├── spiral_calculator.py
│       ├── transformation_calculator.py
│       ├── transition_calculator.py
│       ├── rationale_calculator.py
│       └── synthesis_calculator.py
│
├── repositories/                   # Data access
│   ├── dialectical_component_repository.py
│   └── wisdom_unit_repository.py
│
├── relationship_manager.py         # RelationshipTo/From declarative API
├── estimation_manager.py           # Estimation CRUD + invalidation propagation
├── wheel_segment.py                # Logical segment grouping
└── wheel_segment_polar_pair.py     # T/A polar pairs
```

---

## Node Hierarchy

```
BaseNode (uid, handle, save())
  │
  ├── AssessableEntity (score, probability, relevance, rationales, estimations)
  │   ├── DialecticalComponent   # Leaf: statements (T, A, T+, T-, A+, A-, S+, S-)
  │   ├── Transition             # Leaf: connects components (source→target)
  │   ├── Rationale              # Leaf: evidence/critique with audit-wins semantics
  │   ├── Synthesis              # Composite: S+/S- pair
  │   ├── WisdomUnit             # Composite: T-side + A-side + optional synthesis/transformation
  │   ├── Nexus                  # Pool: collection of WisdomUnits for shared analysis
  │   ├── Transformation         # Composite: internal spiral (2 transitions)
  │   ├── Cycle                  # Composite: causal sequence from Nexus
  │   ├── Spiral                 # Composite: transformational sequence
  │   └── Wheel                  # Top-level: detailed view of Cycle with transitions
  │
  ├── Input                      # NOT assessable: content source (content_uri→statements)
  │
  └── Estimation                 # NOT assessable: P/R values
```

**Score Flow (child → parent):**
```
Component → WisdomUnit → Nexus → Cycle → Wheel
```

### Node Containment (Nexus-based Structure)

```
Wheel (top-level container)
  └── Cycle (parent, required)
      ├── Nexus (pool of WisdomUnits)
      │   └── WisdomUnits (1+)
      │       ├── DialecticalComponents (T, A, T+, T-, A+, A-)
      │       │   └── Rationales (0+) → Rationales (0+) [recursive critiques]
      │       ├── Synthesis (0-N)
      │       │   └── DialecticalComponents (S+, S-)
      │       └── Transformation (0-1)
      │           ├── Transitions (exactly 2: T-→A+, A-→T+)
      │           └── ac_re: WisdomUnit (action-reflection context)
      └── Transitions (2+, cycle-level)
  ├── Transitions (wheel-level, more detailed)
  └── Spiral (0-1)
      └── Transitions (2+)
```

**Key insight:** Nexus is a "pool" of WisdomUnits that can be shared across
different Cycles and analytical perspectives. WisdomUnits can belong to
multiple Nexuses within the same `t_cycle` group.

**Note:** Provenance traces through Nexus to Input nodes via `get_root_inputs()`.

---

## Relationship Manager API

The `RelationshipManager` provides a declarative, neomodel-like API for graph relationships.

### Core Methods

```python
# Connect nodes
wu.t.connect(component)                              # Basic connection
wu.t.connect(component, relationship=TRelationship(alias="T1"))  # With properties

# Access connections
result = wu.t.get()          # Returns (node, relationship) or None
all_items = wu.t.all()       # Returns [(node, rel), ...]
count = wu.t.count()         # Returns int

# Disconnect
wu.t.disconnect(component)
```

### RelationshipTo vs RelationshipFrom

These define the **SAME edge** from different perspectives:

```python
# Child defines outgoing edge TO parent
class WisdomUnit(AssessableEntity):
    nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")  # WU→Nexus

# Parent sees same edge FROM children
class Nexus(AssessableEntity):
    wisdom_units = RelationshipFrom("WisdomUnit", "BELONGS_TO_NEXUS")  # Same edge!
```

**Convention**: Child→Parent edges use `RelationshipTo` on the child.

**Full Nexus-based hierarchy:**
```python
WU.nexus.connect(nexus)      # WU → Nexus
nexus.cycles.connect(cycle)   # Nexus → Cycle
cycle.wheels.connect(wheel)   # Cycle → Wheel
```

### Cardinality

```python
# Exactly one (required)
t: ClassVar[RelationshipManager[Component]] = RelationshipFrom(..., cardinality=(1, 1))

# Zero or one (optional)
transformation: ClassVar[...] = RelationshipFrom(..., cardinality=(0, 1))

# Zero or more (unbounded)
rationales: ClassVar[...] = RelationshipFrom(..., cardinality=(0, None))
```

### All Relationship Mappings

| Child | Parent | Edge Type | Child Attr | Parent Attr |
|-------|--------|-----------|------------|-------------|
| WisdomUnit | Nexus | BELONGS_TO_NEXUS | `nexus` | `wisdom_units` |
| Nexus | Cycle | HAS_CYCLE | `cycles` | `nexus` |
| Cycle | Wheel | HAS_WHEEL | `wheels` | `cycle` |
| DialecticalComponent | WisdomUnit | T/A/T+/T-/A+/A- | - | `t`, `a`, `t_plus`, etc. |
| Transformation | WisdomUnit | TRANSFORMATION_OF | `wisdom_unit` | `transformation` |
| Transformation | WisdomUnit | AC_RE_OF | `ac_re` | - |
| Transition | Cycle/Spiral/Wheel | TRANSITION_OF | `cycle` | `transitions` |
| Spiral | Wheel | SPIRAL_OF | `wheel` | `spiral` |
| Rationale | AssessableEntity | EXPLAINS | `explanation` | `rationales` |
| Rationale | Rationale | CRITIQUES | `critiques` | `_critiqued_by` |
| Input | DialecticalComponent | HAS_STATEMENT | `statements` | `_source_inputs` |
| Transition | DialecticalComponent | IS_SOURCE_OF | `source` | `source_of` |
| Transition | DialecticalComponent | IS_TARGET_OF | `target` | `target_of` |
| Nexus | Nexus | SHRINKS_TO | `shrinks_to` | `shrunk_from` |
| Nexus | Nexus | EXPANDS_TO | `expands_to` | `expanded_from` |
| WisdomUnit | WisdomUnit | CHANGED_TO | `changed_to` | `changed_from` |

---

## Scoring Architecture (TaroRank)

### Formula

```
Score = P × R^α
```

- **P** (Probability): Structural feasibility (0.0-1.0)
- **R** (Relevance): Dialectical quality / contextual fit (0.0-1.0)
- **α** (Alpha): Relevance exponent (default 1.0)

### Calculator per Node Type

| Node | Calculator | P Logic | R Logic |
|------|------------|---------|---------|
| DialecticalComponent | `ComponentCalculator` | GM(own, rationales) | GM(own, rationales) |
| Transition | `TransitionCalculator` | GM(own, rationales) | GM(own, rationales) |
| Rationale | `RationaleCalculator` | Audit-wins (deepest critique) | Audit-wins |
| WisdomUnit | `WisdomUnitCalculator` | Transformation.P | PM(T↔A pairs) + transformation.R |
| Nexus | `NexusCalculator` | GM(WU transformation Ps) | GM(WU relevances) |
| Transformation | `TransformationCalculator` | Product(transitions) | GM(transitions) + ac_re.R |
| Cycle | `CycleCalculator` | Product(transitions) + Nexus.P | GM(transitions) + Nexus.R |
| Spiral | `SpiralCalculator` | Product(transitions) | GM(transitions) |
| Synthesis | `SynthesisCalculator` | GM(s_plus, s_minus) | GM(s_plus, s_minus) |
| Wheel | `WheelCalculator` | GM(Cycle.P, Nexus.P, wheel trans) | GM(Nexus.R, transitions) |

### Aggregation Methods

| Method | Use Case | Formula |
|--------|----------|---------|
| **GM** | Independent evidence | nth_root(x₁ × x₂ × ... × xₙ) |
| **PM (p=4)** | Symmetric pairs (T↔A) | (Σxᵢ⁴/n)^(1/4) |
| **Product** | Sequential probability | P₁ × P₂ × ... × Pₙ |

### Hard Veto vs Soft Exclusion

```python
# Element's own R=0 or P=0 → HARD VETO (returns 0)
if component.relevance == 0:
    return 0.0  # Authority decision

# Rationale R=0 or P=0 → SOFT EXCLUSION (filtered out, no veto)
if rationale.relevance == 0:
    pass  # Skip, but parent can still have R>0
```

**Philosophy**: Element is authority, rationales are advisors.

---

## Estimation Management

### Manual vs Calculated Estimations

**Manual** (set by user/system):
- `ProbabilityEstimation`
- `RelevanceEstimation`
- `FeasibilityEstimation` (fallback R)

**Calculated** (set by TaroRank):
- `CalculatedProbabilityEstimation`
- `CalculatedRelevanceEstimation`

### CRUD Operations

```python
from dialectical_framework.graph.estimation_manager import upsert_estimation
from dialectical_framework.graph.nodes.estimation import (
    ProbabilityEstimation,
    RelevanceEstimation,
)

# Create/update estimation
upsert_estimation(component, ProbabilityEstimation, 0.8)
upsert_estimation(component, RelevanceEstimation, 0.9)

# Access via properties (auto-resolves manual vs calculated)
p = component.probability  # Returns calculated if exists, else manual
r = component.relevance    # Returns calculated, else manual, else feasibility
```

### Invalidation

When manual estimation changes:
1. Clear calculated estimations from node
2. Set `score_invalidated_at = now()`
3. Recursively invalidate parents (upward only)

```python
# Invalidation happens automatically via estimation_manager
upsert_estimation(component, RelevanceEstimation, 0.5)
# → component invalidated
# → wisdom_unit (parent) invalidated
# → wheel (grandparent) invalidated
```

---

## Adding New Things

### Add a New Node Type

1. **Create class** in `graph/nodes/`:

```python
# graph/nodes/my_node.py
from __future__ import annotations
from typing import ClassVar, TYPE_CHECKING
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipManager, RelationshipFrom

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.rationale import Rationale

class MyNode(AssessableEntity):
    my_field: str = ""

    # Relationships (if any)
    rationales: ClassVar[RelationshipManager[Rationale]] = RelationshipFrom(
        "Rationale", "EXPLAINS", cardinality=(0, None)
    )
```

2. **Add calculator** (if assessable) in `graph/scoring/tarorank_calculators/`:

```python
# graph/scoring/tarorank_calculators/my_node_calculator.py
from __future__ import annotations
from .base_calculator import BaseCalculator

class MyNodeCalculator(BaseCalculator):
    def calculate_probability(self, node) -> float | None:
        # Your P logic
        return 1.0

    def calculate_relevance(self, node) -> float | None:
        # Your R logic
        return node.relevance
```

3. **Register calculator** in `graph/scoring/tarorank.py`:

```python
from .tarorank_calculators.my_node_calculator import MyNodeCalculator

class TaroRank:
    def __init__(self, ...):
        self._calculators = {
            # ... existing ...
            MyNode: MyNodeCalculator(self),
        }
```

### Add a New Relationship Type

1. **Create relationship model** (if needed) in `graph/relationships/`:

```python
# graph/relationships/my_relationship.py
from gqlalchemy import Relationship

class MyRelationship(Relationship, type="MY_EDGE"):
    custom_property: str = ""
```

2. **Add to node classes**:

```python
# In source node (child)
class ChildNode(BaseNode):
    parent = RelationshipTo("ParentNode", "MY_EDGE", model=MyRelationship)

# In target node (parent)
class ParentNode(BaseNode):
    children = RelationshipFrom("ChildNode", "MY_EDGE", model=MyRelationship)
```

---

## Common Pitfalls

### Using Undirected Queries for Parent Finding

```cypher
# WRONG - matches both directions
MATCH (child)-[rel]-(parent)

# CORRECT - matches only outgoing (child→parent)
MATCH (child)-[rel]->(parent)
```

### Forgetting ClassVar for Descriptors

```python
# WRONG - GQLAlchemy tries to treat as Pydantic field
transitions: RelationshipManager[Transition] = RelationshipFrom(...)

# CORRECT - ClassVar tells metaclass to skip
transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(...)
```

### Forgetting to Apply Rationale Rating

```python
# WRONG - missing rating application
rat_r = auditor.get_relevance(rationale)
values.append(rat_r)

# CORRECT - parent applies rating
rat_r = auditor.get_relevance(rationale)
rating = rationale.rating if rationale.rating is not None else 1.0
weighted_r = rat_r * rating
if weighted_r > 0.0:
    values.append(weighted_r)
```

### Mixing Hard Veto and Soft Exclusion

```python
# Element's own value = HARD VETO
if component.relevance == 0:
    return 0.0

# Rationale value = SOFT EXCLUSION (filter, don't veto)
rat_r = auditor.get_relevance(rationale)
if rat_r is not None and rat_r > 0.0:
    values.append(rat_r)
```

### Using Quoted Type Strings

```python
# WRONG
def get_nodes() -> "list[MyNode]":
    ...

# CORRECT - use from __future__ import annotations
from __future__ import annotations

def get_nodes() -> list[MyNode]:
    ...
```

---

## Key Design Principles

1. **Child→Parent edges**: Child nodes define `RelationshipTo` parent
2. **Separate manual/calculated**: Prevents circular dependencies during scoring
3. **Clear-before-calculate**: Clear calculated estimations before rescoring
4. **Invalidation propagates upward**: Child changes → ancestors invalidated
5. **Audit-wins semantics**: Deepest rationale critique overrides parent values
6. **Element is authority**: Hard veto for element's own zero values
7. **Rationales are advisors**: Soft exclusion for rationale zero values

---

## Quick Reference: Node Properties

### All AssessableEntity Nodes

```python
node.uid                    # Unique identifier (string)
node.score                  # Final composite score (float | None)
node.probability            # P value (calculated or manual)
node.relevance              # R value (calculated, manual, or feasibility)
node.score_computed_at      # Timestamp of last scoring
node.score_invalidated_at   # Timestamp of invalidation
node.is_score_valid()       # True if score is current
node.rationales             # RelationshipManager to Rationale nodes
node.estimations            # RelationshipManager to Estimation nodes
```

### WisdomUnit Specific

```python
wu.t          # T component (cardinality 1,1)
wu.a          # A component (cardinality 1,1)
wu.t_plus     # T+ component (cardinality 1,1)
wu.t_minus    # T- component (cardinality 1,1)
wu.a_plus     # A+ component (cardinality 1,1)
wu.a_minus    # A- component (cardinality 1,1)
wu.synthesis  # Synthesis nodes (cardinality 0,N)
wu.transformation  # Transformation (cardinality 0,1)
wu.nexus      # Parent Nexus (cardinality 0,N - can belong to multiple)
```

### Nexus Specific

```python
nexus.wisdom_units  # WisdomUnits in this pool (cardinality 1,N)
nexus.cycles        # Cycles derived from this Nexus (cardinality 0,N)
nexus.shrinks_to    # Evolution: reduced Nexus (cardinality 0,N)
nexus.expands_to    # Evolution: expanded Nexus (cardinality 0,N)
nexus.shrunk_from   # Inverse of shrinks_to
nexus.expanded_from # Inverse of expands_to
```

### Wheel Specific

```python
wheel.cycle         # Parent Cycle (cardinality 1,1 - required)
wheel.transitions   # Wheel-level transitions (more detailed than Cycle)
wheel.spiral        # Spiral (cardinality 0,1)
wheel.wisdom_units  # Property: WUs via cycle.nexus (not direct relationship)
wheel.get_nexus()   # Helper: access Nexus via Cycle
```

**Provenance Tracing:**

Trace a Wheel's source Inputs via the Nexus hierarchy:

```python
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)

repo = DialecticalComponentRepository()
roots = repo.get_root_inputs(wheel)  # All Inputs that contributed
```

```python
# Create full hierarchy
nexus = Nexus()
nexus.save()
wu.nexus.connect(nexus)

cycle = Cycle()
cycle.save()
nexus.cycles.connect(cycle)

wheel = Wheel()
wheel.save()
cycle.wheels.connect(wheel)

# Access WisdomUnits through the hierarchy
for wu, _ in wheel.wisdom_units:
    print(f"WU: {wu.uid}")
```

---

## Further Reading

- **`docs/graph.md`**: Quick reference guide (human-readable)
- **`docs/scoring.md`**: Complete TaroRank specification with examples
- **`CLAUDE.md`** (project root): Project philosophy, conventions, testing
- **`relationship_manager.py`**: Declarative API implementation
- **`scoring/tarorank_calculators/`**: Individual calculators with docstrings
