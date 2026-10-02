# Advisor seams: tools, modes, the closing weave, the feasibility audit, the leak

<!-- Vocabulary moved on 2026-09-18, after these notes were written: "counsel mode" /
"counsel register" / "counsel toggle" is now the ADVISORY mode / register / toggle
(`NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER`), and `Advisor(read_only=True)` became
`Advisor(mode=AdvisorMode.VIEW)`, with a new `AdvisorMode.CONSULTANT` between it and FULL
(`agents/advisor/mode.py`). On 2026-09-26 that one axis became two parameters,
`Advisor(build=BuildPolicy.ON_ELECTION|ON_CONSENT|NEVER, records=True|False)`
(`agents/advisor/build_policy.py`, no alias): FULL = `ON_ELECTION`, CONSULTANT = `NEVER` ("the sealed Advisor" since 2026-09-28,
when `Consultant` became the name of the tool-less one-off agent, `agents/consultant/`),
VIEW = `NEVER, records=False`; see "The build policy" at the end of this note. The reasoning
below is unchanged; read the old names as the new. -->

<!-- Moved verbatim out of CLAUDE.md on 2026-09-18. This is lab-notebook material:
the reasoning behind a change, the measurements that justified it, and the traps hit
on the way. Figures are as-of the run that produced them; re-derive with the named
probe before quoting one. The rules distilled from these notes live in CLAUDE.md. -->

## Tool constraints, as written

Advisor has `discard` but NO edit tool — re-framing means discard + `anchor` the new version. On user rejection: unscoped Advisor discards silently; advisory-mode (nexus-pinned) head confirms first for exploration members (consent contract), fresh own anchors need no ceremony. To drop a claim: discard the perspective, then its statement (one still used by a live perspective won't discard; discarding a perspective never cascades to shared statements). Tools split by what the LLM knows at call time:

- `ingest` — bulk discovery from material → standalone perspectives (composes AnalysisPipeline)

- `anchor` — plant a specific T/A tension → standalone perspective (IntroducePolarity + ExpandPolarity)

- `explore` — group perspectives into nexus + pathways + synthesis (CreateNexus/ExpandNexus + ExplorationPipeline + GenerateSynthesis). LAZY: builds+ranks ALL wheels, deep-generates only the top (`EXPLORE_DEEP_WHEELS = 1`) **plus the coarser ancestry it refines from** (`EXPLORE_REFINE_FROM_COARSER = True`), coarsest rung first; rest reported as `shallow_wheel_hashes`. The climb is not a depth dial: without it `find_parent_transformations` has no parents to return, so the deepest wheel is the one generated with no refinement context (0 of 8 lookups at k=4, against 18 of 20 with it — `tests/probe_transformation_recursion.py`). Costs 1.5× the calls of a run, ~5% off-provider wall clock. Weaves ≤ `advisor_max_perspectives_per_exploration` per call (excess deferred).

- `deepen` — develop a shallow wheel on demand (ExploreTransformations + GenerateSynthesis, synthesis always). The escape from explore's budget when the user's lived reality picks a non-top arrangement. Scoped variant guards wheel-membership in code.

- `audit_feasibility` — score named pathways for practical achievability on demand (TransformationAudit, the concern `explore` no longer runs eagerly). Takes `transformation_hashes` (the `[[hash]]` on every pathway line), audits Ac+/Re+, renders band + factors + success conditions read back from the graph. Idempotent: an already-estimated pathway is returned free, because re-auditing accumulates critique Rationales that disagree while `upsert_estimation` keeps only one score. Capped at `MAX_TRANSFORMATIONS_PER_CALL = 4` with the excess named as `deferred` (2 calls per pathway — an unbounded list re-spends the whole eager audit). Shared by both agents (`orchestrator/tools/`); scoped variant guards nexus-membership in code.

- `record_decision` — persist an explicitly confirmed decision (RecordDecision + fail-soft DecisionCoherenceCheck). Consent-first in BOTH modes — the one exception to silent machinery; the `_DECISION_READINESS` engine section renders only when wired

- `sync` — re-read graph state (DialecticalContext); optional `nexus_hash` zooms into one exploration in full depth (no wheel cap — same exemption as advisory-mode dumps)

- `discard`, `inspect_node`, `read_digest` — graph curation and detail reads (shared orchestrator tools)

## Explorer: lazy by toolset, and the deleted `explore` tool

- **Explorer** = everything after nexus (nexus-scoped: cycles → wheels → transformations → synthesis). Constructed with `nexus_hash`. Carries `create_dx_input` to START the round-trip: capture a Transition insight as a dx:// Case Input → Analyst develops it → `expand_nexus` weaves back. **Its depth is LAZY by toolset, not by cap:** it gets `build_wheels` (structural, ALL wheels — cheap) and `explore_transformations` (the one wheel the user picked), so it never runs `ExplorationPipeline` at all. `ExplorationPipeline(max_deep_wheels=None)` deepens EVERY wheel and the wheel count is combinatorial; that default is a headless batch default, and headless callers bound k instead (`test_agents_e2e.py`). An uncapped `@llm.tool explore` did sit at the bottom of `explorer/explorer.py` in NO toolset, reading as live only because `test_tool_signatures.py` listed it among the framework's tools — deleted 2026-09-10, comment left in its place. Priced first (`tests/probe_explore_deep_wheels.py`, LLM mocked): at k=2 uncapped asks **100** formatted calls against the Advisor cap's **36**, of which only 4 build wheels — the rest is per-wheel deepening. **The "edge-pair reuse saves ~30%" once written here is WRONG and the mechanism does not exist: cross-wheel reuse is structurally ZERO.** `Transition`'s hash includes a `uuid4` nonce (`graph/nodes/transition.py`) so every wheel commits its own fresh Transitions, and `TransformationRepository.find_by_edge` matches `id(t) = $edge_id` — an internal node id — so no wheel can ever see another's Transformations. What actually explains 100 rather than 4x the top wheel's cost is a SIZE effect: at k=2 two of the four wheels are layer-1 (N=1) and cost half of a layer-2 one, since every per-wheel figure scales in 2N edges. **The consequence for scoping: deepening a second arrangement costs the full price of deepening it, i.e. exactly what electing `deepen` on it costs, so widening `EXPLORE_DEEP_WHEELS` buys no efficiency over the on-demand tool — only pre-payment.** At k=4 (96 wheels) the uncapped run had **not returned after 41 minutes with a zero-latency model**, so its ceiling is graph work before any provider time is added. Two transferable parts: **a tool nobody registered is still a trap while a test lists it among the real ones**; and a docstring that explains a default by naming a path the code does not take ("the Explorer agent's path ... is already lazy and never sets this") is right about the behaviour and useless as a guard — check the toolset, not the prose. Counting calls under mock brain needs its own instrument: `utils/call_census.py` reads ZERO there, because `record_call` lives inside the real `use_brain` the mock replaces, so the probe wraps `mock_brain.build_mock_response` instead.

## Advisor, read-only, apps, advisory mode

- **Advisor** = pure-conversation agent, framework runs silently (no terminology exposed). Composes both pipelines via `ingest`, `anchor`, `explore`, `deepen`, `sync` (+ shared `inspect_node`, `read_digest`, `discard`, `audit_feasibility`). System prompt is a FUNCTION `system_prompt(tool_names, scoped_nexus_hash)` — tool docs render only for wired tools. **It has THREE render shapes, not two, and the third is derived rather than passed: `read_only = not (set(names) & _WRITE_TOOL_NAMES)`.** See `read_only=` below.

- **Advisor(read_only=True)** = the reading surface: `sync` + `inspect_node` + `read_digest`, and no write tool BUILT at all — for a second reader on someone else's Case, a shared/public view, a support seat, or counsel without write access. Composes with `nexus_hash=`. **Enforced in exactly two places and nowhere else: the TOOLSET, and the closing seam declining** (`_repair_unrecorded_decision` returns before the classifier is asked, so both `TurnTiming` outcome fields stay `None` — a third way into that `None`, deliberately given no `ClosingOutcome` member, because reading it as `NO_CLOSING` would turn "nobody asked" into "the answer was no"). Never by prompt: the prompt's job is only to stop the head spending turns reaching for what it does not have, which is the nexus pin's division of labour. **`audit_feasibility` and `discard` are WRITES** — the first spends 2 provider calls writing a FeasibilityEstimation plus a critique Rationale, the second soft-marks a node out of every active query. **`_settle_deferred_work` and `_refresh_context` still run**, and a "read-only means do nothing" edit that takes them is the failure mode to watch: settling honours ONE WRITER PER SID (reading a half-woven graph is worse than reading a shallow one) and the refresh is a read. What it COSTS, which a host must be told rather than discover: a person who states a decision here gets **no record** (the seam switched off is the one that catches the model not calling `record_decision` — 0/6 at the weak tier), and the graph never deepens. `principal` is accepted and ignored (nothing is recorded, so nothing is attested — unlike `advanced`, ignoring it changes nothing a person can see, so it does not raise); **`app_tools` are still merged, deliberately** — the framework cannot tell a host's chart lookup from a host's write, so this flag governs the FRAMEWORK's surface and the host owns its own, and refusing them would push those apps onto `app_preamble=`, the trap `advanced` fell into. The prompt side is the part that does NOT follow the toolset for free: gating the tools gates the tool DOCS and two name-gated sections, while `_EAGER`, `_CONVERSATION_USE`, `_REJECTION_HANDLING*`, `_DEFAULT_ARC`, `_TOOLS_INTRO_SCOPED` and `_SCORE_READING` all still instruct absent tools. Fixed with three small forks mirroring the existing `*_SCOPED` ones, two literal heading swaps in `_CONVERSATION_USE`, dropping `_DEFAULT_ARC` (already dropped when scoped — the arc IS the building sequence), and ONE new `_READ_ONLY_MANDATE` placed LAST among the instruction sections so later-sections-win overrides what `_SCORE_READING` and `_CONVERSATION_USE` still say — deliberately NOT forking those two, whose tool references sit mid-paragraph inside reasoning about what the scores mean, which is where prompt drift lives. Tests: `tests/test_advisor_read_only.py` (22, five mutations verified), whose `TestTheTwoListsAreOne` is the only thing holding `_WRITE_TOOL_NAMES` and `_build_read_only_tools` together — drift gives a head that holds a write tool while being told it has none, or a full Advisor whose own prompt renders as read-only.

- **Apps plug in via `app=`** (an `AppSpec`, `agents/app_spec.py`) — pieces `voicing`/`advisor_persona`/`tool_guide`/`tools`; each head composes its own preamble (Analyst/Explorer: NAVIGATOR_APP+voicing+tool_guide; advisory toggle: NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER+…; standalone Advisor: advisor_persona+tool_guide). ONE AppSpec per app, passed to EVERY head (toggle shares literal history; Analyst owes parity). **`advanced=` on the head constructor is the expert register, and it is a per-SESSION property of the person, not an AppSpec field** — one spec serves both registers, so pass the SAME flag to every head the person is looking at and the level CARRIES across the Explorer↔advisory toggle instead of resetting mid-conversation. It raises rather than being ignored wherever no AppSpec composes the preamble (standalone Advisor; any `app is None` case). Ignoring it is the defect it was added to fix: until 2026-09-16 `advanced` existed only on `AppSpec.navigator_preamble()`, `resolve_app_layer` called that with no argument, and the expert register was UNREACHABLE for every app using `app=` while a unit test on the parameter stayed green — and the escape hatch the code recommended (`app_preamble=my_app.navigator_preamble(advanced=True)`) forced dropping `app=`, which silently unwired `app_tools` too. Manual layer: `app_preamble=`/`app_tools=` (replaces AppSpec composition; mixing with `app=` raises). Tools merge via `agents/toolsets.py::merge_app_tools` (append; shadowing a built-in raises; system prompts skip unknown names).

- **Advisor(nexus_hash=...)** = advisory mode of the Explorer↔Advisor session toggle (NOT standalone): host hands `messages` + `nexus_hash` between heads; preamble pairing `NAVIGATOR_APP_ADVANCED_TOGGLE` ↔ `NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER` (both on `NAVIGATOR_APP`) — or, under `advanced=True`, `NAVIGATOR_APP_ADVANCED_TOGGLE` ↔ `NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER_ADVANCED` (both on `NAVIGATOR_APP_ADVANCED_TOGGLE`). The two counsel registers share ONE body (`_ADVISORY_REGISTER`) so they cannot drift, and the advanced one appends a trailer that must stay LAST: the body was written for the non-expert default (contextual vocabulary, meaning first, "Nexus" stays internal) and later sections win, so without the trailer the advanced pairing would re-lock the register a host just unlocked. Nexus pin enforced by tool closures (`advisor/tools/scoped.py`), not prompt. **The pin protects other EXPLORATIONS, not everything outside the pinned one:** members of other nexuses are refused by the tool guards and reduced to a count line in the dump, while a perspective attached to no exploration (which is what `anchor` plants in advisory mode, until `explore` weaves it in) is fully readable and writable from here. Both halves must say the same thing — the render enforced the stricter rule until 2026-09-15 while `discard` and `explore` already used the looser one, so the head could act on its own anchor only by remembering the hash from an earlier tool result. See `docs/agents.md` Handoffs.

## The silent-framework contract measurably leaks

- **"Framework runs silently" is a PROMPT ASPIRATION that measurably fails in about 1 reply in 20, and only `_HOW_YOU_SPEAK` defends it.** Archive-wide (`tests/e2e/probe_leak_shape.py`, 438 A2 sessions / 1645 non-empty replies, recounted 2026-09-17): **85 replies leak (5.2%)**, 72 of them unambiguously (4.4%), across 70 sessions and 126 snippets. It is NOT caused by any of the latency work: the rate is the same with the extraction round restored, and the two configurations merely leak different vocabulary (with reuse the reply reads the dump aloud; without it, it narrates its method). So treat leakage as an open prompt-level defect, not a regression to bisect, and never assert the silent contract from the fact that the prompt states it — the regression tests that check the prompt says so are the trap this finding walked into. `score_machinery_leak` is the endpoint; `read_reply_hygiene.py` re-runs it over any archived stem for free, and `probe_leak_shape.py` groups the hits by shape.

- **The leak is machinery-as-actor and bare position labels; it is not vocabulary.** Of the 126 archived snippets: **NARRATED 59 (47%)** — "the framework found five genuine oppositions", "the system flagged", "the record says"; **LABEL 38 (30%)** — a bare `T+`/`A-`/`S-` in the prose; BARE TERM 29 (23%); ECHOED 1. The unambiguous jargon barely appears at all (`nexus` 1, `wheel` 1, `polarity` 0, `tetrad` 0, `dialectic` 0), so a fix that adds banned words to the prompt is aimed at the wrong 2%. Both real shapes are already banned by worked example in `_HOW_YOU_SPEAK`, which makes this a COMPLIANCE failure, not a missing rule. Two obvious levers are unavailable: `_dump_one_perspective` renders `T{idx}+ [[hash]]` and those labels/hashes are load-bearing for `record_decision`'s `accepted_cost` ground (see its warning comment), and a post-hoc rewrite pass would work on `chat()` and be structurally impossible on `chat_stream()`, making the two entry points diverge on a PRODUCT claim.

- **Do not compare any machinery-leak figure across 2026-09-17.** `score_machinery_leak` was inflated and its own comment was false: it claimed to be "verbatim from `_HOW_YOU_SPEAK`" while carrying three phrases no prompt bans — `accepted cost` (51 of the old 181 snippets, and `rounds.md` had already recorded that a decision record legitimately names it), `adopted pathway`, and a bare `the framework` (56, mixed: "the framework found five oppositions" is a leak, "help you build the framework" is English). It also matched substrings, so **"synthesis" counted as "thesis"**, and used `lowered.find(term)`, so a reply that said `nexus` four times counted once. Corrected: word-bounded terms with explicit inflections, `the framework` only in the actor form (`_MACHINERY_ACTOR`), all occurrences counted, and `tetrad`/`dialectic` added to the PROMPT rather than dropped from the scorer so the "verbatim" claim is now true. Measured effect over the same archive: **8.4% → 5.2% of replies** (139 → 85), 112 → 70 sessions, 181 → 126 snippets. The old "1 turn in 6" came from a 40-reply targeted probe read as if it were the archive rate.

- **`score_machinery_leak` is the contract; `score_machinery_leak_unambiguous` is the evidence.** Four banned terms are also ordinary advisory English — `perspective` ("from my perspective", 14/14 archived hits), `transformation` ("a digital transformation"), `wheel` ("reinventing the wheel"), `thesis` ("your buyout thesis"). They stay in the contract score because the prompt bans them by name and softening a contract is not a scorer's job, but a leak count made mostly of them measures vocabulary rather than disclosure. Print both or neither; one alone is a claim about the other.

## `audit_transformations` and the feasibility audit mode

**`audit_transformations` (False)** — a non-`advisor_*` behavioural knob (there are three now: this, `automatic_feasibility_audit` below, and `extraction_step2_carries_source` in the extraction section above), and it applies to BOTH agent paths. Off means the EAGER pass never runs, so an exploration writes no `FeasibilityEstimation` and no CRITIQUES Rationale of its own. **Two paths audit regardless of it, and always have:** the `audit_feasibility` tool (whose own description is what this flag points at — "agents reach the same concern on demand"), and the deferred closing drain, which scores the ONE pathway a recorded decision is grounded on (`Advisor._audit_adopted_pathways` — 2 provider calls per closing, not 2 × 6N, and through the tool body so it inherits the idempotent skip, the cap and the shared label). So this knob bounds the eager pass, never the concern. **The drain's own route has its own knob since 2026-09-14: `automatic_feasibility_audit`, default OFF (manual) since 2026-09-15, and it is a MODE rather than an off switch** — manual leaves the `audit_feasibility` tool wired, so no configuration exists in which a person cannot ask what a recipe costs; what it chooses is who initiates, since under election alone the band effectively does not exist (the model elected the tool 1/6 in `a15-floor` and 0/6 in `weave-offturn`). `feasibility-offturn` priced automatic mode: the band reached **5 of 5** records that ground a pathway against a 0/6 baseline (Fisher p=0.0152), at **+46% A2 cell wall** (701.0s vs 479.1s) and one turn in 48 where the person waited **284.5s** — 95% of that turn's reply path, failing that round's ≤5s tail bar by 57×. And the seam it was aimed at **did not move** (wobble discrimination 1/3 pairs before and after). So the band is produced, rendered into the prompt every turn, and so far unread. **The default is MANUAL since 2026-09-15, and the elective route was repaired in the same change rather than left to chance** — automatic had survived only because flipping it would have un-measured the round that priced it, which is a research reason and expires when the build ships. What made manual untrustworthy was the 1/6-then-0/6 election rate, and **that rate had a cause other than model reluctance**: the engine prompt named ONE affirmative moment for the tool (the person asks) against THREE prohibitions written to stop the eager spend, so suppression won. The prompt now names the two moments automatic mode was silently covering — **the closing**, on the ONE pathway about to be recorded as the recipe, and **the wobble**, when what resurfaced is whether that recipe can still be carried out (which also closes the re-audit instruction's never mentioning feasibility, recorded as open by the render round). Same scope, same ~2 calls, asked for on the turn it is needed. Two guards are the point rather than trimmings: **the closing moment is never a gate** — "write this down" IS the confirmation and the record obeys it in the same turn, so the passage says three times that the audit does not delay the record — and **rule 3's ban now has an object**, "auditing a MENU, not auditing at all", because that sentence and the one that produced 0/6 are one careless edit apart. Both passages are module constants gated on `"audit_feasibility" in names`, since `_DECISION_READINESS` renders on `record_decision` alone and a scoped session can wire one without the other. Whether the repair lands is the next round's measurement, not a claim here. Tests: `TestTheFeasibilityAuditIsAMode`, `test_prompt_review_regressions.py::TestTheElectiveRouteNamesItsMoments`. Safe to leave off and safe to turn on: nothing in the code branches on either artifact (the score renders where present, is omitted where absent; the critique Rationale has no reader in the tree), and no resume/completeness/status accounting counts an unaudited Transformation as owing anything — **an unaudited wheel is finished, not partial**. It is off because it was 2 provider calls per Transformation = 40% of `explore`'s entire provider spend (`probe_explore_cost.py`) for an annotation. What off costs is one ranking input: both agents' prompts say "prefer high-feasibility + low-to-moderate insight first", and both now state that a missing band means *not estimated*, never *low* — required regardless of this knob, since only Ac+/Re+ are ever audited and Ac-/Re- have never carried a band. Tests: `tests/test_transformation_audit_optional.py`.

## The closing weave runs off the turn

**The closing weave runs OFF the turn, and the cap does not bound it.** A decision closes on pathways, not on tensions alone (`_DECISION_READINESS`), and the model does not comply: `explore` fires in 6/55 weak-tier runs against 17/25 strong, and in `a15-floor`'s six A2 cells the election rates were `anchor` 6/6, `explore` 2/6, `audit_feasibility` 1/6, `deepen` 0/6, and the perspective cap's own "weave the deferred ones in a follow-up call" **0**. The model reliably does the cheap first step and reliably skips every deepening one, so a repair delegated to a model-elected tool is a repair that does not happen. What it costs is measured: judged mean −0.25 with a woven graph at closing against −0.69 without (36 scores each, `claim2-weak-r15-voice`), reproduced in `a15-floor` as +0.74 vs −0.32 structural against A1. So `Advisor._schedule_pathway_construction` STARTS the weave rather than advertising it — `asyncio.create_task` inside the turn's scope, which inherits the `sid` ContextVar because task creation snapshots the context. Grounding a decision afterwards is legal because **GROUNDED_IN is analytical**: `Decision`'s own docstring shows `commit()` preceding `grounds.connect(...)`, so the record is written on the turn and grounded on the pathway when it lands (by captured HASH, never by `last_tool_results`, which is per-turn state the weave outlives). Three bounds, each mutation-verified: single flight via the task reference (decisions closed mid-weave queue where the running task re-reads them, so the seam cannot race itself), `_MAX_WEAVE_ROUNDS = 4`, and a no-progress check so a graph the pipeline declines costs one round instead of spinning. **The task and that queue are keyed by SID, in the module-level `_DEFERRED_WORK`, not held on the Advisor** — because the framework documents `Advisor(messages=saved)` as how a conversation is carried forward, which is what a stateless host does (one instance per request), and per-instance state defeated both bounds on exactly that shape: instance N+1 saw no task, so it settled nothing at the top of its turn AND its own closing started a second weave on the same sid. The queue had to move WITH the task, not merely alongside it: `JOINED` rests on "the running task re-reads the queue", so a sid-keyed task over a per-instance queue reports JOINED and then drains a list the decision was never in — mutation-verified to lose the ground silently, which is worse than the race it replaces. Entries retire when their work ends (swept on access, so one entry per sid *currently weaving*), a live task from a dead event loop is discarded with a warning rather than awaited into "attached to a different loop", and the one accepted limit is stated rather than engineered around: the running task weaves under the nexus pin of the instance that created it, reachable only if two turns on one sid OVERLAP, which is the contract violation the seam exists because of. The loop is what drains `advisor_max_perspectives_per_exploration` — that cap bounds a CALL and there is no turn here, so each call still weaves ≤2 and the loop keeps calling; the cap is honoured, not bypassed. **Two obligations this creates.** `chat`/`chat_stream` wait for an in-flight weave before starting, because ONE WRITER PER SID is a hard contract not enforced in code; that wait is normally 0.0 (think-time absorbs it) and is recorded as `TurnTiming.deferred_wait_s`, a COMPONENT of `reply_path_s` and never a third addend. And `wait_for_deferred_work(timeout=None)` is a documented HOST obligation for shutdown, the same shape as the `aclosing` one — it drains by sid (so a resumed instance can drain what an earlier one started), and its optional timeout bounds the WAIT without cancelling the work, because whether a half-woven graph beats an unfinished one is the host's call and a `timeout=` argument is not that decision; `asyncio.wait` rather than `wait_for` for exactly that reason. The turn-top settle stays deliberately unbounded: it protects a correctness invariant, so a timeout there would trade duplicate nodes for latency — which is what keeps this from being "a queue nothing drains": the deferral starts its own consumer and the bench drains it at cell end (`AdvisorArm.finish`, called before `_read_decisions`/`_graph_summary`, or the measurement lands on the pre-weave graph). **The drain has a second half, added 2026-09-14, and it repays the SECOND of the three audited latency-for-reasoning trades:** after every waiting decision is grounded, `_audit_adopted_pathways` scores the feasibility of the pathway each closing actually adopted — read from the GROUNDS edge (`role == "adopted_pathway"`), never from what the weave returned, because the weave knows what it built and the edge knows what the record rests on. It runs after the WHOLE drain rather than inside the loop, so the weave never queues behind an annotation and a task cancelled at shutdown loses the cheaper half; that is why a failing weave `break`s instead of returning — a decision grounded in an earlier round still has a recipe worth scoring. Deduped per pathway, fail-soft, and the reason the scope is ONE pathway is that unlike the weave this trade was a COST trade (40% of `explore`'s provider spend), so moving it off the turn removes the wait and not the spend. **A decision rests on FOUR things and this seam grounded three of them until 2026-09-18** — the price (`accepted_cost`), the tension (a plain ground on the Perspective), the recipe (`adopted_pathway`) and the ARRANGEMENT the recipe is one step of, which was reachable and never grounded. `_adopted_pathway_grounds` now returns the Transformation AND its Wheel, the Wheel as a PLAIN ground by `GroundedInRelationship`'s own rule (a role exists iff a consumer branches on it, and `rendering.decision_ground_line` already selects `format_spiral` from the node TYPE) — so `DECISION_GROUND_ROLES` still holds exactly two entries. **The case for the edge is that a prompt cannot traverse:** `Transformation.get_wheel()` is one hop, but the consumer is `DialecticalContext._dump_decisions` re-rendered every turn, so ungrounded the re-audit could name the step and not the circle it closes. Safe by frame-neutrality rather than by measurement — `_perspective_frame` resolves Transformation and Wheel identically to the owning Nexus and `_ground_set_inconsistency` checks only ROLED grounds against the union of the OTHERS' frames, so adding the pathway's own wheel cannot move that union and no previously-recordable set starts refusing. **The reasoning change is in the read that feeds it:** `_existing_pathway_hashes` returned every developed wheel's transformations and the seam grounded `pathway_hashes[0]`, which its own comment called "the floor, not the ceiling" — arbitrary-but-stable is defensible for a recipe and not for an arrangement, since `EXPLORE_REFINE_FROM_COARSER` guarantees several developed wheels per nexus and a lexicographic pick can land on a rung built only as refinement CONTEXT. It now ranks by `_select_deep_wheels`' own rule (deepest layer, then highest causality P) reusing `explorer.py`'s module-level `_causality_probability`, reading layer as `len(cycle.perspective_hashes)` — what `find_developed_by_nexus` already orders on — rather than `Wheel._perspectives`, which would read `Wheel.edges`. The arrangement write sits BELOW the pathway write over one pre-read ground set, so it can never cost the record its recipe, and it is read off the pathway actually RECORDED, not off the candidates. The bench is blind to it (`E2EDriver._read_decisions` branches on the two roles only), so no archived figure moves and none needs re-reading. Pinned by `TestTheArrangementIsGroundedToo`, `TestTheArrangementLookup`, `TestTheGroundedArrangementIsTheBestRankedOne`, plus `tests/test_pathways_seam_real_llm.py` as the ONLY place the `Transformation`→`Wheel` walk runs on a real graph (every DB-free test stubs `_arrangement_of`, and the lookup is fail-soft, so a broken traversal drops the arrangement silently). Tests: `TestDeferredPathwayConstruction`, `TestOneWriterPerSidSurvivesAFreshAdvisor` (two Advisors on one sid: no second weave, the joined decision still grounded, another sid not made to wait, draining after the scope closed, the timeout that does not cancel, and the registry not outliving the work), `TestTheAdoptedRecipeIsScored`, `TestTheAdoptedPathwayIsReadFromTheEdge`, `TestBothClosingBranchesDefer` (the two closing branches split 50/48 across the archive, so wiring one would miss half the closings), `TestTheDeferredWaitIsOnTheReplyPath`.

## Decision provenance

Only `Rationale.agent` tracks generating model (`<provider>/<model>`, auto-filled from settings; sentinel `"human"` = user-confirmed content, e.g. a Decision's rationale). Other nodes trace provenance through their Rationale — intentional, don't "fix" by adding `agent` elsewhere. **`"human"` is never a DEFAULT anywhere, and that is a rule about this field rather than a preference:** it means a person read the wording back and said yes, and both renderers then present such a rationale as that person's own unattributed "Why", so a default would be the framework making a claim about who was in the room. `Advisor(principal=...)`/`RecordDecision.resolve(principal=...)` default to `UNATTESTED_PRINCIPAL = "agent:unattested"` (`concerns/record_decision.py`); a host with a real person on the other end must pass `"human"` explicitly, and an automated one passes `"agent:<name>"`. The value is in the `agent:` family because the ledger renders NOTHING for an `agent` outside `human`/`agent:*` — a neutral placeholder would delete the recorded why from the Advisor's own prompt — and it is deliberately ugly so "confirmed by agent:unattested" reads as the contradiction it is. See the systemic map's Decision-provenance section for the census that ruled out making the argument required.

## The pinned Advisor that keeps its persona (`persona=True`, 2026-09-21)

The pin (`nexus_hash=`) used to select the Navigator's advisory register unconditionally,
because the only pinned Advisor anyone had built was the Explorer toggle. The owner's
category map exposed the shape that breaks: a mediator's client starts in `Advisor(app=)`,
the framework builds a nexus silently, and the natural next step is to pin the later
sessions to that exploration — at which point the head flipped into a register that says
"you built this in the interactive analysis tools" and grants terminology disclosure, to a
person who has never seen the machinery. So `AppSpec.advisor_preamble(scoped=True,
persona=True)` composes `advisor_persona + tool_guide` (byte-identical to the unscoped
preamble, which is the point: one voice across the collapse), and the Advisor takes
`persona=` as a per-session flag with the `advanced` rules — raises with no `app=`
(`_PERSONA_WITHOUT_SPEC`), excludes `advanced` (a persona has nothing to unlock), and is
ignored without a pin because there it changes nothing a person can see. Tools and engine
are untouched: `_build_scoped_tools` and `system_prompt(..., scoped_nexus_hash)` do not know
the flag exists, and the scoped engine's consent rule (`_REJECTION_HANDLING_SCOPED`, "the
exploration is THEIR deliverable") reads a little off for a client whose mediator built it,
but confirming before a retraction is the right behaviour for that person too, so it was
left alone. No AppSpec field, for the same reason `advanced` is not one: one app serves the
mediator and their client. Unmeasured — no bench cell pins an Advisor with a persona.

## A shared price between readings is located, not refused (2026-09-21)

`nexus-pinned` was the first round to run a pinned Advisor, and its tool-outcome column was
the finding nobody pre-registered: 11 of 16 tool calls failed, all `record_decision`, all the
Rule B refusal ("that same wording is a price in 2 tensions and no other ground says which one
was decided"), and the weak-tier model answered every refusal by re-sending the identical
call — three to five times per closing, on the sealed Advisor as much as the pinned head — until
an `inspect_node` happened to make it cite a tension. Reading the archived dumps: every
instance was `ExpandPolarity`'s sibling readings on one T/A pair (`Reading along: recognition
of contribution / basis for sole ownership` beside another reading of "Buy out cofounder, run
company solo"), whose identical T- wording `commit()` dedup had made one Statement. Rule B's
argument is that a mislocated price sends the re-audit to the wrong RISK; between readings
the risk is the same node and only the condition's plus wording differs, so the refusal was
protecting nothing and costing the closing turn its rounds. `_locate_shared_price` runs
before Rule B, and only when every candidate keys to one (T, A) statement pair — keyed on the
statements, not the Polarity node, because a Polarity's hash carries its commit instant and
the test helper builds one per call. Preference order is a set of reasons: a reading an
active record already grounds beside this price (one price, one tetrad across the ledger),
then woven, then undiscarded, then SP, then hash for a stable pick. Cross-polarity sharing
still refuses. Four tests in `tests/test_decision.py::TestASharedPriceBetweenReadingsIsLocated`;
disabling the step fails the two that need it. Not re-benched.

**Across tensions, the adopted pathway locates it (2026-09-23).** `ladder-sonnet` added
the wheel narrowing (3a555f1) and `prompt-vs-machinery` measured it insufficient the same
day: one wording priced in two tensions of ONE wheel, so the wheel held both, the
polarity key said "different tensions", Rule B refused, and Sonnet 5 resent the call five
times in one 203s turn — plus one attempt with a listed tension hash in the WRONG role
and one with a fabricated 64-character expansion of a short hash. The refusal's ask ("add
EXACTLY ONE of those tension hashes as a plain ground") did not land on the production
model either, so the message is not the escape. The escape is a fact of the edge: a
Transformation's Ac+ is `source.T- → target.A+` and its Re+ is `source.opposite.T- →
target.opposite.A+` (`Transformation` docstring), so BOTH minuses a recipe transforms
belong to its SOURCE segment's perspective — the priced tetrad is the pathway's source,
read off `get_source_polar_segment()`, no guess between tensions. `_pathway_source_perspectives`
runs first; the wheel narrowing stays as the fallback when the segment cannot be read; a
source outside the candidates locates nothing (the price is not that recipe's price, and
inventing a tetrad is the thing Rule B exists to prevent). Two tests in
`TestTheAdoptedPathwayLocatesTheSharedPrice`. What still refuses: a cross-tension price
with NO pathway ground — the closing seam always grounds one, so that is the hand-assembled
case only. The bench now records the ground set of every `record_decision` call
(`TurnRecord.decision_args`, short hashes and roles) so the next refusal can be read.
Not re-benched.


## The leak by model, and the hash filter (2026-09-22)

The archive-wide 5.2% leak rate hid a split: 10.9% of Haiku replies, 0.6% of Sonnet 5
replies, and the two mechanical shapes (a `[[hash]]` citation, a bare position label)
appear 25 times on Haiku and never on Sonnet (`rounds.md`, `reply-hygiene`). So the silent
contract is a compliance property of the model reading `_HOW_YOU_SPEAK`, and the owner's
production floor (Sonnet 5) meets it. What the framework can still own is the one shape
that is never legitimate and can be removed without touching the sentence: the hash. It
was the pinned Advisor's specific leak in `nexus-pinned` (five citations, `[[69961e3]] Re+
is "..."`), because reaching the pathways in the scoped dump and quoting their addresses
turned out to be the same behaviour on the weak tier. `reply_hygiene.py` holds a regex and
a streaming filter with one contract — equal output over any chunking — so the filter can
sit under `chat_stream`'s deltas AND over `ResponseComplete.message` without breaking the
`streamed=True` promise; it is reset at every tool boundary (the promise is per segment)
and its held-back tail is released as its own delta before the tool event. Wired by
`Advisor._hides_hashes`, decided at construction from the composed preamble: the
Navigator's advisory registers carry `## Terminology Disclosure` and are exempt, every
persona-shaped head filters, history is never filtered. Bare labels were deliberately left
alone: stripping `T+` from "That's the T+ — you got ownership clarity" leaves a sentence
with a hole, and rewriting it is the model's job.

## The build policy and the `note` tool (2026-09-26)

**What was wrong with three modes.** The owner's question that ended the surface review: "the
sealed is useless, it should be some sort of a flag on Advisor to not build anything, just
discuss/decide". Two defects behind it. (1) CONSULTANT on an empty case recorded a decision that
rested on nothing — the model called `record_decision` with no grounds, and `_anchor_when_empty`
only ran where the off-turn task existed, i.e. FULL — so the surface that measured best as
counsel was hollow as a product on its own. (2) A person who says "write that down" about
something that is not a decision had no way to make the graph keep it, so "only reading without
ability to enrich" was, in the owner's words, "quite weird". The axis was also conflating two
questions: whether the head may WRITE (a host permission) and WHEN it may BUILD (a latency
policy).

**What replaced it.** `build=` is when structure is built — `ON_ELECTION` (the shipped head),
`ON_CONSENT`, `NEVER` — and `records=` is whether the seat may write at all. `ON_CONSENT` is the
new surface: no build tool on the turn, so a reply stays one graph read plus the model, and two
triggers start the same off-turn task a closing's weave runs on — the `note` tool and a confirmed
decision. `note(thesis, antithesis=None, context="")` is `anchor`'s signature with its moment
(since 2026-10-01 the Note also carries `utterance`, the person's turn it was kept on, which the
plant hands to `_anchor(utterance=)` so the tension traces to the words — `antithesis-selection.md`)
moved: on the turn it queues into the sid-keyed `_DeferredWork.notes` and returns "Kept."; after
the reply `_schedule_noted_tensions` (both turn loops, right after the seam, because the seam's
`NO_CLOSING` exit schedules nothing) starts the task; the drain plants each note with `_anchor`
FIRST, then `_anchor_when_empty` for a closing on an empty graph, then the weave — so a decision
closed on a noted tension grounds on the pathway woven in the same round. A note that fails to
plant costs the person none of the others (per-note guard); the queue is emptied per round, the
registry entry survives while a note is queued (`idle` reads it), and the task's own cleanup
checks both queues.

**Where the weave lands.** `_weave_unwoven_perspectives` used to pass `nexus_hash=self._nexus_hash`
— the pin, or `None` — and `None` reaches `CreateNexus`, so an unpinned closing on a case with an
existing exploration forked a sibling holding one tension. Under election that is measured
behaviour (every benched A2 cell; changing it is a bench round, and `TestWhereTheWeaveLands`
pins that it stays). Under consent it is the wrong default — a note is "add this to what you
know" — so `_weave_target_nexus` expands the case's ONE exploration when there is exactly one.
With no target (none, or several and no pin) the two triggers part ways — the owner's rule,
2026-09-26: a closing still weaves and CREATES the exploration its record rests on, while notes
alone are the analysis part only, planted as tensions and not woven ("a note is 'keep this',
not 'build me a map'"; the exploration is born at the closing). Read once per drain, not per
round. The trade-off, stated: between the first note and a decision, counsel reads from
tensions without pathways.

**The prompt got a fifth shape, derived like the others.** `note` is in `_WRITE_TOOL_NAMES`
via `_CONSENT_TOOL_NAMES` and not in `_BUILD_TOOL_NAMES`, so `consent = sealed and "note"
in names`. Forked: `_EAGER_CONSENT`, `_TOOLS_INTRO_CONSENT`, `_CONSENT_MANDATE` (last, as the
others), a `noting=` branch of `_scope_section`, and two rejection sections DERIVED from the
sealed head's by replacing the one sentence that said a revealed tension cannot be added (a test
pins that both replacements took). Decision Readiness' record-on-what-exists note becomes
`_RECORD_THEN_BUILT` under consent — under NEVER the pathway never comes, under consent it comes
after the reply, and the section the model reads at the closing must not say otherwise. The
sealed mandate's "nothing is built after the conversation either" stays exactly where it
still holds (`NEVER`) and is the sentence the consent mandate exists to replace.

**Two refusals, stated.** `ON_CONSENT` with `records=False` raises: both triggers are writes,
so the combination would be NEVER wearing another name, and a silently dropped flag is the
defect (`persona=` set the precedent). A pinned head without `records` gets no build tool
either, unlike the unscoped factory — pinned, `anchor`/`explore` are writes into someone else's
deliverable.

**Unmeasured.** No bench cell runs `ON_CONSENT`; `A2c` stays `NEVER`, which is what every
Sealed Advisor figure in `rounds.md` was measured on. The claims that need a round before anyone
quotes them: that a noted tension is planted with the person's particulars intact (the
`context` path is `anchor`'s, so `TestAnchorContext`'s guarantees carry, but nobody has read a
consent session's dump), and that expanding the one exploration beats forking (`ExpandNexus`
re-weaves the whole nexus, so a note on a 4-tension case is a k=5 build off the turn — the
`_MAX_WEAVE_ROUNDS` and yield-to-a-waiting-turn bounds apply, and the next turn's
`deferred_wait_s` is where the cost would show).

## The off-turn seam on a shared server (2026-09-28)

**The question that opened it.** The owner, designing chat widgets: "apps using the framework will
definitely be multi-tenant applications, a shared server running the framework, every request scoped
by sid". Two read-only reviews were run against that deployment — one on the deferred-work queue,
one on the substrate it runs on (scope, DI, the graph client, process-global state). The substrate
held: `sid` is a ContextVar with token reset, every one of the 50 injection sites reads it per call
through `providers.Callable`, a task created inside the request inherits a copy, the registry holds
a strong reference, the idle sweep cannot drop another sid's live entry, and the accounting
ContextVars are empty when the task is created. Two defects were confirmed, both only visible with
more than one process.

**Defect 1: one writer per sid was enforced by an in-process dict.** Turn N on worker A starts a
weave; turn N+1 lands on worker B, finds no task, waits 0.0s, and its closing starts a second
`run_exploration_detailed` on the same sid. The `(hash, sid)` constraint covers committed atomic
nodes only — containers skip dedup, directed edges duplicate — and the weave swallows the resulting
exception fail-soft. No document mentioned sticky routing. **Fix:** a `WeaveLease` row per sid
(`CaseRepository.acquire_weave_lease`, MERGE + WHERE + SET in ONE statement, so the read and the
write cannot interleave under autocommit; held unique by a `WeaveLease(sid)` constraint
`_ensure_schema` creates), taken at the top of `_run_deferred_pathway_construction`, renewed at
the top of every round, released in the `finally`; TTL 600s after the last renewal so a dead holder
frees the sid. A task that cannot take it stands down with its queues intact.
`_settle_deferred_work` now also waits out a lease another process holds (`_wait_for_foreign_weave`,
1s poll) — that wait cannot ask the other process to yield, which is why sticky-by-sid routing stays
a latency recommendation. Not a `:Node`: no listing sees it, `scope_fingerprint` does not move when
it changes hands, the stale-node reaper cannot reap it. **Fail-OPEN on faults:** a broken lease
query degrades to the pre-lease behaviour with an exception in the log, never to a surface that
silently stops building. The owner string is per PROCESS (`_WEAVE_OWNER`), because a fresh Advisor
resuming a sid on the same worker must read its own process's lease as its own.

**Defect 2: notes lived in RAM and the model said "written down".** `_queue_note` appended a triple
and returned "tell the person it is written down"; a deploy between the reply and the plant lost
exactly what the consent surface exists to keep, and `agents.md`'s "skipping the drain loses
nothing but the pathway" was true for decisions and false for notes. **Fix:** `Note`
(`graph/nodes/note.py`; `thesis`/`antithesis`/`context`, mutable `planted`, a NONCE in the hash)
committed in `_queue_note`; the drain reads `NoteRepository.find_unplanted()` every round and
stamps each planted note. A note lives in exactly one place: the in-memory list holds it only when
the commit could not happen (no scope, or a failed write), so nothing can anchor a note twice and a
note another process already planted is simply no longer pending. The nonce was a correction made
the same day: the first cut dedup'd on the words ("the same words kept twice are one note"), and
the owner's question about multiple readings exposed that this silently swallowed the one route
to an alternative tetrad — `anchor` on IDENTICAL wording, which the engine prompt asks for by
name. Each keep is a speech act, as each record is. `_schedule_noted_tensions` re-offers whatever
is still queued on every turn
(RAM notes, unplanted Notes from the graph, AND decisions a stood-down task left waiting — before,
a decision whose task stood down waited for the next closing to be grounded). The context dump
counts pending notes under `# Unfinished`, including on an otherwise empty case, and `planted` is a
term of `scope_fingerprint`.

**The drain a server can call.** `wait_for_deferred_work` resolves the sid in scope plus one
instance's keys — the right shape for a console chat, unreachable from an ASGI lifespan hook.
`drain_deferred_work(timeout)` (module-level) awaits every sid's task on this loop, same
never-cancels contract; `deferred_work_in_flight(sid)` is the in-process probe for a handler that
wants to answer with a heartbeat instead of blocking behind the settle wait.

**Left as capacity work, deliberately.** Every graph write is synchronous over one cached mgclient
socket (110.9s of a 163.2s k=4 wall with no suspension before the yields were added), so concurrent
weaves serialise the loop and jitter other tenants' streams; moving writes to a thread needs a
connection per worker first (the client is not thread-safe). Settings, event buses and DI wiring are
process singletons (a second `setup()` re-points every tenant — now a documented contract, not a
guard). No priority between off-turn weaves and on-turn replies. Event-bus subscriber queues are
unbounded. None of these corrupts a graph; all wait for a load test. Tests:
`tests/test_multi_tenant_deferred_work.py`.

## The quality floor never empties the section (2026-10-01)

`DialecticalContext._apply_quality_floor` suppressed every standalone
perspective below the floors (antithesis HS, SP, DV, or a failed validation
verdict) and left a count line. Measured on the thesis-only `anchor` path with
the tetrad-quality instrument (40 free utterances, both sets, after the day's
three fixes): validation failed on 26/47 and 34/47 committed tetrads, and
**10/20 and 13/20 utterances ended with no visible tetrad at all** — the
Advisor's next turn read "1 unexplored tension(s) suppressed for low quality"
where the tension it planted a turn earlier should have been, with no hash in
the prompt to reach it by `inspect_node`. On the given-antithesis path the HS
floor alone would have hidden 5 more of 20.

Fix: when the floor leaves nothing, keep the least weak one (`_floor_rank`:
a passing verdict first, then SP, DV, HS; unscored sorts below any score) with
its `Validation:` line and its scores as they are, count the rest. Pruning a
crowded prompt so the head ranks within it is the floor's purpose; with nothing
left to rank it is not pruning. The prioritization prompt names the exception
("read that line before leaning on it"), `TestContextDumpPrePruned` still
holds the claim. `test_all_suppressed_still_reports_count` asserted the old
behaviour and was rewritten; the advisory-mode test
(`TestTheBoundIsTheQualityFloorAndNothingElse`) now plants a sound anchor
beside the weak one, because what it pins is that advisory mode runs the SAME
floor, not that a lone anchor disappears.

Not changed: the floors, their defaults, and HS's low scores for genuine
dilemma antitheses (0.02–0.85, mean 0.45 on 20 named antitheses) — that is an
open question about HS on a NAMED antithesis, recorded in
`antithesis-selection.md`.

## `anchor`'s thesis-only branch is the one-shot build; HS left the floor (2026-10-01)

`anchor(thesis=, antithesis=None, context=)` no longer runs `AnchorTheses` →
`AnalysisPipeline(thesis_hashes=)`. It runs `SketchTetrad`: one json-mode
thinking call over the person's turn (the thesis pinned, the Consultant's
`method_prompt()` as system prompt) writes A and the four aspects;
`IntroducePolarity` and `ExpandPolarity(given_tetrad=)` classify, score, dedup,
ground, validate and persist. Measured in `antithesis-selection.md` ("The
one-shot build"): coherent first tetrads 42/80 against the staged 14/40,
genuine antitheses 74/80 against 27/40, ~43 s against ~55 s, two generations.
The two-pole branch and `note` are unchanged; `ingest` keeps the staged path.

In the same change the HS term left `DialecticalContext._apply_quality_floor`
and `settings.advisor_polarity_quality_min_hs` is gone (no alias; env
`DIALEXITY_ADVISOR_POLARITY_QUALITY_MIN_HS` no longer read). Reason: the
one-shot build's antitheses are genuine positions, HS scores a genuine position
low by construction (28/40 and 20/40 below 0.5 across the two generations, min
0.03) while validation passed on 21/40, so with the term the Advisor would have
hidden 33 of 40 tetrads it had just built. The floor keeps the paper's SP+DV
pair and the validator's verdict; `_floor_rank` orders the kept slot by
verdict, SP, DV.
