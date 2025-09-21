from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.synthesist.domain.synthesis import Synthesis
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment
from dialectical_framework.utils.pm import pm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.analyst.domain.transformation import \
        Transformation

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

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        if self.t:
            result.append(self.t)
        if self.t_minus:
            result.append(self.t_minus)
        if self.t_plus:
            result.append(self.t_plus)
        if self.a:
            result.append(self.a)
        if self.a_minus:
            result.append(self.a_minus)
        if self.a_plus:
            result.append(self.a_plus)
        if self.synthesis:
            if self.synthesis.t:
                result.append(self.synthesis.t)
            if self.synthesis.t_minus:
                result.append(self.synthesis.t_minus)
            if self.synthesis.t_plus:
                result.append(self.synthesis.t_plus)
        if self.transformation:
            result.append(self.transformation)
        return result

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        """
        Calculates the relevance score for this wisdom unit as the geometric mean
        of its constituent DialecticalComponent's scores, including those from its synthesis,
        and weighted rationale opinions.
        Components with a relevance of 0.0 or None are excluded from the calculation.
        """
        parts = []

        # Collect symmetrical pairs
        pairs = [
            (self.t, self.a),
            (self.t_plus, self.a_minus),
            (self.t_minus, self.a_plus),
        ]

        if self.synthesis is not None:
            pairs.append((self.synthesis.t_plus, self.synthesis.t_minus))

        for one, two in pairs:
            one_cf = one.calculate_relevance() if one else None
            two_cf = two.calculate_relevance() if two else None
            pm = pm_with_zeros_and_nones_handled((one_cf, two_cf))
            if pm is not None:
                parts.append(pm)

        # Collect relevance from transformation
        if self.transformation is not None:
            # We don't take transitions, we take the aggregated thing on purpose
            relevance = self.transformation.calculate_relevance()
            if relevance is not None:
                parts.append(relevance)

        return parts

    def calculate_probability(self) -> float | None:
        """
        Calculate probability from the transformation cycle.
        This represents the structural feasibility of the dialectical transformation,
        not expert opinions about it (those influence relevance).

        IMPORTANT: we don't use rationale probabilities here, because only the structural relationship matters.
        """
        if self.transformation is None:
            probability = None
        else:
            probability = self.transformation.calculate_probability()

        # Save the calculation as this object is derivative composition
        self.calculated_probability = probability
        return self.probability

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
