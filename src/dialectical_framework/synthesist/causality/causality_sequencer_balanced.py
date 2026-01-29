import asyncio
from typing import Union

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
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship
from dialectical_framework.protocols.causality_sequencer import CausalitySequencer
from dialectical_framework.utils.sequence_generation import (
    generate_compatible_sequences,
    generate_permutation_sequences,
)
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.decompose_probability_uniformly import decompose_probability_uniformly
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain


class CausalitySequencerBalanced(CausalitySequencer, HasBrain, SettingsAware):
    """
    Stateless causality sequencer that takes text as method parameter.
    """

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
        self, *, sequences: list[list[DialecticalComponent]], text: str
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
                text=text
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
                    text=text
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
        self,
        thoughts: Union[list[WisdomUnit], list[DialecticalComponent]],
        *,
        text: str,
    ) -> Union[list[Cycle], list[Wheel]]:
        """
        Arrange thoughts into circular topologies.

        Returns:
            - list[Cycle] when given DialecticalComponents (thesis-level ordering)
            - list[Wheel] when given WisdomUnits (detailed T+A arrangement)
        """
        sequences = self._get_sequences(thoughts)

        if thoughts and isinstance(thoughts[0], WisdomUnit):
            # WisdomUnits → Wheels
            ordered_wisdom_units: list[WisdomUnit] = thoughts
            if len(thoughts) == 1:
                # Single WisdomUnit: create wheel with T → A → T sequence
                wu = ordered_wisdom_units[0]
                t_result = wu.t.get()
                a_result = wu.a.get()

                if not t_result or not a_result:
                    raise ValueError("WisdomUnit missing T or A component")

                t_comp, t_rel = t_result
                a_comp, a_rel = a_result

                assert isinstance(t_rel, PolarityRelationship)
                assert isinstance(a_rel, PolarityRelationship)

                # Create single wheel with probability 1.0 (only option)
                wheel = Wheel()
                wheel.save()

                # Create transitions: T → A → T
                for source_comp, target_comp in [(t_comp, a_comp), (a_comp, t_comp)]:
                    trans = Transition()
                    trans.save()
                    trans.source.connect(source_comp)
                    trans.target.connect(target_comp)
                    trans.cycle.connect(wheel)

                # Create rationale
                rationale = Rationale(
                    summary="Single unit wheel",
                    text="Default single-wisdom-unit wheel arrangement"
                )
                rationale.save()

                estimation_manager = EstimationManager()
                estimation_manager.upsert_estimation(rationale, ProbabilityEstimation, 1.0)
                estimation_manager.upsert_estimation(rationale, RelevanceEstimation, 1.0)

                wheel.rationales.connect(rationale)

                return [wheel]

            elif len(thoughts) in [2, 3, 4]:
                # Multiple WisdomUnits: get AI assessment and create Wheels
                components_with_aliases: list[tuple[DialecticalComponent, str]] = []

                for wu in ordered_wisdom_units:
                    t_result = wu.t.get()
                    a_result = wu.a.get()
                    if t_result:
                        t_comp, t_rel = t_result
                        assert isinstance(t_rel, PolarityRelationship)
                        components_with_aliases.append((t_comp, t_rel.alias))
                    if a_result:
                        a_comp, a_rel = a_result
                        assert isinstance(a_rel, PolarityRelationship)
                        components_with_aliases.append((a_comp, a_rel.alias))

                causal_cycles_deck = await self._estimate_cycles(sequences=sequences, text=text)
                return self._normalize(components_with_aliases, causal_cycles_deck, sequences, node_type=Wheel)
            else:
                raise ValueError(f"{len(ordered_wisdom_units)} thoughts are not supported yet.")

        else:
            # DialecticalComponents → Cycles
            dialectical_components: list[DialecticalComponent] = thoughts

            if len(dialectical_components) == 1:
                # Single component: create synthetic cycle DTO with self-loop
                component = dialectical_components[0]
                alias = "T"
                components_with_aliases = [(component, alias)]

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

            causal_cycles_deck = await self._estimate_cycles(sequences=sequences, text=text)
            return self._normalize(components_with_aliases, causal_cycles_deck, sequences)

    def _normalize(
        self,
        components_with_aliases: list[tuple[DialecticalComponent, str]],
        causal_cycles_deck: CausalCyclesDeckDto,
        sequences: list[list[DialecticalComponent]],
        node_type: type = Cycle,
    ) -> Union[list[Cycle], list[Wheel]]:
        """
        Normalize cycle DTOs from AI into graph-native Cycle or Wheel objects.

        Args:
            components_with_aliases: List of (component, alias) tuples
            causal_cycles_deck: DTO from AI with cycle assessments
            sequences: Original sequences of graph-native components
            node_type: Type of node to create (Cycle or Wheel)

        Returns:
            List of graph-native Cycle or Wheel objects sorted by probability
        """
        from decimal import ROUND_HALF_UP, Decimal, getcontext

        estimation_manager = EstimationManager()

        # Build translation map from technical aliases to original aliases
        uid_to_original_alias: dict[str, str] = {
            comp.uid: original_alias for comp, original_alias in components_with_aliases
        }
        alias_translations: dict[str, str] = {}
        for seq_idx, sequence in enumerate(sequences, 1):
            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                original_alias = uid_to_original_alias.get(component.uid)
                if original_alias:
                    alias_translations[technical_alias] = original_alias

        nodes: list = []

        if not causal_cycles_deck.causal_cycles:
            return nodes

        # Normalize probabilities
        getcontext().prec = 28
        q = Decimal("0.001")

        raw_probs: list[Decimal] = [
            Decimal(str(c.probability)) for c in causal_cycles_deck.causal_cycles
        ]
        total_score = sum(raw_probs)

        if total_score > 0:
            normalized = [p / total_score for p in raw_probs]
        else:
            normalized = [Decimal("1") / Decimal(str(len(raw_probs)))] * len(raw_probs)

        cycle_prob_pairs = list(zip(causal_cycles_deck.causal_cycles, normalized))
        if len(cycle_prob_pairs) > 1:
            cycle_prob_pairs.sort(key=lambda cp: cp[1], reverse=True)

        quantized = [p.quantize(q, rounding=ROUND_HALF_UP) for _, p in cycle_prob_pairs]
        if quantized:
            remainder = Decimal("1.000") - sum(quantized)
            quantized[0] = (quantized[0] + remainder).quantize(q, rounding=ROUND_HALF_UP)

        for (causal_cycle, _), p in zip(cycle_prob_pairs, quantized):
            # Map technical aliases to components
            ordered_components: list[DialecticalComponent] = []
            for technical_alias in causal_cycle.aliases:
                parts = technical_alias.split("_")
                if len(parts) == 2 and parts[0].startswith("C"):
                    try:
                        seq_idx = int(parts[0][1:]) - 1
                        comp_idx = int(parts[1]) - 1
                    except ValueError:
                        seq_idx = -1
                        comp_idx = -1

                    if (
                        0 <= seq_idx < len(sequences)
                        and 0 <= comp_idx < len(sequences[seq_idx])
                    ):
                        ordered_components.append(sequences[seq_idx][comp_idx])
                        continue

                # Fallback
                for comp, alias in components_with_aliases:
                    if alias == technical_alias:
                        ordered_components.append(comp)
                        break

            # Create node (Cycle with intent, or Wheel without)
            if node_type == Cycle:
                node = Cycle(intent=self.settings.cycle_intent)
            else:
                node = Wheel()
            node.save()

            # Create transitions
            if ordered_components:
                for i in range(len(ordered_components)):
                    source_comp = ordered_components[i]
                    target_comp = ordered_components[(i + 1) % len(ordered_components)]

                    transition = Transition()
                    transition.save()
                    transition.source.connect(source_comp)
                    transition.target.connect(target_comp)
                    transition.cycle.connect(node)

            # Translate aliases in text
            reasoning_text = causal_cycle.reasoning_explanation
            argumentation_text = causal_cycle.argumentation
            for technical_alias, original_alias in alias_translations.items():
                reasoning_text = dc_replace(reasoning_text, technical_alias, original_alias)
                argumentation_text = dc_replace(argumentation_text, technical_alias, original_alias)

            # Create rationale
            rationale = Rationale(
                summary=argumentation_text,
                text=reasoning_text,
            )
            rationale.save()

            estimation_manager.upsert_estimation(rationale, ProbabilityEstimation, float(p))
            estimation_manager.upsert_estimation(rationale, RelevanceEstimation, causal_cycle.probability)

            node.rationales.connect(rationale)

            self._decompose_probability_into_transitions(
                probability=float(p),
                cycle=node,
                overwrite_existing=True
            )

            nodes.append(node)

        def get_priority(node) -> float:
            """Get node's competitive probability from its rationale."""
            rationales = list(node.rationales.all())
            if rationales:
                rat, _ = rationales[0]
                return rat.probability or 0.0
            return 0.0

        nodes.sort(key=get_priority, reverse=True)
        return nodes

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
        all_transitions = cycle.transitions
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
