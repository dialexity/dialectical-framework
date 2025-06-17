from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.transition import Transition
from dialectical_framework.wheel_segment import WheelSegment


class TransitionSegmentToSegment(Transition):
    """
    Note that though the transition is from segment to segment,
    the source aliases and target aliases can be subsets of segments components.
    """
    source: WheelSegment = Field(description="Source segment of the wheel.")
    target: WheelSegment = Field(description="Target segment of the wheel.")