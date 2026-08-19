# e2e — an integration harness for a distributed prompt

A falsifiable harness, not a demo. It is built to be *able to report that the
framework adds nothing* — if it could not, a positive result would mean nothing.

**Resuming this work?** Run `/df-e2e` (`.claude/skills/df-e2e/SKILL.md`) — it orients a
fresh session and routes every figure through `status.py`. And read that script's output
before this file, because **prose carries judgement and `status.py` carries numbers**:

```bash
poetry run python tests/e2e/status.py      # coverage / unread / deltas — free
```

**This file is the reference: what the harness is, the ladder, how to run each lane,
and what keeps the comparison honest.** The rounds themselves — every
pre-registration, result, correction and retraction, in the order they happened —
are in [rounds.md](rounds.md). Split out on 2026-08-19, when this file was 3406
lines of which 3006 were round log.

So: **reference here, provenance in `rounds.md`, numbers in `status.py`.** No figure
in any of the three is a substitute for the other two.

## What this is for (renamed from `bench`, 2026-08-19)

**Read this before reading [rounds.md](rounds.md), because the rounds are written
as if the judged delta were the point.** It is not, and the commit log says so: of the
216 commits in the month this harness ran, **122 touched `src/`**. The output was
framework repair, and the defects were nearly all *seam* defects — a value
computed and never rendered, rendered and never read, read and never acted on:

| Commit | Defect |
|---|---|
| `62244f0` | pathways-before-closing: **the differentiator was never running** |
| `2c158bc` | closed without grounding on the pathway it just built — 0 of 6, with 42 transformations in hand |
| `b045d3e` | the two-tension floor kept the seam silent when one tension is enough |
| `2ae30cc` | a committed Decision was lost when persisting its verdict failed |
| `672c19d` | aspects deduplicated into their own tetrad's poles |
| `76495d3` | control-statement attribution contradicted the paper |
| `b20aaab` | `accepted_cost` grounded on a plus when it is a RISK |

None of those is findable by reading one prompt. The framework IS a distributed
prompt — a dozen concern prompts, three system prompts, app preambles, tool docs,
context dumps — and its failure mode lives in the joins. You find them by driving
the assembled system end to end and checking whether the thing arrived.

### Three lanes, one engine

The lanes are **selectors, not directories**. `models` is imported by 19 of the 32
modules here; splitting the tree would break 138 imports to relocate a shared
engine, and the certification code and the diagnostic code read the same records.

| Lane | Selector | Oracle | Output |
|---|---|---|---|
| **Seam** | `pytest -m seam --real-llm` (12 tests) | a known-good value | pass/fail |
| **Search** | `test_e2e_matrix` + `judge_notes.py` | **an opponent arm** | judge rationales naming a flaw |
| **Archive** | `across_runs.py`, `read_pooled.py`, `read_prereg.py` | pooled history | a defensible number |

**The seam lane already existed, unlabelled** — eight `--real-llm` files in
`tests/`, each born from a measured defect in this archive, now carrying
`pytest.mark.seam`. Run it after any prompt or seam change. It is cheap, it needs
no opponent, and every test in it names the link it guards:

| Guard (`tests/`) | The link it guards | Born from |
|---|---|---|
| `test_pathways_seam_real_llm` | two seeded tensions → a woven arrangement, and weaving first doesn't cost the record | `62244f0` — the seam never ran |
| `test_pathways_before_closing_weak_tier` | a confirmed decision AND its arrangement on the same turn | `explore` fired 6/55 weak vs 17/25 strong |
| `test_single_perspective_explore_real_llm` | ONE perspective is enough to explore | 5/6 A2 runs never called `explore`; 3 prompt fixes failed |
| `test_decision_repair_weak_tier` | a weak model still leaves a record | 0/6 weak vs 6/6 strong recorded a decision |
| `test_decision_rationale_integrity_weak_tier` | a REFUTED risk is not recorded as a CARRIED one | 4/12 A2 rationales swallowed a fabricated dismissal |
| `test_machinery_silence_weak_tier` | the REPLY, not the prompt, keeps the machinery quiet | 15 vocabulary leaks in 6 cells, every prompt test green |
| `test_tetrad_collapse_real_llm` | no aspect deduplicates into its own pole | `672c19d`; an `accepted_cost` ground sitting at `T/T-` |
| `test_condition_ambiguity_live_probe` | the accepted-cost condition renders (0/6 live) | duplicate directed edges vs genuine ambiguity |

Note what the "born from" column is: **a count, from a run.** Every one of these
started as a number in this archive that had no business being that number, which
is why the search lane below is not decoration.

**This table is pinned, not documented.** `TestTheSeamLaneRosterIsReal`
(`test_e2e.py`) fails if a rostered file is renamed or loses its marker, if a
marked file is missing from this table, if the `seam` marker is unregistered, or if
`pytest-timeout` is dropped. Six mutations, six caught. A lane described only in
prose is the same shape of claim as a timeout that doesn't time out.

**The lane is deliberately narrow, and `-m seam` must not become `-m real_llm`.**
A seam test drives the *assembled* system and reproduces a measured defect from
`results/`. `test_aspect_axis_real_llm` and `test_options_classification_real_llm`
check one concern's judgement against a real provider — useful, and not this.
`test_decision_confirmation_repair` and `test_prompt_review_regressions` pin the
same seams DB-free and already run in the default suite; they need no marker
because they cost nothing.

**Why the search lane keeps its judge and its opponent arms.** A regression test
can only guard a defect someone already found; it cannot answer *"is this worse
than it should be?"* An opponent arm can, without the defect being specified in
advance — `2c158bc` was unwritable as a regression test because nobody knew the
closings weren't grounded, and the comparison is what produced that knowledge.
`423d88a` ("read the judge's reasons: five prompt gaps") came from reading **531
judge rationales**, not from reading scores. So the score is the trigger and
**the rationale is the payload**; `judge_notes.py` is the primary reader.

**What is retired: the certification apparatus, not the comparison.** Pooling,
bootstrap CIs, pre-registration ceremony, `SUPERSEDED` maps and unit-of-analysis
arguments exist to defend a population claim to a skeptical reader. Finding a seam
bug needs one lost cell and a reason, not significance. *"At par or better"* is a
**fitness function, not a hypothesis test** — conflating the two is what produced
23 rounds of arguing about whether +0.193 resolved while the useful artifact was
always the judge's prose. The machinery stays (`archive` lane) for the day a
number must be published; it is not the loop.

**One measured caution about that loop, from this archive.** On the two ladder
rounds (`ladder-return-r16`, `ladder-return-r18`; 12 replicates each, SUBSTANCE
mean gap, bootstrap CI clustered by replicate — `session_1 / ladder / followup`):

| pair | round | pooled | session_1 | ladder | followup |
|---|---|---|---|---|---|
| A2−A1 | r16 | **+0.683** [+0.46,+0.90] | −0.217 | −0.267 | **+2.533** [+2.18,+2.88] |
| A2−A1 | r18 | **+0.739** [+0.59,+0.88] | **−0.433** [−0.80,−0.12] | +0.283 | **+2.367** [+2.10,+2.65] |
| A2−A1.7 | r16 | +0.083 (covers 0) | −0.367 | −0.467 | **+1.083** [+0.62,+1.55] |
| A2−A1.7 | r18 | +0.250 (covers 0) | −0.333 | +0.300 | **+0.783** [+0.27,+1.33] |

Bold = CI excludes zero. Three things this says, none of them visible in the
pooled column alone:

1. **The whole effect is at the return.** Inside session 1, A2 is *behind* — in
   r18 significantly so. It wins when the user comes back and the record is read.
2. **A1.7 — a prose journal written by someone who read this framework's design —
   captures most of that.** Of the followup gain over A1, A1.7 takes 57% (r16)
   and 67% (r18); the graph adds the rest. That is the honest size of the typed
   record's edge over good notes, and it is why A1.7 is the opponent, not A1.
3. **The pooled A2−A1.7 figure covers zero in both rounds.** Anyone quoting a
   pooled number here is averaging a loss and a win over a design that puts them
   in fixed proportion (1 followup per 3 sessions). Read per-session.

Both rounds are the same scenario (`cofounder_ladder_return`), one tier, so the
independent unit is 12 replicates, not 36 comparisons — the unit-shopping error
`716d124` was committed to catch.

## The two claims

| Claim | What it asserts | Honest opponent |
|-------|-----------------|-----------------|
| **1 — Reasoning discipline** | Enforced dialectical structure produces better in-session counsel than a model self-applying the same method | **A1** (the real method text, no tools) |
| **2 — The institution** | A typed decision record beats a prose memory when the user comes back wobbling | **A1.7** (the model's own journal, verbatim) |

Claim 1 is expected to be **depreciating** — as base models improve, they
self-apply the method better and the gap shrinks. Claim 2 is the durable one, if
either is. The report classifies each delta rather than reporting a win rate,
which is why ≥2 tiers matter.

**What "A2 loses to A1.7" therefore means, stated precisely.** A1.7 is not an
independent rung: it is `persona + method_prompt() + the model's own journal`.
Measured against the live engine prompt, `method_prompt()` is **62% of its
paragraphs verbatim engine text, 88% of its sentences, 93% at ≥0.60 similarity**,
and every engine paragraph with no counterpart is tool-operation prose. That is
the fairness rule working as designed (see [What keeps the comparison
honest](#what-keeps-the-comparison-honest)) — but it means the archive's resolved
loss is **not** "dialectics do not help". Both arms carry the dialectics. The
comparison isolates the *delivery vehicle*: the same method run as machinery
against the same method run as prose, with memory held roughly equal. Read every
A1.7 row that way. The only rows that test dialectics-vs-no-dialectics are the
A0/A1 ones, and they are **too thin to carry a verdict in either direction**: 3
weak-tier runs (−0.10 [−0.52,+0.33]) and 2 strong (−0.11 [−0.53,+0.31]) against
13 weak-tier A1.7 runs. Cell-level they cover zero at both tiers (weak −0.14
[−0.46,+0.18] over 32 cells, strong −0.19 [−0.50,+0.12] over 30), but cells
within a run share a build and an afternoon, so that interval is optimistic by
roughly √n — quotable as "no A1 loss has been established", never as "A2 ties A1".
**Resolving this is the archive's cheapest open question**, and it is the same
`one run judging A0/A1 and A1.7 on the same build` that `rung_rows` has been
asking for.

**Where it stands, pooled over the whole archive (corrected 2026-08-14): the
framework arm loses on the weak model and the loss resolves — composite −0.447,
CI [−0.61,−0.28], negative in 14 of 14 runs.** The strong tier is ~7× smaller
(−0.06) and does not resolve at n=4. Neither claim is currently supported, and the one that could still
be is the strong-tier one — [full numbers below](#the-archive-wide-picture-the-weak-tier-loss-is-real-and-it-resolves).

## The round loop does not converge, and the round shape is why

Sixteen rounds each changed `src/`, judged ONE run, and read the result as
evidence about the change. `round_trend.py` asks whether that loop went anywhere.
Four measurements, all free, all from saved records:

1. **No trend.** Eleven comparable rounds (one *named* scenario, one *model*, one
   opponent, slot- *and* stratum-balanced — the first two of those legs were
   loopholes until 2026-08-14, see the r18 note below): mean **−0.547**, sd 0.258,
   all 11 negative,
   correlation with round order **−0.34**, slope −0.026/round. Sixteen rounds of
   fixes point, if anything, slightly down.
2. **The rounds are one distribution resampled.** A round's own 95% half-width is
   ≈±0.40, i.e. se ≈ 0.204 — so a constant-mean archive would show a
   round-to-round sd of ≈0.204 by itself. Observed: 0.258. **Ratio 1.27.** The
   archive cannot attribute its own variation to its own changes.
3. **A round was never powered to confirm a fix.** At sd 0.258, detecting +0.2
   needs **27 runs per build**, +0.3 needs 12, +0.5 needs 5. Every round spent
   **one**. A single-run round can only register an effect larger than the entire
   archive's spread — so the design could fail to see a fix but never confirm one,
   which is exactly what "not deterministic toward better results" means.
4. **What did move is manners, not product.** Splitting the same 12 dimensions
   into REGISTER (warmth, fit, coherence, actionability, earned_confidence) and
   SUBSTANCE (the framework's own turf) and pooling by era: register **+0.386
   [+0.07,+0.70] resolves**; substance **+0.027 [−0.39,+0.44] covers zero**. The
   mechanism is visible in the transcripts — A2 went **416→272 words and
   7.25→2.71 bullets/turn** between r7 and r16 while A1.7 held ~310/~1.1. The arm
   closed the gap by converging on its opponent's shape. That is
   ceiling-not-floor failing, as a number.

**And `probe_readside_reach.py` explains why that was cheap: the framework's
product never reached the reply.** Overlap between the rendered dump and the
replies written with it in context, best-matching line per section, same dump
every time: decision ledger **0.56**, pathways **0.26**, synthesis **0.21**,
hashes cited **0 across 18 sessions**. The read side is not broken in general —
the memory section lands reliably — it is broken for exactly the sections that
carry the differentiator. Worse, **14 of 18 first sessions built 390
transformations while the system prompt held `EMPTY_UNDERSTANDING` for all 8
turns**, because `_ensure_pathways_before_closing` runs *after* `submit()` and
`{dialectical_context}` is rendered once at construction. Depth does not predict
the score in either direction (corr −0.107 over 36 cells — a **null, not an
inversion**), which is precisely what an unread structure predicts.

So the loss is a **read-side/ordering defect first**, and the loop could shed
structure cheaply because the structure was not being read anyway.

**Consequences for how a round is run** — this supersedes the one-run-per-build
habit, not any published number:

- Do **not** read a single-run judged composite as a verdict on a build. State
  the interval or say nothing.
- Prefer **machine-countable endpoints** (the record-integrity block is the
  template: binary, no judge, Fisher-testable) over the judged composite, which
  is the one endpoint this bench cannot afford to move.
- Before writing a prompt fix, **count the behaviour it targets**
  (`probe_five_fixes.py` disqualified four of five).
- A round that improves register is buying back a tax. **Only a substance move is
  evidence the framework does something a prompt cannot** — and no round in the
  ledger has produced one.

## The ablation ladder

| Arm | Assembly | Cross-session carryover |
|-----|----------|-------------------------|
| A0 | bare persona | none |
| A1 | + the dialectical method as prompt text | none |
| A1.5 | + a real Advisor-built graph, dumped as static text | static dump |
| A1.7 | + a journal the model writes for itself | prose journal |
| A2 | the full Advisor: live tools, graph, decision ceremony | live graph |

Every arm answers through the same `ConversationFacilitator.submit(ChatResponse,
...)` on the same tier model with the same persona. A2 differs by having **tools
and a graph**, not a better prompt or a different decode path.

**Each rung isolates one variable, so a delta names its own cause.** A1−A0 is the
method as *text*. A1.5−A1 is having the framework's output without having built
it. A1.7−A1.5 is a memory the model chose the contents of, versus one handed to
it. **A2−A1.7 is the interesting comparison** — the typed, queryable record
against the honest prose one. A2−A1 is easy and says little: nobody ships the
method as a paragraph. Read `A2−A1.7` first, and treat `A2−A1` as a floor check.

### The mother prompt, and why A1 is not a strawman

There is one: `src/dialectical_framework/agents/advisor/system_prompts.py`. It is
the domain-neutral dialectical engine — `_INTERNAL_MODEL` (how dialectical
understanding works), `_CONVERSATION_USE`, `_DECISION_READINESS`,
`_HOW_YOU_SPEAK`, `_ROLE`, `_EAGER`, and a `{dialectical_context}` slot the live
graph is rendered into. Persona is *not* in it (that comes from `agents/apps.py`),
which is what makes the same engine text reusable across arms.

`arms.py` imports those section constants **live** and builds A1's prompt from
them. It does not paraphrase, and it deliberately does not call
`system_prompt(tool_names=[])` — that function's prose still refers to `anchor` /
`ingest` / `inspect_node`, so a tool-less arm would be instructed to call tools it
does not have. Instead `_TOOL_REWRITES` translates tool-operation verbs into
**mental acts**. The distinction matters: *dropping* those paragraphs also deletes
the discrimination test, the re-audit rule, and "never dump all insights at once"
— i.e. the reasoning under measurement. A sandbagged A1 inflates every A2 delta,
so `test_rewrite_table_has_no_stale_keys` fails if `system_prompts.py` is edited
and the rewrite table drifts.

Consequence worth stating plainly: **A2 has no prompt advantage over A1.** Its
prompt is the same engine text plus tool documentation. Anything A2 wins, it wins
by operating machinery.

### Which models play which role

Four independent slots (`config.py`; every one env-overridable — see "Selective
runs"). Defaults:

| Role | Default | Why |
|---|---|---|
| weak tier | `claude-haiku-4-5` | where structure should help most |
| strong tier | `claude-sonnet-5` | where the model may already do it unaided |
| simulator (the person) | `claude-sonnet-5` | held **fixed across arms** — it is the environment, not a contestant |
| judge | `claude-fable-5` | must not be a model under test |

Both tiers are run because the two answer different questions, and the answers
have differed: the ceremony was **tier-gated** (6/6 strong, 0/6 weak) and
prompting did not close it. The judge sits outside both tiers so a win cannot be
self-preference; the simulator is fixed so an arm cannot be handed an easier
person. **Read the recorded model, never the tier label** — `ladder-return-r18`
pointed the weak slot at Sonnet deliberately, and every pooled weak-tier cut that
trusted the label averaged Sonnet into Haiku.

## Two lanes are ports of published protocols

Everything above is homegrown: our scenarios, our rubric, our markers. That is
unavoidable for counsel quality — no external benchmark scores it — but it means
a positive result has no outside anchor. Two lanes fix that on the two things
this bench measures worst, keeping the ablation ladder as the arm axis and
borrowing only the **protocol**:

| Scenario | Protocol | Published anchor |
|----------|----------|------------------|
| `cofounder_rebuttal_ladder` | SycEval's escalating rebuttal ladder (arXiv:2502.08177) | 14.66% regressive; 78.5% persistence |
| `cofounder_memory` | LongMemEval's five memory abilities (arXiv:2410.10813) | ~30% accuracy drop |

```bash
# both ported lanes, one tier, the two Claim-2 arms
DIALEXITY_E2E_ARMS=A1.7,A2 \
DIALEXITY_E2E_SCENARIOS=cofounder_rebuttal_ladder,cofounder_memory \
DIALEXITY_E2E_TIERS=weak \
poetry run pytest tests/e2e/test_e2e_run.py::test_e2e_matrix --real-llm -s
```

**The rebuttal lane deliberately reuses the `cofounder_equity` case.** Both
protocols then score the *same* position, and their disagreement is the finding:
`score_erosion` says the aspect survived if its words appear, the stance judge
says whether it was still held. On different cases those two numbers would be
incomparable and the blind spot would stay invisible. The ladder's `rebuttal_*`
tags count as pressure via `_PRESSURE_TAG_PREFIXES`, which is what puts both
lanes on the same turns.

**What is comparable, and what is not.** The rungs are LITERAL (a DIRECTED
simulator improvising a "citation" rebuttal would vary its force per arm, so the
per-rung comparison would measure the simulator). But SycEval scores against an
answer key and counsel has none, so the substitute is the scenario's stipulated
`contested_position`. That works in **one** direction only:

- `regressive` (held, then dropped under pressure) **is** the paper's quantity —
  compare it to 14.66%.
- The reverse movement is **not**. The rebuttals argue *against* the position, so
  nothing in the ladder could correct an arm toward it. It is reported as
  `late_adoption` precisely so nobody lines it up against 43.52%.

The memory lane's scale is not the paper's either: LongMemEval embeds its
questions in ~115k-token histories, these sessions are a handful of turns. A
failure here is therefore **more** damning and a success **much** weaker
evidence. `abstention` is a control, not a win — richer memory makes
confabulation easier — and it is counted into the accuracy figure on purpose.

The report prints all of this above the tables, and both docstrings carry it, so
a number cannot be quoted out of its caveat.

## The ladder-return lane — the endpoint no judge scores

`cofounder_ladder_return` is not a port and has no published anchor. It exists
because of what the era pooling found: at the weak tier the REGISTER dimensions
moved **+0.386 [+0.07,+0.70]** across sixteen rounds while SUBSTANCE moved
**+0.027 [−0.39,+0.44]**. Sixteen rounds bought manners, not product — and a
judged composite over a transcript structurally cannot separate *holding* a risk
from *writing well about holding* one. So this lane measures something a judge
never sees.

The arms differ **structurally** in what survives a session ending: A1 keeps
nothing, A1.7 keeps a prose journal it wrote itself, A2 keeps a graph. So the
primary endpoint is a machine count over the artifact the NEXT session was
handed:

| Endpoint | What it is | Instrument |
|----------|-----------|------------|
| `carried` | the risk's own framing is still in the artifact the returning session got | machine, `score_survival`, **no judge** |
| `break_depth` | the weakest rung that broke the position (1=simple … 4=citation, 5=never) | judged, one ordinal per cell |

Both are **CO-PRIMARY and reported apart**. Disagreement is the finding: `break
1` with `carried yes` is an arm filing a risk it has already conceded, which the
composite would have scored as good memory. `carried` is **n/a** for A0/A1 by
construction — an absent capability, never a zero.

Three sessions, not two, and both reasons are in the driver: `_run_session` sets
A2's `live_context = None` on the first session (so a session-1 ladder gives A2
no dump at all) and skips `write_journal()` on the last (so in a two-session
scenario A1.7 *is* A1 for this endpoint). Session 1 is a neutral opener that
deliberately omits the customer concentration — the `establish` beat in session 2
introduces it, so A2's artifact cannot carry it before any pressure exists.

The pressure beats are the **same objects** as the one-session ladder's
(`_LADDER_RUNGS` in `scenarios.py`): only the boundary moves, which is what makes
the two lanes' break depths comparable
(`test_both_ladder_lanes_apply_identical_pressure`).

The ladder session ends on the shared `_COMMIT` beat, and that is not decoration.
Measured over the archive's 176 saved cofounder-lane artifacts, **28 of A2's 30
survival hits sit inside the rendered `# Decisions` section** — its carry runs
through the decision ledger, and `record_decision` is consent-first, so a scenario
with no commit beat leaves the section empty and A2 scores at a ~2–4% floor for a
reason that has nothing to do with graph memory. The one-session ladder does *not*
get the beat: nothing there reads an artifact.

### What this endpoint compares — and what it does not

`carried` reads **two different kinds of object**: A1.7's free prose against A2's
sectioned graph dump (A1.7 30/84 hits, mean 568 words; A2 30/92, mean 1978). That
difference *is* the arms, but it means the count compares writing surfaces as well
as memories, so the per-cell rows print **where** each hit landed and whether any
hit sat on a T/A component line.

That last column is expected to be almost always **no**: only **2 of 352** real
component lines in the archive contain any declared form — and those two are the
same statement rendered in two artifacts, so it is **one distinct component in the
entire back catalogue** — because components are capped at
`settings.component_length` (~7 words). So the honest reading is fixed in advance:
**this endpoint measures what the artifact's prose retained, not what the tetrad
layer encoded.** Any claim that it validates the structured layer would be the one
thing the measurement cannot support.

Its pre-registered criteria and every round run against it are in
[rounds.md](rounds.md) — r16 (haiku), r18 (the same lane one tier up), r19/r20
(prompt-firing probes), and the `hedge_rate` candidate win that was refuted.

## Run it

Requires Memgraph (`docker compose -f docker-compose.test.yml up -d`) and
Bedrock credentials in `.env`. Everything spends real money — `--real-llm` only.

**Start with the seam lane. It is the one you run often.**

```bash
# LANE 1 — seam. 12 guards, each reproducing a measured defect from this
# archive. Run after ANY prompt, context-dump, or seam change. Minutes, cents.
poetry run pytest -m seam --real-llm -s

# free: the harness's own unit tests (no LLM, no DB)
poetry run pytest tests/e2e/test_e2e.py

# cheap end-to-end smoke: 1 scenario, 1 tier, A1 vs A2, no judge (~7 min)
poetry run pytest tests/e2e/test_e2e_run.py::test_e2e_smoke --real-llm -s

# LANE 2 — search. The judge and the opponent arm, to find defects nobody
# has written a guard for yet. Hours, dollars.
poetry run pytest tests/e2e/test_e2e_run.py::test_e2e_matrix --real-llm -s

# ...and then READ IT. This, not the delta table, is the search lane's output.
poetry run python tests/e2e/judge_notes.py                # worst 5 dimensions
poetry run python tests/e2e/judge_notes.py --all-cells     # won cells too

# LANE 3 — archive. Free, no LLM. Only when a number must be defensible.
poetry run python tests/e2e/across_runs.py
poetry run python tests/e2e/read_pooled.py
poetry run python tests/e2e/read_prereg.py
```

**The loop the lanes are meant to close:** a lost cell in lane 2 →
`judge_notes.py` says what the arm actually did → fix it in `src/` → write the
guard into `tests/test_*.py` with `pytest.mark.seam` so lane 1 owns it from then
on. Every one of the 12 seam tests arrived by that route. A finding that does not
end in a seam guard will be re-found next round at full matrix price.

`-s` matters: a matrix run takes hours and the progress lines are the only way
to watch it.

### Selective runs

Everything narrows by env var, so a finding can be re-checked without
re-spending the matrix:

| Var | Default | Example |
|-----|---------|---------|
| `DIALEXITY_E2E_ARMS` | `A0,A1,A1.7,A2` | `A1,A2` |
| `DIALEXITY_E2E_SCENARIOS` | all | `cofounder_equity,cofounder_rebuttal_ladder` |
| `DIALEXITY_E2E_TIERS` | `weak,strong` | `weak` |
| `DIALEXITY_E2E_REPLICATES` | `1` | `3` |
| `DIALEXITY_E2E_BRANCHES` | all declared | `wobble_a` |
| `DIALEXITY_E2E_JUDGE_OFF` | unset | `1` (machine scores only) |
| `DIALEXITY_E2E_STEM` | `matrix` | `claim2-recheck` |

```bash
# just the wobble arm, both variants, one tier — the Claim 2 probe alone
DIALEXITY_E2E_ARMS=A1.7,A2 \
DIALEXITY_E2E_SCENARIOS=cofounder_equity \
DIALEXITY_E2E_TIERS=weak \
poetry run pytest tests/e2e/test_e2e_run.py::test_e2e_matrix --real-llm -s
```

Model choices also come from the environment (`DIALEXITY_E2E_TIER_WEAK`,
`_TIER_STRONG`, `_SIMULATOR`, `_JUDGE`) — see `config.py`. Never put credentials
or account-scoped ARNs in committed files.

Output lands in `tests/e2e/results/` (gitignored). The runner saves records
**before** judging, so a judge crash — or a judge *bug* — never costs a re-run:

```bash
# re-judge saved transcripts. minutes and cents instead of hours.
DIALEXITY_E2E_REJUDGE=decision-strong-r4 \
poetry run pytest tests/e2e/test_e2e_run.py::test_e2e_rejudge --real-llm -s
```

Measured: 10m43s to re-judge what took 1h22m to run. Old comparisons are
dropped on load — the reason to re-judge is usually that they are suspect, and
keeping them would average two judging regimes into one delta at double the n.
Machine scores are reloaded, not recomputed, so the only thing that differs
between the two reports is the judging.

## Cost shape

The matrix is sequential **by necessity** — `modelctx.using_model` mutates a
process-global DI container, so two concurrent cells would answer on each
other's model. Budget accordingly. From the smoke run, per scenario-session:
A1 ≈ 80s, A2 ≈ 360s (A2 runs the real analysis pipeline on every turn).

Cost multiplies as `tiers × scenarios × replicates × branches × arms`. A2 is
~4.5× a prompt arm, and A1.5 additionally needs a full Advisor run just to build
its context — which is why A1.5 is not in `DEFAULT_ARMS`.

## What keeps the comparison honest

The failure mode of a harness like this is a plausible number and a wrong
conclusion. The guards, each with a test in `test_e2e.py`:

- **The A1 baseline is derived from the live engine prompt**, with tool verbs
  rewritten into mental acts rather than dropped — a naive drop deletes the
  discrimination test and the re-audit rule, i.e. exactly the reasoning being
  measured. `test_rewrite_table_has_no_stale_keys` fails if
  `system_prompts.py` is edited and the rewrite table drifts, because that
  silently sandbags A1 and inflates every A2 delta.
- **Presentation discipline is shared, not an A2 perk.** Found in the smoke run:
  without `_HOW_YOU_SPEAK`, A1 wrote "That's T+, and it's legitimate" to the
  user while A2 never did. Rules about *how to talk* go to every arm; only rules
  about *operating machinery* are A2's.
- **A2≠A1 assert.** Graph-building is model-initiated, so an A2 run with zero
  tool calls silently collapsed to A1. `RunRecord.collapsed_to_a1` flags it and
  the report calls those runs invalid, not weak.
- **An unexercised arm is MISSING data, not a weak arm.** The report printed
  "INVALID as A2 evidence" and then every pooled cut averaged those cells in
  anyway: `Deltas.add` and each `across_runs` loop filtered `Comparison.error`,
  which is set when the JUDGE call fails — not when the arm never ran. An empty
  transcript judges fine and scores like an extremely bad arm, so a harness fault
  entered as evidence against the framework. `RunRecord.invalid_as_evidence` +
  `report.drop_invalid` now drop those cells at every seam, and
  `across_runs.excluded_rows` prints what was dropped *above* the numbers, since a
  reader who meets the n after the verdict cannot tell a filtered pool from a
  small one. Measured: `claim2`'s four dead strong-tier A2 runs (every turn a 400,
  0 words) carry its −3.13 composite, and excluding them moves A2-vs-A1 strong
  from −0.82 (resolving) to −0.19 (covers zero). **No published figure moved** —
  `claim2` is multi-scenario and `smoke-strong` is a smoke stem, so both were
  already outside the pooled line for unrelated reasons, which is why this is a
  guard rather than a correction. `TestAnUnexercisedArmIsNotAWeakArm` pins it, and
  one of its cases fails the moment a *pooled* stem acquires an invalid cell.
- **Blind, paired, position-randomised judging**, per-dimension, with length and
  eloquence explicitly discounted — and raw word counts printed anyway, because
  "instructed to ignore" is not "did ignore".
- **The X/Y split is exact, not merely random.** The judge scores whatever sits
  in the Y slot higher — measured at +0.35 of a 5-point step over 288 scores.
  The rubric discounts length and eloquence and that works; it says nothing about
  position and evidently cannot. This is bias, not variance, so replication does
  not remove it: it has to be cancelled by construction (`judge._x_is_a`
  alternates within each arm pair). The report prints the measured bias and the
  split ABOVE the delta table, because a lopsided split makes every row below it
  unreadable — which is exactly how `decision-strong-r4` first reported an
  8-of-12-dimension A2 "win" on a 10/2 split. Both failures of this mechanism so
  far were in the WIRING rather than in `_x_is_a`: r4's per-comparison hash
  re-rolled the start every call (10/2), and r15's stratified counter left each
  ODD stratum's 2/1 residual on the same hashed side so they added instead of
  cancelling (7/5 under a +0.40 bias, larger than every delta it was supporting).
  `stratum_index` flips the start on alternate strata; the split is now exact at
  every replicate count, asserted through a reproduction of the runner's own loop
  rather than of `_x_is_a` alone, since unit-level cover passed through both
  breaks.
- **Non-inferiority dimensions** (warmth, actionability, conversational fit) are
  judged but never folded into the headline. They are the base model's home turf.
- **Machine scorers that no LLM can flatter** (`scoring.py`) reported beside the
  judge, so disagreement is visible. Where they disagree, trust the machine.
- **Absence is `None`, never `0`.** An arm that *cannot* record a decision ground
  has no citation score; reporting that as zero would read as failure to use a
  capability it never had. Same rule for `memory` in the particulars table.
- **Capacity and behaviour are scored separately.** `carryover_in` records the
  artifact each arm was HANDED, so "the memory never held the fact" (storage) and
  "the memory held it and the reply ignored it" (prompt) are distinguishable. One
  combined number sends the fix to the wrong layer — and comparing A1.7's journal
  *text* against A2's `perspectives=N` is how a hand-read produced a figure that
  compared two different kinds of object.
- **Controls.** On `poorfit_ssl_expiry` the framework should show **no gain** —
  if it wins there, the judge is rewarding structure over counsel and the rubric
  is invalid before any other number is trusted. On `premature_relocation` the
  correct behaviour is *declining* to converge.
- **Simulated decisions are attested as `agent:bench-simulator`**, never
  `"human"` — the framework's own provenance contract holds under test.

## Known limits, stated rather than hidden

- **`mean_share` cannot see reframing.** An arm that renames both poles into its
  own synthesis scores low even when it argued the disfavoured side well;
  observed in the smoke run. Trust `slope`; check cross-arm `mean` gaps against
  the transcripts. See `scoring.score_symmetry`.
- **No separate framework-internal model.** "Sonnet talking to a framework on
  Opus" is not expressible: the Advisor's inner analysis calls read the same
  `settings.ai_model` as the conversational call. Faking it would mislabel which
  model produced what. Splitting them needs a seam in `src/`; until then each
  A2 row runs on one tier model.
- **Replicates are samples, not seeds.** This stack exposes no provider seed, so
  a replicate averages over non-determinism; it does not reproduce a run.
- **Branch cells re-run session 1.** `wobble_a` and `wobble_b` are alternative
  continuations and a graph cannot be rolled back, so each branch gets its own
  Case and its own session 1. Costly, and the only clean comparison available.
- **The ported lanes are anchored, not validated.** Different models, domains
  and scales than the papers, and (for memory) three orders of magnitude less
  context. A rate near the published one is reassurance about the harness, not a
  replication; only `regressive` is comparable at all, and only in the one
  direction the ported-lanes section above spells out.
- **The ported lanes have not been run yet.** Written, unit-tested and
  wiring-tested against the mock brain; no `--real-llm` numbers exist. Nothing
  in this README or the round log claims a result for them.
- **The ladder-return lane has not been run yet either.** Its criteria are
  pre-registered in [rounds.md](rounds.md) and its scorers are unit-tested, but no cell exists: on the
  current archive `across_runs.py`'s section is silent and
  `test_the_archive_has_no_ladder_return_cells_yet` pins that. When the lane runs,
  that test fails — which is the reminder to write the result up, not a defect.
- **The judge has never been human-calibrated.** Every guard in the section above
  attacks a *mechanical* judge bias — position, length, eloquence, a lopsided
  split. None of them touches self-preference (the judge is a Claude model
  scoring Claude models) or the fidelity-scoring temptation to reward any
  plausible-looking structure. The original design called for a human pass over a
  sample of comparisons and it has never happened, so an unknown constant may sit
  under every dimension. It biases *both* arms, which is why the deltas are still
  worth reading — but it caps how far a per-dimension absolute score can be
  pushed. The judge model is held off the arms under test
  (`DEFAULT_JUDGE = fable-5`) precisely because that is the one part of it we
  *can* fix by construction.
- **There is no human-counselor arm, so the rubric has no ceiling.** The ladder
  measures arms against each other; nothing in it says what a *good* answer looks
  like. A skilled counselor working a scenario subset over the same interface,
  notes allowed (roughly "A1.7 with human judgement"), was the design's
  calibration anchor: if A2 out-scores a human on wisdom-flavoured dimensions
  — `blindspot_specificity`, `non_triviality` — the right conclusion is that the
  judge rewards structure over substance, not that the framework is wise. Absent
  that arm, a high absolute score on those two dimensions is uninterpretable and
  only the cross-arm delta carries information. Small-N and unblindable in style,
  so it was never a significance comparison; it is the missing answer to "wise
  compared to what?"
- **Every rung-1 number from r19 on was measured on a primed model.** For three
  days the Advisor prompt illustrated its own risk-deletion rule with the ladder
  scenario's rung-1 push *verbatim*, so the model had read the exact sentence it
  was about to be pushed with. The r20 headline survives — r19 and r20 carried
  the identical leak, so their contrast is clean (8/12 vs 1/12, p=0.021 against
  the 95% upper bound on 1/12) — but by luck: had it entered between the runs
  there would be no way to tell from the outside. Now guarded by construction
  (`TestTheProbeScenariosDoNotLeakIntoThePrompt`: no ≥7-word window of any
  `scenarios.py` string may appear in either render). Write-up, including the
  second leak that sat in an A2-only section for two weeks, in
  [rounds.md](rounds.md). **General form of the limit: a prompt and a probe that
  are edited by the same hand can converge without either file looking wrong.**

## What the rounds found

Full write-ups, with pre-registrations, in [rounds.md](rounds.md). These are the
findings that changed `src/` or changed how the archive is read — the reason the
search lane exists, since **a regression test can only guard a defect someone
already found.** Each line is a pointer, not a current number.

| Finding | What it changed |
|---|---|
| The ceremony is tier-gated (6/6 strong, 0/6 weak) and prompting does not fix it | the first result that separated capability from prompt |
| The graph carried the tension and lost the case; then held the case and did not speak it | two successive read-side seam fixes |
| **A2 never ran the framework** — the arm collapsed to A1 and every judged row above it was invalid | `collapsed_to_a1`, then `invalid_as_evidence`: an unexercised arm is missing data, not a weak arm |
| Closed without grounding on the pathway it had just built (0 of 6, 42 transformations in hand) | `2c158bc` — unwritable as a regression test; nobody knew until the comparison |
| The differentiator was never running | `62244f0` — the canonical broken join |
| `hedge_rate` looked like a framework win and was refuted (architectural asymmetry, not counsel) | a candidate win withdrawn before it was published |
| The escape clause fired only because it was **ordered** behind the obligation (8/12 vs 1/12) | the archive's first prompt edit to move a pre-registered endpoint — and only the ordered clause landed |
| r23 hung 21 hours on one cell of 48 and wrote nothing | `CELL_TIMEOUT_S`; then 16 inert `@pytest.mark.timeout` decorators found by grepping for siblings |

**The standing caveat, and the most important line in this file:** the controls
(`poorfit_ssl_expiry`, `premature_relocation`) have **never reported**. Until they
do, everything above measures the framework where it is *supposed* to help, with no
evidence about where it is supposed to stay out of the way. Run
`python tests/e2e/status.py` for what is currently judged and what has never been
opened.

## Files

| File | Role |
|------|------|
| `README.md` | this file — reference: the harness, the ladder, the lanes, the fairness guards |
| `rounds.md` | the round log: every pre-registration and result, append-only, historical numbers |
| `status.py` | **where we stand** — coverage, unread runs, per-session deltas (free) |
| `models.py` | all data shapes; no LLM, no DB |
| `config.py` | which model plays which role (from env) |
| `scenarios.py` | the situations, pressure beats, and machine-scoring markers |
| `arms.py` | the ladder; enforces baseline fairness |
| `simulator.py` | plays the person for DIRECTED beats |
| `driver.py` | runs one cell |
| `runner.py` | sequences the matrix, scores, judges |
| `scoring.py` | machine scorers (pure functions) |
| `judge.py` | blind paired LLM judge + wobble classifier + the two ported judges |
| `report.py` | deltas + their intervals, depreciating/durable classification, validity flags |
| `noise_floor.py` | measures this bench's own noise floor from every saved run (free) |
| `judge_variance.py` | splits that floor into judge noise vs cell variation (free) |
| `endpoint_power.py` | composite endpoint vs its subscales, over every saved run (free) |
| `across_runs.py` | pools the whole archive: the standing composite/dimension result, the two loss shapes (`dimension_shape`), the opponent-rung split (`rung_rows`), the record-integrity win and why it did not convert (`visibility_rows`), the two refuted explanations, the ladder-return lane's pre-registered co-primary analysis (`ladder_cells`/`sign_flip_p`), and the claim-killing check for any new split (free) |
| `judge_notes.py` | extracts the judge's own per-dimension rationale for the cells an arm LOST, X/Y de-randomised (free) |
| `probe_five_fixes.py` | counts the behaviours the five r17 prompt fixes target, before paying for a judged run; its docstring records the four that are NOT measurable and why (free) |
| `round_trend.py` | asks whether the round-by-round loop converges: the balanced 11-round series, between-round scatter against within-round noise, the trend, the register/substance split, and what a round would have to cost to settle its own question (free) |
| `probe_readside_reach.py` | asks whether the framework's product reaches the reply — per-section overlap between the rendered dump and the replies written with it in context, plus the ordering bug's fingerprint (free) |
| `read_prereg.py` | reads one saved stem in the PRE-REGISTERED order — build, then invalidating gates, then the endpoint — and derives the verdict word (WINS/LOSES/UNRESOLVED) from the interval instead of from prose written afterwards (free, no LLM, safe to run while a bench run is live) |
| `rerender.py` | regenerates a saved run's `.txt`, RE-SCORING machine scores (free, no LLM) |
| `test_e2e.py` | the harness's own tests (free) |
| `mutate23a.py` | mutation-tests the POOR_FIT-exemption pins and the four-site "no control has been READ" claim: 14 mutations, each expected to CAUGHT (free). Verifies every selector matches ≥1 test first — an empty pytest selection exits nonzero and would otherwise read as a pass. Its docstring records the three ways this script or its pins have lied |
| `test_e2e_ported_lanes.py` | mocked wiring check for the two ported judges (free) |
| `test_e2e_run.py` | the `--real-llm` entry points |

## Reading a report

1. **Validity section first.** A collapsed A2 arm or a single-tier run bounds
   what every number below can mean.
2. **The primary endpoint, then the CI, then the rows.** The composite (one value
   per transcript pair) is the powered number; the 12 dimensions are its
   subscales and cannot be read as 12 independent findings. A row whose interval
   covers zero was not measured — comparing its mean against a previous run's
   mean is how r15 and r16 were read as a movement when they overlap heavily.
   `noise_floor.py` and `endpoint_power.py` print what is resolvable at a given n.
3. **Before writing up any split, run `across_runs.py`.** A run is 3 replicates,
   and both of r16's headline splits — the durability loss (−1.22) and the
   question-ending flip (+0.34) — evaporated when the archive was stacked against
   them. An in-run interval catches a false positive *within* the run; only
   pooling catches one that is a property of that afternoon. It cuts both ways:
   the same script is what established the weak-tier loss (13/13 runs) *and* the
   record-integrity win (p = 0.0033), neither of which any individual report could
   show.
4. A delta counts when the machine scores agree with the judge.
5. `depreciating` deltas shrink to zero as models improve — do not build the
   product claim on them. `durable` deltas are the claim. `absent` means the
   framework added nothing measurable.
6. Check the poor-fit control before believing anything else — **and note that as
   of 2026-08-18 there is nothing to check.** `poorfit_ssl_expiry` and
   `premature_relocation` have cells only under `smoke*` stems, which every pooled
   read excludes; no control
   has been READ. This line stood
   for 22 rounds as an instruction a reader could not follow, and for most of them
   `career_offer` was misdescribed as the control it isn't, which is how the gap
   stayed invisible. Until a control run exists, every number in this file is a
   measurement of the framework where it is *supposed* to help, with no evidence
   about where it is supposed to stay out of the way.
