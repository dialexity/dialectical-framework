# Portability & Merkle Identity

This document defines the Merkle-based identifier model used in the dialectical graph so that:
- graphs can be copied ("cloned") between workspaces,
- parts of graphs can be escalated into broader visibility realms,
- references remain stable across exports/imports,
- we do not rely on database-internal node IDs for identity,
- content integrity is cryptographically verifiable.

## Goals

1. **Content-addressable identity**
   - Node identity is derived from content (Merkle tree), not assigned randomly.
   - Same content produces same identity across all environments.

2. **Portability across databases and environments**
   - Identifiers must survive export/import, backups, restores, and vendor changes (Memgraph/Neo4j).
   - Database-internal IDs (e.g., `id(n)` / `_id`) are treated as implementation details.

3. **Safe scoping in a shared database**
   - The same database instance may store many independent explorations.
   - Queries and references must not accidentally cross between explorations.

4. **Create-new, reject-old editing model**
   - Editing a committed node means creating a new node and rejecting the old one.
   - No per-node lineage tracking — the Case is the unit of versioning.

5. **Immutable committed state**
   - Uncommitted (draft) nodes can be modified; committed nodes are immutable.

## Terminology

- **Scope**: A "site-like" container for a portable exploration graph.
- **Site**: Synonym for scope; conceptually a Case acts as the site root.
- **Page**: Any node within a scope/site.
- **Realm**: Access realm of a scope (e.g., private/protected/public). Realms are properties of scopes.
- **Clone**: Copying a graph/subgraph into a new scope such that identities are regenerated but lineage is preserved.
- **Commit**: Computing and finalizing a node's hash, making the node immutable, and persisting to database.

## Identifier Fields (stored on every node)

### 1) `hash` — Primary Identity
- **Type**: SHA256 hex string (64 characters) or None (uncommitted)
- **Meaning**: Identifies this specific node based on its content.
- **Computed from** (varies by node category):
  - Structure parts: Node's structural content (type-specific, see tables below)
  - `intent`: Only for intent-aware nodes
  - `committed_at`: Ensures temporal ordering
- **Stability**:
  - Immutable once computed (committed).
  - Content-addressable atoms: same content = same hash (globally deduplicated).
  - Structural nodes: same content + same timestamp = same hash.
- **Notes**:
  - This is the primary identifier used by application code.
  - Supports short prefix lookups (minimum 7 characters).
  - **Exception**: Case has `hash = None` (uses UUID `sid` as identity).

### 2) `sid` — Scope Identity (Site ID)
- **Type**: String (UUID for Case, propagated to descendants)
- **Meaning**: Identifies the "site" (scope) to which this node belongs.
- **Stability**:
  - Stable for a node as long as it belongs to the same scope.
  - Changes when a node is cloned into a different scope.
- **Root convention**:
  - The scope root (Case) generates a UUID for `sid` on creation.
  - All nodes under that Case carry the same `sid` value.

### 3) `committed_at` — Temporal Ordering
- **Type**: Float (Unix timestamp) or None
- **Meaning**: When the node was committed.
- **Purpose**:
  - Included in hash computation to ensure temporal ordering.
  - Prevents critique cycles (a node cannot critique something committed after it).

## Scoped Address

While `hash` provides content-based identity, the same content can exist in different scopes. For globally unique addressing, use `sid:hash`:

- **Format**: `<sid>:<hash>` (e.g., `a1b2c3d4-...:e5f6g7h8...`)
- **Case**: Since `hash = None`, use just `sid`
- **Within scope**: `hash` alone is sufficient when scope is known

This pattern ensures:
- Identical content in different scopes has the same `hash` (content-addressable)
- Each node instance is still uniquely addressable via `sid:hash`

## Node Lifecycle

### States

1. **Draft**: Node is created but not committed.
   - `hash` is None
   - `committed_at` is None
   - Node can be modified

2. **Committed**: Node is committed and persisted.
   - `hash` is set (SHA256 hex)
   - `committed_at` is set (Unix timestamp)
   - `_id` is set (database ID)
   - Structure is immutable (modifications require cloning)

### Workflow

**Standard nodes** (Statement, Rationale, etc.):

```python
# 1. Create node (draft state)
stmt = Statement(text="Example")
assert not stmt.is_committed
assert stmt.hash is None

# 2. Commit (computes hash AND persists to database)
stmt.commit()
assert stmt.is_committed
assert len(stmt.hash) == 64
assert stmt._id is not None  # Already in database
```

**Container nodes** (Nexus, Cycle, Wheel, Spiral - via IncrementalBuildMixin):

```python
# 1. Create container (draft state)
nexus = Nexus(intent="Focus on productivity tensions")

# 2. Save as HEAD state (persisted but hash=None)
nexus.save()
assert nexus._id is not None  # In database
assert nexus.hash is None     # Not committed yet

# 3. Add children incrementally
nexus.perspectives.connect(pp1)
nexus.perspectives.connect(pp2)

# 4. Commit (computes Merkle hash, makes immutable)
nexus.commit()
assert nexus.is_committed
assert nexus.hash is not None
# Cannot add more perspectives after commit
```

**Case** (scope root):

```python
# Case uses UUID for sid, never computes hash
case = Case()
assert case.sid is not None  # UUID generated
assert len(case.sid) == 36   # UUID format

case.commit()
assert case.hash is None     # Always None for Case
assert case._id is not None  # Persisted
```

## Node Categories and Identity

Nodes are organized into categories based on their role and identity model.

### Container

| Node | hash | Role |
|------|------|------|
| **Case** | None (UUID sid) | Scope root, never finished |

### Atoms — Content

Global facts. Same content = same identity everywhere. No lineage tracking.

| Node | hash = sha256(...) | Role |
|------|-------------------|------|
| **Statement** | text | Content |
| **Input** | content | Content |

### Atoms — Effect (Content-Addressable)

Computed outcomes attached to structures. Same effect = same identity. No lineage tracking.
Designed for deduplication: same content on same target resolves to the same node.

| Node | hash = sha256(...) | Role |
|------|-------------------|------|
| **Rationale** | text, target.hash | Evidence |
| **Estimation** | type_name, value, target.hash | Measurement |

### Atoms — Effect (Instance-Unique)

Computed outcomes where each instance is unique. No lineage tracking.

| Node | hash = sha256(...) | Role |
|------|-------------------|------|
| **Transition** | source.hash, target.hash, nonce, committed_at | Effect |
| **Synthesis** | s+.hash, s-.hash, [intent], committed_at | Effect |

### Reasoning Foundations

These are the basis of reasoning. Editing means creating a new node and rejecting the old one.

| Node | hash = sha256(...) | Role |
|------|-------------------|------|
| **Perspective** | polarity.hash, t+.hash, t-.hash, a+.hash, a-.hash, [intent], committed_at | Tension framing |
| **Nexus** | preset, [intent], committed_at | Exploration container |

### Derived Structures

Computed from forking points or inputs. No lineage tracking — fork upstream instead.
Uses `IncrementalBuildMixin` for staged building (save → add children → commit).

| Node | hash = sha256(...) | Role |
|------|-------------------|------|
| **Ideas** | input.hash, sorted(statement_hashes), [intent], committed_at | Extraction (from Input) |
| **Cycle** | nexus.hash, sorted(transition_hashes), [intent], committed_at | Ordering (from Nexus) |
| **Wheel** | cycle.hash, sorted(transition_hashes), [intent], committed_at | Detail (from Cycle) |
| **Transformation** | pp.hash, ordered(transition_hashes), [intent], committed_at | Resolution (from PP) |
| **Spiral** | wheel.hash, sorted(transition_hashes), [intent], committed_at | Navigation (from Wheel) |

[brackets] = optional, only included if non-None

### Key Observations

- **Atoms are global facts/effects**: Same content = same node.
- **Reasoning foundations (Perspective, Nexus)** are immutable after commit — editing means creating a new node and rejecting the old.
- **`committed_at`** ensures temporal ordering.
- **`nonce`** (Transition only) ensures uniqueness for repeated source→target pairs.
- **Sorting** makes order-independent containers produce consistent hashes.

## Editing Semantics

Committed nodes are immutable. To "edit" a Perspective or Nexus:
1. Clone the node (creates an uncommitted copy)
2. Modify the clone
3. Commit the clone (gets a new hash)
4. Reject the old node (`rejected` field)

```python
# Edit a Perspective by creating a new one
new_pp = original_pp.clone()
new_pp.save()
new_pp.t_plus.disconnect(old_stmt)
new_pp.t_plus.connect(new_stmt)
new_pp.commit()

# Mark old PP as rejected
original_pp.rejected = "replaced by edit"
original_pp.save()
```

### Cross-scope references

Atoms (Statement, Input, etc.) are globally addressable by hash.
A Perspective in scope B can reference the same Statement as one in scope A — they share the atom.

## Short Hash Lookup

You can reference nodes by short hash prefixes (minimum 7 characters):

```python
from dialectical_framework.graph.repositories.node_repository import NodeRepository

repo = NodeRepository()

# Full hash lookup
node = repo.find_by_hash("abc123def456...")

# Short prefix lookup
node = repo.find_by_prefix("abc123d")  # Minimum 7 chars
```

## Scope Access / Realms

### Realms
We recognize these access realms:
- **private**: visible to workspace members per application rules.
- **protected**: visible to a broader set of users but not globally public.
- **public**: globally accessible ("Indranet" public knowledge).

### Where access is stored
Access is a **scope-level property**, not part of identifiers:
- A scope (Case/site) has an access realm stored by the application.
- Nodes inherit access from their scope via `sid`.

## Database Indexes

The following indexes support efficient lookups:

- `hash`: Primary identity lookups, unique constraint
- `sid`: Scope-based queries (find all nodes in a scope)

## Summary

### Identity Fields

| Field | Type | Used By | Purpose |
|-------|------|---------|---------|
| `hash` | SHA256 | All except Case | Primary identity (content-derived) |
| `sid` | UUID | All | Scope identity (Case's UUID) |
| `committed_at` | Float | Structural nodes | Temporal ordering |
| `intent` | String | Intent-aware nodes | Reasoning purpose |

### Node Categories

| Category | Nodes | Role |
|----------|-------|------|
| Container | Case | Scope root |
| Atoms (Content) | Statement, Input | Global facts |
| Atoms (Effect) | Transition, Rationale, Estimation, Synthesis | Computed outcomes |
| Reasoning Foundations | Perspective, Nexus | Tension framing & exploration |
| Derived | Ideas, Cycle, Wheel, Transformation, Spiral | Computed from inputs/foundations |

### Key Properties

- **Atoms are global**: Same content = same hash = same node across all of Indranet
- **Immutable after commit**: Editing = create new + reject old
- **Derived structures flow down**: Create new upstream (Nexus/PP) to explore alternatives
- **Scoped address**: `sid:hash` for global uniqueness across scopes
