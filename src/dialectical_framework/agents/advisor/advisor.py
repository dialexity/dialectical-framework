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

import asyncio
import logging
import time
from contextlib import aclosing
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
from dialectical_framework.protocols.has_config import SettingsAware

logger = logging.getLogger(__name__)


class ChatResponse(BaseModel):
    """Response from the advisor chat."""

    message: str = Field(description="The assistant's response message")


class Advisor(SettingsAware):
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

    # How many times the off-turn weave may re-call exploration before giving
    # up. Each round weaves at most `advisor_max_perspectives_per_exploration`
    # (2), so 4 rounds covers the 4-perspective ceiling applications actually
    # use with one round of slack. Not a latency budget — there is no turn
    # waiting on this — but a spin guard: see `_weave_unwoven_perspectives`.
    _MAX_WEAVE_ROUNDS = 4

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
        # Pathway construction moved OFF the turn — see
        # `_schedule_pathway_construction`. The task reference is held to keep
        # the task from being garbage-collected mid-flight (asyncio only holds a
        # weak reference), and it is the single-flight guard: one weave at a
        # time, so this seam can never race itself. Decisions closed while a
        # weave is in flight queue here and the running task drains them, which
        # is why the queue is a field and not a local.
        self._deferred_pathway_task: Optional[asyncio.Task] = None
        self._decisions_awaiting_pathway: list[str] = []
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
            # Cleared before the work, not after it: `_record_turn_timing` is the
            # LAST thing this turn does, so anything that raises before it would
            # otherwise leave the previous turn's split standing as if it were
            # this one's. A reader cannot tell a stale figure from a fresh one;
            # they can tell None.
            self.last_turn_timing = None
            # Before everything: the previous turn may have left a weave running,
            # and ONE WRITER PER SID is a hard contract (docs/agents.md) — two
            # concurrent writers on one sid produce duplicate nodes and
            # half-built containers. Usually free, because the person's
            # think-time already absorbed it.
            deferred_wait_s = await self._settle_deferred_work()
            # Before submit, so this turn's prompt reflects what the LAST turn
            # wrote. The person waits for it, so it counts against the reply path.
            context_render_s = await self._refresh_context()
            result = await self._conversation.submit(ChatResponse, user_message)
            reply_path_s = (
                deferred_wait_s
                + context_render_s
                + self._conversation.last_submit_seconds
            )
            repair_started = time.monotonic()
            await self._repair_unrecorded_decision(user_message, result.message)
            self._record_turn_timing(
                reply_path_s,
                time.monotonic() - repair_started,
                context_render_s=context_render_s,
                deferred_wait_s=deferred_wait_s,
            )
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        """Stream one turn's events.

        **The caller owes this generator a CLOSE, not merely a `break`.** Every
        `chat_stream` in the tree is an async generator wrapping another one, and an
        async generator's cleanup runs when it is CLOSED — so a host that stops
        iterating leaves this frame suspended at its `yield`, and the whole chain
        below it suspended with it. What is deferred is the turn's recorded seconds
        (`last_submit_seconds`, which a newer turn may have claimed the slot for by
        the time the collector arrives) and the provider's open HTTP response. There
        is no way for the library to reach up and fix that: only the outermost
        consumer can close the outermost generator. So on disconnect, do

            async with aclosing(advisor.chat_stream(msg)) as events:
                async for event in events:
                    ...

        or hand it to a host that closes for you — an ASGI server closes the
        generator behind an SSE response when the client goes away. A bare
        `async for` with a `break` is the one shape that leaks.
        """
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            self.last_turn_timing = None  # see `chat` — a crashed turn reports nothing
            # See `chat`: the one-writer-per-sid contract, not an optimisation.
            deferred_wait_s = await self._settle_deferred_work()
            # Before the stream, for the same reason as in `chat`: this turn's
            # prompt must reflect what the last turn wrote.
            context_render_s = await self._refresh_context()
            # The reply comes from ResponseComplete because that is the DURABLE
            # one — text yielded before a ToolStart is the model saying what it
            # is about to do, and only the last segment is counsel. This is not
            # a claim that the person waited for it: on the ordinary turn
            # `event.streamed` is True and `message` is byte-for-byte the deltas
            # they already read, which is the point of streaming at all.
            reply = ""
            # `aclosing`, not a bare `async for`: unwinding an `async for` does not
            # close what it iterates, so without this, `submit_stream`'s cleanup on
            # the ABANDONED exit — the turn's seconds, and letting go of the
            # provider's connection — waits for the collector, by which time a newer
            # turn may have claimed the slot and the seconds are lost for good. (The
            # crashed and completed exits need none of this: the exception, or
            # StopAsyncIteration, unwinds `submit_stream` on its own.)
            #
            # This link only fires when THIS generator is closed, which is the
            # caller's job — see the docstring. It is still worth writing: it makes
            # the chain complete from the host's close downward, and it is the half
            # that is ours to get right.
            async with aclosing(
                self._conversation.submit_stream(ChatResponse, user_message)
            ) as rounds:
                async for event in rounds:
                    if isinstance(event, ResponseComplete):
                        reply = event.message
                    yield event
            reply_path_s = (
                deferred_wait_s
                + context_render_s
                + self._conversation.last_submit_seconds
            )
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
            first_delta = self._conversation.last_submit_first_delta_s
            self._record_turn_timing(
                reply_path_s,
                time.monotonic() - repair_started,
                context_render_s=context_render_s,
                deferred_wait_s=deferred_wait_s,
                # Same construction as `reply_path_s` above and for the same
                # reason: the person's wait starts before the submit does, so
                # everything they waited through belongs inside the figure. None
                # when nothing streamed, which is not the same as zero.
                first_delta_s=(
                    deferred_wait_s + context_render_s + first_delta
                    if first_delta is not None
                    else None
                ),
            )

    def _record_turn_timing(
        self,
        reply_path_s: float,
        off_path_s: float,
        *,
        context_render_s: float = 0.0,
        deferred_wait_s: float = 0.0,
        first_delta_s: Optional[float] = None,
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
            deferred_wait_s=deferred_wait_s,
            retry_seconds=retries.wasted_s,
            retry_count=retries.count,
            first_delta_s=first_delta_s,
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
            # ...and what the graph does NOT hold yet is built off the turn and
            # attached when it lands. Both, not either: the existing pathway is
            # grounded NOW so a person who never returns still has a recipe on
            # the record, and the weave upgrades what it can afterwards. The
            # hash comes back from the attach so the decision is resolved once,
            # inside its own fail-soft guard.
            self._schedule_pathway_construction(
                self._attach_adopted_pathway(pathways)
            )
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
                # Scheduled only with a hash in hand: this branch's record is
                # the thing the deferred weave grounds, and a weave with nothing
                # to attach to is work spent on no one's behalf.
                self._schedule_pathway_construction(str(decision_hash))
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
        `grounds.connect(...)`).

        THAT DEFERRAL NOW EXISTS — see `_schedule_pathway_construction`, which
        the two callers invoke after this returns. This method's job is
        therefore only the READ, and an unwoven closing is no longer a logged
        gap: it grounds on what is there now and is grounded again when the
        off-turn weave lands. The log below stays, because "the model skipped
        the pathways" remains the finding even once the seam covers for it.

        The queue that drains is not a contradiction of the older note here
        ("a queue nothing drains is this archive's signature defect"): the
        deferral starts its own consumer in the same call, and
        `wait_for_deferred_work` is a documented host obligation, so there is no
        state waiting on a drain that might never be written.

        Still `async` though it awaits nothing: both callers are async, the
        signature is stable, and the alternative churns them for no gain.

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

    async def _settle_deferred_work(self) -> float:
        """Let the previous turn's off-turn work finish, and say what it cost.

        Called at the TOP of every turn, and the reason is the one-writer-per-sid
        contract rather than tidiness: the deferred weave writes to the graph, so
        a turn that starts while it runs is a second concurrent writer on one
        sid, which `docs/agents.md` records as producing duplicate nodes,
        duplicated directed edges and half-built containers. That contract is not
        enforced in code, so the framework must not be the one to break it.

        Runs BEFORE `_refresh_context`, which is a second benefit for free: the
        turn's prompt then shows the wheel the weave just built, so the model
        sees its own pathways instead of the graph as it was mid-closing.

        Returns the seconds waited — normally 0.0, because the person's
        think-time absorbed the weave. When it is not zero the deferral has
        genuinely charged the person, and `TurnTiming.deferred_wait_s` is where
        that shows up rather than being buried in `generation_s`.
        """
        if self._deferred_pathway_task is None:
            return 0.0
        started = time.monotonic()
        await self.wait_for_deferred_work()
        return time.monotonic() - started

    async def wait_for_deferred_work(self) -> None:
        """Await anything this Advisor started off-turn. A HOST OBLIGATION.

        Call this before the process (or the session's scope) goes away —
        typically once, after the last turn. It is the same shape of contract as
        `aclosing(...)` around `chat_stream`: the framework starts work the turn
        does not wait for, and only the host knows when there is no more turn
        coming.

        Skipping it does not corrupt anything — every deferred write is
        fail-soft and idempotent — but the weave is cancelled with the loop, so
        the decision keeps whatever grounds it was recorded with. That is the
        pre-deferral behaviour, not a new failure mode.

        Safe to call any number of times, including when nothing was deferred.
        """
        # Loops on the FIELD rather than awaiting one captured task: a turn that
        # lands while this is waiting replaces it, and awaiting the stale
        # reference would return with work still in flight.
        while True:
            task = self._deferred_pathway_task
            if task is None or task.done():
                return
            try:
                await task
            except asyncio.CancelledError:
                raise
            except Exception:
                # The task logs its own failures; this guard only stops a
                # deferred failure from surfacing at an unrelated shutdown seam.
                logger.exception("Deferred Advisor work ended in an error")
                return

    def _schedule_pathway_construction(self, decision_hash: str | None) -> None:
        """Queue the weave this closing is entitled to, to run OFF the turn.

        This is the deferral `_ensure_pathways_before_closing` was written
        against ("the construction is not unnecessary — it is in the wrong
        PLACE. It belongs off the turn entirely, and the architecture already
        permits that"). Nothing here awaits: the person's turn ends when their
        reply is delivered, and the pathway lands afterwards.

        WHY THIS IS NOT OPTIONAL
        =======================
        Every other repair the latency work left behind is delegated to a tool
        the model must elect, and measured across the six A2 cells of
        `a15-floor` the model does not elect them: `explore` fired in 2/6,
        `audit_feasibility` in 1/6, `deepen` in 0/6, and the perspective cap's
        own "weave the deferred ones in a follow-up call" in 0. `anchor` fired
        6/6 — the cheap first step is reliable and every deepening step is not.
        So the weave is STARTED here rather than advertised to the model, and
        the only thing left to a caller is draining it at shutdown
        (`wait_for_deferred_work`).

        SCOPE TRAVELS, BECAUSE THE TASK IS CREATED INSIDE IT
        ===================================================
        `asyncio.create_task` snapshots the current context, so the `sid`
        ContextVar this turn is running under is inherited by the task. That is
        the whole reason this is scheduled from the turn rather than handed to a
        host to run later: outside the scope every write would land under a
        different root, or refuse (`require_for_current_scope`).

        Fail-soft and silent: the reply is already delivered, and a pathway the
        person never asked about must not surface to them as an error.
        """
        if decision_hash and decision_hash not in self._decisions_awaiting_pathway:
            self._decisions_awaiting_pathway.append(decision_hash)
        if not self._decisions_awaiting_pathway:
            # Nothing to ground. The graph may still be unwoven, and weaving it
            # would leave a better graph behind — but no record would point at
            # the result, and an exploration run on no one's behalf is the kind
            # of unattributed cost this seam was moved to stop paying.
            return

        task = self._deferred_pathway_task
        if task is not None and not task.done():
            # Single flight. The running task re-reads the queue after every
            # weave, so a decision closed while it works is picked up without a
            # second exploration running concurrently against the same nexus.
            return

        try:
            self._deferred_pathway_task = asyncio.create_task(
                self._run_deferred_pathway_construction()
            )
        except RuntimeError:
            # No running loop (a synchronous caller driving `chat` through
            # `asyncio.run` has one; something more exotic may not). Nothing to
            # defer onto, so the closing keeps exactly the behaviour it had
            # before this existed.
            logger.exception("Could not schedule deferred pathway construction")

    async def _run_deferred_pathway_construction(self) -> None:
        """Weave, ground every decision waiting on a pathway, then audit the recipe.

        Ordering matters and is the reason this is a loop rather than one pass:
        a decision recorded while the weave was running has to be grounded too,
        and it arrives in `_decisions_awaiting_pathway` after this task has
        already read it once.

        Bounded three ways, because an unbounded drain against a graph that
        refuses to weave is the failure this replaces, not an improvement on it:
        the round cap, the no-progress check, and the fact that each round's
        work is `run_exploration_detailed`'s own budgeted call.

        The feasibility pass runs AFTER the whole drain rather than inside it, on
        two grounds: the weave is the larger reasoning restoration, so it should
        not queue behind an annotation; and a task cancelled at shutdown then
        loses the cheaper half rather than the dearer one.
        """
        rounds = 0
        grounded: list[str] = []
        while self._decisions_awaiting_pathway and rounds < self._MAX_WEAVE_ROUNDS:
            rounds += 1
            pending = list(self._decisions_awaiting_pathway)
            self._decisions_awaiting_pathway.clear()
            try:
                pathways = await self._weave_unwoven_perspectives()
            except Exception:
                logger.exception(
                    "Deferred pathway construction failed (fail-soft); the "
                    "decisions it would have grounded keep the grounds they "
                    "were recorded with"
                )
                # BREAK, not return: a decision grounded in an earlier round
                # still has a recipe worth scoring, and this round's failure is
                # about the weave rather than about that record.
                break
            for decision_hash in pending:
                self._ground_recorded_decision(decision_hash, pathways)
                grounded.append(decision_hash)
        await self._audit_adopted_pathways(grounded)

    async def _audit_adopted_pathways(self, decision_hashes: list[str]) -> None:
        """Score the recipe each closing actually adopted, off the turn.

        THE THIRD AUDITED TRADE, PAID AT ONE PLACE ONLY
        ==============================================
        `settings.audit_transformations` was turned off because auditing all 6N
        Transformations of an exploration was 40% of `explore`'s provider spend
        for an annotation, and the repair was delegated to a tool the model must
        elect. It elects it in **1 of 6** A2 cells (`a15-floor`) and **0 of 6**
        in `weave-offturn` — the same finding as `explore` 2/6 and `deepen` 0/6,
        and the same conclusion: a repair the model has to ask for is a repair
        that does not happen. (This docstring said "1/5 in `weave-offturn`" when
        first written; the archive holds no `audit_feasibility` call in any of
        that round's six A2 cells. Counted from `tool_calls` in the run JSON —
        the rendered `.txt` never names an unelected tool, so a count read off
        the report reads 0 whether the tool was skipped or never wired.)

        So this asks for it, at exactly one place: the pathway a recorded
        decision is GROUNDED on. Two provider calls per closing, not 2 x 6N —
        the eager pass is still off and this is not it. What makes that scope
        the right one is where the band is read: `audit_feasibility` renders the
        score plus the resource/resistance/timeline factors and the success
        conditions, and the moment those matter most is the RETURNING session,
        where the person comes back shaky and the record's `adopted_pathway` is
        what the re-audit reassures from. `weave-offturn` measured that seam as
        the weakest one A2 has (wobble discrimination 1/3), so the recipe
        arriving with a feasibility band is aimed there.

        NOT GATED ON `audit_transformations`, AND THAT IS NOT AN OVERRIDE
        ===============================================================
        That flag's own description is about the EAGER pass ("EAGERLY audit
        every new Transformation ... agents reach the same concern on demand via
        the audit_feasibility tool"), and the tool has always ignored it. This
        goes through that tool's body, so it inherits the same standing — plus
        its idempotence, its cap and its resolve-before-spending order.

        GATED ON `automatic_feasibility_audit`, WHICH IS A MODE AND NOT AN OFF
        ====================================================================
        Off does not mean no feasibility scoring; it means no scoring THIS WAY.
        `audit_feasibility` is a tool and stays wired in both modes, so the band
        is always reachable by asking — there is deliberately no flag that takes
        that away. What the switch chooses is who initiates:

          automatic — this method runs, and the band exists on 5 of 5 records
                      that ground a pathway (`feasibility-offturn`).
          manual    — nothing runs here, and the band exists at the rate the
                      model elects the tool, measured 1/6 and 0/6.

        The cost of automatic is measured and it is not small: +46% A2 cell wall
        (701.0s vs 479.1s) and one turn in 48 where the person waited 284.5s for
        off-turn work to settle. On that same round the seam this was aimed at
        did not move — wobble discrimination 1/3 pairs before and after, and the
        one correct reassure did not cite the record. Automatic therefore buys a
        band that is present, rendered into the prompt, and so far unused. That
        is an argument about the DEFAULT, and the default stays automatic only
        because flipping it would silently un-measure the round that priced it.

        HONEST ASYMMETRY, RECORDED RATHER THAN HIDDEN
        ============================================
        The record's rationale was written before this band existed, so a low
        score arrives against a ground the decision never weighed, and
        `DecisionCoherenceCheck` has already run and will not re-run. That is
        additive information about an existing ground rather than a change to
        it — and a recipe the person cannot actually execute is worth knowing
        late, since the alternative is not knowing.

        Fail-soft and silent throughout: the reply was delivered turns ago.
        """
        if not decision_hashes:
            return
        if not self.settings.automatic_feasibility_audit:
            # Manual mode. Logged rather than silent, because the absence of a
            # band is otherwise indistinguishable from an audit that failed —
            # and the bench reads that absence as an endpoint.
            logger.info(
                "Manual feasibility mode: %d adopted pathway(s) left unscored. "
                "The audit_feasibility tool is still wired, so the band remains "
                "reachable by asking.",
                len(decision_hashes),
            )
            return
        pathways: list[str] = []
        for decision_hash in decision_hashes:
            pathway = self._adopted_pathway_hash(decision_hash)
            if pathway and pathway not in pathways:
                pathways.append(pathway)
        if not pathways:
            return
        try:
            from dialectical_framework.agents.orchestrator.tools import \
                audit_feasibility as audit_tool

            # Through the tool body, never `TransformationAudit` directly: that
            # is what buys the skip on an already-scored pathway (asking twice
            # costs twice AND leaves two critiques whose prose disagrees), the
            # per-call cap, and one wording for one check.
            logger.info(
                "Scoring the feasibility of %d adopted pathway(s) off the turn "
                "— the engine prompt ranks pathways on achievability and the "
                "model elects the audit about 1 closing in 6",
                len(pathways),
            )
            await audit_tool.run_audit_feasibility(pathways)
        except Exception:
            logger.exception(
                "Deferred feasibility audit of the adopted pathway failed "
                "(fail-soft); the decision keeps its recipe unscored"
            )

    def _adopted_pathway_hash(self, decision_hash: str) -> str | None:
        """The Transformation a decision names as its recipe, read from the edge.

        Read from `grounds` rather than from whatever the weave returned,
        because those are two different questions: the weave knows what it
        built, and the edge knows what the record actually rests on — which may
        be a pathway the model itself chose with the conversation in view
        (`_adopted_pathway_grounds` calls its own pick "the floor, not the
        ceiling"). Scoring anything else would score a recipe nobody adopted.
        """
        try:
            from dialectical_framework.graph.nodes.decision import Decision
            from dialectical_framework.graph.nodes.transformation import \
                Transformation
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            decision = NodeRepository().find_by_hash(
                decision_hash, node_type=Decision
            )
            if decision is None:
                return None
            for node, rel in decision.grounds.all():
                if getattr(rel, "role", None) != "adopted_pathway":
                    continue
                if isinstance(node, Transformation) and node.hash:
                    return node.hash
            return None
        except Exception:
            logger.exception(
                "Could not read the adopted pathway of decision [[%s]] "
                "(fail-soft)",
                decision_hash[:7],
            )
            return None

    async def _weave_unwoven_perspectives(self) -> list[str]:
        """Build pathways for every perspective the model left unwoven.

        This is the body `_ensure_pathways_before_closing` used to run ON the
        turn, restored verbatim in reasoning and moved off it. The measured
        reason it exists: split by whether the graph was woven at closing, the
        judged mean was -0.25 woven against -0.69 unwoven over 36 scores each
        (`claim2-weak-r15-voice`) — independently reproduced in `a15-floor`,
        where A2's structural delta against A1 was +0.74 in the cells that wove
        and -0.32 in the cells that did not.

        ONE tension is enough to weave. `PerspectiveCombination` treats a single
        PP as the circular-causality base case (W(1)=1: one Cycle, one Wheel, 2
        edges, 1 pair), and a 1-PP exploration measurably yields 6
        transformations and a synthesis
        (`tests/test_single_perspective_explore_real_llm.py`).

        THE LOOP DRAINS THE PERSPECTIVE CAP, WHICH NOTHING ELSE DID
        =========================================================
        `run_exploration_detailed` weaves at most
        `advisor_max_perspectives_per_exploration` (default 2) and reports the
        rest as `deferred_perspective_hashes` for the model to weave in a
        follow-up call. That follow-up fired 0 times in `a15-floor`. The cap's
        stated purpose is to bound TURN latency ("not total work") and there is
        no turn here, so this keeps calling until nothing is unwoven — which is
        the cap honoured rather than bypassed: each individual call still obeys
        it, and no single call gets wider.

        Stops on no progress, so a perspective the pipeline cannot weave costs
        one wasted round instead of spinning.
        """
        from dialectical_framework.agents.advisor.tools.explore import \
            run_exploration_detailed
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        built: list[str] = []
        for _ in range(self._MAX_WEAVE_ROUNDS):
            repo = PerspectiveRepository()
            unwoven = [
                p
                for p in repo.find_all_active()
                if p.hash and not repo.is_in_use_by_cycle(p)
            ]
            if not unwoven:
                break
            logger.info(
                "Weaving %d unwoven perspective(s) off the turn — the engine "
                "prompt requires pathways at a closing and the model skipped "
                "them",
                len(unwoven),
            )
            _report, round_built = await run_exploration_detailed(
                perspective_hashes=[p.hash for p in unwoven],
                intent=(
                    "The person is closing a decision on these tensions. Build "
                    "the causal arrangements so the decision rests on a pathway."
                ),
                nexus_hash=self._nexus_hash,
            )
            built += [h for h in (round_built or []) if h not in built]
            still_unwoven = [
                p
                for p in PerspectiveRepository().find_all_active()
                if p.hash and not PerspectiveRepository().is_in_use_by_cycle(p)
            ]
            if len(still_unwoven) >= len(unwoven):
                # No progress. Either the cap is 0-with-nothing-woven or the
                # pipeline declined these perspectives; either way another
                # identical call is not going to do better.
                logger.warning(
                    "Deferred weave made no progress on %d perspective(s); "
                    "stopping rather than repeating the same call",
                    len(unwoven),
                )
                break

        # A wheel that reuses every transformation reports them as existing
        # rather than new, so an empty `built` over a graph that already holds
        # pathways is a successful weave with nothing NEW to report.
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

    def _attach_adopted_pathway(self, pathway_hashes: list[str]) -> str | None:
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

        Returns that decision's HASH, which the caller hands to the deferral so
        the same record can be re-grounded once the off-turn weave lands. The
        hash is returned even when there was nothing to ground on — an unwoven
        closing is precisely the case the deferral exists for, so "no pathway
        yet" must not lose the identity of the record waiting for one.
        """
        try:
            decision = self._decision_recorded_this_turn()
        except Exception:
            logger.exception(
                "Could not resolve this turn's recorded decision (fail-soft)"
            )
            return None
        self._connect_adopted_pathway(decision, pathway_hashes)
        return getattr(decision, "hash", None)

    def _ground_recorded_decision(
        self, decision_hash: str, pathway_hashes: list[str]
    ) -> None:
        """Same attachment, for a decision resolved by HASH rather than by turn.

        The off-turn weave cannot use `_decision_recorded_this_turn`: that reads
        `last_tool_results`, which is per-turn state and has moved on by the time
        a deferred weave finishes (that is the whole point of deferring). So the
        hash is captured when the closing is scheduled and the node re-resolved
        here — which also means a weave outliving its session still grounds the
        right decision rather than the newest one.
        """
        from dialectical_framework.graph.nodes.decision import Decision
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        try:
            decision = NodeRepository().find_by_hash(
                decision_hash, node_type=Decision
            )
        except Exception:
            logger.exception(
                "Could not resolve decision [[%s]] to ground it on a deferred "
                "pathway (fail-soft)",
                decision_hash[:7],
            )
            return
        self._connect_adopted_pathway(decision, pathway_hashes)

    def _connect_adopted_pathway(self, decision, pathway_hashes: list[str]) -> None:
        """The GROUNDED_IN write both attachment paths share."""
        if not pathway_hashes or decision is None:
            return
        try:
            from dialectical_framework.graph.nodes.transformation import \
                Transformation
            from dialectical_framework.graph.relationships.grounded_in_relationship import \
                GroundedInRelationship
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

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
    from dialectical_framework.agents.orchestrator.tools.audit_feasibility import \
        audit_feasibility
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
        audit_feasibility,
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
