from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Union

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto
from dialectical_framework.ai_dto.causal_cycle_dto import CausalCycleDto
from dialectical_framework.ai_dto.causal_cycles_deck_dto import \
    CausalCyclesDeckDto
from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship
from dialectical_framework.protocols.causality_sequencer import CausalitySequencer
from dialectical_framework.utils.sequence_generation import (
    generate_compatible_sequences,
    generate_permutation_sequences,
)
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.enums.di import DI
from dependency_injector.wiring import inject, Provide
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.decompose_probability_uniformly import decompose_probability_uniformly
from dialectical_framework.utils.extend_tpl import extend_tpl
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin


class CausalitySequencerBalanced(CausalitySequencer, HasBrain, SettingsAware):
    """
    Causality sequencer that arranges WisdomUnits into Cycles and Wheels.
    """

    @inject
    def __init__(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ):
        self._input_resolver = input_resolver

    @property
    def input_resolver(self) -> InputResolver:
        return self._input_resolver

    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences provides the best assessment considering realism, desirability, and feasibility (given that the final step cycles back to the first step):
        {sequences:list}

        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) considering realistic existence, optimal outcomes, and (implementation) feasibility
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        - Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>

        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_assess_multiple_sequences(
        self, *, sequences: list[str]
    ) -> "Messages.Type": ...

    @prompt_template(
        """
        USER:
        Assess the following circular causality sequence considering realism, desirability, and feasibility (given that the final step cycles back to the first step):
        {sequence}

        <instructions>
        1) Estimate the numeric probability (0 to 1) considering realistic existence, optimal outcomes, and (implementation) feasibility
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        - Only use the sequence **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
        </instructions>

        <formatting>
        - In the explanations and argumentation, for fluency, try to use explicit wording instead of technical aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_assess_single_sequence(self, *, sequence: str) -> "Messages.Type": ...

    async def _estimate_cycles(
        self, *, sequences: list[list[DialecticalComponent]], text: str
    ) -> CausalCyclesDeckDto:
        """
        Estimate cycles from graph-native component sequences.

        Args:
            sequences: List of sequences, where each sequence is a list of graph-native components

        Returns:
            CausalCyclesDeckDto with assessments for each sequence
        """
        sequences_str: dict[str, list[str]] = {}

        # Track graph-native components for later mapping back
        component_map: dict[str, DialecticalComponent] = {}  # uid -> graph-native component

        # Build DTOs for AI boundary
        component_dtos: dict[str, DialecticalComponentDto] = {}  # identity -> DTO

        for seq_idx, sequence in enumerate(sequences, 1):
            sequence_aliases: list[str] = []

            for comp_idx, component in enumerate(sequence, 1):
                # Generate uniform technical alias to avoid AI bias
                technical_alias = f"C{seq_idx}_{comp_idx}"

                # Store graph-native component by identity for later mapping
                if component.hash not in component_map:
                    component_map[component.hash] = component

                    # Convert graph-native component → DTO for AI
                    # Get first rationale as explanation if available
                    explanation = ""
                    rationales = list(component.rationales.all())
                    if rationales:
                        rationale, _ = rationales[0]
                        explanation = rationale.text if rationale.text else ""

                    component_dtos[component.hash] = DialecticalComponentDto(
                        alias=technical_alias,
                        statement=component.statement,
                        explanation=explanation
                    )

                sequence_aliases.append(technical_alias)

            # Build cycle string: "C1_1 → C1_2 → C1_3 → C1_1..."
            cycle_str = " → ".join(sequence_aliases + [sequence_aliases[0]]) + "..."

            # Add human-readable statements for clarity
            readable_parts = [comp.statement for comp in sequence]
            readable_cycle = " → ".join(readable_parts + [readable_parts[0]]) + "..."

            full_cycle_str = f"{cycle_str} ({readable_cycle})"
            sequences_str[full_cycle_str] = sequence_aliases

        # Create DTO deck for AI boundary
        dialectical_components_deck_dto = DialecticalComponentsDeckDto(
            dialectical_components=list(component_dtos.values())
        )

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=CausalCyclesDeckDto)
        async def _estimate_all() -> CausalCyclesDeckDto:
            prompt = self.prompt_assess_multiple_sequences(
                sequences=list(sequences_str.keys())
            )
            tpl = ReverseEngineer.till_theses(
                theses=dialectical_components_deck_dto.dialectical_components,
                text=text
            )
            return extend_tpl(tpl, prompt)

        async def _estimate_single(
            sequence_str: str, aliases: list[str]
        ) -> CausalCycleDto:
            @with_langfuse()
            @use_brain(brain=self.brain, response_model=CausalCycleAssessmentDto)
            async def _estimate_single_call() -> CausalCycleAssessmentDto:
                prompt = self.prompt_assess_single_sequence(sequence=sequence_str)
                tpl = ReverseEngineer.till_theses(
                    theses=dialectical_components_deck_dto.dialectical_components,
                    text=text
                )
                return extend_tpl(tpl, prompt)

            assessment = await _estimate_single_call()
            return CausalCycleDto(
                aliases=aliases,
                probability=assessment.probability,
                reasoning_explanation=assessment.reasoning_explanation,
                argumentation=assessment.argumentation,
            )

        # result = await _estimate_all()
        async_estimators = []
        for sequence, als in sequences_str.items():
            async_estimators.append(
                _estimate_single(sequence_str=sequence, aliases=als)
            )

        # Execute all async estimators concurrently and collect results
        causal_cycles = list(await asyncio.gather(*async_estimators))
        # Create the result deck from collected cycles
        result = CausalCyclesDeckDto(causal_cycles=causal_cycles)

        # Note: Result contains technical aliases (C1_1, C1_2, etc.) which will be
        # mapped back to graph-native components in _normalize() using the sequences parameter
        # Technical aliases were used to avoid AI bias during assessment

        return result

    @staticmethod
    def _build_components_with_aliases(
        thoughts: Union[list[WisdomUnit], list[DialecticalComponent]],
    ) -> list[tuple[DialecticalComponent, str]]:
        """
        Build component-alias mapping for AI boundary translation.

        Args:
            thoughts: Either WisdomUnits or DialecticalComponents

        Returns:
            List of (component, alias) tuples for translation
        """
        if thoughts and isinstance(thoughts[0], WisdomUnit):
            components_with_aliases: list[tuple[DialecticalComponent, str]] = []
            for wu in thoughts:
                t_result = wu.t.get()
                a_result = wu.a.get()
                if t_result:
                    t_comp, t_rel = t_result
                    assert isinstance(t_rel, PolarityRelationship)
                    components_with_aliases.append((t_comp, t_rel.alias))
                if a_result:
                    a_comp, a_rel = a_result
                    assert isinstance(a_rel, PolarityRelationship)
                    components_with_aliases.append((a_comp, a_rel.alias))
            return components_with_aliases
        else:
            return [(comp, f"T{i+1}") for i, comp in enumerate(thoughts)]

    @staticmethod
    def _get_sequence_signature(sequence: list[DialecticalComponent]) -> str:
        """
        Get a canonical signature for a component sequence.

        Used to compare sequences for equality (idempotent operations).
        The signature is rotation-invariant since cycles can start at any point.

        Rotation invariance is achieved by finding the lexicographically smallest
        rotation of the hash sequence. For example, these are all equivalent:
        - T1→A1→T2→A2 (starting from T1)
        - A1→T2→A2→T1 (starting from A1)
        - T2→A2→T1→A1 (starting from T2)

        All produce the same canonical signature (the lex-smallest rotation).

        Args:
            sequence: List of components in order

        Returns:
            Canonical string signature (colon-joined hashes of lex-smallest rotation)
        """
        if not sequence:
            return ""

        # Get hashes in sequence order
        hashes = [comp.hash for comp in sequence]

        # Find canonical rotation (lexicographically smallest)
        # This ensures rotation-invariance: T1→A1→T2 == A1→T2→T1 == T2→T1→A1
        rotations = [hashes[i:] + hashes[:i] for i in range(len(hashes))]
        canonical = min(rotations)

        return ":".join(canonical)

    @staticmethod
    def _get_structure_signature(structure: Union[Cycle, Wheel]) -> str:
        """
        Get the sequence signature of an existing Cycle or Wheel.

        Extracts the component sequence from transitions and returns its canonical
        signature. The signature is rotation-invariant, so cycles that start from
        different components (due to database ordering) will match correctly.

        Note: `structure.dialectical_components` may return components starting
        from any point in the cycle (depends on `order_transitions` start point).
        The canonical rotation ensures consistent signatures regardless.

        Args:
            structure: Cycle or Wheel node

        Returns:
            Canonical string signature (rotation-invariant)
        """
        components = structure.dialectical_components
        if not components:
            return ""

        hashes = [comp.hash for comp in components]

        # Find canonical rotation (lexicographically smallest)
        # Ensures T1→A1→T2→A2 matches A1→T2→A2→T1 etc.
        rotations = [hashes[i:] + hashes[:i] for i in range(len(hashes))]
        canonical = min(rotations)

        return ":".join(canonical)

    def _build_structures(
        self,
        sequences: list[list[DialecticalComponent]],
        node_type: type = Cycle,
        intent: str = None,
    ) -> list[Union[Cycle, Wheel]]:
        """
        Build Cycle/Wheel structures from component sequences.

        Creates nodes with transitions. Structures are SAVED but NOT COMMITTED.
        Caller must:
        1. Connect structures to parents (Cycle→Nexus, Wheel→Cycle)
        2. Commit structures
        3. Call estimate() to attach AI estimations

        Args:
            sequences: List of component sequences to create structures from
            node_type: Type of node to create (Cycle or Wheel)
            intent: Optional intent for Cycle nodes (defaults to settings.cycle_intent)

        Returns:
            List of saved (uncommitted) Cycle or Wheel nodes
        """
        nodes: list = []

        if not sequences:
            return nodes

        for sequence in sequences:
            # Create node (Cycle with intent, or Wheel without)
            if node_type == Cycle:
                cycle_intent = intent if intent is not None else self.settings.cycle_intent
                node = Cycle(intent=cycle_intent)
            else:
                node = Wheel()
            node.save()

            # Create transitions
            if sequence:
                for i in range(len(sequence)):
                    source_comp = sequence[i]
                    target_comp = sequence[(i + 1) % len(sequence)]

                    transition = Transition()
                    transition.set_source(source_comp)
                    transition.set_target(target_comp)
                    transition.commit()
                    transition.cycle.connect(node)

            nodes.append(node)

        return nodes

    def arrange(
        self,
        nexus: Nexus,
        intent: str,
    ) -> list[Cycle]:
        """
        Arrange WisdomUnits in a Nexus into Cycles and Wheels (idempotent).

        Creates Cycle nodes (from T components) and Wheel nodes (from WisdomUnits).
        Picks up where it left off:
        - If some Cycles with this intent exist, only creates missing ones
        - If some Wheels exist in a Cycle, only creates missing ones

        Commit behavior follows Nexus state:
        - If Nexus is committed: new Cycles and Wheels are committed
        - If Nexus is uncommitted: new Cycles and Wheels are saved but not committed
          (caller is responsible for committing Nexus first, then Cycles, then Wheels)

        Args:
            nexus: Nexus containing WisdomUnits to arrange.
                   Can be uncommitted or committed - new cycles can be added either way.
            intent: Causality intent (e.g., "preset:balanced", "preset:realistic").

        Returns:
            List of all Cycle nodes (existing + new). Wheels via cycle.wheels.all().
            Commit state of new structures matches Nexus commit state.

        Raises:
            ValueError: If nexus has no WisdomUnits.
        """
        # Get WisdomUnits from Nexus
        wisdom_units = [wu for wu, _ in nexus.wisdom_units.all()]
        if not wisdom_units:
            raise ValueError("Nexus has no WisdomUnits.")

        if len(wisdom_units) > 4:
            raise ValueError(f"{len(wisdom_units)} wisdom units are not supported yet.")

        # Extract T components from WisdomUnits
        t_components: list[DialecticalComponent] = []
        for wu in wisdom_units:
            t_result = wu.t.get()
            if t_result:
                t_components.append(t_result[0])

        if not t_components:
            raise ValueError("No T components found in WisdomUnits.")

        # Generate all possible sequences
        t_sequences = self._get_sequences(t_components)
        wu_sequences = self._get_sequences(wisdom_units)

        # Get existing cycles with this intent
        existing_cycles = [c for c, _ in nexus.cycles.all() if c.intent == intent]

        # Build signature map of existing cycles
        existing_cycle_sigs: dict[str, Cycle] = {}
        for cycle in existing_cycles:
            sig = self._get_structure_signature(cycle)
            existing_cycle_sigs[sig] = cycle

        # Find missing cycle sequences
        missing_t_sequences = []
        for t_seq in t_sequences:
            sig = self._get_sequence_signature(t_seq)
            if sig not in existing_cycle_sigs:
                missing_t_sequences.append(t_seq)

        # Build missing cycles
        new_cycles = self._build_structures(missing_t_sequences, node_type=Cycle, intent=intent)

        # Connect new cycles to Nexus
        for cycle in new_cycles:
            nexus.cycles.connect(cycle)

        # Commit new cycles if Nexus is committed
        if nexus.is_committed:
            for cycle in new_cycles:
                cycle.commit()

        # All cycles (existing + new)
        all_cycles = existing_cycles + new_cycles

        # For each cycle, ensure all wheel sequences exist
        # Note: wu_sequences contains component sequences (from generate_compatible_sequences)
        for cycle in all_cycles:
            # Get existing wheel signatures for this cycle
            existing_wheel_sigs: set[str] = set()
            for wheel, _ in cycle.wheels.all():
                sig = self._get_structure_signature(wheel)
                existing_wheel_sigs.add(sig)

            # Find missing wheel sequences
            missing_sequences = []
            for comp_seq in wu_sequences:
                sig = self._get_sequence_signature(comp_seq)
                if sig not in existing_wheel_sigs:
                    missing_sequences.append(comp_seq)

            # Build missing wheels
            if missing_sequences:
                new_wheels = self._build_structures(missing_sequences, node_type=Wheel)
                for wheel in new_wheels:
                    cycle.wheels.connect(wheel)

                # Commit new wheels if Nexus is committed
                if nexus.is_committed:
                    for wheel in new_wheels:
                        wheel.commit()

        return all_cycles

    async def estimate(
        self,
        cycle: CircularTopologyMixin | list[CircularTopologyMixin],
        force: bool = False,
    ) -> None:
        """
        Attach AI-generated estimations to committed structure(s) (idempotent).

        Creates Rationale and Estimation nodes directly attached to the structures.
        Source text is derived from the Input nodes linked to the structures' components.

        Idempotent behavior:
        - If ALL structures have estimations and force=False → skip (already complete)
        - If SOME structures are missing estimations → estimate ALL (add new estimations)
        - If NO structures have estimations → estimate all

        Multiple estimations per structure are allowed (analytical layer).
        New estimations are added alongside existing ones when re-estimating.

        Args:
            cycle: Single committed structure or list of structures
            force: If True, always add new estimations even if all structures have them

        Raises:
            ValueError: If cycle is empty
        """
        # Normalize to list
        structures: list[Union[Cycle, Wheel] | CircularTopologyMixin] = [cycle] if not isinstance(cycle, list) else list(cycle)

        if not structures:
            raise ValueError("No structures provided.")

        # Check which structures already have estimations
        structures_with_estimations = 0
        for structure in structures:
            assert isinstance(structure, (Cycle, Wheel)), f"Structure {structure} is not a Cycle nor Wheel"

            # Check if structure has any ProbabilityEstimation
            for est, _ in structure.estimations.all():
                if isinstance(est, ProbabilityEstimation):
                    structures_with_estimations += 1
                    break

        # If all structures have estimations and not forcing, skip
        if structures_with_estimations == len(structures) and not force:
            return

        # Get component sequences from each structure's transitions
        # List position = sequence index for mapping AI results back
        sequences: list[list[DialecticalComponent]] = []
        for structure in structures:
            components = structure.dialectical_components
            sequences.append(components)

        if not sequences or not sequences[0]:
            return

        # Derive text from Input nodes linked to components
        text = await self._get_source_text(sequences)

        # Get AI estimations
        causal_cycles_deck = await self._estimate_cycles(sequences=sequences, text=text)

        # Apply estimations - creates Rationale + Estimation nodes directly
        # New estimations are added alongside existing ones
        self._apply_estimations(structures, causal_cycles_deck, sequences)

    async def _get_source_text(self, sequences: list[list[DialecticalComponent]]) -> str:
        """
        Get source text from Input nodes linked to the components.

        Uses the injected InputResolver to properly resolve content
        (handles URIs, data URIs, etc.).

        Args:
            sequences: List of component sequences

        Returns:
            Resolved and concatenated source text from all unique Inputs
        """
        from dialectical_framework.graph.nodes.input import Input

        # Collect unique Input nodes
        seen_inputs: set[str] = set()
        input_nodes: list[Input] = []

        for sequence in sequences:
            for component in sequence:
                # Get Input(s) this component was extracted from
                for input_node, _ in component.inputs.all():
                    if input_node.hash not in seen_inputs:
                        seen_inputs.add(input_node.hash)
                        input_nodes.append(input_node)

        if not input_nodes:
            return ""

        # Use InputResolver to resolve all inputs
        return await self.input_resolver.resolve_all(input_nodes)

    def _apply_estimations(
        self,
        structures: list[Union[Cycle, Wheel]],
        causal_cycles_deck: CausalCyclesDeckDto,
        sequences: list[list[DialecticalComponent]],
    ) -> None:
        """
        Create and attach Rationale + Estimation nodes to structures.

        Maps AI results back to structures using sequence index (extracted from
        technical aliases). Creates graph nodes directly - no deferred finalization.

        Args:
            structures: List of committed structures (in sequence order)
            causal_cycles_deck: AI estimation results
            sequences: Component sequences used for AI estimation
        """
        from decimal import ROUND_HALF_UP, Decimal, getcontext

        if not causal_cycles_deck.causal_cycles:
            return

        estimation_manager = EstimationManager()

        # Build index map: sequence_index -> structure (using list position)
        index_to_structure: dict[int, Union[Cycle, Wheel]] = {
            i: structure for i, structure in enumerate(structures)
        }

        # Build component-alias translations for text replacement
        components_with_aliases: list[tuple[DialecticalComponent, str]] = []
        for seq_idx, sequence in enumerate(sequences):
            for comp in sequence:
                # Find existing alias or create default
                alias = None
                for existing_comp, existing_alias in components_with_aliases:
                    if existing_comp.hash == comp.hash:
                        alias = existing_alias
                        break
                if alias is None:
                    alias = f"C{len(components_with_aliases) + 1}"
                    components_with_aliases.append((comp, alias))

        # Build alias translation map
        id_to_original_alias: dict[str, str] = {
            comp.hash: original_alias for comp, original_alias in components_with_aliases
        }
        alias_translations: dict[str, str] = {}
        for seq_idx, sequence in enumerate(sequences, 1):
            for comp_idx, component in enumerate(sequence, 1):
                technical_alias = f"C{seq_idx}_{comp_idx}"
                original_alias = id_to_original_alias.get(component.hash)
                if original_alias:
                    alias_translations[technical_alias] = original_alias

        # Normalize probabilities
        getcontext().prec = 28
        q = Decimal("0.001")

        raw_probs: list[Decimal] = [
            Decimal(str(c.probability)) for c in causal_cycles_deck.causal_cycles
        ]
        total_score = sum(raw_probs)

        if total_score > 0:
            normalized = [p / total_score for p in raw_probs]
        else:
            normalized = [Decimal("1") / Decimal(str(len(raw_probs)))] * len(raw_probs)

        cycle_prob_pairs = list(zip(causal_cycles_deck.causal_cycles, normalized))
        if len(cycle_prob_pairs) > 1:
            cycle_prob_pairs.sort(key=lambda cp: cp[1], reverse=True)

        quantized = [p.quantize(q, rounding=ROUND_HALF_UP) for _, p in cycle_prob_pairs]
        if quantized:
            remainder = Decimal("1.000") - sum(quantized)
            quantized[0] = (quantized[0] + remainder).quantize(q, rounding=ROUND_HALF_UP)

        # Track probabilities for sorting
        structure_probs: dict[int, float] = {}

        # Map AI results to structures by sequence index (extracted from aliases)
        for (causal_cycle, _), norm_prob in zip(cycle_prob_pairs, quantized):
            # Extract sequence index from first alias (format: C{seq_idx}_{comp_idx})
            if not causal_cycle.aliases:
                continue

            first_alias = causal_cycle.aliases[0]
            parts = first_alias.split("_")
            if len(parts) != 2 or not parts[0].startswith("C"):
                continue

            try:
                seq_idx = int(parts[0][1:]) - 1  # Convert 1-indexed to 0-indexed
            except ValueError:
                continue

            # Find structure by sequence index
            matched_structure = index_to_structure.get(seq_idx)
            if not matched_structure:
                continue

            # Translate aliases in text
            reasoning_text = causal_cycle.reasoning_explanation
            argumentation_text = causal_cycle.argumentation
            for technical_alias, original_alias in alias_translations.items():
                reasoning_text = dc_replace(reasoning_text, technical_alias, original_alias)
                argumentation_text = dc_replace(argumentation_text, technical_alias, original_alias)

            # Create and attach Rationale node (use set_explanation pattern)
            rationale = Rationale(
                text=reasoning_text,
                summary=argumentation_text,
            )
            rationale.set_explanation(matched_structure)
            rationale.commit()  # Auto-connects explanation relationship

            # Create Estimation nodes with provenance
            prob_value = float(norm_prob)
            rel_value = causal_cycle.probability

            estimation_manager.upsert_estimation(
                matched_structure, ProbabilityEstimation, prob_value, provider=rationale
            )
            estimation_manager.upsert_estimation(
                matched_structure, RelevanceEstimation, rel_value, provider=rationale
            )

            # Track for sorting
            structure_probs[id(matched_structure)] = prob_value

            # Update transition probabilities
            self._decompose_probability_into_transitions(
                probability=prob_value,
                cycle=matched_structure,
                overwrite_existing=True
            )

        # Sort structures by probability (highest first)
        structures.sort(key=lambda s: structure_probs.get(id(s), 0.0), reverse=True)

    @staticmethod
    def _get_sequences(
        thoughts: Union[list[WisdomUnit], list[DialecticalComponent]],
    ) -> list[list[DialecticalComponent]]:
        """
        Generate sequences from graph-native thoughts.

        Args:
            thoughts: Either WisdomUnits (generates compatible sequences) or
                     DialecticalComponents (generates permutations)

        Returns:
            List of component sequences for cycle generation

        Note:
            Caller must convert strings/DTOs to DialecticalComponents before calling
        """
        if len(thoughts) == 0:
            raise ValueError("No thoughts provided.")

        if thoughts and isinstance(thoughts[0], WisdomUnit):
            ordered_wisdom_units: list[WisdomUnit] = thoughts
            return generate_compatible_sequences(ordered_wisdom_units)
        else:
            # Handle list[DialecticalComponent]
            dialectical_components: list[DialecticalComponent] = thoughts
            return generate_permutation_sequences(dialectical_components)

    @staticmethod
    def _decompose_probability_into_transitions(
        probability: float,
        cycle: Cycle,
        overwrite_existing: bool = False
    ) -> None:
        """
        Decompose cycle probability into individual transition probabilities.

        Uses the same logic as legacy domain implementation:
        - Case 1 (no existing): uniform decomposition (nth root)
        - Case 2 (all existing): do nothing
        - Case 3 (mixed): distribute remaining probability uniformly

        Args:
            probability: Overall cycle probability (0.0 to 1.0)
            cycle: Graph-native Cycle node with transitions
            overwrite_existing: If True, clear all existing transition probabilities first

        Note:
            Sets ProbabilityEstimation on Transition nodes via EstimationManager.
            Probabilities multiply: P_cycle = P_t1 × P_t2 × ... × P_tn
        """
        estimation_manager = EstimationManager()

        # Get all transitions
        all_transitions = cycle.transitions
        if not all_transitions:
            return

        # Optionally clear existing probabilities
        if overwrite_existing:
            for trans in all_transitions:
                # Remove existing ProbabilityEstimation if present
                estimation_manager.clear_estimations(trans, [ProbabilityEstimation])

        # Check which transitions already have probabilities
        transitions_with_probs = []
        transitions_without_probs = []

        for trans in all_transitions:
            # Check if transition has ProbabilityEstimation
            has_prob = False
            for est, _ in trans.estimations.all():
                if isinstance(est, ProbabilityEstimation):
                    transitions_with_probs.append((trans, est.value))
                    has_prob = True
                    break

            if not has_prob:
                transitions_without_probs.append(trans)

        # Case 2: All transitions already have probabilities - don't override
        if not transitions_without_probs:
            return

        # Case 1: No transitions have probabilities - use uniform decomposition
        if not transitions_with_probs:
            individual_prob = decompose_probability_uniformly(
                probability,
                len(all_transitions)
            )
            for trans in all_transitions:
                estimation_manager.upsert_estimation(
                    trans, ProbabilityEstimation, individual_prob
                )
        else:
            # Case 3: Mixed - some have probabilities, some don't
            # Calculate what's "left over" for the unassigned transitions
            assigned_prob_product = 1.0
            for _, prob_value in transitions_with_probs:
                assigned_prob_product *= prob_value

            # Remaining probability to distribute
            remaining_prob = probability / assigned_prob_product if assigned_prob_product > 0 else probability

            # Distribute remaining probability uniformly among unassigned transitions
            if transitions_without_probs and remaining_prob > 0:
                individual_prob = decompose_probability_uniformly(
                    remaining_prob,
                    len(transitions_without_probs)
                )
                for trans in transitions_without_probs:
                    estimation_manager.upsert_estimation(
                        trans, ProbabilityEstimation, individual_prob
                    )
