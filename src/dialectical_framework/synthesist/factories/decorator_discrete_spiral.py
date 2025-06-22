from typing import List

from dialectical_framework.synthesist.factories.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator
from dialectical_framework.synthesist.think_constructive_convergence import ThinkConstructiveConvergence
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class DecoratorDiscreteSpiral(WheelBuilderTransitionCalculator):
    async def _do_calculate_transition(self, wheel: Wheel, at: WheelSegment) -> TransitionSegmentToSegment:
        wu = wheel.wisdom_unit_at(at)

        consultant = ThinkConstructiveConvergence(
            text=self.text,
            config=self.config,
            wisdom_unit=wu,
        )

        return await consultant.think()

    async def _do_calculate_transitions_all(self, wheel: Wheel) -> List[TransitionSegmentToSegment]:
        # TODO: use a single prompt to derive all transitions faster?
        result: List[TransitionSegmentToSegment] = []
        for i in range(wheel.degree):
            tr = await self._do_calculate_transition(wheel, wheel.wheel_segment_at(i))
            wheel.spiral.graph.add_transition(tr)
            result.append(tr)
        return result