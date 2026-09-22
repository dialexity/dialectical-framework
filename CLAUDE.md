# CLAUDE.md - AI Co-Developer Guide

## Collaboration Style

Give honest opinions with clear tradeoffs — not agreement for the sake of agreement. State what you actually think is the better approach and why. If both options are defensible, say so directly.

**This file carries rules and the shape of the system. It does not carry measurements.** The reasoning behind a change, the numbers that justified it and the traps hit on the way go to `docs/dev-notes/<topic>.md` (index at the end of this file); bench figures come from `tests/e2e/status.py`, never from prose. When a session learns something, add the RULE here in one or two sentences and the STORY to the dev note.

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

**Cycle vs Wheel:** Cycle = ordered T-causality sequence (which thesis causes which). Wheel = full circular TA-arrangement with transitions (`generate_compatible_sequences`, diagonal symmetry: T_i opposite A_i). Rotated Cycles are rotations of one directed circle; Wheels are rotation-invariant (`WheelRepository.find_by_component_sequence`), so sibling Cycles share Wheel nodes. All scoped by `sid`. The combination path is tuned by six query levers — the per-wheel signature cache, `immutable=True` on `Transition.source`/`target` only, `RelationshipManager.prefetch`, equality `hash_match` on full-length needles, one dedup lookup per `commit()`, and batched `PerspectiveRepository.find_by_statements` — each safe for a stated reason; read `docs/dev-notes/graph-performance.md` before touching any of them. Two invariants from that work: **`Wheel.edges` must NOT be memoised** (transitions attach through a different manager, which the `immutable` flag does not guard), and **`Wheel._perspectives` order is load-bearing** (it becomes `polar_segments`). Reasoning is untouched and structure counts (24 cycles / 96 wheels at k=4) are the evidence for any change on this path.

**Case flow:** Case → Input → Ideas → Statements
**Exploration flow:** Perspectives → Nexus → Cycles → Wheels

See `docs/graph.md` for full data model (positions, transformations, cardinality, layers, intent levels, discarding/editing rules).

### Synthesis Architecture (Wheel-Level)

Synthesis (S+/S-) is a wheel-level phenomenon. One wheel → one S+/S-.

**Circular causality within Transformations:** Each Transformation already encodes both spiral directions — Ac+ (its own edge direction) and Re+ (the opposite edge's direction). A Transformation IS a complete circular causality statement.

**Refinement recursion (`<broader_journey>`, `utils/edge_context.py`):** every generative position in a tetrad is rendered the coarser Transformations its edge descends from and told to be more concrete than them. THREE instructions, not one, because the two rendered lines (`Action:` / `Reflection:`) are refined by different positions: `REFINE_ACTION` for Ac+, `REFINE_REFLECTION` for Re+/Re-, `REFINE_TETRAD` for Ac-. The negatives are bound by VALENCE, not concreteness, so no instruction points one at a coarser line; when one call produces two positions (`ReSideCompletionDto`), an instruction that names neither is an instruction to both. `_score_hs` and the category reframings are deliberately NOT asked. **Being in the context window is not being asked** — never conclude a position is refined from its signature or from history visibility; read the submitted prompt. The parent lookup happens ONCE per edge (`ExploreTransformations._phase1_for_edge`) and travels as `_EdgeProcessingData.parent_context`, which is three-state: rendered hierarchy / `""` = looked up, nothing coarser / `None` = nobody looked. Tests: `tests/test_refinement_context.py`, `tests/probe_transformation_recursion.py`. Story: `docs/dev-notes/refinement-recursion.md`.

**Scaling:** N-PP wheel = 2N edges, N edge pairs. Opposite-edge Transformations are Ac+/Re+ role-swapped (E1's Ac+ = E3's Re+). **Transformations = 2N × |`INSIGHT_CATEGORIES`| = 6N per wheel**: `ActionExtraction` returns one Ac+ candidate per insight category (`concerns/ac_re_taxonomy.py`) and `ExploreTransformations` Phase 2 generates a tetrad per candidate, so each edge carries 3 depth alternatives. 1-PP = 2 edges / 1 pair / **6** Transformations (`tests/test_single_perspective_explore_real_llm.py`). Each Transformation is 4 sequential `TransformationGeneration` calls, + 2 audit calls only when `settings.audit_transformations` is on.

**Discrete spiral:** Wheel edges form a directed circle where each step transforms the minus of one segment into the plus of the next (T1-→A2+→T2-→A1+→...). S+ emerges from ALL Transformations operating simultaneously.

**BuildWheels is purely structural:** builds all valid Cycle/Wheel combinations from the Nexus's Perspectives and estimates them (layer 2+). Never generates transformations — those run separately via `ExploreTransformations`, even for layer-1 wheels.

**OPPOSITE_DIRECTION** on both Cycle and Wheel (`_is_circular_reverse`). Cycle opposites: reversed causality, layer 3+ only. Wheel opposites: reversed circular sequence — at layer 2 a cycle's two wheels oppose each other; at layer 3+ opposites live across opposite-direction cycles (1:1). Each opposite gets its own synthesis.

**Nexus grouping rule:** Prefer perspectives from different polarities (genuine synthesis with opponents). Same-polarity perspectives in a nexus only produce "angle shifts" within the same opposition.

**Max wheel layer (`settings.max_wheel_layer`, default 4, env `DIALEXITY_MAX_WHEEL_LAYER`):** `PerspectiveCombination` caps layers regardless of nexus size — bounds combinatorial explosion.

**Combinatorial growth (layer = PP count):** `C(N,k)` × `max(1,(k-1)!)` cycles × `W(k)` wheels/cycle, W(1..4)=1,2,4,8; 4PP→24C/96W.

### Structural vs Analytical Layers

- **Structural** (Merkle backbone — in parent hashes, immutable after commit): Statement, Polarity, Perspective, Transition, Cycle, Wheel, Nexus. Containers: `save() → add members → commit()`.
- **Analytical** (attached via `AnalyticalStructure` edges — never in parent hashes, connectable even to committed targets): Rationale, Estimation, Synthesis (SYNTHESIS_OF), Transformation (ACTION_REFLECTION), Decision (GROUNDED_IN); CRITIQUES is Rationale→Rationale (no Critique node). Analytical NODES are hash-frozen at commit — layer mutability = add/replace/discard, not edit.
- Mutable-anytime = metadata fields excluded from hashes, on BOTH layers: `digest`, `display_text`, `instruction`/`summary`/`haiku`, `discarded`, `validation`. **Every one of them must also be a term of `CaseRepository.scope_fingerprint()`** — the Advisor re-renders its graph dump only when that fingerprint moves, and a mutable field the fingerprint cannot see is a stale prompt on exactly the turns that change it (`tests/test_context_render_cache.py` holds the list to the node classes).

### Shared Rendering (`graph/rendering.py`)

`build_pp_index(nexus)` is the canonical source of perspective indices — `dialectical_context` and `inspect_node` both use it so T1 always means the same perspective. Indices are stable over the full `nexus.perspectives.all()` ordering (including discarded): gaps appear rather than re-numbering. Helpers: `component_alias`, `format_edge_label`, `format_spiral`, `find_nexus_for_*`.

### Discarding Nodes

`discarded: Optional[str]` on Statement/Perspective/Decision soft-marks a node as excluded from active queries; `discard_uncommitted()` (PerspectiveRepository) deletes uncommitted ones. The `discard` tool unifies both. Replacing a Decision = record new + discard old (reason names the replacement) — no supersede machinery.

### Advisor Tool Constraints

Advisor has `discard` but NO edit tool — re-framing means discard + `anchor` the new version. On user rejection: unscoped Advisor discards silently; advisory-mode (nexus-pinned) head confirms first for exploration members (consent contract), fresh own anchors need no ceremony. To drop a claim: discard the perspective, then its statement (one still used by a live perspective won't discard; discarding a perspective never cascades to shared statements). Tools split by what the LLM knows at call time:
- `ingest` — bulk discovery from material → standalone perspectives (composes AnalysisPipeline)
- `anchor` — plant a specific T/A tension → standalone perspective (IntroducePolarity + ExpandPolarity)
- `explore` — group perspectives into nexus + pathways + synthesis. LAZY: builds+ranks ALL wheels, deep-generates only the top (`EXPLORE_DEEP_WHEELS = 1`) plus the coarser ancestry it refines from (`EXPLORE_REFINE_FROM_COARSER = True`), coarsest rung first; the rest reported as `shallow_wheel_hashes`. Weaves ≤ `advisor_max_perspectives_per_exploration` per call (excess deferred).
- `deepen` — develop a shallow wheel on demand (ExploreTransformations + GenerateSynthesis). The escape from explore's budget when the user's lived reality picks a non-top arrangement. Scoped variant guards wheel-membership in code.
- `audit_feasibility` — score named pathways (Ac+/Re+) for practical achievability on demand. Idempotent (an already-estimated pathway is returned free); capped at `MAX_TRANSFORMATIONS_PER_CALL = 4`, excess named as `deferred`. Shared by both agents; scoped variant guards nexus-membership in code.
- `record_decision` — persist an explicitly confirmed decision (RecordDecision + fail-soft DecisionCoherenceCheck). Consent-first in BOTH modes — the one exception to silent machinery; `_DECISION_READINESS` renders only when wired.
- `sync` — re-read graph state (DialecticalContext); optional `nexus_hash` zooms into one exploration in full depth (no wheel cap).
- `discard`, `inspect_node`, `read_digest` — graph curation and detail reads (shared orchestrator tools)

Full tool contracts as originally written: `docs/dev-notes/advisor-seams.md`.

**ExpandPolarity creates `count` new perspectives per call (default 1),** sequentially, each using `not_like_these` (existing + generated-this-call) for diversity; a pre-existing partial counts toward `count`.

### User-Facing Vocabulary is App-Layer

The graph model uses universal terms (Statement, Polarity, Perspective, T+/T-/A+/A-); user-facing vocabulary lives in app preambles (`agents/apps.py`). System prompts handle tool selection/workflow only — presentation vocabulary and app-UI behavioral constraints (e.g., viewport scope) go in app preambles.

**Surface names are fixed across all agent prompts:** "analysis view" (Analyst), "exploration view" (Explorer), "advisory mode" (exploration-pinned Advisor) — never "thread" or ad-hoc variants.

**Advisor preamble/engine split:** the system prompt is a domain-neutral dialectical engine; persona comes entirely from the app preamble. `apps.py` naming: `*_APP` = framework-owned Navigator contracts (AppSpec composes per head, hosts never pick); `*_PERSONA` = palette for the STANDALONE Advisor only (`AppSpec.advisor_persona`; ignored in advisory toggle). Switching persona = new chat on the same graph; register toggle = same `messages`. Personas carry voice only — no framework terms, no convergence mechanics (`TestAdvisoryPersonaBoundary`). App/Register/Persona/Phase vocabulary: `apps.py` docstring.

### Agent Design Principles

- **Product model — four CATEGORIES of app, not four products** (the framework cannot predict its applications; owner's framing, 2026-09-21; `docs/agents.md` "Choosing what to build"): **Navigator** = Analyst + Explorer (+ the advisory register), a system scientist builds and navigates the wheel at once, in the open. **Advisor on a nexus** = `Advisor(nexus_hash=, messages=)`, an analyst or mediator exploring ONE constellation with assisted reasoning — the surface built for the framework's own claim; benched 2026-09-21 as `A2n` (`nexus-pinned`): indistinguishable from the Consultant on the same graph, a resolved loss to its static dump, no build tool elected inside the pin. Three live heads lose to the same dump by overlapping margins, so the open variable is the engine prompt plus the tool turn, not building. **Advisor from scratch** = `Advisor(app=)`, a mediator's client resolving an issue with a dialectically thinking LLM; builds silently and **collapses into the previous category** once it has a nexus to dive into (`Advisor(nexus_hash=, app=, persona=True)` keeps the persona and hides the machinery over the pin); the benched arm measures the on-ramp only. **Consultant** = `Advisor(mode=CONSULTANT)`, a person talking to a graph something else built — typically the headless builder (`AnalysisPipeline` → `CreateNexus` → `ExplorationPipeline`, or `run_exploration_detailed`; documented under that heading). `VIEW` is an access level, not a category.
- **Ceiling-not-floor:** the framework must improve the LLM's reasoning, never drop below a bare persona-prompted model. `tests/e2e/README.md` carries the ablation ladder (A0/A1/A1.5/A1.7/A2) and what each rung isolates; `test_advisor_e2e.py` is the collapse tripwire.
- **Lived reality outranks the plausibility score:** when the user gravitates to a non-top causal reading, follow (deepen it), don't argue from %.
- **Prune, don't instruct:** pre-computed filtering of context beats prioritization rules the model must self-apply.

### Agent Ownership

- **Analyst** = everything up to and including nexus creation (inputs → statements → polarities → perspectives → `create_nexus` handoff). `create_nexus` lives here only — Explorer never creates nexuses.
- **Explorer** = everything after nexus (nexus-scoped: cycles → wheels → transformations → synthesis). Constructed with `nexus_hash`. Carries `create_dx_input` to START the round-trip: capture a Transition insight as a dx:// Case Input → Analyst develops it → `expand_nexus` weaves back. **Its depth is LAZY by toolset, not by cap:** `build_wheels` (structural, ALL wheels — cheap) + `explore_transformations` (the one wheel the user picked); it never runs `ExplorationPipeline`. `ExplorationPipeline(max_deep_wheels=None)` deepens EVERY wheel and is a headless batch default — headless callers bound k. **Cross-wheel Transformation reuse is structurally ZERO** (`Transition`'s hash carries a `uuid4` nonce; `find_by_edge` matches internal node id), so widening `EXPLORE_DEEP_WHEELS` pre-pays exactly what `deepen` costs on demand and buys no efficiency. A tool nobody registered is still a trap while a test lists it among the real ones — check the toolset, not the prose.
- **Advisor** = pure-conversation agent, framework runs silently (no terminology exposed). Composes both pipelines via `ingest`, `anchor`, `explore`, `deepen`, `sync` (+ shared `inspect_node`, `read_digest`, `discard`, `audit_feasibility`). System prompt is a FUNCTION `system_prompt(tool_names, scoped_nexus_hash)` — tool docs render only for wired tools; it has FOUR render shapes (full, scoped, consultant, view), the narrow two DERIVED from the names: `view = not (names & _WRITE_TOOL_NAMES)`, `consultant = not view and not (names & _BUILD_TOOL_NAMES)`.
- **`Advisor(mode=)`** (`agents/advisor/mode.py`) = FULL / CONSULTANT / VIEW. The axis is BUILDS STRUCTURE vs DOES NOT, never read vs write: the build tools (`_BUILD_TOOL_NAMES` = ingest, anchor, explore, deepen) are what cost minutes; `record_decision`, `discard` and `audit_feasibility` are writes that add no structure, so the CONSULTANT keeps them and the VIEW keeps only the three reads. **Enforced by toolset and by the closing seam, never by prompt** (tool-election instructions measurably do not hold — `anchor` 6/6, `explore` 2/6, `deepen` 0/6 — so a "prefer reading" preamble would give stochastic latency). VIEW: `_repair_unrecorded_decision` returns before the classifier, both `TurnTiming` outcome fields stay `None`, a person who decides here gets NO record. CONSULTANT: the seam records and grounds on EXISTING pathways, and `_schedule_pathway_construction` returns `DeferralOutcome.NOT_BUILDING` BEFORE the sid-keyed queue is touched (so a FULL instance resuming the sid cannot weave on its behalf). `_settle_deferred_work` and `_refresh_context` still run on every surface; `app_tools` are still merged. Both narrow shapes fork `_EAGER`/`_TOOLS_INTRO`/`_REJECTION_HANDLING`/`_scope_section`, drop `_DEFAULT_ARC`, and end on a mandate placed LAST. `tests/test_advisor_modes.py::TestTheListsAreOne` is the only thing holding the two name sets and the three toolset factories together; `TestTheGateHasThreeSites` pins that `self._mode` is read in exactly `__init__`, `_repair_unrecorded_decision`, `_schedule_pathway_construction`.
- **Apps plug in via `app=`** (an `AppSpec`, `agents/app_spec.py`) — pieces `voicing`/`advisor_persona`/`tool_guide`/`tools`; each head composes its own preamble. ONE AppSpec per app, passed to EVERY head. **`advanced=` is a per-SESSION property of the person, not an AppSpec field** — pass the SAME flag to every head so the register carries across the Explorer↔advisory toggle; it raises where no AppSpec composes the preamble. Manual layer: `app_preamble=`/`app_tools=` (mixing with `app=` raises). Tools merge via `agents/toolsets.py::merge_app_tools` (append; shadowing a built-in raises; system prompts skip unknown names).
- **Advisor(nexus_hash=...)** = advisory mode of the Explorer↔Advisor session toggle by default: host hands `messages` + `nexus_hash` between heads; preambles `NAVIGATOR_APP_ADVANCED_TOGGLE` ↔ `NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER` (or the `_ADVANCED` pairing under `advanced=True`). The two counsel registers share ONE body (`_ADVISORY_REGISTER`); the advanced trailer must stay LAST. **`persona=True` on a pinned Advisor keeps the app's `advisor_persona` instead** — the standalone head continuing inside the exploration it built, machinery still hidden, same scoped tools and engine. Per-session like `advanced` (which it excludes: nothing to unlock) — a silently dropped flag is the defect, so it raises with no `app=`; ignored without a pin (`tests/test_app_spec.py::TestAPinnedAdvisorCanKeepItsPersona`). Nexus pin enforced by tool closures (`advisor/tools/scoped.py`), not prompt. **The pin protects other EXPLORATIONS, not everything outside the pinned one:** members of other nexuses are refused and reduced to a count line; a perspective attached to no exploration (what `anchor` plants here) is fully readable and writable. Render and tool guards must say the same thing. See `docs/agents.md` Handoffs.
- **"Framework runs silently" is a PROMPT ASPIRATION, and it is a WEAK-MODEL failure**: archive-wide (2026-09-22) Haiku leaks in 145 of 1,331 replies (hashes cited in 0.4%, bare labels in 1.5%) and Sonnet 5 in 3 of 484 (no hash, no label ever). The leak is machinery-as-actor ("the framework found…") and bare position labels in prose, NOT vocabulary — a fix that adds banned words is aimed at the wrong 2%, and prompt enforcement scales with compliance, not intelligence. **The one shape the framework strips deterministically is the `[[hash]]` address** (`agents/advisor/reply_hygiene.py`): never legitimate in person-facing text, removed on BOTH entry points — a streaming filter equal to the regex over every chunking, so `ResponseComplete.streamed` stays byte-for-byte true — wherever the composed preamble does not grant terminology disclosure (`Advisor._hides_hashes`; the Navigator's advisory registers are exempt, hashes are the person's own addresses there). History is not filtered. Bare labels cannot be stripped without breaking the sentence, and narration cannot be regexed; both stay prompt-level. `score_machinery_leak` is the contract, `score_machinery_leak_unambiguous` the evidence; print both or neither. Figures, shapes and the 2026-09-17 scorer correction: `docs/dev-notes/advisor-seams.md`.

### Advisor Runtime Budgets (settings, Advisor-only)

Five knobs bound the silent Advisor (`settings.advisor_*`, env `DIALEXITY_ADVISOR_*`; Navigator agents ignore all):
- `advisor_polarity_quality_min_hs` (0.5), `advisor_perspective_quality_min_sp` (0.3), `advisor_perspective_quality_min_dv` (0.3) — standalone perspectives below floors (or failed validation) are SUPPRESSED from the context dump with a count line. Nexus members exempt; unscored never suppressed. SP+DV pair mirrors the paper's acceptance criterion as soft pruning.
- `advisor_wheel_quality_top_plausible` (3) — wheels per cycle in the unscoped dump (advisory-mode dumps exempt).
- `advisor_max_perspectives_per_exploration` (2) — per-explore-call weave cap (excess deferred+reported; bounds turn latency, orthogonal to `max_wheel_layer` which bounds structure size).

The Advisor's prioritization prompt says "pre-pruned, rank within it" — changing floors requires reconciling it (`TestContextDumpPrePruned`).

**Three non-`advisor_*` behavioural knobs**, all applying to both agent paths: `audit_transformations` (False — the EAGER feasibility pass; the `audit_feasibility` tool and the closing drain audit regardless), `automatic_feasibility_audit` (False = manual — a MODE, not an off switch: it chooses who initiates, the tool stays wired; the prompt names the two elective moments, the closing and the wobble, and the closing moment is never a gate), and `extraction_step2_carries_source` (True, below). An unaudited wheel is finished, not partial; a missing feasibility band means *not estimated*, never *low*. Tests: `tests/test_transformation_audit_optional.py`, `TestTheFeasibilityAuditIsAMode`, `TestTheElectiveRouteNamesItsMoments`.

**The closing weave runs OFF the turn.** A decision closes on pathways, and the model reliably skips every deepening step, so `Advisor._schedule_pathway_construction` STARTS the weave (`asyncio.create_task` inside the turn's scope) rather than advertising it; the record is written on the turn and grounded on the pathway when it lands, by captured HASH (GROUNDED_IN is analytical). Bounds: single flight, `_MAX_WEAVE_ROUNDS = 4`, a no-progress check, **and it yields**: `_settle_deferred_work` marks the sid's `_DeferredWork.waiting` while a turn is blocked on the task, and the weave stops after the round in flight when it sees the flag (a measured 367s wait on the turn after a closing, `thinking-off`, is what this bounds; the round in flight always finishes, so the one-writer invariant holds). **The task and its queue are keyed by SID in the module-level `_DEFERRED_WORK`, not held on the Advisor** — a stateless host makes one instance per request. Obligations: `chat`/`chat_stream` wait for an in-flight weave before starting (ONE WRITER PER SID; recorded as `TurnTiming.deferred_wait_s`), and `wait_for_deferred_work(timeout=None)` is a HOST obligation at shutdown (bounds the wait, never cancels the work). **A closing on an EMPTY graph is anchored first:** the off-turn task plants the decision's own stance as a thesis (`_anchor_when_empty` → `anchor(thesis=stance)`), prices it (the stance IS the thesis, so its cost is that tension's T-, attached as `accepted_cost`), then weaves and grounds as usual — only when no active perspective exists, only the first resolvable decision, only where the task exists (FULL). The shape it repairs: 5% of weak-tier first sessions built nothing and the record rested on nothing (`TestAClosingOnAnEmptyGraphIsAnchoredFirst`). **One decision, one record, at two layers:** `DecisionConfirmationCheck` is shown the standing ledger and names the record a confirmation merely re-affirms (`reaffirms_decision_hash` → `ClosingOutcome.REAFFIRMED`, nothing written, nothing scheduled — three consecutive "write that down" turns used to be three records and three weaves), and `RecordDecision` returns the standing record for an exact active question+stance repeat instead of writing again (the model called the tool twice in one turn). The Decision NODE still never dedups — its nonce makes a re-decision after a discard a new speech act. **A price shared only between sibling READINGS of one polarity is located by the framework, not refused:** `RecordDecision._locate_shared_price` adds the reading as a plain ground when every candidate sits on one T/A pair (`nexus-pinned` measured Rule B's refusal at 11 of 16 tool calls, three to five identical retries per closing); different polarities still refuse, because there the tension itself is the guess. After the drain, `_audit_adopted_pathways` scores the ONE pathway each closing adopted, read from the GROUNDS edge. A decision rests on FOUR grounds — price (`accepted_cost`), tension, recipe (`adopted_pathway`), and the ARRANGEMENT (its Wheel, a plain ground selected by `_select_deep_wheels`' rule: deepest layer, then highest causality P). Tests: `TestDeferredPathwayConstruction`, `TestOneWriterPerSidSurvivesAFreshAdvisor`, `TestTheAdoptedRecipeIsScored`, `TestBothClosingBranchesDefer`, `TestTheArrangementIsGroundedToo`, `tests/test_pathways_seam_real_llm.py`. Story and measurements: `docs/dev-notes/advisor-seams.md`.

**Policy is not config.** If no deployment would ever set a value, encode it as a module constant with the rationale in a comment (`EXPLORE_DEEP_WHEELS = 1`, `EXPLORE_REFINE_FROM_COARSER = True` in `advisor/tools/explore.py`). Audit for new settings: "who sets this, ever, to what?"

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

**The full suite takes ~40 minutes — background it** (~2,600 tests, mocked). Run ONE graph-touching pytest at a time: concurrent runs against the single Memgraph deadlock, and a killed run leaves it wedged so the next one needs `docker compose -f docker-compose.test.yml restart`. A backgrounded pytest redirected to a file leaves that file EMPTY until it exits, so poll `pgrep -f "bin/pytest"` rather than tailing the log. Scope to a path or `-k` while iterating; the 40 minutes is for the pre-commit run.

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

**The rule governs the LIBRARY (`src/`); `scripts/` sits OUTSIDE it deliberately**, because its two Cypher-writing scripts (`cleanup_stale_nodes.py`, `cleanup_degenerate_cycles.py`) exist to do the two things a repository must never do — reap uncommitted nodes across cases, and delete committed structure. Neither belongs behind a repository method. What this does NOT license is a third script that merely finds a repository inconvenient: the test is whether the query is impossible to express under the rule.

**Hash lookups accept a PREFIX, and the predicate is chosen by the needle's LENGTH.** Any query taking a caller- or LLM-supplied hash goes through `hash_match` (`graph/repositories/node_repository.py`) so both forms the framework hands out are usable: the full hash on creation, and `short_hash` wherever a hash is rendered into a prompt. Ambiguous prefixes raise rather than guess. A full-length needle is compared with `=` (a point lookup on `Node(hash)`; all hashes are the same length so it selects the same nodes as `STARTS WITH`), short needles with `STARTS WITH`. Never hand-write either predicate at a call site. In-process comparison of two full hashes stays exact. `tests/test_hash_lookup_predicate.py`.

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

**Uncommitted node safety (`saved_at`):** `save()` sets `saved_at`; `commit()` clears it. `saved_at != NULL, hash == NULL` = actively building or abandoned garbage. All listing/discovery queries MUST filter `WHERE n.hash IS NOT NULL` — and **when an invariant is about node state, enumerate every way the node is REACHED, traversals included** (`cycle.wheels.all()` rendered an abandoned wheel into the counsel prompt as `### Wheel [[None]]`; repository greps could not find it). Cleanup: `scripts/cleanup_stale_nodes.py --max-age 86400`, which nothing schedules — wiring the reaper is the host app's job. Tests: `test_uncommitted_wheel_visibility_graph.py`, `test_layer_visibility_graph.py`.

**No node records WHICH hashing recipe produced it — an accepted, unowned gap.** The first change to `compute_hash()` or any `_collect_structure_hash_parts()` makes identical content hash differently from what a live database holds, and nothing errors: dedup stops matching and Merkle claims silently stop verifying. Treat any edit to those methods as the trigger to build the version stamp FIRST (one integer at commit plus a guard in `commit()`).

**Event reporting:** `commit()` emits no SSE events. When it creates relationships internally (e.g., `Polarity.commit()` creates T/A edges), the calling skill emits `relationship_created` per edge. Save-then-commit containers emit split events: `report.node_created(node)` after `save()`, `report.node_committed(node)` after `commit()`. Atomic-commit nodes emit one `node_created` with both set.

**Two channels per scope, and `Effect` stays a mutation.** `sid` carries `GraphEvent(effect=…)`; `sid:progress` carries `ProgressEvent` (`events/progress_event.py`). Long chains that write no node until they finish report via `utils/progress.py`: `progress_scope(stage, key=…)` around the work, `report_progress(detail)` per step, `expect_progress(n)` to grow the denominator, `note_progress(detail)` for a gathered call returning, `flush_progress()` immediately before a fully synchronous stretch. No-op with no scope installed. **Never widen `Effect`/`EffectType` for progress.** Rules that hold at every site:
- **The seam only fires where a scope was installed** — a mute path is a missing `with`, not a missing `report_progress`. Every tool that does provider work installs one at the TOOL, above any gather it creates (a task created before the scope is installed reports nothing).
- **The outermost scope owns the stream**: a nested `progress_scope` folds its `total` into the installed one and publishes no `final`. One tool call = one stage, one key, one `final`.
- **Stage names are the noun of the WORK, never the tool's name** (`anchor`, `ingest`, `analysis`, `decision`, `deepen`, `synthesis`, `transformation`, `feasibility`, `edit`, `opposition`, `extraction`, `expansion`, `exploration`); `stage` and `detail` are host-visible, so no framework vocabulary in either. The closing `final` event carries an EMPTY `detail`.
- **Keys**: `progress_key(*parts)` (sha256) where the argument is the person's own text; `progress_hash_key(raw)` (bracket-sanitised short hash) where it is already a hash; sanitise lists into a SET before keying. A key built from a tool argument is raw model output.
- **Declare each step at its own site, never up front**; report inside the semaphore; indices only, never source content; `done` counts steps ANNOUNCED, not completed; a fraction shown to a person is a promise about the whole, so a window that does not know the whole may not make one.
- **Pluralise only where the singular is reachable.** One operation has ONE label (`placing_candidates_label`, `AUDITING_LABEL`).
- A concurrent fan-out whose children narrate their own steps will duplicate its own first label; that is accepted (three recorded instances) — do not "fix" a fourth without a new argument.

Instrumentation history, live measurements, and the per-tool findings: `docs/dev-notes/progress-channel.md`. Tests: `tests/test_progress.py`, `test_ingest_progress.py`, `test_tool_progress_scopes.py`, `test_explore_progress_scope.py`, `test_edit_progress.py`, `test_decision_progress.py`, `test_analyze_progress.py`.

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

**The application owns Case creation; the framework only reads scope.** Nothing in `src/` creates a Case, and nothing should. `AddInput`/`CreateDxInput` refuse via `CaseRepository.require_for_current_scope()`, which distinguishes **no sid in context** (`MissingScopeError`) from **sid set but no Case** (`ValueError`) — keep them distinguishable. Agent chat entry points guard with `require_current_sid()`.

### Input Digest (Living Understanding)

`Input.digest`: mutable field (excluded from hash) storing LLM-generated understanding of a source. Populated by `SourceDigest`; content <1500 chars skips the LLM. **A source larger than one prompt is READ IN PARTS** (`utils/chunking.py`, `CHUNK_SIZE = 40_000`): one reading per part, then one reduce; coverage is the guarantee. Fitting sources keep the single-pass prompt byte-for-byte; each part gets a FRESH `ConversationFacilitator`; media is never chunked (branch on TYPE, not size). Whoever adds the input, digests it — via `ensure_digest()` (`concerns/source_digest.py`), which takes a **hash, not the node** (`commit()` returns the caller's fresh object on a dedup hit). `refresh=True` only where there is a fresh intent (`ingest`).

**Consumption:** skills use `input_context()` (`utils/input_context.py`) — digests in `<Input id="{hash}">` tags, falling back to content. **Bounded**: `INPUT_CONTEXT_BUDGET` (24k chars) shared across Inputs by water-filling; a cut announces itself. Exception: `surface_theses` needs raw content, so it **SWEEPS**: chunks the source, runs `ThesisExtraction.extract_candidates` per window (`MAX_CONCURRENT_WINDOW_SWEEPS = 3`), merges in document order, then ONE `classify_candidates` over the survivors, each candidate classified against its own window. Extraction has no query, so retrieval is the wrong tool here. Tools: `read_digest` | `read_input` | `digest_input`.

**`settings.extraction_step2_carries_source` (True) is a DECLINED lever — closed, not a to-do.** Step 2 re-sends the whole window once per extracted item (75% of a large ingest's tokens), and the elided arm saves 6.7x, but four A/B runs returned a different faithfulness verdict each time; the default stays because no stable positive result exists, NOT because the elided arm was shown worse. Three lessons: the decision metric must be the fields the code branches on; a pairwise LLM judge carries set SIZE and POSITION as nuisance variables, prefer an unpaired per-item rating; a verdict is provisional until it reproduces. **OPEN and bigger: ~35-39% of what step 2 emits is not cleanly supported by its own source, 13% invented outright** — the instrument (`tests/e2e/probe_support_validity.py`) is validated (specificity 93%, sensitivity 100%), `invented` needs no correction, `distorted` over-reads compression. This is a real extraction-quality defect. An instrument that emits a rate must persist per-item verdicts. Full record: `docs/dev-notes/ingest-and-extraction.md`.

**Multimodal seam (#35):** `InputResolver.resolve() -> str` (text-only, safe to f-string) vs `resolve_native() -> UserContent` (opt-in). `SourceDigest` is the SOLE `resolve_native` consumer — one vision pass emits a text digest, downstream stays text. Never widen `resolve()` to return media (text callers would silently stringify it). `ConversationFacilitator.submit`/`submit_stream` accept `UserContent`.

### Antithesis Persistence Checklist

`AntithesisClassification` returns Mode/Arousal but creates no DB nodes — the caller persists via `EstimationManager.upsert_estimation()` (`AntithesisExtraction` does this internally).

### Model Provenance is Rationale-Only

Only `Rationale.agent` tracks generating model (`<provider>/<model>`, auto-filled from settings; sentinel `"human"` = user-confirmed content). Other nodes trace provenance through their Rationale — intentional, don't "fix" by adding `agent` elsewhere. **`"human"` is never a DEFAULT anywhere:** `Advisor(principal=...)`/`RecordDecision.resolve(principal=...)` default to `UNATTESTED_PRINCIPAL = "agent:unattested"`; a host with a real person passes `"human"` explicitly, an automated one `"agent:<name>"`. The ledger renders nothing for an `agent` outside `human`/`agent:*`, so the placeholder stays in the `agent:` family.

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
- Structured results enter history via `ConversationFacilitator._assistant_history_text` — DTOs with a `message` field store the plain text, never the Pydantic repr. `mock_brain` delegates to the same helper.
- **A conversation turn is ONE provider call, not two.** `_reuse_written_reply` builds the response model from `response.text()` when the turn is finished; the structured call is the FALLBACK (pending tool calls, a response model that is not exactly one required `str` named `message`, or no readable text). Adding a second field to an agent's `ChatResponse` silently re-costs every turn (`tests/test_reply_reuse.py`).
- **On the streaming path the reply is BUILT from the yielded deltas, and `ResponseComplete.streamed` says so.** False = render `message` yourself. Text yielded BEFORE a `ToolStart` is narration, never part of `message`. The bench calls `chat()`, so preamble leaks are invisible to `score_machinery_leak`.
- **Two probe-only instruments answer "why was that slow?"**: `utils/retry_accounting.py` (work vs retry sleep) and `utils/call_census.py` (`provider_s` = cost, `busy_s` = latency). Both hold a MUTABLE accumulator in a ContextVar and are a STACK. **The census does NOT see the tool loop's continuation calls** (`response.resume` is Mirascope's own request), so never classify a turn by its call count — `last_tool_calls` on the facilitator is the authoritative "did a tool fire" signal.
- **Extended thinking is a TOOL-PATH property, and a PER-SESSION one.** `settings.conversation_thinking_level` (env `DIALEXITY_CONVERSATION_THINKING_LEVEL`, default off; renamed from `DIALEXITY_THINKING_LEVEL` 2026-09-19, no alias) is the deployment default; every head takes `thinking=` (like `advanced=`: the person's own toggle, pass the same value to every head; `None` = off, not given = settings) and it is passed by `_call_with_tools` only; `_call_with_response_model` never thinks by default. Concerns never think; they get their own MODEL instead (next bullet). Model-conditional: on Sonnet 5 "medium" is close to free and close to a no-op, and the Consultant's turn there is tool round trips, not thinking (`sonnet-thinking`). So a configured level makes every agent turn with tools wired think (~450 hidden output tokens and ~6s a turn at `medium` on haiku) while every structured concern call and every tool-less conversation does not. Measured: with it unset both Advisor arms answer at the static dump's ~6s and elect no fewer tools (`thinking-off`); what it buys in judged counsel quality is unmeasured. Any latency or quality comparison across the two paths must state the level — the bench records it on every cell (`RunRecord.conversation_thinking_level`) since 2026-09-18 and did not before. `CallRecord.output_tokens` is what tells hidden generation from reply length.
- **Two models, one seam.** `settings.ai_model` (`DIALEXITY_DEFAULT_MODEL`) runs the conversation; `settings.reasoning_model` (`DIALEXITY_REASONING_MODEL`, unset = same model) runs every STRUCTURED call, routed in `use_brain` by call shape (`format=` → reasoning model) so no concern knows. Measured reason: the extraction concern's unsupported-claim rate is 34.6% on Haiku 4.5 and 7.0% on Sonnet 5 with identical prompts — the model is the lever. The bench's `using_model` sets both to the tier. No thinking knobs on concerns: thinking on the extraction concern was priced on both tiers and bought nothing (`probe_extraction_thinking_ab.py`), and its setting was removed the day after it was added. What remains is capability, not config: `ConversationFacilitator(format_mode="json", thinking=level)` can make a structured call think (the default forced-tool mode cannot; JSON parses 4/4 at less prefill; strict is unsupported on Bedrock) — no caller, kept tested for the day a concern needs it (`tests/test_structured_thinking.py`, `tests/test_reasoning_model.py`).
- **Turn timing**: `CallRecord.first_token_seconds` (per round, the only figure a prefill cache can move) and `TurnTiming.first_delta_s` (the person's wait on a blank screen, a PREFIX of `reply_path_s`) answer different questions — never average them. With `DIALEXITY_CONVERSATION_THINKING_LEVEL` set, `first_delta_s` tracks the first thinking chunk; say which way it was set. A streamed turn's seconds are recorded on EVERY exit (epoch-guarded `finally`); `_release_round` closes both `start.chunks` and `stream._chunk_iterator`; `chat_stream` holds `ResponseComplete` and yields it LAST, after the closing work, so a host's `break` on it costs nothing — only a mid-stream exit remains a host obligation (close, don't `break`). `TurnRecord` timing fields are `Optional`, `None` when untimed: **a zero is a claim**, and a reader that coerces with `or 0.0` reinstates the bug. Tests: `tests/test_stream_ttft.py`, `test_turn_finalization.py`, `test_turn_record_timing.py`.
- **Prompt caching is a COST win only.** `split_system_for_cache` (`utils/bedrock_provider.py`) splits the Advisor system block at `CACHE_SPLIT_SENTINEL = "\n\n## Current Understanding\n\n"` so the breakpoint sits on the stable head, not the graph dump (6.8x cheaper prefill; TTFT unchanged). `_CONTEXT_SLOT` must stay the LAST section of `system_prompt()` (`TestTheSeamTheSplitDependsOn`; assert on the function's return, never the encoded request). Mirascope leaks tool breakpoints between requests (`lru_cache`d tool params), so `_normalize_tool_breakpoints` caps them at the real last tool by shallow copy, never pop. Minimum cacheable prefix is 4,096 tokens on haiku-4.5 — only the Advisor engine clears it, so `cache_read=0` on concern calls is correct. `None` usage is a third state distinct from `0`; read `CallCensus.calls_with_usage` before any token total.
- Tests use `@traced` from conftest (not bare `@observe()`) for reliable trace naming. **`@traced` serializes the function's args as span input** — never put it on a test taking `monkeypatch` or other cyclic fixtures; the serializer recurses forever and HANGS. Diagnose with `pytest -o faulthandler_timeout=25`.

Full streaming, timing, caching and retry record: `docs/dev-notes/streaming-latency-and-retry.md`.

### Concurrency & Rate Limiting

Optional concurrency semaphore in `utils/concurrency.py` (env `DIALEXITY_MAX_CONCURRENT_LLM_CALLS`; 0/unset = disabled). Applied inside `use_brain`; streaming (`raw_call=True`) excluded.

**Everything in this section lives inside `use_brain`, and the tool loop's `resume()` calls do not go through it.** The AWAITED loop (`submit`) gets nothing on rounds 2..N — no slot, no ParseError retry, no census record. The STREAMED loop (`submit_stream`) gets transient retry (`retry_transient`: `use_brain`'s own classification and curves) and a census record per round, because its rounds are the ones a person is watching. Concurrency slots are taken on neither.

Rate-limit retry (429/ThrottlingException) in `use_brain`: 10s base, 2× up to 60s cap, max 10 attempts. **ParseError is FLAT at 2s (`_PARSE_RETRY_DELAY_S`)** — backoff works against congestion, and a wrong response *shape* does not heal while you wait. Wrong-envelope responses are unwrapped before retrying (`_salvage_envelope`; candidate field names come from the model's bytes, never the schema). **Hand-rolled by design — do NOT replace with Mirascope's `llm.retry`/`RetryConfig`.**

**A streamed round is retried around the open PLUS its first chunk** (`_start_stream_round`, `_replay_first_chunk`), because `await call.stream()` issues no HTTP request. Throttle budget there is 3 attempts (`_RATE_LIMIT_RETRY_MAX`), not the ladder's ten — a person is watching. Nothing past the first chunk is retryable. Opening a round COSTS a provider round-trip, so the loop runs `max_tool_rounds + 1` consumptions and refuses to execute tools on the last one. `tests/test_stream_retry.py`.

**Parallelization points:** `ExplorationPipeline` runs wheels concurrently. `ExploreTransformations` parallelizes edge pairs, Phase 1 edges, Phase 2 candidates, audits (when enabled). `TransformationAudit` gathers its own Ac+/Re+ pair. `AnalysisPipeline` parallelizes `expand_polarities`/`find_polarities`. `IntroducePolarity` gathers its two poles' classification+headline work and commits them one at a time afterwards (`_commit_statement` is deliberately `def`, not `async def`). `AnchorTheses` gathers classification with headlining in ONE gather. Graph writes stay sequential after gather.

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

**The annotations only reach integrators because of `src/dialectical_framework/py.typed`** (PEP 561). It is an empty file Poetry ships automatically; `tests/test_packaging.py` guards it against a delete. Not in the published 1.8.1 — typing support starts with the next release.

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

**The two event buses are CLASS/MODULE globals wired once by a SESSION-scoped fixture, so `set_event_bus(None)` in a `finally` is a leak, not a teardown.** Save and restore the PREVIOUS value (`previous = ExecutionReport._event_bus` / `progress_module.set_event_bus(previous)`), and a test that subscribes should assert its own wiring first — "nothing arrived" is indistinguishable from the defect such a test exists to catch.

**Mutation-test anything that pins behaviour**, and `touch` a source file after restoring it from a backup copy — a same-size restore with an older mtime leaves Python running the mutant's stale `.pyc`. More traps: `docs/dev-notes/testing-traps.md`.

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
| `agents/apps.py` | User-facing vocabulary/framing (NAVIGATOR_APP, NAVIGATOR_APP_ADVANCED_TOGGLE, the two counsel registers, advisory personas) |
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
| `docs/agents.md` | The three agents, their tools, handoffs, and the host obligations |
| `docs/theory/` | Theory→implementation wiki: every Structured Dialectics claim mapped to its encoding site with status (implemented/partial/absent/diverges). Gaps may carry `**Tracked:** #NN` linking a GitHub issue (orthogonal to status — see `index.md`). Maintained by `/df-sync-theory` — consult it instead of the theory PDFs; keep it synced when implementing theory-encoding code. Start at `index.md` (status ledger + standing cautions). |
| `tests/e2e/README.md` | The bench: ablation ladder, lanes, what keeps the comparison honest. Numbers: `tests/e2e/status.py`. Rounds: `tests/e2e/rounds.md`. |

**The host-facing doc claims are PINNED BY TESTS** (`tests/test_documented_host_seams.py`), because nothing in `src/` depends on the docs being right: the bus payload is on `event.message`; `publish` before `await bus.connect()` is a SILENT no-op; the default resolver returns a URL verbatim; `agent.messages` serializes losslessly with `dataclasses.asdict`. Failure messages name the doc to update. Grep the repo, not the package, before claiming something does not exist (`scripts/cleanup_stale_nodes.py` is the reaper `src/` never reads back).

### Dev Notes (`docs/dev-notes/`)

Lab-notebook material moved out of this file on 2026-09-18: the reasoning behind each change, the measurements, the retractions. Read the relevant one before touching its area; add to it, not to this file, when recording a finding.

| Note | Covers |
|------|--------|
| `graph-performance.md` | The six `build_wheels` query levers, what each one is safe on, the probe counts |
| `graph-invariants.md` | Repository rule scope, `hash_match`, uncommitted-node visibility, hash-recipe gap, Case ownership |
| `progress-channel.md` | Every instrumented tool, the live ingest/explore runs, notes vs steps, the accepted duplicate-label class |
| `streaming-latency-and-retry.md` | Reply reuse, streamed turn finalization, census and timing instruments, prompt caching, the retry ladders |
| `advisor-seams.md` | Tool contracts, Explorer laziness, the read-only surface (now `mode=VIEW`) and the advisory register, the machinery leak, feasibility audit mode, the off-turn weave, decision provenance |
| `refinement-recursion.md` | Which positions refine from coarser layers and why the negatives do not; 6N cardinality |
| `ingest-and-extraction.md` | Chunked digest, the extraction sweep, the declined step-2 lever, extraction faithfulness |
| `testing-traps.md` | Suite runtime, bytecode trap, event-bus leak |
| `host-integration.md` | `py.typed`, the pinned doc claims |
