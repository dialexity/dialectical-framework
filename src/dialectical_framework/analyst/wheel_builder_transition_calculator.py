from abc import ABC, abstractmethod
from typing import Dict, List, Union

from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.settings import Settings
from dialectical_framework.cycle import Cycle
from dialectical_framework.symmetrical_transition import SymmetricalTransition
from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.wheel_builder import WheelBuilder
from dialectical_framework.transition import Predicate, Transition
from dialectical_framework.wheel import Wheel, WheelSegmentReference
from dialectical_framework.wheel_segment import WheelSegment


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
    def wheel_permutations(self) -> List[Wheel]:
        return self.__decorated_builder.wheel_permutations

    @property
    def text(self) -> str | None:
        return self.__decorated_builder.text

    @property
    def settings(self) -> Settings:
        return self.__decorated_builder.settings

    async def build_wheel_permutations(
        self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None
    ) -> List[Wheel]:
        await self.__decorated_builder.build_wheel_permutations(
            theses=theses, t_cycle=t_cycle
        )
        return self.wheel_permutations

    async def redefine(
        self, modified_statement_per_alias: Dict[str, str]
    ) -> List[Wheel]:
        await self.__decorated_builder.redefine(
            modified_statement_per_alias=modified_statement_per_alias
        )
        return self.wheel_permutations

    async def calculate_syntheses(
        self,
        wheel: Wheel,
        at: WheelSegmentReference | List[WheelSegmentReference] = None,
    ):
        await self.__decorated_builder.calculate_syntheses(wheel=wheel, at=at)

    async def calculate_transitions(
            self,
            wheel: Wheel,
            at: WheelSegmentReference | List[WheelSegmentReference] = None,
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

    @abstractmethod
    async def _do_calculate_transitions(
        self, wheel: Wheel, at: WheelSegment
    ) -> List[Transition]:
        """Subclasses implement the actual transition calculation logic here."""
        pass

    @abstractmethod
    async def _do_calculate_transitions_all(self, wheel: Wheel) -> List[Transition]:
        """Subclasses implement the actual transition calculation logic here."""
        pass

    @staticmethod
    def _take_transition(wheel: Wheel, transition: Transition) -> None:
        if isinstance(transition, SymmetricalTransition):
            wu = wheel.wisdom_unit_at(transition.source)
            st: SymmetricalTransition = transition

            # Break the symmetrical transition into 2 transitions to be able to set it uniformly

            old_t_to_a = wheel.spiral.graph.get_transition(
                st.source_aliases, st.target_aliases
            )
            t_to_a = st
            new_t_to_a = t_to_a
            if old_t_to_a is not None:
                new_t_to_a = old_t_to_a.new_with(t_to_a)
            wheel.spiral.graph.add_transition(new_t_to_a)

            old_a_to_t = wheel.spiral.graph.get_transition(wu.a, wu.t)
            a_to_t = st.model_copy()
            a_to_t.source_aliases = st.opposite_source_aliases
            a_to_t.opposite_source_aliases = st.source_aliases
            a_to_t.source = wu.extract_segment_a()
            a_to_t.target_aliases = st.opposite_target_aliases
            a_to_t.opposite_target_aliases = st.target_aliases
            a_to_t.target = wu.extract_segment_t()
            new_a_to_t = a_to_t
            if old_a_to_t is not None:
                new_a_to_t = old_a_to_t.new_with(a_to_t)
            wheel.spiral.graph.add_transition(new_a_to_t)
        else:
            # The decorator might be enriching the existing transition, so we need to merge, not just add
            new_transition = transition
            if transition.predicate == Predicate.CONSTRUCTIVELY_CONVERGES_TO:
                old_transition = wheel.spiral.graph.get_transition(
                    transition.source_aliases, transition.target_aliases
                )
                if old_transition is not None:
                    new_transition = old_transition.new_with(transition)
                wheel.spiral.graph.add_transition(new_transition)
            elif transition.predicate == Predicate.CAUSES:
                # Cycle graphs must be present in the wheel upfront, so we only enrich the transitions
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
