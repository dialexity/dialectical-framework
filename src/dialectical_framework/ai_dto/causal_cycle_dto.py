
from pydantic import Field

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto


class CausalCycleDto(CausalCycleAssessmentDto):
    """
    Causal circular sequence of statements, where aliases reference each statement
    """

    aliases: list[str] = Field(
        ...,
        description="Aliases (not the explicit statements) arranged in the circular causality sequence (cycle) where the last element points to the first",
    )
