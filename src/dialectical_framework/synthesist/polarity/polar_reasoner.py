from __future__ import annotations

from typing import final

from dependency_injector.wiring import Provide, inject
from mirascope import BaseMessageParam, Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.graph_mapper import component_from_dto
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wisdom_unit import (
    WisdomUnit,
    POSITION_T,
    POSITION_T_PLUS,
    POSITION_T_MINUS,
    POSITION_A,
    POSITION_A_PLUS,
    POSITION_A_MINUS,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
    TRelationship,
    ARelationship,
)
from dialectical_framework.protocols.antithesis_extractor import AntithesisExtractor
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.polarity_finder import PolarityFinder
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

# Import for type hints
from typing import TYPE_CHECKING, Union
if TYPE_CHECKING:
    from gqlalchemy import Memgraph, Neo4j
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.ideas import Ideas


class PolarReasoner(HasBrain):
    """
    Stateless polar reasoner that takes text as method parameter.

    Generates WisdomUnits from thesis/antithesis pairs through dialectical reasoning.
    """

    def __init__(
        self,
        polarity_finder: PolarityFinder = Provide[DI.polarity_finder],
        antithesis_extractor: AntithesisExtractor = Provide[DI.antithesis_extractor],
    ):
        self._polarity_finder = polarity_finder
        self._antithesis_extractor = antithesis_extractor

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
    ) -> "Messages.Type":
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
    ) -> "Messages.Type":
        tpl: list[BaseMessageParam] = self.prompt_thesis_negative_side(
            antithesis, not_like_this
        )
        # Replace the technical terms in the prompt, so that it makes sense when passed in the history
        for i in range(len(tpl)):
            if tpl[i].content:
                tpl[i].content = dc_safe_replace(
                    tpl[i].content,
                    {
                        POSITION_T: POSITION_A,
                        POSITION_T_MINUS: POSITION_A_MINUS,
                        POSITION_A_MINUS: POSITION_T_MINUS,
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
    ) -> "Messages.Type":
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
    ) -> "Messages.Type":
        tpl: list[BaseMessageParam] = self.prompt_thesis_positive_side(
            antithesis, thesis_negative
        )
        # Replace the technical terms in the prompt, so that it makes sense when passed in the history
        for i in range(len(tpl)):
            if tpl[i].content:
                tpl[i].content = dc_safe_replace(
                    tpl[i].content,
                    {
                        POSITION_T: POSITION_A,
                        POSITION_T_PLUS: POSITION_A_PLUS,
                        POSITION_A_MINUS: POSITION_T_MINUS,
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
    def prompt_synthesis(self, wisdom_unit: WisdomUnit, *, text: str) -> "Messages.Type":
        tpl = ReverseEngineer.till_wisdom_units(
            wisdom_units=[wisdom_unit], text=text
        )
        wu_dcs = []
        # Iterate through all 6 core positions
        for position in wisdom_unit.core_positions:
            manager = wisdom_unit.get_relationship_manager_by_position(position)
            result = manager.get()
            if not result:
                continue
            dc, rel = result
            # Access alias attribute from PolarityRelationship object
            from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship
            alias = rel.alias if isinstance(rel, PolarityRelationship) else position
            wu_dcs.append(f"{alias} = {dc.statement}")
        return {
            "computed_fields": {
                "wu_construction": tpl,
                "wu_dcs": wu_dcs,
            },
        }

    @prompt_template()
    def prompt_next(self, wu_so_far: WisdomUnit) -> "Messages.Type":
        """
        Raises:
            ValueError: If the wisdom unit is incorrect.
            StopIteration: If the wisdom unit is complete already.
        """
        # Get component at T position
        t_result = wu_so_far.t.get()
        if not t_result:
            raise ValueError("T - not present")
        t = t_result[0]

        prompt_messages = []

        t_minus_result = wu_so_far.t_minus.get()
        if not t_minus_result:
            a_minus_result = wu_so_far.a_minus.get()
            a_minus = a_minus_result[0] if a_minus_result else None
            prompt_messages.extend(
                self.prompt_thesis_negative_side(
                    t, a_minus if a_minus else ""
                )
            )
            return prompt_messages
        t_minus = t_minus_result[0]

        a_result = wu_so_far.a.get()
        if not a_result:
            raise ValueError("A - not present")
        a = a_result[0]

        a_minus_result = wu_so_far.a_minus.get()
        if not a_minus_result:
            prompt_messages.extend(
                self.prompt_antithesis_negative_side(
                    a, t_minus if t_minus else ""
                )
            )
            return prompt_messages
        a_minus = a_minus_result[0]

        t_plus_result = wu_so_far.t_plus.get()
        if not t_plus_result:
            prompt_messages.extend(
                self.prompt_thesis_positive_side(t, a_minus)
            )
            return prompt_messages
        t_plus = t_plus_result[0]

        a_plus_result = wu_so_far.a_plus.get()
        if not a_plus_result:
            prompt_messages.extend(
                self.prompt_antithesis_positive_side(a, t_minus)
            )
            return prompt_messages
        a_plus = a_plus_result[0]

        raise StopIteration("The wisdom unit is complete, nothing to do.")

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
        *,
        text: str,
        perspectives: list[WisdomUnit] | None = None,
    ) -> DialecticalComponentsDeckDto:
        """
        Find the next missing component in a WisdomUnit.

        Args:
            wu_so_far: The WisdomUnit being built
            text: Source text context
            perspectives: Optional list of existing WisdomUnits for context.
                         If provided, they are used to build conversation history.

        Raises:
            StopIteration: if nothing needs to be found anymore
        """
        prompt = self.prompt_next(wu_so_far)
        if perspectives:
            tpl = ReverseEngineer.till_wisdom_units(
                wisdom_units=perspectives, text=text
            )
        else:
            tpl = ReverseEngineer().prompt_input_text(text=text)

        return extend_tpl(tpl, prompt)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentsDeckDto)
    async def find_synthesis(
        self,
        wu: WisdomUnit,
        *,
        text: str,
    ) -> DialecticalComponentsDeckDto:
        return self.prompt_synthesis(wu, text=text)

    @final
    async def _find_polarity(
        self,
        *,
        source: Union[Input, Ideas],
        thesis: str | DialecticalComponent | DialecticalComponentDto = None,
        antithesis: str | DialecticalComponent | DialecticalComponentDto = None
    ) -> tuple[DialecticalComponent, DialecticalComponent]:
        """
        Find polarity pair (thesis, antithesis) as graph nodes.

        Args:
            source: Input or Ideas node for extraction context
            thesis: statement text, graph-native node, or DTO
            antithesis: statement text, graph-native node, or DTO

        Returns graph nodes (already connected to source.statements with OPPOSITE_OF relationship).
        """
        # Helper to normalize input to what polarity_finder expects (DialecticalComponent, str, or None)
        def normalize_input(input_val) -> DialecticalComponent | str | None:
            if isinstance(input_val, DialecticalComponent):
                return input_val  # Pass graph node directly
            elif isinstance(input_val, DialecticalComponentDto):
                # Convert DTO to graph node (includes rationale creation)
                if not input_val.statement:
                    return None  # Treat empty statement as None
                return component_from_dto(input_val)
            else:
                return input_val or None  # String or None, treat "" as None

        # If both are already graph nodes, return them directly
        if isinstance(thesis, DialecticalComponent) and isinstance(antithesis, DialecticalComponent):
            return thesis, antithesis

        # Extract polarities using polarity finder (returns graph nodes)
        # Pass DialecticalComponents directly to avoid creating redundant nodes
        polarity = await self._polarity_finder.extract_polarities(
            source=source,
            given=[(normalize_input(thesis), normalize_input(antithesis))]
        )
        t_node, a_node = polarity[0]

        return t_node, a_node

    @final
    async def think(
        self,
        *,
        source: Union[Input, Ideas],
        text: str,
        thesis: str | DialecticalComponent | DialecticalComponentDto = None,
        antithesis: str | DialecticalComponent | DialecticalComponentDto = None,
        intent: str = "preset:general_concepts",
        nexus: Nexus | None = None,
    ) -> WisdomUnit:
        """
        Core reasoning method that generates a WisdomUnit from thesis and antithesis.

        Args:
            source: Input or Ideas node (for SOA extractors)
            text: Source text context for AI prompts
            thesis: String statement, graph-native DialecticalComponent, or DialecticalComponentDto
            antithesis: String statement, graph-native DialecticalComponent, or DialecticalComponentDto
            intent: The reasoning intent (default: "preset:general_concepts")
            nexus: Optional Nexus to connect the WU to (for querying sibling WUs)

        Returns:
            Graph-native WisdomUnit persisted to the database
        """
        # Query perspectives from nexus if provided
        perspectives: list[WisdomUnit] = []
        if nexus:
            perspectives = [wu for wu, _ in nexus.wisdom_units.all()]

        # Use _find_polarity to get graph nodes
        # polarity_finder now returns graph nodes (already connected to source.statements)
        t, a = await self._find_polarity(source=source, thesis=thesis, antithesis=antithesis)
        t_alias = POSITION_T
        a_alias = POSITION_A

        # Create graph WisdomUnit
        wu = WisdomUnit(intent=intent)
        wu.save()  # Save the WU node first

        # Connect components with typed relationships (validates alias at creation)
        wu.t.connect(t, relationship=TRelationship(alias=t_alias))
        wu.a.connect(a, relationship=ARelationship(alias=a_alias))

        # Connect to nexus if provided
        if nexus:
            wu.nexus.connect(nexus)

        return await self._fill_with_reason(wu, text=text, perspectives=perspectives)

    def _field_to_alias(self, field: str) -> str:
        """
        Map relationship manager field names to component aliases (6 core positions only).

        TODO: Refactor to use POSITION_* constants (from wisdom_unit module) directly throughout
        instead of lowercase field names. This legacy mapping is only needed for
        compatibility with existing redefine() logic that uses field names like
        't', 'a', 't_plus', etc. Should be removed once redefine() is refactored.
        """
        field_to_alias_map = {
            't': 'T',
            'a': 'A',
            't_plus': 'T+',
            't_minus': 'T-',
            'a_plus': 'A+',
            'a_minus': 'A-',
        }
        return field_to_alias_map.get(field, field.upper())

    async def _fill_with_reason(
        self,
        wu: WisdomUnit,
        *,
        text: str,
        perspectives: list[WisdomUnit] | None = None,
    ) -> WisdomUnit:
        empty_count = len(wu.core_positions)
        for position in wu.core_positions:
            if wu.is_set(position):
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
                dc_deck_dto = await self.find_next(wu, text=text, perspectives=perspectives)
                # Convert DTOs to graph components
                for dc_dto in dc_deck_dto.dialectical_components:
                    dto_alias = dc_dto.alias
                    # Extract position name from alias (strip numbers: 'T1' → 'T', 'A+2' → 'A+')
                    position_name = ''.join(c for c in dto_alias if not c.isdigit())

                    if wu.is_set(position_name):
                        # Don't override if we already have component at this position
                        continue
                    else:
                        # Convert DTO to graph component and connect with typed relationship
                        dc = component_from_dto(dc_dto)
                        manager = wu.get_relationship_manager_by_position(position_name)
                        # Create typed relationship for validation and type safety
                        rel = WisdomUnit.get_relationship_class_for_position(position_name)(alias=dto_alias)
                        manager.connect(dc, relationship=rel)
                        ci += 1
        except StopIteration:
            pass

        # Commit the WU now that all components are connected
        wu.commit()
        return wu

    @inject
    async def redefine(
        self,
        *,  # ← everything after * is keyword-only
        original: WisdomUnit,
        text: str = "",
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        **modified_dialectical_components,
    ) -> WisdomUnit:
        """
        This method doesn't mutate the original WisdomUnit. It returns a fresh instance.

        Args:
            original: The original WisdomUnit to base modifications on (required)
            text: Source text context for regeneration (if needed)
            **modified_dialectical_components: Field names (t, a, t_plus, etc.) mapped to new statement strings

        Returns:
            A new graph-native WisdomUnit with modifications applied
        """

        warnings: dict[str, list[str]] = {}

        # Valid field names for WisdomUnit (6 core positions only)
        valid_fields = {'t', 'a', 't_plus', 't_minus', 'a_plus', 'a_minus'}

        # Map field names to POSITION constants
        field_to_position = {
            't': POSITION_T,
            'a': POSITION_A,
            't_plus': POSITION_T_PLUS,
            't_minus': POSITION_T_MINUS,
            'a_plus': POSITION_A_PLUS,
            'a_minus': POSITION_A_MINUS,
        }

        # Convert keys to match POSITION_* constants
        changed: dict[str, str] = {
            field_to_position[k]: str(v)
            for k, v in modified_dialectical_components.items()
            if k in valid_fields
        }

        new_wu: WisdomUnit = WisdomUnit(intent=original.intent)
        new_wu.save()  # Save the new WU node first

        # ==
        # Redefine opposition
        # ==
        base_pos = POSITION_T
        other_pos = POSITION_A

        for position in [base_pos, other_pos]:
            if changed.get(position):
                # Check if statement actually changed
                orig_component = original.get_component(position)
                new_statement = changed.get(position)

                if orig_component and orig_component.statement == new_statement:
                    # Statement unchanged - reuse original component (keep same UID)
                    manager = new_wu.get_relationship_manager_by_position(position)
                    rel = WisdomUnit.get_relationship_class_for_position(position)(alias=position)
                    manager.connect(orig_component, relationship=rel)
                else:
                    # Statement changed - create new component with new UID
                    component = DialecticalComponent(
                        statement=new_statement
                    )
                    component.commit()

                    # Add rationale
                    rationale = Rationale(text=f"{position} redefined.")
                    rationale.set_explanation(component)
                    rationale.commit()  # Auto-connects to component

                    # Connect to new WU with typed relationship
                    manager = new_wu.get_relationship_manager_by_position(position)
                    rel = WisdomUnit.get_relationship_class_for_position(position)(alias=position)
                    manager.connect(component, relationship=rel)
            else:
                # Copy from original
                orig_component = original.get_component(position)
                if orig_component:
                    manager = new_wu.get_relationship_manager_by_position(position)
                    rel = WisdomUnit.get_relationship_class_for_position(position)(alias=position)
                    manager.connect(orig_component, relationship=rel)

        if changed.get(base_pos) or changed.get(other_pos):
            base_alias = base_pos
            other_alias = other_pos
            base_comp = new_wu.get_component(base_alias)
            other_comp = new_wu.get_component(other_alias)

            check1 = check(
                is_valid_opposition,
                self,
                base_comp.statement,
                other_comp.statement,
            )

            if not check1.valid:
                if changed.get(base_pos) and not changed.get(other_pos):
                    # base side changed - regenerate other
                    orig_other = original.get_component(other_pos)
                    o_dto = await self._antithesis_extractor.extract_single_antithesis(text=text, thesis=base_comp.statement)

                    # Check if regenerated statement matches original
                    if orig_other and orig_other.statement == o_dto.statement:
                        # Statement unchanged - reuse original component (keep same UID)
                        manager = new_wu.get_relationship_manager_by_position(other_alias)
                        rel = WisdomUnit.get_relationship_class_for_position(other_alias)(alias=other_alias)
                        manager.connect(orig_other, relationship=rel)
                        changed[other_pos] = orig_other.statement
                    else:
                        # Statement changed - create new component
                        o = component_from_dto(o_dto)
                        if o.best_rationale and o.best_rationale.text:
                            o.best_rationale.text = f"REGENERATED. {o.best_rationale.text}"
                        manager = new_wu.get_relationship_manager_by_position(other_alias)
                        rel = WisdomUnit.get_relationship_class_for_position(other_alias)(alias=other_alias)
                        manager.connect(o, relationship=rel)
                        changed[other_pos] = o.statement
                    check1.valid = 1
                    check1.explanation = "Regenerated, therefore must be valid."
                elif changed.get(other_pos) and not changed.get(base_pos):
                    # other side changed - regenerate base
                    orig_base = original.get_component(base_pos)
                    bm_dto = await self._antithesis_extractor.extract_single_antithesis(text=text, thesis=other_comp.statement)

                    # Check if regenerated statement matches original
                    if orig_base and orig_base.statement == bm_dto.statement:
                        # Statement unchanged - reuse original component (keep same UID)
                        manager = new_wu.get_relationship_manager_by_position(base_alias)
                        rel = WisdomUnit.get_relationship_class_for_position(base_alias)(alias=base_alias)
                        manager.connect(orig_base, relationship=rel)
                        changed[base_pos] = orig_base.statement
                    else:
                        # Statement changed - create new component
                        bm = component_from_dto(bm_dto)
                        if bm.best_rationale and bm.best_rationale.text:
                            bm.best_rationale.text = f"REGENERATED. {bm.best_rationale.text}"
                        manager = new_wu.get_relationship_manager_by_position(base_alias)
                        rel = WisdomUnit.get_relationship_class_for_position(base_alias)(alias=base_alias)
                        manager.connect(bm, relationship=rel)
                        changed[base_pos] = bm.statement
                    check1.valid = 1
                    check1.explanation = "Regenerated, therefore must be valid."

            if not check1.valid:
                # Mark components with ERROR prefix
                # If component is already committed, create new error-marked component
                base_comp = new_wu.get_component(base_alias)
                other_comp = new_wu.get_component(other_alias)
                if base_comp:
                    if base_comp.is_committed:
                        # Create new component with ERROR prefix
                        error_comp = DialecticalComponent(
                            statement=f"ERROR: {base_comp.statement}"
                        )
                        error_comp.commit()
                        # Disconnect old and connect new
                        manager = new_wu.get_relationship_manager_by_position(base_alias)
                        manager.disconnect(base_comp)
                        rel = WisdomUnit.get_relationship_class_for_position(base_alias)(alias=base_alias)
                        manager.connect(error_comp, relationship=rel)
                    else:
                        base_comp.statement = f"ERROR: {base_comp.statement}"
                        base_comp.commit()
                if other_comp:
                    if other_comp.is_committed:
                        # Create new component with ERROR prefix
                        error_comp = DialecticalComponent(
                            statement=f"ERROR: {other_comp.statement}"
                        )
                        error_comp.commit()
                        # Disconnect old and connect new
                        manager = new_wu.get_relationship_manager_by_position(other_alias)
                        manager.disconnect(other_comp)
                        rel = WisdomUnit.get_relationship_class_for_position(other_alias)(alias=other_alias)
                        manager.connect(error_comp, relationship=rel)
                    else:
                        other_comp.statement = f"ERROR: {other_comp.statement}"
                        other_comp.commit()
                warnings.setdefault(base_alias, []).append(check1.explanation)
                warnings.setdefault(other_alias, []).append(check1.explanation)
                raise AssertionError(f"{base_alias}, {other_alias}", warnings, new_wu)

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

            for field in [base_minus, other_plus]:
                alias = self._field_to_alias(field)
                if changed.get(field):
                    # Check if statement actually changed
                    orig_component = original.get_component(alias)
                    new_statement = changed.get(field)

                    if orig_component and orig_component.statement == new_statement:
                        # Statement unchanged - reuse original component (keep same UID)
                        manager = new_wu.get_relationship_manager_by_position(alias)
                        rel = WisdomUnit.get_relationship_class_for_position(alias)(alias=alias)
                        manager.connect(orig_component, relationship=rel)
                    else:
                        # Statement changed - create new component with new UID
                        component = DialecticalComponent(
                            statement=new_statement
                        )
                        component.commit()

                        # Add rationale
                        rationale = Rationale(text=f"{alias} redefined.")
                        rationale.set_explanation(component)
                        rationale.commit()  # Auto-connects to component

                        # Connect to new WU with typed relationship
                        manager = new_wu.get_relationship_manager_by_position(alias)
                        rel = WisdomUnit.get_relationship_class_for_position(alias)(alias=alias)
                        manager.connect(component, relationship=rel)
                else:
                    # Copy from original
                    orig_component = original.get_component(alias)
                    if orig_component:
                        manager = new_wu.get_relationship_manager_by_position(alias)
                        rel = WisdomUnit.get_relationship_class_for_position(alias)(alias=alias)
                        manager.connect(orig_component, relationship=rel)

            if (changed.get(base) or changed.get(base_minus)) or (
                changed.get(other) or changed.get(other_plus)
            ):
                if changed.get(base_minus) or changed.get(base):
                    base_alias = self._field_to_alias(base)
                    base_minus_alias = self._field_to_alias(base_minus)
                    base_comp = new_wu.get_component(base_alias)
                    base_minus_comp = new_wu.get_component(base_minus_alias)

                    check2 = check(
                        is_negative_side,
                        self,
                        base_minus_comp.statement,
                        base_comp.statement,
                    )

                    if not check2.valid:
                        if changed.get(base) and not changed.get(base_minus):
                            not_like_other_minus = ""
                            other_minus_alias = self._field_to_alias(other_minus)
                            other_minus_comp = new_wu.get_component(other_minus_alias)
                            if other_minus_comp:
                                not_like_other_minus = other_minus_comp.statement

                            orig_base_minus = original.get_component(base_minus_alias)
                            bm_dto = await base_negative_side_fn(
                                base_comp.statement, not_like_other_minus
                            )

                            # Check if regenerated statement matches original
                            if orig_base_minus and orig_base_minus.statement == bm_dto.statement:
                                # Statement unchanged - reuse original component (keep same UID)
                                manager = new_wu.get_relationship_manager_by_position(base_minus_alias)
                                rel = WisdomUnit.get_relationship_class_for_position(base_minus_alias)(alias=base_minus_alias)
                                manager.connect(orig_base_minus, relationship=rel)
                                changed[base_minus] = orig_base_minus.statement
                            else:
                                # Statement changed - create new component
                                bm = component_from_dto(bm_dto)
                                assert isinstance(bm, DialecticalComponent)
                                if bm.best_rationale and bm.best_rationale.text:
                                    bm.best_rationale.text = f"REGENERATED. {bm.best_rationale.text}"
                                manager = new_wu.get_relationship_manager_by_position(base_minus_alias)
                                rel = WisdomUnit.get_relationship_class_for_position(base_minus_alias)(alias=base_minus_alias)
                                manager.connect(bm, relationship=rel)
                                changed[base_minus] = bm.statement
                            check2.valid = True
                            check2.explanation = "Regenerated, therefore must be valid."

                    if not check2.valid:
                        base_minus_comp = new_wu.get_component(base_minus_alias)
                        if base_minus_comp:
                            base_minus_comp.statement = f"ERROR: {base_minus_comp.statement}"
                            base_minus_comp.commit()
                        warnings.setdefault(alias_base_minus, []).append(
                            check2.explanation
                        )
                        raise AssertionError(f"{alias_base_minus}", warnings, new_wu)

                # NOTE: At this point we are sure that BASE and BASE- are present and valid between themselves in the new wheel

                other_plus_regenerated = False
                if changed.get(other_plus) or changed.get(other):
                    other_alias = self._field_to_alias(other)
                    other_plus_alias = self._field_to_alias(other_plus)
                    other_comp = new_wu.get_component(other_alias)
                    other_plus_comp = new_wu.get_component(other_plus_alias)

                    check3 = check(
                        is_positive_side,
                        self,
                        other_plus_comp.statement,
                        other_comp.statement,
                    )

                    if not check3.valid:
                        if changed.get(other) and not changed.get(other_plus):
                            base_minus_alias = self._field_to_alias(base_minus)
                            base_minus_comp = new_wu.get_component(base_minus_alias)

                            orig_other_plus = original.get_component(other_plus_alias)
                            op_dto = await other_positive_side_fn(
                                other_comp.statement,
                                base_minus_comp.statement,
                            )

                            # Check if regenerated statement matches original
                            if orig_other_plus and orig_other_plus.statement == op_dto.statement:
                                # Statement unchanged - reuse original component (keep same UID)
                                manager = new_wu.get_relationship_manager_by_position(other_plus_alias)
                                rel = WisdomUnit.get_relationship_class_for_position(other_plus_alias)(alias=other_plus_alias)
                                manager.connect(orig_other_plus, relationship=rel)
                                changed[other_plus] = orig_other_plus.statement
                            else:
                                # Statement changed - create new component
                                op = component_from_dto(op_dto)
                                assert isinstance(op, DialecticalComponent)
                                if op.best_rationale and op.best_rationale.text:
                                    op.best_rationale.text = f"REGENERATED. {op.best_rationale.text}"
                                manager = new_wu.get_relationship_manager_by_position(other_plus_alias)
                                rel = WisdomUnit.get_relationship_class_for_position(other_plus_alias)(alias=other_plus_alias)
                                manager.connect(op, relationship=rel)
                                changed[other_plus] = op.statement
                            check3.valid = True
                            check3.explanation = "Regenerated, therefore must be valid."
                            other_plus_regenerated = True

                    if not check3.valid:
                        other_plus_comp = new_wu.get_component(other_plus_alias)
                        if other_plus_comp:
                            other_plus_comp.statement = f"ERROR: {other_plus_comp.statement}"
                            other_plus_comp.commit()
                        warnings.setdefault(alias_other_plus, []).append(
                            check3.explanation
                        )
                        raise AssertionError(f"{alias_other_plus}", warnings, new_wu)

                # NOTE: At this point we are sure that OTHER and OTHER- are present and valid between themselves in the new wheel

                additional_diagonal_check_skip = other_plus_regenerated or (
                    not changed.get(base_minus) and not changed.get(other_plus)
                )

                if not additional_diagonal_check_skip:
                    base_minus_alias = self._field_to_alias(base_minus)
                    other_plus_alias = self._field_to_alias(other_plus)
                    base_minus_comp = new_wu.get_component(base_minus_alias)
                    other_plus_comp = new_wu.get_component(other_plus_alias)

                    check4 = check(
                        is_strict_opposition,
                        self,
                        base_minus_comp.statement,
                        other_plus_comp.statement,
                    )
                    if not check4.valid:
                        if changed.get(base_minus) and not changed.get(other_plus):
                            # base side changed
                            other_alias = self._field_to_alias(other)
                            other_comp = new_wu.get_component(other_alias)
                            base_minus_comp = new_wu.get_component(base_minus_alias)

                            op_dto = await other_positive_side_fn(
                                other_comp.statement,
                                base_minus_comp.statement,
                            )
                            op = component_from_dto(op_dto)
                            assert isinstance(op, DialecticalComponent)
                            if op.best_rationale and op.best_rationale.text:
                                op.best_rationale.text = f"REGENERATED. {op.best_rationale.text}"
                            manager = new_wu.get_relationship_manager_by_position(other_plus_alias)
                            rel = WisdomUnit.get_relationship_class_for_position(other_plus_alias)(alias=other_plus_alias)
                            manager.connect(op, relationship=rel)
                            changed[other_plus] = op.statement
                            check4.valid = True
                            check4.explanation = "Regenerated, therefore must be valid."
                        elif changed.get(other_plus) and not changed.get(base_minus):
                            # other side changed
                            not_like_other_minus = ""
                            other_minus_alias = self._field_to_alias(other_minus)
                            other_minus_comp = new_wu.get_component(other_minus_alias)
                            if other_minus_comp:
                                not_like_other_minus = other_minus_comp.statement

                            base_alias = self._field_to_alias(base)
                            base_comp = new_wu.get_component(base_alias)
                            bm_dto = await base_negative_side_fn(
                                base_comp.statement, not_like_other_minus
                            )
                            bm = component_from_dto(bm_dto)
                            assert isinstance(bm, DialecticalComponent)
                            if bm.best_rationale and bm.best_rationale.text:
                                bm.best_rationale.text = f"REGENERATED. {bm.best_rationale.text}"
                            manager = new_wu.get_relationship_manager_by_position(base_minus_alias)
                            rel = WisdomUnit.get_relationship_class_for_position(base_minus_alias)(alias=base_minus_alias)
                            manager.connect(bm, relationship=rel)
                            changed[base_minus] = bm.statement
                            check4.valid = True
                            check4.explanation = "Regenerated, therefore must be valid."

                    if not check4.valid:
                        base_minus_comp = new_wu.get_component(base_minus_alias)
                        other_plus_comp = new_wu.get_component(other_plus_alias)
                        if base_minus_comp:
                            base_minus_comp.statement = f"ERROR: {base_minus_comp.statement}"
                            base_minus_comp.commit()
                        if other_plus_comp:
                            other_plus_comp.statement = f"ERROR: {other_plus_comp.statement}"
                            other_plus_comp.commit()
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

        # Optimization: If ALL components have the same UIDs (nothing changed),
        # return the original WisdomUnit instead of creating a new one.
        # This allows wheel_builder to detect unchanged WUs by UID comparison.
        # Compare using WheelSegment.is_same() for both T and A sides.
        t_side_unchanged = original.segment_t.is_same(new_wu.segment_t)
        a_side_unchanged = original.segment_a.is_same(new_wu.segment_a)

        if t_side_unchanged and a_side_unchanged:
            # Nothing changed - return original WU (same UID)
            # Delete the new_wu we created to avoid orphaned nodes in the graph
            if new_wu._id:
                query = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n"
                graph_db.execute(query, {"node_id": new_wu._id})
            return original

        # Commit the WU now that all components are connected
        new_wu.commit()
        return new_wu
