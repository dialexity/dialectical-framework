"""
Analyst: Conversational agent for dialectical analysis.

Scoped to a Case (sid). Helps users go from raw situations to structured
perspectives through dialectical reasoning.

Two modes:
- default: Autonomous pipeline (analyze tool) + steering tools.
- advanced: Granular step-by-step control over each operation.

Also contains AnalysisPipeline — the headless pipeline exposed as @llm.tool analyze().
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator, Literal, Optional

from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.analyst.system_prompts import (
    ADVANCED_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.stream_events import StreamEvent

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
            analyst = Analyst(app_preamble="You are a counselor...")
            response = await analyst.chat("I'm struggling with work-life balance")

        # Resuming with history:
        with scope(case.sid):
            analyst = Analyst(messages=loaded_messages)
            response = await analyst.chat("What about the second tension?")
    """

    def __init__(
        self,
        mode: Literal["default", "advanced"] = "default",
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
    ) -> None:
        self._mode = mode
        self._tools = _build_tool_list(mode)
        self._conversation = ConversationFacilitator(tools=self._tools)
        if messages:
            self._conversation._messages = list(messages)
        self._conversation.set_system_prompt(self._build_system_prompt(app_preamble))

    def _build_system_prompt(self, app_preamble: Optional[str] = None) -> str:
        parts = []
        if app_preamble:
            parts.append(app_preamble)
        if self._mode == "advanced":
            parts.append(ADVANCED_SYSTEM_PROMPT)
        else:
            parts.append(DEFAULT_SYSTEM_PROMPT)
        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        result = await self._conversation.submit(ChatResponse, user_message)
        return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        async for event in self._conversation.submit_stream(ChatResponse, user_message):
            yield event

    @property
    def messages(self) -> list:
        return self._conversation._messages

    @property
    def mode(self) -> str:
        return self._mode


def _build_tool_list(mode: str) -> list:
    if mode == "advanced":
        return _advanced_tools()
    return _default_tools()


def _default_tools() -> list:
    from dialectical_framework.agents.analyst.skills.edit_perspective import \
        edit_perspective
    from dialectical_framework.agents.analyst.tools.create_dx_input import \
        create_dx_input
    from dialectical_framework.agents.explorer.tools.create_nexus import \
        create_nexus
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.present_analysis import \
        present_analysis
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph
    from dialectical_framework.agents.orchestrator.tools.reject import reject

    return [
        analyze,
        create_nexus,
        create_dx_input,
        edit_perspective,
        reject,
        present_analysis,
        inspect_node,
        query_graph,
        get_schema,
    ]


def _advanced_tools() -> list:
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
    from dialectical_framework.agents.analyst.tools.create_dx_input import \
        create_dx_input
    from dialectical_framework.agents.analyst.tools.place_statement import \
        place_statement
    from dialectical_framework.agents.explorer.tools.create_nexus import \
        create_nexus
    from dialectical_framework.agents.orchestrator.tools.add_input import \
        add_input
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.present_analysis import \
        present_analysis
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph
    from dialectical_framework.agents.orchestrator.tools.reject import reject

    return [
        add_input,
        surface_theses,
        find_polarities,
        introduce_polarity,
        expand_polarities,
        place_statement,
        create_dx_input,
        edit_perspective,
        reject,
        create_nexus,
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
    ) -> None:
        self.text = text
        self.intent = intent
        self.thesis_hashes = thesis_hashes or []
        self.input_hashes = input_hashes

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
                errors.append(StepError(step="add_input", message=str(e)))

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
                    self._report.summary = "No theses found"
                    return AnalysisResult(
                        ideas_hash=ideas_hash, errors=errors, reports=reports
                    )
            except Exception as e:
                errors.append(StepError(step="surface_theses", message=str(e)))
                self._report.ok = False
                self._report.summary = f"Surface theses failed: {e}"
                return AnalysisResult(errors=errors, reports=reports)

        try:
            find = FindPolarities(thesis_hashes=thesis_hashes)
            await find.resolve()
            reports.append(find.report)

            polarity_data = find.report.artifacts.get("polarity_data", [])
            polarity_hashes = [
                p["polarity_hash"] for p in polarity_data if p.get("polarity_hash")
            ]
        except Exception as e:
            errors.append(StepError(step="find_polarities", message=str(e)))
            self._report.ok = True
            self._report.summary = (
                f"Found {len(thesis_hashes)} theses, polarity extraction failed"
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

        self._report.ok = True
        self._report.summary = (
            f"Analysis complete: {len(thesis_hashes)} theses, "
            f"{len(polarity_hashes)} polarities, "
            f"{len(perspective_hashes)} perspectives"
        )
        self._report.artifacts["thesis_hashes"] = thesis_hashes
        self._report.artifacts["polarity_hashes"] = polarity_hashes
        self._report.artifacts["perspective_hashes"] = perspective_hashes

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

    async def _expand_one(self, polarity_hash: str) -> tuple[list[str], object]:
        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity

        concern = ExpandPolarity(polarity_hash=polarity_hash)
        perspectives = await concern.resolve()
        pp_hashes = [pp.hash for pp in perspectives if pp.hash]
        return pp_hashes, concern.report


@llm.tool
async def analyze(
    text: str = Field(
        description="The user's situation, dilemma, or content to analyze"
    ),
    intent: Optional[str] = Field(
        default=None,
        description="Optional focus for analysis (e.g., 'focus on the trust dimension')",
    ),
    thesis_hashes: Optional[list[str]] = Field(
        default=None,
        description="Existing thesis hashes to develop further (skips input capture and extraction)",
    ),
    input_hashes: Optional[list[str]] = Field(
        default=None,
        description="Optional list of input hashes to process selectively. If None, processes all inputs in scope.",
    ),
) -> str:
    """Run full dialectical analysis: captures input, extracts theses, finds tensions, and builds complete perspectives with quality-gated expansion. Use when the user describes a new situation or provides material to analyze."""
    pipeline = AnalysisPipeline(
        text=text, intent=intent, thesis_hashes=thesis_hashes, input_hashes=input_hashes
    )
    await pipeline.resolve()
    return str(pipeline.report)
