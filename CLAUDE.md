# CLAUDE.md - AI Co-Developer Guide

## Collaboration Style

Give honest opinions with clear tradeoffs — not agreement for the sake of agreement. State what you actually think is the better approach and why. If both options are defensible, say so directly.

## What is the Dialectical Framework?

A semantic graph system for dialectical reasoning — thesis-antithesis-synthesis dynamics as graph structures. Used for systems analysis, wisdom mining, ethical modeling, and decision-making apps.

### Theoretical Foundation (Generative Rules)

The framework implements **Structured Dialectics** (theory papers in `docs/r-n-d/`, gitignored). Claim-by-claim theory→code mapping with statuses lives in `docs/theory/` (maintained by `/df-sync-theory`) — consult it before any theory-adjacent work. Promoted essentials (details in `docs/theory/generative-rules.md`):

**1. Tetrad structure.** Every thesis T generates exactly one antithesis A; the T–A interaction yields four components under three constraints:
- **T+** / **A+**: constructive developments that actively balance the other side (not merely "positive")
- **T-** / **A-**: one-sided overdevelopments — exaggerate the parent AND underdevelop the opposition (not merely "negative")
- T+ directly contradicts A- (vice versa); T- directly contradicts A+

**2. Circular Causality (Transition Rule).** S+ arises iff two transitions occur simultaneously: T-→A+ (constructive antithesis) and A-→T+ (constructive thesis). This closed loop is the source of self-regulation — WHY `Ac+` (T-→A+) and `Re+` (A-→T+) are the required Transformation positions.

**3. Modality Balance.** M(T+) = −M(T-) = M(A+) = −M(A-). Only the equality chain has content (sum is always zero under the paper's approximation); the paper found Ks-derived balance criteria "not useful" — see Rule 3.2 before wiring any check.

**4. Complementarity.** K = (K_T + K_A) / 2 — how well aspects complement T and A. Balanced tetrads: K_T(T+) > K_T(T-), K_T(A+) > K_T(A-). Complementarity + HS (similarity to apex) determine tetrad quality.

**5. Equal-Sign Synthesis.** S+ emerges between T+/A+ (like-signed constructive); S- between T-/A- (like-signed destructive). No direct interaction between different-sign poles — those are contradictions at different developmental levels of the same phenomenon.

**6. Control Statements.** Coherence test: "T+ without A+ yields T-", "A+ without T+ yields A-". A system exhibits S+ iff it increases dimensionality while preserving stability, distinction, and normative coherence.

**7. Apex Coherence.** S+/- must lie within the convex hull / semantic centroid of its valid sub-syntheses (those passing modality balance, complementarity, control statements) — prevents arbitrary abstraction.

**8. Systemic Taxonomy.** Universal taxonomy (Table S-1), 5 branches — Integrity, Fidelity, Exchange, Flexibility, Resilience — apex concepts for T+/T-/A+/A- per domain. `SYSTEMIC_TAXONOMY` in `concerns/statement_classification.py`; used for HS and anchor aspects.

**Greimas mapping:** Ac (Action) = Not-A space (T to Ac+); Re (Reflection) = Not-T space (A to Re+). Ac+/Re+ generative; Ac-/Re- = degradation modes.

### Scoring & Metrics (see docs/scoring.md for full reference)

**Ks** (complementarity toward synthesis) = `(K_T + K_A) / 2`. Computed property, never stored — only K_T and K_A persisted on `AspectRelationship` edges.

**Tetrad quality metrics (on Perspective):**
- `area` = Ks(T+) + Ks(A+) - Ks(T-) - Ks(A-) — higher = better differentiation. Theory's canonical name is **SP (Synthesis Potential)** — same formula; SP ≡ area.
- `rectangularity` = [Ks(T+)-Ks(A+)]² + [Ks(T-)-Ks(A-)]² — lower = better balance. Deliberately diverges from the paper's (rejected) linear form — see `docs/theory/scoring.md` before "fixing".
- Empirical thresholds: diff ≥ 0.1, |diff_t − diff_a| ≤ 0.15 (side balance), Ks(+) > 0.4, Ks(-) < 0.6
- **DV (Dialectical Validity)** IS implemented — scored alongside CC in `ControlStatementsCheck`, annotation + Advisor render floor only (no DV > 0.5 gate). MMI, PSI, PC are NOT implemented — don't let prompts claim them. See `docs/theory/scoring.md`.

**HS (Heuristic Similarity):** T=1.0 (defines apex), A/Aspects/Ac+/Re+ = LLM-computed, Ac/Re/Ac-/Re- = None.

**Validation, in practice:** Tetrads are never blocked — the generation prompt enforces structure; `AnalysisPipeline` gates only on HS (`_rank_polarities`, `HS_THRESHOLD=0.7`).
- `PerspectiveValidation` (CC + empirical inequalities) runs post-commit in `ExpandPolarity._validate_and_flag` as a non-blocking flag → `Perspective.validation` ("passed" / "failed: reasons" / None). Rendered by `dialectical_context`, `present_analysis`, `inspect_node`; prompts deprioritize failed perspectives, the graph drops nothing. Fail-soft, sequential.
- `edit_perspective._validate_tetrad_coherence` checks user-edited tetrads via `ControlStatementsCheck` + `DiagonalOppositionsCheck` (diagonal LLM call only needed when generation-prompt constraints are bypassed).
- SIMPLE-path antitheses (hardcoded HS=1.0) render as "mechanical opposition — HS not evaluated", never a numeric score.

### Core Model

**Positions (6 core + 2 synthesis):**

| Position | Role |
|----------|------|
| T / A | Neutral thesis / antithesis (dialectical opposition) |
| T+ / A+ | Constructive balance — enhances the opposition's upsides |
| T- / A- | Exaggeration — overdevelops self, underdevelops opposition |
| S+ | Emergent quality from circular causality (dimensionality increase) |
| S- | Consolidation/reduction (dominance or oscillation, finite lifespan) |

**Key nodes:** Statement, Perspective (PP), Polarity, Nexus, Cycle, Wheel, Transformation, Transition, Ideas, Input, Case, Synthesis, Decision

**Perspective.intent = the tetrad's "reading"** ("Reading along: X / Y", axes from TetradDto). Set BEFORE commit (hash-participating: distinct readings = distinct nodes; same reading dedups). Distinguishes sibling tetrads on one Polarity; `edit_perspective` clones drop it (stale after edits).

**Hierarchy:** Perspective → Cycle → Wheel (edges) → Transformation

**Cycle vs Wheel:** Cycle = ordered T-causality sequence (which thesis causes which). Wheel = full circular TA-arrangement with transitions (`generate_compatible_sequences`, diagonal symmetry: T_i opposite A_i). Rotated Cycles are rotations of one directed circle; Wheels are rotation-invariant (`WheelRepository.find_by_component_sequence`), so sibling Cycles share Wheel nodes. All scoped by `sid`.

**Case flow:** Case → Input → Ideas → Statements
**Exploration flow:** Perspectives → Nexus → Cycles → Wheels

See `docs/graph.md` for full data model (positions, transformations, cardinality, layers, intent levels, discarding/editing rules).

### Synthesis Architecture (Wheel-Level)

Synthesis (S+/S-) is a wheel-level phenomenon. One wheel → one S+/S-.

**Circular causality within Transformations:** Each Transformation already encodes both spiral directions — Ac+ (its own edge direction) and Re+ (the opposite edge's direction). A Transformation IS a complete circular causality statement.

**Scaling:** N-PP wheel = 2N edges, N edge pairs. Opposite-edge Transformations are Ac+/Re+ role-swapped (E1's Ac+ = E3's Re+). **Transformations = 2N × |`INSIGHT_CATEGORIES`| = 6N**, not 2N: `ActionExtraction` returns one Ac+ candidate per insight category (Generative/Configurational/Corrective, `concerns/action_extraction.py`) and `ExploreTransformations` Phase 2 generates a tetrad per candidate, so each edge carries 3 depth alternatives (`docs/graph.md` "multiple Transformation alternatives", paper Fig. 8). 1-PP = 2 edges/1 pair/**6** Transformations — measured on a real provider in `tests/test_single_perspective_explore_real_llm.py` (3 × `A → T`, 3 × `T → A`). Cost follows the same multiplier: each Transformation is 4 sequential `TransformationGeneration` calls + 2 audit calls.

**Discrete spiral:** Wheel edges form a directed circle where each step transforms the minus of one segment into the plus of the next (T1-→A2+→T2-→A1+→...). S+ emerges from ALL Transformations operating simultaneously.

**BuildWheels is purely structural:** builds all valid Cycle/Wheel combinations from the Nexus's Perspectives and estimates them (layer 2+). Never generates transformations — those run separately via `ExploreTransformations`, even for layer-1 wheels.

**OPPOSITE_DIRECTION** on both Cycle and Wheel (`_is_circular_reverse`). Cycle opposites: reversed causality, layer 3+ only. Wheel opposites: reversed circular sequence — at layer 2 a cycle's two wheels oppose each other; at layer 3+ opposites live across opposite-direction cycles (1:1). Each opposite gets its own synthesis.

**Nexus grouping rule:** Prefer perspectives from different polarities (genuine synthesis with opponents). Same-polarity perspectives in a nexus only produce "angle shifts" within the same opposition.

**Max wheel layer (`settings.max_wheel_layer`, default 4, env `DIALEXITY_MAX_WHEEL_LAYER`):** `PerspectiveCombination` caps layers regardless of nexus size — bounds combinatorial explosion.

**Combinatorial growth (layer = PP count):** `C(N,k)` × `max(1,(k-1)!)` cycles × `W(k)` wheels/cycle, W(1..4)=1,2,4,8; 4PP→24C/96W.

### Structural vs Analytical Layers

- **Structural** (Merkle backbone — in parent hashes, immutable after commit): Statement, Polarity, Perspective, Transition, Cycle, Wheel, Nexus. Containers: `save() → add members → commit()`.
- **Analytical** (attached via `AnalyticalStructure` edges — never in parent hashes, connectable even to committed targets): Rationale, Estimation, Synthesis (SYNTHESIS_OF), Transformation (ACTION_REFLECTION), Decision (GROUNDED_IN); CRITIQUES is Rationale→Rationale (no Critique node). Analytical NODES are hash-frozen at commit — layer mutability = add/replace/discard, not edit.
- Mutable-anytime = metadata fields excluded from hashes, on BOTH layers: `digest`, `instruction`/`summary`/`haiku`, `discarded`, `validation`.

### Shared Rendering (`graph/rendering.py`)

`build_pp_index(nexus)` is the canonical source of perspective indices — `dialectical_context` and `inspect_node` both use it so T1 always means the same perspective. Indices are stable over the full `nexus.perspectives.all()` ordering (including discarded): gaps appear rather than re-numbering. Helpers: `component_alias`, `format_edge_label`, `format_spiral`, `find_nexus_for_*`.

### Discarding Nodes

`discarded: Optional[str]` on Statement/Perspective/Decision soft-marks a node as excluded from active queries; `discard_uncommitted()` (PerspectiveRepository) deletes uncommitted ones. The `discard` tool unifies both. Replacing a Decision = record new + discard old (reason names the replacement) — no supersede machinery.

### Advisor Tool Constraints

Advisor has `discard` but NO edit tool — re-framing means discard + `anchor` the new version. On user rejection: unscoped Advisor discards silently; counsel-mode (nexus-pinned) head confirms first for exploration members (consent contract), fresh own anchors need no ceremony. To drop a claim: discard the perspective, then its statement (one still used by a live perspective won't discard; discarding a perspective never cascades to shared statements). Tools split by what the LLM knows at call time:
- `ingest` — bulk discovery from material → standalone perspectives (composes AnalysisPipeline)
- `anchor` — plant a specific T/A tension → standalone perspective (IntroducePolarity + ExpandPolarity)
- `explore` — group perspectives into nexus + pathways + synthesis (CreateNexus/ExpandNexus + ExplorationPipeline + GenerateSynthesis). LAZY: builds+ranks ALL wheels, deep-generates only the top (`EXPLORE_DEEP_WHEELS = 1`); rest reported as `shallow_wheel_hashes`. Weaves ≤ `advisor_max_perspectives_per_exploration` per call (excess deferred).
- `deepen` — develop a shallow wheel on demand (ExploreTransformations + GenerateSynthesis, synthesis always). The escape from explore's budget when the user's lived reality picks a non-top arrangement. Scoped variant guards wheel-membership in code.
- `record_decision` — persist an explicitly confirmed decision (RecordDecision + fail-soft DecisionCoherenceCheck). Consent-first in BOTH modes — the one exception to silent machinery; the `_DECISION_READINESS` engine section renders only when wired
- `sync` — re-read graph state (DialecticalContext); optional `nexus_hash` zooms into one exploration in full depth (no wheel cap — same exemption as counsel-mode dumps)
- `discard`, `inspect_node`, `read_digest` — graph curation and detail reads (shared orchestrator tools)

**ExpandPolarity creates `count` new perspectives per call (default 1),** sequentially, each using `not_like_these` (existing + generated-this-call) for diversity; a pre-existing partial counts toward `count`.

### User-Facing Vocabulary is App-Layer

The graph model uses universal terms (Statement, Polarity, Perspective, T+/T-/A+/A-); user-facing vocabulary lives in app preambles (`agents/apps.py`). System prompts handle tool selection/workflow only — presentation vocabulary and app-UI behavioral constraints (e.g., viewport scope) go in app preambles.

**Surface names are fixed across all agent prompts:** "analysis view" (Analyst), "exploration view" (Explorer), "counsel mode" (exploration-pinned Advisor) — never "thread" or ad-hoc variants.

**Advisor preamble/engine split:** the system prompt is a domain-neutral dialectical engine; persona comes entirely from the app preamble. `apps.py` naming: `*_APP` = framework-owned Navigator contracts (AppSpec composes per head, hosts never pick); `*_PERSONA` = palette for the STANDALONE Advisor only (`AppSpec.advisor_persona`; ignored in counsel toggle). Switching persona = new chat on the same graph; register toggle = same `messages`. Personas carry voice only — no framework terms, no convergence mechanics (`TestAdvisoryPersonaBoundary`). App/Register/Persona/Phase vocabulary: `apps.py` docstring.

### Agent Design Principles

- **Product model:** Analyst + Explorer = the "Navigator" (transparent consulting agency, framework visible). Advisor = the consultant *replacement* (hidden machinery, pure counsel). Counsel mode = the partner debriefing the user's own deliverable.
- **Ceiling-not-floor:** the framework must improve the LLM's reasoning, never drop below a bare persona-prompted model. The judged-eval design (`docs/r-n-d/judged-eval-vs-prompted-llm.md`, gitignored — competitive analysis) carries the ablation ladder (A0/A1/A1.5/A1.7/A2); `test_advisor_e2e.py` is the collapse tripwire.
- **Lived reality outranks the plausibility score:** when the user gravitates to a non-top causal reading, follow (deepen it), don't argue from %.
- **Prune, don't instruct:** pre-computed filtering of context beats prioritization rules the model must self-apply.

### Agent Ownership

- **Analyst** = everything up to and including nexus creation (inputs → statements → polarities → perspectives → `create_nexus` handoff). `create_nexus` lives here only — Explorer never creates nexuses.
- **Explorer** = everything after nexus (nexus-scoped: cycles → wheels → transformations → synthesis). Constructed with `nexus_hash`. Carries `create_dx_input` to START the round-trip: capture a Transition insight as a dx:// Case Input → Analyst develops it → `expand_nexus` weaves back.
- **Advisor** = pure-conversation agent, framework runs silently (no terminology exposed). Composes both pipelines via `ingest`, `anchor`, `explore`, `deepen`, `sync` (+ shared `inspect_node`, `read_digest`, `discard`). System prompt is a FUNCTION `system_prompt(tool_names, scoped_nexus_hash)` — tool docs render only for wired tools.
- **Apps plug in via `app=`** (an `AppSpec`, `agents/app_spec.py`) — pieces `voicing`/`advisor_persona`/`tool_guide`/`tools`; each head composes its own preamble (Analyst/Explorer: NAVIGATOR_APP+voicing+tool_guide; counsel toggle: NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER+…; standalone Advisor: advisor_persona+tool_guide). ONE AppSpec per app, passed to EVERY head (toggle shares literal history; Analyst owes parity). Manual layer: `app_preamble=`/`app_tools=` (replaces AppSpec composition; mixing with `app=` raises). Tools merge via `agents/toolsets.py::merge_app_tools` (append; shadowing a built-in raises; system prompts skip unknown names).
- **Advisor(nexus_hash=...)** = counsel mode of the Explorer↔Advisor session toggle (NOT standalone): host hands `messages` + `nexus_hash` between heads; preamble pairing `NAVIGATOR_APP_ADVANCED_TOGGLE` ↔ `NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER` (both on `NAVIGATOR_APP`). Nexus pin enforced by tool closures (`advisor/tools/scoped.py`), not prompt. See `docs/agents.md` Handoffs.

### Advisor Runtime Budgets (settings, Advisor-only)

Five knobs bound the silent Advisor (`settings.advisor_*`, env `DIALEXITY_ADVISOR_*`; Navigator agents ignore all):
- `advisor_polarity_quality_min_hs` (0.5), `advisor_perspective_quality_min_sp` (0.3), `advisor_perspective_quality_min_dv` (0.3) — standalone perspectives below floors (or failed validation) are SUPPRESSED from the context dump with a count line. Nexus members exempt; unscored never suppressed. SP+DV pair mirrors the paper's acceptance criterion as soft pruning.
- `advisor_wheel_quality_top_plausible` (3) — wheels per cycle in the unscoped dump (counsel-mode dumps exempt).
- `advisor_max_perspectives_per_exploration` (2) — per-explore-call weave cap (excess deferred+reported; bounds turn latency, orthogonal to `max_wheel_layer` which bounds structure size).

The Advisor's prioritization prompt says "pre-pruned, rank within it" — changing floors requires reconciling it (`TestContextDumpPrePruned`).

**Policy is not config.** If no deployment would ever set a value, encode it as a module constant with the rationale in a comment (`EXPLORE_DEEP_WHEELS = 1` in `advisor/tools/explore.py`). Audit for new settings: "who sets this, ever, to what?"

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

**black/isort are NOT enforced** (no pre-commit/CI); most of the tree is non-conforming. Don't run `black <file>` after a small edit — it reformats the whole file and bloats the diff. Hand-format only your own lines.

**Concurrent sessions share this working tree.** Before committing: check `git diff --cached --stat` for foreign staged files and `git status` for unexpected dirty ones; stage explicit paths, never `git add -A`. If edits from two sessions land in ONE file, split by hunk (`git diff <file> > /tmp/f.patch`, drop foreign hunks, `git apply --cached /tmp/f.patch`).

**No deprecated aliases on renames.** Rename public constants/functions outright and sweep all consumers (incl. host apps on live path dependencies) in the same change — never re-alias.

---

## Technology Stack

- **Graph DB**: Memgraph or Neo4j (via GQLAlchemy)
  - GQLAlchemy hardcodes `autocommit = True` — no multi-statement transactions; each `save_node()`/`save_relationship()` commits alone. `saved_at` tracking (`IncrementalBuildMixin`) is the atomicity signal instead.
- **DI**: dependency-injector
- **Validation**: Pydantic v1 *style* (v1-compatible `Field`/validators), but the installed lib is **v2** — for introspection use `Model.model_fields[name].description`, not `__fields__`/`.field_info`.
- **LLM**: Mirascope (OpenAI, Anthropic, Bedrock via custom provider)

---

## Where Things Live

| Purpose | Location |
|---------|----------|
| DI Container (START HERE) | `dialectical_reasoning.py` |
| Graph nodes / relationships / mixins | `graph/nodes/`, `graph/relationships/`, `graph/mixins/` |
| Relationship API | `graph/relationship_manager.py` |
| Repositories (data access) | `graph/repositories/` |
| Concerns (standalone services) | `concerns/` |
| Shared scoring vocabulary (aspect defs, HS/complementarity/insight/proactiveness scales) | `concerns/scoring_scales.py`, `concerns/ac_re_taxonomy.py` (pure constants) |
| Agents (conversational) | `agents/analyst/analyst.py` (Case-scoped), `agents/explorer/explorer.py` (Nexus-scoped), `agents/advisor/advisor.py` (silent framework) |
| App preambles + advisory personas | `agents/apps.py` |
| Shared agent tools | `agents/orchestrator/tools/` |
| Agent skills/tools | `agents/{analyst,explorer,advisor}/` |
| Dialectical context (graph→natural language) | `concerns/dialectical_context.py` |
| LLM abstraction / Bedrock provider | `utils/use_brain.py`, `utils/bedrock_provider.py` |
| Input context (digest→prompt) | `utils/input_context.py` |
| Events / Exceptions / Protocols | `events/`, `exceptions/`, `protocols/` |
| Configuration | `settings.py` |
| LLM Wiki mapping docs | `docs/llm-wiki.md` |

All paths relative to `src/dialectical_framework/`.

**Claude skills:** shared `df-*` skills live in `.claude/skills/df-<name>/SKILL.md` (committed; `disable-model-invocation: true` + scoped `allowed-tools` — mirror a sibling). Personal `local-*` skills are gitignored. DB lifecycle: `/df-memgraph`. After renaming/moving a skill dir, re-run `/reload-skills` — the session's skill list doesn't auto-refresh.

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

A tool parameter must not be both "literal value" AND "instructions for an inner LLM to interpret." If a tool needs two modes, split it into two tools rather than adding an `intent` string an inner LLM must re-interpret. Reference: `anchor_theses` (literal statements) vs `surface_theses` (extraction instructions).

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

**Anti-patterns:** Don't pass `graph_db` between `@inject` methods (each gets the same singleton) or store it as an instance variable — inject on each method that needs it.

### Graph Node Lifecycle

```python
# Simple (atomic): commit() does save + hash
stmt = Statement(text="..."); stmt.commit()
# Container (IncrementalBuildMixin): save() → add → commit() (immutable after)
container.save()
child.rel.connect(container)  # OK before commit
container.commit()
```

**Uncommitted node safety (`saved_at`):** `save()` sets `saved_at`; `commit()` clears it. `saved_at != NULL, hash == NULL` = actively building or abandoned garbage. All listing/discovery queries MUST filter `WHERE n.hash IS NOT NULL`. Cleanup: `scripts/cleanup_stale_nodes.py --max-age 86400`.

**Event reporting:** `commit()` emits no SSE events. When it creates relationships internally (e.g., `Polarity.commit()` creates T/A edges), the calling skill emits `relationship_created` per edge. Save-then-commit containers emit split events: `report.node_created(node)` after `save()`, `report.node_committed(node)` after `commit()`. Atomic-commit nodes emit one `node_created` with both set.

### Relationship Direction

`RelationshipTo` and `RelationshipFrom` define the SAME edge from different perspectives. Convention: Child→Parent edges use `RelationshipTo` on child.

```python
nexus = RelationshipTo("Nexus", "BELONGS_TO_NEXUS")            # on Perspective (child)
perspectives = RelationshipFrom("Perspective", "BELONGS_TO_NEXUS")  # on Nexus — same edge
```

**Event direction for `relationship_created`:** `from_node`/`to_node` must match the actual DB edge direction, NOT the owner's perspective. E.g. `relationship_created(polarity.t, thesis_stmt, polarity)` — Statement is from_node because the DB edge is `(Statement)-[T]->(Polarity)`.

**Idempotent connect:** `RelationshipManager.connect()` deduplicates only `direction="any"` relationships; directed ones silently create duplicate edges on repeated calls — check `manager.all()` first if re-invocation is possible.

### Scope (sid)

All nodes share `sid` from their Case. Enforced at connect time. Use `with scope(case.sid):` to set context.

### Input Digest (Living Understanding)

`Input.digest`: mutable field (excluded from hash) storing LLM-generated understanding of a source. Populated by `SourceDigest`; content <1500 chars skips the LLM (used as its own digest). Whoever adds the input, digests it.

**Consumption:** skills use `input_context()` (`utils/input_context.py`) — digests in `<Input id="{hash}">` tags, falling back to resolved content when digest is None. Exception: `surface_theses` needs raw content for extraction (digest for previews only). Tools: `read_digest` | `read_input` | `digest_input` (Analyst and Explorer).

**Multimodal seam (#35):** `InputResolver.resolve() -> str` (text-only, safe to f-string) vs `resolve_native() -> UserContent` (opt-in). `SourceDigest` is the SOLE `resolve_native` consumer — one vision pass emits a text digest, downstream stays text. Never widen `resolve()` to return media (text callers would silently stringify it). `ConversationFacilitator.submit`/`submit_stream` accept `UserContent`.

### Antithesis Persistence Checklist

`AntithesisClassification` returns Mode/Arousal but creates no DB nodes — the caller persists via `EstimationManager.upsert_estimation()` (`AntithesisExtraction` does this internally).

### Model Provenance is Rationale-Only

Only `Rationale.agent` tracks generating model (`<provider>/<model>`, auto-filled from settings; sentinel `"human"` = user-confirmed content, e.g. a Decision's rationale). Other nodes trace provenance through their Rationale — intentional, don't "fix" by adding `agent` elsewhere.

### Statement Generation Conventions

- Word limit: always use `self.settings.component_length` (headlines, ~7) or `self.settings.transition_length` (transitions, ~15) via `SettingsAware` — never hardcode. Pydantic `Field` descriptions can't interpolate `self.settings`: keep length qualitative there, numeric limit in the method prompt body.
- **`component_length` is enforced at generation/extraction time, not by `StatementClassification`** (echoes text verbatim). The `anchor` path has no extraction step, so `StatementHeadline` condenses there (gathered with classification; classification reads full text, stored `Statement.text` = headline; text ≤ limit skips the LLM call). `edit_perspective` deliberately does NOT condense — user-typed wording must survive.
- Analytical artifacts (synthesis, transformations) scope uniqueness via meaning field: `meaning=f"synthesis:positive:{wheel.hash}"` prevents cross-context dedup while `commit()` handles exact-match dedup automatically.

### Classification → HS Chain (Critical Invariant)

`StatementClassification` (SIMPLE vs COMPLEX) determines the entire antithesis path: SIMPLE → mechanical negation, HS hardcoded 1.0, no taxonomy contextualization; COMPLEX → LLM-evaluated antithesis taxonomy, LLM-scored HS (0.0–1.0). Polarity HS (UI + `_rank_polarities` gate at `HS_THRESHOLD=0.7`) comes from the A-relationship's `heuristic_similarity` — misclassifying COMPLEX as SIMPLE inflates all polarities to HS=1.0, defeating quality differentiation. The SIMPLE/COMPLEX boundary is the most leverage-dense prompt in the extraction pipeline.

Named options / courses of action ("Take the startup offer") classify COMPLEX — SIMPLE strips taxonomy anchoring from the option tetrad. For option-pairs, Mode (in the anchor report) is the "differ rather than oppose" tell, not HS: mutually exclusive options sit in each other's negation space, so HS scores moderate; Mode ~0.0–0.1 (distancing/privation) flags a fork that isn't the tension.

### Observability (Langfuse)

- `ReasonableConcern.__init_subclass__` auto-wraps every concern's `resolve()` with `@observe` — spans only when an active Langfuse trace exists (no orphan traces).
- `use_brain` names generation spans via `method.__qualname__` with `capture_input=False`; input set by `_trace_generation`.
- `ConversationFacilitator._strip_unsupported_input_fields()` strips output-only API fields (e.g. `caller`) before replaying — Mirascope passthrough-bug workaround.
- Mirascope `BaseResponse`: use `response.messages[:-1]` for input messages — `response.input_messages` does NOT exist.
- Structured results enter history via `ConversationFacilitator._assistant_history_text` — DTOs with a `message` field store the plain text, never the Pydantic repr (wastes tokens, invites imitation). `mock_brain` delegates to the same helper.
- Tests use `@traced` from conftest (not bare `@observe()`) for reliable trace naming. **`@traced` serializes the function's args as span input** — never put it on a test taking `monkeypatch` or other cyclic fixtures; the serializer recurses forever and HANGS. Diagnose with `pytest -o faulthandler_timeout=25`.

### Concurrency & Rate Limiting

Optional concurrency semaphore in `utils/concurrency.py` (env `DIALEXITY_MAX_CONCURRENT_LLM_CALLS`; 0/unset = disabled). Applied inside `use_brain`; streaming (`raw_call=True`) excluded.

Rate-limit retry (429/ThrottlingException) in `use_brain`: 10s base, 2× up to 60s cap, max 10 attempts; ParseError: 2× up to 120s. **Hand-rolled by design — do NOT replace with Mirascope's `llm.retry`/`RetryConfig`** (can't express separate retry curves, per-attempt slot re-acquisition/tracing, or string-based Bedrock throttle detection).

**Parallelization points:** `ExplorationPipeline` runs wheels concurrently. `ExploreTransformations` parallelizes edge pairs, Phase 1 edges, Phase 2 candidates, audits. `AnalysisPipeline` parallelizes `expand_polarities`/`find_polarities`. Graph writes stay sequential after gather.

**Pattern:** Always `asyncio.gather` the LLM work, collect results, then write graph nodes sequentially in a loop. Never call `_create_transformation` or similar graph-writing code inside a gathered task — GQLAlchemy is not concurrency-safe.

---

## Tool Pattern (Mirascope)

Two-layer: `ReasonableConcern[T]` (implementation) + `@llm.tool` function (LLM-facing interface).

**Hierarchy (increasing scope):**
- **Concern** = standalone single-responsibility service → `concerns/`. Public, reusable across tools/skills/pipelines.
- **Tool** = `@llm.tool` function + optional internal helper class → `agents/{phase}/tools/`. Helpers may extend `ReasonableConcern` (for `self._report`) but stay internal — not importable elsewhere.
- **Skill** = orchestrates multiple concerns, has reasoning responsibility → `agents/{phase}/skills/`
- **Agent** = top-level conversational coordinator, owns a tool set → `agents/{phase}/`

**When to promote:** if anything outside the tool file calls a helper's `resolve(...)`, move it to `concerns/`. Only `@llm.tool` functions go into tool lists — `ReasonableConcern` classes never pass to Mirascope directly.

**Tool return convention:** Mutating tools return `str(concern.report)` (JSON with effects, artifacts, hashes for the LLM). Read-only tools (inspect_node, read_digest, sync) return `await concern.resolve()` directly — the content is the useful output.

```python
@llm.tool
async def surface_theses(
    intent: Annotated[str, Field(description="What theses to find")],
) -> str:
    """Surfaces theses for dialectical analysis."""
    skill = SurfaceTheses(intent=intent)
    await skill.resolve()
    return str(skill.report)
```

**Critical:** Never use `param = Field(default=X, ...)` as a Python default — Mirascope leaves the raw `FieldInfo` as the runtime default. Always `Annotated[type, Field(...)] = actual_default`. Test coverage: `test_tool_signatures.py`.

**Mirascope does NOT coerce nested models in tool kwargs** — `json.loads`'d args mean a `list[Model]` param arrives as raw dicts. Normalize via `Model.model_validate` in the concern (`RecordDecision`); test with raw-dict calls (`TestRecordDecisionToolBoundary`) — `test_tool_signatures.py` fills arrays with strings and can't catch it.

**Report artifacts must include final-state text.** After `StatementDeduplication`, the LLM sees only `node_created` (original text) and `node_deleted` (hash-only) effects — every skill that deduplicates must add an artifact with the authoritative post-dedup text (e.g. `artifacts["theses"]`). Reference: `expand_polarities.py`.

**`AnalysisPipeline` does NOT merge sub-skill reports.** Anything the agent must see (HS scores, quality signals) must go on the pipeline's OWN `self._report.artifacts` (see `polarity_quality`) — sub-reports live on the discarded `AnalysisResult.reports`. Report artifacts reach only the LLM (via `__str__`), never the frontend — the event bus publishes `Effect`s only.

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

**Mock brain** (`tests/mock_brain.py`) auto-constructs Pydantic responses. Does NOT test streaming, tool registration/argument parsing, or provider behavior. Returns **identical** DTOs every call — to test diversity/dedup, `monkeypatch` the concern's `resolve`. Fills `Literal[...]` fields with the FIRST allowed value — order Literals so the first is a safe default.

**Fixtures may use `meaning="test"` ONLY on paths that never reach taxonomy lookups** — `lookup_*` raises on unparseable meanings; else use a real `dx://taxonomy/...` URI.

**Response-model *shape* changes are invisible to the mocked suite** (auto-fills every field) — the real LLM may drop a branch → `ParseError`. Verify DTO-shape changes with `--real-llm`; prefer flatter schemas.

**One graph-test run at a time.** The autouse `cleanup_graph_db` fixture `DETACH DELETE`s around each test — concurrent pytest processes against one Memgraph deadlock. A `pkill -9`'d run leaves a stuck lock: `docker compose -f docker-compose.test.yml restart`. The volume (`mg_lib`) persists across restarts — confirm a failure is pre-existing via `git stash` + re-run; truly wipe with `down -v`.

**DB-free tests:** Override autouse fixtures `cleanup_graph_db` and `cleanup_test_graph_data` with empty yields.

**Ad-hoc verification scripts must live under `tests/`.** DI wiring and mock-brain fixtures come from `tests/conftest.py`; a pytest file run from `/tmp` fails with unresolved `Provide` sentinels (`'Provide' object has no attribute 'save_node'`).

---

## Environment Configuration

`.env.example` is the source of truth for all env vars (copy to `.env`). All vars are read in
`settings.py` (`Settings.from_env`) except `DIALEXITY_MAX_CONCURRENT_LLM_CALLS` (`utils/concurrency.py`)
and `DIALEXITY_TEST_CLEANUP` (`tests/conftest.py`).

**File convention:** uncommented vars are REQUIRED; commented vars are optional and the value shown
IS the code default. When you change a default in code, update `.env.example` in the same change.

`Settings.from_partial` merges with `exclude_unset` — a field at its Pydantic default never stomps
an env-configured one.

Only required: `DIALEXITY_DEFAULT_MODEL` — combined `provider/model` string (e.g.
`bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0`) — plus credentials for that provider.

---

## Prompt Engineering

The project is infused with LLM prompts at multiple layers. Use `/df-review-reasoning-layer` when writing or editing prompts — it reviews at three altitudes (isolated prompt → assembled context → whole reasoning chain) and carries the full methodology, checklist, drift-hotspot catalog, and cross-agent parity map (`.claude/skills/df-review-reasoning-layer/reference/systemic-map.md`).

**`df-review-reasoning-layer` is a LIVING skill — keep it in lockstep.** Any change it maps (prompt site, shared constant/scale, generative rule, pipeline stage/score-gate, agent/handoff, regression test) updates the skill AND its reference map in the same change — part of "done", same as `GRAPH_SCHEMA` for graph changes.

| Location | What it controls |
|----------|-----------------|
| `agents/apps.py` | User-facing vocabulary/framing (NAVIGATOR_APP, NAVIGATOR_APP_ADVANCED_TOGGLE, advisory personas) |
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
