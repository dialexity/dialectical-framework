from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.synthesist.wisdom.decorator_discrete_spiral import DecoratorDiscreteSpiral
from dialectical_framework.synthesist.wisdom.think_constructive_convergence_auditor import ThinkConstructiveConvergenceAuditor


class DecoratorDiscreteSpiralAudited(DecoratorDiscreteSpiral):
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[Transition]:
        consultant = ThinkConstructiveConvergenceAuditor(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )

        return await consultant.think(at)