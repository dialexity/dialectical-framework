# What you can build: the heads, the axes, the combinations

The one-page map. `docs/agents.md` has the detail behind every row; this page
exists so a developer can see the whole space at once and pick a construction
without reading it.

## The four heads

Every head has the same conversational surface (`chat`, `chat_stream`,
`messages` for resume). They differ in what they need and what they leave behind.

| Head | Construct | Needs a Case / `scope(sid)` | What the person sees | Builds the graph | Keeps a record |
|------|-----------|-----------------------------|----------------------|------------------|----------------|
| **MethodAdvisor** | `MethodAdvisor(app_preamble=)` | **no** — no database at all | a conversation | never | never: a confirmed decision is restated in the reply, and that is the only record |
| **Analyst** | `Analyst(app=)` | yes | the structure, in the open (inputs → tensions → a nexus) | yes, every tool call visible | no decision ledger |
| **Explorer** | `Explorer(nexus_hash=, app=)` | yes | the structure, in the open (one nexus → pathways → synthesis) | yes, inside the pin | no decision ledger |
| **Advisor** | `Advisor(app=, build=, records=, nexus_hash=)` | yes | a conversation; the framework runs silently | per `build=` | per `records=` |

Analyst + Explorer (+ the Advisor's advisory register over the same `messages`) is the
**Navigator**: the person watches the wheel being built. Everything else is the Advisor
in one configuration or another.

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
`MethodAdvisor` drops the convergence ceremony for conversations that are not
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
| **`NEVER`** | **The Consultant.** Reads, records decisions grounded on the pathways that exist, retracts on request, scores a pathway on request. Nothing built, on or off the turn. The bench's `A2c`. | **The reading seat.** Three read tools. Nothing recorded, and the host must tell the person so. |

All six compose with `nexus_hash=` (pinned: the build tools are also withheld without
`records`, since pinned they would write into someone else's deliverable) and with
`persona=True` on the pin.

## Recipes: from app idea to construction

| You want to build | Construction | What the bench says |
|-------------------|--------------|---------------------|
| **Advise and forget** — a widget, a bot, a "talk it through once" feature; a demo; the funnel into the products below | `MethodAdvisor(app_preamble=COUNSELOR_PERSONA)`; keep `messages` for the session, drop them after | this prompt IS the `A1` arm: the graph-backed head is ahead in session, unresolved, and only with thinking on |
| **The eye-opener** — watch the wheel being built | `Analyst(app=)` → `Explorer(nexus_hash=, app=)` → `Advisor(nexus_hash=, messages=, app=)`, same `messages` across heads; `advanced=True` for someone who reads scores | tool contracts and skills; never benched as counsel |
| **The companion** — coaching, a decision journal, a founder's sounding board; it comes back | `Advisor(app=, principal="human")`; when it has a nexus to dive into, `Advisor(nexus_hash=, app=, persona=True)` | the resolved win: the return against no memory (`ladder-return`); the first session loses to a static dump of what it builds |
| **The consulting room over a headless build** — transcripts, strategy docs, interview notes analysed by a pipeline, then consulted by people | `AnalysisPipeline` → `CreateNexus` → `ExplorationPipeline` (or `run_exploration_detailed`) with no chat; then `Advisor(build=NEVER, principal="human")`, or `build=ON_CONSENT` so people can add to it by saying so | the best counsel measured on both models; a resolved win over the static dump on Sonnet 5, replication needed; `ON_CONSENT` unbenched |
| **The shared case** — one graph, several seats | the mediator on the Navigator; each party on `Advisor(nexus_hash=, app=, persona=True)`; reviewers on `Advisor(build=NEVER, records=False)`; one seat that may grow it on `ON_CONSENT` | unbenched as a multi-seat product; the pin's guards are tested |
| **Wisdom mining with no chat** — a corpus in, a graph out, for a dashboard or another agent | the headless builder alone; `DialecticalContext` renders it for whatever reads it | the pipeline's own quality figures (extraction faithfulness per model) |

Numbers behind the last column come from `tests/e2e/status.py`, never from this page.

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
