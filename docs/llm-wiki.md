# LLM Wiki Mapping

This framework implements the same idea as [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — a persistent, compounding knowledge base that LLMs maintain and query rather than re-deriving understanding from raw sources on every call. The difference is substrate: where Karpathy's version uses interlinked markdown pages, ours uses a typed semantic graph with rule-constrained relationships.

## Concept Mapping

| LLM Wiki (Karpathy) | Dialectical Framework |
|---|---|
| Raw sources (immutable files) | Input nodes (content pointers, hashed) |
| Source summaries | `Input.digest` — living analytical understanding shaped by reasoning context |
| Wiki pages (interlinked, compounding) | Graph nodes: Statements, Perspectives, Wheels, Transformations, Synthesis |
| Links between pages | Graph edges with typed semantics: opposition, causality, transformation, synthesis |
| Schema (instructions for the LLM) | Generative rules + system prompts + app preambles |
| Index (catalog for navigation) | GRAPH_SCHEMA + `query_graph` tool |
| Ingest operation | Input → digest → thesis extraction → dialectical analysis |
| Query operation | Graph traversal, Cypher queries, `inspect_node` |
| Lint operation | Validation: modality balance, complementarity, control statements |

## What the Graph Encodes

The edges aren't just "relates to" — they carry formal dialectical meaning:

- **Opposition**: T/A pairs where each side's constructive development balances the other's excesses
- **Transformation**: How one pole's failure mode becomes another's constructive contribution (circular causality)
- **Synthesis**: Emergent properties from validated transformations operating across a wheel
- **Quality metrics**: Complementarity, modality balance, area — telling the LLM which paths are well-developed vs thin

This means an LLM querying the graph doesn't just get "what was concluded" — it gets the reasoning topology: what opposes what, where synthesis emerged, what remains unresolved.
