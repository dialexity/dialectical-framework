# Agents: Analyst, Explorer, Advisor

The three conversational agents are the primary building blocks for any application
on top of the dialectical framework. Each is a thin LLM orchestrator that owns a set
of tools and a system prompt; the dialectical reasoning ("wisdom") lives in the
orchestrator + concern layer, while the **app preamble** supplies only user-facing
flavor (persona, vocabulary). Swap the preamble and the same reasoning engine serves
a different product.

They are three products over one graph, split by **when you know what**:

| Agent | Metaphor | Scope | Turns... | Framework visible? |
|-------|----------|-------|----------|--------------------|
| **Analyst** | workbench | Case | raw material → structured tensions, up to grouping | yes (structure-forward) |
| **Explorer** | lab bench | one Nexus | one group of tensions → causal pathways + synthesis | yes (structure-forward) |
| **Advisor** | conversation | Case | anything → counsel, framework runs silent | no (hidden) |

Analyst + Explorer together are the **graph-navigator** experience (two visible
phases). The Advisor is a **separate app**: internally it does what Analyst + Explorer
do, but exposes none of the machinery.

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

`chat()` returns the same durable reply with no streaming at all, so a host on `chat()`
gets no first-token benefit; that is a host choice, not a framework limit.

Construction is uniform except for what each is bound to:

```python
Analyst(app=None, app_preamble=None, messages=None, app_tools=None)              # Case-scoped (ambient)
Explorer(nexus_hash, app=None, app_preamble=None, messages=None, app_tools=None) # bound to one Nexus
Advisor(app=None, app_preamble=None, dialectical_context=None, messages=None,
        nexus_hash=None, app_tools=None)
```

**`app` (an `AppSpec`, `agents/app_spec.py`) is the recommended interface**: the app
declares its custom pieces once — `voicing` (Navigator-side domain flavor),
`advisor_persona` (standalone-Advisor identity), `tool_guide` (shared tool usage rules),
`tools` — and every head composes the right preamble itself: Analyst/Explorer get
`NAVIGATOR_APP + voicing + tool_guide`, the counsel toggle gets
`NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER + voicing + tool_guide`, the standalone Advisor gets
`advisor_persona + tool_guide`. The framework owns the composition lore; apps never
touch the base preambles. One AppSpec constant, passed to every constructor — the
continuity rule below is then automatic.

`app_preamble`/`app_tools` are the manual low-level layer (full preamble control; see
`agents/apps.py`): `app_preamble` replaces the AppSpec-derived composition entirely,
`app_tools` are `@llm.tool` functions appended to the built-in set
(`agents/toolsets.py`; shadowing a built-in name raises). Mixing `app=` with either
manual param raises. `messages` resumes a saved conversation. The **host application** owns four things the framework does not:

1. **DI setup** — `DialecticalReasoning.setup(Settings.from_env())` once at startup.
2. **Scope** — wrap every `chat()` in `with scope(sid):` (all graph writes are `sid`-scoped).
   Enforced: an unscoped `chat()`/`chat_stream()` raises `MissingScopeError` immediately —
   running unscoped would otherwise fail silently (nodes save with `sid=None`, invisible to
   every listing, and commit dedup can alias onto another Case's nodes).
   **One writer per sid** — a hard contract, not enforced in code: never run two
   agent conversations that write the same `sid` concurrently (headless drivers
   fanning out included). The graph client is a singleton with one cached
   connection, `commit()` dedup is check-then-act across autocommitted
   statements, and directed `connect()` duplicates edges on repeated calls —
   concurrent same-sid writers produce duplicate nodes/edges and half-built
   containers. Different sids are fine. Parallelism *inside* one turn is
   already handled (LLM work gathers, graph writes stay sequential).
3. **Message persistence** — save/load `agent.messages` per conversation thread.
4. **Phase handoff & live updates** — see [Handoffs](#handoffs-the-ux-glue) and the
   `GraphEventBus` (effects publish per `sid` for reactive canvas updates).

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
nexus_hash=None, app_tools=None, principal="human")`. `dialectical_context` is an optional
pre-rendered graph snapshot (from `DialecticalContext().resolve()`) injected into the system
prompt — use it when a rich graph already exists at conversation start. `principal` is the
host's attestation of WHO confirms decisions in this conversation: leave the default only
when an actual person is on the other end; a delegated driver (agent-to-agent runs) must
pass its identity (e.g. `"agent:dataset-driver"`) so recorded decisions carry honest
provenance — the ledger renders driver-confirmed rationales attributed, never as the
person's own "Why". Closed over by the tool in code; the LLM cannot set it. `nexus_hash` pins the
Advisor to one exploration — this is the **counsel mode of an Explorer session**, not a
standalone deployment; see [Explorer ↔ Advisor](#handoffs-the-ux-glue) below.
`app_tools` is the app's domain-resource seam: additional `@llm.tool` functions
(chart lookups, methodology references, knowledge-base fetches) appended to the
built-in set. The engine prompt carries no docs for them (their tool-schema docstrings
reach the LLM automatically) — introduce them and their usage rules in the app
preamble, where domain vocabulary lives. Shadowing a built-in tool name raises.

**Tools (10)** — coarse, composed super-tools that hide the machinery:

| Tool | Composes | Purpose |
|------|----------|---------|
| `ingest` | AnalysisPipeline | raw material → perspectives (bulk discovery) |
| `anchor` | IntroducePolarity + ExpandPolarity | plant a specific T/A tension |
| `explore` | CreateNexus + ExplorationPipeline + GenerateSynthesis | group → pathways → synthesis in one shot (budgeted: deepens only the top-plausibility arrangement) |
| `deepen` | ExploreTransformations + GenerateSynthesis | develop an alternative arrangement when the person's lived reality picks a shallow reading |
| `audit_feasibility` | TransformationAudit | answer "could I actually do that?" about named pathways — a practical-achievability band per Ac+/Re+ step with its factors and success conditions (on demand: 2 calls per pathway, idempotent, absent unless asked) |
| `record_decision` | RecordDecision + DecisionCoherenceCheck | record an explicitly confirmed decision with grounds + the confirming principal's rationale (consent-first in BOTH modes — the one exception to silent machinery; provenance = `principal`, host-attested) |
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
  buttons. The prompt forbids all framework terminology.
- Optionally a **persona picker** (which `app_preamble`).
- The graph exists and grows silently; an optional "show me the structure" power view is
  possible but the default is just the conversation.
- The **unscoped** Advisor is a standalone app, not a mode of the navigator. The
  **exploration-pinned** Advisor (`nexus_hash=...`) is the opposite: a mode of the
  Explorer session, reached by handover, never started cold.

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
**operator mode** (Explorer: technical tools, wheels, scores) and **counsel mode**
(Advisor pinned to the same nexus: "what does this mean for me?"). The toggle is a
handover of the SAME conversation between two heads, driven by the host:

```python
# user in Explorer asks "so what should I actually do?" → toggle to counsel mode
advisor = Advisor(
    app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,  # NAVIGATOR_APP + advisory register — same user contract, counsel voice
    nexus_hash=explorer.nexus_hash,
    messages=explorer.messages,
)

# later: "let's compare the other wheels again" → toggle back
explorer = Explorer(
    nexus_hash=advisor_nexus_hash,
    app_preamble=NAVIGATOR_APP_ADVANCED_TOGGLE,
    messages=advisor.messages,
)
```

Handover payload: `messages` + `nexus_hash` (+ the preamble pairing above). Constructing
either agent replaces the system prompt (`messages[0]`) and keeps the rest of the history
— including tool-use blocks from tools the new head doesn't carry (provider-accepted;
locked by `tests/test_agent_handover.py`, structure mocked + one `--real-llm` replay test).
App capability continuity: define ONE `AppSpec` per app and pass it to EVERY head —
Analyst included, not just the toggle pair. The toggle heads share literal history, so a
missing tool there breaks a capability the conversation already references (e.g. a chart
lookup) mid-conversation; the Analyst thread is a separate conversation, but the app's
user expects the same domain resources in the analysis phase (Analyst + Explorer +
counsel toggle = one Navigator app). The framework cannot detect a forgotten head: at
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
Advisor(nexus_hash=nx, messages=msgs, app=ASTRO_APP)   # counsel toggle
```

Both heads narrate the toggle moment without switching themselves: the Explorer suggests
counsel mode when the conversation pulls from structure to meaning (only if the host offers
one — otherwise it keeps counseling from pathways), and the counsel head points back to the
exploration view for technical work. The host performs every switch.

**Both preambles sit on `NAVIGATOR_APP`** — that's what keeps both registers in Navigator
territory: same vocabulary contract (say "exploration", never "Nexus"), same
first-person/third-party perspective detection, same score presentation
(meaning-first). The toggle changes the engine (tool-driving vs counseling) and the
register — never the user contract.

The Advisor head keeps full analytical power (anchor + explore + deepen +
audit_feasibility pinned to the nexus — it IS Analyst+Explorer behind one
voice), but with two constraints:

- **Nexus pin in code** (`advisor/tools/scoped.py`): it cannot create sibling nexuses or
  reach outside the exploration (deepen refuses wheels of other explorations;
  audit_feasibility refuses pathways of other explorations — it writes and it
  spends provider calls, so it is guarded like the other write tools). Only
  `ingest` is excluded (bulk extraction belongs to the Analyst thread).
- **Transparent mutation** (`NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER`): unlike the unscoped Advisor's
  silent graph-building, the counsel head asks before adding a new tension to the
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
just the renderers). The counsel toggle is the covered exception: after a
counsel-mode recording, the Explorer head sees the record in its replayed
history (verbatim tool blocks) and can read it via `inspect_node`/
`query_graph`; its prompt routes decision *lifecycle* (record/retire) back
to counsel mode and forbids fake acknowledgments.

## Choosing what to build

Two product shapes share one backend:

- **Navigator** (Analyst + Explorer): two visible phases, structure-forward. For users
  who want to *see and steer* the dialectics. More UI, but degrades gracefully — the user
  sees and fixes each step.
- **Advisor**: one chat, structure hidden. For users who just want counsel. Minimal UI,
  but demands the framework be reliable end-to-end unattended.

They are **not** one UI with a toggle — the Advisor's value is that it hides exactly what
the Navigator exists to show. If you build both, they are two front-ends over one graph
service, distinguished only by which agents they instantiate and which preamble they inject.
