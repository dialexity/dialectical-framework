"""
SynthesisGeneration: Generate S+/S- synthesis from a Wheel's Transformations.

Synthesis is a wheel-level phenomenon emerging from circular causality — the
complete spiral of Ac+/Re+ Transformations operating simultaneously.

TODO: Apex coherence validation — verify S+/S- lies within convex hull of valid
      sub-syntheses with MHS ≈ 0.84 (paper §Apex Coherence, p.14)
TODO: Discrimination coordinates — use Qn/Qf and ST/OS to validate S+/S-
      cluster separation (paper Table 7, Fig. 7)
TODO: Three-mode decomposition — decompose S+ into Sa+/Sb+/Sc+ processual/
      structural/normative dimensions (paper Table 5)
TODO: Recursive enforcement — higher-layer synthesis must satisfy convex-hull
      containment relative to lower-layer validated syntheses
TODO: Control statements — "S+ without lower-layer support yields S-" style
      coherence checks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import (
    ConversationFacilitator,
)
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel


SYSTEM_PROMPT = """You are an expert in dialectical synthesis — the emergent properties arising from circular causality loops.

## What Synthesis IS

Synthesis is NOT a compromise or middle ground between thesis and antithesis. It is an EMERGENT PROPERTY of their circular interaction through Action (Ac+) and Reflection (Re+) transformations operating simultaneously.

## S+ (Positive Synthesis): Emergent Harmony (1+1>2)

S+ emerges when ALL Ac+ and Re+ transformations in the spiral work together as a self-reinforcing loop:
- Each transformation enhances the conditions for the next
- New capabilities or properties arise that no single transformation could produce alone
- The circular causality creates an upward spiral of increasing integration and dimensionality

S+ produces new qualitative dimensions — it increases a system's capacity for self-regulation, structural differentiation, and normative coherence. It supports indefinite continuation without requiring repeated breakdown and repair.

## S- (Negative Synthesis): Collapse Pattern (1+1<2)

S- emerges when the failure modes (Ac- and Re-) reinforce each other:
- Acting without reflecting yields regression; reflecting without acting yields drift
- Together these create downward spirals — dominance of one pole, or unstable oscillation between them
- Diversity is reduced and qualitative growth is replaced by quantitative amplification

S- manifests as imitation rather than transformation: external forms, metrics, or rules substitute for internal development. It results in faster formation but finite lifespan.

## Requirements

- S+ must be genuinely emergent — not merely restating any single Ac+ or Re+
- S- must describe a genuine collapse pattern — not merely restating any single Ac- or Re-
- Both must be declarative statements naming a state or quality (not instructions)
- For multi-perspective wheels: the synthesis must account for cross-perspective interactions"""


# --- DTOs ---


class SynthesisComponentDto(BaseModel):
    """Single synthesis component (S+ or S-)."""

    statement: str = Field(description="Synthesis statement (declarative, naming an emergent state or quality)")
    explanation: str = Field(description="How this emerges from the circular causality of the transformations")


class SynthesisPairDto(BaseModel):
    """S+ and S- pair emerging from a Wheel's circular causality."""

    s_plus: SynthesisComponentDto = Field(
        description="Positive synthesis: emergent harmony (1+1>2), new qualitative dimension"
    )
    s_minus: SynthesisComponentDto = Field(
        description="Negative synthesis: collapse pattern (1+1<2), dominance or oscillation"
    )


# --- Result ---


@dataclass
class SynthesisResult:
    """Result of synthesis generation — caller creates Synthesis node."""

    s_plus_statement: Statement
    s_minus_statement: Statement
    s_plus_explanation: str
    s_minus_explanation: str


# --- Concern ---


class SynthesisGeneration(ReasonableConcern[Optional[SynthesisResult]], SettingsAware):
    """
    Generate S+/S- synthesis pair from a Wheel's Transformations.

    Takes a Wheel with computed Transformations, extracts the Ac+/Re+ spiral,
    and asks the LLM to articulate what emerges when all loops operate simultaneously.

    Returns committed Statements. Caller creates Synthesis node and connects them.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        wheel: Wheel,
        input_text: str = "",
        lower_layer_context: str = "",
    ) -> Optional[SynthesisResult]:
        """
        Generate S+/S- synthesis pair for a Wheel.

        Args:
            wheel: Wheel with Transformations computed
            input_text: Source text for additional context
            lower_layer_context: Formatted S+/S- from lower-layer sub-wheels

        Returns:
            SynthesisResult with committed S+ and S- Statements, or None if failed.
        """
        transformations = wheel.transformations
        if not transformations:
            self._report.ok = False
            self._report.summary = (
                f"Wheel {wheel.short_hash} has no Transformations — "
                f"cannot generate synthesis"
            )
            return None

        # Group transformations by edge
        edge_to_transformations = self._group_by_edge(transformations)

        # Build the spiral context from wheel edges in order
        spiral_context = self._build_spiral_context(wheel, edge_to_transformations)

        if not spiral_context:
            self._report.ok = False
            self._report.summary = (
                f"Could not extract transformation context from Wheel {wheel.short_hash}"
            )
            return None

        # Build the user prompt
        max_words = self.settings.component_length
        user_prompt = self._build_user_prompt(
            spiral_context, input_text, lower_layer_context, max_words
        )

        # Call LLM
        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        synthesis_pair = await self._conversation.submit(
            response_model=SynthesisPairDto,
            user_content=user_prompt,
        )

        if synthesis_pair is None:
            self._report.ok = False
            self._report.summary = (
                f"LLM synthesis generation failed for Wheel {wheel.short_hash}"
            )
            return None

        # Create S+ and S- Statements
        assert wheel.hash is not None
        s_plus_stmt = Statement(
            text=synthesis_pair.s_plus.statement,
            meaning=f"synthesis:positive:{wheel.hash}",
        )
        s_plus_stmt.commit()

        s_minus_stmt = Statement(
            text=synthesis_pair.s_minus.statement,
            meaning=f"synthesis:negative:{wheel.hash}",
        )
        s_minus_stmt.commit()

        self._report.node_created(s_plus_stmt, meta={"position": "S+"})
        self._report.node_created(s_minus_stmt, meta={"position": "S-"})
        self._report.artifacts["wheel"] = wheel.short_hash
        self._report.summary = (
            f"Generated synthesis for Wheel {wheel.short_hash}: "
            f"S+ = \"{s_plus_stmt.text}\", S- = \"{s_minus_stmt.text}\""
        )

        return SynthesisResult(
            s_plus_statement=s_plus_stmt,
            s_minus_statement=s_minus_stmt,
            s_plus_explanation=synthesis_pair.s_plus.explanation,
            s_minus_explanation=synthesis_pair.s_minus.explanation,
        )

    @staticmethod
    def _group_by_edge(
        transformations: list[Transformation],
    ) -> dict[str, list[Transformation]]:
        """Group transformations by their edge hash."""
        edge_map: dict[str, list[Transformation]] = {}
        for tr in transformations:
            edge_result = tr.edge.get()
            if edge_result:
                edge_node, _ = edge_result
                if edge_node.hash:
                    edge_map.setdefault(edge_node.hash, []).append(tr)
        return edge_map

    def _build_spiral_context(
        self,
        wheel: Wheel,
        edge_to_transformations: dict[str, list[Transformation]],
    ) -> list[str]:
        """Build spiral context by iterating wheel edges in order."""
        parts: list[str] = []

        for i, edge in enumerate(wheel.edges, 1):
            if not edge.hash:
                continue

            trs = edge_to_transformations.get(edge.hash, [])
            if not trs:
                continue

            # Get perspective context from edge segments
            segment_context = self._format_edge_context(edge, i)

            # Format each transformation on this edge
            tr_parts: list[str] = []
            for tr in trs:
                tr_text = self._format_transformation(tr)
                if tr_text:
                    tr_parts.append(tr_text)

            if tr_parts:
                edge_section = segment_context + "\n" + "\n".join(tr_parts)
                parts.append(edge_section)

        return parts

    @staticmethod
    def _format_edge_context(edge: Transition, index: int) -> str:
        """Format the edge's source/target segment context."""
        source_segment = edge.get_source_wheel_segment()
        target_segment = edge.get_target_wheel_segment()

        source_label = "?"
        target_label = "?"

        if source_segment:
            core = source_segment.t.get()
            if core:
                stmt, rel = core
                source_label = rel.alias if hasattr(rel, "alias") else stmt.text

        if target_segment:
            core = target_segment.t.get()
            if core:
                stmt, rel = core
                target_label = rel.alias if hasattr(rel, "alias") else stmt.text

        return f"### Step {index}: {source_label} → {target_label}"

    @staticmethod
    def _format_transformation(tr: Transformation) -> str:
        """Format a single Transformation's Ac+/Re+ (and optionally Ac-/Re-)."""
        lines: list[str] = []

        # Ac+ (required)
        ac_plus_result = tr.ac_plus.get()
        if ac_plus_result:
            transition, _ = ac_plus_result
            headline = transition.instruction or transition.summary or "?"
            lines.append(f"  Ac+ (what to DO): \"{headline}\"")

        # Re+ (required)
        re_plus_result = tr.re_plus.get()
        if re_plus_result:
            transition, _ = re_plus_result
            headline = transition.instruction or transition.summary or "?"
            lines.append(f"  Re+ (what to REFLECT ON): \"{headline}\"")

        # Ac- (optional, for S- context)
        ac_minus_result = tr.ac_minus.get()
        if ac_minus_result:
            transition, _ = ac_minus_result
            headline = transition.instruction or transition.summary or "?"
            lines.append(f"  Ac- (failure mode): \"{headline}\"")

        # Re- (optional, for S- context)
        re_minus_result = tr.re_minus.get()
        if re_minus_result:
            transition, _ = re_minus_result
            headline = transition.instruction or transition.summary or "?"
            lines.append(f"  Re- (failure mode): \"{headline}\"")

        return "\n".join(lines) if lines else ""

    @staticmethod
    def _build_user_prompt(
        spiral_context: list[str],
        input_text: str,
        lower_layer_context: str,
        max_words: int,
    ) -> str:
        """Assemble the user prompt from spiral context and metadata."""
        sections: list[str] = []

        sections.append(
            f"## Transformation Spiral ({len(spiral_context)} steps)\n\n"
            + "\n\n".join(spiral_context)
        )

        if lower_layer_context:
            sections.append(
                f"## Lower-Layer Synthesis (context from sub-wheels)\n\n"
                f"{lower_layer_context}"
            )

        if input_text:
            truncated = input_text[:1500]
            sections.append(f"## Source Context\n\n{truncated}")

        sections.append(
            f"## Generate S+ and S-\n\n"
            f"What emergent quality arises when ALL the Ac+/Re+ loops in this spiral "
            f"operate together simultaneously? What collapse pattern forms when the "
            f"failure modes (Ac-/Re-) reinforce each other?\n\n"
            f"Each statement should be approximately {max_words} words — "
            f"a declarative label naming the emergent state or quality."
        )

        return "\n\n".join(sections)
