from __future__ import annotations

from asyncio import gather
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.synthesist.wisdom.think_constructive_convergence import \
    ThinkConstructiveConvergence
from dialectical_framework.synthesist.wisdom.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator


class DecoratorDiscreteSpiral(WheelBuilderTransitionCalculator):
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[Transition]:
        consultant = ThinkConstructiveConvergence(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )

        return await consultant.think(at)

    async def _do_calculate_transitions_all(
        self, wheel: Wheel
    ) -> list[Transition]:
        # Run all transitions in parallel for better performance
        async_tasks = [
            self._do_calculate_transitions(wheel, segment)
            for segment in wheel.segments
        ]

        results = await gather(*async_tasks)

        # Flatten the list of lists
        result: list[Transition] = []
        for tr_list in results:
            result.extend(tr_list)
        return result
