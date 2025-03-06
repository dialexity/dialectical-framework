from pprint import pprint

from mirascope import llm, prompt_template
from mirascope.llm import CallResponse
from openai import BaseModel
from pydantic import Field

from config import Config
from dialectical_framework.dialectical_component import DialecticalComponent

WHEEL_COMPONENT_ALIAS_MAP = {
    "t_minus": "T-",
    "t": "T",
    "t_plus": "T+",
    "a_plus": "A+",
    "a": "A",
    "a_minus": "A-",
}

class Wheel2(BaseModel):
    t_minus: DialecticalComponent = Field(description="The negative side of the thesis: T-")
    t: DialecticalComponent =  Field(description="The major thesis of the input: T")
    t_plus: DialecticalComponent = Field(description="The positive side of the thesis: T+")
    a_minus: DialecticalComponent = Field(description="The negative side of the antithesis: A-")
    a: DialecticalComponent = Field(description="The antithesis: A")
    a_plus: DialecticalComponent = Field(description="The positive side of the antithesis: A+")

    class Config:
        populate_by_name = True

        @classmethod
        def alias_generator(cls, string: str) -> str:
            return WHEEL_COMPONENT_ALIAS_MAP.get(string, string)

    def __str__(self):
        ini_data = []
        for k, v in self.model_dump().items():
            alias = Wheel2.Config.alias_generator(k)
            ini_data.append(f"{alias} = {v}")
        return "\n------------------\n".join(ini_data)


@llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
@prompt_template("""
<context>
{text}
</context>

Identify the primary thesis or the central idea provided in the context (denote it as T). Be detailed enough to show deep understanding, yet concise enough to maintain clarity. Capture the essence without overwhelming specificity. Generalize it to no more than 6 words.

(If the text does not have a clear thesis or the central idea, please also consider any implicit themes or underlying messages that could be present, and consider them as T.)

Output the dialectical component T and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T". 
""")
def thesis(text: str) -> str: ...


@llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
@prompt_template("""
<context>
{text}
</context>

Generate a strict semantic opposition (A) of the thesis "{thesis}" (T), while considering the subtleties available in the context. If several semantic oppositions are possible, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. Generalize all of them using up to 6 words.

For instance, if T = Courage, then A = Fear. If T = Love, then A = Hate or Indifference. If T = War is bad, then A = War is good.

Output the dialectical component A and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A".
"""
)
def antithesis(text: str, thesis: str | CallResponse) -> str: ...


@llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
@prompt_template("""
<context>
{text}
</context>

Generate a negative side (T-) of a thesis "{thesis}" (T), while considering the subtleties available in the context, representing its strict semantic exaggeration and overdevelopment, as if the author of T lost his inner control. Make sure that T- is not the same as: "{not_like_this}".

For instance, if T = Courage, then T- = Foolhardiness. If T = Love, then T- = Obsession, Fixation, Loss of Mindfulness. If T = Fear, then T- = Paranoia. If T = Hate and Indifference then T- = Malevolence and Apathy.

If more than one T- exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. For instance, T- = "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation

Output the dialectical component T- and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T-" or "A-".
""")
def thesis_negative(text: str, thesis: str | CallResponse, not_like_this: str | CallResponse = "") -> str: ...
def antithesis_negative(text: str, antithesis: str | CallResponse, not_like_this: str | CallResponse) -> str:
    return thesis_negative(text, antithesis, not_like_this)


@llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
@prompt_template("""
<context>
{text}
</context>

Generate a positive side or outcome (T+) of a thesis "{thesis}" (T), while considering the subtleties available in the context, representing its constructive (balanced) form, that is also the semantic opposition of "{antithesis_negative}" (A-).

For instance, if A- = Paranoia, then T+ = Trust. If A- = Malevolence and Apathy, then T+ = Kindness and Empathy. If A- = Foolhardiness, then T+ = Prudence. If A- = Obsession, then T+ =  Mindfulness or Balance. If A- = Suppressed Natural Immunity, then T+ = Enhanced Natural Immunity.

Make sure that T+ is truly connected to the semantic T, while considering the subtleties subtleties available in the context, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships.

For instance, T+ = Trust can be seen as the constructive side of T = Courage. T+ = Kindness and Empathy are natural constructive outcomes of T = Love.

If more than one T+ exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. 

Output the dialectical component T+ and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-".
""")
def thesis_positive(text: str, thesis: str | CallResponse, antithesis_negative: str | CallResponse) -> str: ...
def antithesis_positive(text: str, antithesis: str | CallResponse, thesis_negative: str | CallResponse) -> str:
    return thesis_positive(text, antithesis, thesis_negative)

def generate(um: str) -> Wheel2:
    t = thesis(um)
    a = antithesis(um, t)
    t_minus = thesis_negative(um, t)
    a_minus = antithesis_negative(um, a, t_minus)
    t_plus = thesis_positive(um, t, a_minus)
    a_plus = antithesis_positive(um, a, t_minus)

    assert isinstance(t_minus, DialecticalComponent)
    assert isinstance(t, DialecticalComponent)
    assert isinstance(t_plus, DialecticalComponent)
    assert isinstance(a_minus, DialecticalComponent)
    assert isinstance(a, DialecticalComponent)
    assert isinstance(a_plus, DialecticalComponent)
    return Wheel2(
        t_minus=t_minus,
        t=t,
        t_plus=t_plus,
        a_minus=a_minus,
        a=a,
        a_plus=a_plus
    )

if __name__ == "__main__":
    # user_message = "I'm in love with you, what else can I say..."
    user_message = "Love"
    half_wheel = generate(user_message)
    print(half_wheel)
