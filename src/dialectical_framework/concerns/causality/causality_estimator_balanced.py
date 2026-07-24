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
    StepCausation,
)
from dialectical_framework.protocols.input_resolver import InputResolver

from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.use_brain import use_brain


class StepCausationDto(BaseModel):
    from_alias: str = Field(
        default="",
        description="Technical alias of the step's source, exactly as given in the sequence (e.g. C1_1).",
    )
    to_alias: str = Field(
        default="",
        description="Technical alias of the step's target, exactly as given in the sequence (e.g. C1_2).",
    )
    causation: str = Field(
        default="",
        description=(
            "One sentence: the causal mechanism why the source naturally leads to "
            "the target. Use the actual statement wording, never aliases."
        ),
    )


class CausalCycleAssessmentDto(BaseModel):
    # steps comes FIRST: justifying each step before scoring is deliberate
    # chain-of-thought — the holistic probability must be informed by them
    steps: list[StepCausationDto] = Field(
        default_factory=list,
        description=(
            "One entry per consecutive step of the sequence, in order, "
            "including the final wrap-around step back to the first element."
        ),
    )
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


def _resolve_steps(
    step_dtos: list[StepCausationDto],
    sequence: list[Statement],
    seq_idx: int,
    alias_translations: dict[str, str],
) -> list[StepCausation]:
    """
    Resolve step DTOs (alias-identified) to StepCausation (hash/text-identified).

    Primary path: parse C{seq}_{comp} aliases against the sequence.
    Fallback: if aliases are garbled but the step count matches the sequence
    length, map positionally (step i = statements[i] → statements[i+1 mod n]).
    Otherwise drop the steps — per-step causation is best-effort enrichment.
    """
    n = len(sequence)
    if not step_dtos or n == 0:
        return []

    def parse(alias: str) -> Optional[Statement]:
        parts = alias.strip().split("_")
        if len(parts) != 2 or not parts[0].startswith("C"):
            return None
        try:
            s, c = int(parts[0][1:]), int(parts[1])
        except ValueError:
            return None
        if s != seq_idx or not (1 <= c <= n):
            return None
        return sequence[c - 1]

    resolved: list[StepCausation] = []
    for i, dto in enumerate(step_dtos):
        source = parse(dto.from_alias)
        target = parse(dto.to_alias)
        if source is None or target is None:
            if len(step_dtos) != n:
                return []  # aliases garbled and counts don't line up — drop all
            source = sequence[i]
            target = sequence[(i + 1) % n]
        causation = dto.causation
        for technical_alias, text in alias_translations.items():
            causation = dc_replace(causation, technical_alias, text)
        assert source.hash is not None and target.hash is not None
        resolved.append(
            StepCausation(
                source_hash=source.hash,
                target_hash=target.hash,
                source_text=source.text,
                target_text=target.text,
                causation=causation,
            )
        )
    return resolved


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

    def _lens_phrase(self) -> str:
        """Assessment lens inserted after 'Assess the following circular causality sequence'."""
        return "considering realism, desirability, and feasibility"

    def _probability_instruction(self) -> str:
        """Qualifier inserted after 'Estimate the numeric probability (0 to 1)'."""
        return (
            "considering realistic existence, optimal outcomes, and (implementation) "
            "feasibility — weigh these together holistically into a single plausibility score"
        )

    def prompt_assess_single_sequence(self, *, sequence: str) -> list:
        """
        Single prompt template shared by all estimator variants.

        Subclasses customize only _lens_phrase() and _probability_instruction();
        the sequence handling, instructions, and formatting rules stay identical.
        """
        return [llm.messages.user(
            f"Assess the following circular causality sequence {self._lens_phrase()}\n"
            f"(given that the final step cycles back to the first step):\n"
            f"{sequence}\n\n"
            f"<instructions>\n"
            f"1) For each consecutive step of the sequence (including the final wrap-around step back to the first element), state in one sentence the causal mechanism: why does the source naturally lead to the target?\n"
            f"2) Only then, informed by the step-by-step causation, estimate the numeric probability (0 to 1) {self._probability_instruction()}\n"
            f"3) Explain why this sequence might occur (or already occurs) in reality\n"
            f"4) Describe circumstances or contexts where this sequence would be most applicable or useful\n\n"
            f"- Only use the sequence **exactly as provided**, do not shorten, skip, collapse, or reorder steps.\n"
            f"</instructions>\n\n"
            f"<formatting>\n"
            f"- In each step, identify source and target by their technical aliases exactly as given in the sequence; write the causation sentence itself using the actual statement wording, never aliases.\n"
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
                steps=assessment.steps,
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

        # Translate technical aliases to statement text. Aliases are
        # batch-relative and must never survive into persisted rationale
        # prose — statement text is the only durable identifier.
        alias_translations: dict[str, str] = {}
        for seq_idx, sequence in enumerate(sequences, 1):
            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                alias_translations[technical_alias] = component.text

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
            for technical_alias, text in alias_translations.items():
                reasoning_text = dc_replace(reasoning_text, technical_alias, text)
                argumentation_text = dc_replace(
                    argumentation_text, technical_alias, text
                )

            results[matched_structure.hash] = EstimationStructured(
                probability=causal_cycle.probability,
                reasoning=reasoning_text,
                argumentation=argumentation_text,
                steps=_resolve_steps(
                    causal_cycle.steps,
                    sequences[seq_idx],
                    seq_idx + 1,
                    alias_translations,
                ),
            )

        return results
