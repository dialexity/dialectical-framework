"""
AspectGeneration: Concern for generating tetrad aspects (T+, T-, A+, A-).

Generates aspects with:
- Heuristic similarity (HS) to taxonomy apex
- Complementarity values (K_T, K_A)

Supports generating 1, 2, 3, or 4 aspects. Contradiction pairs (T+/A-, A+/T-)
should be generated together to ensure semantic coherence.

Takes a Perspective (saved but not committed) with T and A already connected.
User-provided aspects should be connected to the PP before calling execute().
Returns generated aspects - caller is responsible for connecting them to PP.

Usage:
    service = AspectGeneration()

    # Create PP with T and A
    pp = Perspective()
    pp.save()
    pp.t.connect(thesis_component, relationship=TRelationship(alias=POSITION_T))
    pp.a.connect(antithesis_component, relationship=ARelationship(alias=POSITION_A))

    # Generate a contradiction pair
    results = await service.resolve(
        perspective=pp,
        positions=[POSITION_T_PLUS, POSITION_A_MINUS],
        text=source_text,
    )

    # Connect results to PP
    for result in results:
        manager = pp.get_relationship_manager_by_position(result.position)
        rel_class = Perspective.get_relationship_class_for_position(result.position)
        manager.connect(result.component, relationship=rel_class(
            alias=result.position,
            heuristic_similarity=result.heuristic_similarity,
            complementarity_t=result.complementarity_t,
            complementarity_a=result.complementarity_a,
        ))

    pp.commit()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.perspective import (POSITION_A,
                                                          POSITION_A_MINUS,
                                                          POSITION_A_PLUS,
                                                          POSITION_T,
                                                          POSITION_T_MINUS,
                                                          POSITION_T_PLUS,
                                                          Perspective)
from dialectical_framework.concerns.scoring_scales import (
    ASPECT_DEFINITIONS, COMPLEMENTARITY_SCALE, HS_SCALE)
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

SYSTEM_PROMPT = f"""You are a dialectical aspect generator.

Your task is to generate aspects (T+, T-, A+, A-) for a thesis-antithesis pair.

{ASPECT_DEFINITIONS}

## Examples

Each tetrad resolves into two diagonal contradiction pairs. A pair shares one
**axis** — a single dimension on which its two aspects sit at opposite ends, so
they cannot both hold at once.

Derive each aspect from its own parent first, then name the axis and place the
pair on it. The axis is a test that the finished pair genuinely contradicts; it
is not the recipe for building either half. A minus is never obtained by
negating the plus it faces — both poles can supply a negative end of the same
axis, so negation alone leaves the parent undetermined.

T = Love, A = Indifference:
- Axis "closeness": T+ = Bonding (Love developed) ⟷ A- = Alienation (Indifference overdeveloped)
- Axis "self-standing": A+ = Autonomy (Indifference developed) ⟷ T- = Enmeshment (Love overdeveloped)

T = Courage, A = Fear:
- Axis "risk-taking": T+ = Trust (Courage developed) ⟷ A- = Paranoia (Fear overdeveloped)
- Axis "caution": A+ = Prudence (Fear developed) ⟷ T- = Foolhardiness (Courage overdeveloped)

The mistake to avoid, on that same Courage/Fear pair. Given the axis
"risk-taking" and T+ = Trust, writing A- = "recklessness that ignores every
warning" is wrong. It does sit opposite Trust on that axis — but recklessness is
COURAGE overdeveloped, so that content belongs at T- (Foolhardiness), and A- is
left with nothing. A- must be FEAR overdeveloped: Paranoia.

The mistake to avoid on a plus. T = "Standardise the deployment toolchain across
every team", A = "Let each team choose its own toolchain". Writing A+ =
"Team-driven choices enable rapid local optimization" is wrong: that is A's own
native benefit restated, taking up nothing standardisation is for, so it
restates A instead of developing it. The repair is not to bolt the opposition on
as a constraint either — A+ = "Teams choose within centrally aligned standards"
hands the generative act to T and is T+ in A's clothes. A+ keeps team choice as
the generative act AND yields what standardisation is for: "Teams publish their
chosen toolchain for others to adopt" — choosing still drives it, and
interoperability arrives as its result.

Generate aspect statements that fit the semantic structure."""


# The verification clause every generation path in this file was missing.
#
# The take-up half of Rule 1 is already ASSERTED four times over — in
# `ASPECT_DEFINITIONS`, in the `TetradDto` field descriptions, and in each
# prompt's own procedure — and was still violated in **17 of 128 audited plus
# slots (13.3%)** on the weak tier (`tests/e2e/probe_option_pair_tetrads.py`).
# Minus-parentage, the rule that had a re-read step, ran at 3.1% in the same
# audit output. The difference between the two was not how forcefully each rule
# was stated; it was that only one of them was checked. Hence a check, stated
# once here and interpolated, rather than a fifth restatement of the rule.
PLUS_RESTATEMENT_CHECK = (
    "Restated parent: if a plus only names what its own parent already "
    "delivers, rewrite it so the parent stays the generative act while its "
    "result also supplies what the other pole is for."
)


# --- DTOs ---


class AspectDto(BaseModel):
    """Generated aspect with scoring."""

    statement: str = Field(description="Aspect statement")
    heuristic_similarity: float = Field(
        ge=0.0, le=1.0, description="Heuristic Similarity to taxonomy apex (0.0-1.0)"
    )
    complementarity_t: float = Field(
        ge=0.0,
        le=1.0,
        description="K_T: How well this complements, balances, or contributes positively to the thesis (0.0-1.0)",
    )
    complementarity_a: float = Field(
        ge=0.0,
        le=1.0,
        description="K_A: How well this complements, balances, or contributes positively to the antithesis (0.0-1.0)",
    )
    explanation: str = Field(description="Brief reasoning for the aspect and scores")


class ContradictionPairDto(BaseModel):
    """Two aspects that form a diagonal contradiction pair.

    The pair is defined by its `axis`: a single dimension on which the two
    aspects sit at opposite ends, so they cannot both hold at once. The model
    must name the axis first, which forces a genuine opposition rather than two
    independently-plausible aspects.
    """

    axis: str = Field(
        description=(
            "The single dimension on which the two aspects are opposite ends "
            "(e.g. 'closeness', 'risk-taking'). If no such shared dimension "
            "exists, the pair is not a genuine contradiction — say so here."
        )
    )
    positive_aspect: AspectDto = Field(
        description=(
            "The positive aspect (T+ or A+): the constructive development of the "
            "parent assigned to it in the prompt."
        )
    )
    negative_aspect: AspectDto = Field(
        description=(
            "The negative aspect (A- or T-): the one-sided overdevelopment of the "
            "parent assigned to it in the prompt — not a negation of positive_aspect."
        )
    )


class TetradDto(BaseModel):
    """Full tetrad: four aspects grouped by the two axes they oppose along.

    The four aspects stay as top-level fields (deep nesting made the model drop
    a whole diagonal branch), but each diagonal pair leads with an explicit
    `axis` field — the shared dimension its two poles sit at opposite ends of.
    Naming the axis forces genuine diagonal contradiction into the output
    instead of leaving it to a trailing constraint.
    """

    # --- Pair 1: T+ vs A- (thesis-constructive axis) ---
    t_plus_vs_a_minus_axis: str = Field(
        description=(
            "The single dimension on which T+ and A- are opposite ends "
            "(e.g. 'closeness'). If T and A share no such dimension, the pair "
            "is not a genuine contradiction — say so here."
        )
    )
    t_plus: AspectDto = Field(
        description=(
            "T+ - the THESIS developed constructively, so that it also strengthens "
            "what A offers. Derive it from T, then place it at the positive end of "
            "the axis above."
        )
    )
    a_minus: AspectDto = Field(
        description=(
            "A- - the ANTITHESIS overdeveloped: A pushed one-sidedly with T "
            "underdeveloped, i.e. what A itself degenerates into. Derive it from A, "
            "never by negating T+, then place it at the negative end of the axis above."
        )
    )

    # --- Pair 2: A+ vs T- (antithesis-constructive axis) ---
    a_plus_vs_t_minus_axis: str = Field(
        description=(
            "The single dimension on which A+ and T- are opposite ends. If A "
            "and T share no such dimension, say so here rather than inventing "
            "two unrelated aspects."
        )
    )
    a_plus: AspectDto = Field(
        description=(
            "A+ - the ANTITHESIS developed constructively, so that it also strengthens "
            "what T offers. Derive it from A, then place it at the positive end of "
            "the axis above."
        )
    )
    t_minus: AspectDto = Field(
        description=(
            "T- - the THESIS overdeveloped: T pushed one-sidedly with A "
            "underdeveloped, i.e. what T itself degenerates into. Derive it from T, "
            "never by negating A+, then place it at the negative end of the axis above."
        )
    )


# --- Result ---


@dataclass
class AspectResult:
    """Result of aspect generation."""

    component: Statement
    position: str
    apex_concept: str
    heuristic_similarity: float
    complementarity_t: float
    complementarity_a: float


# --- Concern ---


class AspectGeneration(ReasonableConcern[list[AspectResult]], SettingsAware):
    """
    Concern for generating tetrad aspects (T+, T-, A+, A-).

    Generates aspects with HS calculated against taxonomy apex and K values.
    Contradiction pairs are generated together to ensure coherence.

    Design decision — diagonal contradiction is enforced by the PROMPT here, not
    by a post-hoc scorer. `TetradDto` makes each diagonal pair name the `axis`
    it opposes along, which forces genuine contradiction into the output. We do
    NOT run `DiagonalOppositionsCheck` on this path: generation is latency- and
    cost-sensitive (it fans out across polarities × aspects), and the scorer
    would add 2 LLM calls per perspective. `DiagonalOppositionsCheck` exists as
    a safety net only where the prompt is bypassed — user edits in
    `edit_perspective._validate_tetrad_coherence`. If a T/A pair is genuinely
    not an opposition, that is caught upstream at polarity formation
    (AntitheticalThesisDetection / the HS gate), not here.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()
        # Axes named by the last resolve() (full-tetrad and pair paths only).
        # Keys: "t_plus_vs_a_minus", "a_plus_vs_t_minus". The caller
        # (ExpandPolarity) composes these into Perspective.intent — the
        # human-readable name of THIS reading of the tension. Disclaimer
        # axes ("no shared dimension...") are filtered to None.
        self.axes: dict[str, str] = {}

    async def resolve(
        self,
        perspective: Perspective,
        positions: Optional[list[str]] = None,
        text: str = "",
        not_like_these: Optional[list[Perspective]] = None,
    ) -> list[AspectResult]:
        """
        Generate aspects for a Perspective.

        The Perspective must have T and A already connected. Any aspects already
        connected to the PP (user-provided) will be used as context for generating
        the remaining aspects.

        Args:
            perspective: Perspective with T and A connected (saved but not committed)
            positions: Which aspects to generate (POSITION_T_PLUS, etc.). If None or empty, generates all 4.
            text: Optional source text for context
            not_like_these: Perspectives with tetrads to avoid (must share T or A with perspective)

        Returns:
            List of AspectResult with components and scoring.
            Caller is responsible for connecting these to the PP.
        """
        self._pp = perspective
        self._text = text
        self.axes = {}

        # Extract T and A from Perspective
        t_result = perspective.t.get()
        a_result = perspective.a.get()

        if not t_result:
            raise ValueError("Perspective must have T connected")
        if not a_result:
            raise ValueError("Perspective must have A connected")

        self._thesis = t_result[0]
        self._antithesis = a_result[0]

        # Filter and validate not_like_these Perspectives
        self._not_like_these = self._filter_relevant_pps(not_like_these or [])

        # Default to all 4 aspects if positions not specified
        all_positions = [
            POSITION_T_PLUS,
            POSITION_T_MINUS,
            POSITION_A_PLUS,
            POSITION_A_MINUS,
        ]
        positions = positions if positions else all_positions

        # Check which positions already have components
        self._existing_aspects: dict[str, Statement] = {}
        for pos in [
            POSITION_T_PLUS,
            POSITION_T_MINUS,
            POSITION_A_PLUS,
            POSITION_A_MINUS,
        ]:
            manager = perspective.get_relationship_manager_by_position(pos)
            result = manager.get()
            if result:
                self._existing_aspects[pos] = result[0]

        # Determine which positions to generate
        # If PP is complete, it's a template - generate all requested positions
        # If PP is incomplete, skip positions that already exist
        is_template = perspective.is_complete()
        if is_template:
            positions_to_generate = positions
        else:
            positions_to_generate = [
                p for p in positions if p not in self._existing_aspects
            ]

        # Validate positions
        for pos in positions_to_generate:
            if pos not in all_positions:
                raise ValueError(
                    f"Invalid position '{pos}'. Must be one of: {all_positions}"
                )

        if not positions_to_generate:
            # All requested positions already filled (only in non-template mode)
            self._report.ok = True
            self._report.summary = "All requested positions already filled"
            return []

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Determine generation strategy based on positions
        results: list[AspectResult] = []

        if len(positions_to_generate) == 4:
            # Full tetrad - generate all together
            results = await self._generate_tetrad(positions_to_generate)
        elif self._is_contradiction_pair(positions_to_generate):
            # Contradiction pair - generate together
            results = await self._generate_contradiction_pair(positions_to_generate)
        else:
            # Individual aspects or non-pair combination
            for pos in positions_to_generate:
                result = await self._generate_single_aspect(pos)
                results.append(result)

        # Build report
        self._report.ok = True
        self._report.artifacts["generated"] = {
            r.position: r.component.hash for r in results
        }
        self._report.summary = (
            f"Generated {len(results)} aspect(s): "
            + ", ".join(f"{r.position}={r.component.short_hash}" for r in results)
            if results
            else "No aspects generated"
        )

        return results

    def _capture_axis(self, key: str, axis: str) -> None:
        """Record a named axis for the caller, filtering disclaimers.

        The DTO instructs the model to SAY when no genuine shared dimension
        exists rather than invent one — such disclaimers must not become a
        perspective's reading. Heuristic: a real axis is a short dimension
        name ("closeness", "self-directed growth vs institutional security");
        a disclaimer is a sentence about the absence of one.
        """
        axis = (axis or "").strip()
        if not axis:
            return
        lowered = axis.lower()
        disclaimer_markers = (
            "no ",  # "no such dimension", "no shared axis"
            "not a genuine",
            "do not share",
            "does not",
            "doesn't",
            "cannot",
            "lack",
        )
        if any(marker in lowered for marker in disclaimer_markers):
            return
        if len(axis.split()) > 12:  # sentence-length = explanation, not a name
            return
        self.axes[key] = axis

    def _is_contradiction_pair(self, positions: list[str]) -> bool:
        """Check if positions form a contradiction pair."""
        if len(positions) != 2:
            return False
        pos_set = set(positions)
        for pair in CONTRADICTION_PAIRS:
            if pos_set == set(pair):
                return True
        return False

    async def _generate_tetrad(self, positions: list[str]) -> list[AspectResult]:
        """Generate full tetrad (all 4 aspects together)."""
        existing_context = self._build_existing_aspects_context(positions)

        result = await self._conversation.submit(
            response_model=TetradDto,
            user_content=self._tetrad_prompt(existing_context),
        )

        self._capture_axis("t_plus_vs_a_minus", result.t_plus_vs_a_minus_axis)
        self._capture_axis("a_plus_vs_t_minus", result.a_plus_vs_t_minus_axis)

        results = []
        position_to_dto = {
            POSITION_T_PLUS: result.t_plus,
            POSITION_A_MINUS: result.a_minus,
            POSITION_A_PLUS: result.a_plus,
            POSITION_T_MINUS: result.t_minus,
        }

        for pos in positions:
            dto = position_to_dto[pos]
            aspect_result = self._create_aspect_result(pos, dto.statement, dto)
            results.append(aspect_result)

        return results

    async def _generate_contradiction_pair(
        self, positions: list[str]
    ) -> list[AspectResult]:
        """Generate a contradiction pair (T+/A- or A+/T-)."""
        # Determine which pair
        pos_set = set(positions)
        if pos_set == {POSITION_T_PLUS, POSITION_A_MINUS}:
            positive_pos, negative_pos = POSITION_T_PLUS, POSITION_A_MINUS
        else:
            positive_pos, negative_pos = POSITION_A_PLUS, POSITION_T_MINUS

        existing_context = self._build_existing_aspects_context(positions)

        result = await self._conversation.submit(
            response_model=ContradictionPairDto,
            user_content=self._contradiction_pair_prompt(
                positive_pos, negative_pos, existing_context
            ),
        )

        axis_key = (
            "t_plus_vs_a_minus"
            if positive_pos == POSITION_T_PLUS
            else "a_plus_vs_t_minus"
        )
        self._capture_axis(axis_key, result.axis)

        results = []
        results.append(
            self._create_aspect_result(
                positive_pos, result.positive_aspect.statement, result.positive_aspect
            )
        )
        results.append(
            self._create_aspect_result(
                negative_pos, result.negative_aspect.statement, result.negative_aspect
            )
        )

        return results

    async def _generate_single_aspect(self, position: str) -> AspectResult:
        """Generate a single aspect."""
        existing_context = self._build_existing_aspects_context([position])

        result = await self._conversation.submit(
            response_model=AspectDto,
            user_content=self._single_aspect_prompt(position, existing_context),
        )

        return self._create_aspect_result(position, result.statement, result)

    def _create_aspect_result(
        self,
        position: str,
        statement: str,
        dto: AspectDto,
    ) -> AspectResult:
        """Create AspectResult from position, statement and DTO."""
        # Get parent for meaning lookup
        parent = (
            self._thesis
            if position in [POSITION_T_PLUS, POSITION_T_MINUS]
            else self._antithesis
        )

        # Get meaning and apex from taxonomy
        meaning = StatementClassification.lookup_aspect_meaning(parent, position)
        apex = StatementClassification.lookup_aspect_apex(parent, position)

        # Create component
        component = Statement(
            text=statement,
            meaning=meaning,
        )
        component.commit()
        self._report.node_created(component, meta={"position": position})

        return AspectResult(
            component=component,
            position=position,
            apex_concept=apex,
            heuristic_similarity=dto.heuristic_similarity,
            complementarity_t=dto.complementarity_t,
            complementarity_a=dto.complementarity_a,
        )

    def _filter_relevant_pps(self, pps: list[Perspective]) -> list[Perspective]:
        """Filter Perspectives to only those with the same tension (T-A pair, either orientation)."""
        relevant = []
        target_hashes = {self._thesis.hash, self._antithesis.hash}

        for pp in pps:
            pp_t = pp.t.get()
            pp_a = pp.a.get()
            pp_t_hash = pp_t[0].hash if pp_t else None
            pp_a_hash = pp_a[0].hash if pp_a else None

            # Both T and A must match (same orientation or swapped)
            if {pp_t_hash, pp_a_hash} == target_hashes:
                relevant.append(pp)

        return relevant

    def _build_existing_aspects_context(self, positions_to_generate: list[str]) -> str:
        """Build context string for existing aspects NOT being regenerated."""
        # Only show aspects that exist AND are not being regenerated
        relevant_aspects = {
            pos: comp
            for pos, comp in self._existing_aspects.items()
            if pos not in positions_to_generate
        }

        if not relevant_aspects:
            return ""

        lines = ["The following aspect(s) are already defined:"]
        for pos, component in relevant_aspects.items():
            lines.append(f'- {pos} = "{component.prompt_text}"')
        lines.append("Generate the remaining aspects to be coherent with these.")
        return "\n".join(lines)

    def _build_avoid_context(self) -> str:
        """Build context string for tetrads to avoid.

        Handles T-A symmetry: if an existing PP has T and A swapped relative to
        the current PP, the aspect positions are remapped when displaying.
        """
        if not self._not_like_these:
            return ""

        # Only avoid complete PPs; partial ones are still in progress
        complete_pps = [pp for pp in self._not_like_these if pp.is_complete()]
        if not complete_pps:
            return ""

        lines = ["\n## Previous Tetrads (generate different interpretations)"]
        for i, pp in enumerate(complete_pps, 1):
            lines.append(f"Tetrad {i}:")

            # Check if this PP has T and A swapped relative to current
            pp_t = pp.t.get()
            is_swapped = pp_t and pp_t[0].hash == self._antithesis.hash

            for pos in [
                POSITION_T_PLUS,
                POSITION_T_MINUS,
                POSITION_A_PLUS,
                POSITION_A_MINUS,
            ]:
                manager = pp.get_relationship_manager_by_position(pos)
                result = manager.get()
                if result:
                    # Remap position if T-A are swapped
                    display_pos = self._swap_position(pos) if is_swapped else pos
                    lines.append(f'  - {display_pos}: "{result[0].prompt_text}"')
        lines.append("")
        lines.append(
            "Generate semantically distinct aspects while maintaining contradiction relationships."
        )
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

        t_plus_apex = StatementClassification.lookup_aspect_apex(
            self._thesis, POSITION_T_PLUS
        )
        t_minus_apex = StatementClassification.lookup_aspect_apex(
            self._thesis, POSITION_T_MINUS
        )
        a_plus_apex = StatementClassification.lookup_aspect_apex(
            self._antithesis, POSITION_A_PLUS
        )
        a_minus_apex = StatementClassification.lookup_aspect_apex(
            self._antithesis, POSITION_A_MINUS
        )

        text_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        existing_section = f"\n{existing_context}\n" if existing_context else ""
        avoid_section = self._build_avoid_context()
        avoid_section = f"\n{avoid_section}\n" if avoid_section else ""

        return f"""{text_section}Generate a complete tetrad for this thesis-antithesis pair.

Thesis (T): "{self._thesis.prompt_text}"
Antithesis (A): "{self._antithesis.prompt_text}"

Taxonomy apex concepts for reference:
- T+ apex: {t_plus_apex}
- T- apex: {t_minus_apex}
- A+ apex: {a_plus_apex}
- A- apex: {a_minus_apex}
{existing_section}{avoid_section}
Build the tetrad as its two diagonal contradiction pairs (T+ vs A-, A+ vs T-).
Each aspect has one fixed parent: T+ and T- develop T; A+ and A- develop A.
For each pair:
1. Derive each aspect from ITS OWN parent — a plus develops that parent so it also takes up what the other pole offers; a minus overdevelops that parent one-sidedly, with the other pole absent.
2. Then name the **axis** — the single dimension on which the two aspects are opposite ends, so they cannot both hold at once.
3. Re-read both aspects against step 1 for two distinct failures. (a) Wrong parent: if one is really the OTHER parent developed, rewrite it from its own parent; opposing the facing aspect well is not a reason to keep the wrong parentage. (b) {PLUS_RESTATEMENT_CHECK}
If T and A do not admit a genuine shared axis of opposition, say so in the pair's `axis` field rather than inventing two unrelated aspects.

Generate each aspect (1-{max_words} words) with:

{HS_SCALE}

{COMPLEMENTARITY_SCALE}"""

    def _contradiction_pair_prompt(
        self,
        positive_pos: str,
        negative_pos: str,
        existing_context: str,
    ) -> str:
        """Build prompt for contradiction pair generation."""
        max_words = self.settings.component_length

        # Get parent for each position
        pos_parent = (
            self._thesis
            if positive_pos in [POSITION_T_PLUS, POSITION_T_MINUS]
            else self._antithesis
        )
        neg_parent = (
            self._thesis
            if negative_pos in [POSITION_T_PLUS, POSITION_T_MINUS]
            else self._antithesis
        )

        pos_apex = StatementClassification.lookup_aspect_apex(pos_parent, positive_pos)
        neg_apex = StatementClassification.lookup_aspect_apex(neg_parent, negative_pos)

        text_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        existing_section = f"\n{existing_context}\n" if existing_context else ""
        avoid_section = self._build_avoid_context()
        avoid_section = f"\n{avoid_section}\n" if avoid_section else ""

        return f"""{text_section}Generate a contradiction pair for this thesis-antithesis pair.

Thesis (T): "{self._thesis.prompt_text}"
Antithesis (A): "{self._antithesis.prompt_text}"

Generate {positive_pos} and {negative_pos} that contradict each other.

Taxonomy apex concepts for reference:
- {positive_pos} apex: {pos_apex}
- {negative_pos} apex: {neg_apex}
{existing_section}{avoid_section}
Generate each aspect (1-{max_words} words) with:

{HS_SCALE}

{COMPLEMENTARITY_SCALE}

The positive_aspect is {positive_pos}, the negative_aspect is {negative_pos}.

Each one has a fixed parent:
- {positive_pos} develops "{pos_parent.prompt_text}" constructively, so that it also takes up what the opposing pole offers.
- {negative_pos} overdevelops "{neg_parent.prompt_text}" one-sidedly, with the opposing pole absent.

Derive each aspect from its own parent above. Then name the **axis** — the single dimension on which they are opposite ends — and check that each sits at an opposite end of it. They cannot both hold at once. Do not build {negative_pos} by negating {positive_pos}: both poles can supply a negative end of the same axis, so negation alone leaves the parent undetermined. If no such shared axis exists, say so in the `axis` field rather than inventing two unrelated aspects.

Then re-read {positive_pos}: {PLUS_RESTATEMENT_CHECK}"""

    def _single_aspect_prompt(self, position: str, existing_context: str) -> str:
        """Build prompt for single aspect generation."""
        max_words = self.settings.component_length

        parent = (
            self._thesis
            if position in [POSITION_T_PLUS, POSITION_T_MINUS]
            else self._antithesis
        )
        apex = StatementClassification.lookup_aspect_apex(parent, position)

        # Get description based on position
        if position == POSITION_T_PLUS:
            desc = "constructive development of the thesis that also strengthens the antithesis"
        elif position == POSITION_T_MINUS:
            desc = "exaggerated overdevelopment of the thesis that underdevelops the antithesis"
        elif position == POSITION_A_PLUS:
            desc = "constructive development of the antithesis that also strengthens the thesis"
        else:
            desc = "exaggerated overdevelopment of the antithesis that underdevelops the thesis"

        text_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        existing_section = f"\n{existing_context}\n" if existing_context else ""
        avoid_section = self._build_avoid_context()
        avoid_section = f"\n{avoid_section}\n" if avoid_section else ""
        # Only the plus positions can fail this way — a minus is SUPPOSED to
        # develop its parent one-sidedly, so asking it not to would invert the rule.
        check_section = (
            f"\nAfter drafting it, re-read: {PLUS_RESTATEMENT_CHECK}\n"
            if position in (POSITION_T_PLUS, POSITION_A_PLUS)
            else ""
        )

        return f"""{text_section}Generate {position} for this thesis-antithesis pair.

Thesis (T): "{self._thesis.prompt_text}"
Antithesis (A): "{self._antithesis.prompt_text}"

{position} is the {desc}.
Taxonomy apex concept: {apex}
{check_section}{existing_section}{avoid_section}
Generate the aspect (1-{max_words} words) with:

{HS_SCALE}

{COMPLEMENTARITY_SCALE}"""
