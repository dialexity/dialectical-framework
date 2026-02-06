# Vocabulary

**Vocabulary** is the pool of `DialecticalComponent` nodes available for building WisdomUnits in a given context. Think of it as "what words/concepts can I use here?"

## Quick Reference

| Context | Method | What's Included |
|---------|--------|-----------------|
| Single Input | `repo.get_vocabulary(input)` | Components from that Input + its Ideas |
| Brainstorm (Gen-0) | `repo.get_vocabulary(brainstorm)` | All HAS_INPUT components + derivative dx:// components |
| Nexus (Gen-1+) | `repo.get_vocabulary(nexus)` | WU positions + Synthesis + dx:// + inherited |

All vocabulary operations go through `DialecticalComponentRepository.get_vocabulary()`:

```python
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository
)

repo = DialecticalComponentRepository()

# All three context types use the same API
input_vocab = repo.get_vocabulary(input_node)       # Single Input
brainstorm_vocab = repo.get_vocabulary(brainstorm)  # Gen-0
nexus_vocab = repo.get_vocabulary(nexus)            # Gen-1+
```

---

## Input Vocabulary

```python
vocab = repo.get_vocabulary(input_node)
```

**Returns:** Components extracted from that single Input:
- Direct: `Input --HAS_STATEMENT--> Component`
- Via Ideas: `Input --DISTILLED_TO--> Ideas --HAS_STATEMENT--> Component`

**Example:** If you have an Input pointing to an article, the vocabulary is all the statements/concepts extracted from that article.

---

## Brainstorm Vocabulary (Gen-0)

```python
vocab = repo.get_vocabulary(brainstorm)
```

**Returns:** Union of components from:
1. **HAS_INPUT Inputs** - Direct user uploads
2. **Ideas** - Components extracted via Ideas nodes
3. **Derivative dx:// Inputs** - Components from Inputs referencing Rationales/Components within this Brainstorm's scope (even without HAS_INPUT connection)

```
Brainstorm (sid=abc123)
├── HAS_INPUT → Input-A (https://article.com)
│   ├── HAS_STATEMENT → "Remote work increases productivity"
│   └── DISTILLED_TO → Ideas
│       └── HAS_STATEMENT → "Isolation is a challenge"
│                            ↑
│                            Rationale1.EXPLAINS
│
└── Input-B (dx://abc123/rationale1-hash)  ← NOT connected via HAS_INPUT
    └── HAS_STATEMENT → "New insight from rationale"  ← INCLUDED in vocabulary!

get_vocabulary() → [all 3 components]
```

This is your **Gen-0 working set** - the raw material before any synthesis. Derivative Inputs allow analytical work (explaining, critiquing) to produce new components that remain part of the same vocabulary.

---

## Nexus Vocabulary (Gen-1+)

```python
vocab = repo.get_vocabulary(nexus)
```

**Returns:** A richer set including:
1. **Position components** - From WisdomUnits in this Nexus (T, A, T+, T-, A+, A-)
2. **Synthesis components** - S+/S- created via Transformations
3. **dx:// referenced content** - Components from derivative Inputs within scope
4. **Inherited vocabulary** - From parent Nexuses (via `origin_hash` lineage)

This is your **analytical vocabulary** - original concepts plus new synthesized insights.

---

## Multi-Context Components

A `DialecticalComponent` can belong to **multiple vocabulary contexts** because:
- Components are **content-addressable** (same statement = same hash)
- Multiple sources can independently extract the same insight
- `HAS_STATEMENT` means "this source produced this insight" (provenance, not ownership)

```
Input-A (article about climate)     Input-B (article about policy)
    │                                   │
    └── HAS_STATEMENT ──────┬───────────┘
                            ▼
              "Rising sea levels threaten cities"
              (same component, two sources)
```

**Checking membership:**

```python
repo = DialecticalComponentRepository()

# Get all contexts for a component (returns list)
contexts = repo.get_vocabulary_contexts(component)

# Check if component belongs to a specific vocabulary
if repo.is_in_vocabulary(component, target_input):
    print("Component can be used in this vocabulary")
```

---

## Vocabulary Purity Rule

When building a WisdomUnit, all 6 components must **share at least one vocabulary context**:

```python
# Gen-0 WU: components must share an Input context
wu.t.connect(comp_from_input_a)        # Sets vocabulary context
wu.a.connect(comp_from_both_a_and_b)   # ✓ OK - shares Input-A
wu.t_plus.connect(comp_only_from_b)    # ❌ ERROR - no shared context

# Gen-1 WU (in Nexus): components must be in that Nexus's vocabulary
wu.t.connect(comp_in_nexus_vocab)      # ✓ OK
wu.a.connect(comp_not_in_vocab)        # ❌ ERROR
```

This ensures **coherent reasoning** - you can't mix concepts from unrelated contexts.

**Derived components** (no vocabulary context) are allowed anywhere - they're generated during analysis and haven't been assigned to a source.

---

## dx:// URIs and Vocabulary

The `dx://` URI scheme enables derivative content:

```
dx://<sid>/<hash>
```

- **sid**: Scope identifier (Brainstorm.sid or Nexus.sid)
- **hash**: Content hash of referenced node (Rationale, Component)

**Example flow:**
1. Input-A extracts Component-X from an article
2. Rationale1 explains Component-X
3. Input-B with `content="dx://sid/rationale1-hash"` references that explanation
4. Input-B extracts new insights → these become part of the vocabulary

```python
# Create derivative Input
dx_uri = f"dx://{brainstorm.sid}/{rationale.hash}"
derivative_input = Input(content=dx_uri)
derivative_input.commit()

# Extract new component
new_insight = DialecticalComponent(statement="Derived insight")
new_insight.commit()
derivative_input.statements.connect(new_insight)

# This component is now in repo.get_vocabulary(brainstorm)
# even though derivative_input has no HAS_INPUT connection!
```

---

## Summary

| Concept | Description |
|---------|-------------|
| **Vocabulary** | Pool of components available in a context |
| **Gen-0** | Raw material from user uploads (Brainstorm) |
| **Gen-1+** | Analytical work including synthesis (Nexus) |
| **Multi-context** | Same component can belong to multiple vocabularies |
| **dx:// derivative** | New components from referencing existing content |
| **Purity rule** | WU components must share at least one context |
| **is_in_vocabulary()** | Preferred method for membership checks |
