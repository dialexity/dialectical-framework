from __future__ import annotations

from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.synthesis import Synthesis
from dialectical_framework.wheel_segment import WheelSegment

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
