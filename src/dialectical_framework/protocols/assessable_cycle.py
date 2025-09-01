from abc import ABC, abstractmethod

from pydantic import Field, BaseModel

from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.transition import Transition
from dialectical_framework.utils.decompose_probability import decompose_probability_into_transitions


class AssessableCycle(ABC, BaseModel):
    score: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="The final composite score (Pr(S) * CF_S^alpha) for ranking this cycle."
    )

    probability: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="The normalized probability (Pr(S)) of the cycle to exist in reality.",
    )

    graph: DirectedGraph[Transition] = Field(
        default=None,
        description="Directed graph representing the cycle of dialectical components.",
    )

    @property
    @abstractmethod
    def context_fidelity_score(self) -> float: ...

    def calculate_score(self, alpha: float = 1.0, mutate: bool = True) -> float | None:
        """
        Calculates the final composite score for the cycle: Score(S) = Pr(S) × CF_S^α
        This method should be called after probability and context_fidelity_score are available.
        """
        if self.probability is None:
            score = None
        else:
            cf_s = self.context_fidelity_score
            score = self.probability * (cf_s ** alpha)

        if mutate:
            self.score = score

        return self.score

    def calculate_probability(self, mutate: bool = True) -> float | None:
        """
        Calculates the overall probability as the multiplication of all transition probabilities.
        Transitions with None or 0.0 probability are skipped (treated as irrelevant).
        If no transitions have positive probabilities, returns None.
        """
        transitions = self.graph.first_path()
        if not transitions:
            probability = None
        else:
            probability = 1.0
            has_any_valid_probability = False
            
            for transition in transitions:
                if transition.probability is not None and transition.probability > 0.0:
                    probability *= transition.probability
                    has_any_valid_probability = True
                # Skip transitions with None or 0.0 probability (they're irrelevant)
            
            # If no transitions had valid probabilities, the overall probability is undefined
            if not has_any_valid_probability:
                probability = None

        if mutate:
            self.probability = probability

        return probability


    def decompose_probability(self, overwrite_existing_probabilities: bool = False) -> None:
        """
        Decomposes overall probability into individual transition probabilities.
        This should be called after `spiral.probability` is set.
        """
        if self.probability is None:
            # Cannot decompose if overall probability is not set
            return

        transitions = self.graph.first_path()
        if not transitions:  # If there are no transitions, nothing to decompose
            return

        decompose_probability_into_transitions(
            self.probability, transitions, overwrite_existing_probabilities
        )
