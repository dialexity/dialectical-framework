from dialectical_framework.symmetrical_transition import SymmetricalTransition
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_transition_calculator import \
    WheelBuilderTransitionCalculator
from dialectical_framework.synthesist.think_reciprocal_solution import ThinkReciprocalSolution
from dialectical_framework.transition import Transition
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class DecoratorReciprocalSolution(WheelBuilderTransitionCalculator):
    def __init__(self, builder: WheelBuilder):
        super().__init__(builder=builder)

    async def _do_calculate_transitions(self, wheel: Wheel, at: WheelSegment = None) -> None:
        wu = wheel.main_wisdom_unit
        if at is not None:
            wu = wheel.wisdom_unit_at(at)

        consultant = ThinkReciprocalSolution(
            text=self.text,
            config=self.config,
            wisdom_unit=wu,
        )

        st: SymmetricalTransition = await consultant.think()

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

