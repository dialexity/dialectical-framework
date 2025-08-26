from typing import List

from pydantic import BaseModel
from pydantic import Field

from dialectical_framework.ai_structured_data.causal_cycle_assessment import CausalCycleAssessment


class CausalCycle(CausalCycleAssessment):
    """
    Causal circular sequence of statements, where aliases reference each statement
    """
    aliases: List[str] = Field(
        ...,
        description="Aliases (not the explicit statements) arranged in the circular causality sequence (cycle) where the last element points to the first",
    )
