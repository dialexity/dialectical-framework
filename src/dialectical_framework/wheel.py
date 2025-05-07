from __future__ import annotations
from typing import Any, Iterable, overload, Iterator, Optional, List

from dialectical_framework.wheel2 import Wheel2


class Wheel(Iterable[Wheel2]):
    _ordered_synthesis_pairs: list[Wheel2] = []

    @overload
    def __init__(self, *synthesis_pairs: Wheel2) -> None: ...

    @overload
    def __init__(self, synthesis_pairs: Iterable[Wheel2]) -> None: ...

    def __init__(self, *synthesis_pairs):
        # One iterable argument → use it directly
        if len(synthesis_pairs) == 1 and not isinstance(synthesis_pairs[0], Wheel2):
            self._ordered_synthesis_pairs = list(synthesis_pairs[0])
        else:  # One or more Wheel2 positional args
            self._ordered_synthesis_pairs = list(synthesis_pairs)

    def __iter__(self) -> Iterator[Wheel2]:
        return iter(self._ordered_synthesis_pairs)

    @property
    def synthesis_pairs(self) -> list[Wheel2]:
        return self._ordered_synthesis_pairs

    @property
    def main_synthesis_pair(self) -> Wheel2:
        if len(self._ordered_synthesis_pairs) > 0:
            return self._ordered_synthesis_pairs[0]
        else:
            raise ValueError("The wheel is empty, therefore no main segment exists.")

    @property
    def orthogonal_synthesis_pair(self) -> Wheel2:
        """
        Raises:
            ValueError: If the number of segments is not even.

        Returns:
            Wheel2: The orthogonal segment
        """
        n = len(self._ordered_synthesis_pairs)
        if n == 0:
            raise ValueError("The wheel is empty, therefore no orthogonal segment exists.")
        if n % 2 == 0:
            return self._ordered_synthesis_pairs[n // 2]
        else:
            raise ValueError("The wheel is not balanced orthogonally.")

    def spin(
            self,
            offset: int = 1,
            *,
            mutate: bool = True,
    ) -> List[Wheel2]:
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
        n = len(self._ordered_synthesis_pairs)
        if n == 0:
            raise ValueError("Cannot spin an empty wheel")

        if not -n <= offset < n:
            raise IndexError(
                f"spin offset {offset} out of range for list of length {n}"
            )

        offset %= n  # bring offset into the list’s range

        rotated = (
                self._ordered_synthesis_pairs[offset:]
                + self._ordered_synthesis_pairs[:offset]
        )

        if mutate:
            # update in place
            self._ordered_synthesis_pairs[:] = rotated
            return self.synthesis_pairs

        # return a copy, leave the internal list unchanged
        return rotated
