# Dialectical Framework

A reasoning framework for AI applications that need structured dialectical analysis. It curates a graph database through LLM-guided conversation, building up thesis-antithesis-synthesis structures from any domain.

The graph database **is** the state. Every interaction — extracting theses, finding oppositions, building wheels — writes semantic nodes and relationships into the graph. The framework is essentially a curation engine: an LLM orchestrator that progressively structures user input into dialectical knowledge graphs.

## How It Works

1. **Input** — User provides text, URLs, or ideas
2. **Analysis** — LLM extracts theses, finds antitheses, generates aspects (T+, T-, A+, A-)
3. **Graph curation** — Each insight is committed as nodes/relationships in the graph database
4. **Exploration** — Perspectives are combined into Cycles, arranged into Wheels, and Transformations reveal paths toward synthesis

The graph accumulates structured reasoning over time. Applications query it, visualize it, or build on it.

## Architecture

```
Host Application (Chainlit, API, CLI)
        │
        ▼
    Agent: Analyst · Explorer · Advisor (LLM + tools)
        │
        ▼
    Graph Database (Memgraph / Neo4j)
```

An **agent** is the entry point — a thin LLM orchestrator that manages a conversation with tools that read and write the graph. There are three (Analyst, Explorer, Advisor); each owns a tool set and a domain-neutral reasoning prompt. The host app controls persona (via the app preamble) and session identity (`sid`); the framework handles reasoning and graph curation. See [docs/agents.md](docs/agents.md).

### Core Graph Structure

At the heart is the **Dialectical Wheel** — a semantic graph where nodes are statements and edges encode dialectical relationships (opposition, complementarity, transformation).

| Structure | Role |
|-----------|------|
| **Statement** | Atomic unit of meaning |
| **Perspective** | T/A opposition with aspects (T+, T-, A+, A-) |
| **Cycle** | Ordered sequence of Perspectives |
| **Wheel** | Concrete T-A arrangement implementing a Cycle |
| **Transformation** | Action-Reflection paths between segments |
| **Synthesis** | Emergent S+/S- from the Wheel's circular causality |

Think of a Wheel as a pizza: segments are slices (T, T+, T-), Perspectives are half-pizzas (thesis + opposing antithesis), and Transitions are the cuts between slices.

| Simple | Detailed |
|--------|----------|
| ![Wheel](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/wheel-scheme.png) | ![Wheel](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/wheel-scheme2.png) |

## Why a Reasoning Graph

Most AI systems treat knowledge as flat context — dump text into the prompt and hope the LLM figures out the structure. The dialectical framework builds a **persistent reasoning graph** where the structure itself encodes how to think about a domain:

- **Oppositions are explicit.** The LLM doesn't need to discover tensions — they're mapped as T/A pairs with typed aspects showing where each side overreaches (T-, A-) and where it constructively balances the other (T+, A+).
- **Transformations encode causality.** Edges don't just connect — they show how one position's failure becomes another's strength. This is the circular causality that drives synthesis.
- **Quality is measurable.** Complementarity, modality balance, area metrics tell the LLM which reasoning paths are well-developed and which are thin — no guessing about confidence.
- **Knowledge compounds.** Each new perspective enters an existing graph of validated reasoning. The LLM builds on prior synthesis rather than re-deriving from scratch.

The result: an LLM with this graph in context doesn't just have facts about a topic — it has the intellectual terrain mapped. What opposes what, where balance was achieved, what assumptions remain untested, and where synthesis is possible.

This is the [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern realized as a semantic graph rather than a pile of markdown files — knowledge that is structured, rule-validated, and queryable by reasoning topology.

## Integration

The framework is designed as a drop-in reasoning engine for AI applications that need dialectical analysis — decision support, systems thinking, mediation, ethical modeling.

You build on three conversational agents — the main building blocks:

- **Analyst** — turns raw material into structured tensions, up to grouping them into a Nexus (Case-scoped).
- **Explorer** — takes one Nexus and works out its causal pathways and synthesis (Nexus-scoped).
- **Advisor** — runs the whole machine silently and returns pure counsel, with no framework vocabulary exposed (Case-scoped).

Analyst + Explorer are the structure-forward "graph navigator" experience; the Advisor is a chat-only product over the same graph. See [docs/agents.md](docs/agents.md) for full specs, tool lists, and the UX to build around each.

```python
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.settings import Settings
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.agents.advisor.advisor import Advisor

# Initialize once
DialecticalReasoning.setup(Settings.from_env())

# A Case owns the session id (sid); all graph writes are sid-scoped.
case = Case(); case.commit()

with scope(case.sid):
    advisor = Advisor(app_preamble="You are a systems thinking coach...")
    async for event in advisor.chat_stream("Analyze the tension between growth and sustainability"):
        # ThinkingDelta, TextDelta, ToolStart, ToolResult, ResponseComplete
        handle(event)
```

## Setup

### Requirements

- Python 3.11+
- Memgraph or Neo4j
- An LLM provider (OpenAI, Anthropic, or any LiteLLM-compatible)

### Install

```bash
poetry install
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DIALEXITY_DEFAULT_MODEL` | Model in provider/model format | `bedrock/anthropic.claude-sonnet-4-20250514-v1:0` |
| `DIALEXITY_GRAPH_DB_VENDOR` | Graph database | `memgraph` (default) or `neo4j` |
| `DIALEXITY_GRAPH_DB_HOST` | Database host | `127.0.0.1` |
| `DIALEXITY_GRAPH_DB_PORT` | Database port | `7687` |
| `DIALEXITY_THINKING_LEVEL` | Extended thinking budget | `medium`, `high`, `max` (optional) |

Store in `.env` or export in your environment.

### Run Tests

```bash
poetry run pytest              # All tests (LLM mocked)
poetry run pytest -m llm       # Only LLM-path tests (mocked)
poetry run pytest --real-llm   # Hit real LLM provider
```

## Built With

- [Mirascope](https://mirascope.com/) — LLM abstraction
- [GQLAlchemy](https://memgraph.com/docs/gqlalchemy) — Graph ORM
- [dependency-injector](https://python-dependency-injector.ets-labs.org/) — DI container

## Learn More

- [Agents: Analyst, Explorer, Advisor](docs/agents.md) — the building blocks, their tools, and the UX to build around them
- [Graph Data Model](docs/graph.md) · [Scoring & Metrics](docs/scoring.md) · [Graph Portability](docs/graph-portability.md)
- [Dialectical Wheels Overview](https://dialexity.com/blog/dialectical-wheels-for-systems-optimization/)
- [Dialectical Ethics](https://dialexity.com/blog/dialectical-ethics/)
- [Earlier Work](https://dialexity.com/blog/wp-content/uploads/2023/11/Moral-Wisdom-from-Ontology-1.pdf)