# CLAUDE.md - AI Co-Developer Guide

This file provides context for Claude Code to be an effective co-developer on the Dialectical Framework.

## What is the Dialectical Framework?

A semantic graph system for dialectical reasoning - modeling thesis-antithesis-synthesis dynamics as graph structures. Used for systems analysis, wisdom mining, and ethical modeling.

### Core Metaphor: The Wheel

Think of a Dialectical Wheel as a pizza:
- **Wheel** = entire pizza (top-level container)
- **Segment** = pizza slice (contains T, T+, T- components)
- **Perspective** = half-pizza (T-segment + opposing A-segment)

### Key Positions (6 core + 2 synthesis)

| Position | Meaning | Example |
|----------|---------|---------|
| T | Neutral thesis | "Remote work exists" |
| T+ | Positive aspect of thesis | "Eliminates commute" |
| T- | Negative aspect of thesis | "Causes isolation" |
| A | Neutral antithesis | "Office work exists" |
| A+ | Positive aspect of antithesis | "Enables collaboration" |
| A- | Negative aspect of antithesis | "Requires presence" |
| S+ | Positive synthesis | "Hybrid model works" |
| S- | Negative synthesis | "Context switching cost" |

### Structural Elements

- **Transition**: Recipe for moving between segments (T-→A+, A-→T+)
- **Transformation**: Action-Reflection structure with 6 positions (Ac, Re, Ac+, Ac-, Re+, Re-)
  - Belongs to a wheel edge via ACTION_REFLECTION relationship (`transformation.edge`)
  - Each edge can have multiple Transformation alternatives at different insight/proactiveness levels
  - Source/target segments derived from Ac+ transition's source/target components
- **Synthesis**: Emergent S+/S- pair from Transformation
- **Cycle**: T-cycle - ordered sequence of Perspectives defining abstract thesis causality
  - Stores PP hashes directly (cycle.perspective_hashes)
  - Intent field for dynamics type ("preset:balanced", "preset:realistic", etc.)
- **Wheel**: Concrete T-A arrangement implementing a subset of Cycle's PPs
  - `_perspectives`: PPs derived from edge components (internal)
  - `polarity_count`: number of PPs (derived from edges)
  - Contains `edges` (causality sequence / ta_cycle level)
  - Transformations belong to individual edges (access via `wheel.transformations`)
  - Wheels are reused across Cycles if same PP set (rotation-invariant hash)
- **Input**: External content source (URL/IPFS) linked to extracted components
- **Ideas**: Container of distilled concepts from an Input (uses IncrementalBuildMixin: save → add statements → commit)
- **Case**: Multi-input exploration container with unified vocabulary

**Hierarchy:** Perspective → Cycle → Wheel (edges) → Transformation
**Case flow:** Case → Input → Ideas → Components

**Exploration flow:** Perspectives → Nexus (exploration context) → Cycles (T-cycle orderings) → Wheels (TA arrangements)

- **Nexus**: Required exploration container for Perspectives. Groups PPs with a specific intent for layer-by-layer combination into Cycles and Wheels.

**DEPRECATED nodes (kept for backwards compatibility):**
- **Spiral**: Replaced by Transformations on edges

### Intent Levels

All reasoning nodes inherit from `IntentMixin`, providing a unified `intent: Optional[str]` field. Intent maps to the reflective practice framework:

| Level | Reflection | Question | Lives On |
|-------|------------|----------|----------|
| **Discovery** | (Gathering) | What sources to explore? | Ideas |
| **Focus** | What? | What tensions exist? | Cycle |
| **Dynamics** | So What? | Why do they matter? | Cycle (intent field) |
| **Path** | Now What? | How to navigate? | Perspective, Transformation, Wheel |
| **Synthesis** | (Outcome) | What emerges? | Synthesis |

**Nodes with IntentMixin:** Ideas, Cycle, Perspective, Transformation, Synthesis, Wheel

Note: Case does not have intent - it's a container for inputs.

### Transformation Model

**Transformation (per edge)**: Action-Reflection structure with 6 positions:
- Ac (Action): T → A
- Ac+ (Positive Action): T- → A+ (REQUIRED)
- Ac- (Negative Action): T+ → A-
- Re (Reflection): A → T
- Re+ (Positive Reflection): A- → T+ (REQUIRED)
- Re- (Negative Reflection): A+ → T-

**Edges**: Each edge in a wheel's causality sequence can have multiple Transformation alternatives
at different insight/proactiveness levels. Use `transformation.set_on_edge(edge)` to connect.

**Example:**
```python
# Create wheel with edges
wheel = Wheel()
edge1 = Transition()  # T1- → A2+
edge1.set_source(t1_minus).set_target(a2_plus)
edge1.commit()
edge1.cycle.connect(wheel)

# Create transformation for this edge
transformation = Transformation()
transformation.set_on_edge(edge1)
transformation.save()
# ... add ac_plus, re_plus transitions ...
transformation.commit()

# Access all transformations
for tr in wheel.transformations:
    edge_result = tr.edge.get()  # Returns (Transition, rel) tuple
```

### Cardinality Design: Where to Branch

**Cycle is a snapshot:** Contains ordered PP hashes directly. Once committed, immutable.

**Wheel implements subset of Cycle:** Each Wheel uses a subset of the Cycle's PPs, building up in layers.

**To explore different paths, branch upstream:**
- Different transformation interpretations → Create different **Transformations** on same edge
- Different PP pools → Create different **Cycles** within the same **Nexus**
- Different PP arrangements → Create different **Wheels** for the same **Cycle**

Multiple synthesis interpretations are supported via `Synthesis (0, ∞)` on Transformation.

### Layered Combination Model

**Nexus-based exploration:** All Cycles/Wheels are generated from a Nexus containing Perspectives.
The layer structure is implicit in the PP overlap:

```
Given Nexus with [PP1, PP2, PP3]:

Layer 1:  Cycle(PP1)    Cycle(PP2)    Cycle(PP3)
Layer 2:  Cycle(PP1,PP2)  Cycle(PP1,PP3)  Cycle(PP2,PP3)
Layer 3:  Cycle(PP1,PP2,PP3)

Each Cycle can have multiple Wheels (different TA arrangements).
```

**Wheel reuse:** Wheels with same PP set (rotation-invariant hash) are reused across Cycles.

**Transformation context:** When computing Transformations for a wheel, use related wheels'
Transformations as input (coarse → fine refinement).

See `docs/graph.md` → "Intent Levels" and "Branching and Cardinality Rationale" for detailed explanation.

### Structural vs Analytical Layers

The graph separates relationships into two layers:

**Structural Layer** (immutable after commit):
- Forms the Merkle-tree backbone (hash-linked)
- Components, Perspectives, Ideas, Cycle, Wheel, Transitions
- Base classes: `IdentityRelationship`, `ContainerMembership`, `OutgoingContainerMembership`

**Analytical Layer** (can evolve anytime):
- Insights and assessments that don't affect structural hashes
- Rationale, Estimation, Critique, Synthesis, ac_re
- Base class: `AnalyticalStructure`

**Key rule**: Structural containers must follow `save() → add members → commit()`. Analytical relationships can be connected/disconnected even after commit.

```python
# Structural: blocked after container commits
transformation.save()
transition.cycle.connect(transformation)  # OK
transformation.commit()
transition.cycle.connect(transformation)  # BLOCKED

# Analytical: always allowed
transformation.ac_re.connect(new_pp)      # OK even after commit
```

See `docs/graph.md` → "Structural vs Analytical Layers" for full details.

### Semantic Relationships (auto-created)

When connecting components to Perspective positions, semantic relationships are automatically created:

| Relationship | Direction | When Created |
|--------------|-----------|--------------|
| `OPPOSITE_OF` | Symmetric | T ↔ A (dialectical opposition) |
| `CONTRADICTION_OF` | Symmetric | T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity) |
| `POSITIVE_SIDE_OF` | Directed | T+ → T, A+ → A |
| `NEGATIVE_SIDE_OF` | Directed | T- → T, A- → A |
| `SIMILAR_TO` | Directed | Manual creation only |

---

## Quick Navigation

### Where Things Live

| Purpose | Location |
|---------|----------|
| DI Container (START HERE) | `src/dialectical_framework/dialectical_reasoning.py` |
| Graph nodes | `src/dialectical_framework/graph/nodes/*.py` |
| Relationships | `src/dialectical_framework/graph/relationships/*.py` |
| Relationship API | `src/dialectical_framework/graph/relationship_manager.py` |
| Scoring (TaroRank) | `src/dialectical_framework/graph/scoring/tarorank.py` |
| Framework features (API) | `src/dialectical_framework/features/` |
| Agentic orchestration | `src/dialectical_framework/agents/` |
| AI/LLM reasoning | `src/dialectical_framework/synthesist/` |
| Wisdom reasoning | `src/dialectical_framework/synthesist/wisdom/` |
| Configuration | `src/dialectical_framework/settings.py` |
| LLM abstraction | `src/dialectical_framework/brain.py` |

### Key Files to Understand First

1. `graph/nodes/base_node.py` - Foundation (hash, commit(), update())
2. `graph/nodes/assessable_entity.py` - Scoreable nodes (P, R, score)
3. `graph/relationship_manager.py` - Declarative relationship API
4. `graph/relationships/immutable_structure.py` - Layer base classes (Structural vs Analytical)
5. `graph/scoring/tarorank.py` - Score = P × R^α
6. `dialectical_reasoning.py` - DI container setup

---

## Development Commands

This is a Python project using Poetry for dependency management:

- **Install dependencies**: `poetry install`
- **Run tests**: `poetry run pytest` or `pytest` if in activated environment
- **Format code**: `poetry run black src/ tests/`
- **Sort imports**: `poetry run isort src/ tests/`
- **Remove unused imports**: `poetry run autoflake --in-place --remove-all-unused-imports --recursive src/ tests/`
- **Activate virtual environment**: `poetry shell`
- **Build package**: `poetry build`

---

## Architecture Overview

### Technology Stack

- **Graph DB**: Memgraph or Neo4j (via GQLAlchemy)
- **DI**: dependency-injector
- **Validation**: Pydantic v1
- **LLM**: Mirascope (OpenAI, Anthropic, LiteLLM)
- **Python**: 3.11+

### Module Map

```
src/dialectical_framework/
├── brain.py                  # LLM abstraction (provider-agnostic)
├── settings.py               # Configuration via environment
├── dialectical_reasoning.py  # DI container (START HERE)
│
├── graph/                    # Core graph-native data model
│   ├── nodes/               # BaseNode → AssessableEntity → {Component, PP, Wheel, ...}
│   ├── mixins/              # Shared node behaviors (IntentMixin)
│   ├── relationships/       # Polarity, opposition relationship models
│   ├── scoring/             # TaroRank: Score = P × R^α
│   │   └── tarorank_calculators/  # Per-node-type calculators
│   ├── repositories/        # Data access layer
│   └── relationship_manager.py    # RelationshipTo/From declarative API
│
├── features/                # Framework services (API-callable, standalone)
│   ├── thesis_extraction.py    # Extract theses from text
│   ├── aspect_generation.py      # Generate T+, T-, A+, A- aspects
│   ├── transformation_generation.py
│   └── ...                     # 15 feature modules total
│
├── agents/                  # LLM-driven agentic orchestrators
│   ├── executable_capability.py  # Adapter: makes features agent-usable
│   ├── analyst/            # Analysis mode: Input → Ideas → Perspectives
│   │   ├── skills/         # Reasoning brain centers
│   │   │   ├── anchoring.py        # Thesis surfacing & anchoring
│   │   │   ├── polarity.py         # Antithesis finding & polarity creation
│   │   │   └── wisdom.py           # Perspective building
│   │   └── tools/          # Mirascope tools for analyst
│   ├── explorer/           # Exploration mode: PP pool → Cycles → Wheels
│   │   ├── skills/
│   │   │   ├── causality.py        # Cycle & Wheel arrangement
│   │   │   └── transformation.py   # Action-Reflection transformation
│   │   └── tools/
│   └── orchestrator/       # Conversation layer, delegates to analyst/explorer
│
├── synthesist/              # Reasoning engines
│   ├── polarity/           # Polar reasoning (PolarReasoner, Perspective building)
│   ├── causality/          # Order transitions (preset:balanced, preset:realistic, etc.)
│   ├── concepts/           # Concept extraction
│   └── wisdom/             # Transition analysis & validation
│       ├── consultant.py   # Base for transition analysis
│       └── decorators      # Action-reflection, spiral decorators
│
├── protocols/               # Python Protocol interfaces
├── ai_dto/                  # DTOs for LLM communication
├── enums/                   # DI enum, etc.
└── utils/                   # Helpers
```

---

## Core Patterns

### Dependency Injection

```python
from dependency_injector.wiring import inject, Provide
from dialectical_framework.enums.di import DI

@inject
def my_function(
    graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    settings: Settings = Provide[DI.settings],
    tarorank: TaroRank = Provide[DI.tarorank],
):
    # All services injected automatically
    pass
```

### DI Anti-Patterns to Avoid

**`graph_db` is a singleton** - it's registered once in the DI container and the same instance is injected everywhere. This means:

1. **Don't pass `graph_db` between `@inject` methods** - each method gets the same singleton automatically:

```python
# BAD - redundant passing
@inject
def outer_method(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]):
    self.inner_method(graph_db=graph_db)  # Don't do this!

@inject
def inner_method(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]):
    graph_db.execute(...)

# GOOD - let DI inject at each call site
@inject
def outer_method(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]):
    self.inner_method()  # DI injects graph_db automatically

@inject
def inner_method(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]):
    graph_db.execute(...)
```

2. **Don't store `graph_db` as instance variable** - use `@inject` on each method that needs it:

```python
# BAD - storing singleton as instance variable
class MyClass:
    @inject
    def __init__(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]):
        self._graph_db = graph_db  # Don't do this!

    def some_method(self):
        self._graph_db.execute(...)  # Uses stored reference

# GOOD - inject where needed
class MyClass:
    def __init__(self):
        pass

    @inject
    def some_method(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]):
        graph_db.execute(...)  # Fresh injection
```

**Why this matters:** Explicit passing adds verbosity without benefit since DI provides the same singleton. It also obscures the dependency graph and makes refactoring harder.

### Graph Node Lifecycle

**Simple nodes** (DialecticalComponent, Rationale):
```python
component = DialecticalComponent(statement="Remote work increases productivity")
component.commit()  # save + compute hash in one step
```

**Container nodes** (Ideas, Transformation, Spiral, Nexus, Cycle, Wheel) use `IncrementalBuildMixin`:
```python
# Pattern: save() → add members → commit()
transformation = Transformation()
transformation.set_perspective(pp)
transformation.save()  # HEAD state - no hash yet

# Add members while uncommitted
transition.cycle.connect(transformation)  # OK

# Commit after all members added
transformation.commit()  # Computes hash from members, makes immutable
```

**Relationship operations:**
```python
pp = Perspective()
pp.save()

# Connect (child→parent direction)
pp.t.connect(component)

# Access
result = pp.t.get()  # Returns (node, relationship) or None
all_items = pp.t.all()  # Returns [(node, rel), ...]
count = pp.t.count()

# Disconnect
pp.t.disconnect(component)
```

### Relationship Pattern (CRITICAL)

RelationshipTo and RelationshipFrom define the **SAME edge** from different perspectives:

```python
# Child defines outgoing edge TO parent
class Perspective(AssessableEntity):
    nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")  # PP→Nexus

# Parent sees incoming edge FROM children (SAME edge!)
class Nexus(AssessableEntity):
    perspectives = RelationshipFrom("Perspective", "BELONGS_TO_NEXUS")
```

**Convention**: Child→Parent edges use `RelationshipTo` on child.

**Full hierarchy (simplified):**
```
PP.nexus → Nexus.perspectives (reverse)
Cycle.wheels → Wheel
Cycle.perspective_hashes → [PP hashes] (field, not relationship)
```

**Complete scoring hierarchy:**
```
Component → PP → Cycle → Wheel
    │        ▲            ▲
    │        │            │
    │   Transformation ← Synthesis
    │                │
    └→ Synthesis ────┘
```

### Scoring

```python
from dependency_injector.wiring import inject, Provide
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.scoring.tarorank import TaroRank

@inject
def score_wheel(
    wheel: Wheel,
    tarorank: TaroRank = Provide[DI.tarorank]
):
    tarorank.score_node(wheel)  # Recursive depth-first scoring
    print(f"Score: {wheel.score}")  # P × R^α
    print(f"P: {wheel.probability}")
    print(f"R: {wheel.relevance}")
```

---

## Environment Configuration

Required environment variables:
- `DIALEXITY_DEFAULT_MODEL`: Default LLM model (e.g., "gpt-4")
- `DIALEXITY_DEFAULT_MODEL_PROVIDER`: Model provider ("openai", "anthropic", etc.)

Optional:
- `DIALEXITY_GRAPH_DB_VENDOR`: "memgraph" (default) or "neo4j"
- `DIALEXITY_GRAPH_DB_HOST`: Database host (default: "127.0.0.1")
- `DIALEXITY_GRAPH_DB_PORT`: Database port (default: 7687)
- `DIALEXITY_TARORANK_ALPHA`: Relevance exponent (default: 1.0)
- `DIALEXITY_DEFAULT_CYCLE_PRESET`: Default causality preset (default: "preset:balanced"). Also reads legacy `DIALEXITY_DEFAULT_CYCLE_INTENT`.

Store these in a `.env` file in the project root.

---

## Critical Conventions

### Keep `__init__.py` files empty

All `__init__.py` files must be empty. This project does not use `__init__.py` for module exports. When creating new packages, add an empty `__init__.py` file.

### Preserve TODOs - Ask Before Removing

**IMPORTANT:** Do not remove TODO comments from code without explicitly confirming with the user first. When deleting or refactoring code that contains TODOs:

1. **Flag the TODO** - Point out that there's a TODO in the code being modified
2. **Ask for confirmation** - Check if the TODO is still relevant or can be removed
3. **Document if keeping** - If the TODO should be preserved, ensure it's not lost in the refactor

TODOs often represent important reminders about incomplete work, edge cases, or future improvements. Accidentally removing them can cause loss of important context.

### Adding New Node Types

1. Create class in `graph/nodes/`, inherit from `BaseNode` or `AssessableEntity`
2. Use `ClassVar[RelationshipManager[T]]` for relationship descriptors
3. If assessable, add calculator in `graph/scoring/tarorank_calculators/`
4. Register calculator in `tarorank.py`

### Relationship Cardinality

```python
# Exactly one
t: ClassVar[RelationshipManager[Component]] = RelationshipFrom(..., cardinality=(1, 1))

# Zero or one
transformation: ClassVar[...] = RelationshipFrom(..., cardinality=(0, 1))

# Zero or more
rationales: ClassVar[...] = RelationshipFrom(..., cardinality=(0, None))
```

### Prefer `isinstance` over `getattr` for Mixin Attributes

When checking for mixin-provided attributes (like `origin_hash`, `branch` from `ForkableMixin`), use `isinstance` checks instead of `getattr`. This enables easier refactoring and provides better IDE support.

```python
# GOOD - isinstance for mixin attributes
from dialectical_framework.graph.mixins.forkable_mixin import ForkableMixin

if isinstance(node, ForkableMixin):
    origin = node.origin_hash  # IDE knows this exists
    branch = node.branch

# BAD - getattr hides the dependency
origin = getattr(node, 'origin_hash', None)  # No IDE support, harder to refactor
```

**When to use `getattr`:** For class-level attributes like `label` or `type` that aren't mixin-based, `getattr` with a default is acceptable. When unsure, ask whether `isinstance` or `getattr` is appropriate.

### Vocabulary and Scope

**Vocabulary** is all DialecticalComponents within a scope (by `sid`).

**Scope (sid)** is the primary boundary. All nodes within the same analytical context share a `sid` inherited from their Case. This is enforced at connect time - nodes with different `sid` values cannot be connected.

```python
from dialectical_framework.graph.scope_context import scope

# Case is the scope root
case = Case()  # Generates UUID for sid
case.commit()

# App layer sets scope (after authorization)
with scope(case.sid):
    # All nodes inherit sid automatically
    input_node = Input(content="https://article.com")
    input_node.commit()
    case.inputs.connect(input_node)

    comp = DialecticalComponent(statement="Main idea")
    comp.commit()  # sid inherited from scope context

    # Query vocabulary (framework reads sid from DI)
    repo = DialecticalComponentRepository()
    vocab = repo.get_vocabulary()
```

### Query Safety: All Queries Must Be Scoped by sid

**CRITICAL: All database queries must be scoped by `sid` to prevent cross-user data leaks.**

Since different users/sessions have different `sid` values, unscoped queries could return data belonging to other users. Always use repository helper methods which automatically inject `sid` from DI:

```python
# GOOD - Use repository methods (sid auto-injected)
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository

repo = NodeRepository()
node = repo.find_by_hash("abc123...")       # Scoped by sid
node = repo.find_by_prefix("abc123")        # Scoped by sid
nodes = repo.find_by_origin("origin_hash")  # Scoped by sid

comp_repo = DialecticalComponentRepository()
vocab = comp_repo.get_vocabulary()                    # Scoped by sid
comps = comp_repo.find_by_perspective(pp)             # Validates PP belongs to scope

pp_repo = PerspectiveRepository()
pps = pp_repo.find_by_dialectical_component(comp)    # Validates component belongs to scope
pp_repo.safe_delete(pp)                               # Validates PP belongs to scope

# BAD - Raw queries without sid scoping (DATA LEAK RISK!)
graph_db.execute_and_fetch("MATCH (n:Node {hash: $hash}) RETURN n", {"hash": hash})
```

**Repository method pattern:** All repository methods use `@inject` with `sid: Optional[str] = Provide[DI.sid]` to automatically scope queries. The `sid` is read from the DI context set by `with scope(case.sid):`.

**Key repositories:**
- `NodeRepository` - Hash lookups, lineage queries
- `DialecticalComponentRepository` - Vocabulary queries
- `PerspectiveRepository` - PP lifecycle and usage queries

---

## Type Hints Best Practices

**CRITICAL: NEVER USE QUOTED TYPE STRINGS!**

This is a hard requirement. Every module MUST use `from __future__ import annotations` + `TYPE_CHECKING`.

### The Golden Rule

```python
# ALWAYS DO THIS
from __future__ import annotations  # MANDATORY - First import in EVERY module!

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some.module import SomeType

def my_function(arg: SomeType) -> list[SomeType]:  # NO QUOTES!
    ...

# NEVER DO THIS
def my_function(arg: "SomeType") -> "list[SomeType]":  # WRONG - Don't use quotes!
    ...
```

**If you find yourself typing quotes around a type, STOP. Use `from __future__ import annotations` instead.**

### Strong Typing Philosophy

**ALWAYS provide type hints for function parameters and return types.** This project values strong typing:

- Type ALL function parameters
- Type ALL return values (including `None`)
- Use specific types over `Any` whenever possible
- Prefer `list[Type]` over `list` or `List`
- Prefer `dict[KeyType, ValueType]` over `dict` or `Dict`

```python
# GOOD - Fully typed
def process_components(
    components: list[DialecticalComponent],
    filter_fn: Optional[Callable[[DialecticalComponent], bool]] = None
) -> list[DialecticalComponent]:
    if filter_fn:
        return [c for c in components if filter_fn(c)]
    return components

# BAD - Missing types
def process_components(components, filter_fn=None):
    if filter_fn:
        return [c for c in components if filter_fn(c)]
    return components
```

### Required Pattern for All Modules

```python
from __future__ import annotations  # ALWAYS include this first

from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    # Import types that would cause circular imports
    from some.module import SomeType
```

### Why This Pattern?

1. **`from __future__ import annotations`**: Defers evaluation of all type annotations, preventing circular import errors at runtime
2. **`TYPE_CHECKING`**: Makes types available to IDEs and type checkers without runtime imports
3. **No quoted strings**: Write `Union[Cycle, Spiral]` NOT `"Union[Cycle, Spiral]"`

### Generic Type Parameters

When using `RelationshipManager`, ALWAYS specify the generic type:

```python
# CORRECT - IDE sees methods
transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(...)

# WRONG - IDE can't resolve methods
transitions: ClassVar[RelationshipManager] = RelationshipFrom(...)
```

### ClassVar Requirement for GQLAlchemy Descriptors

**IMPORTANT**: Descriptors like `RelationshipManager` **MUST** use `ClassVar` with GQLAlchemy nodes:

```python
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition

class Cycle(AssessableEntity):
    # REQUIRED - ClassVar tells GQLAlchemy metaclass to skip this field
    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(...)
```

**Why ClassVar is required:**
- GQLAlchemy's metaclass processes class attributes during creation
- Without `ClassVar`, it tries to treat descriptors as Pydantic fields
- This causes `AttributeError: 'ForwardRef' object has no attribute '__name__'`
- `ClassVar` tells the metaclass "this is class-level, don't process as a field"

### Modern Python Type Syntax

Use Python 3.10+ syntax (this project targets Python 3.11+):

```python
# GOOD - Modern syntax
def get_items() -> list[str]:
    return ["a", "b"]

def union_type(value: int | str) -> int | str:
    return value

# OLD - Don't use typing.List, typing.Dict
from typing import List, Dict, Union

def get_items() -> List[str]:  # Don't use List
    return ["a", "b"]
```

---

## Testing

### Key Test Files

- `test_graph.py` (64KB): Core graph operations, Perspectives, components
- `test_tarorank.py` (48KB): Comprehensive scoring tests
- `test_synthesist.py`: Reasoning engines
- `conftest.py`: DI setup and fixtures

### DI in Tests

Tests use session-scoped DI container with test database wrapper. Test nodes are auto-labeled for cleanup.

```python
# conftest.py pattern
@pytest.fixture(scope="session", autouse=True)
def di_container():
    container = DialecticalReasoning.setup(Settings.from_env())
    container.graph_db.override(providers.Singleton(_create_test_graph_db, ...))
    yield container
    container.unwire()
```

### Writing Tests

```python
def test_create_perspective():
    pp = Perspective()
    pp.save()

    t = DialecticalComponent(statement="Democracy empowers citizens")
    t.save()
    pp.t.connect(t)

    assert pp.t.count() == 1
    result = pp.t.get()
    assert result is not None
    component, rel = result
    assert component.statement == "Democracy empowers citizens"
```

---

## Documentation References

| Doc | Purpose |
|-----|---------|
| `docs/graph.md` | Graph data model reference |
| `docs/graph-portability.md` | Identifiers, scopes, cloning & realms |
| `docs/scoring.md` | Complete TaroRank specification |
