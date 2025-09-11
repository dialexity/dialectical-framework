import inspect

from mirascope import BaseMessageParam, Messages, prompt_template

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
    In the given context, identify the primary thesis or the central idea in the text. Generalize it to no more than 12 words and denote it as T.
    
    (If the text does not have a clear thesis or the central idea, please also consider any implicit themes or underlying messages that could be present, and consider them as T.)
    
    1)  For this T, generate strict semantic opposition - Antithesis A. If several  semantic oppositions are possible, then generalize all of them using up to 8 words
    
    For instance, if T = Courage, then A = Fear. If T = Love, then A = Hate or Indifference. If T = 'War is bad', then A = 'War is good'.
    
    2) For a given T, generate its negative side (T-) defined as the strict semantic exaggeration and overdevelopment of T, as if the author of T lost his inner control.
    
    For instance, if T = Courage, then T- = Foolhardiness. If T= Love, then T- = Obsession, Fixation, Loss of Mindfulness
    
    If more than one T- exists, generalize all of them in up to 4 words. For instance T- =  "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation
    
    Extend the reasoning toward the sharpest and most radical possible statement, to achieve the highest possible awakening effect. For instance, if T = Vaccination, then T- = Over-dependence on vaccination, equivalent to loss of independence, autonomy, self-regulation, suppressed natural immunity, and Health Disruption
    
    Note that all positive and negative outcomes are ALWAYS TRUE, but some dominate the others due to the specific circumstances. So, the question is not "does the given outcomes exist?", but "what they may become when they really take over?"
    
    3) For a given semantic A, generate its positive side or outcome (A+), defined as the semantic opposition of T- from the previous step.
    
    For instance, if T- = Foolhardiness, then A+ = Prudence. If T = Obsession, then A+ =  Mindfulness or Balance.
    
    If T- = Suppressed Natural Immunity, then A+ = Enhanced Natural Immunity
    
    If more than one A+ exists, generalize all of them in up to 4 words.
    
    4) Make sure that A+ is truly connected to the semantic A that was generated above, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships.
    
    For instance, A+ = Prudence can be seen as the constructive side of A = Cautiousness or Fear.
    
    If A+ is not the natural constructive side of A, then we may need to expand the definitions of A+ and T- or correct the definition of A.
    
    5) For the abovementioned semantic A, generate its negative side (A-) defined as the strict semantic exaggeration and overdevelopment of A, as if the author of A lost his inner control.  Imagine that the author of T has a harsh semantic opponent who first claimed A, but then lost control and exaggerated to A-
    
    For instance, if A = Fear, then A- =  Paranoia. If A = Hate and Indifference then A- = Malevolence and Apathy.
    
    If A = Non-vaccination, then A- = Restricted Choices
    
    If more than one A- exists, generalize all of them in up to 4 words.
    
    6) For a given T, generate its positive side (T+), defined as the semantic opposition of A- from the previous step.
    
    For instance, if A- = Paranoia, then T+ = Trust. If A- = Malevolence and Apathy, then T+ = Kindness and Empathy.
    
    If A- = Restricted Choices, then T+ = Expanded Choices
    
    If more than one A+ exists, generalize all of them in up to 4 words.
    
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
    
    Output the dialectical components. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", etc.
    """
    )
    def prompt_wu(self, text: str) -> Messages.Type: ...

    @prompt_template()
    def prompt_wu_with_thesis_provided(self, text: str, thesis: str) -> Messages.Type:
        tpl: list[BaseMessageParam] = self.prompt_wu(text)
        tpl.append(
            BaseMessageParam(
                role="user",
                content=inspect.cleandoc(
                    f"""
                    IMPORTANT: use T = \"{thesis}\" as the primary thesis of the given context. I hope it makes sense.
                    
                    Base all the following analysis of the initial context on this primary thesis and follow the instructions as provided (skipping the part of finding the primary thesis).
                    """
                ),
            )
        )

        return tpl

    @prompt_template()
    def prompt_next(self, wu_so_far: WisdomUnit) -> Messages.Type:
        """
        Raises:
            ValueError: If the wisdom unit is incorrect.
            StopIteration: If the wisdom unit is complete already.
        """

        if wu_so_far.is_complete():
            raise StopIteration("The wisdom unit is complete, nothing to do.")

        if wu_so_far.t:
            return self.prompt_wu_with_thesis_provided(
                text=self._text, thesis=wu_so_far.t.statement
            )
        else:
            return self.prompt_wu(text=self._text)

    async def think(self, thesis: str | DialecticalComponent = None) -> WisdomUnit:
        wu = WisdomUnit(reasoning_mode=self._mode)

        if thesis is not None:
            if isinstance(thesis, DialecticalComponent):
                if thesis.alias != ALIAS_T:
                    raise ValueError(
                        f"The thesis cannot be a dialectical component with alias '{thesis.alias}'"
                    )
                wu.t = thesis
            else:
                wu.t = DialecticalComponent(
                    alias=ALIAS_T, statement=thesis,
                    # explanation="Provided as string"
                )

        await self._fill_with_reason(wu)

        self._wisdom_unit = wu
        self._analysis.perspectives.append(self._wisdom_unit)
        return self._wisdom_unit
