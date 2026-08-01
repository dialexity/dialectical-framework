# Pipeline — Where Theory Is Enforced vs Described

Maps the paper's *procedural* content (workflow steps, prompts, module architecture) onto the live
pipelines, and records where each generative rule is actually enforced. Complements
`.claude/skills/df-review-reasoning-layer/reference/systemic-map.md` §4 (call-chain seams/gates).

## Paper procedure → live pipeline

Paper workflow (Fig 2 steps): 1 Thesis → 2 Antithesis → 3 Tetrads (3.1-3.4 checks) → 4 S± →
5 Transitions (5.1-5.2) → 6-7 Multi-thesis wheels → 8 Transitions' Matrix. Innovation workflow:
Problem → Major Polarity → 2-4 Tetrads → Tr-Matrices → Ontologies → Practical Ideas. [P0 pp.5-6,18,28]

| Paper step | Live pipeline | Status |
|-----------|---------------|--------|
| 1-2 Thesis/Antithesis | `SurfaceTheses` → `FindPolarities` (AnalysisPipeline) | implemented |
| 3 Tetrads + checks | `ExpandPolarity`/`AspectGeneration`; checks 3.2/3.4 absent, 3.3 edit-only | partial |
| 4 Synthesis | `GenerateSynthesis` — but AFTER transformations, not before | diverges (order) |
| 5 Transitions | `ExploreTransformations` (Ac±/Re± per edge pair) | implemented |
| 6-7 Wheels | `BuildWheels`/`PerspectiveCombination`/`generate_compatible_sequences` | implemented |
| 8 Transitions' Matrix | — | absent |
| Ontology compression | — | absent |

**Step-order divergence:** the paper derives S± at step 4 then transitions at 5/8; the pipeline
derives S± FROM transformations (synthesis consumes Ac+/Re+ headlines). The paper itself notes
[P0 p.16] transitions don't require prior S± classification (step 3 → step 5 shortcut), so the
pipeline's order is theory-compatible; recorded because prompts should not imply the paper's
ordering.

## Rule enforcement map (which rules gate, which merely inform prompts)

| Rule | Enforced at generation | Checked post-hoc | Merely described |
|------|----------------------|------------------|------------------|
| 3.1 tetrad/diagonal | prompt constraints (`aspect_generation`) | `edit_perspective` only (`DiagonalOppositionsCheck`) | — |
| 3.2 modality balance | — (deliberate: paper's own tests found Ks-balance criteria "not useful") | measurable as `rectangularity` = 0 (see generative-rules.md R3.2), nothing gates on it | — |
| 3.3 control statements | backfire constraint (`transformation_generation`) | `edit_perspective` (blocking) + `expand_polarities._validate_and_flag` via `PerspectiveValidation` (non-blocking flag) | — |
| 3.4 ontology profiling | — | — | absent everywhere |
| 4.x synthesis rules | input selection (`synthesis_generation`) | — | prompt framing |
| 5.x circular causality | prompt constraints (`transformation_generation`) | audits annotate, don't gate | — |
| 6-7 wheel geometry | `generate_compatible_sequences` (hard structural) | — | — |
| 8 transitions matrix | wheel-native: arrangement enumeration + `ExploreTransformations` per edge (eager/lazy = app policy) | audits annotate, don't gate | principles/ontologies compression layer only |

**The only live hard gates:** HS ≥ 0.7 (`_rank_polarities`) + consolidation bands 0.7/0.1
(`antithetical_thesis_detection`) + wheel geometry (structural, can't be violated). Everything else
is prompt-constrained generation with annotation-only auditing — including the generation-path
`PerspectiveValidation` run, which flags `Perspective.validation` without blocking. This is a
deliberate architecture (generation prompts enforce; validation is post-hoc and non-blocking) —
see CLAUDE.md "Validation, in practice".

## Paper's module architecture vs agent architecture

**Theory:** Five reasoning modules [P0 p.27; P1 pp.47-48]: Hypothesis Explorer (T/A taxonomies +
validated tetrads + S± cases + calibrated scoring), Ontology Builder (tetrad ensembles →
Tr-matrices → principles), Principle Discovery (invariants across ontologies → analogies),
Collective Memory (reusable S± case/pattern libraries), Decision Navigator (ontologies+matrices →
context-specific interventions, using insight/proactiveness + Greimas). Maturity axis:
Understanding → Intervention → Discernment → Transformation. [P0 p.28]
**Implementation:** Analyst (≈ Hypothesis Explorer's front half), Explorer (≈ parts of Decision
Navigator), Advisor (composition). No Ontology Builder / Principle Discovery / Collective Memory
counterparts — they depend on the absent transitions-matrix + principles layer.
**Status:** partial (rough correspondence, different decomposition)
**Notes:** Roadmap-level in the paper. Do not rename agents to match; record correspondence for
orientation.

## Portable prompt language (verbatim from the papers, usable when relevant)

- Feasibility (conditional): "estimate practical feasibility of step x in the presence of steps
  y1, y2, …" [P1 p.39]
- Transitions matrix generation + row/column child-clear compression [P1 p.42]
- PC: "Estimate the extent [0,1] to which the commonly perceived meaning of T fosters A+." [P1 p.49]
- 4-thesis wheel seed: "suggest 4 major steps T1–T4 describing a given system in terms of circular
  causation, such that T1 opposes T3 and T2 opposes T4" [P0 p.19]
- Blind-spot trigger: "How can T+ be achieved while fostering A+ and/or avoiding T− and A−?" [P0 p.25]
- Circular causality: "suggest how to transform T− into A+ and A− into T+" [P0 p.16]
- Balanced transitions: "Suggest intermediate steps Ac that transform T into A, and Re that
  transform A into T, such that Ac+ opposes Re− and Ac− opposes Re+" [P0 p.17]

## Known source inconsistencies (do not "fix" code against these)

- DISC worked example [P1 pp.26-27]: prose pairs T3 with "A4 = Flexibility" while its own scheme E
  labels A3=Flexibility, A4=Dynamism — a typo in the source.
- Some domain tables label the S− row "Pathology" or the S± row "Quality/Quantity" [P1 pp.32,34] —
  terminology variants, not model changes.
