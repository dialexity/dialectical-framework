from idna import check_bidi
from mirascope import llm, prompt_template
from mirascope.llm import CallResponse

from config import Config
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.basic_wheel import BasicWheel
from dialectical_framework.synthesist.wheel_factories.abstract_wheel_factory import AbstractWheelFactory
from dialectical_framework.validator.basic_checks import check, is_valid_opposition, is_negative_side, \
    is_strict_opposition, is_positive_side


@llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
@prompt_template("""
<context>
{text}
</context>

Extract the central idea (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

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

class BasicWheelFactory(AbstractWheelFactory):
    def generate(self, input_text: str) -> BasicWheel:
        t = thesis(input_text)
        a = antithesis(input_text, t)
        t_minus = thesis_negative(input_text, t)
        a_minus = antithesis_negative(input_text, a, t_minus)
        t_plus = thesis_positive(input_text, t, a_minus)
        a_plus = antithesis_positive(input_text, a, t_minus)

        assert isinstance(t_minus, DialecticalComponent)
        assert isinstance(t, DialecticalComponent)
        assert isinstance(t_plus, DialecticalComponent)
        assert isinstance(a_minus, DialecticalComponent)
        assert isinstance(a, DialecticalComponent)
        assert isinstance(a_plus, DialecticalComponent)
        return BasicWheel(
            t_minus=t_minus,
            t=t,
            t_plus=t_plus,
            a_minus=a_minus,
            a=a,
            a_plus=a_plus
        )

    def redefine(self, input_text: str, original: BasicWheel, **modified_dialectical_components) -> BasicWheel:
        warnings: dict[str, list[str]] = {}

        changed: dict[str, str] = {
            k: str(v) for k, v in modified_dialectical_components.items()
            if k in BasicWheel.__pydantic_fields__
        }

        new_wheel: BasicWheel = BasicWheel()

        # ==
        # Redefine opposition
        # ==
        base = 't'
        other = "a" if base == 't' else "t"

        alias_base = "T" if base == 't' else "A"
        alias_other = "A" if base == 't' else "T"


        for dialectical_component in [base, other]:
            if changed.get(dialectical_component):
                setattr(new_wheel, dialectical_component, DialecticalComponent(
                    statement=changed.get(dialectical_component),
                    explanation=f"{new_wheel.Config.alias_generator(dialectical_component)} redefined."
                ))
            else:
                new_wheel.dialectical_component_copy_from(original, dialectical_component)

        if changed.get(base) or changed.get(other):
            check1 = check(is_valid_opposition, getattr(new_wheel, base).statement, getattr(new_wheel, other).statement)

            if not check1.is_valid:
                if changed.get(base) and not changed.get(other):
                    # base side changed
                    o = antithesis(input_text, getattr(new_wheel, base).statement)
                    assert isinstance(o, DialecticalComponent)
                    o.explanation = f"REGENERATED. {o.explanation}"
                    setattr(new_wheel, other, o)
                    changed[other] = o.statement
                    check1.is_valid = True
                    check1.explanation = "Regenerated, therefore must be valid."
                elif changed.get(other) and not changed.get(base):
                    # other side changed
                    bm = antithesis(input_text, getattr(new_wheel, other).statement)
                    assert isinstance(bm, DialecticalComponent)
                    bm.explanation = f"REGENERATED. {bm.explanation}"
                    setattr(new_wheel, base, bm)
                    changed[base] = bm.statement
                    check1.is_valid = True
                    check1.explanation = "Regenerated, therefore must be valid."

            if not check1.is_valid:
                getattr(new_wheel, base).statement = f"ERROR: {getattr(new_wheel, base).statement}"
                getattr(new_wheel, other).statement = f"ERROR: {getattr(new_wheel, other).statement}"
                warnings.setdefault(alias_base, []).append(check1.explanation)
                warnings.setdefault(alias_other, []).append(check1.explanation)
                raise AssertionError(f"{alias_base}, {alias_other}", warnings, new_wheel)

        else:
            # Keep originals
            pass

        # NOTE: At this point we are sure that T and A are present and valid in the new wheel

        # ==
        # Redefine diagonal relations
        # ==
        for side in ['t', 'a']:
            base = side
            other = "a" if base == 't' else "t"

            base_minus = "t_minus" if side == 't' else "a_minus"
            base_plus = "t_plus" if side == 't' else "a_plus"
            other_plus = "a_plus" if side == 't' else "t_plus"
            other_minus = "a_minus" if side == 't' else "t_minus"

            alias_base_minus = "T-" if side == 't' else "A-"
            alias_other_plus = "A+" if side == 't' else "T+"

            for dialectical_component in [base_minus, other_plus]:
                if changed.get(dialectical_component):
                    setattr(new_wheel, dialectical_component, DialecticalComponent(
                        statement=changed.get(dialectical_component),
                        explanation=f"{new_wheel.Config.alias_generator(dialectical_component)} redefined."
                    ))
                else:
                    new_wheel.dialectical_component_copy_from(original, dialectical_component)

            if (changed.get(base) or changed.get(base_minus)) or (changed.get(other) or changed.get(other_plus)):
                if changed.get(base_minus) or changed.get(base):
                    check2 = check(is_negative_side, getattr(new_wheel, base_minus).statement, getattr(new_wheel, base).statement)

                    if not check2.is_valid:
                        if changed.get(base) and not changed.get(base_minus):
                            not_like_other_minus = ""
                            if hasattr(new_wheel, other_minus):
                                if getattr(new_wheel, other_minus):
                                    not_like_other_minus = getattr(new_wheel, other_minus).statement
                            bm = thesis_negative(input_text, getattr(new_wheel, base).statement, not_like_other_minus)
                            assert isinstance(bm, DialecticalComponent)
                            bm.explanation = f"REGENERATED. {bm.explanation}"
                            setattr(new_wheel, base_minus, bm)
                            changed[base_minus] = bm.statement
                            check2.is_valid = True
                            check2.explanation = "Regenerated, therefore must be valid."

                    if not check2.is_valid:
                        getattr(new_wheel, base_minus).statement = f"ERROR: {getattr(new_wheel, base_minus).statement}"
                        warnings.setdefault(alias_base_minus, []).append(check2.explanation)
                        raise AssertionError(f"{alias_base_minus}", warnings, new_wheel)

                # NOTE: At this point we are sure that BASE and BASE- are present and valid between themselves in the new wheel

                other_plus_regenerated = False
                if changed.get(other_plus) or changed.get(other):
                    check3 = check(is_positive_side, getattr(new_wheel, other_plus).statement, getattr(new_wheel, other).statement)

                    if not check3.is_valid:
                        if changed.get(other) and not changed.get(other_plus):
                            op = antithesis_positive(input_text, getattr(new_wheel, other).statement, getattr(new_wheel, base_minus).statement)
                            assert isinstance(op, DialecticalComponent)
                            op.explanation = f"REGENERATED. {op.explanation}"
                            setattr(new_wheel, other_plus, op)
                            changed[other_plus] = op.statement
                            check3.is_valid = True
                            check3.explanation = "Regenerated, therefore must be valid."
                            other_plus_regenerated = True

                    if not check3.is_valid:
                        getattr(new_wheel, other_plus).statement = f"ERROR: {getattr(new_wheel, other_plus).statement}"
                        warnings.setdefault(alias_other_plus, []).append(check3.explanation)
                        raise AssertionError(f"{alias_other_plus}", warnings, new_wheel)

                # NOTE: At this point we are sure that OTHER and OTHER- are present and valid between themselves in the new wheel

                additional_diagonal_check_skip = other_plus_regenerated or (not changed.get(base_minus) and not changed.get(other_plus))

                if not additional_diagonal_check_skip:
                    check4 = check(is_strict_opposition, getattr(new_wheel, base_minus).statement, getattr(new_wheel, other_plus).statement)
                    if not check4.is_valid:
                        if changed.get(base_minus) and not changed.get(other_plus):
                            # base side changed
                            op = antithesis_positive(
                                text=input_text,
                                antithesis=getattr(new_wheel, other).statement,
                                thesis_negative=getattr(new_wheel, base_minus).statement
                            )
                            assert isinstance(op, DialecticalComponent)
                            op.explanation = f"REGENERATED. {op.explanation}"
                            setattr(new_wheel, other_plus, op)
                            changed[other_plus] = op.statement
                            check4.is_valid = True
                            check4.explanation = "Regenerated, therefore must be valid."
                        elif changed.get(other_plus) and not changed.get(base_minus):
                            # other side changed
                            not_like_other_minus = ""
                            if hasattr(new_wheel, other_minus):
                                if getattr(new_wheel, other_minus):
                                    not_like_other_minus = getattr(new_wheel, other_minus).statement
                            bm = thesis_negative(
                                text=input_text,
                                thesis=getattr(new_wheel, base).statement,
                                not_like_this=not_like_other_minus
                            )
                            assert isinstance(bm, DialecticalComponent)
                            bm.explanation = f"REGENERATED. {bm.explanation}"
                            setattr(new_wheel, base_minus, bm)
                            changed[base_minus] = bm.statement
                            check4.is_valid = True
                            check4.explanation = "Regenerated, therefore must be valid."

                    if not check4.is_valid:
                        getattr(new_wheel, base_minus).statement = f"ERROR: {getattr(new_wheel, base_minus).statement}"
                        getattr(new_wheel, other_plus).statement = f"ERROR: {getattr(new_wheel, other_plus).statement}"
                        warnings.setdefault(alias_base_minus, []).append(check4.explanation)
                        warnings.setdefault(alias_other_plus, []).append(check4.explanation)
                        raise AssertionError(f"{alias_base_minus}, {alias_other_plus}", warnings, new_wheel)

                # NOTE: At this point we are sure that diagonals are present and valid in the new wheel

            else:
                # Keep originals
                pass

        return new_wheel