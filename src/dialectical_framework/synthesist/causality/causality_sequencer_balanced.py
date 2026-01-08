import asyncio
from typing import Any, Self, Union

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto
from dialectical_framework.ai_dto.causal_cycle_dto import CausalCycleDto
from dialectical_framework.ai_dto.causal_cycles_deck_dto import \
    CausalCyclesDeckDto
from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship
from dialectical_framework.protocols.causality_sequencer import (
    CausalitySequencer, generate_compatible_sequences,
    generate_permutation_sequences)
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.decompose_probability_uniformly import decompose_probability_uniformly
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain


class CausalitySequencerBalanced(CausalitySequencer, HasBrain, SettingsAware):
    def __init__(self, *, text: str = ""):
        self.__text = text

    @property
    def text(self) -> str:
        return self.__text

    @text.setter
    def text(self, value: str):
        self.__text = value

    def reload(self, *, text: str) -> Self:
        self.text = text
        return self

    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences provides the best assessment considering realism, desirability, and feasibility (given that the final step cycles back to the first step):
        {sequences:list}

        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) considering realistic existence, optimal outcomes, and (implementation) feasibility
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        - Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>

        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_assess_multiple_sequences(
        self, *, sequences: list[str]
    ) -> "Messages.Type": ...

    @prompt_template(
        """
        USER:
        Assess the following circular causality sequence considering realism, desirability, and feasibility (given that the final step cycles back to the first step):
        {sequence}

        <instructions>
        1) Estimate the numeric probability (0 to 1) considering realistic existence, optimal outcomes, and (implementation) feasibility
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        - Only use the sequence **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>

        <formatting>
        - In the explanations and argumentation, for fluency, try to use explicit wording instead of technical aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_assess_single_sequence(self, *, sequence: str) -> "Messages.Type": ...

    async def _estimate_cycles(
        self, *, sequences: list[list[DialecticalComponent]]
    ) -> CausalCyclesDeckDto:
        """
        Estimate cycles from graph-native component sequences.

        Args:
            sequences: List of sequences, where each sequence is a list of graph-native components

        Returns:
            CausalCyclesDeckDto with assessments for each sequence
        """
        sequences_str: dict[str, list[str]] = {}

        # Track graph-native components for later mapping back
        component_map: dict[str, DialecticalComponent] = {}  # uid -> graph-native component

        # Build DTOs for AI boundary
        component_dtos: dict[str, DialecticalComponentDto] = {}  # uid -> DTO

        for seq_idx, sequence in enumerate(sequences, 1):
            sequence_aliases: list[str] = []

            for comp_idx, component in enumerate(sequence, 1):
                # Generate uniform technical alias to avoid AI bias
                technical_alias = f"C{seq_idx}_{comp_idx}"

                # Store graph-native component by UID for later mapping
                if component.uid not in component_map:
                    component_map[component.uid] = component

                    # Convert graph-native component → DTO for AI
                    # Get first rationale as explanation if available
                    explanation = ""
                    rationales = list(component.rationales.all())
                    if rationales:
                        rationale, _ = rationales[0]
                        explanation = rationale.text if rationale.text else ""

                    component_dtos[component.uid] = DialecticalComponentDto(
                        alias=technical_alias,
                        statement=component.statement,
                        explanation=explanation
                    )

                sequence_aliases.append(technical_alias)

            # Build cycle string: "C1_1 → C1_2 → C1_3 → C1_1..."
            cycle_str = " → ".join(sequence_aliases + [sequence_aliases[0]]) + "..."

            # Add human-readable statements for clarity
            readable_parts = [comp.statement for comp in sequence]
            readable_cycle = " → ".join(readable_parts + [readable_parts[0]]) + "..."

            full_cycle_str = f"{cycle_str} ({readable_cycle})"
            sequences_str[full_cycle_str] = sequence_aliases

        # Create DTO deck for AI boundary
        dialectical_components_deck_dto = DialecticalComponentsDeckDto(
            dialectical_components=list(component_dtos.values())
        )

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=CausalCyclesDeckDto)
        async def _estimate_all() -> CausalCyclesDeckDto:
            prompt = self.prompt_assess_multiple_sequences(
                sequences=list(sequences_str.keys())
            )
            tpl = ReverseEngineer.till_theses(
                theses=dialectical_components_deck_dto.dialectical_components,
                text=self.text
            )
            return extend_tpl(tpl, prompt)

        async def _estimate_single(
            sequence_str: str, aliases: list[str]
        ) -> CausalCycleDto:
            @with_langfuse()
            @use_brain(brain=self.brain, response_model=CausalCycleAssessmentDto)
            async def _estimate_single_call() -> CausalCycleAssessmentDto:
                prompt = self.prompt_assess_single_sequence(sequence=sequence_str)
                tpl = ReverseEngineer.till_theses(
                    theses=dialectical_components_deck_dto.dialectical_components,
                    text=self.text
                )
                return extend_tpl(tpl, prompt)

            assessment = await _estimate_single_call()
            return CausalCycleDto(
                aliases=aliases,
                probability=assessment.probability,
                reasoning_explanation=assessment.reasoning_explanation,
                argumentation=assessment.argumentation,
            )

        # result = await _estimate_all()
        async_estimators = []
        for sequence, als in sequences_str.items():
            async_estimators.append(
                _estimate_single(sequence_str=sequence, aliases=als)
            )

        # Execute all async estimators concurrently and collect results
        causal_cycles = await asyncio.gather(*async_estimators)
        # Create the result deck from collected cycles
        result = CausalCyclesDeckDto(causal_cycles=causal_cycles)

        # Note: Result contains technical aliases (C1_1, C1_2, etc.) which will be
        # mapped back to graph-native components in _normalize() using the sequences parameter
        # Technical aliases were used to avoid AI bias during assessment

        return result

    async def arrange(
        self, thoughts: Union[list[WisdomUnit], list[DialecticalComponent]]
    ) -> list[Cycle]:
        sequences = self._get_sequences(thoughts)

        if thoughts and isinstance(thoughts[0], WisdomUnit):
            ordered_wisdom_units: list[WisdomUnit] = thoughts
            if len(thoughts) == 1:
                # Single WisdomUnit: create synthetic cycle DTO and normalize
                wu = ordered_wisdom_units[0]
                t_result = wu.t.get()
                a_result = wu.a.get()

                if not t_result or not a_result:
                    raise ValueError("WisdomUnit missing T or A component")

                # Unpack with type annotations for IDE support
                t_comp: DialecticalComponent
                t_comp, t_rel = t_result

                a_comp: DialecticalComponent
                a_comp, a_rel = a_result

                # Extract aliases from typed polarity relationships (refactor-safe!)
                # WisdomUnit relationships are always PolarityRelationship, so no fallback needed
                assert isinstance(t_rel, PolarityRelationship), f"Expected PolarityRelationship for T, got {type(t_rel)}"
                assert isinstance(a_rel, PolarityRelationship), f"Expected PolarityRelationship for A, got {type(a_rel)}"

                t_alias = t_rel.alias  # Direct property access, fully typed and validated
                a_alias = a_rel.alias  # Direct property access, fully typed and validated

                # Graph-native components with alias mapping
                components_with_aliases = [
                    (t_comp, t_alias),
                    (a_comp, a_alias)
                ]

                # Create synthetic cycle DTO with feasibility=1.0 (single cycle, certain)
                causal_cycles_deck = CausalCyclesDeckDto(
                    causal_cycles=[
                        CausalCycleDto(
                            aliases=[t_alias, a_alias],
                            probability=1.0,
                            reasoning_explanation="Single unit cycle",
                            argumentation="Default unit cycle"
                        )
                    ]
                )

                return self._normalize(components_with_aliases, causal_cycles_deck, sequences)
            elif len(thoughts) in [2, 3, 4]:
                # Extract all T components, then all A components
                # Graph-native components with aliases from edges
                components_with_aliases: list[tuple[DialecticalComponent, str]] = []

                # First, add all T components
                for wu in ordered_wisdom_units:
                    t_result = wu.t.get()
                    if not t_result:
                        raise ValueError(f"WisdomUnit {wu.uid} missing T component")
                    t_comp, t_rel = t_result

                    # Extract alias from typed polarity relationship (refactor-safe!)
                    # WisdomUnit relationships are always PolarityRelationship
                    assert isinstance(t_rel, PolarityRelationship), f"Expected PolarityRelationship for T, got {type(t_rel)}"
                    t_alias = t_rel.alias  # Direct property access, fully typed and validated

                    components_with_aliases.append((t_comp, t_alias))

                # Then, add all A components
                for wu in ordered_wisdom_units:
                    a_result = wu.a.get()
                    if not a_result:
                        raise ValueError(f"WisdomUnit {wu.uid} missing A component")
                    a_comp, a_rel = a_result

                    # Extract alias from typed polarity relationship (refactor-safe!)
                    # WisdomUnit relationships are always PolarityRelationship
                    assert isinstance(a_rel, PolarityRelationship), f"Expected PolarityRelationship for A, got {type(a_rel)}"
                    a_alias = a_rel.alias  # Direct property access, fully typed and validated

                    components_with_aliases.append((a_comp, a_alias))
            else:
                raise ValueError(
                    f"{len(ordered_wisdom_units)} thoughts are not supported yet."
                )
            causal_cycles_deck = await self._estimate_cycles(sequences=sequences)
        else:
            # Handle list[DialecticalComponent]
            dialectical_components: list[DialecticalComponent] = thoughts

            if len(dialectical_components) == 1:
                # Single component: create synthetic cycle DTO with self-loop
                component = dialectical_components[0]
                alias = "T"  # Default alias for single component
                components_with_aliases = [(component, alias)]

                # Create synthetic cycle DTO with probability=1.0 (single cycle, self-loop)
                causal_cycles_deck = CausalCyclesDeckDto(
                    causal_cycles=[
                        CausalCycleDto(
                            aliases=[alias],
                            probability=1.0,
                            reasoning_explanation="Single component self-loop cycle",
                            argumentation="Default single-thought cycle"
                        )
                    ]
                )

                return self._normalize(components_with_aliases, causal_cycles_deck, sequences)

            elif len(dialectical_components) <= 4:
                # Multiple components: assign default aliases
                components_with_aliases = [
                    (comp, f"T{i+1}") for i, comp in enumerate(dialectical_components)
                ]
            else:
                raise ValueError(f"More than 4 thoughts are not supported yet.")

            causal_cycles_deck = await self._estimate_cycles(sequences=sequences)

        return self._normalize(components_with_aliases, causal_cycles_deck, sequences)

    def _normalize(
        self,
        components_with_aliases: list[tuple[DialecticalComponent, str]],
        causal_cycles_deck: CausalCyclesDeckDto,
        sequences: list[list[DialecticalComponent]],
    ) -> list[Cycle]:
        """
        Normalize cycle DTOs from AI into graph-native Cycle objects.

        Args:
            components_with_aliases: List of (component, alias) tuples from WisdomUnit edges
            causal_cycles_deck: DTO from AI with cycle assessments
            sequences: Original sequences of graph-native components

        Returns:
            List of graph-native Cycle objects sorted by score
        """
        from decimal import ROUND_HALF_UP, Decimal, getcontext

        # Create estimation manager for setting probabilities/relevance
        estimation_manager = EstimationManager()

        # Build translation map from technical aliases to original aliases
        # Technical aliases: C{seq_idx}_{comp_idx} (e.g., "C1_2")
        # Original aliases: T1, A1, etc. (from WisdomUnit edges)
        alias_translations: dict[str, str] = {}
        for seq_idx, sequence in enumerate(sequences, 1):
            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                # Find original alias from components_with_aliases
                for comp, original_alias in components_with_aliases:
                    if comp.uid == component.uid:
                        alias_translations[technical_alias] = original_alias
                        break

        cycles: list[Cycle] = []
        total_score = 0
        for causal_cycle in causal_cycles_deck.causal_cycles:
            total_score += causal_cycle.probability

        # Probability was a guesswork, let's make it normalized to have statistical strictness
        if total_score > 0:
            getcontext().prec = 16
            q = Decimal("0.001")

            probs = []
            if causal_cycles_deck.causal_cycles:
                # Normalize and round to 3 decimals using Decimal
                probs = [
                    Decimal(c.probability) / Decimal(total_score) for c in causal_cycles_deck.causal_cycles
                ]

                if len(causal_cycles_deck.causal_cycles) > 1:
                    # Multiple cycles: normalize to sum to 1.0 and sort by probability

                    # Sort by rounded probabilities (descending)
                    causal_cycles_deck.causal_cycles.sort(
                        key=lambda c: float(
                            Decimal(c.probability) / Decimal(total_score)
                        ),
                        reverse=True,
                    )
                    # Recompute in sorted order
                    probs.sort(reverse=True)

                    # Add the exact decimal remainder to the highest-probability cycle
                    total_after = sum(probs)
                    diff = Decimal("1.000") - total_after
                    probs[0] = (probs[0] + diff).quantize(q, rounding=ROUND_HALF_UP)
                    assert abs(sum(probs) - Decimal("1.000")) < Decimal("0.001")


            probs = [p.quantize(q, rounding=ROUND_HALF_UP) for p in probs]

            for causal_cycle, p in zip(causal_cycles_deck.causal_cycles, probs):
                # Map technical aliases back to graph-native components
                # Technical aliases format: "C{seq_idx}_{comp_idx}" (e.g., "C1_2")
                ordered_components: list[DialecticalComponent] = []
                for technical_alias in causal_cycle.aliases:
                    # Parse technical alias to find component in sequences
                    parts = technical_alias.split('_')
                    if len(parts) == 2:
                        seq_idx = int(parts[0][1:]) - 1  # C1 -> index 0
                        comp_idx = int(parts[1]) - 1      # 2 -> index 1
                        if seq_idx < len(sequences) and comp_idx < len(sequences[seq_idx]):
                            ordered_components.append(sequences[seq_idx][comp_idx])
                    else:
                        # Fallback: try to find by alias in components_with_aliases
                        for comp, alias in components_with_aliases:
                            if alias == technical_alias:
                                ordered_components.append(comp)
                                break

                # Create graph-native cycle
                cycle = Cycle(causality_type=self.settings.causality_type)
                cycle.save()

                # Create transitions for the component chain
                if ordered_components:
                    for i in range(len(ordered_components)):
                        source_comp = ordered_components[i]
                        target_comp = ordered_components[(i + 1) % len(ordered_components)]  # Wrap to first

                        # Create transition node
                        transition = Transition()
                        transition.save()

                        # Connect transition to source and target components
                        transition.source.connect(source_comp)
                        transition.target.connect(target_comp)

                        # Connect transition to cycle
                        transition.cycle.connect(cycle)

                # Translate technical aliases back to original aliases in text fields
                # This ensures the rationale text uses meaningful aliases (T1, A1) instead of (C1_1, C1_2)
                reasoning_text = causal_cycle.reasoning_explanation
                argumentation_text = causal_cycle.argumentation
                for technical_alias, original_alias in alias_translations.items():
                    reasoning_text = dc_replace(reasoning_text, technical_alias, original_alias)
                    argumentation_text = dc_replace(argumentation_text, technical_alias, original_alias)

                # Create rationale from reasoning and argumentation
                cycle_rationale = Rationale(
                    summary=argumentation_text,
                    text=reasoning_text,
                )
                cycle_rationale.save()  # Save before connecting

                # Set probability and relevance via estimation manager
                # The normalized probability is the cycle's competitive strength
                estimation_manager.upsert_estimation(
                    cycle_rationale, ProbabilityEstimation, float(p)
                )
                # The initial "probability" from AI is actually "feasibility" (relevance)
                estimation_manager.upsert_estimation(
                    cycle_rationale, RelevanceEstimation, causal_cycle.probability
                )

                # Add the rationale to the cycle
                cycle.rationales.connect(cycle_rationale)

                # Decompose cycle probability into transition probabilities
                # This ensures transitions have proper P values for TaroRank scoring
                self._decompose_probability_into_transitions(
                    probability=float(p),  # Use normalized probability
                    cycle=cycle,
                    overwrite_existing=True
                )

                cycles.append(cycle)

        # Sort by rationale probability (competitive strength)
        # The normalized probability represents how likely this cycle is relative to alternatives
        def get_cycle_priority(cycle: Cycle) -> float:
            """Get cycle's competitive probability from its rationale."""
            rationales = list(cycle.rationales.all())
            if rationales:
                rat, _ = rationales[0]
                return rat.probability or 0.0
            return 0.0

        cycles.sort(key=get_cycle_priority, reverse=True)
        return cycles

    @staticmethod
    def _get_sequences(
        thoughts: Union[list[WisdomUnit], list[DialecticalComponent]],
    ) -> list[list[DialecticalComponent]]:
        """
        Generate sequences from graph-native thoughts.

        Args:
            thoughts: Either WisdomUnits (generates compatible sequences) or
                     DialecticalComponents (generates permutations)

        Returns:
            List of component sequences for cycle generation

        Note:
            Caller must convert strings/DTOs to DialecticalComponents before calling
        """
        if len(thoughts) == 0:
            raise ValueError("No thoughts provided.")

        if thoughts and isinstance(thoughts[0], WisdomUnit):
            ordered_wisdom_units: list[WisdomUnit] = thoughts
            return generate_compatible_sequences(ordered_wisdom_units)
        else:
            # Handle list[DialecticalComponent]
            dialectical_components: list[DialecticalComponent] = thoughts
            return generate_permutation_sequences(dialectical_components)

    @staticmethod
    def _decompose_probability_into_transitions(
        probability: float,
        cycle: Cycle,
        overwrite_existing: bool = False
    ) -> None:
        """
        Decompose cycle probability into individual transition probabilities.

        Uses the same logic as legacy domain implementation:
        - Case 1 (no existing): uniform decomposition (nth root)
        - Case 2 (all existing): do nothing
        - Case 3 (mixed): distribute remaining probability uniformly

        Args:
            probability: Overall cycle probability (0.0 to 1.0)
            cycle: Graph-native Cycle node with transitions
            overwrite_existing: If True, clear all existing transition probabilities first

        Note:
            Sets ProbabilityEstimation on Transition nodes via EstimationManager.
            Probabilities multiply: P_cycle = P_t1 × P_t2 × ... × P_tn
        """
        estimation_manager = EstimationManager()

        # Get all transitions
        all_transitions = [trans for trans, _ in cycle.transitions.all()]
        if not all_transitions:
            return

        # Optionally clear existing probabilities
        if overwrite_existing:
            for trans in all_transitions:
                # Remove existing ProbabilityEstimation if present
                estimation_manager.clear_estimations(trans, [ProbabilityEstimation])

        # Check which transitions already have probabilities
        transitions_with_probs = []
        transitions_without_probs = []

        for trans in all_transitions:
            # Check if transition has ProbabilityEstimation
            has_prob = False
            for est, _ in trans.estimations.all():
                if isinstance(est, ProbabilityEstimation):
                    transitions_with_probs.append((trans, est.value))
                    has_prob = True
                    break

            if not has_prob:
                transitions_without_probs.append(trans)

        # Case 2: All transitions already have probabilities - don't override
        if not transitions_without_probs:
            return

        # Case 1: No transitions have probabilities - use uniform decomposition
        if not transitions_with_probs:
            individual_prob = decompose_probability_uniformly(
                probability,
                len(all_transitions)
            )
            for trans in all_transitions:
                estimation_manager.upsert_estimation(
                    trans, ProbabilityEstimation, individual_prob
                )
        else:
            # Case 3: Mixed - some have probabilities, some don't
            # Calculate what's "left over" for the unassigned transitions
            assigned_prob_product = 1.0
            for _, prob_value in transitions_with_probs:
                assigned_prob_product *= prob_value

            # Remaining probability to distribute
            remaining_prob = probability / assigned_prob_product if assigned_prob_product > 0 else probability

            # Distribute remaining probability uniformly among unassigned transitions
            if transitions_without_probs and remaining_prob > 0:
                individual_prob = decompose_probability_uniformly(
                    remaining_prob,
                    len(transitions_without_probs)
                )
                for trans in transitions_without_probs:
                    estimation_manager.upsert_estimation(
                        trans, ProbabilityEstimation, individual_prob
                    )
