from __future__ import annotations

from pydantic import Field

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class TransitionSegmentToSegment(Transition):
    """
    Note that though the transition is from segment to segment,
    the source aliases and target aliases can be subsets of segments components.
    """

    source: WheelSegment = Field(description="Source segment of the wheel.")
    target: WheelSegment = Field(description="Target segment of the wheel.")
