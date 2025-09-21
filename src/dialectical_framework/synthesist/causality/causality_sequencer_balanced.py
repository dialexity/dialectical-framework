import asyncio
from typing import Self, Union, cast

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto
from dialectical_framework.ai_dto.causal_cycle_dto import CausalCycleDto
from dialectical_framework.ai_dto.causal_cycles_deck_dto import \
    CausalCyclesDeckDto
from dialectical_framework.analyst.domain.assessable_cycle import decompose_probability_into_transitions
from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.analyst.domain.rationale import Rationale
from dialectical_framework.protocols.causality_sequencer import (
    CausalitySequencer, generate_compatible_sequences,
    generate_permutation_sequences)
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.synthesist.domain.wheel_segment import ALIAS_T
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
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
    ) -> Messages.Type: ...

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
    def prompt_assess_single_sequence(self, *, sequence: str) -> Messages.Type: ...

    async def _estimate_cycles(
        self, *, sequences: list[list[DialecticalComponent]]
    ) -> CausalCyclesDeckDto:
        sequences_str: dict[str, list[str]] = {}

        # To avoid hallucinations, make all alias uniform so that AI doesn't try to guess where's a thesis or antithesis
        translated_components: list[DialecticalComponent] = []
        alias_translations: dict[str, str] = {}
        for sequence in sequences:
            for i, dc in enumerate(sequence, 1):
                if dc in translated_components:
                    continue
                translated_components.append(dc)
                alias_translations[f"C{i}"] = dc.alias
                dc.alias = f"C{i}"
                # TODO: we should also do dc_replace for statement/rationales texts, and later translate these back (as alias got translated)

            deck = DialecticalComponentsDeck(dialectical_components=sequence)
            cycle = deck.get_aliases_as_cycle_str()

            # Add statements to sequences, for more clarity
            as_is_seq = cycle
            for a in alias_translations:
                as_is_seq = dc_replace(as_is_seq, a, deck.get_by_alias(a).statement)
            cycle = f"{cycle} ({as_is_seq})"
            sequences_str[cycle] = deck.get_aliases()

        dialectical_components = []
        for dc in translated_components:
            # Check if this component is already in our deduplicated list
            if not any(
                existing_dc.is_same(dc) for existing_dc in dialectical_components
            ):
                dialectical_components.append(dc)

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=CausalCyclesDeckDto)
        async def _estimate_all() -> CausalCyclesDeckDto:
            prompt = self.prompt_assess_multiple_sequences(
                sequences=list(sequences_str.keys())
            )
            tpl = ReverseEngineer.till_theses(
                theses=dialectical_components, text=self.text
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
                    theses=dialectical_components, text=self.text
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
        for sequence, aliases in sequences_str.items():
            async_estimators.append(
                _estimate_single(sequence_str=sequence, aliases=aliases)
            )

        # Execute all async estimators concurrently and collect results
        causal_cycles = await asyncio.gather(*async_estimators)
        # Create the result deck from collected cycles
        result = CausalCyclesDeckDto(causal_cycles=causal_cycles)

        # Translate aliases back in the parameter
        for sequence in sequences:
            for dc in sequence:
                if dc.alias in alias_translations:
                    dc.alias = alias_translations[dc.alias]

        # Translate back the aliases in the result
        for causal_cycle in result.causal_cycles:
            for a in causal_cycle.aliases:
                # Normally technical aliases aren't mentioned in the texts, but who knows... let's blindly translate back
                causal_cycle.reasoning_explanation = dc_replace(
                    causal_cycle.reasoning_explanation, a, alias_translations[a]
                )
                causal_cycle.argumentation = dc_replace(
                    causal_cycle.argumentation, a, alias_translations[a]
                )
            causal_cycle.aliases = [
                alias_translations[alias] for alias in causal_cycle.aliases
            ]

        return result

    async def arrange(
        self, thoughts: Union[list[str], list[WisdomUnit], list[DialecticalComponent]]
    ) -> list[Cycle]:
        sequences = self._get_sequences(thoughts)

        if thoughts and isinstance(thoughts[0], WisdomUnit):
            ordered_wisdom_units: list[WisdomUnit] = thoughts
            if len(thoughts) == 1:
                # TODO: must we normalize anything here?
                return [
                    Cycle(
                        dialectical_components=[
                            ordered_wisdom_units[0].t,
                            ordered_wisdom_units[0].a,
                        ],
                        probability=1.0,
                        causality_type=self.settings.causality_type,
                    )
                ]
            elif len(thoughts) == 2:
                dialectical_components_deck = DialecticalComponentsDeck(
                    dialectical_components=[
                        ordered_wisdom_units[0].t,
                        ordered_wisdom_units[1].t,
                        ordered_wisdom_units[0].a,
                        ordered_wisdom_units[1].a,
                    ]
                )
            elif len(thoughts) == 3:
                dialectical_components_deck = DialecticalComponentsDeck(
                    dialectical_components=[
                        ordered_wisdom_units[0].t,
                        ordered_wisdom_units[1].t,
                        ordered_wisdom_units[2].t,
                        ordered_wisdom_units[0].a,
                        ordered_wisdom_units[1].a,
                        ordered_wisdom_units[2].a,
                    ]
                )
            elif len(thoughts) == 4:
                dialectical_components_deck = DialecticalComponentsDeck(
                    dialectical_components=[
                        ordered_wisdom_units[0].t,
                        ordered_wisdom_units[1].t,
                        ordered_wisdom_units[2].t,
                        ordered_wisdom_units[3].t,
                        ordered_wisdom_units[0].a,
                        ordered_wisdom_units[1].a,
                        ordered_wisdom_units[2].a,
                        ordered_wisdom_units[3].a,
                    ]
                )
            else:
                raise ValueError(
                    f"{len(ordered_wisdom_units)} thoughts are not supported yet."
                )
            causal_cycles_deck = await self._estimate_cycles(sequences=sequences)
        else:
            if len(thoughts) == 1:
                if thoughts and isinstance(thoughts[0], DialecticalComponent):
                    return [
                        Cycle(
                            dialectical_components=thoughts,
                            probability=1.0,
                            causality_type=self.settings.causality_type,
                        )
                    ]
                else:
                    return [
                        Cycle(
                            dialectical_components=[
                                DialecticalComponent(
                                    alias="T",
                                    statement=thoughts[0],
                                )
                            ],
                            probability=1.0,
                            causality_type=self.settings.causality_type,
                        )
                    ]
            elif len(thoughts) <= 4:
                if thoughts and isinstance(thoughts[0], DialecticalComponent):
                    dialectical_components_deck = DialecticalComponentsDeck(
                        dialectical_components=thoughts
                    )
                else:
                    # TODO: We need to actualize the thesis using AI, so that we don't need to write 'Provided as string'
                    dialectical_components_deck = DialecticalComponentsDeck(
                        dialectical_components=[
                            DialecticalComponent(
                                alias=f"T{i + 1}",
                                statement=t,
                                # explanation="Provided as string.",
                            )
                            for i, t in enumerate(thoughts)
                        ]
                    )
            else:
                raise ValueError(f"More than 4 thoughts are not supported yet.")

            causal_cycles_deck = await self._estimate_cycles(sequences=sequences)

        return self._normalize(dialectical_components_deck, causal_cycles_deck)

    def _normalize(
        self,
        dialectical_components_deck: DialecticalComponentsDeck,
        causal_cycles_deck: CausalCyclesDeckDto,
    ) -> list[Cycle]:
        from decimal import ROUND_HALF_UP, Decimal, getcontext

        cycles: list[Cycle] = []
        total_score = 0
        for causal_cycle in causal_cycles_deck.causal_cycles:
            total_score += causal_cycle.probability

        # Probability was a guesswork, let's make it normalized to have statistical strictness
        if total_score > 0:
            getcontext().prec = 16
            q = Decimal("0.001")

            if causal_cycles_deck.causal_cycles and len(causal_cycles_deck.causal_cycles) > 1:
                # Normalize and round to 3 decimals using Decimal
                probs = [
                    Decimal(c.probability) / Decimal(total_score) for c in causal_cycles_deck.causal_cycles
                ]
            else:
                # No normalization needed, just round to 3 decimals using Decimal
                probs = [
                    Decimal(c.probability) for c in causal_cycles_deck.causal_cycles
                ]

            probs = [p.quantize(q, rounding=ROUND_HALF_UP) for p in probs]

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
            else:
                #Single cycle - keep original probability, no normalization needed
                pass

            for causal_cycle, p in zip(causal_cycles_deck.causal_cycles, probs):
                # Create cycle first to get transition count
                cycle = Cycle(
                    dialectical_components=dialectical_components_deck.rearrange_by_aliases(causal_cycle.aliases),
                    causality_type=self.settings.causality_type,
                )
                
                # Create rationale from reasoning and argumentation
                cycle_rationale = Rationale(
                    summary=causal_cycle.reasoning_explanation,
                    text=f"{causal_cycle.reasoning_explanation}\n\n{causal_cycle.argumentation}",
                    # Now here's the trick, the normalized probability is assigned to the cycle
                    # because the initial "probability" is actually "feasibility"
                    relevance=causal_cycle.probability,
                    probability=float(p),
                )

                # Add the rationale to the cycle
                cycle.rationales.append(cycle_rationale)
                # Decompose probabilities to transitions (because cycle probability is multiplication of transition probabilities)
                decompose_probability_into_transitions(
                    probability=cycle_rationale.probability,
                    transitions=cycle.graph.get_all_transitions(),
                    overwrite_existing_transition_probabilities=True)

                cycles.append(cycle)

        cycles.sort(key=lambda c: cast(Cycle, c).calculate_score(), reverse=True)
        return cycles

    @staticmethod
    def _get_sequences(
        thoughts: Union[list[str], list[WisdomUnit], list[DialecticalComponent]],
    ) -> list[list[DialecticalComponent]]:
        if len(thoughts) == 0:
            raise ValueError("No thoughts provided.")

        if thoughts and isinstance(thoughts[0], WisdomUnit):
            ordered_wisdom_units: list[WisdomUnit] = thoughts
            return generate_compatible_sequences(ordered_wisdom_units)
        else:
            if isinstance(thoughts[0], DialecticalComponent):
                dialectical_components = thoughts
            else:
                # TODO: We need to actualize the thesis using AI, so that we don't need to write 'Provided as string'
                dialectical_components = [
                    DialecticalComponent(
                        alias=f"{ALIAS_T}{i + 1}",
                        statement=t,
                        # explanation="Provided as string.",
                    )
                    for i, t in enumerate(thoughts)
                ]
            return generate_permutation_sequences(dialectical_components)
