from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.synthesis import Synthesis
from dialectical_framework.wheel_segment import WheelSegment

if TYPE_CHECKING:
    from dialectical_framework.analyst.domain.transformation import \
        Transformation

ALIAS_A = "A"
ALIAS_A_PLUS = "A+"
ALIAS_A_MINUS = "A-"


class WisdomUnit(WheelSegment):
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

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        if self.a:
            result.append(self.a)
        if self.a_minus:
            result.append(self.a_minus)
        if self.a_plus:
            result.append(self.a_plus)
        if self.synthesis:
            result.append(self.synthesis)
        if self.transformation:
            result.append(self.transformation)
        return result

    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, *, mutate: bool = True) -> list[float]:
        """
        Calculates the context fidelity score for this wisdom unit as the geometric mean
        of its constituent DialecticalComponent's scores, including those from its synthesis,
        and weighted rationale opinions.
        Components with a context_fidelity_score of 0.0 or None are excluded from the calculation.
        """
        parts = []

        # Collect from dialectical components
        for f in self.field_to_alias.keys():
            dc = getattr(self, f)
            if isinstance(dc, DialecticalComponent):
                fidelity = dc.calculate_contextual_fidelity(mutate=mutate)
                parts.append(fidelity)

        # Collect scores from Synthesis (S+, S-) components if present
        if self.synthesis is not None:
            # Synthesis is also a WheelSegment, so it has its own components (T/T+ equivalent to S+/S-)
            for f in self.synthesis.field_to_alias.keys():
                dc = getattr(self.synthesis, f)
                if isinstance(dc, DialecticalComponent):
                    fidelity = dc.calculate_contextual_fidelity(mutate=mutate)
                    parts.append(fidelity)

        # Collect fidelity from transformation
        if self.transformation is not None:
            # We don't take transitions, we take the aggregated thing on purpose
            fidelity = self.transformation.calculate_contextual_fidelity(mutate=mutate)
            parts.append(fidelity)

        return parts

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        """
        Calculate probability from the transformation cycle.
        This represents the structural feasibility of the dialectical transformation,
        not expert opinions about it (those influence contextual_fidelity).

        IMPORTANT: we don't use opinion probabilities here, because only the structural relationship matters.
        """
        if self.transformation is None:
            probability = None
        else:
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
