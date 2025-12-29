# Graph-Native Data Model Reference

This document provides a comprehensive overview of the graph-native dialectical framework implementation using Memgraph/Neo4j.

## Architecture Overview

The graph-native implementation replaces the legacy domain object model with a true graph database structure where:
- **Nodes** = Assessable entities (Components, WisdomUnits, Wheels, etc.)
- **Edges** = Structural relationships (containment, composition, critique)
- **Properties** = Scores, estimations, metadata stored on nodes

## Node Hierarchy

```
Wheel (top-level composite)
  ├─ WisdomUnits (1+)
  │   ├─ DialecticalComponents (T, A, T+, A-, T-, A+, S+, S-)
  │   │   └─ Rationales (0+) [explains components]
  │   │       └─ Rationales (0+) [critiques of critiques, recursive]
  │   └─ Transformation (0-1 internal spiral)
  │       ├─ Transitions (2: T-→A+, A-→T+)
  │       └─ ac_re: WisdomUnit (action-reflection context)
  ├─ Cycles (T-cycle, TA-cycle)
  │   └─ Transitions (2+)
  │       ├─ source: DialecticalComponent
  │       ├─ target: DialecticalComponent
  │       └─ Rationales (0+)
  └─ Spiral (0-1 transformational analysis)
      └─ Transitions (2+)
```

## Core Node Types

### Assessable Entities (inherit from AssessableEntity)

All scorable nodes inherit from `AssessableEntity`:

- **DialecticalComponent**: Leaf nodes representing statements (T, A, T+, A-, etc.)
- **Transition**: Edge-like nodes representing relationships between components
- **Rationale**: Explanatory/critique nodes that justify scores
- **WisdomUnit**: Composite containing thesis-antithesis pairs + synthesis
- **Transformation**: Internal spiral within a WisdomUnit
- **Cycle**: Sequence of transitions forming causal chain
- **Spiral**: Transformational sequence (softer semantics than Cycle)
- **Wheel**: Top-level composite containing multiple WisdomUnits

### Estimation Nodes (separate from AssessableEntity hierarchy)

Estimations store P and R values:

- **ProbabilityEstimation**: Manual probability assessment
- **RelevanceEstimation**: Manual relevance assessment
- **CalculatedProbabilityEstimation**: Computed probability from children
- **CalculatedRelevanceEstimation**: Computed relevance from children

**Key Design**: Separating manual from calculated prevents circular dependencies during scoring.

## Relationship Patterns

### RelationshipTo vs RelationshipFrom

**Critical Concept**: These define the **same edge** from different perspectives:

- **`RelationshipTo(Target)`**: Outgoing edge → defines `SourceNode→TargetNode`
- **`RelationshipFrom(Source)`**: Incoming edge ← sees `SourceNode→TargetNode` from target's perspective

**Example**:
```python
# WisdomUnit defines outgoing edge to Wheel
class WisdomUnit:
    wheel = RelationshipTo("Wheel", "BELONGS_TO_WHEEL")  # WU→Wheel

# Wheel defines incoming edge from WisdomUnits (SAME edge, different view)
class Wheel:
    wisdom_units = RelationshipFrom("WisdomUnit", "BELONGS_TO_WHEEL")  # WU→Wheel
```

### Parent-Child Relationships (Containment)

All **child→parent** edges use `RelationshipTo()` on the child:

| Child | Parent | Relationship | Edge Direction |
|-------|--------|--------------|----------------|
| WisdomUnit | Wheel | `wu.wheel` | WU→Wheel |
| Transformation | WisdomUnit | `trans.wisdom_unit` | Trans→WU |
| Transformation | WisdomUnit (ac_re) | `trans.ac_re` | Trans→WU(ac_re) |
| DialecticalComponent | WisdomUnit | `comp` in `wu.t`, `wu.t_plus`, etc. | Comp→WU |
| Transition | Cycle/Spiral | `trans` in `cycle.transitions` | Trans→Cycle |
| Cycle | Wheel | `cycle._wheel_as_t` | Cycle→Wheel |
| Spiral | Wheel | `spiral._wheel_as_spiral` | Spiral→Wheel |
| Rationale | AssessableEntity | `rat.explanation` | Rat→Entity |

**Parents** use `RelationshipFrom()` to see these edges from their side.

### Rationale Relationships (Evidence)

Rationales provide evidence for assessable entities:

```python
class AssessableEntity:
    rationales = RelationshipFrom("Rationale", "EXPLAINS")  # Rat→Entity

class Rationale:
    explanation = RelationshipTo("AssessableEntity", "EXPLAINS")  # Rat→Entity
    critiques = RelationshipTo("Rationale", "CRITIQUES")  # RatA→RatB (critique→critiqued)
```

**Semantic**: Rationales can critique other rationales recursively, implementing audit-wins semantics where deepest critique overrides parent rationale values.

### Transition Relationships

Transitions connect components:

```python
class Transition:
    source = RelationshipTo("DialecticalComponent", "IS_SOURCE_OF")  # Trans→Source
    target = RelationshipTo("DialecticalComponent", "IS_TARGET_OF")  # Trans→Target
```

## Cardinality Constraints

Cardinality is expressed as `(min, max)` where `None` = unbounded:

| Pattern | Meaning | Example |
|---------|---------|---------|
| `(1, 1)` | Exactly one | `WisdomUnit.t` (exactly 1 T component) |
| `(1, 1)` | Exactly one | `WisdomUnit.t_plus` (exactly 1 T+ component) |
| `(0, 1)` | Zero or one | `WisdomUnit.transformation` (optional) |
| `(0, None)` | Zero or more | `WisdomUnit.s_plus` (0+ S+ components) |

**Important**: Each polarity position (T, A, T+, T-, A+, A-) holds exactly ONE component. Multiple explorations of the same thesis require multiple WisdomUnits (alternatives).

## Scoring Architecture (TaroRank)

### Score Formula

```
Score = P × R^α
```

Where:
- **P** (Probability): Structural feasibility (0.0-1.0)
- **R** (Relevance): Dialectical quality (0.0-1.0)
- **α** (Alpha): Relevance exponent (default 1.0)

### Scoring Flow

```
1. Check if score is valid (cached)
2. Detect cycles (prevent infinite recursion)
3. Clear calculated estimations (P, R) from this node
4. Recursively score all children (depth-first)
5. Calculate node's P and R from children + rationales
6. Store calculated P and R
7. Compute Score = P × R^α
8. Store score with timestamp
```

### Calculator Hierarchy

Each node type has a specialized calculator:

- **ComponentCalculator**: Aggregates own P/R with rationale P/R via GM
- **TransitionCalculator**: Same as component (leaf-like)
- **RationaleCalculator**: Delegates to RationaleAuditor for critique handling
- **WisdomUnitCalculator**: Power mean of symmetric pairs + transformation + rationales
- **TransformationCalculator**: Product of transition Ps (soft policy) + GM of transition Rs + ac_re R
- **CycleCalculator**: Product of transition Ps (hard veto) + GM of transition Rs
- **SpiralCalculator**: Product of transition Ps (soft policy) + GM of transition Rs
- **WheelCalculator**: GM of canonical cycles + WU transformations (summarized)

### Aggregation Methods

| Method | Use Case | Formula |
|--------|----------|---------|
| **GM (Geometric Mean)** | Independent evidence | nth_root(x₁ × x₂ × ... × xₙ) |
| **PM (Power Mean, p=4)** | Symmetric pairs | (Σxᵢ⁴/n)^(1/4) |
| **Product** | Sequential probability | P₁ × P₂ × ... × Pₙ |
| **Weighted Average** | Rated critiques | Σ(xᵢ × wᵢ) / Σwᵢ |

**Key Distinction**:
- **GM**: For independent evidence (own value + rationales)
- **Product**: For sequential feasibility (transitions in cycle)
- **Power Mean**: For dialectical symmetry (T↔A pairs)

### Hard Veto vs Soft Exclusion

**Element's own R=0 or P=0**: Hard veto
- Returns 0 immediately (authority decision)
- Example: Component with R=0 → component.R = 0

**Rationale R=0 or P=0**: Soft exclusion
- Filtered out, doesn't veto parent (advisory evidence)
- Example: Rationale with R=0 → excluded from GM, parent can still have R>0

**Philosophy**: Element is authority, rationales are advisors.

## Invalidation Propagation

### When Estimations Change

When a node's estimation is updated (manual P or R change):

1. **Clear calculated estimations** from this node
2. **Invalidate node** by setting `score_invalidated_at = now()`
3. **Recursively invalidate parents** up the containment hierarchy

### Parent Traversal

Uses directed query to find only parents:

```cypher
MATCH (child)-[rel]->(parent:AssessableEntity)
WHERE id(child) = $child_id
AND type(rel) <> 'HAS_STATEMENT'
RETURN DISTINCT id(parent) as parent_id
```

**Critical**: Uses `(child)-[rel]->(parent)` (directed) NOT `(child)-[rel]-(parent)` (undirected) to avoid finding children.

**Excluded**: `HAS_STATEMENT` relationships prevent crossing wheel boundaries (derivation, not containment).

### Recursive Invalidation

```python
def _invalidate_node_and_parents(node, visited):
    if node in visited: return  # Cycle detection
    visited.add(node)

    node.score_invalidated_at = now()
    node.save()

    for parent in find_parents(node):
        _invalidate_node_and_parents(parent, visited)  # Recurse upward
```

**Example Flow**:
```
Component updated (manual R change)
  → Invalidate Component
  → Find WisdomUnit (parent)
    → Invalidate WisdomUnit
    → Find Wheel (grandparent)
      → Invalidate Wheel
      → No more parents, done
```

## Cycle Detection

Two levels of cycle detection:

### 1. Scoring Cycle Detection

Prevents infinite recursion when circular dependencies exist (e.g., WU_A → Trans_A → ac_re: WU_B → Trans_B → ac_re: WU_A):

```python
# TaroRank maintains scoring stack
self._scoring_stack: set[str] = set()

if node.uid in self._scoring_stack:
    return None  # Cycle detected, return gracefully

self._scoring_stack.add(node.uid)
try:
    # ... score node ...
finally:
    self._scoring_stack.discard(node.uid)
```

### 2. Invalidation Cycle Detection

Prevents infinite loops during parent traversal:

```python
visited: set[int] = set()

if node._id in visited:
    return  # Already visited, stop

visited.add(node._id)
# ... invalidate and recurse ...
```

## Special Cases and Design Patterns

### WisdomUnit Without Transformation

**Probability**: Returns `P = 1.0` (no structural constraint)
- Philosophy: Absence of constraint ≠ unknown feasibility
- Allows base-case WUs to be scored on dialectical merit alone

**Relevance**: Computed from component pairs only (no transformation.R)

### Single Component per Polarity Position

Each polarity position holds exactly ONE component:

```python
# t_plus has cardinality (1, 1) - exactly one
wu.t_plus.connect(Comp1(R=0.8))

# To explore alternative T+ consequences, create separate WisdomUnits
wu2.t_plus.connect(Comp2(R=0.9))  # Different WU, same T, different T+
wu3.t_plus.connect(Comp3(R=0.7))  # Another alternative

# Alternatives can share the same T component node (component reuse)
t = get_or_create_component("Remote work")
wu1.t.connect(t)
wu2.t.connect(t)  # Same T node, different exploration
wu3.t.connect(t)

# Find alternatives via query: "Find all WUs sharing this T component"
```

### Wheel Transition Deduplication

Transitions can be shared across T-cycle, TA-cycle, and Spiral. Wheel calculator deduplicates with specificity preference:

**Priority**: Spiral > TA-cycle > T-cycle (most specific wins)

```python
unique_transitions = {}
for trans in t_cycle.transitions: unique_transitions[trans.uid] = trans
for trans in ta_cycle.transitions: unique_transitions[trans.uid] = trans  # Overwrite
for trans in spiral.transitions: unique_transitions[trans.uid] = trans  # Overwrite
```

Prevents double-counting same transition's relevance.

### WU Transformation Probability Summarization

Wheel probability uses summarized WU transformations to prevent over-weighting:

```python
# Individual WU transformation Ps
wu_ps = [wu1.P, wu2.P, wu3.P]

# Summarize first via GM
internal_summary = GM(wu_ps)

# Then include as single term
wheel_p = GM(t_cycle.P, ta_cycle.P, spiral.P, internal_summary)
```

**Not**: `GM(t_cycle.P, ta_cycle.P, spiral.P, wu1.P, wu2.P, wu3.P)` ← would over-weight internals

## Key Design Principles

### 1. Separation of Manual vs Calculated

**Problem**: Circular dependency if calculated P/R stored on same nodes
**Solution**: Separate estimation node types (Manual vs Calculated)

### 2. Clear-Before-Calculate

**Pattern**: Clear calculated estimations BEFORE scoring
**Benefit**: Properties return correct values (manual during calculation, calculated after)

### 3. Invalidation Propagates Upward Only

**Rule**: Child changes invalidate ancestors, not descendants
**Implementation**: Follow only outgoing edges (child→parent) during invalidation

### 4. Score Validity Caching

**Check**: `is_score_valid()` returns True if:
- Score exists
- Score was computed (has timestamp)
- Either never invalidated OR computed after last invalidation

**Optimization**: Skip rescoring valid nodes (hierarchical invalidation ensures correctness)

### 5. Rationale Audit-Wins Semantics

**Rule**: Deepest critique overrides parent rationale value
**Implementation**: RationaleAuditor recursively finds deepest critiques, uses those

### 6. Type Safety with TYPE_CHECKING

**Pattern**: Use `from __future__ import annotations` + `TYPE_CHECKING` guard
**Benefit**: Avoid circular imports while maintaining IDE autocomplete

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some.module import SomeType

def my_function(arg: SomeType) -> list[SomeType]:  # No quotes!
    ...
```

## Common Pitfalls

### ❌ Using Undirected Patterns for Parent Finding

```cypher
# WRONG - matches both directions
MATCH (child)-[rel]-(parent)

# CORRECT - matches only outgoing (child→parent)
MATCH (child)-[rel]->(parent)
```

### ❌ Forgetting to Apply Rationale.rating

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

### ❌ Using Only First Component When Multiple Exist

```python
# WRONG - ignores other components
comps = [c for c, _ in rel_manager.all()]
return comps[0].relevance

# CORRECT - aggregate all via GM
comp_rs = [c.relevance for c in comps if c.relevance is not None]
return gm_with_zeros_and_nones_handled(comp_rs)
```

### ❌ Mixing Hard Veto and Soft Exclusion

```python
# Element's own value (HARD VETO)
if component.relevance == 0:
    return 0.0  # Authority decision

# Rationale value (SOFT EXCLUSION)
rat_r = auditor.get_relevance(rationale)
if rat_r is not None and rat_r > 0.0:  # Filter, don't veto
    values.append(rat_r)
```

## Quick Reference: Node Properties

### All AssessableEntity Nodes Have

- `uid`: Unique identifier (string)
- `score`: Final composite score (float or None)
- `score_computed_at`: Timestamp of last scoring
- `score_invalidated_at`: Timestamp of invalidation (if any)
- `rationales`: Relationship to Rationale nodes (0+)

### Accessing P and R

```python
# Properties delegate to estimation nodes
node.probability  # Gets from ProbabilityEstimation or CalculatedProbabilityEstimation
node.relevance    # Gets from RelevanceEstimation or CalculatedRelevanceEstimation

# Direct estimation access
estimations = node.estimations.all()  # Gets all estimation nodes
```

### Checking Score Validity

```python
if node.is_score_valid():
    return node.score  # Use cached score
else:
    # Need to rescore
    score = scorer.calculate_score(node)
```

## Testing the Graph

### Manual P/R Updates Trigger Invalidation

```python
# Update manual estimation
estimation_manager.upsert_estimation(component, ProbabilityEstimation, 0.8)

# Automatically invalidates:
# - component
# - wisdom_unit (parent)
# - wheel (grandparent)

# Next scoring will recalculate all three
```

### Scoring Traversal Order

```python
# Depth-first, bottom-up
scorer.calculate_score(wheel)
  → scores all WisdomUnits
    → scores all Components (leaves)
    → scores Transformation
      → scores ac_re WisdomUnit (may recurse)
      → scores Transitions
    → aggregates WU score
  → scores Cycles
  → aggregates Wheel score
```

## Migration Notes (Legacy → Graph-Native)

### Key Differences

1. **Synthesis**: Legacy had separate `Synthesis` object (inherited WheelSegment with t, t_plus, t_minus). Graph-native has direct `s_plus`, `s_minus` relationships on WisdomUnit.

2. **Neutral S**: Legacy had `synthesis.t` (neutral S) that was scored but never used. Graph-native correctly omits it.

3. **Cardinality**: Both legacy and graph-native enforce exactly ONE component per polarity position (T, A, T+, T-, A+, A-). To explore alternative consequences, create multiple WisdomUnits that share the same T/A component nodes (component reuse pattern).

4. **Transformation Optional**: Both allow optional transformation, but graph-native returns `P=1.0` (no constraint) vs legacy `P=None` (unknown). Graph-native semantics preferred.

5. **Rationale Rating**: Both support `rationale.rating`, but graph-native properly applies it during aggregation (parent applies rating).

6. **Component Reuse**: Graph-native supports reusing the same component node across multiple WisdomUnits. This enables implicit "alternative" relationships discoverable via queries (e.g., "find all WUs exploring this thesis").

## Further Reading

- **scoring.md**: Complete TaroRank specification with examples
- **CLAUDE.md** (project root): Development commands, testing, conventions
- **relationship_manager.py**: Declarative relationship API documentation
- **tarorank_calculators/**: Individual calculator implementations with detailed docstrings
