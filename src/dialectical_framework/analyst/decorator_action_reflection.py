from __future__ import annotations

from asyncio import gather
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.analyst.think_action_reflection import \
    ThinkActionReflection
from dialectical_framework.analyst.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator


class DecoratorActionReflection(WheelBuilderTransitionCalculator):
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[Transition]:
        consultant = ThinkActionReflection(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )

        return await consultant.think(focus=at)

    async def _do_calculate_transitions_all(
        self, wheel: Wheel
    ) -> list[Transition]:
        # Action-Reflection: iterate over unique WisdomUnits, not all segments
        # Each WU needs only one transformation (T-side and A-side point to same WU)
        wus = [wu for wu, _ in wheel.wisdom_units.all()]

        # Run all transitions in parallel for better performance
        async_tasks = [
            self._do_calculate_transitions(wheel, wu.segment_t)  # Use T-side segment
            for wu in wus
        ]

        results = await gather(*async_tasks)

        # Flatten the list of lists
        result: list[Transition] = []
        for tr_list in results:
            result.extend(tr_list)
        return result
