# Agents: Analyst, Explorer, Advisor

> The one-page map of heads, axes and combinations is [`docs/surfaces.md`](surfaces.md);
> this document is the detail behind each row.

The three conversational agents are the primary building blocks for any application
on top of the dialectical framework. Each is a thin LLM orchestrator that owns a set
of tools and a system prompt; the dialectical reasoning ("wisdom") lives in the
orchestrator + concern layer, while the **app preamble** supplies only user-facing
flavor (persona, vocabulary). Swap the preamble and the same reasoning engine serves
a different product.

They are three heads over one graph, split by **when you know what** — and four
categories of app, split by who is talking (see [Choosing what to build](#choosing-what-to-build)):

| Agent | Metaphor | Scope | Turns... | Framework visible? |
|-------|----------|-------|----------|--------------------|
| **Analyst** | workbench | Case | raw material → structured tensions, up to grouping | yes (structure-forward) |
| **Explorer** | lab bench | one Nexus | one group of tensions → causal pathways + synthesis | yes (structure-forward) |
| **Advisor** | conversation | Case | anything → counsel, framework runs silent | no (hidden) |
| **Advisor (sealed)** | conversation | Case or one Nexus | a built graph → counsel and recorded decisions, nothing built | no (hidden) |

Analyst + Explorer together are the **Navigator** experience (two visible phases).
The Advisor is a **separate app**: internally it does what Analyst + Explorer do, but
exposes none of the machinery — pinned to one exploration for an analyst or mediator
(`Advisor(nexus_hash=, messages=)`), or from scratch for their client (`Advisor(app=)`),
whose sessions end up building a nexus and diving into it (`persona=True` keeps the
persona over the pin). The **sealed Advisor** is the Advisor with the build tools withheld
(`Advisor(build=BuildPolicy.NEVER)`, or `ON_CONSENT` to let the graph grow on the person's
word between turns): a graph something else built — see
[Choosing what to build](#choosing-what-to-build) and the headless builder under it.

All three live in `agents/{analyst,explorer,advisor}/`. See also `docs/graph.md`
(data model) and `docs/scoring.md` (metrics).

---

## Shared shape

Every agent exposes the same conversational surface:

```python
agent.chat(user_message: str) -> str                       # full turn, returns text
agent.chat_stream(user_message: str) -> AsyncGenerator[StreamEvent]
agent.messages -> list                                      # for persistence / resume
```

Stream events: `ThinkingDelta`, `TextDelta`, `ToolStart`, `ToolResult` (carries the
parsed `ExecutionReport` for graph-mutating tools; `report` is `None` for read-only
tools like `query_graph`), `ResponseComplete`.

**Render the `TextDelta`s — do not wait for `ResponseComplete` to show text.** On the
ordinary turn `ResponseComplete.streamed` is `True`, and `message` is then byte-for-byte
the deltas already yielded (the reply is *built* from them, not merely expected to
match). A host that waits for the event pays the whole turn — ~18s measured — for text
that started arriving in about a second. `streamed=False` means the deltas are not the
reply and `message` must be rendered: either nothing streamed (the tool-free path makes
one formatted call and cannot stream) or the streamed text was unusable and a separate
structured call produced this one. Text yielded *before* a `ToolStart` is the model
saying what it is about to do and is never part of `message` — fine to leave on screen
as progress, never persisted as counsel.

**`ResponseComplete` arrives last, after the turn's closing work.** Breaking on it is
therefore free and always safe:

```python
async for event in advisor.chat_stream(msg):
    ...
    if isinstance(event, ResponseComplete):
        break            # safe: everything this turn owed was done before you got it
```

That ordering is why it is safe. The Advisor's turn does not end at the last token —
it still has to write the decision record the model confirmed but did not save
(`_repair_unrecorded_decision`), schedule the pathway weave and record the turn's
seconds. All of that runs *before* the final event goes out, so a host that stops at
`ResponseComplete` cannot skip it. You wait no longer than you did before: the work
sat between the last token and the end of the loop either way.

**A host that stops iterating MID-STREAM must CLOSE the generator.** `chat_stream` is
an async generator, and an async generator's cleanup runs when it is closed — not when
the consumer walks away. So a `break` before the reply exists (a real disconnect, a
cancelled request) leaves the frame suspended, and two things wait on the close that
never came: the turn's recorded wall clock (`last_submit_seconds`, which a *newer* turn
may have taken ownership of by the time the garbage collector arrives, at which point
this turn's seconds are lost) and the provider's open HTTP response, which stays
suspended inside the streaming decoder's `async with`. The framework closes every
generator it owns; the outermost one is the host's, and nothing inside can reach up to
it.

```python
async with aclosing(advisor.chat_stream(msg)) as events:   # contextlib.aclosing
    async for event in events:
        if client_gone:
            break        # safe: the `async with` closes on the way out
```

Consuming to exhaustion needs nothing extra, and neither does an exception — both
unwind the chain on their own. An ASGI server also closes the generator behind an SSE
response when the client disconnects. The one shape that leaks is a bare `async for`
that `break`s part-way through a turn.

`chat()` returns the same durable reply with no streaming at all, so a host on `chat()`
gets no first-token benefit; that is a host choice, not a framework limit.

Construction is uniform except for what each is bound to:

```python
Analyst(app=None, app_preamble=None, messages=None, app_tools=None, advanced=False)              # Case-scoped (ambient)
Explorer(nexus_hash, app=None, app_preamble=None, messages=None, app_tools=None, advanced=False) # bound to one Nexus
Advisor(app=None, app_preamble=None, dialectical_context=None, messages=None,
        nexus_hash=None, app_tools=None, principal=UNATTESTED_PRINCIPAL, advanced=False,
        build=BuildPolicy.ON_ELECTION, records=True, thinking=FROM_SETTINGS, persona=False)
```

**`app` (an `AppSpec`, `agents/app_spec.py`) is the recommended interface**: the app
declares its custom pieces once — `voicing` (Navigator-side domain flavor),
`advisor_persona` (standalone-Advisor identity), `tool_guide` (shared tool usage rules),
`tools` — and every head composes the right preamble itself: Analyst/Explorer get
`NAVIGATOR_APP + voicing + tool_guide`, the advisory toggle gets
`NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER + voicing + tool_guide`, the standalone Advisor gets
`advisor_persona + tool_guide`. The framework owns the composition lore; apps never
touch the base preambles. One AppSpec constant, passed to every constructor — the
continuity rule below is then automatic.

**`advanced=True` is the expert register**, for a user who knows the framework: the
Navigator base becomes `NAVIGATOR_APP_ADVANCED_TOGGLE` (framework vocabulary, short
hashes, numeric scores, structural tetrad presentation) and the advisory toggle becomes
`NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER_ADVANCED` — so the level **carries
across the toggle** instead of resetting mid-conversation. It is a property of the
person, not of the app, so it is a per-session constructor flag rather than an AppSpec
field: one AppSpec serves both registers, and a host with a user-level toggle passes the
same value to every head that user is looking at. It is refused, loudly, wherever it
could not be honoured: on the standalone Advisor (that head hides the machinery, so
there is nothing to unlock) and alongside `app_preamble=` (you own the preamble there —
compose `AppSpec.navigator_preamble(advanced=True)` /
`advisor_preamble(scoped=True, advanced=True)` yourself, **and pass `app_tools=` with
it**). Ignoring the flag is the defect it was added to fix: until 2026-09-16 it existed
on `AppSpec` and nothing ever passed it, so no app using `app=` could reach it at all.

`app_preamble`/`app_tools` are the manual low-level layer (full preamble control; see
`agents/apps.py`): `app_preamble` replaces the AppSpec-derived composition entirely,
`app_tools` are `@llm.tool` functions appended to the built-in set
(`agents/toolsets.py`; shadowing a built-in name raises). Mixing `app=` with either
manual param raises. `messages` resumes a saved conversation. The **host application** owns five things the framework does not:

1. **DI setup** — `DialecticalReasoning.setup(Settings.from_env())` once at startup.
2. **Scope** — wrap every `chat()` in `with scope(sid):` (all graph writes are `sid`-scoped).
   Enforced: an unscoped `chat()`/`chat_stream()` raises `MissingScopeError` immediately —
   running unscoped would otherwise fail silently (nodes save with `sid=None`, invisible to
   every listing, and commit dedup can alias onto another Case's nodes).
   **One writer per sid** — a hard contract: never run two agent conversations
   that write the same `sid` concurrently (headless drivers fanning out
   included). The graph client is a singleton with one cached connection,
   `commit()` dedup is check-then-act across autocommitted statements, and
   directed `connect()` duplicates edges on repeated calls — concurrent
   same-sid writers produce duplicate nodes/edges and half-built containers.
   Different sids are fine. Parallelism *inside* one turn is already handled
   (LLM work gathers, graph writes stay sequential).

   The framework enforces its OWN half of this — the Advisor's off-turn weave —
   in two layers: single flight per sid inside a process (a registry keyed by
   `sid`), and a **DB-held weave lease per sid across processes**
   (`CaseRepository.acquire_weave_lease`: compare-and-set in one statement, a
   `WeaveLease` row per sid, renewed per round, released when done, expiring
   600s after the last renewal if the holder dies). A turn opening on ANY
   process waits out a lease another process holds before it reads or writes.
   What it does not enforce is the host's half: two of YOUR turns on one `sid`
   at the same time. **Multi-tenant servers** (several uvicorn workers,
   replicas behind a load balancer): the lease makes cross-process weaves
   safe; routing every turn of a `sid` to one process (sticky by `sid`) is
   still recommended, because a turn behind another process's weave cannot
   ask it to yield and waits up to a full round. One DI container per process
   — the container, the event buses and the wiring are process singletons, and
   a second `setup()` silently re-points every tenant. **A per-person setting
   (model, word limits, thinking level, floors) is a scope, not a container:**
   wrap the request in `with using_settings(base.model_copy(update={...})):`
   (`dialectical_framework.settings_context`), beside `scope(sid)`. Concurrent
   requests each see their own; tasks the framework starts inside (best-of-N,
   the off-turn weave) inherit it. `container.settings.override(...)` raises —
   it would put every request in flight on one object. The graph connection,
   the provider's connect timeout and the effect log are read once from the
   base and cannot be scoped (`Settings` docstring).
3. **Message persistence** — save/load `agent.messages` per conversation thread. Carrying
   the list forward inside one process needs nothing: hand it to the next
   `Advisor(messages=saved)` and you are done.

   **Writing it to a database needs a projection, and the obvious projection is the
   lossy one.** These are Mirascope message dataclasses — `SystemMessage`,
   `UserMessage`, `AssistantMessage` — not Pydantic models: no `model_dump`, no
   `model_validate`, and Mirascope ships no dump/load helper. What they do have is a
   shape that serializes cleanly by hand. Every message and every content part is a
   dataclass with a `type` (or `role`) discriminator and JSON-able fields, including
   multimodal ones, whose bytes live as base64 `str` inside a `source` object. So:

   ```python
   import dataclasses, json
   json.dumps([dataclasses.asdict(m) for m in advisor.messages])   # lossless
   ```

   Rebuild by dispatching on `role`, then on each part's `type` (`text`, `tool_call`,
   `thought`, `tool_output`, `image`, `audio`, `document`). **A text-only history needs
   no rebuild**: every head hydrates `role` + string (or text parts) dicts on load
   (`ConversationFacilitator.load_messages`); a dict carrying tool calls, tool outputs
   or media raises `TypeError` at construction — rebuild those yourself — rather than
   failing inside the next provider call (`tests/test_consultant.py`).

   **Keep `raw_message`.** It looks like provenance and is not: it holds the provider's
   own payload, and Mirascope passes it back **verbatim** as input on the next call —
   the framework has to reach into it and strip output-only fields (`caller` on
   `tool_use` blocks) or the following request 400s (`_strip_caller_from_messages`).
   A role-plus-content projection therefore does more than lose detail: the provider
   sees a conversation in which the assistant referred to tool work it never did.

   The system message is the one thing you may drop. It sits at `messages[0]` and the
   framework rewrites it every turn from the live graph dump, so a saved copy is
   replaced rather than honoured.
4. **Phase handoff & live updates** — see [Handoffs](#handoffs-the-ux-glue) and
   [Events](graph.md#events) for the `GraphEventBus`: where to get it
   (`container.event_bus()`), the `await bus.connect()` that a host must not skip
   (publishing is a silent no-op without it), and the separate `f"{sid}:progress"`
   channel for work-in-flight signals.
5. **Draining deferred work** — `await advisor.wait_for_deferred_work()` before the
   conversation's scope goes away (once, after the last turn). The Advisor starts one
   thing the turn does not wait for: when a decision closes over tensions nothing has
   arranged into a pathway, it weaves them **off the turn** and grounds the record on
   the result afterwards. Building that inline was measured at 127.7s and 387.7s on
   two turns of `timing-check-building`, both landing on the turn immediately before
   the closing; leaving it undone cost quality (judged mean −0.25 with a woven graph
   at closing against −0.69 without, 36 scores each). So it happens, just not while
   the person waits.

   Only the host knows when there is no next turn, which is what makes this the
   host's call and not the framework's — the same shape as the `aclosing` obligation
   above. **Skipping it loses nothing durable**: every deferred write is fail-soft
   and idempotent, the decision keeps the grounds it was recorded with, and a
   `note` the person asked to keep is a committed `Note` node from the moment
   the tool answered — the next turn on any process plants it (the in-memory
   queue is only the trigger; the graph is the queue of record). What a skipped
   drain does cost is the pathway of a decision closed on that last turn, and a
   container caught mid-commit (`saved_at` set, no hash — invisible to every
   listing, reaped by `scripts/cleanup_stale_nodes.py`). Safe to call any
   number of times, including when nothing was deferred.

   **A shared server drains the PROCESS, not a conversation:**
   `await drain_deferred_work(timeout=...)` (module-level in
   `agents/advisor/advisor.py`) awaits every sid's off-turn work on this loop —
   the call for an ASGI lifespan shutdown hook, which has no scope and no
   instance. Same contract: bounded by `timeout`, never cancels. For a
   request-scoped worker (one process per request, killed after the response),
   stream the reply and then `await advisor.wait_for_deferred_work()` before the
   handler returns — the person already has the reply on screen.
   `deferred_work_in_flight(sid)` tells a handler whether this process is
   weaving a sid right now, so it can answer with a heartbeat or a 202 instead
   of blocking a request behind `chat()`'s settle wait.

   **It waits for the conversation, not for the object.** Deferred work is tracked
   per `sid`, so `wait_for_deferred_work()` drains a weave started by an *earlier*
   Advisor on the same conversation — which is what makes the stateless shape
   (`Advisor(messages=saved_messages)`, one instance per request) safe. Two
   Advisors on one `sid` also share the single-flight guard: the second cannot
   start a concurrent weave, and a decision it closes mid-weave is drained by the
   running one rather than dropped. Different `sid`s are independent.

   `wait_for_deferred_work(timeout=30)` bounds the wait for a shutdown path that
   must not hang on a slow provider. It returns `True` when nothing is left in
   flight and `False` if the timeout passed first — and it does **not** cancel the
   work: whether a half-woven graph beats an unfinished one is the host's call, so
   the weave keeps running and the caller decides (keep waiting, carry on, or drop
   the loop, which cancels it).

   The *next turn* needs no help: `chat()`/`chat_stream()` wait for any in-flight
   weave before they start, because of the one-writer-per-sid contract in (2). That
   wait is deliberately unbounded — it protects the graph, and a timeout there
   would trade duplicate nodes for latency. It is normally zero anyway — the
   person's think-time absorbs it — and when it is not, it is recorded as
   `TurnTiming.deferred_wait_s` rather than hidden inside `generation_s`.

```python
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.settings import Settings
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.agents.analyst.analyst import Analyst

DialecticalReasoning.setup(Settings.from_env())   # once

case = Case(); case.commit()                       # a Case owns the sid
with scope(case.sid):
    analyst = Analyst(app_preamble=NAVIGATOR_APP)
    reply = await analyst.chat("We're torn between preplanning courses and generating them on demand.")
```

**All five obligations, running:** [`examples/advisor_chat.py`](../examples/advisor_chat.py)
is a console chat with each one marked in place — a chat loop being the smallest program
in which all five are load-bearing. `tests/test_examples_advisor_chat.py` asserts that it
still honours them, so it is a checked reference rather than a snapshot of one that used
to work.

---

## Analyst — content → nexus

**Owns:** everything up to and including nexus creation. Turns inputs into statements,
polarities, and full perspectives (tetrads), then groups them into a Nexus as the
handoff. It is a **thin dispatcher over deep concern-level prompts** — the SIMPLE/COMPLEX
classification, thesis quality, HS gates all live in the concerns it calls, not in its
own prompt. It must **not** do advisory discussion; its one genuine dialectical judgment
is **nexus grouping**.

**Construct:** `Analyst(app_preamble=None, messages=None)` — Case-scoped via ambient `scope(sid)`.

**Tools (20):**

| Group | Tools | Purpose |
|-------|-------|---------|
| Capture | `add_input`, `digest_input`, `read_input`, `read_digest` | ingest & summarize source material |
| Extract | `analyze` (full pipeline), `surface_theses`, `anchor_theses`, `introduce_polarity`, `place_statement` | material → theses / polarities |
| Develop | `find_polarities`, `expand_polarities` | thesis → oppositions → full tetrad (T+/T-/A+/A-) |
| Curate | `edit_perspective`, `discard`, `create_dx_input` | fix / remove / feed exploration insight back as input |
| Handoff | `create_nexus`, `expand_nexus` | group perspectives → the exit door to the Explorer |
| Read | `present_analysis`, `inspect_node`, `query_graph`, `get_schema` | orient / detail / raw Cypher |

**Tool selection** (the prompt disambiguates by input shape):
- explicit "X vs Y" → `introduce_polarity`; a single named concept → `anchor_theses`;
  substantial pasted text → `analyze`; "extract from what I gave you" → `surface_theses`.

**Nexus grouping (the judgment it owns):** prefer perspectives from **different
polarities** (genuine synthesis with opponents). Same-polarity grouping is valid when
it fits the intent or the user asks — it yields "angle shifts" (reframing within one
opposition) rather than cross-opposition synthesis. Never refuse an explicit
same-polarity request.

**The handoff moment:** `create_nexus` returns `artifacts["nexus_hash"]`. That hash is
the token the host app watches for to launch the Explorer.

**UX to build around it:**
- A **statements / perspectives canvas**: theses with their tetrads; HS / area /
  rectangularity shown *as meaning* ("strong opposition", "weak tension"), not numbers.
- An **input tray** (add text / URL, view digests).
- Inline **edit / discard** on any perspective.
- A **"Group into exploration"** action → `create_nexus` → surface **"Open in Explorer"**
  when the report returns a `nexus_hash`.
- **No pathways / synthesis UI here** — deliberately the Explorer's job.

---

## Explorer — inside one nexus

**Owns:** everything after the nexus. A **sandboxed mini-advisor** that consults within
one Nexus: builds causal arrangements (Cycles + Wheels), generates Action-Reflection
transformations, and synthesizes S+/S-. It is a **bounded consumer** — it cannot capture
new material or build new perspectives. When the user wants new analysis, it routes them
back to the Analyst thread.

**Construct:** `Explorer(nexus_hash, app_preamble=None, messages=None, app_tools=None)`
— `nexus_hash` is **required** and hard-bound at construction; a missing nexus raises
immediately. `app_tools` works as on the Advisor (see below).

**Tools (13):**

| Group | Tools | Purpose |
|-------|-------|---------|
| Build | `build_wheels` | perspectives → Cycles + Wheels, scored by causal plausibility |
| Deepen | `explore_transformations` | a chosen Wheel → Ac+/Re+ pathways (6 positions per edge) |
| Synthesize | `generate_synthesis` | a Wheel with transformations → S+/S- |
| Assess | `audit_feasibility` | named pathways → practical achievability bands + the factors behind them (on demand; 2 calls per pathway) |
| Grow | `expand_nexus` | attach *existing* perspectives to this nexus |
| Round-trip | `create_dx_input` | capture a Transition's insight as a Case Input for the Analyst (see [Handoffs](#handoffs-the-ux-glue)) |
| Read | `present_exploration`, `inspect_node`, `read_input`, `read_digest`, `digest_input`, `query_graph`, `get_schema` | state / detail |

**The boundary (tool-enforced, not just prompt):** the Explorer has **no** `add_input`,
`surface_theses`, `find_polarities`, `expand_polarities`, `anchor_theses`,
`introduce_polarity`. It literally cannot analyze material into tensions —
`create_dx_input` only *captures* an insight; developing it still happens in the
Analyst thread. This is intentional; a regression test (`tests/test_explorer.py`)
locks the `create_nexus` exclusion specifically.

**Reads scores to prioritize** (its prompt interprets the shared taxonomy ladders):
- **Causality** `P` (raw plausibility) vs `%` (normalized across siblings) — lead with
  the highest `%`; competing arrangements explain the same tensions.
- **Transformation** `insight` (reflex → transcendence, 0.0-1.0, a *characterization* of
  depth) and `proactiveness` (Ac+ in 0.5-1.0, Re+ in 0.0-0.4). Match depth to readiness.
- `feasibility` bands; `HS` on Ac+/Re+ = fit to taxonomy apex (distinct from HS on an antithesis).
- **Synthesis:** `S+` = emergence (1+1>2); `S-` = the trap (domination / oscillation /
  either-or) — name it when the user heads there.

**UX to build around it:**
- Launched **from** the Analyst handoff, scoped to one nexus
  (e.g. `/cases/{sid}/exploration/{nexusHash}`).
- A **three-stage progressive flow** matching the prompt's phases — don't auto-generate
  everything:
  1. **Navigation** — show Wheels with causality `%` (lead with highest); user picks one.
  2. **Insight** — on a chosen Wheel, `explore_transformations` → present Ac+ ("what to do")
     / Re+ ("what to reflect on").
  3. **Synthesis** — `generate_synthesis` → S+ (emergence) vs S- (trap).
- A **"want to add a new tension?" → bounce to Analyst** affordance (the critical
  cross-phase nav, since the Explorer can't analyze).
- `expand_nexus` needs a picker of *existing* perspectives, not a creation flow.

---

## Advisor — silent framework, pure conversation

**Owns:** everything (analyze + explore + counsel), but exposes none of it. A
pure-conversation agent where the framework runs behind the scenes and the user
experiences only progressively wiser responses. Its system prompt is a domain-neutral
dialectical engine; the **persona** comes entirely from the app preamble (counselor,
strategist, coach, mediator, sparring partner, decision partner — see `agents/apps.py`;
`DECISION_PARTNER_PERSONA` is the convergence-forward persona for decision-making apps:
it drives toward the choice and keeps the recorded decision, while the convergence
mechanics stay in the engine's Decision Readiness section).

**Construct:** `Advisor(app_preamble=None, dialectical_context=None, messages=None,
nexus_hash=None, app_tools=None, app=None, principal=UNATTESTED_PRINCIPAL, advanced=False,
build=BuildPolicy.ON_ELECTION, records=True, thinking=FROM_SETTINGS, persona=False)`. `thinking` is the person's extended-thinking
toggle for this session, the same per-session shape as `advanced` (pass one value to every head
they are looking at): not given defers to the deployment's `DIALEXITY_CONVERSATION_THINKING_LEVEL`,
`None` is off, a level is on. It reaches only the conversational call, never a concern — concerns
do not think; what they get instead is their own MODEL: `DIALEXITY_REASONING_MODEL` runs every
structured call when set (unset = the conversation model), which is where quality was measured to
live (extraction: 34.6% unsupported claims on Haiku 4.5, 7.0% on Sonnet 5, identical prompts).
The deployment default is `medium` since 2026-09-26 (`thinking-check`: with the conversational
round not thinking the framework's counsel sat below the same method as a tool-less prompt
in-session, −0.27 against +0.35 at medium, at ~18s a turn against ~49s; the turn is the price
and the toggle trades it back). On Haiku 4.5 "medium" is ~3x the call with no election gain
(`thinking-off`). `messages` is resumption and nothing else — every head takes it, a host
passes it on every turn, and the Explorer↔Advisor toggle below is built on it (construct the other
class with the same history); it is not a mode. `dialectical_context` is an
optional pre-rendered graph snapshot (from `DialecticalContext().resolve()`) injected into the
system prompt — use it when a rich graph already exists at conversation start. `principal` is
the host's attestation of WHO confirms decisions in this conversation, and it is the one
argument where OMITTING it is not a neutral choice: **pass `"human"` when an actual person is
on the other end, and a delegated driver (agent-to-agent runs) must pass its own identity**
(e.g. `"agent:dataset-driver"`). The default attests NOTHING (`"agent:unattested"`, from
`concerns/record_decision.py`), because a default cannot know whether anyone was in the room —
so a conversation with a real person that never passes `"human"` records decisions whose why
renders as "confirmed by agent:unattested" instead of as the person's own "Why". That is the
deliberately visible failure: the wording is intact and passing the argument fixes it, whereas
a fabricated human attestation is unfixable after the fact. Closed over by the tool in code;
the LLM cannot set it. `nexus_hash` pins the
Advisor to one exploration. By default that is the **advisory mode of an Explorer session**
(the Navigator's advisory register: vocabulary disclosed, the person addressed as someone who
knows the map; see [Explorer ↔ Advisor](#handoffs-the-ux-glue) below). `persona=True` is the
same pin for someone who is **not** a Navigator user: the app's `advisor_persona` stays the
preamble and the machinery stays hidden, over the same scoped tools and the same scoped
engine. It exists for the collapse a client's conversation makes — started as `Advisor(app=)`,
built an exploration silently, and now pinned to it by the host — which without the flag would
flip mid-history into a register that names the machinery. Per-session like `advanced` (which
it excludes: a persona has nothing to unlock) and `thinking`; ignored without a pin; raises
with no `app=` to take the persona from.
`app_tools` is the app's domain-resource seam: additional `@llm.tool` functions
(chart lookups, methodology references, knowledge-base fetches) appended to the
built-in set. The engine prompt carries no docs for them (their tool-schema docstrings
reach the LLM automatically) — introduce them and their usage rules in the app
preamble, where domain vocabulary lives. Shadowing a built-in tool name raises.

`build=` says WHEN this head builds structure and `records=` WHETHER it may write at all
(`agents/advisor/build_policy.py`) — a different axis from the four app categories in
[Choosing what to build](#choosing-what-to-build): a category says WHO is talking, the policy
says what the head is allowed to do to the graph, and when. What costs a person minutes on a
turn is the four build tools (`ingest`, `anchor`, `explore`, `deepen`), while recording a
confirmed decision is one call of a few seconds and discarding is free — so the question is not
"may it write" but "when may it build".

| `build=` | Tools | Builds on the turn | Builds off the turn | For |
|----------|-------|--------------------|---------------------|-----|
| `ON_ELECTION` (default) | all ten | yes, whenever the model elects to | yes — the closing seam weaves what was left unwoven | the two Advisor categories: from scratch, and on a nexus (the advisory register or a pinned persona) |
| `ON_CONSENT` | `sync`, `inspect_node`, `read_digest`, `record_decision`, `discard`, `audit_feasibility`, **`note`** | **never** — a reply is one graph read plus the model | yes, on the person's word: what they ask to have written down (`note`: `anchor`'s parameters, queued and planted after the reply) and a decision they confirm start the same off-turn task, anchored first if the graph is empty. In an exploration (the pin, or the case's one exploration) a note is woven into it; outside any, a note is the analysis part alone — planted as a tension, not woven — and a closing is what creates the exploration | a consultation whose understanding should keep growing without ever making the person wait for it — the "write that down" surface. Unbenched |
| `NEVER` | the same minus `note` | never | **never** — the closing seam records without starting the weave | **the sealed Advisor**: a conversation over a graph that was built before it and stays as built. Measured (`consultant-latency`, weak tier): median turn 17.6s against the full Advisor's 24.3s and a static dump's 6.3s — faster, not yet fast; see the note below the table |

`records=False` narrows any of them to the three reads (`sync`, `inspect_node`, `read_digest`):
a second reader on someone else's Case, a shared or public view, a support seat. A permission,
not a policy: it composes with `NEVER` (the reading seat) and with `ON_ELECTION` (a head that
builds what the model elects and keeps no ledger), and raises with `ON_CONSENT`, whose two
triggers are both writes. Pinned (`nexus_hash=`), the permission also withholds the build
tools — they would be writes into someone's deliverable.

All of them compose with `nexus_hash=`. Enforced by the TOOLSET and, for the framework's own
initiative, by the closing seam — never by prompt, the same division of labour as the nexus
pin. That is a deliberate choice against a "prefer reading" preamble: tool-election
instructions measurably do not hold (`anchor` fired 6/6, `explore` 2/6, `deepen` 0/6 under
the full prompt), so a prompt-deprioritised policy would be fast on most turns and take a
minute on whichever turn the model anchors anyway. What `records=False` costs, and it must be
said to whoever picks it: a person who states a decision in that conversation gets **no record
of it** (the seam that catches the model not calling `record_decision` is exactly what is
switched off — measured 0/6 at the weak tier). `principal` is accepted and ignored without
`records`; `app_tools` are still merged on every surface, deliberately — the framework cannot
tell a host's chart lookup from a host's write, so the policy governs the framework's tools and
the host owns its own. And the host obligation does not change: `wait_for_deferred_work()`
before the process goes away, on `ON_CONSENT` as on `ON_ELECTION` — a note is planted by the
same task a closing's weave runs on. The sealed Advisor's latency against the full Advisor and against a static dump
is measured by the bench's `A2c` arm (`tests/e2e/README.md`). Its first run says the build
tools were a small part of the gap: tool-free turns are still ~15s against the dump's ~6s over
the same graph. The per-turn graph render (3.2s) has since been removed by a fingerprint-gated
cache. What remains is not the prompt's size (measured: under a second) but **extended
thinking on the tool path**: `conversation_thinking_level`, when set, applies to every tool-enabled call
and never to the structured path the prompt arms answer through, and at `medium` it is ~450
hidden output tokens and ~6s a turn on the weak tier. Unset, the sealed Advisor answers in ~6s
and elects no fewer tools (`tests/e2e/rounds.md`, `probe-consultant-prompt-cost`,
`thinking-off`). Whether thinking earns that in counsel quality is unmeasured. None of this
is the mode's enforcement.

**Tools (10)** — coarse, composed super-tools that hide the machinery:

| Tool | Composes | Purpose |
|------|----------|---------|
| `ingest` | AnalysisPipeline | raw material → perspectives (bulk discovery) |
| `anchor` | IntroducePolarity + ExpandPolarity | plant a specific T/A tension |
| `explore` | CreateNexus + ExplorationPipeline + GenerateSynthesis | group → pathways → synthesis in one shot (budgeted: deepens only the top-plausibility arrangement) |
| `deepen` | ExploreTransformations + GenerateSynthesis | develop an alternative arrangement when the person's lived reality picks a shallow reading |
| `audit_feasibility` | TransformationAudit | answer "could I actually do that?" about named pathways — a practical-achievability band per Ac+/Re+ step with its factors and success conditions (on demand: 2 calls per pathway, idempotent, absent unless asked) |
| `record_decision` | RecordDecision + DecisionCoherenceCheck | record an explicitly confirmed decision with grounds + the confirming principal's rationale (consent-first in BOTH modes — the one exception to silent machinery; provenance = `principal`, host-attested). One decision, one record: an exact repeat of an active decision's question and stance returns the standing record instead of writing a second one |
| `sync` | DialecticalContext | re-read full graph state |
| `discard`, `inspect_node`, `read_digest` | shared | curate / detail (discard also retracts/supersedes Decisions) |

`ingest` and `explore` each collapse an entire Analyst-or-Explorer workflow into one
call; the Advisor decides internally when to analyze vs. explore — no phase split is
exposed. `deepen` is the follow-up to `explore`'s depth budget: all arrangements are
built and ranked, one is developed; when conversation gravitates to another reading,
`deepen` develops it on demand (the Explorer needs no equivalent — its
`explore_transformations`/`generate_synthesis` are already per-wheel, user-driven).
`audit_feasibility` is the same shape applied to a *judgement* rather than to
structure: the transformation audit used to run on every pathway `explore` built
(40% of its provider spend, for an annotation nothing read), so it is now off by
default and this tool spends it on the pathway the person actually asked about.
Both agents carry it — the Advisor ranks partly on feasibility, the Explorer
displays it.

**UX to build around it:**
- **A chat window — essentially that.** No graph canvas, no scores, no hashes, no phase
  buttons. The prompt forbids all framework terminology, and the one leak shape a prompt
  cannot be trusted with is removed in code: a `[[hash]]` address never reaches the person
  on either entry point (`chat` and the `TextDelta`s alike, with `ResponseComplete.message`
  still byte-for-byte the deltas), wherever the preamble does not grant terminology
  disclosure. Measured before the filter: 0 hash citations in 484 Sonnet 5 replies, 5 in
  1,331 Haiku ones — the filter is a floor for the weak model and a no-op for the strong.
- Optionally a **persona picker** (which `app_preamble`).
- The graph exists and grows silently; an optional "show me the structure" power view is
  possible but the default is just the conversation.
- The **unscoped** Advisor is a standalone app, not a mode of the navigator. The
  **exploration-pinned** Advisor (`nexus_hash=...`) is by default the opposite: a mode of the
  Explorer session, reached by handover. Pinned **with `persona=True`** it is the standalone
  app again, narrowed to one exploration — how a client's conversation continues inside the
  exploration it built.
- The **sealed Advisor** (`build=BuildPolicy.NEVER`) is the one to reach for when the graph
  already exists and the person wants to talk it through and decide: same chat window, a
  turn is one graph read plus the model, decisions are recorded, nothing is built.
  `build=ON_CONSENT` is the same window with one more thing the person can say — "write
  that down" — and the graph grows from it between turns.
- A **reading seat** (`records=False`) is for a seat that is not the one doing the work —
  a viewer, a second reader, a support agent. The conversation looks identical; the graph is
  untouched, and nothing said in it is recorded.

### Advise and forget — `Consultant`

(Vocabulary since 2026-09-28: `Consultant` is this agent. The Advisor that never builds,
`build=NEVER`, is the **sealed Advisor**; it was called "the Consultant" before.)

`Consultant(app_preamble=None, messages=None, app=None, thinking=FROM_SETTINGS,
include_decision=True)` (`agents/consultant/consultant.py`) is the Advisor's method as a prompt
and nothing behind it: no Case, no `scope(sid)`, no graph, no tools, no memory beyond the
`messages` of this one conversation. A host can run it with no database at all. It is the
surface for the shallow application — "I have a problem with my wife…", counsel that
reasons dialectically, and nothing written anywhere. What it cannot do, by construction and
stated in its own prompt: keep a record (a confirmed decision is restated in the reply, and
that restatement is the only record), remember the person at the return, or read a graph
someone else built — everything the bench has measured the framework's value to live in.

Its prompt, `method_prompt()`, is DERIVED from the engine's own sections (`_ROLE`, `_EAGER`,
`_INTERNAL_MODEL`, `_CONVERSATION_USE`, `_DECISION_READINESS`, `_HOW_YOU_SPEAK`) with every
tool verb rewritten into a mental act ("anchor the pair" → "take the pair as it comes",
"explore what you have" → "work out their pathways") and every paragraph that stays about
machinery dropped — so the method cannot drift between the two heads. It is byte-for-byte the
bench's A1 arm (`tests/e2e/README.md`), which means A1 now measures a shipped surface and every
edit to this prompt moves the baseline every `A2−A1` figure was read against;
`tests/e2e/test_e2e.py::TestMethodPrompt` is the guard. `app=` takes the AppSpec's
`advisor_persona`; app tools are refused rather than dropped (the prompt says "You have no
tools"). `chat()` / `chat_stream()` / `messages` / `last_turn_timing` as on every head, with
`closing` and `deferral` `None` because there is no seam to conclude anything.

**The view.** `await consultant.exploration_view(focus=None)` is the one view this head
can draw: an `ExplorationView` (`graph/views.py`, the same shape the graph-backed heads render
from), made by a structured TURN on this same conversation — full history, both sides, its
own system prompt — that renders what is established and builds what `focus` asks for that
is not yet worked out (`concerns/view_sketch.py`). It thinks (json mode) and it is
kept in `messages` as the consultant's own words, so the next turn knows what it drew. No
hash, alias or score exists to strip; nothing is validated (no HS gate, no validation flag, no
dedup) and nothing is persisted. `attempts=` (default `DEFAULT_SKETCH_ATTEMPTS`, max 3,
`concerns/tetrad_candidates.py`) draws that many in parallel, each on a copy of the history,
and the framework's own control statements pick the one that holds best — the agent checking
its work before the person sees it; the record lands in `messages` once. The model cannot
call it; the host owns the trigger.
The Advisor has the same method over its graph: `await advisor.exploration_view()` resolves
the pin (that exploration, numbered as the prompts number it; else every active perspective
in the Case) and applies `hides_terminology` itself, so a persona app and a Navigator get the
view their prose matches without the host holding the flag.

**The upgrade.** A Consultant session becomes a Case in two steps, both the host's: create
the Case, then inside its scope `await migrate_consultation(consultant.messages,
principal="human")` (`agents/advisor/migration.py`) — a utility that fills the GRAPH and
nothing else. The host then opens `Advisor(app=, principal=)` on the Case as it always does: a
NEW conversation, which reads as picking up where the old one left off because the memory is
already there (the tensions in the dump, the decisions in the ledger, the person's own words
readable back from the Input). The utility plants structure from the PERSON's turns only (the
replies are counsel, not statements of the situation — the reason a transcript-ingesting
design was rejected in review), weaves it synchronously, runs the closing seam over every
(person, reply) exchange in order so a confirmed decision is recorded under `principal` with
the grounds a live closing gets and a re-affirmation is not a second record, drains, and
returns a `MigrationReport` (turns, perspectives, pathways, decisions recorded / failed) the
host may show or log. It composes the Advisor's own seam and weave on a throwaway head the
host never sees. Costs one ingest plus one classifier call per exchange; a history with no
person's turn returns an empty report. Unbenched; `tests/test_migration.py` pins what is mined
and the order.

---

## Handoffs: the UX glue

There is **no automatic agent-switching** in the framework — the host app drives every
transition by watching tool reports and constructing the next agent.

```
┌── Analyst thread ──────────┐   create_nexus → nexus_hash   ┌── Explorer thread ──┐
│ inputs → theses →          │  ───────────────────────────▶ │ (bound to nexus)    │
│ polarities → tetrads       │                                │ build_wheels →      │
│ → GROUP                    │  ◀── "new tension" (UX route)  │ transformations →   │
└────────────────────────────┘                                │ synthesis           │
        both share NAVIGATOR_APP voice                           └─────────────────────┘
```

**Forward (Analyst → Explorer):** Analyst's `create_nexus` report carries
`artifacts["nexus_hash"]`. The UX offers "Open in Explorer" → the app constructs
`Explorer(nexus_hash=...)` as a new thread.

**Backward (Explorer → Analyst):** the reverse-handoff loop. When a Transition's
insight suggests a genuinely new tension, the **Explorer itself** calls
`create_dx_input(transition_hash)` — a shared orchestrator tool — wrapping the
transition as a `dx://` Case Input right where the insight appeared. Developing it
still happens in the Analyst thread (same `sid`): `surface_theses` / `analyze` on that
input produce new perspectives, then `expand_nexus` weaves them back into the
exploration. The loop is: *insight captured in Explorer → developed by Analyst →
returned via `expand_nexus`*. Both prompts narrate this — the Explorer offers the
capture at the resonance moment instead of off-ramping the user, and the Analyst
recognizes `dx://` inputs as exploration feedback to be developed and offered back.
(The Explorer still cannot *analyze*: `create_dx_input` only captures. `create_nexus`
remains Analyst-only — it is the forward phase boundary.)

The loop is closable end-to-end: `create_dx_input` stamps provenance into the
Input's digest ("Origin: insight from exploration [[hash]]…, pathway [[hash]]"),
`present_analysis` lists pending inputs under Sources (dx ones flagged "from
exploration" with their origin line), and `inspect_node` renders Transitions with
full lineage (position/edge → parent Transformation or Wheel → owning Nexus) — so
the Analyst always knows *which* exploration to weave back into without raw Cypher.

**Advisor (unscoped):** no handoff UX at all — it is one thread, one chat window.

**Explorer ↔ Advisor (the mode toggle):** an exploration session has two registers —
**operator mode** (Explorer: technical tools, wheels, scores) and **advisory mode**
(Advisor pinned to the same nexus: "what does this mean for me?"). The toggle is a
handover of the SAME conversation between two heads, driven by the host:

```python
# user in Explorer asks "so what should I actually do?" → toggle to advisory mode
advisor = Advisor(
    app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER,  # NAVIGATOR_APP + advisory register — same user contract, advisory voice
    nexus_hash=explorer.nexus_hash,
    messages=explorer.messages,
    principal="human",  # a person is on the other end — see Construct above
)

# later: "let's compare the other wheels again" → toggle back
explorer = Explorer(
    nexus_hash=advisor_nexus_hash,
    app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
    messages=advisor.messages,
)
```

That is the manual layer, spelled out so the pairing is visible. **An app toggles with
its own `AppSpec` instead**, and then the pairing is the framework's job — including the
register level, which must not change under the user mid-conversation:

```python
advisor  = Advisor(nexus_hash=nx, messages=explorer.messages, app=ASTRO_APP,
                   principal="human", advanced=user_is_expert)
explorer = Explorer(nexus_hash=nx, messages=advisor.messages, app=ASTRO_APP,
                    advanced=user_is_expert)
```

Do NOT reach for `app_preamble=my_app.navigator_preamble(advanced=True)` to get the
expert register: `app_preamble` cannot be combined with `app=` (mixing raises), so you
would drop the spec — and with it `app_tools`, leaving the app's own tools unwired with
no error at all. `advanced=` exists so that shape is never necessary.

Handover payload: `messages` + `nexus_hash` (+ the preamble pairing above). Constructing
either agent replaces the system prompt (`messages[0]`) and keeps the rest of the history
— including tool-use blocks from tools the new head doesn't carry (provider-accepted;
locked by `tests/test_agent_handover.py`, structure mocked + one `--real-llm` replay test).
App capability continuity: define ONE `AppSpec` per app and pass it to EVERY head —
Analyst included, not just the toggle pair. The toggle heads share literal history, so a
missing tool there breaks a capability the conversation already references (e.g. a chart
lookup) mid-conversation; the Analyst thread is a separate conversation, but the app's
user expects the same domain resources in the analysis phase (Analyst + Explorer +
advisory toggle = one Navigator app). The framework cannot detect a forgotten head: at
construction, "no app" is indistinguishable from "this app has none", and diffing
history tool-blocks against the tool set would false-positive on the intended built-in
asymmetry (Advisor carries `anchor`; Explorer deliberately doesn't). One constant makes
forgetting structurally hard — and each head derives its own correct preamble from it:

```python
ASTRO_APP = AppSpec(
    voicing=ASTRO_VOICING,            # Navigator-side flavor
    advisor_persona=ASTRO_PERSONA,    # standalone-Advisor identity
    tool_guide=ASTRO_TOOL_GUIDE,      # shared usage rules, verbatim in every head
    tools=[lookup_natal_chart, lookup_transits],
)

Analyst(app=ASTRO_APP)
Explorer(nexus_hash=nx, messages=msgs, app=ASTRO_APP)
Advisor(nexus_hash=nx, messages=msgs, app=ASTRO_APP)   # advisory toggle
Advisor(app=ASTRO_APP)                                  # standalone: persona, machinery hidden
Advisor(nexus_hash=nx, messages=msgs, app=ASTRO_APP, persona=True)  # pinned, machinery still hidden
```

The last line is not a toggle. It is the standalone Advisor continuing inside the exploration
it built — the same persona, the same hidden machinery, now with the pin's tool guards and
the scoped engine. A host reaches for it when a client's session has produced an exploration
worth staying in; a mediator toggling out of the Explorer never needs it.

Both heads narrate the toggle moment without switching themselves: the Explorer suggests
advisory mode when the conversation pulls from structure to meaning (only if the host offers
one — otherwise it keeps counseling from pathways), and the advisory head points back to the
exploration view for technical work. The host performs every switch.

**Both preambles sit on `NAVIGATOR_APP`** — that's what keeps both registers in Navigator
territory: same vocabulary contract (say "exploration", never "Nexus"), same
first-person/third-party perspective detection, same score presentation
(meaning-first). The toggle changes the engine (tool-driving vs counseling) and the
register — never the user contract.

Under `advanced=True` both sit on `NAVIGATOR_APP_ADVANCED_TOGGLE` instead, and the same
sentence still holds one level up: the contract is the *expert* one on both sides. That
pairing needs a trailer the ordinary one does not, because the advisory register body was
written for the non-expert default — it re-affirms the contextual vocabulary and
"meaning first, numbers on request" that advanced mode overrode, and later sections win,
so without a final word the advisory side would silently re-lock the register the host
just asked for (`"Nexus"` included). `NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER_ADVANCED`
is therefore `NAVIGATOR_APP_ADVANCED_TOGGLE + the same register body + that trailer`; the
body is one shared constant, so the two pairings cannot drift apart.

The Advisor head keeps full analytical power (anchor + explore + deepen +
audit_feasibility pinned to the nexus — it IS Analyst+Explorer behind one
voice), but with two constraints:

- **Nexus pin in code** (`advisor/tools/scoped.py`): it cannot create sibling nexuses or
  reach into ANOTHER exploration (deepen refuses wheels of other explorations;
  audit_feasibility refuses pathways of other explorations — it writes and it
  spends provider calls, so it is guarded like the other write tools; discard
  refuses their perspectives). Only `ingest` is excluded (bulk extraction belongs
  to the Analyst thread).

  What the pin does NOT hide is a tension attached to no exploration, and that
  matters because `anchor` plants exactly that: a freshly anchored tension is
  standalone until `explore` weaves it in. So the advisory head reads its own
  anchors in the context dump (under `# Unexplored Tensions`, quality-floored like
  the unscoped dump, with their particulars hoisted) and can weave, discard or
  draw on them. Other explorations' tensions appear only as a count.
- **Transparent mutation** (`NAVIGATOR_APP_EXPLORER_AGENT_ADVISORY_REGISTER`): unlike the unscoped Advisor's
  silent graph-building, the advisory head asks before adding a new tension to the
  user-built exploration and announces the change afterwards. The deliverable never
  changes behind the user's back. (`deepen` needs no consent ceremony — it only adds
  analytical depth to existing structure, never changes what the exploration contains.)

---

## Decision-making apps

The Advisor carries the full decision lifecycle in its engine prompt (the
"Decision Readiness" section, rendered whenever `record_decision` is wired):
convergence mechanics (discrimination test, saturation-by-family judgment),
the propose-and-confirm recording ceremony, the soft pre-commit ritual
(accepted cost confronted, S- trap named), and the post-decision re-audit
(reassure from the record vs legitimately reopen). All of that is
domain-neutral framework behavior — always on, never re-specify it in an app.

**The record itself does not depend on the prompt.** A decision is a
user-driven artefact: it exists because the person declared it, and that
declaration is an observable event in their message. So after every Advisor
turn, `DecisionConfirmationCheck` asks whether the person confirmed a decision
that then went unrecorded, and `Advisor._repair_unrecorded_decision` writes it
under the same host-attested `principal` the tool would have used. Hosts get
this for free on both `chat()` and `chat_stream()` — nothing to wire.

Why it exists: `record_decision` fired 6/6 at a strong tier and **0/6** at a
weak one on identical prompt text, the weak model writing a formatted "Your
Decision" section in prose every time while the person was told it was saved
(`tests/e2e/README.md`). Three rounds of prompt strengthening changed that by
zero. The model calling the tool itself is still the preferred path — it can
adopt a pathway, which the repair never guesses — so the seam is a floor, not a
replacement. The engine prompt does not mention it: telling the model a backstop
exists would license the laziness it compensates for.

The repair does attach the **`accepted_cost`** ground, because that half is
derivable rather than guessable. The check asks which mapped tension's pole the
person's stance corresponds to — a matching question with a verifiable answer —
and the cost then follows by definition: chose the thesis, the price is `T-`;
chose the antithesis, `A-`. (A plus is a goal or an obligation, i.e. something to
do, so it can never be a price.) No clear match means no ground: a wrong
`accepted_cost` claims the person accepted a price they never faced, and sends
the later re-audit to reassure them about the wrong risk.

In the ledger an `accepted_cost` renders with its **condition**, not as a bare
risk — "accounts may follow him out — arises when buying him out is held without
diversifying the client relationships". That is what lets the person tell "the
risk I accepted, and I'm not paying it" from "the thing now happening to me",
which is the whole job of the record when they come back wobbling. Derived
structurally from the tetrad, so it costs no LLM call. It renders the theory's
**neutral-T** control statement ("T without A+ yields T−", Rule 3.3's second
form) rather than the primary aspect-level one ("T+ without A+ yields T−") that
`ControlStatementsCheck` scores — the person committed to the side, not to its
idealised plus. Both are the paper's; they sit at different levels and are not
interchangeable.

What belongs **app-side** (via `AppSpec`):
- **Persona/ceremony intensity** — how pushy convergence feels, how formal the
  recording moment is (a `DECISION_PARTNER_PERSONA`-style persona whose contract is
  the decision, not the exploration: establish what's being decided and by
  when, treat every blindspot/pathway as input to that choice, switch register
  at readiness).
- **Urgency/deadline handling** — deadlines are conversation content the
  persona attends to, not framework state.
- **Decision-list UI** — the `# Decisions` ledger renders in the context dump;
  a host can also query `DecisionRepository` directly for a decisions panel.
- **Re-open flows** — the framework's primitive is record-new + discard-old
  (reason naming the replacement); how a UI surfaces "revisit this decision"
  is the host's design.

**Navigator visibility (deliberate deferral):** `present_analysis` and
`present_exploration` do NOT render decisions — the Analyst/Explorer heads
have no rendered awareness of them (reachable only via `query_graph`/
`inspect_node` by hash; the shared `discard` tool is technically
decision-capable wherever it's wired, including the Analyst, but no Navigator
prompt directs it at decisions — the consent ceremony lives in the Advisor
line). Decisions are an Advisor-line artifact for now; extending the ledger
to the Navigator surfaces is a scope decision to make explicitly, not an
omission (it would touch the Navigator prompts' vocabulary contract, not
just the renderers). The advisory toggle is the covered exception: after a
advisory-mode recording, the Explorer head sees the record in its replayed
history (verbatim tool blocks) and can read it via `inspect_node`/
`query_graph`; its prompt routes decision *lifecycle* (record/retire) back
to advisory mode and forbids fake acknowledgments.

## Choosing what to build

The framework cannot predict its own applications; what can be named are the CATEGORIES
of app that will emerge (owner's framing, 2026-09-21), and each maps to one construction.
They differ by WHO is talking and WHETHER the graph is being built:

| Category | Who | Construct | Builds | Measured |
|----------|-----|-----------|--------|----------|
| **Navigator** | a system scientist building and navigating the wheel at the same time | `Analyst(app=)`, then `Explorer(nexus_hash=)`, switching heads by resuming with the same `messages`; the advisory register (`Advisor(nexus_hash=, messages=)`) is its third head | yes, in the open — every tool call is visible, buttons in the app route through the same chat | tool contracts and skills; never benched as counsel |
| **Advisor on a nexus** | an analyst or mediator exploring ONE constellation of perspectives with assisted reasoning | `Advisor(nexus_hash=, messages=, app=)` — the Navigator's advisory register, vocabulary disclosed; or `persona=True` for a person who never used the Navigator | silently, inside the pin | `nexus-pinned` (Haiku, n=8): equal to the sealed Advisor, loses to the dump. `ladder-sonnet` (Sonnet 5, n=6): above the dump (+0.22, unresolved) but a resolved loss to the sealed Advisor (−0.51 [−0.97, −0.05]) — and on both models no build tool elected inside the pin. Read with the caveat in `rounds.md`: a Sonnet build makes several nexuses and the bench pins to one, so the pin hid most of the graph |
| **Advisor from scratch** | the client of a mediator, psychologist or similar, resolving an issue with a dialectically thinking LLM | `Advisor(app=)` | silently, from nothing — and **it ends up building a nexus and diving into it**, i.e. it collapses into the row above: the host pins the later sessions with `Advisor(nexus_hash=, app=, persona=True)` | the benched A2 arm: the first session loses to a static dump of the graph it builds (−1.47 [−1.76, −1.18], `reasoning-sonnet`); it wins at the return (`ladder-return`). What the bench has measured is the on-ramp, not the destination |
| **Advise and forget** | anyone, once: a situation described, counsel that reasons dialectically, nothing kept | `Consultant(app_preamble=)` — the method as a prompt, no graph, no tools, no Case | never | the bench's A1 arm IS this head's prompt: in-session `A2−A1` is positive and unresolved on Sonnet 5 (+0.26 at 12 pairs, `prompt-vs-machinery`; `thinking-check` +0.35 with thinking, −0.27 without); at the return it has nothing to return to |
| **Sealed Advisor** | a person talking to a graph that something else built — typically an agentic LLM running the [headless builder](#the-headless-builder) | `Advisor(build=NEVER)` (or `ON_CONSENT`, to let it grow on their word), with or without `nexus_hash` | never — reads, records decisions, retracts, scores a pathway on request | the best counsel measured on both models, and on Sonnet 5 a RESOLVED win over the static dump of the same graph (+0.50 [+0.08, +0.92], `ladder-sonnet`); never worse than the builder; ~47s a turn on Sonnet against the dump's ~10s |

The categories and the Advisor's `build=`/`records=` are two axes, not one list: the two
Advisor categories run `ON_ELECTION`, the sealed Advisor runs `NEVER` (as benched) or `ON_CONSENT`
(unbenched), and `records=False` is an access level under any of them rather than a fifth
category — the same conversation, nothing recorded, for a seat that is not the one doing the
work.
`messages` is resumption on every head and never a mode. `thinking=`, `advanced=` and
`persona=` are properties of the person for the session, passed to every head they see;
`DIALEXITY_REASONING_MODEL` is the deployment's, for the structured calls every category
shares.

What the bench says, stated once: counsel from a FINISHED graph beats counsel from a graph
being built in front of the person, resolved on the weak tier; the value accrues in the
record and the map and is collected at the return. That is not a verdict against the two
building categories — it is the reason the first session is the expensive one and the
Sealed Advisor exists — and it was the WEAK model's verdict. On Sonnet 5 (`ladder-sonnet`) every
live head sits above the static dump and the sealed Advisor does so resolved; the builder is not
worse than the sealed Advisor and costs 8x the dump's turn; the pinned head, as benched, loses
to the sealed Advisor because a Sonnet build makes several nexuses and a pin to one hides the
rest. The model is the brain: the same products, a different verdict, and the production
verdict is the one to build against.

Navigator and the Advisors are **not** one UI with a toggle — the Advisor's value is that it
hides exactly what the Navigator exists to show. If you build both, they are two front-ends
over one graph service, distinguished only by which agents they instantiate and which
preamble they inject. The sealed Advisor composes with any of them: it is the same `Advisor`
class, handed fewer tools.

### The headless builder

The sealed Advisor presupposes a graph, and the thing that built it need not be a person in a
chat. The same pipelines every agent composes are callable directly, under a scope, with no
conversation and no preamble. Three calls take material to a developed exploration:

```python
from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.explorer.explorer import ExplorationPipeline
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.graph.scope_context import scope

with scope(case.sid):                                  # the app owns the Case
    analysis = await AnalysisPipeline(text=material, intent=intent).resolve()
    #   -> perspective_hashes (standalone tetrads), plus thesis/polarity hashes
    created = await CreateNexus().resolve(intent=intent,
                                          perspective_hashes=analysis.perspective_hashes[:k])
    exploration = await ExplorationPipeline(
        nexus_hash=created.nexus.hash,
        perspective_hashes=analysis.perspective_hashes[:k],
        max_deep_wheels=1,            # the Advisor's own budget; None deepens EVERY wheel
        refine_from_coarser=True,     # the refinement recursion; off, the top wheel refines from nothing
    ).resolve()
    #   -> cycle/wheel hashes, deepened_wheel_hashes, transformation hashes
```

Synthesis is a separate skill (`GenerateSynthesis`, per deepened wheel) and the Advisor's
`explore` tool runs it after the pipeline; a headless builder that wants the same one-call
shape, synthesis included and the perspective cap applied, calls
`agents/advisor/tools/explore.py::run_exploration_detailed(perspective_hashes, intent,
nexus_hash)`, which is the shared body behind the tool and is already entered directly by
the closing seam and the probes. Three things the pipelines leave to the caller: **bound k**
(the wheel count is combinatorial — `max_deep_wheels=None` deepens all of them, which at
k=4 is 96 wheels and had not returned after 41 minutes with a zero-latency model); **open a
progress scope** if a host is watching (`utils/progress.py`; the pipelines report into it
and are silent without one); and **nothing here records decisions** — that is the
Sealed Advisor's job on the graph this produced. An agentic builder that drives the Analyst and
Explorer heads through `chat()` instead gets the same graph with the tool-election
variance those prompts carry; the pipelines are deterministic in what they run.
`tests/test_agents_e2e.py` runs exactly this sequence against a real provider.

**This is also how a sealed Advisor's graph GROWS between sessions, and it needs no framework
change.** The sealed Advisor builds nothing on the turn or after it (its mandate says so to the
person). A host that wants the next session to open on a richer graph runs the three calls
above between sessions, under the same scope, on the person's material (their own words and
facts — not the assistant's replies), and bounds `k`. That is the configuration every
Sealed Advisor number in the archive was measured on (each A2c cell's graph was built by a full
Advisor run BEFORE the session), and it keeps one writer per sid where it is enforceable: the
host's process, not a concurrent head. A design that had the sealed Advisor grow its own graph
off the turn was reviewed and dropped on 2026-09-24 (`tests/e2e/rounds.md`, `### critics'
review`): the off-turn weave creates no perspectives, an unscoped weave forks a second
nexus, and transcript ingest is speaker-blind and unconsented.

## The brain: what is measured per model

The products above do not depend on the model. Every category is the same construction
whichever model sits under it — the model is the brain, the framework is what powers it
with dialectics — and the framework enforces in code only what is true of any brain: one
writer per sid, a decision recorded when the person confirms it, a price located to one
tetrad, nothing built silently against consent, the pin. Elections (whether to explore,
deepen, anchor) are reasoning and stay with the model. What the framework DOES hold is
knowledge of how each model it has been run on behaves, so a host can pick one. Measured,
all figures from `tests/e2e/rounds.md` (never from memory; re-derive before quoting):

| behaviour | Haiku 4.5 | Sonnet 5 | where |
|---|---|---|---|
| extraction claims not supported by their source | 34.6% (6.2% invented) | 7.0% (3.5%) | `sonnet-thinking` |
| machinery leak, share of replies | 10.9% (hash cited 0.4%, bare label 1.5%) | 0.6% (never a hash or label) | `reply-hygiene` |
| `record_decision` fired when the person confirmed | 0 of 6 | 6 of 6 | `tests/e2e/README.md` |
| `explore` elected in an Advisor run | 6 of 55 | 17 of 25 | `a15-floor`, README |
| build tools elected inside a nexus pin | 1 explore in 4 cells, no anchor, no deepen | none in 3 cells (discard, record, inspect, audit only) | `nexus-pinned`, `ladder-sonnet` |
| a refused `record_decision` retried identically | 3–5 times per closing | 4 times on one closing — the loop is the refusal's, not the model's (fixed 3a555f1) | `nexus-pinned`, `ladder-sonnet` |
| extended thinking at `medium` on the tool path | ~3x the call, no election gain | close to free, close to a no-op — measured against a baseline that was ALREADY thinking: Bedrock's default for Claude 5 on a plain text/tools call is adaptive thinking on, and "unset" was not sent as off until 2026-09-24 | `thinking-off`, `sonnet-thinking`, `probe_tool_path_hidden_output` |
| hidden output on an unset-thinking CONVERSATIONAL round | none (4.x thinks only when asked) | ~500 thinking tokens on a plain reply, ~2,500 on a tool-wired turn over a real graph — the sealed Advisor's 42s vs the dump's 13s; now sent as disabled inside `conversational_round()` only | `probe_consultant_42s`, `probe_tool_path_hidden_output` |
| hidden output on a structured (forced-tool `format`) concern call, level unset | none | none — 0 thinking tokens with no parameter sent; tool choice suppresses the default, so the graph builders never thought and the prompt arms (which answer through the same path) never thought either | `probe_tool_path_hidden_output::test_probe_where_thinking_lands_now` |
| live head vs static dump of its own graph | loses, resolved (−1.47 / −0.83 / −0.78) | sealed Advisor +0.50 [+0.08, +0.92] — marked RESOLVED by the report but BELOW the round's own pre-registered margin (≥0.12), 6 pairs from 2 replicates, slot split 4/2 in the winner's favour (the memory kill), winner 8% longer; substance-only +0.59 [+0.09, +1.09]; replication needed. Builder +0.38 and pinned +0.22 unresolved; pinned −0.51 vs sealed Advisor measured a blindfold (pin to 2 of 4–5 perspectives), not the category | `reasoning-sonnet`, `nexus-pinned`, `ladder-sonnet`, critics' review |
| median turn, live head over a built graph | sealed Advisor 11.8s, builder 12.3s | sealed Advisor 47s, builder 76s (worst deferred wait 174s); the dump 9.8s | `nexus-pinned`, `ladder-sonnet` |
| decisions flagged incoherent by the coherence check | 6 of 15 | 1 of 12 | `nexus-pinned`, `ladder-sonnet` |
| the assembly vs the same method as a tool-less prompt (`A2−A1`), in-session / at the return | −0.43 resolved / +2.4 resolved | +0.26 unresolved (A2 converges, A1 diagnoses) / +1.07, followup cells resolved | `ladder-return-r18`, `prompt-vs-machinery` |
| the typed record vs the model's own prose journal at the return (`A2−A1.7`) | +0.78 / +1.08 resolved | +0.06 at n=2, a null | `ladder-return-r16/r18`, `prompt-vs-machinery` |
| a prompt arm claiming a record it cannot write (PHANTOM) | not measured | after the scorer fix (typed-before-claimed, offers excluded; critics' review 2026-09-24): A0 0 of 6, A1 1 of 7, A1.7 2 of 6; A2 7 of 7 honoured. Not a graph property: a durable write plus the repair seam delivers it, and the prompt arms were taught the word "record" by the rewrite table | `prompt-vs-machinery`, `systemic-loop` |
| median turn, builder vs the tool-less prompt | not measured | 76.8s vs 11.4s (equity), 50.0s vs 8.4s (return) | `prompt-vs-machinery` |
| causal links named on a four-tension loop (hand label, 0–4) | not measured | NOT QUOTABLE — one rater, no persisted verdicts, two of four links scripted into the person's turns (critics' review, `rounds.md`); the judged row is `A2 vs A1` +0.39 [−0.03, +0.81], `A2 vs A1.7` 0.00, n=4 | `systemic-loop` |
| builder elects multi-perspective structure on a four-tension situation | not measured | 2 of 4 cells (8 and 7 perspectives); 1 perspective in the other two | `systemic-loop` |

What follows from the table, as of 2026-09-22: **Sonnet 5 is the floor for a conversation
with tools wired**, and on it the direction of the bench's central finding flips — every
live head sits above the static dump of its own graph, the sealed Advisor resolved — so the
"live loses to static" story was the weak model's. Haiku 4.5 is a development model — every seam that compensates for
a model not doing what the prompt says (the closing repair, the off-turn weave, the
empty-graph anchor, the shared-price location, the hash filter) was built against the
Haiku column, and each is either a no-op or idempotent under a model that complies.
`DIALEXITY_DEFAULT_MODEL` and `DIALEXITY_REASONING_MODEL` are where a host makes the
choice; the framework never checks a model name. Models not in the table (Opus, non-Claude
providers) have no figures, which means unmeasured, not unsupported: the same bench runs
against any provider Mirascope reaches (`DIALEXITY_E2E_TIER_*`).
