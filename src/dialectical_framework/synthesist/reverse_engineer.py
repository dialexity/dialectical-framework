from typing import Dict, List

from mirascope import BaseMessageParam, Messages, prompt_template

from dialectical_framework import Transition
from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.synthesist.domain.wheel import Wheel
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


# TODO: reuse the prompts from the reasoners?
class ReverseEngineer:
    @prompt_template(
        """
        USER:
        Consider the following text as the initial context for further analysis:
        
        <context>{text}</context>
        
        ASSISTANT:
        OK, let's start.
        """
    )
    def prompt_input_text(self, *, text: str) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Consider these statements:
        
        {dialectical_components:lists}

        ASSISTANT:
        OK, let's proceed.
        """
    )
    def prompt_input_theses(
        self, *, dialectical_components: list[List:str]
    ) -> Messages.Type: ...

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
    def prompt_dialectical_reasoner_find_thesis(
        self, *, thesis: str, explanation: str, denotation: str = "T"
    ) -> Messages.Type: ...

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
        self,
        *,
        reasoning_mode: str,
        theses: list[List:str],
        wisdom_units: list[list[str]],
    ) -> Messages.Type: ...

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
        self,
        *,
        reasoning_mode: str,
        theses: list[list[str]],
        wisdom_units: list[list[str]],
    ) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Consider the following circular causality sequences of dialectical components:
        {sequences:list}
        
        <instructions>
        Estimate how realistic is each sequence, i.e. what typically happens in natural systems (given that the final step cycles back to the first step):
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
    def prompt_cycle__realistic(
        self, sequences: list[str], estimations: list[list[str]]
    ) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Consider the following circular causality sequences of dialectical components:
        {sequences:list}

        <instructions>
        Estimate how desirable is each sequence, i.e. would produce optimal outcomes and maximum results (given that the final step cycles back to the first step):
        1) Estimate the numeric probability (0 to 1) regarding how beneficial/optimal this sequence would be if implemented
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
    def prompt_cycle__desirable(
        self, sequences: list[str], estimations: list[list[str]]
    ) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Consider the following circular causality sequences of dialectical components:
        {sequences:list}

        <instructions>
        Estimate how feasible is each sequence, i.e. best achievable with minimum resistance (given that the final step cycles back to the first step):
        1) Estimate the numeric probability (0 to 1) regarding how easily this sequence could be implemented given current constraints
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
    def prompt_cycle__feasible(
        self, sequences: list[str], estimations: list[list[str]]
    ) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Consider the following circular causality sequences of dialectical components:
        {sequences:list}

        <instructions>
        Estimate how balanced is each sequence, i.e. provides the best balanced assessment considering realism, desirability, and feasibility (given that the final step cycles back to the first step):
        1) Estimate the numeric probability (0 to 1) as a balanced assessment considering realistic existence, optimal outcomes, and implementation feasibility
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
    def prompt_cycle__balanced(
        self, sequences: list[str], estimations: list[list[str]]
    ) -> Messages.Type: ...

    @staticmethod
    def till_theses(
        theses: list[DialecticalComponent], text: str = None
    ) -> list[BaseMessageParam]:
        reverse_engineer = ReverseEngineer()
        tpl: list[BaseMessageParam] = []

        if text:
            # Convert Messages.Type to list and extend instead of append
            input_messages = reverse_engineer.prompt_input_text(text=text)
            extend_tpl(tpl, input_messages)

        theses = [
            [
                f"### Concept/Statement {index + 1} ({dc.alias})",
                f"Alias: {dc.alias}",
                f"Statement: {dc.statement}",
                # Don't render explanations here, as these might be referring to other places in the wisdom unit,
                # which might be confusing or even misleading in further prompt
            ]
            for index, dc in enumerate(theses)
        ]

        dc_messages = reverse_engineer.prompt_input_theses(
            dialectical_components=theses
        )
        extend_tpl(tpl, dc_messages)

        return tpl

    @staticmethod
    def till_wisdom_units(
        wisdom_units: list[WisdomUnit], text: str = None
    ) -> list[BaseMessageParam]:
        reverse_engineer = ReverseEngineer()
        tpl: list[BaseMessageParam] = []

        if text:
            # Convert Messages.Type to list and extend instead of append
            input_messages = reverse_engineer.prompt_input_text(text=text)
            extend_tpl(tpl, input_messages)

        wus: Dict[DialecticalReasoningMode, list[WisdomUnit]] = (
            _wisdom_units_grouped_by_reasoning_mode(wisdom_units)
        )
        for mode, wisdom_units in wus.items():
            theses = [
                [
                    f"### Thesis {index + 1} ({wu.t.alias})",
                    f"Alias: {wu.t.alias}",
                    f"Statement: {wu.t.statement}",
                    f"Explanation: {wu.t.best_rationale.text if wu.t.best_rationale else 'N/A'}",
                ]
                for index, wu in enumerate(wisdom_units)
            ]
            wu_lists = [
                [
                    f"### Wisdom Unit for {wu.t.alias}",
                    f"{wu.t.alias} = {wu.t.statement}",
                    f"{wu.a.alias} = {wu.a.statement}",
                    f"{wu.a.alias} explanation: {wu.a.best_rationale.text if wu.a.best_rationale else 'N/A'}",
                    f"{wu.t_minus.alias} = {wu.t_minus.statement}",
                    f"{wu.t_minus.alias} explanation: {wu.t_minus.best_rationale.text if wu.t_minus.best_rationale else 'N/A'}",
                    f"{wu.t_plus.alias} = {wu.t_plus.statement}",
                    f"{wu.t_plus.alias} explanation: {wu.t_plus.best_rationale.text if wu.t_plus.best_rationale else 'N/A'}",
                    f"{wu.a_plus.alias} = {wu.a_plus.statement}",
                    f"{wu.a_plus.alias} explanation: {wu.a_plus.best_rationale.text if wu.a_plus.best_rationale else 'N/A'}",
                    f"{wu.a_minus.alias} = {wu.a_minus.statement}",
                    f"{wu.a_minus.alias} explanation: {wu.a_minus.best_rationale.text if wu.a_minus.best_rationale else 'N/A'}",
                ]
                for wu in wisdom_units
            ]

            if mode == DialecticalReasoningMode.MAJOR_TENSION:
                wu_messages = reverse_engineer.prompt_find_wisdom_units__major_tension(
                    reasoning_mode=DialecticalReasoningMode.MAJOR_TENSION.value,
                    theses=theses,
                    wisdom_units=wu_lists,
                )
            else:
                wu_messages = (
                    reverse_engineer.prompt_find_wisdom_units__general_concepts(
                        reasoning_mode=DialecticalReasoningMode.GENERAL_CONCEPTS.value,
                        theses=theses,
                        wisdom_units=wu_lists,
                    )
                )

            extend_tpl(tpl, wu_messages)

        return tpl

    @staticmethod
    def till_cycle(
        wisdom_units: list[WisdomUnit],
        t_cycle: Cycle,
        ta_cycle: Cycle = None,
        text: str = None,
    ) -> list[BaseMessageParam]:
        reverse_engineer = ReverseEngineer()
        tpl: list[BaseMessageParam] = ReverseEngineer.till_wisdom_units(
            wisdom_units, text
        )

        cycles = {
            t_cycle.cycle_str(): [
                f"### {t_cycle.causality_type.value.capitalize()} Causality Estimation for {t_cycle.cycle_str()}",
                f"Probability: {t_cycle.relevance}",  # Note that it's the initial assessment that we take, not normalized
                f"Rationale: {t_cycle.best_rationale.text if t_cycle.best_rationale and t_cycle.best_rationale.text else 'N/A'}",
            ],
        }
        if ta_cycle:
            cycles[ta_cycle.cycle_str()] = [
                f"### {ta_cycle.causality_type.value.capitalize()} Causality Estimation for {ta_cycle.cycle_str()}",
                f"Probability: {ta_cycle.relevance}", # Note that it's the initial assessment that we take, not normalized
                f"Rationale: {ta_cycle.best_rationale.text if ta_cycle.best_rationale and ta_cycle.best_rationale.text else 'N/A'}",
            ]

        if t_cycle.causality_type == CausalityType.REALISTIC:
            cycle_messages = reverse_engineer.prompt_cycle__realistic(
                sequences=list(cycles.keys()),
                estimations=list(cycles.values()),
            )
        elif t_cycle.causality_type == CausalityType.DESIRABLE:
            cycle_messages = reverse_engineer.prompt_cycle__desirable(
                sequences=list(cycles.keys()),
                estimations=list(cycles.values()),
            )
        elif t_cycle.causality_type == CausalityType.FEASIBLE:
            cycle_messages = reverse_engineer.prompt_cycle__feasible(
                sequences=list(cycles.keys()),
                estimations=list(cycles.values()),
            )
        else:
            cycle_messages = reverse_engineer.prompt_cycle__balanced(
                sequences=list(cycles.keys()),
                estimations=list(cycles.values()),
            )

        extend_tpl(tpl, cycle_messages)

        return tpl

    @staticmethod
    def till_wheel_without_convergent_transitions(wheel: Wheel, text: str = None) -> list[BaseMessageParam]:
        return ReverseEngineer.till_cycle(
            wheel.wisdom_units, wheel.t_cycle, wheel.cycle, text
        )


def _wisdom_units_grouped_by_reasoning_mode(
    wisdom_units: list[WisdomUnit],
) -> Dict[DialecticalReasoningMode, list[WisdomUnit]]:
    grouped_units = {}
    for wu in wisdom_units:
        if wu.reasoning_mode not in grouped_units:
            grouped_units[wu.reasoning_mode] = []
        grouped_units[wu.reasoning_mode].append(wu)
    return grouped_units
