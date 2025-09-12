from asyncio import gather

from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.analyst.think_action_reflection import \
    ThinkActionReflection
from dialectical_framework.analyst.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator
from dialectical_framework.synthesist.domain.wheel import Wheel
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class DecoratorActionReflection(WheelBuilderTransitionCalculator):
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[TransitionSegmentToSegment]:
        consultant = ThinkActionReflection(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )

        return await consultant.think(focus=at)

    async def _do_calculate_transitions_all(
        self, wheel: Wheel
    ) -> list[TransitionSegmentToSegment]:
        # Run all transitions in parallel for better performance
        async_tasks = [
            self._do_calculate_transitions(wheel, wu)
            for wu in wheel.wisdom_units
        ]
        
        results = await gather(*async_tasks)
        
        # Flatten the list of lists
        result: list[TransitionSegmentToSegment] = []
        for tr_list in results:
            result.extend(tr_list)
        return result
