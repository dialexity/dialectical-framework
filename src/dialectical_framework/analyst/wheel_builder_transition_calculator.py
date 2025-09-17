from abc import ABC, abstractmethod
from typing import Dict, Union

from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.domain.wheel import Wheel, WheelSegmentReference
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class WheelBuilderTransitionCalculator(WheelBuilder, ABC):
    def __init__(self, builder: WheelBuilder):
        super().__init__(text=builder.text)
        self.__decorated_builder = builder

    @property
    def decorated_builder(self) -> WheelBuilder:
        return self.__decorated_builder

    @property
    def reasoner(self) -> PolarityReasoner:
        return self.__decorated_builder.reasoner

    @property
    def wheel_permutations(self) -> list[Wheel]:
        return self.__decorated_builder.wheel_permutations

    @property
    def text(self) -> str | None:
        return self.__decorated_builder.text

    @property
    def settings(self) -> Settings:
        return self.__decorated_builder.settings

    async def build_wheel_permutations(
        self, *, theses: list[Union[str, None]] = None, t_cycle: Cycle = None
    ) -> list[Wheel]:
        return await self.__decorated_builder.build_wheel_permutations(
            theses=theses, t_cycle=t_cycle
        )

    async def redefine(
        self, modified_statement_per_alias: Dict[str, str]
    ) -> list[Wheel]:
        return await self.__decorated_builder.redefine(
            modified_statement_per_alias=modified_statement_per_alias
        )

    async def calculate_syntheses(
        self,
        wheel: Wheel,
        at: WheelSegmentReference | list[WheelSegmentReference] = None,
    ):
        await self.__decorated_builder.calculate_syntheses(wheel=wheel, at=at)

    async def calculate_transitions(
            self,
            wheel: Wheel,
            at: WheelSegmentReference | list[WheelSegmentReference] = None,
    ):
        if wheel not in self.wheel_permutations:
            raise ValueError(f"Wheel permutation {wheel} not found in available wheels")

        if at is None:
            # Calculate for each
            if hasattr(self.decorated_builder, "calculate_transitions"):
                await self.decorated_builder.calculate_transitions(wheel=wheel, at=None)
            # This is for subclasses to implement
            trs = await self._do_calculate_transitions_all(wheel=wheel)
            for tr in trs:
                self._take_transition(wheel=wheel, transition=tr)
        elif isinstance(at, list):
            # Calculate for some
            for ref in at:
                if hasattr(self.decorated_builder, "calculate_transitions"):
                    await self.decorated_builder.calculate_transitions(
                        wheel=wheel, at=ref
                    )
                # This is for subclasses to implement
                trs_i = await self._do_calculate_transitions(wheel=wheel, at=ref)
                for tr in trs_i:
                    self._take_transition(wheel=wheel, transition=tr)
        else:
            # Calculate for one
            if hasattr(self.decorated_builder, "calculate_transitions"):
                await self.decorated_builder.calculate_transitions(wheel=wheel, at=at)
            # This is for subclasses to implement
            trs = await self._do_calculate_transitions(wheel=wheel, at=at)
            for tr in trs:
                self._take_transition(wheel=wheel, transition=tr)

        wheel.calculate_score()

    @abstractmethod
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[Transition]:
        """Subclasses implement the actual transition calculation logic here."""

    @abstractmethod
    async def _do_calculate_transitions_all(self, wheel: Wheel) -> list[Transition]:
        """Subclasses implement the actual transition calculation logic here."""

    @staticmethod
    def _take_transition(wheel: Wheel, transition: Transition) -> None:
        """
        The decorator might be enriching the existing transition, so we need to merge, not just add
        """
        new_transition = transition

        if transition.predicate == Predicate.TRANSFORMS_TO:
            # this is only valid for wisdom units!
            wu = wheel.wisdom_unit_at(transition.source)
            old_transition = wu.transformation.graph.get_transition(
                transition.source_aliases, transition.target_aliases
            )
            if old_transition is not None:
                new_transition = old_transition.new_with(transition)
            wu.transformation.graph.add_transition(new_transition)
        elif transition.predicate == Predicate.CONSTRUCTIVELY_CONVERGES_TO:
            old_transition = wheel.spiral.graph.get_transition(
                transition.source_aliases, transition.target_aliases
            )
            if old_transition is not None:
                new_transition = old_transition.new_with(transition)
            wheel.spiral.graph.add_transition(new_transition)
        elif transition.predicate == Predicate.CAUSES:
            # Cycle graphs must be present in the wheel upfront, so we only enrich the transitions
            # TODO: I'm not 100% confident, that given a transition we should update it in both cycles. They might have different rationales... in each cycle.
            graph = None
            old_transition = wheel.t_cycle.graph.get_transition(
                transition.source_aliases, transition.target_aliases
            )
            if old_transition is not None:
                graph = wheel.t_cycle.graph
            if graph:
                if old_transition is not None:
                    new_transition = old_transition.new_with(transition)
                graph.add_transition(new_transition)
                graph = None

            old_transition = wheel.cycle.graph.get_transition(
                transition.source_aliases, transition.target_aliases
            )
            if old_transition is not None:
                graph = wheel.cycle.graph
            if graph:
                if old_transition is not None:
                    new_transition = old_transition.new_with(transition)
                graph.add_transition(new_transition)
