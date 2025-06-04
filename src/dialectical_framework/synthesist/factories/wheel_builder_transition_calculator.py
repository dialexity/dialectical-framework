from abc import abstractmethod
from typing import List, Self, Dict, Union

from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment
from dialectical_framework.wisdom_unit import WisdomUnit


class WheelBuilderTransitionCalculator(WheelBuilder):
    def __init__(self, builder: WheelBuilder):
        super().__init__(text=builder.text, config=builder.config)
        self.__decorated_builder = builder

    @property
    def decorated_builder(self) -> WheelBuilder:
        return self.__decorated_builder

    @property
    def reasoner(self) -> DialecticalReasoning:
        return self.__decorated_builder.reasoner

    @property
    def wheel_permutations(self) -> List[Wheel]:
        return self.__decorated_builder.wheel_permutations

    @property
    def text(self) -> str | None:
        return self.__decorated_builder.text

    @property
    def config(self) -> ConfigWheelBuilder:
        return self.__decorated_builder.config

    async def build_wheel_permutations(self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None) -> List[Wheel]:
        await self.__decorated_builder.build_wheel_permutations(theses=theses, t_cycle=t_cycle)
        return self.wheel_permutations

    async def redefine(self, modified_statement_per_alias: Dict[str, str]) -> List[Wheel]:
        await self.__decorated_builder.redefine(modified_statement_per_alias)
        return self.wheel_permutations

    async def calculate_transitions(self, wheel: Wheel, at: WheelSegment|int|str = None):
        if wheel not in self.wheel_permutations:
            raise ValueError(f"Wheel permutation {wheel} not found in available wheels")

        if not isinstance(at, WisdomUnit):
            if at is None:
                at = wheel.main_wisdom_unit
            elif isinstance(at, int):
                at = wheel.wisdom_units[at]
            elif isinstance(at, str):
                for wu in wheel.wisdom_units:
                    if wu.t.alias == at:
                        at = wu.extract_segment_t()
                        break
                    elif wu.a.alias == at:
                        at = wu.extract_segment_a()
                        break

        if hasattr(self.decorated_builder, 'calculate_transitions'):
            await self.decorated_builder.calculate_transitions(wheel=wheel, at=at)

        # This is for subclasses to implement
        await self._do_calculate_transitions(wheel=wheel, at=at)

    @abstractmethod
    async def _do_calculate_transitions(self, wheel: Wheel, at: WheelSegment = None) -> None:
        """Subclasses implement the actual transition calculation logic here."""
        pass

    @classmethod
    def load(cls, *, text: str, config: ConfigWheelBuilder = None, wheels: List[Wheel] = None) -> Self:
        return cls(super().load(text=text, config=config, wheels=wheels))


