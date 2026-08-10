# Systemic Prompt Map — dialectical-framework

Reference catalog for **Altitude 2 (assembled)** and **Altitude 3 (systemic)** prompt review.
Load this when a prompt edit could interact with text assembled elsewhere, with the encoded
theory, or with the pipeline chain the prompt sits in.

**Line numbers are snapshot hints (as of 2026-07), not contracts.** Every entry leads with a
grep-able symbol or phrase — verify location before relying on a number. Paths are relative to
`src/dialectical_framework/`.

---

## 1. Assembly maps — what co-occurs in one context window

A single LLM call's context is *assembled* from separately-authored layers. Editing one layer
changes the meaning of the others it lands beside. Two assembly shapes exist.

### Stack A — Conversational agent (Analyst / Explorer / Advisor)

The system message is built at **agent construction time** as `"\n\n".join([app_preamble, SYSTEM_PROMPT])`,
installed via `ConversationFacilitator.set_system_prompt` (`agents/conversation_facilitator.py`, `set_system_prompt`).
The model sees **one fused system block** — it cannot tell where the preamble ends and the workflow prompt begins.

```
[ app_preamble ]              agents/apps.py  (NAVIGATOR_APP / NAVIGATOR_APP_ADVANCED_TOGGLE / COUNSELOR_PERSONA / ...)
   + "\n\n" +
[ agent SYSTEM_PROMPT ]       agents/{analyst,explorer,advisor}/system_prompts.py
   ↓ set_system_prompt → _messages[0]
[ system ][ history... ][ user turn ]
   ↓ use_brain(tools=, thinking=)   utils/use_brain.py
   → provider
```

- Analyst: `analyst/analyst.py` `_build_system_prompt` — `NAVIGATOR_APP`/`NAVIGATOR_APP_ADVANCED_TOGGLE` + `SYSTEM_PROMPT` constant.
- Explorer: `explorer/explorer.py` — system prompt is a **function** `system_prompt(nexus_hash, nexus_intent)`
  (`explorer/system_prompts.py`) that f-string-injects the live nexus hash/intent (DB read at construction)
  **and** renders `INSIGHT_SCALE`/`PROACTIVENESS_SCALE` via `_ladder()`.
- Advisor: `advisor/advisor.py` — preamble + engine prompt with `{dialectical_context}` **string-replaced**
  by a live graph dump (or a "fresh conversation" fallback), landing at the tail of the system prompt.
  The engine is now a **function** `system_prompt(tool_names, scoped_nexus_hash)`
  (`advisor/system_prompts.py`) assembled from section constants — tool docs render only for wired tools,
  and settings-derived values (the `max_wheel_layer` nexus-size ladder) resolve at render time. The Advisor
  always renders via the function at construction; the module-level `SYSTEM_PROMPT` constant is the
  import-time default render (settings defaults), kept for back-compat + regression tests.
  Nexus-scoped mode (`Advisor(nexus_hash=...)`) adds a `## Scope` section and swaps eager-building guidance
  for counsel-from-existing-structure guidance.
  The system prompt is **static after its first render** — fresh graph state flows through the
  conversation (tool results + model-invoked `sync`), never by rewriting the system prompt (a per-turn
  refresh was tried and removed 2026-07-28: it busted prompt caching to re-present information already in
  history). One exception: scoped construction without a precomputed context renders the scoped dump
  lazily on turn 1 (`_render_pending_context`, one-shot). Graph-building itself is **model-initiated
  only** (prompt-steered tools); a background-analysis hook was also tried and removed (same day, too
  naive: per-turn full-pipeline cost, context-blind single-message input, drain-latency wall). The
  `--real-llm` e2e test (`test_advisor_e2e.py`) is the guard: it fails if a multi-turn conversation
  produces no graph (A2→A1 collapse, `docs/r-n-d/judged-eval-vs-prompted-llm.md`) — treat failure as prompt-steering signal, not flake.
  **The bench imports these section constants.** `tests/bench/arms.py` builds its A1 baseline (the
  "prompt-only model given the real method") from `_ROLE`, `_EAGER`, `_INTERNAL_MODEL`,
  `_CONVERSATION_USE`, `_DECISION_READINESS`, `_HOW_YOU_SPEAK` — rewriting tool verbs into mental acts
  via a phrase table, then dropping only what stays machinery. Editing any of those sections can silently
  invalidate the eval: an unmatched rewrite key means the paragraph keeps its tool verbs, gets dropped, and
  the baseline loses method text — inflating every framework-vs-baseline delta. `tests/bench/test_bench.py::
  TestMethodPrompt::test_rewrite_table_has_no_stale_keys` fails on that drift (free, no `--real-llm`);
  run it after editing these constants and update `_TOOL_REWRITES` in the same change.
  Rule of thumb for what belongs where: rules about **how to talk** (`_HOW_YOU_SPEAK`) must reach every
  arm; only rules about **operating machinery** are the framework arm's. See `tests/bench/README.md`.
- `NAVIGATOR_APP_ADVANCED_TOGGLE = NAVIGATOR_APP + "..."` (`apps.py`) — the advanced preamble literally *contains* the default one.
  Any edit to `NAVIGATOR_APP` also ships inside `NAVIGATOR_APP_ADVANCED_TOGGLE`.
- **Tool-budget exhaustion is a prompt surface too.** The agentic loop in `submit`/`submit_stream` stops after
  `max_tool_rounds` (10) even if the model just asked for another tool, and `self._messages` is then reassigned from the
  response chain — so an unanswered `tool_use` is PERSISTED and replayed every later turn, which every Anthropic-shaped
  API rejects ("`tool_use` ids were found without `tool_result` blocks immediately after"). One overrun therefore bricks
  the whole session, each turn failing on the same stale id, and the turns record no text — which reads as model
  collapse rather than malformed history (the recurring misdiagnosis; cf. the connect-timeout and thinking-shape bugs).
  `_close_dangling_tool_calls` answers every open call with a synthetic `tool_result` carrying `_BUDGET_STOP_NOTICE`
  (`conversation_facilitator.py`) — **model-visible text**: it says the tool did not run and to answer now without
  further calls, so a cut-short turn can't present unverified material as tool-confirmed. Caught by `tests/bench`
  (an A2 arm lost 103 min of real tool work to it); locked by `test_conversation_tool_budget.py`.
- **A tool that RAN and failed is not an error anywhere.** `last_tool_calls` records only what the model *attempted*;
  a tool returning `ok=False` raises nothing and sets no turn error, so the turn reads as a normal reply over a graph
  that never grew. `_record_tool_results` pairs each call with its `ExecutionReport` onto `last_tool_results` on BOTH
  `submit` and `submit_stream` (the streaming path yields exactly what it recorded, so UI events and caller-visible
  outcomes can't drift); the bench renders failures in the **validity** section, not the scores, because they bound
  what the arm could do at all. Two traps when touching this: tool payloads arrive wrapped in Mirascope `ToolOutput`,
  whose `str()` is the dataclass repr — `_tool_output_text` reads `.result`, and a test built on a bare string passes
  against the broken code (that's how `report=None` for EVERY event survived from streaming's introduction until a
  real bench run made 16 successful calls and recorded zero outcomes); and read-only tools (`sync`, `inspect_node`)
  legitimately have no report, so "no report" can't be treated as failure. Locked by `test_conversation_tool_budget.py`
  and `test_bench.py::TestReport`.
- **The judge's rubric is a prompt, and its slot order outweighs some of what it scores.** `tests/bench/judge.py`'s
  `_JUDGE_PROMPT` explicitly discounts length, eloquence, framework vocabulary and agreement — and it works for those.
  It says nothing about position, and measurement says it cannot: whichever arm sat in the **Y** slot scored **+0.35** of
  a 5-point step higher (288 scores in `decision-strong-r3`; per-comparison mean +0.354, sd 0.704, n=24, t=2.5; Y won
  16/24). Hashing the comparison identity balances only *in expectation* — that run drew 8/4 splits, so the bias didn't
  cancel, it entered the deltas as a per-arm effect worth roughly a third of the gaps being read. `_x_is_a(key,
  ordinal=…)` now alternates to make the split **exact** (hash picks only the starting side, so layout stays
  scenario-dependent); `report.position_bias` measures and prints it above the delta table, since replication cannot
  remove bias. Two standing implications: **a judged delta is only as trustworthy as its X/Y split** — check it before
  reading rows; and **any new rubric dimension must be assumed position-sensitive** until the reported bias says
  otherwise. Also record `Comparison.session_label`: a delta pooled over sessions cannot be attributed, and the
  `decide`-vs-`wobble` split is what localised A2's `earned_confidence` loss (−1.50 vs −0.50) to the commitment turn.
  Locked by `test_bench.py::TestJudgeSetup`, `TestPositionBias`, `TestReportedBiasAndSessions`.

### Stack B — Structured concern call (Mirascope, `concerns/*.py`)

Each concern owns a tool-less `ConversationFacilitator`. Prompt surface is split across **three** places
that co-occur in one call:

```
[ module SYSTEM_PROMPT ]      often an f-string interpolating shared constants + self.settings.*
   ↓ set_system_prompt → _messages[0]
[ per-call _*_prompt() ]      user message; may re-interpolate the SAME constants again
   ↓ submit(response_model=Dto, user_content=prompt)
[ DTO Field(description=...) ] Mirascope serializes response_model field descriptions INTO the request
   ↓ use_brain(format=Dto)   utils/use_brain.py  (+ ParseError / rate-limit retry)
   → provider → response.parse() → Pydantic Dto
```

**DTO field descriptions are prompt surface.** Review them alongside the SYSTEM_PROMPT and `_*_prompt()`
(e.g. `AspectDto.heuristic_similarity` description in `aspect_generation.py`;
`TaxonomyLocationDto.taxonomy_type` in `statement_classification.py`).

**The DTO *shape* is prompt surface too, and it is model-specific.** Some models re-serialize the whole
response object and return that string as the first field's value — observed on sonnet-5/Bedrock answering
`SemanticDedupDto` with `{"matches": "{\"matches\": [...]}"}`. Pydantic rejects the field
(`input_type=str`) although every byte of the answer is there. The cost is the retry, not the parse: a
re-ask resamples the same tendency, and `parse_delay` (10s ×2 → 120s cap over `retry_max`=10) spends 10+
minutes per call before raising — nested in `AnalysisPipeline` that became **2.6h for one bench A2 cell**
(a single `anchor`: 857s-then-fail on sonnet-5 vs ~33s-succeed on haiku), read as framework slowness when
the model answered correctly first try. `_salvage_double_encoded` (`use_brain.py`) unwraps exactly one
layer, gated on the inner object validating against the model AND naming one of its fields — validation
alone is too weak because all-defaulted DTOs (`matches` included) accept any JSON object, so unrelated
JSON would "salvage" into a silently empty result. Locked by `test_double_encoded_response.py`.
Two standing implications when editing this stack: **mocked tests cannot see this class of bug** (mock
brain auto-fills every field — verify shape changes with `--real-llm`, prefer flatter schemas per
CLAUDE.md), and **a per-model parse failure presents as latency, not as an error**, which is the same
misdiagnosis family as the connect-timeout and thinking-shape bugs.

### Co-occurrence hotspots (edit one → silently affects the other)

1. **`NAVIGATOR_APP` "communicate as MEANING not numbers" sits directly above Analyst's numeric HS bands**
   (`analyst/system_prompts.py` "Reading Polarity Quality", `≥0.7 / 0.5–0.7 / <0.5`). They reconcile only via
   the preamble's "unless asked" clause. `NAVIGATOR_APP_ADVANCED_TOGGLE` flips it to "Show numeric scores" — so the *same*
   Analyst prompt co-occurs with two opposite presentation rules depending on which preamble the host injects.
2. **Advisor's "How You Speak" (keeps framework terms + machinery internal) co-occurs with its own
   score-reading section** dense in `T+/A-/Ac+/Re+`, `HS`, insight/proactiveness numbers. Reconciliation is
   "internal reasoning only, never output." Any edit blurring that internal/external fence breaks the
   silent-framework contract. NOTE: the terminology fence is now **preamble-overridable** ("unless the app
   preamble explicitly grants terminology disclosure") — same override mechanism as `NAVIGATOR_APP_ADVANCED_TOGGLE` flipping
   `NAVIGATOR_APP`'s presentation rules. A preamble granting disclosure is a legitimate configuration, not a leak.
3. **A concern's SYSTEM_PROMPT inline examples co-occur with interpolated shared constants + DTO field text.**
   In `aspect_generation.py`, the hand-written Love/Indifference example sits with interpolated `ASPECT_DEFINITIONS`
   / `HS_SCALE` / `COMPLEMENTARITY_SCALE` + live taxonomy apexes. Changing the constant reaches every consumer;
   changing the inline example reaches only this file. The example is **axis-framed** (each diagonal pair leads with
   the dimension it opposes along) to match `TetradDto`'s nested `ContradictionPairDto(axis, positive, negative)`
   shape — if you revert the example to four flat aspects, it contradicts the DTO the model must fill.

---

## 2. Theory → prompt ownership (the 8 generative rules)

Where each rule is encoded, and whether it is single-sourced (robust) or duplicated prose (fragile).

| Rule | Encoded in | Sourcing |
|------|-----------|----------|
| **R1 Tetrad structure** (T+/T-/A+/A- defs) | `ASPECT_DEFINITIONS` in `concerns/scoring_scales.py`, imported by `aspect_generation`, `aspect_classification`, `positive_ac_re_apex_derivation` | Def block **single-source (good)**. But the "T+ contradicts A-" diagonal rule is ALSO re-stated in prose in `aspect_generation`, `aspect_classification`, and coded in `statement_classification.get_contradiction_pair()` — **duplicated**. |
| **R2 Circular causality** (Ac+ = T-→A+, Re+ = A-→T+) | `transformation_generation` SYSTEM_PROMPT; `positive_ac_re_apex_derivation`; `action_extraction`; `synthesis_generation`; comments in `ac_re_taxonomy.py` | **Duplicated prose across 4+ prompts, no single owner.** Directionality is theory-critical. |
| **R3 Modality balance** (Eq (1) chain: M(T+)=−M(T-)=M(A+)=−M(A-); NOT the zero-sum form — that is identically true under the paper's `M(X) ≈ Ks(X) − Ks_avg` and thus vacuous) | *Nowhere in a generation/scoring prompt* — deliberately: the paper's own tests found Ks-derived balance criteria "not useful" [P1 S1.6-3]. Measurable as `rectangularity` = 0 (exact algebraic identity under the approximation — see generative-rules.md R3.2). Only surfaced in `NAVIGATOR_APP_ADVANCED_TOGGLE` ("modality alignment"). Mode scale in `antithesis_classification` is a DIFFERENT concept (thesis-lessness ladder). | **Prompt-absent by design.** Reject edits that claim to enforce it OR that dress rectangularity's empirical bands in R3.2 theory authority. |
| **R4 Complementarity K** (Ks = (K_T+K_A)/2) | `COMPLEMENTARITY_SCALE` in `scoring_scales.py`, consumed by aspect concerns; thresholds in `concerns/perspective_validation.py` | **Single-source (good).** |
| **R5 Equal-sign synthesis** (S+ between T+/A+) | `synthesis_generation` SYSTEM_PROMPT — explicit "Like-signed inputs only… Never synthesize across opposite signs" requirement + input routing (Ac+/Re+ → S+, Ac−/Re− → S−) | **Encoded (belt + suspenders)**: constraint stated AND enforced by which inputs feed the prompt. Locked by `TestEqualSignSynthesisConstraint`. |
| **R6 Control statements** ("T+ without A+ yields T-") | `concerns/control_statements_check.py` (aspect level) AND `transformation_generation` (transition level, `Ac+ without Re+`; also carries the R6 backfire corollary "Never propose direct reinforcement of a '+' aspect", locked by `TestBackfireConstraint`, and the forcefulness→polarity-flip constraint "Forcefulness reverses polarity" — sibling in `action_extraction.py` Requirements #5; both locked by `TestForcefulnessPolarityFlip`) AND `ASPECT_DEFINITIONS` (neutral-T variant: "-" aspects defined as what T/A degenerate into when the opposition's "+" is absent, + truth criterion; locked by `test_aspect_definitions_carry_neutral_degeneration`) | **Duplicated form**, independent wording across check/prompt sites; neutral-T variant single-sourced in the constant. The forcefulness rule is stated 2× (transformation_generation + action_extraction) with independent wording — drift-watch. |
| **R7 Apex coherence** (S+/- within convex hull of sub-syntheses) | *Not implemented* — TODO stubs in `synthesis_generation.py`. | **Prompt-absent.** Any claim that synthesis is apex-validated is currently false. |
| **R8 Systemic taxonomy** (Table S-1, 5 branches) | `SYSTEMIC_TAXONOMY` dict in `statement_classification.py` (~L45) **AND** a hand-typed markdown table in the same file's SYSTEM_PROMPT (~L300). `ELEMENTAL_TAXONOMY` is the peer dict. | **DUPLICATED WITHIN ONE FILE — the top hotspot** (see §3.1). |

### Scoring-vocabulary single sources of truth
- `concerns/scoring_scales.py`: `ASPECT_DEFINITIONS`, `HS_SCALE`, `COMPLEMENTARITY_SCALE`.
- `concerns/ac_re_taxonomy.py`: `INSIGHT_SCALE`, `PROACTIVENESS_SCALE`, `POLAR_PAIRS`, `AC_PLUS_APEX_TARGET`, `RE_PLUS_APEX_TARGET`.
- `statement_classification.py`: `SYSTEMIC_TAXONOMY`, `ELEMENTAL_TAXONOMY` (consumed programmatically via `lookup_aspect_apex` etc.).

**Rule of thumb:** if your edit changes scale *semantics*, edit the constant — not an inline prompt copy.

---

## 3. Drift hotspot catalog (same theory re-stated in multiple places)

Ranked by blast radius. Each is a place where an edit to one copy silently diverges from the others.
**The correct fix is usually structural: make the prose derive from the constant** (see how
`explorer/system_prompts.py` `_ladder(INSIGHT_SCALE)` renders the ladder from the dict), not re-sync by hand.

1. **Systemic taxonomy: dict vs. prompt table** — `statement_classification.py`. The `SYSTEMIC_TAXONOMY`/
   `ELEMENTAL_TAXONOMY` dicts drive URI lookup + HS apex names; the hand-typed markdown table in the
   SYSTEM_PROMPT is what the LLM reads to pick a branch. Maintained separately. Divergence → LLM classifies
   against one vocabulary while `lookup_aspect_apex` scores HS against another → **silent HS corruption.**
   *Grep:* `SYSTEMIC_TAXONOMY = {` and the `| Integrity |` table row.
2. **Insight/Proactiveness ladders re-typed 3×** — hand-typed prose in `transformation_generation.py`,
   `positive_ac_re_apex_derivation.py`, `action_extraction.py` (all three *import* `INSIGHT_SCALE`/
   `PROACTIVENESS_SCALE` but use them only numerically, while pasting the ladder as prose).
   `explorer/system_prompts.py` AND `advisor/system_prompts.py` now both render from the constant
   (`_ladder` / `_ladder_lines`). Labels round-trip
   through `insight_label_to_value` / `proactiveness_label_to_value` — a drifted table means the LLM's stated
   label and the persisted number diverge. *Grep:* `reflex`, `stewardship`, `transcendence`.
3. **HS band scale stated 3×** — canonical `HS_SCALE` (imported by aspect concerns) vs. an independently-worded
   copy in `antithesis_classification.py` (antithesis path does NOT import `HS_SCALE`) vs. `docs/scoring.md`.
   Bands agree today but phrasing differs ("Perfect antithesis" vs "Exemplary").
4. **Mode & Arousal scales stated 2× in one file** — `antithesis_classification.py` numeric dicts
   (`MODE_FIELDS`, `AROUSAL_VALUES`) + their markdown-table restatements in the same file's SYSTEM_PROMPT.
5. **Circular-causality direction (Ac+ = T-→A+) re-stated 4+×** — `transformation_generation`,
   `positive_ac_re_apex_derivation`, `action_extraction`, `synthesis_generation`, `ac_re_taxonomy` comments.
6. **Diagonal-contradiction rule re-stated ~5×** — `COMPLEMENTARITY_SCALE` (last line), `aspect_generation`,
   `aspect_classification`, `transformation_generation`, `concerns/diagonal_oppositions_check.py`, and the code
   map `get_contradiction_pair`. Wording varies ("contradicts" / "mutually exclusive" / "cannot both be true").
   Any edit must not imply *lowering K* (contradicts `scoring_scales.py`). **On the generation side the rule is now
   partly structural, not just prose:** `TetradDto` nests two `ContradictionPairDto`s each carrying an `axis`
   field (the dimension the pair opposes along), so `aspect_generation` enforces diagonal contradiction through the
   output schema + an axis-first procedure rather than a trailing "Ensure T+ contradicts A-" line. Locked by
   `TestTetradDiagonalStructure` in `tests/test_prompt_review_regressions.py`.
7. **CC control-statement wording stated 2×** — `control_statements_check.py` (aspect) vs.
   `transformation_generation` (transition), independent phrasing + thresholds.

### Agent-prompt hand-typed scales (also drift-prone, currently untested for agreement)

**De-duplicated (removed from this catalog):** the Advisor's insight/proactiveness ladders in
`_SCORE_READING` are now derived from `ac_re_taxonomy.py` via `_ladder_lines()` (same pattern as the
Explorer's `_ladder()`); locked by `TestAdvisorScoreLaddersDerived`. `_SCORE_READING` is an f-string —
keep it one, and assert on the module attribute, not `inspect.getsource`. Likewise the explore doc's
nexus-size ladder ("How a nexus evolves", ">N: combinatorial explosion") is rendered by
`_nexus_evolution(_resolve_max_wheel_layer())` from `settings.max_wheel_layer` — never re-type the cap
as a literal "4"; locked by `TestAdvisorNexusSizeCapDerived`.
- Analyst HS bands (`analyst/system_prompts.py` "Reading Polarity Quality", 3 bands).
- Advisor score-reading section (`advisor/system_prompts.py`, 4 HS bands — ladders now derived, HS bands still hand-typed).
- Neither imports `HS_SCALE` (6 bands) — three granularities for the same `HS_THRESHOLD=0.7` gate.

---

## 4. Reasoning pipeline as a call-chain (output→input seams)

A prompt is a step in a chain; its output is the next step's input. Both pipeline classes live *inside*
the agent files: `AnalysisPipeline` in `analyst/analyst.py`, `ExplorationPipeline` in `explorer/explorer.py`.

### Analysis chain (`AnalysisPipeline.resolve`)
`AddInput` → **SurfaceTheses** (parse-intent → `ThesisExtraction` 3-hop → `StatementDeduplication`) →
**FindPolarities** (Phase-0 `AntitheticalThesisDetection` consolidation → Phase-1 `AntithesisExtraction`
per thesis → Phase-2 dedup) → **`_rank_polarities` gate** → **ExpandPolarity ×N** (`AspectGeneration` →
aspect dedup). `create_nexus` is the Analyst-only handoff.

### Exploration chain (`ExplorationPipeline.resolve`)
**BuildWheels** (structural + `CausalityEstimation` scoring, no gate) → **depth gate
`_select_deep_wheels`** (`max_deep_wheels` cap: rank by layer desc, then raw causality P desc; None = all —
the Explorer agent path; the Advisor's `run_exploration` pins `MAX_DEEP_WHEELS = 1` in
`advisor/tools/explore.py`) → **ExploreTransformations ×deepened-wheels**
(Phase-1 `ApexDerivation` + `ActionExtraction`; Phase-2 `TransformationGeneration` = 4 sequential LLM calls
`_generate_ac_minus`→`_generate_re_side`→`_score_hs`→`_generate_category_reframings`; `TransformationAudit`
annotation) → **GenerateSynthesis** (`SynthesisGeneration` → S+/S-; the Advisor path syntheses only
`deepened_wheel_hashes`, and its explore tool docs must keep telling the model that
`shallow_wheel_hashes` are ranked-but-undeveloped — not presentable as insight).

### Critical output→input seams (upstream wording ripples downstream)
1. **ThesisExtraction text → StatementClassification → AntithesisExtraction.** The classifier's SIMPLE/COMPLEX
   verdict on the *generated wording* routes the entire antithesis path. Wording that reads as a bare fact flips
   COMPLEX→SIMPLE → mechanical negation with **HS hardcoded 1.0**.
2. **Thesis `meaning` URI → all taxonomy lookups.** `StatementClassification` writes the taxonomy branch into
   `meaning`; `lookup_aspect_apex` etc. derive the apex names that AspectGeneration/AntithesisExtraction score
   HS *against*. Wrong branch → HS scored against the wrong reference. Guarded: `TaxonomyLocationDto` fields are
   Literal-constrained (out-of-vocabulary anchor → ParseError → retry, never coerced), and the `lookup_*` methods
   raise on missing/unparseable meanings instead of falling back to Fidelity/Apex rows (`TestTaxonomyFailsLoudly`).
3. **Aspect statement text → wheel segments → transition context.** `build_edge_context` feeds exact
   T/T+/T-/A+/A- wording into Ac+/Re+ generation. Prompts require prose to "refer to concepts by their actual
   statement wording, never by T/A notation" — upstream phrasing is quoted verbatim.
4. **ApexDerivation apex text → `TransformationGeneration._score_hs`.** Apex-prompt wording sets the HS
   reference frame for Ac+/Re+.
5. **Label vocabulary is a hard contract.** `insight_label` / `proactiveness_label` outside the known scales
   → matching silently falls back to `candidates[0]` / midpoint defaults (`get_polar_pair`, `explore_transformations`).
6. **Only Ac+/Re+ headlines reach SynthesisGeneration.** If a transformation prompt stops producing crisp
   headlines, synthesis degrades with no other signal.

### Gates (score-based filters — the prompt that feeds each *is* a gate input)
- **`_rank_polarities`** (`analyst/analyst.py`, `HS_THRESHOLD=0.7`, `MAX_POLARITIES_TO_EXPAND=5`): keeps
  polarities with antithesis HS ≥ 0.7. Fed by `AntithesisExtraction` / `AntithesisClassification` HS. The
  SIMPLE=1.0 shortcut can inflate everything past it → gate stops differentiating.
- **`AntitheticalThesisDetection`** (`MERGE_THRESHOLD=0.7`, `SUGGEST_THRESHOLD=0.1`): HS≥0.7 auto-merges two
  theses into one Polarity; 0.1–0.7 suggests; ≤0.1 drops.
- **ThesisExtraction Step-2 candidate gate** (`is_assertable & is_substantive`, with all-rejected safety net).
- **`_select_deep_wheels`** (`explorer/explorer.py`, `max_deep_wheels`): caps which wheels get
  transformations+synthesis — layer desc, then raw `CausalityProbabilityEstimation` desc (unestimated last).
  The Advisor's `run_exploration` feeds it from the **silent-explore depth budget**
  (top-1 eager deepening is FIXED policy — `EXPLORE_DEEP_WHEELS = 1` in `advisor/tools/explore.py`,
  deliberately not a setting: 0 strands the conversation arc, N>1 pre-pays for unpicked arrangements /
  `advisor_max_perspectives_per_exploration`=2, excess reported as
  `deferred_perspective_hashes`, never dropped; env
  `DIALEXITY_ADVISOR_*`; synthesis is UNCONDITIONAL for deepened wheels — a deepened wheel without
  S+/S- is structurally unfinished, the toggle was removed 2026-07-31) — "rich vs simple" exploration is this runtime budget, not a schema concept.
  Explorer agent path passes None (user selects wheels). The Advisor explore tool docs narrate
  `shallow_wheel_hashes` + `deferred_perspective_hashes` semantics — keep in lockstep with the budget.
  The escape from the budget is the Advisor's **`deepen` tool** (`advisor/tools/deepen.py`,
  `run_deepen` = ExploreTransformations + GenerateSynthesis, synthesis always, fail-soft):
  when the person's lived reality picks a shallow reading, the model deepens that wheel — the
  decision point is in prioritization rule 2 ("the person's reality outranks the plausibility
  score"). Scoped variant guards nexus membership in code (`_wheel_outside_scope_refusal`); its
  doc states deepening never changes exploration CONTENTS, so no consent ceremony (unlike
  anchor/explore/discard). Explorer needs no equivalent — `explore_transformations` +
  `generate_synthesis` are already per-wheel user-driven tools there.
  Locked by `tests/test_exploration_lazy_depth.py` + `tests/test_advisor_explore_budget.py` +
  `tests/test_advisor_deepen.py`.
- **`PerspectiveValidation` flag** (`ExpandPolarity._validate_and_flag`, live since 2026-07): CC +
  empirical inequalities run post-commit on every generated tetrad; verdict persisted on
  `Perspective.validation` ("passed" / "failed: reasons" / None). NOT a blocking gate — prompts
  deprioritize failed perspectives (Advisor `_SCORE_READING` + `_INTERNAL_MODEL` "machine-run verdict",
  Analyst "Reading Polarity Quality"); rendered by `dialectical_context` / `present_analysis` /
  `inspect_node`. The CC prompt (`control_statements_check.py`) is therefore a flag input — wording
  changes shift the verdict distribution. SIMPLE-path antitheses render as "mechanical opposition — HS
  not evaluated" in the dump (never a fake numeric 1.0). Locked by
  `tests/test_perspective_validation_wiring.py`.
- **Context-dump quality filter** (`DialecticalContext._apply_quality_floor` + wheel cap in `_dump_cycle`,
  live since 2026-07): standalone perspectives with HS(A) < `settings.advisor_polarity_quality_min_hs` (0.5), SP/area <
  `advisor_perspective_quality_min_sp` (0.3), DV < `advisor_perspective_quality_min_dv` (0.3), or `validation` starting
  "failed" are SUPPRESSED from the dump (count line notes them) — the SP+DV floor pair mirrors the paper's acceptance
  criterion (SP AND DV [P0 p.12]) as soft pruning, conservative defaults, never the paper's 0.5 verbatim; wheels per
  cycle capped to top-% `advisor_wheel_quality_top_plausible` (3), % denominator stays the full
  sibling set. Nexus members and unscored perspectives are never suppressed, and the wheel cap applies to
  the UNSCOPED dump only — the counsel-mode (nexus-pinned) render shows the user-built exploration in full
  (same load-bearing exemption). This is a RENDER gate — it
  filters what the Advisor sees, not what exists; `inspect_node` reaches everything. The Advisor's
  prioritization rules now say "pre-pruned, rank within it, don't re-filter" — if you change the floors,
  reconcile that section (`TestContextDumpPrePruned`). Env: `DIALEXITY_ADVISOR_POLARITY_QUALITY_MIN_HS` /
  `DIALEXITY_ADVISOR_PERSPECTIVE_QUALITY_MIN_SP` / `DIALEXITY_ADVISOR_PERSPECTIVE_QUALITY_MIN_DV` /
  `DIALEXITY_ADVISOR_WHEEL_QUALITY_TOP_PLAUSIBLE`. Locked by
  `tests/test_context_quality_filter.py`. The unscoped Advisor `sync` tool takes an optional `nexus_hash`
  to zoom into one exploration in full depth (no wheel cap — same exemption as counsel-mode dumps); its
  tool doc in `_TOOL_DOCS["sync"]` describes overview-vs-zoom and must stay consistent with this cap.
- **Decision lifecycle** (`_DECISION_READINESS` in `advisor/system_prompts.py` + `DialecticalContext._dump_decisions`
  + `concerns/record_decision.py` + `concerns/decision_coherence_check.py`, live since 2026-08): the Advisor's
  convergence mechanics — discrimination test (map a new tension only if it could change the choice; cross-referenced
  from `_EAGER`/`_DEFAULT_ARC`/`_HOW_YOU_SPEAK` via the `{decision_filter_note}`/`{decision_arc_step}`/
  `{decision_speech_note}` placeholders, all rendering ONLY when `record_decision` is wired),
  saturation-by-family judgment (reads the correspondence lines; "tensions saturate, never exhausted" — the
  exhaustiveness claim belongs to arrangements only), propose-and-confirm recording ceremony (a decision is a speech
  act; NEVER silent in either mode — explicit carve-out from the unscoped Advisor's hidden machinery), soft pre-commit
  ritual (strongest unchosen A+ confronted, the CHOSEN side's `-` stated as the price + S- trap named; person's wish
  outranks it), and post-decision re-audit
  (reassure FROM the record vs legitimate reopening → record new + consented discard of old, reason naming the
  replacement — no bespoke supersede machinery). **Materialised ≠ resurfacing** (added 2026-08): a well-named cost
  matches almost any development in its own subject matter, so the re-audit's failure mode is filing an EVENT as the
  probability it already priced. Measured — once `accepted_cost` named a real risk, 2 of 3 `decision-strong-r4` A2 runs
  met "the customer called yesterday, 40% of revenue on a six-week clock" by reassuring from the record (one verbatim:
  it changed "the shape of the risk, not the decision itself"), dropping A2's wobble accuracy to 4/6 against A1.7's
  6/6. The rule bounds reassurance to "no more than what was priced" and names that rationalisation so the model can
  catch itself. Note the coupling: sharpening the cost is what created this, so the two rules must be read together.
  Locked by `test_prompt_review_regressions.py::test_materialised_risk_is_not_the_risk_resurfacing`. `DecisionCoherenceCheck` is a fail-soft record-time flag
  (`Decision.validation`, `PerspectiveValidation` pattern — never blocks; DTO bool is `incoherent` so the mock brain's
  auto-False reads as passed). The `# Decisions` dump section renders in BOTH unscoped and scoped dumps (decisions are
  Case-level facts); its wording (role labels "accepted cost"/"adopted pathway", "since discarded" ground flag,
  `Validation` line) must stay in lockstep with `_SCORE_READING`'s Decisions block and `_TOOL_DOCS["record_decision"]`.
  **Aspect addressability** (fixed 2026-08): every T/A/aspect line in `_dump_one_perspective` renders its Statement
  `[[short_hash]]`. Load-bearing for this lifecycle, not cosmetic — `record_decision` asks for the CHOSEN side's
  `-` aspect as the `accepted_cost` ground and the re-audit reassures FROM it; while aspect lines were unaddressed
  the only hash in view was the Perspective's, so every observed recording grounded on the tension instead of the
  cost and the re-audit had nothing specific to point back to (caught by `tests/bench`). `_TOOL_DOCS["record_decision"]`
  names the aspect hash explicitly. Locked by `test_dialectical_context.py::test_aspect_lines_are_addressable`.
  **Second addressability surface — the anchor RESULT** (fixed 2026-08): the dump is not the only place aspect hashes
  are needed. A decision reached in the FIRST session has no dump at all — the only artifact in view is
  `ExpandPolarity`'s `perspectives` final-state, which carried each aspect's TEXT but only the Perspective's hash.
  Measured: all 3 recorded costs in `claim1-weak-r2` grounded on the Perspective, exactly the pre-fix failure the dump
  change was supposed to have ended, because the Perspective's was the sole hash on offer. `_perspective_final_state`
  now emits `{position}_hash` per aspect and `_TOOL_DOCS["record_decision"]` says both surfaces carry them (so the
  Perspective hash is never "the closest thing available"). Locked by
  `test_perspective_reading.py::test_final_state_addresses_every_aspect`. Generalise: any hash the prompt ASKS for
  must be addressable on every surface the model can be asked from, not just the richest one.
  **A cost is a MINUS** (corrected 2026-08, was "the unchosen side's `+`"): reading the tetrad plainly, T is what is
  said, T+ its implied goal, T- its risk; A is the opponent's say, A+ the obligation falling on the T-sayer, A- the
  risk that follows. So a `+` names a goal or an obligation — something to DO — and a request for one yields a REMEDY
  where a price was wanted. Measured: with the old wording, 4 of 6 `decision-strong-r3` A2 runs recorded remedies
  ("Diversify client relationships before any separation") as the accepted cost, and A2 lost `earned_confidence` by
  1.50 in the commitment session to the A1.7 prose-journal control that named the actual risk. The correction spans
  `GroundLink.role`, `GROUNDED_IN`'s docstring (the owning definition), `_TOOL_DOCS["record_decision"]`,
  `_DECISION_READINESS`, `DialecticalContext`'s `_SCORE_READING` Decisions block, `DecisionCoherenceCheck`'s
  ACCEPTED COST special case, `GRAPH_SCHEMA` and `docs/graph.md` — all must move together. Locked by
  `test_prompt_review_regressions.py::test_accepted_cost_asks_for_the_chosen_side_minus` (which also asserts the old
  "unchosen side's `+`" phrasing is gone) and `..._tool_schema_matches_the_prompt`.
  **Decision mode closes on PATHWAYS** (added 2026-08): the discrimination test tells the model what not to map, and
  nothing told it to develop what it kept — so pruning read as permission to stop building. Measured: all 6 weak-tier
  A2 runs in `claim1-weak-r1` stopped at `anchor` (1-2 perspectives, zero `explore`) where the strong tier explored in
  4 of 6, leaving the ceremony with no pathway to offer as the `adopted_pathway` ground and no arrangement to read the
  S- trap version from. Method, not machinery, so `bench/arms.py` REWRITES the tool verb instead of dropping the
  paragraph (`explore` is deliberately absent from `_TOOL_TOKENS`) — a prompt-only arm owes the same reasoning. Locked
  by `test_decision_mode_closes_on_pathways_not_tensions_alone`. Bench side: `report.py` now flags live A2 runs that
  never explored, because `collapsed_to_a1` clears on a single tool call and the validity section otherwise asserts
  the opposite ("A2 != A1 holds") over an arm that was never assembled.
  **The ceremony's three weak-model failure modes** (fixed 2026-08, all measured in `claim1-weak-r1` — the weak tier
  is where ceremony discipline breaks, so a strong-tier pass proves nothing about them). (a) *The soft ritual pressed
  twice is a hard gate*: handed "That's the decision, final… I'm not reopening this one", one run demanded "Can you
  name that cost and own it?" and recorded nothing. The section already deferred to the person's wish but illustrated
  declining only with the polite "just record it", so a firm refusal did not pattern-match — now "Ask once.", the
  observed refusals quoted, and "does not have to be polite". (b) *Reading the record back became speaking AS them*:
  "in their own words" produced a commit reply entirely in the user's first person ("I'm paying the premium now…
  Record it: Buy out cofounder now") — a script of the decision instead of a record of it; now "Their words, YOUR
  voice". An A1 run drifted the same way, so both (a) and (b) belong in the shared section and MUST survive
  `_strip_tool_prose` (asserted in `bench/arms.py`'s rewrite table + the bench's own tests). (c) *Prose is not
  recording*: 4 of 6 A2 runs never called `record_decision`, 2 having already written the full record out under
  headings. That paragraph names the tool deliberately so prompt-only arms drop it — they record in prose
  legitimately. Locked by `test_ritual_asks_once_and_never_gates_the_record`,
  `test_reading_the_record_back_is_not_speaking_as_them`, `test_prose_summary_is_not_a_substitute_for_recording`.
  Explorer side of the toggle: decision declarations are an IMMEDIATE handover signal (explorer/system_prompts.py
  "when the user tries to DECIDE" — the Explorer cannot record and must never fake an acknowledgment; reading
  recorded decisions stays available via query_graph/inspect_node, and NAVIGATOR_APP_ADVANCED_TOGGLE names Decision
  in its vocabulary list). Analyst side (live since 2026-08, cross-agent parity fix): the same seam in
  analyst/system_prompts.py — cannot record, never fakes an acknowledgment, and NEVER anchors the declared choice
  as a thesis (a decision is a stance, not a tension; anchoring it misfiles it as analytical structure); locked by
  `test_analyst_never_fakes_or_anchors_decisions`. No settings knobs (policy-not-config).
  **Decision provenance** (live since 2026-08): the rationale's `agent` names the confirming PRINCIPAL — "human"
  iff a person confirmed the ceremony; delegated drivers (agent-to-agent runs) record "agent:<name>" instead.
  Host-attested at construction (`Advisor(principal=...)` → closed over by `build_record_decision`, same
  code-not-prompt enforcement as the nexus pin), never LLM-supplied. Renderers branch on it: the ledger shows
  unattributed "Why:" ONLY for agent=="human" ("Why (confirmed by agent:<name>):" otherwise); inspect_node
  mirrors this. Changing the sentinel or adding principals must update `_dump_decisions`, `_inspect_decision`,
  GRAPH_SCHEMA's Decision row, and docs/graph.md together (locked by `TestDecisionProvenance`).
  **Named-options guidance** (in `_DECISION_READINESS`, live since 2026-08): when a decision arrives
  as "X or Y", the pair is anchored AS the person's framing (options are valid graph citizens — the tetrad
  expansion, not a translation layer, surfaces the root tension); alternative tetrads on the same polarity are
  LAZY (ask which pull matters most first, repeat-anchor only on demonstrated demand — mirrors the
  explore/deepen budget split) and explicitly exempted from the discrimination test ("readings of the choice
  itself, not new candidate tensions" — remove that clause and the two rules compete); weave-time rule (take
  the resonant reading + tensions beyond the fork — sibling readings are angle shifts per the nexus grouping
  principle); weak/distancing opposition read from the anchor result AT CALL TIME (later dumps mask or
  suppress it): low HS *or low Mode* — peer alternatives live in each other's negation space so HS alone can
  score moderate; Mode ~0.0-0.1 (distancing/privation) is the "options differ rather than oppose" tell —
  then keep the pair as frame and anchor EACH option alone (never drop an option from the graph).
  Dependency chain: `_TOOL_DOCS["anchor"/"anchor_scoped"]` repeat-call line carries the identical-wording
  caveat (statement hashing is content-addressed — a rephrase creates a new polarity, not a sibling tetrad);
  `IntroducePolarity` reports `mode` in `artifacts["polarities"]` + summary (the paragraph's Mode-read
  instruction points at it); `StatementClassification` SYSTEM_PROMPT + `_classification_prompt` classify
  courses of action as COMPLEX (keystone: SIMPLE would strip taxonomy anchoring from option tetrads);
  `AspectGeneration`'s `not_like_these` diversity instruction is load-bearing for sibling-tetrad variation —
  weakening "generate something different" collapses repeat-anchors into dedup-discards.
  **Perspective reading (axis → intent)** (live since 2026-08): the axis names `TetradDto` forces the model
  to produce (issue #25 fix) now PERSIST — `AspectGeneration._capture_axis` collects them on `self.axes`
  (filtering the "no genuine shared axis" disclaimers the DTO deliberately allows; heuristic filter, sentence-length
  or negation-marker axes are dropped), `ExpandPolarity._compose_reading` writes "Reading along: X / Y" into
  `Perspective.intent` BEFORE commit (intent participates in the hash → distinct readings are structurally
  distinct nodes; identical readings hash-collide into dedup — intended). The reading is what distinguishes
  sibling tetrads on one Polarity; rendered by `_dump_one_perspective` (one_line-hardened) + `inspect_node`
  (pre-existing Intent line) + `expand_polarities` final-state artifact (`reading` key); GRAPH_SCHEMA documents
  the semantics. `edit_perspective` clones DROP the inherited intent (stale axis after user edits).
  Promotion path (prompt): a resonant reading is an anchor candidate — anchor its poles as a real Polarity
  (lazy materialization; axis-string = breadcrumb, Polarity = paid-for structure). Ontology note: an axis IS
  polarity-shaped, but eager Polarity minting per tetrad was rejected (front-half LLM cost on every tetrad +
  scaffolding promoted to first-class vocabulary); the string field + on-resonance anchor is the lazy variant.
  Locked by `tests/test_perspective_reading.py` + `TestDecisionReadiness::test_named_options_reading_promotion`.
  Locked by
  `tests/test_prompt_review_regressions.py::TestDecisionReadiness` (+ `TestExplorerAdvisorToggleNarration::
  test_explorer_routes_decision_moments_to_counsel`) + `tests/test_decision.py` (incl.
  `TestRecordDecisionToolBoundary` — Mirascope passes raw dicts for nested-model tool params; the tool normalizes
  via `GroundLink.model_validate`, the only `@llm.tool` in the tree with a nested-model list param).
  Named-options locks: `TestDecisionReadiness::test_named_options_*`, `::test_anchor_doc_alternative_tetrad_line_in_both_modes`,
  `::test_classifier_treats_options_as_complex`, `::test_anchor_report_carries_mode`;
  behavioral: `tests/test_options_classification_real_llm.py` (--real-llm).
- **Multi-nexus dump cross-references** (`DialecticalContext._build_cross_nexus_refs`, live since 2026-08):
  when >1 nexus exists — or one-plus nexus with unexplored standalone tensions beside it — the unscoped
  dump (a) prepends an index-disambiguation note when >1 nexus ("indices are per-exploration — qualify
  with the nexus"), and (b) annotates perspectives (nexus members AND standalone) with machine-stated
  correspondences derived from persisted data only: "Also woven into Nexus [[x]]" (shared perspective,
  `cardinality=(0, None)`; never emitted for standalone — they're in no nexus by construction) and
  "Same opposition family (Branch) as perspective(s) N in [[x]] / [[hash]] (unexplored)" (same
  thesis taxonomy branch via `parse_meaning_uri`; Apex and Simple excluded; correspondences computed
  across groups only, never within one nexus). Deliberately NO persisted analogy edge —
  cross-exploration parallels stay LLM interpretation over these raw correspondences. The engine
  prompt's `_SCORE_READING` has a "Cross-exploration correspondences" block teaching what the lines
  are for (parallels), that family matches are coarse (substance-check before drawing the parallel),
  and that family names follow the How You Speak vocabulary rules — keep it in sync with the dump's
  line formats. Locked by `tests/test_dialectical_context.py::TestDialecticalContextMultiNexus` and
  `TestCrossExplorationGuidance`.
- **NOT gates (scoring/annotation only):** `CausalityEstimation`, `TransformationAudit`, aspect K/area/rectangularity.
  The other live post-hoc check is `edit_perspective._validate_tetrad_coherence` (CC + diagonal) on user edits.

---

## 5. Cross-agent parity matrix (Analyst ↔ Explorer ↔ Advisor)

Independently-authored prompts that share a concept which MUST stay identical or a handoff misleads model/user.

| Shared concept | Analyst | Explorer | Advisor | Ground truth |
|----------------|---------|----------|---------|--------------|
| HS-on-A vs HS-on-Ac+/Re+ disambiguation | uses only HS-on-A | disambiguates both | disambiguates both | — (must agree) |
| HS threshold bands | 4 bands (0.7/0.5/0.3) | — | 4 bands (same boundaries) | `HS_SCALE` (6 bands) — neither imports it, but boundaries now agree; locked by `TestCrossAgentHsBandParity` |
| DV semantics (naturalness-of-framing; low DV → re-frame, not polish; counsel-mode floor prunes very-low DV) | validation section (incl. the toggle warning: counsel prunes what analysis keeps) | — | score-reading section + `min_dv` floor | `DialecticalValidityEstimation` + `advisor_perspective_quality_min_dv`; qualitative wording (no bands); locked by `test_analyst_and_advisor_agree_on_dv_semantics` |
| Nexus grouping rule ("different polarities → synthesis; same → angle shift") | prose | — | prose | duplicated, hand-written twice |
| S+/S- emergence-vs-trap, "1+1>2" | `NAVIGATOR_APP` | prose | prose | `synthesis_generation` concern |
| Ac+ = T-→A+, Re+ = A-→T+ direction | `NAVIGATOR_APP` | prose | prose | `docs/graph.md` + `GRAPH_SCHEMA` |
| `nexus_intent` surface classification | "internal, do not surface" | interpolated raw into header | — | leak risk |
| Round-trip narration (dx:// loop: capture → develop → weave back) | "Inputs from exploration" section (recognize `dx://`, develop, offer `expand_nexus` back to the origin named in the input's digest) | "Feeding Insights Back" section (`create_dx_input` at resonance moments, loop framed as growth not exit) | — (unscoped Advisor has no dx tools) | `orchestrator/tools/create_dx_input.py` — both narrations must describe the SAME loop. Provenance channel: `CreateDxInput` stamps "Origin: insight from exploration [[hash]]" into the Input digest; `present_analysis` Sources section + `inspect_node`'s Transition renderer surface it. If the digest format changes, the Analyst prompt's "Origin: insight from" pointer must change with it. `CreateDxInput` is idempotent: repeat capture of the same transition reuses the existing Input (content-addressable hash) without clobbering a refined digest or duplicating the HAS_INPUT edge. `InputRepository.get_all` carries the committed-only filter (its two new LLM-facing consumers — `present_analysis` Sources + `DialecticalContext` pending list — would otherwise surface uncommitted garbage). |
| Arrangement-contrast rule (close-% + different causal readings → contrast-and-ask, not argmax) | — | Causality section (~15pp closeness band) | Prioritization rule 2 (same band + "depth is selective" tie-in to lazy explore) | hand-written twice — `TestArrangementContrast.test_both_share_the_closeness_heuristic` pins the band; wheel `%` convention = siblings within the parent Cycle, rendered identically by `dialectical_context._dump_cycle` and `present_exploration._causality_label` (locked by `tests/test_present_exploration_scores.py`) |

### Agent-mode authority matrix (who may touch the graph, enforced in code)

| Mode | Create nexus | Expand nexus | Anchor/ingest | Record decision | Discard | Context scope |
|------|:---:|:---:|:---:|:---:|:---:|---|
| Analyst | ✅ (`create_nexus`, the handoff) | ✅ | ✅ | ❌ | ✅ sid-wide | full case |
| Explorer(nexus_hash) | ❌ (but ✅ `create_dx_input` — a Case-Input write that STARTS the round-trip; analysis of it stays Analyst-side) | ✅ (prompt-steered hash) | ❌ | ❌ | — | full case dump via tools |
| Advisor (unscoped) | ✅ (via `explore` w/o hash) | ✅ | ✅ | ✅ (consent-first, prompt-enforced) | ✅ sid-wide (incl. Decisions) | full case (render at construction) |
| Advisor(nexus_hash) | ❌ unreachable | ✅ pinned (closure) | ✅ anchor (standalone until woven) | ✅ unguarded (Decisions are Case-level, not exploration members) | ✅ pinned members + standalone PPs + Decisions; ❌ other explorations' members (code guard) | one nexus + outside count + Decisions (Case-wide) |

`Advisor(nexus_hash=...)` is NOT a standalone variant — it is the **counsel mode of an Explorer↔Advisor
session toggle**: the host hands the Explorer conversation (messages + nexus_hash) to an Advisor head
("what does this mean for me?") and can hand back for technical work. Same conversation, same exploration,
different register; the host app drives the toggle (no automatic agent-switching). Its prompt is
`system_prompt(tool_names, scoped_nexus_hash)` (`advisor/system_prompts.py`) — the tool-docs section renders
only wired tools (app-provided `app_tools=` names are unknown to it and skipped: app tools are documented
in the app preamble, their schemas travel via the `@llm.tool` docstring — `TestAppTools`; the seam is
uniform across Analyst/Explorer/Advisor via `agents/toolsets.py::merge_app_tools`; one app definition per
app, passed to EVERY head — toggle heads share literal history, and the Analyst thread owes the same
domain resources by parity. The recommended host interface is `AppSpec` (`agents/app_spec.py`): apps
declare pieces (voicing / advisor_persona / tool_guide / tools) and each head composes its correct base —
NAVIGATOR_APP, NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER, or bare persona — so the composition lore stays in the framework;
`tool_guide` lands verbatim in every head, preventing per-head drift of app-tool usage rules —
`tests/test_app_spec.py`); the nexus pin
is enforced by closures in `advisor/tools/scoped.py` (`build_scoped_tools`),
never by prompt admonition. Explorer, by contrast, steers its nexus_hash via prompt text only — a known
weaker enforcement. Preamble pairing for the toggle: `NAVIGATOR_APP_ADVANCED_TOGGLE` (Explorer side) ↔
`NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER` (Advisor side). BOTH are `NAVIGATOR_APP + override` — that composition is what
keeps both registers in Navigator territory (same vocabulary contract, third-party detection, score
presentation); the toggle changes engine + register, never the user contract. The advisory override also
mandates **transparent mutation**: anchor/explore/discard on the user-built exploration are consent-first
and announced (vs the unscoped Advisor's silent graph-building). The ENGINE enforces this too — the scoped
render swaps SIX sections for `_SCOPED` variants: `_ROLE_SCOPED` (analysis is shared work, not hidden
machinery), `_EAGER_SCOPED`, `_scope_section` (defers consent to the preamble — "when the person agrees
to add it"), `_TOOLS_INTRO_SCOPED` (never name tools, but announce their EFFECTS), `_REJECTION_HANDLING_SCOPED`
(fresh own anchors → no ceremony; unwoven members → confirm-then-discard; woven-in members → can't remove,
offer re-anchor instead — reconciles with `Discard`'s cycle-member refusal), `_HOW_YOU_SPEAK_SCOPED`, plus
`_TOOL_DOCS` `_scoped` variants for `anchor`/`sync`/`explore`/`discard`, and the `_CONVERSATION_USE`
"After ingest or anchor" heading drops `ingest` when unwired. (`record_decision` needs no `_scoped`
variant — its doc is consent-first in BOTH modes, since the decision record is the person's artifact
even for the otherwise-silent unscoped Advisor; see the Decision lifecycle entry in §4.) **The whole assembled scoped render carries
NO silent-mutation or machinery-hiding wording** (checked by a full-prompt sweep, not per-section — the
first fix missed the `discard` tool doc's "Silently retracts", `_TOOLS_INTRO`'s "eagerly and silently",
and `_ROLE`'s "never see the machinery" because it only checked the rejection section's phrases). Locked
by `TestScopedAdvisorConsentContract` (whole-prompt sweep + woven-in dead-end + ingest bare-word). Scoped
`discard`'s code guard matches: pinned-nexus members and standalone perspectives (own rejected anchors)
allowed, members of OTHER explorations refused (multi-membership counts as another's).

**Toggle narration lives on both heads** (each surfaces the handover signal, neither auto-switches):
the Explorer prompt's "When the User Shifts from Structure to Meaning" section suggests counsel mode only
if the host offers one (graceful floor: otherwise keep counseling from pathways); the counsel side's
`NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER` narrates switching back to the exploration view — hedged the same way ("if the
application offers a way back"). The preamble also treats history as ground truth (cold start with
messages=None on an ingest-built or shared nexus must not fabricate shared memories or authorship);
the scoped engine's `_HOW_YOU_SPEAK_SCOPED` replaces machinery-invisible/rephrase-freely with the
Navigator-territory precision rule (exact statement text when citing by hash). Handover
mechanics (messages + nexus_hash, system prompt replaced on construction, history survives verbatim
including foreign tool-use blocks) are locked by `tests/test_agent_handover.py` — mocked structure tests
plus a `--real-llm` replay-acceptance test for tool-use blocks from tools not in the current head's set.

### App/engine vocabulary boundary
- **Engine** (`agents/{analyst,explorer,advisor}/system_prompts.py`) = domain-neutral; may name graph nodes
  (Statement, Polarity, T+/A-) because those are the model. Must NOT hardcode persona voice/tone.
- **App** (`agents/apps.py`) = persona + presentation vocabulary. `NAVIGATOR_APP` forbids a fixed translation
  table; advisory personas (`COUNSELOR/STRATEGIC_ADVISOR/COACH/MEDIATOR/SPARRING_PARTNER/DECISION_PARTNER`)
  carry ONLY voice — including convergence: `DECISION_PARTNER_PERSONA` tunes how convergence FEELS
  (decision-frame-first, phase shift on a formed leaning, keeper-not-prosecutor after recording) but the
  mechanics (discrimination/saturation/ceremony/re-audit) stay engine-owned in `_DECISION_READINESS`.
  Locked by `TestAdvisoryPersonaBoundary` (no framework terms, no engine-mechanics re-specification).
  `NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER = NAVIGATOR_APP + "## Advisory Register ..."` (same construction as `NAVIGATOR_APP_ADVANCED_TOGGLE`)
  is the advisory-side override: counsel register for a Navigator-built exploration, transparent-mutation
  rule, and a "Terminology Disclosure" section that the engine's "How You Speak" escape hatch honors —
  deferring to `NAVIGATOR_APP`'s vocabulary rules (so "Nexus" stays internal even with disclosure granted).
- **Known partial violations:** engine score-reading sections carry presentation defaults ("as meaning, not
  numbers") that *reference* the app preamble — a two-way dependency the split says should be one-way.
- **Nexus→Exploration vocabulary contract:** "Nexus" is internal; the user-facing term is **"Exploration"**.
  `NAVIGATOR_APP` whitelist drops "Nexus" (keeps Polarity/Wheel/Cycle/Transformation/Position) and carries the
  explicit "say exploration, never surface Nexus" rule; the Analyst prompt keeps the internal↔user mapping
  (so it still uses "nexus" in reasoning + the `create_nexus`/`expand_nexus` tool names). `NAVIGATOR_APP_ADVANCED_TOGGLE`
  (experts) is unchanged; the Advisor's terminology fence (in "How You Speak") still bans "nexus" by default
  but is preamble-overridable. Locked by
  `TestNexusExplorationVocabulary` in `tests/test_prompt_review_regressions.py`.

---

## 6. Test coverage — what exists vs. the gap

- **`tests/test_prompt_review_regressions.py`** (~68 tests, no LLM) — the real coverage. Mechanical
  string/logic assertions: shared scoring constants exist and are imported by `aspect_generation`/
  `aspect_classification`; transformation worked-example directions; CC both-scores rule; apex sweet-spots;
  settings-driven transition length; Explorer dead-tool + 1-PP claims; `NAVIGATOR_APP_ADVANCED_TOGGLE` override wording;
  causality alias format; Advisor discard wiring + empty-ingest fallback; anchor headline clamp; Analyst
  nexus grouping phrase; dedup report merge; elemental taxonomy; **`TestAdvisorFloorGuarantee`** — the
  Advisor floor contract (full-native-capability guarantee, eager-thinking/ungated-speech section, no
  speech-gating or fabricate-a-tension language, Default Arc not Sequence, no unwired "structural guarantee"
  claim, preamble-overridable terminology fence, Analyst no-tension-valid-conclusion, Explorer
  intent-driven build_wheels); **`TestNavigatorRoundTrip`** — both prompts narrate the dx:// loop, the
  Explorer carries `create_dx_input`, the dead off-ramp phrasing is gone; **`TestExplorerAdvisorToggleNarration`** —
  both heads surface the handover signal without auto-switching.
- **`tests/test_prompt_vocabulary.py`** (1 test, `--real-llm`) — behavioral: a live Analyst response never
  labels T-/T+ as "blindspot." NAVIGATOR_APP + Analyst only. Skipped in the default suite.

### Coverage gaps a systemic review should close (add a regression when you touch these)
- **Cross-agent HS-band parity now tested** (`TestCrossAgentHsBandParity`: Analyst/Advisor HS-on-A
  boundaries agree). Still untested cross-agent: the nexus grouping rule wording and Ac+/Re+ direction.
- **Agent-prompt hand-typed scales untested for agreement** with `scoring_scales.py` / `ac_re_taxonomy.py`
  (Analyst HS bands, Advisor score section). The enforced-shared parametrize covers only the two aspect concerns.
- **The taxonomy dict-vs-table lockstep is untested** (hotspot §3.1).
- **No app/engine boundary test** — nothing asserts engine prompts avoid persona vocab, or personas avoid
  framework terms. (Partial: `TestNexusExplorationVocabulary` now locks the Nexus→Exploration user-facing
  vocabulary contract across `NAVIGATOR_APP` / `NAVIGATOR_APP_ADVANCED_TOGGLE` / Analyst prompt.)
- **No test that `concerns/dialectical_context.py` score labels match the Advisor's score-reading section.**
- **Advisory personas now have boundary tests** (`TestAdvisoryPersonaBoundary`: no framework terminology,
  no engine-mechanics re-specification, DECISION_PARTNER convergence-forward contract). Still untested:
  persona voice/tone quality (would need `--real-llm`).
