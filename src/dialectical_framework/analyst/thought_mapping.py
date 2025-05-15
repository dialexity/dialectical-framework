import inspect
from abc import ABC, abstractmethod
from itertools import permutations
from typing import List

from mirascope import prompt_template, Messages, llm
from mirascope.integrations.langfuse import with_langfuse

from config import Config
from dialectical_framework.brain import Brain
from dialectical_framework.causal_cycle import CausalCycle
from dialectical_framework.causal_cycles_box import CausalCyclesBox
from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_box import DialecticalComponentsBox


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
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallbck to litellm
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
    async def find_multiple(self, prompt_stuff: Messages.Type) -> DialecticalComponentsBox:
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallbck to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponentsBox,
        )
        async def _find_multiple_call() -> DialecticalComponentsBox:
            return prompt_stuff

        return await _find_multiple_call()

    @prompt_template()
    def prompt_sequencing(self, previous_prompt_stuff: Messages.Type, box: DialecticalComponentsBox) -> Messages.Type:
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
            "Which of the following circular causality sequences is the most realistic (given that the final step cycles back to the first step):"
            
            f"\n\n{sequences}\n\n" +

            inspect.cleandoc("""
            For each sequence:
            1) Estimate the numeric probability (0 to 1) regarding its realistic existence
            2) Explain why this sequence might occur in reality
            3) Describe circumstances or contexts where this sequence would be most applicable or useful
            
            <formatting>
            Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
            However, in the explanations don't use these technical placeholders.
            </formatting>
            """))
        )
        return prompt_messages

    @with_langfuse()
    async def find_sequencing(self, previous_prompt_stuff: Messages.Type, box: DialecticalComponentsBox) -> CausalCyclesBox:
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallbck to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=CausalCyclesBox,
        )
        async def _find_sequencing_call() -> CausalCyclesBox:
            return self.prompt_sequencing(previous_prompt_stuff=previous_prompt_stuff, box=box)

        return await _find_sequencing_call()

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

        causal_cycles_box = await self.find_sequencing(previous_prompt_stuff=prompt_stuff, box=box)
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

