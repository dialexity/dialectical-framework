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

Fix, first applicable wins: (1) add one concrete example; (2) positive specification; (3) reduce polysemy; (4) consolidate competing sections.

---

## Altitude 2 — The assembled context

What ELSE lands in the model's context window on this call? Load
[reference/systemic-map.md](reference/systemic-map.md) §1 for the two assembly stacks and the
co-occurrence hotspots. Then:

- [ ] **Identify the assembly stack.** Agent prompt (Stack A: `app_preamble` + `SYSTEM_PROMPT` fused into
      one system message)? Or concern (Stack B: `SYSTEM_PROMPT` + `_*_prompt()` + DTO `Field` descriptions)?
- [ ] **Read the co-occurring layers, not just the file you're editing.**
    - Agent prompt → open the app preambles it fuses with. For Analyst that means **both `NAVIGATOR_APP` and
      `NAVIGATOR_APP_ADVANCED_TOGGLE`** (`NAVIGATOR_APP_ADVANCED_TOGGLE = NAVIGATOR_APP + override`); for Advisor, all five personas. Check the edit
      doesn't contradict the preamble's vocabulary / score-presentation rules (esp. the "communicate as MEANING
      not numbers" default vs. `NAVIGATOR_APP_ADVANCED_TOGGLE`'s "show numeric scores").
    - Concern → check the SYSTEM_PROMPT, the `_*_prompt()` user content, AND the DTO field descriptions
      (Mirascope sends them). Inline examples must not contradict interpolated constants or field text.
- [ ] **DTO `Field(description=...)` is prompt surface** — review it too.
- [ ] **Runtime splices.** Explorer embeds `nexus_hash`/`nexus_intent`; Advisor embeds the whole
      `{dialectical_context}` dump. Your edit must tolerate an empty/"fresh conversation" block and untrusted
      interpolated text.
- [ ] **Assert on the interpolated module attribute, not `inspect.getsource`** — f-string prompts show the
      literal `{CONST}` token in source, not the resolved text.

---

## Altitude 3 — The systemic review (theory + chain + cross-agent)

The edit touches shared theory, a score, a taxonomy, or vocabulary that crosses an agent handoff. Load
[reference/systemic-map.md](reference/systemic-map.md) fully — it carries the theory-ownership table, the
drift-hotspot catalog, the pipeline seams, the gates, and the cross-agent parity matrix, each with grep-able
anchors.

### Theory fidelity (the 8 generative rules)
- [ ] **Single-source-of-truth for scales.** Any prompt stating HS / complementarity / area / Ks / insight /
      proactiveness / mode / arousal bands must **interpolate the constant** (`HS_SCALE`, `COMPLEMENTARITY_SCALE`,
      `ASPECT_DEFINITIONS` from `scoring_scales.py`; `INSIGHT_SCALE`, `PROACTIVENESS_SCALE`, `POLAR_PAIRS` from
      `ac_re_taxonomy.py`) — never hand-type bands. If semantics change, edit the constant. See §3 for the
      current hand-typed offenders; prefer the structural fix (derive prose from the constant).
- [ ] **Taxonomy dict/table lockstep (R8, top hotspot).** Editing `SYSTEMIC_TAXONOMY`/`ELEMENTAL_TAXONOMY` OR
      the hand-typed taxonomy table in `statement_classification.py`'s SYSTEM_PROMPT requires updating BOTH — the
      LLM classifies against the table while `lookup_aspect_apex` scores HS against the dict. Divergence = silent HS corruption.
- [ ] **Circular-causality directionality (R2).** Keep `Ac+ = T-→A+`, `Re+ = A-→T+`, and "Ac+ without Re+
      regresses to Re-, Re+ without Ac+ drifts to Ac-". Restated across 4+ prompts with no owner — verify all agree.
- [ ] **Diagonal contradiction (R1).** "T+ contradicts A-, A+ contradicts T-, and this is NOT a K defect."
      An edit must not imply lowering K (contradicts `COMPLEMENTARITY_SCALE`) and must match `get_contradiction_pair`.
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
      Regression-test classification stability.
- [ ] **A prompt that sets a score is a gate input.** `AntithesisExtraction` / `AntithesisClassification` /
      `TransformationGeneration._score_hs` feed `_rank_polarities` (0.7) and consolidation bands (0.7/0.1). A
      wording change that shifts the distribution changes what passes — review the gate, not just the call.
- [ ] **Honor the downstream consumer's contract.** Aspect/transition text is quoted verbatim into edge context
      and synthesis; `insight_label`/`proactiveness_label` must stay in the known scales (else matching falls back
      to defaults); only Ac+/Re+ **headlines** reach synthesis.
- [ ] **Preserve "refer to concepts by actual statement wording, never T/A notation"** in transition/synthesis edits — stored text is re-read later without wheel-relative aliases.
- [ ] **Diversity chains.** `not_like_these` (ExpandPolarity, SurfaceTheses retries) — don't weaken "generate
      something different," or alternatives collapse into near-dupes that dedup silently removes.

### Cross-agent parity (see the §5 matrix)
- [ ] **Grep the other two agents when editing a shared concept.** HS disambiguation, HS bands, nexus grouping
      rule, Ac+/Re+ direction, S+/S- framing must stay consistent across Analyst/Explorer/Advisor.
- [ ] **App/engine boundary.** Engine system prompts must not hardcode persona voice; app preambles must not
      redefine tool selection; advisory personas must carry zero framework terminology; presentation defaults
      belong in the preamble.
- [ ] **`NAVIGATOR_APP_ADVANCED_TOGGLE` override completeness.** New section in `NAVIGATOR_APP`? Re-check the override list, or
      expert users inherit non-expert framing.
- [ ] **Internal-only strings** (`nexus_intent` is "do not surface to user") must keep that classification when interpolated into another agent's prompt.
- [ ] **Structural/direction conventions match `docs/graph.md` and `GRAPH_SCHEMA`** — update `GRAPH_SCHEMA` in lockstep (per CLAUDE.md).

### Conversational rules the bench found missing (Advisor engine)
- [ ] **A graph-hygiene instruction is not a conversational instruction.** `_REJECTION_HANDLING`'s "silently
      `discard`, don't announce it" is right for the graph and, read as speech guidance, made 37 of 105 judged
      cells drop a frame with no bridge. Any rule about what the machinery does must say what the REPLY does:
      *the graph discards; the reply amends.* Same shape as the `record_decision` pair — prose without a call
      and a call without prose are both failures, so state both halves.
- [ ] **The internal model describes positions, never the person.** A+ is "the obligation that falls on the
      T-sayer" (`docs/theory/generative-rules.md` Rule 3.1) — an obligation, not an incapacity. "Structurally
      blind" appears nowhere in `docs/theory/`; it was an application gloss, and it converted straight into
      "here's what you're not seeing" in 54–56 of 120 judged warmth cells. Never re-introduce person-as-blind
      phrasing, and **rewrite the worked examples with the rule** — the regression caught them still teaching the
      old register three paragraphs after the new rule.
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
  (a risk recorded as refuted vs. the same risk recorded as carried). Watch the fixture, not just the prompt: the
  first run of that test failed on a scope-wide `find_all_active()` duplicate rather than on the rule under test.
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
