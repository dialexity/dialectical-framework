# Theory Wiki — Theory → Implementation Map

Maps every implementable claim of **Structured Dialectics** (the theory this framework implements)
to its encoding site in `src/dialectical_framework/`, with an honest status. Maintained by
`/df-sync-theory`. Consult this instead of the theory PDFs; the PDFs (gitignored,
`docs/r-n-d/`) are the source of truth only when this wiki is silent or suspected stale.

**Entry format:** claim → theory anchor (paper, page) → implementation anchor (`file:symbol`) →
status → notes. Statuses: `implemented` | `partial` | `absent` | `diverges`.
Symbols are authoritative; page/line numbers are hints.

**Tracking:** a gap (`partial`/`absent`/`diverges`) may carry a `**Tracked:** #NN[, #NN]` line
linking the GitHub issue(s) that own its implementation. Status states theory-fidelity fact;
Tracked states work-item existence — orthogonal axes. A gap without `Tracked:` is known but has no
committed work item (deliberate backlog). When an issue closes, the implementer flips the status
and drops/annotates the `Tracked:` line in the same change.

## Source fingerprints (SHA-256)

Last full sync: **2026-07-25** (initial ingestion).

| Paper | File | SHA-256 |
|-------|------|---------|
| 0 | `docs/r-n-d/0. Structured-Dialectics-A-Generative-Framework.pdf` (34 pp) | `672b24bc04414d3d2a11e1946cb641dd4a99758aad36f184fee1e4d6859efd4c` |
| 1 | `docs/r-n-d/1. Supplementary-Material-for-Structured-Dialectics.pdf` (50 pp) | `233b7f959d37453509dbad8d58f4f9ee3b03d3abca1243840d83157908a2656e` |

Citations below use `[P0 p.N]` / `[P1 p.N]`.

## Pages

| Page | Covers |
|------|--------|
| [generative-rules.md](generative-rules.md) | The formal constraint network: tetrad, modality, control statements, synthesis rules, circular causality, multi-thesis geometry, transitions matrix |
| [taxonomies.md](taxonomies.md) | Systemic (Table S1.11-1), Elemental, thesis-lessness/Mode ladder, Mode×Arousal plane |
| [scoring.md](scoring.md) | K/Ks, SP(=area), rectangularity, HS/MHS, CC, DV, MMI, PSI, PC, feasibility, thresholds & gates |
| [transformations-synthesis.md](transformations-synthesis.md) | Ac/Re mechanics, insight×proactiveness, Greimas criteria, transitions matrix, principles/ontologies, S± subtypes |
| [pipeline.md](pipeline.md) | Where each rule is enforced vs merely described in the live pipelines; procedural theory (steps, workflows) vs agent architecture |

## Status ledger (last updated 2026-07-31; initial sync 2026-07-25)

| Status | Count | Highlights |
|--------|-------|-----------|
| implemented | 20 | tetrad rules, circular causality, control statements (aspect checks both paths + neutral-T variant + backfire constraint), Mode ladder (=thesis-lessness), insight/proactiveness scales, systemic+elemental taxonomies, diagonal wheel geometry, Ks formula, SP formula (as `area`), Greimas criteria (5/5), equal-sign synthesis (explicit constraint), transitions matrix (as wheel-native decomposition; same-side cells deliberately unmediated), multi-antithesis per thesis (N candidates → N Polarities sharing the same T node), forcefulness→polarity-flip (subtlety constraint at both Ac/Re generation sites) |
| partial | 4 | transition tetrad rules, Mode×Arousal semantics, feasibility scoring, apex coherence (data now available; also owns the "S+ without lower-layer support" control-statement extrapolation) |
| absent | 9 | principles/ontologies layer, DV/MMI/PSI/PC metrics, Sa/Sb/Sc subtypes, sub-aspects hierarchy, coupling dendrograms, modality balance enforcement, reverse-order S− trigger, Abstraction scalar, Self-Reg metric |
| diverges | 3 | rectangularity formula (code² vs paper-linear-and-rejected), acceptance gate (HS≥0.7 vs paper SP/DV>0.5), naming: paper "SP" = code `area` |

## Standing cautions

- The paper itself contains at least one internal inconsistency (DISC example [P1 pp.26-27]
  mislabels A3/A4 vs its own scheme). Do not "fix" code against a source typo — check both.
- Several paper metrics are explicitly reported as *unsuccessful or uncalibratable* by the authors
  (linear rectangularity rejected; taxonomy (K_T;K_A;HS) triples "did not identify any useful
  dependences"; no universal SP cutoff; CC less reliable than DV). Implementing a theory metric
  is not automatically an improvement — check the paper's own verdict first.
- All numeric scores are **LLM-dependent** [P0 p.21; P1 p.24]: thresholds must be calibrated per
  model (e.g. GPT feasibility ≥0.5 ≈ Gemini ≥0.2). Any hardcoded threshold in code implicitly
  assumes one provider's calibration.
