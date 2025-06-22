from abc import abstractmethod, ABC
from typing import List, Self, Dict, Union

from dialectical_framework.cycle import Cycle
from dialectical_framework.symmetrical_transition import SymmetricalTransition
from dialectical_framework.synthesist.dialectical_reasoner import DialecticalReasoner
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wheel import Wheel, WheelSegmentReference
from dialectical_framework.wheel_segment import WheelSegment
from dialectical_framework.wisdom_unit import WisdomUnit


class WheelBuilderTransitionCalculator(WheelBuilder, ABC):
    def __init__(self, builder: WheelBuilder):
        super().__init__(text=builder.text, config=builder.config)
        self.__decorated_builder = builder

    @property
    def decorated_builder(self) -> WheelBuilder:
        return self.__decorated_builder

    @property
    def reasoner(self) -> DialecticalReasoner:
        return self.__decorated_builder.reasoner

    @property
    def wheel_permutations(self) -> List[Wheel]:
        return self.__decorated_builder.wheel_permutations

    @property
    def text(self) -> str | None:
        return self.__decorated_builder.text

    @property
    def config(self) -> ConfigWheelBuilder:
        return self.__decorated_builder.config

    async def build_wheel_permutations(self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None) -> List[Wheel]:
        await self.__decorated_builder.build_wheel_permutations(theses=theses, t_cycle=t_cycle)
        return self.wheel_permutations

    async def redefine(self, modified_statement_per_alias: Dict[str, str]) -> List[Wheel]:
        await self.__decorated_builder.redefine(modified_statement_per_alias)
        return self.wheel_permutations

    async def calculate_transitions(self, wheel: Wheel, at: WheelSegmentReference | List[WheelSegmentReference] = None):
        if wheel not in self.wheel_permutations:
            raise ValueError(f"Wheel permutation {wheel} not found in available wheels")

        async def iterate_wisdom_units(wisdom_units: List[WisdomUnit]):
            for wisdom_unit in wisdom_units:
                if hasattr(self.decorated_builder, 'calculate_transitions'):
                    await self.decorated_builder.calculate_transitions(wheel=wheel, at=wisdom_unit)
                # This is for subclasses to implement
                tr_i =  await self._do_calculate_transition(wheel=wheel, at=wisdom_unit)
                self._take_transition(wheel=wheel, transition=tr_i)

        if at is None:
            # Calculate for each
            if hasattr(self.decorated_builder, 'calculate_transitions'):
                await self.decorated_builder.calculate_transitions(wheel=wheel, at=None)
            # This is for subclasses to implement
            trs = await self._do_calculate_transitions_all(wheel=wheel)
            for tr in trs:
                self._take_transition(wheel=wheel, transition=tr)
        elif isinstance(at, list):
            # Calculate for some
            wus = []
            for ref in at:
                wus.append(wheel.wisdom_unit_at(ref))
            await iterate_wisdom_units(wus)
        else:
            # Calculate for one
            wu = wheel.wisdom_unit_at(at)
            if hasattr(self.decorated_builder, 'calculate_transitions'):
                await self.decorated_builder.calculate_transitions(wheel=wheel, at=wu)
            # This is for subclasses to implement
            tr = await self._do_calculate_transition(wheel=wheel, at=wu)
            self._take_transition(wheel=wheel, transition=tr)

    @abstractmethod
    async def _do_calculate_transition(self, wheel: Wheel, at: WheelSegment) -> TransitionSegmentToSegment:
        """Subclasses implement the actual transition calculation logic here."""
        pass

    @abstractmethod
    async def _do_calculate_transitions_all(self, wheel: Wheel) -> List[TransitionSegmentToSegment]:
        """Subclasses implement the actual transition calculation logic here."""
        pass

    @staticmethod
    def _take_transition(wheel: Wheel, transition: TransitionSegmentToSegment) -> None:
        wu = wheel.wisdom_unit_at(transition.source)
        if isinstance(transition, SymmetricalTransition):
            st: SymmetricalTransition = transition

            # Break the symmetrical transition into 2 transitions to be able to set it uniformly

            old_t_to_a = wheel.spiral.graph.get_transition(st.source_aliases, st.target_aliases)
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
            wheel.spiral.graph.add_transition(transition)

    @classmethod
    def load(cls, *, text: str, config: ConfigWheelBuilder = None, wheels: List[Wheel] = None) -> Self:
        return cls(super().load(text=text, config=config, wheels=wheels))


