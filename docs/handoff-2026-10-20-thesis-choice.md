# Handoff from alsotrue, 2026-10-20: the view turn bears the mildest claim and opposes it with the opponent the person already granted

From the first app (`alsotrue`, the sibling repo), after three pieces of user feedback on one shared
card and a four-draw probe on the same input. This is a report of what the framework drew and
what the app measured around it. The proposals at the end are things to measure, not asks to
ship; the app changes its own side regardless (the last section).

Framework 2.1.1 on the released pin, Sonnet 5.5 on Bedrock, `Consultant.exploration_view`
with `attempts=3`, `COUNSELOR_PERSONA` as the app preamble, `component_length` 7.

## The case

The public card: https://alsotrue.app/c/ml3NM-CatQkq2Ks1oJDuPQ. The person's session record
stays in the app repo on the owner's machine (`backend/cases/`, never committed; ask the owner),
so this note quotes only what the point needs.

**The input** is a six-sentence Lithuanian polemic about school violence in France and mass
migration, addressed to the public broadcaster. It holds at least four claims, in this order of
force: society has the right to ask how much failed migration policy contributed; this is an
integration and order problem, not only a school problem; the broadcaster should not only repeat
"bad schools" but also ask who these youths are and where they come from; **"Stop masinei
migracijai"** (stop mass migration), and Lithuania should not wait. The text names the opponent
it is reacting against, "bad schools" as the whole explanation, and concedes it in the same
breath: **"ne tik … bet ir"** (not only, but also), "ne vien" (not solely).

The app's gate cut this to an 80-word stance (all of the above minus two sentences) and pinned
it verbatim as T (`exploration_view(thesis=)`, the 2026-10-12 pin).

**What the framework drew** (the card on the link; `tetrad.draw`, best-of-3, pinned):

| corner | text |
|---|---|
| T | the 80-word stance |
| A | Smurtą aiškinti socialinėmis sąlygomis: skurdu, atskirtimi, mokyklų būkle (explain violence by social conditions: poverty, exclusion, state of schools) |
| T+ | Atvirai įvardyti faktus ir riziką, matuoti ir tikrinti duomenimis (name facts openly, measure with data) |
| T- | Visą smurtą priskirti kilmei, žmones paversti grupe (attribute all violence to origin, turn people into a group) |
| A+ | Smurto šaknis tirti per skurdą, atskirtį, mokyklą (study the roots through poverty, exclusion, school) |
| A- | Etninės ar kilmės klausimų nutylėjimas, vien "sąlygų" kartojimas (silence on origin, repeating "conditions") |
| reading | Nepatogių faktų įvardijimas prieš pasekmių ignoravimą |

**What the person said about it**: they would make the central question harder: "Ar skurdas ir
socialinė atskirtis iš tiesų paneigia migracijos politikos įtaką smurtui, ar jie gali būti tos
pačios nesėkmingos integracijos politikos pasekmės?" (do poverty and exclusion refute the
influence of migration policy, or are they consequences of the same failed integration policy?).
A colleague of the owner: "pats pirmas promptas (T identification) su AI varikliu yra ypač
svarbus", and one bad card is enough to stop using the app.

## What is wrong with the drawn tetrad, by the method's own rules

1. **A fails the axis test.** `TETRAD_BUILD_PROCEDURE` wants an axis on which T and A cannot
   both hold. T here already concedes A ("ne vien", "ne tik … bet ir"). Both hold. A+, "study
   the roots through poverty, exclusion, school", is a clause the person typed, not a blind
   spot; the person read it as "the line I was complaining about, stamped also true".
2. **The strongest claim is in no corner.** "Stop masinei migracijai" is the sentence the person
   would sign. It appears in T only because T is the whole paragraph; T+ is "name facts, measure
   with data", the one claim A can live with, and the four corners are a tetrad about the
   mildest sub-claim ("society has the right to ask").
3. **The vocabulary was swapped.** The person wrote "migracijos politika", "integracijos
   problema", "politika be aiškių ribų ir atsakomybės". No corner says "politika". The tetrad
   rewrote migration policy as "kilmė" / "etninės" (origin, ethnic), then warned the person about
   group-blame by origin. The card's text inherited the nouns.
4. **The text then charged a price for a position they did not take.** The app's text voices
   "T+ without A+ yields T-" as the theory says; with this A+ the conditional lands as "if you
   ask ONLY where they are from", against a person who wrote "not only". The text layer did
   its job; the defect is upstream, in which A was drawn.

## The probe: is it the model or the pin?

`alsotrue/backend/alsotrue_tests/e2e/probe_case_tensions.py` (added with this handoff), the same
input through `Consultant.exploration_view` four ways, `attempts=3`, one draw each,
2026-10-20. The winner of each:

| run | T | A | A+ | s |
|---|---|---|---|---|
| prod: Sonnet 5.5, pinned | the 80-word stance | explain violence by social conditions | study the roots through poverty, exclusion, school | ~25 |
| A: Sonnet 5.5, unpinned, free focus | Turime atvirai klausti, kiek smurtą mokyklose lemia migracija | Smurtą mokyklose pirmiausia lemia mokyklų ir socialinės sąlygos | Smurto šaknys tiriamos per sąlygas ir įrodymus | 15 |
| D: Sonnet 5.5, stance quoted in the focus, not pinned | Smurto mokyklose šaknis reikia viešai kelti per migraciją ir sustabdyti masinę migraciją | Mokyklų smurtą spręsti per mokyklų sąlygas ir socialinę įtrauktį | Smurtą aiškinti socialinėmis, mokyklos ir integracijos sąlygomis | 30 |
| B: Opus 5.5, unpinned, free focus | Stop masinei migracijai – reikia aiškių ribų | Integruoti atvykusius, o ne užsidaryti | Integracija paverčia atvykusius bendruomenės dalimi | 42 |
| C: Opus 5.5, pinned | the 80-word stance | Smurtą gimdo atskirtis, ne kilmė | Šalinti atskirtį, kuri augina smurtą | 34 |

Free focus = the app's unpinned ask, "the perspective for what I just said: my position, what
it stands against, and above all the constructive side of that opposing view that I am not
seeing". The pinned ask quotes the stance and adds `THESIS_IS_FIXED`.

**Readings.**

- **Sonnet 5.5 bears the mild claim and opposes it with the named, granted opponent in every
  configuration.** Pinned or not, with or without the stance in the focus. Run B is the
  tension the person and four independent reviewers asked for: the strong claim against
  integration, with an A+ the person had not granted. Opus 5.5 found it unpinned, and even
  pinned (C) it put "integracijos nesėkmes" into T+ and moved A+ one step past "bad schools".
- **Sonnet drew the right T and threw it away.** Run A's two runners-up were
  "Sustokime masinę migraciją, kol nebuvo per vėlu" against "aiškinti sąlygomis ir integracija"
  (A+ "Mokyklos saugumas ir integracija, kuriuos valstybė užtikrina") and "Sustokime masinę
  migraciją ir kalbėkime atvirai apie smurtautojų kilmę" against integration. The judge,
  running on Sonnet too, ranked the mild tetrad first. So on Sonnet the selection is part of
  the failure, not only the sketch: a tetrad about a hedge is more coherent than a tetrad about
  a demand, and coherence is all the ranking reads.
- **The pin is a smaller effect than the model.** Sonnet unpinned looks like Sonnet pinned.
  Opus pinned is worse than Opus unpinned but better than anything Sonnet drew.
- One case. Not a measurement; a reproduction with a clear direction.

## Where in the framework each push comes from

- `concerns/view_sketch.py:193` `THESIS_IS_A_STANCE` says T is a stance the person holds and
  says nothing about WHICH claim when the words hold several. Nothing prefers the decisive
  claim (the one they would sign) over the hedged premise ("we have the right to ask").
- `concerns/antithesis_extraction.py:69` `_OPPOSING_POSITION_ASK` wants A "in the thesis's own
  terms". When the thesis's own terms contain its opponent, that opponent is the most literal
  answer. The ask rates a caricature low for tetrad potential; nothing rates an A whose A+ the
  person's own words already grant.
- `concerns/scoring_scales.py:25` T+ "also strengthens what A offers": with the wrong A this
  pulls T+ to the one claim A can live with, and the strong claim leaves every corner.
- `agents/apps.py:563` `COUNSELOR_PERSONA`, "gently illuminate": with the above, a hard stance
  arrives sanitised ("politika" to "kilmė"). Not measured apart from the rest.
- `agents/consultant/consultant.py:503` the pin writes the given text over T; with
  `view_sketch.py:296-306` ("whatever its length") an 80-word T sits over 7-word corners built
  from one clause of it. This is the app's own doing (below), noted so the trace is whole.
- `tetrad_candidates.judge_sketches` ranks by the weaker control statement, reading the
  person's turns since 2.1.1 (`judge_context`) but never T or A. It cannot see that draw 1's T
  is a hedge and draw 2's T is the demand.

Known and respected: the different-opposition ask for draws 2..N was measured and rejected on
2026-10-13 (`docs/dev-notes/antithesis-selection.md`, "Best-of-3 drew the same tetrad three
times"), and "selection, never regeneration from the verdict" is the rule. Nothing below asks
for either.

## Proposals, each to measure

1. **Thesis choice on multi-claim input.** In `THESIS_IS_A_STANCE` (or beside it, for the view
   turn only): when the words hold several claims, T is the one the person would sign, the
   conclusion or demand, not the premise or the hedge that leads to it; the claims they concede
   on the way ("not only X", "X matters, but") are not T. Measure on a set of long polemics
   (real people paste these; the app's eval cases are short and single-claim, which is why this
   was never seen). The app will supply the inputs it has, de-identified, if useful.
2. **An A whose A+ the person already grants is not an opposition.** Next to the caricature
   rule in `_OPPOSING_POSITION_ASK`: an A the person's own words already name AND concede is
   seen, not missing; rate its tetrad potential low and oppose the claim they actually made.
   This is the same shape as the caricature rule and the same place.
3. **A thesis-fit term in the ranking.** The judge reads the person's words since 2.1.1. A
   read of "is this draw's T the claim the person would sign, and is its A+ something their
   words do not already grant" would have ranked run A's runner-up first. It is a selection
   term, not a regeneration loop, so it stays inside the 2026-10-13 rule. Gate it on
   `probe_joint_judge_stability.py` like any judge change.
4. **The model.** Opus 5.5 unpinned drew the right tension at 42 s for the view turn alone,
   against the app's 52 s card deadline. The two time levers in the dev note stand
   (`Consultant(thinking="low")` on the view turn, the judge on Sonnet 5.5); the app has not
   tried them. If 1 to 3 do not close the gap on Sonnet, the app's choice is Opus with those
   levers, and then the quality of a "low" view turn needs its own number.

## What the app changes on its side

- **Unpinning.** The 2026-10-12 pin fed a presentation artefact (the gate's faithful cut, kept
  for the screen) into the reasoning as T. The app stops pinning the first draw and labels the
  screen honestly instead: "You said" is their text, "Taken as" is the framework's T. The app's
  no-rewrite rule covers what is labelled theirs; T is not. The pin's contract in
  `exploration_view(thesis=)` stays as is for hosts that want it.
- The app's prompts (text, closing) need no change for this case: they voice "T+ without A+
  yields T-" as the theory says, and the defect was which A they were voicing.
- An eval the app owes itself (`evals/README.md`, "is the first card's A+ a real blind spot")
  and a case set with long multi-claim inputs. The app's "faithful" eval judges the shown line
  against the typed words and would not have caught any of this.

## Reproducing

From `alsotrue/backend`, with the case file in `cases/` (owner's machine only) or any
multi-claim polemic as the opening:

    PYTHONPATH=$PWD uv run python alsotrue_tests/e2e/probe_case_tensions.py cases/<id>.json out.json

It prints the winner and the two runners-up of each of the four runs; results are gitignored
(`alsotrue_tests/e2e/results/`). The framework's own `tests/e2e/probe_view_turn_ask.py` is the
right instrument for a measured arm once there is a case set.
