from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from mirascope import BaseMessageParam, Messages, prompt_template

from dialectical_framework.ai_dto.statement_dto import \
    StatementDto
from dialectical_framework.utils.extend_tpl import extend_tpl

# Graph-native imports
if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.relationship_manager import BoundRelationshipManager

from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship


def _get_component_info(manager: BoundRelationshipManager[Statement], position_name: str) -> tuple[str, str, str]:
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
    statement = component.text

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
        
        {statements:lists}

        ASSISTANT:
        OK, let's proceed.
        """
    )
    def prompt_input_theses(
        self, *, statements: list[list[str]]
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
        ## Dialectical Analysis (Intent: {intent})
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
        ## Perspectives:
        {perspectives:lists}
        """
    )
    def prompt_find_perspectives__general_concepts(
        self,
        *,
        intent: str,
        theses: list[list[str]],
        perspectives: list[list[str]],
    ) -> "Messages.Type": ...

    @prompt_template(
        """
        USER:
        Consider these theses:
        {theses:lists}

        USER:
        ## Dialectical Analysis (Intent: {intent})}
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
        {perspectives:lists}
        """
    )
    def prompt_find_perspectives__major_tension(
        self,
        *,
        intent: str,
        theses: list[list[str]],
        perspectives: list[list[str]],
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
        theses: list[StatementDto], text: str = None
    ) -> list[BaseMessageParam]:
        """
        Build prompt template up to thesis introduction.

        Args:
            theses: List of StatementDto objects (DTOs used because this
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
                f"Statement: {dc.text}",
                # Don't render explanations here, as these might be referring to other places in the perspective,
                # which might be confusing or even misleading in further prompt
            ]
            for index, dc in enumerate(theses)
        ]

        dc_messages = reverse_engineer.prompt_input_theses(
            statements=theses
        )
        extend_tpl(tpl, dc_messages)

        return tpl

    @staticmethod
    def till_perspectives(
        perspectives: list[Perspective], text: str = None
    ) -> list[BaseMessageParam]:
        reverse_engineer = ReverseEngineer()
        tpl: list[BaseMessageParam] = []

        if text:
            # Convert "Messages.Type" to list and extend instead of append
            input_messages = reverse_engineer.prompt_input_text(text=text)
            extend_tpl(tpl, input_messages)

        pps: Dict[str, list[Perspective]] = (
            _perspectives_grouped_by_intent(perspectives)
        )
        for intent_mode, perspectives in pps.items():
            # Extract component info for all PPs using graph-native helper
            theses = []
            pp_lists = []

            for index, pp in enumerate(perspectives):
                # Get T component info
                t_alias, t_statement, t_rationale = _get_component_info(pp.t, 'T')

                theses.append([
                    f"### Thesis {index + 1} ({t_alias})",
                    f"Alias: {t_alias}",
                    f"Statement: {t_statement}",
                    f"Explanation: {t_rationale}",
                ])

                # Get all component info for this PP
                a_alias, a_statement, a_rationale = _get_component_info(pp.a, 'A')
                tm_alias, tm_statement, tm_rationale = _get_component_info(pp.t_minus, 'T-')
                tp_alias, tp_statement, tp_rationale = _get_component_info(pp.t_plus, 'T+')
                ap_alias, ap_statement, ap_rationale = _get_component_info(pp.a_plus, 'A+')
                am_alias, am_statement, am_rationale = _get_component_info(pp.a_minus, 'A-')

                pp_lists.append([
                    f"### Perspective for {t_alias}",
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

            if intent_mode == "major_tension":
                pp_messages = reverse_engineer.prompt_find_perspectives__major_tension(
                    intent=intent_mode,
                    theses=theses,
                    perspectives=pp_lists,
                )
            else:
                pp_messages = (
                    reverse_engineer.prompt_find_perspectives__general_concepts(
                        intent=intent_mode,
                        theses=theses,
                        perspectives=pp_lists,
                    )
                )

            extend_tpl(tpl, pp_messages)

        return tpl

    @staticmethod
    def till_cycle(
        perspectives: list[Perspective],
        t_cycle: Cycle,
        ta_cycle: Cycle = None,
        text: str = None,
    ) -> list[BaseMessageParam]:
        reverse_engineer = ReverseEngineer()
        tpl: list[BaseMessageParam] = ReverseEngineer.till_perspectives(
            perspectives, text
        )

        cycles = {
            str(t_cycle): [
                f"### {(t_cycle.intent or 'preset:balanced')} Causality Estimation for {t_cycle}",
                f"Probability: {t_cycle.relevance}",  # Note that it's the initial assessment that we take, not normalized
                f"Rationale: {t_cycle.best_rationale.text if t_cycle.best_rationale and t_cycle.best_rationale.text else 'N/A'}",
            ],
        }
        if ta_cycle:
            cycles[str(ta_cycle)] = [
                f"### {(ta_cycle.intent or 'preset:balanced')} Causality Estimation for {ta_cycle}",
                f"Probability: {ta_cycle.relevance}", # Note that it's the initial assessment that we take, not normalized
                f"Rationale: {ta_cycle.best_rationale.text if ta_cycle.best_rationale and ta_cycle.best_rationale.text else 'N/A'}",
            ]

        cycle_intent = (t_cycle.intent or "preset:balanced").lower()
        if cycle_intent in ("preset:realistic", "realistic"):
            cycle_messages = reverse_engineer.prompt_cycle__realistic(
                sequences=list(cycles.keys()),
                estimations=list(cycles.values()),
            )
        elif cycle_intent in ("preset:desirable", "desirable"):
            cycle_messages = reverse_engineer.prompt_cycle__desirable(
                sequences=list(cycles.keys()),
                estimations=list(cycles.values()),
            )
        elif cycle_intent in ("preset:feasible", "feasible"):
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
        # Wheel belongs to Cycle which stores PP hashes
        # Get the parent cycle from wheel
        cycle_result = wheel.cycle.get()
        cycle = cycle_result[0] if cycle_result else None

        # Get perspectives list
        perspectives_list = wheel._perspectives

        # In the new architecture, the wheel IS the ta-cycle level
        # Pass the same cycle for both t_cycle and ta_cycle
        return ReverseEngineer.till_cycle(
            perspectives_list, cycle, None, text
        )


def _perspectives_grouped_by_intent(
    perspectives: list[Perspective],
) -> Dict[str, list[Perspective]]:
    grouped_units: Dict[str, list[Perspective]] = {}
    for pp in perspectives:
        intent_key = pp.intent or "preset:general_concepts"
        if intent_key not in grouped_units:
            grouped_units[intent_key] = []
        grouped_units[intent_key].append(pp)
    return grouped_units
