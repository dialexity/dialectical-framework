# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This is a Python project using Poetry for dependency management:

- **Install dependencies**: `poetry install`
- **Run tests**: `poetry run pytest` or `pytest` if in activated environment
- **Format code**: `poetry run black src/ tests/`
- **Sort imports**: `poetry run isort src/ tests/`
- **Remove unused imports**: `poetry run autoflake --in-place --remove-all-unused-imports --recursive src/ tests/`
- **Activate virtual environment**: `poetry shell`
- **Build package**: `poetry build`

## Core Architecture

The Dialectical Framework implements a semantic graph system for dialectical reasoning, structured as a wheel metaphor:

### Core Components

- **Wheel**: The main container composed of segments, representing a complete dialectical system
- **WheelSegment**: Individual "slices" of the wheel, each containing dialectical components
- **WisdomUnit**: A half-wheel structure containing thesis-antithesis pairs with validation constraints
- **DialecticalComponent**: Basic building blocks representing statements/concepts with aliases (T, A, T+, A-, etc.)
- **Transition**: Rules for moving between segments, enabling synthesis pathways

### Key Domain Objects

- **Cycle**: Represents cyclical patterns in dialectical reasoning
- **Spiral**: Advanced cycle with transformational properties
- **Transformation**: Rules for converting dialectical components
- **Rationale**: Explanatory context for dialectical relationships

### Architectural Patterns

1. **Protocol-Based Design**: Uses Python protocols (`Assessable`, `Ratable`, `HasBrain`) for flexible composition
2. **Circular Dependency Resolution**: The `__init__.py` file carefully orders imports and rebuilds Pydantic models to resolve circular references
3. **AI Integration**: Heavy use of Mirascope for LLM interactions, with Brain abstraction for model switching
4. **Dependency Injection**: Uses `dependency-injector` for service composition

### Module Structure

- `synthesist/`: Core reasoning engines (polarity, causality, concepts)
- `analyst/`: Analysis and validation tools (domain objects, consultants, decorators)
- `protocols/`: Interface definitions for extensibility
- `ai_dto/`: Data transfer objects for AI interactions
- `utils/`: Utility functions and helpers
- `validator/`: Validation and checking logic

## Environment Configuration

Required environment variables:
- `DIALEXITY_DEFAULT_MODEL`: Default LLM model (e.g., "gpt-4")
- `DIALEXITY_DEFAULT_MODEL_PROVIDER`: Model provider ("openai", "anthropic", etc.)

Store these in a `.env` file in the project root.

## Testing

Tests are located in `tests/` directory. The project uses pytest with asyncio support enabled. Key test files:
- `test_synthesist.py`: Core reasoning engine tests
- `test_analyst.py`: Analysis functionality tests
- `test_wu_construction.py`: Wisdom Unit construction tests
- `conftest.py`: Shared test configuration

## Development Notes

- **Pydantic Models**: Many classes inherit from Pydantic models for validation and serialization
- **Async Support**: The framework supports both sync and async operations
- **Model Rebuilding**: Due to circular dependencies, Pydantic models require explicit rebuilding in `__init__.py`
- **AI Brain Abstraction**: The `Brain` class provides a unified interface for different LLM providers
- **Contextual Fidelity**: The system tracks probability and confidence propagation through dialectical structures
- Scoring architecture is described in scoring.md

## Important Conventions

- **DO NOT update `__init__.py` files**: These files handle critical import ordering and circular dependency resolution. Adding logic to `__init__.py` files can break imports. Put helper functions in separate modules instead.
- **Graph Database**: The framework uses `graph_db` (via DI) for graph-native structures with Memgraph/Neo4j

## Type Hints Best Practices

⚠️ **CRITICAL: NEVER USE QUOTED TYPE STRINGS!** ⚠️

**This is a hard requirement. Every module MUST use `from __future__ import annotations` + `TYPE_CHECKING`.**

### The Golden Rule

```python
# ✅ ALWAYS DO THIS
from __future__ import annotations  # MANDATORY - First import in EVERY module!

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some.module import SomeType

def my_function(arg: SomeType) -> list[SomeType]:  # NO QUOTES!
    ...

# ❌ NEVER DO THIS
def my_function(arg: "SomeType") -> "list[SomeType]":  # WRONG - Don't use quotes!
    ...
```

**If you find yourself typing quotes around a type, STOP. Use `from __future__ import annotations` instead.**

### Strong Typing Philosophy

**ALWAYS provide type hints for function parameters and return types.** This project values strong typing:

- ✅ Type ALL function parameters
- ✅ Type ALL return values (including `None`)
- ✅ Use specific types over `Any` whenever possible
- ✅ Prefer `list[Type]` over `list` or `List`
- ✅ Prefer `dict[KeyType, ValueType]` over `dict` or `Dict`

```python
# ✅ GOOD - Fully typed
def process_components(
    components: list[DialecticalComponent],
    filter_fn: Optional[Callable[[DialecticalComponent], bool]] = None
) -> list[DialecticalComponent]:
    if filter_fn:
        return [c for c in components if filter_fn(c)]
    return components

# ❌ BAD - Missing types
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

### Examples

**✅ CORRECT - Use actual types:**
```python
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition

class Cycle(BaseNode):
    # IDE can autocomplete .all(), .connect(), etc.
    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(...)

    def get_components(self) -> list[DialecticalComponent]:
        return [comp for comp in self.components]
```

**❌ INCORRECT - Avoid quoted strings:**
```python
# BAD: No __future__ annotations, uses strings
class Cycle(BaseNode):
    transitions: ClassVar[RelationshipManager["Transition"]] = RelationshipFrom(...)

    def get_components(self) -> "list[DialecticalComponent]":  # Don't quote!
        return [comp for comp in self.components]
```

### Generic Type Parameters

When using `RelationshipManager`, ALWAYS specify the generic type:

```python
# ✅ CORRECT - IDE sees methods
transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(...)

# ❌ WRONG - IDE can't resolve methods
transitions: ClassVar[RelationshipManager] = RelationshipFrom(...)
```

### Benefits

- IDE autocomplete works perfectly (`.all()`, `.connect()`, `.get()`, `.count()`)
- Type checkers (mypy, pyright) can verify correctness
- No "Unresolved attribute reference" warnings
- Better refactoring support
- Catches bugs at development time instead of runtime
- Makes code self-documenting and easier to understand

### Descriptor Protocol Typing

When implementing descriptors (like `RelationshipManager`), use `@overload` to help IDEs understand the return types:

```python
from typing import overload

class RelationshipManager(Generic[T]):
    @overload
    def __get__(self, instance: None, owner: type) -> RelationshipManager[T]:
        """When accessed on class, returns descriptor itself."""
        ...

    @overload
    def __get__(self, instance: Node, owner: type) -> BoundRelationshipManager[T]:
        """When accessed on instance, returns bound manager."""
        ...

    def __get__(self, instance, owner):
        """Actual implementation."""
        if instance is None:
            return self
        return BoundRelationshipManager(...)
```

This allows IDEs to properly resolve methods like `.all()`, `.connect()`, etc. on relationship attributes.

### ClassVar Requirement for GQLAlchemy Descriptors

**IMPORTANT**: Descriptors like `RelationshipManager` **MUST** use `ClassVar` with GQLAlchemy nodes:

```python
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition

class Cycle(AssessableEntity):
    # ✅ REQUIRED - ClassVar tells GQLAlchemy metaclass to skip this field
    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(...)
```

**Why ClassVar is required:**
- GQLAlchemy's metaclass processes class attributes during creation
- Without `ClassVar`, it tries to treat descriptors as Pydantic fields
- This causes `AttributeError: 'ForwardRef' object has no attribute '__name__'`
- `ClassVar` tells the metaclass "this is class-level, don't process as a field"

**Known limitation with Union types:**
When using descriptors on Union types, type checkers may struggle:

```python
@inject
def order_transitions(
    cycle_or_spiral: Union[Cycle, Spiral],
    graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
) -> list[Transition]:
    # Type checkers struggle with descriptor protocol on Union types
    # Use explicit annotation with type: ignore to help IDE
    transitions_manager: BoundRelationshipManager[Transition] = cycle_or_spiral.transitions  # type: ignore[assignment]
    all_transitions = [trans for trans, _ in transitions_manager.all()]  # Now IDE sees .all()
```

This is a known limitation of type checkers with descriptors. The code works correctly at runtime.

### Modern Python Type Syntax

Use Python 3.10+ syntax (this project targets Python 3.11+):

```python
# ✅ GOOD - Modern syntax
def get_items() -> list[str]:
    return ["a", "b"]

def get_mapping() -> dict[str, int]:
    return {"a": 1}

def union_type(value: int | str) -> int | str:
    return value

# ❌ OLD - Don't use typing.List, typing.Dict
from typing import List, Dict, Union

def get_items() -> List[str]:  # Don't use List
    return ["a", "b"]

def get_mapping() -> Dict[str, int]:  # Don't use Dict
    return {"a": 1}

def union_type(value: Union[int, str]) -> Union[int, str]:  # Prefer | over Union
    return value
```