"""
WheelSegmentPolarPair for graph-based dialectical framework.

This module provides a flexible "window" into a WisdomUnit with swappable polarity,
allowing you to view the dialectical structure from different perspectives:
- Normal polarity: T-side has theses (T, T+, T-), A-side has antitheses (A, A+, A-)
- Swapped polarity: T-side has antitheses (A, A+, A-), A-side has theses (T, T+, T-)
"""

from __future__ import annotations

from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

from dialectical_framework.graph.wheel_segment import WheelSegment


class WheelSegmentPolarPair:
    """
    A "window" into a WisdomUnit with swappable polarity.

    Provides two sides (t_side and a_side) where the polarity can be:
    - "normal": T-side has theses, A-side has antitheses (standard view)
    - "swapped": T-side has antitheses, A-side has theses (inverted view)

    This allows viewing the same dialectical structure from different perspectives,
    which can be useful for:
    - Exploring alternative interpretations
    - Testing symmetry of arguments
    - Educational demonstrations of dialectical flexibility

    Example:
        # Normal polarity view
        pair = WheelSegmentPolarPair(wu, "normal")
        thesis = pair.t_side.t.get()  # Gets T component
        antithesis = pair.a_side.t.get()  # Gets A component

        # Swapped polarity view
        pair = WheelSegmentPolarPair(wu, "swapped")
        thesis = pair.t_side.t.get()  # Gets A component (swapped!)
        antithesis = pair.a_side.t.get()  # Gets T component (swapped!)
    """

    def __init__(
        self,
        wisdom_unit: WisdomUnit,
        polarity: Literal["normal", "swapped"] = "normal",
        t_segment: Optional[WheelSegment] = None,
        a_segment: Optional[WheelSegment] = None
    ):
        """
        Initialize a polar wheel segment pair.

        Args:
            wisdom_unit: The WisdomUnit to view
            polarity: Either "normal" (T=thesis, A=antithesis) or
                     "swapped" (T=antithesis, A=thesis)
            t_segment: Optional existing T-side WheelSegment to reuse
            a_segment: Optional existing A-side WheelSegment to reuse
        """
        if polarity not in ('normal', 'swapped'):
            raise ValueError(f"polarity must be 'normal' or 'swapped', got: {polarity}")

        self._wisdom_unit = wisdom_unit
        self._polarity = polarity

        # Use existing segments or create new ones
        if t_segment is None:
            t_segment = WheelSegment(wisdom_unit, "T")
        if a_segment is None:
            a_segment = WheelSegment(wisdom_unit, "A")

        # Configure sides based on polarity
        # _left and _right are positional, t_side/a_side are semantic (can swap)
        if polarity == "normal":
            # T-side shows T components, A-side shows A components
            self._left = t_segment
            self._right = a_segment
        else:
            # Swapped: T-side shows A components, A-side shows T components
            self._left = a_segment
            self._right = t_segment

    @property
    def wisdom_unit(self) -> WisdomUnit:
        """Get the WisdomUnit being viewed."""
        return self._wisdom_unit

    @property
    def polarity(self) -> Literal["normal", "swapped"]:
        """Get the polarity configuration ('normal' or 'swapped')."""
        return self._polarity

    @property
    def segment_west(self) -> WheelSegment:
        """
        Get the T-side view.

        In normal polarity: Contains T, T+, T- components
        In swapped polarity: Contains A, A+, A- components
        """
        return self._left

    @property
    def segment_north(self) -> WheelSegment:
        """
        Helper, same as left.
        """
        return self.segment_west

    @property
    def segment_east(self) -> WheelSegment:
        """
        Get the A-side view.

        In normal polarity: Contains A, A+, A- components
        In swapped polarity: Contains T, T+, T- components
        """
        return self._right

    @property
    def segment_south(self) -> WheelSegment:
        """
        Helper, same as right.
        """
        return self.segment_east

    @property
    def segment_top(self) -> WheelSegment:
        """
        Helper, same as north.
        """
        return self.segment_north

    @property
    def segment_bottom(self) -> WheelSegment:
        """
        Helper, same as south.
        """
        return self.segment_south

    @property
    def segment_left(self) -> WheelSegment:
        """
        Helper, same as west.
        """
        return self.segment_west

    @property
    def segment_right(self) -> WheelSegment:
        """
        Helper, same as east.
        """
        return self.segment_east

    def swap(self) -> None:
        """
        Swap the polarity in place.

        Swaps t_side and a_side and updates the polarity state.

        Example:
            pair = WheelSegmentPolarPair(wu, "normal")
            assert pair.polarity == "normal"
            pair.swap()
            assert pair.polarity == "swapped"
            pair.swap()
            assert pair.polarity == "normal"
        """
        # Swap the sides
        self._left, self._right = self._right, self._left

        # Update polarity
        self._polarity = "swapped" if self._polarity == "normal" else "normal"

    def get_component(self, alias: str) -> Optional[DialecticalComponent]:
        """
        Find a component by its alias, searching both sides.

        Args:
            alias: The alias to search for (e.g., "T", "T+", "A-")

        Returns:
            The matching component, or None if not found
        """
        return self.wisdom_unit.get_component(alias)

    def is_complete(self) -> bool:
        """
        Check if both sides are complete.

        Returns:
            True if both t_side and a_side have all components populated
        """
        return self._left.is_complete() and self._right.is_complete()

    def __repr__(self) -> str:
        """String representation of the pair."""
        return (
            f"WheelSegmentPolarPair("
            f"polarity={self._polarity}, "
            f"wisdom_unit={self._wisdom_unit.uid}, "
            f"t_side={self._left.side}, "
            f"a_side={self._right.side})"
        )
