# Bench — does the framework beat a plain prompted LLM?

A falsifiable harness, not a demo. It is built to be *able to report that the
framework adds nothing* — if it could not, a positive result would mean nothing.

Design spec: `docs/r-n-d/judged-eval-vs-prompted-llm.md` (gitignored).

## The two claims

| Claim | What it asserts | Honest opponent |
|-------|-----------------|-----------------|
| **1 — Reasoning discipline** | Enforced dialectical structure produces better in-session counsel than a model self-applying the same method | **A1** (the real method text, no tools) |
| **2 — The institution** | A typed decision record beats a prose memory when the user comes back wobbling | **A1.7** (the model's own journal, verbatim) |

Claim 1 is expected to be **depreciating** — as base models improve, they
self-apply the method better and the gap shrinks. Claim 2 is the durable one, if
either is. The report classifies each delta rather than reporting a win rate,
which is why ≥2 tiers matter.

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

## Run it

Requires Memgraph (`docker compose -f docker-compose.test.yml up -d`) and
Bedrock credentials in `.env`. Everything spends real money — `--real-llm` only.

```bash
# free: the harness's own unit tests (no LLM, no DB)
poetry run pytest tests/bench/test_bench.py

# cheap end-to-end smoke: 1 scenario, 1 tier, A1 vs A2, no judge (~7 min)
poetry run pytest tests/bench/test_bench_run.py::test_bench_smoke --real-llm -s

# the full matrix
poetry run pytest tests/bench/test_bench_run.py::test_bench_matrix --real-llm -s
```

`-s` matters: a matrix run takes hours and the progress lines are the only way
to watch it.

### Selective runs

Everything narrows by env var, so a finding can be re-checked without
re-spending the matrix:

| Var | Default | Example |
|-----|---------|---------|
| `DIALEXITY_BENCH_ARMS` | `A0,A1,A1.7,A2` | `A1,A2` |
| `DIALEXITY_BENCH_SCENARIOS` | all | `cofounder_equity,agile_process` |
| `DIALEXITY_BENCH_TIERS` | `weak,strong` | `weak` |
| `DIALEXITY_BENCH_REPLICATES` | `1` | `3` |
| `DIALEXITY_BENCH_BRANCHES` | all declared | `wobble_a` |
| `DIALEXITY_BENCH_JUDGE_OFF` | unset | `1` (machine scores only) |
| `DIALEXITY_BENCH_STEM` | `matrix` | `claim2-recheck` |

```bash
# just the wobble arm, both variants, one tier — the Claim 2 probe alone
DIALEXITY_BENCH_ARMS=A1.7,A2 \
DIALEXITY_BENCH_SCENARIOS=cofounder_equity \
DIALEXITY_BENCH_TIERS=weak \
poetry run pytest tests/bench/test_bench_run.py::test_bench_matrix --real-llm -s
```

Model choices also come from the environment (`DIALEXITY_BENCH_TIER_WEAK`,
`_TIER_STRONG`, `_SIMULATOR`, `_JUDGE`) — see `config.py`. Never put credentials
or account-scoped ARNs in committed files.

Output lands in `tests/bench/results/` (gitignored). The runner saves records
**before** judging, so a judge crash — or a judge *bug* — never costs a re-run:

```bash
# re-judge saved transcripts. minutes and cents instead of hours.
DIALEXITY_BENCH_REJUDGE=decision-strong-r4 \
poetry run pytest tests/bench/test_bench_run.py::test_bench_rejudge --real-llm -s
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
conclusion. The guards, each with a test in `test_bench.py`:

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
  8-of-12-dimension A2 "win" on a 10/2 split.
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

## Measured: the ceremony is tier-gated, and prompting does not fix it

The clearest repeatable result so far is not a delta — it is a **capability
threshold**, and it bounds every Claim 2 number at the weak tier.

Same prompt, same tools, same scenario, `record_decision` firing rate:

| Tier | model | runs recording ≥1 decision | wobble accuracy |
|------|-------|---------------------------|-----------------|
| strong | `claude-sonnet-5` | **6/6** (`decision-strong-r3`) | A2 5/6, A1 3/6 |
| weak | `claude-haiku-4-5` | **0/6** (`claim2-weak-r2`, `-r3`) | A2 3/6, A1.7 6/6 |

The weak tier fails the same way every time: asked to "write that down", it
writes a beautifully formatted **"Your Decision"** section in prose, with
`tool_calls == []`. The person is told it is recorded. It is not. Session 2 then
opens with an empty ledger, so variant (a) — "reassure me from the record" — has
no record, `reopen` is the only honest answer, and the judge scores it wrong.
**One defect was being counted as two**: `wobble_a_without_a_record` and
`prose_only_decision` in `models.py` now separate them, which is why the r3
validity section names the cause instead of leaving a bad convergence number to
be misread as the re-audit failing.

Three rounds of prompt strengthening were spent on it, and are worth recording
as **negative results**, because each looked like the obvious fix:

1. `_DECISION_READINESS` prose — "Writing the record out is not recording it",
   "is a MESSAGE", "not alternatives". Verified present in the rendered prompt.
   Weak tier: no change.
2. The `record_decision` **tool docstring** and `_TOOL_DOCS` entry — the
   asymmetry was real (the text nearest the call carried only the prohibition,
   "never call this speculatively", which a weak model reads as "when in doubt,
   don't"), so the obligation now sits there too (77930f6). Strong tier is
   unaffected because it already complied. Weak tier: no change.
3. The `explore` **call threshold** in its tool doc — "two mapped tensions are
   already enough", since a decision closed without `explore` cannot carry an
   `adopted_pathway` and so has no recipe half (71be246). Weak tier: 2/2 still
   never called `explore`.

The general lesson that did generalise: **when a prompt rule governs whether to
CALL something, it belongs in the tool doc, not only in a prose section** — a
rule ~100 lines below the tool list loses to the docstring at call time. It is
in the systemic map. It just is not sufficient here.

### Fixed in code, and the number moved (`claim2-weak-r4`)

The prompt layer was the wrong layer. A decision is a **user-driven artefact** —
it exists because the person declared it, and that declaration is an *observable
event in their message* — so `DecisionConfirmationCheck` +
`Advisor._repair_unrecorded_decision` now write the record whenever the person
confirmed one and the model didn't (`docs/agents.md`; framework-side, so every
host gets it). What r4 measured, same tier, same scenario, n=3:

| | r2/r3 (prompt only) | r4 (with the seam) |
|---|---|---|
| runs recording ≥1 decision | **0/6** | **6/6** |
| `wobble_a` convergence | **−2.67** | **−0.33** |
| `wobble_a` decision_closure | **−2.67** | **0.00** |
| `wobble_a` earned_confidence / entanglement / non_triviality / tension_coverage | negative | **+0.33 each** |

3 of 6 runs still closed in prose — the seam caught all 3, which is the point.
The `wobble_a` misattribution is gone: those rows now measure the re-audit
instead of a missing record.

**It is still not a win, and the remaining gap is honest.** Two things sit
between here and a real Claim 2 result, and both are visible in the r4 validity
section rather than inferred:

1. **The record exists but is mostly empty.** `accepted_cost` 2/6,
   `adopted_pathway` 1/6, COMPLETE records **0/6**. The repair deliberately
   guesses no grounds (a fabricated `accepted_cost` invents the very
   confrontation the ledger reports), so a repaired record secures *existence*,
   not *substance* — and reassurance at wobble time needs the substance. Read the
   `wobble_a` transcripts: A2's replies are *correct* — they faithfully audit a
   record that does not contain the cost, which is why they call "reopen". The
   machine scorer marks that wrong against the scenario's intent, and it is right
   to: the arm cannot reassure from a record with nothing in it.
2. **5/6 still never called `explore`**, so the pathway half has no source at
   all. That flag has survived every prompt fix aimed at it.

`wobble_b` now carries the loss (decision_closure −2.00, convergence −1.67) —
but A2 called `reopen` correctly **3/3** there by machine score, so judge and
machine disagree, and this report's own rule is to trust the machine. Worth
re-judging before treating that row as a finding.

What this means for the product claim, stated plainly:

- **Claim 2 was not measurable at the weak tier by prompting alone.** The
  institution cannot beat a prose journal in a run where the institution was
  never written to. Weak-tier A2-vs-A1.7 rows from r2/r3 measure a non-firing
  ceremony; they are not evidence about the record. r4 is the first weak-tier row
  where the record exists in every run.
- **Existence was the first blocker; substance is the next.** The seam fixed the
  0/6, and the `wobble_a` numbers moved with it. But COMPLETE records are 0/6, so
  the re-audit still has little to point back to — and the two missing halves have
  different causes: `accepted_cost` needs the model to identify the chosen side's
  minus (a real judgement, correctly left to it), `adopted_pathway` needs
  `explore` to have run at all (a steering problem that has resisted three prompt
  fixes).
- **The next thing to try is not more prompt text.** The lesson that generalised
  from the ceremony is that a rule governing whether an observable user event gets
  persisted belongs in code. Whether the same reasoning applies to `explore` is a
  genuine design question — unlike a confirmation, "there is enough structure to
  build pathways from" is not an observable user event, so it is not obviously the
  same fix. That needs review before it is built.
- Still **not a framework win**. What the harness has produced so far is one
  framework limitation found and closed, with the measurement to show the close
  worked, and a clearly-named remaining gap.

### Measured: the graph carries the tension and loses the case (`claim2-weak-r5`)

A tetrad's text is **universal by construction**, and that is not a defect:
`component_length` caps every pole near seven words, `commit()` folds matching
wording into one shared node, and taxonomy anchoring pulls each aspect toward a
`SYSTEMIC_TAXONOMY` apex. Transferability is the point. But counsel memory needs
the opposite thing — the 45%, the March feedback, the three-week holiday — and
those are exactly what the abstraction strips.

So `scoring.score_particulars` measures it, and the report prints **two**
columns per cell:

| column | question | a low number means |
|---|---|---|
| `memory` | was the fact in the artifact the session was HANDED? | **storage** defect — the carryover never held the person's case |
| `used` | did the reply actually reference it? | **prompt** defect — it was there to read and the reply generalised anyway |

Denominator discipline, all three enforced by tests:

- Only facts the **person stated** in the base sessions count. An arm that
  invents "60% of revenue" and remembers its own inference has demonstrated
  nothing about their case.
- Facts the person **re-states** in the returning session are subtracted. The
  wobble openers repeat some verbatim, and echoing them back is transcript
  reading, not memory.
- `memory` is `None`, never `0`, for arms that carry nothing (A0/A1) — absence
  of capability, same rule as `cited_record`.

Re-scoring r5's saved transcripts (free — `BenchRun.load` + `score_machine`, no
model calls):

| | `memory` | `used` |
|---|---|---|
| A1.7 (prose journal) | **~3/4 per cell** | **0–1/4** |
| A2 (graph) | not recorded before this metric existed | **0/N in 6 of 6** |

**This corrects a hand-read.** The figure carried in earlier notes — "the graph
ledger carried 0 of 15 particulars against A1.7's journal at 11 of 15" —
compared one arm's *artifact* against the other arm's *replies*, because
`SessionRecord` stored A1.7's journal text but only `perspectives=N` for A2. A
count says nothing about whether the case is inside. `carryover_in` now records
what every arm was handed, on one field, so the two are the same kind of object.
What survives the correction is narrower and more useful: **both** arms use
almost none of their memory in the reply, and A1.7's journal at least *holds* the
particulars while nothing yet establishes that a graph dump does.

That is what the grounding lane (`ROLE_GROUNDING` on the EXPLAINS edge, see
`docs/graph.md`) is for, and this metric is how the next run answers whether it
worked. **No win is claimed here** — the metric is instrumentation, and it has
not yet been run against a graph built with grounding.

### Measured: the graph now holds the case, and still does not speak it (`claim2-weak-r6-grounding`)

First run with the grounding lane live (same cell as r5: `cofounder_equity`,
weak tier, A1.7 vs A2, n=3, both wobble branches; 1h23m). What the graph
carried, verbatim from a `ROLE_GROUNDING` Rationale:

> 60% revenue from two accounts. User can access both CEOs within a week.
> Cofounder holds 45% equity. Cofounder took 3-week holiday during launch;
> sales notes chaotic. User assesses relationships as transactional.

| | `memory` | `used` |
|---|---|---|
| A1.7 (prose journal) | **0.92** | **0.11** |
| A2 (graph + grounding) | **0.62** | **0.12** |

**Storage moved; behaviour did not.** A2's `memory` went from *unrecordable* to
0.62 — 3–5 particulars per cell in 5 of 6 cells, where the abstraction had
previously left nothing. But `used` is a dead heat, ~0.11 both arms: **both**
arms hold the person's facts and neither says them out loud. That is the
two-column split earning its keep. A grounding lane can only move `memory`, it
did exactly that, and the remaining gap is a prompt problem — the counsel dump
renders `Grounded in:` on every turn and the replies still generalise.

`45%` and "messy sales notes" appear under "no reply referenced" while sitting
verbatim in the grounding text above. That is not a matcher bug: that callout
reads `used`, and the `held` count beside each label now says so explicitly.

**A2 lost every judged dimension** (−0.42 to −1.33) on a clean −0.06 position
split with near-identical word counts (2637 vs 2632) — and per this file's own
rules that number is unreadable, because a third of the cells were structurally
broken:

- 1 of 6 A2 runs built **no graph at all** (invalid as A2 evidence; it is also
  the `0/3` particulars cell).
- 1 `anchor` call returned `FAILED — 5 polarities, 0 perspectives`, every
  tension lost to *"Perspective has no Polarity connected"*. A framework bug on
  the thesis-only branch, which r4/r5 never took even once.
- 3 of 6 closed a decision in prose without `record_decision` (the tier-gated
  ceremony defect, again).
- 3 of 5 never called `explore`; `adopted_pathway` 0/6, COMPLETE records 0/6.

Two machine scores did favour A2 and are worth more than the judge rows:
**sycophantic erosion 5/6 survived vs A1.7's 3/6**, and symmetry `slope` flat or
negative in 5 of 6 (A1.7 drifts positive in 5 of 6). A1.7 still wins wobble
accuracy 6/6 vs 3/6 — driven by the missing-record defect above, not by the
re-audit.

**Still not a win.** What r6 establishes is narrower and real: the framework's
memory can now hold the person's case at all, which it demonstrably could not
before, and the next blocker is one layer up from storage.

### Known limits, stated rather than hidden

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

## Files

| File | Role |
|------|------|
| `models.py` | all data shapes; no LLM, no DB |
| `config.py` | which model plays which role (from env) |
| `scenarios.py` | the situations, pressure beats, and machine-scoring markers |
| `arms.py` | the ladder; enforces baseline fairness |
| `simulator.py` | plays the person for DIRECTED beats |
| `driver.py` | runs one cell |
| `runner.py` | sequences the matrix, scores, judges |
| `scoring.py` | machine scorers (pure functions) |
| `judge.py` | blind paired LLM judge + wobble classifier |
| `report.py` | deltas, depreciating/durable classification, validity flags |
| `test_bench.py` | the harness's own tests (free) |
| `test_bench_run.py` | the `--real-llm` entry points |

## Reading a report

1. **Validity section first.** A collapsed A2 arm or a single-tier run bounds
   what every number below can mean.
2. A delta counts when the machine scores agree with the judge.
3. `depreciating` deltas shrink to zero as models improve — do not build the
   product claim on them. `durable` deltas are the claim. `absent` means the
   framework added nothing measurable.
4. Check the poor-fit control before believing anything else.
