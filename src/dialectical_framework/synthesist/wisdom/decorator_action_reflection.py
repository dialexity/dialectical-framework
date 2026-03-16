from __future__ import annotations

from asyncio import gather
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transformation import Transformation
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

    Action-reflection always processes both T-side and A-side together
    (they form one transformation unit). When iterating over segments
    in the same calculate_transitions call, subsequent segments of the same WU
    are skipped. On new calculate_transitions calls, a new transformation
    may be created.
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
    ) -> list[Transformation]:
        """
        Calculate action-reflection transformation for a wisdom unit.

        Always creates the full Ac-Re structure (action-reflection needs
        the full transformation context with 6 positions).

        Skips if the same WU was already processed in this calculate_transitions call.

        Returns:
            List containing the Transformation (or empty if already processed)
        """
        wu = wheel.wisdom_unit_at(at)

        # Skip if already processed in this call
        if wu.hash in self._processed_wus_this_call:
            # Return existing transformations (no new LLM call)
            transformations = [t for t, _ in wu.transformations.all()]
            return transformations

        # Mark as processed
        self._processed_wus_this_call.add(wu.hash)

        # Create transformation (action-reflection is a single unit of work)
        consultant = ThinkActionReflection(
            text=self.text, wheel=wheel, brain=self.reasoner.brain
        )
        transformation = await consultant.think(focus=at)
        return [transformation]

    async def _do_calculate_transitions_all(
        self, wheel: Wheel
    ) -> list[Transformation]:
        """
        Calculate action-reflection transformations for all wisdom units.

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
        result: list[Transformation] = []
        for trans_list in results:
            result.extend(trans_list)
        return result
