from pydantic import Field

from dialectical_framework.reciprocal_solution import ReciprocalSolution
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.wisdom_unit import WisdomUnit

ALIAS_AC = "Ac"
ALIAS_AC_PLUS = "Ac+"
ALIAS_AC_MINUS = "Ac-"
ALIAS_RE = "Re"
ALIAS_RE_PLUS = "Re+"
ALIAS_RE_MINUS = "Re-"


class SymmetricalTransition(TransitionSegmentToSegment):
    reciprocal_solution: ReciprocalSolution | None = Field(
        default=None,
        description="Dialectically balanced solution (strategic action plan)",
    )
    action_reflection: WisdomUnit | None = Field(
        default=None,
        description="Condensed solution that encompasses both linear action  and dialectical reflections",
    )

    opposite_source_aliases: list[str] = Field(
        default_factory=list, description="Aliases of the source segment of the wheel."
    )
    opposite_target_aliases: list[str] = Field(
        default_factory=list, description="Aliases of the target segment of the wheel."
    )

    def pretty(self) -> str:
        str_pieces = [super().pretty()]
        if self.reciprocal_solution:
            str_pieces.append("\nRECIPROCAL SOLUTION:")
            str_pieces.append(str(self.reciprocal_solution))
        if self.action_reflection:
            str_pieces.append("\nACTION REFLECTION:")
            str_pieces.append(str(self.action_reflection))
        return "\n".join(str_pieces)

    def __str__(self):
        return self.pretty()
