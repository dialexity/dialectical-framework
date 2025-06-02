from pydantic import BaseModel, Field, ConfigDict

from dialectical_framework.reciprocal_solution import ReciprocalSolution
from dialectical_framework.transition import Transition
from dialectical_framework.wisdom_unit import WisdomUnit

ALIAS_AC = "Ac"
ALIAS_AC_PLUS = "Ac+"
ALIAS_AC_MINUS = "Ac-"
ALIAS_RE = "Re"
ALIAS_RE_PLUS = "Re+"
ALIAS_RE_MINUS = "Re-"

class SymmetricalTransition(Transition):
    reciprocal_solution: ReciprocalSolution | None = Field(default=None, description="Dialectically balanced solution (strategic action plan)")
    action_reflection: WisdomUnit | None = Field(default=None, description="Condensed solution that encompasses both linear action  and dialectical reflections")


