from dialectical_framework.analyst.decorator_discrete_spiral import DecoratorDiscreteSpiral
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.analyst.think_constructive_convergence_auditor import ThinkConstructiveConvergenceAuditor
from dialectical_framework.synthesist.domain.wheel import Wheel
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class DecoratorDiscreteSpiralAudited(DecoratorDiscreteSpiral):
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[TransitionSegmentToSegment]:
        consultant = ThinkConstructiveConvergenceAuditor(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )

        return await consultant.think(at)