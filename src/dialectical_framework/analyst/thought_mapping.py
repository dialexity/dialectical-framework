import inspect
import itertools
from itertools import permutations
from typing import List

from mirascope import prompt_template, Messages, llm
from mirascope.integrations.langfuse import with_langfuse

from config import Config
from dialectical_framework.analyst.causal_cycles_deck import CausalCyclesDeck
from dialectical_framework.brain import Brain
from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.wisdom_unit import WisdomUnit


# TODO: needs heavy refactoring, this is quite dirty
class ThoughtMapping:
    def __init__(
        self,
        text: str,
        *,
        component_length=7,
    ):
        self._text = text

        self._component_length = component_length

        # Default brain
        self._brain = Brain(ai_model=Config.MODEL, ai_provider=Config.PROVIDER)

    # TODO: this is duplication with dialectical_reasoning.py, refactor
    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        Extract the central idea or the primary thesis (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

        <formatting>
        Output the dialectical component T within {component_length} word(s), the shorter, the better. The Explanation how it was derived in the passive voice. Don't mention any special denotations such as "T".
        </formatting> 
        """
    )
    def prompt_thesis1(self, text: str, component_length: int) -> Messages.Type: ...

    @with_langfuse()
    async def find_thesis1(self) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_thesis1_call() -> DialecticalComponent:
            return self.prompt_thesis1(text=self._text, component_length=self._component_length)

        return await _find_thesis1_call()

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        In the given context, identify the most important 2 theses (concepts, ideas, elements, steps), T1 and T2, that form the most essential circular causation: T1 → T2 → T1...
        
        <formatting>
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T1", "T+", "A-", "Ac", "Re", etc.
        </formatting> 
        """
    )
    def prompt_thesis2(self, text, component_length: int) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        In the given context, identify the most important 3 concepts (steps, theses, ideas, elements, obstacles, actions, reflections, functions, or other phenomena), T1, T2, T3, that form the most essential circular causation: T1 → T2 → T3 → T1...

        These concepts should represent elements that naturally flow into or cause each other in a repeating cycle.

        <formatting>
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T1", "T+", "A-", "Ac", "Re", etc.
        </formatting> 
        """
    )
    def prompt_thesis3(self, text, component_length: int) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        In the given context, identify the most important 4 concepts (steps, theses, ideas, elements, obstacles, actions, reflections, functions, or other phenomena), T1, T2, T3, T4, that form the most essential circular causation: T1 → T2 → T3 → T4 → T1... 

        These elements should represent the key components of the system described in the text, where opposing concepts appear diagonally: T1 opposes T3, and T2 opposes T4.
        
        For instance, in the 4-stroke engine we have:
        T1 = Fuel Intake; 
        T2 = Compression;
        T3 = Combustion - opposes T1 (Fuel Intake); 
        T4 = Exhaust - opposes T2 (Compression).

        <formatting>
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T1", "T+", "A-", "Ac", "Re", etc.
        </formatting> 
        """
    )
    def prompt_thesis4(self, text, component_length: int) -> Messages.Type: ...

    @with_langfuse()
    async def find_multiple(self, prompt_stuff: Messages.Type) -> DialecticalComponentsDeck:
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponentsDeck,
        )
        async def _find_multiple_call() -> DialecticalComponentsDeck:
            return prompt_stuff

        return await _find_multiple_call()

    @prompt_template()
    def prompt_sequencing1(self, previous_prompt_stuff: Messages.Type, box: DialecticalComponentsDeck) -> Messages.Type:
        prompt_messages: list = []

        prompt_messages.extend(previous_prompt_stuff)
        findings = []
        aliases = []
        for dc in box.dialectical_components:
            findings.append(dc.to_formatted_message())
            aliases.append(dc.alias)
        prompt_messages.append(
            Messages.Assistant(inspect.cleandoc("\n\n".join(findings)))
        )

        if len(aliases) == 1:  # degenerate 1-node cycle
            sequences = f"{aliases[0]} → {aliases[0]}..."
        else:
            first, rest = aliases[0], aliases[1:]
            sequences = " \n\n".join(
                f"{first} → " + " → ".join(p) + f" → {first}..."
                for p in permutations(rest)
                )

        prompt_messages.append(
            Messages.User(
            # "Which of the following circular causality sequences is the most realistic (given that the final step cycles back to the first step):"
            "Assess the following circular causality sequences if they're realistic (given that the final step cycles back to the first step):"
            
            f"\n\n{sequences}\n\n" +

            inspect.cleandoc("""
            For each sequence:
            1) Explain why this sequence might occur in reality
            2) Describe circumstances or contexts where this sequence would be most applicable or useful
            3) Estimate the numeric probability (0 to 1) regarding its realistic existence
            
            <formatting>
            Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
            However, in the explanations don't use these technical placeholders. Probability is a float between 0 and 1.
            </formatting>
            """))
        )
        return prompt_messages

    @with_langfuse()
    async def find_sequencing1(self, previous_prompt_stuff: Messages.Type, box: DialecticalComponentsDeck) -> CausalCyclesDeck:
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=CausalCyclesDeck,
        )
        async def _find_sequencing1_call() -> CausalCyclesDeck:
            return self.prompt_sequencing1(previous_prompt_stuff=previous_prompt_stuff, box=box)

        return await _find_sequencing1_call()

    @prompt_template()
    def prompt_sequencing2(self, previous_prompt_stuff: Messages.Type, ordered_wisdom_units: List[WisdomUnit]) -> Messages.Type:
        prompt_messages: list = []

        prompt_messages.extend(previous_prompt_stuff)
        findings = []
        for wu in ordered_wisdom_units:
            findings.append(wu.t.to_formatted_message())

        prompt_messages.append(
            Messages.Assistant(inspect.cleandoc("\n\n".join(findings)))
        )

        # TODO: Do we want to add the cycle detection for theses only? prompt_sequencing1?

        # Prepend the dialectical analysis to the prompt stuff
        prompt_messages.append(Messages.User(inspect.cleandoc(f"""
            For each concept (T1, T2, T3, etc.) identified in the initial context, identify its semantic/functional antithesis (A), such that positive/constructive side of a given stage/thesis (T+) should oppose/contradict the negative/exaggerated side of its antithesis (A-), and negative/exaggerated side of stage/thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+). 

            For example:
            T = Love
            T+ = Happiness (positive aspect of Love)
            T- = Fixation (negative aspect of Love)
            A = Indifference (antithesis of Love)
            A+ = Objectivity (positive aspect of Indifference, contradicts Fixation)
            A- = Misery (negative aspect of Indifference, contradicts Happiness).
        """)))
        prompt_messages.append(Messages.Assistant(
            "# Dialectical Analysis Results\n" +
            "\n\n".join([wu.formatted_dialectical_analysis() for wu in ordered_wisdom_units])
        ))

        if len(ordered_wisdom_units) == 1:  # degenerate 1-node cycle
            sequences = f"{ordered_wisdom_units[0].t.alias} → {ordered_wisdom_units[0].a.alias} → {ordered_wisdom_units[0].t.alias}..."
        else:
            # Produce all valid diagonal sequences
            raw_sequences = _generate_diagonal_sequences(ordered_wisdom_units)

            # Human-friendly formatting
            sequences = "\n\n".join(
                " → ".join(seq + [seq[0]]) + "..." for seq in raw_sequences
            )

        prompt_messages.append(
            Messages.User(
                # "Which of the following circular causality sequences is the most realistic (given that the final step cycles back to the first step):"
                "Assess the following circular causality sequences if they're realistic (given that the final step cycles back to the first step):"

                f"\n\n{sequences}\n\n" +

                inspect.cleandoc("""
                For each sequence:
                1) Explain why this sequence might occur in reality
                2) Describe circumstances or contexts where this sequence would be most applicable or useful
                3) Estimate the numeric probability (0 to 1) regarding its realistic existence

                <formatting>
                Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
                However, in the explanations don't use these technical placeholders. Probability is a float between 0 and 1.
                </formatting>
                """))
        )
        return prompt_messages

    @with_langfuse()
    async def find_sequencing2(self, previous_prompt_stuff: Messages.Type, ordered_wisdom_units: List[WisdomUnit]) -> CausalCyclesDeck:
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=CausalCyclesDeck,
        )
        async def _find_sequencing2_call() -> CausalCyclesDeck:
            return self.prompt_sequencing2(previous_prompt_stuff=previous_prompt_stuff, ordered_wisdom_units=ordered_wisdom_units)

        return await _find_sequencing2_call()

    async def extract(self, thoughts = 2) -> List[Cycle]:
        if thoughts == 1:
            return [Cycle(
                dialectical_components=[await self.find_thesis1()],
                probability=1.0,
            )]
        elif thoughts == 2:
            prompt_stuff = self.prompt_thesis2(text=self._text, component_length=self._component_length)
            box = await self.find_multiple(prompt_stuff=prompt_stuff)
        elif thoughts == 3:
            prompt_stuff = self.prompt_thesis3(text=self._text, component_length=self._component_length)
            box = await self.find_multiple(prompt_stuff=prompt_stuff)
        elif thoughts == 4:
            prompt_stuff = self.prompt_thesis4(text=self._text, component_length=self._component_length)
            box = await self.find_multiple(prompt_stuff=prompt_stuff)
        else:
            raise ValueError(f"More than 4 thoughts are not supported yet.")

        causal_cycles_box = await self.find_sequencing1(previous_prompt_stuff=prompt_stuff, box=box)
        cycles: list[Cycle] = []
        for causal_cycle in causal_cycles_box.causal_cycles:
            cycles.append(Cycle(
                dialectical_components=box.get_sorted_by_example(causal_cycle.aliases),
                probability=causal_cycle.probability,
                reasoning_explanation=causal_cycle.reasoning_explanation,
                argumentation=causal_cycle.argumentation
            ))
        cycles.sort(key=lambda c: c.probability, reverse=True)
        return cycles

    async def resequence_with_blind_spots(self, ordered_wisdom_units: List[WisdomUnit]) -> List[Cycle]:
        thoughts = len(ordered_wisdom_units)
        if thoughts == 1:
            return [Cycle(
                dialectical_components=[
                    ordered_wisdom_units[0].t,
                    ordered_wisdom_units[0].a,
                ],
                probability=1.0,
            )]
        elif thoughts == 2:
            return [Cycle(
                dialectical_components=[
                    ordered_wisdom_units[0].t,
                    ordered_wisdom_units[1].t,
                    ordered_wisdom_units[0].a,
                    ordered_wisdom_units[1].a,
                ],
                probability=1.0,
            )]
        elif thoughts == 3:
            prompt_stuff = self.prompt_thesis3(text=self._text, component_length=self._component_length)
            box = DialecticalComponentsDeck(dialectical_components=[
                ordered_wisdom_units[0].t,
                ordered_wisdom_units[1].t,
                ordered_wisdom_units[2].t,
                ordered_wisdom_units[0].a,
                ordered_wisdom_units[1].a,
                ordered_wisdom_units[2].a,
            ])
        elif thoughts == 4:
            prompt_stuff = self.prompt_thesis4(text=self._text, component_length=self._component_length)
            box = DialecticalComponentsDeck(dialectical_components=[
                ordered_wisdom_units[0].t,
                ordered_wisdom_units[1].t,
                ordered_wisdom_units[2].t,
                ordered_wisdom_units[3].t,
                ordered_wisdom_units[0].a,
                ordered_wisdom_units[1].a,
                ordered_wisdom_units[2].a,
                ordered_wisdom_units[3].a,
            ])
        else:
            raise ValueError(f"More than 4 thoughts are not supported yet.")

        causal_cycles_box = await self.find_sequencing2(previous_prompt_stuff=prompt_stuff, ordered_wisdom_units=ordered_wisdom_units)
        cycles: list[Cycle] = []
        for causal_cycle in causal_cycles_box.causal_cycles:
            cycles.append(Cycle(
                dialectical_components=box.get_sorted_by_example(causal_cycle.aliases),
                probability=causal_cycle.probability,
                reasoning_explanation=causal_cycle.reasoning_explanation,
                argumentation=causal_cycle.argumentation
            ))
        cycles.sort(key=lambda c: c.probability, reverse=True)
        return cycles

def _generate_diagonal_sequences(ordered_wisdom_units: List[WisdomUnit]):
    """
    Generate all ‘diagonal’ sequences while preserving the given order of
    WisdomUnits.  For N units the result contains 2^(N-1) sequences:

        T1 – [T/A]2 – … – [T/A]N – A1 – … – [A/T]N

    The very first thesis (T1) is always fixed at index 0; every other unit may
    appear either as (T, A) or (A, T) across the two halves, but the **unit
    order itself never changes**.
    """
    if not ordered_wisdom_units:
        return []

    first_unit = ordered_wisdom_units[0]
    remaining_units = ordered_wisdom_units[1:]

    sequences = []

    # orientation[i] == True  → antithesis first (A-T)
    # orientation[i] == False → thesis first      (T-A)
    for orientation in itertools.product([False, True], repeat=len(remaining_units)):
        # Collect both halves at once: (head_alias, tail_alias)
        first_half_pairs = [(first_unit.t.alias, first_unit.a.alias)]

        for unit, swapped in zip(remaining_units, orientation):
            if swapped:                       # A first, then T later
                first_half_pairs.append((unit.a.alias, unit.t.alias))
            else:                             # T first, then A later
                first_half_pairs.append((unit.t.alias, unit.a.alias))

        # Flatten: first all heads, then all tails
        first_half = [head for head, _ in first_half_pairs]
        second_half = [tail for _, tail in first_half_pairs]

        sequences.append(first_half + second_half)

    return sequences

