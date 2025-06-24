from typing import List, Dict

from mirascope import Messages, prompt_template, BaseMessageParam

from dialectical_framework.wheel import Wheel
from dialectical_framework.wisdom_unit import WisdomUnit, DialecticalReasoningMode


class ReverseEngineering:
    @prompt_template(
        """
        USER:
        Consider the following text as the initial context for further analysis analysis:
        
        <context>{text}</context>
        
        ASSISTANT:
        OK, let's start.
        """
    )
    def prompt_input_text(self, *, text: str) -> Messages.Type:
        ...

    @prompt_template(
        """
        USER:
        Extract the central idea or the primary thesis (denote it as {denotation}) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

        <formatting>
        Output the dialectical component {denotation} and explanation how it was derived in the passive voice.
        </formatting>

        ASSISTANT:
        ## Dialectical Component:
        Alias = {denotation}
        Statement = {thesis}
        Explanation: {explanation}
        """
    )
    def prompt_dialectical_reasoner_find_thesis(self, *, thesis: str, explanation: str,
                                                denotation: str = "T") -> Messages.Type:
        ...

    @prompt_template(
        """
        USER:
        Consider these theses:
        {theses:lists}
        
        USER:
        ## Dialectical Analysis (Reasoning Mode: {reasoning_mode})
        <instructions>
        For every thesis (T), identify its semantic/functional antithesis (A), such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+). 

        For example:
        T = Love
        T+ = Happiness (positive aspect of Love)
        T- = Fixation (negative aspect of Love)
        A = Indifference (antithesis of Love)
        A+ = Objectivity (positive aspect of Indifference, contradicts Fixation)
        A- = Misery (negative aspect of Indifference, contradicts Happiness).

        Compose the explanations how each dialectical component was derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", etc.
        </instructions>
        
        ASSISTANT:
        ## Wisdom Units:
        {wisdom_units:lists}
        """
    )
    def prompt_find_wisdom_units__general_concepts(
            self, *,
            reasoning_mode: str, theses: List[List:str], wisdom_units: List[List[str]]) -> Messages.Type:
        ...

    @prompt_template(
        """
        USER:
        Consider these theses:
        {theses:lists}

        USER:
        ## Dialectical Analysis (Reasoning Mode: {reasoning_mode})}
        <instructions>
        For very thesis (T), frame the problem as a tension between two opposing approaches:
        - Thesis (T): The first approach or position
        - Antithesis (A): The contrasting approach or position
    
        T and A must be such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+).
            
        For example:
        In a token vesting dispute, stakeholders disagreed about extending the lock period from January 2025 to January 2026. The original solution was a staged distribution with incentives.
        
        T: Vest Now
        T+ = Trust Building
        T- = Loss of Value
        A: Vest Later
        A+ = Value Protection (contradicts T-)
        A- = Trust Erosion (contradicts T+) 
        </instructions>

        ASSISTANT:
        {wisdom_units:lists}
        """
    )
    def prompt_find_wisdom_units__major_tension(
            self, *, reasoning_mode: str, theses: List[List[str]], wisdom_units: List[List[str]]) -> Messages.Type:
        ...

    @prompt_template(
        """
        USER:
        Consider the following circular causality sequences of dialectical components:
        {sequences:list}
        
        <instructions>
        Estimate how realistic is each sequence, i.e. what typically happens in natural systems, (given that the final step cycles back to the first step):
        1) Estimate the numeric probability (0 to 1) regarding its realistic existence in natural/existing systems
        1) Explain why this sequence might occur in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful
        </instructions>
        <formatting>
        Probability is a float between 0 and 1.
        In the explanations don't use these technical placeholders. 
        </formatting>
        
        ASSISTANT:
        {estimations:lists}
        """
    )
    def prompt_cycle_realistic(self, sequences: List[str], estimations: List[List[str]]) -> Messages.Type:
        ...

    @staticmethod
    def wheel(wheel: Wheel, text: str = None) -> list[BaseMessageParam]:
        reverse_engineering = ReverseEngineering()
        tpl: list[BaseMessageParam] = []
        
        if text:
            # Convert Messages.Type to list and extend instead of append
            input_messages = reverse_engineering.prompt_input_text(text=text)
            if isinstance(input_messages, list):
                tpl.extend(input_messages)
            elif hasattr(input_messages, 'messages'):
                tpl.extend(input_messages.messages)
            else:
                tpl.append(input_messages)

        wus: Dict[DialecticalReasoningMode, List[WisdomUnit]] = wheel.wisdom_units_grouped_by_reasoning_mode
        for mode, wisdom_units in wus.items():
            theses = [
                [
                    f"### Thesis {index + 1} ({wu.t.alias})",
                    f"Alias: {wu.t.alias}",
                    f"Statement: {wu.t.statement}",
                    f"Explanation: {wu.t.explanation if wu.t.explanation else 'N/A'}"
                ] for index, wu in enumerate(wisdom_units)
            ]
            wu_lists = [
                [
                    f"### Wisdom Unit for {wu.t.alias}",

                    f"{wu.t.alias} = {wu.t.statement}",

                    f"{wu.a.alias} = {wu.a.statement}",
                    f"{wu.a.alias} explanation: {wu.a.explanation if wu.a.explanation else 'N/A'}",

                    f"{wu.t_minus.alias} = {wu.t_minus.statement}",
                    f"{wu.t_minus.alias} explanation: {wu.t_minus.explanation if wu.t_minus.explanation else 'N/A'}",

                    f"{wu.t_plus.alias} = {wu.t_plus.statement}",
                    f"{wu.t_plus.alias} explanation: {wu.t_plus.explanation if wu.t_plus.explanation else 'N/A'}",


                    f"{wu.a_plus.alias} = {wu.a_plus.statement}",
                    f"{wu.a_plus.alias} explanation: {wu.a_plus.explanation if wu.a_plus.explanation else 'N/A'}",

                    f"{wu.a_minus.alias} = {wu.a_minus.statement}",
                    f"{wu.a_minus.alias} explanation: {wu.a_minus.explanation if wu.a_minus.explanation else 'N/A'}",

                ] for wu in wisdom_units]

            if mode == DialecticalReasoningMode.MAJOR_TENSION:
                wu_messages = reverse_engineering.prompt_find_wisdom_units__major_tension(
                    reasoning_mode=DialecticalReasoningMode.MAJOR_TENSION.value,
                    theses=theses,
                    wisdom_units=wu_lists
                )
            else:
                wu_messages = reverse_engineering.prompt_find_wisdom_units__general_concepts(
                    reasoning_mode=DialecticalReasoningMode.GENERAL_CONCEPTS.value,
                    theses=theses,
                    wisdom_units=wu_lists
                )
            
            # Properly handle Messages.Type return
            if isinstance(wu_messages, list):
                tpl.extend(wu_messages)
            elif hasattr(wu_messages, 'messages'):
                tpl.extend(wu_messages.messages)
            else:
                tpl.append(wu_messages)

        cycles = {
            wheel.t_cycle.graph.pretty(wheel.main_wisdom_unit.t): [
                f"### Realistic Causality Estimation for {wheel.t_cycle.graph.pretty(wheel.main_wisdom_unit.t)}",
                f"Probability: {wheel.t_cycle.probability}",
                f"Explanation: {wheel.t_cycle.reasoning_explanation if wheel.t_cycle.reasoning_explanation else 'N/A'}",
                f"Argumentation: {wheel.t_cycle.argumentation if wheel.t_cycle.argumentation else 'N/A'}",
            ],
            wheel.cycle.graph.pretty(wheel.main_wisdom_unit.t): [
                f"### Realistic Causality Estimation for {wheel.cycle.graph.pretty(wheel.main_wisdom_unit.t)}",
                f"Probability: {wheel.cycle.probability}",
                f"Explanation: {wheel.cycle.reasoning_explanation if wheel.cycle.reasoning_explanation else 'N/A'}",
                f"Argumentation: {wheel.cycle.argumentation if wheel.cycle.argumentation else 'N/A'}",
            ],
        }
        
        cycle_messages = reverse_engineering.prompt_cycle_realistic(
            sequences=list(cycles.keys()),
            estimations=list(cycles.values()),
        )
        
        # Properly handle Messages.Type return for cycle messages
        if isinstance(cycle_messages, list):
            tpl.extend(cycle_messages)
        elif hasattr(cycle_messages, 'messages'):
            tpl.extend(cycle_messages.messages)
        else:
            tpl.append(cycle_messages)

        return tpl