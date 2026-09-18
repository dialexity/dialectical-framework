---
name: df-review-reasoning-layer
description: Review the layered prompt system that assembles the framework's dialectical reasoning — across apps, agents, concerns, and shared theory. Reviews at three altitudes — the isolated prompt, the assembled context it lands in, and the whole reasoning chain it steers. Use proactively when writing or modifying LLM prompts in agents/, concerns/, or orchestrator/tools/.
paths: src/dialectical_framework/agents/**, src/dialectical_framework/concerns/**, src/dialectical_framework/agents/orchestrator/tools/**
---

You are reviewing or writing LLM prompts in the dialectical-framework.

Context from user: $ARGUMENTS

## Core principle: prompts are not isolated

The prompts are scattered across many files, and the reasoning framework **assembles** them at
runtime to steer reasoning according to the dialectical theory. A single LLM call's context is
composed from layers authored in different files: an app preamble + an agent system prompt, or a
concern's SYSTEM_PROMPT + a per-call `_*_prompt()` + DTO field descriptions + interpolated theory
constants. And each call is one step in a chain — its output becomes the next call's input, or feeds
a score-gate.

So a prompt can be **internally flawless and still be wrong**: it can contradict the app preamble it
fuses with, restate a theory constant that has since drifted, shift a score distribution that changes
what passes a downstream gate, or diverge from a sibling agent's wording across a handoff.

Review at **three altitudes**, in order. Escalate to the next only when the edit's blast radius warrants
it — but a change to shared theory, a score, a taxonomy, or agent-handoff vocabulary **always** reaches
Altitude 3.

**Fixes are not always text.** When the same theory lives as prose in N prompts, the right fix is
usually **structural** — make the prose derive from the single-source constant (as
`explorer/system_prompts.py` `_ladder(INSIGHT_SCALE)` already does), not re-sync copies by hand. Flag
these; a text patch that re-syncs by hand just resets the drift clock.

---

## Altitude 1 — The isolated prompt

Craft/quality of the prompt in front of you. (Original checklist — still necessary, no longer sufficient.)

### Writing principles
1. **Positive specification over negative constraint.** "Format as X" beats "Don't format as Y".
2. **One concept, one word.** Never use the same word for two concepts. If "statement" means both a
   thesis node and a user utterance, rename one.
3. **Concise and dense.** Every sentence carries information. Shorter prompts perform better.
4. **No conflicting instructions.** Don't combine contradictory directives; consolidate into one authority.
5. **Concrete examples over abstract rules** where format/style could be misread.
6. **Explicit output format** (Pydantic schema, table, bulleted list) — don't hope the model infers it.
7. **Context / Instructions / Format separation.** Don't mix "who you are" with "what to output."

### Anti-patterns to reject
- **Patch-stacking** ("IMPORTANT: NEVER…", "CRITICAL: ALWAYS…") on top of existing instructions. Diagnose WHY it failed; don't add emphasis.
- **Redundant emphasis** — same instruction in multiple forms. Consolidate.
- **Model-specific forks.** Fix for Haiku (weakest model); Sonnet/Opus follow.
- **Negative-only constraints** — "don't use jargon" without saying what vocabulary TO use.
- **Unbounded generation** — no length/format constraint. Use `self.settings.component_length` / `transition_length`, never hardcode.

### Diagnose → fix (for a prompt producing wrong output)
| Failure pattern | Root cause | Signal |
|----------------|-----------|--------|
| Wrong term/format | **Polysemy** | Same word, two concepts |
| Oscillates between behaviors | **Competing signals** | Two sections contradict |
| Invents wrong structure | **Missing example** | No concrete output example |
| Does the opposite | **Negative-only constraint** | "don't X" without "do Y instead" |
| Ignores a rule the prompt clearly states | **Rule is context, not a step** | A numbered procedure exists and the rule is not one of its steps |

Fix, first applicable wins: (1) add one concrete example; (2) positive specification; (3) reduce polysemy; (4) consolidate competing sections; (5) move the rule into the procedure.

**Check the procedure before concluding "weak compliance."** These two look identical
at the output and have opposite fixes: a rule the model *under-weights* (fix: consolidate,
make it proximate) versus a rule the numbered procedure *omits* (fix: make it a step —
emphasis does nothing). `aspect_generation.py` stated R1 parentage correctly and
symmetrically in the shared `ASPECT_DEFINITIONS` constant the whole time, while
`_tetrad_prompt` told the model to (1) name the axis, (2) place each aspect at an opposite
end of it. Neither step mentions the parent. The model complied exactly, and 10 of 36 A-
slots took the other pole's exaggeration. **A numbered procedure outranks every
non-procedural layer in the same context** — if a rule matters, it is a step.

**A verification criterion stated where a derivation rule belongs becomes the derivation
rule.** "A- contradicts T+" is a CHECK on a finished A-, never a recipe for building one:
both poles can supply a negative end of one axis, so negation alone leaves the parent
undetermined. That prompt supplied the check three times (axis field, diagonal pairing,
"opposite ends") and the recipe zero times. When you write a constraint, say whether it
builds the thing or tests it.

**A bare-noun worked example teaches only the relation it annotates.** The same file's
Love/Indifference examples annotated parentage (`T+ = Bonding (Love developed)`) while
Courage/Fear were bare (`T+ = Trust ⟷ A- = Paranoia`) — teaching the axis and nothing
about where either end came from, in the example set nearest the output. Annotate every
worked example with every relation it is supposed to teach.

---

## Altitude 2 — The assembled context

What ELSE lands in the model's context window on this call? Load
[reference/systemic-map.md](reference/systemic-map.md) §1 for the two assembly stacks and the
co-occurrence hotspots. Then:

- [ ] **Identify the assembly stack.** Agent prompt (Stack A: `app_preamble` + `SYSTEM_PROMPT` fused into
      one system message)? Or concern (Stack B: `SYSTEM_PROMPT` + `_*_prompt()` + DTO `Field` descriptions)?
- [ ] **Read the co-occurring layers, not just the file you're editing.**
    - Agent prompt → open the app preambles it fuses with. For Analyst that means **both `NAVIGATOR_APP` and
      `NAVIGATOR_APP_ADVANCED_TOGGLE`** (`NAVIGATOR_APP_ADVANCED_TOGGLE = NAVIGATOR_APP + override`); for the counsel
      toggle, **both** `NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER` and its `_ADVANCED` pairing (same shared
      `_ADVISORY_REGISTER` body on a different base, plus a trailer that gets the last word); for Advisor, all five personas. Check the edit
      doesn't contradict the preamble's vocabulary / score-presentation rules (esp. the "communicate as MEANING
      not numbers" default vs. `NAVIGATOR_APP_ADVANCED_TOGGLE`'s "show numeric scores").
    - Concern → check the SYSTEM_PROMPT, the `_*_prompt()` user content, AND the DTO field descriptions
      (Mirascope sends them). Inline examples must not contradict interpolated constants or field text.
- [ ] **DTO `Field(description=...)` is prompt surface** — review it too.
- [ ] **Every line-oriented dump section must `one_line()` any model- or user-written text it interpolates.**
      The `# Decisions` ledger, the `#### Transformation` block and the perspective dumps all teach the model to
      parse by line prefix (`Stance:`, `Validation:`, `- adopted pathway:`), so one raw newline lets generated
      content fabricate sibling entries. Found twice: `Stance:` (guarded), then `_dump_transformation`'s
      `instruction` (2026-09-15, a pathway forging `## Decision [[fakefak]]` with a spoofed `Validation:` line).
      When you put new prose on a dump line, that is the check — not whether the prose looks benign.
- [ ] **"Something reads it" is not enough — ask WHEN the reader runs.** A value can be written, rendered into the
      prompt every turn, and genuinely read by a prompt rule, and still be dead if the rule's moment and the
      write's moment are different turns. The feasibility band's only behavioural reader is "when OFFERING
      pathways, prefer high-feasibility first", while the automatic audit scores the pathway a decision is ALREADY
      grounded on, at the last turn of the session — reader and writer never met (traced 2026-09-15; see the
      feasibility entry in [reference/systemic-map.md](reference/systemic-map.md)). Proximity is the other half:
      a number correlated to the record by hash alone, in a block that may not be rendered at all, is not on the
      line the model was told to reassure from. **Fix by moving the value ONTO the line the rule reads, not by
      adding prompt text telling the model to go look** — the band now renders on both the pathway menu
      (`pathway_line`, where the offer is made) and the decision ground line (`adopted_pathway_summary`, where it
      is remembered), sharing one `feasibility_suffix` so the two cannot disagree, and neither prompt changed.
      **That fix has a bound, found one round later: moving the value onto the line only works where a rule already
      reads the line at that moment.** On a wobble turn nothing did — the re-audit instruction never mentioned
      feasibility — so the band sat on the ground line with no reader, and that half genuinely needed prompt text
      (`_FEASIBILITY_ON_A_WOBBLE`, 2026-09-15). So run the WHEN question in both directions: for each moment the
      value matters, ask whether a rule fires there, and only then whether the value is on the line that rule
      reads. Render fixes the second; nothing but prompt fixes the first.
- [ ] **REACHABLE IS NOT AVAILABLE: a prompt cannot traverse.** When a fact the model needs is one hop away in the
      graph, the temptation is to call it already present — it is derivable, nothing is lost, a reader could get it.
      But if the consumer is a rendered dump (`_dump_decisions`, the perspective dumps, the pathway menu), the only
      facts that exist are the ones some renderer walked to and PUT on a line. `Transformation.get_wheel()` recovers
      a recipe's arrangement in one hop, and the decision ledger still could not name the circle a step closes until
      the Wheel was grounded as its own edge (2026-09-18; see the four-things paragraph in
      [reference/systemic-map.md](reference/systemic-map.md)). So when reviewing a dump, ask what it would take to
      answer each question the prompt asks the model to answer — if the answer is "a second query", the fact is
      missing, however short the path.
- [ ] **Runtime splices.** Explorer embeds `nexus_hash`/`nexus_intent`; Advisor embeds the whole
      `{dialectical_context}` dump. Your edit must tolerate an empty/"fresh conversation" block and untrusted
      interpolated text.
- [ ] **Assert on the interpolated module attribute, not `inspect.getsource`** — f-string prompts show the
      literal `{CONST}` token in source, not the resolved text.
- [ ] **Section ORDER in the Advisor engine is a cost contract, not a layout choice.** The provider's cache
      breakpoint is placed at the `"\n\n## Current Understanding\n\n"` seam (`split_system_for_cache`), which
      only works while `_CONTEXT_SLOT` is the LAST section `system_prompt()` appends and that heading is unique
      in the render. Append a section after the dump, or repeat the heading in prose, and prefill cost on every
      post-write turn goes up ~6.8x — silently, because the split fails soft by returning the prompt unchanged.
      `tests/test_prompt_cache_split.py` is the tripwire; run it with any section-order edit.
- [ ] **A `gather` over `isolate()` branches pays for prompt caching and gets nothing back.** Mirascope stamps a
      cache breakpoint on the last message of any multi-turn request, so each branch WRITES its copied history at
      1.25x — and concurrent siblings cannot read what a sibling has not finished writing. Measured at 184,438
      tokens written / 0 read per 120 KB ingest (`tests/e2e/probe_ingest_cost.py`). If your fan-out copies a long
      history, the cost question is how much history it copies, not whether caching will absorb it; see the
      caching CORRECTION in [reference/systemic-map.md](reference/systemic-map.md).
- [ ] **Trimming a fan-out's copied history is a REASONING change, and "the prompt already contains the item"
      does not make it safe.** Dropping the source from `ThesisExtraction`'s step-2 branches has now been
      measured TWICE and taken NEITHER time, so treat this as a closed lever and not an outstanding
      optimization. The no-history arm (system prompt only) is worth 8.5x at `CHUNK_SIZE` and was rejected
      because, with both self-consistency floors at 0.0%, the arms disagreed on 5.6% of items and every
      disagreement was `is_substantive` flipping the same way — the gate ADMITS what it would otherwise reject,
      because "substantive" means "adds something to THIS document" and no item states that about itself. The
      elided-source arm (step 1's request and answer kept, the window replaced by a sentinel) keeps the sibling
      items for exactly that reason, is worth 6.7-7.2x, and moved no keep/drop decision at all — 0.0% in each of
      three runs, 216 paired comparisons, on 0.0% floors. It is still not the default, and **the reason matters
      if you reopen this: not that it lost, but that the protocol never settled.** The same preregistered
      endpoints returned don't-take, take and no-call on three same-day runs. Generalize the mechanism anyway:
      **ask which of a call's judgements are properties of the item and which are properties of the item's place
      in the source**; only the first survive losing the history. Both arms remain shipped behind
      `extraction_step2_carries_source` (default `True`) so a corpus with different economics can opt in
      (`tests/e2e/probe_step2_isolate_ab.py`, `tests/test_thesis_extraction_step2_source.py`).
- [ ] **An A/B over LLM judgements needs a self-consistency floor per arm, a decision metric restricted to fields
      code actually READS, and a positional control on any judge.** All three changed the verdict of the probe
      above. Its judge put 62%, then 47%, then 73% of decided calls on whichever set was shown first, so
      alternating labels without REPORTING the raw split would have laundered a positional bias into a fake
      50/50 between arms — an apparent 7-2 lean died under that fix. A cross-arm rate with no within-arm floor
      beside it is not a finding, and a run whose positive control fails to reproduce is not evidence of
      agreement, only of an insensitive instrument (that control reproduced in 1 of 3 runs here, which is the
      honest statement of the instrument's resolution).
- [ ] **A PAIRWISE judge carries two nuisance variables — set SIZE and set POSITION — so prefer an UNPAIRED
      per-item rating whenever the question allows one.** Both bit the probe above. Control size directly by
      judging one arm's set against a randomly trimmed copy of ITSELF (identical provenance makes "tie" the clean
      answer; trim randomly, not from the tail, or you are testing coverage of the ending). Then drop the pairing
      where you can: `_support` rates every candidate against the source alone — no other set to be longer than,
      no position to prefer, no tie to hide in, and a denominator in the hundreds instead of twelve. It found a
      2.4pp difference inside a 38pp within-arm swing where the paired judge had been reporting a lopsided
      preference across three runs. **And an endpoint that counts ties against detection is decided by the
      judge's tie rate**, which was the least stable thing it did (1, 6, 4 of 12) — pool runs before moving a
      default, and treat any single-run verdict as provisional.
- [ ] **An unpaired rate is only as quotable as its instrument, and validating one takes SPIKES INSIDE REAL
      BATCHES — plus persisted per-item verdicts, or the rate is unfalsifiable by construction.** The judge
      recommended above went on to report ~44% of extracted claims as unsupported, which sat in CLAUDE.md as an
      unquotable lead until `tests/e2e/probe_support_validity.py` measured it: specificity 93%, sensitivity 100%,
      FIT TO QUOTE, finding intact at 35-39%. Three transferable parts. **A homogeneous control set does not
      transfer** when the judge batches a LIST into one call, because a claim is judged among its neighbours — so
      shuffle known-truth spikes into real output and send them through the IMPORTED judge (validating a
      reimplemented copy validates nothing). **Author the confound you suspect as its own class**: "distorted
      catches legitimate compression" became a registered ±15pp endpoint and measured +17pp, confirming the
      mechanism instead of hand-waving it. **And hold wording exactly constant where you can get it free** — every
      out-of-source spike was another document's verbatim spike, so identical strings were judged against a source
      that states them and one that does not (18/18 vs 0/18), which no argument about spike authorship can
      explain away. The original probe printed rates and discarded the claims, so its 44% could not be audited at
      any price short of re-running; persisting all verdicts is what later bought the per-label decomposition
      (`invented` 0/39 false positives and quotable uncorrected, `distorted` 5/39 and needing correction) for
      free, after the run. **A judge's LABELS may be separate instruments — decompose before correcting.**
- [ ] **"Read by no code" is not "harmless" — a field can be unread while the thing it DESCRIBES is the
      output.** Restricting the decision metric to `is_assertable & is_substantive` was right (they are what
      `_step2_identify_candidates` branches on) but the corollary drawn from it was wrong for a year: `is_atomic`
      is read nowhere, yet the same call's `atomic_theses` IS the candidate list, so the two move together and a
      pure-`is_atomic` disagreement means the arms CUT the item differently. The instrument that catches that is
      **candidate yield**, not the gate rate — the no-history arm agreed with the default on every keep/drop and
      still produced 18% more candidates. So when a preregistered endpoint covers only the branch condition,
      carry a second, unblinded count of what the call actually emits, and say plainly which one the verdict
      rests on.

---

## Altitude 3 — The systemic review (theory + chain + cross-agent)

The edit touches shared theory, a score, a taxonomy, or vocabulary that crosses an agent handoff. Load
[reference/systemic-map.md](reference/systemic-map.md) fully — it carries the theory-ownership table, the
drift-hotspot catalog, the pipeline seams, the gates, and the cross-agent parity matrix, each with grep-able
anchors.

### Theory fidelity (the 8 generative rules)
- [ ] **A stated invariant is only as strong as the queries that honour it — so grep the CLASS, never
      trust the sibling you happen to be reading.** CLAUDE.md says every listing/discovery query MUST
      filter `WHERE n.hash IS NOT NULL` (the `saved_at`/`hash IS NULL` garbage convention). Two of the
      three wheel reads did not, for months, while `find_by_nexus` sitting between them did — and the map
      entry describing that one as "committed-only" read as if it covered all three. What made it a
      reasoning defect rather than stale rows: `find_by_layer` feeds probability normalisation across
      competing alternatives, so an abandoned wheel is a PHANTOM ALTERNATIVE, and
      `find_by_component_sequence` is the dedup read, so returning one makes the builder skip a real
      wheel. When you fix such a query, pin BOTH halves: that the ghost is excluded (the test must fail
      without the fix — verify by reverting it) and that committed structure is still returned, since a
      predicate that drops everything satisfies the first half perfectly. And check whether the filter
      closes a live hole or is only a guard; say which, because a guard whose safety comes from caller
      habit is one refactor from being a hole. **And grepping the class is still not enough: the third
      instance of that same hole, found 2026-09-15 by rendering the prompt rather than reading the
      repositories, was `DialecticalContext._get_cycle_wheels` — a RELATIONSHIP TRAVERSAL
      (`cycle.wheels.all()`), which no sweep over `*Repository` queries can reach. When an invariant is
      about node state rather than about SQL, enumerate every way the node is REACHED, traversals
      included, and prefer proving it at the surface the invariant exists to protect (here: is the ghost
      in the rendered prompt?) over proving it query by query.**
- [ ] **Single-source-of-truth for scales.** Any prompt stating HS / complementarity / area / Ks / insight /
      proactiveness / mode / arousal bands must **interpolate the constant** (`HS_SCALE`, `COMPLEMENTARITY_SCALE`,
      `ASPECT_DEFINITIONS` from `scoring_scales.py`; `INSIGHT_SCALE`, `PROACTIVENESS_SCALE`, `POLAR_PAIRS` from
      `ac_re_taxonomy.py`) — never hand-type bands. If semantics change, edit the constant. See §3 for the
      current hand-typed offenders; prefer the structural fix (derive prose from the constant).
- [ ] **Taxonomy dict/table lockstep (R8, top hotspot).** Editing `SYSTEMIC_TAXONOMY`/`ELEMENTAL_TAXONOMY` OR
      the hand-typed taxonomy table in `statement_classification.py`'s SYSTEM_PROMPT requires updating BOTH — the
      LLM classifies against the table while `lookup_aspect_apex` scores HS against the dict. Divergence = silent HS corruption.
- [ ] **Circular-causality directionality (R2).** Keep `Ac+ = this edge's T-→A+`, `Re+ = the OPPOSITE edge's
      T-→A+` (i.e. `source.opposite`/`target.opposite`), and "Ac+ without Re+
      degenerates into Ac-, Re+ without Ac+ degenerates into Re-". Restated across 4+ prompts with no owner —
      verify all agree. **The SUBJECT is preserved and its own polarity flips**, exactly as at the aspect level
      ("T+ without A+ yields T-", `control_statements_check.py`; "What T itself degenerates into when A+ is
      absent", `scoring_scales.py`). This checklist itself carried the mirrored version until 2026-09-11 and
      would have enforced the bug: `transformation_generation`'s CC block and the Ac-/Re- prompt bodies each
      described the OTHER position's mechanism, while lines 85/87 of the same prompt stated the rule correctly.
      A swapped subject reads plausibly, so check the subject, not just that a "without" sentence is present.
      `Re+ = A-→T+` is the **1-Polarity collapse only** — true when the edge joins the two sides of one
      Polarity, so `source.opposite == target`. Treat that shorthand as a defect on any wheel with ≥2
      Polarities. Ground truth is `explore_transformations._create_transformation` (Ac side from the
      segments, Re side from their `.opposite`); ~10 sites stated the collapse as the general rule until
      the 2026-09-11 sweep, two of them model-facing (`GRAPH_SCHEMA`, Explorer system prompt). Locked by
      `TestReSideLivesOnTheOppositeEdge`. The one place it is still written bare is
      `transformation_generation`'s worked example, which is correct because it declares itself "1-PP".
- [ ] **Never ask a negative to REFINE.** Refinement is concreteness at one valence; degradation is valence at
      one grain (the R2 rule above). `build_coarser_context` renders only a parent's `Action:` (its Ac+) and
      `Reflection:` (its Re+), so the only coarser lines that exist are POSITIVES — telling Ac- to be more
      concrete than the parent's Ac+ asks it to refine the statement it is defined by contradicting. Hence
      `REFINE_TETRAD` names no position (it points at the whole transition) and `REFINE_REFLECTION` names `Re+`
      explicitly, because `ReSideCompletionDto` returns Re+ AND Re- from ONE call. Generalize: **when one call
      produces two positions, an instruction that names neither is an instruction to both** — and the tidy-up
      that breaks it ("your reflections refine it") passed every pre-existing test, since
      `test_the_three_instructions_differ` pinned only "Reflection line". Locked by
      `TestTheNegativesAreBoundByValenceNotConcreteness`, which asserts the renderer's omission at the renderer
      because the wordings rest on it.
- [ ] **Diagonal contradiction (R1).** "T+ contradicts A-, A+ contradicts T-, and this is NOT a K defect."
      An edit must not imply lowering K (contradicts `COMPLEMENTARITY_SCALE`) and must match `get_contradiction_pair`.
- [ ] **A plus that only restates its own pole fails R1, and it is the most common measured tetrad defect
      (13.3%).** R1 says T+/A+ are "constructive developments that actively **balance the other side** (not
      merely 'positive')" — so "Team-driven toolchain choices enable rapid local optimization" on the autonomy
      pole is a defect, not a plus: it names that pole's native benefit and takes up nothing standardisation
      offers. `probe_option_pair_tetrads.py` audited 128 plus slots on the weak tier and found **17 (13.3%)
      restating their parent**, against 3.1% minus-misparentage — i.e. the defect the probe lane chased across
      three runs is **four times rarer** than the one sitting beside it in the same audit output. When editing
      `aspect_generation.py`, the load-bearing clause is the "takes up what the opposition offers" half, NOT the
      parentage half; check it is a positive specification with an example, since "develops T" alone is
      satisfied by a restatement. **The fix shipped as a CHECK, not a fifth restatement, and that choice is the
      transferable part:** the take-up clause was already asserted four times (`ASPECT_DEFINITIONS`, the
      `TetradDto` plus fields, `_tetrad_prompt` step 1, both sibling prompts) and ran at 13.3%, while
      minus-parentage — the one rule with a re-read step in the numbered procedure — ran at 3.1%. Forcefulness of
      statement was not the difference; being verified was. So `PLUS_RESTATEMENT_CHECK` is stated ONCE and
      interpolated into all three generation paths (`test_prompt_review_regressions.py::TestPlusTakeUpIsChecked`
      pins that, including that it is absent for minus positions — asking a minus not to develop its parent
      one-sidedly would invert R1). **Measured: 16.1% → 7.8%, Fisher p=0.0176 on 192 plus slots per arm
      (`tests/e2e/probe_plus_takeup.py`) — a check beat four restatements of the same rule.** Registered verdict
      is INDETERMINATE anyway (the 4.4% ceiling was not reached), and the run had 0.97 power to see that ceiling,
      so the honest statement is "roughly halves it". Two caveats travel with the number: the interpolated check
      and the worked example landed together, so the mechanism is unseparated; and **that run also found the
      archive's minus base rate moving 3x between two runs of one instrument (p=0.0406), so do not size or judge
      anything here on another run's rate — use a within-run arm.**
- [ ] **A risk the person wants dropped stays priced (R1 dialogical + R5.1).** `_INTERNAL_MODEL` distinguishes a
      correction about their SITUATION (take it — they are the authority) from an instruction to delete T−. Their
      fact resizes the price, or it dissolves the tension and takes that side's pull with it — **"never zeroes it"
      was the wording for three runs and it was wrong; see the fork entry below**. Deleting T− strips the
      `accepted_cost` a decision is priced on AND
      Ac+'s source term (T−→A+), so the loop has nothing to transform → S−. `_HOW_YOU_SPEAK`'s "concede in the
      first clause" must keep pointing at that boundary — the two read as contradictory otherwise, and the ladder
      measured every arm folding to the weakest possible push (72/72 cells at rung 1) when only the concede rule
      existed. Any softening needs the person's-call-still-wins half intact: they may have it out, carried as a
      cost they chose not to confront, never as a risk that turned out not to exist.
- [ ] **An escape clause must be ORDERED behind the obligation, not offered beside it.** The first version of the
      rule above put the person's-call exit in the same paragraph as the duty, worded "if they hold the line and
      want it out anyway". A model reads a first bare "no" as holding the line: the firing probe measured the rule
      reaching the output (4 of 12 rung-1 replies used its own price vocabulary vs 0 of 12 pre-rule) while the
      endpoint did not move (1 of 12 held), because two cells folded *by invoking it* — offering to record the risk
      as an "accepted cost" on turn one. That is worse than a plain fold: the record then claims a cost was weighed
      that was never priced. **Generalise past this rule** — any prompt granting an exception must say what has to
      happen FIRST and on which turn, or the exception becomes the default path. And note the diagnostic that told
      the two failure modes apart: a rule the model never reads and a rule it reads and misapplies fail identically
      at the endpoint, and have opposite fixes (`tests/e2e/probe_rung_firing.py::price_vocabulary`, free).
      **Ordering it worked, and measurably: 8 of 12 vs 1 of 12, p=0.0003 against the most generous
      pre-registered null** — the archive's first prompt edit to move a pre-registered behavioural endpoint at
      conventional significance (r20-probe; still a screen, same lane at n=12, A1-only). **But only the clause that
      was ordered landed.** All 8 holds then folded at rung 2, where the person supplies a real fact, and the
      arithmetic clause never governed the reply: **10 of 12 zeroed the price, 2 resized it, p=0.9968** against a
      pre-registered "resize is modal" bar (`tests/e2e/probe_price_arithmetic.py`, free — it re-reads r20's saved
      replies). So *price-before-permission* (sequence) and *what a fact does to the price* (arithmetic) are two
      clauses of one paragraph, and fixing the first left the second untouched. **Check each clause of a
      multi-clause rule separately — a rule is not one instruction, and an endpoint that moves can hide a clause
      that never fired.** The mechanism came from the transcripts, not the count: 10 of 12 retire the advisor's
      own named ROUTE to the risk and treat that as retiring the price (*"that read was mine, not yours to
      inherit"*), so the missing thing was a distinction (**a route is not a price**), not emphasis — and two
      cells prove emphasis would not have helped, one negating the clause verbatim and one borrowing its
      `unconfronted` vocabulary to certify the write-off. **A rule can be read, quoted, and routed around**;
      when it is, emphasis is definitely not the fix.
- [ ] **But the distinction was not the fix either — and naming a seam can teach a cleaner way to cross it.**
      The obvious next move above (*add the distinction it lacks*) was made and measured: `b28ebf5` added "a fact
      can retire the MECHANISM you named without retiring the price", with the two tells the transcripts supplied.
      **It did not land: 1 of 12 resized against a pooled pre-fix 2 of 24, one-sided Fisher p=0.72** — the point
      estimate BELOW baseline (r24-probe; hand-labelled, same lane/model/n). And the failure is instructive rather
      than merely null: the edit demonstrably reached the output (**"mechanism" appears in 0 of 24 pre-fix cells
      and 5 of 12 post-fix**) and **four cells used the fix's own distinction to certify the write-off** —
      *"That retires the RISK I was pricing, not just the way I was describing it"*, *"it changes the mechanism,
      not just the framing"*. The rule says the mechanism goes and the price stays; they assert the fact went
      *deeper* than the mechanism, which reads as satisfying the rule while doing the opposite. **Handing a model
      a distinction hands it the vocabulary to claim the exempt side of it.** Three shapes of edit (emphasis,
      ordering, distinction) on one behaviour, and only ordering moved anything. So: **after two failed edits on
      the same clause, stop editing and ask whether the rule has a structural home** — here, a
      `record_decision`-side check that an `accepted_cost` was actually priced, which prose cannot enforce and a
      prompt-only lane cannot test. Also pinned: **check the scenario before writing a fourth edit.** The cheap
      rescue for a repeated null is "the endpoint was wrong all along"; it was checked and REFUTED (rung 2 argues
      relationship ownership, the priced risk is ~60% revenue concentration — a structural fact no ownership claim
      touches), and it is now a test rather than a paragraph
      (`test_e2e.py::TestR24MechanismDistinctionResult`) so it cannot decay back into an open question.
- [ ] **Three failed edits later, the check that should have run first was the THEORY check — the rule itself was
      wrong.** Emphasis, ordering and distinction all tried to make the model obey *"a fact cannot make the price
      zero"*. Nobody asked whether that absolute is a framework claim. It is not:
      `docs/theory/generative-rules.md` labels the dialogical reading of T− as the price *"the framework author's
      gloss, 2026-08 — not a paper claim"* — the same species as "structurally blind", and the second time an
      application gloss hardened into a prompt rule and then into a measured null. Sometimes a fact really does
      kill a risk, so 11 of 12 cells were arguing with an absolute the theory does not support, and **a rule the
      model is right to resist cannot be rescued by wording.** What theory carries is Rule 3.2, `M(T+) = -M(T-)`:
      a genuinely zeroed price does not yield a cheaper tetrad, it DISSOLVES the tension and takes that side's pull
      with it. So the rule is now a **fork with two priced exits** — name the smaller price, or say the tension is
      gone and give up the recommendation that rested on it — plus a discriminator that is deliberately NOT a depth
      judgement ("is there still a reason to want this side?"), because depth is the axis four r24 cells claimed in
      order to fold. **Generalise: before the second wording attempt on any rule, check that the rule states a
      theory claim and not a gloss** — `docs/theory/` marks its own glosses, so this is a grep, not a judgement
      call. And note the shape: the previous three edits all assumed the rule was right and the wording wrong.
      **Knowingly crossing this file's own "stop editing after two" guidance**, on the argument that changing what
      a rule SAYS is not a fourth attempt at making the same rule land, and that the structural home named above
      (a `record_decision`-side priced-`accepted_cost` check) does not reach this behaviour at all — the rung-2
      lane is a conversation about a risk with no record in it. Pre-committed before the run: **if the fork nulls
      too, the conclusion is that this rule is not prose-enforceable, and no fifth wording gets written.**
      Pinned by `test_a_corrected_fact_has_two_exits_and_both_cost_something`; uses modality balance as reasoning
      only and wires no check (R3.2 status: diverges, deliberate non-enforcement).
      Two further transfers. **An absolute with no legitimate exit gets argued with — price the escape instead of
      forbidding it.** The write-off was free because the prompt offered no priced way out, and "never" is the
      wording most likely to be the gloss rather than the claim. And **when you add a legitimate exit, add the
      check for it being abused, and read that check BEFORE the endpoint** — a model that takes the new exit to
      avoid the obligation has found a cheaper route, which is a finding against the fix however good the endpoint
      looks (`DISSOLVE_OVERSHOOT_MIN` in `probe_price_arithmetic.py`; the label requires both halves of the exit,
      so the failure shape it replaces cannot relabel itself into a pass).
      **RESULT (r25, 2026-08-20): the fork moved the reply and did not reach the record.** Rung-2 resizing went
      from a pooled 3/36 under the old absolute to **6/12** (one-sided Fisher p=0.0042) — the first of the four
      edits to move this clause at all, and it moved once the rule stopped asserting something false. It **missed
      the pre-registered absolute bar** (`LANDED_MIN_SHARE`, `share > 0.5`, needs 7) and landed on the single
      integer r25's own pre-registration gave two incompatible readings of; resolved against the fix, with the
      defective bands row left standing and corrected in place. The overshoot check did not fire (`dissolve` 0/12),
      so the second exit is written and **untested**. **The finding that matters for prompt work: 3 of the 6 price
      the residual in the reply and then write it off in the decision record they offer in the same breath** —
      including one that reaches for `unconfronted cost`, the vocabulary this very rule names as a folding tell.
      That shape appears in none of the 36 pre-fork cells. So **a prompt rule can reach the prose and stop at the
      artifact boundary, and the prose is where you will look**: when a rule's whole point is what gets *recorded*,
      measure the record, and expect the fix to be a tool-side check rather than a better paragraph. The
      `record_decision`-side priced-`accepted_cost` check is now the next move on evidence, with three real replies
      it must refuse. Sequence clause, third reading: 11/12 (was 8/12, 8/12).
      **BUILT (2026-08-20): check 5 in `DecisionCoherenceCheck`, and the shape of the fix is the lesson.** The gap
      was not a missing rule — checks 2 and 3 already say a price must be named and must not be argued away — it
      was that **the auditor was never shown the price it should have looked for.** Check 2 reads the cost that WAS
      cited and check 3 what the rationale ARGUED, so a record merely SILENT about its price cleared both by
      construction (archive-wide: no-`accepted_cost` decisions pass **17 of 19** against 68 of 120 with one). So
      `RecordDecision._unpriced_aspects` resolves the overdevelopments the cited tensions carry and the record did
      not, and passes them in. **Generalise: an omission check needs the omitted thing supplied to it — diagnose
      whether the auditor CAN SEE the failure before writing more prompt at it.** Two further transfers, both about
      not over-claiming: reach is **5 of the 19** (5 cite only a pathway, 9 cite nothing at all and stay check 2's
      documented exemption), and the probe prints that shortfall on every run, because *a check motivated by a big
      asymmetry and reaching a slice of it must publish the slice*. And the false-positive half is pinned harder
      than the true-positive one — flagging every record with no cost EDGE would audit bookkeeping and, given the
      incentive above, teach the model to attach a cost it never weighed, so "priced **in its own words**" passes.
      Details, including why `_unpriced_aspects` returns nothing once any cost is attached (the leftover would be
      the *opposite* side's minus, i.e. what the choice avoids), in the reference map under "A price nobody
      recorded".
      **AND THE NEXT MOVE TURNED OUT TO BE ALREADY BUILT (2026-08-20) — check whether the structural home exists
      before building it.** "The `record_decision`-side check … is now the next move, with three real replies it
      must refuse" was written as a build order. It was a MEASUREMENT order: check 3 already names *immaterial*
      verbatim and already splits on the verdict rather than on the evidence, so the open question was never
      *write it* but *does it reach this shape* — and the shape genuinely was new, because every other REFUTED
      case in the archive denies the risk from the first sentence while these concede the residual, price it, and
      void it in the record. Measured as a fourth pair in
      `tests/test_decision_rationale_integrity_weak_tier.py` (rep 9's record line against rep 6's on a
      **byte-identical body**, weak tier, pre-registered at ~65%/~85%): **both halves held**, the flag quoting the
      deciding clause and the twin passing clean. Two transfers. **When a probe names a tool-side fix, spend the
      two calls asking the existing check first** — four prompt rounds on this clause cost far more than the pair
      that answered it. And **a "new shape" is worth testing even against a check whose prompt appears to cover it
      in words**: coverage of the vocabulary is not coverage of the case, and the case here inverts the order the
      prompt's examples assume (price first, void second). Note precisely what this does and does not license: the
      shape is caught at the record on the framework path and cannot be caught on the prompt-only path, which has
      no record — but it is a **mechanism** claim from 2 isolated calls, not a lane result, and the check is
      fail-soft, so the person is handed a named flag rather than stopped.
- [ ] **A hand-labelling pre-registration is worth its cost, and here is the receipt.** r24's regex reported the
      SAME headline count as the hand labels (1 resize) while inverting both cells that mattered: it scored the
      cell that says *"Dropped, fully — not resized"* as a resize, and missed the one genuine resize. A
      regex-first read would have published a correct number from a broken classifier. When a fix under test
      raises the vocabulary a classifier keys on, the classifier's error runs in the direction that manufactures
      a win — disqualify it in the pre-registration, before the run, and print its agreement against the labels.
- [ ] **Do NOT invent enforcement of prompt-absent rules.** Modality balance (R3, zero-sum) and apex coherence
      (R7, convex hull) live only in theory/TODOs — no prompt enforces them. Reject edits that *claim* to
      enforce them without wiring the check (`synthesis_generation.py` TODOs).

### Chain coherence (output → input)
- [ ] **Guard the SIMPLE/COMPLEX boundary.** Any edit to a thesis-generation/anchor prompt OR to
      `StatementClassification` can flip theses to SIMPLE → mechanical negation with HS forced to 1.0 →
      inflates every polarity past `HS_THRESHOLD=0.7` → Analyst tells the user a weak framing is strong.
      Regression-test classification stability. **Measured baseline** (`probe_classifier_stability.py`,
      47 texts × 6 readings, weak tier): the SIMPLE/COMPLEX boundary itself holds — **0 flips in 47** — but
      the BRANCH under it does not, and only 38% of texts return the same (family, domain, branch) six
      times. So this checklist item is about the boundary; the branch is a separate hazard (reference §3.1a)
      and it is already unstable before your edit. Any before/after you run downstream of the classifier
      must pin or record the classification, or the two arms are not the same prompt.
- [ ] **A prompt that sets a score is a gate input.** `AntithesisExtraction` / `AntithesisClassification` /
      `TransformationGeneration._score_hs` feed `_rank_polarities` (0.7) and consolidation bands (0.7/0.1). A
      wording change that shifts the distribution changes what passes — review the gate, not just the call.
- [ ] **A reference must be derived from the frame it scores.** `AcReApexDerivation` builds the Ac+ apex from
      THIS edge and the Re+ apex from the OPPOSITE edge (`source_segment.opposite, target_segment.opposite`),
      because that is where each path runs and where `TransformationGeneration` generates each position from.
      Until 2026-09-11 it read both apexes off the own edge, so every Re+ HS score on a wheel with ≥2
      Polarities compared a path against a reference through different nodes. **Neither module was wrong on
      its own — only the pair disagreed**, which is why this needs a cross-module assertion rather than a
      reading (`TestApexFramesMatchGenerationFrames`). When you touch either module, check the frames still
      match. Generalize: for any score, ask what the reference was built from, not just whether it exists.
- [ ] **Honor the downstream consumer's contract.** Aspect/transition text is quoted verbatim into edge context
      and synthesis; `insight_label`/`proactiveness_label` must stay in the known scales (else matching falls back
      to defaults); only Ac+/Re+ **headlines** reach synthesis.
- [ ] **Preserve "refer to concepts by actual statement wording, never T/A notation"** in transition/synthesis edits — stored text is re-read later without wheel-relative aliases.
- [ ] **Diversity chains.** `not_like_these` (ExpandPolarity, SurfaceTheses retries) — don't weaken "generate
      something different," or alternatives collapse into near-dupes that dedup silently removes.
- [ ] **A latency fix that removes work removes REASONING — and no prompt surface changes, so this review would
      never see it.** The prompt still requiring the artefact does not make it appear: `_DECISION_READINESS`
      requires pathways at a closing, the seam stopped building them (correctly — it was billing 127.7s and 387.7s
      to the person's wait), and the judged cost of an unwoven closing is **−0.69 vs −0.25 woven**. Two rules.
      (1) When reviewing a chain, ask what the code actually still produces, not what the prompt asks for. (2) When
      *making* such a change, price the removal in judged quality or move the work off the turn — a caps/skips/
      early-returns diff is a quality change hiding in a performance commit. Corollary: **a cap whose stated
      purpose is bounding TURN latency has no authority off the turn** — drain it there
      (`_schedule_pathway_construction`; the cap's own "next turn" follow-up was elected 0/6). **Rule (2) has a
      measured limit, from the A/B that put the work back (`weave-offturn`, 2026-09-14): the MACHINE record moved
      decisively (pathway ground 1/6 → 5/6, full weave coverage) while the judged composite moved only in
      direction (A2 vs A1 −0.06 → +0.19, every interval overlapping). So "price it in judged quality" is a bar a
      12-pair round cannot clear in either direction — which is exactly why the machine-score half must be
      stated: it is the part of such a change that is reviewable at all.** **And ask which KIND of trade it was
      before reaching for the same fix: the weave was a LATENCY trade, so moving it off the turn repaid it in
      full, while the feasibility audit (2026-09-14) was a COST trade — 40% of `explore`'s provider spend — where
      deferral removes the wait and not the spend. There the repair has to be SCOPED instead, and the scope comes
      from asking where the artifact is actually READ (one adopted pathway, 2 calls, not the eager 2 × 6N) — and
      then WHEN, because scoping the write to the read site still buys nothing if the two land on different turns,
      which is exactly what that scoping did (see the WHEN item in Altitude 2).** See
      "The construction came back, off the turn" under Decision lifecycle in reference §4.

### Cross-agent parity (see the §5 matrix)
- [ ] **Grep the other two agents when editing a shared concept.** HS disambiguation, HS bands, nexus grouping
      rule, Ac+/Re+ direction, S+/S- framing must stay consistent across Analyst/Explorer/Advisor.
- [ ] **App/engine boundary.** Engine system prompts must not hardcode persona voice; app preambles must not
      redefine tool selection; advisory personas must carry zero framework terminology; presentation defaults
      belong in the preamble.
- [ ] **`NAVIGATOR_APP_ADVANCED_TOGGLE` override completeness.** New section in `NAVIGATOR_APP`? Re-check the override list, or
      expert users inherit non-expert framing. Same question one layer out for the COUNSEL pairing: a new section in
      `_ADVISORY_REGISTER` ships in both registers, and if it re-affirms a non-expert default (vocabulary, "meaning
      first, numbers on request", "Nexus" stays internal) it must be named in `_ADVANCED_SURVIVES_THE_COUNSEL_TOGGLE`
      — later sections win, so an unaddressed one silently re-locks the expert register a host asked for.
- [ ] **Internal-only strings** (`nexus_intent` is "do not surface to user") must keep that classification when interpolated into another agent's prompt.
- [ ] **Structural/direction conventions match `docs/graph.md` and `GRAPH_SCHEMA`** — update `GRAPH_SCHEMA` in lockstep (per CLAUDE.md).

### Conversational rules the bench found missing (Advisor engine)
- [ ] **A graph-hygiene instruction is not a conversational instruction.** `_REJECTION_HANDLING`'s "silently
      `discard`, don't announce it" is right for the graph and, read as speech guidance, made 37 of 105 judged
      cells drop a frame with no bridge. Any rule about what the machinery does must say what the REPLY does:
      *the graph discards; the reply amends.* Same shape as the `record_decision` pair — prose without a call
      and a call without prose are both failures, so state both halves.
- [ ] **Never accept a machinery-leak claim measured only on tool-electing turns, and never accept a null
      measured on the whole term list.** Leaks show up on turns that elect NO tool, off the standing context
      dump alone (`probe_leak_reply_reuse.py`), so a fix judged against tool-heavy turns is judged against the
      loudest cases only. And four banned terms — `perspective`, `transformation`, `wheel`, `thesis` — are also
      ordinary advisory English: leave them in and they fire on both arms of every comparison, collapsing the
      discordant count and manufacturing a null. Score twice — `score_machinery_leak` for the contract,
      `score_machinery_leak_unambiguous` for discrimination. The reply-path latency work is NOT a suspect here
      (reuse on vs off: 4/20 vs 2/20 leaking, p=0.688).
- [ ] **Never accept a leak RATE without checking the detector against the prompt it claims to measure.** This
      one was inflated for months while its own comment said "verbatim from `_HOW_YOU_SPEAK`": it counted
      `accepted cost` (51 of 181 archived snippets, ordinary English, banned nowhere), `adopted pathway`, and a
      bare `the framework` ("help you build the framework"); it matched substrings, so **"synthesis" counted as
      "thesis"**; and `lowered.find(term)` stopped at the first hit per term per turn. Corrected 2026-09-17:
      **8.4% → 5.2% of 1645 archived replies**, and the old "1 turn in 6" was a 40-reply targeted probe read as
      an archive rate. The shape claim survived and sharpened — the leak is **machinery-as-actor (47%) and bare
      position labels (30%)**, not vocabulary, and `polarity`/`tetrad`/`dialectic` never leak at all. So: a
      fix that adds banned words to the prompt is aimed at the wrong 2%, and `test_the_term_list_is_verbatim_from_the_prompt`
      now fails if the two drift again. Two levers stay unavailable — `_dump_one_perspective`'s `T{idx}+ [[hash]]`
      labels are load-bearing for `record_decision`'s `accepted_cost` ground, and a post-hoc rewrite pass works
      on `chat()` and is impossible on `chat_stream()`, which would split the two entry points on a PRODUCT claim.
- [ ] **The internal model describes positions, never the person.** A+ is "the obligation that falls on the
      T-sayer" (`docs/theory/generative-rules.md` Rule 3.1) — an obligation, not an incapacity. "Structurally
      blind" appears nowhere in `docs/theory/`; it was an application gloss, and it converted straight into
      "here's what you're not seeing" in 54–56 of 120 judged warmth cells. Never re-introduce person-as-blind
      phrasing, and **rewrite the worked examples with the rule** — the regression caught them still teaching the
      old register three paragraphs after the new rule.
- [ ] **A prohibition needs an OBJECT, or it suppresses the affirmative case too.** `audit_feasibility` was
      elected 1/6 then 0/6, and the cause was not model reluctance: the engine prompt named ONE affirmative moment
      (the person asks) against THREE prohibitions written to stop an eager spend — in the tool doc, in Reading the
      Scores, and in prioritization rule 3 — so suppression won, which is the right outcome for a prompt that says
      "don't" three times and "do" once. When a tool must be elected, count the two kinds of sentence about it, and
      write every ban with the thing it bans: "do not audit a MENU" survives an edit that "do not audit" does not.
      Absence also has to be EXPLAINED where the model reads scores, or the model infers a schedule that does not
      exist. And an instruction may only name a tool where the tool is WIRED — a section gated on one tool
      (`_DECISION_READINESS` renders on `record_decision`) that names another must hold that passage out behind a
      placeholder gated on the second name, else a scoped session spends a turn looking for a tool it lacks
      (`TestTheElectiveRouteNamesItsMoments`). The same applies to naming a SECTION: a cross-reference added to a
      section that renders in every mode (`_SCORE_READING`) can dangle, which is what `_decision_note` and the
      `_INTERNAL_MODEL` mid-sentence placeholder exist for — and when you gate a sentence, keep the part that
      carries the RULE outside the gate and put only the pointer inside it.
- [ ] **Gating the TOOLSET does not gate the PROMPT — and at mode scale that is not one dangling sentence but
      most of the render.** `Advisor(read_only=True)` (2026-09-17, the engine's THIRD render shape; the flag is
      DERIVED in `system_prompt()` as `read_only = not (set(names) & _WRITE_TOOL_NAMES)`, never passed, so it
      cannot disagree with the tools the head actually holds) removes all 7 write tools, and only tool DOCS plus
      the two name-gated sections followed it. `_EAGER`, `_CONVERSATION_USE`, `_REJECTION_HANDLING*`,
      `_DEFAULT_ARC`, `_TOOLS_INTRO_SCOPED` and `_SCORE_READING` all still instructed a head to `ingest`,
      `anchor`, `explore` and `discard` with none of them wired. So when you add a mode that withdraws a CLASS of
      tools, enumerate every section and ask what it tells the model to DO, not just which names it mentions —
      the name-gates that already exist cover the sections written after them and nothing else. Two shape rules
      from the fix. (1) **Fork the sections whose whole subject is the withdrawn work** (`_EAGER`,
      `_CONVERSATION_USE`, `_REJECTION_HANDLING`) and drop the ones that are pure procedure for it
      (`_DEFAULT_ARC`). (2) **For a section whose tool references sit mid-paragraph inside reasoning about what
      the scores MEAN, do not fork it** — that is where drift lives; state one mandate and place it LAST among
      the instruction sections, immediately before `_CONTEXT_SLOT`, because later sections win and the cache
      seam requires the dump to stay last. Enforcement stays in CODE at two sites (the toolset, and the closing
      seam's single `_repair_unrecorded_decision` method); the prompt's only job is to stop the head spending
      turns reaching for what it does not have. `tests/test_advisor_read_only.py` pins both halves, including
      that `DEFAULT_TOOL_NAMES` is exactly the read set ∪ `_WRITE_TOOL_NAMES` so a new tool cannot be added
      without being classified.
- [ ] **Ceremonies must have a satisfied-by clause.** An explicit request IS the consent ("write this down" =
      confirmation): a ritual with no way to be already-satisfied reads as a gate holding the person's own
      decision, which is the failure the ritual exists to prevent. Check any new precondition for the case where
      the person has already supplied it.
- [ ] **A ceremony hardened in one direction has an unmeasured other direction — check it before hardening
      again.** `_DECISION_READINESS` has been strengthened four times against WITHHOLDING a record, and the
      opposite pole went unmeasured until a control scenario looked: on `premature_relocation`, whose
      pre-registered right answer is "you do not have enough to decide yet", **12 of 12 A2 cells recorded anyway**
      (26 Decision nodes, `DecisionCoherenceCheck` 25 passed / 1 failed) and A2 **lost** that control's blended
      composite. Left unfixed by product decision (2026-08-20) — the check still stands: before hardening a
      ceremony, look at what the opposite failure costs, because here nobody had. UNFIXED on purpose — decision *timing* appears nowhere in the eight generative rules, so this is
      a design conflict rather than a defect against spec, and a prompt-only fix could not bind anyway (the
      code seam repairs an unrecorded confirmation back in). Do not write the restraining rule as a prompt patch;
      see the `r23-controls` entry under Decision lifecycle in reference §4 for the three constraints on any fix.
- [ ] **Accumulation and concession are register-independent, so verify the SCOPED render too.** Counsel mode
      swaps `_ROLE`/`_HOW_YOU_SPEAK`/`_REJECTION_HANDLING` for scoped variants; a conversational rule that only
      lands unscoped silently exempts the toggle (`TestWhatTheJudgeSaidWasWrong` asserts both).
- [ ] **A plural structure must not surface as a plural question.** Wheels/pathways rank internally; a menu of N
      options hands the work back (26 of 85 judged convergence cells). Lead with one and its price. Measured
      afterwards (`scoring.score_menu`), the defect is the **frequency**, not the costing: A2 offers a choice 3.5×
      more often than the journal arm and prices it 57% of the time against the journal's 0%.
- [ ] **Before writing a prompt rule from a judged frequency, count the behaviour it targets.**
      `tests/e2e/probe_five_fixes.py` is free and it disqualified four of five fixes: one had 12 events in 704
      turns, two are semantic (no regex reaches "did the reply AMEND the frame"), and one runs *against* A2 in the
      archive. Two traps it caught, both general: a **simulator instruction can manufacture the user's complaint**
      (94 of 118 "you're going in circles" turns sit on one beat that tells the simulator to say it — it appears in
      4 of 4 A0 cells too), and a judged frequency can pass the won-vs-lost selectivity check while its wording
      points at a **narrower behaviour than the notes describe**. A rule whose behaviour cannot be counted is still
      worth writing — but say so, because a null result on it will be uninterpretable.
- [ ] **Then size the run before you register a bar** — `tests/e2e/power.py`, free and exact. Counting the
      behaviour tells you the base rate; power tells you whether the n you can afford could see the change.
      Both are prerequisites, and the second is the one this archive skipped (see Verify: the parentage
      probe ran at 0.28).

---

## Verify

- **Structural regressions (default suite, no LLM):** `poetry run pytest tests/test_prompt_review_regressions.py`
  — ~45 assertions over prompt constants (imports, worked-example directions, override wording, grouping phrase, …).
  **This is the primary net; add a case here when your edit touches a shared constant, a gate, a taxonomy, or cross-agent wording.**
- **Behavioral vocabulary (real provider):** `poetry run pytest tests/test_prompt_vocabulary.py --real-llm`
  — thin (one Analyst "blindspot" check); extend it when reviewing user-facing vocabulary.
- **Behavioral discrimination (real provider):** when a rule's whole value is telling two cases APART, a structural
  assertion cannot show it and the mock brain cannot either (it auto-fills the verdict field, so a mocked run shows
  neither firing nor declining to fire). Test it as a PAIR built from the same facts, at the WEAK tier, and assert
  the contrast in one test — an auditor that flags everything passes half the bar and is useless; one that flags
  nothing passes the other half and is the bug. Reference: `tests/test_decision_rationale_integrity_weak_tier.py`
  (four pairs now: refuted vs carried, cost-grounded, silent vs priced-in-prose, and **resized vs
  resized-then-zeroed**, whose two halves differ only in the LAST CLAUSE — the sharpest form of the technique, and
  the one that proves the check splits on the verdict rather than on tone). Watch the fixture, not just the prompt:
  the first run of that test failed on a scope-wide `find_all_active()` duplicate rather than on the rule under
  test. And keep the provenance of each pair visible: three reproduce a record the audit saw and passed; the fourth
  asks a forward question about an arm that has no record at all, which licenses less.
- **A control arm must be able to come out clean.** Check that before spending the run, by asking what
  answer the control gives when nothing is wrong. `probe_tetrad_pole.py` audited the tetrad's `+`
  aspects as a control on its `−` endpoint, using one verdict field whose vocabulary was minus-only
  (`overdevelops_own_pole` / `misparented` / `no_exaggeration`). The control returned **4 defects of 4**
  — because `no_exaggeration` is the *correct* answer for a constructive aspect and the tally counted it
  as a failure. The auditor said so in its own rationale ("as an exaggeration audit it registers none").
  A control pinned at 100% cannot distinguish an over-flagging auditor from a real defect, which is the
  only thing it was there to do. **The fix was to split the one verdict into the question that IS shared
  between the arms and the question that is not** — parentage (asked in identical words of `T+` and `T−`,
  so the rates are comparable) vs. valence (position-specific, reported separately). Generalise: when a
  control and an endpoint are scored by one instrument, only the sub-question phrased identically for
  both is a control; the rest is two different measurements sharing a number.
- **An endpoint defined over a name that is free to be swapped measures the naming, not the behaviour.**
  The T/A labels are assigned per perspective, so "defects concentrate at T−" can be a fact about which
  statement got called T. Make the label a manipulated variable: generate each tension twice with T and A
  swapped and cross-tabulate defect-by-position against defect-by-content (`probe_tetrad_pole.py`
  `_TENSIONS` × `forward`/`swapped`). If the defect follows the POSITION across both orderings the
  asymmetry is real; if it follows the CONTENT it is naming only. Note the archive could not answer this
  at all — `probe_cost_side.py` measured `opened_against = 0` of 88 because every bench scenario pins one
  `favoured_side` for its whole run, so the convention was never once stressed.
- **The seam lane (real provider) — run this after ANY prompt edit with behavioural reach:**
  `poetry run pytest -m seam --real-llm` (needs Memgraph up). Each guard reproduces a defect
  measured end to end in `tests/e2e/results/`, and they exist because **a prompt assertion cannot
  see a broken join.** `test_prompt_review_regressions.py` was fully green while 6 A2 cells printed
  framework vocabulary at the person 15 times — the ban was *in* the prompt and absent from the
  *reply*. Structural net answers "does the prompt say it"; the seam lane answers "did it arrive".
  Roster and provenance: `tests/e2e/README.md` (pinned by `TestTheSeamLaneRosterIsReal`).
- **A prompt fix that was never measured is a guess.** Before writing a rule from a judged
  frequency, count the behaviour (`tests/e2e/probe_five_fixes.py`, free — it disqualified four of
  five). Before claiming a fix worked, read the rationales, not the delta
  (`tests/e2e/judge_notes.py --all-cells`, free). Three prompt fixes aimed at "A2 never calls
  explore" all failed because the flag's cause was elsewhere; `/df-e2e` carries that loop.
- **An endpoint and a pre-registered bar with no power calculation is a coin-flip dressed as a
  hypothesis test.** Size the run with `tests/e2e/power.py` (free, exact, no provider) BEFORE
  registering a bar. The parentage probe was pre-registered, replicated, and honestly reported
  NOT CONFIRMED at n=72/arm — and its **power for the effect its own point estimate implies was
  0.28.** A design that misses a real effect 7 times in 10 produces that verdict whether or not the
  fix works, so neither run carried much evidence, and the run that DID clear the bar was the
  favourable tail by construction. Pre-registration stops you moving the goalposts; it does nothing
  about goalposts too small to hit. Three rules fall out. (1) If the affordable n cannot reach ~0.8,
  say up front that the run is a **screen** and that a null will be uninterpretable — do not report
  the number as a finding later. (2) **Enrich rather than enlarge**: power responds to the base rate
  faster than to n (0.80 needed n=252/arm at 18%→9%, or n=96/arm at 40%→20%), but enrichment must
  select on a property known in ADVANCE, never on which cells failed in the runs you are comparing
  against — that bakes the selection into the baseline arm's rate. (3) **Pairing is not a free win**:
  running both prompts on the same cells doubles power only if the fix acts near-monotonically, and
  falls below unpaired Fisher once generation noise dominates the discordance. The same parentage
  prompt gave 4/72 and 9/72 on identical inputs, so plan against the noise-dominated row.
- **A power number inherits the uncertainty of the base rate you feed it, so measure that rate
  first.** Acting on rule (2) above, `probe_option_pair_tetrads.py` was sized on an assumed 40%
  base rate in the enriched stratum and reported 0.86 power. The observed rate was **3.1% in both
  strata** — below even the 18% the archive already had. Power for the proportional effect at the
  real base rate was **0.01**, so the run could not have sized the follow-up A/B it existed to size.
  `power.py` was not wrong; it was **conditional on a premise that had never been measured.** An
  enrichment hypothesis is itself an untested hypothesis. Repair: spend one replicate × one ordering
  (16 cells) as a **pilot to measure the base rate, then size** — or size on the rate you already
  have. Sizing on the rate you hope for is how a careful-looking design ends up blind.
- **A gate with no magnitude cannot fail, so it cannot invalidate anything.** The same run carried a
  manipulation check registered as able to void its own primary — and registered as a DIRECTION only
  (`mean_a < mean_b`). It passed on a separation of **0.026** and printed "MANIPULATION HELD" while
  the two strata overlapped almost completely (3 of 8 cells in the predicted band, three at the
  opposite extreme). That verdict had to be withdrawn after the fact, which demoted the primary from
  a claim about the property to a claim about one hand-built population. This is the power defect in
  a different costume: **every pre-registered gate needs a threshold it could realistically miss**,
  and an invalidating gate needs one most of all, because it is the only thing standing between a
  null and an overclaim. Check any `if x < y:` acceptance test for an implied magnitude of zero.
- **A band picked off the power table is not a band picked off what matters.** `probe_plus_takeup.py`
  registered "CONFIRMED iff the fixed arm reaches 4.4%" because 4.4% was what 192 slots could see at
  0.85 power. The fix then produced a significant halving (16.1% → 7.8%, p=0.0176) and the registered
  verdict came out **INDETERMINATE** — not for lack of power (0.97 to see the 4.4% ceiling at the
  observed baseline) but because the ceiling encoded the instrument's reach instead of the effect worth
  shipping. Register the CONSEQUENTIAL threshold, then state plainly whether the run can see it; a
  design that can only confirm effects larger than the ones you would act on will keep returning
  INDETERMINATE on real wins.
- **"Same build" checked on the PROMPT is not the same build when an arm's input is GENERATED.** Every
  pooling guard in this bench compares `prompt_sha`, and A1.5's entire context is a pre-built graph dumped
  as static text — a framework ARTIFACT, not a prompt. Between `a15-floor` and `weave-offturn` that dump
  went from **9,841 chars `woven=0 transformations=0`** to **~26,000 chars `woven=5 transformations=42`**
  because `abe386d` moved pathway construction off the turn, with the same `prompt_sha` on both. Pooling
  them would have averaged two different arms and reported one arm at twice the n. So whenever the thing
  under test is fed something the framework BUILDS, that artifact's provenance is part of the build
  identity and belongs in the gate (`read_pooled.py` now refuses on it) — and compare the recorded RECIPE,
  not the byte size, or regeneration noise refuses every pool that could ever exist.
- **An interval over pairs that share a replicate assumes independence, and in this archive that is
  usually false.** 4 judged pairs come from one replicate (2 sessions × 2 branches off one opening), and
  swept over every saved set, **17 of 37 have a POSITIVE intra-replicate ICC, up to +0.697** — so the flat
  interval is anti-conservative nearly half the time, and `report.py`'s `n≈N pairs` is an UNDER-estimate by
  the design effect (on `A1.5 vs A1`: published n≈55, actually ~68). Price it rather than falling back on
  replicate means: at the 3 replicates a round produces, the replicate-mean interval carries t(2)=4.303 and
  resolves nothing whatever the data say, which reports a df problem as a null result. Inflate the standard
  error by sqrt(deff) and take df from the effective n.
- **A pairwise judge carries a LENGTH nuisance variable as well as position and set size, and this bench
  cancels only one of the three.** Position is cancelled by DESIGN (`judge.py::_x_is_a` shows each pair both
  ways); nothing equalises how much an arm SAYS, and the judge is shown both transcripts at once. Measured off
  the archive for free (`read_length_confound.py`): on the 24 poolable `A1.5 vs A1` pairs the per-pair word gap
  explains **53% of the endpoint** (slope +3.27 rubric steps per 1,000 words, t=+5.02), the raw +0.514 falls to
  **+0.095 [−0.21, +0.40]** at gap zero, and the 6 pairs where the OTHER arm was longer read −0.98 against +1.01
  for the 18 where the arm under test was. It is not a property of that pair either: **29 of 36 (stem, arm-pair)
  sets are positive** (sign test p=0.0003; pooled within-set +1.14 [+0.88, +1.40] over 530 pairs), including sets
  whose mean delta is negative, so it is not "the better arm writes more". Three rules. **(1) Quote the mean
  length gap beside any judged delta** — it is free, it comes off transcripts already paid for, and a delta
  reported without it has left its largest known nuisance variable unlooked-at. **(2) An adjustment that cannot
  separate a CONFOUNDER from a MEDIATOR is not an estimate — and here the PLACEBO settled it against the
  adjustment.** Length is either something the judge pays for (adjusting removes bias) or the channel the gain
  arrives through (adjusting deletes the effect), and only a comparison with the manipulation ABSENT can say
  which. `probe_same_arm_placebo.py` built one out of transcripts already paid for: the two `decide` runs of one
  (arm, tier, scenario, replicate) are the same script sampled twice, so the true delta is zero in expectation
  while length varies by generation noise. 32 pre-registered pairs, judged on the same instrument, gave
  **−0.13 per 1,000 words, CI [−0.57, +0.30]** — excluding the +1.14 archive slope, the +3.27 marquee slope AND
  the +0.57 registered as consequential, with mean delta −0.000 confirming exchangeability. **With the arm held,
  words buy nothing, so the RAW delta is the estimate and the adjusted column is an over-correction.** Two
  transferable lessons rather than one. First, **when a nuisance covariate has a slope, look for the population
  where the manipulation is missing before you adjust anything** — an unused branch structure had 174 such pairs
  sitting in this archive, free apart from the judging, and the earlier read had written off the question as
  unanswerable. Second, **a nuisance can reproduce in SHAPE and not in LEVEL, and only the level was the
  problem**: the ordering of which dimensions respond to length does reproduce (r=+0.79 over 12, +0.76 to +0.83
  leave-one-out, `conversational_fit` negative in both — this judge discounts length exactly where its rubric
  says to and pays on substance), but at `placebo = 0.39 × cross-arm − 0.51`, and a near-uniform offset across
  every dimension is what an arm effect travelling with length looks like, not a judge habit. Two design rules if
  you build one: **assign the sides by BRANCH NAME, never by length** (side A = the longer transcript makes every
  gap positive and turns the slope question into an intercept question), and **write the output to a
  SUBDIRECTORY** — every archive reader globs `results/*.json` non-recursively, and a same-arm comparison saved as
  an ordinary stem enters them all as a legitimate arm pair, pooling the placebo into the numbers it exists to
  interpret. **(3) Run it even when the direction is unflattering, which is what makes it trustworthy** — A2 is the
  SHORTER arm in every marquee set, so adjusting moves A2's numbers UP (`r21` +0.372 → +0.521), and a tool whose
  only recorded effect flatters its author is not evidence. **And drop dead cells FIRST when regressing against
  any transcript PROPERTY:** an arm that never ran leaves an empty transcript, at once the shortest possible and
  the worst-scoring possible — one point at the extreme of both axes, which is how you manufacture a slope.
  Applying `invalid_cells` the way `drop_invalid` does took one set from **20 pairs at +1.82 (t=+3.48) to 16 at
  +1.02 (t=+1.00)**, so four dead rows were most of that set's slope.
- **An endpoint correction that flips a published result in the FLATTERING direction is a flag, not a
  fix.** Holding the NI dimensions out of the headline is right — `a15-floor` established it — and doing it
  in code moved the archive's marquee pooled read from **+0.325 [−0.003, +0.653] UNRESOLVED** to **+0.372
  [+0.008, +0.737] WINS**, by eight thousandths, in a correction written by the person who would quote it.
  Print both, name which one was pre-registered, and leave the adoption to someone else; switching to the
  reading that excludes zero after seeing that it does is the move pre-registration exists to forbid. The
  check that makes the correction believable is the opposite one: applied across all 37 sets, the
  design-effect fix changed 2 verdicts and both were recorded LOSSES becoming unresolved.
- **Two runs of one instrument are not two measurements of one rate.** Same 16 tensions, same weak
  tier, same auditor model, baseline prompt verified byte-identical to the pre-fix commit, four hours
  apart: minus misparentage went **3.1% → 9.4% (p=0.0406)** while the plus endpoint reproduced
  (13.3% → 16.1%, p=0.53). So a cross-run rate comparison in this lane can be significant with no
  intervention between the runs. **Every arm you intend to compare must live inside one run**, and a
  probe that borrows a historical rate as its baseline is measuring the archive's variance as much as
  its fix. A live mechanism, not just noise: `StatementClassification` re-runs each time and the branch
  it picks selects the apex row interpolated into the generation prompt — so print the per-pole
  classification in any probe whose rates will be compared to another run's.
- **One run cannot tell a fix from the favourable tail. Replicate before banking.** The
  parentage fix measured 4/72 on the first post-fix run — clearing its pre-registered
  `<= 4/72` bar by exactly zero margin, p=0.036 — and 9/72 on a replication with the same
  prompt, config and auditor. Pooled: p=0.075, and the registered CONFIRMED band missed on
  both prongs. At a base rate near 15% with n=72, the run-to-run spread is about as wide as
  the effect you are hunting. Register the pooling rule BEFORE the second run so pooling is
  not a post-hoc rescue, and report the adjudicated comparison alongside the raw one — those
  two disagreed here (raw 13→4 p=0.036, adjudicated 11→4 p=0.099), and the raw one was the
  registered endpoint only by luck of how it was written.
- **"Same prompt" is not the same prompt when a classifier sits upstream.** `_tetrad_prompt`
  and `_contradiction_pair_prompt` interpolate `lookup_aspect_apex(parent, position)`, and
  the branch comes from `StatementClassification` — a non-deterministic LLM call. Measured on
  its own in `probe_classifier_stability.py` (47 texts × 6 readings, no generation, free of any
  graph): **6/12 branch-unanimous** on the replicated pole set and **only 38% of texts stable on
  (family, domain, branch)**; 5 of 47 cross SYSTEMIC↔ELEMENTAL, swapping the apex vocabulary
  wholesale. **Any pre/post measurement downstream of the classifier is not a matched pair** —
  record the per-text branch AND domain, or pin the classification. Same branch feeds HS, so this
  reaches `_rank_polarities` (0.7), not just probes.
- **A pattern read off the rows that will test it is a description, not a hypothesis — and it can
  die on new text.** The instability above first came with an explanation: the split is by FORM,
  long concrete courses of action stable, short abstract nouns not. It was read off the same 12
  rows that revealed the instability, it was compelling, and it went into this skill and the
  reference map as a claim. A pre-registered three-arm test on 36 statements written for the
  purpose — bare noun / short action / long course of action, domains matched across arms so
  domain could not be the confound — killed it: **6/12 vs 5/12 vs 7/12, gap 1, p = 1.0**, inside
  the pre-registered NO-EFFECT band rather than merely short of significance. Two rules follow.
  (1) **Build the test set from new text whenever the hypothesis was generated by looking** — had
  Set B been the original 12, the numbers would have "confirmed" it and nothing would have been
  learned. (2) **Pre-register the null band, not only the success bar**, or a dead hypothesis is
  indistinguishable from an underpowered run and survives on "needs more data" forever.
  Corollary for the instrument: **gate every derived readout on its primary firing.** The probe's
  third arm printed "LENGTH drives stability" off a 1-count difference at p=1.0, because the
  discriminator block ran unconditionally — a conclusion manufactured from noise by the tool that
  was supposed to prevent exactly that.
- **Never draw a worked counter-example from the population you measure on.** Recitation and
  rule-learning are indistinguishable at the endpoint. The parentage counter-example was
  first drafted on `freedom_security` — 3 of the 13 baseline defects — and rebuilt on
  Courage/Fear, which appears in no probed tension
  (`TestTetradParentage::test_system_prompt_carries_a_counter_example_from_outside_the_probe_set`
  pins the probe's tensions out of the prompt).
- **Do not edit the arm you registered as a control.** The same fix added the parentage clause
  to `t_plus`/`a_plus` as well as the minuses, which destroyed the plus arm as a control while
  leaving it useful only as an auditor-stability check (6/72 both runs). Decide which arms are
  under treatment before editing, not after reading the result.
- **Known coverage gaps** (see reference §6): no cross-agent consistency test, agent-prompt hand-typed scales
  untested for agreement, taxonomy dict-vs-table lockstep untested, no app/engine boundary test, personas
  untested. If your edit lands in one of these, add the missing regression rather than relying on manual review.

---

## How to use

- **Manual:** `/df-review-reasoning-layer [what you're working on]`
  - `…rewriting the antithesis extraction prompt to reduce hallucinated format`
  - `…review the analyst system prompt for competing signals with the app preamble`
- **Proactive:** when editing any prompt under the `paths:` above, apply Altitude 1 automatically, escalate to
  2/3 by blast radius. Read the actual file(s) first — including co-occurring layers — then report:
  1. Issues found, with root cause (Altitude 1 table) and, for 2/3, the specific co-occurring/theory/chain interaction.
  2. Fix recommendation — and say explicitly when the right fix is **structural** (derive from a constant / add a test) rather than a text edit.
  3. Whether a regression test exists or needs to be added, and where.
