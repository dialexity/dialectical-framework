# What you can build: the heads, the axes, the combinations

The one-page map. `docs/agents.md` has the detail behind every row; this page
exists so a developer can see the whole space at once and pick a construction
without reading it.

## The four heads

Every head has the same conversational surface (`chat`, `chat_stream`,
`messages` for resume). They differ in what they need and what they leave behind.

| Head | Construct | Needs a Case / `scope(sid)` | What the person sees | Builds the graph | Keeps a record |
|------|-----------|-----------------------------|----------------------|------------------|----------------|
| **Consultant** | `Consultant(app_preamble=)` | **no** — no database at all | a conversation | never | never: a confirmed decision is restated in the reply, and that is the only record |
| **Analyst** | `Analyst(app=)` | yes | the structure, in the open (inputs → tensions → a nexus) | yes, every tool call visible | no decision ledger |
| **Explorer** | `Explorer(nexus_hash=, app=)` | yes | the structure, in the open (one nexus → pathways → synthesis) | yes, inside the pin | no decision ledger |
| **Advisor** | `Advisor(app=, build=, records=, nexus_hash=)` | yes | a conversation; the framework runs silently | per `build=` | per `records=` |

Analyst + Explorer (+ the Advisor's advisory register over the same `messages`) is the
**Navigator**: the person watches the wheel being built. Everything else is the Advisor
in one configuration or another — except the Consultant, which is the Advisor's method
with no Advisor behind it. (Vocabulary, 2026-09-28: "Consultant" is this one-off agent;
the Advisor that never builds, `build=NEVER`, is the **sealed Advisor**. Before that date
the docs and the round log called the sealed Advisor "the Consultant".)

## The axes

Seven parameters, and they answer seven different questions. Nothing else is a knob.

| Axis | Parameter | On which heads | Values | The question it answers |
|------|-----------|----------------|--------|-------------------------|
| **Who is talking, how visible the machinery is** | the head itself | — | see above | Do they want to see the structure (Navigator) or only feel it (Advisor)? |
| **Scope** | `nexus_hash=` | Explorer (required), Advisor (optional) | a nexus hash | One exploration, pinned in code (other explorations are refused and reduced to a count), or the whole Case? |
| **When structure is built** | `build=` | Advisor | `ON_ELECTION` (default) · `ON_CONSENT` · `NEVER` | May the model build mid-turn on its own election? Only on the person's word, between turns? Never? |
| **Whether this seat may write** | `records=` | Advisor | `True` (default) · `False` | Is this the seat doing the work, or a viewer? `False` is three read tools and no closing seam: a person who decides here gets no record. |
| **The app** | `app=` (an `AppSpec`) — or manual `app_preamble=` / `app_tools=`, never both | all | persona, vocabulary, domain tools | What voice, what vocabulary, what domain lookups? One `AppSpec` per app, passed to every head. |
| **Properties of the person, for the session** | `advanced=`, `persona=`, `thinking=` | `advanced`: Analyst, Explorer, pinned Advisor · `persona`: pinned Advisor · `thinking`: all | booleans; a thinking level or `None` | Do they know the framework (numeric scores, hashes)? Is the pinned head continuing a client's persona rather than the Navigator's register? Extended thinking on or off? Pass the same value to every head they see. |
| **Who confirms decisions** | `principal=` | Advisor | `"human"`, `"agent:<name>"`; default attests nobody | Whose confirmation does a recorded decision carry? Never defaulted to a person. |

Two more parameters exist and are not axes: `messages=` is resumption on every head
(hand the previous head's `messages` to the next one), and `include_decision=` on
`Consultant` drops the convergence ceremony for conversations that are not
decision-shaped. `dialectical_context=` on the Advisor seeds the first turn's graph
render and is a bench convenience; a host can ignore it.

Rules that hold across the axes:

- **`advanced` and `persona` exclude each other** (a persona has nothing to unlock), and
  each RAISES where it cannot apply rather than being ignored: a silently dropped flag is
  the defect the parameters exist to fix.
- **`app=` and the manual layer exclude each other.** Mixing raises.
- **`ON_CONSENT` + `records=False` raises**: both consent triggers (the note and the
  confirmed decision) are writes, so the combination would be `NEVER` under another name.
- **Everything is enforced by toolset and by the closing seam, never by prompt.** The
  prompt is told which surface it is on so the model does not spend turns reaching for what
  it lacks; the code is what makes reaching fail.

## The Advisor's six configurations

`build=` × `records=`, with the one refused cell:

| | `records=True` (the seat doing the work) | `records=False` (a viewer) |
|---|---|---|
| **`ON_ELECTION`** | **The Advisor as shipped.** Builds mid-turn whenever the model elects to; the closing seam weaves what was left unwoven, off the turn, and grounds the record on it. | A head that builds what the model elects and keeps no ledger. Coherent; rarely what you want. |
| **`ON_CONSENT`** | **The consulting room that grows.** No build tool on the turn, so a reply is one graph read plus the model. "Write that down" (`note`) and a confirmed decision are planted and woven after the reply. In an exploration, a note joins it; outside any, a note is kept as a tension and only a closing creates an exploration. | *raises* |
| **`NEVER`** | **The sealed Advisor.** Reads, records decisions grounded on the pathways that exist, retracts on request, scores a pathway on request. Nothing built, on or off the turn. The bench's `A2c`. | **The reading seat.** Three read tools. Nothing recorded, and the host must tell the person so. |

All six compose with `nexus_hash=` (pinned: the build tools are also withheld without
`records`, since pinned they would write into someone else's deliverable) and with
`persona=True` on the pin.

## Recipes: from app idea to construction

| You want to build | Construction | What the bench says |
|-------------------|--------------|---------------------|
| **Advise and forget** — a widget, a bot, a "talk it through once" feature; a demo; the funnel into the products below | `Consultant(app_preamble=COUNSELOR_PERSONA)`; keep `messages` for the session, drop them after | this prompt IS the `A1` arm: the graph-backed head is ahead in session, unresolved, and only with thinking on |
| **The eye-opener** — watch the wheel being built | `Analyst(app=)` → `Explorer(nexus_hash=, app=)` → `Advisor(nexus_hash=, messages=, app=)`, same `messages` across heads; `advanced=True` for someone who reads scores | tool contracts and skills; never benched as counsel |
| **The companion** — coaching, a decision journal, a founder's sounding board; it comes back | `Advisor(app=, principal="human")`; when it has a nexus to dive into, `Advisor(nexus_hash=, app=, persona=True)` | the resolved win: the return against no memory (`ladder-return`); the first session loses to a static dump of what it builds |
| **The consulting room over a headless build** — transcripts, strategy docs, interview notes analysed by a pipeline, then consulted by people | `AnalysisPipeline` → `CreateNexus` → `ExplorationPipeline` (or `run_exploration_detailed`) with no chat; then `Advisor(build=NEVER, principal="human")`, or `build=ON_CONSENT` so people can add to it by saying so | the best counsel measured on both models; a resolved win over the static dump on Sonnet 5, replication needed; `ON_CONSENT` unbenched |
| **The shared case** — one graph, several seats | the mediator on the Navigator; each party on `Advisor(nexus_hash=, app=, persona=True)`; reviewers on `Advisor(build=NEVER, records=False)`; one seat that may grow it on `ON_CONSENT` | unbenched as a multi-seat product; the pin's guards are tested |
| **The upgrade** — a Consultant session becomes a Case, and a new conversation with an Advisor picks up where it left off | the host creates the Case, then inside `scope(sid)`: `await migrate_consultation(consultant.messages, principal="human")` (`agents/advisor/migration.py`) fills the graph — tensions from the PERSON's turns only, woven; every exchange replayed through the closing seam so a decision settled in prose is recorded with grounds — and returns a report; then `Advisor(app=, principal=)` as usual, a NEW conversation over a graph that already holds the case | unbenched; the pieces it composes are the measured ones (the seam, the weave) |
| **Wisdom mining with no chat** — a corpus in, a graph out, for a dashboard or another agent | the headless builder alone; `DialecticalContext` renders it for whatever reads it | the pipeline's own quality figures (extraction faithfulness per model) |

Numbers behind the last column come from `tests/e2e/status.py`, never from this page.

### The upgrade, step by step

The funnel: a person talks to the `Consultant` once, likes it, and upgrades. Their
conversation becomes a Case, and a new conversation with an Advisor reads as picking up
where they left off, because the memory is already in the graph. Three steps, two of them
the host's own.

```python
from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.advisor.migration import migrate_consultation
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope

# 1. The one-off session: no Case, no database, nothing kept but `messages`.
consultant = Consultant(app=spec)
reply = await consultant.chat("I have a problem with my wife...")
...                                              # the session runs its course
saved = consultant.messages                      # what the person brings to the upgrade

# 2. The upgrade: the host creates the Case (the framework never does), then fills its graph.
case = Case()
case.commit()
with scope(case.sid):
    report = await migrate_consultation(saved, principal="human")
    # report.turns / .perspectives / .pathways / .decisions_recorded / .decisions_failed

# 3. A NEW conversation on the Case, constructed as always. Nothing is resumed;
#    the graph is the memory.
with scope(case.sid):
    advisor = Advisor(app=spec, principal="human")
    reply = await advisor.chat("So, where were we?")
    ...
    await advisor.wait_for_deferred_work()       # the host obligation, as on every turn-based head
```

What `migrate_consultation` does with the saved messages, in order:

1. **Plants tensions from the person's turns only.** The model's replies are counsel, not
   statements of the situation, so they are never material; mining them would plant the
   counselor's framings as the person's positions. The joined turns are also kept as an
   Input, so the Advisor can read the person's own words back in full.
2. **Weaves what it planted**, synchronously and within the usual bounds.
3. **Replays every exchange through the closing seam**, in order. A decision the person
   confirmed in the Consultant session is recorded under `principal` with the grounds a live
   closing gets; a later "yes, that" is filed as a re-affirmation, not a second record.
4. **Drains** the off-turn work those closings started, and returns the report.

What to know before shipping it:

- **Cost.** One ingest plus one classifier call per exchange. A twenty-turn session is a
  noticeable wait, so run it behind an "upgrading…" screen, not on the first reply.
- **Nothing is written into any conversation.** The Consultant's history stays the
  person's; the Advisor's starts empty. If the product wants the new conversation to open
  with "here is what I kept", the host asks that as the first turn, and the Advisor answers
  from its graph.
- **Unbenched.** The seam and the weave it composes are the measured pieces; the
  composition is not. Read the first migrated graphs by hand, especially whether the
  recorded decisions are the ones the person meant.
- **The old sealed Advisor is not this.** `Advisor(build=NEVER)` over a migrated Case is a
  fine consulting room, but the graph will not grow from the new conversation; use
  `ON_ELECTION` (grows on the model's election) or `ON_CONSENT` (grows on "write that
  down") for a case that is meant to keep growing.

## Drawing it: the view schema

`graph/views.py` is the view side of the graph — typed frozen dataclasses with
`to_dict()`, for a widget in a chat or a side pane. `rendering.py` next door renders prose
for a prompt; these two have different rules and are deliberately separate modules.

```python
# The head does it: pin → that exploration, else the whole Case; hides_terminology applied.
view = await advisor.exploration_view()
view = await consultant.exploration_view(focus="a perspective for the thesis you named")  # no graph: a turn on its own conversation

# Or the module functions, inside the scope, for a host composing its own page:
with scope(case.sid):
    view = exploration_view()              # every active perspective in the Case, nexus_hash None
    view = exploration_view(nexus)         # one exploration's, numbered as the prompts number it
    view = perspective_view(perspective)   # one perspective
    view = wheel_view(wheel)               # segments + spiral + synthesis
    if advisor.hides_terminology:             # the SAME flag reply_hygiene reads
        view = view.without_terminology()
return view.to_dict()                      # str / float / bool / None / list / dict
```

Three things to know:

- **Absence is `None`, in every field.** An unscored aspect, an unaudited wheel, an
  unvalidated tetrad: `None`, never `0.0`. In particular a wheel's `causality` is `None`
  when nobody estimated it — the `-1.0` in `explorer._causality_probability` is a ranking
  sentinel and never reaches a view.
- **Terminology is the optional half.** Structure (the six poles, the `intent`, the
  segments, the spiral) is always there; positions (`T+`), stored aliases (`T1+`), hashes
  and every number come off with `without_terminology()`. The host does not decide this:
  `Advisor.hides_terminology` is the flag, and it is the same one that strips `[[hash]]`
  from the reply text. A widget that disagreed with the filter would put `T+` on screen
  inside a conversation whose prose is scrubbed of it.
- **It is priced for a user-triggered widget, not a per-turn dump.** A tetrad is ~20
  relationship reads; `RelationshipManager.prefetch` first when drawing many.

**The graphless head draws the same view, as a turn.** A `Consultant` has no graph to
read, so `await consultant.exploration_view(focus=None)` is a structured turn on its OWN
conversation — same system prompt, full history, both sides — that renders what the
conversation has established and, where `focus` asks for structure not yet worked out ("a
perspective for the thesis you named", "the antitheses we discussed"), builds it by the
method first (`concerns/view_sketch.py`). It thinks at the session's level (json
mode, the one structured shape that can), and what it drew stays in `messages` as the
consultant's own words so the next turn can be asked about a corner. Same `ExplorationView`
— texts and the reading (`intent`, composed as the graph composes it) only, a corner the ask
did not reach left `null`. Terminology-free by construction (no hash, alias or score exists;
`without_terminology()` is a no-op on it) and unchecked by construction (no HS gate, no
validation, no dedup, nothing kept): the view BEFORE the upgrade, not a lighter version
of the checked one. It raises on a provider failure rather than returning an empty view,
so "nothing drawn yet" and "the drawing failed" stay distinguishable to the button that asked.

Not built: any tool that lets the model open a view itself. The trigger is the host's
(a button calling `exploration_view()` inside the scope, or `consultant.exploration_view()`), and that
is a decision, not an omission — an LLM-elected `show` tool would be unreliable anyway
(measured election rates: `anchor` 6/6, `explore` 2/6, `deepen` 0/6).

## What the host owns, on every surface with memory

- **The Case.** Nothing in `src/` creates one. Open `scope(sid)` around every turn.
- **Who may open which Case.** `records=False` is a permission the framework enforces
  inside a Case; which Cases a seat can see at all is the host's.
- **The principal.** Pass `"human"` when a person is on the other end, `"agent:<name>"`
  when an agent is. The default attests nobody.
- **The drain.** `await advisor.wait_for_deferred_work()` before the process or the scope
  goes away: the closing weave and the note run off the turn, on `ON_ELECTION` and
  `ON_CONSENT` alike.
- **The close.** `async with aclosing(advisor.chat_stream(msg))` on any mid-stream exit.
- **The person's flags.** `advanced`, `persona`, `thinking`: one value per session, the
  same on every head they see.

## What could be simpler (not done)

`advanced=` and `persona=` are two mutually exclusive booleans that both describe the
pinned Advisor's register; one enum would say the same with no illegal state. And the
Advisor's constructor carries thirteen parameters, three of which (`app_preamble`,
`app_tools`, `dialectical_context`) exist for the bench and for manual control most hosts
never need. Both are renames with a sweep behind them, so they wait for a decision rather
than happening as a side effect of this page.
