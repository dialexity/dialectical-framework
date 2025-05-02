from typing import Annotated

from mirascope import prompt_template, Messages, BaseMessageParam, llm
from mirascope.integrations.langfuse import with_langfuse

from config import Config
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.abstract_wheel_strategy import AbstractWheelStrategy, Wheel
from dialectical_framework.synthesist.wheel2 import Wheel2, ALIAS_T, ALIAS_A, ALIAS_T_MINUS, ALIAS_A_MINUS, \
    ALIAS_T_PLUS, ALIAS_A_PLUS
from utils.dc_replace import dc_safe_replace


class Wheel2BaseStrategy(AbstractWheelStrategy[Wheel2]):
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
    """)
    def antithesis(self, thesis: str | DialecticalComponent) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        return {
            "computed_fields": {"thesis": thesis},
        }

    @prompt_template("""
    Generate a negative side (T-) of a thesis "{thesis}" (T), representing its strict semantic exaggeration and overdevelopment, as if the author of T lost his inner control. Make sure that T- is not the same as: "{not_like_this}".

    For instance, if T = Courage, then T- = Foolhardiness. If T = Love, then T- = Obsession, Fixation, Loss of Mindfulness. If T = Fear, then T- = Paranoia. If T = Hate and Indifference then T- = Malevolence and Apathy.

    If more than one T- exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. For instance, T- = "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation

    Output the dialectical component T- and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T-" or "A-".
    """)
    def negative_side(self, thesis: str | DialecticalComponent, not_like_this: str | DialecticalComponent = "") -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        if isinstance(not_like_this, DialecticalComponent):
            not_like_this = not_like_this.statement
        return {
            "computed_fields": {
                "thesis": thesis,
                "not_like_this": not_like_this
            },
        }

    def thesis_negative_side(self, thesis: str | DialecticalComponent, not_like_this: str | DialecticalComponent = "") -> Messages.Type:
        return self.negative_side(thesis, not_like_this)

    def antithesis_negative_side(self, antithesis: str | DialecticalComponent, not_like_this: str | DialecticalComponent = "") -> Messages.Type:
        tpl: list[BaseMessageParam] =  self.negative_side(antithesis, not_like_this)
        # Replace the technical terms in the prompt, so that it makes sense when passed in the history
        for i in range(len(tpl)):
            if tpl[i].content:
                tpl[i].content = dc_safe_replace(tpl[i].content, {
                    ALIAS_T: ALIAS_A,
                    ALIAS_T_MINUS: ALIAS_A_MINUS,
                    ALIAS_A_MINUS: ALIAS_T_MINUS
                })
        return tpl


    @prompt_template("""
    A contradictory/semantic opposition presents a direct semantic opposition and/or contradiction to the original statement that excludes their mutual coexistence. For instance, Happiness vs. Unhappiness; Truthfulness vs. Lie/Deceptiveness; Dependence vs. Independence.

    Generate a positive side or outcome (T+) of a thesis "{thesis}" (T), representing its constructive (balanced) form/side, that is also the contradictory/semantic opposition of "{antithesis_negative}" (A-).
    
    Make sure that T+ is truly connected to the semantic T, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships. For instance, T+ = Trust can be seen as the constructive side of T = Courage. T+ = Kindness and Empathy are natural constructive outcomes of T = Love.

    If more than one T+ exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

    Output the dialectical component T+ and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-".
    """)
    def positive_side(self, thesis: str | DialecticalComponent, antithesis_negative: str | DialecticalComponent) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        if isinstance(antithesis_negative, DialecticalComponent):
            antithesis_negative = antithesis_negative.statement
        return {
            "computed_fields": {
                "thesis": thesis,
                "antithesis_negative": antithesis_negative
            },
        }

    def thesis_positive_side(self, thesis: str | DialecticalComponent, antithesis_negative: str | DialecticalComponent) -> Messages.Type:
        return self.positive_side(thesis, antithesis_negative)

    def antithesis_positive_side(self, antithesis: str | DialecticalComponent, thesis_negative: str | DialecticalComponent) -> Messages.Type:
        tpl: list[BaseMessageParam] = self.positive_side(antithesis, thesis_negative)
        # Replace the technical terms in the prompt, so that it makes sense when passed in the history
        for i in range(len(tpl)):
            if tpl[i].content:
                tpl[i].content = dc_safe_replace(tpl[i].content, {
                    ALIAS_T: ALIAS_A,
                    ALIAS_T_PLUS: ALIAS_A_PLUS,
                    ALIAS_A_MINUS: ALIAS_T_MINUS
                })
        return tpl

    @prompt_template()
    def next_missing_component(self, wheel_so_far: Wheel2) -> Messages.Type:
        """
        Raises:
            ValueError: If the wheel is incorrect.
            StopIteration: If the wheel is complete already.
        """
        if not wheel_so_far.t:
            raise ValueError("T - not found in the wheel")

        prompt_messages = []

        if not wheel_so_far.a:
            prompt_messages.extend(
                self.antithesis(wheel_so_far.t),
            )
            return prompt_messages

        if not wheel_so_far.t_minus:
            prompt_messages.extend(
                self.negative_side(
                    wheel_so_far.t,
                    wheel_so_far.a_minus if wheel_so_far.a_minus else ""
                )
            )
            return prompt_messages

        if not wheel_so_far.a:
            raise ValueError("A - not found in the wheel")

        if not wheel_so_far.a_minus:
            prompt_messages.extend(
                self.negative_side(
                    wheel_so_far.a,
                    wheel_so_far.t_minus if wheel_so_far.t_minus else ""
                )
            )
            return prompt_messages

        if not wheel_so_far.a_minus:
            raise ValueError("A- - not found in the wheel")
        if not wheel_so_far.t_plus:
            prompt_messages.extend(
                self.positive_side(
                    wheel_so_far.t,
                    wheel_so_far.a_minus
                )
            )
            return prompt_messages

        if not wheel_so_far.t_minus:
            raise ValueError("T- - not found in the wheel")
        if wheel_so_far.a_plus:
            prompt_messages.extend(
                self.positive_side(
                    wheel_so_far.a,
                    wheel_so_far.t_minus
                )
            )
            return prompt_messages

        raise StopIteration("The wheel is complete, nothing to do.")

    @with_langfuse()
    @llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
    async def find_thesis(self) -> DialecticalComponent:
        return self.thesis(self.text)

    @with_langfuse()
    @llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
    async def find_next_missing_component(self, wheel_so_far: Wheel2) -> DialecticalComponent:
        return self.next_missing_component(wheel_so_far)

    async def expand(self, wheel: Wheel = None) -> Wheel:
        if not self.text:
            raise ValueError("Text is not provided")

        if wheel is None:
            wheel = Wheel2()
            wheel.t = await self.find_thesis()

        dc: DialecticalComponent = await self.find_next_missing_component(wheel)
        setattr(wheel, dc.alias, dc)

        return wheel


