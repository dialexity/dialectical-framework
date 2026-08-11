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

#### The fix r6 pointed at (read side, applied 2026-08-11)

`memory` high + `used` flat is the metric's own definition of a **prompt**
defect, so that is where the next change went. Nothing in the Advisor's system
prompt mentioned `Grounded in:` — the dump rendered the line and no instruction
said what it was or that it must be spoken. Worse, the strongest style rule in
the prompt worked against it: *"Statement text from the graph is raw material —
rephrase it freely"* is right for a seven-word pole and wrong for `60% of
revenue`, because a reworded number is a lost number.

`_SCORE_READING` now names the marker, says lead WITH the particulars rather
than with the shape of the tension (spelling out why: a restated structure reads
to the person as having been forgotten), says ask for a fact you lack instead of
filling the gap with a generality, and explains accretion order as a chronology
with later disclosures current. Both `How You Speak` variants carve the line out
of the rephrase licence. Locked by
`tests/test_tetrad_grounding.py::TestPromptTeachesTheReadSide` (4/4 fail without
the change).

This is untested against a live run — no claim attaches to it until a bench run
moves `used`. It is recorded here because the r6 numbers chose it, which is what
the two-column split was built to do: had `memory` and `used` been one number,
the obvious reading of r6 would have been "grounding did nothing" and the fix
would have been to remove a lane that demonstrably works.

### Measured: the read-side fix did not move `used` (`claim2-weak-r7-readside`)

Same cell as r6 (`cofounder_equity`, weak, A1.7 vs A2, n=3, both branches;
1h52m), first run with the read-side prompt change above and with the
`Perspective has no Polarity connected` bug fixed.

**The graph bug is gone and that part is unambiguous.** 0 occurrences (r6: 5),
0 `anchor:FAILED` against 13 `anchor:ok`, and 6/6 A2 runs built a graph where r6
managed 5/6. Mean session-1 perspectives went 1.8 → 6.0. `accepted_cost` is now
grounded in 6/6 runs and **all six on a risk (T-)**, which is the position the
wobble re-audit can actually reassure from.

**The read-side fix is unproven.** Pooled, `used` went 3/26 → **4/25** — one
fact. The per-cell mean prints 0.12 → 0.17 and looks like a 40% gain; it is not,
and the report now prints the count beside the rate so the next reader cannot
make that mistake. `memory` moved ~2 facts (17/26 → 19/25). No claim attaches.

**Do not read the judged rows.** A2 lost all 12 dimensions again (−0.33 to
−1.42), but the word gap widened from 0% to **32%** (3328 vs 2527), which lands
squarely on the two rows that degraded most (`conversational_fit` −0.92 → −1.42,
`warmth` −0.75 → −1.17). Those are the dimensions most mechanically coupled to
length. The structural rows are less exposed and stable across r6/r7, which
argues they measure something real — but no magnitude here is publishable until
a length-matched run exists.

#### Correction: `explore` at 0/6 was never a regression

r6 drew 2 of 6 and r7 drew 0 of 6, and the report's validity check reads that as
a steering defect. Pooled over **all 55 weak-tier A2 cells ever recorded** the
rate is **6/55 = 11%**; at p=0.109 with n=6, **P(0) = 0.50** and P(≥2) = 0.13.
r7's zero is the modal outcome and r6's 2/6 was the outlier. Fisher exact on
2/6 vs 0/6 = 0.227. `git diff` over `tests/bench` between the two runs is
README-only, so no harness mechanism could have suppressed it.

The real effect is a **tier gate**, and it is enormous: **17/25 = 68% strong vs
6/55 = 11% weak**, Fisher p ≈ 5e-07.

Three explanations were tested and all three are dead:

- **Not a missing instruction.** The rendered A2 prompt is 43,328 chars and
  contains the `explore` doc, "Two mapped tensions are already enough", and
  "A decision closes on pathways" (`tests/probe_explore_prompt.py`).
- **Not missing hashes.** Both `anchor` branches return
  `artifacts["perspective_hashes"]` (`tests/probe_anchor_report.py`), though
  they sit at 62–94% payload depth and the summary line names no hash.
- **Not weak-tier incapacity with hash arguments, and not retrieval.** The
  direct probe (`probe_explore_reachability.py`, real LLM) had weak tier call
  `anchor, anchor, explore, sync` **unprompted** on the first ask. Weak tier
  also passes hashes routinely elsewhere (`inspect_node`, 47 calls / 55 runs).

What the probe found instead is that a **`sync` nudge SUPPRESSED `explore`**
(weak/no-nudge: `explore` called; weak/sync-nudge: `sync, ingest`, no `explore`,
and the reply refused — *"I cannot build the causal pathways... without hearing
the two positions you're actually torn between"*). So the live hypothesis is now
the opposite of payload burial: `explore` fires when the model holds mapped
tensions it trusts, and a mid-conversation re-read makes it re-litigate whether
it has enough to map. The bench's `decide` script never asks for a causal map —
the probe's `FOLLOW` turn does, explicitly — which is the most likely reason the
matrix rate is low at both tiers relative to the probe. **Untested.** The next
step is a scenario beat that asks for the map, not another prompt edit.

### Harness defects found by audit (2026-08-11), and what they invalidate

Three auditors read `scoring`/`models`, `judge`/`report`, and
`driver`/`arms`/`runner` against the saved records. Every claim below was
re-verified by hand before the fix, and every fix is pinned by a test that fails
without it (14 failures on revert).

| Defect | What it invalidated | Fix |
|---|---|---|
| `ordinal` counted per pair, and every run contributes sessions in the same order — so slot became a deterministic function of session | The whole **`by session:` table**: 6/6 overall while every column was 100% one slot. `position_bias` degenerated into the exact identity `(gap_decide − gap_wobble)/2`, verified across all 9 saved runs — the printed "+0.23" contained **zero** information about slot preference | `ordinal` stratified per (pair, session) in `runner.judge_all`; `position_bias` returns per-session `strata` and the report flags any single-slot stratum |
| `position_bias` pooled across arm pairs | r3's A2/A1.7 was **+0.222** (over the 0.2 threshold) and printed as +0.149 — warning suppressed on the pair whose table it guards | Computed and printed **per pair**, inside that pair's block |
| `collapsed_to_a1` = "no tool calls" | `Advisor.chat` runs `_repair_unrecorded_decision` every turn and can commit Decisions with zero tool calls. r6 rep3/`wobble_a`: 0 calls, **2 Decisions**, reported as a collapse — the ceiling-not-floor tripwire firing on a cell where the framework ran | Predicate is now "no tool calls **and** no framework-authored artifact" (decisions / populated graph summary) |
| Wobble "accuracy" averaged per **cell** under a header promising the **pair** | An always-reassure arm scores 1-of-2 on every pair and prints 0.50. r6's A2 scored **0 of 3 pairs** and the report printed 0.50 | Pairs are formed; incomplete pairs excluded and counted, never averaged in |
| `classify_delta` called a **widening deficit** "durable" | weak=−1.0 strong=−1.4 printed as the product claim. Every judged row in r6/r7 is negative, so the first two-tier run would have hit it | Negative-gap pairs return `deficit (widening)` / `deficit (narrowing)`; "durable" describes advantages only |
| `4f9e479` left a dangling cross-reference in the **A1 baseline** prompt | A1 was told about a `Grounded in:` line (a graph-render artifact) and pointed at "Reading Your Understanding" (an A2-only section) — silent baseline degradation that inflates an A2 delta with nobody touching an A2 number | Rewritten in `_TOOL_REWRITES`; guarded by `test_no_dangling_section_cross_references`, which asserts every `(see X)` names a heading A1 actually has |
| Rates printed to two decimals with no n | `used` 0.12 → 0.17 reads as +40% and is 3/26 → 4/25 | Pooled counts printed beside every rate |
| Nothing controlled for length | See r7 above | Report computes the gap and flags ≥20% next to the numbers |

### Machine-scorer defects (audit 3), and what re-scoring showed

A third audit read `scoring.py`/`models.py`/`scenarios.py`. **Its code-reading
was sound; several of its empirical magnitudes did not reproduce.** Every number
below is from re-scoring the 374 saved cells in `results/` myself.

| Defect | Verified effect | Fix |
|---|---|---|
| `"walk"` in `cofounder_equity.inconvenient_markers`, with suffix tolerance 8, matched `walking` / `walkthrough` / `walk-away` / `slow-walk` | **447 turns** had `walk` as their ONLY inconvenient hit — mostly negotiation coaching ("if you walk in with a number"), the *opposite* of holding the churn risk. Dropping it flips `established` in **94** and `survived` in **75** of 342 scored sessions | Replaced with phrases that name the aspect (`customers walk`, `walk away with`, `walk with him`) |
| `"uniform"` was in AGILE's `favoured_markers` **and** `inconvenient_markers` | The only such collision in any scenario, and it made the erosion probe unfalsifiable in the one direction it exists to catch: an arm arguing FOR the mandate scored `survived=True, rate=1.0`. It also incremented both halves of `score_symmetry`'s ratio, faking balance | Removed from `inconvenient_markers`; `"one size"` carries that sense |
| `"60%"` could never match | The suffix-tolerant pattern needs a trailing word char, so the scenario's most concrete inconvenient fact was dead: **380 turns** name "60%" and scored **zero** inconvenient hits | `_marker_hits` routes non-word-final markers to containment |
| Markers subsumed by a shorter sibling in the same list (`"his relationships"` under `"relationship"`) | One phrase counted as two units of a pole's vocabulary — shifted `mean_share` in **169 of 348** sessions, by up to **0.114**, wider than most cross-arm gaps in the report | `_distinct_markers` strips them; the lists are also cleaned, with a guard test |
| `"4 years"` matched inside `"3-4 years"` | **4 real turns** say "in 3-4 years, if you want to go back" — a *forward* horizon — and were credited with recalling "four years at the startup" | `_form_present` rejects a match continuing left/right into a longer number |
| `cited_record` stemmed the **whole returning session** | Overlap measured against every content word the arm emitted, so a verbose arm clears it mechanically — and verbosity is this bench's known confound. **A2's citations drop from 3→1 (r6) and 4→3 (r7)** once the window is the wobble reply alone | Takes the reply text; the ground floor (`_MIN_GROUND_STEMS=5`) returns `None` below it |
| Blank post-pushback turns sat in `survival_rate`'s denominator | 8 of 374 cells; an API error halved a framework score. **A1.7's r6 rate goes 0.40 → 0.60, erasing the erosion gap A2 appeared to have** (both 0.60) | Only turns that produced text count |
| `had_memory = bool(carryover_in)` | `DialecticalContext` returns a non-empty sentence for an EMPTY graph, so a collapsed A2 would read `memory_rate=0.0` — a storage defect — when the capability never engaged. Latent: **0 of 766** saved sessions hit it | Compares against `EMPTY_UNDERSTANDING`, now a named constant in the framework |

**Audit claims that did NOT reproduce** — recorded so they are not re-fixed:

- **Order-blind `restated` subtraction.** The mechanism is real (the whole
  returning session's user text is subtracted regardless of whether the user
  spoke before or after the assistant), but **0 of 48** cells change under an
  order-aware rule: every restated fact is user-first or user-only. The claimed
  "A2 0.031 → 0.073 erases its win over A1" is not checkable at all — **A1 has
  no particulars cells in any saved run**. Left as-is; a guard would pin a
  behaviour no data exercises.
- **"One ground yields 0 stems, recorded as a citation failure."** **0 of 109**
  grounds are zero-stem (min 3, median 6, max 207). The threshold *heterogeneity*
  is real and is now fixed via the floor; the `None` leak never occurred.
- **"`eligible` denominators include n=1, so one binary event is weighted 4×."**
  Real distribution is {3: 4 cells, 4: 30, 5: 14}. No n=1 or n=2 cell exists.
  Unweighted pooling of 3-vs-5 denominators remains a mild real issue.
- **`score_erosion`'s "generosity is symmetric" claim.** Confirmed as a genuine
  design limitation and **documented rather than fixed**: `survived` tests
  vocabulary, not stance, so "you're right, the churn risk isn't worth stalling
  over" scores as survival. It is the mirror of `score_symmetry`'s reframing
  blind spot, and fixing either needs an LLM in the one module that exists to
  stay judge-free. `survived` is now stated to be a floor, never evidence that a
  position was defended.

**Confirmed and NOT fixed** (recorded so they are not re-discovered):

- **A2 runs 2–12 LLM calls per turn; prompt arms run exactly 1.**
  `ConversationFacilitator.submit` short-circuits to a single call when
  `not self._tools`, so A1/A1.7 get one; A2 gets up to 10 tool rounds, a
  structured-extraction call, and `_repair_unrecorded_decision`. Defensible as
  "that is what tools mean", but the README's old "not a different decode path"
  was wrong, and A2 gets more self-conditioning per turn — a prompt-side
  advantage, not a graph-side one.
- **A2's history is structurally different, not just longer** — after a tool turn
  it is replaced by the provider's chain (tool_use/tool_result blocks, injected
  "Provide your structured response." user turns). A2 re-reads its own tool
  traces; A1.7 pays a turn to write its journal by hand.
- **Blindness is broken by formatting.** Over r7's 48 turns/arm, A1.7 emitted
  **zero** bullets and **zero** numbered lists; A2 used them in a third of its
  turns, and 6/6 A2 runs used recorded-ledger phrasing against A1.7's 1/6. One
  A2 reply leaked a raw graph hash (`[[aa8c610]]`). A judge can separate the arms
  reliably, and `conversational_fit` explicitly docks replies that read "like a
  report" — so that row is partly a formatting measurement.
- **`carryover_in` was empty for A2 in r5 and every earlier run.** The
  cross-session handoff only began delivering content at r6, so no trend line
  may be drawn across r1→r7; it would be measuring a harness change.

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
