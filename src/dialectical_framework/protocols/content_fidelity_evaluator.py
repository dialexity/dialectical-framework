from abc import abstractmethod
from typing import List, Union

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.reloadable import Reloadable
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment
from mirascope import Messages


class ContentFidelityEvaluator(Reloadable):
    @abstractmethod
    async def evaluate(self, *, target: Union[
        List[str | DialecticalComponent | WheelSegment | Wheel],
        str, DialecticalComponent, WheelSegment, Wheel
    ]) -> DialecticalComponent: ...
