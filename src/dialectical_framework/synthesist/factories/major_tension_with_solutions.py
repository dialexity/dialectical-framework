from typing import List

from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.synthesist.think_reciprocal_solution import ThinkReciprocalSolution
from dialectical_framework.wheel import Wheel


class MajorTensionWithSolutions(WheelBuilder):
    def __init__(self, *, thesis: str = None):
        if thesis and thesis.strip():
            self._theses = [thesis]

        self._theses = None

    async def build(self, text: str, config: WheelBuilderConfig = None) -> List[Wheel]:
        reasoner = ReasonFastPolarizedConflict(
            text=text,
            config=config,
        )
        wu = await reasoner.think(thesis=self._theses[0] if self._theses else None)

        consultant = ThinkReciprocalSolution(
            text=text,
            config=config,
            wisdom_unit=wu,
        )

        wheel = Wheel(wu)

        t = await consultant.think()
        wheel.add_transition(0, t)

        return [wheel]