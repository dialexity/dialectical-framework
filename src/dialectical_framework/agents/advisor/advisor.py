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
import time
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
from dialectical_framework.agents.turn_timing import TurnTiming

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

    The Current Understanding dump is re-read from the graph on EVERY turn, by
    the host loop rather than at the model's discretion — see
    `_refresh_context`. The system prompt is only REWRITTEN when that dump
    actually changed, so a turn that mutated nothing keeps its provider-side
    prefix cache. `dialectical_context` seeds the slot for turn 1; it does not
    freeze it. This replaces a one-shot render whose staleness was the read-side
    half of the archive's primary defect (14 of 18 first sessions built 390
    transformations while the prompt still claimed an empty graph).

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
        # The context currently rendered into the system prompt. A
        # construction-time `dialectical_context` SEEDS this (saving the turn-1
        # read); `_refresh_context` owns it from then on and re-renders every turn.
        # `None` means "nothing rendered yet", which is distinct from a rendered
        # empty graph and must stay so — otherwise turn 1 skips its first read.
        self._last_context: Optional[str] = dialectical_context
        # Cleared only when the pinned nexus proves unresolvable — see
        # `_refresh_context`. Not a host knob: a turn that must see the graph
        # cannot be configured into not looking.
        self._context_refresh_enabled = True
        # Where the last turn's seconds went, split at the point the reply was
        # handed to the person. None until the first turn completes.
        self.last_turn_timing: Optional[TurnTiming] = None
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
            # Before submit, so this turn's prompt reflects what the LAST turn
            # wrote. The person waits for it, so it counts against the reply path.
            context_render_s = await self._refresh_context()
            result = await self._conversation.submit(ChatResponse, user_message)
            reply_path_s = context_render_s + self._conversation.last_submit_seconds
            repair_started = time.monotonic()
            await self._repair_unrecorded_decision(user_message, result.message)
            self._record_turn_timing(
                reply_path_s,
                time.monotonic() - repair_started,
                context_render_s=context_render_s,
            )
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            # Before the stream, for the same reason as in `chat`: this turn's
            # prompt must reflect what the last turn wrote.
            context_render_s = await self._refresh_context()
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
            reply_path_s = context_render_s + self._conversation.last_submit_seconds
            # After the stream, so the text is on screen before the repair runs.
            # NOT the same as being free: this generator cannot finish until the
            # repair does, and `chat` is worse still — it holds its return value
            # for the whole repair. That comment used to claim `chat` carried the
            # same guarantee, and it never did; the repair was measured at 387.7s
            # on a turn whose reply took 14.3s. Which is why the repair must stay
            # BOUNDED — see `_ensure_pathways_before_closing`, which reads the
            # graph and no longer builds on it.
            repair_started = time.monotonic()
            await self._repair_unrecorded_decision(user_message, reply)
            self._record_turn_timing(
                reply_path_s,
                time.monotonic() - repair_started,
                context_render_s=context_render_s,
            )

    def _record_turn_timing(
        self,
        reply_path_s: float,
        off_path_s: float,
        *,
        context_render_s: float = 0.0,
    ) -> None:
        """Publish where this turn's seconds went.

        The split matters more than either number: `reply_path_s` is time the
        person spent waiting, `off_path_s` is time spent after they had their
        reply. Those are the same second to a cost budget and opposite seconds to
        a UX decision, and until this existed only the sum was ever recorded —
        at the granularity of a whole multi-session cell, which is why
        `probe_reply_path_latency.py` had to regress the split out of 187 runs
        instead of reading it.

        Tool rounds come from the facilitator rather than being re-timed here:
        it owns the loop, and a second clock around the same awaits could only
        disagree with the first. Retry waste comes from there for the same
        reason — the sleeps happen many frames below this method.
        """
        retries = self._conversation.last_submit_retries
        self.last_turn_timing = TurnTiming(
            reply_path_s=reply_path_s,
            off_path_s=off_path_s,
            tool_rounds=tuple(self._conversation.last_tool_rounds),
            context_render_s=context_render_s,
            retry_seconds=retries.wasted_s,
            retry_count=retries.count,
        )

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
        """The pathways this closing may ground on — READ from the graph, not built.

        Returns Transformation hashes already in scope. Empty when the graph
        holds none.

        WHY THIS NO LONGER BUILDS
        =========================
        It used to call `run_exploration_detailed` for every unwoven
        perspective, and that call sits on the person's wait. `chat` awaits this
        repair before returning the reply; `chat_stream` delivers the text first
        but still cannot end the turn without it. So "off the reply path" was
        true of the reply TEXT and false of the person.

        Measured on a real provider (`timing-check-building`, weak tier, 16
        turns, per-turn timing rather than regression): two turns that made ZERO
        tool calls cost 141.9s and 402.0s, of which 127.7s and 387.7s were this
        method. Both landed on the turn immediately before the closing — the one
        turn in a conversation that has to feel exact.

        WHAT GIVING THAT UP COSTS, STATED PLAINLY
        =========================================
        Building here bought something real, and this surrenders it. The engine
        prompt's rule stands: "A decision closes on pathways, not on tensions
        alone... Without pathways there is no paired recipe to adopt, no trap
        version of the choice to name, and the counsel at the closing turn is a
        single tension restated with more emphasis." The model does not obey it
        — `explore` fires in 6 of 55 weak-tier runs (11%) against 17 of 25 at
        the strong tier (68%, Fisher p ~ 5e-07). Split by whether the graph was
        woven at closing (`claim2-weak-r15-voice`), the judged mean was -0.25
        woven against -0.69 unwoven over 36 scores each: the single largest
        identified component of A2's remaining loss.

        So the construction is not unnecessary — it is in the wrong PLACE. It
        belongs off the turn entirely, and the architecture already permits
        that: GROUNDED_IN is analytical, so a Decision committed now can be
        grounded on a pathway built later (`_attach_adopted_pathway`; and
        `Decision`'s own docstring shows `commit()` preceding
        `grounds.connect(...)`). Until that deferral exists, an unwoven closing
        is LOGGED rather than quietly accepted. Deliberately a log and not a
        queue: a queue nothing drains is this archive's signature defect, so
        there is a visible gap instead of a fake mechanism.

        Still `async` though it now awaits nothing — the deferral restores awaits
        here, and churning both call sites twice would obscure that.

        Fail-soft throughout: a closing that cannot see a pathway is recorded
        without one, exactly as before this method existed.
        """
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        try:
            repo = PerspectiveRepository()
            unwoven = [
                p
                for p in repo.find_all_active()
                if p.hash and not repo.is_in_use_by_cycle(p)
            ]
        except Exception:
            logger.exception("Unwoven-perspective lookup failed (fail-soft)")
            unwoven = []

        # Read regardless of `unwoven`: nothing to weave is NOT nothing to
        # ground. Measured in `claim2-weak-r16-floor` — 6/6 A2 cells closed with
        # 12-42 transformations on the graph and 0/6 carried an
        # `adopted_pathway`, including the cell that called `explore` itself.
        pathways = self._existing_pathway_hashes()
        if unwoven:
            logger.warning(
                "Decision closing over %d unwoven perspective(s); grounding on "
                "%d existing pathway(s) rather than building. The engine prompt "
                "requires pathways at a closing and the model skipped them, so "
                "this closing rests on less than it is entitled to — pathway "
                "construction is deferred off the turn, not performed here.",
                len(unwoven),
                len(pathways),
            )
        return pathways

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

    async def _refresh_context(self) -> float:
        """Re-read the graph into the system prompt, EVERY turn. Returns seconds.

        This used to be a one-shot render, and the one-shot was the read-side
        half of this archive's primary defect. Two ways it went wrong:

        1. Unscoped (the standalone Advisor) never rendered at all, so the prompt
           held `EMPTY_UNDERSTANDING` for the whole session while the agent's own
           `anchor`/`ingest`/`explore` calls wrote to the graph. Measured:
           **14 of 18 first sessions built 390 transformations against an empty
           slot for all 8 turns** (`probe_readside_reach`). Depth then failed to
           predict the score in either direction (corr -0.107 over 36 cells) —
           a null, which is exactly what unread structure predicts.
        2. Scoped rendered once, so anything built on turn 3 was invisible from
           turn 4 on.

        Host-driven on purpose. The model has `sync` and could re-read whenever it
        liked, and across 55 weak-tier runs it elected `explore` 6 times — no
        amount of prompt text makes an elective call reliable. A turn that must
        see the graph cannot depend on the model choosing to look.

        A construction-time `dialectical_context` is therefore a SEED, not a lock:
        it fills the slot before turn 1 and spares the turn-1 prompt REWRITE when
        the graph has not moved since (the read still happens — that is what
        detects movement). The refresh owns the slot from then on. Locking it would
        have left the bench exactly half-fixed, since the driver passes a
        session-start snapshot on returning sessions only (and nothing on first
        sessions), then holds it static for all 8 turns of that session.

        On the prompt-caching objection this reverses: rewriting a system prompt
        does cost provider-side prefix caching, which is why the rewrite is gated
        on the rendered text actually CHANGING. A turn that mutated nothing keeps
        its cache. A turn that built structure loses it — and that turn already
        spent tens of seconds inside the tool that built it, so the miss is small
        against a model that can finally see its own work. The old rule also held
        that history already carries this ("tool results + sync"); history carries
        the tool's REPORT, not the derived dump — indices (T1/A1), scores,
        validation flags and suppression counts appear nowhere else, and a prompt
        asserting EMPTY_UNDERSTANDING actively contradicts the history it sits on.

        Cheap enough to do per turn: `DialecticalContext.resolve()` is repository
        reads and string assembly with no LLM call in it, against a reply path
        whose median tool round is 42s. Not free, though — so the cost is returned
        and recorded as `TurnTiming.context_render_s` rather than assumed small.
        """
        if not self._context_refresh_enabled:
            return 0.0

        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        started = time.monotonic()
        try:
            context = await DialecticalContext(
                nexus_hash=self._nexus_hash
            ).resolve()
        except ValueError:
            # The pinned nexus is gone. Not transient and not recoverable by
            # retrying, so stop re-reading it every turn — but keep the last good
            # prompt rather than reverting to EMPTY_UNDERSTANDING, which would
            # throw away understanding the conversation has already been given.
            self._context_refresh_enabled = False
            logger.exception(
                "Dialectical context refresh disabled: pinned nexus unresolvable"
            )
            return time.monotonic() - started
        except Exception:
            # Fail-soft: this turn runs on the previous turn's prompt, and the
            # next turn tries again. The model still reaches graph state through
            # `sync` meanwhile.
            logger.exception("Dialectical context refresh failed (fail-soft)")
            return time.monotonic() - started

        # Idempotent by comparing the RENDERED text, not by trusting a
        # graph-version signal that does not exist. A turn that changed nothing
        # must not churn the system prompt: re-setting an identical prompt buys
        # nothing and needlessly disturbs provider-side prefix caching.
        if context != self._last_context:
            self._conversation.set_system_prompt(
                self._build_system_prompt(self._app_preamble, context)
            )
            self._last_context = context
        return time.monotonic() - started

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
