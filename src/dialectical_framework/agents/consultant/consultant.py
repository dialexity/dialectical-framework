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

import dataclasses
import logging
import re
from contextlib import aclosing
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional

from mirascope import llm
from mirascope.llm.exceptions import ProviderError

from dialectical_framework.agents.advisor.advisor import ChatResponse
from dialectical_framework.agents.advisor.system_prompts import (
    _CONVERSATION_USE, _DECISION_READINESS, _EAGER, _EXPLORE_BEFORE_CEREMONY,
    _HOW_YOU_SPEAK, _INTERNAL_MODEL, _ONE_TENSION_IS_ENOUGH, _ROLE)
from dialectical_framework.agents.app_spec import AppSpec, resolve_app_layer
from dialectical_framework.agents.conversation_facilitator import (
    FROM_SETTINGS, ConversationFacilitator)
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.agents.turn_timing import TurnTiming
from dialectical_framework.exceptions.provider_errors import ModelRefusal
from dialectical_framework.graph.views import (
    ExplorationView,
    FailedDrawView,
    PerspectiveView,
)

if TYPE_CHECKING:
    # Imported lazily inside `exploration_view` at runtime (the concern pulls
    # the judges in); only the annotation needs it here.
    from dialectical_framework.concerns.tetrad_candidates import SketchVerdict

logger = logging.getLogger(__name__)

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


def _with_verdict(
    perspective: PerspectiveView, verdict: Optional[SketchVerdict]
) -> PerspectiveView:
    """The drawn tension with the fit judge's two reads on it, when it was
    judged; a `None` verdict (judging failed on that draw) leaves both None."""
    if verdict is None:
        return perspective
    return dataclasses.replace(
        perspective,
        thesis_fit=verdict.thesis_fit,
        antithesis_granted=verdict.antithesis_granted,
    )


def _failed_draw(error: BaseException) -> FailedDrawView:
    """A failed draw's record: the exception's type, the provider's refusal
    category when it is a `ModelRefusal` that carries one, and its text.

    The type is the PROVIDER's where Mirascope wrapped one: its `ProviderError`
    subclasses carry the SDK exception as `original_exception`, and that is
    the name a host counts by (`APITimeoutError` for a stalled draw, where the
    wrapper says only `TimeoutError` — the builtin's name too). `ParseError`
    is not a `ProviderError` and keeps its own name.
    """
    original = (
        getattr(error, "original_exception", None)
        if isinstance(error, ProviderError)
        else None
    )
    return FailedDrawView(
        kind=type(original if isinstance(original, BaseException) else error).__name__,
        category=getattr(error, "category", None) if isinstance(error, ModelRefusal) else None,
        message=str(error) or None,
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


#: The view turn's ONE re-ask when every draw's opposition is a view the
#: person's words already grant (`concerns/view_sketch.GRANTED_OPPOSITION_REASK`).
#: OFF, by measurement (2026-10-28, `tests/e2e/probe_granted_opposition_redraw.py`,
#: the 22 conceding petitions, best-of-3, paired, fresh judges on the final
#: card): it fired on 5 of 22 cards and the granted A went 5 → 4 against a
#: pre-registered bar of −4 (discordant 1 win / 2 losses), while coherence
#: went 21 → 18, the whole of its −3 allowance, and the antithesis kind held
#: (22 against 21 positions). Of the five re-draws two became the card with a
#: real opposition (one of them failing a fresh CC), one won still carrying
#: the granted view at the line, and two — each a different opposition —
#: lost the ranking to the granted original on the pass rule. A miss is a
#: miss: the mechanism stays here as the measured arm the probe can re-run
#: (the WITH arm sets this True), and no deployment turns it on. Re-run with
#: the writer on Opus 5.5 the same day: fired on 4, granted A 4 → 4, the same
#: four petitions as Sonnet 5.5 drew — the model is not the lever either. Record:
#: `docs/dev-notes/antithesis-selection.md`, "A is the view the author granted".
REDRAW_ON_GRANTED_OPPOSITION = False


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
        #: The granted view the last `exploration_view` re-asked about, or None
        #: when it sent no re-ask (one draw, a field not unanimous, the switch
        #: off — which it is). Read by the gate probe.
        self.last_view_redraw: Optional[str] = None

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

    async def exploration_view(
        self,
        focus: Optional[str] = None,
        attempts: Optional[int] = None,
        thesis: Optional[str] = None,
    ) -> ExplorationView:
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

        `thesis` pins T to the host's own text, VERBATIM: the request says so
        (`view_sketch.THESIS_IS_FIXED`) and the given words are then written
        back over whatever each draw wrote, so the guarantee is code and not
        compliance. For a host that shows the person their own sentence as
        their position, a seven-word recomposition of it is a different
        sentence. The rest of the tetrad is still built — and still built
        around the pinned position, which is why the request carries the text
        too rather than relying on the overwrite alone. Not the same contract
        as `SketchTetrad(thesis=)`, which asks for the position condensed to
        `component_length` because the graph stores a headline.

        Terminology-free by construction (no hash, alias or score exists),
        unchecked by construction (no HS gate, no validation, nothing
        persisted). Not a tool: the model cannot call this, and the prompt's
        "You have no tools" stays true. Raises on a provider failure rather
        than returning an empty view, so the host can tell "nothing drawn"
        from "the drawing failed".
        """
        from dialectical_framework.concerns.view_sketch import (
            ViewSketchDto, ViewSketchPerspectiveDto,
            exploration_view_from_sketch, history_ask, history_text,
            judge_context, perspective_from_sketch, view_sketch_prompt)

        import asyncio
        import dataclasses

        from dialectical_framework.agents.advisor.migration import person_turns
        from dialectical_framework.concerns.attribution_check import \
            drop_unborne_holders
        from dialectical_framework.concerns.tetrad_candidates import (
            clamp_attempts, every_opposition_granted, judge_candidates,
            ranking, select_sketch)

        level = self._conversation._thinking_kwargs().get("thinking")
        history = self._conversation._messages
        self.last_view_redraw = None
        max_words = self._conversation.settings.component_length
        # The WHOLE request is the turn's user message, its "Answer with ONE
        # JSON object" included — by measurement, not habit. For one day
        # (2026-10-06) the static instructions rode on the system prompt so the
        # cache would cover them (~$0.007 a card) and only "What to show: ..."
        # was the turn. First cards did not notice; a RETRY did: its history
        # already holds "Show me: ..." and the previous drawing in PROSE, and with
        # a bare focus as the last user turn the model answered in prose too —
        # 1.75 parse retries a retry card, 4.75 view-turn calls instead of 3,
        # 33 s instead of 20 (`tests/e2e/probe_view_turn_retry_calls.py`, 8
        # utterances; the first app had measured the same 4.6 calls and +17 s).
        # The request->prose pair `history_ask` keeps OUT of the history is the
        # same trap; the long request as the last turn is what holds the format.
        request = view_sketch_prompt(focus, max_words, thesis=thesis)

        async def draw(ask: str) -> ViewSketchDto:
            # Each draw works on a COPY of the history: the turns run in
            # parallel and none of them may write into the record the others
            # read. What the view leaves behind is appended once, below.
            sketch_turn = ConversationFacilitator(format_mode="json", thinking=level)
            sketch_turn._messages = list(history)
            return await sketch_turn.submit(ViewSketchDto, ask)

        # Fully parallel, deliberately. On a COLD cache all N draws write the
        # ~12k system head instead of one writing and the rest reading (~$0.06
        # a card at list prices, 2026-10-06), and the fix would be to await the
        # first draw before firing the rest — but these turns do not stream, so
        # nothing here can tell a cold cache from a warm one, and the stagger
        # would spend a whole draw's latency (~6 s) on EVERY card to save money
        # on the rare one. The 1h breakpoint TTL
        # (`utils/bedrock_provider.py::_CACHE_TTL`) attacks the same cost
        # without the latency, which is the trade taken. Revisit only with a
        # measured cold-start rate.
        n = clamp_attempts(attempts)
        # The SAME request N times, by measurement: N identical requests draw
        # the same opposition N times, reworded (the first app, 52/52 cards),
        # and asking draw 2..N for a different one made the spares differ and
        # the winner worse (CC 19/40 against 27/40, 2026-10-13,
        # `tests/e2e/probe_view_turn_ask.py`) — so this is a coherence re-roll,
        # and a host's "another" served from `runners_up` is a rewording.
        drawn = await asyncio.gather(*(draw(request) for _ in range(n)), return_exceptions=True)
        sketches = [d for d in drawn if not isinstance(d, BaseException)]
        failures = [d for d in drawn if isinstance(d, BaseException)]
        # A failed draw is a finding, not noise: it costs the card a candidate
        # (or its whole comparison, when two fail) and it costs time before it
        # fails. Said once per failure, by type — the host that counted 8 lost
        # draws in 240 on Opus 5.5 had no cause on record because this branch
        # was silent — and carried on the view as `failed_draws`.
        failed_draws = [_failed_draw(e) for e in failures]
        for failed in failed_draws:
            logger.warning(
                "A view-turn draw failed (%d of %d drawn): %s%s: %s",
                len(sketches), n, failed.kind,
                f" ({failed.category})" if failed.category else "",
                failed.message,
            )
        if not sketches:
            raise failures[0]
        # The pin, enforced: every draw's first tension carries the host's own
        # words as T, so the winner and any runner-up a host serves later all
        # show the sentence the person typed. Done before selection, so the
        # coherence check judges the tetrad the host will actually get.
        pinned = (thesis or "").strip()

        def pin(drawn_sketch: ViewSketchDto) -> None:
            if pinned and drawn_sketch.tensions:
                drawn_sketch.tensions[0].thesis = pinned
                # A pinned position is the host's own words for the
                # person's own position: never someone else's.
                drawn_sketch.tensions[0].thesis_held_by = ""

        for drawn_sketch in sketches:
            pin(drawn_sketch)
        # The person's turns, for the judges below. Also the words a named
        # holder is checked against.
        words = judge_context(person_turns(history))
        # A holder the words do not bear is dropped, in code, on every draw
        # (`concerns/attribution_check.py`, 2026-10-27): the prompt rule
        # halved the misquotation on pasted material and did not end it, and a
        # runner-up served later must not carry one either. No call where no
        # holder is named — the person's own words cost nothing here.
        firsts_to_check = [s.tensions[0] for s in sketches if s.tensions]
        for dropped in await drop_unborne_holders(firsts_to_check, words):
            logger.info("A drawn holder was dropped: %s", dropped)
        # With several draws the framework's own coherence check picks the one
        # whose FIRST tension holds best (`concerns/tetrad_candidates.py`); a
        # draw with no complete first tension sorts last. The card a blindspot
        # screen shows is that first tension. The judged draws that lost come
        # back too, best first, as `runners_up` — a host's "again"/"another"
        # can serve one without a new call (the module's stated intent).
        # The judge reads the PERSON's turns as its context (`judge_context`):
        # it never sees T or A, and called blind — as it was here until
        # 2026-10-13, while the build and the persisted path passed their
        # material — it scored the four aspects against nothing.
        def complete(tension: Optional[ViewSketchPerspectiveDto]) -> bool:
            return tension is not None and all(
                (getattr(tension, k) or "").strip()
                for k in ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")
            )

        runners_up: list[PerspectiveView] = []
        winner_verdict: Optional[SketchVerdict] = None
        if len(sketches) > 1:
            firsts = [s.tensions[0] if s.tensions else None for s in sketches]
            judgeable = [i for i, t in enumerate(firsts) if complete(t)]
            if len(judgeable) > 1:
                # This writer CHOOSES the thesis, so a second judge reads each
                # draw's T, A and A+ against the person's words — the claim
                # they would sign, an opposition they have not granted
                # (`tetrad_candidates.judge_fit`, 2026-10-20). With a pinned T
                # the first read is the same on every draw and the second
                # still tells them apart.
                field = [sketches[i] for i in judgeable]
                pool = [firsts[i] for i in judgeable]
                _best, verdicts = await select_sketch(pool, context=words, fit_against=words)
                # THE ONE RE-ASK (2026-10-28), OFF by measurement — see the
                # constant. The draws of one request are one tension reworded,
                # so when the fit judge reads EVERY draw's A as a view the
                # person's words already grant, no selection can help — the
                # handoff's "X is true, however Y" cards had A = X in every
                # rep. One more request names that view and asks for the
                # opposition to the claim actually made; the re-draw is judged
                # once and joins the field under the SAME ranking, so it wins
                # only if it passes and fits, and a passing original beats a
                # re-draw that fails the pass rule (every keep-any-passing
                # figure stands). Unanimity is the trigger; never a loop. On
                # the gate it fixed 2 of the 5 cards it fired on and cost 3
                # coherence passes of 22, which missed the bar.
                if REDRAW_ON_GRANTED_OPPOSITION and every_opposition_granted(verdicts):
                    granted = pool[ranking(verdicts)[0]].antithesis
                    try:
                        again: Optional[ViewSketchDto] = await draw(
                            view_sketch_prompt(
                                focus, max_words, thesis=thesis, granted_opposition=granted
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 — the card stands on its draws
                        failed_draws.append(_failed_draw(exc))
                        logger.warning("The view turn's re-ask failed; the card stands on its draws: %s", exc)
                        again = None
                    if again is not None and again.tensions and complete(again.tensions[0]):
                        pin(again)
                        for dropped in await drop_unborne_holders([again.tensions[0]], words):
                            logger.info("A drawn holder was dropped: %s", dropped)
                        (verdict,) = await judge_candidates(
                            [again.tensions[0]], context=words, fit_against=words
                        )
                        field.append(again)
                        pool.append(again.tensions[0])
                        verdicts.append(verdict)
                        self.last_view_redraw = granted
                        logger.info(
                            "The view turn re-asked once: every draw opposed a granted view (%r); "
                            "the re-draw %s",
                            granted,
                            "ranks first" if ranking(verdicts)[0] == len(pool) - 1 else "did not win",
                        )
                order = ranking(verdicts)
                sketch = field[order[0]]
                winner_verdict = verdicts[order[0]]
                runners_up = [
                    _with_verdict(perspective_from_sketch(pool[i]), verdicts[i])
                    for i in order[1:]
                ]
            else:
                sketch = sketches[judgeable[0]] if judgeable else sketches[0]
        else:
            sketch = sketches[0]
        view = dataclasses.replace(
            exploration_view_from_sketch(sketch),
            runners_up=runners_up,
            failed_draws=failed_draws,
        )
        # The winner's verdict rides on the card it was chosen for (the first
        # tension is what the ranking judged), and each runner-up carries its
        # own, so a spare served later says the same thing about itself. The
        # fit judge's A read is what a host shows a line for; nothing here
        # changes the choice (the app's handoff of 2026-10-29).
        if winner_verdict is not None and view.perspectives:
            view = dataclasses.replace(
                view,
                perspectives=[
                    _with_verdict(view.perspectives[0], winner_verdict),
                    *view.perspectives[1:],
                ],
            )
        # What the turn leaves behind is NOT what it sent: the long request and
        # the DTO come off, and the person's ask plus the drawing in words go
        # on. Kept as a request→prose pair, the long request taught the next
        # view turn to answer in prose (`view_sketch.history_ask`).
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
