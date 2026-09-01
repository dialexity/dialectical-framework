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

**Scaling:** N-PP wheel = 2N edges, N edge pairs. Opposite-edge Transformations are Ac+/Re+ role-swapped (E1's Ac+ = E3's Re+). **Transformations = 2N × |`INSIGHT_CATEGORIES`| = 6N**, not 2N: `ActionExtraction` returns one Ac+ candidate per insight category (Generative/Configurational/Corrective, `concerns/ac_re_taxonomy.py`) and `ExploreTransformations` Phase 2 generates a tetrad per candidate, so each edge carries 3 depth alternatives (`docs/graph.md` "multiple Transformation alternatives", paper Fig. 8). 1-PP = 2 edges/1 pair/**6** Transformations — measured on a real provider in `tests/test_single_perspective_explore_real_llm.py` (3 × `A → T`, 3 × `T → A`). Cost follows the same multiplier: each Transformation is 4 sequential `TransformationGeneration` calls, + 2 audit calls only when `settings.audit_transformations` is on (default off — see the Settings section).

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
- `audit_feasibility` — score named pathways for practical achievability on demand (TransformationAudit, the concern `explore` no longer runs eagerly). Takes `transformation_hashes` (the `[[hash]]` on every pathway line), audits Ac+/Re+, renders band + factors + success conditions read back from the graph. Idempotent: an already-estimated pathway is returned free, because re-auditing accumulates critique Rationales that disagree while `upsert_estimation` keeps only one score. Capped at `MAX_TRANSFORMATIONS_PER_CALL = 4` with the excess named as `deferred` (2 calls per pathway — an unbounded list re-spends the whole eager audit). Shared by both agents (`orchestrator/tools/`); scoped variant guards nexus-membership in code.
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
- **Ceiling-not-floor:** the framework must improve the LLM's reasoning, never drop below a bare persona-prompted model. `tests/e2e/README.md` carries the ablation ladder (A0/A1/A1.5/A1.7/A2) and what each rung isolates; `test_advisor_e2e.py` is the collapse tripwire.
- **Lived reality outranks the plausibility score:** when the user gravitates to a non-top causal reading, follow (deepen it), don't argue from %.
- **Prune, don't instruct:** pre-computed filtering of context beats prioritization rules the model must self-apply.

### Agent Ownership

- **Analyst** = everything up to and including nexus creation (inputs → statements → polarities → perspectives → `create_nexus` handoff). `create_nexus` lives here only — Explorer never creates nexuses.
- **Explorer** = everything after nexus (nexus-scoped: cycles → wheels → transformations → synthesis). Constructed with `nexus_hash`. Carries `create_dx_input` to START the round-trip: capture a Transition insight as a dx:// Case Input → Analyst develops it → `expand_nexus` weaves back.
- **Advisor** = pure-conversation agent, framework runs silently (no terminology exposed). Composes both pipelines via `ingest`, `anchor`, `explore`, `deepen`, `sync` (+ shared `inspect_node`, `read_digest`, `discard`, `audit_feasibility`). System prompt is a FUNCTION `system_prompt(tool_names, scoped_nexus_hash)` — tool docs render only for wired tools.
- **Apps plug in via `app=`** (an `AppSpec`, `agents/app_spec.py`) — pieces `voicing`/`advisor_persona`/`tool_guide`/`tools`; each head composes its own preamble (Analyst/Explorer: NAVIGATOR_APP+voicing+tool_guide; counsel toggle: NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER+…; standalone Advisor: advisor_persona+tool_guide). ONE AppSpec per app, passed to EVERY head (toggle shares literal history; Analyst owes parity). Manual layer: `app_preamble=`/`app_tools=` (replaces AppSpec composition; mixing with `app=` raises). Tools merge via `agents/toolsets.py::merge_app_tools` (append; shadowing a built-in raises; system prompts skip unknown names).
- **Advisor(nexus_hash=...)** = counsel mode of the Explorer↔Advisor session toggle (NOT standalone): host hands `messages` + `nexus_hash` between heads; preamble pairing `NAVIGATOR_APP_ADVANCED_TOGGLE` ↔ `NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER` (both on `NAVIGATOR_APP`). Nexus pin enforced by tool closures (`advisor/tools/scoped.py`), not prompt. See `docs/agents.md` Handoffs.
- **"Framework runs silently" is a PROMPT ASPIRATION that measurably fails about 1 turn in 6, and only `_HOW_YOU_SPEAK` defends it.** On a controlled 20-pair run whose questions invited narration, 7 of 40 replies said a banned term out loud — `nexus`, `thesis`, `antithesis`, `wheel`, `the framework` — one of them handing the person "the main wheel is 63.9% probable" straight out of the context dump (`tests/e2e/probe_leak_reply_reuse.py`). It is NOT caused by any of the latency work: the rate is the same with the extraction round restored, and the two configurations merely leak different vocabulary (with reuse the reply reads the dump aloud; without it, it narrates its method). So treat leakage as an open prompt-level defect, not a regression to bisect, and never assert the silent contract from the fact that the prompt states it — the regression tests that check the prompt says so are the trap this finding walked into. `score_machinery_leak` is the endpoint; `read_reply_hygiene.py` re-runs it over any archived stem for free.

### Advisor Runtime Budgets (settings, Advisor-only)

Five knobs bound the silent Advisor (`settings.advisor_*`, env `DIALEXITY_ADVISOR_*`; Navigator agents ignore all):
- `advisor_polarity_quality_min_hs` (0.5), `advisor_perspective_quality_min_sp` (0.3), `advisor_perspective_quality_min_dv` (0.3) — standalone perspectives below floors (or failed validation) are SUPPRESSED from the context dump with a count line. Nexus members exempt; unscored never suppressed. SP+DV pair mirrors the paper's acceptance criterion as soft pruning.
- `advisor_wheel_quality_top_plausible` (3) — wheels per cycle in the unscoped dump (counsel-mode dumps exempt).
- `advisor_max_perspectives_per_exploration` (2) — per-explore-call weave cap (excess deferred+reported; bounds turn latency, orthogonal to `max_wheel_layer` which bounds structure size).

The Advisor's prioritization prompt says "pre-pruned, rank within it" — changing floors requires reconciling it (`TestContextDumpPrePruned`).

**`audit_transformations` (False)** — the one non-`advisor_*` behavioural knob, and it applies to BOTH agent paths. Off means `TransformationAudit` never runs, so no `FeasibilityEstimation` and no CRITIQUES Rationale is written. Safe to leave off and safe to turn on: nothing in the code branches on either artifact (the score renders where present, is omitted where absent; the critique Rationale has no reader in the tree), and no resume/completeness/status accounting counts an unaudited Transformation as owing anything — **an unaudited wheel is finished, not partial**. It is off because it was 2 provider calls per Transformation = 40% of `explore`'s entire provider spend (`probe_explore_cost.py`) for an annotation. What off costs is one ranking input: both agents' prompts say "prefer high-feasibility + low-to-moderate insight first", and both now state that a missing band means *not estimated*, never *low* — required regardless of this knob, since only Ac+/Re+ are ever audited and Ac-/Re- have never carried a band. Tests: `tests/test_transformation_audit_optional.py`.

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
| Build status (derived pause/resume state, typed for host apps) | `concerns/build_status.py` |
| LLM abstraction / Bedrock provider | `utils/use_brain.py`, `utils/bedrock_provider.py` |
| Input context (digest→prompt) | `utils/input_context.py` |
| Events / Exceptions / Protocols | `events/`, `exceptions/`, `protocols/` |
| Configuration | `settings.py` |
| LLM Wiki mapping docs | `docs/llm-wiki.md` |

All paths relative to `src/dialectical_framework/`.

**Claude skills:** shared `df-*` skills live in `.claude/skills/df-<name>/SKILL.md` (committed; `disable-model-invocation: true`, plus scoped `allowed-tools` **only for run-a-command skills** — a skill whose workflow ends in edits must omit the key, or its documented loop is unexecutable; `df-sync-theory` and `df-e2e` omit it deliberately). Personal `local-*` skills are gitignored. DB lifecycle: `/df-memgraph`. E2E/benchmark work: `/df-e2e` (resume point; numbers come from `tests/e2e/status.py`, never from prose). After renaming/moving a skill dir, re-run `/reload-skills` — the session's skill list doesn't auto-refresh.

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

**Two channels per scope, and `Effect` stays a mutation.** `sid` carries `GraphEvent(effect=…)`; `sid:progress` carries `ProgressEvent` (`events/progress_event.py`, `bus.publish_progress`/`subscribe_progress`). Long chains that write no node until they finish — `TransformationGeneration` is 4 sequential calls, measured as 34s of dead air — report via `utils/progress.py`: `progress_scope(stage, key=…)` around the work, `report_progress(detail)` per step, `expect_progress(n)` to grow the denominator as work is discovered. No-op with no scope installed. **Never widen `Effect`/`EffectType` for progress** — a separate channel is what lets an existing host upgrade without changes (pinned by `TestTheGraphChannelIsUntouched`). Two traps: the ContextVar holds a MUTABLE scope so gathered children share it, which means **a task created before the scope is installed reports nothing** (open the scope above the `gather`); and `detail` strings must carry no framework vocabulary, since a host may render them verbatim under the silent Advisor. `done` = steps finished, `detail` = step just started, `total` grows — see the module docstrings before rendering any of it.

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
- **A conversation turn is ONE provider call, not two.** With tools wired, `submit`/`submit_stream` used to follow every tool loop with a structured `_call_with_response_model` round — even when the model requested no tools — re-rendering prose it had already written, and the reply landed in history twice. **Measured at +1.6s per turn** (95% CI 0.6–2.6s, 24 paired turns, weak tier, 15.7k-token prompt — `tests/e2e/probe_reply_reuse_saving.py`) — about a fifth of a tool-free turn, NOT the "half the reply path" the arithmetic implied before anyone measured it. The likely reason it is that cheap is that the second round re-sends a prompt the provider has already cached, so it pays output tokens and little else. `_reuse_written_reply` now builds the response model from `response.text()` when the turn is finished, and the structured call remains the FALLBACK for the turns where that text is not the answer: tool calls still pending (round-budget overrun), a response model that is not exactly one required `str` named `message`, or no readable text. Adding a second field to an agent's `ChatResponse` silently re-costs every turn — that is the shape's price, so decide it deliberately (`tests/test_reply_reuse.py`).
- **On the streaming path the reply is BUILT from the deltas that were yielded, and `ResponseComplete.streamed` says so.** True = `message` is byte-for-byte the `TextDelta`s since the last `ToolResult`, so a host renders at first-token latency instead of paying the whole turn (~18s median) for text that started arriving in about a second; the reply is joined from the yielded deltas rather than re-read from `stream.text()`, which is a second construction with a separator the deltas never carried. False = render `message` yourself: either nothing streamed (the tool-free `submit_stream` branch makes one formatted call and cannot stream — a known gap, pinned) or the streamed text was unusable and the structured fallback produced the reply. Text yielded BEFORE a `ToolStart` is the model narrating what it is about to do — progress, never part of `message`, so `answer` resets each round. **Consequence for the bench:** it calls `chat()` (`tests/e2e/arms.py`), so machinery leaking into preamble text is invisible to `score_machinery_leak`.
- **Two probe-only instruments answer "why was that slow?", and they are not interchangeable.** `utils/retry_accounting.py` splits a wall clock into work vs. retry sleep; `utils/call_census.py` splits the work into `provider_s` (sum of call durations — the COST lever) and `busy_s` (union of their intervals — the LATENCY lever, with `depth`). `parallelism = provider_s / busy_s` is neither; it reports compression already achieved. Both install via a contextmanager holding a MUTABLE accumulator in a `ContextVar` — a task inherits a *copy* of the context, so a `set()` in a gathered child would be invisible and every fan-out would read as sequential. Both are a STACK: a per-tool measurement never blinds a per-turn one. `record_call` is a no-op when nothing is installed, which is why it can sit on the hot path.
- **The census does NOT see the tool loop's continuation calls, so never classify a turn by its call count.** Only `_call_with_tools` is `@use_brain`-decorated; the loop advances with `response.resume(tool_outputs)` (in `submit`'s tool loop, and via `_start_stream_round` in `submit_stream`'s — cited by symbol on purpose, the line numbers rot on every edit), which is Mirascope's own request and reaches nothing inside `use_brain`. An AWAITED turn that ran five tool rounds therefore records exactly ONE `format_name=None` call — the same as a turn that ran none. The STREAMED path is the exception and only since `_record_stream_round`: it records one call per round explicitly, so five rounds are five records there. Neither count is a classifier. Concern calls made *by* the tools are recorded, so the tell is a pile of unexplained non-`ChatResponse` calls, not the raw count. **`last_tool_calls` on the facilitator is the authoritative "did a tool fire" signal** (reset per submit, next to `last_tool_rounds`). `probe_reply_reuse_saving.py` classified on the census count and admitted five tool-electing turns as clean single generations — one 92.8s with 70 recorded concern calls — into a comparison of a sub-second effect.
- **The streaming path records itself, and its two latency figures answer DIFFERENT questions — never average them together.** `use_brain` hands the caller a raw callable and returns before its own recording (`raw_call=True`), so until `ConversationFacilitator._record_stream_round` a whole `chat_stream` turn contributed NOTHING to any census. It now writes one `CallRecord` per round-trip (`caller = ConversationFacilitator._STREAM_ROUND_CALLER`, deliberately not matched to the awaited path's `_llm_call` — the two have different guarantees). **`CallRecord.first_token_seconds` is the ONLY latency figure a prefill cache can move**, per round, and it is `None` on every non-streaming call because the question does not apply there. **`TurnTiming.first_delta_s` is the person's wait on a blank screen**, per turn, a PREFIX of `reply_path_s` and never an addend — and it is NOT TTFT: the Advisor is contracted to call tools without narrating first, so on a tool-electing turn the first delta can land after a full tool round. **How often it does is UNMEASURED** — counting text deltas before the first `ToolStart` needs the streaming path, and nothing has done it; the ~17% figure that used to be quoted here is the vocabulary-leak rate off the AWAITED path (`probe_leak_reply_reuse.py`, 7 of 40 replies), a different quantity. A caching comparison must select round 1 by `min(started)` and then check whether it took a reading — **never filter on the reading first**, or an unmeasured round 1 silently promotes round 2 (a different prefill at a different breakpoint) into the comparison with a report that looks identical; drop the turn, don't substitute. `CallCensus.mean_first_token_s` is a summary and the wrong statistic for an arm comparison. Three honesty limits are load-bearing, all pinned by `tests/test_stream_ttft.py`: **`first_token_seconds` is NOT a provider RTT** (`await call.stream()` issues no HTTP request — Anthropic's manager sends on `__aenter__`, which mirascope defers to the first `__anext__` — so the interval includes the `use_brain` wrapper, `encode_request`, and the breakpoint scan over a ~60k-char prompt); **the CONSUMER's time is subtracted** (the `yield`s are inside the chunk loop, so a slow host would otherwise read as a slow model and `parallelism` would blame the model for the terminal — and since `ended = started + seconds`, the recorded interval shortens too, deliberately, because consumer time belongs in the `wall - busy_s` remainder); and **prefill may be UNMEASURED rather than zero** (mirascope iterates the raw event stream and DISCARDS the `message_start` usage the Anthropic SDK's own accumulator would have folded in, reading prefill only from the optional `message_delta` fields, while `Usage` stays truthy on output tokens alone — zeros here would publish "caching does nothing" from a round that never saw a prefill token — in the event Bedrock DOES populate those fields, measured 16/16 in `probe_stream_ttft.py`, so that branch is insurance rather than description). One more token trap is upstream and unfixable from here: `message_delta.usage` is CUMULATIVE and mirascope `+=`s every one of them, so a stream emitting two `message_delta`s reports roughly doubled prefill — latent, since one is the norm, but it is why a streamed token figure deserves less trust than an awaited one. Which token convention applies is DECLARED at the recording site (`prefill_token_kwargs(..., pre_added=)`), never inferred: the arithmetic can only DISPROVE pre-adding, and a round with 25,000 uncached against 18,075 read would be reported as 6,925 / 0.72 share instead of 25,000 / 0.42. Recording is fail-soft by design — it runs after the person has read half their answer. **The round's two clocks are deliberately different**: `seconds` runs from the first attempt (the person waited through any retry ladder) while `first_token_seconds` runs from the attempt that ANSWERED, so a throttled round cannot report a 10-second prefill and decide an arm comparison; with no retry the two start at the same instant, and both include request construction on purpose. **A streamed turn's seconds are recorded on EVERY exit, and getting that right took an epoch counter.** `submit_stream` owns the turn's wall clock and nothing else — the rounds live in `_stream_turn` — stamping `last_submit_seconds` the moment `ResponseComplete` passes through it, with a `finally` that writes the figure on any other exit: abandoned, crashed, cancelled. It used to be assigned only after the tool loop, so a turn the person walked away from or one that died mid-stream reported the `0.0` its reset had left, for eight seconds of work. `0.0` is not a gap but a claim: it reads as instant, drags down any mean it enters, and hides precisely the expensive turns. The crash half has a live trigger — a `redacted_thinking` block raises `NotImplementedError` from inside mirascope's `content_block_stop` dispatch, i.e. inside the chunk loop where nothing can retry — gated on `DIALEXITY_THINKING_LEVEL` being set, since `thinking_level` defaults to `None`. **That `finally` must NOT write unconditionally**, for two reasons that pull in opposite directions: an async generator's `finally` runs at CLOSE, not when the consumer stops iterating, and for an abandoned generator that is whenever the collector gets to it — possibly after a newer turn has started, whose correct figure it would overwrite with its own (measured from ITS start, so arbitrarily large); and on the happy path a second reading would absorb however long the host took to come back for the last event. So the write is guarded by `not recorded and epoch == self._turn_epoch`, where the epoch comes from `_begin_turn()`; `submit` claims one too, so a stale stream finalising during an awaited turn cannot clobber it either. **Letting go of the connection is a SECOND cleanup, in a different `finally` — `_stream_turn`'s, around the chunk loop — and it takes two closes, not one.** Unwinding an `async for` does NOT close what it iterates, so an abandoned round stays suspended inside the provider's decoder holding the HTTP response open in an `async with`. But that decoder is three generators down: `chunk_stream()` iterates the response's `_chunk_iterator` (mirascope's `_wrap_async_iterator_errors`, which holds nothing — its `with self._wrap_errors()` is synchronous and catches `Exception`, so `GeneratorExit` passes through; what it contributes is its FRAME) which iterates `decode_async_stream` (the `async with`). Closing only the outermost frees nothing, because `_chunk_iterator` is an ATTRIBUTE of the response object and the response outlives the round — the code after the loop reads its usage and tool calls. So `_release_round` closes `start.chunks` AND `stream._chunk_iterator`, which drops the decoder to zero references — of the two, only the second is load-bearing (the real `chunk_stream()` has no cleanup, so closing it drops just its own frame; it is closed anyway because it is the generator this module owns); the final `__aexit__` is then run by the event loop's async-generator finaliser hook, not by us, because mirascope exposes no close on a stream response. Reaching through a private attribute is the deliberate choice it looks like. **Third cleanup, and it does not end inside the framework:** on the ABANDONED exit — and only that one; a crash or a normal finish unwinds `submit_stream` by itself — nothing runs until someone CLOSES the generator, because stopping an `async for` is not closing. So every `chat_stream` wraps `submit_stream` in `contextlib.aclosing`, which was missing entirely at first and made the abandonment guarantee dead code on the only path that mattered. **But `chat_stream` is itself an async generator, so that link fires only once the HOST closes `chat_stream`** — a bare `async for` with a `break` leaves the outermost frame suspended and the whole chain with it, back to waiting for the collector. Nothing inside can reach up and fix that: only the outermost consumer can close the outermost generator. It is therefore a documented host obligation (`Advisor.chat_stream`'s docstring, `docs/agents.md`, the README example), and `TestTheChainOnlyRunsWhenTheHostClosesTheOutermostGenerator` pins both halves — that a close propagates, and what a `break` costs. Second-order effect worth knowing: on the abandoned streamed turn `_record_turn_timing` never runs at all, so `last_turn_timing` stays `None` — a visible gap, not a stale figure. `Advisor.last_turn_timing` is reset to `None` at the top of `chat`/`chat_stream` for the mirror reason — `_record_turn_timing` is the last thing a turn does, so without the reset a crashed turn wore the previous turn's split, and the e2e driver archives that field per turn. Pinned by `tests/test_turn_finalization.py`, whose mock is built in the same three layers for the same reason — a one-layer fake stream makes the connection assertion unfailable. Each guarantee there was checked by mutating it away and confirming which test failed; the one exception is `submit`'s own epoch claim, which no test covers (nothing bumps the epoch mid-`submit`) and which is symmetry rather than a pinned behaviour. **The same "a zero is a claim" argument reaches one layer further out, into the bench archive, and the fix there has TWO halves.** FIVE of `TurnRecord`'s timing fields defaulted to zero (four `float = 0.0`, `retry_count` an `int = 0`; `first_delta_s` is newer and was born `None`) and the driver wrote those defaults whenever `arm.last_turn_timing` was `None` — which is exactly the crashed turn, since timing is assembled after the reply. **No archived record shows the damage** (all 62 error turns in the archive predate the fields — none carries a timing key at all), so the case is mechanical, not observed, and must be stated that way: a crashed turn would have entered every split column as instant, `retry_count=0` would have claimed a clean turn for one that died mid-ladder, and since `duration_s` is real and often large on those records the `duration_s ≈ reply_path_s + off_path_s` check would have reported the whole turn as harness overhead. **Do NOT reach for "and a crash lands in the tool-heavy turns" to sharpen that** — it was written here once and withdrawn: the driver's `except` branch sets `tool_calls = []`, so all 62 error turns record zero tool calls by construction and this archive cannot be asked the question. `reply_path_s`, `off_path_s`, `context_render_s`, `retry_seconds`, `retry_count` and `first_delta_s` are therefore `Optional` with `None` defaults (the two `tool_*_seconds` lists stay lists, since empty already reads as nothing-recorded — at the cost that an untimed turn is indistinguishable from a tool-free one there, which is why the readers scope their tool counts to timed turns). `duration_s` stays non-Optional because it is timed OUTSIDE the try, and the simulator-failure branch now times its own call rather than writing the 0.0 default — otherwise the field exempted from the rule was breaking it. **`None` TOGETHER holds only for records this driver writes:** across the archive 152 of 184 timed turns predate `retry_seconds`/`retry_count` and 24 predate `context_render_s`, so `reply_path_s is None` is the "no split" signal and every other field still needs its own presence check before arithmetic. The second half is the readers, and it is the half that stays wrong quietly: **a reader that coerces with `or 0.0` reinstates the whole bug while the archive stays honest**. `read_turn_timing.py` prints `untimed turns (dropped)` and scopes `arithmetic closes` plus its tool counts to the timed turns; `probe_reply_path_latency.py` puts the dropped count in its tier header because every share under it has those turns as its denominator, and reports `context refresh: fired on N% of turns` over the turns that RECORDED the field — zero-filling the 20 weak-tier turns that predate it printed 72% where the 96 that recorded it say 86%, understating a pre-registered >90% endpoint, and the retry line carries its own denominator for the same reason. The same coercion has a second form — `median(x) if x else 0.0` — and it produced the identical lie a row over: the reader printed `median context_render 0.00` for `timing-check-building` (0 of 16 turns carry the field) beside `0.19` for `timing-after-audit-gather` (16 of 16), i.e. a refresh cost the newer build appeared to introduce, in the one output stem-to-stem comparisons are quoted from. Empty samples now print `not recorded` with a per-field count row, because a string cannot be read as a measurement. A third reader owes the same lines. Verified against the published stems (16/16 closes, 0 dropped) and pinned by `tests/test_turn_record_timing.py`, which drives the driver's real turn loop rather than constructing records, because the defect lived in the `if timing else 0.0` — including a mixed-vintage turn, since deleting a reader's presence check raises `TypeError` on real data while a synthetic same-vintage sample stays green. Arm asymmetry worth knowing before differencing crashed turns: `PromptArm.last_turn_timing` never returns `None` (`submit`'s own `finally` fills `last_submit_seconds` whatever happened) while `AdvisorArm` does — compare crashed turns on `duration_s`, which every arm reports.
- **Prompt caching: the breakpoint is RELOCATED off the graph dump, and almost nothing else in the tree is cacheable at all.** Mirascope emits the system prompt as ONE text block with `cache_control` at its very END (`anthropic/_utils/encode.py:471-478`); the Advisor's prompt ends with `{dialectical_context}`, so the breakpoint sat behind the only bytes that move and every graph write re-prefilled the whole ~15.6k engine at full rate. `split_system_for_cache` (`utils/bedrock_provider.py`) splits that block at `CACHE_SPLIT_SENTINEL = "\n\n## Current Understanding\n\n"` and leaves the breakpoint on the stable head — **measured 4/4 at cache-read 18,075 / write 0 against read 0 / write 18,732, billed-equivalent prefill 6.8x cheaper on any post-write turn** (`probe_prompt_cache.py`). **Quote the tokens, never the seconds — and that is now a MEASURED null, not a missing measurement.** `probe_stream_ttft.py` timed the only quantity a prefill cache can move: **first token 1.46s with the split against 1.34s without (4/4, nominally slower, far inside the noise) while cache read was 18,075 against 0 and every warm turn wrote 18,075** — mechanism confirmed, setup verified, so the null is an effect size and not a broken condition. **This is a cost win only.** Why it is: TTFT was ~1.4s in BOTH arms, both of which send the same ~19,100 prefill and differ only in billing, so ~19k of prefix is not what that 1.4s is made of and the floor is the fixed cost of getting a request out. **A prompt-size lever aimed at snappiness has nothing to bite on at this scale.** (The older whole-call seconds — 7.5s vs 9.2s at 4 reps, inverting to 8.9s vs 7.2s at 2 — remain unquotable: `CallRecord.seconds` is dominated by output length.) On a turn whose dump did NOT change the split is slightly worse (~2,470 vs ~1,910 billed-equivalent, since the tail is now full-rate input), so the win shrinks as the dump grows; buying both halves would need a second breakpoint the budget cannot afford. **That budget is the other half of this: the split is count-neutral, but there is NO headroom, because mirascope leaks tool breakpoints between requests** — `convert_tool_to_tool_param` is `@lru_cache`d (`encode.py:380`) and `last_tool["cache_control"] = ...` (`:458`) mutates the shared cached dict, so every tool that was ever last keeps its stamp for the life of the process (reproduced: 3 tools in 3 orders → 1, 2, 3 tool breakpoints). Advisor-then-Analyst in one process already sends 4 of 4 (Advisor ends on `discard`, which Analyst carries mid-list while ending on `get_schema`), and `merge_app_tools` appends host tools LAST, so one registered app tool makes it 5 and the API rejects the request. `_normalize_tool_breakpoints` caps it at the real last tool by shallow-COPYING the others without the key — never popping, since that heals an entry aliased into every in-flight request using that tool. The invariant it rests on: `_CONTEXT_SLOT` must stay the LAST section of `system_prompt()` (`TestTheSeamTheSplitDependsOn`) — assert the suffix on `system_prompt()`'s return value only, never on the encoded request, since `providers/base/_utils.py:95-101` appends formatting instructions to system when `format` is set. **The scope limit is the headline: the minimum cacheable prefix is 4,096 tokens on haiku-4.5 — NOT 1,024, and not monotonic across model generations — and under it the provider silently declines and bills full rate without erroring.** Only the Advisor engine clears it; Analyst ~3.5k, Explorer ~2.8k, `transformation_generation` ~1.9k, `aspect_generation`/`statement_classification`/`antithesis_classification` ~0.8k. So `cache_read=0` on every concern call is CORRECT, not a defect, and this fix touches no tool path. Two accounting traps: Mirascope's non-streaming decoder sets `input_tokens = raw + cache_read + cache_write` (`decode.py:99`) while the streaming one does not (`:286`) — hence `CallRecord.uncached_input_tokens`, subtracted once at the recording site; and `None` is a third state distinct from `0` (`None` = the round-trip reported no usage — every tool-loop continuation, and every streamed round whose provider sent no prefill in `message_delta`). Read `CallCensus.calls_with_usage` before any token total.
- Tests use `@traced` from conftest (not bare `@observe()`) for reliable trace naming. **`@traced` serializes the function's args as span input** — never put it on a test taking `monkeypatch` or other cyclic fixtures; the serializer recurses forever and HANGS. Diagnose with `pytest -o faulthandler_timeout=25`.

### Concurrency & Rate Limiting

Optional concurrency semaphore in `utils/concurrency.py` (env `DIALEXITY_MAX_CONCURRENT_LLM_CALLS`; 0/unset = disabled). Applied inside `use_brain`; streaming (`raw_call=True`) excluded.

**Everything in this section lives inside `use_brain`, and the tool loop's `resume()` calls do not go through it.** Both continuation sites are Mirascope's own requests, so a tool-round continuation gets no concurrency slot, no ParseError retry and no generation span; the turn's FIRST call is covered and rounds 2..N are not. **The two paths now differ, and the difference is deliberate.** The AWAITED loop (`submit`) still gets nothing — not even a census record. The STREAMED loop (`submit_stream`) gets transient retry and a census record per round, because its rounds are the ones a person is watching: `_start_stream_round` wraps every open and every resume in `retry_transient`, which is `use_brain`'s own classification and curves (`_transient_kind`, `rate_limit`/`connection`/`server` with their separate budgets) applied by a caller that cannot use the ladder. Concurrency slots are still not taken on either.

Rate-limit retry (429/ThrottlingException) in `use_brain`: 10s base, 2× up to 60s cap, max 10 attempts. **ParseError is FLAT at 2s (`_PARSE_RETRY_DELAY_S`) — the one non-exponential curve, on purpose:** backoff works against congestion, and a wrong response *shape* does not heal while you wait (measured — the old 10s→120s curve slept 750s around 41s of `anchor` work and changed nothing). Nonzero only as back-pressure, since a fan-out stage fails many children at once. Wrong-envelope responses are unwrapped before retrying at all (`_salvage_envelope`); its invariant is that candidate field names come from the model's bytes, never the schema. **Hand-rolled by design — do NOT replace with Mirascope's `llm.retry`/`RetryConfig`** (can't express separate retry curves, per-attempt slot re-acquisition/tracing, or string-based Bedrock throttle detection).

**A streamed round is retried around the open PLUS its first chunk, and that pairing is the whole mechanism.** `await call.stream()` issues no HTTP request (see the streaming bullet above), so the facilitator's old `_open_stream_with_retry` retried local encoding while its docstring claimed to retry connections: a 429 or 503 surfaced inside the chunk loop and killed the turn, on the one path where a person was watching, while `submit()` retried the identical error up to ten times. `_start_stream_round` now pulls the first chunk as part of starting the round and hands it back for the loop to replay (`_replay_first_chunk`), so the failure is caught where it actually arrives. **The throttle budget here is 3 attempts (~30s), not the ladder's ten (~430s)** — see `_RATE_LIMIT_RETRY_MAX`: a person is watching this one, and the consequence, accepted deliberately, is that a sustained throttle fails a streamed turn earlier than an awaited one. `connection` and `server` budgets do match. Retry is on a NEW stream every time — mirascope's `chunk_stream()` caches consumed chunks and drives one underlying iterator, which is spent once it has raised — and re-asking is safe on both entry points (`_get_tools_call` re-renders from `self._messages`; `resume_stream_async` is `response.messages + [user(content)]` with no mutation). **Nothing past the first chunk is retryable**: re-asking would duplicate text already on screen, so a mid-stream failure propagates out of `submit_stream`. Only transient kinds are retried — the old ladder caught bare `Exception` and slept 15s on a malformed request, buying exactly what the flat parse curve buys. **Consequence to keep in mind when touching that loop: opening a round now COSTS a provider round-trip.** It used to be free, which let `submit_stream` end with an unconsumed resume dangling and cost nothing; the same shape now pays for an answer nobody reads, and a throttle on it would raise out of the generator after the reply had already been streamed. So the loop runs `max_tool_rounds + 1` consumptions and refuses to execute tools on the last one, matching `submit`'s "one call plus up to N resumes". **That also fixed three bugs the old shape hid, and they are worth knowing because the same trap is one edit away.** Everything below the loop used to run against the UNCONSUMED dangling round, and an unconsumed mirascope stream reports no tool calls and empty content — so on an overrun streamed turn (a) `_reuse_written_reply`'s pending-tool-calls guard could not fire and the previous round's mid-work narration was returned as the reply with `streamed=True`, (b) `_close_dangling_tool_calls` returned immediately, meaning it had **never fired on the streamed path at all**, and (c) `self._messages` ended on an assistant message whose `content` is a live alias of the stream's empty content list, which the next request 400s on. The exit now costs one extra call (the extraction the reuse guard correctly declines to skip), and an overrun turn streams `TextDelta`s that are deliberately NOT part of `message` — unavoidable, since nothing reveals the overrun until after that text has streamed. Pinned by `tests/test_stream_retry.py`, including the budget ceiling, the resume leg, and the overrun.

**Parallelization points:** `ExplorationPipeline` runs wheels concurrently. `ExploreTransformations` parallelizes edge pairs, Phase 1 edges, Phase 2 candidates, audits (when enabled). `TransformationAudit` gathers its own Ac+/Re+ pair (invisible under the eager path, but it IS the wait on the on-demand `audit_feasibility` path). `AnalysisPipeline` parallelizes `expand_polarities`/`find_polarities`. On the `anchor` path, `IntroducePolarity` gathers its TWO POLES' classification+headline work (`_classify_statement`) and commits them one at a time afterwards (`_commit_statement`, deliberately `def` not `async def` so a future caller cannot gather it) — worth ~5.8s of a ~40s tool; and `AnchorTheses` gathers classification with headlining in ONE gather rather than two sequential ones (worth ~1.0s at most, usually nothing, since `StatementHeadline` short-circuits at `component_length`). Graph writes stay sequential after gather.

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
| `@pytest.mark.seam` | Assembled-system guard for an archive defect | Skipped | Runs |

**Adding or dropping `mark.seam` is a three-file change:** the test, `ROSTER` in `tests/e2e/test_e2e.py`, and the table in `tests/e2e/README.md` — `TestTheSeamLaneRosterIsReal` fails on any drift between them (it caught exactly that).

Default to `@pytest.mark.llm` for anything touching `use_brain` or `ConversationFacilitator`.

**Mock brain** (`tests/mock_brain.py`) auto-constructs Pydantic responses. Does NOT test streaming, tool registration/argument parsing, or provider behavior. Returns **identical** DTOs every call — to test diversity/dedup, `monkeypatch` the concern's `resolve`. Fills `Literal[...]` fields with the FIRST allowed value — order Literals so the first is a safe default.

**Test helpers are shared by importing the sibling module directly** (`from test_dialectical_context import _create_perspective_with_aspects`) — `tests/` is on `sys.path`; there is no helper package.

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
