from __future__ import annotations

from typing import Iterable, Iterator, List

from tabulate import tabulate

from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.directed_graph import DirectedGraph
from dialectical_framework.spiral import Spiral
from dialectical_framework.transition import Transition
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wheel_segment import WheelSegment
from dialectical_framework.wisdom_unit import WisdomUnit


class Wheel:
    def __init__(self, *wisdom_units, t_cycle: Cycle, ta_cycle: Cycle):
        # One iterable argument → use it directly
        if len(wisdom_units) == 1 and not isinstance(wisdom_units[0], WisdomUnit):
            self._wisdom_units = list(wisdom_units[0])
        else:
            self._wisdom_units = list(wisdom_units)

        self._ta_cycle: Cycle = ta_cycle
        self._t_cycle: Cycle = t_cycle
        self._spiral: Spiral  = Spiral()

    @property
    def cardinality(self) -> int:
        if len(self._wisdom_units) > 0:
            return len(self._wisdom_units)
        else:
            raise ValueError("The wheel is empty, therefore no main segment exists.")

    @property
    def wisdom_units(self) -> List[WisdomUnit]:
        return self._wisdom_units

    @property
    def main_wisdom_unit(self) -> WisdomUnit:
        if len(self._wisdom_units) > 0:
            return self._wisdom_units[0]
        else:
            raise ValueError("The wheel is empty, therefore no main segment exists.")

    @property
    def theses(self) -> DialecticalComponentsDeck:
        theses_from_wheels = []
        for wu in self.wisdom_units:
            theses_from_wheels.append(wu.t)

        return DialecticalComponentsDeck(dialectical_components=theses_from_wheels)

    def wisdom_unit_at(self, i: int|str|WheelSegment) -> WisdomUnit:
        if isinstance(i, WisdomUnit) and i in self.wisdom_units:
            return i

        if isinstance(i, WheelSegment):
            for wu in self.wisdom_units:
                if wu.t.alias == i.t.alias or wu.a.alias == i.t.alias:
                    return wu
            raise ValueError(f"Cannot find wisdom unit at: {i.t.alias}")
        elif isinstance(i, str):
            for wu in self.wisdom_units:
                if wu.t.alias == i or wu.a.alias == i:
                    return wu
        elif isinstance(i, int):
            if i < 0 or i >= len(self.wisdom_units):
                raise IndexError(f"index {i} out of range for wheel of length {len(self.wisdom_units)}")
            return self.wisdom_units[i]

        raise ValueError(f"Cannot find wisdom unit at: {i}")

    @property
    def orthogonal_wisdom_unit(self) -> WisdomUnit:
        """
        Raises:
            ValueError: If the number of segments is not even.

        Returns:
            WisdomUnit: The orthogonal segment
        """
        n = len(self._wisdom_units)
        if n == 0:
            raise ValueError(
                "The wheel is empty, therefore no orthogonal segment exists."
            )
        if n % 2 == 0:
            return self._wisdom_units[n // 2]
        else:
            raise ValueError("The wheel is not balanced orthogonally.")

    def spin(
        self,
        offset: int = 1,
    ) -> List[WisdomUnit]:
        # TODO: do we ned to also adjust the cycle and spiral?
        """
        Rotate the synthesis-pair list by ``offset`` positions.

        Parameters
        ----------
        offset : int
            How far to rotate. Positive values rotate left; negative values
            rotate right.
        """
        n = len(self._wisdom_units)
        if n == 0:
            raise ValueError("Cannot spin an empty wheel")

        if not -n <= offset < n:
            raise IndexError(
                f"spin offset {offset} out of range for list of length {n}"
            )

        offset %= n  # bring offset into the list's range

        def rot(lst: List) -> List:
            return lst[offset:] + lst[:offset]

        self._wisdom_units[:] = rot(self._wisdom_units)

        return self._wisdom_units

    @property
    def cycle(self) -> Cycle:
        return self._ta_cycle

    @property
    def t_cycle(self) -> Cycle:
        return self._t_cycle

    @property
    def spiral(self) -> Spiral:
        return self._spiral

    def __str__(self):
        table = self._print_wheel_tables()

        output = (
                "\n---\n".join([self.t_cycle.pretty(skip_dialectical_component_explanation=True) if self.t_cycle else ""]) +
                ("\n---\n" if self.t_cycle else "") +
                "\n---\n".join([self.cycle.pretty(skip_dialectical_component_explanation=True) if self.cycle else ""]) +
                ("\n---\n" if self.cycle else "") +
                table
        )

        return output




    def _print_wheel_tables(self) -> str:
        roles = [
            ('t_minus', 'T-'),
            ('t', 'T'),
            ('t_plus', 'T+'),
            ('a_plus', 'A+'),
            ('a', 'A'),
            ('a_minus', 'A-'),
        ]

        n_units = len(self._wisdom_units)

        # Create headers: WU1_alias, WU1_statement, (transition1), WU2_alias, ...
        headers = []
        for i in range(n_units):
            headers.extend([f"Alias (WU{i + 1})", f"Statement (WU{i + 1})"])

        table = []
        # Build the table: alternate wisdom unit cells and transitions
        for role_attr, role_label in roles:
            row = []
            for i, wu in enumerate(self._wisdom_units):
                # Wisdom unit columns
                component = getattr(wu, role_attr, None)
                row.append(component.alias if component else '')
                row.append(component.statement if component else '')
            table.append(row)

        return tabulate(
            table,
            # headers=headers,
            tablefmt="plain")