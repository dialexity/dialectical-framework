---
name: df-sync-theory
description: Sync the theory→implementation wiki (docs/theory/) with the Structured Dialectics theory PDFs and the codebase. Ingests/validates theory changes, updates the wiki's claim→code mapping and statuses, promotes essentials to CLAUDE.md, and reports theory↔implementation gaps. Use after theory PDFs change, after implementing/changing theory-encoding code, or to audit drift.
disable-model-invocation: true
---

Usage: `/df-sync-theory [optional: scope hint, e.g. "taxonomies only" or "verify"]`

Maintains `docs/theory/` — the committed wiki that maps Structured Dialectics theory to its
implementation — so agentic coding steers by distilled technicalities instead of re-reading theory PDFs.

## The pipeline this skill owns

```
docs/r-n-d/*.pdf                 theory source of truth (gitignored, may be ABSENT)
    ▼  ingest / validate
docs/theory/               committed wiki: claim → PDF anchor → file:symbol → status
    ▼  promote essentials
CLAUDE.md "Theoretical Foundation" + "Scoring & Metrics"   (committed, always loaded)
    ▼  steers
agentic coding  +  /df-review-reasoning-layer
```

## Modes — pick by what's available and what changed

**Determine mode first:**
1. Check PDFs: `ls docs/r-n-d/*.pdf`. Absent → **verify-only mode**.
2. PDFs present → compare `shasum -a 256` of each PDF against the fingerprints recorded in
   `docs/theory/index.md`. Unchanged → **verify-only mode** (skip ingestion). Changed or
   never fingerprinted → **full sync mode**.
3. `$ARGUMENTS` may narrow scope (a single wiki page, "verify", a specific rule).

### Verify-only mode (works on any machine, no PDFs needed)

Audit the wiki against the code — never against the PDFs:
1. For every wiki entry, check its implementation anchors still exist (grep the `file:symbol`
   references; symbols are authoritative, line numbers are hints).
2. Check statuses are still truthful: an `absent` entry whose concept now appears in code should
   flip to `implemented`/`partial`; an `implemented` entry whose site was deleted/renamed must be
   re-anchored or downgraded.
3. Check CLAUDE.md's theory sections still agree with the wiki (rules, formulas, thresholds).
4. Report drift found and fix the wiki entries. Do NOT touch code.

### Full sync mode (PDFs present and changed)

1. **Ingest** — read the changed PDF(s) with the Read tool (`pages` param, ≤20 pages/request);
   fan out subagents over page ranges for whole-paper reads (`/local-understand-theory` is the
   ad-hoc single-question reader). Extract implementable claims: rules, formulas, constraints,
   scales, taxonomies, thresholds, structural invariants — each with a page anchor.
2. **Validate against the current wiki** — diff extracted claims vs existing entries: new claims,
   changed formulas/thresholds, removed/renamed concepts. This is the theory-intake gate: list
   what changed BEFORE editing anything.
3. **Map to implementation** — for each new/changed claim, locate its encoding site(s) in
   `src/dialectical_framework/` (constants, prompts, concerns, validation checks, graph model)
   and assign a status.
4. **Update the wiki** — apply the entry format below; update `index.md` fingerprints and the
   status ledger.
5. **Promote essentials to CLAUDE.md** — the "Theoretical Foundation (Generative Rules)" and
   "Scoring & Metrics" sections are the promoted distillation. Update them when a rule, formula,
   or threshold changed. CLAUDE.md must stay SELF-SUFFICIENT — never "see docs/theory/ for
   details"; the wiki elaborates, CLAUDE.md summarizes completely.
6. **Gap report** — end with a report: entries added/changed, statuses flipped, and the current
   list of `absent`/`partial`/`diverges` entries, each marked tracked (#NN) or untracked. Code
   changes are human-initiated follow-ups — this skill NEVER edits `src/`.

## Wiki entry format

Every theory claim gets one entry:

```markdown
### <Claim name>
**Theory:** <precise statement, formulas exact> — [paper 0/1, p.N]
**Implementation:** `path/file.py:symbol` (+ prompts/tests that encode it), or "—"
**Status:** implemented | partial | absent | diverges
**Tracked:** #NN[, #NN]          ← optional; only on gaps with a GitHub issue
**Notes:** <divergence details, simplifications, TODOs, gate/threshold values>
```

- Anchor on **symbols and grep-able phrases**, not line numbers.
- `diverges` means implementation deliberately or accidentally contradicts theory — say which, and
  what the theory demands.
- `partial` names exactly what's missing.
- **Tracked is orthogonal to Status:** Status = theory-fidelity fact; Tracked = a GitHub issue owns
  the work. Never encode tracking into the status value.

### Issue lifecycle (both modes)

- **Verify-only mode additionally reconciles Tracked lines:** for each `Tracked: #NN`, check the
  issue state via `gh issue view NN --json state,title`. Closed issue + status still a gap → either
  the implementation landed (flip status, verify anchors, drop/annotate Tracked) or the issue was
  abandoned (keep gap, remove the stale Tracked line, note it). Open issue whose gap has meanwhile
  been implemented → flag the issue for closing in the gap report.
- **Full sync mode:** when a NEW gap is discovered, do NOT auto-create issues. List new gaps in the
  gap report as "untracked"; issue creation is a human decision (`gh issue create` — check existing
  issues for overlap first, e.g. theory metrics often half-exist as old enhancement issues).
- Issue bodies should link back to the wiki entry (page + claim heading) and the PDF anchor, so the
  implementer reads the mapping, not just the issue.

## Wiki layout

```
docs/theory/
  index.md                       purpose, PDF fingerprints, status ledger (counts per status),
                                 reading order, last-sync date
  generative-rules.md            the formal rules (tetrad, circular causality, modality balance,
                                 complementarity, equal-sign synthesis, control statements,
                                 apex coherence, ...)
  taxonomies.md                  systemic/elemental/universal taxonomies, apex structure, Table S-1
  scoring.md                     HS, K/Ks, Mode, Arousal, insight/proactiveness, area/rectangularity,
                                 thresholds and gates
  transformations-synthesis.md   Ac/Re mechanics, wheels/cycles/spirals, S+/S- emergence
  pipeline.md                    how theory maps onto the reasoning pipelines (analysis/exploration),
                                 where each rule is enforced vs merely described
```

Add pages sparingly; prefer extending an existing page over creating a sibling.

## Cross-links (keep in lockstep)

- **`/df-review-reasoning-layer`** — its reference map (`.claude/skills/df-review-reasoning-layer/reference/systemic-map.md`)
  tracks WHERE theory is encoded in prompts and what drifts. When this skill flips a rule's status
  (e.g. a prompt-absent rule gets wired), update that map's theory-ownership table too.
- **`docs/scoring.md` / `docs/graph.md`** — existing deep docs; the wiki links to them rather than
  duplicating. If a sync reveals they contradict theory, flag it in the gap report.
- **CLAUDE.md living-skill contract** — theory enrichment triggers both this skill AND the
  review-reasoning-layer update duty (see CLAUDE.md "Prompt Engineering").

## Ground rules

- Never edit `src/` — gap reports only.
- Never weaken CLAUDE.md self-sufficiency.
- The wiki records what IS, including unflattering statuses (`absent`, `diverges`) — it is a
  steering instrument, not marketing.
- PDFs are gitignored IP: quote sparingly (claims, formulas, tables), don't reproduce prose at length.
