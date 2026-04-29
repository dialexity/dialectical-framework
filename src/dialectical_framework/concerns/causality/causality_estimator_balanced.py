from __future__ import annotations

import asyncio
from typing import Union

from dependency_injector.wiring import Provide, inject
from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto
from dialectical_framework.ai_dto.causal_cycle_dto import CausalCycleDto
from dialectical_framework.ai_dto.causal_cycles_deck_dto import \
    CausalCyclesDeckDto
from dialectical_framework.ai_dto.statement_dto import \
    StatementDto
from dialectical_framework.ai_dto.statements_deck_dto import \
    StatementsDeckDto
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.concerns.causality.causality_estimator import (
    CausalityEstimator,
    EstimationStructured,
)
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain


class CausalityEstimatorBalanced(CausalityEstimator, HasBrain, SettingsAware):
    """
    Causality estimator that estimates probabilities for Cycles and Wheels.

    This is a "dumb" AI estimator - it runs estimation on whatever it receives
    and returns raw results. It does NOT:
    - Check for existing estimations
    - Normalize probabilities
    - Save to database

    The CausalityEstimation concern handles all the smart orchestration.

    Subclasses (Desirable, Feasible, Realistic, Criteria) override prompt
    templates to change the assessment perspective.
    """

    @inject
    def __init__(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ):
        self._input_resolver = input_resolver

    @property
    def input_resolver(self) -> InputResolver:
        return self._input_resolver

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

    async def estimate(
        self,
        structures: Union[Cycle, list[Cycle], Wheel, list[Wheel]],
    ) -> dict[str, EstimationStructured]:
        """
        Estimate probabilities for structures using AI.

        This is a simple AI estimator - it estimates ALL structures provided
        and returns raw (non-normalized) results. Does NOT touch the database.

        Args:
            structures: Single structure or list of same-type structures
                       (all Cycles OR all Wheels, not mixed)

        Returns:
            Dict mapping structure hash to EstimationStructured with raw AI results

        Raises:
            ValueError: If structures is empty or mixed types
        """
        # Normalize to list
        structure_list: list[Union[Cycle, Wheel]] = (
            [structures] if not isinstance(structures, list) else list(structures)
        )

        if not structure_list:
            raise ValueError("No structures provided.")

        # Validate all structures are same type
        first_type = type(structure_list[0])
        if not all(type(s) == first_type for s in structure_list):
            raise ValueError(
                "All structures must be same type (all Cycles or all Wheels, not mixed)"
            )

        # Get component sequences from each structure
        sequences: list[list[Statement]] = []
        for structure in structure_list:
            components = structure.statements
            sequences.append(components)

        if not sequences or not sequences[0]:
            return {}

        # Derive text from Input nodes linked to components
        text = await self._get_source_text(sequences)

        # Get AI estimations
        causal_cycles_deck = await self._estimate_cycles(sequences=sequences, text=text)

        # Map results back to structures
        return self._map_results_to_structures(
            structure_list, causal_cycles_deck, sequences
        )

    async def _estimate_cycles(
        self, *, sequences: list[list[Statement]], text: str
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
        component_map: dict[str, Statement] = (
            {}
        )  # uid -> graph-native component

        # Build DTOs for AI boundary
        component_dtos: dict[str, StatementDto] = {}  # identity -> DTO

        for seq_idx, sequence in enumerate(sequences, 1):
            sequence_aliases: list[str] = []

            for comp_idx, component in enumerate(sequence, 1):
                # Generate uniform technical alias to avoid AI bias
                technical_alias = f"C{seq_idx}_{comp_idx}"

                # Store graph-native component by identity for later mapping
                if component.hash not in component_map:
                    component_map[component.hash] = component

                    # Convert graph-native component → DTO for AI
                    # Get first rationale as explanation if available
                    explanation = ""
                    rationales = list(component.rationales.all())
                    if rationales:
                        rationale, _ = rationales[0]
                        explanation = rationale.text if rationale.text else ""

                    component_dtos[component.hash] = StatementDto(
                        alias=technical_alias,
                        text=component.text,
                        explanation=explanation,
                    )

                sequence_aliases.append(technical_alias)

            # Build cycle string: "C1_1 → C1_2 → C1_3 → C1_1..."
            cycle_str = " → ".join(sequence_aliases + [sequence_aliases[0]]) + "..."

            # Add human-readable statements for clarity
            readable_parts = [comp.text for comp in sequence]
            readable_cycle = " → ".join(readable_parts + [readable_parts[0]]) + "..."

            full_cycle_str = f"{cycle_str} ({readable_cycle})"
            sequences_str[full_cycle_str] = sequence_aliases

        # Create DTO deck for AI boundary
        statements_deck_dto = StatementsDeckDto(
            statements=list(component_dtos.values())
        )

        async def _estimate_single(
            sequence_str: str, aliases: list[str]
        ) -> CausalCycleDto:
            @with_langfuse()
            @use_brain(brain=self.brain, response_model=CausalCycleAssessmentDto)
            async def _estimate_single_call() -> CausalCycleAssessmentDto:
                prompt = self.prompt_assess_single_sequence(sequence=sequence_str)
                tpl = ReverseEngineer.till_theses(
                    theses=statements_deck_dto.statements,
                    text=text,
                )
                return extend_tpl(tpl, prompt)

            assessment = await _estimate_single_call()
            return CausalCycleDto(
                aliases=aliases,
                probability=assessment.probability,
                reasoning_explanation=assessment.reasoning_explanation,
                argumentation=assessment.argumentation,
            )

        # Execute all async estimators concurrently
        async_estimators = []
        for sequence, als in sequences_str.items():
            async_estimators.append(
                _estimate_single(sequence_str=sequence, aliases=als)
            )

        causal_cycles = list(await asyncio.gather(*async_estimators))
        return CausalCyclesDeckDto(causal_cycles=causal_cycles)

    async def _get_source_text(
        self, sequences: list[list[Statement]]
    ) -> str:
        """
        Get source text from Input nodes linked to the components.

        Uses the injected InputResolver to properly resolve content
        (handles URIs, data URIs, etc.).

        Args:
            sequences: List of component sequences

        Returns:
            Resolved and concatenated source text from all unique Inputs
        """
        from dialectical_framework.graph.nodes.input import Input

        # Collect unique Input nodes
        seen_inputs: set[str] = set()
        input_nodes: list[Input] = []

        for sequence in sequences:
            for component in sequence:
                # Get Input(s) this component was extracted from
                for input_node, _ in component.inputs.all():
                    if input_node.hash not in seen_inputs:
                        seen_inputs.add(input_node.hash)
                        input_nodes.append(input_node)

        if not input_nodes:
            return ""

        # Use InputResolver to resolve all inputs
        return await self.input_resolver.resolve_all(input_nodes)

    def _map_results_to_structures(
        self,
        structures: list[Union[Cycle, Wheel]],
        causal_cycles_deck: CausalCyclesDeckDto,
        sequences: list[list[Statement]],
    ) -> dict[str, EstimationStructured]:
        """
        Map AI results back to structures by hash.

        Args:
            structures: List of structures (in sequence order)
            causal_cycles_deck: AI estimation results
            sequences: Component sequences used for AI estimation

        Returns:
            Dict mapping structure hash to EstimationStructured
        """
        if not causal_cycles_deck.causal_cycles:
            return {}

        # Build index map: sequence_index -> structure
        index_to_structure: dict[int, Union[Cycle, Wheel]] = {
            i: structure for i, structure in enumerate(structures)
        }

        # Build component-alias translations for text replacement
        components_with_aliases: list[tuple[Statement, str]] = []
        for seq_idx, sequence in enumerate(sequences):
            for comp in sequence:
                alias = None
                for existing_comp, existing_alias in components_with_aliases:
                    if existing_comp.hash == comp.hash:
                        alias = existing_alias
                        break
                if alias is None:
                    alias = f"C{len(components_with_aliases) + 1}"
                    components_with_aliases.append((comp, alias))

        # Build alias translation map
        id_to_original_alias: dict[str, str] = {
            comp.hash: original_alias
            for comp, original_alias in components_with_aliases
        }
        alias_translations: dict[str, str] = {}
        for seq_idx, sequence in enumerate(sequences, 1):
            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                original_alias = id_to_original_alias.get(component.hash)
                if original_alias:
                    alias_translations[technical_alias] = original_alias

        # Map results
        results: dict[str, EstimationStructured] = {}

        for causal_cycle in causal_cycles_deck.causal_cycles:
            if not causal_cycle.aliases:
                continue

            # Extract sequence index from first alias (format: C{seq_idx}_{comp_idx})
            first_alias = causal_cycle.aliases[0]
            parts = first_alias.split("_")
            if len(parts) != 2 or not parts[0].startswith("C"):
                continue

            try:
                seq_idx = int(parts[0][1:]) - 1
            except ValueError:
                continue

            matched_structure = index_to_structure.get(seq_idx)
            if not matched_structure:
                continue

            # Translate aliases in text
            reasoning_text = causal_cycle.reasoning_explanation
            argumentation_text = causal_cycle.argumentation
            for technical_alias, original_alias in alias_translations.items():
                reasoning_text = dc_replace(
                    reasoning_text, technical_alias, original_alias
                )
                argumentation_text = dc_replace(
                    argumentation_text, technical_alias, original_alias
                )

            results[matched_structure.hash] = EstimationStructured(
                probability=causal_cycle.probability,
                reasoning=reasoning_text,
                argumentation=argumentation_text,
            )

        return results
