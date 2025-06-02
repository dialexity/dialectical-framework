from typing import List, Union

from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.synthesist.think_reciprocal_solution import ThinkReciprocalSolution
from dialectical_framework.wheel import Wheel


class MajorTensionWithSolutions(WheelBuilder):
    def __init__(self, *, text: str = None, config: WheelBuilderConfig = None):
        super().__init__(text=text, config=config)
        self._reasoner = ReasonFastPolarizedConflict(
            text=text,
            config=config,
        )

    async def build(self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None) -> List[Wheel]:
        wu_count = len(theses) if theses else 1
        if wu_count > 1:
            raise ValueError(f"Major tension with solutions only supports one thesis, got {wu_count}")

        wheels = await super().build(theses=theses)
        wheel = wheels[0]

        consultant = ThinkReciprocalSolution(
            text=self.text,
            config=self._config,
            wisdom_unit=wheel.main_wisdom_unit,
        )

        t = await consultant.think()
        wheel.add_transition(0, t)

        return wheels