
from pydantic import Field, BaseModel

from dialectical_framework.ai_dto.causal_cycle_assessment_dto import \
    CausalCycleAssessmentDto


class ActionPlanDto(BaseModel):
    action_plan: str = Field(
        default="", description="Fluent action plan"
    )
