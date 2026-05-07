"""
IdeaPlacement: Concern for determining where an idea belongs in the dialectical graph.

Given an arbitrary idea and existing graph state, determines:
- Is it a duplicate of an existing component?
- Is it an antithesis of an existing thesis?
- Is it an aspect (T+/T-/A+/A-) of an existing tension?
- Or is it a new thesis?

This is the routing concern for agentic apps where the user introduces
ideas without specifying the position.

Flow:
1. Check for semantic duplicate (LLM check, no component created yet)
2. If not duplicate, determine placement type (thesis/antithesis/aspect)
3. Run appropriate classification based on placement:
   - thesis -> StatementClassification
   - antithesis -> AntithesisClassification
   - aspect -> AspectClassification
4. Create component with proper meaning from classification
5. Attach Rationale with placement + classification reasoning

Usage:
    placer = IdeaPlacement()
    result = await placer.resolve(
        idea="Hate",
        vocabulary=[love_component, trust_component, ...],
        tensions=[(love, indifference), ...],
        text="context about relationships..."
    )

    if result.placement == "antithesis":
        print(f"Hate is antithesis of {result.antithesis_of}")
    elif result.placement == "aspect":
        print(f"Hate is {result.position} of {result.aspect_of}")

    # The component is always available (with proper classification)
    component = result.component
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.aspect_classification import \
    AspectClassification
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.concerns.statement_deduplication import \
    StatementDeduplication
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical idea placement specialist.

Your task is to determine where a new idea belongs in an existing dialectical structure.
Note: Duplicate detection has already been done - the idea is NOT a duplicate.

## Placement Types

1. **ANTITHESIS**: The idea is a dialectical opposite of an existing thesis
   - Creates tension with the thesis
   - Represents opposition, negation, or absence
   - Only consider if the existing component is a thesis (not already an antithesis)

2. **ASPECT**: The idea is a positive/negative aspect of an existing tension
   - T+: Positive aspect of thesis (benefit, strength)
   - T-: Negative aspect of thesis (risk, shadow)
   - A+: Positive aspect of antithesis (benefit, strength)
   - A-: Negative aspect of antithesis (risk, shadow)
   - Only consider if a tension (T-A pair) exists

3. **THESIS**: The idea is a new thesis
   - Not related to existing components
   - Or related but represents a new dialectical anchor

## Priority Order

When analyzing, consider in this order:
1. First check if it's an ANTITHESIS of an existing thesis
2. Then check if it's an ASPECT of an existing tension
3. Finally, treat as new THESIS

Respond with structured output matching the requested format."""


# --- DTOs ---


class PlacementAnalysisDto(BaseModel):
    """Result of analyzing idea placement (after deduplication).

    This DTO only determines WHERE the idea belongs - actual metrics (HS, K_T, K_A)
    are computed by the appropriate classification capability.
    """

    placement: str = Field(
        description="Where the idea belongs: 'antithesis', 'aspect', or 'thesis'"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the placement decision (0.0-1.0)",
    )

    # For antithesis - just identify which thesis
    antithesis_of_hash: Optional[str] = Field(
        default=None,
        description="If antithesis, hash of the thesis it opposes",
    )

    # For aspect - identify the tension and position
    tension_thesis_hash: Optional[str] = Field(
        default=None,
        description="If aspect, hash of the thesis in the tension",
    )
    tension_antithesis_hash: Optional[str] = Field(
        default=None,
        description="If aspect, hash of the antithesis in the tension",
    )
    position: Optional[str] = Field(
        default=None,
        description="If aspect, position: T+, T-, A+, A-",
    )

    reasoning: str = Field(description="Explanation of the placement decision")


# --- Result ---


PlacementType = Literal["duplicate", "antithesis", "aspect", "thesis"]


@dataclass
class IdeaPlacementResult:
    """Result of idea placement with the Statement."""

    idea: str
    placement: PlacementType
    confidence: float
    reasoning: str
    component: Statement  # The component (new or existing duplicate)

    # For duplicate
    duplicate_of: Optional[str] = None  # Component hash of existing duplicate

    # For antithesis or aspect - HS from classification
    heuristic_similarity: Optional[float] = None

    # For antithesis
    antithesis_of: Optional[str] = None  # Thesis hash

    # For aspect
    aspect_of: Optional[tuple[str, str]] = None  # (thesis_hash, antithesis_hash)
    position: Optional[str] = None  # T+, T-, A+, A-
    complementarity_t: Optional[float] = None
    complementarity_a: Optional[float] = None


@dataclass
class TensionInfo:
    """Info about an existing tension for placement analysis."""

    thesis_hash: str
    thesis_statement: str
    antithesis_hash: str
    antithesis_statement: str


# --- Concern ---


class IdeaPlacement(ReasonableConcern[IdeaPlacementResult]):
    """
    Concern for determining where an idea belongs in the dialectical graph.

    Creates a Statement for the idea, uses StatementDeduplication
    to check for duplicates, then determines placement (antithesis, aspect, or thesis).

    The result always contains a component - either the newly created one or
    the existing duplicate found during deduplication.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        idea: str,
        vocabulary: list[Statement],
        tensions: list[TensionInfo],
        text: str = "",
    ) -> IdeaPlacementResult:
        """
        Determine where an idea belongs in the dialectical graph.

        Flow:
        1. Check for semantic duplicate (no component created yet)
        2. Determine placement type (thesis/antithesis/aspect)
        3. Run appropriate classification based on placement
        4. Create component with proper meaning from classification
        5. Attach Rationale with placement + classification reasoning

        Args:
            idea: The idea/concept to place
            vocabulary: Existing components in the graph
            tensions: Existing T-A tensions (from Perspectives or OPPOSITE_OF)
            text: Optional source context

        Returns:
            IdeaPlacementResult with placement type, component, and metadata
        """

        # Validate input
        if not idea or not idea.strip():
            raise ValueError("Cannot place empty idea")

        self._idea = idea.strip()
        self._vocabulary = vocabulary
        self._tensions = tensions
        self._text = text

        # If no vocabulary, it's a new thesis - run classification
        if not vocabulary:
            return await self._handle_new_thesis()

        # Step 1: Check for semantic duplicate (no component created yet)
        duplicate_result = await self._check_for_duplicate()
        if duplicate_result is not None:
            return duplicate_result

        # Step 2: Analyze placement (antithesis, aspect, or thesis)
        analysis = await self._analyze_placement()

        # Step 3: Run appropriate classification and create component
        result = await self._classify_and_create(analysis)

        self._build_report(result)
        return result

    async def _handle_new_thesis(self) -> IdeaPlacementResult:
        """Handle idea as new thesis when no vocabulary exists."""
        # Run StatementClassification for proper meaning
        classifier = StatementClassification()
        classification = await classifier.resolve(
            statement=self._idea,
            text=self._text,
        )

        # Create component with classified meaning
        component = Statement(
            text=self._idea,
            meaning=classification.meaning,
        )
        component.commit()
        self._report.node_created(component)

        # Create rationale
        rationale_text = (
            f"Placement: thesis (no existing vocabulary)\n\n"
            f"Classification: {classification.classification_reasoning}"
        )
        self._create_rationale(component, rationale_text)

        result = IdeaPlacementResult(
            idea=self._idea,
            placement="thesis",
            confidence=1.0,
            reasoning="No existing vocabulary - classified as new thesis",
            component=component,
        )
        self._build_report(result)
        return result

    async def _check_for_duplicate(self) -> Optional[IdeaPlacementResult]:
        """
        Check if idea is a semantic duplicate of existing vocabulary.

        Uses StatementDeduplication.check_idea() for consistent dedup logic.

        Returns IdeaPlacementResult if duplicate found, None otherwise.
        """
        # Convert vocabulary to dict format for StatementDeduplication
        vocab_dicts = [
            {
                "hash": c.hash,
                "statement": c.text,
                "meaning": c.meaning,
                "rejected": False,
                "rationale": None,
            }
            for c in self._vocabulary
        ]

        # Use StatementDeduplication.check_idea() for consistent logic
        dedup = StatementDeduplication()
        existing = await dedup.check_idea(
            idea=self._idea,
            vocabulary=vocab_dicts,
            text=self._text,
        )

        if existing:
            result = IdeaPlacementResult(
                idea=self._idea,
                placement="duplicate",
                confidence=0.9,  # High confidence from deduplication
                reasoning=f"Semantically equivalent to existing component '{existing.text}'",
                component=existing,
                duplicate_of=existing.hash,
            )
            self._build_report(result)
            return result

        return None

    async def _classify_and_create(
        self, analysis: PlacementAnalysisDto
    ) -> IdeaPlacementResult:
        """Run appropriate classification based on placement and create component."""
        placement = analysis.placement.lower()

        if placement == "antithesis" and analysis.antithesis_of_hash:
            return await self._handle_antithesis(analysis)
        elif placement == "aspect" and analysis.tension_thesis_hash:
            return await self._handle_aspect(analysis)
        else:
            # Default to thesis
            return await self._handle_thesis(analysis)

    async def _handle_thesis(
        self, analysis: PlacementAnalysisDto
    ) -> IdeaPlacementResult:
        """Handle idea as new thesis."""
        # Run StatementClassification
        classifier = StatementClassification()
        classification = await classifier.resolve(
            statement=self._idea,
            text=self._text,
        )

        # Create component with classified meaning
        component = Statement(
            text=self._idea,
            meaning=classification.meaning,
        )
        component.commit()
        self._report.node_created(component)

        # Create rationale
        rationale_text = (
            f"Placement: thesis\n"
            f"Reasoning: {analysis.reasoning}\n\n"
            f"Classification: {classification.classification_reasoning}"
        )
        self._create_rationale(component, rationale_text)

        return IdeaPlacementResult(
            idea=self._idea,
            placement="thesis",
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            component=component,
        )

    async def _handle_antithesis(
        self, analysis: PlacementAnalysisDto
    ) -> IdeaPlacementResult:
        """Handle idea as antithesis of existing thesis."""
        # Find the thesis component
        repo = NodeRepository()
        thesis = repo.find_by_hash(analysis.antithesis_of_hash)
        if not thesis or not isinstance(thesis, Statement):
            # Fallback to thesis if we can't find the target
            return await self._handle_thesis(analysis)

        # Run AntithesisClassification
        classifier = AntithesisClassification()
        classification = await classifier.resolve(
            thesis=thesis,
            antithesis_statement=self._idea,
            text=self._text,
        )

        # Create component with classified meaning
        component = Statement(
            text=self._idea,
            meaning=classification.meaning,
        )
        component.commit()
        self._report.node_created(component)

        # Create rationale
        rationale_text = (
            f"Placement: antithesis of '{thesis.text}'\n"
            f"Reasoning: {analysis.reasoning}\n\n"
            f"Classification:\n"
            f"- Mode: {classification.mode_label} ({classification.mode_value})\n"
            f"- Heuristic Similarity: {classification.heuristic_similarity}\n"
            f"- Arousal: {classification.arousal_value}\n"
            f"- Reasoning: {classification.reasoning}"
        )
        self._create_rationale(component, rationale_text)

        return IdeaPlacementResult(
            idea=self._idea,
            placement="antithesis",
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            component=component,
            antithesis_of=thesis.hash,
            heuristic_similarity=classification.heuristic_similarity,
        )

    async def _handle_aspect(self, analysis: PlacementAnalysisDto) -> IdeaPlacementResult:
        """Handle idea as aspect of existing tension."""
        # Find thesis and antithesis components
        repo = NodeRepository()
        thesis = repo.find_by_hash(analysis.tension_thesis_hash)
        antithesis = (
            repo.find_by_hash(analysis.tension_antithesis_hash)
            if analysis.tension_antithesis_hash
            else None
        )

        if not thesis or not isinstance(thesis, Statement):
            return await self._handle_thesis(analysis)
        if not antithesis or not isinstance(antithesis, Statement):
            return await self._handle_thesis(analysis)

        position = analysis.position or "T+"

        # Run AspectClassification
        classifier = AspectClassification()
        classification = await classifier.resolve(
            thesis=thesis,
            antithesis=antithesis,
            aspect_statement=self._idea,
            position=position,
            text=self._text,
        )

        # Create component with classified meaning
        component = Statement(
            text=self._idea,
            meaning=classification.meaning,
        )
        component.commit()
        self._report.node_created(component)

        # Create rationale (HS > 0.1 means valid for position)
        validity = (
            "valid" if classification.heuristic_similarity > 0.1 else "wrong category"
        )
        rationale_text = (
            f"Placement: {position} aspect of tension '{thesis.text}' ↔ '{antithesis.text}'\n"
            f"Reasoning: {analysis.reasoning}\n\n"
            f"Classification ({validity}):\n"
            f"- Heuristic Similarity: {classification.heuristic_similarity:.2f}\n"
            f"- K_T (Complementarity to Thesis): {classification.complementarity_t:.2f}\n"
            f"- K_A (Complementarity to Antithesis): {classification.complementarity_a:.2f}\n"
            f"- Apex: {classification.apex_concept}\n"
            f"- Reasoning: {classification.reasoning}"
        )
        self._create_rationale(component, rationale_text)

        return IdeaPlacementResult(
            idea=self._idea,
            placement="aspect",
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            component=component,
            heuristic_similarity=classification.heuristic_similarity,
            aspect_of=(thesis.hash, antithesis.hash),
            position=position,
            complementarity_t=classification.complementarity_t,
            complementarity_a=classification.complementarity_a,
        )

    def _create_rationale(self, component: Statement, text: str) -> None:
        """Create and attach rationale to component."""
        rationale = Rationale(text=text)
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)

    async def _analyze_placement(self) -> PlacementAnalysisDto:
        """Analyze idea placement using LLM.

        Called AFTER duplicate check, so system prompt correctly states
        that duplicate detection has already been done.
        """
        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        prompt = self._build_analysis_prompt()
        return await self._conversation.submit(
            response_model=PlacementAnalysisDto,
            user_content=prompt,
        )

    def _build_analysis_prompt(self) -> str:
        """Build prompt for placement analysis."""
        context_section = (
            f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        )

        # Build vocabulary list (use full hash for accurate matching)
        vocab_lines = []
        for comp in self._vocabulary[:50]:  # Limit for token budget
            vocab_lines.append(f"  [{comp.hash}] {comp.text}")
        vocab_section = "\n".join(vocab_lines) if vocab_lines else "  (empty)"

        # Build tensions list (use full hash for accurate matching)
        tension_lines = []
        for t in self._tensions[:20]:  # Limit for token budget
            tension_lines.append(
                f"  T:[{t.thesis_hash}] {t.thesis_statement} ↔ "
                f"A:[{t.antithesis_hash}] {t.antithesis_statement}"
            )
        tension_section = (
            "\n".join(tension_lines) if tension_lines else "  (no tensions yet)"
        )

        return f"""{context_section}Determine where this idea belongs in the dialectical structure.
Note: This idea has already been checked and is NOT a duplicate of existing vocabulary.

**Idea to place:** "{self._idea}"

**Existing vocabulary:**
{vocab_section}

**Existing tensions (T ↔ A pairs):**
{tension_section}

**Analysis steps:**

1. **Check for ANTITHESIS**: Is "{self._idea}" a dialectical opposite of any existing thesis?
   - Consider: Does it create meaningful tension? Is it opposition/negation/absence?
   - If yes: set placement="antithesis", antithesis_of_hash=thesis hash

2. **Check for ASPECT**: Is "{self._idea}" a positive/negative aspect of any existing tension?
   - T+: benefit/strength of thesis
   - T-: risk/shadow of thesis
   - A+: benefit/strength of antithesis
   - A-: risk/shadow of antithesis
   - If yes: set placement="aspect", provide tension hashes (thesis and antithesis) and position

3. **Otherwise THESIS**: Treat as a new thesis anchor

Provide confidence (0.0-1.0) in your placement decision and reasoning.
Note: Actual metrics (HS, complementarity) will be computed by specialized classifiers."""

    def _build_result(
        self, analysis: PlacementAnalysisDto, component: Statement
    ) -> IdeaPlacementResult:
        """Build result from analysis DTO (after deduplication).

        Note: This method is not used in the current flow - classification handlers
        build their own results with actual metrics from classification.
        """
        placement = analysis.placement.lower()

        # Validate placement type (duplicate handled before this)
        if placement not in ("antithesis", "aspect", "thesis"):
            placement = "thesis"

        result = IdeaPlacementResult(
            idea=self._idea,
            placement=placement,  # type: ignore
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            component=component,
        )

        if placement == "antithesis":
            result.antithesis_of = analysis.antithesis_of_hash
            # heuristic_similarity comes from actual classification, not DTO

        elif placement == "aspect":
            if analysis.tension_thesis_hash and analysis.tension_antithesis_hash:
                result.aspect_of = (
                    analysis.tension_thesis_hash,
                    analysis.tension_antithesis_hash,
                )
            result.position = analysis.position
            # heuristic_similarity and complementarity come from actual classification

        return result

    def _build_report(self, result: IdeaPlacementResult) -> None:
        """Build execution report from result."""
        self._report.artifacts["placement"] = result.placement
        self._report.artifacts["confidence"] = result.confidence

        if result.placement == "duplicate":
            self._report.artifacts["duplicate_of"] = result.duplicate_of
        elif result.placement == "antithesis":
            self._report.artifacts["antithesis_of"] = result.antithesis_of
            self._report.artifacts["heuristic_similarity"] = result.heuristic_similarity
        elif result.placement == "aspect":
            self._report.artifacts["aspect_of"] = result.aspect_of
            self._report.artifacts["position"] = result.position
            self._report.artifacts["heuristic_similarity"] = result.heuristic_similarity

        self._report.ok = True
        self._report.summary = (
            f"Placed '{self._idea}' as {result.placement} "
            f"(confidence={result.confidence:.2f})"
        )
