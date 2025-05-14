from __future__ import annotations

from typing import Iterable, Iterator, List, overload

from dialectical_framework.transition import Transition
from dialectical_framework.wisdom_unit import WisdomUnit


class Wheel(Iterable[WisdomUnit]):
    _wisdom_units: list[WisdomUnit] = []
    _transitions: List[Transition | None]

    @overload
    def __init__(self, *wisdom_units: WisdomUnit) -> None: ...

    @overload
    def __init__(self, wisdom_units: Iterable[WisdomUnit]) -> None: ...

    def __init__(self, *wisdom_units):
        # One iterable argument → use it directly
        if len(wisdom_units) == 1 and not isinstance(wisdom_units[0], WisdomUnit):
            self._wisdom_units = list(wisdom_units[0])
        else:  # One or more Wheel2 positional args
            self._wisdom_units = list(wisdom_units)

        if len(self._wisdom_units) > 0:
            self._transitions = [None] * len(self._wisdom_units)

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
    def transitions(self) -> List[Transition]:
        return self._transitions

    def transition_at(self, i: int) -> Transition | None:
        """Edge from unit i → unit (i+1)."""
        idx = i % len(self._transitions)
        if i < 0 or i >= len(self._transitions):
            raise IndexError(f"index {i} out of range for wheel of length {len(self._transitions)}")

        return self._transitions[idx]


    def add_transition(self, at: int, tr: Transition) -> None:
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
