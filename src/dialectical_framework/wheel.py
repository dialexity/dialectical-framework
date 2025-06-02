from __future__ import annotations

from typing import Iterable, Iterator, List, overload

from tabulate import tabulate

from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.symmetrical_transition import SymmetricalTransition
from dialectical_framework.wisdom_unit import WisdomUnit


class Wheel(Iterable[WisdomUnit]):
    def __init__(self, *wisdom_units):
        # One iterable argument → use it directly
        if len(wisdom_units) == 1 and not isinstance(wisdom_units[0], WisdomUnit):
            self._wisdom_units = list(wisdom_units[0])
        else:
            self._wisdom_units = list(wisdom_units)

        self._cycle: Cycle | None = None
        if len(self._wisdom_units) > 0:
            self._transitions: List[SymmetricalTransition | None] = [None] * len(self._wisdom_units)
        else:
            self._transitions: List[SymmetricalTransition | None] = []

    def __iter__(self) -> Iterator[WisdomUnit]:
        return iter(self._wisdom_units)

    @property
    def wisdom_units(self) -> list[WisdomUnit]:
        return self._wisdom_units

    @property
    def main_wisdom_unit(self) -> WisdomUnit:
        if len(self._wisdom_units) > 0:
            return self._wisdom_units[0]
        else:
            raise ValueError("The wheel is empty, therefore no main segment exists.")

    @property
    def transitions(self) -> List[SymmetricalTransition]:
        return self._transitions

    @property
    def theses(self) -> DialecticalComponentsDeck:
        theses_from_wheels = []
        for wu in self.wisdom_units:
            theses_from_wheels.append(wu.t)

        return DialecticalComponentsDeck(dialectical_components=theses_from_wheels)

    def transition_at(self, i: int) -> SymmetricalTransition | None:
        """Edge from unit i → unit (i+1)."""
        idx = i % len(self._transitions)
        if i < 0 or i >= len(self._transitions):
            raise IndexError(f"index {i} out of range for wheel of length {len(self._transitions)}")

        return self._transitions[idx]


    def add_transition(self, at: int, tr: SymmetricalTransition) -> None:
        idx = at % len(self._transitions)
        if at < 0 or at >= len(self._transitions):
            raise IndexError(f"index {at} out of range for wheel of length {len(self._transitions)}")
        self._transitions[idx] = tr

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

        offset %= n  # bring offset into the list’s range

        def rot(lst: List) -> List:
            return lst[offset:] + lst[:offset]

        self._wisdom_units[:] = rot(self._wisdom_units)
        self._transitions[:] = rot(self._transitions)

        return self._wisdom_units

    @property
    def cycle(self) -> Cycle:
        return self._cycle

    @cycle.setter
    def cycle(self, cycle: Cycle):
        # TODO: not good to have mutability here, as wisdom units may be swapped or rearranged...
        self._cycle = cycle

    def __str__(self):
        # TODO: also add transitions

        table = self._print_wheel_tables()

        output = (
                "\n---\n".join([self.cycle.pretty(skip_dialectical_component_explanation=True) if self.cycle else ""]) +
                ("\n---\n" if self.cycle else "") +
                table
        )

        return output

    def _print_wheel_tables(self):
        roles = [
            ('t_minus', 'T-'),
            ('t', 'T'),
            ('t_plus', 'T+'),
            ('a_plus', 'A+'),
            ('a', 'A'),
            ('a_minus', 'A-'),
        ]

        n_units = len(self._wisdom_units)
        has_transitions = hasattr(self, "_transitions") and self._transitions is not None

        # Create headers: WU1_alias, WU1_statement, (transition1), WU2_alias, ...
        headers = []
        for i in range(n_units):
            headers.extend([f"Alias (WU{i + 1})", f"Statement (WU{i + 1})"])
            if has_transitions and i < n_units:
                # Add a transition column after each wisdom unit except the last (cycle or not)
                headers.extend([f"Transition ({i + 1}→{(i + 2) if i + 1 < n_units else 1})", " "])

        table = []
        # Build the table: alternate wisdom unit cells and transitions
        for role_attr, role_label in roles:
            row = []
            for i, wu in enumerate(self._wisdom_units):
                # Wisdom unit columns
                component = getattr(wu, role_attr, None)
                row.append(component.alias if component else '')
                row.append(component.statement if component else '')
                # Transition columns
                if has_transitions:
                    # Add a transition after each wisdom unit
                    if i < len(self._transitions):
                        tr = self._transitions[i]
                        if tr is not None:
                            ac_re: WisdomUnit | None = tr.action_reflection
                            if ac_re:
                                component = getattr(ac_re, role_attr, None)
                                row.append(component.alias if component else '')
                                row.append(component.statement if component else '')
            table.append(row)

        return tabulate(
            table,
            # headers=headers,
            tablefmt="plain")


