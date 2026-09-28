"""
The ablation ladder: five ways to assemble an assistant.

Each arm exposes the same interface — `await arm.reply(text)` — so the driver
is arm-agnostic and the scenario script is literally identical across arms.
Only the assembly differs.

Fairness rules this module exists to enforce
============================================
1. **Same final-response generation.** Every arm answers through
   `ConversationFacilitator.submit(ChatResponse, ...)` on the same tier model
   with the same persona. A2 differs by having *tools and a graph*, not by
   having a different decode path or a better persona.

2. **The baseline gets the real method, not a strawman.** A1's prompt is
   `method_prompt()` from `agents/consultant/consultant.py` — the engine's OWN method
   sections (`_INTERNAL_MODEL`, `_CONVERSATION_USE`, ...) derived live from
   `system_prompts.py`, tool verbs rewritten into mental acts — not a
   paraphrase that could quietly under-sell the opponent. Since 2026-09-26 that
   prompt is also a SHIPPED head (`Consultant`, advise-and-forget), so A1
   measures a product surface and every edit to it moves the baseline.
   `system_prompt(tool_names=[])` is NOT usable for this: it still refers to
   `anchor`/`ingest`/`inspect_node` in its prose sections, so an arm with no
   tools would be told to call tools it does not have.

3. **A1.7 is a real steelman of "ChatGPT with memory".** The model writes its
   own journal, in its own words, and gets it back verbatim next session. A
   lazy journal would make A2 look good for the wrong reason, so the journal
   prompt asks for exactly what a careful person would keep — including what
   was given up.

4. **Presentation discipline is shared, not a framework perk.** `_HOW_YOU_SPEAK`
   goes into the A1+ arms too. Found the hard way: without it, A1 wrote "That's
   T+, and it's legitimate" straight to the user while A2 (which has the rule)
   never did — so A1 was losing `conversational_fit` for jargon THIS MODULE
   handed it, not for any property of prompt-only reasoning. Any rule about how
   to talk belongs to every arm; only rules about *operating machinery* are A2's.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from dialectical_framework.agents.advisor.advisor import Advisor, ChatResponse
from dialectical_framework.agents.advisor.build_policy import BuildPolicy
from dialectical_framework.agents.consultant.consultant import method_prompt
from dialectical_framework.agents.conversation_facilitator import (
    ConversationFacilitator,
)
from dialectical_framework.agents.turn_timing import TurnTiming

from .models import Arm

logger = logging.getLogger(__name__)

#: Tools with an optional `context` parameter that is the ONLY carrier of the
#: person's particulars into the next session. Currently just `anchor`; `ingest`
#: deliberately has none (one document holds several tensions, so a shared
#: context would cross-contaminate them). Keep in step with the tool signatures
#: — a new grounding-carrying tool that is missing here records as if it had no
#: grounding to carry.
_GROUNDING_TOOLS = frozenset({"anchor"})


class ArmSession(Protocol):
    """One conversation with one arm."""

    async def reply(self, user_text: str) -> str: ...

    @property
    def last_tool_calls(self) -> list[str]: ...

    @property
    def last_tool_outcomes(self) -> list[str]: ...

    @property
    def last_grounding_args(self) -> list[str]: ...

    @property
    def last_turn_timing(self) -> Optional[TurnTiming]: ...


# ---------------------------------------------------------------------------
# Prompt construction for the non-framework arms (the method itself lives in
# `agents/consultant/consultant.py`; only the static-context and journal pieces are
# the bench's own)
# ---------------------------------------------------------------------------

_STATIC_CONTEXT_INTRO = """## Structural Analysis (prepared in advance)

A dialectical analysis of this person's situation was prepared before this
conversation. It is a static snapshot: it does not update as you talk, and you
cannot query it further. Draw on it as far as it goes, and rely on your own
judgment beyond it.

"""

_JOURNAL_INTRO = """## Your Notes From Earlier Sessions

These are notes you wrote yourself at the end of previous sessions with this
person. They are all you retain — there is no other record.

"""

_JOURNAL_REQUEST = (
    "The session is ending. Write the notes you want your future self to have "
    "when this person returns, knowing you will retain NOTHING else — no "
    "transcript, no memory of this conversation. Include: the situation as you "
    "understand it, the tension underneath it, any decision they committed to "
    "in their own words, why they chose it, and specifically what they "
    "accepted giving up by choosing it. Write prose for yourself, not a report "
    "for them."
)


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


class PromptArm:
    """A0 / A1 / A1.5 / A1.7 — one persona, one prompt, no tools.

    Deliberately thin: it is the same ConversationFacilitator the Advisor uses
    internally, with tools omitted. Any quality difference against A2 therefore
    comes from structure and state, not from response plumbing.
    """

    def __init__(
        self,
        arm: Arm,
        persona: str,
        *,
        engine_prompt: Optional[str] = None,
        static_context: Optional[str] = None,
        journal: Optional[str] = None,
    ) -> None:
        self._arm = arm
        self._conversation = ConversationFacilitator()
        parts = [persona]
        if engine_prompt:
            parts.append(engine_prompt)
        if static_context:
            parts.append(_STATIC_CONTEXT_INTRO + static_context)
        if journal:
            parts.append(_JOURNAL_INTRO + journal)
        self._conversation.set_system_prompt("\n\n".join(parts))

    async def reply(self, user_text: str) -> str:
        result = await self._conversation.submit(ChatResponse, user_text)
        return result.message

    @property
    def last_tool_calls(self) -> list[str]:
        return []  # no tools by construction

    @property
    def last_tool_outcomes(self) -> list[str]:
        return []  # no tools by construction

    @property
    def last_grounding_args(self) -> list[str]:
        return []  # no tools by construction

    @property
    def last_turn_timing(self) -> Optional[TurnTiming]:
        """All reply path, by construction — a prompt arm has nothing off it.

        Recorded rather than left None because this arm's per-turn seconds ARE
        the reply-cost baseline the A2 split is read against, and
        `probe_reply_path_latency.py` currently derives that baseline by dividing
        a whole cell's `duration_s` by its turn count — which silently assumes
        every turn in a session costs the same.

        `context_render_s` stays 0.0 by construction too, and that zero is a
        measurement: a prompt arm has no graph to re-read, so the whole of
        A2's per-turn refresh cost shows up as a difference against this arm
        rather than having to be isolated inside it.

        Worth knowing when comparing crashed turns across arms: this property
        never returns None, because `submit`'s own `finally` fills
        `last_submit_seconds` whatever happened, so a prompt turn that raised is
        still archived with real seconds. `AdvisorArm` reports None there — its
        timing is assembled AFTER the reply, so a crash leaves nothing to
        publish. Neither is a figure the other can be differenced against;
        compare crashed turns on `duration_s`, which the driver measures for
        every arm alike.

        The retry account is read rather than left to default, and that is not
        cosmetic: `TurnRecord.retry_count`'s own documentation calls 0 "the turn
        ran clean, which is a finding", so omitting it here would have published
        that finding — falsely — for every prompt-arm turn from here on. Nothing
        false is in the archive: 68 A0/A1/A1.7 turns carry a split and NONE of
        them carries `retry_count`, because the field postdates every one of them
        (the only 32 records that have it are A2). Forward-looking, then, like the
        rest of this fix. This arm throttles like any other; `retry_account` wraps
        its `submit` the same way (`ConversationFacilitator.submit`), so the figure
        was one attribute away the whole time. `tool_rounds` stays empty because it
        genuinely is.

        `closing` and `deferral` are the opposite call, and the difference is
        worth stating because it looks like the same one: they stay `None`
        deliberately and must NOT become `NO_CLOSING`/`NOTHING_TO_DEFER`. Those
        members say a seam ran and concluded there was nothing to do; this arm has
        no seam to run, which is why it cannot record a decision the model skips
        and why the repair rate is an A2-only quantity. `None` here reads as
        "nothing to report", which is the truth. A reader comparing repair rates
        across arms therefore has no A1 baseline to difference against — by
        construction, not by omission.
        """
        retries = self._conversation.last_submit_retries
        return TurnTiming(
            reply_path_s=self._conversation.last_submit_seconds,
            off_path_s=0.0,
            retry_seconds=retries.wasted_s,
            retry_count=retries.count,
        )

    async def write_journal(self) -> str:
        """A1.7: have the model write its own carry-forward notes.

        Asked in-conversation so the notes reflect what the model actually
        judged important — a journal we wrote for it would be our summary, not
        its memory, and would not test "ChatGPT with memory" honestly.
        """
        result = await self._conversation.submit(ChatResponse, _JOURNAL_REQUEST)
        return result.message


class AdvisorArm:
    """A2 — the full Advisor: live tools, graph persistence, ceremony.

    Also A2c with `build=BuildPolicy.NEVER`: the same class over a graph
    built beforehand, handed the reading and deciding tools and none of the
    build tools, so its per-turn cost is one graph read plus the model.

    And A2n with `nexus_hash=`: the same pre-built graph, the head PINNED to
    the exploration it produced with every tool kept — the Advisor on a nexus.
    The persona stays the preamble (the manual `app_preamble=` layer is what
    the bench uses, and it is untouched by the pin), which is the
    `persona=True` shape a client's pinned session gets in an app.

    `principal` is passed as an agent identity, never "human": the user turns
    here are produced by a simulator, and a recorded decision must not claim a
    human confirmation it never got. This is the framework's own provenance
    contract holding under test conditions.
    """

    def __init__(
        self,
        persona: str,
        *,
        principal: str,
        dialectical_context: Optional[str] = None,
        build: BuildPolicy = BuildPolicy.ON_ELECTION,
        nexus_hash: Optional[str] = None,
    ) -> None:
        self._advisor = Advisor(
            app_preamble=persona,
            dialectical_context=dialectical_context,
            principal=principal,
            build=build,
            nexus_hash=nexus_hash,
        )

    async def reply(self, user_text: str) -> str:
        return await self._advisor.chat(user_text)

    async def finish(self) -> None:
        """Await the work the Advisor deliberately did not put on a turn.

        The Advisor defers pathway construction off the turn
        (`_schedule_pathway_construction`) and documents draining it as a host
        obligation; the bench is a host. This MUST run before the cell reads
        decisions or renders a graph summary, or every measurement lands on the
        pre-weave graph and the deferral would score as having done nothing —
        the reverse of the r-round mistake where the bench measured a seam the
        product did not have.

        It also means A2's `duration_s` includes the weave. That is the honest
        number for a batch harness: the wall clock the framework spends. It is
        NOT the person's wait, and per-turn timing (`last_turn_timing`) remains
        the number to read for that.
        """
        await self._advisor.wait_for_deferred_work()

    @property
    def last_tool_calls(self) -> list[str]:
        return list(self._advisor._conversation.last_tool_calls)

    @property
    def last_tool_outcomes(self) -> list[str]:
        """Whether each tool the model called actually did anything.

        Only tools returning an ExecutionReport are represented — read-only ones
        (`sync`, `inspect_node`) return prose and are skipped rather than
        recorded as a fake "ok", so this list is shorter than `last_tool_calls`
        by design.

        A tool that RAISED is the exception to that rule and must be recorded:
        it also carries `report=None` (Mirascope turns the exception into a
        plain-string result), so skipping it would file a crash as a read-only
        call. That is how r11's `anchor` failures read as calls with no
        outcome against a graph with nothing in it.
        """
        outcomes = []
        for result in self._advisor._conversation.last_tool_results:
            report = result.report
            if result.error is not None:
                outcomes.append(f"{result.tool_name}:RAISED — {result.error}")
                continue
            if report is None:
                continue
            if report.ok:
                outcomes.append(f"{result.tool_name}:ok")
            else:
                outcomes.append(f"{result.tool_name}:FAILED — {report.summary}")
        return outcomes

    @property
    def last_grounding_args(self) -> list[str]:
        """Whether each grounding-carrying call actually carried its grounding.

        `anchor(context=...)` is optional, and the person's particulars survive
        ONLY through it — the tetrad itself keeps a few words per pole. So a
        session can show `anchor:ok`, a healthy graph, and still carry nothing
        into the next session, with no way to tell from the record whether the
        model omitted `context` (a prompt defect) or the grounding lane dropped
        it (a framework one). Both read identically: an ok call over a graph with
        no grounding on it. Observed in `r12-raise-probe`: two `anchor:ok` calls,
        two perspectives, ZERO `Grounded in:` lines in the carryover.

        Recorded as a presence flag with a length, never the text: `context`
        holds the person's whole case, and every saved record would carry a
        second copy of the transcript.
        """
        flags = []
        conversation = self._advisor._conversation
        names = conversation.last_tool_calls
        for name, args in zip(names, conversation.last_tool_call_args):
            if name not in _GROUNDING_TOOLS:
                continue
            value = args.get("context") or ""
            if value:
                flags.append(f"{name}:context={len(value)}c")
            else:
                flags.append(f"{name}:context=MISSING")
        return flags

    @property
    def last_decision_args(self) -> list[str]:
        """The ground SET each `record_decision` call carried, as short hashes
        and roles — never the question, stance or rationale.

        `last_tool_outcomes` records a refusal and nothing recorded what was
        refused. `prompt-vs-machinery` (2026-09-22): one turn called the tool
        seven times, five refused identically on one price, and whether the
        model had added the plain ground the refusal asked for — the whole
        question of whose loop it was — could not be read off the record.
        A plain ground is written as `<hash7>:plain`; an empty set as `NONE`.
        """
        rows = []
        conversation = self._advisor._conversation
        for name, args in zip(conversation.last_tool_calls, conversation.last_tool_call_args):
            if name != "record_decision":
                continue
            parts = []
            for ground in args.get("grounds") or []:
                if isinstance(ground, dict):
                    ground_hash = ground.get("hash")
                    role = ground.get("role")
                else:
                    ground_hash = getattr(ground, "hash", None)
                    role = getattr(ground, "role", None)
                parts.append(f"{str(ground_hash or '')[:7]}:{role or 'plain'}")
            rows.append(f"record_decision:grounds={','.join(parts) or 'NONE'}")
        return rows

    @property
    def last_turn_timing(self) -> Optional[TurnTiming]:
        """The reply-path / off-path split, straight from the Advisor.

        Read off the agent rather than timed here: only the Advisor knows where
        the reply was handed over, and the harness timing `arm.reply()` from
        outside can see the total and nothing else.
        """
        return self._advisor.last_turn_timing

    @property
    def messages(self) -> list:
        return self._advisor.messages
