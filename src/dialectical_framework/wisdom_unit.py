from __future__ import annotations

from statistics import geometric_mean  # Import geometric_mean
from typing import TYPE_CHECKING

from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.synthesis import Synthesis
from dialectical_framework.wheel_segment import WheelSegment

if TYPE_CHECKING:
    from dialectical_framework.analyst.domain.transformation import Transformation

ALIAS_A = "A"
ALIAS_A_PLUS = "A+"
ALIAS_A_MINUS = "A-"


class WisdomUnit(WheelSegment, Assessable):
    """
    A basic "molecule" in the dialectical framework, which makes up a diagonal relationship (complementary opposing pieces of the wheel).
    It's very restrictive to avoid any additional fields.
    However, it's flexible that the fields can be set by the field name or by alias.
    """

    reasoning_mode: DialecticalReasoningMode = Field(
        default_factory=lambda: DialecticalReasoningMode.GENERAL_CONCEPTS,
        description="The type of dialectical reasoning strategy used to construct this wisdom unit (e.g., 'General Concepts' = default, 'Problem/Solution', 'Action Plan/Steps')",
    )

    a_plus: DialecticalComponent | None = Field(
        default=None,
        description="The positive side of the antithesis: A+",
        alias=ALIAS_A_PLUS,
    )

    a: DialecticalComponent | None = Field(
        default=None, description="The antithesis: A", alias=ALIAS_A
    )

    a_minus: DialecticalComponent | None = Field(
        default=None,
        description="The negative side of the antithesis: A-",
        alias=ALIAS_A_MINUS,
    )

    synthesis: Synthesis | None = Field(
        default=None, description="The synthesis of the wisdom unit."
    )

    transformation: Transformation | None = Field(
        default=None, description="The transformative cycle."
    )

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Calculates the context fidelity score for this wisdom unit as the geometric mean
        of its constituent DialecticalComponent's scores, including those from its synthesis.
        Components with a context_fidelity_score of 0.0 or None are excluded from the calculation.
        """
        scores_for_gm = []

        for f in self.field_to_alias.keys():
            dc: DialecticalComponent | None = getattr(self, f)
            if isinstance(dc, DialecticalComponent) and dc.contextual_fidelity is not None and dc.contextual_fidelity > 0.0:
                scores_for_gm.append(dc.contextual_fidelity)

        # Collect scores from Synthesis (S+, S-) components if present
        if self.synthesis is not None:
            # Synthesis is also a WheelSegment, so it has its own components (T/T+ equivalent to S+/S-)
            for f in self.synthesis.field_to_alias.keys():
                dc: DialecticalComponent | None = getattr(self.synthesis, f)
                if isinstance(dc, DialecticalComponent) and dc.contextual_fidelity is not None and dc.contextual_fidelity > 0.0:
                    scores_for_gm.append(dc.contextual_fidelity)

        if not scores_for_gm:
            score = 1.0 # Neutral impact if no components with positive scores
        else:
            score = geometric_mean(scores_for_gm)

        if mutate:
            self.contextual_fidelity = score

        return score

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        if self.transformation is None:
            return None
        probability = self.transformation.probability
        if probability is None:
            probability = self.transformation.calculate_probability(mutate=mutate)

        if mutate:
            self.probability = probability
        return probability

    def extract_segment_t(self) -> WheelSegment:
        # TODO: maybe it's enough to return self, because the interface is still WheelSegment?
        return WheelSegment(
            t=self.t,
            t_plus=self.t_plus,
            t_minus=self.t_minus,
        )

    def extract_segment_a(self) -> WheelSegment:
        return WheelSegment(
            t=self.a,
            t_plus=self.a_plus,
            t_minus=self.a_minus,
        )

    def swap_segments(self, mutate: bool = True) -> WisdomUnit:
        """
        Swap thesis (T, T+, T−) and antithesis (A, A+, A−) components.

        Parameters
        ----------
        mutate : bool, default True
            • True – perform the swap in-place and return *self*
            • False – leave *self* unchanged and return a **new** `WisdomUnit`
              whose positions are swapped.

        Returns
        -------
        WisdomUnit
            The mutated instance (if ``mutate``) or the newly created,
            swapped copy.
        """
        # Choose the object we will modify.
        target: WisdomUnit = self if mutate else self.model_copy()

        # Swap each corresponding pair.
        target.t, target.a = target.a, target.t
        target.t_plus, target.a_plus = target.a_plus, target.t_plus
        target.t_minus, target.a_minus = target.a_minus, target.t_minus

        return target

    def pretty(self) -> str:
        ws_formatted = super().pretty()
        if self.synthesis and self.synthesis.t_plus:
            return ws_formatted + f"\nSynthesis: {self.synthesis.pretty()}"
        else:
            return ws_formatted

    def add_indexes_to_aliases(self, human_friendly_index: int):
        super().add_indexes_to_aliases(human_friendly_index)
        if self.synthesis:
            self.synthesis.add_indexes_to_aliases(human_friendly_index)

    def set_dialectical_component_as_copy_from_another_segment(
        self, wheel_segment: WheelSegment, dc_field: str
    ):
        if not hasattr(wheel_segment, dc_field):
            setattr(self, dc_field, None)
            return

        c: DialecticalComponent | None = getattr(wheel_segment, dc_field)
        setattr(self, dc_field, c.model_copy() if c else None)
