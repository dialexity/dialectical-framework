from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Optional, Union

from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.polarity.polar_reasoner import \
    PolarReasoner
from dialectical_framework.synthesist.wheel_builder import WheelBuilder

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel, WheelSegmentReference
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.wheel_segment import WheelSegment


class WheelBuilderTransitionCalculator(WheelBuilder, ABC):
    def __init__(self, builder: WheelBuilder):
        super().__init__(text=builder.text, source=builder.source)
        self.__decorated_builder = builder

    @property
    def decorated_builder(self) -> WheelBuilder:
        return self.__decorated_builder

    @property
    def reasoner(self) -> PolarReasoner:
        return self.__decorated_builder.reasoner

    @property
    def wheel_permutations(self) -> list[Wheel]:
        return self.__decorated_builder.wheel_permutations

    @property
    def text(self) -> str | None:
        return self.__decorated_builder.text

    @property
    def source(self):
        return self.__decorated_builder.source

    @property
    def input_resolver(self):
        return self.__decorated_builder.input_resolver

    @property
    def settings(self) -> Settings:
        return self.__decorated_builder.settings

    @property
    def scorer(self):
        return self.__decorated_builder.scorer

    async def build_wheel_permutations(
        self, *, theses: Union[list[str | DialecticalComponent | None], list[tuple[str | DialecticalComponent | None, str | DialecticalComponent | None]]] = None, t_cycle: Cycle = None
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
        *,
        wheel: Wheel,
        at: Union[WisdomUnit, list[WisdomUnit], None] = None,
    ):
        await self.__decorated_builder.calculate_syntheses(wheel=wheel, at=at)

    async def calculate_transitions(
            self,
            wheel: Wheel,
            at: WheelSegmentReference | list[WheelSegmentReference] = None,
    ):
        if wheel not in self.wheel_permutations:
            raise ValueError(f"Wheel permutation {wheel} not found in available wheels")

        # Collect all transitions created by this and decorated builders
        all_transitions: list[Transition] = []

        if at is None:
            # Calculate for each
            if hasattr(self.decorated_builder, "calculate_transitions"):
                await self.decorated_builder.calculate_transitions(wheel=wheel, at=None)
            # This is for subclasses to implement
            # Duplicate detection now happens inside think() methods
            transitions = await self._do_calculate_transitions_all(wheel=wheel)
            if transitions:
                all_transitions.extend(transitions)
        elif isinstance(at, list):
            # Calculate for some
            if hasattr(self.decorated_builder, "calculate_transitions"):
                await self.decorated_builder.calculate_transitions(
                    wheel=wheel, at=at
                )
            for ref in at:
                segment = wheel.segment_at(ref)
                # This is for subclasses to implement
                # Duplicate detection now happens inside think() methods
                transitions = await self._do_calculate_transitions(wheel=wheel, at=segment)
                if transitions:
                    all_transitions.extend(transitions)
        else:
            # Calculate for one
            if hasattr(self.decorated_builder, "calculate_transitions"):
                await self.decorated_builder.calculate_transitions(wheel=wheel, at=at)

            segment = wheel.segment_at(at)
            # This is for subclasses to implement
            # Duplicate detection now happens inside think() methods
            transitions = await self._do_calculate_transitions(wheel=wheel, at=segment)
            if transitions:
                all_transitions.extend(transitions)

        # Note: Scoring is caller's responsibility.
        # Call scorer.calculate_score(wheel, force=True) after all modifications are complete.
        # The upsert_estimation calls inside think() methods handle DB invalidation propagation.

    @abstractmethod
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> list[Transition]:
        """Subclasses implement the actual transition calculation logic here."""

    @abstractmethod
    async def _do_calculate_transitions_all(self, wheel: Wheel) -> list[Transition]:
        """Subclasses implement the actual transition calculation logic here."""

