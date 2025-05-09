from abc import ABC, abstractmethod
from typing import List

from mirascope import prompt_template, Messages, BaseMessageParam, llm
from mirascope.integrations.langfuse import with_langfuse

from config import Config
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_box import DialecticalComponentsBox
from dialectical_framework.validator.basic_checks import (
    check,
    is_valid_opposition,
    is_negative_side,
    is_positive_side,
    is_strict_opposition,
)
from dialectical_framework.wisdom_unit import (
    WisdomUnit,
    ALIAS_T,
    ALIAS_A,
    ALIAS_T_MINUS,
    ALIAS_A_MINUS,
    ALIAS_T_PLUS,
    ALIAS_A_PLUS,
)
from utils.dc_replace import dc_safe_replace


class DialecticalReasoner(ABC):
    def __init__(
        self,
        text: str,
        *,
        ai_model: str = Config.MODEL,
        ai_provider: str | None = Config.PROVIDER,
    ) -> None:
        if not ai_provider:
            if not "/" in ai_model:
                raise ValueError(
                    "ai_model must be in the form of 'provider/model' if ai_provider is not specified."
                )
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                self._ai_provider, self._ai_model = (
                    derived_ai_provider,
                    derived_ai_model,
                )
        else:
            if not "/" in ai_model:
                self._ai_provider, self._ai_model = ai_provider, ai_model
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                if derived_ai_provider != ai_provider:
                    raise ValueError(
                        f"ai_provider '{ai_provider}' does not match ai_model '{ai_model}'"
                    )
                self._ai_provider, self._ai_model = (
                    derived_ai_provider,
                    derived_ai_model,
                )

        self._text = text
        self._wisdom_unit = None

    @prompt_template(
    """
    USER:
    <context>{text}</context>
    
    USER:
    Extract the central idea or the primary thesis (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.

    Output the dialectical component T and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T". 
    """
    )
    def prompt_thesis(self, text: str) -> Messages.Type: ...

    @prompt_template(
    """
    A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.
    
    Generate a dialectical opposition (A) of the thesis "{thesis}" (T). Be detailed enough to show deep understanding, yet concise enough to maintain clarity. Generalize all of them using up to 6 words.

    Output the dialectical component A and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A".
    """
    )
    def prompt_antithesis(self, thesis: str | DialecticalComponent) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        return {
            "computed_fields": {"thesis": thesis},
        }

    @prompt_template(
    """
    Generate a negative side (T-) of a thesis "{thesis}" (T), representing its strict semantic exaggeration and overdevelopment, as if the author of T lost his inner control. Make sure that T- is not the same as: "{not_like_this}".

    For instance, if T = Courage, then T- = Foolhardiness. If T = Love, then T- = Obsession, Fixation, Loss of Mindfulness. If T = Fear, then T- = Paranoia. If T = Hate and Indifference then T- = Malevolence and Apathy.

    If more than one T- exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. For instance, T- = "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation

    Output the dialectical component T- and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T-" or "A-".
    """
    )
    def prompt_thesis_negative_side(
        self,
        thesis: str | DialecticalComponent,
        not_like_this: str | DialecticalComponent = "",
    ) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        if isinstance(not_like_this, DialecticalComponent):
            not_like_this = not_like_this.statement
        return {
            "computed_fields": {"thesis": thesis, "not_like_this": not_like_this},
        }

    @prompt_template()
    def prompt_antithesis_negative_side(
        self,
        antithesis: str | DialecticalComponent,
        not_like_this: str | DialecticalComponent = "",
    ) -> Messages.Type:
        tpl: list[BaseMessageParam] = self.prompt_thesis_negative_side(
            antithesis, not_like_this
        )
        # Replace the technical terms in the prompt, so that it makes sense when passed in the history
        for i in range(len(tpl)):
            if tpl[i].content:
                tpl[i].content = dc_safe_replace(
                    tpl[i].content,
                    {
                        ALIAS_T: ALIAS_A,
                        ALIAS_T_MINUS: ALIAS_A_MINUS,
                        ALIAS_A_MINUS: ALIAS_T_MINUS,
                    },
                )
        return tpl

    @prompt_template(
    """
    A contradictory/semantic opposition presents a direct semantic opposition and/or contradiction to the original statement that excludes their mutual coexistence. For instance, Happiness vs. Unhappiness; Truthfulness vs. Lie/Deceptiveness; Dependence vs. Independence.

    Generate a positive side or outcome (T+) of a thesis "{thesis}" (T), representing its constructive (balanced) form/side, that is also the contradictory/semantic opposition of "{antithesis_negative}" (A-).
    
    Make sure that T+ is truly connected to the semantic T, representing its positive and constructive side or outcome that is also highly perceptive, nuanced, gentle, evolving, and instrumental in solving problems and creating friendships. For instance, T+ = Trust can be seen as the constructive side of T = Courage. T+ = Kindness and Empathy are natural constructive outcomes of T = Love.

    If more than one T+ exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity.

    Output the dialectical component T+ and explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-".
    """
    )
    def prompt_thesis_positive_side(
        self,
        thesis: str | DialecticalComponent,
        antithesis_negative: str | DialecticalComponent,
    ) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        if isinstance(antithesis_negative, DialecticalComponent):
            antithesis_negative = antithesis_negative.statement
        return {
            "computed_fields": {
                "thesis": thesis,
                "antithesis_negative": antithesis_negative,
            },
        }

    @prompt_template()
    def prompt_antithesis_positive_side(
        self,
        antithesis: str | DialecticalComponent,
        thesis_negative: str | DialecticalComponent,
    ) -> Messages.Type:
        tpl: list[BaseMessageParam] = self.prompt_thesis_positive_side(
            antithesis, thesis_negative
        )
        # Replace the technical terms in the prompt, so that it makes sense when passed in the history
        for i in range(len(tpl)):
            if tpl[i].content:
                tpl[i].content = dc_safe_replace(
                    tpl[i].content,
                    {
                        ALIAS_T: ALIAS_A,
                        ALIAS_T_PLUS: ALIAS_A_PLUS,
                        ALIAS_A_MINUS: ALIAS_T_MINUS,
                    },
                )
        return tpl

    @prompt_template()
    @abstractmethod
    def prompt_next(self, wu_so_far: WisdomUnit) -> Messages.Type: ...

    @with_langfuse()
    async def find_thesis(
        self, *, ai_provider: str | None = None, ai_model: str | None = None
    ) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_thesis_call() -> DialecticalComponent:
            return self.prompt_thesis(self._text)

        return await _find_thesis_call()

    @with_langfuse()
    async def find_antithesis(
        self,
        thesis: str,
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_antithesis_call() -> DialecticalComponent:
            return self.prompt_antithesis(thesis)

        return await _find_antithesis_call()

    @with_langfuse()
    async def find_thesis_negative_side(
        self,
        thesis: str,
        not_like_this: str = "",
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_thesis_negative_side_call() -> DialecticalComponent:
            return self.prompt_thesis_negative_side(thesis, not_like_this)

        return await _find_thesis_negative_side_call()

    @with_langfuse()
    async def find_antithesis_negative_side(
        self,
        thesis: str,
        not_like_this: str = "",
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_antithesis_negative_side_call() -> DialecticalComponent:
            return self.prompt_antithesis_negative_side(thesis, not_like_this)

        return await _find_antithesis_negative_side_call()

    @with_langfuse()
    async def find_thesis_positive_side(
        self,
        thesis: str,
        antithesis_negative: str,
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_thesis_positive_side_call() -> DialecticalComponent:
            return self.prompt_thesis_positive_side(thesis, antithesis_negative)

        return await _find_thesis_positive_side_call()

    @with_langfuse()
    async def find_antithesis_positive_side(
        self,
        thesis: str,
        antithesis_negative: str,
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> DialecticalComponent:
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponent,
        )
        async def _find_antithesis_positive_side_call() -> DialecticalComponent:
            return self.prompt_antithesis_positive_side(thesis, antithesis_negative)

        return await _find_antithesis_positive_side_call()

    @with_langfuse()
    async def find_next(
        self,
        wu_so_far: WisdomUnit,
        *,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> DialecticalComponentsBox:
        """
        Raises:
            StopIteration: if nothing needs to be found anymore
        """
        overridden_ai_provider, overridden_ai_model = self._fix_ai_provider_and_model(
            ai_provider, ai_model
        )
        if overridden_ai_provider == "bedrock":
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = (
                self._fix_ai_provider_and_model("litellm")
            )

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponentsBox,
        )
        async def _find_next_call() -> DialecticalComponentsBox:
            return self.prompt_next(wu_so_far)

        return await _find_next_call()

    async def generate(self, thesis: str | DialecticalComponent = None) -> WisdomUnit:
        wu = WisdomUnit()

        if thesis is not None:
            if isinstance(thesis, DialecticalComponent):
                if thesis.alias != ALIAS_T:
                    raise ValueError(
                        f"The thesis cannot be a dialectical component with alias '{thesis.alias}'"
                    )
                wu.t = thesis
            else:
                wu.t = DialecticalComponent.from_str(
                    ALIAS_T, thesis, "Provided as string"
                )
        else:
            wu.t = await self.find_thesis()

        self._wisdom_unit = await self._fill_with_reason(wu)
        return self._wisdom_unit

    async def _fill_with_reason(self, wu: WisdomUnit) -> WisdomUnit:
        empty_count = len(wu.alias_to_field)
        for alias in wu.alias_to_field:
            if wu.is_set(alias):
                empty_count -= 1

        try:
            ci = 0
            while ci < empty_count:
                if wu.is_complete():
                    break
                """
                We assume here, that with every iteration we will find a new dialectical component(s).
                If we keep finding the same ones (or not find at all), we will still avoid the infinite loop - that's good.
                """
                dc: DialecticalComponentsBox = await self.find_next(wu)
                for d in dc.dialectical_components:
                    if wu.get(d.alias):
                        # Don't override if we already have it
                        continue
                    else:
                        setattr(wu, d.alias, d)
                        ci += 1
        except StopIteration:
            pass

        return wu

    async def redefine(
        self,
        *,  # ← everything after * is keyword-only
        original: WisdomUnit | None = None,
        **modified_dialectical_components,
    ) -> WisdomUnit:

        warnings: dict[str, list[str]] = {}

        if original is None:
            original = self._wisdom_unit

        if original is None:
            raise ValueError("Wisdom unit is not generated yet.")

        # Replace it in case the parameter "original" was given
        self._wisdom_unit = original

        changed: dict[str, str] = {
            k: str(v)
            for k, v in modified_dialectical_components.items()
            if k in WisdomUnit.__pydantic_fields__
        }

        new_wu: WisdomUnit = WisdomUnit()

        # ==
        # Redefine opposition
        # ==
        base = "t"
        other = "a" if base == "t" else "t"

        for dialectical_component in [base, other]:
            if changed.get(dialectical_component):
                setattr(
                    new_wu,
                    dialectical_component,
                    DialecticalComponent(
                        alias=new_wu.__pydantic_fields__.get(
                            dialectical_component
                        ).alias,
                        statement=changed.get(dialectical_component),
                        explanation=f"{new_wu.__pydantic_fields__.get(dialectical_component).alias} redefined.",
                    ),
                )
            else:
                new_wu.dialectical_component_copy_from(original, dialectical_component)

        alias_base = "T" if base == "t" else "A"
        alias_other = "A" if base == "t" else "T"

        if changed.get(base) or changed.get(other):
            check1 = check(
                is_valid_opposition,
                getattr(new_wu, base).statement,
                getattr(new_wu, other).statement,
            )

            if not check1.valid:
                if changed.get(base) and not changed.get(other):
                    # base side changed
                    o = await self.find_antithesis(getattr(new_wu, base).statement)
                    assert isinstance(o, DialecticalComponent)
                    o.explanation = f"REGENERATED. {o.explanation}"
                    setattr(new_wu, other, o)
                    changed[other] = o.statement
                    check1.valid = 1
                    check1.explanation = "Regenerated, therefore must be valid."
                elif changed.get(other) and not changed.get(base):
                    # other side changed
                    bm = await self.find_antithesis(getattr(new_wu, other).statement)
                    assert isinstance(bm, DialecticalComponent)
                    bm.explanation = f"REGENERATED. {bm.explanation}"
                    setattr(new_wu, base, bm)
                    changed[base] = bm.statement
                    check1.valid = 1
                    check1.explanation = "Regenerated, therefore must be valid."

            if not check1.valid:
                getattr(new_wu, base).statement = (
                    f"ERROR: {getattr(new_wu, base).statement}"
                )
                getattr(new_wu, other).statement = (
                    f"ERROR: {getattr(new_wu, other).statement}"
                )
                warnings.setdefault(alias_base, []).append(check1.explanation)
                warnings.setdefault(alias_other, []).append(check1.explanation)
                raise AssertionError(f"{alias_base}, {alias_other}", warnings, new_wu)

        else:
            # Keep originals
            pass

        # NOTE: At this point we are sure that T and A are present and valid in the new wheel

        # ==
        # Redefine diagonal relations
        # ==
        for side in ["t", "a"]:
            base = side
            other = "a" if base == "t" else "t"

            base_negative_side_fn = (
                self.find_thesis_negative_side
                if side == "t"
                else self.find_antithesis_negative_side
            )
            other_positive_side_fn = (
                self.find_antithesis_positive_side
                if side == "t"
                else self.find_thesis_positive_side
            )

            base_minus = "t_minus" if side == "t" else "a_minus"
            base_plus = "t_plus" if side == "t" else "a_plus"
            other_plus = "a_plus" if side == "t" else "t_plus"
            other_minus = "a_minus" if side == "t" else "t_minus"

            alias_base_minus = "T-" if side == "t" else "A-"
            alias_other_plus = "A+" if side == "t" else "T+"

            for dialectical_component in [base_minus, other_plus]:
                if changed.get(dialectical_component):
                    setattr(
                        new_wu,
                        dialectical_component,
                        DialecticalComponent(
                            alias=new_wu.__pydantic_fields__.get(
                                dialectical_component
                            ).alias,
                            statement=changed.get(dialectical_component),
                            explanation=f"{new_wu.__pydantic_fields__.get(dialectical_component).alias} redefined.",
                        ),
                    )
                else:
                    new_wu.dialectical_component_copy_from(
                        original, dialectical_component
                    )

            if (changed.get(base) or changed.get(base_minus)) or (
                changed.get(other) or changed.get(other_plus)
            ):
                if changed.get(base_minus) or changed.get(base):
                    check2 = check(
                        is_negative_side,
                        getattr(new_wu, base_minus).statement,
                        getattr(new_wu, base).statement,
                    )

                    if not check2.valid:
                        if changed.get(base) and not changed.get(base_minus):
                            not_like_other_minus = ""
                            if hasattr(new_wu, other_minus):
                                if getattr(new_wu, other_minus):
                                    not_like_other_minus = getattr(
                                        new_wu, other_minus
                                    ).statement
                            bm = await base_negative_side_fn(
                                getattr(new_wu, base).statement, not_like_other_minus
                            )
                            assert isinstance(bm, DialecticalComponent)
                            bm.explanation = f"REGENERATED. {bm.explanation}"
                            setattr(new_wu, base_minus, bm)
                            changed[base_minus] = bm.statement
                            check2.valid = True
                            check2.explanation = "Regenerated, therefore must be valid."

                    if not check2.valid:
                        getattr(new_wu, base_minus).statement = (
                            f"ERROR: {getattr(new_wu, base_minus).statement}"
                        )
                        warnings.setdefault(alias_base_minus, []).append(
                            check2.explanation
                        )
                        raise AssertionError(f"{alias_base_minus}", warnings, new_wu)

                # NOTE: At this point we are sure that BASE and BASE- are present and valid between themselves in the new wheel

                other_plus_regenerated = False
                if changed.get(other_plus) or changed.get(other):
                    check3 = check(
                        is_positive_side,
                        getattr(new_wu, other_plus).statement,
                        getattr(new_wu, other).statement,
                    )

                    if not check3.valid:
                        if changed.get(other) and not changed.get(other_plus):
                            op = await other_positive_side_fn(
                                getattr(new_wu, other).statement,
                                getattr(new_wu, base_minus).statement,
                            )
                            assert isinstance(op, DialecticalComponent)
                            op.explanation = f"REGENERATED. {op.explanation}"
                            setattr(new_wu, other_plus, op)
                            changed[other_plus] = op.statement
                            check3.valid = True
                            check3.explanation = "Regenerated, therefore must be valid."
                            other_plus_regenerated = True

                    if not check3.valid:
                        getattr(new_wu, other_plus).statement = (
                            f"ERROR: {getattr(new_wu, other_plus).statement}"
                        )
                        warnings.setdefault(alias_other_plus, []).append(
                            check3.explanation
                        )
                        raise AssertionError(f"{alias_other_plus}", warnings, new_wu)

                # NOTE: At this point we are sure that OTHER and OTHER- are present and valid between themselves in the new wheel

                additional_diagonal_check_skip = other_plus_regenerated or (
                    not changed.get(base_minus) and not changed.get(other_plus)
                )

                if not additional_diagonal_check_skip:
                    check4 = check(
                        is_strict_opposition,
                        getattr(new_wu, base_minus).statement,
                        getattr(new_wu, other_plus).statement,
                    )
                    if not check4.valid:
                        if changed.get(base_minus) and not changed.get(other_plus):
                            # base side changed
                            op = await other_positive_side_fn(
                                getattr(new_wu, other).statement,
                                getattr(new_wu, base_minus).statement,
                            )
                            assert isinstance(op, DialecticalComponent)
                            op.explanation = f"REGENERATED. {op.explanation}"
                            setattr(new_wu, other_plus, op)
                            changed[other_plus] = op.statement
                            check4.valid = True
                            check4.explanation = "Regenerated, therefore must be valid."
                        elif changed.get(other_plus) and not changed.get(base_minus):
                            # other side changed
                            not_like_other_minus = ""
                            if hasattr(new_wu, other_minus):
                                if getattr(new_wu, other_minus):
                                    not_like_other_minus = getattr(
                                        new_wu, other_minus
                                    ).statement
                            bm = await base_negative_side_fn(
                                getattr(new_wu, base).statement, not_like_other_minus
                            )
                            assert isinstance(bm, DialecticalComponent)
                            bm.explanation = f"REGENERATED. {bm.explanation}"
                            setattr(new_wu, base_minus, bm)
                            changed[base_minus] = bm.statement
                            check4.valid = True
                            check4.explanation = "Regenerated, therefore must be valid."

                    if not check4.valid:
                        getattr(new_wu, base_minus).statement = (
                            f"ERROR: {getattr(new_wu, base_minus).statement}"
                        )
                        getattr(new_wu, other_plus).statement = (
                            f"ERROR: {getattr(new_wu, other_plus).statement}"
                        )
                        warnings.setdefault(alias_base_minus, []).append(
                            check4.explanation
                        )
                        warnings.setdefault(alias_other_plus, []).append(
                            check4.explanation
                        )
                        raise AssertionError(
                            f"{alias_base_minus}, {alias_other_plus}", warnings, new_wu
                        )

                # NOTE: At this point we are sure that diagonals are present and valid in the new wheel

            else:
                # Keep originals
                pass

        return new_wu

    def _fix_ai_provider_and_model(
        self, ai_provider: str | None = None, ai_model: str | None = None
    ) -> tuple[str, str]:
        current_provider, current_model = self._ai_provider, self._ai_model

        if ai_provider == "litellm":
            if not ai_model:
                if not current_provider and not current_model:
                    raise ValueError("ai_model not provided.")
                else:
                    return ai_provider, f"{current_provider}/{current_model}"
            else:
                if not "/" in ai_model:
                    if not current_provider:
                        raise ValueError(
                            "ai_model must be in the form of 'provider/model' for litellm."
                        )
                    else:
                        return ai_provider, f"{current_provider}/{ai_model}"
                else:
                    return ai_provider, ai_model

        if not ai_model and not ai_provider:
            if Config.PROVIDER or Config.MODEL or current_provider or current_model:
                return self._fix_ai_provider_and_model(
                    Config.PROVIDER if not current_provider else current_provider,
                    Config.MODEL if not current_model else current_model,
                )
            else:
                raise ValueError(
                    "Cannot fallback to default model as they're not present"
                )

        if not ai_provider:
            if not "/" in ai_model:
                raise ValueError(
                    "ai_model must be in the form of 'provider/model' if ai_provider is not specified."
                )
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                return derived_ai_provider, derived_ai_model
        else:
            if not "/" in ai_model:
                return ai_provider, ai_model
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                if derived_ai_provider != ai_provider:
                    raise ValueError(
                        f"ai_provider '{ai_provider}' does not match ai_model '{ai_model}'"
                    )
                return derived_ai_provider, derived_ai_model
