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

**Where it stands, pooled over the whole archive (2026-08-13): the framework arm
loses at the weak tier and the loss resolves — composite −0.47, CI [−0.64,−0.31],
negative in 13 of 13 runs.** The strong tier is ~7× smaller (−0.06) and does not
resolve at n=4. Neither claim is currently supported, and the one that could still
be is the strong-tier one — [full numbers below](#the-archive-wide-picture-the-weak-tier-loss-is-real-and-it-resolves).

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
DIALEXITY_BENCH_ARMS=A1.7,A2 \
DIALEXITY_BENCH_SCENARIOS=cofounder_rebuttal_ladder,cofounder_memory \
DIALEXITY_BENCH_TIERS=weak \
poetry run pytest tests/bench/test_bench_run.py::test_bench_matrix --real-llm -s
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
| `DIALEXITY_BENCH_SCENARIOS` | all | `cofounder_equity,cofounder_rebuttal_ladder` |
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

### The finding that invalidates every judged row so far: A2 never ran the framework

Before any scorer or judge defect matters, this does. Reading the tool traces of
the 6 `claim2-weak-r7-readside` A2 cells:

| Cell | Tools called | `graph_summary` |
|---|---|---|
| all 6 | `anchor` ×1–3, plus `sync` / `inspect_node` / `record_decision` | `perspectives=5..7 decisions=1..2` |

**`explore` was called zero times.** Zero nexuses, zero cycles, zero wheels,
zero transformations, zero syntheses — across all six. So r7 compared **`anchor`
against a prompted LLM**, not Structured Dialectics against a prompted LLM. The
tetrad is the framework's *unit*; the pathway, the transformation and the
synthesis are its *product*, and none of the product existed in any cell a judge
scored. Every negative judged row in r5/r6/r7 was collected from an arm running
with its differentiator switched off.

This also retires the earlier framing in this file. I wrote that "the framework
does not win." The defensible statement is narrower: **we never turned it on.**

Rate across every saved run: `explore` fires in **6/55 weak-tier runs (11%)** vs
**17/25 strong (68%)** — Fisher p ≈ 5e-07. The same tier-shaped signature as
`record_decision` before its repair, and the same diagnosis: not capability
(`probe_explore_reachability.py` shows the weak tier calling `explore`
unprompted when a turn asks for a causal map) but **election**, at the moment the
model is most inclined to simply answer well. The `decide` script's beats (opener
→ deepen → pushback ×2 → ask_advice → commit) never ask for a map, so nothing in
the run forces the election.

**Fixed in code, not in the prompt** (2026-08-11), because
`_DECISION_READINESS` had *already* mandated it in prose — "A decision closes on
pathways, not on tensions alone… `explore` what you have before the ceremony" —
and was ignored anyway; a fourth round of strengthening was not going to be the
first one that worked. `Advisor._ensure_pathways_before_closing` weaves the
unwoven perspectives once a confirmed decision is closing, before the record is
written. Same seam and same ranking as the decision repair (see the systemic map
entry for scope, idempotence, ordering and the floor — which was `< 2` here and
was itself a bug; see "The floor was the bug" below).

#### Measured after the fix (`claim2-weak-r8-pathways`, 2 cells, judge off)

| | r7 (6 A2 cells) | r8 wobble_a | r8 wobble_b |
|---|---|---|---|
| `explore` called | 0/6 | yes (model's own) | no |
| decisions recorded | 3/6 | 2 | **0** |
| `adopted_pathway` ground | **0/6** | **1** (`T1 → T2, T2 → A1, A1 → A2, A2 → T1`) | 0 |
| COMPLETE record (risk cost + pathway) | 0/6 | **1** | 0 |
| duration | 404-2007s | 2532s | 1924s |

So the first complete record the bench has ever produced — but note what
produced it: in wobble_a the MODEL called `explore` itself, which means
`record_decision` succeeded, which means the repair returned early and **the new
seam never ran**. The cell that needed the seam (wobble_b, 6 tensions, prose-only
closing) recorded nothing at all.

Two findings, both acted on:

1. **The seam was gated on the wrong branch.** Placing it after the
   "already recorded" early return skips every turn where the model records the
   decision itself — and that is the LARGER population: across every saved A2
   cell, `record_decision` ran WITHOUT `explore` **50** times against 48 with
   both. It now also fires on the recorded branch. *(Called "weaker there: the
   written record can no longer take an `adopted_pathway`" until 2026-08-13 —
   that was false, and it cost r16 its grounds. See the r16 section.)* Pinned by
   `test_a_model_recorded_decision_still_gets_pathways`.
2. **Weaving does NOT cost the record** — the obvious suspicion, since the seam
   now sits between the confirmation verdict and `RecordDecision`. Tested
   directly on the weak tier with the r8/wobble_b shape seeded
   (`tests/test_pathways_seam_real_llm.py::test_weaving_first_does_not_cost_the_record`):
   2 perspectives woven AND the decision recorded, same turn. The seam itself is
   verified end-to-end too — `0 → 2` woven perspectives on a real weak-tier run.

**wobble_b's missing record is still unexplained, and it is an observability
gap, not a mystery worth guessing at.** Replaying that exact turn's classifier on
that exact tier returns `confirmed=True, is_recordable=True`
(`probe_confirmation_on_r8_wobble_b.py`), so the loss is downstream of the
verdict; every downstream branch is guarded and reproduces correctly under test.
The remaining candidate is a transient provider fault inside a fail-soft
`except`.

**Fixed in the harness** (2026-08-11): `TurnRecord.swallowed_errors` now captures
every ERROR the `dialectical_framework` logger emits during a turn, and the report
prints them as a VALIDITY flag. Every `except: logger.exception(...)` in `src/` is
deliberate — a graph fault must not break a live conversation — and the cost was
that a turn which lost a decision record, a pathway or an entire exploration read
as perfectly healthy: reply present, `error` None, every tool `ok`. That is
precisely wobble_b's state. An empty list is now a real finding ("nothing was
swallowed"), and a populated one says to stop reading the scores as reasoning
quality. Runs recorded before this exists cannot be diagnosed retroactively,
r8/wobble_b included.

Also measured: pathway construction is expensive. wobble_a took 2532s against
r7's 1271s for the same branch. Latency was never a claim, but a re-run of the
full matrix now costs roughly twice what it did.

#### A framework bug the bench caught next, in the BASELINE (2026-08-11)

`claim2-weak-r9-pathways-judged` was abandoned after two cells because its first
line was:

```
[weak] cofounder_equity r1 wobble_a A1.7 done: 116.1s
  !! 3 TURN ERROR(S): simulator: ProviderError:
     Error code: 503 - {'message': 'Bedrock is unable to process your request.'}
```

A transient 5xx matched neither retry predicate in `utils/use_brain.py` —
`_is_connection_error` keys off exception class names, `_is_rate_limit_error` off
429/Throttling — so it reached the bare `else: raise` and was **not retried at
all**. One provider blip killed three turns.

The direction is what makes this urgent rather than merely annoying: the losses
landed in **A1.7, the baseline**. A silently degraded baseline inflates every
framework-vs-baseline delta with nobody touching a framework number — it
manufactures a win instead of hiding one. Any A1.7 row from r9 is unusable, which
is why the run was killed rather than caveated.

Fixed with `_is_transient_server_error` + a separately bounded retry branch
(`_SERVER_RETRY_MAX = 3`, 5s doubling), deliberately not matching 4xx (our bug —
retrying wastes budget and buries the cause) and leaving 429 on its own longer
curve. Pinned by `tests/test_llm_transport_resilience.py`
(`TestTransientServerErrorDetection`, `TestServerErrorRetryLoop`), including the
verbatim message-only shape above, since the status code never appears as an
attribute on it.

Note the sequencing: the swallowed-error harness above catches faults the
framework hides from itself, and this one was visible in the log all along. Both
failure classes are now instrumented, and no judged run should be read from
before either fix.

#### `claim2-weak-r10-pathways-judged` — the first readable judged run, and A2 loses

First judged run with the 503 retry and the swallowed-error capture in place.
A1.7 vs A2, weak tier, 3 replicates, 6 cells per arm, 1h51m.

**The confounds that invalidated earlier rows are gone.** Verbosity is matched
(A2 2726 words/run vs A1.7 2805 — the earlier runs' 2x gap is what made every
prior judged row unreadable). Swallowed framework exceptions: **0**. No turn
errors. So the deltas below are not artifacts of a degraded arm.

**A2 loses every judged dimension**, worst on `conversational_fit` (−1.33),
`cross_turn_coherence` (−1.17), `convergence` and `decision_closure` (−0.92).
Machine scores are less lopsided: wobble accuracy ties 2/3, erosion is slightly
better for A2 (4 of 6 cells ≥ 0.5 vs 3 of 6), symmetry mean slightly worse.

Three findings, in descending order of how much they explain:

1. **The silent-framework contract was broken, and `conversational_fit` was
   measuring that.** 15 machinery leaks across the 6 A2 cells against 1 in A1.7 —
   labelled tables (`**T+: Solo leadership with unified strategic vision**`) and
   the machinery as an actor ("which the framework flagged as avoidance"). Being
   handed a position table is a worse conversation whatever the reasoning behind
   it. Now measured on output (`score_machinery_leak`, a validity flag) and
   partly fixed: a concrete counter-example in `_HOW_YOU_SPEAK` took a real
   weak-tier probe from 15 hits to 1. Not yet zero — see
   `tests/test_machinery_silence_weak_tier.py`.

2. **A2 remembers everything and says none of it.** `memory` 1.00 (24/24 of the
   person's own particulars were in the carryover) against `used` 0.04 (1/24
   referenced in a reply); A1.7 is 0.92 / 0.12. Three facts — the founder's 55%,
   the messy sales notes, the three-week holiday during the launch — were held in
   memory in every eligible cell and spoken in none. By the report's own
   two-column rule this is a PROMPT defect, not storage: the case was there to
   read. This is the strongest candidate for the actual cause of
   `cross_turn_coherence` −1.17, and it is not addressed yet.

3. **The pathway seam works; the ceremony still doesn't complete.** 6/6 runs
   recorded a decision (against 0/6 in r7) with 6/6 risk-grounded costs — the
   repair seam is doing its job. But `adopted_pathway` is 0/6 and therefore
   COMPLETE records are 0/6, *including the cells that called `explore`
   themselves*. A pathway exists and the model never grounds the decision on it.

**Finding 2 is now addressed by placement, not more prompt** (2026-08-12,
uncommitted at r10 time, in the tree for r11). The read-side instruction was
already long and emphatic with a worked example, and `used` was still 0.04 — so
the diagnosis is not "the model wasn't told". What the model was reading: one
`Grounded in:` line per tetrad, buried mid-block behind `insight=`/`HS=`/`Ks=`/
`DV=`/`area=`, landing between **14% and 95%** of the way through the dump, and
repeated across up to **7** near-duplicate lines. `DialecticalContext.
_dump_case_particulars` now opens both dumps with a `# The Person's Case`
section — deduped by exact text, oldest-first, near-duplicate wordings both kept
(dropping one reads as a forgotten fact). The per-tetrad line stays: the hoisted
section says what you know about this person, the in-block line says which
tension rests on which fact. This is the framework's own "prune, don't instruct"
rule turned on its own prompt. **It is not verified yet**: a context change is a
claim about the reply, so `used` has to be re-measured on the weak tier before
this counts as a fix — and r10's A2 rows carry both this defect and the machinery
leak, so r11 cannot attribute a movement to either alone.

**Finding 3 had a cause that no prompt could have fixed** (2026-08-12). The
seam works — 6/6 decisions, 6/6 risk-grounded costs, 5/6 cells with woven
pathways — and `adopted_pathway` was 0/6 anyway, *including the cells that
explored themselves*. `ExplorationPipeline` reported `transformation_count` and
no hashes, so a model told "12 transformations" had nothing to pass. Unlike
`record_decision` and `explore`, this was never an election failure: the ground
did not exist in the tool's output. `explore` and `deepen` now return a
`pathways` artifact — hash + edge + Ac+/Re+ recipe per line, since a bare hash
list is not a menu — sourced from `.all` rather than `.new` (the reuse case is
the likely one, and reading `.new` reports zero pathways for a fully developed
wheel) and deduped across wheels. All five tool docs that govern passing the
ground now name it. **Unverified**: whether the model passes the role is a bench
question, measured by `adopted_pathway_grounds` per record.

**A retraction about r10's own validity block:** it reported "4/6 live A2 runs
never called explore", which was wrong. That flag read `tool_calls`, and the
closing seam calls `run_exploration` directly — 5 of 6 cells did build nexuses.
`graph_summary` now reports `woven` and `transformations`, and the flag reads the
graph (`wove_no_pathway`). Verified against a real graph: `woven=0 → 2`,
`transformations=0 → 12` across the seam.

#### `claim2-weak-r11-particulars` — unjudged, and its A2 rows are not readable

The re-measurement of the hoisted `# The Person's Case` section (finding 2
above). A1.7 vs A2, weak tier, 3 replicates, 6 cells per arm, no judge. Read the
validity section and stop: **three of the six A2 cells contain `anchor` calls
with no recorded outcome at all**, and that is the signature of a tool that
RAISED, not one that declined to run.

| cell | mutating calls | outcomes | graph |
|---|---|---|---|
| rep1 `wobble_a` | anchor ×3, record_decision | anchor:ok ×2, record_decision:ok | perspectives=1 |
| rep1 `wobble_b` | anchor ×2 | *(none)* | **perspectives=0** |
| rep2 `wobble_a` | anchor ×4, record_decision | anchor:ok ×3, record_decision:ok | perspectives=6 |

Why it was invisible in both directions: Mirascope catches the exception inside
`Tool.execute` and returns `str(e)` as the tool's result, so (a) no framework
logger ever saw a traceback, and (b) the recorded `report` was `None` — the same
value `sync` and `inspect_node` legitimately produce — so `last_tool_outcomes`
skipped it as a read-only call. The record therefore showed an attempt, an empty
graph, and nothing in between: exactly the shape that reads as "the model chose
not to build". Fixed (`ToolResult.error` + an ERROR-level log line +
`<tool>:RAISED — <error>` in the validity section); the underlying exception is
still unidentified, which is what the fix makes identifiable on r12.

**So the `memory` movement cannot be attributed yet.** The report prints A2
`memory` 0.65 (13/23) against r10's 1.00, but rep1 `wobble_b` is the crashed
cell (`--`, `carryover_in` = `EMPTY_UNDERSTANDING`, 54 chars, plus this run's one
swallowed `GQLAlchemyError`) and rep3 `wobble_b` scores 0/4 with **zero
`Grounded in:` lines written at all**. Grounding-line counts across the six
cells: r10 `3,6,5,6,7,1` vs r11 `0,0,0,4,5,0`. The regression is in *writing*
groundings, not in rendering them — `_dump_case_particulars` correctly renders
nothing when there are no facts, and it demonstrably works in the four cells
that have them (`# The Person's Case` at the top with particulars intact).
`_ground_tetrads` fails soft at `logger.warning`, below the bench's ERROR
capture threshold, so it too left no trace.

What can be said: `used` moved 0.04 → 0.12 (1/24 → 3/23 facts), which is **two
facts** and inside noise; the hoist is neither confirmed nor refuted. Machinery
leaks fell 15 → 4 (3 A2 hits). `adopted_pathway` is 0/6 but the run predates
`068f645`, so that row measures the old tool output and must be re-measured.
New finding worth its own fix: **4 of 6 A2 runs closed a decision in prose
without calling `record_decision`** — the person was told it was written down and
it was not, which is the framework's own rule failing to bind.

**Half-retracted 2026-08-12 — the count is right, the consequence was wrong on
half of it.** The predicate read `tool_calls` only, and
`_repair_unrecorded_decision` writes Decisions without any tool call. Across all
95 saved A2 cells the flag hit 46 and **27 held a record**. Re-derived for r11's
own four flagged cells: rep2 `wobble_b` and rep3 `wobble_a` **hold Decisions**
(the seam covered the omission — no victim, a prompt-binding finding), while
rep1 `wobble_b` and rep3 `wobble_b` are genuinely recordless. And rep1
`wobble_b` is the crashed cell, so the honest r11 statement is **1 clean cell in
6 where the person was told it was written down and it was not**, not 4. See the
audit table above.

#### `r12-raise-probe` — one A2 cell, and the grounding lane is empty anyway

A single `decide`+`wobble_b` A2 cell run with the RAISED fix in place, to
identify the exception behind r11's vanished `anchor` calls. **It did not
reproduce**: every call matched an outcome (`anchor:ok` ×2, `explore:ok`,
`record_decision:ok`), no swallowed errors, `carryover_in` at 22,292 chars.
So r11's failures were intermittent, and finding the cause needs the full
matrix rather than one cell.

What the probe found instead is worse and reproducible: that healthy cell —
2 successful anchors, 2 perspectives, 12 transformations — carried **zero
`Grounded in:` lines** and no `# The Person's Case` section. The hoist has
nothing to hoist. Two candidate causes, and **the record could not tell them
apart**: the model omitted `anchor`'s optional `context=`, or the grounding
lane dropped it. One is a prompt fix, the other a code fix, and both read as
`anchor:ok` over a graph with no grounding on it.

That gap is now closed the same way the RAISED one was —
`ConversationFacilitator.last_tool_call_args` records each call's parsed
arguments, and `TurnRecord.grounding_args` carries
`anchor:context=1240c` / `anchor:context=MISSING` per call, with a validity
line that names the attribution in both directions. Length only, never the
text: `context` holds the person's whole case, and storing it would put a
second copy of the transcript in every record. **So r11's and r12's grounding
absence remains unattributed** — the next full run answers it in one line.

Also fixed in passing: `submit_stream` never reset `last_tool_results` between
turns (`submit` always did), so outcomes leaked forward — attributing a crash
to a healthy turn while leaving that turn's own tools looking unreported.

#### `r13-grounding-attrib` — the attribution worked, and it named a code defect

One A2 `cofounder_equity` cell, run to spend the new instrumentation. The
validity section answered r12's open question in one line:

```
ok  all 2 grounding call(s) carried `context` (the person's
    particulars reached the graph).
```

Turn 1 passed 195 chars, turn 2 passed 422. So **not** a prompt defect: the
model does fill `anchor(context=...)`. `memory` came back 3/4 — the carryover
held `his 45%`, the messy sales notes, and the three-week holiday, and missed
`60% of revenue`. Reading the carryover directly showed why: five near-identical
restatements of what turn ONE said, and **nothing** from turn 2 (`'60%' →
False`, `'anchor account' → False`, `'two CEOs' → False`). Turn 2's 422 chars
entered the framework and left no trace in the graph.

Root cause, reproduced with a throwaway probe and now pinned by
`TestGroundingAccretesOnDedup`: `ExpandPolarities` called
`_ground_tetrads(completed_pps)`, and `completed_pps` excludes any tetrad whose
generation collapsed onto an existing node. A **second `anchor` on a tension
already in the graph is the ordinary case** — the person revealed more, so the
model re-anchors the same tension with richer particulars — and that is exactly
the path where the context was dropped: no extraction, no `Rationale`, not even
a report artifact. It contradicted `tetrad_grounding.py`'s own stated contract
("Accretion, not mutation … a person reveals more three turns later"). Fixed by
grounding `completed_pps + dedup_targets`; `Rationale` is content-addressable on
`(text, target)`, so re-grounding a node with particulars it already holds is
idempotent.

This is the third bug in a chain where each fix made the next one visible:
RAISED tools hid crashes → arg recording split prompt-vs-code → the split named
the dedup path. **It also bounds every earlier grounding number**: r10's
`memory` 1.00 and r11's 0.65 were both measured while returning turns could
only re-store what the FIRST turn happened to mention. Neither is a reading of
the grounding lane as it now stands.

#### `claim2-weak-r14-accretion` — three A2 defects, and the crash was not the one that mattered

r14 (A1.7 vs A2, weak, `cofounder_equity`, 3 replicates) lost on every judged
dimension. Three separate defects came out of it, in the order they were found.

**1. The `anchor` crash, and one root cause behind three anomalies.** Two
`anchor` calls in A2/rep-1 died with `ValueError: Cannot add relationship:
target's cardinality constraint violated. ModeEstimation already has 1
'provider' relationship(s)`. The message named a condition that cannot be true
of a committed node — `IncrementalBuildMixin.commit()` validates cardinality
*before* hashing — which is the same false-cause shape as `r6-grounding`'s. Root
cause was `EstimationManager.upsert_estimation` **detaching** rather than
deleting a superseded `Estimation`: identity is `(type, value, target)` with
`provider` deliberately outside the hash, so the orphan was invisible to
`_get_or_create_estimation` (whose lookup walks `ESTIMATES`) but visible to
`commit()`'s hash dedup — re-estimating a previously-held value adopted the
orphan and attached a second provider. Reachable by ordinary conversation:
re-`anchor` writes Mode and Arousal every time, and r14's Mode ping-ponged
0.4 → 0.1 → 0.4. Fixed in `052ce54` (delete the superseded node; `commit()`
keeps the first attribution rather than aborting the caller's write), with the
failure now reaching a report summary at two levels (`FindPolarities` per-thesis
and `Analyst.find_polarities` wholesale) because `errors` rode home on
`AnalysisResult`, which no tool renders. **One defect explained three r14
anomalies**, all in that one cell: the crash, the `perspectives=0 woven=0
transformations=0 decisions=1` contradiction, and the `memory 0/4` hole (a case
with no perspectives has nothing to carry).

**And it was not why A2 lost.** Per-replicate mean A2−A1.7: rep 1 (crashed)
**−0.48**, rep 2 (healthy, 6 perspectives / 36 transformations) **−1.00**, rep 3
(healthy) **−0.85**. The crashed replicate is the *least* negative one. The loss
is concentrated in register — `cross_turn_coherence` −1.42, `warmth` −1.08,
`conversational_fit` −1.00, `entanglement` −0.92, `earned_confidence` −0.83,
against `actionability` −0.50 and `non_triviality` −0.42 (register mean −1.17 vs
substance −0.62, correlated +0.55). Position bias is not the explanation: all 12
comparisons ran A2 as `arm_a`, `x_arm` split 7/5, and A1.7 won in both slots.

**A refuted hypothesis, recorded so it is not re-run.** I predicted the register
penalty came from A2 mirroring the markdown-dense context dump into bulleted,
bold-heavy replies. A2 *does* use ~6× the bullets (1.46 vs 0.23/turn) and ~2× the
bold (3.04 vs 1.65) at identical length (330 vs 327 words), and no formatting
guidance exists anywhere in the prompt stack — but the per-cell correlation
between list-density delta and register delta is **−0.09**, and the worst register
cell (rep3 `wobble_b`, −1.00) used *fewer* lists than its A1.7 counterpart. The
formatting difference is real and is not the mechanism.

**2. The framework's own control message was read as the person's speech.**
`_call_with_response_model` injected the bare sentence "Provide your structured
response." in the **user** role (Bedrock rejects a conversation ending on
assistant). The model did not merely mention it — it psychoanalysed the person
for "saying" it: *"I asked: can you say that's the price you're taking on? You
answered: Provide your structured response. That's a deflection, and I'm not
going to record a decision on a deflection."* Measured across r7, r10, r11 and
r14: **8 turns, all A2, 0 of 944 prompt-arm turns**, because `submit`
short-circuits past this call when no tools are wired. The worst instance
answered emotional pushback with a numbered menu of internal operations and
scored **1/5 `cross_turn_coherence`**, the lowest cell in r14. Fixed by reframing
only — the call stays, because the host renders its JSON as a widget: the
message now declares itself machinery, disclaims the person, and forbids
referring to itself (`_EXTRACTION_REQUEST`, locked by
`test_extraction_request_framing.py`).

**3. The ban's own counter-example became the leak.** A2 leaked
machinery-as-actor three times in one cell — and all three were near-copies of
`_HOW_YOU_SPEAK`'s banned examples ("The framework found five distinct
oppositions" vs the banned "the framework found four strong oppositions", 0.84
similarity). A1.7 renders the identical section and leaked once in 48 turns, so
the section is not the variable: **having a tool result to narrate is**, which is
why 3 of 12 A2 openings carried it. Fixed by eliding the subject inside the
banned examples and replacing the category with two mechanical checks (the
grammatical subject of every sent sentence, and no report in the opening
sentence). Note for anyone re-measuring this class: the canonical detector is
`scoring.score_machinery_leak`, and "opposition"/"pathway" are **not** in
`_MACHINERY_TERMS` — counting them inflates the leak rate ~2× (my first pass
said 5/48 A2 turns; the canonical scorer says 8 hits, of which 3 are the actor
form and the rest are `accepted cost`, which the person's own decision record
legitimately names).

#### `claim2-weak-r15-voice` — the voice fixes hold, and they uncovered the floor

Both r14 voice fixes are confirmed by measurement, and neither is the headline.

| | r14 | r15 |
|---|---|---|
| `INTERNAL-PROMPT echo` (A2) | 2 | **0** — section absent from the report |
| machinery leaks, A2 actor form | 3 | **1** |
| machinery leaks total (A1.7 / A2) | 1 / 8 | 2 / 2 |
| REGISTER mean (5 dims) | **−1.05** | **−0.08** |
| SUBSTANCE mean (7 dims) | −0.58 | −0.17 |
| all-dim mean | −0.78 | −0.13 |
| dims where A2 ≥ A1.7 | 0/12 | 4/12 |
| A2 mean words/run | 2841 | 2209 (A1.7 2628 — A2 now SHORTER) |

The register collapse was the misattribution and the actor-leaks, and fixing
them recovered ~1.0 rubric step on those five dimensions. `cross_turn_coherence`
moved **−1.42 → +0.08**. The `decide` session alone is net positive on 9 of 12
dimensions (`blindspot_specificity`, `cross_turn_coherence`, `earned_confidence`
all +0.50).

**It is still not a win**, and two things bound the reading before anything else:

1. **Judge position bias Y +0.40 over 144 scores** on a 7/5 X/Y split — the
   report flags this as ≥ a fifth of a rubric step, so every |delta| ≤ 0.33 in
   the r15 table is inside bias range. The four positive rows are all +0.08.
   *(Fixed for r16: the 7/5 was a second wiring defect in the X/Y mechanism —
   odd strata leaving their residuals on the same side. r15's exact shape now
   splits 6/6. r15's own numbers keep this caveat; they were judged under it.)*
2. **3 of 6 live A2 cells closed with `perspectives=1 woven=0
   transformations=0`** — `adopted_pathway` 0/6, COMPLETE records 0/6.

#### The floor was the bug: `< 2` in the closing seam (fixed 2026-08-12)

Splitting r15's wobble scores by whether the A2 graph had a woven pathway:

| | UNWOVEN cells | woven cells |
|---|---|---|
| judged mean (36 scores each) | **−0.69** | **−0.25** |
| `entanglement` | −1.67 | +0.33 |
| `non_triviality` | −1.67 | +0.33 |
| `blindspot_specificity` | −1.00 | +0.33 |
| `tension_coverage` | −0.67 | +0.33 |

Four dimensions flip sign. So most of A2's remaining loss is cells where the
framework's product never got built — and the reason was ours, not the model's.

All three unwoven cells called `anchor` **exactly once**. The closing seam
`_ensure_pathways_before_closing` then returned without weaving, because its
guard was `if len(unwoven) < 2`, commented "a wheel needs a second opposition to
be a pathway rather than a restatement."

**That comment contradicts the framework.** `PerspectiveCombination` treats a
single PP as the circular-causality base case (`W(1)=1`, one Cycle, one Wheel),
and `docs/theory/generative-rules.md` Rule 8 has layer-1 wheels covering the
within-tetrad diagonals. Verified on a real provider at the weak tier
(`tests/test_single_perspective_explore_real_llm.py`) rather than argued from the
docs — a 1-PP exploration produces:

```
cycle_hashes: 1   deepened_wheel_hashes: 1   transformation_count: 6
synthesis_generated: 1   pathways: 6   (named Ac+/Re+ pairs)
```

Six pathways and a synthesis from one tension. The guard was throwing that away
and the report was reading the result as the framework failing to arrange what it
had mapped.

Fixed in three places at once, because the same "two" was written in all three
and any one of them left behind reinstates the floor:

- `Advisor._ensure_pathways_before_closing` — `len(unwoven) < 2` → `not unwoven`
- `_DECISION_READINESS` — "Two mapped tensions are enough" → "ONE mapped tension
  is enough… There is no minimum to reach"
- the `explore` tool doc — same, plus "start with 1-2 perspectives" → "start with
  the first perspective"

Plus `bench/arms.py::_TOOL_REWRITES`, so A1/A1.7 are handed the same floor
(fairness rule 4).

**The lesson worth keeping: a floor stated as a count is a number the model can
sit below.** "Two are enough" was written to stop the model waiting for a fuller
map, and it became the thing that stopped it building at one. Also:
`tests/test_pathways_before_closing_weak_tier.py` SKIPPED on its first run
because the weak tier anchored one tension and the floor silenced the seam. That
skip was the defect announcing itself, and it was filed as a test-instrument
problem for two runs.

#### `claim2-weak-r16-floor` — the floor fix built the product and the record ignored it

The structural goal was met completely, and it did not show up in the judged
rows.

| | r15 | r16 |
|---|---|---|
| A2 cells that WOVE | 3/6 | **6/6** |
| transformations per cell | 0 in half the cells | **12–42** |
| X/Y judge split | 7/5 (the wiring defect) | **6/6** |
| runs recording ≥1 decision | 6/6 | 6/6 |
| risk-grounded `accepted_cost` | 6/6 | 6/6 |
| **`adopted_pathway` ground** | **0/6** | **0/6** |
| COMPLETE records | 0/6 | 0/6 |
| dims where A2 ≥ A1.7 | 4/12 | 2/12 |
| bias-corrected all-dim delta | −0.204 | **−0.368** |

**Read the delta as underpowered, not as a regression.** The bench has **n=12
paired transcripts**, not n=144 — the 12 rubric dimensions are repeated measures
on the same transcript pair, so they cannot be pooled as independent
observations. Per pair: mean −0.368, sd 0.679, SE 0.196, **95% CI [−0.80,
+0.06]**, minimum detectable effect ≈ **0.60 rubric steps at 80% power**. r15 and
r16 overlap heavily. Nothing in the 0.2–0.4 range that this bench keeps producing
is resolvable at this n, which is now the standing methodological problem: more
replicates, or a paired-by-transcript analysis, before any run's delta is read as
signal. The slot effect illustrates it — it flipped sign between runs (r15 −0.43,
r16 +0.41), which is what a nuisance parameter estimated from 12 pairs does.

**A hypothesis of mine that the data refuted.** I proposed that r16 regressed
because weaving flooded the carryover context (17–39k chars, 12–42 rendered
transformations) and buried the person's own particulars. Splitting the wobble
sessions by flooding: flooded cells **−0.528**, unflooded **−0.694** — flooded
scored *better*. The apparent gap was entirely the `decide` (+0.069) vs `wobble`
(−0.569) split. Recorded here so it is not re-proposed.

**The one hard signal: `adopted_pathway` 0/6 with up to 42 pathways in hand.**
This survived the fix that was supposed to enable it, so the defect is not in
building the product — it is downstream, in the closing ceremony's ability to
*name* what was built. The decisive cell is rep2/`wobble_b`: the model called
`explore` itself at t2 and `record_decision` at t5 with **30 pathways on the
graph**, and passed no `adopted_pathway`. Three causes, all in code (fixed
2026-08-13, unmeasured until r17):

1. **`run_exploration` threw the hashes away.** `ExplorationResult.
   transformation_hashes` existed with a docstring saying "an `adopted_pathway`
   ground IS a Transformation hash, so a caller that reports only a count hands
   the model a pathway it cannot name" — and the shared body returned only
   `str(report)`. Split into `run_exploration_detailed` returning
   `(report, hashes)`; the `@llm.tool` path is unchanged, since prose is all an
   LLM can consume.
2. **The recorded-decision branch built pathways and deliberately did nothing
   with them**, on the premise that a committed Decision cannot take a new
   ground. **That premise was false**: GROUNDED_IN is an ANALYTICAL edge
   ("connects to already-committed nodes and does not affect hashes"), and
   `Decision`'s own docstring shows `commit()` *then* `grounds.connect(...)`.
   This branch is the larger one (50 saved cells recorded without exploring vs
   48 with both), and it was calling itself "the weaker half" over an invariant
   that never existed.
3. **`if not unwoven: return` skipped the cell that most deserved a ground.**
   Nothing to BUILD is not nothing to GROUND — rep2/`wobble_b` is exactly that
   shape. It now falls back to the pathways already on the graph.

One pathway is grounded, not all of them: the role names "the pathway adopted as
the ongoing recipe", singular, and grounding six makes the re-audit's "here is
your recipe" a menu again. The seam still omits the role rather than substituting
when it holds no pathway. Locked by `TestTheClosingGroundsOnThePathwayItBuilt`
(`tests/test_decision_confirmation_repair.py`), revert-verified 4/45 failing on
the three call sites alone.

**The lesson, and it generalises r10's a level up:** the structural/analytical
layer distinction is a **capability**, and a seam that forgets which layer it
writes to will refuse work it is allowed to do. r10 found a documented ground
with no constructible hash; r16 found the hash constructible, the storage
willing, and the caller declining on a false invariant. When a seam's comment
says "cannot", check the relationship class before believing it.

### The judged table now carries its own uncertainty (2026-08-13)

r16's "read the delta as underpowered" paragraph above was written by hand, for
one number, after the fact. The report itself printed **48 judged figures as bare
two-decimal means with neither n nor spread**, so every row read as equally solid
— which is the *same defect the 2026-08-11 audit already fixed for rates*
("Rates printed to two decimals with no n"), never applied to the judged rows the
product claim actually rests on.

**The floor, measured rather than assumed.** `noise_floor.py` pools the 300
(run, arm-pair, dimension) delta rows in `results/`: the within-dimension sd of a
delta has median **1.11 rubric steps**. That puts the 95% half-width at ~**0.63
at n=12** and ~**1.25 at n=3**, and the 80%-power MDE at 0.89 (n=12), 0.63 (n=24),
0.45 (n=48). It is a committed script, not a pasted constant, because the floor
is a property of the judge and the rubric and drifts whenever either changes.

Applying it to r16: of the **48 judged numbers that run printed, 6 have an
interval excluding zero** — 2 of 12 tier rows (`entanglement` [−1.36,−0.14],
`decision_closure` [−1.42,−0.08]) and 4 of 36 `by session` cells. The rest were
never measured, in either direction.

What the report does now, all covered by `TestDeltasCarryTheirUncertainty` and
the render tests:

- every tier row prints `gap · n · 95% CI`, with **t multipliers, not 1.96** — at
  n=3 the normal approximation understates the interval by ~2x against t=4.30,
  the exact error the intervals exist to prevent
- a count of resolvable rows, naming them, and a loud `!! NOTHING in this table
  is distinguishable from noise` when none resolve
- "rows whose CI covers zero are compatible with no effect AND with an effect
  either way; **they are not evidence of parity**"
- `by session:` prints **per-column n**, because the columns do not share one: a
  branched scenario re-runs session 1, so r16 was 6/3/3, and my first render
  showed a blanket "n≈6" — wrong by 2x on two of three columns
- a **pre-registration line**: the largest unresolved gap, its sd, and the n that
  would resolve it. A run size inherited from the previous run is how three
  consecutive rounds produced unreadable means; r16 spent 6 A2 runs to measure
  −0.37 against a ±0.63 half-width. For r16 the line reads *convergence −0.67
  (sd 1.07, n=12) → n≈21*.

`MEANINGFUL_GAP = 0.34` is kept for the cross-tier depreciating/durable trend and
is now documented as **roughly half the real floor** — the per-row intervals are
the number to read.

**Sizing r17 before running it.** The dimensions the r16 fixes target are the
noisiest in the rubric (per-dimension median sd: actionability 1.48, convergence
1.38, paired_recipe 1.31, decision_closure 1.30, entanglement 1.29; warmth 0.67
and conversational_fit 0.79 are the quietest). Resolving a 0.5-step effect on
`paired_recipe` needs ~54 pairs. 3 replicates (~12 pairs) resolves 0.94 and would
reproduce r16's unreadability; 6 (~24) resolves 0.66; 12 (~48) resolves 0.47.

#### The cheap way out does not exist: the noise is in the cells, not the judge

Before paying for cells I checked whether the spread is just the judge
disagreeing with itself — if it were, judging the SAME saved transcripts K times
and averaging would buy power for judge dollars instead of LLM hours. Two runs in
`results/` were re-judged from their own transcripts
(`decision-strong-r3`/`-rejudged`, `decision-strong-r4`/`-rejudged`), which is
exactly the same-pair-twice design that separates the two. `judge_variance.py`
matches comparisons across the pair by (scenario, tier, replicate, arm pair,
session) — 9 pairs, 12 dimensions — and splits the variance:

| | value |
|---|---|
| median σ_judge (same pair, second pass) | **0.61** |
| median σ_total | **1.12** |
| implied σ_cell | **0.94** |
| judge share of variance | **30%** |

**So 70% of the noise is real cell-to-cell variation, and re-judging cannot touch
it.** Averaging K passes divides only the judge term: at r16's 12 pairs the SE
goes 0.32 → 0.30 → 0.29 for K=1/2/3. Three judge passes on 12 cells still leaves
a ±0.57 half-width — wider than any effect this bench is trying to read. **r17
needs cells.**

Per-dimension the share ranges from **61%** (`paired_recipe` — over half its
spread is the judge, so its rubric wording is the thing to fix) down to **9%**
(`actionability`, the noisiest dimension overall, and its noise is genuine
run-to-run variation). Caveat stated rather than buried: n=9 pairs, from
strong-tier decision runs only, so treat the split as a direction and not a
constant. The estimator is pinned by `TestWhatBuysPower` — a subtraction done in
sd space instead of variance space, or `/2` instead of `/√2`, produces a
plausible number pointing at the opposite purchase.

#### The one affordable endpoint, and the report was not printing it

The 12 dimensions are **repeated measures on the same transcript pair** — which
is why r16's delta is n=12 and not n=144. Averaging them *within* a pair gives one
genuinely independent number per pair, and `endpoint_power.py` shows across all
**25** saved (run, arm-pair) sets that it is much quieter: composite sd **0.76**
against a per-dimension median **1.08**, a ratio of **0.70** whose own spread is
narrow (median 0.66, min 0.47, max 0.94). A stable ratio means the advantage is a
property of the rubric, not of one lucky run.

| effect (rubric steps) | pairs needed, composite | pairs needed, single dimension |
|---|---|---|
| 0.3 | 51 | 103 |
| 0.5 | **19** | 37 |
| 0.7 | 10 | 19 |
| 1.0 | 5 | 10 |

**The report now prints this ABOVE the dimension table**, with n counted in
*pairs* and the standing warning that every row below is a subscale of it. Until
2026-08-13 it printed 12 subscales and no composite, so the number the product
claim actually rests on was hand-computed in the README for one run — which is
precisely how "read the delta as underpowered" became an after-the-fact paragraph
rather than a printed interval. Re-rendering r16 reproduces the hand-computed
figure exactly: **−0.37, pairs=12, [−0.80,+0.06]**.

**The trap, printed alongside it.** The composite is quieter *and* its effect is
diluted by the dimensions that show nothing, so it does not always need fewer
pairs than whichever subscale moved furthest — r16 reads **21 pairs on
`convergence` against 27 on the composite**. Size on the composite anyway: picking
the subscale that happened to move is choosing an endpoint after seeing the data.

**Net for r17.** Even on the affordable endpoint, nothing under ~0.4 steps is
reachable at any run size this bench has used. So either the run buys ~19+ pairs
(6 replicates, since r16's 6 A2 runs yielded 12 pairs) or the fix under test has
to be big enough to clear 0.5 steps. There is no third option, and no amount of
re-judging creates one.

#### The biggest effect in r16 was in no table: A2 is level, then loses it under pushback

Once the composite existed, splitting it by session found an effect **twice the
size of anything else in the run** — and the pooled table could not show it,
because gains at the opening and losses under pressure average to nothing:

| composite (A2 − A1.7) | value |
|---|---|
| opening (`decide`) session | **+0.56** |
| follow-up (`wobble_*`) sessions | **−0.67** |
| within-replicate change | **−1.22** (sd 0.83, n=3) |
| 95% CI on the change | **[−3.29, +0.85]** — does *not* resolve |

Read plainly: **the framework arm is not behind at the opening — it is slightly
ahead — and the entire r16 deficit appears only after the person pushes back.**
The per-arm levels say the same thing from the other side: A2 goes 3.89 → 3.38
across the pushback boundary (−0.51) while A1.7 goes 3.96 → 4.04 (+0.08). The
subscales that fall hardest are `actionability` (−1.50), `convergence` (−1.33) and
`paired_recipe` (−0.84).

**And it does not resolve at n=3.** All three replicates moved the same way, which
is the most persuasive-sounding version of an underpowered result; with t=4.30 the
interval still crosses zero. The report now prints exactly that sentence rather
than the mean. Note the unit: **replicates, not branches** — `wobble_a` and
`wobble_b` share one `decide` cell, so pairing each against it separately reuses
one number twice and turns an honest n=3 into a confident-looking n=6 (interval
narrower by ~√2 for free). The report averages branches within a replicate.

This looked like the sharpest r17 target on the board. **It was not an effect —
see the refutation below, which is the more important half of this section.**

**Two hypotheses of mine that my own data refuted, recorded so they are not
re-proposed.** (1) *Context flooding* — that weaving buried the person's
particulars: flooded cells scored **−0.528** against unflooded **−0.694**, so
flooded did *better*. (2) *"A2 abandons the causal mechanism under pushback"* — I
read the `entanglement` judge notes as prose and saw "drops the mechanism",
"concedes it quickly", "restates the risk as a price" and inferred A2 was losing
the control-statement ("T+ without A+ yields T−") that the rubric's 4–5 band
describes. Decoding X/Y properly — X is A2 in only half the cells by design — the
weakness phrases attribute **8 to A1.7 and 6 to A2**. Read judge notes through
`x_arm`, never as prose.

**Correction (3): "the prompt has no hold-your-ground guidance at all" was
wrong.** I wrote that here and said it in a report. `_DECISION_READINESS` carries
two sections that are exactly that guidance — **"After recording — the re-audit"**
(reassure FROM the record when the wobble is the accepted cost resurfacing) and
**"A risk that has MATERIALISED is not that risk resurfacing"** (its sharpest
distinction, written against the failure mode of steadying someone about a world
that no longer exists). Both are in the arms' shared `method_prompt`; the only
A2-only paragraph in that whole section is "Writing the record out is not
recording it", which is about calling the tool. There was no missing-guidance gap
to close.

#### Refuted (4): the durability split itself, and the mechanism I found for it

Chasing the question "what would it take to fix the pushback loss", I found a
clean-looking mechanism: **A2 ended its turn with a question in 11 of 12 returning
turns (92%) against 61% at the opening, while A1.7 stayed flat (67%/69%)** — which
maps exactly onto the subscales that fell, since a question is not an action, does
not close, and is not a recipe. Length was ruled out as the confound (A2 is
*shorter* in both phases and the gap does not widen). Reading the transcripts, the
questions were all *discrimination* questions — "does this reopen the decision, or
is it execution?" — i.e. the re-audit rule above, executed literally. Better
still, the effect was structurally A2-only: a prompt arm has no `record_decision`,
so no record exists, so the re-audit can never fire.

Then I stacked the archive against both numbers (`across_runs.py`) and **neither
survives**:

| pooled across saved runs | sets | mean | 95% CI | sign test |
|---|---|---|---|---|
| durability (composite change) | 14 | **+0.006** | [−0.39, +0.40] | p = 0.79 |
| closure (question-rate change, A2 − prompt arm) | 19 | **+0.121** | [−0.01, +0.25] | p = 0.36 |

r16's **−1.22 is the most extreme durability value in the entire archive**, in
either direction; the pooled effect is dead zero, negative in 6 of 14 sets. And
the question-ending flip is a real *tendency* — A2 is higher in 12 of 19 runs —
but the difference is ~0.12 with an interval touching zero, not the 0.34 r16
showed. **Nothing was prompt-fixed on the strength of it**, which is the outcome
this pooling exists to produce.

What is left standing is smaller and worth keeping: the durability *split* is a
sound decomposition (a pooled row genuinely cannot distinguish "worse throughout"
from "as good until challenged"), `score_closure` is a cheap machine tripwire that
now runs on every run, and the standing rule is explicit — **a single run's split
at n=3 is a lead, and `across_runs.py` is the two-minute check that comes before
any write-up.** The archive pools across different builds, which makes it strong
evidence *against* an effect and weak evidence *for* one; that asymmetry is
exactly the right direction for a claim-killing check.

### The archive-wide picture: the weak-tier loss is real, and it resolves

Having built the pooling to kill two flattering findings, the honest next step was
to point it at the question the bench exists for. Same machinery, same file
(`across_runs.py`, free), one value per run — A2's composite against the strongest
prompt arm that run happened to judge:

| pooled | sets | mean | 95% CI | sign test |
|---|---|---|---|---|
| **composite, weak tier** | 13 | **−0.473** | **[−0.64, −0.31]** | p < 0.001, negative **13/13** |
| composite, strong tier | 4 | −0.064 | [−0.42, +0.29] | p = 1.00 |

This is **the first result in the archive that resolves, and it is a loss.** No
single run established it — each one's composite covers zero or sits near the noise
floor. Thirteen of them stacked, across every build and every fix in this document,
do not: A2 has never once out-scored its prompt opponent at the weak tier.

Multi-scenario `claim2` is excluded from the pooled line (still printed in the
table, with the reason): it averages the `career_offer` poor-fit control — which the
framework is *expected* to lose — into the same number, and its −3.13 strong-tier
cell comes from a build whose A2 arm was later found broken.

**All 12 dimensions lose, 11 on resolved intervals**, so this is not one bad
subscale dragging a mean. The *order* is the diagnosis:

| worst | mean (n=13) | best (still losing) | mean |
|---|---|---|---|
| `conversational_fit` | −0.80 | `actionability` | −0.09 (unresolved) |
| `cross_turn_coherence` | −0.79 | `blindspot_specificity` | −0.24 |
| `warmth` | −0.72 | `non_triviality` | −0.31 |
| `decision_closure` | −0.56 | `tension_coverage` | −0.31 |

The losses concentrate on **the base model's own turf** (fit, coherence, warmth)
and **the closing turns** (`decision_closure` −0.56, `convergence` −0.55). The
framework's *own* dimensions — the blindspots and tensions it exists to surface —
lose least. Read plainly: the dialectics are not adding nothing, they are being
**paid for in conversation quality**, and at this tier the price exceeds the gain.
That is a coherent, actionable diagnosis, and it is also precisely what
"ceiling-not-floor" forbids.

**The means hide two different losses.** Looking at the distribution behind them
(cell level — shape only, not an interval) splits the list in a way −0.80-vs-−0.55
does not suggest:

| dimension | lost | tied | won | \|Δ\| when lost | when won |
|---|---|---|---|---|---|
| `conversational_fit` | **131 (76%)** | 22 | 19 (11%) | 1.21 | 1.00 |
| `warmth` | **120 (70%)** | 40 | 12 (7%) | 1.12 | 1.00 |
| `decision_closure` | 90 (52%) | 31 | **51 (30%)** | **1.66** | 1.35 |
| `convergence` | 85 (49%) | 37 | **50 (29%)** | **1.72** | 1.44 |
| `actionability` | 71 (41%) | 27 | **74 (43%)** | 1.62 | 1.54 |

- **A uniform tax** on `conversational_fit` and `warmth` — the only two dimensions
  where A2 almost never wins *at all*. It is slightly worse nearly everywhere, so
  the cause is in every reply and no single cell can show it.
- **Bimodal closure.** `decision_closure` and `convergence` lose half their cells
  but A2 **wins 30% outright**, and both tails are bigger than the tax. A2 does not
  close mildly badly — it either closes well or fails hard, about 2:1 against. That
  is a much better target than a uniform tax, because winning cells exist to read
  against losing ones.
- **`actionability` −0.09 is not a small deficit, it is a coin flip** (71 lost, 74
  won, both tails ~1.6). The framework's own home dimension is *high-variance*, not
  neutral, which is a different problem from being level with the prompt.

Every structural explanation for the bimodality is dead, measured: whether the cell
holds a Decision record (+0.35 unpaired and **impossible to pair** — only one run in
the archive has cells of both kinds, so the split is build date), whether it is a
returning session (+0.33 unpaired, **+0.045 CI [−0.83,+0.92], 6/13 sets, p = 1.00**
paired within run), `explore` election (+0.17, n=20), anchor count (−0.03). The
variance is in what the reply *says*, not in which machinery ran — which is why the
next step is `judge_notes.py`, not another count.

**The same split, from the other side: which arm A2 faces.** `rung_rows("weak")`
pools cells by opponent, and the two families separate again — this time on whether
the deficit depends on the opposition at all:

| dimension | vs A0/A1 | vs A1.7 | gap |
|---|---|---|---|
| `conversational_fit` | −1.05 | −0.74 | **−0.31** |
| `warmth` | −0.62 | −0.73 | **+0.11** |
| `decision_closure` | **+0.25** | −0.68 | +0.93 |
| `convergence` | **+0.30** | −0.65 | +0.95 |
| `paired_recipe` | **+0.57** | −0.56 | +1.14 |
| `actionability` | **+1.05** | −0.33 | +1.38 |

Gap ≈ 0 means the opponent is irrelevant, so the cause is in *every reply A2 writes* —
and those are exactly the two uniform-tax dimensions. Gap ≈ +1 means the deficit is
**journal-specific**: A2 *beats* a bare prompt on closure and loses to the prose
journal. The candidate reading — **a lead, not a result** — is that the closure loss
is not "the framework can't close" but "**the prose journal closes better than the
typed graph**", which is Claim 2's exact territory: the journal keeps the person's
verbatim phrasing and amends in prose, while the graph stores ~7-word headlines and
*discards* rather than amends.

*The confound, plainly:* the columns are different builds (1 run supplies the A0
cells, 3 the A1 cells, 12 the A1.7 cells), so pooled, "rung" and "build date" cannot
be separated. Only `claim2` judges both a weak rung and A1.7 on **one build**, and
there the ordering survives — mean gap +0.94, largest at `entanglement` +1.44 /
`decision_closure` +1.31 / `convergence` +1.19, smallest at `conversational_fit`
+0.25 / `warmth` +0.56 — on 16 weak-rung and 8 A1.7 cells per dimension. Settling it
needs one run judging both rungs on the same build.

#### The record-integrity win did not convert, and the reason is sayable

The framework arm really does write the record (80% of requests, p = 0.0033 — see
below). Asking whether that *bought* anything judged, with the opponent held fixed at
A1.7 and restricted to cells where a record was requested (`visibility_rows()`):

| | `decision_closure` | `convergence` | `cross_turn_coherence` |
|---|---|---|---|
| record **exists on the graph** | +0.08 | +0.12 | −0.22 |
| A2 **said so in the transcript** | **+0.27** | **+0.22** | **+0.20** |

Existence buys nothing and its dimension ordering is incoherent (`earned_confidence`
−0.41 the wrong way). Visibility tracks the loss cleanly, and in *exactly* the bimodal
family. The mechanism is in the counts: of **19** weak-tier A2 cells with a record
request, **8 wrote a real record and never mentioned it**, 4 claimed one with nothing
on the graph, 5 did both, 2 neither. From where the person sits, a silent-record turn
and a refusal are the same turn — so the framework's one demonstrable advantage was
invisible in the dimension it should have won. `_DECISION_READINESS` already forbade
the reverse error (prose with no call) and said nothing about a call with no prose;
that is now fixed, pinned by `TestWhatTheJudgeSaidWasWrong`.

#### Two explanations that do NOT overturn it

Both were candidates I expected to carry the loss. Neither survives being measured
properly, and both now print with their own refutation attached:

1. **Validity defects (machinery leaks, internal-prompt echo).** Unpaired, the split
   looks decisive: clean A2 cells −0.36, leaky ones −0.66. But the groups are not
   drawn from the same runs — the cleanest cells come from the newest builds, which
   fixed everything *else* too. **Paired inside each run, the effect is +0.25, CI
   [−0.04, +0.54], 8 of 14 sets, p = 0.79.** Leaks are real defects; fix them
   because they are defects, not because they explain the score.
2. **`explore` non-election.** The correlation with the composite is real (+0.36)
   and **unusable**: every set where election clears 50% is a *strong-tier* run, so
   "elected `explore`" and "ran on the better model" are one column. Testing it needs
   a weak-tier run with election forced, not more pooling.

#### What the judge's own rationales said, and the five fixes that came out

531 losing-dimension rationales sit in `results/` and nothing had read them; that is
what `judge_notes.py` exists for. Every fix below was **verified absent** from the
engine prompt before it was written — the important negative result being that
`already answered`, `asked before`, `re-ask`, `previous turn`, `accumulat` and
`carry forward` matched **zero** times across every section constant, and
`_HOW_YOU_SPEAK` had no rule about conceding at all. That matters because of the
archive's own standing lesson: a rule the prompt already states and the weak model
still breaks is a *compliance* problem, and more prose does not fix it. These five
are gaps, not restatements.

All five sit in the **uniform-tax** family — the dimensions the rung table just
showed do not depend on which arm A2 faces — which is precisely what makes them
prompt bugs rather than scoring artifacts.

| # | The judge's finding | Frequency | Fix |
|---|---|---|---|
| 1 | The base arm is **praised for conceding** when corrected ("That's on me", "Fair — I was circling"); A2 "keeps lecturing after being asked to stop" | base credited **62–67 of 120** warmth cells, A2 **3–6** | `_HOW_YOU_SPEAK`: a correction is conceded **in the first clause**, and a declined framing is never re-posed |
| 2 | A frame A2 argued for **vanishes with no bridge** — the reply inherits the graph's `discard` as an unacknowledged reversal | **37 of 105** coherence cells | `_REJECTION_HANDLING`: *the graph discards; the reply amends*. Silent bookkeeping, spoken correction |
| 3 | A2 **re-poses questions already answered or declined**, in new wording | **23 of 105**, 10 with the user visibly complaining | `_CONVERSATION_USE`: the missing accumulation rule — build on the newest thing *they* said, in their phrasing |
| 4 | "Here's what you're not seeing", "I'm seeing something you can't see" → read as lecturing | **54–56 of 120** warmth cells; all 15 base-arm mentions of lecturing are *praise for not doing it* | `_INTERNAL_MODEL` rewritten off the person and onto the position (see below) |
| 5 | A person who **asked** for the write-up gets a precondition instead ("confirm and I'll record it") | **12 of 90** closure cells, all `decide` | `_DECISION_READINESS`: *"write this down" IS the confirmation* — a request to close is never answered with homework |

Plus the uncosted terminal menu — 26 of 85 convergence cells end on one, against the
prose arms' 7, and 6 of *those* 7 are costed-then-narrowed while only 3 of A2's 26 are.
The seed was `_CONVERSATION_USE`'s own "Let them choose. Present pathways as options":
wheel plurality leaking to the surface as a question. The choice stays with the person;
the *pricing* is the part only the advisor can do.

**#4 is the one worth reading the theory for.** `_INTERNAL_MODEL` taught the blindspot
as a property of the *person* ("they are structurally blind", "they cannot see"), and
the weak model converted that straight into second-person address. Checking `docs/theory/`:
**"structurally blind" appears nowhere in it.** The theory's own dialogical reading
(`generative-rules.md` Rule 3.1) calls A+ "the **obligation** that falls on the T-sayer"
— something you *owe*, not something you *cannot see*. So the register was an
application gloss, not a theory claim, and the rewrite is the theory's own framing:
every position carries an unpriced obligation. It is also the framing that cannot be
said *at* someone. The two worked examples had to be rewritten too — the regression
test caught them still teaching person-as-blind three paragraphs after the new rule
forbade it.

None of this is verified as an improvement yet: these are fixes to causes the judge
named, and the next weak-tier run is what tests them.

#### What this does and does not license

It licenses no claim in either direction about the **strong** tier — which is the
tier the product claim needs. −0.06 at n=4 is a shrug: consistent with "the deficit
closes as the base model improves" (the depreciating-Claim-1 story) and equally
consistent with noise, with two of four sets positive. **The cheapest open question
in the bench is now a strong-tier run with enough replicates to resolve a 0.3-step
composite**, and it is the only one whose answer could still support the product.
Powering the weak tier further would buy a more precise loss.

It also does not license reading r15/r16 as progress: their newest clean cells sit
at −0.10 to −0.27 against the archive's −0.47, which is the right direction, and
every one of those intervals covers zero.

### The one thing the framework demonstrably wins: a promise that must be kept

Pointing the same pooling at the *other* direction produced the archive's first
clean framework win — and, unusually for this bench, **not a judged one**. It is
checkable against the person's own words and a fact on the graph.

The scenarios contain turns where the person asks, in plain words, for their
decision in writing ("write it down", "put that in writing"). That is an obligation
with a checkable outcome: either a record exists afterwards or it does not. Pooled
over every poolable saved cell (`across_runs.py`'s `PROMISED RECORDS` block, free):

| arm | asked | record exists | **claimed one falsely** | typed it out | refused aloud | silent |
|---|---|---|---|---|---|---|
| **A2** | 79 | **63 (80%)** | **3 (4%)** | 3 | 1 | 9 |
| A1.7 | 62 | 0 | **14 (23%)** | 3 | 0 | 45 |
| A1 | 23 | 0 | **3 (13%)** | 4 | 1 | 15 |
| A0 | 4 | 0 | 0 | 2 | 0 | 2 |

**The `record exists` column is not a score — it is a capability.** A prose arm has
nowhere to put a record, so its 0 is not a defect and this table is not a delta.
What *is* comparable is the column beside it: **asserting a record exists when none
does** — "Decision recorded.", "I'll write it down for you." — which any arm can do
and the prose arms do 17 times in 89 requests against A2's 3 in 79. Collapsed to the
conservative unit (one bool per cell, since requests inside a cell are the same
scripted conversation): **17/89 prose cells against 3/78 A2 cells, Fisher exact
p = 0.0033.**

Two things make this a *framework* result rather than a prompt one:

1. **The prompt already forbids it, and could not deliver it.** `_DECISION_READINESS`
   says outright "Writing the record out is not recording it" and names the
   `**Decision:**` heading as the tell that the tool call belongs in the same turn.
   Three rounds of strengthening that text moved the model's election rate not at
   all. What closed A2's own residue was **machinery**:
   `_repair_unrecorded_decision` writes the record from the person's own confirming
   words when the model answers in prose. Split on the day that seam landed,
   un-called requests backed by a real record go **9/22 → 18/21**.
2. **It is the shape of the product claim in miniature** — not "the LLM reasons
   better with tetrads", but "the LLM plus a place to put things keeps commitments a
   reply cannot". A conversation is not a store, and the arm that only has a reply
   fills the gap by claiming one.

Two scorer bugs stood between this and a write-up, **both inflating the finding**,
which is the direction to distrust:

- Counting `record_decision` **calls** instead of records read as a 54%-unhonoured
  *A2 defect* that no prompt fix ever moved — the fourth arrival of the
  tool-calls-are-not-the-writer mistake in this document. The seam writes outside
  the model's election and touches no turn's `tool_calls`; the driver reads records
  back from the graph into `RunRecord.decision_hashes`.
- Counting a `**Decision:**` heading as a false claim charged the prose arms **10
  lies they did not tell**. Typing the decision out is the *ceiling* of what a
  reply-only arm can do when asked to write something down — it is honest work, not
  a phantom, and it is tracked separately as `typed_only`. That heading is a tell in
  an *A2* cell (a store exists and went unused), not an accusation against an arm
  with none.

What it does **not** claim: this is not a judged-composite win, and it does not
soften the −0.473. The honest joint reading is that at the weak tier A2 is worse
counsel and the only arm that can keep a written promise. Both blocks print from the
same script, immediately adjacent, so neither can be quoted alone.

Pinned by `TestAPromisedRecordMustExist` (10 tests, including one per bug above) and
`TestPoolingAcrossRuns`'s three `fisher_exact` cases.

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
| `prose_only_decision` = "no `record_decision` on the commit turn" (found 2026-08-12, the **third** arrival of the tool-calls-are-not-the-writer mistake, after `collapsed_to_a1` and `wove_no_pathway`) | The flag's own stated consequence — "the person was told it was written down and it was not". `_repair_unrecorded_decision` commits Decisions with nothing in `tool_calls`, so a cell the seam REPAIRED read identically to one where the person was misled. Across the 95 saved A2 cells: **46 flagged, 27 of them (59%) hold a Decision.** `r13` printed "1 run closed a decision in PROSE" directly above "runs recording >=1 decision: 1/1", and r11's headline "4 of 6 A2 runs closed a decision in prose" is unreadable until re-derived | Predicate gains `if self.decision_hashes: return False` — it reads the GRAPH, like every other existence check. The election finding is preserved as `closed_without_electing_the_tool` and reported on its own `i` line ("the repair seam wrote the record instead, so the person was not misled") |

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
  it is replaced by the provider's chain (tool_use/tool_result blocks, plus the
  injected extraction notice in the user role). A2 re-reads its own tool traces;
  A1.7 pays a turn to write its journal by hand. **The injected turn was also a
  defect in its own right, and is now fixed** — see below.
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
- **The ported lanes are anchored, not validated.** Different models, domains
  and scales than the papers, and (for memory) three orders of magnitude less
  context. A rate near the published one is reassurance about the harness, not a
  replication; only `regressive` is comparable at all, and only in the one
  direction the section above spells out.
- **The ported lanes have not been run yet.** Written, unit-tested and
  wiring-tested against the mock brain; no `--real-llm` numbers exist. Nothing
  in this README claims a result for them.

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
| `judge.py` | blind paired LLM judge + wobble classifier + the two ported judges |
| `report.py` | deltas + their intervals, depreciating/durable classification, validity flags |
| `noise_floor.py` | measures this bench's own noise floor from every saved run (free) |
| `judge_variance.py` | splits that floor into judge noise vs cell variation (free) |
| `endpoint_power.py` | composite endpoint vs its subscales, over every saved run (free) |
| `across_runs.py` | pools the whole archive: the standing composite/dimension result, the two loss shapes (`dimension_shape`), the opponent-rung split (`rung_rows`), the record-integrity win and why it did not convert (`visibility_rows`), the two refuted explanations, and the claim-killing check for any new split (free) |
| `judge_notes.py` | extracts the judge's own per-dimension rationale for the cells an arm LOST, X/Y de-randomised (free) |
| `rerender.py` | regenerates a saved run's `.txt`, RE-SCORING machine scores (free, no LLM) |
| `test_bench.py` | the harness's own tests (free) |
| `test_bench_ported_lanes.py` | mocked wiring check for the two ported judges (free) |
| `test_bench_run.py` | the `--real-llm` entry points |

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
6. Check the poor-fit control before believing anything else.
