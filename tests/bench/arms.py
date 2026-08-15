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

2. **The baseline gets the real method, not a strawman.** A1's prompt is built
   from the engine's OWN method sections (`_INTERNAL_MODEL`, `_CONVERSATION_USE`,
   ...) imported live from `system_prompts.py` — not a paraphrase that could
   quietly under-sell the opponent. `system_prompt(tool_names=[])` is NOT
   usable for this: it still refers to `anchor`/`ingest`/`inspect_node` in its
   prose sections, so an arm with no tools would be told to call tools it does
   not have. Sections whose subject is tool operation are dropped; the
   dialectical method itself is passed through verbatim.

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
import re
from typing import Optional, Protocol

from dialectical_framework.agents.advisor.advisor import Advisor, ChatResponse
from dialectical_framework.agents.advisor.system_prompts import (
    _CONVERSATION_USE,
    _DECISION_READINESS,
    _EAGER,
    _HOW_YOU_SPEAK,
    _INTERNAL_MODEL,
    _ROLE,
)
from dialectical_framework.agents.conversation_facilitator import (
    ConversationFacilitator,
)

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


# ---------------------------------------------------------------------------
# Prompt construction for the non-framework arms
# ---------------------------------------------------------------------------

#: Tool-operation phrasing -> the equivalent mental act, applied BEFORE any
#: paragraph is dropped.
#:
#: Translating beats dropping. A naive "drop every paragraph mentioning a tool
#: name" also deletes the discrimination test ("before ANCHORING a new
#: candidate tension"), the re-audit rule, and "never DUMP all insights at
#: once" — i.e. precisely the reasoning the eval measures. An A1 arm missing
#: the re-audit rule would fail the wobble probe by handicap, not by lack of
#: enforcement, and the result would be worthless. So the method survives in
#: full; only its *operational* verbs become mental ones.
#: Match keys whitespace-insensitively: the engine prompt is hard-wrapped, so a
#: literal key containing a space fails wherever the source happens to wrap.
_TOOL_REWRITES: tuple[tuple[str, str], ...] = (
    # _ROLE / _EAGER: the framework's "silent machinery" framing has no
    # prompt-only counterpart, but the BEHAVIOUR does — including the
    # no-analysis exceptions, which are exactly the poor-fit control.
    ("Your understanding deepens through dialectical analysis that runs silently — they never see the machinery, only experience increasingly precise and insightful responses that help them find their own path.", "You reason dialectically about their situation as you go, and let that reasoning show up as increasingly precise and insightful responses that help them find their own path."),
    ("If the machinery has nothing yet, you are still a fully capable counselor — respond from your own judgment and let the structural understanding catch up.", "If the analysis has nothing yet, you are still a fully capable counselor — respond from your own judgment and let the structural understanding catch up."),
    ("Building structural understanding through your internal tools is part of how you think — the default on any counsel-shaped turn, not an optional extra. When someone shares a situation, a decision, a conflict, a position — anchor or ingest it as a matter of course. Your counsel is only as deep as the understanding you've built.", "Building structural understanding is part of how you think — the default on any counsel-shaped turn, not an optional extra. When someone shares a situation, a decision, a conflict, a position — work out its dialectical structure as a matter of course. Your counsel is only as deep as the understanding you've built."),
    ("Your response to the person never waits on the machinery — speak from what you have. Analysis deepens your next turn; it never delays or deforms this one.", "Your response to the person never waits on the analysis — speak from what you have."),
    ("After ingest or anchor (tensions identified)", "Once you have identified the tension"),
    ("After explore (pathways available)", "Once you have worked out the pathways"),
    ("Before anchoring a new candidate tension", "Before working out a new candidate tension"),
    ("Anchor the pair as it comes", "Take the pair as it comes"),
    ("anchor the same pair again (identical wording) for an alternative tetrad", "work out an alternative tetrad for the same pair"),
    ("it is itself an anchor candidate: anchor it as its own tension", "it is itself worth working out as its own tension"),
    ("also anchor each option alone", "also work out each option alone"),
    ("read the anchor result at call time", "judge it as you work"),
    ("When weaving, take the reading", "Take the reading"),
    ("the person enumerates cheaply what the machinery maps expensively", "the person enumerates cheaply what you would work out expensively"),
    # Working out pathways before closing is METHOD, not machinery — a
    # prompt-only arm owes the same reasoning, so this is rewritten rather
    # than dropped (and "explore" is deliberately not a drop token).
    ("`explore` what you have before the ceremony.", "Work out their pathways before the ceremony."),
    ("ONE mapped\ntension is enough to explore — a single opposition already has a pathway\nthrough it, and exploring it names that pathway. There is no minimum to reach;\nwaiting for a fuller map means closing without one.", "ONE mapped\ntension is enough to work pathways from — a single opposition already has a\npathway through it, and working it out names that pathway. There is no minimum\nto reach; waiting for a fuller map means closing without any."),
    ("offer to record the decision", "offer to set the decision down in writing"),
    ("Record ONLY on their explicit confirmation", "Write it down ONLY on their explicit confirmation"),
    ("Before proposing to record", "Before proposing to set it down"),
    ("record that confrontation in the rationale", "state that confrontation in the record"),
    ("If they decline the test, record it — their wish outranks the ritual.", "If they decline the test, write it down anyway — their wish outranks the ritual."),
    ("Note in the rationale that the cost went unconfronted.", "Note in the record itself that the cost went unconfronted."),
    ("Decisions are NEVER recorded silently", "Decisions are NEVER set down silently"),
    ("the record is named in plain words, never as a tool; its reference (hash) follows the same disclosure rules as any other node reference.", "the record is named in plain words."),
    ("check the distilled record against the Decisions section of your understanding", "check the distilled record against the decisions you have already written down"),
    ("If a ground of the decision has since been discarded, surface that:", "If a support the decision rested on has since fallen away, surface that:"),
    ("(when correspondence lines appear in your understanding they are this signal; otherwise judge whether the new framing's deep structure matches a mapped tension)", "(judge whether the new framing's deep structure matches a tension you have already worked out)"),
    ("completeness belongs only to causal arrangements, which are enumerated systematically for the tensions woven in", "completeness is not available to you here"),
    ("Never dump all insights at once", "Never deliver all insights at once"),
    ("If the Current Understanding section below contains perspectives, you already have structural insight.", "If you have already worked out the tensions, you already have structural insight."),
    ("options that merely differ rather than oppose show up as weak opposition (low HS) or a low mode (drifting/absence rather than negation)", "the options merely differ rather than genuinely oppose each other"),
    # _HOW_YOU_SPEAK. This is presentation discipline every arm needs; without
    # the rewrite the whole no-jargon paragraph is dropped for saying
    # "the machinery", and A1 writes "That's T+" to the user.
    ("The machinery stays invisible: never reveal tools, internal processes, hash codes, or pipeline steps; never say \"let me analyze\" or \"I'm processing\"; never present findings as structural tables or labeled positions.", "Your reasoning stays invisible: never narrate your own analysis; never say \"let me analyze\" or \"I'm processing\"; never present findings as structural tables or labeled positions."),
    ("Statement text from the graph is raw material — rephrase it freely into their language; exactness matters only when referencing nodes internally by hash.", "The structure you work out is raw material — rephrase it freely into their language."),
    # Speaking the person's own particulars verbatim is grounding DISCIPLINE,
    # which a prompt-only arm owes just as much — so it is rewritten, not
    # dropped. What must go is the cross-reference: `Grounded in:` is a
    # graph-render artifact and "Reading Your Understanding" is an A2-only
    # section, so unrewritten this pointed A1 at a construct and a heading
    # neither of which exists in its own prompt. Landed in 4f9e479, between r6
    # and r7 — exactly the class of baseline degradation that inflates an A2
    # delta without anyone editing an A2 number.
    # (`_HOW_YOU_SPEAK_SCOPED` carries the same sentence, but A1 never draws
    # from the scoped section and the engine always renders `_SCORE_READING`, so
    # the reference resolves there. A rewrite key for it would be stale by
    # construction — see test_rewrite_table_has_no_stale_keys.)
    ("The one\nexception is a `Grounded in:` line: those are the person's own facts, spoken\nas stated, not reworded (see Reading Your Understanding).", "The one\nexception is the person's own facts — their numbers, names, and dates are\nspoken back as stated, never reworded into your own phrasing."),
)

#: Paragraphs that remain purely about machinery AFTER rewriting are dropped —
#: they describe reading a graph dump or calling a tool, which has no
#: prompt-only equivalent at all.
_TOOL_TOKENS = (
    "ingest",
    "anchor",
    "inspect_node",
    "read_digest",
    "record_decision",
    "internal tool",
    "the machinery",
    "[[",
)


def _apply_rewrites(section: str) -> tuple[str, list[str]]:
    """Apply the rewrite table whitespace-insensitively.

    Returns the rewritten text and the list of keys that did NOT match — a
    stale key means the engine prompt was edited and this table drifted, which
    `test_bench.py` asserts on rather than letting the baseline silently rot.
    """
    unmatched: list[str] = []
    for old, new in _TOOL_REWRITES:
        pattern = re.compile(r"\s+".join(re.escape(w) for w in old.split()))
        section, n = pattern.subn(lambda _m, _new=new: _new, section)
        if not n:
            unmatched.append(old)
    return section, unmatched


def _strip_tool_prose(section: str) -> str:
    """Rewrite tool verbs into mental acts; drop only what stays machinery.

    Paragraph-level dropping (not line-level) so a removed sentence never
    leaves a dangling fragment.
    """
    section, _ = _apply_rewrites(section)
    kept: list[str] = []
    for para in section.split("\n\n"):
        lowered = para.lower()
        if any(tok.lower() in lowered for tok in _TOOL_TOKENS):
            continue
        kept.append(para)
    return "\n\n".join(kept).strip()


def method_prompt(include_decision: bool = True) -> str:
    """The dialectical METHOD as instructions, with no tools to call.

    This is the A1 arm's engine prompt and the honest opponent for Claim 1: if
    a frontier model given the real method text self-applies it as well as the
    framework enforces it, Claim 1 fails — and the eval should be able to say
    so cleanly rather than win by handicapping the baseline.
    """
    # The engine fills these placeholders in system_prompt(); an unrendered
    # "{decision_filter_note}" reaching the model is a prompt bug, and one the
    # baseline must not be handicapped by.
    eager = _EAGER.replace(
        "{decision_filter_note}",
        (
            "\nIn decision-shaped conversations, the Decision Readiness "
            "section below adds one more filter: a candidate tension that "
            "could not change the choice is acknowledged, not mapped.\n"
        )
        if include_decision
        else "",
    )
    # Presentation discipline, shared with A2 (see fairness rule 4). The
    # exception note is about the decision RECORD, which a prompt-only arm keeps
    # in prose, so it is rendered whenever the decision section is included.
    how_you_speak = _HOW_YOU_SPEAK.replace(
        "{decision_speech_note}",
        (
            "\n\nOne exception: the decision record (see Decision Readiness) "
            "is named openly, in plain words."
        )
        if include_decision
        else "",
    )
    # Mid-sentence placeholder, on the paragraph that refuses to drop a risk
    # because the person instructed it. A prompt-only arm has no `Decision
    # Readiness` section unless one is appended below, so the cross-reference
    # renders on the same condition the section does.
    internal_model = _INTERNAL_MODEL.replace(
        "{decision_unconfronted_note}",
        (
            ", noted as unconfronted in the record you write out (see Decision "
            "Readiness)"
        )
        if include_decision
        else "",
    )
    sections = [
        _strip_tool_prose(_ROLE),
        _strip_tool_prose(eager),
        # The method itself — passed through with only tool prose rewritten.
        _strip_tool_prose(internal_model),
        _strip_tool_prose(_CONVERSATION_USE),
        _strip_tool_prose(how_you_speak),
    ]
    if include_decision:
        decision = _DECISION_READINESS
        # The engine's ceremony section is written around a recording tool.
        # Keep the convergence REASONING (readiness, discrimination test,
        # saturation, confronting the cost) and let the model "record" in prose.
        decision = _strip_tool_prose(decision)
        sections.append(decision)
        sections.append(
            "## Recording Decisions\n\n"
            "You have no tools. When the person confirms a decision, restate "
            "it in your reply as an explicit record: the question, their "
            "stance in their own confirmed words, the why, and what they are "
            "giving up by choosing it. That restatement is the only record "
            "that exists."
        )
    return "\n\n".join(s for s in sections if s)


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
    ) -> None:
        self._advisor = Advisor(
            app_preamble=persona,
            dialectical_context=dialectical_context,
            principal=principal,
        )

    async def reply(self, user_text: str) -> str:
        return await self._advisor.chat(user_text)

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
    def messages(self) -> list:
        return self._advisor.messages
