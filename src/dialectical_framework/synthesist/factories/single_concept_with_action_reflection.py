from dialectical_framework.synthesist.factories.single_concept import SingleConcept
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.think_action_reflection import ThinkActionReflection
from dialectical_framework.wheel import Wheel


class SingleConceptWithActionReflection(SingleConcept):
    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        if not config:
            config = WheelBuilderConfig()

        wheel: Wheel = await super().build(text, config)

        consultant = ThinkActionReflection(
            text=text,
            component_length=config.component_length,
            wisdom_unit=wheel.main_wisdom_unit,
        )
        t = await consultant.think()
        wheel.add_transition(0, t)
        return wheel
