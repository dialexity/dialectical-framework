from typing import List, overload, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from mirascope import prompt_template, Messages
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_structured_data.causal_cycles_deck import CausalCyclesDeck
from dialectical_framework.brain import Brain
from dialectical_framework.config import Config
from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.enums.di import DI
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.wisdom_unit import WisdomUnit


class ConceptExtractor(HasBrain):
    @inject
    def __init__(
        self,
        config: Config = Provide[DI.config],
        *,
        text: str = "",
    ):
        self.__text = text
        self.__config = config

    @property
    def config(self) -> Config:
        return self.__config

    @property
    def text(self) -> str:
        return self.__text

    @text.setter
    def text(self, value: str):
        self.__text = value

    @prompt_template(
        """
        USER:
        <context>{text}</context>
        
        USER:
        For the given context extract **{count}** distinct, essential **concepts** that best capture the core dynamics of the text.

        **For strategic/philosophical texts, focus on:**
        - Big-picture or recurring ideas that reflect the **essence** of the content
        - **Abstract or strategic drivers** of the text  
        - Terms that **structure the argument** or explain system-level dynamics
    
        **For technical/operational texts, focus on:**
        - **Process stages, steps, or functional components** that form the system
        - **Sequential elements** that flow into or cause each other
        - **Operational phases** or mechanisms that drive the system forward
    
        **Guidelines:**
        - Let the content guide whether to extract high-level themes or operational stages
        - If the text describes processes/systems, identify functional components
        - If the text presents arguments/strategies, identify conceptual themes
        - Aim for concepts that are **interdependent** and form a coherent framework

        **Output Format:**
        T1 = [concept in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]
        
        T2 = [concept in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]
        
        ...
        
        Tx = [concept in 1-{component_length} words]
        Explanation: [The explanation how it was derived in the passive voice]
        """
    )
    def prompt_theses(self, count: int, text: str, component_length: int) -> Messages.Type: ...

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
        
        Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>
        
        
        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
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
        
        Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>
    
        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
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
        
        Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>

        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
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
        
        - Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>

        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_sequencing_balanced(self, sequences: List[str]) -> Messages.Type: ...

    async def find_theses(self, count: int = 1) -> DialecticalComponentsDeck:
        if count > 4 or count < 1:
            raise ValueError(f"Incorrect number of theses requested. Max 4 theses are supported.")

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=DialecticalComponentsDeck)
        async def _find_theses():
            return self.prompt_theses(text=self.__text, count=count, component_length=self.config.component_length)

        if count <= 4:
            box = await _find_theses()
            if count == 1 and len(box.dialectical_components) == 1:
                dc: DialecticalComponent = box.dialectical_components[0]
                dc.set_human_friendly_index(0)
        else:
            raise ValueError(f"More than 4 theses are not supported yet.")
        return box

    async def find_t_cycles(self, theses: DialecticalComponentsDeck) -> CausalCyclesDeck:
        # To avoid hallucinations, make all alias uniform so that AI doesn't try to guess where's a thesis or antithesis
        alias_translations: dict[str, str] = {}
        for i, dc in enumerate(theses.dialectical_components, 1):
            alias_translations[f"C{i}"] = dc.alias
            dc.alias = f"C{i}"

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
        # First add all theses
        for i, wu in enumerate(ordered_wisdom_units, 1):
            alias_translations[f"C{i}"] = wu.t.alias
            wu.t.alias = f"C{i}"
            dialectical_components.append(wu.t)

        # Then add all antitheses
        for i, wu in enumerate(ordered_wisdom_units, 1):
            alias_translations[f"C{i + len(ordered_wisdom_units)}"] = wu.a.alias
            wu.a.alias = f"C{i + len(ordered_wisdom_units)}"
            dialectical_components.append(wu.a)

        theses = DialecticalComponentsDeck(dialectical_components=dialectical_components)
        if len(ordered_wisdom_units) == 1:  # degenerate 1-node cycle
            sequences = [
                f"{ordered_wisdom_units[0].t.alias} → {ordered_wisdom_units[0].a.alias} → {ordered_wisdom_units[0].t.alias}..."]
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
        if self.config.causality_type == CausalityType.REALISTIC:
            prompt = self.prompt_sequencing_realistic(sequences=sequences)
        elif self.config.causality_type == CausalityType.DESIRABLE:
            prompt = self.prompt_sequencing_desirable(sequences=sequences)
        elif self.config.causality_type == CausalityType.FEASIBLE:
            prompt = self.prompt_sequencing_feasible(sequences=sequences)
        else:
            prompt = self.prompt_sequencing_balanced(sequences=sequences)

        tpl = ReverseEngineer.till_theses(theses=dialectical_components, text=self.__text)

        return extend_tpl(tpl, prompt)

    async def map(self, thoughts: int = 2) -> List[Cycle]:
        if thoughts == 1:
            return [Cycle(
                dialectical_components=(await self.find_theses()).dialectical_components,
                causality_type=self.config.causality_type,
                probability=1.0
            )]
        else:
            box = await self.find_theses(count=thoughts)


        causal_cycles_box = await self.find_t_cycles(theses=box)
        cycles: list[Cycle] = []
        for causal_cycle in causal_cycles_box.causal_cycles:
            cycles.append(Cycle(dialectical_components=box.sort_by_example(causal_cycle.aliases),
                                causality_type=self.config.causality_type,
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
                ], probability=1.0, causality_type=self.config.causality_type)]
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
                        causality_type=self.config.causality_type,
                    )]
                else:
                    return [Cycle(
                        dialectical_components=[
                            DialecticalComponent(alias="T", statement=thoughts[0], explanation=thoughts[0])
                        ],
                        probability=1.0,
                        causality_type=self.config.causality_type,
                    )]
            elif len(thoughts) <= 4:
                if thoughts and isinstance(thoughts[0], DialecticalComponent):
                    box = DialecticalComponentsDeck(dialectical_components=thoughts)
                else:
                    box = DialecticalComponentsDeck(dialectical_components=[
                        DialecticalComponent(alias=f"T{i + 1}", statement=t, explanation="Provided as string.")
                        for i, t in enumerate(thoughts)
                    ])
            else:
                raise ValueError(f"More than 4 thoughts are not supported yet.")

            causal_cycles_box = await self.find_t_cycles(theses=box)

        cycles: list[Cycle] = []
        for causal_cycle in causal_cycles_box.causal_cycles:
            cycles.append(Cycle(dialectical_components=box.sort_by_example(causal_cycle.aliases),
                                causality_type=self.config.causality_type,
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