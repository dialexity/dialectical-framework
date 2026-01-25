# CLAUDE.md - AI Co-Developer Guide

This file provides context for Claude Code to be an effective co-developer on the Dialectical Framework.

## What is the Dialectical Framework?

A semantic graph system for dialectical reasoning - modeling thesis-antithesis-synthesis dynamics as graph structures. Used for systems analysis, wisdom mining, and ethical modeling.

### Core Metaphor: The Wheel

Think of a Dialectical Wheel as a pizza:
- **Wheel** = entire pizza (top-level container)
- **Segment** = pizza slice (contains T, T+, T- components)
- **WisdomUnit** = half-pizza (T-segment + opposing A-segment)

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

- **Nexus**: Pool of WisdomUnits that can be shared across perspectives
- **Transition**: Recipe for moving between segments (T-→A+, A-→T+)
- **Transformation**: Internal spiral within a WisdomUnit (2 transitions), produces Synthesis
- **Synthesis**: Emergent S+/S- pair from Transformation or Spiral (meta-synthesis at wheel level)
- **Cycle**: Sequence of transitions derived from a Nexus (has causality_type: BALANCED, REALISTIC, etc.)
- **Spiral**: Transformational sequence derived from Wheel structure + WU Transformations
- **Wheel**: Top-level container with detailed transitions (belongs to Cycle)
- **Input**: External content source (URL/IPFS) linked to extracted components

**Hierarchy:** WisdomUnit → Nexus → Cycle → Wheel

### Cardinality Design: Where to Branch

Both `WisdomUnit.transformation` and `Wheel.spiral` use **(0, 1)** cardinality because they are **derived structures** - fully determined by their inputs. The Spiral inherits intentions from WU Transformations; it has no independent "intentions."

**To explore different paths, branch upstream:**
- Different transformation interpretations → Create different **WisdomUnits**
- Different WU combinations → Create different **Nexuses**
- Different orderings/causality types → Create different **Cycles**

Multiple synthesis interpretations are supported via `Synthesis (0, ∞)` on both Transformation and Spiral.

See `docs/graph.md` → "Branching and Cardinality Rationale" for detailed explanation.

### Semantic Relationships (auto-created)

When connecting components to WisdomUnit positions, semantic relationships are automatically created:

| Relationship | Direction | When Created |
|--------------|-----------|--------------|
| `OPPOSITE_OF` | Symmetric | T ↔ A, T+ ↔ A-, A+ ↔ T- |
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
| AI/LLM reasoning | `src/dialectical_framework/synthesist/` |
| Wisdom reasoning | `src/dialectical_framework/synthesist/wisdom/` |
| Configuration | `src/dialectical_framework/settings.py` |
| LLM abstraction | `src/dialectical_framework/brain.py` |

### Key Files to Understand First

1. `graph/nodes/base_node.py` - Foundation (uid, handle, save())
2. `graph/nodes/assessable_entity.py` - Scoreable nodes (P, R, score)
3. `graph/relationship_manager.py` - Declarative relationship API
4. `graph/scoring/tarorank.py` - Score = P × R^α
5. `dialectical_reasoning.py` - DI container setup

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
│   ├── nodes/               # BaseNode → AssessableEntity → {Component, WU, Wheel, ...}
│   ├── relationships/       # Polarity, opposition relationship models
│   ├── scoring/             # TaroRank: Score = P × R^α
│   │   └── tarorank_calculators/  # Per-node-type calculators
│   ├── repositories/        # Data access layer
│   └── relationship_manager.py    # RelationshipTo/From declarative API
│
├── synthesist/              # Reasoning engines
│   ├── ideas/              # Idea extraction (thesis, antithesis, polarity)
│   │   ├── thesis_extractor_basic.py      # Extract thesis concepts
│   │   ├── antithesis_extractor_basic.py  # Extract antithesis concepts
│   │   └── polarity_finder_basic.py       # Orchestrate polarity extraction
│   ├── polarity/           # Polar reasoning (PolarReasoner, WisdomUnit building)
│   ├── causality/          # Order transitions (BALANCED, REALISTIC, etc.)
│   ├── concepts/           # Concept extraction
│   └── wisdom/             # Transition analysis & validation
│       ├── consultant.py   # Base for transition analysis
│       └── decorators      # Action-reflection, spiral decorators
│
├── protocols/               # Python Protocol interfaces
├── ai_dto/                  # DTOs for LLM communication
├── enums/                   # DI enum, CausalityType, etc.
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

### Graph Node Lifecycle

```python
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit

# Create and save
component = DialecticalComponent(statement="Remote work increases productivity")
component.save()  # Uses injected graph_db

wu = WisdomUnit()
wu.save()

# Connect (child→parent direction)
wu.t.connect(component)

# Access
result = wu.t.get()  # Returns (node, relationship) or None
all_items = wu.t.all()  # Returns [(node, rel), ...]
count = wu.t.count()

# Disconnect
wu.t.disconnect(component)
```

### Relationship Pattern (CRITICAL)

RelationshipTo and RelationshipFrom define the **SAME edge** from different perspectives:

```python
# Child defines outgoing edge TO parent
class WisdomUnit(AssessableEntity):
    nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")  # WU→Nexus

# Parent sees incoming edge FROM children (SAME edge!)
class Nexus(AssessableEntity):
    wisdom_units = RelationshipFrom("WisdomUnit", "BELONGS_TO_NEXUS")
```

**Convention**: Child→Parent edges use `RelationshipTo` on child.

**Full hierarchy (simplified):**
```
WU.nexus → Nexus.cycles → Cycle.wheels → Wheel
```

**Complete scoring hierarchy:**
```
Component → WU → Nexus → Cycle → Wheel
    │        ▲                     ▲
    │        │                     │
    │   Transformation ← Synthesis │
    │                       │      │
    └→ Synthesis ───────────┴→ Spiral
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

Store these in a `.env` file in the project root.

---

## Critical Conventions

### DO NOT modify `__init__.py` files

These files handle critical import ordering and circular dependency resolution. Adding logic to `__init__.py` files can break imports. Put helper functions in separate modules instead.

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

### Vocabulary and WisdomUnit Purity

**WisdomUnits must only contain components from the same vocabulary context.** This is enforced at connect time.

**Vocabulary Contexts:**

| Generation | Context | Components Include |
|------------|---------|-------------------|
| **Gen-0** | Input | Components born via `Input.HAS_STATEMENT` |
| **Gen-1+** | Nexus | Position components + Synthesis S+/S- + HAS_STATEMENT from Nexus tree |

**Purity Rule:** All 6 components in a WisdomUnit (T, A, T+, T-, A+, A-) must belong to the same vocabulary:
- Gen-0 WU: All components from the same Input
- Gen-1+ WU: All components from the same Nexus vocabulary

```python
# Gen-0: Components from same Input
input_a = Input(content_uri="https://article.com/x")
input_a.save()
comp1 = DialecticalComponent(statement="Thesis from A")
comp1.save()
input_a.statements.connect(comp1)

wu = WisdomUnit()
wu.save()
wu.t.connect(comp1)  # OK - first component sets vocabulary
wu.a.connect(comp2_from_input_a)  # OK - same Input vocabulary

# This fails - different vocabulary!
wu.t_plus.connect(comp_from_input_b)  # ValueError: component not in vocabulary
```

**Query Helpers** (in `dialectical_component_repository.py`):

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

# Trace all root Inputs (multi-root provenance)
roots = repo.get_root_inputs(wheel)  # All Inputs that contributed
```

**Multi-Root Provenance:** Gen-1+ components trace back to multiple original Inputs via the Nexus ancestry—this is by design for synthesis.

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

- `test_graph.py` (64KB): Core graph operations, WisdomUnits, components
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
def test_create_wisdom_unit():
    wu = WisdomUnit()
    wu.save()

    t = DialecticalComponent(statement="Democracy empowers citizens")
    t.save()
    wu.t.connect(t)

    assert wu.t.count() == 1
    result = wu.t.get()
    assert result is not None
    component, rel = result
    assert component.statement == "Democracy empowers citizens"
```

---

## Documentation References

| Doc | Purpose |
|-----|---------|
| `docs/graph.md` | Graph data model reference |
| `docs/scoring.md` | Complete TaroRank specification |
