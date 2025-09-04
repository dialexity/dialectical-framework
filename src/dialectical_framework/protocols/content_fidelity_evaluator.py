from abc import abstractmethod
from typing import Union


from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.reloadable import Reloadable
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class ContentFidelityEvaluator(Reloadable):
    @abstractmethod
    async def evaluate(self, *, target: Union[
        list[str | DialecticalComponent | WheelSegment | Wheel],
        str, DialecticalComponent, WheelSegment, Wheel
    ]) -> DialecticalComponent: ...
