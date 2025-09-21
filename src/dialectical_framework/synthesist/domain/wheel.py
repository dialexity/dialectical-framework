from __future__ import annotations

from typing import List, Union, Any, Dict, TYPE_CHECKING

from tabulate import tabulate

if TYPE_CHECKING:
    from dialectical_framework.analyst.domain.cycle import Cycle
    from dialectical_framework.analyst.domain.spiral import Spiral
    from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit

WheelSegmentReference = Union[int, WheelSegment, str, DialecticalComponent]


class Wheel(Assessable):
    def __init__(self, *wisdom_units, t_cycle: "Cycle", ta_cycle: "Cycle", **kwargs):
        super().__init__(**kwargs)

        # One iterable argument → use it directly
        if len(wisdom_units) == 1 and not isinstance(wisdom_units[0], WisdomUnit):
            self._wisdom_units: list[WisdomUnit] = list(wisdom_units[0])
        else:
            self._wisdom_units: list[WisdomUnit] = list(wisdom_units)

        self._ta_cycle: "Cycle" = ta_cycle
        self._t_cycle: "Cycle" = t_cycle
        
        # Import Spiral at runtime to avoid circular imports
        from dialectical_framework.analyst.domain.spiral import Spiral
        self._spiral: Spiral = Spiral()

    @property
    def order(self) -> int:
        """The order of the wheel (number of wisdom units in the dialectical structure)"""
        if len(self._wisdom_units) == 0:
            raise ValueError("The wheel is empty, therefore order is undefined.")
        return len(self._wisdom_units)

    @property
    def degree(self) -> int:
        """The degree of the wheel (total number of segments = 2 × order)"""
        return self.order * 2

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        result.extend(self._wisdom_units)
        result.append(self._t_cycle)
        result.append(self._ta_cycle)
        result.append(self._spiral)
        return result

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        """
        Calculates the WheelFidelity as the geometric mean of:
        1. All individual DialecticalComponent relevance scores across the entire wheel
        2. All wheel-level rationales/opinions (weighted by their rating)
        
        Components with relevance of 0.0 or None are excluded from the calculation.
        """
        # Import at runtime to avoid circular imports
        from dialectical_framework.analyst.domain.transition import Transition
        
        parts = []

        # Collect from wisdom units
        for wu in self._wisdom_units:
            relevance = wu.calculate_relevance()
            if relevance is not None and relevance > 0.0:
                parts.append(relevance)

        # Collect transitions from cycles without overlaps
        unique_transitions: Dict[Any, Transition] = {}

        # Get transitions from t_cycle (most generic)
        if self.t_cycle.graph and not self.t_cycle.graph.is_empty():
            for transition in self.t_cycle.graph.get_all_transitions():
                unique_transitions[transition.get_key()] = transition

        # Get transitions from ta_cycle (more specific than t_cycle, so we prefer this)
        if self.cycle.graph and not self.cycle.graph.is_empty():
            for transition in self.cycle.graph.get_all_transitions():
                if transition.get_key() in unique_transitions:
                    # calculate the one which is being overwritten
                    unique_transitions[transition.get_key()].calculate_relevance()
                # take the more specific one
                unique_transitions[transition.get_key()] = transition

        # Get transitions from spiral (even more specific, than ta_cycle, so we prefer this)
        if self.spiral.graph and not self.spiral.graph.is_empty():
            for transition in self.spiral.graph.get_all_transitions():
                if transition.get_key() in unique_transitions:
                    # calculate the one which is being overwritten
                    unique_transitions[transition.get_key()].calculate_relevance()
                # take the more specific one
                unique_transitions[transition.get_key()] = transition
        
        # Extract relevance scores from unique transitions
        for transition in unique_transitions.values():
            transition_relevance = transition.calculate_relevance()
            if transition_relevance is not None and transition_relevance > 0.0:
                parts.append(transition_relevance)


        return parts

    def calculate_probability(self) -> float | None:
        """
        Wheel Pr = GM over a fixed canonical set of cycle probabilities (T, TA, Spiral).
        - Keep 0.0 (impossibility ⇒ 0).
        - Skip None (unknown).
        - If all canonical cycles are None ⇒ None.
        Optionally add a single summarized term for unit transformations (see note).
        """
        # 1) Canonical cycles (ensure these are EXTERNAL transitions only)
        canonical_vals = []
        for cyc in (self._t_cycle, self._ta_cycle, self._spiral):
            p = cyc.calculate_probability()
            if p is not None:
                canonical_vals.append(p)

        # 2) Optional: summarize unit transformations ONCE (only if not already in canonical cycles)
        internal_summary = None
        unit_vals = []
        for wu in self._wisdom_units:
            p = wu.calculate_probability()  # Pr of the unit’s internal 2-edge Transformation
            if p is not None:
                unit_vals.append(p)
        if unit_vals:
            internal_summary = gm_with_zeros_and_nones_handled(unit_vals)

        # Build final list (omit internal_summary if your canonical cycles include internal edges)
        all_terms = list(canonical_vals)
        if internal_summary is not None:
            all_terms.append(internal_summary)

        self.calculated_probability = gm_with_zeros_and_nones_handled(all_terms)
        return self.probability

    @property
    def wisdom_units(self) -> list[WisdomUnit]:
        return self._wisdom_units

    @property
    def main_wisdom_unit(self) -> WisdomUnit:
        if len(self._wisdom_units) > 0:
            return self._wisdom_units[0]
        else:
            raise ValueError("The wheel is empty.")

    def is_set(self, s: str | DialecticalComponent | WheelSegment) -> bool:
        try:
            self.wisdom_unit_at(s)
        except ValueError:
            return False
        else:
            return True

    def is_same_structure(self, other: Wheel) -> bool:
        if len(self.wisdom_units) != len(other.wisdom_units):
            return False
        for wu in self.wisdom_units:
            if not other.is_set(wu):
                return False

        return self.t_cycle.is_same_structure(
            other.t_cycle
        ) and self.cycle.is_same_structure(other.cycle)

    def wisdom_unit_at(self, i: WheelSegmentReference) -> WisdomUnit:
        """
        Determines and retrieves a WisdomUnit based on the input index or key.

        This method identifies and returns a specific WisdomUnit from the collection
        of WisdomUnits maintained by the object. The input can be provided as an integer
        index, string key, or an instance of the WheelSegment, with distinct lookup
        logic applied for each type. If the input does not correspond to
        a valid WisdomUnit, an exception is raised.

        Parameters:
        i : int | str | WheelSegment
            The input used to locate a specific WisdomUnit. Can be an integer
            index of a wisdom unit, a string alias of a dialectical component, or an instance of the WheelSegment.

        Returns:
        WisdomUnit
            The WisdomUnit corresponding to the provided input.

        Raises:
        IndexError
            If the integer input is out of range for the collection of WisdomUnits.
        ValueError
            If the input of type WheelSegment or string does not correspond to
            a valid WisdomUnit in the collection.
        """
        if isinstance(i, WisdomUnit):
            for wu in self.wisdom_units:
                if wu.is_same(i):
                    return wu
        elif isinstance(i, WheelSegment):
            for wu in self.wisdom_units:
                if wu.extract_segment_t().is_same(i) or wu.extract_segment_a().is_same(
                    i
                ):
                    return wu
            raise ValueError(f"Cannot find wisdom unit at: {i.t.alias}")
        elif isinstance(i, str) or isinstance(i, DialecticalComponent):
            for wu in self.wisdom_units:
                if wu.is_set(i):
                    return wu
        elif isinstance(i, int):
            if i < 0 or i >= len(self.wisdom_units):
                raise IndexError(
                    f"index {i} out of range for wheel of length {len(self.wisdom_units)}"
                )
            return self.wisdom_units[i]

        raise ValueError(f"Cannot find wisdom unit at: {i}")

    def wheel_segment_at(self, i: int | str | DialecticalComponent) -> WheelSegment:
        """
        Retrieves a specific wheel segment from the wisdom units based on the provided index or component.

        The method allows accessing a wheel segment by an integer index, a string, or a DialecticalComponent.
        If an integer index is provided, it is validated to ensure it lies within the appropriate range and then
        used to determine the specific segment from a sequence of wisdom units. For string or DialecticalComponent
        inputs, the method searches through the wisdom units to locate and return the segment containing the
        specified component.

        Raises:
            IndexError: If the integer index is out of the valid range.
            ValueError: If no wisdom unit or segment corresponding to the given identifier is found.

        Args:
            i: The index of the wheel segment as an integer or the identifier of the component
               as a string or DialecticalComponent.

        Returns:
            The matching WheelSegment extracted from the appropriate wisdom unit.
        """
        if isinstance(i, int):
            total_segments = self.degree
            if i < 0 or i >= total_segments:
                raise IndexError(
                    f"index {i} out of range for wheel of {total_segments} segments"
                )
            wu_index = i % self.order
            wu = self.wisdom_units[wu_index]
            return wu.extract_segment_t() if i < self.order else wu.extract_segment_a()
        elif isinstance(i, str) or isinstance(i, DialecticalComponent):
            for wu in self.wisdom_units:
                if wu.is_set(i):
                    segment_t = wu.extract_segment_t()
                    if segment_t.is_set(i):
                        return segment_t
                    segment_a = wu.extract_segment_a()
                    if segment_a.is_set(i):
                        return segment_a
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
    ) -> list[WisdomUnit]:
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

    def index_of(self, ws: WheelSegment) -> int:
        for i, wu in enumerate(self._wisdom_units):
            if wu.extract_segment_t().is_same(ws):
                return i
            if wu.extract_segment_a().is_same(ws):
                return i + self.order
        # Should never happen
        return -1

    def __str__(self):
        main_segment = self.main_wisdom_unit
        output = (
            "\n---\n"
            + self.t_cycle.pretty(
                skip_dialectical_component_explanation=True, start_alias=main_segment.t
            )
            + "\n---\n"
            + "\n---\n"
            + self.cycle.pretty(
                skip_dialectical_component_explanation=True, start_alias=main_segment.t
            )
            + "\n---\n"
            + self._print_wheel_tabular()
            + "\n---\n"
            + self.spiral.pretty(start_wheel_segment=main_segment)
            + "\n---\n"
        )

        return output

    def _print_wheel_tabular(self) -> str:
        roles = [
            ("t_minus", "T-"),
            ("t", "T"),
            ("t_plus", "T+"),
            ("a_plus", "A+"),
            ("a", "A"),
            ("a_minus", "A-"),
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
                row.append(component.alias if component else "")
                row.append(component.statement if component else "")
            table.append(row)

        return tabulate(
            table,
            # headers=headers,
            tablefmt="plain",
        )
