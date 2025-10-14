import inspect

from dependency_injector.wiring import Provide
from mirascope import BaseMessageParam, Messages, prompt_template

from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.domain.wheel_segment import ALIAS_T
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


class ReasonFast(PolarityReasoner):
    @prompt_template(
        """
        USER:
        # Dialectical Analysis
        
        <instructions>
        In the given context, identify the primary thesis or the central idea in the text. Generalize it to no more than {component_length} words and denote it as T.
        
        (If the text does not have a clear thesis or the central idea, please also consider any implicit themes or underlying messages that could be present, and consider them as T.)
        
        1)  For this T, generate strict semantic opposition - Antithesis A. If several  semantic oppositions are possible, then generalize all of them using up to {component_length} words
        
        For instance, if T = Courage, then A = Fear. If T = Love, then A = Hate or Indifference. If T = 'War is bad', then A = 'War is good'.
        
        2) For a given T, generate its negative side (T-) defined as the strict semantic exaggeration and overdevelopment of T, as if the author of T lost his inner control.
        
        For instance, if T = Courage, then T- = Foolhardiness. If T= Love, then T- = Obsession, Fixation, Loss of Mindfulness
        
        If more than one T- exists, generalize all of them in up to {component_length} words. For instance T- =  "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation
        
        Extend the reasoning toward the sharpest and most radical possible statement, to achieve the highest possible awakening effect. For instance, if T = Vaccination, then T- = Over-dependence on vaccination, equivalent to loss of independence, autonomy, self-regulation, suppressed natural immunity, and Health Disruption
        
        Note that all positive and negative outcomes are ALWAYS TRUE, but some dominate the others due to the specific circumstances. So, the question is not "does the given outcomes exist?", but "what they may become when they really take over?"
        </instructions>
        
        ASSISTANT:
        {assistant_msg}
        
        USER:
        <instructions>
        3) For a given semantic A, generate its positive side or outcome (A+), defined as the semantic opposition of T- from the previous step.
        
        For instance, if T- = Foolhardiness, then A+ = Prudence. If T = Obsession, then A+ =  Mindfulness or Balance.
        
        If T- = Suppressed Natural Immunity, then A+ = Enhanced Natural Immunity
        
        If more than one A+ exists, generalize all of them in up to {component_length} words.
        
        4) Make sure that A+ is truly connected to the semantic A that was generated above, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships.
        
        For instance, A+ = Prudence can be seen as the constructive side of A = Cautiousness or Fear.
        
        If A+ is not the natural constructive side of A, then we may need to expand the definitions of A+ and T- or correct the definition of A.
        
        5) For the abovementioned semantic A, generate its negative side (A-) defined as the strict semantic exaggeration and overdevelopment of A, as if the author of A lost his inner control.  Imagine that the author of T has a harsh semantic opponent who first claimed A, but then lost control and exaggerated to A-
        
        For instance, if A = Fear, then A- =  Paranoia. If A = Hate and Indifference then A- = Malevolence and Apathy.
        
        If A = Non-vaccination, then A- = Restricted Choices
        
        If more than one A- exists, generalize all of them in up to {component_length} words.
        
        6) For a given T, generate its positive side (T+), defined as the semantic opposition of A- from the previous step.
        
        For instance, if A- = Paranoia, then T+ = Trust. If A- = Malevolence and Apathy, then T+ = Kindness and Empathy.
        
        If A- = Restricted Choices, then T+ = Expanded Choices
        
        If more than one A+ exists, generalize all of them in up to {component_length} words.
        
        7) Make sure that T+ is truly connected to the T, representing its positive and constructive side that is highly perceptive, nuanced, gentle, evolving , instrumental in solving problems and creating friendships.
        
        For instance, if T+ = Trust can be viewed as natural constructive side of  T = Courage. T+ = Kindness and Empathy are natural constructive outcomes of T = Love.
        
        T+ = Expanded Choices is a natural extension of T = Vaccination. Note the difference from your internal regulations - the positive side of Vaccination is not the "Life Saving", but only "Expanding Choices".
        
        If T+ is not the natural constructive side of T, then we may need to expand the definitions of T+ and A-
        </instructions>
        <examples>
        First example:
        
        Primary thesis T = Courage
        
        Output:
        
        T = Courage
        T+ = Trust
        T- = Foolhardiness
        A = Fear
        A+ = Prudence
        A- = Paranoia
        
        Another example:
        
        Primary thesis T = Love
        
        Output:
        
        T = Love
        A = Hate or Indifference
        T- = Disempowered Equilibrium
        A+ = Empowered Equilibrium
        A- = Malevolence and Apathy
        T+ = Kindness and Empathy
        
        Yet another example:
        
        Primary thesis T = Love is Good
        
        Output:
        
        T = Love is Good
        A = Love is Bad
        T- = Idealization
        A+ = Realism
        A- = Cynicism
        T+ = Optimism
        </examples>
        
        Output the dialectical components. Compose the explanations how they were derived in the passive voice, but don't mention any special denotations such as "T", "T+", "A-", etc. in them.
        """
    )
    def prompt_next(self, wu_so_far: WisdomUnit, config: Settings = Provide[DI.settings]) -> Messages.Type:
        assistant_msg = "Ok, will do, any additional instructions?"
        if wu_so_far.t or wu_so_far.a:
            assistant_msg = "\n".join([f'T = {wu_so_far.t.statement}', f'A = {wu_so_far.a.statement}'])
        return {
            "computed_fields": {
                "assistant_msg": assistant_msg,
                "component_length": config.component_length,
            }
        }
