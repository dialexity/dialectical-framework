# CLAUDE.md - AI Co-Developer Guide

This file provides context for Claude Code to be an effective co-developer on the Dialectical Framework.

## Collaboration Style

When reasoning together on design decisions, give honest opinions with clear tradeoffs — not agreement for the sake of agreement. State what you actually think is the better approach and why. If both options are defensible, say so directly rather than leaning toward whichever the user seems to prefer.

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
- **Synthesis**: Emergent S+/S- pair from Wheel's circular causality
- **Cycle**: T-cycle - ordered sequence of Perspectives defining abstract thesis causality
  - Stores PP hashes directly (cycle.perspective_hashes)
  - Intent field for dynamics type ("preset:balanced", "preset:realistic", etc.)
- **Wheel**: Concrete T-A arrangement implementing a subset of Cycle's PPs
  - `_perspectives`: PPs derived from edge components (internal)
  - `polarity_count`: number of PPs (derived from edges)
  - Contains `edges` (causality sequence / ta_cycle level)
  - Transformations belong to individual edges (access via `wheel.transformations`)
  - Wheels are reused across Cycles if same PP set (rotation-invariant hash)
- **Input**: External content source (URL/IPFS) linked to extracted statements
- **Ideas**: Container of distilled concepts from an Input (uses IncrementalBuildMixin: save → add statements → commit)
- **Case**: Multi-input exploration container with unified vocabulary

**Hierarchy:** Perspective → Cycle → Wheel (edges) → Transformation
**Case flow:** Case → Input → Ideas → Statements

**Exploration flow:** Perspectives → Nexus (exploration context) → Cycles (T-cycle orderings) → Wheels (TA arrangements)

- **Nexus**: Required exploration container for Perspectives. Groups PPs with a specific intent for layer-by-layer combination into Cycles and Wheels.

**DEPRECATED nodes (kept for backwards compatibility):**
- **Spiral**: Replaced by Transformations on edges

### Intent Levels

Reasoning nodes inherit from `IntentMixin`, providing a unified `intent: Optional[str]` field. Intent is part of the hash — same structure + different intent = different node. Maps to the reflective practice framework:

| Level | Reflection | Question | Lives On |
|-------|------------|----------|----------|
| **Discovery** | (Gathering) | What sources to explore? | Ideas |
| **Focus** | What? | What tensions exist? | Cycle |
| **Dynamics** | So What? | Why do they matter? | Cycle (intent field) |
| **Path** | Now What? | How to navigate? | Perspective, Transformation, Wheel, Nexus |

**Nodes with IntentMixin:** Ideas, Cycle, Perspective, Transformation, Wheel, Nexus

**Nodes WITHOUT IntentMixin:** Polarity (shared atom — intent belongs on Perspective), Synthesis (S+/S- content IS the outcome), Statement, Case

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

Multiple synthesis interpretations are supported via `Synthesis (0, ∞)` on Wheel.

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
- Statements, Perspectives, Ideas, Cycle, Wheel, Transitions
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

### Rejection and Editing

**`rejected: Optional[str]`** is a metadata field (does not affect hash) on:
- **Statement** — "this idea is wrong/irrelevant"
- **Perspective** — "this framing is superseded or unwanted"

**NOT rejectable:** Polarity, Nexus, Cycle, Wheel. Polarity is a shared structural atom (T-A pairing). If the opposition is bad, reject the Perspective(s) that use it. Nexus is an exploration container — filter rejected PPs at query time.

**Rejection blocking rules:**
- **Statement**: blocked if used by any non-rejected Perspective. Reject/edit those PPs first.
- **Perspective**: blocked if it participates in any Cycle. Delete Cycles first or use `edit_perspective`.

**Editing a committed Perspective** (via `edit_perspective`):
1. Clone → modify → commit (new PP with new hash)
2. Connect old→new via `CHANGED_TO` relationship (analytical lineage)
3. Polarity and Statements are untouched (shared atoms)
4. New PP is independent — not attached to old PP's Nexuses or Cycles

Editing is evolution, not replacement. The old PP and its downstream structures
remain valid. The caller decides what to do with the new PP (add to a new Nexus, etc.).

**`CHANGED_TO` lineage** (analytical layer, old_pp→new_pp):
- If old PP is not rejected: lineage is meaningful (evolution chain)
- If old PP is rejected: new PP lives as a first-class citizen
- `changed_positions` property records what changed (e.g. `["T+", "A-"]`)

**Querying should filter rejected nodes:** `WHERE pp.rejected IS NULL`.

### Semantic Relationships (auto-created)

When connecting statements to Perspective positions, semantic relationships are automatically created:

| Relationship | Direction | When Created |
|--------------|-----------|--------------|
| `OPPOSITE_OF` | Symmetric | T ↔ A (dialectical opposition) |
| `CONTRADICTION_OF` | Symmetric | T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity) |
| `POSITIVE_SIDE_OF` | Directed | T+ → T, A+ → A |
| `NEGATIVE_SIDE_OF` | Directed | T- → T, A- → A |

---

## Quick Navigation

### Where Things Live

| Purpose | Location |
|---------|----------|
| DI Container (START HERE) | `src/dialectical_framework/dialectical_reasoning.py` |
| Graph nodes | `src/dialectical_framework/graph/nodes/*.py` |
| Relationships | `src/dialectical_framework/graph/relationships/*.py` |
| Relationship API | `src/dialectical_framework/graph/relationship_manager.py` |
| Estimation management | `src/dialectical_framework/graph/estimation_manager.py` |
| Concerns (API) | `src/dialectical_framework/concerns/` |
| Agentic orchestration | `src/dialectical_framework/agents/` |
| AI/LLM reasoning | `src/dialectical_framework/synthesist/` |
| Wisdom reasoning | `src/dialectical_framework/synthesist/wisdom/` |
| Configuration | `src/dialectical_framework/settings.py` |
| LLM abstraction | `src/dialectical_framework/brain.py` |

### Key Files to Understand First

1. `graph/nodes/base_node.py` - Foundation (hash, commit(), update())
2. `graph/nodes/assessable_entity.py` - Entities with estimations and rationales
3. `graph/relationship_manager.py` - Declarative relationship API
4. `graph/relationships/immutable_structure.py` - Layer base classes (Structural vs Analytical)
5. `dialectical_reasoning.py` - DI container setup

---

## Development Commands

This is a Python project using Poetry for dependency management:

- **Install dependencies**: `poetry install`
- **Run tests**: `poetry run pytest` (all tests, LLM mocked)
- **Run tests with real LLM**: `poetry run pytest --real-llm`
- **Run only LLM tests (mocked)**: `poetry run pytest -m llm`
- **Run only LLM tests (real)**: `poetry run pytest -m llm --real-llm`
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
│   ├── nodes/               # BaseNode → AssessableEntity → {Statement, PP, Wheel, ...}
│   ├── mixins/              # Shared node behaviors (IntentMixin)
│   ├── relationships/       # Polarity, opposition relationship models
│   ├── repositories/        # Data access layer
│   └── relationship_manager.py    # RelationshipTo/From declarative API
│
├── concerns/                # Concerns to resolve (API-callable, standalone)
│   ├── thesis_extraction.py    # Extract theses from text
│   ├── aspect_generation.py      # Generate T+, T-, A+, A- aspects
│   ├── transformation_generation.py
│   └── ...                     # 15 concern modules total
│
├── agents/                  # LLM-driven agentic orchestrators
│   ├── reasonable_concern.py    # ReasonableConcern base class
│   ├── analyst/            # Analysis mode: Input → Ideas → Perspectives
│   │   ├── skills/         # Workflows orchestrating concerns
│   │   │   ├── surface_theses.py      # Thesis extraction & deduplication
│   │   │   ├── find_polarities.py     # Antithesis finding & Polarity creation
│   │   │   ├── introduce_polarity.py  # Direct T-A tension introduction
│   │   │   ├── expand_polarities.py    # Perspective building (T+, T-, A+, A-)
│   │   │   └── edit_perspective.py     # Unified edit: any position(s) of a Perspective
│   │   └── tools/          # Thin tools (minimal logic, no multi-concern orchestration)
│   │       └── place_statement.py  # Recognize if statement exists in graph
│   ├── explorer/           # Exploration mode: PP pool → Cycles → Wheels
│   │   ├── skills/
│   │   │   ├── build_wheels.py     # Cycle & Wheel arrangement + estimation
│   │   │   └── explore_transformations.py  # Action-Reflection generation
│   │   └── tools/
│   │       └── create_nexus.py     # Create exploration container
│   └── orchestrator/       # Conversation layer, delegates to analyst/explorer
│       └── tools/          # Phase-agnostic utilities
│           ├── add_input.py        # Capture source material
│           ├── get_scope_status.py # Node counts in scope
│           ├── present_analysis.py # Readable graph summary
│           ├── query_graph.py      # Read-only Cypher queries
│           └── reject.py           # Discard statements/perspectives
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

### Orchestrator Architecture

The Orchestrator is the main entry point for LLM-driven graph curation.

**Design: one conversation, all tools available, phase-aware behavior.**
No hard mode switching — the LLM recognizes Analysis vs Exploration phases
and shifts naturally. Like Claude Code: all capabilities always available,
posture adapts to context.

**App-level persona via `app_preamble`:**

```python
# The host app (Chainlit, API) controls persona via system prompt prefix
orchestrator = Orchestrator(
    sid="existing-sid",           # Resume existing session, or None for new
    app_preamble="You are a wise counselor helping someone think clearly..."
)
```

System prompt = `app_preamble` (persona/tone) + `BASE_SYSTEM_PROMPT` (framework behavior) + `GRAPH_SCHEMA` + live DB schema.

**UI actions as synthetic messages:**

When the user acts on the graph via UI (reject, select, regenerate), the host app
injects synthetic messages: `orchestrator.chat("[SYSTEM] User rejected statement abc1234")`

**Resuming sessions:** Pass an existing `sid` to pick up where a previous conversation
left off. The LLM uses `present_analysis` to orient itself on first message.

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

**Simple nodes** (Statement, Rationale):
```python
stmt = Statement(text="Remote work increases productivity")
stmt.commit()  # save + compute hash in one step
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
pp.t.connect(stmt)

# Access
result = pp.t.get()  # Returns (node, relationship) or None
all_items = pp.t.all()  # Returns [(node, rel), ...]
count = pp.t.count()

# Disconnect
pp.t.disconnect(stmt)
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

**Quality is measured by structural edge properties:**
- `heuristic_similarity` on T/A/aspect edges (0.0-1.0)
- `complementarity_t`, `complementarity_a` on aspect edges (0.0-1.0)
- `insight`, `proactiveness` on transformation aspect edges (0.0-1.0)
- Perspective computed properties: `diff_t`, `diff_a`, `area_normalized`, `rectangularity`

### Tool Pattern (Mirascope v2)

Tools use a two-layer pattern:

1. **`ReasonableConcern[T]` class** — the implementation. Provides `ExecutionReport` tracking and `resolve()`. **The LLM never sees this class.**
2. **`@llm.tool` async function** — the LLM-facing interface. Its docstring = tool description. Its `Field(description=...)` defaults = parameter descriptions. This is what goes in tool lists.

The framework hierarchy (all inherit from `ReasonableConcern`):

- **Concern** = standalone service (e.g. `ThesisExtraction`)
- **Skill** = workflow that orchestrates concerns (e.g. `SurfaceTheses`)
- **Agent** = orchestrator with tools + skills (e.g. `Orchestrator`)

**What the LLM sees vs. what it doesn't:**

| Source | LLM sees it? | Purpose |
|--------|-------------|---------|
| `@llm.tool` function docstring | **YES** — becomes tool description | Tell the LLM WHEN and HOW to use the tool |
| `@llm.tool` function `Field(description=...)` | **YES** — becomes parameter description | Tell the LLM what each parameter means |
| `ReasonableConcern` class docstring | **NO** | Developer documentation only |

**Simple concern (params in resolve):**

```python
from mirascope import llm
from dialectical_framework.agents.reasonable_concern import ReasonableConcern

class GetScopeStatus(ReasonableConcern[str]):
    @inject
    async def resolve(self, graph_db=Provide[DI.graph_db], sid=Provide[DI.sid]) -> str:
        self._report.ok = True
        return result

@llm.tool
async def get_scope_status() -> str:
    """Show counts of all node types in the current scope."""
    concern = GetScopeStatus()
    return await concern.resolve()
```

**Skill (params in __init__, orchestrates concerns):**

```python
from mirascope import llm
from pydantic import Field
from dialectical_framework.agents.reasonable_concern import ReasonableConcern

class SurfaceTheses(ReasonableConcern[Optional[Ideas]]):
    def __init__(self, intent: str) -> None:
        self.intent = intent

    async def resolve(self) -> Optional[Ideas]:
        # uses ThesisExtraction, StatementDeduplication, etc.
        return ideas

@llm.tool
async def surface_theses(
    intent: str = Field(description="What theses to find"),
) -> str:
    """Surfaces theses for dialectical analysis."""
    skill = SurfaceTheses(intent=intent)
    await skill.resolve()
    return str(skill.report)
```

**Folder conventions — where to put new tools:**

| Folder | Contains | Complexity | Example |
|--------|----------|-----------|---------|
| `concerns/` | Standalone services (no `@llm.tool`) | Single responsibility, reusable | `ThesisExtraction`, `AspectGeneration` |
| `agents/{phase}/tools/` | Thin `@llm.tool` wrappers | Minimal logic, calls one concern or does simple DB ops | `place_statement`, `create_nexus`, `add_input` |
| `agents/{phase}/skills/` | Workflow `@llm.tool` wrappers | Orchestrates multiple concerns, has retry/dedup/validation | `SurfaceTheses`, `BuildWheels` |
| `agents/orchestrator/tools/` | Phase-agnostic utilities | Shared across analyst/explorer | `query_graph`, `reject`, `present_analysis` |

**Decision rule:** If the `ReasonableConcern` class calls other concerns or has multi-step logic (retry, dedup, validation), it's a **skill**. If it's a single DB operation or thin wrapper around one concern, it's a **tool**.

**Key rules:**
- Only `@llm.tool`-decorated functions go into `ConversationFacilitator(tools=[...])` or `_build_tool_list()`
- `ReasonableConcern` classes are never passed directly to Mirascope — they lack the `.name` attribute Mirascope requires
- The `@llm.tool` function's docstring = tool description visible to the LLM
- `Field(description=...)` on `@llm.tool` function parameters = parameter descriptions visible to the LLM

**For simple tools without graph mutations** (e.g., in tests), skip the service class:

```python
@llm.tool
async def get_current_time() -> str:
    """Return the current UTC time."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
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
3. **Update `GRAPH_SCHEMA`** in `agents/orchestrator/orchestrator.py` — the LLM relies on it for `query_graph` Cypher composition

### Maintain GRAPH_SCHEMA When Refactoring

The `GRAPH_SCHEMA` constant in `agents/orchestrator/orchestrator.py` is the LLM's reference for composing Cypher queries. It documents node types, relationship directions, and query patterns. When you:

- Add/remove/rename a node type or relationship
- Change relationship direction or endpoints
- Add significant properties to nodes

**You must update `GRAPH_SCHEMA` to match.** Wrong directions or fictional relationships cause the LLM to write broken queries. The live DB schema (from `SchemaRepository`) only provides bare label/type lists — `GRAPH_SCHEMA` provides the semantic understanding of how things connect.

### Relationship Cardinality

```python
# Exactly one
t: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(..., cardinality=(1, 1))

# Zero or one
transformation: ClassVar[...] = RelationshipFrom(..., cardinality=(0, 1))

# Zero or more
rationales: ClassVar[...] = RelationshipFrom(..., cardinality=(0, None))
```

### Prefer `isinstance` over `getattr` for Mixin Attributes

When checking for mixin-provided attributes (like `intent` from `IntentMixin`), use `isinstance` checks instead of `getattr`. This enables easier refactoring and provides better IDE support.

```python
# GOOD - isinstance for mixin attributes
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin

if isinstance(node, IntentMixin):
    intent = node.intent  # IDE knows this exists

# BAD - getattr hides the dependency
intent = getattr(node, 'intent', None)  # No IDE support, harder to refactor
```

**When to use `getattr`:** For class-level attributes like `label` or `type` that aren't mixin-based, `getattr` with a default is acceptable. When unsure, ask whether `isinstance` or `getattr` is appropriate.

### Vocabulary and Scope

**Vocabulary** is all Statements within a scope (by `sid`).

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

    stmt = Statement(text="Main idea")
    stmt.commit()  # sid inherited from scope context

    # Query vocabulary (framework reads sid from DI)
    repo = StatementRepository()
    vocab = repo.get_vocabulary()
```

### Query Safety: All Queries Must Live in Repositories

**CRITICAL: All database queries must go through repository classes and be scoped by `sid` to prevent cross-user data leaks.**

Never write raw `graph_db.execute_and_fetch()` calls in tools, skills, concerns, or node classes. If you need a new query, add a method to the appropriate repository (or create a new one). This ensures all queries are sid-scoped and centralized.

Since different users/sessions have different `sid` values, unscoped queries could return data belonging to other users. Always use repository helper methods which automatically inject `sid` from DI:

```python
# GOOD - Use repository methods (sid auto-injected)
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.statement_repository import StatementRepository
from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository

repo = NodeRepository()
node = repo.find_by_hash("abc123...")       # Scoped by sid
node = repo.find_by_prefix("abc123")        # Scoped by sid

stmt_repo = StatementRepository()
vocab = stmt_repo.get_vocabulary()                    # Scoped by sid
stmts = stmt_repo.find_by_perspective(pp)             # Validates PP belongs to scope

pp_repo = PerspectiveRepository()
pps = pp_repo.find_by_statement(stmt)                 # Validates statement belongs to scope
pp_repo.safe_delete(pp)                               # Validates PP belongs to scope

# BAD - Raw queries without sid scoping (DATA LEAK RISK!)
graph_db.execute_and_fetch("MATCH (n:Node {hash: $hash}) RETURN n", {"hash": hash})
```

**Repository method pattern:** All repository methods use `@inject` with `sid: Optional[str] = Provide[DI.sid]` to automatically scope queries. The `sid` is read from the DI context set by `with scope(case.sid):`.

**Key repositories:**
- `NodeRepository` - Hash lookups, generic node retrieval
- `StatementRepository` - Vocabulary queries
- `PerspectiveRepository` - PP lifecycle and usage queries
- `CaseRepository` - Case lookups
- `NexusRepository` - Nexus lookups, scope status aggregation
- `SchemaRepository` - Live DB schema discovery (labels, relationship types)

**Allowed exceptions** (infrastructure code that operates below the repository layer):
- `dialectical_reasoning.py` — schema initialization (indexes, constraints) at DI setup time
- `relationship_manager.py` — generic relationship CRUD (framework plumbing)
- `estimation_manager.py` — estimation node CRUD (framework plumbing)
- `query_graph.py` — LLM-driven arbitrary read-only Cypher (sid auto-injected, write-blocked)

**Everything else MUST use a repository.** When adding a new query:
1. Identify which repository it belongs to (by entity type)
2. If no suitable repository exists, create one in `graph/repositories/`
3. Add the method with `@inject` and `sid: Optional[str] = Provide[DI.sid]`
4. Call the repository method from your tool/skill/concern

**If you find a raw query outside the allowed exceptions, move it to a repository before proceeding with other work.**

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
def process_statements(
    statements: list[Statement],
    filter_fn: Optional[Callable[[Statement], bool]] = None
) -> list[Statement]:
    if filter_fn:
        return [s for s in statements if filter_fn(s)]
    return statements

# BAD - Missing types
def process_statements(statements, filter_fn=None):
    if filter_fn:
        return [s for s in statements if filter_fn(s)]
    return statements
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

### Test Markers and Mock Brain

Tests are split into three groups:

| Marker | What it tests | Default (`pytest`) | With `--real-llm` |
|--------|--------------|--------------------|--------------------|
| *(none)* | Pure logic, no LLM code paths | Runs (mock installed, harmless) | Runs (real LLM) |
| `@pytest.mark.llm` | Exercises LLM code paths | Runs with **mock brain** | Runs with **real LLM** |
| `@pytest.mark.real_llm` | Must have real LLM (e.g. provider connectivity) | **Skipped** | Runs with **real LLM** |

**Mock brain** (`tests/mock_brain.py`) auto-constructs Pydantic response models without hitting inference endpoints. It patches two things:
1. `ConversationFacilitator._call_with_response_model` — returns auto-constructed Pydantic model
2. The `use_brain` decorator — when `format` is set, auto-constructs; otherwise returns mock AsyncResponse

The `mock_llm` autouse fixture in `conftest.py` installs it for **all** tests unless `--real-llm` is passed.

### When to Use Which Marker

| Scenario | Marker | Why |
|----------|--------|-----|
| Graph operations, validation, pure logic | *(none)* | No LLM paths touched |
| Test calls concerns/skills using `use_brain` or `ConversationFacilitator` | `@pytest.mark.llm` | Mock brain fakes responses; `--real-llm` verifies with real provider |
| End-to-end integration that MUST hit real provider (streaming, connectivity) | `@pytest.mark.real_llm` | Only meaningful with real inference |

**Default to `@pytest.mark.llm`** for any test that exercises LLM code paths. Use `real_llm` when:
- The test asserts on downstream effects that require semantically meaningful LLM output (e.g., "vocabulary has statements" after extraction)
- The test exercises streaming, tool argument parsing, or provider-specific behavior
- Mock brain's auto-constructed empty/default responses would always fail the assertions

**How `--real-llm` affects test selection:**
- Without flag: all tests run, `llm`-marked use mock brain, `real_llm`-marked are skipped
- With flag: only `llm` + `real_llm` marked tests run (pure logic tests are deselected), all hit real provider

Apply markers at module level (`pytestmark = pytest.mark.llm`) or per class/function.

### What Mock Brain Does NOT Test

**Critical:** Mock brain only fakes the final structured extraction (`_call_with_response_model`) and direct `use_brain` calls. It does NOT exercise:

- **Mirascope tool registration** — tools need `@llm.tool` decorator; mock won't catch a missing decorator
- **Streaming infrastructure** — `AsyncCall.stream()`, `text_stream()`, `tool_calls`, `execute_tools()`, `resume()`
- **Tool argument parsing** — real `ToolCall.args` is a JSON string, not a dict
- **Provider-specific behavior** — Bedrock streaming, token limits, rate limits

If your code touches these paths, you need `@pytest.mark.real_llm` tests that go end-to-end without patches.

### Writing Tests That Don't Need the DB

The conftest has autouse fixtures (`cleanup_graph_db`, `cleanup_test_graph_data`) that skip tests when Memgraph is unavailable. For pure unit tests that don't touch the DB, override them:

```python
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override — this test module doesn't need the DB."""
    yield

@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override — this test module doesn't need the DB."""
    yield
```

For tests that construct an `Orchestrator` without DB, patch its constructor dependencies:

```python
with patch("...orchestrator.Case") as mock_case, \
     patch.object(Orchestrator, "_query_live_schema", return_value=""):
    mock_case.return_value.commit.return_value = None
    mock_case.return_value.sid = "test-sid"
    orchestrator = Orchestrator()
```

### Tool Definition for Tests

Tools must be decorated with `@llm.tool` to work with Mirascope's toolkit (it expects `.name` attribute):

```python
from mirascope import llm

@llm.tool
async def my_test_tool(query: str) -> str:
    """Description visible to the LLM."""
    return "result"
```

Plain functions or BaseModel subclasses without `@llm.tool` will fail with `AttributeError: 'function' object has no attribute 'name'`.

### Key Test Files

- `test_graph.py`: Core graph operations, Perspectives, statements
- `test_analyst_*.py`: Analyst agent concerns (LLM-marked)
- `test_streaming.py`: Stream events, submit_stream, chat_stream (unit + real_llm end-to-end)
- `conftest.py`: DI setup, mock brain fixture, graph DB cleanup

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

    t = Statement(text="Democracy empowers citizens")
    t.save()
    pp.t.connect(t)

    assert pp.t.count() == 1
    result = pp.t.get()
    assert result is not None
    stmt, rel = result
    assert stmt.text == "Democracy empowers citizens"
```

---

## Documentation References

| Doc | Purpose |
|-----|---------|
| `docs/graph.md` | Graph data model reference |
| `docs/graph-portability.md` | Identifiers, scopes, cloning & realms |
