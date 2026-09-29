"""
The dialectical method as a prompt — and the head that carries it alone.

`method_prompt()` is the Advisor engine's method with every tool verb turned
into a mental act: the same `_ROLE`, `_EAGER`, `_INTERNAL_MODEL`,
`_CONVERSATION_USE`, `_DECISION_READINESS` and `_HOW_YOU_SPEAK` the tool-wired
head reads, DERIVED from those constants at call time so the two can never say
different things about the method. What a graph-backed head does with a tool
("anchor the pair", "explore what you have"), this prompt asks the model to do
in its own reasoning ("take the pair as it comes", "work out their pathways"),
and what has no prompt-only counterpart at all (reading a graph dump, calling
`inspect_node`) is dropped paragraph by paragraph.

`Consultant` is the head for it: a conversation with a dialectically
thinking model and nothing else — no Case, no scope, no graph, no tools, no
memory beyond the messages of this one conversation. Advise and forget. It is
the surface for the shallow application: a person describes a situation, gets
counsel that reasons dialectically, and walks away; nothing is written anywhere.
Where the framework's value has been measured to live — the record's grounds,
the return against no memory, the Consultant's live read of a finished graph —
this head has none of it by construction, and says so in its own prompt (a
confirmed decision is restated in the reply, and that restatement is the only
record that exists).

THE SAME TEXT IS THE BENCH'S A1 ARM
===================================
This began as the bench's honest opponent (`tests/e2e/arms.py`, fairness rule
2: the baseline gets the real method, not a strawman) and moved into `src/` on
2026-09-26 because the owner wants it shipped. The consequence runs both ways:
the A1 arm now measures a product surface, and every edit to this prompt is an
edit to the baseline every `A2−A1` figure in `rounds.md` was read against.
`tests/e2e/test_e2e.py::TestMethodPrompt` is the guard on the derivation — a
rewrite key that no longer matches the engine means method text is silently
dropped from BOTH the product and the baseline.
"""

from __future__ import annotations

import re
from contextlib import aclosing
from typing import Any, AsyncGenerator, Optional

from mirascope import llm

from dialectical_framework.agents.advisor.advisor import ChatResponse
from dialectical_framework.agents.advisor.system_prompts import (
    _CONVERSATION_USE, _DECISION_READINESS, _EAGER, _EXPLORE_BEFORE_CEREMONY,
    _HOW_YOU_SPEAK, _INTERNAL_MODEL, _ONE_TENSION_IS_ENOUGH, _ROLE)
from dialectical_framework.agents.app_spec import AppSpec, resolve_app_layer
from dialectical_framework.agents.conversation_facilitator import (
    FROM_SETTINGS, ConversationFacilitator)
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.agents.turn_timing import TurnTiming
from dialectical_framework.graph.views import ExplorationView

#: Tool verbs → mental acts. These are REWRITES, not drops: dropping every
#: paragraph that mentions a tool name would also delete the discrimination test
#: ("before ANCHORING a new candidate tension"), the re-audit rule, and "never
#: DUMP all insights at once" — i.e. precisely the reasoning the method IS. A
#: method prompt missing the re-audit rule would fail the wobble by handicap,
#: not by lack of enforcement. So the method survives in full; only its
#: *operational* verbs become mental ones.
#: Match keys whitespace-insensitively: the engine prompt is hard-wrapped, so a
#: literal key containing a space fails wherever the source happens to wrap.
_TOOL_REWRITES: tuple[tuple[str, str], ...] = (
    # _ROLE / _EAGER: the framework's "silent machinery" framing has no
    # prompt-only counterpart, but the BEHAVIOUR does — including the
    # no-analysis exceptions, which are exactly the poor-fit control.
    ("Your understanding deepens through dialectical analysis that runs silently — they never see the machinery, only experience increasingly precise and insightful responses that help them find their own path.", "You reason dialectically about their situation as you go, and let that reasoning show up as increasingly precise and insightful responses that help them find their own path."),
    ("If the machinery has nothing yet, you are still a fully capable counselor — respond from your own judgment and let the structural understanding catch up.", "If the analysis has nothing yet, you are still a fully capable counselor — respond from your own judgment and let the structural understanding catch up."),
    ("Building structural understanding through your internal tools is part of how you think — the default on any advice-shaped turn, not an optional extra. When someone shares a situation, a decision, a conflict, a position — anchor or ingest it as a matter of course. Your counsel is only as deep as the understanding you've built.", "Building structural understanding is part of how you think — the default on any advice-shaped turn, not an optional extra. When someone shares a situation, a decision, a conflict, a position — work out its dialectical structure as a matter of course. Your counsel is only as deep as the understanding you've built."),
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
    # prompt-only head owes the same reasoning, so this is rewritten rather
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
    # _HOW_YOU_SPEAK. This is presentation discipline every head needs; without
    # the rewrite the whole no-jargon paragraph is dropped for saying
    # "the machinery", and the model writes "That's T+" to the person.
    ("The machinery stays invisible: never reveal tools, internal processes, hash codes, or pipeline steps; never say \"let me analyze\" or \"I'm processing\"; never present findings as structural tables or labeled positions.", "Your reasoning stays invisible: never narrate your own analysis; never say \"let me analyze\" or \"I'm processing\"; never present findings as structural tables or labeled positions."),
    ("Statement text from the graph is raw material — rephrase it freely into their language; exactness matters only when referencing nodes internally by hash.", "The structure you work out is raw material — rephrase it freely into their language."),
    # Speaking the person's own particulars verbatim is grounding DISCIPLINE,
    # which a prompt-only head owes just as much — so it is rewritten, not
    # dropped. What must go is the cross-reference: `Grounded in:` is a
    # graph-render artifact and "Reading Your Understanding" is a graph-only
    # section, so unrewritten this pointed the model at a construct and a
    # heading neither of which exists in its own prompt. Landed in 4f9e479 —
    # exactly the class of baseline degradation that inflates an A2 delta
    # without anyone editing an A2 number.
    # (`_HOW_YOU_SPEAK_SCOPED` carries the same sentence, but this prompt never
    # draws from the scoped section and the engine always renders
    # `_SCORE_READING`, so the reference resolves there. A rewrite key for it
    # would be stale by construction — see test_rewrite_table_has_no_stale_keys.)
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
    `tests/e2e/test_e2e.py::TestMethodPrompt` asserts on rather than letting
    the method silently rot out of the prompt.
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


#: What replaces the `record_decision` tool on this surface: the record is the
#: reply. Rendered only with the decision section, which is what it closes.
_RECORDING_IN_PROSE = """## Recording Decisions

You have no tools. When the person confirms a decision, restate it in your
reply as an explicit record: the question, their stance in their own confirmed
words, the why, and what they are giving up by choosing it. That restatement is
the only record that exists."""


def method_prompt(include_decision: bool = True) -> str:
    """The dialectical METHOD as instructions, with no tools to call.

    The engine's own sections, derived live: `_ROLE`, `_EAGER`,
    `_INTERNAL_MODEL`, `_CONVERSATION_USE`, `_HOW_YOU_SPEAK`, and — with
    `include_decision` — `_DECISION_READINESS` in its BUILDING form (the two
    name-gated passages the tool-wired head renders under `explore`), each
    rewritten by `_TOOL_REWRITES` and stripped of what stays machinery. Taking
    the non-building form of Decision Readiness would hand this head less
    method than the graph-backed one reads, so the building form is taken and
    the table turns it into a mental act.

    `include_decision=False` is a conversation that is not decision-shaped —
    counsel without the convergence ceremony and without the prose record.
    """
    # The engine fills these placeholders in system_prompt(); an unrendered
    # "{decision_filter_note}" reaching the model is a prompt bug.
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
    # Presentation discipline, shared with the graph-backed head. The
    # exception note is about the decision RECORD, which this head keeps in
    # prose, so it is rendered whenever the decision section is included.
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
    # because the person instructed it. There is no `Decision Readiness`
    # section unless one is appended below, so the cross-reference renders on
    # the same condition the section does.
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
        # Both feasibility passages ask for `audit_feasibility`, and this head
        # has no tools at all — so they collapse the same way they do in the
        # engine when that tool is unwired, blank line and all. Deliberately
        # dropped rather than stripped to prose: unlike the record (which the
        # model can write out in its reply), a feasibility band is a
        # MEASUREMENT this head has no way to produce, so prose about reading
        # one would be an instruction to invent it.
        for placeholder in (
            "{feasibility_before_record_note}",
            "{feasibility_wobble_note}",
        ):
            decision = decision.replace(f"\n\n{placeholder}", "")
        decision = decision.replace(
            "{explore_before_ceremony_note}", _EXPLORE_BEFORE_CEREMONY
        ).replace("{one_tension_note}", _ONE_TENSION_IS_ENOUGH)
        # The engine's ceremony section is written around a recording tool.
        # Keep the convergence REASONING (readiness, discrimination test,
        # saturation, confronting the cost) and let the model "record" in prose.
        sections.append(_strip_tool_prose(decision))
        sections.append(_RECORDING_IN_PROSE)
    return "\n\n".join(s for s in sections if s)


_TOOLS_ON_A_TOOLLESS_HEAD = (
    "Consultant holds no tools by construction — its prompt tells the model "
    "so, and a tool it could call would make that a lie. Pass an AppSpec "
    "without `tools`, or use Advisor(...) for a head that wires them."
)


class Consultant:
    """The method as a prompt, and nothing behind it. Advise and forget.

    Usage:
        advisor = Consultant(app_preamble=COUNSELOR_PERSONA)
        reply = await advisor.chat("I have a problem with my wife...")
        # ...later turns on the same instance, or resume elsewhere:
        again = Consultant(app_preamble=COUNSELOR_PERSONA, messages=advisor.messages)

    No scope is needed and none is read: nothing here touches a Case or the
    graph, so a host may run it with no database at all. What the person says
    survives only as `messages` — carry them for the length of the session and
    drop them after; there is no other memory, and the prompt tells the model
    as much (a confirmed decision is restated in the reply, and that is the
    only record). `exploration_view(focus=)` is the one view this head can
    draw: a structured turn on this same conversation, building what the ask
    needs and drawing it in the view shape the graph-backed heads share
    (`graph/views.py`).

    Takes the persona the same way the Advisor does: `app_preamble=` (manual) or
    `app=` (an AppSpec's `advisor_persona`, the same preamble the unscoped
    Advisor composes). `advanced=` does not exist here for the reason it raises
    on the unscoped Advisor — there is no machinery to disclose. App tools are
    refused rather than dropped: the prompt says "You have no tools", and a
    silently dropped tool list is the defect, not the tool.

    `thinking=` is the person's per-session toggle, as on every head. Worth
    knowing before choosing it: on this head the conversational call is a
    plain text call, which on Claude 5 thinks by provider default when no level
    is set (`thinking_compat.conversational_round()` sends OFF when unset, the
    same as every other head); the measured in-session delta between this
    prompt and the graph-backed head was read WITH thinking at medium
    (`thinking-check`, rounds.md).
    """

    AGENT_NAME = "consultant"

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
        app: Optional[AppSpec] = None,
        thinking: Any = FROM_SETTINGS,
        include_decision: bool = True,
    ) -> None:
        preamble, tools = resolve_app_layer(
            app, app_preamble, None, preamble_for="advisor_unscoped"
        )
        if tools:
            raise ValueError(_TOOLS_ON_A_TOOLLESS_HEAD)
        self._conversation = ConversationFacilitator(conversation_thinking=thinking)
        if messages:
            self._conversation.load_messages(messages)
        parts = [p for p in (preamble, method_prompt(include_decision)) if p]
        self._conversation.set_system_prompt("\n\n".join(parts))

    async def chat(self, user_message: str) -> str:
        result = await self._conversation.submit(ChatResponse, user_message)
        return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        """Stream one turn's events; `ResponseComplete` last, as on every head.

        Nothing runs after the stream here — no seam, no filter — so this is
        the facilitator's stream passed through. The host still owes a CLOSE on
        a mid-stream exit (`aclosing`), for the reason `Advisor.chat_stream`
        gives: an abandoned generator's cleanup waits for the collector.
        """
        async with aclosing(
            self._conversation.submit_stream(ChatResponse, user_message)
        ) as rounds:
            async for event in rounds:
                yield event

    @property
    def messages(self) -> list:
        """The conversation so far — the only state this head has."""
        return self._conversation._messages

    async def exploration_view(self, focus: Optional[str] = None) -> ExplorationView:
        """The structure of this conversation as a view — drawn by this head.

        The same name as `graph/views.py::exploration_view` because it is the
        same view (`ExplorationView`, `nexus_hash` None as for a case with no
        exploration); a METHOD here because this head has no graph for a module
        function to read, only its conversation. It is a STRUCTURED TURN on that
        conversation — same system prompt, full history, both sides — so the
        view shows what has been ESTABLISHED, and where `focus` asks for
        structure not yet worked out ("a perspective for the thesis you
        named") the turn builds it by the method first
        (`concerns/view_sketch.py::view_sketch_prompt`). What it built is
        kept in `messages` as the consultant's own words, so the next turn can
        be asked about a corner it just drew.

        Thinks at the session's level: the turn runs on a json-mode facilitator
        over the SAME history, because forced-tool structured calls cannot
        think and building a tetrad in one shot is the heaviest reasoning a
        structured call is asked to do here.

        Terminology-free by construction (no hash, alias or score exists),
        unchecked by construction (no HS gate, no validation, nothing
        persisted). Not a tool: the model cannot call this, and the prompt's
        "You have no tools" stays true. Raises on a provider failure rather
        than returning an empty view, so the host can tell "nothing drawn"
        from "the drawing failed".
        """
        from dialectical_framework.concerns.view_sketch import (
            ViewSketchDto, exploration_view_from_sketch, history_ask,
            history_text, view_sketch_prompt)

        level = self._conversation._thinking_kwargs().get("thinking")
        sketch_turn = ConversationFacilitator(format_mode="json", thinking=level)
        history = self._conversation._messages
        sketch_turn._messages = history  # the same list: one history
        before = len(history)
        sketch = await sketch_turn.submit(
            ViewSketchDto,
            view_sketch_prompt(focus, self._conversation.settings.component_length),
        )
        view = exploration_view_from_sketch(sketch)
        # What the turn leaves behind is NOT what it sent: the long request and
        # the DTO come off, and the person's ask plus the drawing in words go
        # on. Kept as a request→prose pair, the long request taught the next
        # view turn to answer in prose (`view_sketch.history_ask`).
        del history[before:]
        history.append(llm.messages.user(history_ask(focus)))
        history.append(
            llm.messages.assistant(history_text(view), model_id=None, provider_id=None)
        )
        return view

    @property
    def last_turn_timing(self) -> TurnTiming:
        """All reply path, by construction: nothing runs off it.

        `closing` and `deferral` stay `None` deliberately — there is no seam to
        conclude anything; `None` reads as "nothing to report", which is the
        truth. The retry account is read rather than defaulted, because a zero
        `retry_count` is a finding ("the turn ran clean") and must be earned.
        """
        retries = self._conversation.last_submit_retries
        return TurnTiming(
            reply_path_s=self._conversation.last_submit_seconds,
            off_path_s=0.0,
            retry_seconds=retries.wasted_s,
            retry_count=retries.count,
        )
