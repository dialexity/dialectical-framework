"""
Advisor: Conversational agent for advisory apps.

Pure conversation — the framework runs silently in the background.
The user never sees framework terminology, just experiences progressively
wiser responses as dialectical understanding builds.

Two use cases:
- Fresh start: user talks, framework builds graph behind the scenes.
- Post-analysis: rich graph exists, advisor draws on it immediately.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.system_prompts import \
    system_prompt
from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.graph.scope_context import require_current_sid
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.app_spec import AppSpec, resolve_app_layer
from dialectical_framework.agents.stream_events import ResponseComplete, StreamEvent
from dialectical_framework.agents.toolsets import merge_app_tools

logger = logging.getLogger(__name__)


class ChatResponse(BaseModel):
    """Response from the advisor chat."""

    message: str = Field(description="The assistant's response message")


class Advisor:
    """
    Conversational agent for advisory apps.

    The host app is responsible for:
    - Creating the Case and managing scope(sid)
    - Persisting and loading conversation messages
    - Wrapping chat() calls in `with scope(sid):`
    - Optionally pre-computing dialectical_context via DialecticalContext

    The system prompt is static after its first render: the Current
    Understanding dump reflects the graph at construction time. Fresh graph
    state flows through the conversation itself — tool results carry each
    change, and the model calls `sync` when it wants a full re-dump. (One
    exception: an exploration-pinned Advisor constructed without a precomputed
    dialectical_context renders its scoped dump lazily on the first turn,
    because __init__ is sync and DialecticalContext.resolve() is async. A
    transient render failure retries on the next turn; only success — or a
    vanished nexus — consumes the one shot.)

    Usage (fresh start):
        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_PERSONA)
            response = await advisor.chat("My son started smoking...")

    Usage (post-analysis, rich graph exists):
        with scope(case.sid):
            context = await DialecticalContext().resolve()
            advisor = Advisor(app_preamble=COUNSELOR_PERSONA, dialectical_context=context)
            response = await advisor.chat("I want to talk through what we found...")

    Usage (resuming conversation):
        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_PERSONA, messages=saved_messages)
            response = await advisor.chat("What about the other angle?")

    Usage (app-provided domain tools):
        # The app brings field knowledge two ways: prose in the preamble,
        # and callable resources as app @llm.tool functions. The engine
        # prompt carries no docs for app tools (their tool-schema docstrings
        # travel to the LLM automatically) — introduce them and their usage
        # rules in the app preamble, where domain vocabulary lives.
        with scope(case.sid):
            advisor = Advisor(
                app_preamble=ASTRO_COUNSELOR_PERSONA,  # explains when to consult the chart
                app_tools=[lookup_natal_chart],   # @llm.tool from the app
            )

    Usage (Advisor mode of an exploration session — Explorer handover):
        # User was chatting in Explorer (operator mode) and asks "what does
        # this all mean for me?" — the host toggles to counsel mode by
        # handing the SAME conversation to an Advisor pinned to the SAME
        # exploration:
        with scope(case.sid):
            advisor = Advisor(
                app_preamble=NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER,
                nexus_hash=explorer.nexus_hash,
                messages=explorer.messages,
            )
            response = await advisor.chat("So what does this all mean for me?")

        # Toggling back to operator mode is the reverse handover:
        #   Explorer(nexus_hash=nx, messages=advisor.messages, ...)

        This is a register toggle, not a different scope: same conversation,
        same exploration, different head. The Advisor keeps its full
        analytical power (it IS Analyst+Explorer behind one voice): it
        anchors new tensions from the conversation and weaves them in. The
        nexus pin is enforced in code: the tools close over nexus_hash — the
        model cannot create sibling nexuses or reach outside the exploration.
        Requires an active scope(sid) at construction (nexus is validated
        against the DB). The host app drives the toggle — there is no
        automatic agent-switching.
    """

    AGENT_NAME = "advisor"

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        dialectical_context: Optional[str] = None,
        messages: Optional[list] = None,
        nexus_hash: Optional[str] = None,
        app_tools: Optional[list] = None,
        app: Optional[AppSpec] = None,
        principal: str = "human",
    ) -> None:
        # principal: WHO confirms decisions in this conversation — a host
        # attestation, fixed for the session (the counterpart doesn't change
        # mid-conversation). "human" = an actual person; a delegated driver
        # (agent-to-agent runs) must pass its own identity ("agent:<name>"
        # or <provider>/<model>) so recorded decisions never claim human
        # confirmation they didn't get. Closed over by record_decision —
        # never an LLM-visible parameter. Kept on the instance because the
        # decision-confirmation repair records under the same attestation as
        # the tool would have (see _repair_unrecorded_decision).
        self._principal = principal
        self._nexus_hash = nexus_hash
        # app: declarative app definition — composition depends on the mode:
        # counsel toggle (nexus_hash set) keeps the Navigator contract
        # (NAVIGATOR_APP_EXPLORER_AGENT_COUNSELOR_REGISTER + voicing + tool_guide); standalone uses
        # the spec's advisor_persona (machinery hidden). See AppSpec.
        app_preamble, app_tools = resolve_app_layer(
            app,
            app_preamble,
            app_tools,
            preamble_for="advisor_scoped" if nexus_hash else "advisor_unscoped",
        )
        if nexus_hash:
            self._validate_nexus(nexus_hash)
            self._tools = _build_scoped_tools(nexus_hash, principal)
        else:
            self._tools = _build_tools(principal)
        # App-provided @llm.tool functions (domain resources: chart lookups,
        # methodology references, ...) — see toolsets.merge_app_tools.
        self._tools = merge_app_tools(self._tools, app_tools)
        self._conversation = ConversationFacilitator(tools=self._tools)
        if messages:
            self._conversation._messages = list(messages)
        self._app_preamble = app_preamble
        # Scoped mode without a precomputed context: render the scoped dump
        # lazily on turn 1 (init is sync; resolve() is async). One-shot —
        # the system prompt is static after its first render.
        self._pending_context_render = bool(nexus_hash and not dialectical_context)
        self._conversation.set_system_prompt(
            self._build_system_prompt(app_preamble, dialectical_context)
        )

    @staticmethod
    def _validate_nexus(nexus_hash: str) -> None:
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        if NexusRepository().find_by_hash_prefix(nexus_hash) is None:
            raise ValueError(f"Nexus not found: {nexus_hash}")

    def _build_system_prompt(
        self,
        app_preamble: Optional[str] = None,
        dialectical_context: Optional[str] = None,
    ) -> str:
        parts = []
        if app_preamble:
            parts.append(app_preamble)

        # Deferred like the render call below — `dialectical_context` imports
        # the graph layer, which imports back through the agent package.
        from dialectical_framework.concerns.dialectical_context import \
            EMPTY_UNDERSTANDING

        context_text = dialectical_context or EMPTY_UNDERSTANDING
        # Rendered at construction (not the import-time SYSTEM_PROMPT
        # constant) so settings-derived prompt values (max_wheel_layer)
        # reflect the live DI configuration.
        engine = system_prompt(
            tool_names=[t.__name__ for t in self._tools],
            scoped_nexus_hash=self._nexus_hash,
        )
        parts.append(engine.replace("{dialectical_context}", context_text))

        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            await self._render_pending_context()
            result = await self._conversation.submit(ChatResponse, user_message)
            await self._repair_unrecorded_decision(user_message, result.message)
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            await self._render_pending_context()
            # The final reply comes from ResponseComplete, not from accumulated
            # TextDeltas: deltas cover the tool rounds, and the structured
            # message is what the person actually receives.
            reply = ""
            async for event in self._conversation.submit_stream(
                ChatResponse, user_message
            ):
                if isinstance(event, ResponseComplete):
                    reply = event.message
                yield event
            # After the stream, so the person's reply is never delayed by the
            # repair. Same guarantee as chat(): a confirmed decision is on
            # disk by the time the turn is over.
            await self._repair_unrecorded_decision(user_message, reply)

    async def _repair_unrecorded_decision(
        self, user_message: str, assistant_message: str
    ) -> None:
        """Write the record when the person confirmed one and the model didn't.

        A decision is a USER-driven artefact: it exists because the person
        declared it, and that declaration is an observable event in their
        message. So the record must not depend on the conversational model
        electing to call `record_decision` at the very moment it is most
        inclined to just answer well instead — which is exactly what it does
        at the weak tier. Measured: `record_decision` fired 6/6 at the strong
        tier and 0/6 at the weak tier on the same prompt, the weak tier
        writing a formatted "Your Decision" section in prose every time. The
        person was told it was written down; it was not. Three rounds of
        prompt strengthening moved that number not at all (see
        `tests/bench/README.md`), because no amount of prompt text makes an
        elective call reliable.

        `record_decision` already treats WHO confirmed as a host attestation
        rather than an LLM parameter (`principal`); this is the same principle
        applied to WHETHER.

        Consent is honoured, not bypassed — this fires ONLY on the person's own
        confirming words, and the framework's own rule is that refusing to
        write down a decision the person has stated "is the one failure the
        record exists to prevent".

        The `accepted_cost` ground is attached when — and only when — the
        stance clearly IS one pole of one mapped tension. That is a matching
        question with a verifiable answer, and the cost then follows by
        DEFINITION rather than by judgement: the price of choosing a side is
        that side's own minus (chose T → T-), because a plus is a goal or an
        obligation, i.e. something to do, never a price. No match means no
        ground: a wrong `accepted_cost` is worse than none, since it makes the
        record claim the person accepted a price they never faced and sends the
        later re-audit to reassure them with the wrong risk. `adopted_pathway`
        is never guessed here at all — it needs a transformation the wheel may
        not have, so it stays the model's own path.

        Fail-soft in every direction: no exception here may affect the reply
        the person already received.
        """
        if self._recorded_decision_this_turn():
            return
        try:
            from dialectical_framework.concerns.decision_confirmation_check import \
                DecisionConfirmationCheck
            from dialectical_framework.concerns.record_decision import \
                RecordDecision

            check = DecisionConfirmationCheck()
            verdict = await check.resolve(
                user_message=user_message,
                assistant_message=assistant_message,
            )
            if verdict is None or not verdict.is_recordable:
                return

            # The person is closing. Build the pathways their decision is
            # supposed to rest on, if the model never did. Contained in its own
            # guard: a richer grounding is worth attempting, never worth losing
            # the record over — that failure mode is the one this whole method
            # exists to prevent.
            try:
                await self._ensure_pathways_before_closing()
            except Exception:
                logger.exception(
                    "Pathway construction before closing failed (fail-soft); "
                    "recording the decision on tensions alone"
                )

            recorder = RecordDecision()
            decision_hash = await recorder.resolve(
                question=verdict.question,
                stance=verdict.stance,
                rationale=verdict.rationale,
                grounds=self._accepted_cost_ground(verdict),
                principal=self._principal,
            )
            if decision_hash:
                logger.info(
                    "Recorded a decision the person confirmed but the model "
                    "left unrecorded: [[%s]]",
                    decision_hash[:7],
                )
        except Exception:
            logger.exception("Decision confirmation repair failed (fail-soft)")

    async def _ensure_pathways_before_closing(self) -> None:
        """Build pathways for unwoven perspectives when a decision is closing.

        The engine prompt already states the rule: "A decision closes on
        pathways, not on tensions alone... Without pathways there is no paired
        recipe to adopt, no trap version of the choice to name, and the counsel
        at the closing turn is a single tension restated with more emphasis."
        The model does not obey it. Measured over every saved bench run,
        `explore` fires in 6 of 55 weak-tier runs (11%) against 17 of 25 at the
        strong tier (68%, Fisher p ~ 5e-07) — and in the 6 cells of
        `claim2-weak-r7-readside` it fired ZERO times while `anchor` built 5-7
        tensions per cell. Those runs closed decisions over a graph with no
        nexus, no cycle, no wheel, no transformation and no synthesis: the
        framework's actual differentiator never executed, so the arm was a
        prompted model with tetrads bolted on. A direct probe confirmed the weak
        tier CAN call `explore` unprompted when a turn asks for a causal map, so
        this is election, not capability — the same failure mode, and the same
        remedy, as `_repair_unrecorded_decision` itself.

        Scope is deliberately narrow: this fires only once a decision has been
        confirmed (the caller already established that), never mid-exploration.
        It builds what the person's own closing entitles them to and nothing
        more. Weaving obeys `run_exploration`'s existing per-call perspective
        cap, so a wide graph is woven across successive closings rather than in
        one latency spike.

        Fail-soft and silent to the person: their reply has already been
        delivered, and a pathway they never asked about must not surface as an
        error. What it changes is the RECORD — `adopted_pathway` becomes
        available, the re-audit has a recipe to reassure from, and the synthesis
        exists.
        """
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        repo = PerspectiveRepository()
        perspectives = repo.find_all_active()
        unwoven = [
            p
            for p in perspectives
            if p.hash and not repo.is_in_use_by_cycle(p)
        ]
        # One tension has no arrangement to enumerate: a wheel needs a second
        # opposition to be a pathway rather than a restatement. Below two, the
        # honest state IS "tensions only".
        if len(unwoven) < 2:
            return

        logger.info(
            "Decision closing over %d unwoven perspective(s) — building "
            "pathways the engine prompt requires and the model skipped",
            len(unwoven),
        )
        await run_exploration(
            perspective_hashes=[p.hash for p in unwoven],
            intent=(
                "The person is closing a decision on these tensions. Build the "
                "causal arrangements so the decision rests on a pathway."
            ),
            nexus_hash=self._nexus_hash,
        )

    @staticmethod
    def _accepted_cost_ground(verdict) -> list | None:
        """Resolve the matched pole into the minus aspect it costs.

        Returns None (no ground) unless the whole chain holds: a matched
        polarity that still exists, a recognised side, and a committed minus
        aspect on the perspective built over it. Every break is a non-event,
        not an error — the record is worth having without the ground, and a
        half-resolved ground is worth less than none.

        The PERSPECTIVE is grounded too, as a plain ground alongside the cost.
        Two reasons, both measured. (1) A minus aspect is shared across
        perspectives whenever `commit()` dedup finds the same wording, and an
        ordinary session anchors several adjacent tensions on one theme: 7 of 10
        minus aspects were shared on the live anchor path, which is why
        `claim2-weak-r5` recorded 5 risk-grounded costs and rendered 0 condition
        clauses — `accepted_cost_condition` cannot tell which tetrad to read
        without being told, and guessing would attribute the price to a tension
        the person never decided on. The perspective ground is exactly that
        telling. (2) It is true independently of the rendering: the tension the
        person resolved is part of what the decision rests on, and the aspect
        alone names the price without naming the choice it was the price of.
        """
        position = verdict.chosen_cost_position
        if not position:
            return None
        try:
            from dialectical_framework.concerns.record_decision import GroundLink
            from dialectical_framework.graph.repositories.perspective_repository import \
                PerspectiveRepository

            wanted = verdict.chosen_polarity_hash.strip()
            for pp in PerspectiveRepository().find_all_active():
                # RelationshipManager.get() yields (node, relationship).
                polarity_result = pp.polarity.get()
                if not polarity_result:
                    continue
                polarity, _ = polarity_result
                if not polarity.hash or not polarity.hash.startswith(wanted):
                    continue
                aspects = getattr(pp, position).all()
                for aspect, _rel in aspects:
                    if aspect.is_committed:
                        grounds = [
                            GroundLink(hash=aspect.hash, role="accepted_cost")
                        ]
                        if pp.is_committed:
                            grounds.append(GroundLink(hash=pp.hash, role=None))
                        return grounds
        except Exception:
            logger.exception("Accepted-cost ground resolution failed (fail-soft)")
        return None

    def _recorded_decision_this_turn(self) -> bool:
        """Did `record_decision` already run, successfully, on this turn?

        A FAILED call still needs the repair — an in-band refusal (empty
        stance, dangling ground hash) leaves the person believing in a record
        that does not exist, which is the same defect by a different route.
        Read-only tools contribute no report and are simply absent here.
        """
        for result in self._conversation.last_tool_results:
            if result.tool_name != "record_decision":
                continue
            report = result.report
            if report is None or report.ok:
                return True
        return False

    async def _render_pending_context(self) -> None:
        """One-shot deferred render of the scoped Current Understanding dump
        (scoped construction without a precomputed dialectical_context).

        One-shot on SUCCESS — a transient failure (DB blip) keeps the flag
        set so the next turn retries, instead of leaving the whole session
        with a prompt that claims rich understanding over an empty slot.
        """
        if not self._pending_context_render:
            return
        try:
            from dialectical_framework.concerns.dialectical_context import \
                DialecticalContext

            context = await DialecticalContext(
                nexus_hash=self._nexus_hash
            ).resolve()
            self._conversation.set_system_prompt(
                self._build_system_prompt(self._app_preamble, context)
            )
            self._pending_context_render = False
        except ValueError:
            # Nexus disappeared — not transient, don't retry forever.
            self._pending_context_render = False
            logger.exception("Deferred dialectical context render failed")
        except Exception:
            # Fail-soft this turn; retry next turn. The model still reaches
            # graph state through sync meanwhile.
            logger.exception("Deferred dialectical context render failed")

    @property
    def messages(self) -> list:
        return self._conversation._messages


def _build_tools(principal: str = "human") -> list:
    from dialectical_framework.agents.advisor.tools.anchor import anchor
    from dialectical_framework.agents.advisor.tools.deepen import deepen
    from dialectical_framework.agents.advisor.tools.explore import explore
    from dialectical_framework.agents.advisor.tools.ingest import ingest
    from dialectical_framework.agents.advisor.tools.record_decision import \
        build_record_decision
    from dialectical_framework.agents.advisor.tools.sync import sync
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest
    from dialectical_framework.agents.orchestrator.tools.discard import \
        discard

    return [
        ingest,
        anchor,
        explore,
        deepen,
        build_record_decision(principal),
        sync,
        inspect_node,
        read_digest,
        discard,
    ]


def _build_scoped_tools(nexus_hash: str, principal: str = "human") -> list:
    from dialectical_framework.agents.advisor.tools.scoped import \
        build_scoped_tools

    return build_scoped_tools(nexus_hash, principal)
