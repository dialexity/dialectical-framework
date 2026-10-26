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
