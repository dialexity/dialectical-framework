import inspect

from mirascope import prompt_template, Messages

from dialectical_framework.synthesist.abstract_wheel_strategy import AbstractWheelStrategy

class Wheel2SemanticContextualizedStrategy(AbstractWheelStrategy):
    def __init__(self):
        self.text = ""

    @prompt_template()
    def thesis(self, text: str) -> Messages.Type:
        self.text = text
        return [
            Messages.User(f"<initial_context>{self.text}</initial_context>"),
            Messages.User(inspect.cleandoc("""
            Extract the central idea (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.
        
            Output the dialectical component T and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T".
            """))
        ]

    @prompt_template()
    def antithesis(self, thesis: str) -> Messages.Type:
        return [
            Messages.User(f"<initial_context>{self.text}</initial_context>"),
            Messages.User(inspect.cleandoc("""
            Generate a strict semantic opposition (A) of the thesis "{thesis}" (T), while considering the subtleties available in the context. If several semantic oppositions are possible, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. Generalize all of them using up to 6 words.
        
            For instance, if T = Courage, then A = Fear. If T = Love, then A = Hate or Indifference. If T = War is bad, then A = War is good.
        
            Output the dialectical component A and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A".
            """))
        ]

    @prompt_template()
    def negative_side(self, thesis: str, not_like_this: str = "") -> Messages.Type:
        return [
            Messages.User(f"<initial_context>{self.text}</initial_context>"),
            Messages.User(inspect.cleandoc("""
            Generate a negative side (T-) of a thesis "{thesis}" (T), while considering the subtleties available in the context, representing its strict semantic exaggeration and overdevelopment, as if the author of T lost his inner control. Make sure that T- is not the same as: "{not_like_this}".
        
            For instance, if T = Courage, then T- = Foolhardiness. If T = Love, then T- = Obsession, Fixation, Loss of Mindfulness. If T = Fear, then T- = Paranoia. If T = Hate and Indifference then T- = Malevolence and Apathy.
        
            If more than one T- exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. For instance, T- = "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation
        
            Output the dialectical component T- and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T-" or "A-".
            """))
        ]

    @prompt_template()
    def positive_side(self, thesis: str, antithesis_negative: str) -> Messages.Type:
        return [
            Messages.User(f"<initial_context>{self.text}</initial_context>"),
            Messages.User(inspect.cleandoc("""
            Generate a positive side or outcome (T+) of a thesis "{thesis}" (T), while considering the subtleties available in the context, representing its constructive (balanced) form, that is also the semantic opposition of "{antithesis_negative}" (A-).

            For instance, if A- = Paranoia, then T+ = Trust. If A- = Malevolence and Apathy, then T+ = Kindness and Empathy. If A- = Foolhardiness, then T+ = Prudence. If A- = Obsession, then T+ =  Mindfulness or Balance. If A- = Suppressed Natural Immunity, then T+ = Enhanced Natural Immunity.
        
            Make sure that T+ is truly connected to the semantic T, while considering the subtleties subtleties available in the context, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships.
        
            For instance, T+ = Trust can be seen as the constructive side of T = Courage. T+ = Kindness and Empathy are natural constructive outcomes of T = Love.
        
            If more than one T+ exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. 
        
            Output the dialectical component T+ and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-".
            """))
        ]