"""
SynthesisGeneration: Feature for generating S+/S- synthesis pairs from WisdomUnits.

TODO: This feature needs revision. Synthesis calculation is more complex than
the current simple LLM prompt approach. The actual synthesis should consider:
- Transformation paths (Ac-Re sequences)
- Multiple synthesis interpretations per WU
- Context from the wheel/cycle structure
- Scoring and ranking of synthesis alternatives

Synthesis represents emergent properties from thesis-antithesis dialectic:
- S+ (Positive Synthesis): Complementary harmony where 1+1>2
- S- (Negative Synthesis): Reinforcing uniformity where 1+1<2

Takes a complete WisdomUnit (all 6 positions: T, A, T+, T-, A+, A-) and generates
the synthesis pair. Returns components that the caller connects to a Synthesis node.

Usage:
    service = SynthesisGeneration()

    # Generate synthesis for a complete WisdomUnit
    result = await service.execute(
        wisdom_unit=wu,
        text=source_text,
    )

    if result:
        # Create Synthesis node and connect components
        synthesis = Synthesis()
        synthesis.save()
        synthesis.s_plus.connect(
            result.s_plus_component,
            relationship=SPlusRelationship(alias=result.s_plus_alias)
        )
        synthesis.s_minus.connect(
            result.s_minus_component,
            relationship=SMinusRelationship(alias=result.s_minus_alias)
        )
        synthesis.target.connect(wu)
        synthesis.commit()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import (
    ConversationFacilitator,
)
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.dialectical_component import (
    DialecticalComponent,
)
from dialectical_framework.graph.nodes.synthesis import POSITION_S_MINUS, POSITION_S_PLUS
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    pass


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical synthesis expert.

Given a complete WisdomUnit with thesis (T), antithesis (A), and their poles (T+, T-, A+, A-),
generate the synthesis pair:

## S+ (Positive Synthesis)
The emergent integration where positive aspects (T+ and A+) combine synergistically.
This represents 1+1>2 emergence, creating new possibilities beyond the sum of parts.
Examples include musical harmony, cross-pollination of ideas, or creative collaboration.

## S- (Negative Synthesis)
The reduction that results when negative/exaggerated aspects (T- and A-) reinforce each other.
This represents 1+1<2 reduction, increasing intensity along limited axes at the expense of diversity.
Examples include echo chambers, vicious cycles, or mutual destruction.

Provide concrete statements that emerge from this specific tension."""


# --- DTOs ---


class SynthesisComponentDto(BaseModel):
    """Single synthesis component (S+ or S-)."""

    alias: str = Field(description="S+ or S-")
    statement: str = Field(description="Synthesis statement")
    explanation: str = Field(description="How this synthesis was derived")


class SynthesisPairDto(BaseModel):
    """S+ and S- pair for a WisdomUnit."""

    s_plus: SynthesisComponentDto = Field(
        description="Positive synthesis (emergent integration)"
    )
    s_minus: SynthesisComponentDto = Field(
        description="Negative synthesis (reduction/uniformity)"
    )


# --- Result ---


@dataclass
class SynthesisResult:
    """Result of synthesis generation."""

    s_plus_component: DialecticalComponent
    s_plus_alias: str
    s_plus_explanation: str
    s_minus_component: DialecticalComponent
    s_minus_alias: str
    s_minus_explanation: str


# --- Feature ---


class SynthesisGeneration(ExecutableCapability[Optional[SynthesisResult]], SettingsAware):
    """
    Feature for generating S+/S- synthesis pairs from WisdomUnits.

    Generates synthesis components with explanations. Returns uncommitted
    DialecticalComponents that the caller connects to a Synthesis node.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()
        self._report: ExecutionReport

    async def execute(
        self,
        wisdom_unit: WisdomUnit,
        text: str = "",
    ) -> Optional[SynthesisResult]:
        """
        Generate S+/S- synthesis pair for a WisdomUnit.

        The WisdomUnit must have all 6 positions connected (T, A, T+, T-, A+, A-).

        Args:
            wisdom_unit: Complete WisdomUnit with all positions
            text: Optional source text for context

        Returns:
            SynthesisResult with S+ and S- components, or None if generation failed.
            Components are committed. Caller creates Synthesis node and connects them.
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Build context from WU components
        wu_components = []
        for position in wisdom_unit.core_positions:
            manager = wisdom_unit.get_relationship_manager_by_position(position)
            result = manager.get()
            if result:
                dc, rel = result
                alias = rel.alias if hasattr(rel, "alias") else position
                wu_components.append(f"{alias} = {dc.statement}")

        if len(wu_components) < 6:
            self._report.ok = False
            self._report.summary = (
                f"WisdomUnit {wisdom_unit.short_hash} incomplete "
                f"({len(wu_components)}/6 positions), skipping synthesis"
            )
            return None

        self._report.artifacts["wisdom_unit"] = wisdom_unit.short_hash
        self._report.artifacts["positions_found"] = len(wu_components)

        # Build user prompt
        user_prompt = f"""Generate synthesis for this WisdomUnit:

{chr(10).join(wu_components)}

Context: {text[:1000] if text else 'No additional context provided'}

Create S+ (positive synthesis) and S- (negative synthesis) that emerge from this dialectical tension."""

        # Call LLM
        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        synthesis_pair = await self._conversation.submit(
            response_model=SynthesisPairDto,
            user_content=user_prompt,
        )

        if synthesis_pair is None:
            self._report.ok = False
            self._report.summary = f"Synthesis generation failed for WU {wisdom_unit.short_hash}"
            return None

        # Compute indexed alias (e.g., S2+ for WU index 2)
        wu_index = wisdom_unit.get_human_friendly_index()
        s_plus_alias = POSITION_S_PLUS if wu_index <= 0 else f"S{wu_index}+"
        s_minus_alias = POSITION_S_MINUS if wu_index <= 0 else f"S{wu_index}-"

        # Create S+ component
        s_plus_comp = DialecticalComponent(statement=synthesis_pair.s_plus.statement)
        s_plus_comp.commit()

        # Create S- component
        s_minus_comp = DialecticalComponent(statement=synthesis_pair.s_minus.statement)
        s_minus_comp.commit()

        self._report.node_created(s_plus_comp, meta={"position": s_plus_alias})
        self._report.node_created(s_minus_comp, meta={"position": s_minus_alias})

        self._report.summary = (
            f"Generated synthesis for WU {wisdom_unit.short_hash}: "
            f"{s_plus_alias}, {s_minus_alias}"
        )

        return SynthesisResult(
            s_plus_component=s_plus_comp,
            s_plus_alias=s_plus_alias,
            s_plus_explanation=synthesis_pair.s_plus.explanation,
            s_minus_component=s_minus_comp,
            s_minus_alias=s_minus_alias,
            s_minus_explanation=synthesis_pair.s_minus.explanation,
        )
