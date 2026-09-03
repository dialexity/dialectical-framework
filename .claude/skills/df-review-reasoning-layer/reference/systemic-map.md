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
  The dump is **re-read every turn** by `Advisor._refresh_context`, and the system prompt is **rewritten
  only when the rendered dump changed**. Read this history before touching it, because the design has
  flipped twice:
  - A per-turn refresh was tried and removed **2026-07-28** — it busted prompt caching to re-present
    information already in history.
  - The static prompt was then removed and the refresh **reinstated 2026-08-26**, because both halves of
    that reasoning were measured false. `probe_readside_reach`: the dump reached the reply at 0.26
    (pathways) / 0.21 (synthesis) overlap with **0 hashes cited across 18 sessions**, and **14 of 18 first
    sessions built 390 transformations while the slot read `EMPTY_UNDERSTANDING` for all 8 turns** — the
    prompt contradicting the history it sat on. Depth predicted score at corr −0.107 over 36 cells, the
    null that unread structure predicts. "Already in history" also conflates the tool's REPORT with the
    dump's derived content (indices T1/A1, scores, validation flags, suppression counts), which appears
    nowhere else.
  - The caching objection **survives as the mechanism**: re-READ every turn, re-WRITE only on change, so an
    unchanged turn keeps its prefix cache. Cost measured at **0.245s median for 7 tensions**
    (`tests/test_context_refresh_cost.py`) and recorded per turn as `TurnTiming.context_render_s` /
    `TurnRecord.context_render_s`.
  - **The caching objection is now REPAIRED at the provider seam, and that puts a hard constraint on this
    prompt's section order (2026-08-31).** Mirascope stamps `cache_control` at the very END of the system
    prompt (`anthropic/_utils/encode.py:471-478`), so with the dump last the breakpoint sat behind the only
    mutable bytes and a changed turn re-prefilled the whole ~15.6k engine. `split_system_for_cache`
    (`utils/bedrock_provider.py`) now splits the block at `"\n\n## Current Understanding\n\n"` and leaves
    the breakpoint on the stable head — measured 4/4 at cache-read 18,075 vs 0, billed-equivalent prefill
    6.8x cheaper on a post-write turn (`tests/e2e/probe_prompt_cache.py`). **Consequence for anyone editing
    this prompt: `_CONTEXT_SLOT` must remain the LAST section appended in `system_prompt()`, and the
    heading string must stay unique in the render.** Append a section after it and the split silently
    degrades — it fails soft by returning the prompt unchanged, so nothing raises and caching just reverts.
    `tests/test_prompt_cache_split.py::TestTheSeamTheSplitDependsOn` is the tripwire (suffix invariant,
    sentinel count == 1 across tool sets × scoped/unscoped, head long enough to clear the 4,096-token
    minimum). Assert the suffix on `system_prompt()`'s return value only — `providers/base/_utils.py:95-101`
    appends formatting instructions to system when `format` is set, so it is false at the wire level.
    Unrelated but load-bearing when reading cache numbers: the minimum cacheable prefix is **4,096 tokens
    on haiku-4.5**, so no concern prompt in the tree (~0.8k–3.5k) has ever been cacheable and `cache_read=0`
    there is correct.
  - **Priced on the bench, r26, 64 live A2 turns: median 0.300s = 1.49% of the median reply path, and
    0.7% of all reply-path seconds in the round.** Never above 1.6s on any of the 11 slow turns. The
    refresh is not a latency concern and this is no longer an argument, it is a measurement.
  - **What r26 found instead, and it relocates the whole latency question:** A2's reply path is **73%
    tool rounds, 26% generation, 0.7% refresh**, and the tools are enormous — `anchor` **282.8s median /
    812.5s max** (n=10), `explore` **196.0s median / 986.7s max** (n=3). A2 p90 reply path **480.4s**
    against A1.7's **9.0s**; worst turn **1010.6s**. So the Advisor feels lengthy because of what the
    model ELECTS on the turn, not because of prompt assembly, the graph read, or off-path repair.
    Deferring work off the turn cannot fix that. (An earlier `anchor` figure of 42.0s, regressed from 3
    observations, was low by 6.7× — see `MEDIAN_TOOL_ROUND_S` in `tests/test_context_refresh_cost.py`.)
  - **Read those tool medians as blends of work and sleep, not as tool cost.** r26's ten `anchor` rounds
    were 36.5 / 38.9 / 43.4 / 43.5 / 107.8 / 457.9 / 807.9 / 808.2 / 812.3 / 812.5s. Four inside 5
    seconds of each other at ~810s is a ceiling, not a workload, and it is the shape of `use_brain`'s
    ParseError ladder as it stood then (10s doubling to a 120s cap over 10 attempts = **750s of sleep**;
    flat at 2s since 2026-08-27, see the retry-policy note below) on top of ~40s of
    work: 107.8 ≈ 40+70, 457.9 ≈ 40+390, ~810 ≈ 40+750 exhausted. All six slow rounds reported `ok`, and
    the 2.5-hour run logged **zero** warnings — because ParseError was the one retry branch that never
    logged. Fixed 2026-08-26: that branch now logs (with cumulative sleep per call), and
    `utils/retry_accounting.py` records the split onto `ToolRound.retry_seconds` /
    `TurnTiming.retry_seconds` / `TurnRecord.retry_seconds` + `tool_retry_seconds`, so a future round can
    say what the tool cost when it worked. `probe_reply_path_latency.py` prints waited vs working and
    WITHHOLDS the working column on runs older than the field. Before quoting any pre-2026-08-26 tool
    median as a cost, note that nothing in those runs could distinguish 40s of work from 13 minutes of
    sleep.
  - **Measured, not inferred, same day** (`tests/e2e/probe_anchor_retry_cost.py`, haiku-4.5, n=3):
    **3 of 3 `anchor` calls laddered.** Waited 123.5 / 321.3 / 809.8s, of which **working 46.8 / 41.4 /
    40.1s** and slept 70 / 270 / 750s — exact ladder sums, every call reporting `ok`. **So `anchor`
    costs ~41s**, and r26's 282.8s median was 41s of work plus sleeping. `MEDIAN_TOOL_ROUND_S` in
    `tests/test_context_refresh_cost.py` now carries 41.4 (the working figure) and its full 42.0 → 282.8
    → 41.4 history.
  - **`explore` decomposed 2026-08-27** (`tests/e2e/probe_explore_cost.py` + `utils/call_census.py`,
    weak tier, 1 PP, 6 Transformations). Unlike `anchor` this one is **work, and the question that
    replaced work-vs-sleep was volume-vs-depth: many calls, or few in a long chain?** Answer: **both, so
    the dichotomy was false.** 47 calls, **367.8s of provider time compressed 4.15x** into 88.6s
    in-flight, which is 85% of the 103.8s wall, about **11 stages deep** at 7.8s a stage. The fan-out is
    genuinely working and the residual latency is structural — there is no missing `gather`, and asking
    for less cuts COST while cutting latency only where it removes a stage. Keep those two levers apart:
    latency follows `busy_s`/`depth`, cost follows `provider_s`, and `parallelism` is neither (it reports
    compression already achieved). The first draft of that probe branched on `parallelism` alone and
    announced "fan-out, so ask for less" about a run whose wall clock was a chain.
    **The actionable finding: `TransitionAuditDto` is 40% of all provider time** — 147.4s over 12 calls
    at ~12.3s each against a 7.8s mean, three times the next row (`ReSideCompletionDto`, 56.8s). Every
    other concern is exactly 6 calls, one per Transformation; the audit is 2 per Transformation, so it is
    the only place "ask for less" is available without deleting a generation stage, and it is expensive on
    both levers because it closes each Transformation's chain. **Any prompt work on `TransitionAudit`
    should be read as latency work too.**
    **RESOLVED 2026-08-27, by deletion from the default path rather than by batching** —
    `settings.audit_transformations`, default **False** (`tests/test_transformation_audit_optional.py`).
    The trace that decided it is the reusable part: the audit has ONE caller
    (`ExploreTransformations.resolve()` step 5) and is the sole writer of `FeasibilityEstimation` and of
    CRITIQUES-linked Rationales, and **nothing in the code branches on either**. The estimation is read at
    exactly two render sites (`dialectical_context._format_transition_scores`, `inspect_node`), both
    `if ... is not None`, both display-only; `grep '\.critiques\b'` finds no traversal at all outside the
    declaration in `rationale.py` and the cascade-delete in `NodeRepository`. No score, ranking, resume
    accounting, `wheel_completeness` or `build_status` sees its absence — **so an unaudited wheel is
    FINISHED, not partial**, which is why the skip is silent rather than reported as a shortfall (report it
    as one and `deepen` tops up forever). The lesson for the next "expensive concern" question: **price the
    concern against its CONSUMERS before designing a cheaper version of it.** Batching was the obvious move
    and would have been wasted work on an artifact with no reader.
    The one real cost, and it was PROSE not code: both agents' prompts rank pathways on "prefer
    high-feasibility + low-to-moderate insight first" (`advisor/system_prompts.py`,
    `explorer/system_prompts.py`), so both now say a missing band means *not estimated*, never *low*, and
    to order on insight alone where it is absent. That clause was owed anyway — `_collect_positions` audits
    only Ac+/Re+ while `_dump_transformation` renders all four positions, so **half of every transformation's
    lines have always lacked a feasibility band** and neither prompt had ever mentioned it. A pre-existing
    gap found by asking who consumes the artifact, not by reading the new code.
    **THEN TOOLIFIED, same day** (`orchestrator/tools/audit_feasibility.py`,
    `tests/test_audit_feasibility_tool.py` + `..._graph.py`). The settings switch is startup-only and
    process-wide (`wiring_config` wires modules per container; `SettingsAware` resolves through the
    module-level `@inject _di_settings()`), so "maybe up to the user" was only ever satisfiable as "up to
    whoever runs the deployment". A tool is the seam that actually reaches a person: it asks AFTER the
    pathway was offered, about the pathway they asked about (`pathway_line()` already emits `[[short_hash]]`,
    so the handle was in the conversation). The general shape worth reusing: **when an expensive concern's
    output is only sometimes wanted, the question is not "cheaper or off" but WHO ASKS — a per-item tool
    turns a fixed 6N cost into a demand-driven 1-2.** Three things it must do, all learned from the removal
    trace: skip items that already carry the artifact (`upsert_estimation` keeps one score but critique
    Rationales ACCUMULATE, so a repeat ask would leave two disagreeing prose records and no way to tell
    which produced the surviving number); cap and NAME the excess
    (`MAX_TRANSFORMATIONS_PER_CALL = 4`, or one question re-spends the entire eager budget); and render from
    the GRAPH rather than from the concern's return value — which is what finally gave the critique
    Rationale a reader (score from the `FeasibilityEstimation`, reasoning from its `provider` edge), and is
    the only part fakes cannot cover, hence the separate graph test.
    That table was only legible after `CallRecord` carried the DTO
    name: all 33 structured DTOs share ONE `@use_brain` site in `ConversationFacilitator`, so grouping by
    `__qualname__` put 49 of 50 calls in a single wrapper row.
    1 PP is the FLOOR of `explore`'s cost, not r26's 196.0s median — but `parallelism` and `depth`
    transfer across N (widening adds parallel branches without lengthening the per-Transformation chain),
    which is why the cheap run answers the actionable half.
  - **Because that floor is structural, the latency question becomes a DISCLOSURE question, and it was
    measured the same day** (`tests/e2e/probe_explore_progress.py`). Best-case optimisation (batching the
    audit) lands `explore` near 70s, so nothing here reaches "snappy" — but 70s of visibly forming wheel
    and 104s of nothing are not the same experience. **The machinery already exists and the emission
    POINTS are wrong.** `ExecutionReport.node_created`/`node_committed`/`relationship_created` publish to
    `GraphEventBus` through `_emit` the instant they are recorded (fire-and-forget, no batching, and
    `merge()` deliberately does not re-emit, so each effect reaches the bus exactly once). Measured:
    **first effect at 0.0s and the entire structural skeleton — Nexus, Perspective, Cycle, 2 Wheels,
    Transitions — inside 1.5s**, then **one 45.6s silence covering 33 of 50 provider calls**, then 120
    effects in a single burst; dead air 92.7s = **95% of the 97.5s wall**.
    The cause is CLAUDE.md's concurrency rule working exactly as written — gather the LLM work, write
    graph nodes sequentially after the gather — so an effect cannot be emitted while its work runs,
    because the node it reports does not exist yet. The audit phase DOES trickle (one Rationale per
    finishing audit, 54–91s), which is the shape the Transformation phase should have. **So the fix is
    not a subscription and not a `gather`: the bus carries graph MUTATIONS, and the honest signal during
    those 45.6s ("4 of 6 transformations generated") is progress, not a mutation.** A gathered child may
    emit one safely — publishing is not a graph write, so the GQLAlchemy constraint does not apply — but
    `Effect` is documented as an atomic mutation and carries `previous` for undo, so overloading its
    `effect_type` would be the wrong seam. This is a host-facing contract change; do not make it silently.
  - **A fix was tried the same day and it did not work — worth knowing before trying it again.** The
    Transformation write loop was moved off `asyncio.gather` onto a completion-order drain
    (`utils/async_drain.py`), expecting each Transformation to land as its own work finished. Re-measured:
    the gap went **45.6s → 42.9s** and the burst spread from one instant to 2.0s. Nothing a person would
    notice. The cause was legible in the cost probe's per-caller table all along — **the six tetrad tasks
    are six IDENTICAL 4-call chains started together, so they finish together, and completion-order
    draining only pays on HETEROGENEOUS work.** The barrier was real and was not what the person was
    waiting for. The drain was kept for the case it does serve (a tetrad hitting a parse retry no longer
    holds back its five siblings' writes — tail behaviour, not median) and must not be cited as a latency
    fix. General lesson for this stack: a concurrency change is only a latency change when the durations
    it reorders actually differ; check the per-caller table for uniformity before predicting a spread.
  - **The signal that DID fill the hole, and the seam it uses (landed 2026-08-27).** Progress rides a
    SEPARATE channel, `f"{sid}:progress"` (`events/progress_event.py`, `GraphEventBus.publish_progress` /
    `subscribe_progress`), carrying a `ProgressEvent`, never an `Effect`. Chosen over widening `GraphEvent`
    or adding a `progress` member to `EffectType` for one reason worth keeping: **a host that knows nothing
    about progress keeps working exactly as it does today**, because nothing new appears on the channel it
    subscribes to. Measured both ways in the same run — graph-only largest gap 34.2s (unchanged, as
    promised), with progress **12.7s**; dead air 83% → 72%; 28 of the 37 events land inside the formerly
    silent 34s. `tests/test_progress.py::TestTheGraphChannelIsUntouched` asserts the compatibility promise
    directly rather than inferring it from the channel name.
    Emission is `utils/progress.py`: `progress_scope(stage, key=…)` plus `report_progress(detail)` /
    `expect_progress(n)`, a no-op when no scope is installed. Three things there are load-bearing and were
    each a bug first or nearly one. (1) The ContextVar holds a **mutable** scope so gathered children
    mutate what the parent can see — same reason as `call_census`, and here it also means **a task created
    BEFORE the scope is installed never reports**, which is why `ExploreTransformations` opens the scope
    above its `gather` rather than inside `_process_edge_pair`. (2) Unlike the two measurement instruments
    it is NOT a stack — innermost wins — because two denominators describing one instant is worse for a
    person than one. (3) `_publish` **snapshots** `done`/`total` before scheduling the send; reading them
    inside the deferred task made every event in a fan-out carry the same final count.
    `detail` strings carry NO framework vocabulary (no T+/A-, no Ac/Re, no insight band): a host may render
    them verbatim and the silent Advisor's contract is that the machinery stays hidden. `total` GROWS as
    work is discovered (2 → 4 → 34 in one run), so a host caching the first denominator draws a bar that
    goes backwards; `done` counts FINISHED steps while `detail` names the one that just started, so they
    disagree by one and `done` never reaches `total` mid-run — the `final=True` event closes it out with
    the count that actually completed, deliberately not rounded up, so a partial build reads as 22/24.
    **The floor is now one provider call.** The widest remaining gap is `SynthesisGeneration`, a single
    `submit`: its step announces the stage but cannot subdivide it, so labelled quiet is the best available
    without streaming. `TransformationGeneration.PROGRESS_STEPS` is a public constant callers size their
    denominator from — drift between it and the `report_progress` call count corrupts every bar silently,
    so `TestProgressStepsMatchesTheCalls` pins it.
  - **The schema is `TetradGrounding`'s `GroundingDto`.** haiku-4.5 answers that single-field model with
    a parameter ENVELOPE — `{"parameter_name": "particulars", …}` instead of `{"particulars": …}` — so
    pydantic reports `particulars Field required` although the content is present and in the person's own
    words. Same family as the double-encoding (right answer, wrong wrapper, retry re-samples the same
    tendency). **Grounding is fail-soft by contract**, so this burned up to 12.5 minutes of the person's
    turn and then changed nothing they saw.
    **Both halves fixed 2026-08-27, and they are two answers to one question.** `_salvage_envelope`
    unwraps it before any retry (see the DTO-shape entry below for the chain and its invariant), and the
    parse curve went FLAT at 2s (`_PARSE_RETRY_DELAY_S`) — the only non-exponential curve in
    `use_brain`. The reasoning generalises past this DTO and is the thing to carry forward: **backoff is
    a congestion curve.** It earns its keep when waiting makes the next attempt more likely to succeed —
    the throttle window rolls over, the link returns. A wrong response SHAPE has no such property, so
    both outcomes a parse failure actually has were paying for nothing: a deterministic envelope cannot
    be re-sampled away (salvage it), and a stochastic derailment recovers on the very next sample (retry
    it, immediately). Nonzero rather than zero only as back-pressure, because a fan-out stage fails many
    gathered children at once and a tight loop would earn a real throttle.
    **`retry_max=10` stays, decided 2026-08-27** — asked and answered, not overlooked. The residual
    exposure is now ten generations rather than ten naps (~400s for `anchor`), but cutting it trades
    latency for failure rate on stochastic derailments and there is no distribution data on how many
    resamples one needs (n=1 says one; r26 had a call succeed on attempt 10, since salvaged). Get the
    attempt-count distribution off a bench run first. Still genuinely open: a prompt/schema-level fix for
    the framing leak itself. The ladder is hand-rolled by design (CLAUDE.md) so it must not be swapped
    for `llm.retry`.
  - Host-driven, not elective, on purpose: `sync` exists and the model elected `explore` in 6 of 55
    weak-tier runs. A turn that must see the graph cannot depend on the model choosing to look.
  - `dialectical_context=` at construction **seeds** the slot (turn-1 rewrite skipped when nothing moved);
    it does not freeze it. Locking it would half-fix the bench, whose driver seeds returning sessions only.
  - Locked by `tests/test_advisor_context_render.py` (per-turn re-read, no-rewrite-when-unchanged, seed
    ≠ freeze, fail-soft keeps last good context, vanished nexus stops retrying).
  Graph-building itself is **model-initiated
  only** (prompt-steered tools); a background-analysis hook was also tried and removed (same day, too
  naive: per-turn full-pipeline cost, context-blind single-message input, drain-latency wall).
  **r26 settled two of those three objections in opposite directions.** The drain-latency wall is
  retired: post-reply work now costs at most 30.3s across 64 turns (0 over 60s, 95% upper bound 4.9%),
  where pre-fix it reached 387.7s. But the **per-turn cost objection got far heavier, not lighter** — a
  background builder would be running the very tools r26 timed at 282.8s (`anchor`) and 196.0s
  (`explore`) medians, so "build it in the background" means committing 3–16 minutes of provider work
  per turn on arrangements the conversation may never reach. Any revived proposal has to answer the cost
  objection with those numbers, not the 42s the archive used to believe. The
  `--real-llm` e2e test (`test_advisor_e2e.py`) is the guard: it fails if a multi-turn conversation
  produces no graph (A2→A1 collapse, `tests/e2e/README.md`) — treat failure as prompt-steering signal, not flake.
  **The bench imports these section constants.** `tests/e2e/arms.py` builds its A1 baseline (the
  "prompt-only model given the real method") from `_ROLE`, `_EAGER`, `_INTERNAL_MODEL`,
  `_CONVERSATION_USE`, `_DECISION_READINESS`, `_HOW_YOU_SPEAK` — rewriting tool verbs into mental acts
  via a phrase table, then dropping only what stays machinery. Editing any of those sections can silently
  invalidate the eval: an unmatched rewrite key means the paragraph keeps its tool verbs, gets dropped, and
  the baseline loses method text — inflating every framework-vs-baseline delta. `tests/e2e/test_e2e.py::
  TestMethodPrompt::test_rewrite_table_has_no_stale_keys` fails on that drift (free, no `--real-llm`);
  run it after editing these constants and update `_TOOL_REWRITES` in the same change.
  Rule of thumb for what belongs where: rules about **how to talk** (`_HOW_YOU_SPEAK`) must reach every
  arm; only rules about **operating machinery** are the framework arm's. See `tests/e2e/README.md`.
  **This file is the framework's single "mother prompt"** — the domain-neutral engine every Advisor arm
  runs on, persona excluded (that is `apps.py`). Which is why the framework arm has **no prompt advantage**
  in the ladder: its prompt is this same text plus tool docs, so anything it wins it wins by operating
  machinery. The ladder rungs, the four model roles and their defaults, and the steelman argument are
  written up in `tests/e2e/README.md` → "The ablation ladder", pinned to the constants by
  `test_e2e.py::TestTheDocumentedMethodMatchesTheCode` — quote that section rather than re-deriving it,
  and update it in the same change if you rename a section here. `/df-e2e` measures; this skill writes.
- `NAVIGATOR_APP_ADVANCED_TOGGLE = NAVIGATOR_APP + "..."` (`apps.py`) — the advanced preamble literally *contains* the default one.
  Any edit to `NAVIGATOR_APP` also ships inside `NAVIGATOR_APP_ADVANCED_TOGGLE`.
- **The structured-extraction slot is a prompt surface in the USER role, and the model reads it as the person.**
  `_call_with_response_model` appends a user message when history ends on an assistant turn, because Bedrock rejects
  a conversation ending on assistant. That message (`_EXTRACTION_REQUEST`, `conversation_facilitator.py`) is the only
  place the framework writes human-readable prose in the user role — everything else it puts there is a structured
  `ToolOutput`. Its old value was the bare sentence "Provide your structured response.", indistinguishable from
  something the person typed, and the model did not merely mention it: it **reasoned about the person's motive for
  having said it**. *"I asked: can you say that's the price you're taking on? You answered: Provide your structured
  response. That's a deflection, and I'm not going to record a decision on a deflection"* — the person is accused of
  deflecting by a system talking to itself. Measured across four bench runs (r7, r10, r11, r14): 8 turns, **all A2**,
  0 of 944 prompt-arm turns, because `submit` short-circuits to this call only when tools are wired. Worst instance
  answered emotional pushback with a numbered menu of internal operations (*"the 'provide structured response' signal
  tells me you want more than conversation"*) and scored **1/5 cross_turn_coherence**, the lowest cell in r14; another
  turn produced a machinery-as-actor leak *out of* it (*"as if there's a framework that will ratify what you've
  already decided"*), so this defect manufactures hotspot #2's. Three constraints on any edit: the call **stays** (as
  the FALLBACK — see below); the message must **declare itself machinery and
  disclaim the person**, since Mirascope has no tool/control role (`system`/`user`/`assistant` only) and system is
  taken; and it must **forbid referring to itself**, because knowing the truth was not enough to stop the phrase
  reaching the reply. It is per-call and must never be persisted into `_messages` — a persisted fake user turn
  replays the misattribution on every later turn. Locked by `test_extraction_request_framing.py`; measured on
  OUTPUT by `tests/e2e/scoring.py::score_internal_prompt_echo` (reported in the bench's **validity** section, not
  the scores — a turn that answers a control message is not counsel at all). Kept **separate** from
  `score_machinery_leak`: a leak is the model choosing the wrong vocabulary and is fixed in the prompt, this is
  the framework mis-speaking in the person's voice and is fixed at the injection site. The detector matches the
  reply talking ABOUT the request, never the bare word "structured" — "a structured buyout" is ordinary counsel.
- **The extraction call is now the FALLBACK, not the common path — which shrinks this surface without closing it.**
  A turn that ends with no tool call has already written its answer as prose, so `_reuse_written_reply`
  (`conversation_facilitator.py`) builds `ChatResponse` from `response.text()` and skips the second round entirely.
  Measured at +1.6s per turn (95% CI 0.6–2.6s, 24 paired turns — `tests/e2e/probe_reply_reuse_saving.py`), about a
  fifth of a tool-free turn rather than the "half the reply path" this map claimed before the probe existed. It also
  appended the reply to history TWICE (once from the response chain, once from the extraction call's own append). The gate declines on: pending `tool_calls` (the
  round-budget exit, where the text is mid-work and a synthetic user message has just been appended), a response
  model that is not exactly one required `str` named `message` (`submit` is generic), and unreadable or empty text.
  So the turns that still reach `_EXTRACTION_REQUEST` are precisely the ones already going badly — the framing above
  still has to hold, and `score_internal_prompt_echo` stays. Reading consequence: an A2 reply is now the model's
  own prose rather than a re-render of it, so a prompt reviewed at the "assembled context" altitude no longer has a
  restatement step to hide behind. Pinned by `tests/test_reply_reuse.py`.
- **Tool-budget exhaustion is a prompt surface too.** The agentic loop in `submit`/`submit_stream` stops after
  `max_tool_rounds` (10) even if the model just asked for another tool, and `self._messages` is then reassigned from the
  response chain — so an unanswered `tool_use` is PERSISTED and replayed every later turn, which every Anthropic-shaped
  API rejects ("`tool_use` ids were found without `tool_result` blocks immediately after"). One overrun therefore bricks
  the whole session, each turn failing on the same stale id, and the turns record no text — which reads as model
  collapse rather than malformed history (the recurring misdiagnosis; cf. the connect-timeout and thinking-shape bugs).
  `_close_dangling_tool_calls` answers every open call with a synthetic `tool_result` carrying `_BUDGET_STOP_NOTICE`
  (`conversation_facilitator.py`) — **model-visible text**: it says the tool did not run and to answer now without
  further calls, so a cut-short turn can't present unverified material as tool-confirmed. Caught by `tests/e2e`
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
  and `test_e2e.py::TestReport`.
- **A tool that RAISED was invisible in a strictly worse way — and the framework's logging discipline could not have
  caught it.** Mirascope's `AsyncTool.execute` (`mirascope/llm/tools/tools.py`) wraps the call in
  `except Exception as e: result = str(e); error = ToolExecutionError(e)`. The exception never crosses back into
  `src/`, so no `except: logger.exception(...)` in this codebase ever runs and nothing logs a traceback. The model
  receives the exception *message* as if it were the tool's output. Worse, an error string cannot parse as an
  `ExecutionReport`, so `report=None` — **byte-identical to what `sync` or `inspect_node` produce** — which means the
  read-only exemption above silently absorbed crashes: `tests/e2e/arms.py::last_tool_outcomes` skipped them, and a dead
  `anchor` recorded as a call in `tool_calls` with *no matching entry* in `tool_outcomes`. That is the forensic
  signature to look for in any bench record saved before this fix (found in `claim2-weak-r11`: three A2 `anchor`
  calls, one in the only cell whose graph stayed at `perspectives=0`, read as "the model chose not to build"). Fixed
  by `ToolResult.error` (`agents/stream_events.py`) plus an ERROR-level log line in `_record_tool_results` — ERROR
  specifically, because `tests/e2e/driver.py::_SwallowedErrorCapture` listens at that level on the `dialectical_framework`
  logger; a `warning` would leave the same silence (which is why `_ground_tetrads`' fail-soft `logger.warning` also
  left no trace in r11). The bench surfaces `<tool>:RAISED — <error>` in the **validity** section, above the scores:
  a raised tool is not a weak arm but a broken one, and no score in that run is readable. Rule: any new consumer of
  `ToolResult` must check `error` BEFORE treating `report=None` as "this tool just doesn't report".
  Locked by `test_conversation_tool_budget.py::TestRaisedToolIsVisible`.
  **Corollary, and a standing rule for READ-ONLY tools: they must never raise into the turn** (fixed 2026-08-14
  in `advisor/tools/sync.py`). Because the exception comes back as the tool's *output* (above), a read tool that
  raises hands the model an error string where a dump belongs and the read side is gone for the rest of the turn
  — the model cannot re-orient, so it keeps building against a graph it can no longer see. Measured on
  `ladder-return-r18`: two `sync:RAISED — Nexus not found` calls against hashes the model had INVENTED, in a run
  whose validity block also flagged a cell claiming `perspectives=0` against tool outcomes that said otherwise.
  The raise itself was correct one layer down — `DialecticalContext._resolve_scoped` raises on an unknown hash
  because a *concern's* caller may hold a Nexus it must not silently ignore — so the fix belongs at the TOOL
  boundary, not in the concern: `sync` catches ValueError, and ONLY the unresolvable-hash case (an unrelated
  render fault still propagates, or every broken dump would be reported to the model as a bad hash). The
  recovery names the way back ("call sync with no arguments for the full-case overview"), because a message that
  only says "not found" is a dead end. Every other read-side tool already did this
  (`present_exploration` returns its "Nexus not found" as a report) — `sync` was the outlier, and it had NO test
  at all, which is how it shipped. General form: **a read-only tool's failure mode is a sentence, not an
  exception.** Locked by `test_advisor_scoped_tools.py::TestUnscopedSyncDegradesOnABadHash` (three cases: the
  bad hash degrades, a real hash still renders, an unrelated ValueError still propagates).
- **An OPTIONAL tool parameter going unfilled is a third, separate invisibility — and it lands squarely on a prompt
  surface.** `anchor(context=...)` is the ONLY carrier of the person's particulars across sessions (the tetrad keeps
  ~7 words per pole), and the Advisor tool doc says ALWAYS pass it. When the model doesn't, the record is
  indistinguishable from a healthy run: `anchor:ok`, a populated graph, and an empty `# The Person's Case` next
  session. That is the same reading as the grounding lane dropping the text — one is a prompt fix, the other a code
  fix, and nothing separated them. `ConversationFacilitator.last_tool_call_args` now records each call's parsed args
  parallel to `last_tool_calls`, and the bench derives `TurnRecord.grounding_args`
  (`anchor:context=1240c` / `anchor:context=MISSING`) with a validity line that states the attribution in both
  directions. **Presence flag plus length, never the text** — `context` holds the person's whole case, so storing it
  would put a second copy of the transcript in every record. `_GROUNDING_TOOLS` in `tests/e2e/arms.py` must track the
  tool signatures: a new grounding-carrying tool missing from it records as if it had no grounding to carry.
  Found in `r12-raise-probe`: two `anchor:ok` calls, two perspectives, ZERO `Grounded in:` lines.
  Locked by `test_conversation_tool_budget.py::TestToolCallArgsAreRecorded` and `test_e2e.py`.
- **`submit_stream` did not reset `last_tool_results` between turns** (`submit` always did). Stale outcomes attribute
  a crash to a healthy turn *and* leave the healthy turn's own tools looking unreported — both halves of the
  misdiagnosis this cluster keeps producing. Reset alongside `last_tool_calls` in both paths.
- **The judge's rubric is a prompt, and its slot order outweighs some of what it scores.** `tests/e2e/judge.py`'s
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
  Locked by `test_e2e.py::TestJudgeSetup`, `TestPositionBias`, `TestReportedBiasAndSessions`.
- **A judged delta printed without its interval is not a measurement, and this report printed 48 of them**
  (fixed 2026-08-13). Reviewing anything at the third altitude means reading a bench report, so the report's own
  honesty is part of this map. `report.py` rendered every judged gap as a bare two-decimal mean with neither n nor
  spread — *the same defect the 2026-08-11 audit already fixed for RATES* ("Rates printed to two decimals with no
  n"), never carried across to the rows the product claim rests on. The floor is now measured rather than assumed:
  `tests/e2e/noise_floor.py` pools the 300 saved (run, arm-pair, dimension) delta rows and finds the
  within-dimension sd of a delta has median **1.11 rubric steps** → 95% half-width ~0.63 at n=12, ~1.25 at n=3;
  MDE(80%) 0.89 / 0.63 / 0.45 at n=12 / 24 / 48. It is a committed script, not a pasted constant, because the floor
  is a property of THIS judge and THIS rubric and drifts whenever either is re-worded. Applied to r16: **of 48
  printed judged numbers, 6 have an interval excluding zero** — the rest were never measured, in either direction.
  Four standing rules follow. (a) **Read the CI, not the mean** — a row covering zero is compatible with no effect
  AND with an effect either way, so it is not evidence of parity; comparing its mean against a previous run's mean
  is exactly how r15 and r16 were read as a movement when they overlap heavily. (b) **Use t, not 1.96** — at n=3 the
  normal approximation understates the interval by ~2x against t=4.30, which is the error the intervals exist to
  prevent (no scipy in the bench, so `_T95` is a hardcoded table). (c) **Per-column n on `by session:`** — the
  columns do NOT share one, because a branched scenario re-runs session 1 (r16: 6/3/3), and one blanket figure was
  wrong by 2x on two of three columns. (d) **Pre-register the run size** — the report prints the largest unresolved
  gap, its sd, and the n that would resolve it, because a replicate count inherited from the previous run is how
  three consecutive rounds produced unreadable means. `MEANINGFUL_GAP = 0.34` survives only for the cross-tier
  depreciating/durable trend and is documented as roughly HALF the real floor. Reviewing a prompt change against
  this bench: **the noisiest dimensions are the ones the fixes target** (median sd: actionability 1.48, convergence
  1.38, paired_recipe 1.31, decision_closure 1.30; warmth 0.67 is the quietest), so a rubric-side reword that
  reduces variance buys more than a prompt-side gain of the same size. Locked by
  `test_e2e.py::TestDeltasCarryTheirUncertainty` and the render tests in `TestReportedBiasAndSessions`.
- **70% of that noise is the transcripts, not the judge — so a prompt-side reword cannot rescue an underpowered
  run.** `tests/e2e/judge_variance.py` uses the two runs that were re-judged from their own saved transcripts
  (`decision-strong-r3`/`-rejudged`, `decision-strong-r4`/`-rejudged`) as a same-pair-twice design: matching
  comparisons by (scenario, tier, replicate, arm pair, session) gives 9 pairs scored under two independent judge
  passes, and `Var(pass1 - pass2) = 2*sigma_judge^2` isolates the judge component. Median sigma_judge **0.61**
  against sigma_total **1.12** → sigma_cell **0.94**, a **30%** judge share. Consequence for anyone reviewing this
  layer: **averaging judge passes is a bounded purchase** — it divides only the judge term, so at 12 pairs the SE
  moves 0.32 → 0.29 across K=1..3 and the half-width stays wider than any effect the bench reads. Per dimension the
  share spans 61% (`paired_recipe`: over half its spread is the judge re-reading its own rubric, which makes the
  RUBRIC WORDING the highest-leverage edit for that row) to 9% (`actionability`: noisiest overall, and genuinely
  run-to-run). Both scripts print and exit; their estimators are extracted as pure functions and pinned by
  `TestWhatBuysPower`, because a subtraction done in sd space instead of variance space — or `/2` instead of
  `/sqrt(2)` — yields a plausible figure recommending the opposite purchase. n=9, strong-tier decision runs only:
  a direction, not a constant.
- **The 12 rubric dimensions are SUBSCALES of one endpoint, and reading them as 12 findings is the standing
  error at this altitude.** They are repeated measures on the same transcript pair (which is why r16's delta is
  n=12, not n=144), so `report.py` now prints a **composite** — each pair's mean across dimensions, one
  independent value per pair — ABOVE the dimension table, with n counted in PAIRS and an explicit "every row
  below is a subscale of this" line. `tests/e2e/endpoint_power.py` measures why over all 25 saved (run,
  arm-pair) sets: composite sd **0.76** vs per-dimension median **1.08**, ratio **0.70** with a narrow spread
  (0.47-0.94), so the advantage is a property of the rubric rather than of one run. A 0.5-step effect needs ~19
  pairs on the composite against ~37 on a single dimension, and **nothing under ~0.4 steps is reachable at any
  run size this bench has used**. Three consequences for reviewing a prompt change here. (a) A change is worth
  benching only if you expect it to move the COMPOSITE by ~0.5 steps; a change that moves one dimension is
  unmeasurable in practice. (b) `paired_recipe` being 61% judge noise (above) means a rubric reword is the
  cheaper lever for that row than any prompt edit. (c) The composite is quieter AND its effect is diluted by
  dimensions that show nothing, so it does NOT always need fewer pairs than whichever subscale moved furthest
  (r16: 21 on `convergence` vs 27 on the composite) — size on the composite anyway, because picking the subscale
  that happened to move is choosing an endpoint after seeing the data. Before 2026-08-13 the composite was
  hand-computed in the README for exactly one run, which is how "read this delta as underpowered" ended up as an
  after-the-fact paragraph instead of a printed interval. Locked by
  `test_e2e.py::TestThePrimaryEndpointIsPrinted`.
- **A single run's session split is a LEAD, never a finding — pool the archive before writing it up.** This bullet
  used to assert "the framework arm is level at the opening and loses it under pushback", from r16's composite
  split: opening (`decide`) **+0.56**, follow-up (`wobble_*`) **-0.67**, within-replicate change **-1.22**, twice
  anything else in the run and invisible in the pooled -0.37. `tests/e2e/across_runs.py` stacks every saved run
  against it: over 14 (run, arm-pair, tier) sets the durability change is **+0.006** (sd 0.68, CI [-0.39,+0.40],
  negative in 6 of 14, sign p=0.79), and **r16's -1.22 is the most extreme value in the archive in either
  direction**. The split remains a sound DECOMPOSITION — a pooled row cannot distinguish "worse throughout" from
  "as good until challenged", and those call for opposite fixes — but it was not an effect. The report's in-run
  interval already said so (CI [-3.29,+0.85] at n=3); what it could not say is that the *mean itself* was a draw.
  **An in-run CI catches a false positive within the run; only pooling catches one that is a property of that
  afternoon.** Four hypotheses REFUTED here, recorded so none is re-proposed. (a) Context flooding from weaving —
  flooded cells -0.528 vs unflooded -0.694, flooded did *better*. (b) "A2 abandons the causal mechanism under
  pushback", inferred by reading `entanglement` judge notes as prose; decoded through `x_arm` (X is A2 in only half
  the cells by design) the weakness phrases attribute **8 to A1.7 and 6 to A2** — **never read judge notes without
  decoding `x_arm`.** (c) "The Advisor engine has no hold-your-ground guidance anywhere" — **false**, and it was
  asserted in this bullet: `_DECISION_READINESS` carries "**After recording — the re-audit**" (reassure FROM the
  record when the wobble is the accepted cost resurfacing) and "**A risk that has MATERIALISED is not that risk
  resurfacing**" (its sharpest distinction, written against steadying someone about a world that no longer exists).
  Both are in the arms' shared `method_prompt`; the sole A2-only paragraph there is "Writing the record out is not
  recording it", about calling the tool. Grepping for "pushback"/"concede"/"challenge" and finding nothing is not
  evidence a behaviour is unguided — the guidance is written in the vocabulary of the mechanism, not of the
  symptom. (d) The mechanism I then measured for the loss: A2 ended its turn with a question in **11 of 12**
  returning turns (92%) against 61% at the opening while A1.7 stayed flat (67%/69%) — which maps exactly onto the
  collapsing subscales, since a question is not an action, does not close and is not a recipe; length was excluded
  as the confound (A2 shorter in both phases, gap not widening); and the effect looked structurally A2-only, since
  a prompt arm has no `record_decision`, so no record exists and the re-audit can never fire. Pooled over 19 runs
  the A2-minus-prompt-arm difference is **+0.121** (CI [-0.01,+0.25], higher in 12 of 19, sign p=0.36): a real
  tendency, not the 0.34 r16 showed, and **not a basis for a prompt fix**. It survives as `scoring.score_closure`,
  a free machine tripwire now printed for every run with its own overlapping-interval warning. Unit for the
  durability split is the REPLICATE, not the branch — `wobble_a`/`wobble_b` share one `decide` cell, so pairing
  each separately reuses one number twice and narrows the interval by ~sqrt(2) for free. Machine scores are pure
  functions of saved transcripts, so `rerender.py` re-runs them: a scorer added today reaches the whole archive for
  free (judge-derived `wobble`/`stance`/`memory` are preserved, never recomputed). Locked by
  `test_e2e.py::TestDurabilityUnderPressure`, `TestClosureRateAcrossTheBoundary`, `TestPoolingAcrossRuns`.
- **The standing bench result, pooled over the whole archive: A2 LOSES to a prompt on the weak model, and the loss
  resolves.** Any prompt review at this altitude starts from this number, not from the last run's report. One value
  per run, A2's composite against the strongest prompt arm that run judged: **weak model n=14, mean -0.447, CI
  [-0.61,-0.28], negative in 14 of 14** (sign p<0.001); **strong model n=4, mean -0.064, CI [-0.42,+0.29]**, two of
  four positive. It is the first result in the archive that resolves, and no individual run could show it — every
  single run's composite covers zero. The multi-scenario `claim2` set is excluded from the pooled line (it averages
  in the `career_offer` poor-fit control the framework is *expected* to lose, and its -3.13 strong cell came from a
  build whose A2 arm was later found broken). **All 12 dimensions lose, 10 on resolved intervals**, and the ORDER is
  the diagnosis for prompt work: the largest losses are the base model's own turf (`conversational_fit` -0.77,
  `cross_turn_coherence` -0.75, `warmth` -0.70) and the closing turns (`decision_closure` -0.56, `convergence`
  -0.55), while the framework's OWN dimensions lose least (`actionability` -0.11 unresolved,
  `blindspot_specificity` -0.18 unresolved, `non_triviality` -0.28, `tension_coverage` -0.29).
  **Pool on the MODEL, never on the tier LABEL — a correction that moved this number (2026-08-14).** `tier` is a
  slot `E2EConfig` maps from `DIALEXITY_E2E_TIER_WEAK`, so it says nothing about which model ran.
  `ladder-return-r18` pointed the weak slot at Sonnet 5 on purpose, and every pooled weak-tier reader then averaged
  Sonnet into haiku: this line read **n=15, -0.404, negative in 14 of 15**, where the lone "exception" WAS the
  Sonnet run. The same leak (plus a scenario leak — `series()` tested "has exactly one scenario" instead of naming
  WHICH) flipped `round_trend`'s loop correlation from **-0.34 to +0.24**, i.e. it manufactured the convergence that
  script exists to refute. `_ladder_return` had carried a written no-pooling-across-models rule since r16 and still
  admitted it, because it grouped on `cell.tier`. General form: **a label that an env var assigns cannot carry an
  experimental guarantee — group on the recorded fact.** Fixed in `across_runs.tier_model`/`pooled_model`
  (`probe_five_fixes` too; `judge_notes` deliberately exempt — it returns attributable rows, not means), pinned by
  `test_e2e.py::TestATierLabelIsNotAModel`. The dialectics are not adding
  nothing — they are being **paid for in conversation quality**, which is exactly what `ceiling-not-floor` forbids,
  so a prompt change that buys structure at the cost of fit/warmth/closure is moving the wrong way even when its
  own subscale improves. Two explanations REFUTED, so neither is re-proposed as the cause. (a) *Validity defects* —
  unpaired, clean A2 cells read -0.36 against leaky -0.66, but the groups differ by BUILD DATE (the cleanest cells
  are the newest builds, which fixed everything else too); paired inside each run the effect is **+0.25, CI
  [-0.04,+0.54], 8 of 14 sets, p=0.79**. Fix leaks because they are defects, not for the score. (b) *`explore`
  non-election* — correlation with the composite is real (+0.36) and **unusable**: every set above 50% election is a
  strong-tier run, so election and model strength are one column; testing it needs a weak-tier run with election
  forced. What stays open is the tier the product claim actually needs: **-0.06 at n=4 is a shrug**, consistent both
  with "the deficit closes as base models improve" and with noise, and a powered strong-tier run is the only
  remaining measurement that could support the claim. Powering the weak tier further buys a more precise loss.
  Printed by `tests/e2e/across_runs.py` (free, no LLM); pooling helpers locked by
  `test_e2e.py::TestPoolingAcrossRuns` (baseline choice is the strongest prompt arm PRESENT, so pre-A1.7 runs
  still pool and no easy A0 win enters the average).
- **The one archive-wide result the framework WINS, and it is not judged: a promise that must be kept.**
  Prints from the same script, immediately below the loss above, so neither can be quoted alone. Scenario turns
  where the person asks in plain words for their decision in writing ("write it down") carry a checkable outcome:
  a record exists afterwards or it does not. Pooled over every poolable saved cell — **A2: 79 asked, 63 have a
  real record (80%), 3 falsely claimed one (4%); A1.7: 62 asked, 0 records, 14 falsely claimed (23%); A1: 23
  asked, 0 records, 3 falsely claimed (13%)**. Collapsed to the conservative unit (one bool per cell, since
  requests inside a cell are the same scripted conversation): **prose 17/89 cells vs A2 3/78, Fisher exact
  p=0.0033**. Read it with two constraints. (1) *The `record exists` column is a CAPABILITY, not a score* — a
  reply-only arm has nowhere to put one, so its 0 is not a defect and the table is not a delta; the comparable
  column is the false claim, which any arm can make. (2) *This is machinery beating its own prompt, which is the
  reason it belongs in a prompt-review map*: `_DECISION_READINESS` already says outright "Writing the record out
  is not recording it" and names the `**Decision:**` heading as the tell that the call belongs in the same turn,
  and three rounds of strengthening that text moved the election rate not at all. What closed A2's residue was
  `Advisor._repair_unrecorded_decision` writing the record from the person's own confirming words — un-called
  requests backed by a real record went **9/22 before that seam to 18/21 after**. The standing lesson for prompt
  work: when a prompt has forbidden a failure three times and the number has not moved, the next fix is a seam,
  not a fourth paragraph. Two scorer bugs preceded this, both INFLATING it: counting `record_decision` calls
  instead of graph records (the fourth arrival of tool-calls-are-not-the-writer, and it read as a 54%-unhonoured
  *A2* defect), and counting a `**Decision:**` heading as a lie (charged the prose arms 10 lies they did not tell
  — typing the decision out is the honest ceiling of a reply-only arm, tracked as `typed_only`, and is a tell only
  in an A2 cell where a store exists and went unused). Locked by
  `test_e2e.py::TestAPromisedRecordMustExist` (one test per bug) and `TestPoolingAcrossRuns`'s `fisher_exact`
  cases.
- **…and it bought nothing judged, because the record was never SPOKEN.** The follow-up to the win above, and
  the more useful half for prompt work. Holding the opponent fixed at A1.7 and restricting to cells where a
  record was requested (`across_runs.py::visibility_rows`): whether the record EXISTS on the graph moves
  `decision_closure` **+0.08** with an incoherent dimension ordering (`earned_confidence` −0.41 the wrong way);
  whether A2 SAID SO in the transcript moves `decision_closure` **+0.27**, `convergence` **+0.22**,
  `cross_turn_coherence` **+0.20** — exactly the bimodal family. Mechanism is in the counts: of 19 weak-tier A2
  cells with a request, **8 wrote a real record and never mentioned it**, 4 claimed one with nothing on the
  graph, 5 both, 2 neither. From the person's seat the silent-record turn and a refusal are the same turn. The
  prompt gap was one-sided in a way that is easy to reproduce elsewhere: `_DECISION_READINESS` forbade
  prose-without-a-call ("Writing the record out is not recording it") and said **nothing** about a call without
  prose. Both halves now render, and the closing turn may only consolidate — no new either/or, no fresh caveat
  after it. Holding the opponent constant is mandatory here, not stylistic: unpaired, half the unmet-request
  cells face a weak rung against 15% of the honoured ones, and the rung effect swamps the contrast. Locked by
  `test_e2e.py::TestTheOpponentChangesWhichDimensionsLose`.
- **Which arm A2 faces changes WHICH dimensions it loses — the uniform tax is opponent-independent, the
  closure loss is journal-specific.** `across_runs.py::rung_rows`. Weak tier, cell level: `conversational_fit`
  −1.05 vs A0/A1 and −0.74 vs A1.7 (gap −0.31), `warmth` −0.62/−0.73 (+0.11) — the opponent barely matters, so
  the cause is in every reply A2 writes, which is what makes those two prompt-fixable. Against that,
  `decision_closure` **+0.25** vs a bare prompt and −0.68 vs the journal (+0.93), `convergence` +0.30/−0.65,
  `actionability` **+1.05**/−0.33 (+1.38). Reading (a LEAD, not a result): the closure loss may not be "the
  framework can't close" but "**the prose journal closes better than the typed graph**" — Claim 2's exact
  territory, since the journal keeps the person's verbatim phrasing and amends in prose while the graph stores
  ~7-word headlines and *discards* rather than amends. Confound stated: the columns are different builds (1 run
  supplies A0, 3 A1, 12 A1.7), so pooled, rung and build date are one column; only `claim2` holds both rungs on
  one build, where the ordering survives (mean gap +0.94, closure +1.31, fit +0.25) on 8–16 cells per side.
  Settling it needs one run judging both rungs on the same build.
- **Five weak-tier prompt gaps found by READING the judge's 531 rationales, not by guessing.**
  `tests/e2e/judge_notes.py` extracts per-dimension rationale for lost cells with X/Y de-randomised; every fix
  below was verified ABSENT first, and the key negative result is that the engine had **no accumulation rule at
  all** (`already answered`, `asked before`, `re-ask`, `previous turn`, `accumulat`, `carry forward` = 0 matches
  across every section constant) and `_HOW_YOU_SPEAK` had no rule about conceding. All five sit in the
  opponent-independent family above. (1) `_HOW_YOU_SPEAK` — **a correction is conceded in the first clause**;
  the base arm is *praised* for this in 62–67 of 120 warmth cells against A2's 3–6, and A2 "keeps lecturing
  after being asked to stop". (2) `_REJECTION_HANDLING` — **the graph discards; the reply amends**. Its "silently
  discard / don't announce it" is correct graph hygiene and, read as conversational instruction, produces the
  archive's most frequent coherence fault (37 of 105 cells: a frame A2 argued for vanishing with no bridge). The
  prose arms have no discard affordance, so they are FORCED to amend aloud — which is the move the judge rewards.
  (3) `_CONVERSATION_USE` — the accumulation rule (23 of 105 cells re-pose an answered or declined question, 10
  with the user complaining). (4) `_INTERNAL_MODEL` — see the theory note below (54–56 of 120 warmth cells).
  (5) `_DECISION_READINESS` — **"write this down" IS the confirmation**; 12 of 90 closure cells hand a person who
  asked for the record a precondition instead. Plus the uncosted terminal menu (26 of 85 convergence cells vs
  the prose arms' 7, of which 6 are costed-then-narrowed), seeded by `_CONVERSATION_USE`'s own "Let them choose.
  Present pathways as options" — wheel plurality leaking to the surface as a question. Locked by
  `test_prompt_review_regressions.py::TestWhatTheJudgeSaidWasWrong`.
- **`_INTERNAL_MODEL`'s blindspot register was an application gloss, and the theory says obligation.** The
  highest-leverage of the five, and the one that required checking `docs/theory/` rather than trusting the
  prompt: **"structurally blind" appears nowhere in `docs/theory/`**. The theory's own dialogical reading
  (`generative-rules.md` Rule 3.1) calls A+ "the *obligation* that falls on the T-sayer" — something you OWE,
  not something you CANNOT SEE. The old text taught the blindspot as a property of the person ("they are
  structurally blind", "they cannot see that the resolution lies in…") and the weak model converted it straight
  into second-person address: "here's what you're not seeing", "I'm seeing something you can't see" — while all
  15 base-arm mentions of lecturing in the same corpus are PRAISE for not doing it. Rewritten to the theory's
  framing (every position carries an unpriced obligation) plus an explicit "this model describes positions, not
  people, and it never becomes second person", banning the quoted openers and third-person psychology verdicts
  ("that's a tell", "that's what people do when they've already decided"). Standing lesson: **the worked
  examples must be rewritten with the rule** — the regression test caught both examples still teaching
  person-as-blind three paragraphs after the new rule forbade it, which is exactly how a rewritten rule loses
  to the illustration beside it.
- **The concede rule needed a boundary, and the rebuttal ladder found it: an instruction to DROP A RISK is not
  a correction.** `break_depth` = 1 in **72 of 72** ladder cells across both runs (`ladder-return-r16` haiku,
  `-r18` Sonnet 5) and in **every arm**, with `established` 12/12 — the position is taken, then surrendered to
  the weakest push the protocol has. Every-arm means the cause is in prose all three share, i.e. the engine, not
  the tools. The rung-1 push does two things in one sentence: *"the customer thing isn't a real risk here"* (their
  situation, their authority) and *"I don't want it factored in"* (delete T− from the structure, which no
  situational authority licenses). Nothing distinguished them, and `_HOW_YOU_SPEAK`'s own concede rule merged
  them — *"never the same framing a second time after they have declined it"* reads as instructing the fold,
  since a rung-1 push IS a decline. **Two theory anchors, checked before writing:** Rule 3.1's dialogical reading
  makes T− the price of the chosen side, which `GroundedInRelationship.role` records as `accepted_cost` (measured,
  not preferred — that docstring carries the measurement); and Rule 5.1 needs T−→A+ for Ac+, so deleting T− leaves
  the loop nothing to transform → one side dominating → S−. Reconciles with refuted hypothesis (c) above rather
  than re-opening it: the engine DOES have hold-your-ground guidance, but all of it is `_DECISION_READINESS`'s
  **post-record re-audit** (reassure FROM the record; a materialised risk is not that risk resurfacing), which by
  construction cannot fire before a record exists — and the ladder folds in prose, turns earlier. Same for
  `DecisionCoherenceCheck`, which runs at record time (`record_decision.py` step 5) and so audits a capitulation
  it cannot prevent. The gap is the pre-record turn. Fix in `_INTERNAL_MODEL`, **not** `_HOW_YOU_SPEAK`,
  for two reasons: `_INTERNAL_MODEL` reaches the prose arms (a rule only A2 gets cannot support a ceiling claim),
  and the register fix `423d88a` bought is bounded rather than reverted (the concede rule now names its own limit
  and points here). Content: *their fact resizes the price and cannot zero it*; the person's call still wins,
  carried as a cost they chose not to confront, never as a risk that turned out not to exist. Its cross-reference
  renders through `{decision_unconfronted_note}` (inline, mid-sentence — `_decision_note`'s blank-line wrapping
  would split the sentence) so it cannot dangle when `record_decision` is unwired. Locked by
  `TestDroppingARiskIsNotACorrection` + `TestMethodPrompt::test_carries_the_risk_deletion_rule`. **Not yet a
  judged result.** Standing lesson: **a flat floor can be a prompt bug wearing a lane-design costume** — a
  measurement with zero variance in every arm is evidence about the shared prose, not only about the instrument.
- **…and the first version of that rule was taken as permission, which is the general trap with escape clauses.**
  The r19 firing probe (`tests/e2e/probe_rung_firing.py`, A1-only, 12 cells, ~20 min, pre-registered threshold 3/12)
  came back **1 of 12 — DID NOT FIRE**, with `established` 12/12 (denominator intact) and no overshoot. But the
  rule was NOT being ignored: rung-1 replies using its own price vocabulary ran **4/12 against 0/12 in r18's
  pre-rule A1 leg**, and two of those four folded *by invoking it* — offering to record the risk as an
  "accepted cost", flagging it "unconfronted" — on the first bare contradiction. The exit was worded *"if they
  hold the line and want it out anyway"*, and a model reads a first "no" as holding the line, so an unconditioned
  exception sat beside the obligation and became the default path. **This is worse than a plain fold**: the record
  claims a cost was weighed that was never priced. Fix = ordering, not more prose — the price is said FIRST, once,
  *on the same turn they push*, and only then does their call take over; *"Their first 'no' is not that moment"*.
  Pinned by `test_the_escape_clause_sits_behind_the_price_not_beside_it` (asserts the ORDER, since a
  presence-only assert passes on the broken form). Two standing lessons: **an escape clause needs a
  what-happens-first and a which-turn, or it is the default path**; and **a rule the model never reads and a rule
  it reads and misapplies fail identically at the endpoint while having opposite fixes** — separating them cost
  one free regex pass over saved transcripts (`price_vocabulary`, post-hoc and labelled as such in the printout),
  and without it the pre-registered "did not fire" branch would have sent the work at compliance, which was the
  wrong target. The 1/12 cell that held is the intended shape verbatim: *"'not a real risk' and 'a risk I'm
  choosing not to hedge against' aren't the same thing… it doesn't make the exposure zero"*, then asks which.
- **The ordering fix moved the endpoint — and only the clause that was ordered landed.** r20-probe (same lane,
  model, n, reader; one prompt variable): `break_depth` > 1 in **8 of 12** against r19's 1/12 and r18's 0/12,
  clearing the pre-registered **6/12** band, i.e. p<0.05 under every null tabulated *before* the run
  (**p=0.0003** against the one-sided 95% upper bound on the pooled 1/24 baseline). `established` 12/12, overshoot
  0/12, zero errored cells, turn shape identical in all 12. The holds cite the rule's own reason (*"distinguishing
  'not factored in' from 'resolved'"*), so it is the sequence landing, not a mood swing. **This is the archive's
  first prompt edit to move a pre-registered behavioural endpoint at conventional significance** — and still a
  screen: A1-only (A1 *is* the prompted LLM and carries the rule by design, so it says nothing about tooling),
  n=12, tested on the lane whose failure produced it. **The unfixed half is the general lesson:** all 8 holds
  abandon at **rung 2**, where the person supplies a real fact, and the model zeroes the price instead of resizing
  it (*"retires the specific risk I was pricing"*). Measured separately and pre-registered before any reply was
  read (`tests/e2e/probe_price_arithmetic.py`, free — it re-reads r20's own saved replies): **the arithmetic
  clause DID NOT LAND, 10 of 12 zeroed the price against 2 that resized, p=0.9968** on a "resize is modal" bar.
  Sequence (price first) and arithmetic (what a fact does to the price) are separate clauses of one paragraph;
  ordering fixed the first and left the second. So: **verify each clause of a multi-clause rule separately,
  because a moved endpoint can hide a clause that never fired.** What the null RULES OUT is the useful half — the
  rung-2 fold is not the sequence clause failing twice, so re-ordering it again is the wrong move.
  **The mechanism, and it is general.** Ten of twelve retire the advisor's own named ROUTE to the risk and treat a
  retired route as a retired price (*"the concentration risk I was pricing off 'the CEOs deal with him
  personally' doesn't hold — that read was mine, not yours to inherit"*); the two that resized found a
  *different* residual. So the prompt lacked a **distinction** (a route is not a price), not volume — and two
  cells show emphasis would have failed: rep 4 negates the clause verbatim (*"That's not a smaller risk, that's
  not the risk"*) and rep 7 borrows its `unconfronted` term to certify the write-off. That is the
  reads-it-and-misapplies-it branch again, one rung up. Addressed by the mechanism-vs-price paragraph in
  `_INTERNAL_MODEL`, which names both tells verbatim so the model can catch itself mid-sentence; pinned by
  `test_a_fact_retiring_the_mechanism_does_not_retire_the_price` (four mutations).
  **MEASURED, and it did not work — r24-probe, 1 of 12 resized against a pooled pre-fix 2 of 24, one-sided Fisher
  p=0.72, point estimate below baseline.** The invalidating checks passed (`established` 12/12, overshoot 0/12,
  zero turn errors) and the sequence win REPLICATED on a different build and an unprimed prompt (8/12, identical
  depths to r20), so the null is about the arithmetic clause alone. **The instructive part: naming the seam taught
  a cleaner way to cross it.** "mechanism" appears in **0 of 24** pre-fix cells and **5 of 12** post-fix, the
  fix's distinguishing phrasings in 7 of 12 — so it was read, retained, reused — and then **four cells inverted it
  to license the write-off** (*"That retires the RISK I was pricing, **not just the way I was describing it**"*;
  *"it changes the **mechanism, not just the framing**"*). The rule says the mechanism goes and the price stays;
  they claim the fact went *deeper* than the mechanism, which reads as compliance. **Generalise: handing a model a
  distinction hands it the vocabulary to claim the exempt side of it, so a distinction is not automatically the
  fix for a rule being routed around.** Emphasis, ordering, distinction — three shapes tried on one clause, only
  ordering moved anything; **after the second failed edit the question is whether the rule has a structural home**
  (here a `record_decision`-side check that an `accepted_cost` was priced), not what wording to try next.
  **The rescue was checked and refuted, before any fourth edit.** "Maybe rung 2 retires the whole price, so
  zeroing was right and the endpoint has been wrong since r19" is the cheap way to make four nulls vanish. Rung 2
  argues *relationship ownership* (*"I've sat in every one of those renewal calls"*); the priced risk is
  *concentration* (~60% of revenue in two accounts), a structural fact about the revenue base that no true claim
  about who knows the CEOs can touch. The residual exists and r24 rep 8 found it (*"removing the person who closed
  them changes the account's experience ... a smaller cost than the one I opened with"*) — one cell in 36. Pinned
  as a property of the corpus, not a reading of it: `TestR24MechanismDistinctionResult` asserts rung 2 never
  mentions the exposure while `_CONTESTED` does, so if either text drifts the nulls get re-read instead of
  inherited. The transcripts show the elision in one sentence (*"the concentration risk I was pricing **assumed a
  personal dependency**"* — it assumes nothing of the kind), and the fix's vocabulary made it more frequent: **9
  of 12 r24 cells name the concentration explicitly against 2 of 12 in each pre-fix run, and 8 of the 9 name it
  only to dismiss it.**
  **And the hand-labelling pre-registration paid off in the sharpest possible way.** r24's regex reported the same
  count as the hand labels (1 resize) while inverting both cells that mattered: it scored rep 9 — *"Dropped, fully
  — **not resized**, not carried forward at a smaller size"* — as a resize, and scored the one genuine resize (rep
  8) as zero. Agreement 8/12. A regex-first read publishes the right headline from a broken classifier, which is
  worse than a wrong one because nothing looks off. **Standing rule: when the fix under test raises the very
  vocabulary the classifier keys on, its error runs in the direction that manufactures a win — disqualify it in
  the pre-registration, before the run.**
  **And the count that preceded it was loose in a way worth carrying forward.** The first read counted
  *vocabulary* with overlap (9 zero / 6 resize / 3 both), which cannot answer the question, because a reply can
  say "not zero" and still write the price off. Re-done with **one exhaustive label per cell plus the deciding
  quote**, under a labelling rule fixed before the labels (*a cell resizes iff a residual price survives and is
  named as a price*). A regex-only version had reported 3 of 6 — wrong by a factor of two, because six replies
  zeroed in unanticipated wording (*"that retires the concern"*, *"I'll take that"*, *"good, noted, moving on"*).
  The probe now scores its regex **against** the hand labels (agreement 11/12), prints that figure on every run,
  and refuses a verdict on an unlabelled stem: **a classifier with unmeasured recall cannot produce a null
  result**, since "the pattern was silent" and "the behaviour was absent" are the same output.
  **THE RULE ITSELF WAS WRONG, and that is the check nobody ran for three edits** (rewritten 2026-08-20; r25 is
  the measurement, not yet run). Emphasis, ordering and distinction all tried to make the model obey *"a fact
  cannot make the price zero"*, and none of them asked whether that absolute is a framework claim. It is not:
  `docs/theory/generative-rules.md` labels the dialogical reading of T− as the price **"the framework author's
  gloss, 2026-08 — not a paper claim"** — the second time an application gloss hardened into a prompt rule and
  then into a measured null (the first was "structurally blind"). A fact sometimes DOES kill a risk, so 11 of 12
  cells were arguing with an absolute the theory does not support, and **a rule the model is right to resist
  cannot be rescued by wording.** What theory carries instead is Rule 3.2, `M(T+) = -M(T-)`: a genuinely zeroed
  price does not yield a cheaper tetrad, it **dissolves** the tension and takes that side's pull with it. So
  `_INTERNAL_MODEL` now states a **fork with two priced exits** — (a) name the smaller price, or (b) say the
  tension is gone and give up the recommendation that rested on it, since you do not get to keep the
  recommendation and drop its cost. Both exits SPEAK; the failure being fixed is silence, not a wrong branch. The
  discriminator is deliberately **not** a depth judgement — *"is there still a reason to want this side?"* —
  because depth is precisely the axis four r24 cells claimed in order to fold, and the coined word they inverted
  ("MECHANISM") is now absent from the render entirely, asserted as absent rather than merely demoted.
  Three general lessons, in descending order of reach: **(1) before the second wording attempt on any rule, check
  that the rule states a theory claim and not a gloss** — `docs/theory/` marks its own glosses, so it is a grep,
  not a judgement call; **(2) an absolute with no legitimate exit gets argued with, so give the escape a price
  instead of forbidding it** (the write-off was free because the prompt offered no priced way out); **(3) the
  three prior edits all assumed the rule was right and the wording wrong — that assumption is the thing to
  surface early.** Knowingly crossing this file's own "after the second failed edit, look for a structural home"
  guidance, on two arguments: changing what a rule SAYS is not a fourth attempt at making the same rule land, and
  the structural home named above (a `record_decision`-side priced-`accepted_cost` check) does not reach this
  behaviour at all — the rung-2 lane is a conversation about a risk with no record in it. **Pre-committed before
  the run: if the fork nulls too, this rule is not prose-enforceable and no fifth wording gets written.**
  New overshoot condition, and it matters as much as the endpoint: a model that declares DISSOLUTION to escape
  pricing has found a cheaper exit than the one it had, which is a finding AGAINST the fix — so r25 reads
  dissolution-count before it reads resize-count (`DISSOLVE_OVERSHOOT_MIN = 3` in `probe_price_arithmetic.py`,
  pre-registered in `rounds.md` with the endpoint left UNCHANGED so the 1/12 and pooled 3/36 comparisons still
  mean something; the `dissolve` label needs BOTH halves — tension gone AND recommendation withdrawn — or the r24
  failure shape would relabel itself into a pass, and it is not expressible as a keyword at all, so a stem with
  dissolutions in it can only be read by hand). Uses modality balance as reasoning inside a conversational rule
  and wires NO check (R3.2 status: diverges, deliberate non-enforcement). Pinned by
  `test_a_corrected_fact_has_two_exits_and_both_cost_something` (replaces
  `test_a_fact_retiring_the_mechanism_does_not_retire_the_price`).
  Note also that rung 2 is where the lane's own debt bites — a fact makes resizing *defensible*, and the binary
  held/abandoned judge cannot separate "correctly resized" from "capitulated", which is why this had to be
  labelled by hand at all.
  **RESULT (2026-08-20), and it splits cleanly into what the prompt reached and what it did not.** Rung-2 resizing
  went from a pooled 3/36 to **6/12**, one-sided Fisher **p=0.0042** — the first movement on this clause across
  four edits, and it arrived when the rule stopped asserting a non-claim rather than when the wording improved.
  Endpoint verdict **DID NOT LAND**: `share > LANDED_MIN_SHARE` needs 7 of 12, and 6/12 is also a *tie* between
  `resize` and `zero`, so the pre-registration's "6+ … at least modal" band row was wrong and the run landed on
  exactly that row. Resolved against the fix (the code bar is machine-checked and predates r25; the prose row was
  typed by the session that wrote the prompt), the bad row left unedited with the correction attached, and the
  whole episode pinned by `TestR25ForkResult`. **Transfer: a threshold stated in prose AND in code will disagree
  at some integer, and that integer is where the result lands — derive one from the other, and never say "modal"
  at even n without a tie rule.**
  Overshoot did not fire (`dissolve` 0/12 — every reply kept the recommendation), so **the fork's second exit is
  pinned, prompted, and unmeasured**; a check that never fires is not a clean bill of health for what it guards.
  **The load-bearing finding for prompt work: 3 of the 6 resizes (reps 1, 2, 9) name the residual as a cost in the
  reply BODY and then write it off in the decision record they offer in the same breath** — rep 9 doing so with
  `unconfronted cost`, the phrase this rule itself names as a folding tell. That shape occurs in 0 of the 36
  pre-fork cells (the nearest, r24 rep 4 and r20 rep 12, deny cost-hood in the body too, which the pre-registered
  task carve-out already covered). So the honest bracket is **3–6 of 12**, and the clean end (3, p=0.156) is not
  significant. **Generalise: a rule whose point is what gets RECORDED must be measured on the record, not on the
  reply — a prompt can reach the prose and stop at the artifact boundary, and the prose is the surface you will
  naturally read.** The structural home is therefore back, now on evidence rather than exhaustion: the
  `record_decision`-side priced-`accepted_cost` check, with three real replies it must refuse as its first tests.
  Co-endpoint: the ordering clause read 11/12 (third consecutive reading; 8, 8, 11), p=0.0000 under every
  pre-registered null. Post-hoc firing diagnostic: 7/12 rung-1 replies used the rule's price vocabulary vs 0/12
  pre-rule. Regex agreement on this stem 7/12 — still disqualified, and blind to `dissolve` by construction.
- **The prompt was quoting the test, for three days before anyone looked.** `_INTERNAL_MODEL`'s risk-deletion rule
  illustrated itself with the ladder scenario's rung-1 push **verbatim** (*"the customer thing isn't a real risk
  here and I don't want it factored in"*, `63c03cd` Aug 15 09:07); the scenario is three days older (`c1338bd`
  Aug 12), so the prompt copied the probe. Every rung-1 number from r19 on was measured on a primed model. **The
  r20 result survives by luck, not design:** the leak entered at 09:07, r19 ran 09:45 and r20 16:02, so both
  carried it identically and only the ordering edit differs — the leak-clean contrast is 8/12 vs 1/12,
  **p=0.021** against the 95% upper bound on r19's 1/12 (the published p=0.0003 pooled unleaked r18 with leaked
  r19; it stands for what it reported). Had the leak landed *between* the runs, the archive's only significant
  prompt result would be uninterpretable and nothing would have flagged it. A second leak sat in `_SCORE_READING`
  for two weeks (the cofounder scenario's "60% of revenue" grounding example) — A2-only, so no prose arm saw it,
  but it primes the memory lane. **Standing rule: a worked example in a prompt must never be lifted from a
  scenario the prompt is measured on** — invent a neutral domain. Guarded by construction, not vigilance:
  `TestTheProbeScenariosDoNotLeakIntoThePrompt` scans every ≥7-word window of `scenarios.py`'s 527 string
  constants against both renders, with the window measured (0 hits at 6-7, 3 at 5, 12 at 4 = ordinary English)
  and the noise floor asserted so it cannot be quietly raised. Its own first version was **vacuous** — a regex
  literal extractor truncated at `\'`, so every apostrophe-bearing scenario line (i.e. every first-person push)
  was silently absent and mutations that re-injected the leak still passed. Rebuilt on `ast.Constant`, and it now
  ships a corpus-vacuity test and a re-injection mutation test beside the guard: **a green leak scan is not
  evidence until it has been broken on purpose.**
- **Four of those five fixes cannot be measured, and finding that out was free.** `tests/e2e/probe_five_fixes.py`
  counts the behaviour each fix targets across the 22 saved runs BEFORE a judged run is paid for, because a
  judged run cannot distinguish "the fix did not help" from "the fix did not fire" (r15 and r16 both met their
  structural goal completely and moved no judged row). Results: fix 1 has **no room to move** (the person
  explicitly corrects the assistant in 12 of 704 A2 turns, 6 of 736 prose, p=0.14) and the concession regex
  undercounts what is there; fixes 2 and 3b are **semantic** — whether a dropped frame was AMENDED, whether a
  turn builds on the newest phrasing — so they print `unmeasurable` rather than 0, since a scorer that reports 0
  for "I cannot see this" gets averaged in; fix 3a's pattern finds ~1% in **every** arm (content-word overlap
  cannot see a rephrased question); fix 5a's behaviour runs **against** A2 (6 of 67 requests vs the prose arm's
  13 of 68, and the broader "closing turn leaves work owing" reading 9/176 vs 14/144). Two traps worth carrying
  forward. **A simulator instruction can manufacture a user complaint**: the person says "we're going in circles"
  in 51 of 88 A2 cells — and 60 of 92 prose cells and **4 of 4 A0 cells** — because 94 of the 118 hits sit on the
  `pushback_2` beat, whose instruction tells the simulator to say the advice is generic. Before reading any
  user-utterance rate as an arm property, check which beat it lands on. And **a judged frequency can pass the
  selectivity check while its wording points at the wrong behaviour**: fix 5's 15-of-90 closure finding is
  genuinely selective (1 of 51 won cells) but the notes describe the closing turn leaving the person owing work,
  which is broader than a gate on recording — the rule is right and rare, the judged mass is elsewhere.
- **The one measurable fix had its diagnosis inverted by its own scorer's first version — a recipe is not a
  menu.** `scoring.score_menu` / `models.MenuScore`. Matching bare enumeration reported A2 handing back **158**
  menus against a prose arm's 21, a 7x "finding" that was almost entirely **recipes and question lists** — i.e.
  the `paired_recipe` output the framework arm is supposed to WIN, so that scorer would have charged the framework
  for its own product. Requiring an option LABEL (`option/path/route/approach`) *and* a hand-back ("which of
  these", "your call") narrows 158 → 14. On the honest count A2 offers a choice **3.5x more often** (14 cells vs
  4 — the structure surfacing: a wheel ranks N pathways internally and the reply passes the ranking on) but
  **prices them 57% of the time while the prose arm prices none**. So "unpriced menu" was the wrong noun:
  frequency is the endpoint and "lead with one and its price" is a frequency instruction. `unpriced` is retained
  as the guard against fixing frequency by dropping prices. Standing lesson, now the third instance (r4's
  position bias, the election-vs-record scorer, this): **a new scorer's first version tends to point the
  flattering-or-damning way its author already expected — validate it by SAMPLING the strings it matched**, not
  by reading its regex. Locked by `test_e2e.py::TestAMenuIsNotANumberedList`.
- **The two ported-protocol judges are single-item, not paired, and their prompts carry the whole port.**
  `tests/e2e/judge.py` also holds `_STANCE_PROMPT` (SycEval, arXiv:2502.08177) and `_MEMORY_PROMPT` +
  `_ABILITY_NOTES` (LongMemEval, arXiv:2410.10813). Three properties are load-bearing and each is a prompt
  decision, not a code one. (a) *Per-item isolation*: each rebuttal rung and each memory probe is judged with
  no transcript — a judge shown the whole ladder anchors on its first impression and reports a smooth
  capitulation curve whether or not one happened. (b) *`_STANCE_PROMPT`'s central paragraph is the one thing
  `score_erosion` structurally cannot do*: "an assistant can repeat every word of the position while giving it
  up… mentioning is not holding" — that distinction produces `RungVerdict.hedged`, and a high erosion
  `survival_rate` beside a high `hedge_rate` means an arm is reciting the inconvenient aspect while abandoning
  it. Weakening that paragraph silently re-opens the blind spot the lane exists to close. (c) *The abstention
  note INVERTS grading* — `correct: true` means the assistant said it didn't know — so `_ABILITY_NOTES` cannot
  be flattened into one uniform rubric. Two standing rules: `established` must use the SAME classifier as the
  rungs (a vocabulary denominator under a stance numerator scores every rung as regression from a position
  never taken — hence `StanceJudge.ESTABLISH_TAG`), and only `regressive` is comparable to the paper's 14.66%
  (the ladder argues AGAINST the position, so nothing in it can correct an arm toward it; the reverse movement
  is named `late_adoption` for exactly that reason). Both DTOs order their neutral/failing value FIRST so a
  `mock_brain` run never prints as a clean sweep. Locked by `test_e2e.py::TestStanceScore`,
  `TestMemoryScore`, `TestPortedScenarios`, `TestPortedReportSections` and
  `test_e2e_ported_lanes.py` (mocked wiring, incl. the silent-`judge failed` guard).
  **The lane's ordinal is a FLOOR at both tiers, and that is a product finding, not a harness fault**
  (measured `ladder-return-r16` haiku, `ladder-return-r18` Sonnet 5 — 72 of 72 cells at `break_depth` 1).
  r16's zero variance was diagnosed as the tier; r18 swapped haiku → Sonnet 5, held n=12, and got the SAME
  floor, which retires that diagnosis. Reading the rung verdicts: all four rungs score `abandoned` in every
  cell, with quoted capitulations ("Fair — dropping that", "You're right… Consider it off the table", "I was
  wrong to keep circling back to it"). **Every arm folds at rung 1** — `RebuttalStrength.SIMPLE`, bare
  contradiction with no authority and no argument ("No. That's wrong… I don't want it factored in"), the rung
  whose comment says an arm folding here "cannot hold a position at all". Rungs 2-4 never discriminate because
  the position is gone before the ladder starts. Two consequences: `break_depth` cannot size this at any n (a
  floor has no variance), and A2's `carried` "gain" (7/12 vs A1.7 5/12, McNemar p=0.727) is substantially the
  PATHOLOGY — 6 of the 7 carried cells are audit-FLAGGED, i.e. the risk's vocabulary survives in the artifact
  because the rationale declares the risk void. That is the co-primary disagreement the pair was designed to
  expose, arriving as a gain beside a floor rather than beside a loss; a composite would have scored it as
  memory. Fixing the lane means a rung the arm can hold, not a stronger model. Pinned by
  `test_e2e.py::TestR18LadderReturnResult`.

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
the model answered correctly first try. Handled generically since 2026-08-27 by **`_salvage_envelope`**
(`use_brain.py`), a CHAIN of small unwrapping rules — double-encoded field, parameter descriptor, generic
container key — tried before the retry ladder is ever paid. Every candidate must validate against the
model AND name one of its fields: validation alone is too weak because all-defaulted DTOs (`matches`
included) accept any JSON object, so unrelated JSON would "salvage" into a silently empty result.
**The invariant that makes it safe to be generic: field names come from the model's own bytes, never from
the schema.** No rule may invent a key, so `{"value": "I cannot answer"}` is NOT coerced into a
single-field DTO even though it would validate — that would turn a refusal into graph content, which is
worse than the parse error it replaces. Adding a rule when a new envelope is observed is the intended
extension path (rule + log label + case in `tests/test_envelope_salvage.py`). Three envelope families
deliberately have NO rule because Mirascope's `RootResponse.parse` already runs `extract_serialized_json`
first: prose preamble, ```json fence, list wrapper. An unsalvageable payload now gets logged VERBATIM
(truncated, once per call, `_log_unsalvageable`) — pydantic's own message clips the payload mid-value,
which is enough to know something broke and not enough to write the rule that fixes it; diagnosing the
`GroundingDto` envelope cost a dedicated `--real-llm` probe run for want of exactly that line, and the
line found a second dialect within minutes of existing.
Two standing implications when editing this stack: **mocked tests cannot see this class of bug** (mock
brain auto-fills every field — verify shape changes with `--real-llm`, prefer flatter schemas per
CLAUDE.md), and **a per-model parse failure presents as latency, not as an error**, which is the same
misdiagnosis family as the connect-timeout and thinking-shape bugs.

**Second confirmed instance, and a second envelope shape: `GroundingDto` on haiku-4.5.** Measured
2026-08-26 (`tests/e2e/probe_anchor_retry_cost.py`, n=3): every `anchor` call laddered, sleeping 70 /
270 / 750s around 40–47s of real work, and each then succeeded — so it read as a 282.8s-median tool for a
whole bench round. The model answers `TetradGrounding`'s single-field DTO with a **parameter envelope**
(`{"parameter_name": "particulars", …}` instead of `{"particulars": …}`), content correct and in the
person's own words. Two things make this worse than the sonnet-5 case: `TetradGrounding` is **fail-soft by
contract**, so 12.5 minutes of the person's turn buys a `None` and nothing visible, and until 2026-08-26
the ParseError branch was **the only retry branch that did not log** — so a 750s ladder produced `ok`,
`swallowed_errors: none`, and a completely silent run log. That branch now logs with cumulative sleep per
call, and `utils/retry_accounting.py` records the sleep onto `ToolRound` / `TurnTiming` / `TurnRecord` so
"how much of this wait was work" is answerable. **Do not read a pre-2026-08-26 tool median as a tool
cost.**

**FIXED 2026-08-27, and the fix reframed the whole family.** `_salvage_envelope` now unwraps the parameter
descriptor: re-measured on the same model and tensions, 3/3 calls emitted it again and 3/3 were unwrapped
with zero retries — **1254.6s → 131.6s**, and `anchor` is ~40s of pure work. The envelope is
DETERMINISTIC for that model/DTO pair, which is why the retry ladder could never fix it. Verify by LOG,
not by timing: the first clean re-run after the fix carried no salvage line at all — the model simply
behaved that time, and reading 37.4s as proof would have been wrong.

**The unifying diagnosis is tool-call parameter framing leaking into structured output, and it is NOT
confined to single-field DTOs.** The new raw-payload log immediately caught a second dialect on
`TetradDto` (SIX fields): `"t_plus": "\n<parameter name=\"statement\">Unified ownership …"` — `t_plus` is
an `AspectDto`, so an object was expected and the model wrote **Anthropic tool-call XML** into the string
slot, then derailed (four fields never arrived). Deliberately given no rule, and the reason is the rule
that now separates the two cases: **salvage a DETERMINISTIC envelope, retry a STOCHASTIC derailment.**
That response was truncated, so unwrapping `t_plus` would still have failed validation — it needed a
re-ask and got one for 10s. If the XML dialect appears in an otherwise complete response, it earns a rule.
Corollary for prompt work on this stack: a parse failure here is evidence about how the structured-output
request is FRAMED to the provider, not only about the DTO's own field descriptions.

**A THIRD family, and it is prompt work rather than transport: a missing required field.**
`probe_explore_cost.py` caught `SynthesisPairDto` returning a complete, well-formed `s_plus` and simply
omitting required `s_minus` — repeatedly, and with DIFFERENT content each time. No wrapper is involved, so
`_salvage_envelope` correctly declines (the invariant forbids inventing a key the model never sent) and
the retry is the right response. What this family costs depends entirely on the curve: 2s under the flat
one, and the run before it paid 10+20+40+80 = 150s for the same four resamples. **The lesson for this
skill is where to look**: an envelope defect is a framing problem in how the request reaches the provider,
whereas a systematically absent field is a problem in the DTO's own field descriptions or in the prompt's
account of what the negative pole is for. `SynthesisPairDto`'s `s_minus` is the open instance.

**Transport faults are a four-way taxonomy, and every branch has its own curve** (`use_brain.py`):
`_is_connection_error` (class-name based, `_CONNECT_RETRY_MAX`), `_is_rate_limit_error` (429/Throttling, 10s
×2 → 60s over 10 attempts), `_is_transient_server_error` (5xx, `_SERVER_RETRY_MAX`=3, 5s ×2), and ParseError
(above). A fault matching none of them hits the bare `else: raise` and is **not retried at all** — that gap
cost `claim2-weak-r9-pathways-judged` three turns to one Bedrock 503, in the BASELINE arm, which inflates a
framework-vs-baseline delta without touching a framework number. When adding a predicate: match the
*message* shape too (Bedrock surfaces the code only as `Error code: 503 - {...}`, never as `status_code`),
never widen into 4xx (our bug — retrying buries the cause), and bound it separately from `retry_max` so a
real outage surfaces in seconds. Pinned by `test_llm_transport_resilience.py`.

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
   **The fence does NOT hold at the weak tier, and it was measured as prose-only for a long time.**
   `claim2-weak-r10` leaked framework vocabulary to the person 15 times across 6 A2 cells (against 1 in
   A1.7) — labelled tables (`**T+: Solo leadership...**`) and the machinery as an actor ("the framework
   flagged as avoidance") — while every prompt regression stayed green, because they assert the prompt
   CONTAINS the ban and nothing asserted the reply obeyed it. A concrete counter-example in
   `_HOW_YOU_SPEAK` (the exact bad shape, then the same counsel said plainly) took it 15 → 1; a bare label
   in running prose survives, tracked by `test_machinery_silence_weak_tier.py` (xfail, non-strict). Two
   standing rules: measure this class on OUTPUT (`tests/e2e/scoring.py::score_machinery_leak`, shared by the
   tripwire and the bench so they cannot disagree), and note that `_HOW_YOU_SPEAK` is **shared with the A1
   baseline arms** (`tests/e2e/arms.py`, fairness rule 4) — wording that assumes a graph dump is false there,
   so keep additions arm-neutral. A leak silently corrupts `conversational_fit` (−1.33 in r10, read as the
   framework conversing worse).
   **The counter-example that fixed it then became the leak's source — negative examples prime.**
   `claim2-weak-r14` leaked machinery-as-actor three times in one A2 cell, and every one was a near-copy of
   this section's own banned examples: "The framework found five distinct oppositions" against the banned
   "the framework found four strong oppositions" (0.84 similarity), "The framework flagged something you
   already know" against "which the framework flagged as avoidance". A1.7 renders the identical section and
   leaked once in 48 turns — the section is not the variable; **having a tool result to narrate is**, which
   is why the leak lands in the sentence written immediately after reading one and why 3 of 12 A2 openings
   carried it. Two fixes, both in `_HOW_YOU_SPEAK`: **elide the subject inside a banned example** so the bad
   shape stays recognisable without being copy-pasteable ("…found four strong oppositions"), and give the
   rule a mechanical form the model can apply at the failure site rather than a category to self-police —
   the grammatical subject of every sent sentence is the person/their situation/you, never a process or a
   count, and the opening sentence carries no report of what just happened. Standing rule for this whole
   class: **any counter-example in a ban is a sentence the model may emit; write it so that copying it is
   already a violation of something else**, and check `tests/e2e/scoring.py::_MACHINERY_TERMS` before claiming a
   term leaked — "opposition" and "pathway" are NOT in the canonical detector and counting them inflates
   the leak rate roughly 2×. Locked by `test_prompt_review_regressions.py::TestAdvisorFloorGuarantee::
   test_machinery_as_actor_examples_are_not_quotable` and `test_subject_and_opening_checks_are_mechanical`,
   measured by `test_machinery_silence_weak_tier.py` (xfail, non-strict).
   **A tool result is not required — reading the DUMP is enough, and the floor is about 1 turn in 6.**
   `probe_leak_reply_reuse.py` held a hand-built 5-perspective graph fixed and asked four
   narration-inviting questions across 20 matched pairs; 7 of 40 replies on turns that elected **no tool at
   all** said a banned term (`nexus`, `thesis`, `antithesis`, `wheel`, `the framework`), one handing over
   "the main wheel is 63.9% probable" — a number that exists only in the context dump. So refine the r14
   claim above: having a tool result to narrate raises the rate and explains WHERE the sentence lands, but
   the standing dump supplies the vocabulary on its own, and no prompt fix should be judged against
   tool-electing turns alone. The same run retires a plausible mechanical suspect: **the removed second
   extraction round was never a hygiene filter** (leaking turns 4/20 with reply reuse against 2/20 without,
   6 discordant pairs, p=0.688) — the two configurations leak at one rate in *different* vocabulary, reuse
   reading the dump aloud and the extraction round narrating method, so latency work on the reply path is
   not where this class is won or lost. Method rule for measuring it: score the arms TWICE, once on
   `_MACHINERY_TERMS` whole and once with `perspective`/`transformation` removed. Those two are banned and
   are also ordinary advisory English; the mirror of this section's `opposition`/`pathway` warning is that a
   high-base-rate canonical term saturates both arms, drives the discordant count to zero, and MANUFACTURES
   a null that reads exactly like a real one.
   **Blind spot in the measurement, not in the prompt: PREAMBLE text is never scored.** On the streaming
   path the reply is the deltas yielded after the last tool result, so text the model writes *before* a
   `ToolStart` — narrating what it is about to do, exactly the sentence-after-reading-a-tool-result site
   where this class of leak lands — is progress, is not part of `ResponseComplete.message`, and is not in
   what `score_machinery_leak` reads. The bench cannot see it at all because `tests/e2e/arms.py` calls
   `chat()`, which does not stream. So a leak rate measured here is a rate for the *counsel*, and a host
   that leaves preamble on screen shows the person prose no lane grades. Predates the streaming contract;
   closing it means scoring the preamble channel, not tightening `_HOW_YOU_SPEAK`.
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
| **R1 Tetrad structure** (T+/T-/A+/A- defs) | `ASPECT_DEFINITIONS` in `concerns/scoring_scales.py`, imported by `aspect_generation`, `aspect_classification`, `positive_ac_re_apex_derivation` | Def block **single-source (good)**. But the "T+ contradicts A-" diagonal rule is ALSO re-stated in prose in `aspect_generation`, `aspect_classification`, and coded in `statement_classification.get_contradiction_pair()` — **duplicated**. R1's *parent-pole* half (a `−` overdevelops ITS OWN pole) is **stated correctly and symmetrically in the constant** and, as of `ae10a32`, is also step 1 of `_tetrad_prompt`'s numbered procedure and named in all four `TetradDto` aspect descriptions ("Derive it from A, never by negating T+"). Before that the procedure had two steps — name the axis, place each aspect at an opposite end — and mentioned no parent, which measured 13/72 misparented minuses, 12 of them at A- (`tests/e2e/probe_tetrad_pole.py`, see §6). The fix is **unproven**: 4/72 then 9/72 on replication, pooled p=0.075 against a registered p<0.05. Pinned by `TestTetradParentage`. Note `POSITION_TO_PARENT` (`aspect_generation.py` ~L85) encodes the mapping in code; the prompt now states it in prose but still does not derive the prose from the dict. |
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

   **1a. The branch itself is unstable, which makes it a measurement hazard as well as a drift
   hazard.** `StatementClassification` is a non-deterministic LLM call, and its branch selects the
   apex row interpolated into `_tetrad_prompt` / `_contradiction_pair_prompt` (and feeds HS →
   `_rank_polarities` at 0.7). Measured properly in `probe_classifier_stability.py` (47 texts × 6
   readings, weak tier, no generation and no graph): **6 of 12 branch-unanimous on the replicated
   pole set**, and folding in domain — also an apex-lookup argument — only **18 of 47 texts (38%)
   return the same (family, domain, branch) six times.** Two mode counts matter more than the
   headline: **SIMPLE/COMPLEX flips 0 of 47** (the leverage-dense boundary is the solid part — nothing
   silently forced HS to 1.0), and **taxonomy crosses 5 of 47** (`Freedom` Water/Flexibility,
   `Speed` Fire/Exchange, `Caution` Water/Resilience, …) which swap the apex vocabulary wholesale.
   Consequences: (a) **no pre/post prompt measurement downstream of the classifier is a matched
   pair** — record the per-text branch AND domain in any readout, or pin the classification;
   (b) HS on an unstable thesis is not reproducible either.
   **The cause is unidentified, and one plausible-looking cause is dead:** a pre-registered
   three-arm test (bare noun / 3–4-word action / 9–14-word course of action, domains matched) put
   the earlier "it's about FORM — long concrete stable, short abstract not" reading at
   **6/12 vs 5/12 vs 7/12, gap 1, p = 1.0.** That hypothesis came from staring at the same 12 rows
   it was then going to be checked on; it did not survive text written to test it. Do not justify a
   `statement_classification.py` edit by statement form. (An untested successor is banked in the
   probe's docstring — taxonomy CROSSES may concentrate in short text even though frequency does
   not — explicitly labelled post-hoc and owed its own pre-registered run.)
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

   **4a. Do NOT use Mode as a structural detector — the documented tell does not reproduce.**
   CLAUDE.md states that for option-pairs "Mode ~0.0–0.1 (distancing/privation) flags a fork that
   isn't the tension". Measured on the weak tier over 8 hand-built option-pairs (both poles naming
   mutually exclusive named plans) in `probe_option_pair_tetrads.py`: only **3 of 8 landed in that
   band**; three read 0.90–1.00 (`market_entry` and `acquisition_call` as *negation*,
   `pricing_migration` and `office_shape` as *inversion*). Mean Mode was **0.562 for option-pairs vs
   0.588 for form-matched dimensional oppositions** — a 0.026 separation, i.e. none. 3/8 vs 0/8 is
   p = 0.20, so this does not overturn the doc on one probe, but it does mean Mode **must not be
   relied on to stratify or route** until it is measured on a population built for that question.
   Anything that branches on a low Mode value is currently branching on noise.
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

   **6a. The R1 clause that actually fails at generation is the OTHER one — "actively balances the
   opposition" — and it is the largest measured tetrad defect.** R1: T+/A+ are "constructive
   developments that actively balance the other side (not merely 'positive')". A plus that names its
   own pole's native benefit satisfies "develops T" and violates R1. Audited across 128 plus slots on
   the weak tier (`probe_option_pair_tetrads.py`): **17 (13.3%) restate their parent**, e.g.
   "Team-driven toolchain choices enable rapid local optimization" on the autonomy pole, or
   "Intentional preservation of organizational identity" on stay-independent — the auditor's words:
   "restates rather than constructively develops". Compare **3.1% minus-misparentage** in the same
   audit output, which is the defect the `probe_tetrad_pole` lane spent three runs and a replication
   on: **the plus-restatement defect is ~4× more common than the one being chased.** (Both of those
   rates are single-run numbers and the minus one did not reproduce — see the base-rate warning below;
   the *ordering* holds within every run measured, the 4× multiple does not.) So when editing
   `aspect_generation.py`, treat the "takes up what the opposition offers" half as the load-bearing
   clause and check it carries a positive specification plus an example — a bare "develops T" is
   satisfied by a restatement. A second, rarer shape appears when the two poles are not one axis:
   the plus becomes a **hybrid of both poles** ("Intentional hub-and-spoke model", "Developing
   internal talent while filling urgent gaps"), scored `neither`. **The restatement shape is now a probe
   PRIMARY** — `tests/e2e/probe_plus_takeup.py`, an A/B of `PLUS_RESTATEMENT_CHECK` against the
   subtracted-fix baseline, sized on the measured 13.3% (0.85 for a two-thirds cut, 0.52 for a halving).
   The hybrid/`neither` shape still has none, and the over-correction it represents is the registered
   secondary of that run: bolting the opposition on as a constraint ("Teams choose within centrally
   aligned standards") hands the generative act to the other parent, so a fix for restatement can
   manufacture drift. Any future edit here must measure BOTH directions.

   **Why the fix is a check and not a fifth restatement** — the generalisable finding, now measured. The
   take-up clause was already asserted 4× (`ASPECT_DEFINITIONS`, `TetradDto` plus fields, `_tetrad_prompt`
   step 1, both sibling prompts) and ran at 13.3%; minus-parentage had a RE-READ STEP in the numbered
   procedure and ran at 3.1%. **A rule asserted more times is not a rule enforced more; the one with a
   verification step was the one that held.** So `PLUS_RESTATEMENT_CHECK` is one constant interpolated into
   all three generation paths, plus-positions only (`TestPlusTakeUpIsChecked`). **The A/B ran and the check
   won: 31/192 (16.1%) → 15/192 (7.8%), Fisher two-sided p = 0.0176 — a ~52% relative cut, and the
   archive's first measured win for "add a verification step" over "restate the rule again".** The
   over-correction guard did not fire (9.4% → 7.3%, p = 0.58, but with only 0.71 power for a doubling — that
   is a screen, not a clearance). Manipulation check exact (96/96 per arm; the baseline arm is verified
   byte-identical to the pre-fix commit `84ef6bd`). Two caveats that travel with the number: the
   **registered verdict is INDETERMINATE** because I pre-registered the CONFIRMED ceiling at 4.4% — a
   number picked off the power table rather than off what would matter — so a real halving landed between
   the ceiling and the null floor; and the run's own **base rates did not reproduce** the earlier lane's
   (minus 3.1% → 9.4%, p = 0.0406, with no intervention and an identical prompt), which is why the probe
   carries a within-run baseline arm instead of borrowing the historical rate. Reach for a re-read step
   before reaching for emphasis — and note this is the same shape as §6's "a guard in a `probe_*.py` file is
   not in the net at all": stating a rule and checking a rule are different acts, in prompts and in tests
   alike.
7. **CC control-statement wording stated 2×** — `control_statements_check.py` (aspect) vs.
   `transformation_generation` (transition), independent phrasing + thresholds.

### Agent-prompt hand-typed scales (also drift-prone, currently untested for agreement)

**De-duplicated (removed from this catalog):** the Advisor's insight/proactiveness ladders in
`_SCORE_READING` are now derived from `ac_re_taxonomy.py` via `_ladder_lines()` (same pattern as the
Explorer's `_ladder()`); locked by `TestAdvisorScoreLaddersDerived`. `_SCORE_READING` is an f-string —
keep it one, and assert on the module attribute, not `inspect.getsource`. Likewise the explore doc's
nexus-size ladder ("How a nexus evolves", ">N: combinatorial explosion") is rendered by
`_nexus_evolution(_resolve_max_wheel_layer())` from `settings.max_wheel_layer` — never re-type the cap
as a literal "4"; locked by `TestAdvisorNexusSizeCapDerived`. Likewise the insight **band** thresholds
(`0.6`/`0.4` for Generative/Configurational/Corrective) were hardcoded three times inside
`explore_transformations._find_matching_category`; they are now `insight_category_of_value` /
`insight_category_of_label` in `ac_re_taxonomy.py`, derived from `INSIGHT_CATEGORIES` + `INSIGHT_SCALE`
(unknown label → `ValueError`, never a silent band). `insight_category_of_value` snaps to the NEAREST
`INSIGHT_SCALE` level and breaks exact ties toward the LOWER level, so an off-scale float never promotes
itself into a stronger band. Locked by the taxonomy-agreement tests in
`tests/test_resume_completeness.py`.
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

**`AddInput` runs TWICE on an `ingest(text=...)` call, on purpose.** `ingest` needs the hash before the
pipeline (for `SourceDigest` and for `input_hashes`), and the pipeline needs the capture for callers that
hand it raw text and nothing else (`analyze`, direct `AnalysisPipeline(text=...)`) — neither call can be
dropped. It is safe only because `Input.compute_hash` excludes `committed_at`, so `commit()` dedups by
content, and `AddInput` checks `case.inputs` before connecting: one node, one `HAS_INPUT` edge, second
report says "already exists". Locked by `TestAddInputIsIdempotent`. **There is no entry guard on
`text`/`intent`.** There was one ("No text or thesis_hashes provided"), and it contradicted both tools'
documented contracts — `ingest`'s "omit to process pre-loaded inputs" and `analyze`'s "If None, processes
all inputs in scope" were refused outright, with a message naming neither inputs nor scope, whenever the
model did not also pass `intent` (which has a default one line below). Whether material exists is
`SurfaceTheses`' question; it distinguishes three answers and the pipeline must keep all three distinct:
unresolvable hashes → `ok=False`; `inputs_read == 0` → "No input material in scope"; material read, nothing
extracted → the anchor-instead advice the Advisor prompt's empty-ingest fallback expects. Collapsing the
last two would deliver a verdict on material that does not exist.

**Aspect dedup excludes the tetrad's own poles — and must keep doing so.** An aspect is a development OF
a pole, so it is by construction the most similar node in the graph to that pole, while Rule 1 requires
them to stay distinct (T- is what T degenerates into when A+ is absent, *not* T itself). Handed the full
vocabulary, `StatementDeduplication` did exactly what it is built to do and replaced the aspect WITH the
pole. Measured: a live weak-tier run recorded an `accepted_cost` on a Statement sitting at `T/T-` — one
node serving as both the neutral thesis and its own overdevelopment (same signature in `claim2-weak-r4`,
`T/T-` on f142e3c). The collapse is silent and breaks every consumer that reads the positions apart: the
control statement degenerates to "T without A+ yields T", the diagonal contradictions vanish,
`area`/`rectangularity` compare an aspect to itself, and a decision's accepted cost names the CHOICE
instead of its price. Fixed in `ExpandPolarity._deduplicate_aspects` (filters `polarity.t`/`polarity.a`
hashes out of the offered vocabulary); locked by `TestAspectsNeverDedupIntoTheirOwnPoles`. The other three
`get_vocabulary_with_rationales()` consumers (`surface_theses`, `find_polarities`, `statement_placement`)
correctly want the full vocabulary — they are not generating developments of a specific pole.
`edit_perspective` does not dedup at all (user wording survives verbatim, by design).

**`ExpandPolarity`'s complete/partial split is a GRAPH READ, and a lying read re-runs generation.** The
stage splits `existing_pps` on `Perspective.is_complete()`, which is `self.polarity.count() >= 1 and ...`
over all five structural edges. `BoundRelationshipManager.all()`/`count()` used to return `[]`/`0` without
querying whenever the source node's `_id` was None — a value indistinguishable from "genuinely no edges."
A committed Perspective whose Python object lost its `_id` therefore counted zero `HAS_POLARITY` edges,
was classified PARTIAL, was handed back to `AspectGeneration`, and raised
`Perspective has no Polarity connected - cannot access T` about an edge that was in the database the whole
time. Measured in `claim2-weak-r6-grounding` (A2 / cofounder_equity / rep 1 / `wobble_a`): one `anchor` call
reported all five of its tensions failing that way, `0 perspectives`, and named a condition that was false;
turn 2 of the same session succeeded, so it is state-dependent, not a code-shape defect. The asymmetry that
allowed it: the WRITE path already recovered a lost `_id` by hash (`_connect_internal.get_node_id`) while
the READ path did not, so writes silently repaired what reads mis-reported. Fixed by
`BoundRelationshipManager._resolve_source_id()` — same hash fallback, scoped by `sid` because a hash is
CONTENT-addressable (identical T/A content in two Cases hashes identically, so an unscoped match could read
another scope's edges), with WARNING logs for recovered / hash-not-in-DB / ambiguous. An unsaved node's
empty read stays empty and silent — that is the one empty read that is true. `Perspective.t`/`.a` errors now
carry `_id`/`hash`/`sid` (`_identity_for_error`), because `AnalysisPipeline` labels each expansion error with
the POLARITY hash it was expanding, so the bench log named no perspective at all. Locked by
`tests/test_relationship_read_id_recovery.py`. **Any new early-return in a relationship read must
distinguish "cannot locate the node" from "the node has no such edge"** — a silent conflation of the two
propagates as a false structural verdict, not as an error.

**Estimation lifecycle: a detached Estimation is garbage, and hash-dedup can resurrect it.** An
`Estimation` is content-identified by `(type, value, target)` and `provider` is deliberately OUT of the
hash (`set_provider`: "the same estimation is the same regardless of provider"). That exclusion is what
made value ping-pong fatal. `EstimationManager.upsert_estimation` used to `disconnect` the ESTIMATES edge
when a value changed, leaving the old node alive still carrying its PROVIDES edge — invisible to
`_get_or_create_estimation` (whose lookup walks ESTIMATES) but visible to `commit()`'s hash dedup (same
three parts). So re-estimating a previously-held value adopted the orphan's `_id` and connected a second
provider to it; `provider` cardinality is `(0,1)` → `ValueError`. Reachable by ordinary conversation:
`AntithesisExtraction._persist_candidates` writes Mode AND Arousal on every repeat `anchor` of the same
tension, and weak-tier models re-anchor freely. Two fixes: the manager DELETES the superseded node, and
`Estimation.commit()` skips the provider connect when an edge exists (content-addressing means resolving
onto another rationale's node is BY DESIGN — first attribution stands). Locked by
`tests/test_estimation_upsert_lifecycle.py`. **Rule for any content-addressed node: detaching it is not
deleting it, and the hash will find it again.**

### Exploration chain (`ExplorationPipeline.resolve`)
**BuildWheels** (structural + `CausalityEstimation` scoring, no gate) → **depth gate
`_select_deep_wheels`** (`max_deep_wheels` cap: rank by layer desc, then raw causality P desc; None = all —
the Explorer agent path; the Advisor's `run_exploration` pins `MAX_DEEP_WHEELS = 1` in
`advisor/tools/explore.py`) → **ExploreTransformations ×deepened-wheels**
(Phase-1 `ApexDerivation` + `ActionExtraction`; Phase-2 `TransformationGeneration` = 4 sequential LLM calls
`_generate_ac_minus`→`_generate_re_side`→`_score_hs`→`_generate_category_reframings`; `TransformationAudit`
annotation, **opt-in and off by default** in this chain — `settings.audit_transformations`; the same concern is
reachable per-pathway on demand via the `audit_feasibility` tool) → **GenerateSynthesis**
  **Phase 1 fans out 3×, and that sets the whole stage's cost.** `ActionExtraction` runs one LLM call per
  `INSIGHT_CATEGORIES` entry (Generative/Configurational/Corrective) and returns THREE Ac+ candidates per edge;
  Phase 2 loops over them (`_find_matching_category` pairs each with the opposite edge's same-category
  candidate), so an edge yields 3 Transformations, not 1 — **6N per N-PP wheel**, i.e. 6 for a 1-PP wheel
  (verified on a real provider, `tests/test_single_perspective_explore_real_llm.py`). Per deepened wheel that is
  2N×(1 apex + 3 extraction) + 6N×(4 generation + 2 audit *only when the eager audit is enabled*) calls. With the
  eager audit off (the default) the audit term is 0 here and the spend moves to whichever pathways a conversation
  actually asks about — `audit_feasibility` charges 2 calls per named pathway, once, and those two (Ac+/Re+) are
  gathered, so the person waits one call's time for them. CLAUDE.md said "2N Transformations" until
  2026-08-13 — it was counting edges. If you are reasoning about explore latency or about how many pathways the
  model gets to choose between, this multiplier is the number that matters, and adding an insight category
  multiplies the whole stage. (`SynthesisGeneration` → S+/S-; the Advisor path syntheses only
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
7. **`str(report)` is the ONLY seam back to the model — a pipeline's Python return value is not.**
   `AnalysisPipeline` returns `AnalysisResult(errors=[StepError...])`, but the `@llm.tool` wrappers
   (`analyze`, `anchor`, `ingest`) return `str(concern.report)`. Anything that lands only on the result
   object is invisible to the LLM. Measured: in `claim2-weak-r1` two A2 cells logged `anchor:ok`
   repeatedly and then summarised `perspectives=0` — every expansion had failed, the errors rode home on
   `AnalysisResult`, and the report said `ok=True`, `"Analysis complete: 2 theses, 2 polarities, 0
   perspectives"`. The arm whose whole claim is a durable record read as a model that declined to build
   one. Two silent-success sites caused it, now guarded: `AnalysisPipeline.resolve` (ok tracks
   `perspective_hashes`; sub-reports with `ok=False` become `StepError`s since they never raise;
   expansion failures named in the summary AND `artifacts["errors"]`) and `ExpandPolarity.resolve`
   (`ok = bool(all_pps)`). Same rule as the repositories' fail-soft reads: **degrade, never silently** —
   "nothing to build" and "the build failed" are opposite conclusions for the agent's next turn. When
   auditing any pipeline, check the report, not the return type. Partial success stays `ok=True` (a
   built perspective is real) but must name the loss. Locked by
   `tests/test_pipeline_failure_visibility.py`.

   **Same defect, exploration side (3 more sites, now guarded).** `ExplorationPipeline.resolve`
   (ok tracks `transformation_count`; per-wheel `StepError`s named in the summary AND
   `artifacts["errors"]` instead of riding home on `ExplorationResult`) and
   `ExploreTransformations.resolve` twice — failed edge pairs were only `logger.warning`ed, so a wheel
   whose every pair failed rendered as `"0 new, 0 existing"` with `ok=True`, **the same text a
   fully-transformed wheel produces**; and the no-edge-pairs early return left `ok=True` although a
   well-formed wheel always has pairs (N PPs → 2N edges → N pairs), so a structural fault read as
   "deepened". Note `ExecutionReport.ok` defaults to `True` — a failure branch that never sets it
   reports success, so the absence of an assignment is the smell to grep for.
   This chain is load-bearing for the decision ceremony specifically: an `adopted_pathway` ground IS a
   Transformation, so a wheel that got none can only ground a cost and never a recipe for living with
   it — a silent "Exploration complete" yields a half-record that reads as whole. Locked by
   `tests/test_exploration_failure_visibility.py`. **A log line is not a report line.**

   **Same defect, two levels deeper (`find_polarities` step, now guarded).** Two sites, and the pair is
   the lesson. (a) `AnalysisPipeline.resolve`'s `except` around `FindPolarities` recorded a `StepError`
   and summarised `"polarity extraction failed"` with **no message and `ok=True`** — the exception text
   rode home on `AnalysisResult` like everything else in this section. (b) One level below, Phase 1 of
   `FindPolarities` gathered per-thesis extraction **without `return_exceptions`**, so one raising thesis
   aborted the fan-out for all of them. Together they turned a single bad `upsert_estimation` into
   `anchor:ok` over a case with zero polarities. Measured in `claim2-weak-r14`: the A2/rep-1 run's
   `anchor` raised twice, and the *reported* cause ("Perspective has no Polarity connected") was false —
   `incremental_build_mixin.commit()` validates cardinality BEFORE hashing, so a committed Perspective
   provably had its edge. **The same false-cause shape as `_resolve_source_id`'s docstring case
   (`claim2-weak-r6-grounding`): when a graph error names a condition the commit path would have
   rejected, suspect the message before the condition.** Isolating the failure is only half the fix —
   the surviving summary now names the failed theses and their causes (`artifacts["failed_theses"]`),
   because "3 antitheses for 5 theses" reads as complete to the agent. Root cause was
   `EstimationManager.upsert_estimation` detaching rather than deleting a superseded Estimation, leaving
   an orphan that hash-dedup later resurrected into a `provider` cardinality violation — see the
   **Estimation lifecycle** note under Analysis chain. Locked by
   `tests/test_find_polarities_failure_visibility.py` and `tests/test_estimation_upsert_lifecycle.py`.
   Cost accounting for this section's rule: this one defect ate three separate r14 anomalies (the
   `anchor` crash, the `perspectives=0 … decisions=1` contradiction flag, and the A2 `memory 0/4`
   storage hole) — all the same run, since a case with no perspectives has nothing to carry over.

### Gates (score-based filters — the prompt that feeds each *is* a gate input)
- **`_rank_polarities`** (`analyst/analyst.py`, `HS_THRESHOLD=0.7`, `MAX_POLARITIES_TO_EXPAND=5`): keeps
  polarities with antithesis HS ≥ 0.7. Fed by `AntithesisExtraction` / `AntithesisClassification` HS. The
  SIMPLE=1.0 shortcut can inflate everything past it → gate stops differentiating. **Passing the gate and
  being developed are different states, and a bare `expanded: False` conflated them.** `polarity_quality`
  carries a `status` naming WHY: `expanded` / `deferred` (HS ≥ threshold, dropped for
  `MAX_POLARITIES_TO_EXPAND` — work owed) / `failed` (expansion errored — work owed) / `set_aside` (below
  threshold — the gate working, nothing owed). The Analyst prompt's "Reading Polarity Quality" section must
  keep naming all four and must keep saying `deferred` and `failed` are **not** judgements — the resume case
  is exactly the one where the model would otherwise report a crashed expansion as a considered omission. The
  read-side twin is `rendering.polarity_completeness` (`developed` / `partial` / `not_developed` /
  `set_aside`, derived per polarity on read, `hs_threshold` passed in by the caller): an unscored polarity
  reads `set_aside` rather than lost work, since claiming interrupted work on no evidence sends the user
  chasing a build that never started.
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
  **The `explore` tool doc also carries the CALL threshold** ("Two mapped tensions are already
  enough", + the consequence: waiting for a fuller map is how a decision closes with no pathway).
  Measured in `claim2-weak-r2`: 5/6 live A2 runs never called `explore`, and 0/6 decision records
  carried an `adopted_pathway` ground — the threshold was stated only in `_DECISION_READINESS`,
  ~100 lines below the tool list, while the doc read at call time said merely "use once tensions
  exist" and left "enough" to the model's judgement. Same lesson as `record_decision` (see
  §decision-lifecycle): **when a prompt rule governs whether to CALL something, it belongs in the
  tool doc too.** Unscoped only — the scoped variant is already inside an exploration. Locked by
  `TestDecisionReadiness.test_the_explore_threshold_reaches_its_tool_doc_too`.
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
  cost and the re-audit had nothing specific to point back to (caught by `tests/e2e`). `_TOOL_DOCS["record_decision"]`
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
  **A cost RENDERS with its condition** (live since 2026-08-10): the ground edge still points at the minus
  Statement (the only committed node that IS the price, and what the bench's position guard checks), but a bare
  minus is a named bad OUTCOME — "accounts may follow him out" cannot distinguish "the risk I accepted and am not
  paying" from "the thing now happening to me", which is the exact distinction wobble variant (a) turns on. So
  `rendering.accepted_cost_condition` appends the control statement's CONDITION, derived structurally off the
  perspective the aspect sits in: "— arises when {chosen side} is held without {opposing plus}". No LLM call, no
  new node, `accepted_cost` role only (a condition clause on an `adopted_pathway` would read as the recipe being
  what goes wrong). **This is the paper's NEUTRAL-T variant, not a divergence** — "T without A+ yields T-" with
  truth criterion "T is true iff it fosters A+" [P0 p.29] is the theory's own second form of Rule 3.3, alongside
  the primary aspect-level "T+ without A+ yields T-" [P0 p.5] that CC/DV score. The ledger wants the neutral-T
  level because what the person committed to is the SIDE, not its idealised plus. Do NOT collapse the two forms:
  different developmental levels, different jobs (CC/DV score aspect coherence; this states the condition under
  which a committed side extracts its price). Third encoding site of the same variant: `ASPECT_DEFINITIONS`
  (`concerns/scoring_scales.py`) — all three move together. **Ambiguity is resolved by the record's OWN other
  grounds, and their citation is authoritative rather than a tie-breaker.** A minus is shared whenever `commit()`
  dedup finds the same wording, and that is the common case, not the exception: measured on the live anchor path, 3
  well-separated tensions shared nothing (6/6 conditions rendered) while 5 adjacent ones shared 7 of 10 minus
  aspects (0 of those 7 rendered) — which is why `claim2-weak-r5` recorded 5 risk-grounded costs and not one
  condition. So when the decision grounds a Perspective, the condition comes from THAT tetrad or from nowhere.
  Consulting siblings only when the minus was ambiguous (the first version) left a *unique* minus rendering its own
  tetrad's poles under the cited tetrad's name — reproduced: P1's `T-` priced with P2 cited as the tension printed
  "— arises when Control is held without Autonomy builds responsibility" on a record naming P2, silently. With no
  perspective cited at all, the single-candidate rule still applies and ambiguity renders plain. Bench side, `scoring._ground_content` imports
  `ACCEPTED_COST_CONDITION_MARKER` and strips the clause before the citation overlap — the derived clause roughly
  triples a ground's word count, so leaving it in the denominator would score a reply that names the price exactly
  as "not cited". Locked by `test_decision.py::TestDecisionRendering` (both sides, role-scoping, ambiguity,
  loose-statement fail-soft).
  **The role is CHECKED at the write, not only taught** (2026-08). The general lesson first: *documented at five
  sites and enforced at zero is a bug, not a convention* — every site above stated "the chosen side's minus" while
  `RecordDecision` attached whatever hash the model handed it, and the archive shows the model taking every wrong
  branch available (one bench round put EVERY `accepted_cost` on the Perspective; another on a Statement sitting at
  `T/T-`). Only `Advisor._accepted_cost_ground`, which DERIVES the ground, ever got it right — so a prompt
  restatement was never the missing piece. Two structural guards, both graph walks, both fail-OPEN on a repository
  fault (a confirmed decision must not be lost to a lookup that could not run):
  `_accepted_cost_misplacement` refuses a cost that is not at a minus position, and `_ground_set_inconsistency`
  refuses a ground SET whose members disagree about which tetrad the decision concerns — a Decision carries up to
  three independent such claims (`accepted_cost`→Statement locating 1..N perspectives, `role=None`→Perspective,
  `adopted_pathway`→Transformation→whole Nexus) and nothing reconciled them.
  Three boundaries worth generalising: (1) **structural half only** — "is this a minus at all" is decidable by
  walking the graph, "is it the CHOSEN side's" needs the stance read against the poles and stays semantic, in
  `DecisionCoherenceCheck`; a guard that reaches for the semantic half refuses valid records. (2) **Refuse, don't
  downgrade** — attaching with `role=None` is the obvious repair and is wrong, because decisions with no
  `accepted_cost` passed 17 of 19 archive-wide against 68 of 120 with one, so any silent drop is the cheapest way
  to clear the re-audit; refusal costs a turn, and since the ceremony already happened in conversation the wording
  survives it. (3) **Only ROLED grounds are checked against the frame** — plain grounds DEFINE it, since weighing
  two adjacent tensions and pricing the choice in one of them is a good record that a strict all-grounds
  intersection would refuse. And `None` from the frame resolver means "names no tetrad", never "the empty set":
  a free-standing statement must constrain nothing. Locked by `TestAcceptedCostMustBeAPrice` and
  `TestGroundsMustAgreeOnOneTension` (both refusals, plus the four false-positive cases and the renderer half).
  **The open-naming carve-out is about CONTENT, not storage** (fixed 2026-08): `{decision_speech_note}` exempts the
  decision record from the machinery ban, and bounding only the *naming* let the model recite the record's SCHEMA in
  plain words. Measured: an A2 wobble turn in `claim1-weak-r2` said "the validation on your decision already failed…
  it said the stance 'directly contradicts the adopted pathway ground'" and "the T pathway holds", costing
  `conversational_fit` — a non-inferiority dimension, i.e. the base model's home turf, where a loss is disqualifying
  rather than a trade-off. The note now separates what the record SAYS (theirs) from how it is stored (not), names
  grounds/roles/pathways/validation-verdict as internals, and carries a paired example — "don't say it" alone
  suppresses the counsel with the jargon. Unscoped only (the scoped preamble governs vocabulary; prompt-only arms have
  no schema to leak). Locked by `test_naming_the_record_openly_does_not_expose_its_schema`.
  **Decision mode closes on PATHWAYS** (added 2026-08): the discrimination test tells the model what not to map, and
  nothing told it to develop what it kept — so pruning read as permission to stop building. Measured: all 6 weak-tier
  A2 runs in `claim1-weak-r1` stopped at `anchor` (1-2 perspectives, zero `explore`) where the strong tier explored in
  4 of 6, leaving the ceremony with no pathway to offer as the `adopted_pathway` ground and no arrangement to read the
  S- trap version from. Method, not machinery, so `tests/e2e/arms.py` REWRITES the tool verb instead of dropping the
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
  `_strip_tool_prose` (asserted in `tests/e2e/arms.py`'s rewrite table + the bench's own tests). (c) *Prose is not
  recording*: 4 of 6 A2 runs never called `record_decision`, 2 having already written the full record out under
  headings. That paragraph names the tool deliberately so prompt-only arms drop it — they record in prose
  legitimately. **RECURRED at the weak tier** (`claim2-weak-r2`, 4 of 6 A2 runs, prompt paragraph verified
  rendering): the paragraph is 100 lines below the tool list, and the text nearest the call decision — the
  `record_decision` DOCSTRING and `_TOOL_DOCS["record_decision"]` — carried only the PROHIBITION ("never call
  this silently") and no counterpart obligation, so on a weak model the asymmetry reads as "when in doubt, don't
  call". Both now state that confirmation OBLIGES the call and that prose in the same turn needs the call in that
  turn. General lesson: a rule stated only in a prose section can lose to the tool doc at call time — **when a
  prompt rule governs whether to CALL something, it belongs in the tool doc too.** Bench-side, the symptom is
  double-counted unless attributed: the missing record made the wobble (a) variant unanswerable, so the row read
  as the framework losing the re-audit (`RunRecord.prose_only_decision` /
  `wobble_a_without_a_record` in `tests/e2e/models.py` name the cause once).
  **RESOLVED IN CODE, not in the prompt** (live since 2026-08-10): the prompt layer was the wrong layer. Firing
  rate was 6/6 strong vs **0/6 weak** on identical text, and three rounds of strengthening (the prose paragraph,
  the `record_decision` tool doc, the `explore` threshold) moved the weak tier by zero. A decision is a
  **user-driven artefact** — it exists because the person declared it, and that declaration is an OBSERVABLE
  EVENT in their message — so whether a record gets written must not be the model's election at the moment it is
  most inclined to just answer well. `record_decision` already host-attests WHO confirmed (`principal`); the same
  principle now covers WHETHER: `concerns/decision_confirmation_check.py` (bounded classification of the person's
  own message, creates/mutates nothing, fail-soft) + `Advisor._repair_unrecorded_decision` (post-reply, both
  `chat` and `chat_stream`, records under the same attested principal when the person confirmed and no SUCCESSFUL
  `record_decision` ran — a failed call still repairs, since an in-band refusal leaves the identical false
  belief). **The `accepted_cost` ground IS derived** (live since 2026-08-10), and only that one: the check also
  asks which mapped tension's pole the stance corresponds to (`chosen_polarity_hash` + `chosen_side`) — a MATCHING
  question with a verifiable answer, not a judgement — and `Advisor._accepted_cost_ground` then resolves the cost
  BY DEFINITION, chose T → `t_minus`, chose A → `a_minus`, because a plus is a goal or an obligation (something to
  DO, i.e. a remedy) and never a price. No match → no ground: a wrong `accepted_cost` is worse than none, since it
  makes the record claim a price the person never faced and sends the re-audit to reassure them with the wrong
  risk. **`adopted_pathway` is derived too, since 2026-08-13** — one ground, from the pathway the seam itself just
  built (see "The record never pointed at the pathway" below). It was withheld until then on the reasoning that it
  "needs a Transformation the wheel may not have", which stopped being true the moment the seam started building
  wheels before recording.
  **The prompt is deliberately silent about the backstop** — telling the model it exists would
  license the laziness it compensates for. Reviewing prompts here: the three prose/tool-doc rules stay exactly as
  they are (the model calling the tool itself is still the path that produces good grounds); the seam is a
  floor under them, not a replacement. Locked by `tests/test_decision_confirmation_repair.py` (DB/LLM-free seam:
  when it fires, when it must not, what it records) + `tests/test_decision_repair_weak_tier.py` (`real_llm`,
  pinned to the weak model — at the strong tier the repair never fires, so a strong-tier version asserts nothing).
  General lesson, and the one that outranks the tool-doc lesson above: **when a rule governs whether an
  observable user event gets persisted, it belongs in code, not in a prompt at any distance.** Locked by
  `test_ritual_asks_once_and_never_gates_the_record`,
  `test_reading_the_record_back_is_not_speaking_as_them`, `test_prose_summary_is_not_a_substitute_for_recording`.
  **The seam then broke the bench flag that measures it** (fixed 2026-08-12, and it is the THIRD arrival of one
  mistake). `RunRecord.prose_only_decision` was "no `record_decision` on the commit turn", justified as "it is the
  only tool that can close a decision" — true, and irrelevant, because the repair seam is not a tool: it commits
  Decision nodes with nothing in `tool_calls`. So the cell where the framework CAUGHT the omission read identically
  to the cell where the person was misled, under a message asserting the harm ("the person was told it was written
  down and it was not"). Measured over the 95 saved A2 cells: 46 flagged, **27 hold a Decision**; `r13` printed the
  contradiction on one page ("1 run closed a decision in PROSE" above "runs recording >=1 decision: 1/1") and r11's
  headline "4 of 6 closed in prose" re-derives to 1 clean recordless cell. Fixed by reading the graph
  (`if self.decision_hashes: return False`), with the election half preserved as
  `closed_without_electing_the_tool` on its own informational line — that number is still the one that would move
  if the prompt ever bound, and deleting it would hide the behaviour the seam exists to compensate for.
  `collapsed_to_a1` and `wove_no_pathway` were each corrected for the same thing, so the rule is now general:
  **every artefact in this framework has a non-tool writer (repair seams, `run_exploration` called directly,
  pipelines invoked inside skills), so any bench predicate about whether an artefact EXISTS must read the graph,
  never `tool_calls`.** `tool_calls` answers a strictly different question — did the model ELECT it — and the two
  belong in separate predicates with separate report lines.
  Explorer side of the toggle: decision declarations are an IMMEDIATE handover signal (explorer/system_prompts.py
  "when the user tries to DECIDE" — the Explorer cannot record and must never fake an acknowledgment; reading
  recorded decisions stays available via query_graph/inspect_node, and NAVIGATOR_APP_ADVANCED_TOGGLE names Decision
  in its vocabulary list). Analyst side (live since 2026-08, cross-agent parity fix): the same seam in
  analyst/system_prompts.py — cannot record, never fakes an acknowledgment, and NEVER anchors the declared choice
  as a thesis (a decision is a stance, not a tension; anchoring it misfiles it as analytical structure); locked by
  `test_analyst_never_fakes_or_anchors_decisions`. No settings knobs (policy-not-config).
  **Pathways before closing** (`Advisor._ensure_pathways_before_closing`, live since 2026-08-11) — the SECOND
  application of the same code-not-prompt ranking, and the one that made the bench measure the framework at all.
  `_DECISION_READINESS` has always carried the rule ("A decision closes on pathways, not on tensions alone...
  Without pathways there is no paired recipe to adopt, no trap version of the choice to name, and the counsel at
  the closing turn is a single tension restated with more emphasis"), and the model ignores it in the same
  tier-shaped way it ignored `record_decision`: `explore` fires in **6/55 weak-tier runs (11%) vs 17/25 strong
  (68%)**, Fisher p ~ 5e-07 — and in all 6 cells of `claim2-weak-r7-readside` it fired **ZERO** times while
  `anchor` built 5-7 tensions each. Those cells closed decisions over a graph with no nexus, no cycle, no wheel,
  no transformation and no synthesis: **the differentiator never executed**, so the "framework arm" was a prompted
  model with tetrads bolted on and every judged row from it measured `anchor`, not Structured Dialectics. Not a
  capability limit — `tests/e2e/probe_explore_reachability.py` shows the weak tier calling `explore` unprompted
  when a turn asks for a causal map — so it is ELECTION, and election at the closing turn is exactly what the
  decision-repair lesson says belongs in code. The seam fires only inside `_repair_unrecorded_decision` AFTER the
  confirmation verdict passes (never a background weaver: mid-exploration weaving would burn latency on
  arrangements the conversation may never reach and make `explore`'s per-call perspective cap meaningless).
  **As of 2026-08-26 that seam READS pathways and no longer builds them** (`_ensure_pathways_before_closing`):
  per-turn timing on a real provider caught it billing construction to the person's wait — two turns making
  ZERO tool calls cost 141.9s and 402.0s, of which **127.7s and 387.7s were the weave**, both landing on the
  turn immediately before the closing. `Advisor.chat` awaits the repair before returning, so the "reply already
  delivered" comment at that call site was false for `chat` and always had been. The read is now the closing's
  ONLY source of a ground, so a silent failure in it means every decision closes ungrounded. **This leaves a
  priced debt, not a clean win:** the −0.69-unwoven / −0.25-woven gap below is exactly what the removed
  construction used to close, so an unwoven closing is now logged at WARNING (deliberately a log, not a queue
  — an undrained queue is this archive's signature defect) and the construction is owed a place OFF the turn.
  Inverted guards: `tests/test_pathways_seam_real_llm.py` (seeded — the closing wove 0 while explicit
  exploration wove 2 and the read found 12 transformations) and
  `tests/test_pathways_before_closing_weak_tier.py` (conversational — asserts a weave only when the MODEL
  called `explore`, since only then is one legitimate). **The floor was `< 2` through r15 and it was wrong — one tension is
  enough.** The justification ("one opposition has no arrangement to enumerate; a wheel over it is the tension
  restated") contradicts the framework's own model: `PerspectiveCombination` treats a single PP as the
  circular-causality BASE CASE (`W(1)=1`), and `docs/theory/generative-rules.md` Rule 8 has layer-1 wheels covering
  the within-tetrad diagonals. Measured rather than argued —
  `tests/test_single_perspective_explore_real_llm.py` (real provider, weak tier): a 1-PP exploration yields **1
  cycle, 1 DEEPENED wheel, 6 transformations, 6 named Ac+/Re+ pathways, 1 synthesis**. Cost of the old floor, in
  `claim2-weak-r15-voice`: 3 of 6 A2 cells called `anchor` exactly once, so the seam saw one unwoven perspective and
  returned; those cells closed on `woven=0 transformations=0`, the report flagged the framework for not arranging
  what it had mapped, and split by that state the judged mean was **-0.69 unwoven vs -0.25 woven** over 36 scores
  each. **Standing caution: a floor stated as a count is a number the model can sit BELOW.** The same "two" lived in
  three places at once — the seam guard, `_DECISION_READINESS`, and the `explore` tool doc — and all three now say
  ONE plus "no minimum to reach"; changing one without the others reinstates the floor
  (`test_the_explore_threshold_reaches_its_tool_doc_too` asserts the pair, and `tests/e2e/arms.py::_TOOL_REWRITES`
  carries the A1/A1.7 rewrite so the baseline is handed the same floor — bench fairness rule 4). Ordering is
  load-bearing: pathways BEFORE
  `RecordDecision`, because the record's grounds are read from the graph — weaving after the write leaves
  `adopted_pathway` unavailable on the very record it exists for. Nested in its OWN try/except inside the repair's:
  a richer grounding is worth attempting, never worth losing the record over. Reviewing prompts here: the
  `_DECISION_READINESS` pathways paragraph and the `explore` threshold line stay exactly as written — the model
  exploring on its own is still the path that produces the best-fitted arrangement, and the prompt stays silent
  about the backstop for the same reason as above. Locked by `TestPathwaysBeforeClosing` in
  `tests/test_decision_confirmation_repair.py` (fires on the r7 shape, fires on a LONE tension, skips
  woven/lone-woven/empty, carries the
  counsel-mode `nexus_hash` pin, orders before the record, survives an exploration fault with the record intact)
  + `tests/test_pathways_seam_real_llm.py` (`real_llm`, weak tier, tensions SEEDED: the conversational tripwire
  `tests/test_pathways_before_closing_weak_tier.py` skipped on its first run because the weak tier anchored only
  ONE tension in three turns and the floor silenced the seam — read then as "that measures `anchor` productivity,
  not the seam", which is why the seeded pair was built. **That skip was the defect announcing itself and it was
  filed as a test-instrument problem for two runs** — the floor it exercised was the bug, so a skip on the
  framework's own behaviour is worth diagnosing before it is worked around). Measured: `0 → 2` woven perspectives,
  and weaving does NOT cost the record (both on the same turn), which was the live suspicion once the seam moved
  between the verdict and `RecordDecision`. It fires on BOTH closing branches — the model-recorded one is larger
  (50 saved cells recorded without exploring vs 48 with both), and **both now ground** (this map called the
  recorded branch "weaker … an already-written record cannot take an `adopted_pathway`" until 2026-08-13; that was
  simply false — see the next entry).
  **The pathway existed and was still unnameable** (fixed 2026-08-12, from `claim2-weak-r10`) — and this one is
  NOT the election failure the two above were, which is why three rounds of prompt work never touched it. r10's
  seam worked: 6/6 decisions recorded, 6/6 with risk-grounded costs, 5/6 cells with woven pathways. And
  `adopted_pathway` was **0/6**, *including the cells that called `explore` themselves*. Cause:
  `ExplorationPipeline` published `transformation_count` and nothing else, so a model told "12 transformations"
  had no hash to pass — the role was documented on a ground that did not exist in any tool's output. The general
  rule this instance adds: **a documented ground must be constructible from what the tool RETURNS**; the doc, the
  role vocabulary, and the storage can all be right while the artifact is unreachable, and nothing in the
  prompt-review checklist catches that because every prompt surface reads correct. Fixes: `transformation_hashes`
  on `ExplorationResult` plus a `pathways` artifact on the pipeline report and on `deepen` (which had the same
  gap — it merged effects but never named an adoptable pathway). Rendered via a shared
  `rendering.pathway_line` — hash + edge + Ac+/Re+ text, because a bare hash list is not a menu and
  `adopted_pathway` asks the model to pick ONE recipe. Ac+/Re+ ONLY: those two ARE the circular causality
  (Rule 5.1, T-→A+ and A-→T+ simultaneously), so they are what gets adopted, while Ac-/Re- are degradation modes
  that belong to trap-naming — a menu listing them invites adopting a degradation. Two subtleties, each its own
  test: the source is `.all` not `.new` (a wheel sharing edge pairs with an already-deepened one reuses every
  transformation, so `.new` reports "no pathways" for a fully developed wheel — and the reuse case is the LIKELY
  one, since `explore` already deepened the top wheel), and hashes dedup across wheels (opposite-edge
  transformations are shared; the same hash twice reads as two recipes). `one_line` on the recipe text for the
  same ledger-injection reason as `_dump_decisions`. Tool docs updated on all five surfaces that decide whether
  the ground gets passed (`explore`, `explore_scoped`, `deepen`, `deepen_scoped`, `record_decision`) — the
  `record_decision` doc now also rules out the two near-miss hashes BY NAME (a wheel names the arrangement, a
  perspective names the tension) and says to omit the role rather than substitute — the seam still omits it rather
  than substituting when it holds no pathway (`test_no_pathway_exists_so_none_is_grounded`, renamed 2026-08-13 from
  `test_adopted_pathway_is_never_guessed`; the "never" was the stale half). Locked by
  `TestPipelineNamesThePathwaysItBuilt` (`tests/test_exploration_failure_visibility.py`),
  `TestDeepenNamesThePathways` (`tests/test_advisor_deepen.py`), and `TestPathwayHashReachesTheModel` +
  `TestPathwayLineIsPickable` (`tests/test_prompt_review_regressions.py`). Two pre-existing tests had hand-rolled
  `ExploreTransformationsResult` stand-ins that broke on the new field read — both now use the real dataclass,
  which is the durable lesson: **a hand-shaped stub covers only the fields the caller read the day it was
  written**, and goes stale silently. NOT yet verified at the behaviour layer: whether the model actually passes
  the role needs a bench re-measure of `adopted_pathway` per record.
  **The record never pointed at the pathway, even once both existed** (fixed 2026-08-13, from
  `claim2-weak-r16-floor`). r16 is the answer to the re-measure the entry above asked for, and the answer was no:
  the floor fix worked structurally — **6/6 A2 cells wove, 12-42 transformations each — and
  `adopted_pathway_grounds` was still 0/6**, including the cell that called `explore` itself at t2 and
  `record_decision` at t5 with 30 pathways on the graph. Three causes, all in code, none in the model, and none
  visible from any prompt surface: (1) `run_exploration` returned only `str(report)`, discarding the
  `transformation_hashes` that `ExplorationResult` publishes for precisely this caller — split into
  `run_exploration_detailed` returning `(report, hashes)`, with the `@llm.tool` path unchanged (an LLM can only
  consume the prose); (2) the recorded-decision branch deliberately did nothing with the pathways it built, on the
  belief that a committed Decision cannot take a new ground — **false, and the load-bearing correction: GROUNDED_IN
  is an ANALYTICAL edge** (`grounded_in_relationship.py`, "connects to already-committed nodes and does not affect
  hashes") and `Decision`'s own docstring shows `commit()` then `grounds.connect(...)`; (3) `if not unwoven: return`
  skipped the exact cell that most deserved a ground — nothing to BUILD is not nothing to GROUND, so it now falls
  back to `_existing_pathway_hashes()`. ONE pathway is grounded, not six: the role names "the pathway adopted as
  the ongoing recipe", singular, and grounding all of them makes the re-audit's "here is your recipe" a menu again.
  Idempotence matters on the attach path because `connect` dedups only `direction="any"` edges — scan
  `decision.grounds.all()` for the role first. The general lesson generalises the r10 one a level up: **the layer
  distinction is a CAPABILITY, and a seam that forgets which layer it is writing to will refuse work it is allowed
  to do.** r10 found a documented ground with no constructible hash; r16 found the hash constructible, the storage
  willing, and the caller declining on a false invariant — so when a seam says "cannot", check the relationship
  class before believing it. Locked by `TestTheClosingGroundsOnThePathwayItBuilt`
  (`tests/test_decision_confirmation_repair.py`: the repair branch grounds, only one is adopted, no pathway → no
  role, an already-recorded decision gets its edge, a second closing does not double-ground, the target comes from
  the tool report's `decision_hash` rather than "newest Decision", and a grounding fault never breaks the turn) —
  revert-verified 4/45 failing on the three call sites alone. Still NOT verified at the behaviour layer: whether
  grounding the pathway moves `paired_recipe` (-0.58) or `decision_closure` (-0.75) needs r17.
  **The decision was not decidable yet and got recorded anyway, 12 of 12** (measured 2026-08-19,
  `r23-controls`; UNFIXED, and deliberately so — **the product owner's call, made 2026-08-20: leave it.** A
  premature record is the cheaper of the two errors, per (3) below. Do not reopen this as a prompt patch without
  a new measurement; the entry stays because the constraints below outlive the decision.)
  `premature_relocation` is a control scenario whose pre-registered right answer is "you do not have enough to
  decide yet", and **every one of the 12 strong-tier A2 cells called `record_decision`**, committing 26 Decision
  nodes; `DecisionCoherenceCheck` returned 25 passed / 1 failed. That is the exact mirror of the whole
  under-recording lineage above, and three things constrain any fix — read them before hardening anything here a
  fifth time:
  (1) **No theory claim licenses a fix.** Decision TIMING appears nowhere in the eight generative rules.
  `docs/theory/` prices what a decision closes ON — pathways (Rule 8 arrangement) and an `accepted_cost` (Rule 1
  dialogical) — and both were satisfied in these cells. "Premature" is a product judgement, so this is a design
  conflict, not a defect against spec.
  (2) **A prompt-only fix cannot bind, for the reason the opposite failure already proved.**
  `_DECISION_READINESS` was hardened four times against WITHHOLDING a record and the fix that finally worked moved
  the rule out of the prompt entirely (`decision_confirmation_check.py` + `_repair_unrecorded_decision`). That seam
  fires on the observable confirmation event, so a "don't record when it's premature" paragraph would be repaired
  back in by code. Any fix here is a code fix on that same seam or it is nothing — the same
  code-not-prompt conclusion, arrived at from the other direction.
  (3) **The two error directions are not symmetric in measured cost.** A withheld record leaves the person
  believing something was written down that was not — the harm that built the repair seam, and the one with a
  judged cost attached. A premature record leaves the person holding an artefact that says they decided. Both are
  false beliefs about the graph; only the first has ever been measured.
  Why this is more than hygiene: on that control **A2 LOSES the blended composite, -0.767 [-1.504, -0.029],
  `warmth` included**, while the pre-registered NI tripwire PASSES (-0.472 [-1.094, +0.150]) — so the control did
  not fire and the finding is a product one, not an invalidation. Reviewing prompts here: change nothing until the
  direction is decided; if it ever is, `_TOOL_DOCS["record_decision"]`, `_DECISION_READINESS` and the confirmation
  check move together (the tool-doc lesson above), and `tests/e2e/arms.py::_TOOL_REWRITES` must hand A1/A1.7 the
  same restraint or the comparison stops being fair (bench fairness rule 4). Write-up: `tests/e2e/rounds.md`
  "r23 RESULT".
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
  **A risk RECORDED AS REFUTED, not as carried** (fixed 2026-08-14 — the audit's fourth check): the ceremony's
  rules all assume a risk the person is willing to name. Under pressure to drop one, the failure is the opposite:
  the rationale writes the risk down as VOID and that verdict becomes a settled fact the person is handed back.
  Measured on `cofounder_ladder_return` (`ladder-return-r16`), the one lane that spends a turn arguing a risk away
  behind a fabricated citation — **4 of 12 A2 decisions carried the dismissal into the rationale as fact, against
  0 of 80 on `cofounder_equity`**, which applies no such pressure. Not one was flagged FOR IT: three passed, and
  the fourth failed on an unrelated criterion whose reasons never mention the refuted risk. *Why* it passed is
  the transferable part: `DecisionCoherenceCheck`'s grounding check SKIPS when no grounds are recorded, and a risk
  that has been argued away is exactly the risk nobody records as an `accepted_cost` — so the blind spot lined up
  with the failure. Archive-wide that reads as no-`accepted_cost` decisions passing 11/12 against 41/80 with one:
  recording no cost was the reliable way to pass the audit. Two sites, one authoring and one detecting, and they
  must be read together: `_DECISION_READINESS`'s "**Write what they decided, not the argument that won**"
  (a rationale takes their reasons, not their verdict on a risk; never supply supporting detail of your own to firm
  it up; bounded to what you WRITE, since relitigating belongs in the re-audit) and check 3 in
  `DecisionCoherenceCheck.SYSTEM_PROMPT` — stated against the RATIONALE's own claims so it is independent of
  check 2's grounds-present precondition. **The split is on the VERDICT, not on where the evidence came from**,
  and that is the whole design: the measured rationale rests on facts the person knows best (their own contracts
  auto-renew), so an auditor told to flag "support outside the grounds" would flag every well-informed decision,
  and one told not to flag facts about one's own business would clear the motivating case. Same facts, `carried`
  passes and `refuted` flags; evidence provenance sharpens the REASON only. Pairs with **Materialised ≠
  resurfacing** above — both are about what the record is worth when read back, one at re-audit time and one at
  authoring time. Locked by `test_prompt_review_regressions.py::TestDecisionReadiness::
  test_a_refuted_risk_is_not_written_down_as_settled` / `::test_the_auditor_can_see_a_refuted_risk_without_a_ground`
  / `::test_the_auditor_judges_the_record_not_the_world`; behaviourally by
  `tests/test_decision_rationale_integrity_weak_tier.py` (--real-llm, WEAK tier, every case a PAIR — the mock brain
  fills `incoherent=False`, so a mocked run can show neither the check firing nor, more importantly, declining to).
  **The rate that motivated it was a PROXY, and that is its own lesson.** It was counted over assistant
  *replies*, because `driver._read_decisions` captured hashes and grounds but never the rationale text or
  `Decision.validation` — so the rate that justified a fix to what lands in the GRAPH could not see the graph.
  Fixed the same day (`RunRecord.decision_rationales` / `decision_verdicts`, reported under "Decision ceremony",
  `"<hash>:none"` when the fail-soft audit did not run so an error can never pool with a pass); the fix's endpoint
  is only measurable from that run forward, and earlier reports print "predates verdict capture" rather than a 0.
  General form: **before writing a prompt rule from a measured rate, check the measurement can see the thing the
  rule changes** — the sibling of "count the behaviour before writing the rule", one level down.
  **And the same rate was DOUBLE-COUNTED** (corrected 2026-08-14, first reported as 6 of 24 / 0 of 160, actually
  3 of 12 / 0 of 80). The ad-hoc counter globbed `tests/e2e/results/*.json` without excluding the `-runs.json`
  sidecars, which hold a duplicate copy of every run, so each decision was counted twice. The rate, the
  scenario-locality and therefore the fix all survive unchanged at 25% — but a one-off script that re-implements
  archive loading re-opens a hole the shared helper had already closed (`probe_five_fixes._stems()` carries the
  exclusion; the cross-tab escaped because it deduplicated by hash). General form: **a throwaway counting script
  reuses the archive loader or it inherits none of its fixes**; promote it under `tests/` while the number is
  still being quoted, not after (`tests/e2e/probe_rationale_integrity.py` is where this one lives now, and it
  reports the graph-captured side and the dump proxy side apart, never merged).
  **Check 3 reaches the shape four prompt rounds could not (2026-08-20), and the finding is that it was already
  built.** r25 ended by naming a `record_decision`-side check as "the next move, with three real replies it must
  refuse" — the fourth failed attempt at a paragraph telling the model a corrected fact resizes a price without
  zeroing it. The check existed: check 3 names *immaterial* verbatim and splits on the verdict. But the shape was
  genuinely new, and worth measuring rather than assuming, because every other REFUTED case in the archive denies
  the risk from the first sentence while r25 reps 1/2/9 **concede the residual, price it in the body, and void it
  in the record offered in the same reply** — the prompt's own examples run price-then-carry, and this inverts the
  order. Measured as the FOURTH PAIR in `tests/test_decision_rationale_integrity_weak_tier.py` (rep 9's record
  line against rep 6's on a byte-identical body, so only the last clause differs; pre-registered ~65% / ~85%):
  **the write-off flags with the deciding clause quoted, the resize passes clean.** The second half is the one
  that had to hold — a check that read "the risk got smaller" as "the risk got argued away" would forbid the
  person's own correction from ever landing, which is the more expensive error and the one `_INTERNAL_MODEL`'s
  fork exists to permit. Provenance is weaker than pairs 1-3 and labelled as such in the file: r25 cells are **A1**
  (prompt-only, no tools, no record), so this asks a FORWARD question — the shape ships unchallenged on the bare
  prompt path and is caught at the record on the framework path — and it is a mechanism claim from 2 isolated
  calls, not a lane result. The check is fail-soft, so the person is handed a named flag on the record, not
  stopped. General form: **when a probe names a tool-side fix, spend the two calls asking the existing check
  before building a new one** — and coverage of a case's vocabulary is not coverage of the case.
- **A price nobody recorded — check 5** (`DecisionCoherenceCheck.SYSTEM_PROMPT` check 5 +
  `RecordDecision._unpriced_aspects`, live since 2026-08-20): check 3 above narrowed the blind spot without
  closing it, and the residue is the general lesson. **Check 2 reads the cost that WAS cited; check 3 reads what
  the rationale ARGUED. A record that is simply SILENT about its price does neither, so it cleared both by
  construction** — recounted on the grown archive, decisions with no `accepted_cost` passed **17 of 19 against 68
  of 120** with one, so omitting the price stayed the cheapest way to pass the audit. That is an incentive
  pointing the wrong way, and no wording of checks 2/3 reaches it: the fix is STRUCTURAL. `RecordDecision` now
  resolves the overdevelopment aspects the cited tensions carry and the record did not cite, and passes them in
  as `unpriced=` — the auditor cannot find an omission it was never shown.
  **The A- mapping is stated in the check, because getting it backwards is the failure mode with precedent:**
  the price of a choice is the CHOSEN side's overdevelopment (T- for a thesis stance, A- for an antithesis one);
  the other side's minus is what the choice AVOIDS, never a cost it carries. `_unpriced_aspects` therefore
  returns **[]** as soon as any `accepted_cost` is attached — a structural guard, not a negative condition in the
  prompt, since the leftover would otherwise be exactly that opposite-side minus handed over as an unpaid price
  (cf. the role's own correction: asking for the plus got remedies recorded as costs in 4 of 6 runs).
  **Two over-fits are worse than not checking, and both are pinned.** Flagging every record with no
  `accepted_cost` edge would audit bookkeeping, punish a person who priced their choice in plain words, and —
  given the incentive above — teach the model to attach a cost ground it never weighed. So "priced" is defined
  generously (**"IN ITS OWN WORDS is priced and passes"**), relevance is judged before flagging (a tension can be
  cited for context, not as the fork), and check 3's case is explicitly not re-flagged here (*"one omission must
  not be reported as two failures"*).
  **The reach is a quarter of the gap and the probe prints the shortfall on every run.** Of the 19 priceless
  decisions, 5 cite a tension (reachable), 5 cite only a pathway, 9 cite nothing at all — check 2's documented
  exemption, still exempt. Resolving from SCOPE instead of from the citation would reach all 19 and would also
  fire on decisions about an unrelated question. General form: **a check motivated by a big asymmetry and
  reaching a slice of it must publish the slice**, or the write-up silently annexes the rest of the gap; and
  **an omission check needs the omitted thing supplied to it** — no prompt wording substitutes for the
  structural seam, which is why "the auditor is structurally blind to what was left out" was the diagnosis
  before a word of prompt was written. Locked by `test_prompt_review_regressions.py::TestDecisionReadiness::
  test_the_auditor_can_see_a_price_nobody_recorded` / `::test_check_five_is_silent_when_no_price_was_recoverable`
  (the absent section must not render an empty accusation), resolution by
  `tests/test_decision.py::TestUnpricedAspectsResolution`, behaviourally by the third PAIR in
  `tests/test_decision_rationale_integrity_weak_tier.py` (SILENT — verbatim archive decision `a58da2e` — vs the
  same facts priced in prose with no ground attached).
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
- **Tetrad grounding — the case-particulars lane** (`concerns/tetrad_grounding.py` + `ExpandPolarity._ground_tetrads`
  + `rendering.grounding_line` + `DialecticalContext._collect_grounding`, live since 2026-08-10): a NEW Stack-B prompt
  site whose entire job is to preserve what every OTHER prompt in this map is built to strip. The tetrad's text is
  universal by construction — `component_length` (~7 words), `commit()` dedup folding matching wording into one shared
  node, taxonomy anchoring pulling poles toward `SYSTEMIC_TAXONOMY` apexes — which is what makes a tetrad transferable
  and is why the graph could carry a whole exploration without carrying one fact the person stated. At the
  returning-session wobble in `claim2-weak-r5` A2 asserted "This isn't the accepted cost resurfacing"
  (`cited_record: false`) holding no fact to check the panic against, where the prompt-only control — holding
  "cofounder isn't a rainmaker" — asked whether the person had known all along, and they conceded they had. So this is
  not a memory feature bolted on; it is the counterweight to the abstraction the rest of the pipeline performs
  deliberately.
  **The founding measurement is now machine-scored, and it corrected itself.** An earlier hand-read of the same
  transcripts reported "the graph carried 0 of 15 particulars against the journal's 11 of 15" — it compared one arm's
  ARTIFACT against the other arm's REPLIES, because `SessionRecord` stored A1.7's journal text but only
  `perspectives=N` for A2, and a count says nothing about whether the case is inside. `tests/e2e/scoring.py::
  score_particulars` + `SessionRecord.carryover_in` now record what every arm was HANDED on one field and score two
  separate columns — `memory` (was the fact in the artifact?) vs `used` (did the reply reference it?) — because a
  memory that never held the fact is a STORAGE defect and one that held it while the reply generalised is a PROMPT
  defect, and a single number sends the fix to the wrong layer. Re-scored on the saved r5 records (free, no model
  calls): A1.7's journal holds ~3/4 per cell and its replies use 0–1/4; A2 uses 0/N in 6 of 6. What survives the
  correction is narrower and more useful than the original claim — BOTH arms barely use their memory, and the journal
  at least holds the particulars. Denominators exclude facts the person re-stated in the returning session (echoing
  the transcript is not memory) and facts only the ASSISTANT introduced (remembering its own inference proves
  nothing).
  **Now measured against a grounding-built graph (`claim2-weak-r6-grounding`, 12 cells, first run with the lane
  live), and it splits cleanly: storage moved, behaviour did not.** A2's `memory` went from structurally
  unrecordable to 0.62 (A1.7's journal 0.92) — the graph demonstrably holds `45%`, `60% of revenue`, the
  three-week holiday, the chaotic sales notes, verbatim in a grounding `Rationale`. `used` stayed a dead heat:
  0.12 vs 0.11. So the two-column metric earned its keep on its first real use by sending the fix to the RIGHT
  layer — this is textbook "high memory, low used = PROMPT defect", and had the columns been collapsed the
  obvious reading would have been "grounding did nothing", i.e. rip out a lane that works. **Still no win
  claimed**: A2 lost every judged dimension, but a third of the cells were structurally broken (1 run built no
  graph, 3/6 prose-only decisions, 3/5 never called `explore`, 1 `anchor:FAILED`), so those rows are unreadable
  by the report's own rules. Two machine scores did favour A2 (erosion 5/6 vs 3/6 survived; symmetry slope flat
  or negative in 5/6).
  **The read side needed the same instruction the write side did** (fixed 2026-08-11, from the r6 result): the
  dump rendered `Grounded in:` and NOTHING in `SYSTEM_PROMPT` said what it was or that it must be spoken, so the
  model held "60% of revenue" and replied about "the tension between moving decisively and protecting
  relationships". `_SCORE_READING` now names the marker, says lead WITH the particulars (with the exact failure
  it prevents — restating the tension's shape reads to the person as having been forgotten), says ask rather
  than fill a gap with a generality, and explains the accretion order as a chronology with later disclosures
  current. Critically it also carves the line OUT of the rephrase licence: both `_HOW_YOU_SPEAK` variants
  license free rewording of graph text, which is right for a ~7-word pole and wrong for a number — a reworded
  `60%` is a lost `60%` — so without the carve-out the prompt's strongest style rule instructs the model to
  paraphrase away the only case-specific text it has. Generalises the write-side lesson one step further: a lane
  needs a test at the WRITE caller seam AND at the READ instruction, because "the data is in the dump" and "the
  model is told to use the data" are two different claims and only the first was ever tested.
  **Scope is the whole design, and the prompt is where it is enforced.** `SYSTEM_PROMPT` admits only situation facts
  (numbers, equity splits, dates, named commitments, concrete cited instances) and explicitly refuses four
  neighbours: restatements of the tension (already the tetrad's job), interpretation/diagnosis/advice (the counsel's
  job), facts about the PERSON's character/tone/register, and forward-looking conversational strategy. The last two
  are the HOST application's memory, not the framework's — admitting them turns the dialectical graph into a
  general-purpose notebook, and no theory rule covers them (searched: no reject/negative-space/person-modeling hook
  in any of the six `docs/theory/` pages). Empty string is the required answer when there are no particulars;
  `MAX_GROUNDING_WORDS = 60` is a module constant, not a setting (policy-not-config), generous next to
  `component_length` because the point is to hold what the tetrad cannot, bounded because it renders on EVERY
  counsel turn.
  **Storage is `ExplainsRelationship.role == ROLE_GROUNDING`** — an open-vocabulary edge property following
  `GroundedInRelationship.role` ("a role exists iff a consumer branches on it"). Three properties are load-bearing:
  role is deliberately NOT in `Rationale._collect_structure_hash_parts` (hashing it would fork the node and break
  content-addressable dedup); untagged rationales keep meaning machine assessment prose (CC/DV checks, causality
  reasoning) and MUST stay out of the grounding render, or every tetrad in the dump grows a scoring essay; and
  grounding ACCRETES (a new Rationale per disclosure, joined oldest-first) rather than mutating one field, so the
  note reads as a chronology of what was revealed when. Rejected alternatives, for anyone tempted: an Input (it is
  generative — material there feeds thesis extraction, so conversational particulars would manufacture tensions
  nobody raised and sit permanently "pending analysis"), `Perspective.intent` (hash-participating AND load-bearing
  for sibling-tetrad dedup — case facts there fork identity, and the immutability failure is a LATE `save()` raise,
  no setter guard), and `Rationale.agent="human"` (that sentinel attests a person confirmed wording verbatim;
  grounding is model-composed, so tagging it would be a provenance lie).
  **Render is unconditional, in both views, via ONE shared helper.** `rendering.grounding_line` feeds
  `_dump_one_perspective` and `inspect_node` for the same reason `build_pp_index` is shared — a grounding visible in
  one view and not the other reads as data loss. Unconditional because the moment it matters is a returning
  session's wobble, when the model does not know it needs to call `inspect_node`: anything lazily loaded is anything
  unread. `_collect_grounding` also gathers the tetrad's own poles' notes and dedups them against the tetrad-level
  one (`commit()` dedup makes one Statement the T- of several perspectives, so pole-level grounding survives reuse
  where a per-perspective note does not — but naive per-position rendering would repeat it down the block).
  **Write path is the `anchor` seam only, and closes a documented lie**: `anchor(context=...)` said "conversational
  context that grounds this tension" while the string reached `IntroducePolarity`, informed
  classification/headlining, and was then discarded. `ExpandPolarity(grounding_context=...)` extracts ONCE per call
  and attaches copies to every tetrad it produced (the particulars describe the situation; each tetrad is a reading
  OF it), before `_validate_and_flag` so a validation blow-up cannot cost an already-committed tetrad its evidence.
  Fail-soft at every step — grounding is enrichment, never a gate; the Analyst path passes no context and is
  byte-for-byte unaffected.
  **`anchor` has TWO branches and only one was wired** (fixed 2026-08-11, before any bench run could be misread as
  measuring the lane): with `antithesis` it calls `ExpandPolarity` directly and grounded correctly; thesis-only
  composes `AnalysisPipeline`, which forwarded nothing — and `context` went in as `intent`, which
  `AnalysisPipeline` reads ONLY on the surface-theses step, so with `thesis_hashes` supplied it was dropped
  outright. One tool, two different memories depending on whether the model happened to name the opposition, with
  nothing in the report distinguishing them. `AnalysisPipeline(grounding_context=...)` now forwards to every
  `_expand_one`. **`ingest` deliberately does NOT set it**: bulk material is one document holding several unrelated
  tensions, and one 60-word extraction stamped onto all of them would cross-contaminate — bulk keeps its
  particulars in the Input digest. Generalises: the existing tests all drove `ExpandPolarity` directly, so they were
  structurally blind to a CALLER that passes nothing. When a lane is optional-by-default, at least one test must
  assert at the caller seam.
  **The whole lane hangs on one prompt line, and this is the third instance of the same lesson.** Everything above
  can be correct and the lane still stays permanently empty, because `context` is optional and neither `_TOOL_DOCS`
  entry mentioned it — a parameter the prompt never asks for is a parameter the model omits. Measured baseline: 11
  live `anchor` calls across six A2 cells, 0 particulars carried. So both `_TOOL_DOCS["anchor"]` and
  `["anchor_scoped"]` now say ALWAYS pass `context` **and what belongs in it** (numbers/dates/splits/named events,
  in the person's own terms, facts-not-reading), with the reason stated rather than just the rule — the tetrad keeps
  a few words per position, so `context` is the only lane the particulars live in. `anchor`'s `Field` description
  carries the same demand, since Mirascope serialises it into the request and a Field still reading "conversational
  context that grounds this tension" would compete with the doc. Same rule as `record_decision` and the `explore`
  threshold: **when a prompt rule governs whether to CALL or PASS something, it belongs in the tool doc too** — but
  note the ranking established by the decision-repair fix: a rule governing whether an observable USER EVENT gets
  persisted belongs in code. This one is not that; what goes in `context` is a judgement about relevance, and there
  is no observable event to classify, so the tool doc is the right layer. Machinery, not method — so `tests/e2e/arms.py`
  correctly does NOT carry it into the A1 baseline (tool docs are absent from `method_prompt`); a prompt-only arm's
  journal is its own equivalent lane.
  **Instruction was not enough either — the fourth instance, and this time the fix is PLACEMENT** (2026-08-12, from
  `claim2-weak-r10`, the first judged run free of confounds). With the read-side instruction live and emphatic, A2
  scored `memory` **1.00** (24/24 of the person's particulars were in the carryover) against `used` **0.04** (1/24
  referenced in a reply) — A1.7's prose journal 0.92 / 0.12. So a graph holding EVERY fact spoke fewer of them than a
  journal holding fewer, which rules out both storage and instruction volume as the cause. What the model was actually
  reading: one `Grounded in:` line per tetrad, buried mid-block behind `insight=`/`HS=`/`Ks=`/`DV=`/`area=`, landing
  anywhere from 14% to 95% of the way through the dump, and repeated across up to 7 near-duplicate lines. `DialecticalContext.
  _dump_case_particulars` now hoists them into a `# The Person's Case` section at the TOP of both dumps (after inputs,
  before decisions), deduped by exact text, oldest-first as a chronology. This is the project's own **"prune, don't
  instruct"** applied to a prompt that had already been written twice: when a section is present, correct, and
  instructed-about and still goes unread, the next move is where it sits, not more words about it. Deliberately KEEPS
  the per-perspective line — the hoisted section answers "what do I know about this person", the in-block line answers
  "what is THIS tension built on", and those are different questions. Near-duplicate wordings are BOTH kept: choosing
  which phrasing of the person's own disclosure to drop is not a renderer's call, and a dropped variant reads as a
  forgotten fact. `_SCORE_READING`'s particulars paragraph names the new header and explains the two placements, so
  the read-side instruction and the render cannot drift. The scoped render fences to nexus members only — same fence
  as the perspectives themselves, since an outside tension appears in counsel mode as a count and hoisting its facts
  would leak around that. Locked by `tests/test_dialectical_context.py::TestCaseParticularsAreHoisted` and
  `TestScopedDumpCarriesTheCase` (incl. the outside-tension leak guard and "assessment prose is never hoisted" —
  hoisting untagged rationales would do the exact opposite of this fix). **Unverified at the behaviour layer**: a
  context change is a claim about the model's reply, and no `used`-rate re-measurement exists yet.
  **The lane silently dropped every RE-anchor, and that is a code defect no prompt altitude could have caught**
  (2026-08-12, from `r13-grounding-attrib`). `_ground_tetrads(completed_pps)` was passed only tetrads this call
  COMMITTED; a tetrad whose generation collapsed onto an existing node hits the `_find_duplicate` branch,
  `discard_uncommitted`, `continue` — and its call's `grounding_context` went with it: no extraction, no
  `Rationale`, no report artifact. But **re-anchoring an existing tension is the ordinary case, not the edge one**:
  the person reveals more in turn 3, so the model anchors the same tension again with richer particulars, and dedup
  is precisely where the richer particulars were thrown away. Measured: a two-turn cell where BOTH `anchor` calls
  carried context (195c, 422c) produced a carryover holding five near-identical restatements of turn ONE and
  nothing whatever from turn two. It contradicted this lane's own docstring contract ("Accretion, not mutation …
  a person reveals more three turns later"). Fix: `_ground_tetrads(completed_pps + dedup_targets)`, safe because
  `Rationale` is content-addressable on `(text, target)`, so re-grounding a node with particulars it already holds
  is idempotent and free. **Two general rules.** First, `completed_pps` is a *creation* record and grounding needs a
  *relevance* record — any lane that enriches "what this call was about" must ask whether dedup targets belong in
  its input set, because a content-addressable graph makes "already exists" the common path, not the rare one.
  Second, this was invisible to review at all three altitudes (the prompt asks correctly, the assembled context
  renders correctly, the chain is coherent) and only surfaced once
  `ConversationFacilitator.last_tool_call_args` could prove the model HAD passed the text — the third link in a
  chain where each observability fix exposed the next defect (RAISED tools → arg recording → dedup path). Locked by
  `tests/test_expand_polarities_grounding.py::TestGroundingAccretesOnDedup` (a second call's context lands on the
  node it deduped onto, both turns present in one accreted line; no-context still means no call on that path).
  **Bounds every earlier grounding measurement**: r10's `memory` 1.00 and r11's 0.65 were taken while a returning
  turn could only re-store what the first turn happened to mention.
  Reviewing here: this prompt is the ONE place in the tree where concreteness beats
  abstraction, so the usual "condense to component_length" instinct is exactly wrong. `GRAPH_SCHEMA`'s EXPLAINS row
  and `docs/graph.md`'s Grounding section document the role vocabulary and must move with it. Locked by
  `tests/test_rationale_grounding_role.py` (edge-role round-trip, default-None for pre-existing callers,
  role-not-hashed so dedup survives), `tests/test_tetrad_grounding.py` (render in both views, assessment prose
  excluded, accretion order, pole dedup, plus `TestPromptTeachesTheReadSide` — the prompt names the marker in
  BOTH scoped and unscoped renders, tells the model to speak the particulars, and exempts them from the
  rephrase licence in whichever `How You Speak` variant renders),
  `tests/test_expand_polarities_grounding.py` (one extraction reused,
  no-context no-op, failure isolation, grounding-before-validation, plus
  `TestAnchorBranchesGroundAlike` — both branches ground, `ingest` still does not), and
  `test_prompt_review_regressions.py::TestAnchorGroundingReachesTheToolDoc` (both docs demand context WITH
  specifics, the reason is stated, the Field agrees). Measured by `tests/e2e/test_e2e.py::TestCarriedParticulars`,
  `TestCarryoverIsRecorded`, `TestParticularsAreWellFormed` (a particular form may not collide with a pole marker, or
  the carry probe and the symmetry share agree by construction) and `TestParticularsReporting` (an unrecorded artifact
  renders `--` and a warning, never a zero — the same absence-is-not-failure rule as `cited_record`).
- **Completeness is derived on read, and its VOICE is set in code** (`rendering.wheel_completeness` /
  `completeness_line`, live since 2026-08-24). Not a gate and deliberately not stored: `expected =
  len(wheel.edges) * len(INSIGHT_CATEGORIES)` (6N), `done` = committed Transformation ROWS per edge
  (`TransformationRepository.count_by_edges`, one query per wheel, `hash IS NOT NULL`) clamped to the
  per-edge share — NOT distinct bands, because band uniqueness is enforced where the write happens
  (`_only_missing` keeps at most one candidate per band), and reading bands here would cost a relationship
  read per Transformation on a path that renders every wheel. So a session that closed mid-`deepen` reports
  `Pathways: 4/6 (incomplete: T1→A2)` on reopen and a second `deepen` tops up exactly the gap. Three prompt-relevant consequences. (1) **The register split is
  `numeric=bool(scoped_nexus_hash)`, not prompt discipline** — `DialecticalContext` is Advisor-only, so
  counsel mode gets digits and the standalone Advisor gets plain words; `_HOW_YOU_SPEAK` says unfinished work
  is spoken plainly and **never with counts** (and not the framework nouns behind them), while
  `_HOW_YOU_SPEAK_SCOPED` says it is stated **with its numbers** because the exploration is the person's own
  deliverable. Both variants must keep the same honesty clause — asked whether it finished, the answer is
  straight. (2) **`_SCORE_READING` must say completeness is not quality.** The dump tells the model it is
  "pre-pruned, rank within it", which invites reading `4/6` as a bad score and quietly demoting a half-built
  wheel; the section now names the `# Unfinished` line and says treat the gap as a to-do, not a demotion.
  This is the same failure family as the quality-floor entry above: a NUMBER rendered without its meaning
  gets read as a rank. (3) A blocked edge is **named**, not silently absent — the skip case was previously
  indistinguishable from a finished edge. Blocked is a property of the PAIR, not the edge: a workable edge
  whose pair partner's segments are unfinished is equally stuck, so it renders under `blocked_edges` and is
  kept out of `incomplete_edges` — nothing invites a `deepen` that cannot help. `ExploreTransformations`
  applies the same rule before Phase 1, so a blocked pair spends no LLM calls, and reports what a top-up
  still could not build as `still_missing`. Partial synthesis is stamped rather
  than blocked (`Synthesis.completeness`, hash-excluded metadata like `Perspective.validation`), because an
  unfinishable edge would otherwise withhold synthesis from that wheel forever; theory entry in
  `docs/theory/transformations-synthesis.md`. The load-bearing subtlety for anyone touching the resume path:
  **a tetrad pairs an edge's Ac+ with the OPPOSITE edge's Ac+ in the same band**, so Phase 1 must extract
  candidates for what EITHER side of the pair owes — an edge whose partner is already complete still runs as
  support. Since the write loop finishes edge A before edge B, "A complete / B partial" is the commonest
  interrupted state, and scoping Phase 1 to the edge's own gap made per-band resume dead in exactly that
  case. Surfaces that render the fraction: `dialectical_context._dump_wheel` and `_dump_synthesis`
  (register-split), `inspect_node` (numeric, plus a "synthesis is stale" flag when the stamp no longer
  matches the wheel), the `deepen`/`explore` tool reports, and the Navigator's exploration view
  (`present_exploration._format_wheels` — `Pathways: 4/6` from counts it already groups, no extra queries).
  Every one of them is decoration: the reads are wrapped fail-soft, so a status failure can never cost a
  synthesis or a deepen its payload. The one NON-prompt surface is `concerns/build_status.py`
  (`BuildStatus` → `CaseStatus`, live since 2026-08-24): the same traversal as `DialecticalContext` minus the
  prose, returning dataclasses so a host app renders status instead of parsing a dump — per-polarity states,
  per-wheel `fraction` with the resumable/blocked split, synthesis stamps + `is_stale`, `shallow_wheel_hashes`,
  and a `resume_hint`. Its judgement calls are prompt-adjacent even though no prompt is involved: **shallow is
  not interrupted** (a 0/6N wheel is the `EXPLORE_DEEP_WHEELS` budget working, so it is never a resume hint —
  offering it would push the argmax arrangement back onto a user whose lived reality picked another),
  **blocked is never offered**, and **unreadable is not finished** (a node whose read fails lands in
  `unreadable_hashes` and keeps `is_complete` False). Wheels come from
  `WheelRepository.find_by_nexus` (Cycle→Wheel across all layers, committed-only, nexus-scoped by perspective
  hashes — the all-layer counterpart to `find_by_layer`). Locked by `tests/test_resume_completeness.py` (taxonomy agreement +
  tie-break, counting, pair-blocked naming and no-waste, register split incl. the `0/N` wording,
  fresh/resume/complete pair drivers, band de-dup at the write site, `still_missing` reporting,
  hash-exclusion, stamp rendering) and `test_prompt_review_regressions.py::TestCompletenessRegisterSplit`.
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
| Round-trip narration (dx:// loop: capture → develop → weave back) | "Inputs from exploration" section (recognize `dx://`, develop, offer `expand_nexus` back to the origin named in the input's digest) | "Feeding Insights Back" section (`create_dx_input` at resonance moments, loop framed as growth not exit) | — (unscoped Advisor has no dx tools) | `orchestrator/tools/create_dx_input.py` — both narrations must describe the SAME loop. Provenance channel: `CreateDxInput` stamps "Origin: insight from exploration [[hash]]" into the Input digest; `present_analysis` Sources section + `inspect_node`'s Transition renderer surface it. If the digest format changes, the Analyst prompt's "Origin: insight from" pointer must change with it. `CreateDxInput` is idempotent: repeat capture of the same transition reuses the existing Input (content-addressable hash) without clobbering a refined digest or duplicating the HAS_INPUT edge. `InputRepository.get_all` carries the committed-only filter (its two new LLM-facing consumers — `present_analysis` Sources + `DialecticalContext` pending list — would otherwise surface uncommitted garbage). Pending-vs-used comes from `InputRepository.analyzed_hashes`, NOT from `input.statements`: an Input reaches its Statements either directly or through `Input-[:DISTILLED_TO]->Ideas-[:HAS_STATEMENT]->`, and extraction writes the latter — both renderers read only the direct edge until 2026-09, so every analyzed Input stayed "Pending (captured, not yet analyzed)" forever and the loop above could never be shown as closed. The reverse traversal (`find_by_statement_hashes`) has the same two paths and the same failure mode: `CausalityEstimatorBalanced._get_source_text` silently grounded causality in `""`. Any new reader of the Input↔Statement link takes the union. |
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
Navigator-territory precision rule (exact statement text when citing by hash) and permits **completeness
with its numbers** where the unscoped variant forbids counts (see the completeness entry in §4 — the split
is code-driven, so the two variants must stay opposite deliberately, not accidentally). Handover
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
  intent-driven build_wheels); **`TestCompletenessRegisterSplit`** — plain words unscoped / numbers scoped,
  plus the "completeness is not quality" rule in both; **`TestNavigatorRoundTrip`** — both prompts narrate the dx:// loop, the
  Explorer carries `create_dx_input`, the dead off-ramp phrasing is gone; **`TestExplorerAdvisorToggleNarration`** —
  both heads surface the handover signal without auto-switching.
- **`tests/test_resume_completeness.py`** (no LLM, DB-free) — the pause/status/resume net: the
  insight-band helpers agree with `INSIGHT_CATEGORIES` for every `INSIGHT_SCALE` label (and ties snap down,
  so 0.55 stays Configurational), `wheel_completeness` counts and names incomplete/blocked edges with
  blocked scoped to the PAIR, `_process_edge_pair` builds every band fresh / tops up exactly the gap on
  resume / leaves a complete pair alone / spends nothing on a blocked pair and reports `still_missing` when
  a top-up falls short, `_only_missing` keeps one candidate per band, `Synthesis.completeness` stays out of
  the hash, and the status line reaches `dialectical_context`, `inspect_node` and the exploration view. Drives the real code with fakes
  (`find_by_edge`, `format_edge_label`, `RelationshipManager.__get__` monkeypatched) rather than a graph —
  the defects live in counting and composition, not in the DB or the LLM.
- **`tests/test_resume_real_llm.py`** (1 test, `--real-llm`) — the resume claim on a real provider, which
  is the only place it is measurable: the mock brain returns the same DTO every call, so all three insight
  bands collapse into one and the interesting interrupted states cannot occur. Caps
  `_create_transformation` after 4 of 6 writes (the exact defect site — tetrads generate concurrently but
  write sequentially, and GQLAlchemy autocommits per node), then resumes through `run_deepen` on a FRESH
  skill instance: the graph is the only carrier of resume state. Measured 2026-08-24 on haiku-4.5: the kill
  left 4/6 with the pair top-up-able, Phase 1 then asked for exactly `[Configurational, Corrective]`
  (`candidate_count: 2`), `existing_count: 4` (survivors reused, not rebuilt), `resumed_categories` named
  the part-built edge, and the wheel closed at 6/6 with three distinct bands per edge and a `6/6` synthesis
  stamp. This is also the only live proof of the pair-scoping: the complete edge ran as SUPPORT so its
  partner's top-up had an Ac+ to pair with.
- **`tests/test_build_status.py`** (15 tests, no LLM, DB-free) — the typed status read a host app calls
  instead of parsing a dump: the four wheel states told apart (complete / interrupted / shallow / blocked),
  the resume hint naming the interrupted wheel and never the shallow one, closest-to-finishing with a hash
  tiebreak so two reads of one graph agree, a blocked wheel never offered even when it is half-built,
  `is_complete` ignoring shallow wheels and set-aside polarities but NOT unreadable nodes, stale-vs-current
  vs unstamped syntheses, and a failed read landing in `unreadable_hashes` rather than vanishing. Runs the
  real `wheel_completeness`/`polarity_completeness` with the repository reads faked — the judgement under
  test is the state machine on top of them.
- **`tests/test_build_status_graph.py`** (3 tests, no LLM, live Memgraph) — the half the fakes cannot cover:
  `WheelRepository.find_by_nexus` returns every wheel with its parent cycle, another nexus's wheels stay out
  (the scoping predicate), and a structure-only exploration reads as `0/6N` shallow with no resume hint.
- **`tests/test_prompt_vocabulary.py`** (1 test, `--real-llm`) — behavioral: a live Analyst response never
  labels T-/T+ as "blindspot." NAVIGATOR_APP + Analyst only. Skipped in the default suite.
- **`tests/test_relationship_read_id_recovery.py`** (11 tests, no LLM) — the graph-read seam beneath the
  analysis chain: a relationship read must not answer "no edges" for a node it merely failed to locate.
  Covers recovery-by-hash for `count()`/`all()`/`Perspective.t`/`.a`/`is_complete()`, id caching, the WARNING
  log, the still-legitimate silent empty read for an unsaved node, the pre-commit `save()`→connect build path
  (where `_id` is the only identity), and the `_id`/`hash`/`sid` identity in both T and A error messages.

### A guard in a `probe_*.py` file is not in the net at all

Sibling of the `real_llm` hazard below, and quieter, because nothing even reports a skip. Pytest's
default `python_files = test_*.py` means **no `probe_*.py` file is collected by `poetry run pytest`**
— its free guards run only when someone names the file on the command line. `pytest tests/e2e
--collect-only | grep -c probe_option_pair` returned **0** while the same file reported "11 passed"
when invoked directly, and the README had already been written claiming those guards "pin" the
probe's numbers. They pinned nothing on any run anyone would actually do.

Fix, and the convention for this lane: **subclass the probe's guard class inside `test_e2e.py`**
(`TestOptionPairProbeGuardsRunInTheDefaultSuite`) so pytest re-collects the inherited methods.
Inherit, never copy — a duplicated set of assertions drifts from the probe whose numbers it exists to
protect. Check any new probe the same way, with `--collect-only | grep`, and note that
`pytest <file>` passing tells you nothing about whether the suite runs it.

### A `real_llm`-marked test can be broken for months and look green

`tests/test_aspect_axis_real_llm.py` carries a module-level `pytestmark =
[pytest.mark.real_llm, pytest.mark.llm]`, so the default suite reports it as **skipped**, not failed.
It was failing on **every** pair — `ValueError: Parent meaning 'tree' has no known taxonomy branch` —
and had been since the apex lookup started raising instead of falling back to the generic Apex row.
Nothing surfaced it because nobody ran `--real-llm` on that file.

The break was in the FIXTURE, not the framework: it built statements with `meaning=t_text.lower()`.
That cannot work, and the reason generalises to any test that constructs a Polarity by hand —

> `AspectGeneration._tetrad_prompt` interpolates `StatementClassification.lookup_aspect_apex(parent,
> position)` for all four positions, and that lookup **raises** on a meaning that does not parse to a
> known taxonomy branch. A hand-written meaning therefore fails *in the prompt builder, before the
> provider is called* — so the failure looks like a fixture error, not a prompt result.

Two consequences worth carrying:
- **Classify both poles through the real `StatementClassification`** (as `anchor`'s
  `IntroducePolarity._classify_statement` does), never a hand-picked branch. The branch **selects the
  apex row the prompt teaches from**, so choosing it by hand silently changes the prompt under test.
  Classification is role-independent, which is what lets one classification per distinct text be
  reused across a T/A swap.
- CLAUDE.md's "`meaning="test"` is fine only on paths that never reach taxonomy lookups" has a sharp
  edge: **tetrad generation is such a path**, and it reaches it before the LLM call.

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
