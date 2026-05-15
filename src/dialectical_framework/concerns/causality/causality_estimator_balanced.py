from __future__ import annotations

import asyncio
from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from mirascope import llm

from pydantic import BaseModel, Field

from dialectical_framework.concerns.ai_dto.statement_dto import StatementDto
from dialectical_framework.concerns.ai_dto.statements_deck_dto import StatementsDeckDto
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.concerns.causality.causality_estimator import (
    CausalityEstimator,
    EstimationStructured,
)
from dialectical_framework.protocols.input_resolver import InputResolver

from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.use_brain import use_brain


class CausalCycleAssessmentDto(BaseModel):
    probability: float = Field(
        default=0,
        description="The probability 0 to 1 of the arranged cycle to exist in reality.",
    )
    reasoning_explanation: str = Field(
        default="", description="Explanation why/how this cycle might occur."
    )
    argumentation: str = Field(
        default="",
        description="Circumstances or contexts where this cycle would be most applicable or useful.",
    )


class CausalCycleDto(CausalCycleAssessmentDto):
    aliases: list[str] = Field(
        ...,
        description="Aliases arranged in the circular causality sequence where the last element points to the first",
    )


class CausalCyclesDeckDto(BaseModel):
    causal_cycles: list[CausalCycleDto] = Field(
        ...,
        description="A list of causal circular sequences (cycles).",
    )


def _prompt_input_text(*, text: str) -> list:
    return [
        llm.messages.user(
            f"Consider the following text as the initial context for further analysis:\n\n"
            f"<context>{text}</context>"
        ),
        llm.messages.assistant("OK, let's start.", model_id=None, provider_id=None),
    ]


def _prompt_input_theses(*, statements: list[list[str]]) -> list:
    formatted = "\n\n".join("\n".join(item) for item in statements)
    return [
        llm.messages.user(
            f"Consider these statements:\n\n{formatted}"
        ),
        llm.messages.assistant("OK, let's proceed.", model_id=None, provider_id=None),
    ]


def _build_thesis_context(
    theses: list[StatementDto], text: Optional[str] = None
) -> list:
    """Build prompt context from thesis DTOs and optional source text."""
    tpl: list = []

    if text:
        tpl.extend(_prompt_input_text(text=text))

    statements = [
        [
            f"### Concept/Statement {index + 1} ({dc.alias})",
            f"Alias: {dc.alias}",
            f"Statement: {dc.text}",
        ]
        for index, dc in enumerate(theses)
    ]

    tpl.extend(_prompt_input_theses(statements=statements))
    return tpl


class CausalityEstimatorBalanced(CausalityEstimator):
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

    def prompt_assess_multiple_sequences(
        self, *, sequences: list[str]
    ) -> list:
        sequences_text = "\n".join(f"- {s}" for s in sequences)
        return [llm.messages.user(
            f"Which of the following circular causality sequences provides the best assessment "
            f"considering realism, desirability, and feasibility "
            f"(given that the final step cycles back to the first step):\n"
            f"{sequences_text}\n\n"
            f"<instructions>\n"
            f"For each sequence:\n"
            f"1) Estimate the numeric probability (0 to 1) considering realistic existence, optimal outcomes, and (implementation) feasibility\n"
            f"2) Explain why this sequence might occur (or already occurs) in reality\n"
            f"3) Describe circumstances or contexts where this sequence would be most applicable or useful\n\n"
            f"- Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps.\n"
            f"</instructions>\n\n"
            f"<formatting>\n"
            f"- Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...\n"
            f"- In the explanations, for fluency, use explicit wording instead of aliases.\n"
            f"- Probability is a float between 0 and 1.\n"
            f"</formatting>"
        )]

    def prompt_assess_single_sequence(self, *, sequence: str) -> list:
        return [llm.messages.user(
            f"Assess the following circular causality sequence considering realism, desirability, and feasibility "
            f"(given that the final step cycles back to the first step):\n"
            f"{sequence}\n\n"
            f"<instructions>\n"
            f"1) Estimate the numeric probability (0 to 1) considering realistic existence, optimal outcomes, and (implementation) feasibility\n"
            f"2) Explain why this sequence might occur (or already occurs) in reality\n"
            f"3) Describe circumstances or contexts where this sequence would be most applicable or useful\n\n"
            f"- Only use the sequence **exactly as provided**, do not shorten, skip, collapse, or reorder steps.\n"
            f"</instructions>\n\n"
            f"<formatting>\n"
            f"- In the explanations and argumentation, for fluency, try to use explicit wording instead of technical aliases.\n"
            f"- Probability is a float between 0 and 1.\n"
            f"</formatting>"
        )]

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
            [structures] if not isinstance(structures, list) else structures
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

        # Build DTOs for AI boundary
        component_dtos: dict[str, StatementDto] = {}

        for seq_idx, sequence in enumerate(sequences, 1):
            sequence_aliases: list[str] = []

            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                assert component.hash is not None

                if component.hash not in component_dtos:
                    explanation = ""
                    rationales = list(component.rationales.all())
                    if rationales:
                        rationale, _ = rationales[0]
                        explanation = rationale.text if rationale.text else ""

                    component_dtos[component.hash] = StatementDto(
                        alias=technical_alias,
                        text=component.prompt_text,
                        explanation=explanation,
                    )

                sequence_aliases.append(technical_alias)

            if not sequence_aliases:
                continue

            # Build cycle string: "C1_1 → C1_2 → C1_3 → C1_1..."
            cycle_str = " → ".join(sequence_aliases + [sequence_aliases[0]]) + "..."

            # Add human-readable statements for clarity
            readable_parts = [comp.prompt_text for comp in sequence]
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
            @use_brain(format=CausalCycleAssessmentDto)
            async def _estimate_single_call() -> list:
                prompt = self.prompt_assess_single_sequence(sequence=sequence_str)
                tpl = _build_thesis_context(
                    theses=statements_deck_dto.statements,
                    text=text,
                )
                tpl.extend(prompt)
                return tpl

            assessment: CausalCycleAssessmentDto = await _estimate_single_call()
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
                for input_node, _ in component.inputs.all():
                    assert input_node.hash is not None
                    if input_node.hash not in seen_inputs:
                        seen_inputs.add(input_node.hash)
                        input_nodes.append(input_node)

        if not input_nodes:
            return ""

        # Use InputResolver to resolve all inputs
        return await self.input_resolver.resolve_all(input_nodes)

    @staticmethod
    def _map_results_to_structures(
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
        for sequence in sequences:
            for comp in sequence:
                assert comp.hash is not None
                alias = None
                for existing_comp, existing_alias in components_with_aliases:
                    if existing_comp.hash == comp.hash:
                        alias = existing_alias
                        break
                if alias is None:
                    alias = f"C{len(components_with_aliases) + 1}"
                    components_with_aliases.append((comp, alias))

        # Build alias translation map
        id_to_original_alias: dict[str, str] = {}
        for comp, original_alias in components_with_aliases:
            assert comp.hash is not None
            id_to_original_alias[comp.hash] = original_alias
        alias_translations: dict[str, str] = {}
        for seq_idx, sequence in enumerate(sequences, 1):
            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                assert component.hash is not None
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
            if not matched_structure or not matched_structure.hash:
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
