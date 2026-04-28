"""
WheelSegmentPolarPair for graph-based dialectical framework.

This module provides a flexible "window" into a Perspective with swappable polarity,
allowing you to view the dialectical structure from different viewpoints:
- Normal polarity: T-side has theses (T, T+, T-), A-side has antitheses (A, A+, A-)
- Swapped polarity: T-side has antitheses (A, A+, A-), A-side has theses (T, T+, T-)
"""

from __future__ import annotations

from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

from dialectical_framework.graph.wheel_segment import WheelSegment


class WheelSegmentPolarPair:
    """
    A "window" into a Perspective with swappable polarity.

    Provides two sides (segment_left and segment_right) where the polarity determines
    which components appear on which side:
    - "normal": Left has theses (T, T+, T-), right has antitheses (A, A+, A-)
    - "swapped": Left has antitheses (A, A+, A-), right has theses (T, T+, T-)

    This allows viewing the same dialectical structure from different viewpoints,
    which can be useful for:
    - Exploring alternative interpretations
    - Testing symmetry of arguments
    - Educational demonstrations of dialectical flexibility

    Example:
        # Normal polarity view
        pair = WheelSegmentPolarPair(pp, "normal")
        thesis = pair.segment_left.t.get()  # Gets T component
        antithesis = pair.segment_right.t.get()  # Gets A component

        # Swapped polarity view
        pair = WheelSegmentPolarPair(pp, "swapped")
        antithesis = pair.segment_left.t.get()  # Gets A component (swapped!)
        thesis = pair.segment_right.t.get()  # Gets T component (swapped!)
    """

    def __init__(
        self,
        perspective: Perspective,
        polarity: Literal["normal", "swapped"] = "normal",
        t_segment: Optional[WheelSegment] = None,
        a_segment: Optional[WheelSegment] = None
    ):
        """
        Initialize a polar wheel segment pair.

        Args:
            perspective: The Perspective to view
            polarity: Either "normal" (T=thesis, A=antithesis) or
                     "swapped" (T=antithesis, A=thesis)
            t_segment: Optional existing T-side WheelSegment to reuse
            a_segment: Optional existing A-side WheelSegment to reuse
        """
        if polarity not in ('normal', 'swapped'):
            raise ValueError(f"polarity must be 'normal' or 'swapped', got: {polarity}")

        self._perspective = perspective
        self._polarity = polarity

        # Use existing segments or create new ones
        if t_segment is None:
            t_segment = WheelSegment(perspective, "T")
        if a_segment is None:
            a_segment = WheelSegment(perspective, "A")

        # Configure sides based on polarity
        # _left and _right are positional properties that map to T/A segments based on polarity
        if polarity == "normal":
            # Normal: Left shows T components, right shows A components
            self._left = t_segment
            self._right = a_segment
        else:
            # Swapped: Left shows A components, right shows T components
            self._left = a_segment
            self._right = t_segment

    @property
    def perspective(self) -> Perspective:
        """Get the Perspective being viewed."""
        return self._perspective

    @property
    def polarity(self) -> Literal["normal", "swapped"]:
        """Get the polarity configuration ('normal' or 'swapped')."""
        return self._polarity

    @property
    def segment_left(self) -> WheelSegment:
        """
        Get the left side segment.

        In normal polarity: Contains T, T+, T- components (thesis side)
        In swapped polarity: Contains A, A+, A- components (antithesis side)
        """
        return self._left

    @property
    def segment_right(self) -> WheelSegment:
        """
        Get the right side segment.

        In normal polarity: Contains A, A+, A- components (antithesis side)
        In swapped polarity: Contains T, T+, T- components (thesis side)
        """
        return self._right

    def swap(self) -> None:
        """
        Swap the polarity in place.

        Swaps t_side and a_side and updates the polarity state.

        Example:
            pair = WheelSegmentPolarPair(pp, "normal")
            assert pair.polarity == "normal"
            pair.swap()
            assert pair.polarity == "swapped"
            pair.swap()
            assert pair.polarity == "normal"
        """
        # Swap the sides
        self._left, self._right = self._right, self._left

        # Update polarity
        self._polarity = "swapped" if self._polarity == "normal" else "normal"

    def get_component(self, alias: str) -> Optional[DialecticalComponent]:
        """
        Find a component by its alias, searching both sides.

        Args:
            alias: The alias to search for (e.g., "T", "T+", "A-")

        Returns:
            The matching component, or None if not found
        """
        return self.perspective.get_component(alias)

    def is_complete(self) -> bool:
        """
        Check if both sides are complete.

        Returns:
            True if both segment_left and segment_right have all components populated
        """
        return self._left.is_complete() and self._right.is_complete()

    def __format__(self, format_spec: str) -> str:
        """
        Format this WheelSegmentPolarPair using Python's format string protocol.

        Formats both segments (left and right) in the order determined by polarity.

        Format Specifications:
        ----------------------
        [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored
            "positions" - Uses canonical positions
            "strip_index" - Strips numeric indexes
            "full" - Vertical layout with synthesis + segments + transformation
            "full:compact" - Tabular layout with synthesis + segments side-by-side

        Newlines (optional, for non-"full" modes):
            :0 - Comma separation (compact single line, NO explanations)
            :1 - Single newline between components (compact)
            :2 - Double newline between components (spacious, default)

        Examples:
        ---------
        f"{pair}"              - Default format (6 components vertically)
        f"{pair:positions}"    - Canonical positions
        f"{pair::0}"           - Compact (comma separated, no explanations)
        f"{pair:full}"         - Full vertical layout
        f"{pair:full:compact}" - Full tabular layout

        Returns:
            Formatted string with both segments
        """
        # Handle "full" modes specially
        if format_spec.startswith("full"):
            if format_spec == "full:compact":
                return self._format_full_compact()
            else:
                return self._format_full()

        # For regular modes, format both segments and join
        left_formatted = self._left.__format__(format_spec)
        right_formatted = self._right.__format__(format_spec)

        # Determine separator based on newlines parameter
        if ":0" in format_spec:
            # Comma separated - join both segments
            return f"{left_formatted}, {right_formatted}"
        else:
            # Newline separated - join with one extra newline between segments
            # Parse newlines from format_spec
            if ":" in format_spec:
                _, newlines_str = format_spec.split(":", 1)
                try:
                    newlines = int(newlines_str)
                except ValueError:
                    newlines = 2
            else:
                newlines = 2

            if newlines < 1:
                segment_separator = "\n"
            else:
                segment_separator = "\n" * newlines

            return f"{left_formatted}{segment_separator}{right_formatted}"

    def _format_full(self) -> str:
        """
        Format in full mode: Synthesis, both segments, Transformation, Rationales (vertical).

        Returns:
            Formatted string with all sections separated vertically
        """
        from tabulate import tabulate
        sections = []

        # Section 1: Synthesis (now on Perspective, not transformation)
        synthesis_list = list(self._perspective.synthesis.all())

        if synthesis_list:
            synthesis_parts = ["=== Synthesis ==="]

            for synthesis, _ in synthesis_list:
                synthesis_parts.append(f"{synthesis}")

            sections.append("\n\n".join(synthesis_parts))

        # Section 2: Both segments (6 core positions total)
        sections.append("=== Perspective ===")
        sections.append(self.__format__(""))  # Default format with explanations

        # Section 3: Transformation (if exists)
        transformation_result = self._perspective.transformations.get()
        if transformation_result:
            transformation, _ = transformation_result
            sections.append("=== Transformation ===")
            sections.append(f"{transformation}")

        # Section 4: Rationales (2-column table)
        sections.append("=== Rationales ===")

        # Collect rationales from each source
        pp_rationales = [r.text for r, _ in self._perspective.rationales.all() if r.text]

        trans_rationales = []
        if transformation_result:
            transformation, _ = transformation_result
            trans_rationales = [r.text for r, _ in transformation.rationales.all() if r.text]

        # Build rationale table (2 columns: PP | Transformation)
        max_rows = max(len(pp_rationales), len(trans_rationales), 0)

        if max_rows > 0:
            rationale_table = []
            for i in range(max_rows):
                row = [
                    pp_rationales[i] if i < len(pp_rationales) else "",
                    trans_rationales[i] if i < len(trans_rationales) else "",
                ]
                rationale_table.append(row)

            # Add headers
            headers = ["Perspective", "Transformation"]
            sections.append(tabulate(rationale_table, headers=headers, tablefmt="plain"))
        else:
            sections.append("[No rationales]")

        return "\n\n".join(sections)

    def _format_full_compact(self) -> str:
        """
        Format in full compact mode: Synthesis first, then segments side-by-side.

        Returns:
            Formatted string with synthesis vertical, then segments tabular without explanations
        """
        from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship
        from tabulate import tabulate

        lines = []

        # Section 1: Synthesis (now on PP, not transformation)
        synthesis_list = list(self._perspective.synthesis.all())

        if synthesis_list:
            lines.append("=== Synthesis ===")

            for synthesis, _ in synthesis_list:
                s_plus_result = synthesis.s_plus.get()
                s_minus_result = synthesis.s_minus.get()

                if s_plus_result:
                    s_plus_comp, s_plus_rel = s_plus_result
                    assert isinstance(s_plus_rel, PolarityRelationship)
                    lines.append(f"{s_plus_rel.alias} = {s_plus_comp:short}")

                if s_minus_result:
                    s_minus_comp, s_minus_rel = s_minus_result
                    assert isinstance(s_minus_rel, PolarityRelationship)
                    lines.append(f"{s_minus_rel.alias} = {s_minus_comp:short}")

            lines.append("")  # Blank line separator

        # Section 2: Perspective and Transformation side-by-side (tabular)
        lines.append("=== Perspective / Transformation ===")

        # Helper to get component info
        def _get_component_info(manager):
            result = manager.get()
            if result:
                component, rel = result
                assert isinstance(rel, PolarityRelationship)
                return rel.alias, component.statement
            return "", ""

        # Get Transformation (if exists) - transformation has its own 6 positions now
        transformation_result = self._perspective.transformations.get()
        transformation = None
        if transformation_result:
            transformation, _ = transformation_result

        # Build table rows: one row per position
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
            POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS
        )
        from dialectical_framework.graph.nodes.transformation import (
            POSITION_AC, POSITION_RE,
            POSITION_AC_PLUS, POSITION_AC_MINUS,
            POSITION_RE_PLUS, POSITION_RE_MINUS,
        )

        # Map PP positions to Transformation positions for side-by-side display
        pp_to_trans_position = {
            POSITION_T: POSITION_AC,
            POSITION_T_PLUS: POSITION_AC_PLUS,
            POSITION_T_MINUS: POSITION_AC_MINUS,
            POSITION_A: POSITION_RE,
            POSITION_A_PLUS: POSITION_RE_PLUS,
            POSITION_A_MINUS: POSITION_RE_MINUS,
        }

        positions = [
            (POSITION_T_MINUS, "t_minus"),
            (POSITION_T, "t"),
            (POSITION_T_PLUS, "t_plus"),
            (POSITION_A_PLUS, "t_plus"),
            (POSITION_A, "t"),
            (POSITION_A_MINUS, "t_minus"),
        ]

        table = []
        for i, (position_label, attr_name) in enumerate(positions):
            row = []

            # Determine which segment to use (left 3 = left segment, right 3 = right segment)
            segment = self._left if i < 3 else self._right
            pp_manager = getattr(segment, attr_name)
            pp_alias, pp_statement = _get_component_info(pp_manager)
            row.append(pp_alias)
            row.append(pp_statement)

            # Transformation column (if exists)
            if transformation:
                trans_position = pp_to_trans_position.get(position_label)
                if trans_position:
                    trans_manager = transformation.get_relationship_manager_by_position(trans_position)
                    trans_alias, trans_statement = _get_component_info(trans_manager)
                    row.append(trans_alias)
                    row.append(trans_statement)

            table.append(row)

        lines.append(tabulate(table, tablefmt="plain"))

        # Section 3: Rationales (2-column table: PP, Transformation)
        lines.append("")
        lines.append("=== Rationales ===")

        # Collect rationales from each source
        pp_rationales = [r.text for r, _ in self._perspective.rationales.all() if r.text]

        trans_rationales = []
        if transformation_result:
            transformation, _ = transformation_result
            trans_rationales = [r.text for r, _ in transformation.rationales.all() if r.text]

        # Build rationale table (2 columns: PP | Transformation)
        max_rows = max(len(pp_rationales), len(trans_rationales))

        if max_rows > 0:
            rationale_table = []
            for i in range(max_rows):
                row = [
                    pp_rationales[i] if i < len(pp_rationales) else "",
                    trans_rationales[i] if i < len(trans_rationales) else "",
                ]
                rationale_table.append(row)

            # Add headers
            headers = ["Perspective", "Transformation"]
            lines.append(tabulate(rationale_table, headers=headers, tablefmt="plain"))
        else:
            lines.append("[No rationales]")

        return "\n".join(lines)

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def __repr__(self) -> str:
        """Debug representation of the pair."""
        return (
            f"WheelSegmentPolarPair("
            f"polarity={self._polarity}, "
            f"perspective={self._perspective.hash}, "
            f"left={self._left.side}, "
            f"right={self._right.side})"
        )
