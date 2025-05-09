from __future__ import annotations
from typing import Any, Iterable, overload, Iterator, Optional, List

from dialectical_framework.wisdom_unit import WisdomUnit


class Wheel(Iterable[WisdomUnit]):
    _ordered_wisdom_units: list[WisdomUnit] = []

    @overload
    def __init__(self, *wisdom_units: WisdomUnit) -> None: ...

    @overload
    def __init__(self, wisdom_units: Iterable[WisdomUnit]) -> None: ...

    def __init__(self, *wisdom_units):
        # One iterable argument → use it directly
        if len(wisdom_units) == 1 and not isinstance(wisdom_units[0], WisdomUnit):
            self._ordered_wisdom_units = list(wisdom_units[0])
        else:  # One or more Wheel2 positional args
            self._ordered_wisdom_units = list(wisdom_units)

    def __iter__(self) -> Iterator[WisdomUnit]:
        return iter(self._ordered_wisdom_units)

    @property
    def wisdom_units(self) -> list[WisdomUnit]:
        return self._ordered_wisdom_units

    @property
    def main_wisdom_unit(self) -> WisdomUnit:
        if len(self._ordered_wisdom_units) > 0:
            return self._ordered_wisdom_units[0]
        else:
            raise ValueError("The wheel is empty, therefore no main segment exists.")

    @property
    def orthogonal_wisdom_unit(self) -> WisdomUnit:
        """
        Raises:
            ValueError: If the number of segments is not even.

        Returns:
            WisdomUnit: The orthogonal segment
        """
        n = len(self._ordered_wisdom_units)
        if n == 0:
            raise ValueError(
                "The wheel is empty, therefore no orthogonal segment exists."
            )
        if n % 2 == 0:
            return self._ordered_wisdom_units[n // 2]
        else:
            raise ValueError("The wheel is not balanced orthogonally.")

    def spin(
        self,
        offset: int = 1,
        *,
        mutate: bool = True,
    ) -> List[WisdomUnit]:
        """
        Rotate the synthesis-pair list by ``offset`` positions.

        Parameters
        ----------
        offset : int
            How far to rotate. Positive values rotate left; negative values
            rotate right.
        mutate : bool, default True
            • True → rotate the internal list in place and return it.
            • False → leave internal state untouched and return a rotated copy.
        """
        n = len(self._ordered_wisdom_units)
        if n == 0:
            raise ValueError("Cannot spin an empty wheel")

        if not -n <= offset < n:
            raise IndexError(
                f"spin offset {offset} out of range for list of length {n}"
            )

        offset %= n  # bring offset into the list’s range

        rotated = (
            self._ordered_wisdom_units[offset:] + self._ordered_wisdom_units[:offset]
        )

        if mutate:
            # update in place
            self._ordered_wisdom_units[:] = rotated
            return self.wisdom_units

        # return a copy, leave the internal list unchanged
        return rotated
