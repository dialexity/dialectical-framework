"""
Analyst: Autonomous sub-agent for dialectical analysis.

Takes a situation and autonomously runs the full analysis pipeline:
surface theses → find polarities → score-gate → expand into perspectives.

Quality decisions are score-based: polarities are ranked by heuristic_similarity (HS)
and only the strongest are expanded. LLM tiebreaker when scores are equal.

Usage:
    # Programmatic (headless)
    analyst = Analyst(text="We're growing fast but culture is diluting...")
    result = await analyst.resolve()
    print(result.perspective_hashes)

    # Via orchestrator tool
    @llm.tool analyze(text=...) delegates here.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.analyst.skills.surface_theses import SurfaceTheses
from dialectical_framework.agents.analyst.skills.find_polarities import FindPolarities
from dialectical_framework.agents.analyst.skills.expand_polarities import ExpandPolarity
from dialectical_framework.agents.orchestrator.tools.add_input import AddInput


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


class Analyst(ReasonableConcern[AnalysisResult]):
    """
    Autonomous analyst sub-agent.

    Runs the full dialectical analysis pipeline with score-based quality gates.
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
    ) -> None:
        self.text = text
        self.intent = intent
        self.thesis_hashes = thesis_hashes or []

    async def resolve(self) -> AnalysisResult:
        errors: list[StepError] = []
        reports: list = []
        thesis_hashes = list(self.thesis_hashes)
        ideas_hash: Optional[str] = None
        polarity_hashes: list[str] = []
        perspective_hashes: list[str] = []

        # Step 1: Add input (if text provided)
        if self.text:
            try:
                add_input = AddInput()
                await add_input.resolve(content=self.text)
                reports.append(add_input.report)
            except Exception as e:
                errors.append(StepError(step="add_input", message=str(e)))

        # Step 2: Surface theses (if no thesis_hashes given)
        if not thesis_hashes:
            if not self.text and not self.intent:
                self._report.ok = False
                self._report.summary = "No text or thesis_hashes provided"
                return AnalysisResult(errors=[StepError(step="surface_theses", message="No text or thesis_hashes provided")])

            try:
                surface = SurfaceTheses(intent=self.intent or "extract key theses from the input")
                ideas = await surface.resolve()
                reports.append(surface.report)

                if ideas:
                    ideas_hash = ideas.hash
                    thesis_hashes = surface.report.artifacts.get("thesis_hashes", [])

                if not thesis_hashes:
                    self._report.ok = True
                    self._report.summary = "No theses found"
                    return AnalysisResult(ideas_hash=ideas_hash, errors=errors, reports=reports)
            except Exception as e:
                errors.append(StepError(step="surface_theses", message=str(e)))
                self._report.ok = False
                self._report.summary = f"Surface theses failed: {e}"
                return AnalysisResult(errors=errors, reports=reports)

        # Step 3: Find polarities
        try:
            find = FindPolarities(thesis_hashes=thesis_hashes)
            await find.resolve()
            reports.append(find.report)

            polarity_data = find.report.artifacts.get("polarity_data", [])
            polarity_hashes = [p["polarity_hash"] for p in polarity_data if p.get("polarity_hash")]
        except Exception as e:
            errors.append(StepError(step="find_polarities", message=str(e)))
            self._report.ok = True
            self._report.summary = f"Found {len(thesis_hashes)} theses, polarity extraction failed"
            return AnalysisResult(
                ideas_hash=ideas_hash,
                thesis_hashes=thesis_hashes,
                errors=errors,
                reports=reports,
            )

        if not polarity_hashes:
            self._report.ok = True
            self._report.summary = f"Found {len(thesis_hashes)} theses, no polarities emerged"
            return AnalysisResult(
                ideas_hash=ideas_hash,
                thesis_hashes=thesis_hashes,
                errors=errors,
                reports=reports,
            )

        # Step 4: Score gate — filter polarities by HS
        scored_polarities = self._rank_polarities(polarity_data)
        seen: set[str] = set()
        hashes_to_expand: list[str] = []
        for p in scored_polarities:
            h = p["polarity_hash"]
            if h not in seen:
                seen.add(h)
                hashes_to_expand.append(h)

        # Step 5: Expand polarities (parallel)
        expand_results = await asyncio.gather(
            *[self._expand_one(h) for h in hashes_to_expand],
            return_exceptions=True,
        )

        for i, result in enumerate(expand_results):
            if isinstance(result, Exception):
                errors.append(StepError(
                    step="expand_polarities",
                    message=str(result),
                    hash=hashes_to_expand[i],
                ))
            else:
                pp_hashes, report = result
                perspective_hashes.extend(pp_hashes)
                reports.append(report)

        # Final report
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
        """
        Score-based quality gate: rank polarities by HS, keep best ones.

        Filters out deduped entries (they point to existing polarities that may
        already be expanded). Keeps all above HS_THRESHOLD, capped at MAX.
        """
        valid = [
            p for p in polarity_data
            if p.get("polarity_hash") and not p.get("deduped", False)
        ]
        ranked = sorted(valid, key=lambda p: p.get("heuristic_similarity", 0), reverse=True)

        above_threshold = [p for p in ranked if p.get("heuristic_similarity", 0) >= HS_THRESHOLD]

        if above_threshold:
            return above_threshold[:MAX_POLARITIES_TO_EXPAND]

        # If nothing passes threshold, keep top entries anyway (at least try)
        return ranked[:MAX_POLARITIES_TO_EXPAND]

    async def _expand_one(self, polarity_hash: str) -> tuple[list[str], object]:
        """Expand a single polarity into perspectives."""
        concern = ExpandPolarity(polarity_hash=polarity_hash)
        perspectives = await concern.resolve()
        pp_hashes = [pp.hash for pp in perspectives if pp.hash]
        return pp_hashes, concern.report


@llm.tool
async def analyze(
    text: str = Field(description="The user's situation, dilemma, or content to analyze"),
    intent: Optional[str] = Field(default=None, description="Optional focus for analysis (e.g., 'focus on the trust dimension')"),
    thesis_hashes: Optional[list[str]] = Field(default=None, description="Existing thesis hashes to develop further (skips input capture and extraction)"),
) -> str:
    """Run full dialectical analysis: captures input, extracts theses, finds tensions, and builds complete perspectives with quality-gated expansion. Use when the user describes a new situation or provides material to analyze."""
    agent = Analyst(text=text, intent=intent, thesis_hashes=thesis_hashes)
    result = await agent.resolve()
    return str(agent.report)
