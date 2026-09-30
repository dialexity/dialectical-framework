# Antithesis selection: HS ranked the strawman end of the ladder

Lab notes for the 2026-09-30 change to `concerns/antithesis_extraction.py` and
`AnalysisPipeline._rank_polarities`. Rule in CLAUDE.md ("HS gates;
`tetrad_potential` ORDERS"); theory entry in `docs/theory/taxonomies.md` (Mode ×
Arousal plane, "Optimum A").

## How it was found

The blindspot app's probe (`tests/probe_blindspot_paths.py`, `views.md`) ran 20
free utterances through the headless thesis-only `anchor` path. Every expanded
antithesis was a caricature: "Never quit, stay employed forever", "I hate my new
manager", "Strip every feature; ship nothing", "Abandon parents to fend alone".
HS(A) was 0.95 on every row; 17 of 19 tetrads carried `failed: Conceptual
coherence`. The notebook's Case (one utterance, three perspectives) showed the
selection directly, off the antitheses' own Rationales:

| antithesis | branch | HS |
|---|---|---|
| Never quit, stay employed forever | Negation (1.0) | 0.95 |
| Quitting your job is reckless self-sabotage | Inversion (0.9) | 0.85 |
| Starting a company is just gambling | Devaluation (0.8) | 0.75 |

## The mechanism

1. `AntithesisExtraction` generates one candidate per rung of the
   "thesis-lessness" ladder, each asked to be "{branch} of the thesis".
2. Each rates HS against the apex — defined in the shared prompt as
   "[T]-lessness (complete absence/negation)".
3. `_truncate_candidates` keeps the top `count` **by HS**; `_rank_polarities`
   gates at HS ≥ 0.7 and expands the top `MAX_POLARITIES_TO_EXPAND` **by HS**.

Similarity to complete absence of T is maximised by the most total negation, so
the selector structurally prefers the top of the ladder. The theory's own
canonical pair is Love / Indifference — a Privation-rung (0.0) antithesis, an
independent value. Under this selector "Hate" wins. With A already an extreme,
A- has nowhere to go, A+ becomes "the moderate version of the caricature", and
CC fails — which is the 17/19.

Not new: the selector predates the finding by months. Not universal: the
Advisor's `anchor` with BOTH T and A supplied never runs it (the ladder only
classifies a given A). Affected: every build from a bare thesis — `ingest`
(headless builder, `migrate_consultation`), `AnchorTheses`, the Analyst's
`find_polarities`, `note`/`anchor` without an antithesis. The bench's sealed
Advisor result (+0.50 over a builder-made graph) was measured over graphs with
exactly these antitheses: counsel quality survived it, tetrad quality did not.

The theory ledger had it as a known gap: "selection goes by HS, not by [the
paper's] Optimum A" (`taxonomies.md`, status partial), and the paper's
instruction is "ask what functionally opposes the role played by T, not what
negates T".

## The fix

- `ModePointResultDto.tetrad_potential` (0–1): can this opposition be developed
  so it strengthens what T is for (an A+ exists) and does it have its own
  one-sided failure (an A-); low for T's absence or degradation dressed as a
  stance, or a caricature nobody holds. Rated by the same call — a proxy for the
  tetrad's later CC/DV, not a measurement of them.
- `_OPPOSING_POSITION_ASK` in both mode-point prompts: the paper's ask stated
  as a step, with the measured caricature as the concrete failure (the review
  skill's rule: a rule the procedure omits is not a rule; a check stated where a
  recipe belongs becomes the recipe).
- `AntithesisExtraction.selection_key` and `AnalysisPipeline._selection_key`:
  potential, HS as fallback where nothing rated it (SIMPLE path, consolidated
  pairs, pre-existing oppositions). HS keeps the validity gate.
- `TetradPotentialEstimation` persisted next to Mode/Arousal; `polarity_quality`
  and the Analyst's "Reading Polarity Quality" section carry it.

## Before / after (20 utterances, Path B of the probe, Sonnet 5)

Before (2026-09-29): drawn 19/20; antithesis a caricature on 19/19; HS(A) 0.95
uniform; CC passed 2/19; median 49 s.

After (2026-09-30, same 20 utterances, same model; per-item JSON kept in the
session scratchpad): drawn 20/20, errors 0; **CC passed 7/20** (was 2/19);
HS(A) now spread 0.75–1.0 (was 0.95 uniform); median 59 s (was 49 s — the
extra rating costs tokens, and one run's variance is within that).

The antitheses, read by hand and sorted into two piles:

- **A position with its own value — 12/20.** "Build mastery and security within
  employment", "Decline the offer, stay rooted here", "Keep parents at home,
  care for them ourselves", "Strip features down to the essential core", "Trust
  public school to educate my kids", "Confront it now, fully, unfiltered",
  "Chaos itself drives real innovation", "Strict rules prove how much I care",
  "Discipline just kills spontaneity and joy", "Refusing clients protects my
  energy", "Remote work builds a stronger culture", "Promoting your best
  engineer is the right call".
- **A mirror-image stance — 8/20.** "My co-founder always listens to me" (HS
  1.0: the SIMPLE path's mechanical negation, not this selector at all), "I
  fully trust my new manager", "Hire only juniors; seniors slow the team",
  "Keep funding brother, no matter what", "Double the marketing budget to grow",
  "Prices too high, must be lowered", "Every meeting must end with a firm
  decision", "Always be reachable for work". These are the opposite STANCE
  rather than the absent-T caricature ("never risk anything") the old selector
  chose, and several still yield a usable A+ ("Help with clear, sustainable
  limits attached"), but they are not the functional opposition the paper asks
  for.

So: the selector no longer picks the strawman end of the ladder (19/19 → 0/20
of the "never/forever/nothing" shape), the coherence pass rate more than
tripled, and roughly a third of the antitheses are still mirror stances. One
sample each side, one rater. Two threads remain open, both upstream of the
selector:

1. **The candidates themselves.** The ladder's high rungs are asked for
   Negation/Inversion of T; with the ask fixed the model now offers a stance
   rather than a caricature there, but a stance is what those rungs produce.
   The genuine-position candidates come from the middle and low rungs. Whether
   the selector should weight rungs, or the rung prompts should change, is a
   prompt-review question with a measurement behind it — not this change.
2. **The SIMPLE/COMPLEX boundary.** "My co-founder never listens to me" was
   classified SIMPLE and mechanically negated (HS hardcoded 1.0, no ladder, no
   potential). CLAUDE.md already calls that boundary the most leverage-dense
   prompt in the pipeline; this run is one more row for it.

What this does NOT settle: whether CC at 7/20 is the ceiling of this path or
the selector's floor. The tetrads behind the 13 failures were built from
positions, so the next look is at `AspectGeneration` on these pairs, not here.
