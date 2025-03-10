from mirascope import prompt_template, Messages

from dialectical_framework.synthesist.abstract_wheel_strategy import AbstractWheelStrategy


class Wheel2SimpleSemanticStrategy(AbstractWheelStrategy):
    @prompt_template("""
    USER:
    <context>{text}</context>
    
    USER:
    Extract the central idea or the primary thesis (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

    Output the dialectical component T and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T". 
    """)
    def thesis(self, text: str) -> Messages.Type: ...

    @prompt_template("""
    A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.
    
    Generate a dialectical opposition (A) of the thesis "{thesis}" (T). Be detailed enough to show deep understanding, yet concise enough to maintain clarity. Generalize all of them using up to 6 words.

    Output the dialectical component A and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A".
    """
                     )
    def antithesis(self, thesis: str) -> Messages.Type: ...

    @prompt_template("""
    Generate a negative side (T-) of a thesis "{thesis}" (T), representing its strict semantic exaggeration and overdevelopment, as if the author of T lost his inner control. Make sure that T- is not the same as: "{not_like_this}".

    For instance, if T = Courage, then T- = Foolhardiness. If T = Love, then T- = Obsession, Fixation, Loss of Mindfulness. If T = Fear, then T- = Paranoia. If T = Hate and Indifference then T- = Malevolence and Apathy.

    If more than one T- exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. For instance, T- = "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation

    Output the dialectical component T- and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T-" or "A-".
    """)
    def negative_side(self, thesis: str, not_like_this: str = "") -> Messages.Type: ...

    @prompt_template("""
    A contradictory/semantic opposition presents a direct semantic opposition and/or contradiction to the original statement that excludes their mutual coexistence. For instance, Happiness vs. Unhappiness; Truthfulness vs. Lie/Deceptiveness; Dependence vs. Independence.

    Generate a positive side or outcome (T+) of a thesis "{thesis}" (T), representing its constructive (balanced) form/side, that is also the contradictory/semantic opposition of "{antithesis_negative}" (A-).
    
    Make sure that T+ is truly connected to the semantic T, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships. For instance, T+ = Trust can be seen as the constructive side of T = Courage. T+ = Kindness and Empathy are natural constructive outcomes of T = Love.

    If more than one T+ exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

    Output the dialectical component T+ and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-".
    """)
    def positive_side(self, thesis: str, antithesis_negative: str) -> Messages.Type: ...