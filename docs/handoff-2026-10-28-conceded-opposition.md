# Handoff from alsotrue, 2026-10-28: A is the opposition the text already granted, half the time

**Where it comes from.** The app's new `evals/multiclaim/` flow: your two petition sets
(`tests/e2e/multiclaim_cases.py`), 22 conceding + 18 late, each through the app's gate and
first card (the view turn as the app calls it: `Consultant.exploration_view(focus=…)`, the
focus naming the gate's cut as "the position I hold — «…»", no `thesis=`), 2 reps, framework
2.1.3 on `anthropic/claude-sonnet-5-5`, judge Opus 4.8 on Bedrock. The judges were reviewed
by three independent reads before the baseline; the opposition judge first says whether the
`conceded` clause grants an opposing POSITION (29 of 46 rows) or only a fact, a sympathy or a
view named to be rebutted (17), and the A facts are read over the positions only.

**The figure.** On the 29 rows whose clause grants a position, the card's A is that granted
view on 16 (±19). A+ is that view on 3. T is the demand on 79/80 and one claim on 75/80.

So the T side of the 2026-10-20 handoff is closed on this set, and the A side is not: the
mirror in `_OPPOSING_POSITION_ASK` ("an opposition the words name AND concede is seen, not
missing") is not reaching the view turn's choice on the app's path, at a rate your own
2026-10-26 run on these sets could not see (it scored the writer's A+ against the conceded
clause, where the app's A+ escapes 26/29; the failure is in A, the pole, not in A+).

Rows where A restates the granted clause (petition id, A as drawn, the clause's start):

- 308031 "Keep hospitality businesses trading; families' livelihoods depend on it" — "We in
  Cornwall above all understand the need to keep businesses open…" (both reps)
- 725515 "Single-sex spaces defined by biological sex protect women's privacy and safety" —
  "Whilst some female only spaces may need to be protected…" (both reps)
- 735371 "GPs keep full discretion to decline SCAs" — "SCAs can be declined at a GP's
  discretion. However…" (both reps)
- 763504 "Keep the visa brake to curb surging asylum claims" — "Although intended to prevent
  misuse…" (both reps)
- 771145 "Gilbert's is harmless; guidelines need no change" — "Gilbert's Syndrome is
  classified as a harmless condition, however…" (both reps)
- 308917, 310280, 700317, 771873 (one or both reps)

The pattern is the Lithuanian card's: the text says "X is true, however Y", and A comes back as
X. The person wrote X down to get past it.

**Two other things the same run shows, for the record.**

1. T is over `component_length` (7) on 76/80 rows, median 10 words, max 13, on lines that
   hold one claim as much as on joined ones. The app's focus quotes the gate's cut (one to
   three sentences); whether that is what inflates T is the app's next arm (focus with no
   stance named). If T stays long with no stance in the focus, the cap is not holding on
   its own.
2. The app's gate (its own prompt, reading `THESIS_IS_A_STANCE`) finds the demand 80/80 but
   joins it with a framing or second ask on 13/80 and copies non-adjacent sentences on 22/80,
   differing across reps on 11/40 inputs. That is the app's to fix.

**Asked.** Whether the conceded-opposition rule can be made to bite on the pole A as it is
drawn under a host focus — or whether the selection (the fit judge, HS) should read "A is a
view the words grant" as disqualifying, the way the attribution check drops a holder the
words do not bear. The 29 rows with A, A+, the clause and the judge's reason are in the app's
`.claude/hillclimb/multiclaim-sonnet-5-5/baseline/results.jsonl` (`meta.card`, `meta.conceded`,
`explanation.opposition`), committed there.

---

**Taken up by the framework, 2026-10-28.** `ThesisFitCheck` reads the pole: `antithesis_already_granted`
is a third read beside T-is-the-claim and A+-already-granted, `fit` the weakest of the three, still a
yes/no inside the pass rule. Measured offline on these rows and on the framework's own saved draws
(`tests/e2e/rescore_conceded_a.py`; the record: `docs/dev-notes/antithesis-selection.md`, "A is the
view the author granted"): agrees with the app's judge on 21/29 rows, finds the same petitions on
`attempts=1` draws with a generic focus, flips 14/29 of these rows to "does not fit" — and, because the
draws of one card are one tension reworded (A conceded in both reps or neither on 12/13 petitions
here), it ranks nothing where every draw bears the granted view. The prompt's mirror rule is inert at
the pole too (3 vs 3, 6 vs 6 paired). The T cap: the framework's own draws run over it by one word at
the median with no stance quoted (24–30/40 over 7); the quoted cut adds about two.
