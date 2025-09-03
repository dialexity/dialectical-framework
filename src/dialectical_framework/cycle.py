from __future__ import annotations

from statistics import geometric_mean
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.protocols.assessable_cycle import AssessableCycle
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.transition_cell_to_cell import TransitionCellToCell
from dialectical_framework.utils.decompose_probability import decompose_probability_into_transitions


class Cycle(AssessableCycle):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    causality_type: CausalityType = Field(
        ..., description="The type of causality in the cycle."
    )
    causality_direction: Literal["clockwise", "counterclockwise"] = Field(
        default="clockwise", description="The direction of causality in the ring."
    )

    reasoning_explanation: str = Field(
        default="", description="Explanation why/how this cycle might occur."
    )
    argumentation: str = Field(
        default="",
        description="Circumstances or contexts where this cycle would be most applicable or useful.",
    )

    def __init__(
        self,
        dialectical_components: List[DialecticalComponent],
        causality_type: CausalityType = CausalityType.REALISTIC,
        **data,
    ):
        data["causality_type"] = causality_type
        super().__init__(**data)
        if self.graph is None:
            self.graph = DirectedGraph[TransitionCellToCell]()
            for i in range(len(dialectical_components)):
                next_i = (i + 1) % len(dialectical_components)
                if self.causality_direction == "clockwise":
                    source = dialectical_components[i]
                    target = dialectical_components[next_i]
                else:
                    source = dialectical_components[next_i]
                    target = dialectical_components[i]

                self.graph.add_transition(
                    TransitionCellToCell(
                        source=source,
                        predicate=Predicate.CAUSES,
                        target=target,
                        # TODO: how do we set the transition text?
                    )
                )

    @property
    def dialectical_components(self) -> List[DialecticalComponent]:
        """Returns list of dialectical components from the first path of the ring."""
        path = self.graph.first_path()
        return [transition.source for transition in path] if path else []

    @property
    def context_fidelity_score(self) -> float:
        """
        Calculates the path fidelity (CF_S) as the geometric mean of the content_fidelity_scores
        of the dialectical components in this cycle.
        
        Components with a content_fidelity_score of 0.0 or None are excluded from the calculation,
        as they represent concepts not grounded in the source context, which should not
        zero out the overall fidelity unless all components are ungrounded.
        """
        transitions = self.graph.first_path()
        if not transitions:
            return 1.0 # If no components, assume perfect fidelity (neutral effect)
                       # A cycle with no components can't be assessed for fidelity to content.

        components = [transition.source for transition in transitions]
        
        # Filter for actual DialecticalComponent instances and, crucially,
        # only include those with a content_fidelity_score > 0.0 for the geometric mean.
        # Scores of 0.0 or None are treated as "not set" or "not positively grounded"
        # and are excluded from the geometric mean calculation, to prevent zeroing out.
        scores_for_gm = [
            c.context_fidelity_score
            for c in components
            if isinstance(c, DialecticalComponent) and c.context_fidelity_score is not None and c.context_fidelity_score > 0.0
        ]

        if not scores_for_gm:
            # If after filtering, no components have a positive content_fidelity_score,
            # return 1.0. This means fidelity will have a neutral impact (x1) on the
            # final Score(S) calculation (i.e., Score(S) = Pr(S) * 1^alpha = Pr(S)).
            # This allows blind spots (ungrounded but relevant concepts) to be ranked
            # purely by their probability/feasibility.
            return 1.0
        
        # Calculate the geometric mean of the positive fidelity scores
        return geometric_mean(scores_for_gm)


    def cycle_str(self) -> str:
        """Returns a string representation of the cycle sequence."""
        aliases = [dc.alias for dc in self.dialectical_components]
        if not aliases:
            return ""
        if len(aliases) == 1:
            return f"{aliases[0]} → {aliases[0]}..."
        return " → ".join(aliases) + f" → {aliases[0]}..."

    def is_same_structure(self, other: Cycle) -> bool:
        """Check if cycles represent the same sequence regardless of starting point."""
        self_aliases = DialecticalComponentsDeck(
            dialectical_components=self.dialectical_components
        ).get_aliases()

        other_aliases = DialecticalComponentsDeck(
            dialectical_components=other.dialectical_components
        ).get_aliases()

        # Same length check
        if len(self_aliases) != len(other_aliases):
            return False

        # Convert to sets for same elements check
        if set(self_aliases) != set(other_aliases):
            return False

        # Check rotations only if sets are equal
        if len(self_aliases) <= 1:
            return True

        return any(
            self_aliases == other_aliases[i:] + other_aliases[:i]
            for i in range(len(other_aliases))
        )
            
    def decompose_probability_into_transitions(self, overwrite_existing_probabilities: bool = False) -> None:
        """
        Decomposes the cycle's overall probability into individual transition probabilities
        within its graph. This should be called after `cycle.probability` is set.
        """
        if self.probability is None:
            # Cannot decompose if overall probability is not set
            return

        all_transitions = self.graph.get_all_transitions()
        if not all_transitions: # If there are no transitions, nothing to decompose
            return

        decompose_probability_into_transitions(
            self.probability, all_transitions, overwrite_existing_probabilities
        )

    def pretty(
        self,
        *,
        skip_dialectical_component_explanation=False,
        start_alias: str | DialecticalComponent | None = None,
    ) -> str:
        output = [self.graph.pretty() + f" | Probability: {self.probability}"]

        path = self.graph.first_path(
            start_aliases=[start_alias] if start_alias else None
        )
        if not path:
            raise ValueError(
                f"No path found between {start_alias} and the first dialectical component in the cycle."
            )
        for transition in path:
            dc = transition.source
            output.append(
                dc.pretty(skip_explanation=skip_dialectical_component_explanation)
            )

        output.append(f"Reasoning: {self.reasoning_explanation}")
        output.append(f"Argumentation: {self.argumentation}")

        return "\n".join(output)

    def __str__(self):
        return self.pretty()
