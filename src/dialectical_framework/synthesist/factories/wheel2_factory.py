import asyncio
from typing import Generic

from mirascope import llm
from mirascope.integrations.langfuse import with_langfuse

from config import Config
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.abstract_wheel_factory import AbstractWheelFactory, WheelStrategy
from dialectical_framework.synthesist.wheel2 import Wheel2, ALIAS_T
from dialectical_framework.synthesist.strategies.wheel2_base_strategy import Wheel2BaseStrategy
from dialectical_framework.validator.basic_checks import check, is_valid_opposition, is_negative_side, \
    is_strict_opposition, is_positive_side


class Wheel2Factory(AbstractWheelFactory[Wheel2BaseStrategy, Wheel2]):
    @with_langfuse()
    @llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
    async def _thesis(self, text: str) -> DialecticalComponent:
        return self.strategy.thesis(text)

    @with_langfuse()
    @llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
    async def _antithesis(self, thesis: str) -> DialecticalComponent:
        return self.strategy.antithesis(thesis)

    @with_langfuse()
    @llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
    async def _negative_side(self, thesis: str, not_like_this: str = "") -> DialecticalComponent:
        return self.strategy.negative_side(thesis, not_like_this)

    @with_langfuse()
    @llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=DialecticalComponent)
    async def _positive_side(self, thesis: str, antithesis_negative: str) -> DialecticalComponent:
        return self.strategy.positive_side(thesis, antithesis_negative)

    async def redefine(self, input_text: str, original: Wheel2, **modified_dialectical_components) -> Wheel2:
        warnings: dict[str, list[str]] = {}

        changed: dict[str, str] = {
            k: str(v) for k, v in modified_dialectical_components.items()
            if k in Wheel2.__pydantic_fields__
        }

        new_wheel: Wheel2 = Wheel2()

        # ==
        # Redefine opposition
        # ==
        base = 't'
        other = "a" if base == 't' else "t"

        for dialectical_component in [base, other]:
            if changed.get(dialectical_component):
                setattr(new_wheel, dialectical_component, DialecticalComponent(
                    alias=new_wheel.__pydantic_fields__.get(dialectical_component).alias,
                    statement=changed.get(dialectical_component),
                    explanation=f"{new_wheel.__pydantic_fields__.get(dialectical_component).alias} redefined."
                ))
            else:
                new_wheel.dialectical_component_copy_from(original, dialectical_component)

        alias_base = "T" if base == 't' else "A"
        alias_other = "A" if base == 't' else "T"

        if changed.get(base) or changed.get(other):
            check1 = check(is_valid_opposition, getattr(new_wheel, base).statement, getattr(new_wheel, other).statement)

            if not check1.is_valid:
                if changed.get(base) and not changed.get(other):
                    # base side changed
                    o = await self._antithesis(getattr(new_wheel, base).statement)
                    assert isinstance(o, DialecticalComponent)
                    o.explanation = f"REGENERATED. {o.explanation}"
                    setattr(new_wheel, other, o)
                    changed[other] = o.statement
                    check1.is_valid = True
                    check1.explanation = "Regenerated, therefore must be valid."
                elif changed.get(other) and not changed.get(base):
                    # other side changed
                    bm = await self._antithesis(getattr(new_wheel, other).statement)
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
                        alias=new_wheel.__pydantic_fields__.get(dialectical_component).alias,
                        statement=changed.get(dialectical_component),
                        explanation=f"{new_wheel.__pydantic_fields__.get(dialectical_component).alias} redefined."
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
                            bm = await self._negative_side(getattr(new_wheel, base).statement, not_like_other_minus)
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
                            op = await self._positive_side(getattr(new_wheel, other).statement, getattr(new_wheel, base_minus).statement)
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
                            op = await self._positive_side(
                                getattr(new_wheel, other).statement,
                                getattr(new_wheel, base_minus).statement
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
                            bm = await self._negative_side(
                                getattr(new_wheel, base).statement,
                                not_like_other_minus
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