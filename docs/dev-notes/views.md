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

Two lessons worth the rule they became: **a history record must not carry the
labels the prose must not** (the model echoes its own memory), and **a long
structured request left in history next to a prose answer teaches the next
structured turn to answer in prose** — keep the person's ask, not the request.
