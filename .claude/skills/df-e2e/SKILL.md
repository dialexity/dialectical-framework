---
name: df-e2e
description: Pick up the end-to-end search where it left off. Reports where the archive stands (coverage, gaps, unread runs), runs the seam/search/archive lanes, and turns a lost cell into a committed seam guard. Use to resume e2e work across sessions, before running any matrix, or when asked how the framework is doing versus a prompted LLM.
disable-model-invocation: true
---

<!-- No `allowed-tools`: this skill's own loop ends in EDITS — a new seam guard in
     tests/, its row in the README roster table, and its stem in ROSTER. Pinning a
     Bash-only tool list here would have made the documented workflow unexecutable,
     which is this repo's signature bug (a stated capability that is not wired).
     Siblings that only run a command do pin it; df-sync-theory, which also writes,
     does not. -->


Usage: `/df-e2e [status | seam | search <scenario> | read <stem> | guard <finding>]`
(default: `status`)

The e2e harness (`tests/e2e/`) drives the assembled framework against opponent arms.
Full detail: `tests/e2e/README.md`. This skill is the entry point that keeps sessions
from re-deriving the same state.

## The one rule that makes this skill work

**Prose carries judgement. `status.py` carries numbers.**

Never state a figure from memory, from this file, or from an earlier session's summary.
Every number in this archive that was quoted from prose turned out wrong: an
A1.7-vs-graph attribution stated backwards, "20 poolable strong pairs" that were 5
replicates judged twice, a per-session table averaged across two rounds. A sentence
cannot be re-run. So:

```bash
poetry run python tests/e2e/status.py       # ALWAYS start here
```

If a status claim cannot be printed from `status.py`, it is a memory, not a status.
When the user asks "how are we doing" — run it, read it, then interpret.

## Step 0 — orient (always, ~10s, free)

```bash
poetry run python tests/e2e/status.py    # coverage / unread / deltas
git log --oneline -12                    # what the last session actually did
git status --short                       # concurrent sessions share this tree
```

Read the three sections as three different questions:

- **coverage** — *what has never been asked?* `NEVER JUDGED` scenarios are unopened
  boxes, not weak results. `CONCENTRATION` bounds every archive-wide claim to the
  scenarios named in it. `drop` > 0 on a scenario means its cells are dying — a
  harness or arm defect, not a coverage fact.
- **unread** — *what is already paid for?* Saved runs with no comparisons cost minutes
  to judge instead of hours to run. This is always the cheapest next move.
- **deltas** — *where does the framework stand?* Judge points, −4..+4, A2 minus the
  opponent, split by session because the effect is not uniform across a conversation.
  `reps` is the independent unit; `n` is not.

Then say where things stand in the user's terms, and name the cheapest informative
next move. Do not propose a full matrix run before checking `unread`.

## The method, when you need to explain or defend it

Do not reconstruct the ladder from memory — it has a written home:
**`tests/e2e/README.md` → "The ablation ladder"**. It carries the five arms
(A0 bare persona → A1 method-as-text → A1.5 static graph dump → A1.7 self-written
journal → A2 live tools+graph), what each rung isolates, the four model roles with
their defaults, and why A1 is a steelman rather than a strawman.

Three facts from it worth holding in mind while reading any delta:

- **`A2−A1.7` is the comparison that means something.** A2−A1 is a floor check.
- **A2 has no prompt advantage.** `arms.py` builds A1's prompt from the engine's
  OWN section constants, imported live from
  `src/dialectical_framework/agents/advisor/system_prompts.py` — the framework's
  single mother prompt. `_TOOL_REWRITES` turns tool verbs into mental acts rather
  than dropping the paragraphs, because dropping them would delete the reasoning
  under measurement. Anything A2 wins, it wins by operating machinery.
- **Read the recorded model, never the tier label.** `DIALEXITY_E2E_TIER_WEAK` has
  been pointed at Sonnet before, and every pooled cut that trusted the label was
  wrong.

`TestTheDocumentedMethodMatchesTheCode` pins that section to the constants, so it
is safe to quote — unlike a judged figure, which never is.

**Editing the engine prompt is a `/df-review-reasoning-layer` job, not this one.**
That skill carries the three altitudes, the drift hotspots, and the rule that a
prompt fix which was never measured is a guess. This skill measures; that one
writes. They meet at the seam lane.

## The three lanes

| Lane | Command | Cost | Answers |
|---|---|---|---|
| **seam** | `poetry run pytest -m seam --real-llm` | minutes, cents | did we break a known-fixed seam? |
| **search** | `test_e2e_matrix` + `judge_notes.py` | hours, dollars | is something wrong we haven't named? |
| **archive** | `across_runs.py`, `read_pooled.py`, `read_prereg.py` | free | is a number defensible? |

Lanes are pytest selectors and scripts, not directories: most e2e modules import
`models`, and the certification code and the diagnostic code read the same records, so
splitting the tree would relocate a shared engine for cosmetic gain. Re-measure rather
than trusting a count in prose:

```bash
grep -l "e2e\.models" tests/e2e/*.py | wc -l   # vs: ls tests/e2e/*.py | wc -l
```

### seam — run this after ANY prompt or seam change

```bash
docker compose -f docker-compose.test.yml up -d
poetry run pytest -m seam --real-llm -s
```

Each guard reproduces a measured defect from the archive. The roster (files, and the link
each one guards) lives in the README table and is pinned by
`TestTheSeamLaneRosterIsReal` — if that test fails, a guard was renamed, lost its marker,
or drifted from the table. For the current count, ask pytest rather than this file:

```bash
poetry run pytest -m seam -q --collect-only | tail -1
```

Keep the lane narrow. `-m seam` must not become a synonym for `-m real_llm`: a seam test
drives the *assembled* system and reproduces an archive defect. Single-concern real-LLM
tests and DB-free seam pins stay out (the roster test enforces this and explains why).

### search — the lane that finds unknown defects

The judge and the opponent arm exist because **a regression test can only guard a defect
someone already found.** `2c158bc` (closed without grounding on the pathway it just
built, 0 of 6, with 42 transformations in hand) was unwritable as a regression test —
nobody knew. The comparison produced the knowledge.

So "at par or better" is a **fitness function, not a hypothesis test.** Conflating those
is what produced 23 rounds of arguing about whether a delta resolved while the useful
artifact was the judge's prose. Do not open a significance argument unless the user asks
for a defensible number.

```bash
# narrow first — env vars keep a probe cheap (see README "Selective runs")
DIALEXITY_E2E_ARMS=A1.7,A2 \
DIALEXITY_E2E_SCENARIOS=<scenario> \
DIALEXITY_E2E_TIERS=weak \
DIALEXITY_E2E_STEM=<descriptive-stem> \
poetry run pytest tests/e2e/test_e2e_run.py::test_e2e_matrix --real-llm -s
```

**Then read it. The rationales are the payload, not the delta:**

```bash
poetry run python tests/e2e/judge_notes.py              # worst dimensions, de-randomised
poetry run python tests/e2e/judge_notes.py --all-cells  # won cells too — REQUIRED
```

`--all-cells` is not optional for anything promoted to a finding: notes are selected from
cells the arm LOST, so a behaviour's frequency there is a lead, not a result.

**Before launching anything:** pre-register what would count as a win, in the README,
before the first cell runs. Pre-register n before looking. Every round in the archive
that skipped this was re-argued afterwards.

**Cells are bounded** (`CELL_TIMEOUT_S`, 90 min) because r23 hung 21 hours on one cell of
48 and wrote nothing. A timed-out cell is recorded with `error` and excluded as evidence,
never scored as a weak arm.

### archive — only when a number must be defensible

```bash
poetry run python tests/e2e/across_runs.py
poetry run python tests/e2e/read_pooled.py
poetry run python tests/e2e/read_prereg.py
```

Pooling, bootstrap CIs, `SUPERSEDED` maps and unit-of-analysis arguments defend a
population claim to a skeptical reader. Finding a seam bug needs one lost cell and a
reason. Keep this lane shelved unless publication is the goal.

## The loop the lanes exist to close

```
search: a cell loses
  ▼  judge_notes.py — what did the arm actually DO?
diagnose in src/ (the defect is usually a SEAM: computed -> rendered -> read -> acted on)
  ▼  fix, then prove the fix with a test
seam: new tests/test_*.py with pytest.mark.seam, added to the README roster table
  ▼
commit — the finding now costs minutes to re-check instead of a matrix
```

**A finding that does not end in a seam guard will be re-found next round at full matrix
price.** Every guard in the lane arrived this way.

When adding a guard: mark it `pytest.mark.seam`, add it to the README table with the
count it was born from, and add its stem to `ROSTER` in
`TestTheSeamLaneRosterIsReal` — the test fails until the three agree.

## Reading the framework's standing honestly

The framework is a **distributed prompt**: a dozen concern prompts, three system prompts,
app preambles, tool docs, context dumps. Its characteristic defect is therefore not a bad
prompt but a **broken join** — a value computed and never rendered, rendered and never
read, read and never acted on. `62244f0` (the differentiator was never running) and r23
(a timeout that did not exist) are the same bug wearing different clothes, as were the 16
`@pytest.mark.timeout` decorators that did nothing because `pytest-timeout` was never
installed.

**When a defect turns out to be "the guard was never wired," grep for every other guard
of that shape.** That move has paid three times.

Two standing cautions when interpreting `deltas`:

- **Read per-session, never pooled blind.** The archive's shape puts a loss and a win in
  fixed proportion within one scenario, so a pooled mean is an artefact of scenario
  design.
- **A1.7 is the honest opponent, not A1.** A1.7 is a prose journal written by someone who
  read this framework's design. Beating A1 is easy and uninteresting; the gap over A1.7
  is the typed record's real edge.

And the standing limit: **the search space is barely explored.** Check `NEVER JUDGED` in
`status.py` before saying anything is fine — the framework's own controls (poor-fit,
premature, counsel-with-nothing-to-reason-about) are the cells most able to undercut a
positive reading, and they are the least run.

## House rules for this work

- **Bugs outrank measurement.** If a run surfaces a framework bug, stop measuring, fix
  the bug, then re-run. A number measured over a defect measures the defect.
- **Don't take the theory on faith.** Check `docs/theory/` before asserting what the
  framework should do.
- **Commit, don't push.** Stage explicit paths; concurrent sessions share this tree, so
  check `git status` and `git diff --cached --stat` first, never `git add -A`.
- **Results stay gitignored** (`tests/e2e/results/`), harness code is committed. Renaming
  that directory silently disables the ignore rule — it once swept 208k lines of
  transcripts into a commit.
- **Secrets live in `.env`.** Never put credentials or account-scoped ARNs in committed
  files, including run stems and README examples.
- **One graph-test run at a time.** The autouse cleanup fixture `DETACH DELETE`s around
  each test; concurrent pytest processes against one Memgraph deadlock. A `pkill -9`'d
  run leaves a stuck lock — `docker compose -f docker-compose.test.yml restart`.
- **When something useful shows the framework winning, report it and wait for review**
  before building on it.

## Where things live

| Path | Role |
|---|---|
| `tests/e2e/status.py` | **where we stand** — coverage, unread, deltas (free) |
| `tests/e2e/README.md` | full history, per-round pre-registrations, findings |
| `tests/e2e/judge_notes.py` | the search lane's real output — judge rationales |
| `tests/e2e/scenarios.py` | the situations; `ALL_SCENARIOS` is the declared space |
| `tests/e2e/arms.py` | the ablation ladder (A0/A1/A1.5/A1.7/A2) |
| `tests/e2e/runner.py` | matrix sequencing, `CELL_TIMEOUT_S`, `JUDGED_PAIRS` |
| `tests/e2e/models.py` | every data shape, incl. `invalid_as_evidence` |
| `tests/e2e/test_e2e.py` | the harness's own tests (free, no LLM, no DB) |
| `tests/test_*_weak_tier.py`, `tests/test_*_real_llm.py` | the 8 seam guards |
