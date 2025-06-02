from __future__ import annotations

from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent
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

    def extract_segment_t(self) -> WheelSegment:
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
