from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from mirascope import BaseMessageParam, Messages, prompt_template

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.utils.extend_tpl import extend_tpl

# Graph-native imports
if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.relationship_manager import BoundRelationshipManager

from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship


def _get_component_info(manager: BoundRelationshipManager[DialecticalComponent], position_name: str) -> tuple[str, str, str]:
    """
    Extract component information from a relationship manager.

    Returns:
        (alias, statement, rationale_text) tuple
    """
    result = manager.get()
    if not result:
        return position_name, "N/A", "N/A"

    component, rel = result

    # Get alias from relationship edge
    alias = position_name  # Default
    if isinstance(rel, PolarityRelationship):
        alias = rel.alias

    # Get statement from a component
    statement = component.statement

    # Get rationale from a component
    rationale = component.best_rationale
    rationale_text = rationale.text if rationale else "N/A"

    return alias, statement, rationale_text


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
    def prompt_input_text(self, *, text: str) -> "Messages.Type": ...

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
        self, *, dialectical_components: list[list[str]]
    ) -> "Messages.Type": ...

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
    ) -> "Messages.Type": ...

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
        theses: list[list[str]],
        wisdom_units: list[list[str]],
    ) -> "Messages.Type": ...

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
    ) -> "Messages.Type": ...

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
    ) -> "Messages.Type": ...

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
    ) -> "Messages.Type": ...

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
    ) -> "Messages.Type": ...

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
    ) -> "Messages.Type": ...

    @staticmethod
    def till_theses(
        theses: list[DialecticalComponentDto], text: str = None
    ) -> list[BaseMessageParam]:
        """
        Build prompt template up to thesis introduction.

        Args:
            theses: List of DialecticalComponentDto objects (DTOs used because this
                   builds prompts for AI boundary - DTOs have exact structure needed)
            text: Optional context text

        Returns:
            List of message parameters for prompt template

        Note:
            Uses DTOs (not graph-native) because:
            - This method builds prompts for AI calls (at AI boundary)
            - DTOs have exact structure needed: alias, statement, explanation
            - Graph-native components don't have .alias as direct property
        """
        reverse_engineer = ReverseEngineer()
        tpl: list[BaseMessageParam] = []

        if text:
            # Convert "Messages.Type" to list and extend instead of append
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
            # Convert "Messages.Type" to list and extend instead of append
            input_messages = reverse_engineer.prompt_input_text(text=text)
            extend_tpl(tpl, input_messages)

        wus: Dict[DialecticalReasoningMode, list[WisdomUnit]] = (
            _wisdom_units_grouped_by_reasoning_mode(wisdom_units)
        )
        for mode, wisdom_units in wus.items():
            # Extract component info for all WUs using graph-native helper
            theses = []
            wu_lists = []

            for index, wu in enumerate(wisdom_units):
                # Get T component info
                t_alias, t_statement, t_rationale = _get_component_info(wu.t, 'T')

                theses.append([
                    f"### Thesis {index + 1} ({t_alias})",
                    f"Alias: {t_alias}",
                    f"Statement: {t_statement}",
                    f"Explanation: {t_rationale}",
                ])

                # Get all component info for this WU
                a_alias, a_statement, a_rationale = _get_component_info(wu.a, 'A')
                tm_alias, tm_statement, tm_rationale = _get_component_info(wu.t_minus, 'T-')
                tp_alias, tp_statement, tp_rationale = _get_component_info(wu.t_plus, 'T+')
                ap_alias, ap_statement, ap_rationale = _get_component_info(wu.a_plus, 'A+')
                am_alias, am_statement, am_rationale = _get_component_info(wu.a_minus, 'A-')

                wu_lists.append([
                    f"### Wisdom Unit for {t_alias}",
                    f"{t_alias} = {t_statement}",
                    f"{a_alias} = {a_statement}",
                    f"{a_alias} explanation: {a_rationale}",
                    f"{tm_alias} = {tm_statement}",
                    f"{tm_alias} explanation: {tm_rationale}",
                    f"{tp_alias} = {tp_statement}",
                    f"{tp_alias} explanation: {tp_rationale}",
                    f"{ap_alias} = {ap_statement}",
                    f"{ap_alias} explanation: {ap_rationale}",
                    f"{am_alias} = {am_statement}",
                    f"{am_alias} explanation: {am_rationale}",
                ])

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
            str(t_cycle): [
                f"### {t_cycle.causality_type.value.capitalize()} Causality Estimation for {t_cycle}",
                f"Probability: {t_cycle.relevance}",  # Note that it's the initial assessment that we take, not normalized
                f"Rationale: {t_cycle.best_rationale.text if t_cycle.best_rationale and t_cycle.best_rationale.text else 'N/A'}",
            ],
        }
        if ta_cycle:
            cycles[str(ta_cycle)] = [
                f"### {ta_cycle.causality_type.value.capitalize()} Causality Estimation for {ta_cycle}",
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
        # Get cycles from wheel (graph-native returns tuples from .get())
        t_cycle_result = wheel.t_cycle.get()
        ta_cycle_result = wheel.ta_cycle.get()

        t_cycle = t_cycle_result[0] if t_cycle_result else None
        ta_cycle = ta_cycle_result[0] if ta_cycle_result else None

        # Get wisdom units list
        wisdom_units_list = [wu for wu, _ in wheel.wisdom_units.all()]

        return ReverseEngineer.till_cycle(
            wisdom_units_list, t_cycle, ta_cycle, text
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
