from __future__ import annotations

import inspect
from abc import abstractmethod
from typing import Self

from dependency_injector.wiring import Provide
from mirascope import BaseMessageParam, Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework import Rationale
from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.dto_mapper import (map_from_dto,
                                                     map_list_from_dto)
from dialectical_framework.synthesist.domain.dialectical_analysis import DialecticalAnalysis
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.enums.di import DI
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.reloadable import Reloadable
from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_safe_replace
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.validator.basic_checks import (check,
                                                          is_negative_side,
                                                          is_positive_side,
                                                          is_strict_opposition,
                                                          is_valid_opposition)
from dialectical_framework.synthesist.domain.wheel_segment import (ALIAS_T, ALIAS_T_MINUS,
                                                                   ALIAS_T_PLUS)
from dialectical_framework.synthesist.domain.wisdom_unit import (ALIAS_A, ALIAS_A_MINUS,
                                                                 ALIAS_A_PLUS, WisdomUnit)


class PolarityReasoner(HasBrain, Reloadable):
    def __init__(
        self,
        *,
        text: str = "",
    ):
        self._text = text
        self._wisdom_unit = None

        self._mode: DialecticalReasoningMode = DialecticalReasoningMode.GENERAL_CONCEPTS

        self._analysis = DialecticalAnalysis(corpus=self._text)

    @property
    def text(self) -> str:
        return self._text

    def reload(
        self, *, text: str, perspectives: WisdomUnit | list[WisdomUnit] = None
    ) -> Self:
        self._text = text
        if not perspectives:
            perspectives = []
        if isinstance(perspectives, WisdomUnit):
            perspectives = [perspectives]

        self._analysis = DialecticalAnalysis(
            corpus=text,
            perspectives=perspectives,
        )

        if perspectives:
            # Take first perspective as active
            self._wisdom_unit = perspectives[-1]
        else:
            self._wisdom_unit = None
        return self

    @prompt_template(
        """
        USER:
        {start}
        
        USER:
        Extract the central idea or the primary thesis (denote it as T) of the context with minimal distortion. If already concise (single word/phrase/clear thesis), keep it intact; only condense verbose messages while preserving original meaning.
    
        Output the dialectical component T within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" in the explanation. 
        """
    )
    def prompt_thesis(
        self, text: str = None, config: Settings = Provide[DI.settings]
    ) -> Messages.Type:
        return {
            "computed_fields": {
                # Sometimes we don't want the whole user input again, as we're calculating the thesis within a longer analysis
                "start": (
                    "<context>" + inspect.cleandoc(text) + "</context>"
                    if text
                    else "Ok."
                ),
                "component_length": config.component_length,
            },
        }

    @prompt_template(
        """
        A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.
        
        Generate a dialectical opposition (A) of the thesis "{thesis}" (T). Be detailed enough to show deep understanding, yet concise enough to maintain clarity. Generalize all of them using up to 6 words.
    
        Output the dialectical component A within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T" or "A" in the explanation.
        """
    )
    def prompt_antithesis(
        self, thesis: str | DialecticalComponent, config: Settings = Provide[DI.settings]
    ) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        return {
            "computed_fields": {
                "thesis": thesis,
                "component_length": config.component_length,
            },
        }

    @prompt_template(
        """
        Generate a negative side (T-) of a thesis "{thesis}" (T), representing its strict semantic exaggeration and overdevelopment, as if the author of T lost his inner control. Make sure that T- is not the same as: "{not_like_this}".
    
        For instance, if T = Courage, then T- = Foolhardiness. If T = Love, then T- = Obsession, Fixation, Loss of Mindfulness. If T = Fear, then T- = Paranoia. If T = Hate and Indifference then T- = Malevolence and Apathy.
    
        If more than one T- exists, provide a generalized representation that encompasses their essence. Be detailed enough to show deep understanding, yet concise enough to maintain clarity. For instance, T- = "Obsession, Fixation, Loss of Mindfulness" can be generalized into T- = Mental Preoccupation
    
        Output the dialectical component T- within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T-" or "A-" in the explanation.
        """
    )
    def prompt_thesis_negative_side(
        self,
        thesis: str | DialecticalComponent,
        not_like_this: str | DialecticalComponent = "",
        config: Settings = Provide[DI.settings],
    ) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        if isinstance(not_like_this, DialecticalComponent):
            not_like_this = not_like_this.statement
        return {
            "computed_fields": {
                "thesis": thesis,
                "not_like_this": not_like_this,
                "component_length": config.component_length,
            },
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
    
        Output the dialectical component T+  within {component_length} word(s), the shorter, the better. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-" in the explanation.
        """
    )
    def prompt_thesis_positive_side(
        self,
        thesis: str | DialecticalComponent,
        antithesis_negative: str | DialecticalComponent,
        config: Settings = Provide[DI.settings],
    ) -> Messages.Type:
        if isinstance(thesis, DialecticalComponent):
            thesis = thesis.statement
        if isinstance(antithesis_negative, DialecticalComponent):
            antithesis_negative = antithesis_negative.statement
        return {
            "computed_fields": {
                "thesis": thesis,
                "antithesis_negative": antithesis_negative,
                "component_length": config.component_length,
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

    @prompt_template(
        """
        MESSAGES:
        {wu_construction}
    
        USER:
        Identifying Positive and Negative Syntheses

        USER:
        Consider the dialectical components identified in previous analysis:
        {wu_dcs:list}
        
        For the pair of thesis and antithesis, identify both positive synthesis (S+) and negative synthesis (S-):
        
        S+ (Positive Synthesis): The emergent quality that arises when the positive/constructive aspects (T+ and A+) are combined in complementary harmony. This represents a new dimension where 1+1>2, expanding possibilities while preserving the unique value of each component. Consider the birth of a child from two parents, or binocular vision producing depth perception.

        S- (Negative Synthesis): The uniformity that results when negative/exaggerated aspects (T- and A-) reinforce each other. This represents reduction of dimensionality where 1+1<2, increasing intensity along limited axes at the expense of diversity. Examples include pendulums aligning their rhythms, or centralized rules that suppress variation.
         
        Output the dialectical components S+ and S-. Compose the explanation how it was derived in the passive voice. Don't mention any special denotations such as "T", "T+" or "A-" in the explanation. To the explanation add a concrete real life example.
        """
    )
    def prompt_synthesis(self, wisdom_unit: WisdomUnit) -> Messages.Type:
        tpl = ReverseEngineer.till_wisdom_units(
            wisdom_units=[wisdom_unit], text=self._analysis.corpus
        )
        wu_dcs = []
        for field, alias in wisdom_unit.field_to_alias.items():
            dc = wisdom_unit.get(alias)
            if not dc:
                continue
            wu_dcs.append(f"{alias} = {dc.statement}")
        return {
            "computed_fields": {
                "wu_construction": tpl,
                "wu_dcs": wu_dcs,
            },
        }

    @prompt_template()
    @abstractmethod
    def prompt_next(self, wu_so_far: WisdomUnit) -> Messages.Type: ...

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentDto)
    async def find_thesis(self) -> DialecticalComponentDto:
        return self.prompt_thesis(self._text)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentDto)
    async def find_antithesis(
        self,
        thesis: str,
    ) -> DialecticalComponentDto:
        return self.prompt_antithesis(thesis)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentDto)
    async def find_thesis_negative_side(
        self,
        thesis: str,
        not_like_this: str = "",
    ) -> DialecticalComponentDto:
        return self.prompt_thesis_negative_side(thesis, not_like_this)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentDto)
    async def find_antithesis_negative_side(
        self,
        thesis: str,
        not_like_this: str = "",
    ) -> DialecticalComponentDto:
        return self.prompt_antithesis_negative_side(thesis, not_like_this)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentDto)
    async def find_thesis_positive_side(
        self,
        thesis: str,
        antithesis_negative: str,
    ) -> DialecticalComponentDto:
        return self.prompt_thesis_positive_side(thesis, antithesis_negative)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentDto)
    async def find_antithesis_positive_side(
        self,
        thesis: str,
        antithesis_negative: str,
    ) -> DialecticalComponentDto:
        return self.prompt_antithesis_positive_side(thesis, antithesis_negative)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentsDeckDto)
    async def find_next(
        self,
        wu_so_far: WisdomUnit,
    ) -> DialecticalComponentsDeckDto:
        """
        Raises:
            StopIteration: if nothing needs to be found anymore
        """
        prompt = self.prompt_next(wu_so_far)
        if self._analysis.perspectives:
            tpl = ReverseEngineer.till_wisdom_units(
                wisdom_units=self._analysis.perspectives, text=self._analysis.corpus
            )
        else:
            tpl = ReverseEngineer().prompt_input_text(text=self.text)

        return extend_tpl(tpl, prompt)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentsDeckDto)
    async def find_synthesis(
        self,
        wu: WisdomUnit,
    ) -> DialecticalComponentsDeckDto:
        return self.prompt_synthesis(wu)

    async def think(self, thesis: str | DialecticalComponent = None) -> WisdomUnit:
        # TODO: when thesis is a simple str, we need to actualize it with AI, where it comes from
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
        else:
            wu.t = map_from_dto(await self.find_thesis(), DialecticalComponent)

        self._wisdom_unit = await self._fill_with_reason(wu)
        self._analysis.perspectives.append(self._wisdom_unit)
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
                dc_deck_dto = await self.find_next(wu)
                dc_deck: DialecticalComponentsDeck = DialecticalComponentsDeck(dialectical_components=map_list_from_dto(dc_deck_dto.dialectical_components, DialecticalComponent))
                for dc in dc_deck.dialectical_components:
                    alias = dc.alias
                    if wu.get(alias):
                        # Don't override if we already have it
                        continue
                    else:
                        setattr(wu, alias, dc)
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
        """
        This method doesn't mutate the original WisdomUnit. It returns a fresh instance.
        """

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

        new_wu: WisdomUnit = WisdomUnit(reasoning_mode=original.reasoning_mode)

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
                        rationales=[
                            Rationale(
                                text=f"{new_wu.__pydantic_fields__.get(dialectical_component).alias} redefined."
                            )
                        ]
                    ),
                )
            else:
                new_wu.set_dialectical_component_as_copy_from_another_segment(original, dialectical_component)

        alias_base = "T" if base == "t" else "A"
        alias_other = "A" if base == "t" else "T"

        if changed.get(base) or changed.get(other):
            check1 = check(
                is_valid_opposition,
                self,
                getattr(new_wu, base).statement,
                getattr(new_wu, other).statement,
            )

            if not check1.valid:
                if changed.get(base) and not changed.get(other):
                    # base side changed
                    o = map_from_dto(await self.find_antithesis(getattr(new_wu, base).statement), DialecticalComponent)
                    assert isinstance(o, DialecticalComponent)
                    if o.best_rationale and o.best_rationale.text:
                        o.best_rationale.text = f"REGENERATED. {o.best_rationale.text}"
                    setattr(new_wu, other, o)
                    changed[other] = o.statement
                    check1.valid = 1
                    check1.explanation = "Regenerated, therefore must be valid."
                elif changed.get(other) and not changed.get(base):
                    # other side changed
                    bm = map_from_dto(await self.find_antithesis(getattr(new_wu, other).statement), DialecticalComponent)
                    assert isinstance(bm, DialecticalComponent)
                    if bm.best_rationale and bm.best_rationale.text:
                        bm.best_rationale.text = f"REGENERATED. {bm.best_rationale.text}"
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
                            rationales=[
                                Rationale(
                                    text=f"{new_wu.__pydantic_fields__.get(dialectical_component).alias} redefined."
                                )
                            ]
                        ),
                    )
                else:
                    new_wu.set_dialectical_component_as_copy_from_another_segment(
                        original, dialectical_component
                    )

            if (changed.get(base) or changed.get(base_minus)) or (
                changed.get(other) or changed.get(other_plus)
            ):
                if changed.get(base_minus) or changed.get(base):
                    check2 = check(
                        is_negative_side,
                        self,
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
                            bm = map_from_dto(await base_negative_side_fn(
                                getattr(new_wu, base).statement, not_like_other_minus
                            ), DialecticalComponent)
                            assert isinstance(bm, DialecticalComponent)
                            if bm.best_rationale and bm.best_rationale.text:
                                bm.best_rationale.text = f"REGENERATED. {bm.best_rationale.text}"
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
                        self,
                        getattr(new_wu, other_plus).statement,
                        getattr(new_wu, other).statement,
                    )

                    if not check3.valid:
                        if changed.get(other) and not changed.get(other_plus):
                            op = map_from_dto(await other_positive_side_fn(
                                getattr(new_wu, other).statement,
                                getattr(new_wu, base_minus).statement,
                            ), DialecticalComponent)
                            assert isinstance(op, DialecticalComponent)
                            if op.best_rationale and op.best_rationale.text:
                                op.best_rationale.text = f"REGENERATED. {op.best_rationale.text}"
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
                        self,
                        getattr(new_wu, base_minus).statement,
                        getattr(new_wu, other_plus).statement,
                    )
                    if not check4.valid:
                        if changed.get(base_minus) and not changed.get(other_plus):
                            # base side changed
                            op = map_from_dto(await other_positive_side_fn(
                                getattr(new_wu, other).statement,
                                getattr(new_wu, base_minus).statement,
                            ), DialecticalComponent)
                            assert isinstance(op, DialecticalComponent)
                            if op.best_rationale and op.best_rationale.text:
                                op.best_rationale.text = f"REGENERATED. {op.best_rationale.text}"
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
                            bm = map_from_dto(await base_negative_side_fn(
                                getattr(new_wu, base).statement, not_like_other_minus
                            ), DialecticalComponent)
                            assert isinstance(bm, DialecticalComponent)
                            if bm.best_rationale and bm.best_rationale.text:
                                bm.best_rationale.text = f"REGENERATED. {bm.best_rationale.text}"
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
