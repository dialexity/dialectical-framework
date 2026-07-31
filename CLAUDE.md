# CLAUDE.md - AI Co-Developer Guide

## Collaboration Style

Give honest opinions with clear tradeoffs — not agreement for the sake of agreement. State what you actually think is the better approach and why. If both options are defensible, say so directly.

## What is the Dialectical Framework?

A semantic graph system for dialectical reasoning — modeling thesis-antithesis-synthesis dynamics as graph structures. Used for systems analysis, wisdom mining, and ethical modeling.

### Theoretical Foundation (Generative Rules)

The framework implements **Structured Dialectics** (theory papers in `docs/r-n-d/`, gitignored). The full claim-by-claim theory→code mapping with statuses lives in `docs/theory/` (maintained by `/df-sync-theory`) — consult it before implementing anything theory-adjacent. The rules below are the promoted essentials:

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

### Scoring & Metrics (see docs/scoring.md for full reference)

**Ks** (complementarity toward synthesis) = `(K_T + K_A) / 2`. Computed property, never stored — only K_T and K_A are persisted on `AspectRelationship` edges.

**Tetrad quality metrics (on Perspective):**
- `area` = Ks(T+) + Ks(A+) - Ks(T-) - Ks(A-) — higher = better differentiation. The theory's canonical name is **SP (Synthesis Potential)** — same formula; treat SP ≡ area when reading the papers.
- `rectangularity` = [Ks(T+)-Ks(A+)]² + [Ks(T-)-Ks(A-)]² — lower = better balance. Deliberately diverges from the paper's (rejected) linear form — see `docs/theory/scoring.md` before "fixing" either way.
- Empirical thresholds: diff ≥ 0.1, |diff_t − diff_a| ≤ 0.15 (side balance), Ks(+) > 0.4, Ks(-) < 0.6
- Theory metrics NOT implemented (don't let prompts claim them): DV, MMI, PSI, PC — see `docs/theory/scoring.md`.

**HS (Heuristic Similarity):** T=1.0 (always, defines apex), A=LLM-computed, Aspects=LLM-computed, Ac+/Re+=LLM-computed, Ac/Re/Ac-/Re-=None.

**Validation, in practice:** Generated tetrads are NOT blocked on a validation pass — the generation prompt enforces tetrad structure and the live `AnalysisPipeline` gates only on HS (`_rank_polarities`, `HS_THRESHOLD=0.7`). `PerspectiveValidation` (CC + empirical inequalities) runs LIVE post-commit in `ExpandPolarity._validate_and_flag` as a non-blocking flag: the verdict lands on `Perspective.validation` ("passed" / "failed: reasons" / None=unvalidated or inconclusive), rendered by `dialectical_context`, `present_analysis` and `inspect_node`; prompts deprioritize failed perspectives rather than the graph dropping them. Fail-soft and sequential (CSC commits Estimation/Rationale nodes — no concurrent graph writes). The other live post-hoc check is `edit_perspective._validate_tetrad_coherence`, which runs CC + diagonal contradiction directly (via `ControlStatementsCheck` + `DiagonalOppositionsCheck`, not `PerspectiveValidation`) on user-edited tetrads — the extra diagonal LLM call is only needed when generation-prompt constraints are bypassed. SIMPLE-path antitheses (hardcoded HS=1.0) render as "mechanical opposition — HS not evaluated" in the context dump, never as a numeric score.

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

**Cycle vs Wheel:** Cycle = ordered T-causality sequence (which thesis causes which). Wheel = full circular TA-arrangement with transitions. `generate_compatible_sequences` takes a Cycle's PP ordering as constraint, then places both T and A components respecting diagonal symmetry (T_i opposite A_i). Different Cycles (e.g., [PP1,PP2] vs [PP2,PP1]) produce Wheel arrangements that are rotations of each other — same directed circle, different starting point. Since Wheels are rotation-invariant (`WheelRepository.find_by_component_sequence`), these sibling Cycles share the same Wheel nodes. All scoped by `sid` — no cross-Case or cross-Nexus sharing.

**Case flow:** Case → Input → Ideas → Statements
**Exploration flow:** Perspectives → Nexus → Cycles → Wheels

See `docs/graph.md` for full data model (positions, transformations, cardinality, layers, intent levels, discarding/editing rules).

### Synthesis Architecture (Wheel-Level)

Synthesis (S+/S-) is a wheel-level phenomenon. One wheel → one S+/S-.

**Circular causality within Transformations:** Each Transformation already encodes both spiral directions — Ac+ (its own edge direction) and Re+ (the opposite edge's direction). A Transformation IS a complete circular causality statement.

**Scaling from 1-PP to N-PP:**
- 1-PP wheel: 2 edges, 1 edge pair, 2 Transformations (Ac/Re roles swap between them)
- 2-PP wheel: 4 edges, 2 edge pairs, 4 Transformations — within one wheel, opposite-edge Transformations have Ac+/Re+ role-swapped (E1's Ac+ = E3's Re+, etc.)
- N-PP wheel: 2N edges, N edge pairs, 2N Transformations

**Discrete spiral:** Wheel edges form a directed circle where each step transforms the minus of one segment into the plus of the next (T1-→A2+→T2-→A1+→...). S+ emerges from ALL Transformations operating simultaneously along the spiral.

**BuildWheels is purely structural:** Always builds all valid Cycle/Wheel combinations from the Nexus's attached Perspectives and estimates them (layer 2+). Never generates transformations — those are triggered separately via `ExploreTransformations` (user-initiated or headless pipeline), even for layer-1 wheels.

**OPPOSITE_DIRECTION** exists on both Cycle and Wheel (detected via `_is_circular_reverse`). Cycle opposites: reversed causality ordering within the same PP set (only at layer 3+; layer-2 cycles have no distinct reverse). Wheel opposites: reversed circular component sequence — at layer 2 the two wheels within the same cycle are each other's opposite; at layer 3+ wheel opposites live across opposite-direction cycles (1:1 mapping). Each opposite produces its own independent synthesis.

**Nexus grouping rule:** Prefer perspectives from different polarities (genuine synthesis with opponents). Same-polarity perspectives in a nexus only produce "angle shifts" within the same opposition.

**Max wheel layer (`settings.max_wheel_layer`, default 4):** `PerspectiveCombination` only builds layers up to this cap regardless of nexus size. A nexus can hold any number of perspectives, but combinatorial explosion is bounded by this setting. Override via `DIALEXITY_MAX_WHEEL_LAYER` env var or DI settings override.

**Combinatorial growth (layer = PP count in combination):**
- Layer generation: `C(N, k)` PP combinations × `max(1, (k-1)!)` cycles × `W(k)` wheels per cycle
- W(1)=1, W(2)=2, W(3)=4, W(4)=8 (arrangements from `generate_compatible_sequences`)
- Totals: 1PP→1C/1W, 2PP→3C/4W, 3PP→8C/17W, 4PP→24C/96W

### Structural vs Analytical Layers

- **Structural** (immutable after commit): Merkle-tree backbone. Containers use `save() → add members → commit()`.
- **Analytical** (mutable anytime): Rationale, Estimation, Critique, Synthesis, ac_re.

### Discarding Nodes

- `discarded: Optional[str]` field on Statement/Perspective — soft-marks as excluded from active queries (node stays in graph).
- `discard_uncommitted()` on PerspectiveRepository — physically deletes uncommitted nodes.
- The `discard` tool unifies both: uncommitted → deleted, committed → soft-discarded.

### Shared Rendering (`graph/rendering.py`)

`build_pp_index(nexus)` is the canonical source of perspective indices. Both `dialectical_context` (compact dump) and `inspect_node` (detail view) use it so T1 always means the same perspective. Indices are stable: assigned over the full `nexus.perspectives.all()` ordering (including discarded), so gaps appear rather than re-numbering. Helper functions: `component_alias`, `format_edge_label`, `format_spiral`, `find_nexus_for_*`.

### Advisor Tool Constraints

Advisor has `discard` (to retract a framing the user rejects) but NO edit tool. When the user rejects a framing, the unscoped Advisor silently discards the perspective; the counsel-mode (nexus-pinned) head confirms first for exploration members (consent contract) — fresh own anchors need no ceremony. Uncommitted → deleted, committed → soft-discarded; to drop a claim entirely, discard the perspective first, then its statement (a statement still used by a live perspective won't discard, and discarding a perspective never cascades to its shared statements). If the tension needs re-framing rather than removal, it `anchor`s the new version. It never edits aspects in place. Tools split by what the LLM knows at call time:
- `ingest` — bulk discovery from material → standalone perspectives (composes AnalysisPipeline)
- `anchor` — plant a specific T/A tension → standalone perspective (composes IntroducePolarity + ExpandPolarity)
- `explore` — group perspectives into nexus + pathways + synthesis (composes CreateNexus/ExpandNexus + ExplorationPipeline + GenerateSynthesis). LAZY: builds+ranks ALL wheels, deep-generates only the top-plausibility one (`EXPLORE_DEEP_WHEELS = 1`, fixed policy); rest reported as `shallow_wheel_hashes`. Weaves at most `settings.advisor_max_perspectives_per_exploration` per call (excess deferred, reported, never dropped).
- `deepen` — develop a shallow wheel on demand (composes ExploreTransformations + GenerateSynthesis, synthesis always). The escape from explore's budget: called when the user's lived reality picks a non-top arrangement. Scoped variant guards wheel-membership in code.
- `sync` — re-read graph state (composes DialecticalContext)
- `discard`, `inspect_node`, `read_digest` — graph curation and detail reads (shared orchestrator tools)

**ExpandPolarity creates `count` new perspectives per call (default 1).** Generated sequentially, each using `not_like_these` (existing + already-generated-this-call) for diversity. Pass `count > 1` to build alternative tetrads in one call; a pre-existing partial counts toward `count`.

### User-Facing Vocabulary is App-Layer

The graph model uses universal terms (Statement, Polarity, Perspective, T+/T-/A+/A-). User-facing vocabulary is contextual — not a fixed translation table — and depends on who the user is. Defined in `agents/apps.py` (`NAVIGATOR_APP`, `NAVIGATOR_ADVANCED_MODE_APP`, plus advisory personas) and injected via `app_preamble` in the Analyst/Explorer/Advisor constructor. System prompts handle tool selection/workflow only; they never dictate presentation vocabulary or app-UI behavioral constraints (e.g., viewport scope). Both go in app preambles.

**Advisor preamble/engine split:** Advisor's system prompt is a domain-neutral dialectical engine (how to use graph output for counsel). Persona (warm counselor, sharp strategist, coach) comes entirely from the app preamble. This means the same engine works for personal counseling, CEO strategy, brand marketing, etc. See methodology mappings in `apps.py` docstring.

### Agent Ownership

- **Analyst** = everything up to and including nexus creation (inputs → statements → polarities → perspectives → `create_nexus` as handoff)
- **Explorer** = everything after nexus (nexus-scoped: cycles → wheels → transformations → synthesis). Constructed with `nexus_hash`. Carries `create_dx_input` (shared orchestrator tool) to START the round-trip: capture a Transition insight as a dx:// Case Input → Analyst develops it → `expand_nexus` weaves back.
- **Advisor** = pure-conversation agent where framework runs silently. Composes both pipelines via internal tools: `ingest`, `anchor`, `explore`, `deepen`, `sync` (plus shared `inspect_node`, `read_digest`, `discard`). No framework terminology exposed to user. App preamble defines persona; system prompt is domain-neutral dialectical engine (a FUNCTION `system_prompt(tool_names, scoped_nexus_hash)` — tool docs render only for wired tools).
- **Advisor(nexus_hash=...)** = counsel mode of an Explorer↔Advisor session toggle (NOT a standalone variant): host hands `messages` + `nexus_hash` between heads; preamble pairing `NAVIGATOR_ADVANCED_MODE_APP` ↔ `EXPLORATION_ADVISOR_APP` (both composed on `NAVIGATOR_APP`). Nexus pin enforced by tool closures (`advisor/tools/scoped.py`), not prompt. See `docs/agents.md` Handoffs.
- `create_nexus` lives in Analyst only — it's the handoff moment. Explorer never creates nexuses.

### Advisor Runtime Budgets (settings, Advisor-only)

Four knobs bound the silent Advisor (`settings.advisor_*`, env `DIALEXITY_ADVISOR_*`; Navigator agents ignore all): `advisor_polarity_quality_min_hs` (0.5) / `advisor_perspective_quality_min_area` (0.3) — standalone perspectives below the floor (or failed validation) are SUPPRESSED from the context dump with a count line (nexus members exempt; unscored never suppressed); `advisor_wheel_quality_top_plausible` (3) — wheels per cycle in the unscoped dump (counsel-mode dumps exempt — user-built explorations render in full); `advisor_max_perspectives_per_exploration` (2) — per-explore-call weave cap (excess deferred+reported; bounds turn latency, orthogonal to `max_wheel_layer` which bounds structure size). The Advisor's prioritization prompt says "pre-pruned, rank within it" — changing floors requires reconciling it (`TestContextDumpPrePruned`).

**Policy is not config.** Two knobs were deleted after review (eager-deepen flag, synthesis toggle): if no deployment would ever set a value, encode it as a module constant with the rationale in a comment (`EXPLORE_DEEP_WHEELS = 1` in `advisor/tools/explore.py`). Audit test for new settings: "who sets this, ever, to what?"

---

## Development Commands

Poetry project (Python 3.11+):

```
docker compose -f docker-compose.test.yml up -d  # start Memgraph (required for graph tests)
poetry run pytest                    # all tests, LLM mocked
poetry run pytest --real-llm         # only LLM tests with real provider
poetry run pytest -m llm             # only LLM-path tests (mocked)
poetry run pytest tests/path/test_x.py::test_name  # single test
poetry run black src/ tests/         # format
poetry run isort src/ tests/         # sort imports
poetry run autoflake --in-place --remove-all-unused-imports --recursive src/ tests/
```

**black/isort are NOT enforced** (no pre-commit/CI) and most of the tree is non-conforming. Running `black <file>` after a small edit reformats the WHOLE file (import-wrapping, line-wraps), bloating the diff with unrelated churn. For a targeted change, hand-format only your own lines; don't run black on the file.

---

## Technology Stack

- **Graph DB**: Memgraph or Neo4j (via GQLAlchemy)
  - GQLAlchemy hardcodes `autocommit = True` — no multi-statement transactions available through the ORM. Each `save_node()`/`save_relationship()` is its own committed transaction. Application-level `saved_at` tracking (on `IncrementalBuildMixin`) provides the atomicity signal instead.
- **DI**: dependency-injector
- **Validation**: Pydantic v1 *style* (v1-compatible `Field`/validators), but the installed lib is **v2** — for introspection use `Model.model_fields[name].description`, not `__fields__`/`.field_info`.
- **LLM**: Mirascope (OpenAI, Anthropic, Bedrock via custom provider)

---

## Where Things Live

| Purpose | Location |
|---------|----------|
| DI Container (START HERE) | `dialectical_reasoning.py` |
| Shared Claude skills (df-*) | `.claude/skills/df-<name>/SKILL.md` (committed) — convention: `disable-model-invocation: true` + scoped `allowed-tools`; mirror an existing sibling. DB lifecycle lives in `/df-memgraph` (start/stop/restart/status/logs/clear/wipe) |
| Personal Claude skills (local-*) | `.claude/skills/local-*/` (gitignored) |

**After renaming/moving a skill directory:** re-run `/reload-skills` — the session's skill list doesn't auto-refresh, so a stale name/description can persist for the rest of the conversation.
| Graph nodes | `graph/nodes/*.py` |
| Relationships | `graph/relationships/*.py` |
| Relationship API | `graph/relationship_manager.py` |
| Repositories (data access) | `graph/repositories/` |
| Graph mixins | `graph/mixins/` |
| Concerns (standalone services) | `concerns/` |
| Shared scoring vocabulary (aspect defs, HS/complementarity/insight/proactiveness scales) | `concerns/scoring_scales.py`, `concerns/ac_re_taxonomy.py` (pure constants, no service class) |
| Analyst (conversational, Case-scoped) | `agents/analyst/analyst.py` |
| Explorer (conversational, Nexus-scoped) | `agents/explorer/explorer.py` |
| Advisor (conversational, silent framework) | `agents/advisor/advisor.py` |
| Advisory persona preambles | `agents/apps.py` (COUNSELOR_APP, STRATEGIC_ADVISOR_APP, COACH_APP, MEDIATOR_APP, SPARRING_PARTNER_APP) |
| Dialectical context (graph→natural language) | `concerns/dialectical_context.py` |
| App preambles (vocabulary/framing) | `agents/apps.py` |
| Shared agent tools | `agents/orchestrator/tools/` |
| Agent skills/tools | `agents/{analyst,explorer,advisor}/` |
| LLM abstraction | `utils/use_brain.py` |
| Bedrock provider | `utils/bedrock_provider.py` |
| Utilities | `utils/` |
| Input context (digest→prompt) | `utils/input_context.py` |
| LLM Wiki mapping docs | `docs/llm-wiki.md` |
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

**Committed-only rule:** Repository listing queries (find_all, find_unconnected, get_vocabulary) must include `AND n.hash IS NOT NULL` to exclude uncommitted nodes. `GRAPH_SCHEMA` instructs the LLM to do the same in `query_graph`.

**Allowed exceptions:** `dialectical_reasoning.py` (schema init), `relationship_manager.py`, `estimation_manager.py`, `query_graph.py` (LLM read-only Cypher).

### Truncation Rules for Node Text

`__str__` on graph nodes is LLM-visible (used by `present_analysis`, `inspect_node`, format strings). Must show full text — never truncate. `__repr__` is debug-only and may truncate freely. Internal LLM prompts (dedup, query_graph results, report summaries) may truncate since hashes serve as identifiers; agent system prompts instruct the LLM to use `inspect_node` for exact text.

### Tool Parameter Clarity: No Double-Duty Strings

Tool parameters must not serve as both "literal value" AND "instructions for an inner LLM to interpret." If the Analyst agent already decided *what operation* to perform (by choosing the tool), the tool signature should reflect that decision unambiguously. If a tool needs two modes, split it into two tools rather than adding an `intent` string that an inner LLM must re-interpret.

Reference: `anchor_theses` (literal statements) vs `surface_theses` (extraction instructions).

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

**Uncommitted node safety (`saved_at`):** `IncrementalBuildMixin.save()` sets `saved_at` timestamp; `commit()` clears it. A node with `saved_at != NULL` and `hash == NULL` is either actively building or abandoned garbage (if stale). All listing/discovery queries MUST filter `WHERE n.hash IS NOT NULL` to exclude uncommitted nodes from reasoning pipelines. Cleanup: `scripts/cleanup_stale_nodes.py --max-age 86400`.

**Event reporting:** When a node's `commit()` creates relationships internally (e.g., `Polarity.commit()` creates T/A edges), the calling skill must emit `relationship_created` events for each edge — `commit()` itself does not emit SSE events.

**Container node event lifecycle (save-then-commit):** Container nodes (Perspective, Wheel, Transformation, Synthesis, Ideas) that use `save()` → relationships → `commit()` must emit split events: `report.node_created(node)` after `save()` (db_id set, hash null), then `report.node_committed(node)` after `commit()` (hash now set). Nodes that do atomic `commit()` without prior `save()` emit a single `node_created` with both set.

### Relationship Direction

`RelationshipTo` and `RelationshipFrom` define the SAME edge from different perspectives. Convention: Child→Parent edges use `RelationshipTo` on child.

```python
class Perspective(AssessableEntity):
    nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")  # PP→Nexus

class Nexus(AssessableEntity):
    perspectives = RelationshipFrom("Perspective", "BELONGS_TO_NEXUS")  # Same edge, reverse view
```

**Event direction for `relationship_created`:** `from_node`/`to_node` must match the actual DB edge direction, NOT the owner's perspective. For `RelationshipFrom` (incoming) managers, the DB edge is `(target)-[REL]->(owner)`, so: `report.relationship_created(manager, target, owner)`. Correct example: `relationship_created(polarity.t, thesis_stmt, polarity)` — Statement is from_node because the DB edge is `(Statement)-[T]->(Polarity)`.

**Idempotent connect:** `RelationshipManager.connect()` only deduplicates for `direction="any"` (symmetric) relationships. Directed relationships (`RelationshipTo`/`RelationshipFrom`) will silently create duplicate edges on repeated calls. Callers must check `manager.all()` before connecting if re-invocation is possible.

### Scope (sid)

All nodes share `sid` from their Case. Enforced at connect time. Use `with scope(case.sid):` to set context.

### Input Digest (Living Understanding)

`Input.digest`: mutable field (excluded from hash) storing LLM-generated understanding of a source. Populated by `SourceDigest` concern. Short content (<1500 chars) skips LLM — used as its own digest.

**Consumption:** Skills use `input_context()` from `utils/input_context.py` — returns digests in `<Input id="{hash}">` tags, falls back to resolved content when digest is None. `surface_theses` is the exception (needs raw content for extraction, uses digest for previews only).

**Tools:** `read_digest` | `read_input` | `digest_input` — available to both Analyst and Explorer.

**Responsibility:** Whoever adds the input, digests it. Framework provides building blocks; the caller (agent or app) sequences them.

**Multimodal seam (Option A of #35):** `InputResolver` has two methods — `resolve() -> str` (text-only; safe to f-string interpolate — used by `input_context`/`resolve_all`/`surface_theses`/`read_input`) and `resolve_native() -> UserContent` (opt-in, defaults to delegating `resolve()`). `SourceDigest` is the *sole* `resolve_native` consumer: it's the one multimodal step, running a vision pass over native `Image`/`Document` parts (base64 image/PDF `data:` URIs) and emitting a text digest, so everything downstream stays text. Never widen `resolve()` to return media — text callers would silently stringify it. `ConversationFacilitator.submit`/`submit_stream` accept `UserContent` (superset of `str`).

### Antithesis Persistence Checklist

When calling `AntithesisClassification`, the caller must persist Mode/Arousal via `EstimationManager.upsert_estimation()`. The concern itself does NOT create DB nodes — it only returns the result. `AntithesisExtraction` handles this internally; `AntithesisClassification` does not.

### Model Provenance is Rationale-Only

Only `Rationale.agent` tracks which LLM model generated content (`<provider>/<model>` format, auto-populated from settings). Other nodes (Statement, Estimation, Perspective, etc.) trace provenance indirectly through their associated Rationale. This is intentional — not an oversight to "fix" by adding `agent` to more node types.

### Statement Generation Conventions

- Word limit: always use `self.settings.component_length` (headlines, ~7) or `self.settings.transition_length` (fuller transition statements, ~15) via `SettingsAware` — never hardcode. Pydantic `Field` descriptions can't interpolate `self.settings`, so keep length wording qualitative there and put the numeric limit in the method prompt body.
- **`component_length` is enforced at generation/extraction time, not by `StatementClassification`.** `thesis_extraction`, `aspect_generation`, `synthesis_generation`, etc. clamp their output; `StatementClassification` sits downstream and echoes text verbatim. The `anchor` path has no extraction step, so raw agent prose would be stored as-is — the `StatementHeadline` concern (`concerns/statement_headline.py`) closes that gap. Both anchor legs (`IntroducePolarity._resolve_statement`, `AnchorTheses._classify_and_create`) run it in parallel with classification (`asyncio.gather`, no added latency): classification reads the *full* text for taxonomy anchoring; only the stored `Statement.text` becomes the headline. Text already ≤ `component_length` words short-circuits with no LLM call. `edit_perspective` deliberately does NOT condense — user-typed exact wording must survive.
- Analytical artifacts (synthesis, transformations) scope uniqueness via meaning field: `meaning=f"synthesis:positive:{wheel.hash}"` prevents unintended cross-context dedup while `commit()` handles exact-match dedup automatically.

### Classification → HS Chain (Critical Invariant)

`StatementClassification` (SIMPLE vs COMPLEX) determines the entire antithesis path:
- **SIMPLE** → `AntithesisExtraction._process_simple_thesis()` → mechanical negation, HS hardcoded to 1.0, no taxonomy contextualization
- **COMPLEX** → `AntithesisExtraction._process_complex_thesis()` → LLM-evaluated antithesis taxonomy, LLM-scored HS (0.0–1.0)

The Polarity HS (displayed in UI, used by `AnalysisPipeline._rank_polarities()` quality gate at `HS_THRESHOLD=0.7`) comes from the A-relationship's `heuristic_similarity`. Misclassifying COMPLEX theses as SIMPLE inflates all polarities to HS=1.0, defeating quality differentiation. The classification prompt's SIMPLE/COMPLEX boundary is the most leverage-dense prompt in the extraction pipeline.

### Observability (Langfuse)

- `ReasonableConcern.__init_subclass__` auto-wraps every concern's `resolve()` with `@observe` — but only creates spans when an active Langfuse trace exists (no orphan traces from non-LLM concerns).
- `use_brain` decorator creates generation spans named via `method.__qualname__` with `capture_input=False` — input is set by `_trace_generation` via `update_current_generation`.
- `ConversationFacilitator._strip_unsupported_input_fields()` strips output-only API fields (e.g., `caller`) from raw_message before replaying — workaround for Mirascope passthrough bug.
- Mirascope `BaseResponse`: use `response.messages[:-1]` for input messages — `response.input_messages` does NOT exist.
- Tests use `@traced` from conftest (not bare `@observe()`) for reliable Langfuse trace naming on class methods.
- **`@traced` serializes the decorated function's args as span input** — never put it on a test taking `monkeypatch` or other cyclic fixture objects; Langfuse's serializer recurses forever and the test HANGS (not fails). Existing `@traced` tests take only `self`. Diagnose hangs with `pytest -o faulthandler_timeout=25`.

### Concurrency & Rate Limiting

Optional concurrency semaphore in `utils/concurrency.py` (env `DIALEXITY_MAX_CONCURRENT_LLM_CALLS`, default disabled). Set to a positive integer to cap concurrent LLM calls as runaway protection. Disabled (0 or unset) = no limit, rely purely on rate-limit retry. Applied inside `use_brain` — streaming (`raw_call=True`) excluded.

Rate-limit retry (429/ThrottlingException) also lives in `use_brain`: 10s base backoff, 2× up to 60s cap, max 10 attempts. Log message includes the error string for diagnosis. ParseError retry: 10s base, 2× up to 120s.

**The `use_brain` retry loop is hand-rolled by design — do NOT replace it with Mirascope's native `llm.retry`/`RetryConfig`.** It intentionally does what native retry can't express as one config: separate backoff curves for ParseError (120s cap) vs rate limits (60s cap), per-attempt `llm_concurrency_slot()` re-acquisition, per-attempt Langfuse `_trace_generation`, and string-based Bedrock throttle detection (`"ThrottlingException"`) beyond the SDK's 429→`RateLimitError` mapping. Native retry (added 2.2.0) would have to nest inside the wrapper, not replace it.

**Parallelization points:** `ExplorationPipeline` runs wheels concurrently. `ExploreTransformations` parallelizes edge pairs, Phase 1 edges, Phase 2 candidates, and audits. `AnalysisPipeline` already parallelizes `expand_polarities` and `find_polarities`. Graph writes stay sequential after gather.

**Pattern:** Always `asyncio.gather` the LLM work, collect results, then write graph nodes sequentially in a loop. Never call `_create_transformation` or similar graph-writing code inside a gathered task — GQLAlchemy is not concurrency-safe.

---

## Tool Pattern (Mirascope)

Two-layer: `ReasonableConcern[T]` (implementation) + `@llm.tool` function (LLM-facing interface).

**Hierarchy (increasing scope):**
- **Concern** = standalone service, single responsibility → lives in `concerns/`. Public API — reusable across tools, skills, and pipelines.
- **Tool** = `@llm.tool` function + optional internal helper class → lives in `agents/{phase}/tools/`. Helper classes in tool files may extend `ReasonableConcern` (for `self._report`), but they are **internal to that tool** — not public API, not importable by other modules.
- **Skill** = orchestrates multiple concerns, has reasoning responsibility → lives in `agents/{phase}/skills/`
- **Agent** = top-level conversational coordinator, owns a tool set → lives in `agents/{phase}/`

**Public vs internal:** Location is the signal. `concerns/SourceDigest` is a reusable service anyone can import. `tools/present_analysis.PresentAnalysis` is internal wiring for that tool — it exists to get `self._report` and format output, not to be reused elsewhere.

**When to promote:** If a tool-file helper class gets imported by tests or other modules directly (programmatic usage), move it to `concerns/`. The litmus test: does anything outside the tool file call `Concern().resolve(...)`? If yes → `concerns/`.

Only `@llm.tool` functions go into tool lists. `ReasonableConcern` classes are never passed to Mirascope directly.

**Tool return convention:** Mutating tools return `str(concern.report)` (JSON with effects, artifacts, hashes for the LLM). Read-only tools (inspect_node, read_digest, sync) return `await concern.resolve()` directly — the content is the useful output.

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

**`AnalysisPipeline` does NOT merge sub-skill reports.** `analyze` (and the Advisor's `ingest`) return `str(pipeline.report)`, but the pipeline never `.merge()`s its `find_polarities`/`expand_polarities` sub-reports — those live on the discarded `AnalysisResult.reports`. Anything the agent must see (e.g. HS scores, quality signals) has to be placed on the pipeline's OWN `self._report.artifacts` (see `polarity_quality`). Report artifacts reach only the LLM (via `__str__`), never the frontend — the event bus publishes `Effect`s only.

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
Mock brain returns **identical** DTOs every call — to test diversity/dedup logic (distinct outputs across calls), `monkeypatch` the concern's `resolve` directly instead.

**Mock brain auto-fills every field, so response-model *shape* changes are invisible to the mocked suite.** Restructuring a Mirascope `response_model` (nesting DTOs, adding required fields) can pass all mocked tests while the real LLM drops a branch → `ParseError`. Verify any DTO-shape change with `--real-llm`. Deep nesting is the usual culprit; prefer flatter schemas.

**One graph-test run at a time.** The autouse `cleanup_graph_db` fixture `DETACH DELETE`s before/after each test, so concurrent pytest processes against the same Memgraph deadlock. If a run is `pkill -9`'d mid-test, the stuck lock persists — clear it with `docker compose -f docker-compose.test.yml restart`.

**Test Memgraph has a persistent volume (`mg_lib`).** `restart` clears a stuck lock but NOT the data. Stale nodes cause spurious failures in unrelated tests (e.g. `find_by_hash("abc")` matching a leftover `Transition`). To confirm a failure is pre-existing vs. caused by your change, `git stash` and re-run; to truly wipe, `docker compose -f docker-compose.test.yml down -v`.

**DB-free tests:** Override autouse fixtures `cleanup_graph_db` and `cleanup_test_graph_data` with empty yields.

**Ad-hoc verification scripts must live under `tests/`.** DI wiring (dependency-injector `Provide` resolution) and the mock-brain autouse fixtures come from `tests/conftest.py`, which pytest only applies to files in the tests tree. A pytest file run from `/tmp` fails with `'Provide' object has no attribute 'save_node'` (unresolved `Provide` sentinel). Drop the file in `tests/` to get full wiring.

---

## Environment Configuration

`.env.example` is the source of truth for all env vars (copy to `.env`). Every var is
read in `settings.py` (`Settings.from_env`) except `DIALEXITY_MAX_CONCURRENT_LLM_CALLS`
(`utils/concurrency.py`) and `DIALEXITY_TEST_CLEANUP` (`tests/conftest.py`).

**File convention:** uncommented vars are REQUIRED; commented vars are optional and the
value shown IS the code default (uncommenting unchanged is a no-op). When you change a
default in `settings.py`/`concurrency.py`, update the commented value in `.env.example`
in the same change — the file must never show a stale default.

`Settings.from_partial` merges with `exclude_unset` — only explicitly-set fields override
env values; a field at its Pydantic default never stomps an env-configured one.

Only required: `DIALEXITY_DEFAULT_MODEL` — single combined `provider/model` string
(e.g. `bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0`) — plus credentials for
the named provider (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or AWS creds for `bedrock/`).

---

## Prompt Engineering

The project is infused with LLM prompts at multiple layers. Use `/df-review-reasoning-layer` when writing or editing prompts — it reviews at three altitudes (isolated prompt → assembled context → whole reasoning chain) and carries the full methodology, checklist, drift-hotspot catalog, and cross-agent parity map (`.claude/skills/df-review-reasoning-layer/reference/systemic-map.md`).

**`df-review-reasoning-layer` is a LIVING skill — keep it in lockstep with the framework.** It only stays powerful if it mirrors the current system. Whenever you change something it maps, update the skill AND its reference map in the same change:
- New/moved/renamed prompt site → update the location table (below) and the skill's Altitude-2 assembly maps + Altitude-3 inventory.
- New or changed shared constant/scale (`scoring_scales.py`, `ac_re_taxonomy.py`, `SYSTEMIC_TAXONOMY`) → update the theory-ownership table and drift-hotspot catalog; if you *de-duplicate* a drift site (make prose derive from the constant), remove it from the catalog.
- Enriched/changed generative rule (the 8 in "Theoretical Foundation") → reconcile the rule↔prompt ownership entry; if a previously prompt-absent rule (R3 modality balance, R7 apex coherence) gets wired, flip its entry from "absent" to its encoding site.
- New pipeline stage, output→input seam, or score-gate (e.g. a new `HS_THRESHOLD`) → add it to the chain-coherence section.
- New agent or handoff → add a row to the cross-agent parity matrix.
- New prompt regression test → point the skill's Verify section at it.

Treat this as part of "done" for any prompt/theory/pipeline change, the same way `GRAPH_SCHEMA` must be updated when graph structure changes.

| Location | What it controls |
|----------|-----------------|
| `agents/apps.py` | User-facing vocabulary/framing (NAVIGATOR_APP, NAVIGATOR_ADVANCED_MODE_APP, advisory personas) |
| `agents/analyst/system_prompts.py` | Analyst tool selection and workflow |
| `agents/explorer/system_prompts.py` | Explorer tool selection and workflow (function; interpolates insight/proactiveness ladders) |
| `agents/advisor/system_prompts.py` | Advisor domain-neutral dialectical engine + `{dialectical_context}` slot |
| `concerns/` | Structured LLM calls within skills (Mirascope): `SYSTEM_PROMPT` + `_*_prompt()` + DTO `Field` descriptions |
| `agents/orchestrator/tools/get_schema.py` | `GRAPH_SCHEMA` — Cypher generation guidance for `query_graph` |

When fixing prompt output bugs: follow the revision methodology in `/df-review-reasoning-layer` (diagnose root cause → apply fix → verify with regression test).

**Prompt constant conventions:**
- Aspect definitions and HS/complementarity scales are imported from `concerns/scoring_scales.py` — never re-type them inline (they drift).
- Many concern `SYSTEM_PROMPT`s are f-strings interpolating those constants (and `self.settings.*`). Keep them f-strings when editing; assert on the module attribute (`module.SYSTEM_PROMPT`), not `inspect.getsource` (which shows the literal `{CONST}` token, not interpolated text).

---

## Documentation References

| Doc | Purpose |
|-----|---------|
| `docs/graph.md` | Full graph data model (positions, transformations, cardinality, layers, intent) |
| `docs/theory/` | Theory→implementation wiki: every Structured Dialectics claim mapped to its encoding site with status (implemented/partial/absent/diverges). Gaps may carry `**Tracked:** #NN` linking a GitHub issue (orthogonal to status — see `index.md`). Maintained by `/df-sync-theory` — consult it instead of the theory PDFs; keep it synced when implementing theory-encoding code. Start at `index.md` (status ledger + standing cautions). |
