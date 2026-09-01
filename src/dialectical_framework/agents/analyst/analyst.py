"""
Analyst: Conversational agent for dialectical analysis.

Scoped to a Case (sid). Helps users go from raw situations to structured
perspectives through dialectical reasoning.

Also contains AnalysisPipeline — the headless pipeline exposed as @llm.tool analyze().
"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
from typing import TYPE_CHECKING, Annotated, AsyncGenerator, Optional

from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.graph.scope_context import require_current_sid
from dialectical_framework.agents.analyst.system_prompts import SYSTEM_PROMPT
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.app_spec import AppSpec, resolve_app_layer
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.agents.toolsets import merge_app_tools
from dialectical_framework.utils.progress import (expect_progress,
                                                 report_progress)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Conversational Agent
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Response from the analyst chat."""

    message: str = Field(description="The assistant's response message")


class Analyst:
    """
    Conversational agent for dialectical analysis.

    The host app is responsible for:
    - Creating the Case and managing scope(sid)
    - Persisting and loading conversation messages
    - Wrapping chat() calls in `with scope(sid):`

    Usage:
        with scope(case.sid):
            analyst = Analyst(app=MY_APP_SPEC)  # declarative (see AppSpec)
            response = await analyst.chat("I'm struggling with work-life balance")

        # Resuming with history:
        with scope(case.sid):
            analyst = Analyst(messages=loaded_messages)
            response = await analyst.chat("What about the second tension?")

        # Manual preamble control (app_preamble replaces AppSpec composition):
        with scope(case.sid):
            analyst = Analyst(app_preamble="You are a counselor...")
    """

    AGENT_NAME = "analyst"

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
        app_tools: Optional[list] = None,
        app: Optional[AppSpec] = None,
    ) -> None:
        # app: declarative app definition — the framework composes the
        # Navigator preamble (NAVIGATOR_APP + voicing + tool_guide) and tool
        # set from it. app_preamble/app_tools remain for manual control;
        # mixing them with app= raises (see app_spec.resolve_app_layer).
        app_preamble, app_tools = resolve_app_layer(
            app, app_preamble, app_tools, preamble_for="navigator"
        )
        self._tools = merge_app_tools(_build_tools(), app_tools)
        self._conversation = ConversationFacilitator(tools=self._tools)
        if messages:
            self._conversation._messages = list(messages)
        self._conversation.set_system_prompt(self._build_system_prompt(app_preamble))

    def _build_system_prompt(self, app_preamble: Optional[str] = None) -> str:
        parts = []
        if app_preamble:
            parts.append(app_preamble)
        parts.append(SYSTEM_PROMPT)
        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            result = await self._conversation.submit(ChatResponse, user_message)
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        """Stream one turn's events. **The caller owes this generator a CLOSE** —
        see `Advisor.chat_stream`, which carries the whole argument; a bare
        `async for` with a `break` defers the provider connection to the collector.
        """
        require_current_sid()  # unscoped turns silently drop all work
        with agent_scope(self.AGENT_NAME):
            # `aclosing` for the reason spelled out in `Advisor.chat_stream`: only a
            # close runs `submit_stream`'s cleanup on the abandoned exit, and this
            # link fires only once the caller closes THIS generator.
            async with aclosing(
                self._conversation.submit_stream(ChatResponse, user_message)
            ) as rounds:
                async for event in rounds:
                    yield event

    @property
    def messages(self) -> list:
        return self._conversation._messages


def _build_tools() -> list:
    from dialectical_framework.agents.analyst.skills.anchor_theses import \
        anchor_theses
    from dialectical_framework.agents.analyst.skills.edit_perspective import \
        edit_perspective
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        expand_polarities
    from dialectical_framework.agents.analyst.skills.find_polarities import \
        find_polarities
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        introduce_polarity
    from dialectical_framework.agents.analyst.skills.surface_theses import \
        surface_theses
    from dialectical_framework.agents.analyst.tools.place_statement import \
        place_statement
    from dialectical_framework.agents.explorer.tools.create_nexus import \
        create_nexus
    from dialectical_framework.agents.explorer.tools.expand_nexus import \
        expand_nexus
    from dialectical_framework.agents.orchestrator.tools.add_input import \
        add_input
    from dialectical_framework.agents.orchestrator.tools.create_dx_input import \
        create_dx_input
    from dialectical_framework.agents.orchestrator.tools.digest_input import \
        digest_input
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.present_analysis import \
        present_analysis
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest
    from dialectical_framework.agents.orchestrator.tools.read_input import \
        read_input
    from dialectical_framework.agents.orchestrator.tools.discard import discard

    return [
        analyze,
        add_input,
        digest_input,
        read_digest,
        read_input,
        anchor_theses,
        surface_theses,
        find_polarities,
        introduce_polarity,
        expand_polarities,
        place_statement,
        create_dx_input,
        edit_perspective,
        discard,
        create_nexus,
        expand_nexus,
        present_analysis,
        inspect_node,
        query_graph,
        get_schema,
    ]


# ---------------------------------------------------------------------------
# Headless Pipeline (exposed as @llm.tool)
# ---------------------------------------------------------------------------


class StepError(BaseModel):
    step: str
    message: str
    hash: Optional[str] = None


class AnalysisResult(BaseModel):
    ideas_hash: Optional[str] = None
    thesis_hashes: list[str] = []
    polarity_hashes: list[str] = []
    perspective_hashes: list[str] = []
    errors: list[StepError] = []
    reports: list = []

    model_config = {"arbitrary_types_allowed": True}


HS_THRESHOLD = 0.7
MAX_POLARITIES_TO_EXPAND = 5


class AnalysisPipeline(ReasonableConcern[AnalysisResult]):
    """
    Autonomous analyst pipeline.

    Runs the full dialectical analysis with score-based quality gates.
    Does not interact with the user — curates the graph and returns results.

    Entry points:
        - text provided: full pipeline (add input → surface → find → expand)
        - thesis_hashes provided: partial pipeline (find polarities → expand)
    """

    def __init__(
        self,
        text: Optional[str] = None,
        intent: Optional[str] = None,
        thesis_hashes: Optional[list[str]] = None,
        input_hashes: Optional[list[str]] = None,
        grounding_context: Optional[str] = None,
    ) -> None:
        self.text = text
        self.intent = intent
        self.thesis_hashes = thesis_hashes or []
        self.input_hashes = input_hashes
        #: Conversational material about ONE tension, forwarded to every
        #: `ExpandPolarity` this run performs so the case particulars survive
        #: the abstraction into ~7-word poles (`TetradGrounding`).
        #:
        #: Only `anchor`'s thesis-only branch sets this, and the restriction is
        #: the point: one extraction is reused across every tetrad the run
        #: produces, which is sound when the material describes a single
        #: tension and wrong when it does not. `ingest` material is a whole
        #: document holding several unrelated tensions, so forwarding it here
        #: would stamp one tension's facts onto another's tetrad. Bulk material
        #: keeps its particulars in the Input digest (`read_digest`) instead.
        self.grounding_context = (grounding_context or "").strip() or None

    async def resolve(self) -> AnalysisResult:
        from dialectical_framework.agents.analyst.skills.find_polarities import \
            FindPolarities
        from dialectical_framework.agents.analyst.skills.surface_theses import \
            SurfaceTheses
        from dialectical_framework.agents.orchestrator.tools.add_input import \
            AddInput

        errors: list[StepError] = []
        reports: list = []
        thesis_hashes = list(self.thesis_hashes)
        ideas_hash: Optional[str] = None
        polarity_hashes: list[str] = []
        perspective_hashes: list[str] = []

        if self.text:
            try:
                add_input = AddInput()
                await add_input.resolve(content=self.text)
                reports.append(add_input.report)
            except Exception as e:
                self._report.ok = False
                self._report.summary = f"Failed to capture input: {e}"
                return AnalysisResult(
                    errors=[StepError(step="add_input", message=str(e))]
                )

        if not thesis_hashes:
            if not self.text and not self.intent:
                self._report.ok = False
                self._report.summary = "No text or thesis_hashes provided"
                return AnalysisResult(
                    errors=[
                        StepError(
                            step="surface_theses",
                            message="No text or thesis_hashes provided",
                        )
                    ]
                )

            try:
                surface = SurfaceTheses(
                    intent=self.intent or "extract key theses from the input",
                    input_hashes=self.input_hashes,
                )
                ideas = await surface.resolve()
                reports.append(surface.report)

                if ideas:
                    ideas_hash = ideas.hash
                    thesis_hashes = surface.report.artifacts.get("thesis_hashes", [])

                if not thesis_hashes:
                    self._report.ok = True
                    self._report.summary = (
                        "No tensions extracted from this material. Anchor an "
                        "explicit position (and its opposition, if visible) "
                        "instead of ingesting."
                    )
                    return AnalysisResult(
                        ideas_hash=ideas_hash, errors=errors, reports=reports
                    )
            except Exception as e:
                errors.append(StepError(step="surface_theses", message=str(e)))
                self._report.ok = False
                self._report.summary = f"Surface theses failed: {e}"
                return AnalysisResult(errors=errors, reports=reports)

        try:
            # The `anchor` thesis-only branch's own long stage: nothing has been
            # said since the position was classified, and this is where the
            # opposition is discovered and scored.
            expect_progress(1)
            report_progress("Looking for what genuinely pushes back")
            find = FindPolarities(thesis_hashes=thesis_hashes)
            await find.resolve()
            reports.append(find.report)

            polarity_data = find.report.artifacts.get("polarity_data", [])
            polarity_hashes = [
                p["polarity_hash"] for p in polarity_data if p.get("polarity_hash")
            ]
        except Exception as e:
            errors.append(StepError(step="find_polarities", message=str(e)))
            # ok=False and the message in the summary, for the same reason the
            # expansion block below says so: `errors` rides home on
            # AnalysisResult, which no tool renders, so a bare "polarity
            # extraction failed" is the whole story the agent gets. In
            # `claim2-weak-r14` that story was `anchor:ok` over a case where a
            # cardinality ValueError had killed every polarity — the third time
            # a swallowed message on this exact path cost a bench run its
            # diagnosis.
            self._report.ok = False
            self._report.summary = (
                f"Found {len(thesis_hashes)} theses, polarity extraction "
                f"FAILED ({e})"
            )
            return AnalysisResult(
                ideas_hash=ideas_hash,
                thesis_hashes=thesis_hashes,
                errors=errors,
                reports=reports,
            )

        if not polarity_hashes:
            self._report.ok = True
            self._report.summary = (
                f"Found {len(thesis_hashes)} theses, no polarities emerged"
            )
            return AnalysisResult(
                ideas_hash=ideas_hash,
                thesis_hashes=thesis_hashes,
                errors=errors,
                reports=reports,
            )

        scored_polarities = self._rank_polarities(polarity_data)
        seen: set[str] = set()
        hashes_to_expand: list[str] = []
        for p in scored_polarities:
            h = p["polarity_hash"]
            if h not in seen:
                seen.add(h)
                hashes_to_expand.append(h)

        # Surface the HS-based gate to the agent. _rank_polarities silently
        # drops tensions below HS_THRESHOLD (and beyond the top few); without
        # this the agent only sees a bare perspective count and cannot explain
        # WHY these framings are the strong ones or that weaker tensions were
        # set aside.
        polarity_quality = self._build_polarity_quality(polarity_data, hashes_to_expand)
        set_aside_count = sum(1 for q in polarity_quality if q["status"] == "set_aside")
        # Strong enough to expand, dropped for budget — owed work, not a
        # judgement. Reported separately so a resuming session can ask for it.
        deferred_count = sum(1 for q in polarity_quality if q["status"] == "deferred")

        expand_results = await asyncio.gather(
            *[self._expand_one(h) for h in hashes_to_expand],
            return_exceptions=True,
        )

        for i, result in enumerate(expand_results):
            if isinstance(result, Exception):
                errors.append(
                    StepError(
                        step="expand_polarities",
                        message=str(result),
                        hash=hashes_to_expand[i],
                    )
                )
            else:
                pp_hashes, report = result
                perspective_hashes.extend(pp_hashes)
                reports.append(report)
                # A sub-skill that reports ok=False did not raise, so without
                # this its failure would reach only `reports` — which the
                # pipeline discards (see the class note on report merging).
                if getattr(report, "ok", True) is False:
                    errors.append(
                        StepError(
                            step="expand_polarities",
                            message=getattr(report, "summary", "")
                            or "expansion reported failure",
                            hash=hashes_to_expand[i],
                        )
                    )

        expansion_errors = [e for e in errors if e.step == "expand_polarities"]
        # An expansion that was attempted and failed is not an expanded tension.
        # `status` was set to "expanded" before the gather (it records the gate
        # decision), so without this correction a crashed expansion reads as
        # done — the one state a resuming session most needs to see, since the
        # tension has a Polarity and no usable Perspective.
        failed_hashes = {e.hash for e in expansion_errors if e.hash}
        if failed_hashes:
            for q in polarity_quality:
                if q["polarity_hash"] in failed_hashes:
                    q["status"] = "failed"
        # Producing NO perspectives is a failed analysis, not a quiet success.
        # This block used to set ok=True unconditionally and drop `errors` on
        # the floor (they rode home on AnalysisResult, which no tool renders),
        # so a pipeline whose every expansion raised reported "Analysis
        # complete: 2 theses, 2 polarities, 0 perspectives" and the `anchor`
        # tool that composes it reported `anchor:ok`. Measured in
        # `claim2-weak-r1`: two A2 cells logged `anchor:ok` repeatedly and then
        # summarised `perspectives=0` — the arm whose whole claim is a durable
        # record looked like a model that declined to build one. Same rule as
        # the repositories' fail-soft reads: degrade, but never silently.
        self._report.ok = bool(perspective_hashes) or not errors
        set_aside_note = (
            f", {set_aside_count} weaker tension(s) set aside"
            if set_aside_count
            else ""
        )
        deferred_note = (
            f", {deferred_count} strong tension(s) NOT expanded (budget: "
            f"{MAX_POLARITIES_TO_EXPAND} per run) — call again to develop them"
            if deferred_count
            else ""
        )
        self._report.summary = (
            f"Analysis complete: {len(thesis_hashes)} theses, "
            f"{len(polarity_hashes)} polarities, "
            f"{len(perspective_hashes)} perspectives"
            f"{set_aside_note}{deferred_note}"
        )
        if expansion_errors:
            failed = "; ".join(
                f"{e.hash or '?'}: {e.message}" for e in expansion_errors
            )
            self._report.summary += (
                f" — {len(expansion_errors)} tension(s) FAILED to expand "
                f"({failed})"
            )
        self._report.artifacts["thesis_hashes"] = thesis_hashes
        self._report.artifacts["polarity_hashes"] = polarity_hashes
        self._report.artifacts["perspective_hashes"] = perspective_hashes
        self._report.artifacts["polarity_quality"] = polarity_quality
        if errors:
            self._report.artifacts["errors"] = [e.model_dump() for e in errors]

        return AnalysisResult(
            ideas_hash=ideas_hash,
            thesis_hashes=thesis_hashes,
            polarity_hashes=polarity_hashes,
            perspective_hashes=perspective_hashes,
            errors=errors,
            reports=reports,
        )

    def _rank_polarities(self, polarity_data: list[dict]) -> list[dict]:
        valid = [
            p
            for p in polarity_data
            if p.get("polarity_hash") and not p.get("deduped", False)
        ]
        ranked = sorted(
            valid, key=lambda p: p.get("heuristic_similarity", 0), reverse=True
        )

        above_threshold = [
            p for p in ranked if p.get("heuristic_similarity", 0) >= HS_THRESHOLD
        ]

        if above_threshold:
            return above_threshold[:MAX_POLARITIES_TO_EXPAND]

        return ranked[:MAX_POLARITIES_TO_EXPAND]

    @staticmethod
    def _build_polarity_quality(
        polarity_data: list[dict], hashes_to_expand: list[str]
    ) -> list[dict]:
        """Per-tension HS + gate outcome, HS-descending, for the agent to read.

        Makes the otherwise-silent HS gate visible: each entry flags whether the
        tension was `expanded` into a full perspective or set aside. HS on the
        antithesis measures how genuine the opposition is (see "Reading Polarity
        Quality" in the system prompt), not the quality of the idea itself.
        """
        expanded_set = set(hashes_to_expand)
        quality: list[dict] = []
        seen: set[str] = set()
        for p in polarity_data:
            h = p.get("polarity_hash")
            if not h or h in seen or p.get("deduped", False):
                continue
            seen.add(h)
            hs = p.get("heuristic_similarity")
            quality.append(
                {
                    "polarity_hash": h,
                    "thesis": p.get("thesis_text"),
                    "antithesis": p.get("antithesis_text"),
                    "hs": hs,
                    "expanded": h in expanded_set,
                    # WHY it wasn't expanded, not just that it wasn't. `expanded:
                    # False` conflated two opposite situations: a tension the HS
                    # gate judged too weak (working as designed, nothing to do)
                    # and one strong enough to expand that got dropped for
                    # budget (MAX_POLARITIES_TO_EXPAND) — real work still owed.
                    # Only the latter is worth a follow-up call.
                    "status": (
                        "expanded"
                        if h in expanded_set
                        else (
                            "deferred"
                            if hs is not None and hs >= HS_THRESHOLD
                            else "set_aside"
                        )
                    ),
                }
            )
        quality.sort(
            key=lambda q: q["hs"] if q["hs"] is not None else 0.0, reverse=True
        )
        return quality

    async def _expand_one(self, polarity_hash: str) -> tuple[list[str], object]:
        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity

        concern = ExpandPolarity(
            polarity_hash=polarity_hash,
            grounding_context=self.grounding_context,
        )
        perspectives = await concern.resolve()
        pp_hashes = [pp.hash for pp in perspectives if pp.hash]
        return pp_hashes, concern.report


@llm.tool
async def analyze(
    text: Annotated[
        str, Field(description="The user's situation, dilemma, or content to analyze")
    ],
    intent: Annotated[
        str | None,
        Field(
            description="Optional focus for analysis (e.g., 'focus on the trust dimension')"
        ),
    ] = None,
    thesis_hashes: Annotated[
        list[str] | None,
        Field(
            description="Existing thesis hashes to develop further (skips input capture and extraction)"
        ),
    ] = None,
    input_hashes: Annotated[
        list[str] | None,
        Field(
            description="Optional list of input hashes to process selectively. If None, processes all inputs in scope."
        ),
    ] = None,
) -> str:
    """Run full dialectical analysis: captures input, extracts theses, finds tensions, and builds complete perspectives with quality-gated expansion. Use when the user describes a new situation or provides material to analyze."""
    pipeline = AnalysisPipeline(
        text=text, intent=intent, thesis_hashes=thesis_hashes, input_hashes=input_hashes
    )
    await pipeline.resolve()
    return str(pipeline.report)
