from typing import List, overload, Union

from mirascope import prompt_template, Messages
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_structured_data.causal_cycle import CausalCycle
from dialectical_framework.ai_structured_data.causal_cycles_deck import CausalCyclesDeck
from dialectical_framework.analyst.reverse_engineer import ReverseEngineer
from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder, CausalityType
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain, HasBrain
from dialectical_framework.wisdom_unit import WisdomUnit


class ThoughtMapper(HasBrain):
    def __init__(
        self,
        text: str,
        *,
        config: ConfigWheelBuilder = None,
    ):
        self.__text = text
        self.__config = ConfigWheelBuilder() if config is None else config

    @property
    def brain(self):
        return self.__config.brain

    # TODO: this is duplication with dialectical_reasoner.py, refactor
    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        Extract the central idea or the primary thesis (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

        <formatting>
        Output the dialectical component T within {component_length} word(s), the shorter, the better. The explanation how it was derived in the passive voice. Don't mention any special denotations (such as "T") in the statements nor explanations.
        </formatting> 
        """
    )
    def prompt_thesis1(self, text: str, component_length: int) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        In the given context, identify the most important 2 theses (concepts, ideas, elements, steps), T1 and T2, that form the most essential circular causation: T1 → T2 → T1...
        
        <formatting>
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations (such as "T", "T1", "T+", "A-", "Ac", "Re", etc) in statements nor explanations.
        </formatting>
        
        2 theses labeled T1 and T2 are obligatory. No more, no less.
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
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations (such as "T", "T1", "T+", "A-", "Ac", "Re", etc.) in statements nor explanations.
        </formatting> 
        
        3 theses labeled T1, T2, and T3 are obligatory. No more, no less.
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
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations (such as "T", "T1", "T+", "A-", "Ac", "Re", etc.) in statements nor explanations.
        </formatting> 
        
        4 theses labeled as T1, T2, T3, and T4 are obligatory. No more, no less.
        """
    )
    def prompt_thesis4(self, text, component_length: int) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences is the most realistic, i.e. what typically happens in natural systems (given that the final step cycles back to the first step):
        {sequences:list}
        
        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) regarding its realistic existence in natural/existing systems
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful
        </instructions>
        
        <formatting>
        Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
        However, in the explanations don't use these technical placeholders. Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_sequencing_realistic(self, sequences: List[str]) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences is the most desirable, i.e. would produce optimal outcomes and maximum results (given that the final step cycles back to the first step):
        {sequences:list}
    
        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) regarding how beneficial/optimal this sequence would be if implemented
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful
        </instructions>
    
        <formatting>
        Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
        However, in the explanations don't use these technical placeholders. Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_sequencing_desirable(self, sequences: List[str]) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences is the most feasible, i.e. best achievable with minimum resistance (given that the final step cycles back to the first step):
        {sequences:list}
        
        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) regarding how easily this sequence could be implemented given current constraints
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful
        </instructions>

        <formatting>
        Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
        However, in the explanations don't use these technical placeholders. Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_sequencing_feasible(self, sequences: List[str]) -> Messages.Type: ...

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
        </instructions>

        <formatting>
        Output the cycle as aliases (technical placeholders) of statements as provided e.g. T, T1, A2, etc.
        However, in the explanations don't use these technical placeholders. Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_sequencing_balanced(self, sequences: List[str]) -> Messages.Type: ...

    @with_langfuse()
    async def find_theses(self, count: int = 1) -> DialecticalComponentsDeck:
        @use_brain(brain=self.__config.brain, response_model=DialecticalComponent)
        async def _find_single_thesis():
            return self.prompt_thesis1(text=self.__text, component_length=self.__config.component_length)

        @use_brain(brain=self.__config.brain, response_model=DialecticalComponentsDeck)
        async def _find_multiple_theses():
            if count == 2:
                return self.prompt_thesis2(text=self.__text, component_length=self.__config.component_length)
            elif count == 3:
                return self.prompt_thesis3(text=self.__text, component_length=self.__config.component_length)
            elif count == 4:
                return self.prompt_thesis4(text=self.__text, component_length=self.__config.component_length)
            else:
                raise ValueError(f"Count {count} is not supported here.")

        if count <= 1:
            box = DialecticalComponentsDeck(dialectical_components=[await _find_single_thesis()])
        elif count <= 4:
            box = await _find_multiple_theses()
        else:
            raise ValueError(f"More than 4 theses are not supported yet.")
        return box

    async def find_t_cycles(self, theses: DialecticalComponentsDeck) -> CausalCyclesDeck:
        # To avoid hallucinations, make all alias uniform so that AI doesn't try to guess
        alias_translations: dict[str, str] = {}
        for i, dc in enumerate(theses.dialectical_components, 1):
            alias_translations[f"S{i}"] = dc.alias
            dc.alias = f"S{i}"

        sequences = theses.get_cycles_str()

        # Add statements to sequences, for more clarity
        for i, seq in enumerate(sequences):
            as_is_seq = seq
            for a in alias_translations:
                as_is_seq = dc_replace(as_is_seq, a, theses.get_by_alias(a).statement)
            sequences[i] = f"{seq} ({as_is_seq})"

        result = await self._find_cycles(sequences=sequences, dialectical_components=theses.dialectical_components)

        # Translate aliases back in the parameter
        for dc in theses.dialectical_components:
            dc.alias = alias_translations[dc.alias]

        # Translate back the aliases in the result
        for causal_cycle in result.causal_cycles:
            for a in causal_cycle.aliases:
                # Normally technical aliases aren't mentioned in the texts, but who knows... let's blindly translate back
                causal_cycle.reasoning_explanation = dc_replace(causal_cycle.reasoning_explanation, a, alias_translations[a])
                causal_cycle.argumentation = dc_replace(causal_cycle.argumentation, a, alias_translations[a])
            causal_cycle.aliases = [alias_translations[alias] for alias in causal_cycle.aliases]

        return result

    async def find_ta_cycles(self, ordered_wisdom_units: List[WisdomUnit]) -> CausalCyclesDeck:
        dialectical_components = []

        # To avoid hallucinations, make all alias uniform so that AI doesn't try to guess
        alias_translations: dict[str, str] = {}
        for i, wu in enumerate(ordered_wisdom_units, 1):
            alias_translations[f"S{i}"] = wu.t.alias
            alias_translations[f"S{i + len(ordered_wisdom_units)}"] = wu.a.alias
            wu.t.alias = f"S{i}"
            wu.a.alias = f"S{i + len(ordered_wisdom_units)}"
            dialectical_components.extend([wu.t, wu.a])

        theses = DialecticalComponentsDeck(dialectical_components=dialectical_components)
        if len(ordered_wisdom_units) == 1:  # degenerate 1-node cycle
            sequences = [f"{ordered_wisdom_units[0].t.alias} → {ordered_wisdom_units[0].a.alias} → {ordered_wisdom_units[0].t.alias}..."]
        else:
            # Produce all valid diagonal sequences
            raw_sequences = _generate_compatible_sequences(ordered_wisdom_units)

            # Human-friendly formatting
            sequences = list(
                " → ".join(seq + [seq[0]]) + "..." for seq in raw_sequences
            )

        # Add statements to sequences, for more clarity
        for i, seq in enumerate(sequences):
            as_is_seq = seq
            for a in alias_translations:
                as_is_seq = dc_replace(as_is_seq, a, theses.get_by_alias(a).statement)
            sequences[i] = f"{seq} ({as_is_seq})"


        result = await self._find_cycles(sequences=sequences, dialectical_components=theses.dialectical_components)

        # Translate aliases back in the parameter
        for wu in ordered_wisdom_units:
            wu.t.alias = alias_translations[wu.t.alias]
            wu.a.alias = alias_translations[wu.a.alias]

        # Translate back the aliases in the result
        for causal_cycle in result.causal_cycles:
            for a in causal_cycle.aliases:
                # Normally technical aliases aren't mentioned in the texts, but who knows... let's blindly translate back
                causal_cycle.reasoning_explanation = dc_replace(causal_cycle.reasoning_explanation, a, alias_translations[a])
                causal_cycle.argumentation = dc_replace(causal_cycle.argumentation, a, alias_translations[a])
            causal_cycle.aliases = [alias_translations[alias] for alias in causal_cycle.aliases]

        return result

    @with_langfuse()
    @use_brain(response_model=CausalCyclesDeck)
    async def _find_cycles(self, sequences: List[str], dialectical_components: List[DialecticalComponent]) -> CausalCyclesDeck:
        if self.__config.causality_type == CausalityType.REALISTIC:
            prompt = self.prompt_sequencing_realistic(sequences=sequences)
        elif self.__config.causality_type == CausalityType.DESIRABLE:
            prompt = self.prompt_sequencing_desirable(sequences=sequences)
        elif self.__config.causality_type == CausalityType.FEASIBLE:
            prompt = self.prompt_sequencing_feasible(sequences=sequences)
        else:
            prompt = self.prompt_sequencing_balanced(sequences=sequences)

        tpl = ReverseEngineer.till_theses(theses=dialectical_components, text=self.__text)

        return extend_tpl(tpl, prompt)

    async def map(self, thoughts: int = 2) -> List[Cycle]:
        if thoughts == 1:
            return [Cycle(
                dialectical_components=(await self.find_theses()).dialectical_components,
                causality_type=self.__config.causality_type,
                probability=1.0
            )]
        else:
            box = await self.find_theses(count=thoughts)


        causal_cycles_box = await self.find_t_cycles(theses=box)
        cycles: list[Cycle] = []
        for causal_cycle in causal_cycles_box.causal_cycles:
            cycles.append(Cycle(dialectical_components=box.sort_by_example(causal_cycle.aliases),
                                causality_type=self.__config.causality_type,
                                probability=causal_cycle.probability,
                                reasoning_explanation=causal_cycle.reasoning_explanation,
                                argumentation=causal_cycle.argumentation))
        cycles.sort(key=lambda c: c.probability, reverse=True)
        return cycles

    @overload
    async def arrange(self, thoughts: List[str]) -> List[Cycle]: ...


    @overload
    async def arrange(self, thoughts: List[WisdomUnit]) -> List[Cycle]: ...


    async def arrange(self, thoughts: Union[List[str], List[WisdomUnit], List[DialecticalComponent]]) -> List[Cycle]:
        if thoughts and isinstance(thoughts[0], WisdomUnit):
            ordered_wisdom_units: List[WisdomUnit] = thoughts
            if len(thoughts) == 1:
                return [Cycle(dialectical_components=[
                    ordered_wisdom_units[0].t,
                    ordered_wisdom_units[0].a,
                ], probability=1.0, causality_type=self.__config.causality_type)]
            elif len(thoughts) == 2:
                box = DialecticalComponentsDeck(dialectical_components=[
                    ordered_wisdom_units[0].t,
                    ordered_wisdom_units[1].t,
                    ordered_wisdom_units[0].a,
                    ordered_wisdom_units[1].a,
                ])
            elif len(thoughts) == 3:
                box = DialecticalComponentsDeck(dialectical_components=[
                    ordered_wisdom_units[0].t,
                    ordered_wisdom_units[1].t,
                    ordered_wisdom_units[2].t,
                    ordered_wisdom_units[0].a,
                    ordered_wisdom_units[1].a,
                    ordered_wisdom_units[2].a,
                ])
            elif len(thoughts) == 4:
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

            causal_cycles_box = await self.find_ta_cycles(ordered_wisdom_units=ordered_wisdom_units)
        else:
            if len(thoughts) == 1:
                if thoughts and isinstance(thoughts[0], DialecticalComponent):
                    return [Cycle(
                        dialectical_components=thoughts,
                        probability=1.0,
                        causality_type=self.__config.causality_type,
                    )]
                else:
                    return [Cycle(
                        dialectical_components=[
                            DialecticalComponent.from_str(alias="T", statement=thoughts[0], explanation=thoughts[0])
                        ],
                        probability=1.0,
                        causality_type=self.__config.causality_type,
                    )]
            elif len(thoughts) <= 4:
                if thoughts and isinstance(thoughts[0], DialecticalComponent):
                    box = DialecticalComponentsDeck(dialectical_components=thoughts)
                else:
                    box = DialecticalComponentsDeck(dialectical_components=[
                        DialecticalComponent.from_str(alias=f"T{i + 1}", statement=t, explanation="Provided as string.")
                        for i, t in enumerate(thoughts)
                    ])
            else:
                raise ValueError(f"More than 4 thoughts are not supported yet.")

            causal_cycles_box = await self.find_t_cycles(theses=box)

        cycles: list[Cycle] = []
        for causal_cycle in causal_cycles_box.causal_cycles:
            cycles.append(Cycle(dialectical_components=box.sort_by_example(causal_cycle.aliases),
                                causality_type=self.__config.causality_type,
                                probability=causal_cycle.probability,
                                reasoning_explanation=causal_cycle.reasoning_explanation,
                                argumentation=causal_cycle.argumentation))
        cycles.sort(key=lambda c: c.probability, reverse=True)
        return cycles

def _generate_compatible_sequences(ordered_wisdom_units) -> List[List[str]]:
    """
    Generate all circular, diagonally symmetric arrangements for T/A pairs.

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
            [T1, T2, A4, T3, A1, A2, T4, A3]
        Which means:
            Top:    T1 -> T2 -> A4 -> T3
            Bottom: A1 -> A2 -> T4 -> A3 (mirrored on the circle)
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
        # Skip positions already assigned (to ensure symmetry and distinctness)
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