
from pydantic import Field, BaseModel

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto


class ActionPlanDto(BaseModel):
    probability: float = Field(
        default=0,
        description="The probability 0 to 1 of the transition.",
    )
    action_plan: str = Field(
        default="", description="Fluent action plan"
    )
