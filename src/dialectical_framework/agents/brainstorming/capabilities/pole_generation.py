"""
PoleGeneration: Capability for generating tetrad poles (T+, T-, A+, A-).

Generates poles with:
- Heuristic similarity (HS) to taxonomy apex
- Complementarity values (K_T, K_A)

Supports generating 1, 2, 3, or 4 poles. Contradiction pairs (T+/A-, A+/T-)
should be generated together to ensure semantic coherence.

Takes a WisdomUnit (saved but not committed) with T and A already connected.
User-provided poles should be connected to the WU before calling execute().
Returns generated poles - caller is responsible for connecting them to WU.

Usage:
    service = PoleGeneration()

    # Create WU with T and A
    wu = WisdomUnit()
    wu.save()
    wu.t.connect(thesis_component, relationship=TRelationship(alias=POSITION_T))
    wu.a.connect(antithesis_component, relationship=ARelationship(alias=POSITION_A))

    # Generate a contradiction pair
    results = await service.execute(
        wisdom_unit=wu,
        positions=[POSITION_T_PLUS, POSITION_A_MINUS],
        text=source_text,
    )

    # Connect results to WU
    for result in results:
        manager = wu.get_relationship_manager_by_position(result.position)
        rel_class = WisdomUnit.get_relationship_class_for_position(result.position)
        manager.connect(result.component, relationship=rel_class(
            alias=result.position,
            heuristic_similarity=result.heuristic_similarity,
            complementarity_t=result.complementarity_t,
            complementarity_a=result.complementarity_a,
        ))

    wu.commit()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.brainstorming.capabilities.statement_classification import (
    StatementClassification,
)
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_A,
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    WisdomUnit,
)
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    pass


# --- Constants ---

# Contradiction pairs that should be generated together
CONTRADICTION_PAIRS = [
    (POSITION_T_PLUS, POSITION_A_MINUS),
    (POSITION_A_PLUS, POSITION_T_MINUS),
]

# Map position to its parent (T-side or A-side)
POSITION_TO_PARENT = {
    POSITION_T_PLUS: POSITION_T,
    POSITION_T_MINUS: POSITION_T,
    POSITION_A_PLUS: POSITION_A,
    POSITION_A_MINUS: POSITION_A,
}


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical pole generator.

Your task is to generate poles (T+, T-, A+, A-) for a thesis-antithesis pair.

## Pole Definitions

| Pole | Description |
|------|-------------|
| T+ | Constructive/positive development of T - T developed well, balanced |
| T- | Overdeveloped/exaggerated form of T - T taken too far, imbalanced |
| A+ | Constructive/positive development of A - A developed well, balanced |
| A- | Overdeveloped/exaggerated form of A - A taken too far, imbalanced |

## Key Constraints

1. T+ must directly contradict A- (they cannot both be true/good)
2. A+ must directly contradict T- (they cannot both be true/good)
3. T+/A+ are constructive, balancing developments that enhance upsides
4. T-/A- are overdevelopments/exaggerations (downsides)

## Examples

T = Love, A = Indifference:
- T+ = Bonding (healthy, balanced love)
- T- = Enmeshment (love taken too far)
- A+ = Autonomy (healthy independence)
- A- = Alienation (independence taken too far)

T = Courage, A = Fear:
- T+ = Trust
- T- = Foolhardiness
- A+ = Prudence
- A- = Paranoia

Generate pole statements that fit the semantic structure."""


# --- DTOs ---


class PoleDto(BaseModel):
    """Generated pole with scoring."""

    statement: str = Field(description="Pole statement")
    heuristic_similarity: float = Field(
        ge=0.0, le=1.0,
        description="Heuristic Similarity to taxonomy apex (0.0-1.0)"
    )
    complementarity_t: float = Field(
        ge=0.0, le=1.0,
        description="K_T: How well this complements, balances, or contributes positively to the thesis (0.0-1.0)"
    )
    complementarity_a: float = Field(
        ge=0.0, le=1.0,
        description="K_A: How well this complements, balances, or contributes positively to the antithesis (0.0-1.0)"
    )
    explanation: str = Field(description="Brief reasoning for the pole and scores")


class ContradictionPairDto(BaseModel):
    """Two poles that form a contradiction pair."""

    positive_pole: PoleDto = Field(description="The positive pole (T+ or A+)")
    negative_pole: PoleDto = Field(description="The negative pole (A- or T-)")


class TetradDto(BaseModel):
    """Full tetrad of four poles."""

    t_plus: PoleDto = Field(description="T+ - constructive thesis")
    t_minus: PoleDto = Field(description="T- - exaggerated thesis")
    a_plus: PoleDto = Field(description="A+ - constructive antithesis")
    a_minus: PoleDto = Field(description="A- - exaggerated antithesis")


# --- Result ---


@dataclass
class PoleResult:
    """Result of pole generation."""

    component: DialecticalComponent
    position: str
    apex_concept: str
    heuristic_similarity: float
    complementarity_t: float
    complementarity_a: float


# --- Capability ---


class PoleGeneration(ExecutableCapability[list[PoleResult]], SettingsAware):
    """
    Capability for generating tetrad poles (T+, T-, A+, A-).

    Generates poles with HS calculated against taxonomy apex and K values.
    Contradiction pairs are generated together to ensure coherence.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def execute(
        self,
        wisdom_unit: WisdomUnit,
        positions: Optional[list[str]] = None,
        text: str = "",
        not_like_these: Optional[list[WisdomUnit]] = None,
    ) -> list[PoleResult]:
        """
        Generate poles for a WisdomUnit.

        The WisdomUnit must have T and A already connected. Any poles already
        connected to the WU (user-provided) will be used as context for generating
        the remaining poles.

        Args:
            wisdom_unit: WisdomUnit with T and A connected (saved but not committed)
            positions: Which poles to generate (POSITION_T_PLUS, etc.). If None or empty, generates all 4.
            text: Optional source text for context
            not_like_these: WisdomUnits with tetrads to avoid (must share T or A with wisdom_unit)

        Returns:
            List of PoleResult with components and scoring.
            Caller is responsible for connecting these to the WU.
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)
        self._wisdom_unit = wisdom_unit
        self._text = text

        # Extract T and A from WisdomUnit
        t_result = wisdom_unit.t.get()
        a_result = wisdom_unit.a.get()

        if not t_result:
            raise ValueError("WisdomUnit must have T connected")
        if not a_result:
            raise ValueError("WisdomUnit must have A connected")

        self._thesis = t_result[0]
        self._antithesis = a_result[0]

        # Filter and validate not_like_these WisdomUnits
        self._not_like_these = self._filter_relevant_wus(not_like_these or [])

        # Default to all 4 poles if positions not specified
        all_positions = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]
        positions = positions if positions else all_positions

        # Check which positions already have components
        self._existing_poles: dict[str, DialecticalComponent] = {}
        for pos in [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]:
            manager = wisdom_unit.get_relationship_manager_by_position(pos)
            result = manager.get()
            if result:
                self._existing_poles[pos] = result[0]

        # Determine which positions to generate
        # If WU is complete, it's a template - generate all requested positions
        # If WU is incomplete, skip positions that already exist
        is_template = wisdom_unit.is_complete()
        if is_template:
            positions_to_generate = positions
        else:
            positions_to_generate = [p for p in positions if p not in self._existing_poles]

        # Validate positions
        for pos in positions_to_generate:
            if pos not in all_positions:
                raise ValueError(f"Invalid position '{pos}'. Must be one of: {all_positions}")

        if not positions_to_generate:
            # All requested positions already filled (only in non-template mode)
            self._report.ok = True
            self._report.summary = "All requested positions already filled"
            return []

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Determine generation strategy based on positions
        results: list[PoleResult] = []

        if len(positions_to_generate) == 4:
            # Full tetrad - generate all together
            results = await self._generate_tetrad(positions_to_generate)
        elif self._is_contradiction_pair(positions_to_generate):
            # Contradiction pair - generate together
            results = await self._generate_contradiction_pair(positions_to_generate)
        else:
            # Individual poles or non-pair combination
            for pos in positions_to_generate:
                result = await self._generate_single_pole(pos)
                results.append(result)

        # Build report
        self._report.ok = True
        self._report.artifacts["generated"] = {
            r.position: r.component.hash for r in results
        }
        self._report.summary = f"Generated {len(results)} pole(s): " + ", ".join(
            f"{r.position}={r.component.short_hash}" for r in results
        ) if results else "No poles generated"

        return results

    def _is_contradiction_pair(self, positions: list[str]) -> bool:
        """Check if positions form a contradiction pair."""
        if len(positions) != 2:
            return False
        pos_set = set(positions)
        for pair in CONTRADICTION_PAIRS:
            if pos_set == set(pair):
                return True
        return False

    async def _generate_tetrad(self, positions: list[str]) -> list[PoleResult]:
        """Generate full tetrad (all 4 poles together)."""
        existing_context = self._build_existing_poles_context(positions)

        result = await self._conversation.submit(
            response_model=TetradDto,
            user_content=self._tetrad_prompt(existing_context),
        )

        results = []
        position_to_dto = {
            POSITION_T_PLUS: result.t_plus,
            POSITION_T_MINUS: result.t_minus,
            POSITION_A_PLUS: result.a_plus,
            POSITION_A_MINUS: result.a_minus,
        }

        for pos in positions:
            dto = position_to_dto[pos]
            pole_result = self._create_pole_result(pos, dto.statement, dto)
            results.append(pole_result)

        return results

    async def _generate_contradiction_pair(self, positions: list[str]) -> list[PoleResult]:
        """Generate a contradiction pair (T+/A- or A+/T-)."""
        # Determine which pair
        pos_set = set(positions)
        if pos_set == {POSITION_T_PLUS, POSITION_A_MINUS}:
            positive_pos, negative_pos = POSITION_T_PLUS, POSITION_A_MINUS
        else:
            positive_pos, negative_pos = POSITION_A_PLUS, POSITION_T_MINUS

        existing_context = self._build_existing_poles_context(positions)

        result = await self._conversation.submit(
            response_model=ContradictionPairDto,
            user_content=self._contradiction_pair_prompt(positive_pos, negative_pos, existing_context),
        )

        results = []
        results.append(self._create_pole_result(positive_pos, result.positive_pole.statement, result.positive_pole))
        results.append(self._create_pole_result(negative_pos, result.negative_pole.statement, result.negative_pole))

        return results

    async def _generate_single_pole(self, position: str) -> PoleResult:
        """Generate a single pole."""
        existing_context = self._build_existing_poles_context([position])

        result = await self._conversation.submit(
            response_model=PoleDto,
            user_content=self._single_pole_prompt(position, existing_context),
        )

        return self._create_pole_result(position, result.statement, result)

    def _create_pole_result(
        self,
        position: str,
        statement: str,
        dto: PoleDto,
    ) -> PoleResult:
        """Create PoleResult with DialecticalComponent."""
        # Get parent for meaning lookup
        parent = self._thesis if position in [POSITION_T_PLUS, POSITION_T_MINUS] else self._antithesis

        # Get meaning and apex from taxonomy
        meaning = StatementClassification.lookup_pole_meaning(parent, position)
        apex = StatementClassification.lookup_pole_apex(parent, position)

        # Create component
        component = DialecticalComponent(
            statement=statement,
            meaning=meaning,
        )
        component.commit()
        self._report.node_created(component, meta={"position": position})

        return PoleResult(
            component=component,
            position=position,
            apex_concept=apex,
            heuristic_similarity=dto.heuristic_similarity,
            complementarity_t=dto.complementarity_t,
            complementarity_a=dto.complementarity_a,
        )

    def _filter_relevant_wus(self, wus: list[WisdomUnit]) -> list[WisdomUnit]:
        """Filter WisdomUnits to only those with the same tension (T-A pair, either orientation)."""
        relevant = []
        target_hashes = {self._thesis.hash, self._antithesis.hash}

        for wu in wus:
            wu_t = wu.t.get()
            wu_a = wu.a.get()
            wu_t_hash = wu_t[0].hash if wu_t else None
            wu_a_hash = wu_a[0].hash if wu_a else None

            # Both T and A must match (same orientation or swapped)
            if {wu_t_hash, wu_a_hash} == target_hashes:
                relevant.append(wu)

        return relevant

    def _build_existing_poles_context(self, positions_to_generate: list[str]) -> str:
        """Build context string for existing poles NOT being regenerated."""
        # Only show poles that exist AND are not being regenerated
        relevant_poles = {
            pos: comp for pos, comp in self._existing_poles.items()
            if pos not in positions_to_generate
        }

        if not relevant_poles:
            return ""

        lines = ["The following pole(s) are already defined:"]
        for pos, component in relevant_poles.items():
            lines.append(f"- {pos} = \"{component.statement}\"")
        lines.append("Generate the remaining poles to be coherent with these.")
        return "\n".join(lines)

    def _build_avoid_context(self) -> str:
        """Build context string for tetrads to avoid.

        Handles T-A symmetry: if an existing WU has T and A swapped relative to
        the current WU, the pole positions are remapped when displaying.
        """
        if not self._not_like_these:
            return ""

        # Only avoid complete WUs; partial ones are still in progress
        complete_wus = [wu for wu in self._not_like_these if wu.is_complete()]
        if not complete_wus:
            return ""

        lines = ["\n## Previous Tetrads (generate different interpretations)"]
        for i, wu in enumerate(complete_wus, 1):
            lines.append(f"Tetrad {i}:")

            # Check if this WU has T and A swapped relative to current
            wu_t = wu.t.get()
            is_swapped = wu_t and wu_t[0].hash == self._antithesis.hash

            for pos in [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]:
                manager = wu.get_relationship_manager_by_position(pos)
                result = manager.get()
                if result:
                    # Remap position if T-A are swapped
                    display_pos = self._swap_position(pos) if is_swapped else pos
                    lines.append(f"  - {display_pos}: \"{result[0].statement}\"")
        lines.append("")
        lines.append("Generate semantically distinct poles while maintaining contradiction relationships.")
        return "\n".join(lines)

    def _swap_position(self, position: str) -> str:
        """Swap T-side and A-side positions (T+ ↔ A+, T- ↔ A-)."""
        swap_map = {
            POSITION_T_PLUS: POSITION_A_PLUS,
            POSITION_T_MINUS: POSITION_A_MINUS,
            POSITION_A_PLUS: POSITION_T_PLUS,
            POSITION_A_MINUS: POSITION_T_MINUS,
        }
        return swap_map.get(position, position)

    def _tetrad_prompt(self, existing_context: str) -> str:
        """Build prompt for full tetrad generation."""
        max_words = self.settings.component_length

        t_plus_apex = StatementClassification.lookup_pole_apex(self._thesis, POSITION_T_PLUS)
        t_minus_apex = StatementClassification.lookup_pole_apex(self._thesis, POSITION_T_MINUS)
        a_plus_apex = StatementClassification.lookup_pole_apex(self._antithesis, POSITION_A_PLUS)
        a_minus_apex = StatementClassification.lookup_pole_apex(self._antithesis, POSITION_A_MINUS)

        text_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        existing_section = f"\n{existing_context}\n" if existing_context else ""
        avoid_section = self._build_avoid_context()
        avoid_section = f"\n{avoid_section}\n" if avoid_section else ""

        return f"""{text_section}Generate a complete tetrad for this thesis-antithesis pair.

Thesis (T): "{self._thesis.statement}"
Antithesis (A): "{self._antithesis.statement}"

Taxonomy apex concepts for reference:
- T+ apex: {t_plus_apex}
- T- apex: {t_minus_apex}
- A+ apex: {a_plus_apex}
- A- apex: {a_minus_apex}
{existing_section}{avoid_section}
Generate each pole (1-{max_words} words) with:

## HS (Heuristic Similarity) Scale
HS measures how well the pole captures the essence of its taxonomy apex concept:
- 0.0-0.3: Unrelated or tangentially related to the apex
- 0.3-0.5: Somewhat related but different focus or aspect
- 0.5-0.7: Related, captures some key aspects of the apex
- 0.7-0.9: Very similar, captures most aspects of the apex
- 0.9-1.0: Equivalent or near-equivalent to the apex concept

## Complementarity (K) Scores
- K_T: How well this pole complements, balances, or contributes positively to the thesis (0.0-1.0)
- K_A: How well this pole complements, balances, or contributes positively to the antithesis (0.0-1.0)

Ensure T+ contradicts A-, and A+ contradicts T-."""

    def _contradiction_pair_prompt(
        self,
        positive_pos: str,
        negative_pos: str,
        existing_context: str,
    ) -> str:
        """Build prompt for contradiction pair generation."""
        max_words = self.settings.component_length

        # Get parent for each position
        pos_parent = self._thesis if positive_pos in [POSITION_T_PLUS, POSITION_T_MINUS] else self._antithesis
        neg_parent = self._thesis if negative_pos in [POSITION_T_PLUS, POSITION_T_MINUS] else self._antithesis

        pos_apex = StatementClassification.lookup_pole_apex(pos_parent, positive_pos)
        neg_apex = StatementClassification.lookup_pole_apex(neg_parent, negative_pos)

        text_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        existing_section = f"\n{existing_context}\n" if existing_context else ""
        avoid_section = self._build_avoid_context()
        avoid_section = f"\n{avoid_section}\n" if avoid_section else ""

        return f"""{text_section}Generate a contradiction pair for this thesis-antithesis pair.

Thesis (T): "{self._thesis.statement}"
Antithesis (A): "{self._antithesis.statement}"

Generate {positive_pos} and {negative_pos} that contradict each other.

Taxonomy apex concepts for reference:
- {positive_pos} apex: {pos_apex}
- {negative_pos} apex: {neg_apex}
{existing_section}{avoid_section}
Generate each pole (1-{max_words} words) with:

## HS (Heuristic Similarity) Scale
HS measures how well the pole captures the essence of its taxonomy apex concept:
- 0.0-0.3: Unrelated or tangentially related to the apex
- 0.3-0.5: Somewhat related but different focus or aspect
- 0.5-0.7: Related, captures some key aspects of the apex
- 0.7-0.9: Very similar, captures most aspects of the apex
- 0.9-1.0: Equivalent or near-equivalent to the apex concept

## Complementarity (K) Scores
- K_T: How well this pole complements, balances, or contributes positively to the thesis (0.0-1.0)
- K_A: How well this pole complements, balances, or contributes positively to the antithesis (0.0-1.0)

The positive_pole is {positive_pos}, the negative_pole is {negative_pos}.
They must contradict each other - they cannot both be true/good simultaneously."""

    def _single_pole_prompt(self, position: str, existing_context: str) -> str:
        """Build prompt for single pole generation."""
        max_words = self.settings.component_length

        parent = self._thesis if position in [POSITION_T_PLUS, POSITION_T_MINUS] else self._antithesis
        apex = StatementClassification.lookup_pole_apex(parent, position)

        # Get description based on position
        if position == POSITION_T_PLUS:
            desc = "constructive/positive development of the thesis"
        elif position == POSITION_T_MINUS:
            desc = "overdeveloped/exaggerated form of the thesis"
        elif position == POSITION_A_PLUS:
            desc = "constructive/positive development of the antithesis"
        else:
            desc = "overdeveloped/exaggerated form of the antithesis"

        text_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        existing_section = f"\n{existing_context}\n" if existing_context else ""
        avoid_section = self._build_avoid_context()
        avoid_section = f"\n{avoid_section}\n" if avoid_section else ""

        return f"""{text_section}Generate {position} for this thesis-antithesis pair.

Thesis (T): "{self._thesis.statement}"
Antithesis (A): "{self._antithesis.statement}"

{position} is the {desc}.
Taxonomy apex concept: {apex}
{existing_section}{avoid_section}
Generate the pole (1-{max_words} words) with:

## HS (Heuristic Similarity) Scale
HS measures how well the pole captures the essence of its taxonomy apex concept:
- 0.0-0.3: Unrelated or tangentially related to the apex
- 0.3-0.5: Somewhat related but different focus or aspect
- 0.5-0.7: Related, captures some key aspects of the apex
- 0.7-0.9: Very similar, captures most aspects of the apex
- 0.9-1.0: Equivalent or near-equivalent to the apex concept

## Complementarity (K) Scores
- K_T: How well this pole complements, balances, or contributes positively to the thesis (0.0-1.0)
- K_A: How well this pole complements, balances, or contributes positively to the antithesis (0.0-1.0)"""
