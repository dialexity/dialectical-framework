"""
GetSchema: On-demand graph schema tool.

Provides the LLM with full graph schema (node types, relationships, Cypher patterns)
when needed — typically before writing raw Cypher queries.
"""

from __future__ import annotations

from mirascope import llm

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.repositories.schema_repository import SchemaRepository


GRAPH_SCHEMA = """## Graph Schema

### Node Types

| Node | Description | Key Properties |
|------|-------------|----------------|
| Case | Root scope container | |
| Input | External content (text, URL) for analysis | `content`, `digest` |
| Ideas | Collection of extracted Statements from Inputs | `intent` |
| Statement | A thesis, position, or claim | `text`, `meaning`, `discarded` |
| Polarity | A tension — structural T-A pair (thesis vs antithesis) | |
| Perspective | Full interpretation: Polarity + evaluative aspects (T+, T-, A+, A-) | `intent`, `discarded` |
| Nexus | Exploration container grouping Perspectives for combination | `intent`, `preset`, `title` |
| Cycle | Ordered sequence of Perspectives defining causality | `intent` |
| Wheel | Concrete T-A arrangement implementing a Cycle | `intent` |
| Transformation | Action-reflection structure (Ac, Re, Ac+, Ac-, Re+, Re-) on a Wheel edge | `intent` |
| Transition | Movement between two Statements (source → target) | `statement`, `headline`, `haiku` |
| Synthesis | Emergent S+/S- pair from a Wheel's circular causality | |
| Rationale | Explanation attached to any node | `text` |
| Estimation | Numeric assessment (probability, relevance, feasibility) | `value` |

All nodes share: `hash` (content-addressable ID), `sid` (scope ID), `committed_at`.

**Important:** Only query committed nodes. Always add `WHERE n.hash IS NOT NULL` to filter out incomplete (in-progress or abandoned) nodes. Nodes with `hash IS NULL` are not yet finalized and must not be included in results.

### Relationship Edge Properties

**Polarity positions** (T, A, T_PLUS, T_MINUS, A_PLUS, A_MINUS relationships) carry:
- `heuristic_similarity` (float, 0.0-1.0) — HS: similarity to taxonomy apex

**Aspect positions** (T_PLUS, T_MINUS, A_PLUS, A_MINUS) additionally carry:
- `complementarity_t` (float, 0.0-1.0) — K_T: how well this aspect complements the thesis
- `complementarity_a` (float, 0.0-1.0) — K_A: how well this aspect complements the antithesis

**Transformation aspect positions** (AC_PLUS, AC_MINUS, RE_PLUS, RE_MINUS) carry:
- `heuristic_similarity` (same as above)
- `insight` (float, 0.0-1.0) — how much understanding the transition provides
- `proactiveness` (float, 0.0-1.0) — how actionable the transition is

### Relationship Types and Directions

**Polarity positions** (Statement → Polarity):
- `(s:Statement)-[:T]->(p:Polarity)` — thesis pole
- `(s:Statement)-[:A]->(p:Polarity)` — antithesis pole

**Perspective positions** (Statement → Perspective):
- `(s:Statement)-[:T_PLUS]->(pp:Perspective)` — positive thesis aspect
- `(s:Statement)-[:T_MINUS]->(pp:Perspective)` — negative thesis aspect
- `(s:Statement)-[:A_PLUS]->(pp:Perspective)` — positive antithesis aspect
- `(s:Statement)-[:A_MINUS]->(pp:Perspective)` — negative antithesis aspect

**Perspective structure**:
- `(pp:Perspective)-[:HAS_POLARITY]->(pol:Polarity)` — which tension this Perspective interprets
- `(pp:Perspective)-[:BELONGS_TO_NEXUS]->(nx:Nexus)` — grouped for exploration
- `(pp:Perspective)-[:CHANGED_TO]->(pp2:Perspective)` — edit lineage (old → new)

**Semantic relations** (between Statements):
- `(s1:Statement)-[:OPPOSITE_OF]->(s2:Statement)` — dialectical opposition (symmetric)
- `(s1:Statement)-[:CONTRADICTION_OF]->(s2:Statement)` — cross-polarity (T+ ↔ A-, symmetric)
- `(s:Statement)-[:POSITIVE_SIDE_OF]->(s2:Statement)` — aspect → neutral
- `(s:Statement)-[:NEGATIVE_SIDE_OF]->(s2:Statement)` — aspect → neutral

**Exploration structure**:
- `(c:Cycle)-[:HAS_WHEEL]->(w:Wheel)` — Cycle contains Wheels
- `(t:Transition)-[:BELONGS_TO_CYCLE]->(w:Wheel)` — Transition is an edge in a Wheel
- `(c:Cycle)-[:OPPOSITE_DIRECTION]->(c2:Cycle)` — reversed causal order (symmetric)
- `(w:Wheel)-[:OPPOSITE_DIRECTION]->(w2:Wheel)` — reversed arrangement (symmetric)

**Transition structure**:
- `(s:Statement)-[:IS_SOURCE_OF]->(t:Transition)` — source component
- `(t:Transition)-[:IS_TARGET_OF]->(s:Statement)` — target component

**Transformation positions** (Transition → Transformation):
- `(t:Transition)-[:AC]->(tr:Transformation)` — action (T → A)
- `(t:Transition)-[:AC_PLUS]->(tr:Transformation)` — positive action (T- → A+)
- `(t:Transition)-[:AC_MINUS]->(tr:Transformation)` — negative action (T+ → A-)
- `(t:Transition)-[:RE]->(tr:Transformation)` — reflection (A → T)
- `(t:Transition)-[:RE_PLUS]->(tr:Transformation)` — positive reflection (A- → T+)
- `(t:Transition)-[:RE_MINUS]->(tr:Transformation)` — negative reflection (A+ → T-)
- `(tr:Transformation)-[:ACTION_REFLECTION]->(t:Transition)` — which Wheel edge this Transformation belongs to
- `(tr:Transformation)-[:BELONGS_TO_NEXUS]->(nx:Nexus)` — scoped to Nexus

**Synthesis positions** (Statement → Synthesis → Wheel):
- `(s:Statement)-[:S_PLUS]->(syn:Synthesis)` — positive synthesis
- `(s:Statement)-[:S_MINUS]->(syn:Synthesis)` — negative synthesis
- `(syn:Synthesis)-[:SYNTHESIS_OF]->(w:Wheel)` — which Wheel it synthesizes

**Container membership**:
- `(case:Case)-[:HAS_INPUT]->(i:Input)` — Case owns Inputs
- `(ideas:Ideas)-[:HAS_STATEMENT]->(s:Statement)` — Ideas contains Statements
- `(i:Input)-[:DISTILLED_TO]->(ideas:Ideas)` — Input distilled into Ideas

**Metadata**:
- `(r:Rationale)-[:EXPLAINS]->(n)` — explanation for any node
- `(e:Estimation)-[:ESTIMATES]->(n)` — numeric assessment of any node

### Common Cypher Patterns

```cypher
-- All Perspectives with T and A statements
MATCH (pp:Perspective)-[:HAS_POLARITY]->(pol:Polarity)
MATCH (t:Statement)-[:T]->(pol)
MATCH (a:Statement)-[:A]->(pol)
RETURN pp.hash, t.text AS thesis, a.text AS antithesis

-- Full Perspective (all 6 positions)
MATCH (pp:Perspective) WHERE pp.hash STARTS WITH "abc"
MATCH (pp)-[:HAS_POLARITY]->(pol)
MATCH (t:Statement)-[:T]->(pol), (a:Statement)-[:A]->(pol)
OPTIONAL MATCH (tp:Statement)-[:T_PLUS]->(pp)
OPTIONAL MATCH (tm:Statement)-[:T_MINUS]->(pp)
OPTIONAL MATCH (ap:Statement)-[:A_PLUS]->(pp)
OPTIONAL MATCH (am:Statement)-[:A_MINUS]->(pp)
RETURN t.text, a.text, tp.text, tm.text, ap.text, am.text

-- Wheel edges (transitions in order)
MATCH (w:Wheel) WHERE w.hash STARTS WITH "abc"
MATCH (t:Transition)-[:BELONGS_TO_CYCLE]->(w)
MATCH (src:Statement)-[:IS_SOURCE_OF]->(t)
MATCH (t)-[:IS_TARGET_OF]->(tgt:Statement)
RETURN src.text AS source, tgt.text AS target

-- Transformations for a Wheel
MATCH (w:Wheel) WHERE w.hash STARTS WITH "abc"
MATCH (edge:Transition)-[:BELONGS_TO_CYCLE]->(w)
MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(edge)
MATCH (ac_t:Transition)-[:AC_PLUS]->(tr)
MATCH (re_t:Transition)-[:RE_PLUS]->(tr)
RETURN tr.hash, ac_t.statement AS action, re_t.statement AS reflection

-- Vocabulary (all non-discarded Statements)
MATCH (s:Statement) WHERE s.discarded IS NULL RETURN s.text, s.hash

-- Aspect relationships with complementarity scores
MATCH (s:Statement)-[r:T_PLUS]->(pp:Perspective)
WHERE r.complementarity_t IS NOT NULL
RETURN s.text, r.heuristic_similarity, r.complementarity_t, r.complementarity_a

-- Transformation positions with insight/proactiveness
MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(edge:Transition)
MATCH (t:Transition)-[r:AC_PLUS]->(tr)
WHERE r.insight IS NOT NULL
RETURN t.statement, r.insight, r.proactiveness
```
"""


class GetSchema(ReasonableConcern[str]):
    """Loads the graph schema for the LLM to reference."""

    async def resolve(self) -> str:
        repo = SchemaRepository()
        live_schema = self._query_live_schema(repo)
        return GRAPH_SCHEMA + "\n\n" + live_schema

    def _query_live_schema(self, repo: SchemaRepository) -> str:
        lines = ["## Live Database State"]

        all_labels = repo.get_node_labels()
        if all_labels:
            lines.append("\nNode labels in DB:")
            for label in sorted(all_labels):
                lines.append(f"  - {label}")

        rel_types = repo.get_relationship_types()
        if rel_types:
            lines.append("\nRelationship types in DB:")
            for rel_type in rel_types:
                lines.append(f"  - {rel_type}")

        return "\n".join(lines)


@llm.tool
async def get_schema() -> str:
    """Load the full graph schema — node types, relationship directions, edge properties, and Cypher query patterns. Call this before using query_graph or when you need to understand the graph structure."""
    concern = GetSchema()
    return await concern.resolve()
