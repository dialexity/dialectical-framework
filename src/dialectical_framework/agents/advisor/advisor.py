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
        `tests/e2e/README.md`), because no amount of prompt text makes an
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
        later re-audit to reassure them with the wrong risk.

        `adopted_pathway` used to be excluded on the same reasoning — "it needs
        a transformation the wheel may not have, so it stays the model's own
        path". That was true only while the seam did not build wheels. It now
        does (`_ensure_pathways_before_closing`), so the transformation it needs
        is one it just created and holds the hash of. Measured in
        `claim2-weak-r16-floor`: 6/6 A2 cells closed with 12-42 pathways on the
        graph and 0/6 named one, because the seam wove the artefact and then
        recorded a decision that pointed at nothing. It grounds ONE pathway (the
        role is singular) and stays honest about what it knows: that a pathway
        exists for this closing, not which one the person would pick. The
        model's own `record_decision` names its own with the conversation in
        view; this is the floor under that, not a replacement for it.

        Fail-soft in every direction: no exception here may affect the reply
        the person already received.
        """
        if self._recorded_decision_this_turn():
            # The record is written, so there is nothing to repair — but a
            # decision closing IS the trigger for pathways, and the model
            # recording one is stronger evidence of closing than any classifier
            # verdict. Measured across every saved A2 cell, `record_decision`
            # ran WITHOUT `explore` in 50 of them (against 48 with both): gating
            # pathways on the repair firing would have skipped the single
            # largest population of decisions closed on tensions alone.
            try:
                pathways = await self._ensure_pathways_before_closing()
            except Exception:
                logger.exception(
                    "Pathway construction after a recorded decision failed "
                    "(fail-soft)"
                )
                return
            # This branch used to stop here, on the belief that
            # "`adopted_pathway` cannot be attached to a record already
            # written". That belief was wrong, and it was the whole reason this
            # was called "the weaker half of the seam". GROUNDED_IN is an
            # ANALYTICAL edge (`grounded_in_relationship.py`: "connects to
            # already-committed nodes and does not affect hashes"), and
            # `Decision`'s own docstring shows the order — `decision.commit()`
            # THEN `decision.grounds.connect(...)`. Grounding a committed
            # decision is the designed path, not a workaround.
            self._attach_adopted_pathway(pathways)
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
            pathways: list[str] = []
            try:
                pathways = await self._ensure_pathways_before_closing()
            except Exception:
                logger.exception(
                    "Pathway construction before closing failed (fail-soft); "
                    "recording the decision on tensions alone"
                )

            # This branch writes the record itself, so the pathway it just
            # built goes in as a ground at commit time — the strong half.
            grounds = self._accepted_cost_ground(verdict) or []
            grounds += self._adopted_pathway_grounds(pathways)

            recorder = RecordDecision()
            decision_hash = await recorder.resolve(
                question=verdict.question,
                stance=verdict.stance,
                rationale=verdict.rationale,
                grounds=grounds or None,
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

    async def _ensure_pathways_before_closing(self) -> list[str]:
        """Build pathways for unwoven perspectives when a decision is closing.

        Returns the Transformation hashes now on the deepened wheel — the
        pathways this closing is entitled to ground on. Empty when there was
        nothing to weave or the exploration produced none.

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

        Scope is deliberately narrow: this fires only on a closing — either the
        model recorded a decision this turn, or the confirmation check found one
        in the person's own words — never mid-exploration. It builds what the
        person's own closing entitles them to and nothing more. Weaving obeys
        `run_exploration`'s existing per-call perspective cap, so a wide graph is
        woven across successive closings rather than in one latency spike.

        BOTH closings need it, and the model-recorded branch is the larger one:
        across every saved A2 cell, `record_decision` ran without `explore` 50
        times against 48 with both. Both branches now ground the pathway they
        build — the already-recorded one by connecting a GROUNDED_IN edge to the
        committed Decision (an analytical edge; hashes are unaffected), the
        repair branch by passing it to `RecordDecision` at commit time.

        Fail-soft and silent to the person: their reply has already been
        delivered, and a pathway they never asked about must not surface as an
        error. What it changes is the RECORD — `adopted_pathway` becomes
        available, the re-audit has a recipe to reassure from, and the synthesis
        exists.
        """
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration_detailed
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        repo = PerspectiveRepository()
        perspectives = repo.find_all_active()
        unwoven = [
            p
            for p in perspectives
            if p.hash and not repo.is_in_use_by_cycle(p)
        ]
        # One tension is enough. This guard used to be `< 2` on the reasoning
        # that "a wheel needs a second opposition to be a pathway rather than a
        # restatement" — which contradicts the framework's own model.
        # `PerspectiveCombination` treats a single PP as the circular-causality
        # BASE CASE (W(1)=1: one Cycle, one Wheel, 2 edges, 1 pair), and
        # `docs/theory/generative-rules.md` Rule 8 says layer-1 wheels are what
        # covers the within-tetrad diagonals. Measured directly rather than
        # argued (`tests/test_single_perspective_explore_real_llm.py`, weak tier,
        # real provider): a 1-PP exploration yields 1 cycle, 1 DEEPENED wheel,
        # 6 transformations, 6 named Ac+/Re+ pathways and 1 synthesis.
        #
        # The cost of the old floor, measured in `claim2-weak-r15-voice`: 3 of 6
        # A2 cells called `anchor` exactly once, so the seam saw one unwoven
        # perspective and returned. Those cells closed on `woven=0
        # transformations=0`, and the report flagged them as the framework
        # failing to arrange what it had mapped. Split by this state, the judged
        # mean was -0.69 unwoven against -0.25 woven over 36 scores each — the
        # single largest identified component of A2's remaining loss, and it was
        # this `return`, not the model.
        if not unwoven:
            # Nothing to weave is NOT nothing to ground. The model may have
            # called `explore` itself — that is the cell this seam wants to see
            # — and then the pathways already exist and the closing is still
            # entitled to one. Measured in `claim2-weak-r16-floor`: 6/6 A2 cells
            # closed with 12-42 transformations on the graph and 0/6 carried an
            # `adopted_pathway` ground, INCLUDING the cell that called `explore`
            # at t2 and `record_decision` at t5 with 30 pathways in hand. An
            # early `return` here would keep that exact cell ungrounded.
            return self._existing_pathway_hashes()

        logger.info(
            "Decision closing over %d unwoven perspective(s) — building "
            "pathways the engine prompt requires and the model skipped",
            len(unwoven),
        )
        _report, built = await run_exploration_detailed(
            perspective_hashes=[p.hash for p in unwoven],
            intent=(
                "The person is closing a decision on these tensions. Build the "
                "causal arrangements so the decision rests on a pathway."
            ),
            nexus_hash=self._nexus_hash,
        )
        # The per-call perspective cap can defer some of `unwoven`, and a wheel
        # that reuses every transformation reports them as existing rather than
        # new — either way `transformation_hashes` is "what is now on the
        # deepened wheel", which is what a ground needs. Falling back to the
        # graph covers an exploration that built nothing new on a graph that
        # already had pathways.
        return built or self._existing_pathway_hashes()

    def _existing_pathway_hashes(self) -> list[str]:
        """Transformation hashes already on this session's graph, if any.

        Read-only and fail-soft: a closing that cannot see a pathway is
        recorded without one, exactly as before. Scoped to the pinned nexus in
        counsel mode; unscoped sessions have a single Case's worth of graph, so
        every transformation in scope belongs to the conversation that built it.
        """
        try:
            from dialectical_framework.graph.repositories.nexus_repository import \
                NexusRepository
            from dialectical_framework.graph.repositories.transformation_repository import \
                TransformationRepository

            tr_repo = TransformationRepository()
            nexus_repo = NexusRepository()
            nexuses: list = []
            if self._nexus_hash:
                # Prefix-tolerant: the pinned hash may be a short hash.
                pinned = nexus_repo.find_by_hash_prefix(self._nexus_hash)
                nexuses = [pinned] if pinned else []
            else:
                nexuses = nexus_repo.find_all()
            hashes: list[str] = []
            for nexus in nexuses:
                hashes += [
                    tr.hash for tr in tr_repo.find_by_nexus(nexus) if tr.hash
                ]
            # Sorted for the same reason the explore report sorts: a ground
            # picked from an arbitrary DB order is not reproducible.
            return sorted(set(hashes))
        except Exception:
            logger.exception("Pathway lookup for grounding failed (fail-soft)")
            return []

    def _adopted_pathway_grounds(self, pathway_hashes: list[str]) -> list:
        """One `adopted_pathway` ground, or none.

        ONE, deliberately: the role names "the pathway adopted as their ongoing
        recipe", singular — a decision has one recipe, and grounding six would
        make the re-audit's "here is the recipe you adopted" a menu again.
        The first by sorted hash is an arbitrary-but-stable pick, and it is
        honest about what it is: the seam knows a pathway exists for this
        closing, not which one the person would choose. The model's own
        `record_decision` path still names its own, and that one is chosen with
        the conversation in view — this is the floor, not the ceiling.
        """
        if not pathway_hashes:
            return []
        try:
            from dialectical_framework.concerns.record_decision import GroundLink

            return [
                GroundLink(hash=pathway_hashes[0], role="adopted_pathway")
            ]
        except Exception:
            logger.exception("Adopted-pathway ground construction failed")
            return []

    def _attach_adopted_pathway(self, pathway_hashes: list[str]) -> None:
        """Ground an ALREADY-recorded decision on a pathway built after it.

        The record is committed by the time this runs, which the seam long
        treated as fatal. It is not: GROUNDED_IN is analytical
        (`grounded_in_relationship.py` — "connects to already-committed nodes
        and does not affect hashes"), and `Decision`'s docstring shows
        `commit()` preceding `grounds.connect(...)` as the normal lifecycle.

        Targets the decision recorded THIS TURN — the one whose closing built
        these pathways. Fail-soft and silent: the person's reply is already
        delivered, and a decision grounded on a cost but not a recipe is still
        a decision.
        """
        if not pathway_hashes:
            return
        try:
            from dialectical_framework.graph.nodes.transformation import \
                Transformation
            from dialectical_framework.graph.relationships.grounded_in_relationship import \
                GroundedInRelationship
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            decision = self._decision_recorded_this_turn()
            if decision is None:
                return
            # `connect` deduplicates only direction="any" edges, so a repeated
            # closing in one session would otherwise add a second identical
            # GROUNDED_IN. Check first (CLAUDE.md, Idempotent connect).
            for existing, rel in decision.grounds.all():
                if getattr(rel, "role", None) == "adopted_pathway":
                    return
            repo = NodeRepository()
            target = repo.find_by_hash(pathway_hashes[0], node_type=Transformation)
            if target is None:
                return
            decision.grounds.connect(
                target,
                relationship=GroundedInRelationship(role="adopted_pathway"),
            )
            logger.info(
                "Grounded already-recorded decision [[%s]] on the pathway its "
                "closing built: [[%s]]",
                (decision.hash or "")[:7],
                pathway_hashes[0][:7],
            )
        except Exception:
            logger.exception(
                "Attaching an adopted_pathway to a recorded decision failed "
                "(fail-soft)"
            )

    def _decision_recorded_this_turn(self):
        """The Decision node `record_decision` committed on this turn, if any.

        Read from the tool's own report artifact (`decision_hash`) rather than
        by querying for the newest Decision: a session can record more than one
        decision, and "most recent in the DB" is a guess where the report is a
        fact.
        """
        from dialectical_framework.graph.nodes.decision import Decision
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        for result in self._conversation.last_tool_results:
            if result.tool_name != "record_decision":
                continue
            report = result.report
            if report is None or not report.ok:
                continue
            decision_hash = (report.artifacts or {}).get("decision_hash")
            if not decision_hash:
                continue
            return NodeRepository().find_by_hash(
                str(decision_hash), node_type=Decision
            )
        return None

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
