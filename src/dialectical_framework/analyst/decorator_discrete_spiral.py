
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.analyst.think_constructive_convergence import \
    ThinkConstructiveConvergence
from dialectical_framework.analyst.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class DecoratorDiscreteSpiral(WheelBuilderTransitionCalculator):
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[TransitionSegmentToSegment]:
        consultant = ThinkConstructiveConvergence(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )

        return [await consultant.think(at)]

    async def _do_calculate_transitions_all(
        self, wheel: Wheel
    ) -> list[TransitionSegmentToSegment]:
        # TODO: use a single prompt to derive all transitions faster?
        result: list[TransitionSegmentToSegment] = []
        for i in range(wheel.degree):
            tr = await self._do_calculate_transitions(wheel, wheel.wheel_segment_at(i))
            result.extend(tr)
        return result
