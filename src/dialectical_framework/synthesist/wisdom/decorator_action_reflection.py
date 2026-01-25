from __future__ import annotations

from asyncio import gather
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel, WheelSegmentReference
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.synthesist.wisdom.think_action_reflection import \
    ThinkActionReflection
from dialectical_framework.synthesist.wisdom.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator
from dialectical_framework.synthesist.wheel_builder import WheelBuilder


class DecoratorActionReflection(WheelBuilderTransitionCalculator):
    """
    Decorator that adds Action-Reflection transformation to wheels.

    Action-reflection always processes both T-side and A-side transitions
    together (they form one transformation unit). When iterating over segments
    in the same calculate_transitions call, subsequent segments of the same WU
    are skipped. On new calculate_transitions calls, rationales are added to
    existing transitions.
    """

    def __init__(self, builder: WheelBuilder):
        super().__init__(builder)
        # Track WUs processed in current calculate_transitions call
        self._processed_wus_this_call: set[str] = set()

    async def calculate_transitions(
        self,
        wheel: Wheel,
        at: Union[WheelSegmentReference, list[WheelSegmentReference], None] = None,
    ):
        """Override to reset tracking at the start of each call."""
        self._processed_wus_this_call.clear()
        return await super().calculate_transitions(wheel, at)

    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[Transition]:
        """
        Calculate action-reflection transitions for a wisdom unit.

        Always creates both T-side and A-side transitions (action-reflection
        needs the full transformation context).

        Skips if the same WU was already processed in this calculate_transitions call.
        On subsequent calls, adds rationales to existing transitions.
        """
        wu = wheel.wisdom_unit_at(at)

        # Skip if already processed in this call
        if wu.uid in self._processed_wus_this_call:
            # Return existing transitions (no new LLM call)
            transformation_result = wu.transformation.get()
            if transformation_result:
                transformation, _ = transformation_result
                return transformation.transitions
            return []

        # Mark as processed
        self._processed_wus_this_call.add(wu.uid)

        # Create both transitions (action-reflection is a single unit of work)
        consultant = ThinkActionReflection(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )
        return await consultant.think(focus=at)

    async def _do_calculate_transitions_all(
        self, wheel: Wheel
    ) -> list[Transition]:
        """
        Calculate action-reflection transitions for all wisdom units.

        Parallelizes across unique WUs for efficiency (one LLM call per WU).
        """
        # Get unique WUs (action-reflection works per WU, not per segment)
        unique_wus = wheel.wisdom_units

        # Parallelize across unique WUs
        async_tasks = [
            self._do_calculate_transitions(wheel, wu.segment_t)
            for wu in unique_wus
        ]

        results = await gather(*async_tasks)

        # Flatten the list of lists
        result: list[Transition] = []
        for tr_list in results:
            result.extend(tr_list)
        return result
