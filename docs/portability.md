# Portability & Identifiers

This document defines the identifier model used in the dialectical graph so that:
- graphs can be copied (“cloned”) between workspaces,
- parts of graphs can be escalated into broader visibility realms,
- references remain stable across exports/imports,
- we do not rely on database-internal node IDs for identity.

## Goals

1. **Portability across databases and environments**
   - Identifiers must survive export/import, backups, restores, and vendor changes (Memgraph/Neo4j).
   - Database-internal IDs (e.g., `id(n)` / `_id`) are treated as implementation details.

2. **Safe scoping in a shared database**
   - The same database instance may store many independent explorations.
   - Queries and references must not accidentally cross between explorations.

3. **Clone-friendly provenance**
   - When a graph (or subgraph) is cloned into a new scope, the clone gets new node identities but preserves lineage information.

4. **Access model compatibility**
   - Workspaces and permissions live at the application level.
   - Graph data is organized into scopes that the application can authorize.

## Terminology

- **Scope**: A “site-like” container for a portable exploration graph.
- **Site**: Synonym for scope; conceptually a Brainstorm acts as the site root.
- **Page**: Any node within a scope/site.
- **Realm**: Access realm of a scope (e.g., private/protected/public). Realms are properties of scopes, not embedded into portable IDs.
- **Clone**: Copying a graph/subgraph into a new scope such that identities are regenerated but lineage is preserved.

## Identifier Fields (stored on every node)

### 1) `uid` — Node Identity (Instance ID)
- **Type**: UUIDv7 string
- **Meaning**: Identifies this specific node instance within the database.
- **Stability**:
  - Stable for the lifetime of the node instance.
  - Regenerated on clone/import into a new scope.
- **Notes**:
  - This is the primary internal identifier used by application code.
  - This is not the database-internal ID.

### 2) `sid` — Scope Identity (Site ID)
- **Type**: UUID string (typically the root Brainstorm `uid`)
- **Meaning**: Identifies the “site” (scope) to which this node belongs.
- **Stability**:
  - Stable for a node as long as it belongs to the same scope.
  - Changes when a node is cloned into a different scope.
- **Root convention**:
  - The scope root (Brainstorm) has `sid == uid`.
  - All nodes under that Brainstorm carry the same `sid` value.

### 3) `origin_uid` — Lineage Identity
- **Type**: UUIDv7 string
- **Meaning**: Identifies the lineage origin of a node across clones.
- **Stability**:
  - Never changes across clones.
- **Rules**:
  - For a node created “from scratch”: `origin_uid = uid`.
  - For a cloned node: `origin_uid = source.origin_uid` (fallback: source `uid` if origin is missing).

### 4) `nid` — Portable Address (Node Address)
- **Type**: string
- **Meaning**: A stable, scope-qualified address for referencing a node safely.
- **Format**:
  - **Non-root nodes**: `<sid>:<uid>`
  - **Scope root (Brainstorm)**: `<sid>` (since `sid == uid` for Brainstorm)
- **Purpose**:
  - Enables safe lookups without forgetting scope.
  - Serves as the preferred external identifier for APIs, logs, and export manifests.

## Scope Access / Realms

### Realms
We recognize these access realms:
- **private**: visible to workspace members per application rules.
- **protected**: visible to a broader set of users but not globally public (policy defined by application).
- **public**: globally accessible (“Indranet” public knowledge).

### Where access is stored
Access is treated as a **scope-level property**, not part of `nid`:
- A scope (Brainstorm/site) has an access realm (private/protected/public) stored and enforced by the application.
- Nodes inherit access from their scope because their `sid` ties them to that scope.

### Why access is not encoded into `nid`
- `nid` is a portable address; access policy can change without changing identity.
- Keeping access outside the ID avoids ID churn if a scope transitions from private → protected → public.

## Query & Safety Rules

1. **Scope-first querying**
   - All graph queries must be scoped by `sid` (or by `nid`, which includes `sid`).
   - This prevents cross-scope data leaks in a shared database.

2. **Never depend on database-internal node IDs**
   - Internal IDs may not be stable across export/import or restores.
   - Application-level identity uses `uid`/`nid`.

3. **External references should use `nid`**
   - If an API or UI needs to address a node, it should accept/emit `nid`.
   - `nid` is self-contained with respect to scope (contains `sid`).

## Cloning Semantics

Cloning is the only supported mechanism for escalating content between realms (e.g., private → public).

### Clone operation (node-level rules)
When cloning a node from a source scope `sid_src` to a destination scope `sid_dst`:

- Generate a new `uid` for the cloned node.
- Set `sid = sid_dst`.
- Preserve lineage:
  - `origin_uid = source.origin_uid` (or source `uid` if missing).
- Recompute `nid` using the destination scope:
  - `nid = "<sid_dst>:<new_uid>"`.

### Clone operation (scope-level rules)
Cloning a scope (a Brainstorm/site) into a new scope creates a new site identity:
- Create a new Brainstorm root node with:
  - new `uid` (thus new `sid`, since `sid == uid` for Brainstorm).
  - new `nid` equal to the new `sid`.
  - `origin_uid` preserved from the source Brainstorm lineage.

All cloned child nodes receive the new `sid` and new `nid`s accordingly.

### Escalation between realms
Escalation (private → protected → public) is implemented as:
- cloning from a source scope to a new destination scope in the target realm,
- never mutating the source scope in place,
- preserving `origin_uid` to keep provenance links intact.

## Indranet (Public Knowledge)

Indranet is the public realm where nodes are interlinked and globally accessible.

- Public content is represented as one or more **public scopes** (sites).
- A public scope is still a scope with a `sid` (site id), enabling:
  - clean partitioning of public corpora if needed (e.g., staging vs published),
  - stable addressing via `nid`.

## Migration & Compatibility Notes

- Existing nodes created before this scheme may lack `sid`, `origin_uid`, or `nid`.
- Migration should follow these rules:
  - If `origin_uid` missing: set `origin_uid = uid`.
  - If `sid` missing: derive it from the node’s containing Brainstorm (root) where possible.
  - If `nid` missing: compute it from `sid` and `uid`.

## Summary

- `uid` (UUIDv7) identifies a node instance.
- `sid` identifies the scope/site; Brainstorm is the site root (`sid == uid`).
- `origin_uid` preserves lineage across clones.
- `nid` (`<sid>:<uid>`, or `<sid>` for the root) is the portable address used for external references and safe lookups.
- Access realms (private/protected/public) are scope-level policy enforced by the application; escalation happens by cloning.
