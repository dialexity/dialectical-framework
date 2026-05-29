# CLAUDE.md - AI Co-Developer Guide

## Collaboration Style

Give honest opinions with clear tradeoffs — not agreement for the sake of agreement. State what you actually think is the better approach and why. If both options are defensible, say so directly.

## What is the Dialectical Framework?

A semantic graph system for dialectical reasoning — modeling thesis-antithesis-synthesis dynamics as graph structures. Used for systems analysis, wisdom mining, and ethical modeling.

### Theoretical Foundation (Generative Rules)

The framework is fully rule-constrained. These rules govern what constitutes valid dialectical synthesis:

**1. Tetrad structure.** Every thesis T generates exactly one antithesis A. The T–A interaction yields four components bound by three constraints:
- **T+** / **A+**: Constructive developments that enhance the upsides of opposition (not merely "positive" — they actively balance the other side)
- **T-** / **A-**: Exaggerations of the parent concept AND underdevelopments of the opposition (one-sided overdevelopments, not merely "negative")
- T+ must directly contradict A- (and vice versa); T- must directly contradict A+

**2. Circular Causality (Transition Rule).** Positive synthesis (S+) arises if and only if two complementary transitions occur simultaneously:
- T- is transformed into a constructive antithesis component (A+)
- A- is transformed into a constructive thesis component (T+)
This closed loop is the true source of self-regulation and is WHY `Ac+` (T-→A+) and `Re+` (A-→T+) are the required Transformation positions.

**3. Modality Balance.** M(T+) + M(A-) + M(T-) + M(A+) = 0. A zero-sum constraint: increases in one pole are compensated by decreases in its complement. Balanced systems have symmetry in absolute modality values.

**4. Complementarity.** K = (K_T + K_A) / 2, where K_T and K_A measure how well aspects complement T and A respectively. In balanced tetrads: K_T(T+) > K_T(T-) and K_T(A+) > K_T(A-). Complementarity + HS (Heuristic Similarity to apex) together determine tetrad quality.

**5. Equal-Sign Synthesis.** S+ emerges between T+ and A+ (like-signed constructive poles). S- emerges between T- and A- (like-signed destructive poles). No direct interaction between different-sign poles (T+↔A-, T-↔A+) — these are contradictions at different developmental levels of the same phenomenon.

**6. Control Statements.** Coherence test: "T+ without A+ yields T-" and "A+ without T+ yields A-". A system exhibits S+ iff it increases dimensionality while preserving stability, distinction, and normative coherence.

**7. Apex Coherence.** S+/- must lie within the convex hull (or semantic centroid) of its valid sub-syntheses. Valid sub-syntheses satisfy modality balance, complementarity (Kc), and control-statement coherence. This prevents extrapolation or arbitrary abstraction.

**8. Systemic Taxonomy.** A universal taxonomy (Table S-1 in addendum) classifies balanced tetrads across 5 branches: Integrity, Fidelity, Exchange, Flexibility, Resilience. Each branch has apex concepts for T+, T-, A+, A- per domain. Implemented in `concerns/statement_classification.py` as `SYSTEMIC_TAXONOMY`. Used to compute HS (Heuristic Similarity to apex) and anchor aspects in the taxonomy structure.

**Greimas mapping:** Ac (Action) corresponds to Not-A space (everything from T to Ac+); Re (Reflection) corresponds to Not-T space (everything from A to Re+). Ac+/Re+ are generative operations; Ac-/Re- represent transitions' degradation modes.

### Core Model

**Positions (6 core + 2 synthesis):**

| Position | Role |
|----------|------|
| T / A | Neutral thesis / antithesis (dialectical opposition) |
| T+ / A+ | Constructive balance — enhances the opposition's upsides |
| T- / A- | Exaggeration — overdevelops self, underdevelops opposition |
| S+ | Emergent quality from circular causality (dimensionality increase) |
| S- | Consolidation/reduction (dominance or oscillation, finite lifespan) |

**Key nodes:** Statement, Perspective (PP), Polarity, Nexus, Cycle, Wheel, Transformation, Transition, Ideas, Input, Case, Synthesis

**Hierarchy:** Perspective → Cycle → Wheel (edges) → Transformation
**Case flow:** Case → Input → Ideas → Statements
**Exploration flow:** Perspectives → Nexus → Cycles → Wheels

See `docs/graph.md` for full data model (positions, transformations, cardinality, layers, intent levels, rejection/editing rules).

### Structural vs Analytical Layers

- **Structural** (immutable after commit): Merkle-tree backbone. Containers use `save() → add members → commit()`.
- **Analytical** (mutable anytime): Rationale, Estimation, Critique, Synthesis, ac_re.

### User-Facing Vocabulary is App-Layer

The graph model uses universal terms (Statement, Polarity, Perspective, T+/T-/A+/A-). User-facing vocabulary is contextual — not a fixed translation table — and depends on who the user is. Defined in `agents/apps.py` (`DEFAULT_APP`, `ADVANCED_APP`) and injected via `app_preamble` in the Analyst/Explorer constructor. System prompts handle tool selection/workflow only; they never dictate presentation vocabulary.

---

## Development Commands

Poetry project (Python 3.11+):

```
docker compose -f docker-compose.test.yml up -d  # start Memgraph (required for graph tests)
poetry run pytest                    # all tests, LLM mocked
poetry run pytest --real-llm         # only LLM tests with real provider
poetry run pytest -m llm             # only LLM-path tests (mocked)
poetry run black src/ tests/         # format
poetry run isort src/ tests/         # sort imports
poetry run autoflake --in-place --remove-all-unused-imports --recursive src/ tests/
```

---

## Technology Stack

- **Graph DB**: Memgraph or Neo4j (via GQLAlchemy)
- **DI**: dependency-injector
- **Validation**: Pydantic v1
- **LLM**: Mirascope (OpenAI, Anthropic, LiteLLM)

---

## Where Things Live

| Purpose | Location |
|---------|----------|
| DI Container (START HERE) | `dialectical_reasoning.py` |
| Graph nodes | `graph/nodes/*.py` |
| Relationships | `graph/relationships/*.py` |
| Relationship API | `graph/relationship_manager.py` |
| Repositories (data access) | `graph/repositories/` |
| Graph mixins | `graph/mixins/` |
| Concerns (standalone services) | `concerns/` |
| Analyst (conversational, Case-scoped) | `agents/analyst/analyst.py` |
| Explorer (conversational, Nexus-scoped) | `agents/explorer/explorer.py` |
| App preambles (vocabulary/framing) | `agents/apps.py` |
| Shared agent tools | `agents/orchestrator/tools/` |
| Agent skills/tools | `agents/{analyst,explorer}/` |
| LLM abstraction | `utils/use_brain.py` |
| Utilities | `utils/` |
| Events (domain event bus) | `events/` |
| Exceptions | `exceptions/` |
| Protocols (interfaces) | `protocols/` |
| Configuration | `settings.py` |

All paths relative to `src/dialectical_framework/`.

---

## Critical Conventions

### Keep `__init__.py` files empty

All `__init__.py` must be empty — no module exports.

### Preserve TODOs - Ask Before Removing

Do not remove TODO comments without confirming with the user first. Flag them when refactoring nearby code.

### Update GRAPH_SCHEMA When Changing Graph Structure

`GRAPH_SCHEMA` in `agents/orchestrator/tools/get_schema.py` is the LLM's reference for Cypher queries. Update it when adding/removing/renaming nodes, relationships, or significant properties.

### Query Safety: All Queries in Repositories

All DB queries must go through `graph/repositories/` classes, scoped by `sid`. Never write raw `graph_db.execute_and_fetch()` in tools/skills/concerns/nodes.

**Allowed exceptions:** `dialectical_reasoning.py` (schema init), `relationship_manager.py`, `estimation_manager.py`, `query_graph.py` (LLM read-only Cypher).

---

## Core Patterns

### Dependency Injection

```python
from dependency_injector.wiring import inject, Provide
from dialectical_framework.enums.di import DI

@inject
def my_function(graph_db: Memgraph | Neo4j = Provide[DI.graph_db]):
    pass
```

**Anti-patterns:**
- Don't pass `graph_db` between `@inject` methods — each gets the same singleton automatically
- Don't store `graph_db` as instance variable — inject on each method that needs it

### Graph Node Lifecycle

```python
# Simple nodes: commit() does save + hash
stmt = Statement(text="..."); stmt.commit()

# Container nodes (IncrementalBuildMixin): save() → add → commit()
container.save()
child.rel.connect(container)  # OK before commit
container.commit()            # Immutable after this
```

### Relationship Direction

`RelationshipTo` and `RelationshipFrom` define the SAME edge from different perspectives. Convention: Child→Parent edges use `RelationshipTo` on child.

```python
class Perspective(AssessableEntity):
    nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")  # PP→Nexus

class Nexus(AssessableEntity):
    perspectives = RelationshipFrom("Perspective", "BELONGS_TO_NEXUS")  # Same edge, reverse view
```

### Scope (sid)

All nodes share `sid` from their Case. Enforced at connect time. Use `with scope(case.sid):` to set context.

---

## Tool Pattern (Mirascope)

Two-layer: `ReasonableConcern[T]` (implementation) + `@llm.tool` function (LLM-facing interface).

**Hierarchy (increasing scope):**
- **Concern** = standalone service, single responsibility → lives in `concerns/`
- **Tool** = thin wrapper, single DB op → lives in `agents/{phase}/tools/`
- **Skill** = orchestrates multiple concerns, has reasoning responsibility → lives in `agents/{phase}/skills/`
- **Agent** = top-level conversational coordinator, owns a tool set → lives in `agents/{phase}/`

Only `@llm.tool` functions go into tool lists. `ReasonableConcern` classes are never passed to Mirascope directly.

```python
@llm.tool
async def surface_theses(
    intent: Annotated[str, Field(description="What theses to find")],
    input_hashes: Annotated[list[str] | None, Field(description="Input hashes to process selectively")] = None,
) -> str:
    """Surfaces theses for dialectical analysis."""
    skill = SurfaceTheses(intent=intent, input_hashes=input_hashes)
    await skill.resolve()
    return str(skill.report)
```

**Critical:** Never use `param = Field(default=X, ...)` as a Python default — Mirascope leaves the raw `FieldInfo` object as the runtime default. Always use `Annotated[type, Field(...)] = actual_default`. Test coverage: `test_tool_signatures.py`.

**Report artifacts must include final-state text.** When a skill uses `StatementDeduplication`, the LLM only sees `node_created` effects (with original text) and `node_deleted` effects (hash-only). It cannot access the replacement node's text from effects alone. Every skill that deduplicates must add an artifact with the authoritative post-dedup text (e.g., `artifacts["theses"]`, `artifacts["polarities"]`, `artifacts["perspectives"]`). See `expand_polarities.py` for the reference pattern.

---

## Type Hints

**Hard rules:**
1. Every module starts with `from __future__ import annotations`
2. Use `TYPE_CHECKING` for circular imports — never quoted type strings
3. Type ALL function parameters and return values
4. Use `ClassVar[RelationshipManager[T]]` for GQLAlchemy descriptors
5. Modern syntax: `list[str]`, `dict[str, int]`, `X | None` — not `List`, `Dict`, `Union`
6. Prefer `isinstance(node, IntentMixin)` over `getattr(node, 'intent', None)` for mixin attributes

---

## Testing

| Marker | Purpose | Default run | With `--real-llm` |
|--------|---------|-------------|-------------------|
| *(none)* | Pure logic | Runs | Runs |
| `@pytest.mark.llm` | LLM code paths | Mock brain | Real LLM |
| `@pytest.mark.real_llm` | Must hit real provider | Skipped | Runs |

Default to `@pytest.mark.llm` for anything touching `use_brain` or `ConversationFacilitator`.

**Mock brain** (`tests/mock_brain.py`) auto-constructs Pydantic responses. It does NOT test: streaming, tool registration (`@llm.tool` decorator), tool argument parsing, or provider behavior.

**DB-free tests:** Override autouse fixtures `cleanup_graph_db` and `cleanup_test_graph_data` with empty yields.

---

## Environment Configuration

Required in `.env`:
- `DIALEXITY_DEFAULT_MODEL` / `DIALEXITY_DEFAULT_MODEL_PROVIDER`

Optional:
- `DIALEXITY_GRAPH_DB_VENDOR` (memgraph/neo4j), `_HOST`, `_PORT`
- `DIALEXITY_DEFAULT_CYCLE_PRESET`

---

## Prompt Engineering

The project is infused with LLM prompts at multiple layers. `docs/PROMPTING.md` has general principles.

| Location | What it controls |
|----------|-----------------|
| `agents/apps.py` | User-facing vocabulary/framing (DEFAULT_APP, ADVANCED_APP) |
| `agents/analyst/system_prompts.py` | Analyst tool selection and workflow |
| `agents/explorer/system_prompts.py` | Explorer tool selection and workflow |
| `concerns/` | Structured LLM calls within skills (Mirascope) |
| `agents/orchestrator/tools/query_graph.py` | Cypher generation prompt |

When fixing prompt output bugs: follow the revision methodology in the `apps.py` module docstring (diagnose root cause → apply fix → add regression test to `tests/test_prompt_vocabulary.py`).

---

## Documentation References

| Doc | Purpose |
|-----|---------|
| `docs/graph.md` | Full graph data model (positions, transformations, cardinality, layers, intent) |
| `docs/graph-portability.md` | Identifiers, scopes, cloning & realms |
| `docs/PROMPTING.md` | General prompt engineering DOs and DON'Ts |
