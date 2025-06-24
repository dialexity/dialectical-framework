from typing import List

from dialectical_framework.symmetrical_transition import SymmetricalTransition
from dialectical_framework.synthesist.factories.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator
from dialectical_framework.synthesist.think_action_reflection import ThinkActionReflection
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class DecoratorActionReflection(WheelBuilderTransitionCalculator):
    async def _do_calculate_transition(self, wheel: Wheel, at: WheelSegment) -> SymmetricalTransition:
        consultant = ThinkActionReflection(
            text=self.text,
            config=self.config,
            wheel=wheel
        )

        return await consultant.think(focus=at)

    async def _do_calculate_transitions_all(self, wheel: Wheel) -> List[TransitionSegmentToSegment]:
        result: List[TransitionSegmentToSegment] = []
        for wu in wheel.wisdom_units:
            tr = await self._do_calculate_transition(wheel, wu)
            result.append(tr)
        return result

