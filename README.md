# Dialectical Framework

**Make an LLM reason in oppositions, not averages.**

Ask a model a hard question and it tends to collapse the tension into one confident answer — or hedge with a bland "on one hand… on the other." This framework does neither. For every thesis it generates a genuine antithesis, maps precisely where each side overreaches (T-, A-) and where it constructively balances the other (T+, A+), and drives the pair toward a **synthesis** — not a compromise, but a new quality that emerges from their circular causality and that neither pole held alone.

The reasoning lives in a graph. Every move — surfacing a thesis, finding its opposition, developing its four aspects, arranging them into a **Wheel** — writes semantic, rule-validated nodes and edges into a graph database. The graph **is** the state: a persistent, compounding map of how a domain's tensions resolve, that any application can query, visualize, or build on.

And the synthesis is *earned*, not asserted. Where "think step by step" leaves rigor to chance, formal generative rules define what counts as valid: exactly one antithesis per thesis, modality kept in balance, and positive synthesis (S+) only when T-'s excess transforms into A+ and A-'s into T+. The structure enforces a discipline the prompt alone can't.

## Learn More
- [Structured Dialectics](https://dialexity.com/blog/structured-dialectics-consolidated-manuscript/) - the theory
- [Dialectical Wheels for Systems Optimization](https://dialexity.com/blog/dialectical-wheels-for-systems-optimization/)
- [Dialectical Ethics](https://dialexity.com/blog/dialectical-ethics/)


## How It Works

1. **Input** — text, URLs, or raw ideas from any domain
2. **Analysis** — extract the theses, find each one's true antithesis, develop the four aspects (T+, T-, A+, A-) that say where each side helps and where it overreaches
3. **Graph curation** — commit every insight as content-addressed, rule-validated nodes and edges — nothing is stored until it holds up
4. **Exploration** — combine perspectives into Cycles, arrange them into Wheels, and trace the Transformations whose circular causality yields synthesis

Each pass leaves the graph richer than it found it: new tensions enter an existing web of validated reasoning, so understanding compounds instead of resetting every prompt.

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

An **agent** is the entry point — a thin LLM orchestrator that manages a conversation with tools that read and write the graph. There are three (Analyst, Explorer, Advisor); each owns a tool set and a domain-neutral reasoning prompt. The host app controls persona (via the app preamble) and scope identity (`sid`); the framework handles reasoning and graph curation. See [docs/agents.md](docs/agents.md).

### Docs
- [Agents: Analyst, Explorer, Advisor](docs/agents.md) — the building blocks, their tools, and the UX to build around them
- [Graph Data Model](docs/graph.md)
- [Scoring & Metrics](docs/scoring.md)

## Why a Reasoning Graph

Most AI systems treat knowledge as flat context — dump text into the prompt and hope the LLM figures out the structure. The dialectical framework builds a **persistent reasoning graph** where the structure itself encodes how to think about a domain:

- **Oppositions are explicit.** The LLM doesn't rediscover the tensions on every call — they persist as typed T/A pairs, so reasoning starts from a mapped conflict instead of a blank page.
- **Transformations encode causality.** Edges don't just connect — they show how one position's failure becomes another's strength. This is the circular causality that drives synthesis.
- **Quality is measurable.** Complementarity, modality balance, area metrics tell the LLM which reasoning paths are well-developed and which are thin — no guessing about confidence.
- **Knowledge compounds.** Each new perspective enters an existing graph of validated reasoning. The LLM builds on prior synthesis rather than re-deriving from scratch.

The result: an LLM with this graph in context doesn't just have facts about a topic — it has the intellectual terrain mapped. What opposes what, where balance was achieved, what assumptions remain untested, and where synthesis is possible.

This is the [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern realized as a semantic graph rather than a pile of markdown files — knowledge that is structured, rule-validated, and queryable by reasoning topology.

| Simple | Detailed |
|--------|----------|
| ![Wheel](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/wheel-scheme.png) | ![Wheel](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/wheel-scheme2.png) |

## Core Graph Structure

It's all one graph. **Statements** are the atoms; typed edges carry the dialectical relationships — opposition, complementarity, transformation — and each structure below composes the ones above it into progressively richer reasoning, culminating in the **Dialectical Wheel**.

| Structure | Role |
|-----------|------|
| **Statement** | Atomic unit of meaning — a thesis, position, or claim |
| **Polarity** | A single T↔A tension (thesis vs. antithesis); reusable across perspectives |
| **Perspective** | A full tetrad — a Polarity developed with its four aspects (T+, T-, A+, A-) |
| **Nexus** | A working set of Perspectives grouped for exploration |
| **Cycle** | An ordered sequence of Perspectives — which tension drives which |
| **Wheel** | A concrete circular arrangement of a Cycle, with the edges between components |
| **Transition** | A directed edge between two components — one step around the Wheel |
| **Transformation** | The Action-Reflection paths on an edge that turn one pole's excess into the other's strength |
| **Synthesis** | The emergent S+/S- arising from the whole Wheel's circular causality |

Picture the Wheel as a pizza sliced into segments: each **segment** bundles a component with its plus and minus (e.g. T, T+, T-), a **Perspective** joins a thesis segment with the antithesis segment directly across from it, and **Transitions** are the arrows running segment to segment around the rim.

## Integration

Wherever the answer is a tension rather than a fact, this drops in as the reasoning engine: decision support that weighs both sides, systems thinking, mediation between opposed positions, ethical modeling. You wire it into your app through three conversational agents — the main building blocks:

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

# A Case owns the scope id (sid); all graph writes are sid-scoped.
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
- An LLM provider (OpenAI, Anthropic, or Bedrock via a custom Mirascope provider)

### Install

```bash
poetry install
cp .env.example .env   # then fill in the values (see .env.example for details)
```

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