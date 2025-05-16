from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.synthesist.think_reciprocal_solution import ThinkReciprocalSolution
from dialectical_framework.wheel import Wheel


class MajorTensionWithSolutions(WheelBuilder):
    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        if not config:
            config = WheelBuilderConfig()

        reasoner = ReasonFastPolarizedConflict(
            text=text,
            component_length=config.component_length,
        )
        wu = await reasoner.think()

        consultant = ThinkReciprocalSolution(
            text=text,
            component_length=config.component_length,
            wisdom_unit=wu,
        )

        wheel = Wheel(wu)

        t = await consultant.think()
        wheel.add_transition(0, t)

        return wheel