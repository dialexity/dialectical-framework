---
name: df:review-prompts
description: Review and guide prompt writing/editing in the dialectical-framework. Use proactively when writing or modifying LLM prompts in agents/, concerns/, or orchestrator/tools/.
---

You are reviewing or writing LLM prompts within the dialectical-framework project.

Context from user: $ARGUMENTS

## Where Prompts Live

| Location | What it controls | Pattern |
|----------|-----------------|---------|
| `agents/apps.py` | User-facing vocabulary/framing (DEFAULT_APP, ADVANCED_APP) | Raw string, injected as `app_preamble` |
| `agents/analyst/system_prompts.py` | Analyst tool selection and workflow | SYSTEM_PROMPT constant |
| `agents/explorer/system_prompts.py` | Explorer tool selection and workflow | Function returning prompt string |
| `concerns/*.py` | Structured LLM calls within skills (Mirascope) | `_*_prompt()` methods returning user content; `ConversationFacilitator.set_system_prompt()` |
| `agents/orchestrator/tools/query_graph.py` | Cypher generation prompt | Inline in tool function |

All paths relative to `src/dialectical_framework/`.

## Prompt Writing Principles

1. **Positive specification over negative constraint.** Say what the model SHOULD do, not what it should avoid. "Format as X" beats "Don't format as Y".
2. **One concept, one word.** Never use the same word for two different concepts within a prompt. If "statement" means both "a thesis node" and "a user's utterance," rename one.
3. **Concise and dense.** Every sentence must carry information. Remove filler, hedging, and redundant emphasis. Shorter prompts perform better.
4. **No conflicting instructions.** Never combine contradictory directives ("detailed summary", "comprehensive but simple"). Consolidate into a single authoritative section.
5. **Concrete examples over abstract rules.** When the model might misinterpret a format or style requirement, one concrete example resolves ambiguity faster than three paragraphs of explanation.
6. **Explicit output format.** State the desired structure (JSON schema via Pydantic, table format, bulleted list) rather than hoping the model infers it.
7. **Context/Instructions/Format separation.** Keep these three concerns distinct within a prompt. Don't mix "who you are" with "what to output."

## Anti-Patterns to Reject

- **Patch-stacking:** Adding "IMPORTANT: NEVER..." or "CRITICAL: ALWAYS..." on top of existing instructions. If the model fails, diagnose WHY — do not add emphasis.
- **Redundant emphasis:** Repeating the same instruction in multiple forms hoping one sticks. Consolidate into one clear statement.
- **Model-specific forks:** Different prompt text for different models. Fix for Haiku (the weakest model) — Sonnet/Opus will follow.
- **Negative-only constraints:** "Don't use jargon" without specifying what vocabulary TO use.
- **Unbounded generation:** Asking the model to produce output without length/format constraints.

## Revision Methodology (for fixing prompt bugs)

When a prompt produces incorrect output:

### Step 1: Diagnose Root Cause

| Failure pattern | Root cause | Signal |
|----------------|-----------|--------|
| Model uses wrong term or format | **Polysemy** | Same word used for two concepts in the prompt |
| Model oscillates between two behaviors | **Competing signals** | Two sections give contradictory guidance |
| Model invents wrong format/structure | **Missing example** | No concrete example of correct output |
| Model does the opposite of intent | **Negative-only constraint** | Prompt says "don't X" without "do Y instead" |

### Step 2: Apply Fix (first applicable wins)

1. **Add one concrete example** of correct output
2. **Positive specification** — replace "don't X" with "do Y instead"
3. **Reduce polysemy** — use distinct words for distinct concepts
4. **Consolidate competing sections** into single authority

### Step 3: Verify

Run regression test: `poetry run pytest tests/test_prompt_vocabulary.py --real-llm`

## Review Checklist

When reviewing an existing or newly written prompt, check:

- [ ] No polysemous terms (same word for different concepts)?
- [ ] No competing/contradictory sections?
- [ ] Concrete example included where format ambiguity exists?
- [ ] All constraints stated positively (what TO do)?
- [ ] Output format explicitly defined?
- [ ] No patch-stacking ("IMPORTANT:", "CRITICAL:", "NEVER...")?
- [ ] No redundant emphasis (same instruction repeated)?
- [ ] Length-appropriate? (shorter is better if no information is lost)
- [ ] Context/Instructions/Format clearly separated?
- [ ] For concerns: Pydantic response_model Field descriptions are clear and non-contradictory?
- [ ] For system prompts: Tool selection criteria are mutually exclusive (no ambiguous overlap)?
- [ ] Vocabulary consistent with `apps.py` framing layer (system prompts handle workflow, not presentation)?

## How to Use This Skill

**Manual invocation:** `/df:review-prompts [description of what you're working on]`
- Example: `/df:review-prompts I'm rewriting the antithesis extraction prompt to reduce hallucinated format`
- Example: `/df:review-prompts review the analyst system prompt for competing signals`

**Proactive use:** When you are writing or editing any prompt in the locations listed above, apply these principles automatically. Read the target prompt, run through the checklist, and flag or fix issues.

When reviewing, read the actual prompt file first, then evaluate against the checklist above. Report findings as:
1. Issues found (with root cause from the diagnosis table)
2. Specific fix recommendations (from the fix hierarchy)
3. Whether a regression test exists or needs to be added
