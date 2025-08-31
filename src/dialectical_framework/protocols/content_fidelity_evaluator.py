from abc import abstractmethod
from typing import List, Union

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.reloadable import Reloadable
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment
from mirascope import Messages


class ContentFidelityEvaluator(Reloadable):
    @abstractmethod
    def prompt_single_statement(self, *, statement: str | DialecticalComponent) -> Messages.Type: ...

    @abstractmethod
    def prompt_multiple_statements(self, *, statements: List[
        str | DialecticalComponent | WheelSegment | Wheel]) -> Messages.Type: ...

    @abstractmethod
    async def evaluate(self, *, target: Union[
        List[str | DialecticalComponent | WheelSegment | Wheel],
        str, DialecticalComponent, WheelSegment, Wheel
    ]) -> DialecticalComponent: ...
