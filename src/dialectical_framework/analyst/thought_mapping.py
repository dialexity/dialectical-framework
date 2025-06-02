import inspect
from itertools import permutations
from typing import List, overload, Union

from mirascope import prompt_template, Messages, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.analyst.causal_cycles_deck import CausalCyclesDeck
from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.wisdom_unit import WisdomUnit


# TODO: needs heavy refactoring, this is quite dirty
class ThoughtMapping:
    def __init__(
        self,
        text: str,
        *,
        config: WheelBuilderConfig = None,
    ):
        self._text = text

        if config is None:
            config = WheelBuilderConfig(
                component_length=3
            )

        self._component_length = config.component_length
        self._brain = config.brain

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
        def _find_thesis1_call() -> DialecticalComponent:
            return self.prompt_thesis1(text=self._text, component_length=self._component_length)

        return _find_thesis1_call()

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
        def _find_multiple_call() -> DialecticalComponentsDeck:
            return prompt_stuff

        return _find_multiple_call()

    @prompt_template()
    def prompt_sequencing1(self, previous_prompt_stuff: Messages.Type, box: DialecticalComponentsDeck) -> Messages.Type:
        prompt_messages: list = []

        prompt_messages.extend(previous_prompt_stuff)
        findings = []
        aliases = []
        for dc in box.dialectical_components:
            findings.append(dc.pretty())
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
            1) Explain why this sequence might occur in reality
            3) Describe circumstances or contexts where this sequence would be most applicable or useful
            
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
        def _find_sequencing1_call() -> CausalCyclesDeck:
            return self.prompt_sequencing1(previous_prompt_stuff=previous_prompt_stuff, box=box)

        return _find_sequencing1_call()

    @prompt_template()
    def prompt_sequencing2(self, previous_prompt_stuff: Messages.Type, ordered_wisdom_units: List[WisdomUnit]) -> Messages.Type:
        prompt_messages: list = []

        prompt_messages.extend(previous_prompt_stuff)
        findings = []
        for wu in ordered_wisdom_units:
            findings.append(wu.t.pretty())

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
            "\n\n".join([wu.pretty() for wu in ordered_wisdom_units])
        ))

        if len(ordered_wisdom_units) == 1:  # degenerate 1-node cycle
            sequences = f"{ordered_wisdom_units[0].t.alias} → {ordered_wisdom_units[0].a.alias} → {ordered_wisdom_units[0].t.alias}..."
        else:
            # Produce all valid diagonal sequences
            raw_sequences = _generate_compatible_sequences(ordered_wisdom_units)

            # Human-friendly formatting
            sequences = "\n\n".join(
                " → ".join(seq + [seq[0]]) + "..." for seq in raw_sequences
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
        def _find_sequencing2_call() -> CausalCyclesDeck:
            return self.prompt_sequencing2(previous_prompt_stuff=previous_prompt_stuff, ordered_wisdom_units=ordered_wisdom_units)

        return _find_sequencing2_call()

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

    @overload
    async def arrange(self, thoughts: List[str]) -> List[Cycle]: ...


    @overload
    async def arrange(self, thoughts: List[WisdomUnit]) -> List[Cycle]: ...


    async def arrange(self, thoughts: Union[List[str], List[WisdomUnit]]) -> List[Cycle]:
        # Check if we're dealing with WisdomUnits
        if thoughts and isinstance(thoughts[0], WisdomUnit):
            return await self.__arrange_wisdom_units(ordered_wisdom_units=thoughts)

        if len(thoughts) == 1:
            return [Cycle(
                dialectical_components=[
                    DialecticalComponent.from_str(alias="T", statement=thoughts[0], explanation="Provided as string.")
                ],
                probability=1.0,
            )]
        elif len(thoughts) == 2:
            prompt_stuff = self.prompt_thesis2(text=self._text, component_length=self._component_length)
            box = DialecticalComponentsDeck(dialectical_components=[
                DialecticalComponent.from_str(alias="T1", statement=thoughts[0], explanation="Provided as string."),
                DialecticalComponent.from_str(alias="T2", statement=thoughts[1], explanation="Provided as string."),
            ])
        elif len(thoughts) == 3:
            prompt_stuff = self.prompt_thesis3(text=self._text, component_length=self._component_length)
            box = DialecticalComponentsDeck(dialectical_components=[
                DialecticalComponent.from_str(alias="T1", statement=thoughts[0], explanation="Provided as string."),
                DialecticalComponent.from_str(alias="T2", statement=thoughts[1], explanation="Provided as string."),
                DialecticalComponent.from_str(alias="T3", statement=thoughts[2], explanation="Provided as string."),
            ])
        elif len(thoughts) == 4:
            prompt_stuff = self.prompt_thesis4(text=self._text, component_length=self._component_length)
            box = DialecticalComponentsDeck(dialectical_components=[
                DialecticalComponent.from_str(alias="T1", statement=thoughts[0], explanation="Provided as string."),
                DialecticalComponent.from_str(alias="T2", statement=thoughts[1], explanation="Provided as string."),
                DialecticalComponent.from_str(alias="T3", statement=thoughts[2], explanation="Provided as string."),
                DialecticalComponent.from_str(alias="T4", statement=thoughts[3], explanation="Provided as string."),
            ])
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

    async def __arrange_wisdom_units(self, ordered_wisdom_units: List[WisdomUnit]) -> List[Cycle]:
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
            raise ValueError(f"{len(ordered_wisdom_units)} thoughts are not supported yet.")

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

def _generate_compatible_sequences(ordered_wisdom_units):
    """
    Generate all circular, diagonally-symmetric arrangements for T/A pairs.

    Each wisdom unit consists of a thesis (`T`) and its antithesis (`A`). This function arranges them
    around a circle (of length 2n, where n is the number of units) such that:

    1. **Circular Symmetry**: For each pair, if `T_i` is at position `p`, then `A_i` is at position `(p + n) % (2n)`.
    2. **Order Preservation**: The order of all `T`s matches their input order and is strictly increasing
       in placement (i.e., `T1` before `T2`, etc.).
    3. **Start Condition**: The sequence always starts with the first thesis (`T1`) at position 0.

    Parameters:
        ordered_wisdom_units (list): List of wisdom units, each having `.t.alias` (thesis) and `.a.alias` (antithesis).

    Returns:
        list of list: Each inner list is a possible arrangement; positions 0..n-1 represent the 'top row'
        (or first semi-circle), and positions n..2n-1 represent the 'bottom row' (or mirrored second semi-circle),
        such that the diagonal relationship and thesis order constraints are always met.

    Example:
        For input units T1/A1, T2/A2, T3/A3, T4/A4, a valid output can be:
            [T1, T2, T4, T3, A1, A2, A4, A3]
        Which means:
            Top:    T1 -> T2 -> T4 -> T3
            Bottom: A1 -> A2 -> A4 -> A3 (mirrored on the circle)
    """

    n = len(ordered_wisdom_units)
    ts = [u.t.alias for u in ordered_wisdom_units]
    as_ = [u.a.alias for u in ordered_wisdom_units]
    size = 2 * n

    results = []

    # Step 1: set T1 at 0, its diagonal A1 at n
    def backtrack(t_positions, next_t_idx):
        if next_t_idx == n:
            # Fill arrangement based on t_positions
            arrangement = [None] * size
            occupied = set()
            for t_idx, pos in enumerate(t_positions):
                arrangement[pos] = ts[t_idx]
                diag = (pos + n) % size
                arrangement[diag] = as_[t_idx]
                occupied.add(pos)
                occupied.add(diag)
            results.append(arrangement)
            return

        # Next ti to place: always in order, always > previous ti's position
        # Skip positions already assigned (to ensure symmetry & distinctness)
        prev_pos = t_positions[-1]
        for pos in range(prev_pos + 1, size):
            diag = (pos + n) % size

            # Check if pos or diag are used by previous Ts/A's
            collision = False
            for prev_t_pos in t_positions:
                if pos == prev_t_pos or diag == prev_t_pos:
                    collision = True
                    break
                prev_diag = (prev_t_pos + n) % size
                if pos == prev_diag or diag == prev_diag:
                    collision = True
                    break
            if collision:
                continue

            # Place next T at pos, corresponding A at diag
            backtrack(t_positions + [pos], next_t_idx + 1)

    # T1 fixed at position 0
    backtrack([0], 1)
    return results