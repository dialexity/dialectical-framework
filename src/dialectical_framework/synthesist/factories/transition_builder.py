from abc import abstractmethod, ABC
from typing import List, Self, Dict, Union

from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.wheel import Wheel

class TransitionBuilder(WheelBuilder):
    def __init__(self, builder: WheelBuilder):
        super().__init__()
        self._decorated_builder = builder

    @property
    def reasoner(self) -> DialecticalReasoning:
        return super().reasoner

    @property
    def wheels(self) -> List[Wheel]:
        return super().wheels

    @property
    def text(self) -> str | None:
        return super().text

    async def build(self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None) -> List[Wheel]:
        return await super().build(theses=theses, t_cycle=t_cycle)

    async def redefine(self, modified_statement_per_alias: Dict[str, str]) -> List[Wheel]:
        return await super().redefine(modified_statement_per_alias)

    async def build_transition(self, *, theses: List[Union[str, None]] = None) -> List[Wheel]:
        pass

    @classmethod
    def load(cls, *, text: str, config: WheelBuilderConfig = None, wheels: List[Wheel] = None) -> Self:
        return super().load(text=text, config=config, wheels=wheels)


