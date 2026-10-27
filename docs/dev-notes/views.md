# Views: the graph for a screen, and the Consultant's view turn

Lab notes for `graph/views.py`, `Advisor.exploration_view()`,
`Consultant.exploration_view()` and `concerns/view_sketch.py` (2026-09-28/29).
Rules are in CLAUDE.md ("Shared Rendering"); this is the reasoning and the
measurements.

## Why a view module at all

No JSON view of the graph existed for either head (`grep to_dict\|model_dump
graph/` was empty). `rendering.py` renders prose for a prompt, where a cut text
is a reasoning defect; a widget has different rules — absence must be `None`
(never `explorer._causality_probability`'s `-1.0`, which exists to lose a
ranking), nothing truncated, structure always present, terminology optional. So
a sibling module rather than more functions on `rendering.py`.

## Decisions that were argued, in order

- **Views carry the graph's own fields and invent none.** The first version had
  `diagonals` (which field faces which, with an axis each), `axes` parsed out of
  `intent`, and a `reading` field. Owner's call: drop them; `intent` verbatim,
  call it `intent`; a widget knows T+ faces A- from the theory. Names followed:
  `TetradView`/`tension_map_view` became `PerspectiveView`/`exploration_view`
  (an exploration is a Nexus; without one it is every active perspective and
  `nexus_hash` None).
- **`hides_terminology` stays.** It is the public reading of the flag
  `reply_hygiene` filters text with. Not a necessity — a host usually knows
  which product it runs — but one rule in one place; `Advisor.exploration_view()`
  applies it so the host need not hold it.
- **First-class axis fields on `Perspective`: not now.** A subagent read the
  code: `committed_at` is in every Perspective hash, so no two commits ever
  collide and hash-level dedup for Perspectives does not exist
  (`incremental_build_mixin.py`: "No dedup for container nodes"); real dedup is
  `ExpandPolarity._find_duplicate` → `is_same`, six component hashes, `intent`
  ignored. So the reading is a LABEL, not a key — and CLAUDE.md, two code
  comments, the review map and a test docstring had said otherwise. Corrected.
  Revisit the field pair when a consumer needs axes independently of the
  sentence; names then `axis_t_plus_a_minus` / `axis_a_plus_t_minus`
  (`axis_constructive`/`axis_reflective` rejected: both diagonals hold one plus
  and one minus, and "reflective" is a Transformation word).
- **The Consultant's view is a TURN on its own conversation, not an
  extraction.** Version 1 handed the person's turns to a fresh conversation and
  asked it to derive tensions. Owner's objection, right twice: a view asked for
  mid-conversation must show what the conversation ESTABLISHED (a stranger
  reading half the transcript can disagree with the prose on screen), and the
  ask is often a request to REASON ("a perspective for that thesis" = build the
  tetrad first). So: json-mode facilitator over the same history (the one
  structured shape that thinks — the first caller of
  `ConversationFacilitator(format_mode="json", thinking=)`), builds what
  `focus` needs, leaves unasked corners empty, stays in history.
- **Who initiates: the host (owner's decision).** No `show` tool, no
  model-emitted inline view. Election rates (`anchor` 6/6, `explore` 2/6,
  `deepen` 0/6) are the argument against trusting the model with "when".

## The real runs (`tests/test_view_sketch_real_llm.py`, Sonnet 5 via Bedrock, thinking medium)

One consultation (two chat turns), then `exploration_view()` with no focus,
then with `focus="a full perspective for the thesis you named…"`, then a chat
turn asking about a drawn corner.

| run | what changed | result |
|---|---|---|
| 1 | first real run | both turns parsed; no-focus drew one full perspective + one poles-only (corners `null`, `complete: false`); build turn 25.5s, complete, two-axis reading. **Reply 3 said "the one I'd flag is T-" to the person** — the bare-label leak, caused by `history_text` writing `T+: …; T-: …` into the model's memory |
| 2 | record rewritten in the person's terms ("X developed well: …; X overdone: …") | leak gone from the record — and the **second view turn answered in PROSE**, in the record's shape, 10 parse failures. The long request + prose record had become a Q→A exemplar for the same kind of request |
| 3 | history keeps a short ask (`history_ask`) + the record, request says "earlier drawings are recorded in prose; that is their record, not the format" | 0 parse failures; 8.5s / 3.6s; build complete with reading; reply 3 reasons about "the empty-presence corner" and "Zurich decides fast, blind to the German market" — **no label** |

n = 1 clean after the fix. A screen, not a result: rerun before claiming the
parse defect is closed, and count labels in reply 3 across several runs before
claiming the leak is.

## The blindspot probe (`tests/probe_blindspot_paths.py`, 2026-09-29)

The first app (a blindspot app: one utterance in, a tetrad with A+ in front out)
needs a tetrad per free utterance. Two ways exist; 20 utterances through both,
one rater, per-item JSON kept in the scratchpad of that session.

| | A: `Consultant.exploration_view(focus=…)` | B: headless `anchor` (thesis-only branch) → `perspective_view` |
|---|---|---|
| drawn | 20/20 | 19/20 (one `ClassificationDto` parse failure the envelope salvage did not unwrap: `{"parameter name": {...}}`) |
| latency | median 8.0 s, max 10.4 s | median 49.2 s, max 87.3 s |
| antithesis | a genuine opposing POSITION ("Gaming is his own space", "Focus on doing fewer things excellently") | mostly a strawman EXTREME ("Stay employed forever, never risk it", "I hate my new manager", "Strip every feature; ship nothing") |
| A+ read by hand | usable as a blindspot in most rows | usable in most rows, but as "the moderate version of the extreme" |
| scores / checks | none by construction | HS(A) a uniform 0.95 on every row (not discriminating); 17/19 `failed: Conceptual coherence`; 2 passed |
| memory | none | the graph — the "recurring blindspots" map |

Verdict for the pre-MVP: Path A. Two framework findings from Path B: the
thesis-only anchor path's antithesis was an exaggeration of not-T rather than
an opposing position (which then drove the CC failures), and HS did not
separate them. Traced to HS-ranked selection and fixed the same day —
`docs/dev-notes/antithesis-selection.md` has the mechanism and the before/after
(caricatures 19/19 → 0/20; CC 2/19 → 7/20; a third of antitheses still
mirror stances). Both were one sample.

Also found by this probe, fixed: a resumed conversation passed as dicts (the
documented persistence recipe's own output) failed inside the first structured
call with `AttributeError: 'dict' object has no attribute 'role'` — 20/20 on
Path A's first run. `ConversationFacilitator.load_messages` now hydrates
text-only dicts on every head and refuses tool parts and media at construction.

Two lessons worth the rule they became: **a history record must not carry the
labels the prose must not** (the model echoes its own memory), and **a long
structured request left in history next to a prose answer teaches the next
structured turn to answer in prose** — keep the person's ask, not the request.

## A failed draw is on the view (2026-10-09)

`Consultant.exploration_view(attempts=3)` gathered its draws with
`return_exceptions=True` and kept the survivors; a draw that raised was gone — no log, no
field, and (when it raised inside the provider call) no census record. The first app found the
hole by subtraction: 233 `ViewSketchDto` calls where 240 draws were made on Opus 5.5, six cards
chosen among two and one served as the only draw left. `FailedDrawView` (kind, refusal
category, message) now rides `ExplorationView.failed_draws`, logged once per failure; the
screen projection keeps kind and category and drops the message (a parse error names DTO
fields). The call still raises only when every draw failed. The replay that looked for the
cause (`tests/e2e/probe_card_replay.py`, 144 Opus 5.5 draws) found none, so the field is also
the instrument: `docs/dev-notes/streaming-latency-and-retry.md`, "The 5.5 handoff".

## Pasted material: the view turn hands the reader a position that is not theirs (2026-10-26)

**The question.** `THESIS_IS_A_STANCE` presupposes the text carries the person's own position
("something the person holds ... a claim they could say in the first person"). A host routes
whatever the person pastes to the view turn — the first app routes everything — and nothing in
`src/` distinguishes their own words from an article or a transcript. The fit judge's two reads
both presuppose authorship too. So: what does the writer do with text that carries only other
people's positions?

**The set** (`tests/e2e/pasted_material_cases.py`, built by `screen_pasted_material.py`): 20
pieces of REPORTAGE — Wikipedia controversy intros (CC BY-SA) and one Wikinews article (CC BY
2.5), 100-400 words, the author asserting nothing of their own by a blind screen's read — and
17 pieces of DIALOGUE, windows of 3-5 consecutive Hansard Commons contributions by at least two
named members (Open Parliament Licence). The screen listed each text's held positions with
their holders; the writer saw only the text.

**The finding** (`probe_pasted_material.py`, one arm, the shipped prompts, `attempts=1`):

| | reportage (20) | dialogue (17) |
|---|---|---|
| drew a tetrad | 11 | 17 |
| T worded as the READER's own stance | 11 of 11 | 17 of 17 |
| T worded as someone else's | 0 | 0 |
| T is one of the text's held positions | 10 of 11 | 17 of 17 |
| T and A are two different holders' positions | 7 of 11 | 8 of 17 |
| median seconds | 3.3 | 2.9 |

The hypothesis holds without exception: **whenever the writer draws, T is one of the OTHER
parties' positions, re-worded as the reader's own** — "The government was wrong to lift the beef
ban", "Scott was a bungler, not a hero", "Drop the family farm tax" — 28 of 28 draws attributed
to the reader, 27 of 28 a position the text attributes to someone else. A card built on this
tells the person "your position is X" about a claim they pasted from a newspaper or a debate.
That is the 2026-10-20 handoff's defect in another coat (a person handed a claim they did not
make), and it is not the rare case here but the only case.

Two further things the run says. The writer DECLINED 9 of 20 reportage items (no error, no
failed draw: the view came back empty), so the "a request for information carries no stance"
instinct reaches some third-party text — but not most, and never a dialogue. And in a dialogue
the writer took one speaker's position as T and then, in 9 of 17, INVENTED the opposition (A
matched none of the listed positions) rather than taking the other speaker's — the tension the
transcript actually carries was drawn in 8 of 17.

**What this means, and what it does not.** It does not mean the view turn is wrong to draw on
material: the one-shot writer finding the tension IN a text is exactly what the documents
ladder does, and this run shows it can (T a held position 27/28). It means the view turn has
no way to say WHOSE position it drew, and its prompt tells it to word everything as the
reader's. Three candidate repairs, none measured: (1) routing — a host sends third-party
material to the documents path (`ingest`), which never attributes; (2) a prompt rule for the
view turn — when the words carry others' positions and none of the reader's, draw the tension
in them and word T as theirs, not the reader's — which needs a way for the view to CARRY that
attribution to the screen; (3) an intake read, like the first app's stance gate, that
classifies the input kind before anything is drawn. (1) exists today and costs nothing to try;
(2) is a DTO change as much as a prompt change; (3) is app-side. The run that decides between
them is this probe with a second arm.

Instrument notes. The attribution read sees T's wording alone and the position read sees T
against the screen's list; both are blind to the hypothesis. The writer's arm is pinned by AST
to read only `case.text`. The Wikipedia items are encyclopedic rather than news — a limitation
of the reportage stratum, stated; Wikinews proved too slow to fetch at volume for this run
(its extracts API returns empty for most pages, and the parse route needs one throttled
request per title).

**Arm B, the same evening: drop the presumption of authorship.** The owner's reading of the
finding — why word T in the first person at all, a thesis is a claim — run as a second arm,
`HELD_BY_STANCE` in `probe_pasted_material.py` (`STANCE_ARM=held_by`): the same constant with
every sentence that stopped the question-echo kept, and "something the person holds, written
as a claim they could say in the first person" replaced by "a claim someone in these words
holds; whose depends on the words" — their own when they speak for themselves, one of the
reported holders' when the words carry only others' positions. Two probes, one run each:

| | shipped | arm B |
|---|---|---|
| reportage: drew | 11/20 | 20/20 |
| reportage: T worded as the reader's / as someone else's | 11 / 0 of 11 | 17 / 0 of 20 |
| reportage: T a held position; T and A two holders | 10/11; 7/11 | 16/20; 10/20 |
| dialogue: T worded as the reader's / as someone else's | 17 / 0 of 17 | 16 / 0 of 17 |
| dialogue: T a held position; T and A two holders | 17/17; 8/17 | 16/17; 10/17 |
| echo probe (20 questions): asker's own stance | — | 15/15 |
| echo probe: not-a-stance (the echo) | 0/20 (2026-10-05) | 1/15 |
| echo probe: requests for information declined | 3/4 | 4/4 |

**What arm B shows is that the first-person instruction was never reaching the wording.** Both
arms write bare claims — "Keep the ban; public safety comes first", "Drop the family farm tax"
— and the attribution read calls a bare claim the reader's, because nothing in it names a
holder; 0 of 37 draws in EITHER arm named one. So the attribution the finding is about is not
in T's words at all. It is in the host's ask ("my position, what it stands against") and in
the screen ("Taken as: your position"), and no wording of the rule can carry it. The one thing
arm B did change: the writer stops DECLINING third-party articles (9/20 → 0/20) and draws the
tension in them, a held position 16/20 and the two holders' positions 10/20, at twice the
seconds (7.6 against 3.3). On the person's own questions it is neutral within one case.

So the repair has two halves and only one of them is a prompt: arm B's rule (harmless, draws
the tension in material instead of declining it), and a FIELD the view carries — whose
position T is, named by the writer from the words — so a host can show "the Minister's
position" rather than "your position". The field is a DTO change on `ViewSketchPerspectiveDto`
and a host-contract change on `PerspectiveView`, which is the owner's call; without it, arm B
alone buys "draw on articles" and nothing about attribution. Routing material to the documents
path remains the no-code alternative.

**Shipped (option 2, the owner's call the same evening): the rule AND the field.** Arm B's text
is now `view_sketch.THESIS_IS_A_STANCE`, with one sentence added — the holder is NAMED in
`held_by` — and the old first-person text moved into the probe as the control
(`STANCE_ARM=first_person`), the way rejected prompt text is kept in this tree.
`ViewSketchPerspectiveDto` gained `thesis_held_by` and `antithesis_held_by`, each a text beside
its pole (every field on that DTO is a text; empty = the person's own, and the strict schema
keeps them required — a defaulted field drops out of `required` and the model may omit it).
`PoleView.held_by` carries it: None = the person's own or, off the graph path, unknown (a
persisted Statement stores no holder). It is words, so `without_terminology` keeps it — it is
exactly what a hidden-machinery screen must show instead of "your position". `history_text`
writes "(the Minister's position)" so the next reply does not say "yours". A pinned thesis
(`exploration_view(thesis=)`) forces it empty in code, since the host's words are the person's
own by contract. The real-provider shape check (both probes re-run on the shipped prompts, with
`held_by` read) follows below.

**The shape check, on the real provider (same evening).** Both probes re-run on the shipped
prompts with `held_by` read:

| | reportage (20) | dialogue (17) | the 20-question echo probe |
|---|---|---|---|
| drew | 19 | 17 | 17 (3 declined: 3 of the 4 requests for information) |
| `held_by` named on T | 19/19 | 17/17 | **0/17** — the person's own words, empty as required |
| names the same party the blind screen did | 9/15 | 16/17 | — |
| `held_by` named on A | 18/19 | 15/17 | — |
| T a held position; T and A two holders | 15/19; 13/19 | 17/17; 9/17 | — |
| asker's own stance / echo / CC | — | — | 16/17 / 1/17 / 16/17 |

The field fills where it should and stays empty where it should, and the names are specific
("Lee Myung-bak's government", "Protesters and critics", "Ken Cuccinelli, Virginia Attorney
General"). The 9/15 on articles is partly the same-party judge's strictness ("the documentary
(Hartog)" against the screen's "Hartog" was called a mismatch) and partly real: an article has
more parties than a two-speaker window. Two things stayed open after that evening: the writer
inventing A instead of taking the other speaker's position, and the fit judge's two reads
presupposing authorship. Both are taken up below.

**A name on words never said (2026-10-27).** Re-reading the shipped run's dialogues against
their texts: the "invents A in about half" figure was mostly the position-list judge calling a
paraphrase "none" (8 of 17 at 0, several of them the other speaker's position reworded). The
real defect in it was narrower and worse: the writer had named a speaker as holding an
opposition it had BUILT — the Exchequer Secretary given "Fund public services through taxing
business" over a window in which he defended a rates support package; Anna Turley given the
opposition to a position she had just agreed with. A screen shows that as "the Minister's
position" over words the Minister never said: a misquotation, worse than "your position" was.
The field descriptions said "the other speaker" and nothing about a built opposition.

The repair is one more rule text on the view turn's request, `view_sketch.HOLDER_FROM_THE_WORDS`
(after the opposition ask, before the build procedure, both branches): a party is named as
holding a pole only when its own words state or plainly take it; when another party in the
words holds the position T stands against, A IS that party's position and they are named; when
no one does, build it and leave the holder EMPTY — "a name on words never said is a
misquotation". The two `held_by` field descriptions say the same and stayed in both arms (the
arm isolates the rule text; the fields are the floor). View turn only: the one-shot build drops
the holder before persisting, so its half is unmeasured there.

The gate (`probe_pasted_material.py::test_the_holder_rule_on_pasted_material`): WITH against
WITHOUT the text, the 37 cases, two draws each, 74 per arm, paired by case and draw. The reads
are TEXT-GROUNDED this time — `_holder_in_text` is shown the text and one sentence and asked to
whom the text attributes it — because the position-list read had proved too coarse. Bars were
pre-registered: PRIMARY, A falsely attributed (a holder named and the text does not bear it) at
most 2 of 74 WITH and no more than WITHOUT; SECONDARY, A a position the text attributes to
someone, +6; side conditions, coherence, the antithesis a position and T-from-the-text each
losing at most 5.

Two readings, because the first judge was wrong for half the set and I changed it after seeing
the data — stated as such. The first asked whose OWN WORDS take the sentence, which is right for
a transcript and wrong for an encyclopedic intro, where nobody speaks and every position is
REPORTED: it called "opponents of trophy hunting" a false attribution in both arms (reportage 24
against 25). The second asks to whom the TEXT attributes it, stated or reported, which is the
criterion a misquotation violates. Draws were not redrawn; the saved run was re-read
(`PASTED_REREAD`).

| per arm, 74 draws | WITH | WITHOUT | paired (W/L, p) |
|---|---|---|---|
| A falsely attributed — own-words read | 30 | 37 | 6/7, 1.0 |
| A falsely attributed — attributed-by-the-text read | 16 (dialogue 4/34) | 23 (dialogue 8/34) | 7/12, 0.36 |
| A a position the text attributes to someone | 58 | 46 | 16/4, **0.012** |
| A built and left unnamed (the honest case) | 9 | 9 | |
| A unnamed though the text attributes it (missed holder) | 5 | 1 | |
| T falsely attributed | 11 | 13 | |
| T a position the text attributes | 63 | 65 | 5/7 |
| coherence pass | 41 | 46 | 10/15, 0.42 |
| antithesis a position | 65 | 66 | 5/6 |
| median seconds | 3.6 | 3.6 | |

**The verdict, by the bars: the absolute primary bar is MISSED (16, not 2), the relative half
holds, the secondary clears and resolves (+12, the only resolved effect), the side conditions
sit at or inside their bars** — coherence loses exactly 5, and the 15 pairs it lost include
several where the A text is identical in both arms (the US beef case scored 0.62 against 0.82
on the same words), so that is the judge's own variance. The rule ships. Why, with the primary
bar missed: the bar presupposed a judge with no false positives, and the same-party read is
not one — "Assange's defenders and press freedom groups" against the text's "Assange's
defenders", "Rep. Shelley Berkley and Rep. Jon Porter" against "Jon Porter", "Charles Duelfer;
George W. Bush" against "Iraq Survey Group (headed by Charles Duelfer)" are all counted false in
BOTH arms. One hand read of the flagged rows (one rater, this session, stated): the real
named inventions are about 4 of 74 WITH against about 10 WITHOUT, dialogues about 2 against 5,
and the ones gone are the shipped run's own — the Exchequer Secretary (twice WITHOUT, never
WITH), Sarah Jones given a restructuring position she never stated (twice WITHOUT), Georgia
Gould given "accept transition strain". What remains WITH: Andrew George named for the
inverse of his own position (one draw), the inquiry lawyers and the government swapped
(one), and two arguable inferences from a question ("welfare growth must be held down" from
a member who said the bill keeps growing). So the rule halves the misquotation and does not
end it; about one draw in twenty on material still names a party for words the text does not
bear, and no wording was going to take that to zero — prompt enforcement scales with
compliance. **The lever left is code, not prompt**: a fail-soft attribution check after the
draw, one judge call per NAMED holder (free on the person's own words, where `held_by` is
empty), that blanks a holder the text does not bear — the misquotation becomes an honest
unnamed construction, the way the pin is enforced by write-back rather than by compliance.
Built the same afternoon (owner: "go through the points you recommended"), below.

The first gate run was lost to its own instrument: the reads gathered ~150 judge calls at once
against the organisation's concurrency limit and one judge without a try/except raised a stream
timeout after 148 unsaved draws. Draws are now saved before any read, the judges go through a
semaphore (`PASTED_JUDGE_CONCURRENCY`, 6), and a saved run can be re-read.

**The fit judge no longer presupposes authorship (same day).** Its two reads were worded as
"the claim the PERSON would sign" and "the PERSON's own words", and a host's `fit_against` is
whatever was pasted. `ThesisFitCheck.score_texts(held_by=)` now takes the holder the draw
names for T (`judge_fit` hands on `thesis_held_by`) and asks both questions about THAT party —
"T is the Minister's position, which the words REPORT: its holder is the Minister, not the
person who pasted the words" — and, with no holder, "its holder is the person speaking", the
shipped behaviour in substance. The stability arm of `probe_thesis_fit_judge.py` was re-run on
the reworded prompt the same day (figures in `antithesis-selection.md`, "The fit judge is told
whose claim"); its effect on a choice is still unmeasured, as before.

**The attribution check, in code (2026-10-27, `concerns/attribution_check.py`).** After the draws and
before selection, `Consultant.exploration_view` runs `drop_unborne_holders` over every draw's first
tension — the spares too, since a runner-up is served without a new call. One structured call per
NAMED holder, shown the person's words and one pole, asked whether the text gives that party this
position; a holder not borne is blanked in place. Fail-soft keeps the holder (dropping on error would
show "your position" over the Minister's). No call where no holder is named, so the person's own words
cost nothing. Never a replacement: the judge may not put a different name on the screen.

Measured offline first, on the saved WITH-arm draws of the gate (`tests/e2e/rescore_attribution_check.py`,
130 named holders on 74 draws), read against the probe's own text-grounded judge and same-party read:

| verdict wording | dropped | of them the probe had flagged | of them the probe had grounded (over-blank) | flagged but kept |
|---|---|---|---|---|
| v1: "does the text attribute this position to X" | 28 | 18 | 10 | 9 |
| v2: a fair condensation of their stance is theirs; NOT = no stance, the opposite side, or someone else's | 22 | 17 | 5 | 10 |

v1 read an elaboration as a misquotation ("opponents of trophy hunting" refused "killing for pleasure is
wrong" because the text says only that the controversy is about the morality of hunting for pleasure; a
rhetorical question that takes a side was "no stance"), and a dropped TRUE holder costs exactly what the
check exists to prevent, in reverse. v2's five over-blanks are two compound poles half the writer's own
("the memo doesn't reflect official policy; the case rested on real WMD", the second clause nobody's),
two inferences from a question (Melanie Onn, John Lamont) and "supporters of trophy hunting" given an
argument the intro does not state — defensible drops, all of them. Its ten "flagged but kept" are the
same-party read's compound-name mismatches ("Assange's defenders and press freedom groups" against
"Assange's defenders"), correctly kept. The two clear hand-read misquotations — Andrew George named for
the inverse of his own position, the inquiry lawyers and the government swapped — are among the agreed
drops. v2 ships; v1 is recorded in the module.

**Live, with the check active** (the 37-case finding probe, one draw each, 35 drawn; the same
text-grounded reads as the gate):

| | gate, WITH arm (74 draws, no check) | live with the check (35 draws) |
|---|---|---|
| A named for words the text does not bear | 16 (22%) | 4 (11%; dialogue 1 of 16) |
| T named for words the text does not bear | 11 (15%) | 3 (9%) |
| A still named | 60 (81%) | 25 (71%) |
| A a position the text attributes to someone | 58 (78%) | 26 (74%) |
| median seconds a draw | 3.6 | 7.2 reportage / 8.1 dialogue |

So the rule and the check together take the misquotation from the shipped run's level to about one
A in ten by the probe's judge — which still counts compound-name mismatches as false, so the real
figure is lower — at the cost of one judge call's latency on material, sitting between the draws and
selection because the fit judge reads the holder. On the person's own words nothing changes: no
holder, no call. Not pursued: running the check beside the selection judges (would hide the latency
on best-of-N cards at the price of the fit judge reading an unchecked holder), and a replacement name
from the check (the judge may not name a party for the screen).
