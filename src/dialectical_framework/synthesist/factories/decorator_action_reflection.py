from dialectical_framework.synthesist.factories.wheel_builder_transition_calculator import WheelBuilderTransitionCalculator
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.think_action_reflection import ThinkActionReflection
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class DecoratorActionReflection(WheelBuilderTransitionCalculator):
    def __init__(self, builder: WheelBuilder):
        super().__init__(builder=builder)

    async def _do_calculate_transitions(self, wheel: Wheel, at: WheelSegment = None) -> None:
        wu = wheel.main_wisdom_unit
        if at is not None:
            wu = wheel.wisdom_unit_at(at)

        consultant = ThinkActionReflection(
            text=self.text,
            config=self.config,
            wisdom_unit=wu,
        )

        t = await consultant.think()

        if old_t := wheel.transition_at(0):
            t = old_t.new_with(t)

        wheel.add_transition(0, t)

