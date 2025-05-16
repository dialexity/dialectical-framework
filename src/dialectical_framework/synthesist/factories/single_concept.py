from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class SingleConcept(WheelBuilder):
    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        if not config:
            config = WheelBuilderConfig()

        reasoner = ReasonFastAndSimple(
            text=text,
            component_length=config.component_length,
        )
        wu = await reasoner.think()
        return Wheel(wu)